"""Framework-neutral admin store provisioning and catalog API handlers."""

from __future__ import annotations

from typing import Any, Mapping

from token_payments.contexts.auth.domain import UserRole
from token_payments.contexts.store_catalog.application.commands import (
    CreateOrReuseStoreUserCommand,
    CreateStoreCommand,
    GetStoreProfileQuery,
    GrantStoreMembershipCommand,
    ListMerchantStoresQuery,
    RegisterStoreProductCommand,
    UpdateStoreProfileCommand,
    UpdateStoreProductCommand,
    payload_hash,
)
from token_payments.contexts.store_catalog.application.ports import StoreCatalogCommandStatus
from token_payments.contexts.store_catalog.domain import ProductStatus, ProductVisibility, PublicProductId, PublicStoreId, StoreMembershipRole
from token_payments.shared.domain import CommandId, Crypto, ProductId, StoreId, UserId, WalletAddress

from .contracts import ApiRequest, ApiResponse, json_response
from .idempotency import IdempotencyKeyConflict, idempotency_conflict_response, idempotency_key_from_request


class StoreCatalogApi:
    """Admin provisioning and store-owner product registration facade."""

    def __init__(self, use_case: Any, *, id_generator: Any | None = None) -> None:
        self._use_case = use_case
        self._id_generator = id_generator

    def create_or_reuse_store_user(self, request: ApiRequest) -> ApiResponse:
        try:
            claims = _require_admin(request)
            body = _body(request)
            idempotency_key = _required_idempotency_key(request, body)
            command = CreateOrReuseStoreUserCommand(
                command_id=CommandId(idempotency_key),
                wallet_address=WalletAddress(_required_text(body, "walletAddress")),
                requested_at=request.received_at,
                request_id=request.request_id,
                payload_hash=payload_hash(_idempotency_payload(request, body, claims.user_id)),
            )
            return _result_response(
                self._use_case.create_or_reuse_store_user(command),
                request.request_id,
                created_status=201,
            )
        except _ApiError as exc:
            return exc.response(request.request_id)
        except IdempotencyKeyConflict as exc:
            return idempotency_conflict_response(exc, request.request_id)
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def create_store(self, request: ApiRequest) -> ApiResponse:
        try:
            claims = _require_admin(request)
            body = _body(request)
            _reject_unknown_fields(
                body,
                {
                    "ownerUserId",
                    "storeWalletAddress",
                    "supportedChainIds",
                    "active",
                    "displayName",
                    "description",
                    "supportEmail",
                    "supportEmailPublic",
                    "businessRegistrationLabel",
                    "idempotencyKey",
                    "commandId",
                },
            )
            idempotency_key = _required_idempotency_key(request, body)
            store_id = _new_id(self._id_generator)
            command = CreateStoreCommand(
                command_id=CommandId(idempotency_key),
                actor_user_id=claims.user_id,
                store_id=StoreId(store_id),
                public_store_id=None,
                owner_user_id=UserId(_required_text(body, "ownerUserId")),
                store_wallet=WalletAddress(_required_text(body, "storeWalletAddress")),
                supported_chain_ids=_required_int_tuple(body, "supportedChainIds"),
                active=_optional_bool(body, "active", True),
                display_name=_optional_text(body, "displayName") or "Untitled Store",
                description=_optional_text(body, "description"),
                support_email=_optional_text(body, "supportEmail"),
                support_email_public=_optional_bool(body, "supportEmailPublic", False),
                business_registration_label=_optional_text(body, "businessRegistrationLabel"),
                requested_at=request.received_at,
                request_id=request.request_id,
                payload_hash=payload_hash(_idempotency_payload(request, body, claims.user_id)),
            )
            return _result_response(self._use_case.create_store(command), request.request_id, created_status=201)
        except _ApiError as exc:
            return exc.response(request.request_id)
        except IdempotencyKeyConflict as exc:
            return idempotency_conflict_response(exc, request.request_id)
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def get_store_profile(self, request: ApiRequest) -> ApiResponse:
        try:
            public_store_id = PublicStoreId(_lookup_value(request, "publicStoreId"))
            store = self._use_case.get_store_profile(GetStoreProfileQuery(public_store_id))
            if store is None:
                return _error_response("STORE_NOT_FOUND", "store profile was not found", 404, request.request_id)
            return json_response({"store": store}, request_id=request.request_id)
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def list_merchant_stores(self, request: ApiRequest) -> ApiResponse:
        try:
            claims = _require_authenticated(request)
            if "store:read" not in claims.scopes and "store:read:any" not in claims.scopes:
                raise _ApiError("STORE_PROFILE_FORBIDDEN", "store:read permission is required", 403)
            stores = self._use_case.list_merchant_stores(ListMerchantStoresQuery(claims.user_id))
            return json_response({"stores": list(stores)}, request_id=request.request_id)
        except _ApiError as exc:
            return exc.response(request.request_id)
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def list_public_stores(self, request: ApiRequest) -> ApiResponse:
        try:
            _reject_unknown_query(request.query, {"limit", "offset"})
            page = _page_query(request.query)
            return json_response(
                self._use_case.list_public_stores(limit=page["limit"], offset=page["offset"]),
                request_id=request.request_id,
            )
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def list_all_public_products(self, request: ApiRequest) -> ApiResponse:
        try:
            _reject_unknown_query(request.query, {"q", "category", "tag", "sort", "limit", "offset"})
            result = self._use_case.list_all_public_products(
                filters=_catalog_filters(request.query, merchant=False),
            )
            return json_response(result, request_id=request.request_id)
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def list_public_products(self, request: ApiRequest) -> ApiResponse:
        try:
            _reject_unknown_query(request.query, {"q", "category", "tag", "sort", "limit", "offset", "publicStoreId"})
            result = self._use_case.list_public_products(
                public_store_id=PublicStoreId(_lookup_value(request, "publicStoreId")),
                filters=_catalog_filters(request.query, merchant=False),
            )
            if result is None:
                return _error_response("STORE_NOT_FOUND", "store was not found", 404, request.request_id)
            return json_response(result, request_id=request.request_id)
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def get_public_product(self, request: ApiRequest) -> ApiResponse:
        try:
            result = self._use_case.get_public_product(
                public_store_id=PublicStoreId(_lookup_value(request, "publicStoreId")),
                public_product_id=PublicProductId(_lookup_value(request, "publicProductId")),
            )
            if result is None:
                return _error_response("PRODUCT_NOT_FOUND", "product was not found", 404, request.request_id)
            return json_response(result, request_id=request.request_id)
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def list_merchant_products(self, request: ApiRequest) -> ApiResponse:
        try:
            claims = _require_authenticated(request)
            if "product:read" not in claims.scopes and "product:read:any" not in claims.scopes:
                raise _ApiError("STORE_OWNER_STORE_FORBIDDEN", "product:read permission is required", 403)
            _reject_unknown_query(
                request.query,
                {"q", "category", "tag", "status", "visibility", "sort", "limit", "offset", "publicStoreId"},
            )
            result = self._use_case.list_merchant_products(
                actor_user_id=claims.user_id,
                public_store_id=PublicStoreId(_lookup_value(request, "publicStoreId")),
                filters=_catalog_filters(request.query, merchant=True),
                platform_override="product:read:any" in claims.scopes,
            )
            return _read_result_response(result, request.request_id)
        except _ApiError as exc:
            return exc.response(request.request_id)
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def get_merchant_product(self, request: ApiRequest) -> ApiResponse:
        try:
            claims = _require_authenticated(request)
            if "product:read" not in claims.scopes and "product:read:any" not in claims.scopes:
                raise _ApiError("STORE_OWNER_STORE_FORBIDDEN", "product:read permission is required", 403)
            result = self._use_case.get_merchant_product(
                actor_user_id=claims.user_id,
                public_store_id=PublicStoreId(_lookup_value(request, "publicStoreId")),
                public_product_id=PublicProductId(_lookup_value(request, "publicProductId")),
                platform_override="product:read:any" in claims.scopes,
            )
            return _read_result_response(result, request.request_id)
        except _ApiError as exc:
            return exc.response(request.request_id)
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def update_store_profile(self, request: ApiRequest) -> ApiResponse:
        try:
            claims = _require_authenticated(request)
            if "store:write" not in claims.scopes and "store:write:any" not in claims.scopes:
                raise _ApiError("STORE_PROFILE_FORBIDDEN", "store:write permission is required", 403)
            body = _body(request)
            _reject_unknown_fields(
                body,
                {
                    "displayName",
                    "description",
                    "supportEmail",
                    "supportEmailPublic",
                    "businessRegistrationLabel",
                    "idempotencyKey",
                    "commandId",
                },
            )
            idempotency_key = _required_idempotency_key(request, body)
            command = UpdateStoreProfileCommand(
                command_id=CommandId(idempotency_key),
                actor_user_id=claims.user_id,
                public_store_id=PublicStoreId(_lookup_value(request, "publicStoreId")),
                display_name=_optional_text(body, "displayName"),
                description=_optional_text(body, "description"),
                support_email=_optional_text(body, "supportEmail"),
                support_email_public=_optional_bool_or_none(body, "supportEmailPublic"),
                business_registration_label=_optional_text(body, "businessRegistrationLabel"),
                platform_override="store:write:any" in claims.scopes,
                requested_at=request.received_at,
                request_id=request.request_id,
                payload_hash=payload_hash(_idempotency_payload(request, body, claims.user_id)),
            )
            return _result_response(
                self._use_case.update_store_profile(command),
                request.request_id,
                created_status=200,
            )
        except _ApiError as exc:
            return exc.response(request.request_id)
        except IdempotencyKeyConflict as exc:
            return idempotency_conflict_response(exc, request.request_id)
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def grant_store_membership(self, request: ApiRequest) -> ApiResponse:
        try:
            claims = _require_admin(request)
            body = _body(request)
            idempotency_key = _required_idempotency_key(request, body)
            command = GrantStoreMembershipCommand(
                command_id=CommandId(idempotency_key),
                actor_user_id=claims.user_id,
                store_id=StoreId(_lookup_value(request, "storeId")),
                user_id=UserId(_required_text(body, "userId")),
                role=_store_membership_role(body),
                active=_optional_bool(body, "active", True),
                requested_at=request.received_at,
                request_id=request.request_id,
                payload_hash=payload_hash(_idempotency_payload(request, body, claims.user_id)),
            )
            return _result_response(
                self._use_case.grant_store_membership(command),
                request.request_id,
                created_status=201,
            )
        except _ApiError as exc:
            return exc.response(request.request_id)
        except IdempotencyKeyConflict as exc:
            return idempotency_conflict_response(exc, request.request_id)
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def register_store_product(self, request: ApiRequest) -> ApiResponse:
        try:
            claims = _require_authenticated(request)
            if "product:write" not in claims.scopes and "product:write:any" not in claims.scopes:
                raise _ApiError("STORE_OWNER_STORE_FORBIDDEN", "product:write permission is required", 403)
            body = _body(request)
            _reject_unknown_fields(
                body,
                {
                    "title",
                    "name",
                    "description",
                    "category",
                    "tags",
                    "media",
                    "attributes",
                    "status",
                    "visibility",
                    "price",
                    "initialTotalStock",
                    "active",
                    "available",
                    "idempotencyKey",
                    "commandId",
                },
            )
            idempotency_key = _required_idempotency_key(request, body)
            active = _optional_bool(body, "active", _optional_bool(body, "available", True))
            command = RegisterStoreProductCommand(
                command_id=CommandId(idempotency_key),
                actor_user_id=claims.user_id,
                public_store_id=PublicStoreId(_lookup_value(request, "publicStoreId")),
                product_id=ProductId(_new_id(self._id_generator)),
                public_product_id=None,
                title=_optional_text(body, "title") or _required_text(body, "name"),
                description=_optional_text(body, "description"),
                category=_optional_text(body, "category"),
                tags=_optional_text_tuple(body, "tags"),
                media=_optional_text_tuple(body, "media"),
                attributes=_optional_mapping(body, "attributes"),
                status=_optional_product_status(body, "status", ProductStatus.ACTIVE if active else ProductStatus.INACTIVE),
                visibility=_optional_product_visibility(body, "visibility", ProductVisibility.PUBLIC),
                price=_price(body),
                initial_total_stock=_required_int(body, "initialTotalStock"),
                active=active,
                platform_override="product:write:any" in claims.scopes,
                requested_at=request.received_at,
                request_id=request.request_id,
                payload_hash=payload_hash(_idempotency_payload(request, body, claims.user_id)),
            )
            return _result_response(
                self._use_case.register_store_product(command),
                request.request_id,
                created_status=201,
            )
        except _ApiError as exc:
            return exc.response(request.request_id)
        except IdempotencyKeyConflict as exc:
            return idempotency_conflict_response(exc, request.request_id)
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def update_store_product(self, request: ApiRequest) -> ApiResponse:
        try:
            claims = _require_authenticated(request)
            if "product:write" not in claims.scopes and "product:write:any" not in claims.scopes:
                raise _ApiError("STORE_OWNER_STORE_FORBIDDEN", "product:write permission is required", 403)
            body = _body(request)
            _reject_unknown_fields(
                body,
                {
                    "title",
                    "description",
                    "category",
                    "tags",
                    "media",
                    "attributes",
                    "status",
                    "visibility",
                    "price",
                    "idempotencyKey",
                    "commandId",
                },
            )
            idempotency_key = _required_idempotency_key(request, body)
            command = UpdateStoreProductCommand(
                command_id=CommandId(idempotency_key),
                actor_user_id=claims.user_id,
                public_store_id=PublicStoreId(_lookup_value(request, "publicStoreId")),
                public_product_id=PublicProductId(_lookup_value(request, "publicProductId")),
                title=_optional_text(body, "title"),
                description=_optional_text(body, "description"),
                category=_optional_text(body, "category"),
                tags=_optional_text_tuple_or_none(body, "tags"),
                media=_optional_text_tuple_or_none(body, "media"),
                attributes=_optional_mapping(body, "attributes"),
                status=_optional_product_status_or_none(body, "status"),
                visibility=_optional_product_visibility_or_none(body, "visibility"),
                price=_optional_price(body),
                platform_override="product:write:any" in claims.scopes,
                requested_at=request.received_at,
                request_id=request.request_id,
                payload_hash=payload_hash(_idempotency_payload(request, body, claims.user_id)),
            )
            return _result_response(
                self._use_case.update_store_product(command),
                request.request_id,
                created_status=200,
            )
        except _ApiError as exc:
            return exc.response(request.request_id)
        except IdempotencyKeyConflict as exc:
            return idempotency_conflict_response(exc, request.request_id)
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)


