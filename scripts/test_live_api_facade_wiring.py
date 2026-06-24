from __future__ import annotations

import ast
import json
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import http_route_manifest  # noqa: E402
from token_payments.contexts.auth.domain import UserRole  # noqa: E402
from token_payments.runtime import (  # noqa: E402
    LiveRuntimeConfig,
    LiveRuntimeDependencies,
    build_live_api_facades,
    build_live_api_router,
)
from token_payments.shared.domain import (  # noqa: E402
    CustomerId,
    OrderId,
    PaymentId,
    ProductId,
    StoreId,
    UserId,
    default_public_variant_id,
)


NOW = datetime(2026, 5, 17, 10, 0, tzinfo=UTC)
EXPIRES_AT = NOW + timedelta(minutes=15)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc7101")
TRACKING_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc7102"
ORDER_MESSAGE_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc7103"
INVENTORY_MESSAGE_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc7104"
PAYMENT_ID = PaymentId("018f33aa-9e6d-73d8-9dc3-47d6cdcc7105")
PAYMENT_MESSAGE_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc7106"
CUSTOMER_ID = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc7107")
USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc7108")
OWNER_USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc7109")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc710a")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc710b")
VARIANT_ID = "hoodie-l"
CUSTOMER_WALLET = "0x1111111111111111111111111111111111111111"
STORE_WALLET = "0x2222222222222222222222222222222222222222"
TOKEN_ADDRESS = "0x3333333333333333333333333333333333333333"
TX_HASH = "0x" + "ab" * 32

FORBIDDEN_LIVE_WIRING_IMPORT_ROOTS = {
    "asyncpg",
    "confluent_kafka",
    "docker",
    "fastapi",
    "kafka",
    "psycopg",
    "psycopg2",
    "requests",
    "socket",
    "starlette",
    "uvicorn",
    "web3",
}


def test_build_live_api_router_uses_route_registration_helpers_and_manifest_contract(monkeypatch) -> None:
    import token_payments.runtime.composition as composition

    session = FakePostgresSession()
    calls: list[str] = []
    original_helpers = {
        "auth": composition.register_auth_routes,
        "orders": composition.register_order_routes,
        "checkout": composition.register_checkout_routes,
        "payments": composition.register_payment_routes,
        "catalog": composition.register_store_catalog_routes,
        "inventory": composition.register_store_owner_inventory_routes,
        "merchant": composition.register_merchant_membership_routes,
        "operator": composition.register_operator_routes,
        "operator_action": composition.register_operator_action_routes,
    }

    def _wrap(name: str):
        def wrapper(router, api, **kwargs):
            calls.append(name)
            return original_helpers[name](router, api, **kwargs)

        return wrapper

    monkeypatch.setattr(composition, "register_auth_routes", _wrap("auth"))
    monkeypatch.setattr(composition, "register_order_routes", _wrap("orders"))
    monkeypatch.setattr(composition, "register_checkout_routes", _wrap("checkout"))
    monkeypatch.setattr(composition, "register_payment_routes", _wrap("payments"))
    monkeypatch.setattr(composition, "register_store_catalog_routes", _wrap("catalog"))
    monkeypatch.setattr(composition, "register_store_owner_inventory_routes", _wrap("inventory"))
    monkeypatch.setattr(composition, "register_merchant_membership_routes", _wrap("merchant"))
    monkeypatch.setattr(composition, "register_operator_routes", _wrap("operator"))
    monkeypatch.setattr(composition, "register_operator_action_routes", _wrap("operator_action"))

    router = build_live_api_router(config=_config(), dependencies=_dependencies(session))

    assert calls == ["auth", "orders", "checkout", "payments", "catalog", "inventory", "merchant", "operator", "operator_action"]
    assert [(route.method, route.path_template, route.operation_id) for route in router.routes] == [
        (entry["method"], entry["path"], entry["operationId"]) for entry in http_route_manifest()
    ]
    assert len(router.routes) == 57


