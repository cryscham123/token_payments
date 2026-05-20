from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.inventory.adapter import PostgresInventoryRepository  # noqa: E402
from token_payments.contexts.inventory.domain import (  # noqa: E402
    InventoryReservation,
    ProductInventory,
    Quantity,
    ReservationId,
    ReservationStatus,
)
from token_payments.contexts.payment.adapter import (  # noqa: E402
    PostgresPaymentAuthorizationRepository,
    PostgresPaymentRepository,
)
from token_payments.contexts.payment.domain import (  # noqa: E402
    AuthorizationStatus,
    GasEstimate,
    Payment,
    PaymentAuthorization,
    PaymentStatus,
    TransactionReceipt,
    TransactionSignatureRequest,
)
from token_payments.contexts.store_approval.adapter import (  # noqa: E402
    PostgresOrderDetailRepository,
    PostgresStoreRepository,
)
from token_payments.contexts.store_approval.domain import (  # noqa: E402
    ApprovalStatus,
    OrderDetail,
    Product,
    Store,
)
from token_payments.shared.adapter.postgres import PostgresOutboxMessageRepository  # noqa: E402
from token_payments.shared.domain import (  # noqa: E402
    ChainNetwork,
    CheckoutEventName,
    Crypto,
    CustomerId,
    EventMetadata,
    MessageId,
    OrderId,
    OutboxMessage,
    PaymentId,
    ProductId,
    StoreId,
    TransactionHash,
    UserId,
    WalletAddress,
)


NOW = datetime(2026, 5, 10, 9, 0, tzinfo=UTC)
EXPIRES_AT = NOW + timedelta(minutes=15)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")
PAYMENT_ID = PaymentId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22")
CUSTOMER_ID = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c23")
USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c24")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c26")
RESERVATION_ID = ReservationId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c27")
MESSAGE_ID = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c28")
WALLET_FROM = WalletAddress("0x1111111111111111111111111111111111111111")
WALLET_TO = WalletAddress("0x2222222222222222222222222222222222222222")
TOKEN_ADDRESS = WalletAddress("0x3333333333333333333333333333333333333333")
CHAIN = ChainNetwork(chain_id=11155111, name="Sepolia")
TX_HASH = TransactionHash("0x" + "ab" * 32)


def test_inventory_repository_round_trips_inventory_and_missing_lookup() -> None:
    connection = FakePostgresConnection()
    repository = PostgresInventoryRepository(connection)
    inventory = _inventory()

    assert repository.get(PRODUCT_ID, STORE_ID) is None

    repository.save(inventory)

    assert repository.get(PRODUCT_ID, STORE_ID) == inventory
    normalized_sql = _normalize_sql("\n".join(statement.sql for statement in connection.statements))
    assert "insert into product_inventory" in normalized_sql
    assert "insert into inventory_reservations" in normalized_sql
    assert "select" in normalized_sql and "from product_inventory" in normalized_sql


def test_payment_repositories_round_trip_payment_authorization_and_missing_lookup() -> None:
    connection = FakePostgresConnection()
    payments = PostgresPaymentRepository(connection)
    authorizations = PostgresPaymentAuthorizationRepository(connection)
    payment = _confirmed_payment()
    authorization = _authorized_authorization()

    assert payments.get(PAYMENT_ID) is None
    assert authorizations.get(PAYMENT_ID) is None

    payments.save(payment)
    authorizations.save(authorization)

    assert payments.get(PAYMENT_ID) == payment
    assert authorizations.get(PAYMENT_ID) == authorization
    assert connection.payments[str(PAYMENT_ID)]["receipt_block_number"] == 12345
    assert connection.payment_authorizations[str(PAYMENT_ID)]["tx_hash"] == str(TX_HASH)


def test_store_approval_repositories_round_trip_store_and_order_detail() -> None:
    connection = FakePostgresConnection()
    connection.seed_store(_store())
    stores = PostgresStoreRepository(connection)
    order_details = PostgresOrderDetailRepository(connection)
    approved_order = _order_detail().approve()

    assert stores.get(StoreId("118f33aa-9e6d-73d8-9dc3-47d6cdcc6c25")) is None
    assert order_details.get(ORDER_ID) is None

    order_details.save(approved_order)

    assert order_details.get(ORDER_ID) == approved_order
    assert stores.get(STORE_ID) == Store(
        store_id=STORE_ID,
        owner_user_id=USER_ID,
        products=(_product(),),
        active=True,
        order_details=(approved_order,),
    )