class _Claims:
    def __init__(self, *, user_id: UserId, scopes: tuple[str, ...], role: UserRole = UserRole.CUSTOMER) -> None:
        self.user_id = user_id
        self.role = role
        self.scopes = scopes


class _ApiError(ValueError):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(message)

    def response(self, request_id: str) -> ApiResponse:
        return _error_response(self.code, str(self), self.status_code, request_id)


def _require_admin(request: ApiRequest) -> _Claims:
    claims = _require_authenticated(request)
    if not ({"admin:provision", "rbac:manage"} & set(claims.scopes)):
        raise _ApiError("ADMIN_REQUIRED", "admin session is required", 403)
    return claims


def _require_authenticated(request: ApiRequest) -> _Claims:
    context = request.auth_context
    if context is None or context.user_id is None:
        raise _ApiError("AUTHENTICATION_REQUIRED", "authenticated session is required", 401)
    return _Claims(
        user_id=UserId(context.user_id),
        role=UserRole(context.role) if context.role else UserRole.CUSTOMER,
        scopes=context.scopes,
    )


def _required_idempotency_key(request: ApiRequest, body: Mapping[str, Any]) -> str:
    key = idempotency_key_from_request(request, body)
    if key is None:
        raise _ApiError("IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key header or body idempotencyKey is required", 400)
    return key