def test_live_api_facade_wiring_dispatches_routes_through_injected_transactional_repositories() -> None:
    session = FakePostgresSession()
    session.seed_catalog()
    dependencies = _dependencies(session)
    facades = build_live_api_facades(config=_config(), dependencies=dependencies)
    router = build_live_api_router(config=_config(), dependencies=dependencies)

    assert type(facades.auth).__name__ == "AuthApi"
    assert type(facades.orders).__name__ == "OrdersApi"
    assert type(facades.checkout).__name__ == "CheckoutApi"
    assert type(facades.payments).__name__ == "PaymentsApi"
    assert type(facades.catalog).__name__ == "StoreCatalogApi"
    assert type(facades.inventory).__name__ == "StoreOwnerInventoryApi"
    assert type(facades.merchant).__name__ == "MerchantMembershipApi"
    assert type(facades.merchant._use_case).__name__ == "_TransactionalMerchantMembershipUseCase"
    assert type(facades.operator).__name__ == "OperatorApi"
    assert type(facades.operator_action).__name__ == "OperatorActionApi"

    create_order = router.handle(
        "POST",
        "/orders",
        headers=_customer_headers("req-create-order"),
        body=_json_body(
            {
                "storeId": str(STORE_ID),
                "deliveryAddress": {"id": "ship-to", "street": "2 River Rd"},
                "items": [{"productId": str(PRODUCT_ID), "quantity": 2}],
            }
        ),
        received_at=NOW,
    )

    create_payload = _json(create_order.body)
    assert create_order.status_code == 201
    assert create_payload["order"]["orderId"] == str(ORDER_ID)
    assert create_payload["order"]["trackingId"] == TRACKING_ID
    assert create_payload["order"]["totalAmount"]["amount"] == "25.00"
    assert _transaction_sql(session, 1, "insert into orders")
    assert _transaction_sql(session, 1, "insert into outbox_messages")
    assert _transaction_sql(session, 1, "insert into product_variant_inventory")
    assert _transaction_sql(session, 1, "insert into inventory_reservations")
    assert _transaction_sql(session, 1, "insert into payments")
    assert _transaction_sql(session, 1, "insert into payment_authorizations")
    assert _transaction_sql(session, 1, "insert into processed_commands")
    default_variant_id = default_public_variant_id(PRODUCT_ID)
    assert session.variant_inventory[(str(PRODUCT_ID), str(STORE_ID), default_variant_id)]["available_stock"] == 23
    assert session.variant_inventory[(str(PRODUCT_ID), str(STORE_ID), default_variant_id)]["reserved_stock"] == 2
    payment_items = json.loads(session.payments[str(PAYMENT_ID)]["items"])
    assert len(payment_items) == 1
    assert payment_items[0]["productId"] == str(PRODUCT_ID)
    assert payment_items[0]["quantity"] == 2
    assert payment_items[0]["unitPrice"]["amount"] == "12.50"

    tracking = router.handle(
        "GET",
        f"/checkouts/tracking/{TRACKING_ID}",
        headers={"X-Request-Id": "req-track", "X-User-Id": str(USER_ID)},
        received_at=NOW,
    )
    assert tracking.status_code == 200
    tracking_payload = _json(tracking.body)
    assert tracking_payload["checkout"]["orderId"] == str(ORDER_ID)
    assert tracking_payload["checkout"]["paymentId"] == str(PAYMENT_ID)
    assert tracking_payload["checkout"]["currentStep"] == "AWAITING_SIGNATURE"
    assert tracking_payload["checkout"]["pendingAction"] == "SIGN_PAYMENT"
    assert tracking_payload["checkout"]["paymentRequest"] == {
        "requestId": "payment-request-live-wiring",
        "amount": {
            "amount": "25.00",
            "symbol": "USDC",
            "chainId": 11155111,
            "tokenAddress": TOKEN_ADDRESS,
            "decimals": 6,
        },
        "to": STORE_WALLET,
        "expiresAt": EXPIRES_AT.isoformat(),
    }
    assert tracking_payload["checkout"]["gasEstimate"] == {
        "estimatedFee": {
            "amount": "0.0100",
            "symbol": "ETH",
            "chainId": 11155111,
            "tokenAddress": None,
            "decimals": 18,
        },
        "gasLimit": 21000,
        "bufferRate": "0.10",
        "maxFee": {
            "amount": "0.011000",
            "symbol": "ETH",
            "chainId": 11155111,
            "tokenAddress": None,
            "decimals": 18,
        },
    }

    submit_tx = router.handle(
        "POST",
        "/payments/transaction-hashes",
        headers=_customer_headers("req-submit-tx"),
        body=_json_body(
            {
                "trackingId": str(TRACKING_ID),
                "txHash": TX_HASH,
            }
        ),
        received_at=NOW,
    )
    assert submit_tx.status_code == 202
    submit_payload = _json(submit_tx.body)
    assert submit_payload["payment"]["status"] == "TX_SUBMITTED"
    assert submit_payload["payment"]["trackingId"] == str(TRACKING_ID)
    assert submit_payload["payment"]["txHash"] == TX_HASH
    submit_tx_id = session.statement_tx("insert into payments", after_tx=2)
    assert submit_tx_id is not None
    assert session.statement_tx("insert into payment_authorizations", after_tx=2) == submit_tx_id
    assert session.statement_tx("insert into processed_commands", after_tx=2) == submit_tx_id

    payment_history = router.handle(
        "GET",
        "/payments",
        query={"limit": 20},
        headers=_customer_headers("req-payment-history"),
        received_at=NOW,
    )
    assert payment_history.status_code == 200
    payment_history_payload = _json(payment_history.body)
    assert payment_history_payload["payments"][0]["orderId"] == str(ORDER_ID)
    assert payment_history_payload["payments"][0]["trackingId"] == str(TRACKING_ID)
    assert payment_history_payload["payments"][0]["status"] == "SUBMITTED"
    assert payment_history_payload["payments"][0]["txHash"] == TX_HASH

    dashboard = router.handle(
        "GET",
        "/operator/dashboard",
        query={"context": "orders,payments,outbox", "limit": 10},
        headers=_admin_headers("req-dashboard"),
        received_at=NOW,
    )
    assert dashboard.status_code == 200
    dashboard_payload = _json(dashboard.body)
    assert dashboard_payload["orders"][0]["orderId"] == str(ORDER_ID)
    assert dashboard_payload["payments"][0]["paymentId"] == str(PAYMENT_ID)
    assert dashboard_payload["outbox"][0]["messageId"] == ORDER_MESSAGE_ID

    cancel = router.handle(
        "POST",
        f"/operator/orders/{ORDER_ID}/cancel",
        headers=_admin_headers("req-cancel"),
        body=_json_body({"reason": "operator cancelled abandoned checkout"}),
        received_at=NOW,
    )
    assert cancel.status_code == 202
    cancel_payload = _json(cancel.body)
    assert cancel_payload["action"] == "cancelOrder"
    assert cancel_payload["status"] == "accepted"
    assert cancel_payload["target"] == {"kind": "order", "id": str(ORDER_ID)}
    assert cancel_payload["commandId"] == f"{ORDER_ID}:CancelOrderCommand"
    assert cancel_payload["auditId"] is None

    retry = router.handle(
        "POST",
        f"/operator/outbox/{ORDER_MESSAGE_ID}/retry",
        headers=_admin_headers("req-retry"),
        body=_json_body({"kind": "EVENT", "reason": "broker recovered"}),
        received_at=NOW,
    )
    assert retry.status_code == 202
    retry_payload = _json(retry.body)
    assert retry_payload["action"] == "retryOutboxMessage"
    assert retry_payload["status"] == "accepted"
    assert retry_payload["messageId"] == ORDER_MESSAGE_ID
    assert retry_payload["details"]["outboxActionStatus"] == "RETRYABLE"

    replay = router.handle(
        "POST",
        f"/operator/messages/{ORDER_ID}:CancelOrderCommand/replay",
        headers=_admin_headers("req-replay"),
        body=_json_body({"kind": "COMMAND", "reason": "handler fix deployed"}),
        received_at=NOW,
    )
    assert replay.status_code == 202
    replay_payload = _json(replay.body)
    assert replay_payload["action"] == "replayMessage"
    assert replay_payload["status"] == "accepted"
    assert replay_payload["messageId"] == f"{ORDER_ID}:CancelOrderCommand"
    assert replay_payload["details"]["outboxActionStatus"] == "RECORDED"
    assert replay_payload["details"]["idempotencyRecordsDeleted"] is False

    assert session.begin_count >= 7
    assert session.rollback_count == 0
    assert session.commit_count >= 5