def test_repositories_share_injected_connection_for_transaction_boundary() -> None:
    connection = FakePostgresConnection()
    inventory_repository = PostgresInventoryRepository(connection)
    outbox_repository = PostgresOutboxMessageRepository(connection)

    inventory_repository.save(_inventory())
    outbox_repository.save(_outbox_message())

    assert {id(statement.connection) for statement in connection.statements} == {id(connection)}
    normalized_sql = _normalize_sql("\n".join(statement.sql for statement in connection.statements))
    assert "insert into product_inventory" in normalized_sql
    assert "insert into outbox_messages" in normalized_sql
    assert "commit" not in normalized_sql
    assert "rollback" not in normalized_sql


def test_context_adapter_public_contract_exports_postgres_repositories() -> None:
    import token_payments.contexts.inventory.adapter as inventory_adapter
    import token_payments.contexts.payment.adapter as payment_adapter
    import token_payments.contexts.store_approval.adapter as store_approval_adapter

    assert set(inventory_adapter.__all__) == {
        "PostgresInventoryAuditRepository",
        "PostgresInventoryQueryRepository",
        "PostgresInventoryRepository",
    }
    assert set(payment_adapter.__all__) == {
        "PostgresPaymentAuthorizationRepository",
        "PostgresPaymentRepository",
    }
    assert set(store_approval_adapter.__all__) == {
        "PostgresOrderDetailRepository",
        "PostgresStoreRepository",
    }


def test_inventory_query_sql_casts_nullable_store_filter_for_live_psycopg() -> None:
    import token_payments.contexts.inventory.adapter.postgres as inventory_postgres

    combined_sql = "\n".join(
        (
            inventory_postgres.SELECT_INVENTORY_SNAPSHOTS_SQL,
            inventory_postgres.SELECT_OWNER_INVENTORY_SNAPSHOTS_SQL,
        )
    )

    assert "%(store_id)s::uuid IS NULL" in combined_sql
    assert "inv.store_id = %(store_id)s::uuid" in combined_sql
    assert "store_catalog_store_memberships" in combined_sql
    assert "memberships.user_id = %(owner_user_id)s::uuid" in combined_sql


def test_domain_and_application_layers_do_not_import_postgres_adapters() -> None:
    violations: dict[str, list[str]] = {}
    for context in ("inventory", "payment", "store_approval"):
        for layer in ("domain", "application"):
            for path in (ROOT / f"app/token_payments/contexts/{context}/{layer}").glob("**/*.py"):
                illegal = sorted(
                    module
                    for module in _imported_modules(path)
                    if module.startswith(f"token_payments.contexts.{context}.adapter")
                    or module.startswith("token_payments.shared.adapter.postgres")
                )
                if illegal:
                    violations[str(path.relative_to(ROOT))] = illegal

    assert violations == {}


def _inventory() -> ProductInventory:
    reservation = InventoryReservation(
        reservation_id=RESERVATION_ID,
        order_id=ORDER_ID,
        reserved_qty=Quantity(3),
        status=ReservationStatus.PENDING,
        created_at=NOW,
    )
    return ProductInventory(
        product_id=PRODUCT_ID,
        store_id=STORE_ID,
        available_stock=Quantity(7),
        reserved_stock=Quantity(3),
        total_stock=Quantity(10),
        reservations=(reservation,),
    )


def _confirmed_payment() -> Payment:
    return (
        Payment.initialize_payment(
            payment_id=PAYMENT_ID,
            order_id=ORDER_ID,
            customer_id=CUSTOMER_ID,
            amount=_amount(),
            wallet_from=WALLET_FROM,
            wallet_to=WALLET_TO,
            chain_network=CHAIN,
            gas_estimate=_gas_estimate().apply_buffer(),
            expires_at=EXPIRES_AT,
            status=PaymentStatus.AWAITING_SIGNATURE,
        )
        .submit_tx_hash(TX_HASH)
        .confirm_payment(_receipt())
    )


def _authorized_authorization() -> PaymentAuthorization:
    return PaymentAuthorization.request_transaction_signature(
        payment_id=PAYMENT_ID,
        user_id=USER_ID,
        wallet=WALLET_FROM,
        chain_network=CHAIN,
        signature_request=_signature_request(),
    ).authorize_tx_hash(TX_HASH, authorized_at=NOW + timedelta(minutes=2))


def _store() -> Store:
    return Store(store_id=STORE_ID, owner_user_id=USER_ID, products=(_product(),), active=True)


def _order_detail() -> OrderDetail:
    return OrderDetail(
        order_id=ORDER_ID,
        store_id=STORE_ID,
        order_status="PAID",
        total_amount=_amount(),
        products=(_product(),),
    )


def _product() -> Product:
    return Product(product_id=PRODUCT_ID, name="Ledger Mug", price=_amount(), available=True)


def _amount() -> Crypto:
    return Crypto(
        amount=Decimal("12.50"),
        symbol="USDC",
        chain_id=11155111,
        token_address=TOKEN_ADDRESS,
        decimals=6,
    )


