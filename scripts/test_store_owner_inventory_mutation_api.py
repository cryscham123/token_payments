from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import (  # noqa: E402
    STORE_OWNER_INVENTORY_HTTP_ROUTES,
    ApiAuthContext,
    HttpRouter,
    StoreOwnerInventoryApi,
    register_store_owner_inventory_routes,
)
from token_payments.contexts.auth.domain import UserRole  # noqa: E402
from token_payments.contexts.inventory.application import (  # noqa: E402
    PauseProductSalesCommand,
    ResumeProductSalesCommand,
    StoreOwnerCorrectStockCommand,
    StoreOwnerIncreaseStockCommand,
    StoreOwnerInventoryCommandResult,
    StoreOwnerInventoryCommandStatus,
)
from token_payments.contexts.inventory.domain import InventorySaleStatus, ProductInventory, Quantity  # noqa: E402
from token_payments.runtime.security import (  # noqa: E402
    CorsPolicy,
    CsrfCookieSettings,
    CsrfTokenService,
    HmacCsrfTokenSigner,
    RequestBodyLimit,
    RequestGuard,
)
from token_payments.shared.domain import CommandId, OrderId, ProductId, StoreId, UserId  # noqa: E402


NOW = datetime(2026, 5, 18, 1, 30, tzinfo=UTC)
OWNER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc8201")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc8202")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc8203")
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc8204")


def test_stock_intake_endpoint_requires_positive_quantity_reason_and_updates_stock() -> None:
    handler = FakeMutationHandler(_inventory(available=5))
    router = _router(handler=handler)

    response = router.handle(
        "POST",
        f"/store-owner/stores/{STORE_ID}/inventory/{PRODUCT_ID}/intake",
        headers=_owner_headers("req-intake", idempotency_key="stock-intake-http-001"),
        body=_json_body({"quantity": 4, "reason": "warehouse intake"}),
        received_at=NOW,
    )
    bad_quantity = router.handle(
        "POST",
        f"/store-owner/stores/{STORE_ID}/inventory/{PRODUCT_ID}/intake",
        headers=_owner_headers("req-bad-intake", idempotency_key="stock-intake-http-002"),
        body=_json_body({"quantity": 0, "reason": "bad intake"}),
        received_at=NOW,
    )

    payload = _json(response.body)

    assert response.status_code == 202
    assert handler.commands[0] == StoreOwnerIncreaseStockCommand(
        command_id=CommandId("stock-intake-http-001"),
        store_id=STORE_ID,
        product_id=PRODUCT_ID,
        actor_user_id=OWNER_ID,
        actor_role=UserRole.STORE_OWNER,
        quantity=Quantity(4),
        reason="warehouse intake",
        requested_at=NOW,
        request_id="req-intake",
    )
    assert payload["status"] == "accepted"
    assert payload["inventory"]["availableStock"] == 9
    assert payload["inventory"]["totalStock"] == 9
    assert bad_quantity.status_code == 400


def test_stock_correction_endpoint_rejects_reserved_below_target_total() -> None:
    handler = FakeMutationHandler(
        _inventory(available=7).reserve_inventory(ORDER_ID, Quantity(4))
    )
    response = _router(handler=handler).handle(
        "POST",
        f"/store-owner/stores/{STORE_ID}/inventory/{PRODUCT_ID}/corrections",
        headers=_owner_headers("req-correction", idempotency_key="stock-correction-http-001"),
        body=_json_body({"targetTotalStock": 2, "reason": "cycle count"}),
        received_at=NOW,
    )

    assert response.status_code == 409
    assert _json(response.body)["error"]["code"] == "STOCK_BELOW_RESERVED"