def test_live_order_start_targets_variant_inventory_and_persists_payment_items() -> None:
    session = FakePostgresSession()
    session.seed_variant_catalog()
    dependencies = _dependencies(session)
    router = build_live_api_router(config=_config(), dependencies=dependencies)

    create_order = router.handle(
        "POST",
        "/orders",
        headers=_customer_headers("req-create-order-variant"),
        body=_json_body(
            {
                "storeId": str(STORE_ID),
                "deliveryAddress": {"id": "ship-to", "street": "2 River Rd"},
                "items": [
                    {
                        "productId": str(PRODUCT_ID),
                        "quantity": 2,
                        "publicVariantId": VARIANT_ID,
                        "selectedOptions": {"size": "L"},
                    }
                ],
            }
        ),
        received_at=NOW,
    )

    create_payload = _json(create_order.body)
    assert create_order.status_code == 201
    assert create_payload["order"]["totalAmount"]["amount"] == "29.00"
    # Stock is tracked only on the selected variant; the base row holds no stock.
    assert "available_stock" not in session.inventory[(str(PRODUCT_ID), str(STORE_ID))]
    assert session.variant_inventory[(str(PRODUCT_ID), str(STORE_ID), VARIANT_ID)]["available_stock"] == 3
    assert session.variant_inventory[(str(PRODUCT_ID), str(STORE_ID), VARIANT_ID)]["reserved_stock"] == 2
    assert next(iter(session.inventory_reservations.values()))["public_variant_id"] == VARIANT_ID

    payment_items = json.loads(session.payments[str(PAYMENT_ID)]["items"])
    assert len(payment_items) == 1
    assert payment_items[0]["productId"] == str(PRODUCT_ID)
    assert payment_items[0]["publicVariantId"] == VARIANT_ID
    assert payment_items[0]["selectedOptions"] == {"size": "L"}
    assert payment_items[0]["quantity"] == 2
    assert payment_items[0]["unitPrice"]["amount"] == "14.50"