def _result_response(result: Any, request_id: str, *, created_status: int) -> ApiResponse:
    if result.status is StoreCatalogCommandStatus.CONFLICT:
        return json_response(result.payload, status_code=409, request_id=request_id)
    if result.status is StoreCatalogCommandStatus.REJECTED:
        code = str(result.rejection_reason or result.payload.get("error", {}).get("code", "CATALOG_COMMAND_REJECTED"))
        return json_response(result.payload, status_code=_status_for_rejection(code), request_id=request_id)
    status_code = 200 if result.status is StoreCatalogCommandStatus.DUPLICATE else created_status
    return json_response(result.payload, status_code=status_code, request_id=request_id)


def _read_result_response(result: Mapping[str, Any], request_id: str) -> ApiResponse:
    if "error" in result:
        code = str(result["error"].get("code", "CATALOG_QUERY_REJECTED"))
        return json_response(result, status_code=_status_for_rejection(code), request_id=request_id)
    return json_response(result, request_id=request_id)


def _status_for_rejection(code: str) -> int:
    if code.endswith("_FORBIDDEN"):
        return 403
    if code.endswith("_NOT_FOUND"):
        return 404
    if code.endswith("_CONFLICT"):
        return 409
    if code in {"STORE_INACTIVE", "UNSUPPORTED_PRICE_CHAIN"}:
        return 409
    return 400