def _gas_estimate() -> GasEstimate:
    return GasEstimate(
        estimated_fee=Crypto(
            amount=Decimal("0.0100"),
            symbol="ETH",
            chain_id=11155111,
            token_address=None,
            decimals=18,
        ),
        gas_limit=21000,
        buffer_rate=Decimal("0.10"),
    )


def _signature_request() -> TransactionSignatureRequest:
    return TransactionSignatureRequest(
        request_id="payment-request-123",
        amount=_amount(),
        to=WALLET_TO,
        expires_at=EXPIRES_AT,
    )


def _receipt() -> TransactionReceipt:
    return TransactionReceipt(hash=TX_HASH, block_number=12345, gas_used=21000)


def _outbox_message() -> OutboxMessage:
    metadata = EventMetadata(
        message_id=MESSAGE_ID,
        name=CheckoutEventName.INVENTORY_RESERVED,
        aggregate_id=f"{STORE_ID}:{PRODUCT_ID}",
        occurred_at=NOW,
        correlation_id=str(ORDER_ID),
    )
    return OutboxMessage.record_event(
        metadata=metadata,
        topic="inventory.events",
        key=str(ORDER_ID),
        payload={"orderId": str(ORDER_ID), "productId": str(PRODUCT_ID)},
    )


def _crypto_payload(value: Crypto) -> dict[str, Any]:
    return {
        "amount": format(value.amount, "f"),
        "symbol": value.symbol,
        "chainId": value.chain_id,
        "tokenAddress": str(value.token_address) if value.token_address is not None else None,
        "decimals": value.decimals,
    }


def _product_payload(product: Product) -> dict[str, Any]:
    return {
        "productId": str(product.product_id),
        "name": product.name,
        "price": _crypto_payload(product.price),
        "available": product.available,
    }


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.lower().split())


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


@dataclass(frozen=True)
class ExecutedStatement:
    connection: "FakePostgresConnection"
    sql: str
    params: Mapping[str, Any]


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, rowcount: int = 0) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def fetchone(self) -> dict[str, Any] | None:
        if not self._rows:
            return None
        return self._rows[0]