def test_live_api_facade_wiring_source_avoids_frameworks_drivers_sockets_and_docker() -> None:
    imported_roots = _imported_roots(ROOT / "app/token_payments/runtime/composition.py")

    assert imported_roots.isdisjoint(FORBIDDEN_LIVE_WIRING_IMPORT_ROOTS)


def _config() -> LiveRuntimeConfig:
    return LiveRuntimeConfig(
        blockchain_chain_id=11155111,
        blockchain_native_symbol="ETH",
        blockchain_native_decimals=18,
        blockchain_gas_buffer_rate=Decimal("0.10"),
    )


def _dependencies(session: "FakePostgresSession") -> LiveRuntimeDependencies:
    return LiveRuntimeDependencies(
        postgres_session_factory=lambda: session,
        kafka_producer=FakeKafkaProducer(),
        wallet_signature_client=FakeWalletSignatureClient(),
        blockchain_client=FakeBlockchainClient(),
        clock=FakeClock(NOW),
        id_generator=SequenceIdGenerator(
            (str(ORDER_ID), TRACKING_ID, ORDER_MESSAGE_ID, INVENTORY_MESSAGE_ID, str(PAYMENT_ID), PAYMENT_MESSAGE_ID)
        ),
    )


def _customer_headers(request_id: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Request-Id": request_id,
        "X-User-Id": str(USER_ID),
    }


def _admin_headers(request_id: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Request-Id": request_id,
        "X-User-Id": "operator-1",
        "X-User-Scopes": "operator:read,operator:action,outbox:retry",
    }


def _json_body(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _json(body: bytes) -> dict[str, Any]:
    decoded = json.loads(body)
    assert isinstance(decoded, dict)
    return decoded


def _transaction_sql(session: "FakePostgresSession", tx_id: int, needle: str) -> bool:
    return any(statement.tx_id == tx_id and needle in _normalize_sql(statement.sql) for statement in session.statements)


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".", 1)[0])
    return modules


class FakeClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def now(self) -> datetime:
        return self.current


class SequenceIdGenerator:
    def __init__(self, values: tuple[str, ...]) -> None:
        self._values = list(values)

    def new_id(self) -> str:
        if not self._values:
            raise AssertionError("deterministic id generator exhausted")
        return self._values.pop(0)


class FakeKafkaProducer:
    def __init__(self) -> None:
        self.messages: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def send(self, *args: Any, **kwargs: Any) -> None:
        self.messages.append((args, kwargs))


class FakeWalletSignatureClient:
    def recover_address(self, message: str, signature: str) -> str:
        return CUSTOMER_WALLET


class FakeBlockchainClient:
    def estimate_gas(self, **request: Any) -> dict[str, Any]:
        return {
            "estimatedFee": {
                "amount": "0.0100",
                "symbol": "ETH",
                "chainId": 11155111,
                "tokenAddress": None,
                "decimals": 18,
            },
            "gasLimit": 21000,
            "bufferRate": "0.10",
        }

    def create_signature_request(self, **request: Any) -> dict[str, Any]:
        return {
            "requestId": "payment-request-live-wiring",
            "amount": request["amount"],
            "to": request["wallet_to"],
            "expiresAt": request["expires_at"],
        }

    def get_transaction_receipt(self, **request: Any) -> None:
        return None

    def refund_payment(self, **request: Any) -> dict[str, Any]:
        return {"hash": "0x" + "cd" * 32, "blockNumber": 99, "gasUsed": 21000}


