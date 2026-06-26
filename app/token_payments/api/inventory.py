"""Framework-neutral store owner inventory API handlers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from token_payments.contexts.auth.domain import UserRole
from token_payments.contexts.inventory.application import (
    InventoryQueryRepository,
    InventorySnapshot,
    PauseProductSalesCommand,
    ResumeProductSalesCommand,
    StoreOwnerCorrectStockCommand,
    StoreOwnerIncreaseStockCommand,
    StoreOwnerInventoryCommandResult,
    StoreOwnerInventoryCommandStatus,
)
from token_payments.contexts.inventory.domain import InventorySaleStatus, ProductInventory
from token_payments.shared.domain import CommandId, ProductId, StoreId, UserId

from .contracts import ApiRequest, ApiResponse, json_response
from .idempotency import IdempotencyKeyConflict, idempotency_conflict_response, idempotency_key_from_request


class StoreOwnerInventoryApi:
    """Store-owner/admin inventory facade backed by application ports."""

    def __init__(self, *, query: InventoryQueryRepository, command_handler: Any | None) -> None:
        self._query = query
        self._command_handler = command_handler

    def list_inventory(self, request: ApiRequest) -> ApiResponse:
        try:
            claims = _claims_from_request(request)
            store_id = _optional_store_id(request.query.get("storeId"))
            if "inventory:read:any" in claims.scopes:
                snapshots = self._query.list_inventory(store_id)
            elif "inventory:read" in claims.scopes:
                snapshots = self._list_inventory_for_member(claims, store_id)
            else:
                raise _InventoryForbidden("STORE_OWNER_INVENTORY_FORBIDDEN", "inventory:read permission is required")
            return json_response(
                {"inventory": [_snapshot_payload(snapshot) for snapshot in snapshots]},
                request_id=request.request_id,
            )
        except _AuthenticationRequired:
            return _error_response("AUTHENTICATION_REQUIRED", "authenticated session is required", 401, request.request_id)
        except _InventoryForbidden as exc:
            return _error_response(exc.code, str(exc), 403, request.request_id)
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def increase_stock(self, request: ApiRequest) -> ApiResponse:
        return self._mutate(request, action="increaseStock")

    def correct_stock(self, request: ApiRequest) -> ApiResponse:
        return self._mutate(request, action="correctStock")

    def pause_sales(self, request: ApiRequest) -> ApiResponse:
        return self._mutate(request, action="pauseSales")

    def resume_sales(self, request: ApiRequest) -> ApiResponse:
        return self._mutate(request, action="resumeSales")

    def _mutate(self, request: ApiRequest, *, action: str) -> ApiResponse:
        try:
            claims = _claims_from_request(request)
            store_id = StoreId(_lookup_value(request, "storeId"))
            product_id = ProductId(_lookup_value(request, "productId"))
            public_variant_id = _lookup_value(request, "publicVariantId")
            body = _body_mapping(request)
            _reject_body_variant_id(body)
            idempotency_key = idempotency_key_from_request(request, body)
            if idempotency_key is None:
                return _error_response(
                    "IDEMPOTENCY_KEY_REQUIRED",
                    "Idempotency-Key header or body idempotencyKey is required",
                    400,
                    request.request_id,
                )
            reason = _required_text(body, "reason")
            permission = self._mutation_permission(claims, store_id)
            if permission.forbidden is not None:
                return permission.forbidden(request.request_id)
            handler = self._require_command_handler()
            command_id = CommandId(idempotency_key)
            common = {
                "command_id": command_id,
                "store_id": store_id,
                "product_id": product_id,
                "public_variant_id": public_variant_id,
                "actor_user_id": claims.user_id,
                "actor_role": claims.role,
                "reason": reason,
                "requested_at": request.received_at,
                "request_id": request.request_id,
                "actor_store_role": permission.store_role,
            }
            result = self._dispatch(handler, action=action, body=body, common=common)
            return self._mutation_response(action, result, request.request_id)
        except _AuthenticationRequired:
            return _error_response("AUTHENTICATION_REQUIRED", "authenticated session is required", 401, request.request_id)
        except IdempotencyKeyConflict as exc:
            return idempotency_conflict_response(exc, request.request_id)
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def _list_inventory_for_member(
        self,
        claims: "_InventoryClaims",
        store_id: StoreId | None,
    ) -> tuple[InventorySnapshot, ...]:
        list_for_member = getattr(self._query, "list_inventory_for_member", None)
        if callable(list_for_member):
            return list_for_member(claims.user_id, store_id)
        if claims.role is UserRole.STORE_OWNER:
            return self._query.list_inventory_for_owner(claims.user_id, store_id)
        raise _InventoryForbidden("STORE_OWNER_INVENTORY_FORBIDDEN", "store ownership or membership is required")

    def _mutation_permission(self, claims: "_InventoryClaims", store_id: StoreId) -> "_InventoryPermission":
        if "inventory:write:any" in claims.scopes:
            return _InventoryPermission(store_role=None, forbidden=None)
        if "inventory:write" not in claims.scopes:
            return _InventoryPermission(
                store_role=None,
                forbidden=lambda request_id: _error_response(
                    "STORE_OWNER_INVENTORY_FORBIDDEN",
                    "inventory:write permission is required",
                    403,
                    request_id,
                ),
            )
        store_role_for_user = getattr(self._query, "store_role_for_user", None)
        if callable(store_role_for_user):
            store_role = store_role_for_user(store_id, claims.user_id)
            if _canonical_write_role(store_role):
                return _InventoryPermission(store_role=str(store_role), forbidden=None)
            return _InventoryPermission(
                store_role=None,
                forbidden=lambda request_id: _error_response(
                    "STORE_OWNER_STORE_FORBIDDEN",
                    "store ownership or membership is required",
                    403,
                    request_id,
                ),
            )
        return _InventoryPermission(
            store_role=None,
            forbidden=lambda request_id: _error_response(
                "STORE_OWNER_STORE_FORBIDDEN",
                "store ownership or membership is required",
                403,
                request_id,
            ),
        )

    def _require_command_handler(self) -> Any:
        if self._command_handler is None:
            raise ValueError("store owner inventory command handler is not configured")
        return self._command_handler

    def _dispatch(
        self,
        handler: Any,
        *,
        action: str,
        body: Mapping[str, Any],
        common: Mapping[str, Any],
    ) -> StoreOwnerInventoryCommandResult:
        if action == "increaseStock":
            return handler.increase_stock(
                StoreOwnerIncreaseStockCommand(quantity=_required_int(body, "quantity"), **common)
            )
        if action == "correctStock":
            return handler.correct_stock(
                StoreOwnerCorrectStockCommand(target_total_stock=_required_int(body, "targetTotalStock"), **common)
            )
        if action == "pauseSales":
            return handler.pause_sales(PauseProductSalesCommand(**common))
        if action == "resumeSales":
            return handler.resume_sales(ResumeProductSalesCommand(**common))
        raise ValueError(f"unsupported inventory action {action}")

    def _mutation_response(
        self,
        action: str,
        result: StoreOwnerInventoryCommandResult,
        request_id: str,
    ) -> ApiResponse:
        if result.status is StoreOwnerInventoryCommandStatus.REJECTED:
            return _error_response(
                result.rejection_reason or "INVENTORY_COMMAND_REJECTED",
                "inventory mutation was rejected",
                _rejection_status(result.rejection_reason),
                request_id,
            )
        body: dict[str, Any] = {
            "action": action,
            "status": result.status.value,
            "storeId": str(result.store_id),
            "productId": str(result.product_id),
            "commandId": str(result.command_id),
            "idempotencyKey": str(result.command_id),
            "auditId": result.audit_id,
        }
        if result.inventory is not None:
            if result.inventory.public_variant_id is not None:
                body["publicVariantId"] = result.inventory.public_variant_id
            body["inventory"] = _inventory_payload(result.inventory)
        if result.duplicate_decision is not None:
            body["duplicateDecision"] = result.duplicate_decision.value
        return json_response(body, status_code=202, request_id=request_id)


class _AuthenticationRequired(ValueError):
    pass


class _InventoryForbidden(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class _InventoryClaims:
    def __init__(self, *, user_id: UserId, role: UserRole, scopes: tuple[str, ...] = ()) -> None:
        self.user_id = user_id
        self.role = role
        self.scopes = scopes


class _InventoryPermission:
    def __init__(self, *, store_role: str | None, forbidden: Any | None) -> None:
        self.store_role = store_role
        self.forbidden = forbidden


def _canonical_write_role(value: object) -> bool:
    if value is None:
        return False
    return str(value) in {"OWNER", "MANAGER"}


def _claims_from_request(request: ApiRequest) -> _InventoryClaims:
    if request.auth_context is not None and request.auth_context.user_id is not None:
        role = UserRole(request.auth_context.role) if request.auth_context.role else UserRole.CUSTOMER
        return _InventoryClaims(user_id=UserId(request.auth_context.user_id), role=role, scopes=request.auth_context.scopes)
    if request.local_auth_fallback_enabled:
        headers = {key.lower(): value for key, value in request.headers.items()}
        user_id = headers.get("x-user-id")
        if user_id:
            return _InventoryClaims(
                user_id=UserId(user_id),
                role=UserRole.CUSTOMER,
                scopes=tuple(part.strip() for part in headers.get("x-user-scopes", "").split(",") if part.strip()),
            )
    raise _AuthenticationRequired("authenticated session is required")


def _snapshot_payload(snapshot: InventorySnapshot) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "storeId": str(snapshot.store_id),
        "productId": str(snapshot.product_id),
        "availableStock": snapshot.available_stock,
        "reservedStock": snapshot.reserved_stock,
        "soldStock": snapshot.confirmed_stock,
        "confirmedStock": snapshot.confirmed_stock,
        "totalStock": snapshot.total_stock,
        "saleStatus": snapshot.sale_status.value,
        "updatedAt": snapshot.updated_at.isoformat(),
    }
    if snapshot.public_variant_id is not None:
        payload["publicVariantId"] = snapshot.public_variant_id
    return payload


def _inventory_payload(inventory: ProductInventory, *, updated_at: datetime | None = None) -> dict[str, Any]:
    confirmed_stock = sum(
        reservation.reserved_qty.value
        for reservation in inventory.reservations
        if reservation.status.value == "CONFIRMED"
    )
    payload: dict[str, Any] = {
        "storeId": str(inventory.store_id),
        "productId": str(inventory.product_id),
        "availableStock": inventory.available_stock.value,
        "reservedStock": inventory.reserved_stock.value,
        "soldStock": confirmed_stock,
        "confirmedStock": confirmed_stock,
        "totalStock": inventory.total_stock.value,
        "saleStatus": inventory.sale_status.value,
        "updatedAt": updated_at.isoformat() if updated_at is not None else None,
    }
    if inventory.public_variant_id is not None:
        payload["publicVariantId"] = inventory.public_variant_id
    return payload


def _body_mapping(request: ApiRequest) -> Mapping[str, Any]:
    if not isinstance(request.body, Mapping):
        raise ValueError("request body must be an object")
    return request.body


def _reject_body_variant_id(body: Mapping[str, Any]) -> None:
    if "publicVariantId" in body or "public_variant_id" in body:
        raise ValueError("publicVariantId must be supplied in the inventory variant route path")


def _lookup_value(request: ApiRequest, key: str) -> str:
    value = request.query.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError(f"{key} is required")


def _optional_store_id(value: Any) -> StoreId | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("storeId must be a non-empty string")
    return StoreId(value)


def _required_text(body: Mapping[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value.strip()


def _optional_text(body: Mapping[str, Any], key: str) -> str | None:
    value = body.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _required_int(body: Mapping[str, Any], key: str) -> int:
    value = body.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _rejection_status(reason: str | None) -> int:
    return {
        "INVENTORY_NOT_FOUND": 404,
        "STOCK_BELOW_RESERVED": 409,
        "INSUFFICIENT_STOCK": 409,
    }.get(reason or "", 400)


def _error_response(code: str, message: str, status_code: int, request_id: str | None) -> ApiResponse:
    return json_response(
        {"error": {"code": code, "message": message}},
        status_code=status_code,
        request_id=request_id,
    )


__all__ = ["StoreOwnerInventoryApi"]