def test_sale_pause_and_resume_endpoints_toggle_availability_without_releasing_reservations() -> None:
    handler = FakeMutationHandler(
        _inventory(available=8).reserve_inventory(ORDER_ID, Quantity(2))
    )
    router = _router(handler=handler)

    pause = router.handle(
        "POST",
        f"/store-owner/stores/{STORE_ID}/inventory/{PRODUCT_ID}/pause",
        headers=_owner_headers("req-pause", idempotency_key="sale-pause-http-001"),
        body=_json_body({"reason": "supplier hold"}),
        received_at=NOW,
    )
    resume = router.handle(
        "POST",
        f"/store-owner/stores/{STORE_ID}/inventory/{PRODUCT_ID}/resume",
        headers=_owner_headers("req-resume", idempotency_key="sale-resume-http-001"),
        body=_json_body({"reason": "supplier released hold"}),
        received_at=NOW,
    )

    assert [type(command) for command in handler.commands[-2:]] == [PauseProductSalesCommand, ResumeProductSalesCommand]
    assert _json(pause.body)["inventory"]["saleStatus"] == "PAUSED"
    assert _json(pause.body)["inventory"]["reservedStock"] == 2
    assert _json(resume.body)["inventory"]["saleStatus"] == "ACTIVE"
    assert _json(resume.body)["inventory"]["reservedStock"] == 2