def _body(request: ApiRequest) -> Mapping[str, Any]:
    if not isinstance(request.body, Mapping):
        raise _ApiError("VALIDATION_ERROR", "request body must be an object", 400)
    return request.body


def _idempotency_payload(request: ApiRequest, body: Mapping[str, Any], actor_user_id: UserId) -> dict[str, Any]:
    return {
        "method": request.method,
        "path": request.path,
        "query": dict(request.query),
        "body": dict(body),
        "actorUserId": str(actor_user_id),
    }


def _price(body: Mapping[str, Any]) -> Crypto:
    raw = body.get("price")
    if not isinstance(raw, Mapping):
        raise ValueError("price must be an object")
    return Crypto(
        amount=_required_text(raw, "amount"),
        symbol=_required_text(raw, "symbol"),
        chain_id=_required_int(raw, "chainId"),
        token_address=_optional_text(raw, "tokenAddress"),
        decimals=_required_int(raw, "decimals"),
    )


def _optional_price(body: Mapping[str, Any]) -> Crypto | None:
    if "price" not in body:
        return None
    return _price(body)


def _store_membership_role(body: Mapping[str, Any]) -> StoreMembershipRole:
    role_id = _optional_text(body, "roleId")
    if role_id is not None:
        role_map = {
            "MERCHANT_OWNER": StoreMembershipRole.OWNER,
            "MERCHANT_MANAGER": StoreMembershipRole.MANAGER,
        }
        if role_id not in role_map:
            raise ValueError("roleId must be MERCHANT_OWNER or MERCHANT_MANAGER")
        return role_map[role_id]
    return StoreMembershipRole(_optional_text(body, "role") or StoreMembershipRole.MANAGER.value)