@dataclass(frozen=True)
class ExecutedStatement:
    sql: str
    params: Mapping[str, Any]
    tx_id: int | None


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, rowcount: int = 0) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class FakeTransaction:
    def __init__(self, session: "FakePostgresSession", tx_id: int) -> None:
        self._session = session
        self.tx_id = tx_id
        self.committed = False
        self.rolled_back = False

    def commit(self) -> None:
        self.committed = True
        self._session.commit_count += 1

    def rollback(self) -> None:
        self.rolled_back = True
        self._session.rollback_count += 1


class FakePostgresSession:
    def __init__(self) -> None:
        self.begin_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self._current_tx_id: int | None = None
        self.statements: list[ExecutedStatement] = []
        self.customers: dict[str, dict[str, Any]] = {}
        self.stores: dict[str, dict[str, Any]] = {}
        self.products: dict[str, list[dict[str, Any]]] = {}
        self.product_variants: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.product_option_values: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.orders: dict[str, dict[str, Any]] = {}
        self.order_items: dict[str, list[dict[str, Any]]] = {}
        self.inventory: dict[tuple[str, str], dict[str, Any]] = {}
        self.variant_inventory: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.inventory_reservations: dict[str, dict[str, Any]] = {}
        self.payments: dict[str, dict[str, Any]] = {}
        self.payment_authorizations: dict[str, dict[str, Any]] = {}
        self.outbox: dict[tuple[str, str], dict[str, Any]] = {}
        self.processed_commands: set[tuple[str, str]] = set()

    @contextmanager
    def begin(self):
        self.begin_count += 1
        tx = FakeTransaction(self, self.begin_count)
        self._current_tx_id = tx.tx_id
        try:
            yield tx
        finally:
            self._current_tx_id = None

    def execute(self, sql: str, params: Mapping[str, Any] | None = None) -> FakeResult:
        params = dict(params or {})
        self.statements.append(ExecutedStatement(sql=sql, params=params, tx_id=self._current_tx_id))
        normalized = _normalize_sql(sql)

        if "insert into orders" in normalized:
            row = dict(params)
            existing = self.orders.get(str(params["order_id"]), {})
            row.setdefault("created_at", existing.get("created_at", NOW))
            row["updated_at"] = NOW
            self.orders[str(params["order_id"])] = row
            return FakeResult(rowcount=1)
        if "insert into order_items" in normalized:
            self.order_items.setdefault(str(params["order_id"]), [])
            rows = [row for row in self.order_items[str(params["order_id"])] if row["order_item_id"] != params["order_item_id"]]
            rows.append(dict(params))
            self.order_items[str(params["order_id"])] = rows
            return FakeResult(rowcount=1)
        if "insert into product_inventory" in normalized:
            row = dict(params)
            row.setdefault("updated_at", NOW)
            self.inventory[(str(params["product_id"]), str(params["store_id"]))] = row
            return FakeResult(rowcount=1)
        if "insert into product_variant_inventory" in normalized:
            row = dict(params)
            row.setdefault("updated_at", NOW)
            self.variant_inventory[
                (str(params["product_id"]), str(params["store_id"]), str(params["public_variant_id"]))
            ] = row
            return FakeResult(rowcount=1)
        if "insert into inventory_reservations" in normalized:
            row = dict(params)
            row.setdefault("updated_at", NOW)
            self.inventory_reservations[str(params["reservation_id"])] = row
            return FakeResult(rowcount=1)
        if "delete from inventory_reservations" in normalized:
            if "reservation_ids" in params:
                keep = {str(value) for value in params["reservation_ids"]}
                self.inventory_reservations = {
                    reservation_id: row
                    for reservation_id, row in self.inventory_reservations.items()
                    if (
                        not _reservation_matches(row, params)
                        or reservation_id in keep
                    )
                }
            else:
                self.inventory_reservations = {
                    reservation_id: row
                    for reservation_id, row in self.inventory_reservations.items()
                    if not _reservation_matches(row, params)
                }
            return FakeResult(rowcount=1)
        if "insert into payments" in normalized:
            row = dict(params)
            existing = self.payments.get(str(params["payment_id"]), {})
            row.setdefault("created_at", existing.get("created_at", NOW))
            row["updated_at"] = NOW
            self.payments[str(params["payment_id"])] = row
            return FakeResult(rowcount=1)
        if "insert into payment_authorizations" in normalized:
            row = dict(params)
            existing = self.payment_authorizations.get(str(params["payment_id"]), {})
            row["updated_at"] = NOW
            if "amount_numeric" not in row and existing:
                row.update({key: value for key, value in existing.items() if key not in row})
            self.payment_authorizations[str(params["payment_id"])] = row
            return FakeResult(rowcount=1)
        if "insert into outbox_messages" in normalized:
            row = dict(params)
            self.outbox[(str(row["kind"]), str(row["message_identity"]))] = row
            return FakeResult(rowcount=1)
        if "insert into processed_commands" in normalized:
            key = (str(params["handler"]), str(params["command_id"]))
            inserted = key not in self.processed_commands
            self.processed_commands.add(key)
            return FakeResult([{"inserted": 1}] if inserted else [], rowcount=1 if inserted else 0)

        if "from order_customers" in normalized:
            return _one(self.customers.get(str(params["user_id"])))
        if "from order_stores" in normalized:
            return _one(self.stores.get(str(params["store_id"])))
        if "from order_store_products" in normalized:
            return FakeResult([dict(row) for row in self.products.get(str(params["store_id"]), [])])
        if "from store_catalog_product_variants" in normalized:
            return FakeResult([
                dict(row)
                for row in self.product_variants.get((str(params["store_id"]), str(params["product_id"])), [])
            ])
        if "from store_catalog_product_option_values" in normalized:
            return FakeResult([
                dict(row)
                for row in self.product_option_values.get((str(params["store_id"]), str(params["product_id"])), [])
            ])
        if "from orders where order_id" in normalized:
            return _one(self.orders.get(str(params["order_id"])))
        if "from order_items" in normalized and "order_id" in params:
            return FakeResult([dict(row) for row in self.order_items.get(str(params["order_id"]), [])])
        if "from product_variant_inventory" in normalized and "where product_id" in normalized:
            return _one(
                self.variant_inventory.get(
                    (str(params["product_id"]), str(params["store_id"]), str(params["public_variant_id"]))
                )
            )
        if "from product_inventory" in normalized and "where product_id" in normalized:
            return _one(self.inventory.get((str(params["product_id"]), str(params["store_id"]))))
        if "from inventory_reservations" in normalized:
            rows = [
                dict(row)
                for row in self.inventory_reservations.values()
                if _reservation_matches(row, params)
            ]
            return FakeResult(rows)
        if "from orders where tracking_id" in normalized:
            row = next((order for order in self.orders.values() if order["tracking_id"] == str(params["tracking_id"])), None)
            return _one(_tracking_order_row(row))
        if "from orders where order_id" in normalized:
            return _one(_tracking_order_row(self.orders.get(str(params["order_id"]))))
        if "from payments where payment_id" in normalized:
            return _one(self.payments.get(str(params["payment_id"])))
        if "from payments where order_id" in normalized:
            row = next((payment for payment in self.payments.values() if payment["order_id"] == str(params["order_id"])), None)
            if row is not None and "payment_updated_at" in normalized:
                row = {**row, "payment_updated_at": row.get("updated_at", NOW)}
            return _one(row)
        if "from payment_authorizations where payment_id" in normalized:
            row = self.payment_authorizations.get(str(params["payment_id"]))
            if row is not None and "authorization_updated_at" in normalized:
                row = {**row, "authorization_updated_at": row.get("updated_at", NOW)}
            return _one(row)
        if "from payments p join orders o" in normalized and "join order_customers c" in normalized:
            return FakeResult(self._payment_history_rows(params))
        if "from outbox_messages where message_key" in normalized:
            rows = [
                _outbox_status_row(row)
                for row in self.outbox.values()
                if row["message_key"] == str(params["order_id"])
            ]
            return FakeResult(rows)
        if "from processed_commands" in normalized:
            key = (str(params["handler"]), str(params["command_id"]))
            return FakeResult([{"processed": 1}] if key in self.processed_commands else [])
        if "from orders left join payments" in normalized:
            return FakeResult(self._operator_order_rows(params))
        if "from payments left join orders" in normalized:
            return FakeResult(self._operator_payment_rows(params))
        if "from outbox_messages" in normalized:
            return FakeResult(self._operator_outbox_rows(params))

        return FakeResult()

    def seed_catalog(self) -> None:
        self.customers[str(USER_ID)] = {
            "customer_id": str(CUSTOMER_ID),
            "user_id": str(USER_ID),
            "wallet_address": CUSTOMER_WALLET,
        }
        self.stores[str(STORE_ID)] = {
            "store_id": str(STORE_ID),
            "owner_user_id": str(OWNER_USER_ID),
            "active": True,
            "store_address_id": "store-address",
            "store_address_street": "1 Market St",
            "store_wallet_address": STORE_WALLET,
            "supported_chain_ids": [11155111],
        }
        self.products[str(STORE_ID)] = [
            {
                "store_id": str(STORE_ID),
                "product_id": str(PRODUCT_ID),
                "name": "Ledger Mug",
                "price_numeric": Decimal("12.50"),
                "price_symbol": "USDC",
                "price_chain_id": 11155111,
                "price_token_address": TOKEN_ADDRESS,
                "price_decimals": 6,
            }
        ]
        self.inventory[(str(PRODUCT_ID), str(STORE_ID))] = {
            "product_id": str(PRODUCT_ID),
            "store_id": str(STORE_ID),
            "sale_status": "ACTIVE",
            "updated_at": NOW,
        }
        # Option-less products carry their stock on a hidden default variant.
        default_variant_id = default_public_variant_id(PRODUCT_ID)
        self.variant_inventory[(str(PRODUCT_ID), str(STORE_ID), default_variant_id)] = {
            "product_id": str(PRODUCT_ID),
            "store_id": str(STORE_ID),
            "public_variant_id": default_variant_id,
            "available_stock": 25,
            "reserved_stock": 0,
            "total_stock": 25,
            "sale_status": "ACTIVE",
            "updated_at": NOW,
        }

    def seed_variant_catalog(self) -> None:
        self.seed_catalog()
        self.products[str(STORE_ID)][0]["name"] = "Ledger Hoodie"
        self.product_variants[(str(STORE_ID), str(PRODUCT_ID))] = [
            {
                "public_variant_id": VARIANT_ID,
                "option_values": {"size": "L"},
                "active": True,
                "status": "ACTIVE",
                "price_delta_numeric": Decimal("2.00"),
                "price_delta_symbol": "USDC",
                "price_delta_chain_id": 11155111,
                "price_delta_token_address": TOKEN_ADDRESS,
                "price_delta_decimals": 6,
            }
        ]
        self.variant_inventory[(str(PRODUCT_ID), str(STORE_ID), VARIANT_ID)] = {
            "product_id": str(PRODUCT_ID),
            "store_id": str(STORE_ID),
            "public_variant_id": VARIANT_ID,
            "available_stock": 5,
            "reserved_stock": 0,
            "total_stock": 5,
            "sale_status": "ACTIVE",
            "updated_at": NOW,
        }

    def seed_awaiting_payment(self) -> None:
        self.payments[str(PAYMENT_ID)] = {
            "payment_id": str(PAYMENT_ID),
            "order_id": str(ORDER_ID),
            "customer_id": str(CUSTOMER_ID),
            "amount_numeric": Decimal("25.00"),
            "amount_symbol": "USDC",
            "amount_chain_id": 11155111,
            "amount_token_address": TOKEN_ADDRESS,
            "amount_decimals": 6,
            "status": "AWAITING_SIGNATURE",
            "wallet_from": CUSTOMER_WALLET,
            "wallet_to": STORE_WALLET,
            "chain_id": 11155111,
            "chain_name": "Sepolia",
            "tx_hash": None,
            "gas_estimated_fee": Decimal("0.0100"),
            "gas_fee_symbol": "ETH",
            "gas_fee_chain_id": 11155111,
            "gas_fee_token_address": None,
            "gas_fee_decimals": 18,
            "gas_limit": 21000,
            "gas_buffer_rate": Decimal("0.10"),
            "gas_max_fee": Decimal("0.011000"),
            "receipt_block_number": None,
            "receipt_gas_used": None,
            "failure_reason": None,
            "refund_tx_hash": None,
            "refund_block_number": None,
            "refund_gas_used": None,
            "expires_at": EXPIRES_AT,
            "created_at": NOW,
            "updated_at": NOW,
        }
        self.payment_authorizations[str(PAYMENT_ID)] = {
            "payment_id": str(PAYMENT_ID),
            "user_id": str(USER_ID),
            "wallet_address": CUSTOMER_WALLET,
            "chain_id": 11155111,
            "chain_name": "Sepolia",
            "request_id": "payment-request-live-wiring",
            "amount_numeric": Decimal("25.00"),
            "amount_symbol": "USDC",
            "amount_chain_id": 11155111,
            "amount_token_address": TOKEN_ADDRESS,
            "amount_decimals": 6,
            "to_wallet_address": STORE_WALLET,
            "status": "REQUESTED",
            "tx_hash": None,
            "expires_at": EXPIRES_AT,
            "authorized_at": None,
            "updated_at": NOW,
        }

    def statement_tx(self, needle: str, *, after_tx: int = 0) -> int | None:
        for statement in self.statements:
            if statement.tx_id is not None and statement.tx_id > after_tx and needle in _normalize_sql(statement.sql):
                return statement.tx_id
        return None

    def _operator_order_rows(self, params: Mapping[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for order in self.orders.values():
            if params.get("order_id") is not None and str(order["order_id"]) != str(params["order_id"]):
                continue
            payment = next((row for row in self.payments.values() if row["order_id"] == order["order_id"]), None)
            latest = next((row for row in reversed(list(self.outbox.values())) if row["message_key"] == order["order_id"]), None)
            rows.append(
                {
                    **order,
                    "payment_status": payment["status"] if payment else None,
                    "payment_failure_reason": payment["failure_reason"] if payment else None,
                    "latest_event": latest["name"] if latest else None,
                }
            )
        return rows[: int(params.get("limit") or len(rows))]

    def _operator_payment_rows(self, params: Mapping[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for payment in self.payments.values():
            if params.get("payment_id") is not None and payment["payment_id"] != str(params["payment_id"]):
                continue
            if params.get("order_id") is not None and payment["order_id"] != str(params["order_id"]):
                continue
            rows.append(dict(payment))
        return rows[: int(params.get("limit") or len(rows))]

    def _payment_history_rows(self, params: Mapping[str, Any]) -> list[dict[str, Any]]:
        statuses = set(params.get("statuses") or [])
        rows = []
        customer = self.customers.get(str(params["user_id"]))
        if customer is None:
            return rows
        for payment in self.payments.values():
            if payment["customer_id"] != customer["customer_id"]:
                continue
            if statuses and payment["status"] not in statuses:
                continue
            order = self.orders.get(payment["order_id"])
            if order is None:
                continue
            rows.append({**payment, "tracking_id": order["tracking_id"], "items": []})
        rows.sort(key=lambda row: (row.get("updated_at", NOW), row["payment_id"]), reverse=True)
        return rows[: int(params.get("limit") or len(rows))]

    def _operator_outbox_rows(self, params: Mapping[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for row in self.outbox.values():
            if params.get("message_identity") is not None and row["message_identity"] != str(params["message_identity"]):
                continue
            if params.get("message_key") is not None and row["message_key"] != str(params["message_key"]):
                continue
            if params.get("kind") is not None and row["kind"] != str(params["kind"]):
                continue
            rows.append(_operator_outbox_row(row))
        return rows[: int(params.get("limit") or len(rows))]


def _one(row: Mapping[str, Any] | None) -> FakeResult:
    return FakeResult([dict(row)] if row is not None else [], rowcount=1 if row is not None else 0)


def _reservation_matches(row: Mapping[str, Any], params: Mapping[str, Any]) -> bool:
    public_variant_id = params.get("public_variant_id")
    row_public_variant_id = row.get("public_variant_id")
    return (
        row["product_id"] == str(params["product_id"])
        and row["store_id"] == str(params["store_id"])
        and (
            row_public_variant_id is None
            if public_variant_id is None
            else str(row_public_variant_id) == str(public_variant_id)
        )
    )


def _tracking_order_row(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "order_id": row["order_id"],
        "tracking_id": row["tracking_id"],
        "status": row["status"],
        "failure_messages": row["failure_messages"],
        "order_updated_at": row.get("updated_at", NOW),
    }


def _outbox_status_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "message_identity": row["message_identity"],
        "name": row["name"],
        "status": row["status"],
        "outbox_updated_at": row.get("published_at") or row["created_at"],
    }


def _operator_outbox_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "message_identity": row["message_identity"],
        "kind": row["kind"],
        "name": row["name"],
        "topic": row["topic"],
        "message_key": row["message_key"],
        "status": row["status"],
        "failure_count": row["failure_count"],
        "last_error": row["last_error"],
        "created_at": row["created_at"],
        "published_at": row["published_at"],
        "updated_at": row.get("published_at") or row["created_at"],
    }


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.lower().split())