def test_mutation_routes_require_idempotency_key_and_csrf_for_cookie_auth() -> None:
    csrf = _csrf_service()
    handler = FakeMutationHandler(_inventory(available=5))
    router = _router(handler=handler, request_guard=_guard(csrf))

    missing_idempotency = router.handle(
        "POST",
        f"/store-owner/stores/{STORE_ID}/inventory/{PRODUCT_ID}/intake",
        headers={"Content-Type": "application/json", "X-Request-Id": "req-missing-idem"},
        body=_json_body({"quantity": 1, "reason": "missing idempotency"}),
        received_at=NOW,
    )
    missing_csrf = router.handle(
        "POST",
        f"/store-owner/stores/{STORE_ID}/inventory/{PRODUCT_ID}/intake",
        headers={
            "Content-Type": "application/json",
            "Cookie": f"access_token=session-token; csrf_token={csrf.issue_token(now=NOW).token}",
            "Idempotency-Key": "stock-intake-csrf-001",
            "X-Request-Id": "req-missing-csrf",
        },
        body=_json_body({"quantity": 1, "reason": "missing csrf"}),
        received_at=NOW,
    )

    assert missing_idempotency.status_code == 400
    assert _json(missing_idempotency.body)["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    assert missing_csrf.status_code == 403
    assert _json(missing_csrf.body)["error"]["code"] == "CSRF_TOKEN_MISSING"


def test_store_owner_inventory_mutation_route_manifest_matches_api_spec_names() -> None:
    actual = {
        key: (spec.method, spec.path, spec.operation_id)
        for key, spec in STORE_OWNER_INVENTORY_HTTP_ROUTES.items()
    }
    expected = {
        "increase_stock": (
            "POST",
            "/store-owner/stores/{storeId}/inventory/{productId}/intake",
            "increaseStoreOwnerInventoryStock",
        ),
        "correct_stock": (
            "POST",
            "/store-owner/stores/{storeId}/inventory/{productId}/corrections",
            "correctStoreOwnerInventoryStock",
        ),
        "pause_sales": (
            "POST",
            "/store-owner/stores/{storeId}/inventory/{productId}/pause",
            "pauseStoreOwnerInventorySales",
        ),
        "resume_sales": (
            "POST",
            "/store-owner/stores/{storeId}/inventory/{productId}/resume",
            "resumeStoreOwnerInventorySales",
        ),
    }
    for key, value in expected.items():
        assert actual[key] == value


def _router(
    *,
    handler: "FakeMutationHandler",
    request_guard: RequestGuard | None = None,
) -> HttpRouter:
    query = FakeInventoryQuery(owners={STORE_ID: OWNER_ID})
    router = HttpRouter(
        auth_context_factory=lambda _request: ApiAuthContext(
            user_id=str(OWNER_ID),
            role=UserRole.STORE_OWNER.value,
            scopes=("inventory:write",),
            session_id="session-cookie",
        ),
        allow_dev_auth_headers=False,
        request_guard=request_guard,
    )
    register_store_owner_inventory_routes(router, StoreOwnerInventoryApi(query=query, command_handler=handler))
    return router


def _owner_headers(request_id: str, *, idempotency_key: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotency_key,
        "X-Request-Id": request_id,
    }


def _inventory(*, available: int) -> ProductInventory:
    return ProductInventory(
        product_id=PRODUCT_ID,
        store_id=STORE_ID,
        available_stock=Quantity(available),
        reserved_stock=Quantity(0),
        total_stock=Quantity(available),
    )


def _json_body(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _json(body: bytes) -> dict[str, Any]:
    decoded = json.loads(body)
    assert isinstance(decoded, dict)
    return decoded


def _csrf_service() -> CsrfTokenService:
    return CsrfTokenService(
        signer=HmacCsrfTokenSigner(
            key_id="csrf-active",
            secret_provider=lambda: "active-live-csrf-signing-secret-at-least-32-bytes",
            nonce_factory=lambda: "csrf-nonce-001",
        ),
        cookie_settings=CsrfCookieSettings(max_age_seconds=3600),
    )


def _guard(csrf: CsrfTokenService) -> RequestGuard:
    return RequestGuard(
        csrf_token_service=csrf,
        cors_policy=CorsPolicy(allowed_origins=("http://localhost:5173",), allow_credentials=True),
        body_limit=RequestBodyLimit(max_bytes=1024),
        auth_cookie_names=("access_token", "refresh_token"),
    )


class FakeInventoryQuery:
    def __init__(self, *, owners: dict[StoreId, UserId]) -> None:
        self.owners = owners

    def list_inventory(self, store_id: StoreId | None = None):
        return ()

    def list_inventory_for_owner(self, owner_user_id: UserId, store_id: StoreId | None = None):
        return ()

    def owner_for_store(self, store_id: StoreId) -> UserId | None:
        return self.owners.get(store_id)


class FakeMutationHandler:
    def __init__(self, inventory: ProductInventory) -> None:
        self.inventory = inventory
        self.commands: list[object] = []

    def increase_stock(self, command: StoreOwnerIncreaseStockCommand) -> StoreOwnerInventoryCommandResult:
        self.commands.append(command)
        self.inventory = self.inventory.increase_stock(command.quantity)
        return self._result(command.command_id)

    def correct_stock(self, command: StoreOwnerCorrectStockCommand) -> StoreOwnerInventoryCommandResult:
        self.commands.append(command)
        if command.target_total_stock.value < self.inventory.reserved_stock.value:
            return StoreOwnerInventoryCommandResult(
                command_id=command.command_id,
                store_id=command.store_id,
                product_id=command.product_id,
                status=StoreOwnerInventoryCommandStatus.REJECTED,
                rejection_reason="STOCK_BELOW_RESERVED",
            )
        self.inventory = self.inventory.correct_total_stock(command.target_total_stock)
        return self._result(command.command_id)

    def pause_sales(self, command: PauseProductSalesCommand) -> StoreOwnerInventoryCommandResult:
        self.commands.append(command)
        self.inventory = self.inventory.pause_sales()
        return self._result(command.command_id)

    def resume_sales(self, command: ResumeProductSalesCommand) -> StoreOwnerInventoryCommandResult:
        self.commands.append(command)
        self.inventory = self.inventory.resume_sales()
        return self._result(command.command_id)

    def _result(self, command_id: CommandId) -> StoreOwnerInventoryCommandResult:
        return StoreOwnerInventoryCommandResult(
            command_id=command_id,
            store_id=STORE_ID,
            product_id=PRODUCT_ID,
            status=StoreOwnerInventoryCommandStatus.ACCEPTED,
            inventory=self.inventory,
        )