def _lookup_value(request: ApiRequest, key: str) -> str:
    value = request.query.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError(f"{key} is required")


def _reject_unknown_query(query: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(str(key) for key in query if key not in allowed)
    if unknown:
        raise ValueError(f"unknown catalog query field(s): {', '.join(unknown)}")


def _catalog_filters(query: Mapping[str, Any], *, merchant: bool) -> dict[str, Any]:
    page = _page_query(query)
    sort_by, sort_direction = _sort_query(query.get("sort"))
    filters: dict[str, Any] = {
        "query": _optional_query_text(query.get("q"), "q"),
        "category": _optional_catalog_token(query.get("category"), "category"),
        "tag": _optional_catalog_token(query.get("tag"), "tag"),
        "sort_by": sort_by,
        "sort_direction": sort_direction,
        "limit": page["limit"],
        "offset": page["offset"],
    }
    if merchant:
        status = _optional_query_text(query.get("status"), "status")
        visibility = _optional_query_text(query.get("visibility"), "visibility")
        filters["status"] = ProductStatus(status) if status is not None else None
        filters["visibility"] = ProductVisibility(visibility) if visibility is not None else None
    return filters


def _page_query(query: Mapping[str, Any]) -> dict[str, int]:
    return {
        "limit": _bounded_int(query.get("limit", "20"), "limit", minimum=1, maximum=50),
        "offset": _bounded_int(query.get("offset", "0"), "offset", minimum=0, maximum=10000),
    }


def _bounded_int(value: Any, field_name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}")
    return parsed


def _sort_query(value: Any) -> tuple[str, str]:
    raw = _optional_query_text(value, "sort") or "title"
    direction = "desc" if raw.startswith("-") else "asc"
    sort_by = raw[1:] if raw.startswith("-") else raw
    if sort_by not in {"title", "createdAt", "updatedAt", "price"}:
        raise ValueError("sort must be one of title, createdAt, updatedAt, price with optional '-' prefix")
    return sort_by, direction


def _optional_catalog_token(value: Any, field_name: str) -> str | None:
    text = _optional_query_text(value, field_name)
    if text is None:
        return None
    if len(text) > 80:
        raise ValueError(f"{field_name} must be at most 80 characters")
    if any(char in text for char in "\x00\r\n\t"):
        raise ValueError(f"{field_name} contains unsafe characters")
    return text.lower()


def _optional_query_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, tuple | list):
        raise ValueError(f"{field_name} must be a single value")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    text = value.strip()
    if len(text) > 120:
        raise ValueError(f"{field_name} must be at most 120 characters")
    if any(char in text for char in "\x00\r\n\t"):
        raise ValueError(f"{field_name} contains unsafe characters")
    return text


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
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _optional_public_store_id(body: Mapping[str, Any], key: str) -> PublicStoreId | None:
    value = _optional_text(body, key)
    return PublicStoreId(value) if value is not None else None