class FakePostgresConnection:
    def __init__(self) -> None:
        self.statements: list[ExecutedStatement] = []
        self.product_inventory: dict[tuple[str, str], dict[str, Any]] = {}
        self.inventory_reservations: dict[str, dict[str, Any]] = {}
        self.payments: dict[str, dict[str, Any]] = {}
        self.payment_authorizations: dict[str, dict[str, Any]] = {}
        self.store_approval_stores: dict[str, dict[str, Any]] = {}
        self.store_approval_products: dict[tuple[str, str], dict[str, Any]] = {}
        self.store_approval_order_details: dict[str, dict[str, Any]] = {}
        self.outbox: dict[tuple[str, str], dict[str, Any]] = {}

    def execute(self, sql: str, params: Mapping[str, Any] | None = None) -> FakeResult:
        statement = ExecutedStatement(connection=self, sql=sql, params=dict(params or {}))
        self.statements.append(statement)
        normalized_sql = _normalize_sql(sql)

        if "insert into product_inventory" in normalized_sql:
            return self._upsert_product_inventory(statement.params)
        if "insert into inventory_reservations" in normalized_sql:
            return self._upsert_inventory_reservation(statement.params)
        if "delete from inventory_reservations" in normalized_sql:
            return self._delete_missing_inventory_reservations(statement.params)
        if "from product_inventory" in normalized_sql and "select" in normalized_sql:
            return self._select_product_inventory(statement.params)
        if "from inventory_reservations" in normalized_sql and "select" in normalized_sql:
            return self._select_inventory_reservations(statement.params)
        if "insert into payments" in normalized_sql:
            return self._upsert_payment(statement.params)
        if "from payments" in normalized_sql and "select" in normalized_sql:
            return self._select_payment(statement.params)
        if "insert into payment_authorizations" in normalized_sql:
            return self._upsert_payment_authorization(statement.params)
        if "from payment_authorizations" in normalized_sql and "select" in normalized_sql:
            return self._select_payment_authorization(statement.params)
        if "from store_approval_stores" in normalized_sql and "select" in normalized_sql:
            return self._select_store(statement.params)
        if "from store_approval_products" in normalized_sql and "select" in normalized_sql:
            return self._select_store_products(statement.params)
        if "insert into store_approval_order_details" in normalized_sql:
            return self._upsert_order_detail(statement.params)
        if "from store_approval_order_details" in normalized_sql and "select" in normalized_sql:
            return self._select_order_details(statement.params)
        if "insert into outbox_messages" in normalized_sql:
            return self._insert_outbox(statement.params)
        raise AssertionError(f"unexpected SQL: {sql}")

    def seed_store(self, store: Store) -> None:
        self.store_approval_stores[str(store.store_id)] = {
            "store_id": str(store.store_id),
            "owner_user_id": str(store.owner_user_id),
            "active": store.active,
        }
        for product in store.products:
            self.store_approval_products[(str(store.store_id), str(product.product_id))] = {
                "store_id": str(store.store_id),
                "product_id": str(product.product_id),
                "name": product.name,
                "price_numeric": product.price.amount,
                "price_symbol": product.price.symbol,
                "price_chain_id": product.price.chain_id,
                "price_token_address": (
                    str(product.price.token_address) if product.price.token_address is not None else None
                ),
                "price_decimals": product.price.decimals,
                "available": product.available,
            }

    def _upsert_product_inventory(self, params: Mapping[str, Any]) -> FakeResult:
        key = (str(params["product_id"]), str(params["store_id"]))
        self.product_inventory[key] = dict(params)
        return FakeResult(rowcount=1)

    def _upsert_inventory_reservation(self, params: Mapping[str, Any]) -> FakeResult:
        self.inventory_reservations[str(params["reservation_id"])] = dict(params)
        return FakeResult(rowcount=1)

    def _delete_missing_inventory_reservations(self, params: Mapping[str, Any]) -> FakeResult:
        product_id = str(params["product_id"])
        store_id = str(params["store_id"])
        keep = {str(value) for value in params.get("reservation_ids", ())}
        before = len(self.inventory_reservations)
        self.inventory_reservations = {
            reservation_id: row
            for reservation_id, row in self.inventory_reservations.items()
            if row["product_id"] != product_id or row["store_id"] != store_id or reservation_id in keep
        }
        return FakeResult(rowcount=before - len(self.inventory_reservations))

    def _select_product_inventory(self, params: Mapping[str, Any]) -> FakeResult:
        key = (str(params["product_id"]), str(params["store_id"]))
        row = self.product_inventory.get(key)
        return FakeResult(rows=[dict(row)] if row is not None else [], rowcount=1 if row is not None else 0)

    def _select_inventory_reservations(self, params: Mapping[str, Any]) -> FakeResult:
        rows = [
            dict(row)
            for row in self.inventory_reservations.values()
            if row["product_id"] == str(params["product_id"]) and row["store_id"] == str(params["store_id"])
        ]
        rows.sort(key=lambda row: (row["created_at"], row["reservation_id"]))
        return FakeResult(rows=rows, rowcount=len(rows))

    def _upsert_payment(self, params: Mapping[str, Any]) -> FakeResult:
        self.payments[str(params["payment_id"])] = dict(params)
        return FakeResult(rowcount=1)

    def _select_payment(self, params: Mapping[str, Any]) -> FakeResult:
        row = self.payments.get(str(params["payment_id"]))
        return FakeResult(rows=[dict(row)] if row is not None else [], rowcount=1 if row is not None else 0)

    def _upsert_payment_authorization(self, params: Mapping[str, Any]) -> FakeResult:
        self.payment_authorizations[str(params["payment_id"])] = dict(params)
        return FakeResult(rowcount=1)

    def _select_payment_authorization(self, params: Mapping[str, Any]) -> FakeResult:
        row = self.payment_authorizations.get(str(params["payment_id"]))
        return FakeResult(rows=[dict(row)] if row is not None else [], rowcount=1 if row is not None else 0)

    def _select_store(self, params: Mapping[str, Any]) -> FakeResult:
        row = self.store_approval_stores.get(str(params["store_id"]))
        return FakeResult(rows=[dict(row)] if row is not None else [], rowcount=1 if row is not None else 0)

    def _select_store_products(self, params: Mapping[str, Any]) -> FakeResult:
        store_id = str(params["store_id"])
        rows = [dict(row) for key, row in self.store_approval_products.items() if key[0] == store_id]
        rows.sort(key=lambda row: row["product_id"])
        return FakeResult(rows=rows, rowcount=len(rows))

    def _upsert_order_detail(self, params: Mapping[str, Any]) -> FakeResult:
        self.store_approval_order_details[str(params["order_id"])] = dict(params)
        return FakeResult(rowcount=1)

    def _select_order_details(self, params: Mapping[str, Any]) -> FakeResult:
        if "order_id" in params:
            row = self.store_approval_order_details.get(str(params["order_id"]))
            return FakeResult(rows=[dict(row)] if row is not None else [], rowcount=1 if row is not None else 0)
        store_id = str(params["store_id"])
        rows = [
            dict(row)
            for row in self.store_approval_order_details.values()
            if row["store_id"] == store_id
        ]
        rows.sort(key=lambda row: row["order_id"])
        return FakeResult(rows=rows, rowcount=len(rows))

    def _insert_outbox(self, params: Mapping[str, Any]) -> FakeResult:
        key = (str(params["kind"]), str(params["message_identity"]))
        if key not in self.outbox:
            self.outbox[key] = dict(params)
            return FakeResult(rowcount=1)
        return FakeResult(rowcount=0)