def _optional_public_product_id(body: Mapping[str, Any], key: str) -> PublicProductId | None:
    value = _optional_text(body, key)
    return PublicProductId(value) if value is not None else None


def _required_int(body: Mapping[str, Any], key: str) -> int:
    value = body.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _required_int_tuple(body: Mapping[str, Any], key: str) -> tuple[int, ...]:
    values = body.get(key)
    if not isinstance(values, list) or not values:
        raise ValueError(f"{key} must be a non-empty array")
    return tuple(_int_value(value, key) for value in values)


def _int_value(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must contain integers")
    return value


def _optional_bool(body: Mapping[str, Any], key: str, default: bool) -> bool:
    value = body.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _optional_bool_or_none(body: Mapping[str, Any], key: str) -> bool | None:
    if key not in body:
        return None
    value = body.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _optional_text_tuple(body: Mapping[str, Any], key: str) -> tuple[str, ...]:
    if key not in body:
        return ()
    values = body.get(key)
    if not isinstance(values, list):
        raise ValueError(f"{key} must be an array")
    return tuple(_text_value(value, key) for value in values)


def _optional_text_tuple_or_none(body: Mapping[str, Any], key: str) -> tuple[str, ...] | None:
    if key not in body:
        return None
    return _optional_text_tuple(body, key)


def _optional_mapping(body: Mapping[str, Any], key: str) -> Mapping[str, Any] | None:
    if key not in body:
        return None
    value = body.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return value


def _optional_product_status(body: Mapping[str, Any], key: str, default: ProductStatus) -> ProductStatus:
    value = _optional_text(body, key)
    return default if value is None else ProductStatus(value)


def _optional_product_status_or_none(body: Mapping[str, Any], key: str) -> ProductStatus | None:
    value = _optional_text(body, key)
    return None if value is None else ProductStatus(value)


def _optional_product_visibility(
    body: Mapping[str, Any],
    key: str,
    default: ProductVisibility,
) -> ProductVisibility:
    value = _optional_text(body, key)
    return default if value is None else ProductVisibility(value)


def _optional_product_visibility_or_none(body: Mapping[str, Any], key: str) -> ProductVisibility | None:
    value = _optional_text(body, key)
    return None if value is None else ProductVisibility(value)


def _text_value(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must contain non-empty strings")
    return value.strip()


def _reject_unknown_fields(body: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(str(key) for key in body if key not in allowed)
    if unknown:
        raise ValueError(f"unknown store profile field(s): {', '.join(unknown)}")


def _new_id(generator: Any | None) -> str:
    if generator is None:
        return str(StoreId.new())
    new_id = getattr(generator, "new_id", None)
    if callable(new_id):
        return str(new_id())
    if callable(generator):
        return str(generator())
    raise ValueError("id_generator must expose new_id() or be callable")


def _error_response(code: str, message: str, status_code: int, request_id: str) -> ApiResponse:
    return json_response(
        {"error": {"code": code, "message": message}},
        status_code=status_code,
        request_id=request_id,
    )
