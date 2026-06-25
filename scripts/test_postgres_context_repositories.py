from __future__ import annotations

import ast
import sys
from dataclasses import dataclass, replace
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
    PostgresPaymentHistoryQuery,
    PostgresPaymentRepository,
)
from token_payments.contexts.order.domain import TrackingId  # noqa: E402
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
    default_public_variant_id,
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
ORDER_ID_2 = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c29")
PAYMENT_ID_2 = PaymentId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c2a")
TRACKING_ID = TrackingId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c2d")
WALLET_FROM = WalletAddress("0x1111111111111111111111111111111111111111")
WALLET_TO = WalletAddress("0x2222222222222222222222222222222222222222")
TOKEN_ADDRESS = WalletAddress("0x3333333333333333333333333333333333333333")
CHAIN = ChainNetwork(chain_id=11155111, name="Sepolia")
TX_HASH = TransactionHash("0x" + "ab" * 32)
TX_HASH_2 = TransactionHash("0x" + "cd" * 32)


def test_inventory_repository_round_trips_inventory_and_missing_lookup() -> None:
    connection = FakePostgresConnection()
    repository = PostgresInventoryRepository(connection)
    inventory = _inventory()

    assert repository.get(PRODUCT_ID, STORE_ID) is None

    repository.save(inventory)

    assert repository.get(PRODUCT_ID, STORE_ID) == inventory
    normalized_sql = _normalize_sql("\n".join(statement.sql for statement in connection.statements))
    assert "insert into product_variant_inventory" in normalized_sql
    assert "insert into inventory_reservations" in normalized_sql
    assert "select" in normalized_sql and "from product_variant_inventory" in normalized_sql


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


def test_payment_repository_lists_unconfirmed_receipt_polling_candidates() -> None:
    connection = FakePostgresConnection()
    payments = PostgresPaymentRepository(connection)
    submitted = _submitted_payment()
    confirming = replace(_submitted_payment(payment_id=PAYMENT_ID_2, order_id=ORDER_ID_2, tx_hash=TX_HASH_2), status=PaymentStatus.CONFIRMING)

    payments.save(_awaiting_payment())
    payments.save(submitted)
    payments.save(confirming)
    payments.save(_confirmed_payment(payment_id=PaymentId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c2b"), order_id=OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c2c")))

    candidates = payments.list_receipt_polling_candidates(limit=10)

    assert candidates == (submitted, confirming)
    normalized_sql = _normalize_sql("\n".join(statement.sql for statement in connection.statements))
    assert "receipt_block_number is null" in normalized_sql
    assert "status in ('submitted', 'confirming')" in normalized_sql


def test_payment_repository_falls_back_to_order_items_when_payment_items_are_empty() -> None:
    connection = FakePostgresConnection()
    payments = PostgresPaymentRepository(connection)
    connection.seed_order(ORDER_ID, TRACKING_ID, store_id=STORE_ID)
    connection.seed_order_item(
        order_id=ORDER_ID,
        product_id=PRODUCT_ID,
        product_snapshot_name="Ledger Hoodie",
        unit_price=_amount("14.50"),
        quantity=2,
        public_variant_id="hoodie-l",
        selected_options={"size": "L"},
        line_key="hoodie-l-line",
    )
    payments.save(_submitted_payment())

    payment = payments.get(PAYMENT_ID)

    assert payment is not None
    assert payment.items == (
        {
            "orderLineKey": "hoodie-l-line",
            "productId": str(PRODUCT_ID),
            "publicVariantId": "hoodie-l",
            "name": "Ledger Hoodie",
            "selectedOptions": {"size": "L"},
            "quantity": 2,
            "unitPrice": {
                "amount": "14.50",
                "symbol": "USDC",
                "chainId": 11155111,
                "tokenAddress": str(TOKEN_ADDRESS),
                "decimals": 6,
            },
            "subTotal": {
                "amount": "29.00",
                "symbol": "USDC",
                "chainId": 11155111,
                "tokenAddress": str(TOKEN_ADDRESS),
                "decimals": 6,
            },
        },
    )
    normalized_sql = _normalize_sql("\n".join(statement.sql for statement in connection.statements))
    assert "from order_items" in normalized_sql


def test_payment_history_query_lists_only_authenticated_users_payments() -> None:
    connection = FakePostgresConnection()
    payments = PostgresPaymentRepository(connection)
    history = PostgresPaymentHistoryQuery(connection)
    submitted = _submitted_payment()

    connection.seed_order_customer(USER_ID, CUSTOMER_ID)
    connection.seed_order(ORDER_ID, TRACKING_ID)
    payments.save(submitted)
    payments.save(
        _submitted_payment(
            payment_id=PAYMENT_ID_2,
            order_id=ORDER_ID_2,
            customer_id=CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c2e"),
            tx_hash=TX_HASH_2,
        )
    )

    items = history.list_for_user(USER_ID, statuses=(PaymentStatus.SUBMITTED,), limit=10)

    assert len(items) == 1
    assert items[0].payment_id == PAYMENT_ID
    assert items[0].order_id == ORDER_ID
    assert items[0].tracking_id == TRACKING_ID
    assert items[0].status is PaymentStatus.SUBMITTED
    assert items[0].tx_hash == TX_HASH
    normalized_sql = _normalize_sql("\n".join(statement.sql for statement in connection.statements))
    assert "join order_customers" in normalized_sql
    assert "p.status = any" in normalized_sql


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


def test_store_approval_order_detail_repository_builds_from_order_rows_when_projection_missing() -> None:
    connection = FakePostgresConnection()
    variant_unit_price = _amount("14.75")
    expected_total = _amount("29.50")
    expected_product = Product(
        product_id=PRODUCT_ID,
        name="Ledger Mug - Red / Large",
        price=variant_unit_price,
        available=True,
    )
    connection.seed_order(ORDER_ID, TRACKING_ID, store_id=STORE_ID, status="PENDING")
    connection.seed_order_item(
        order_id=ORDER_ID,
        product_id=PRODUCT_ID,
        product_snapshot_name="Ledger Mug - Red / Large",
        unit_price=variant_unit_price,
        quantity=2,
    )
    PostgresPaymentRepository(connection).save(_confirmed_payment(order_id=ORDER_ID))

    order_detail = PostgresOrderDetailRepository(connection).get(ORDER_ID)

    assert order_detail == OrderDetail(
        order_id=ORDER_ID,
        store_id=STORE_ID,
        order_status="PAID",
        total_amount=expected_total,
        products=(expected_product, expected_product),
    )
    normalized_sql = _normalize_sql("\n".join(statement.sql for statement in connection.statements))
    assert "from store_approval_order_details" in normalized_sql
    assert "from orders" in normalized_sql
    assert "from order_items" in normalized_sql


def test_store_approval_order_detail_fallback_does_not_reopen_cancelled_orders() -> None:
    connection = FakePostgresConnection()
    connection.seed_order(ORDER_ID, TRACKING_ID, store_id=STORE_ID, status="CANCELLED")
    connection.seed_order_item(
        order_id=ORDER_ID,
        product_id=PRODUCT_ID,
        product_snapshot_name="Ledger Mug",
        unit_price=_amount(),
        quantity=1,
    )
    PostgresPaymentRepository(connection).save(_confirmed_payment(order_id=ORDER_ID))

    order_detail = PostgresOrderDetailRepository(connection).get(ORDER_ID)

    assert order_detail is not None
    assert order_detail.order_status == "CANCELLED"


def test_repositories_share_injected_connection_for_transaction_boundary() -> None:
    connection = FakePostgresConnection()
    inventory_repository = PostgresInventoryRepository(connection)
    outbox_repository = PostgresOutboxMessageRepository(connection)

    inventory_repository.save(_inventory())
    outbox_repository.save(_outbox_message())

    assert {id(statement.connection) for statement in connection.statements} == {id(connection)}
    normalized_sql = _normalize_sql("\n".join(statement.sql for statement in connection.statements))
    assert "insert into product_variant_inventory" in normalized_sql
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
        "PostgresPaymentHistoryQuery",
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
        public_variant_id=default_public_variant_id(PRODUCT_ID),
        available_stock=Quantity(7),
        reserved_stock=Quantity(3),
        total_stock=Quantity(10),
        reservations=(reservation,),
    )


def _awaiting_payment(
    *,
    payment_id: PaymentId = PAYMENT_ID,
    order_id: OrderId = ORDER_ID,
    customer_id: CustomerId = CUSTOMER_ID,
) -> Payment:
    return Payment.initialize_payment(
        payment_id=payment_id,
        order_id=order_id,
        customer_id=customer_id,
        amount=_amount(),
        wallet_from=WALLET_FROM,
        wallet_to=WALLET_TO,
        chain_network=CHAIN,
        gas_estimate=_gas_estimate().apply_buffer(),
        expires_at=EXPIRES_AT,
        status=PaymentStatus.AWAITING_SIGNATURE,
    )


def _submitted_payment(
    *,
    payment_id: PaymentId = PAYMENT_ID,
    order_id: OrderId = ORDER_ID,
    customer_id: CustomerId = CUSTOMER_ID,
    tx_hash: TransactionHash = TX_HASH,
) -> Payment:
    return _awaiting_payment(payment_id=payment_id, order_id=order_id, customer_id=customer_id).submit_tx_hash(tx_hash)


def _confirmed_payment(
    *,
    payment_id: PaymentId = PAYMENT_ID,
    order_id: OrderId = ORDER_ID,
    tx_hash: TransactionHash = TX_HASH,
) -> Payment:
    return (
        _submitted_payment(payment_id=payment_id, order_id=order_id, tx_hash=tx_hash)
        .confirm_payment(_receipt(tx_hash=tx_hash))
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
        products=(Product(product_id=PRODUCT_ID, name="Ledger Mug", price=_amount(), available=True),),
    )


def _product() -> Product:
    # Store catalog projection no longer carries price (not used for approval).
    return Product(product_id=PRODUCT_ID, name="Ledger Mug", available=True)


def _amount(amount: Decimal | str = Decimal("12.50")) -> Crypto:
    return Crypto(
        amount=amount,
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


def _receipt(*, tx_hash: TransactionHash = TX_HASH) -> TransactionReceipt:
    return TransactionReceipt(hash=tx_hash, block_number=12345, gas_used=21000)


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


def _payment_item_from_order_item(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "orderLineKey": row.get("line_key"),
        "productId": row["product_id"],
        "publicVariantId": row.get("public_variant_id"),
        "name": row["product_snapshot_name"],
        "selectedOptions": row.get("selected_options") or {},
        "quantity": row["quantity"],
        "unitPrice": {
            "amount": format(row["unit_price_numeric"], "f"),
            "symbol": row["unit_price_symbol"],
            "chainId": row["unit_price_chain_id"],
            "tokenAddress": row["unit_price_token_address"],
            "decimals": row["unit_price_decimals"],
        },
        "subTotal": {
            "amount": format(row["subtotal_numeric"], "f"),
            "symbol": row["subtotal_symbol"],
            "chainId": row["subtotal_chain_id"],
            "tokenAddress": row["subtotal_token_address"],
            "decimals": row["subtotal_decimals"],
        },
    }
    return {key: value for key, value in payload.items() if value is not None}


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


def test_open_order_exists_reports_pending_order_for_customer() -> None:
    from token_payments.contexts.order.adapter.postgres import PostgresOrderRepository
    from token_payments.shared.domain import CustomerId

    class _RowResult:
        def __init__(self, rows: list[Any]) -> None:
            self._rows = rows

        def fetchone(self) -> Any:
            return self._rows[0] if self._rows else None

    class _Conn:
        def __init__(self, rows: list[Any]) -> None:
            self._rows = rows
            self.last_sql: str | None = None
            self.last_params: Mapping[str, Any] | None = None

        def execute(self, sql: str, params: Mapping[str, Any] | None = None) -> _RowResult:
            self.last_sql = sql
            self.last_params = params
            return _RowResult(self._rows)

    customer_id = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22")

    has_open = _Conn([(1,)])
    assert PostgresOrderRepository(has_open).open_order_exists(customer_id) is True
    assert "status = 'PENDING'" in has_open.last_sql
    assert has_open.last_params == {"customer_id": str(customer_id)}

    no_open = _Conn([])
    assert PostgresOrderRepository(no_open).open_order_exists(customer_id) is False


class FakePostgresConnection:
    def __init__(self) -> None:
        self.statements: list[ExecutedStatement] = []
        self.product_inventory: dict[tuple[str, str], dict[str, Any]] = {}
        self.product_variant_inventory: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.inventory_reservations: dict[str, dict[str, Any]] = {}
        self.payments: dict[str, dict[str, Any]] = {}
        self.payment_authorizations: dict[str, dict[str, Any]] = {}
        self.order_customers: dict[str, dict[str, Any]] = {}
        self.orders: dict[str, dict[str, Any]] = {}
        self.order_items: dict[str, list[dict[str, Any]]] = {}
        self.store_approval_stores: dict[str, dict[str, Any]] = {}
        self.store_approval_products: dict[tuple[str, str], dict[str, Any]] = {}
        self.store_approval_order_details: dict[str, dict[str, Any]] = {}
        self.outbox: dict[tuple[str, str], dict[str, Any]] = {}

    def execute(self, sql: str, params: Mapping[str, Any] | None = None) -> FakeResult:
        statement = ExecutedStatement(connection=self, sql=sql, params=dict(params or {}))
        self.statements.append(statement)
        normalized_sql = _normalize_sql(sql)

        if "insert into product_variant_inventory" in normalized_sql:
            return self._upsert_product_variant_inventory(statement.params)
        if "insert into product_inventory" in normalized_sql:
            return self._upsert_product_inventory(statement.params)
        if "insert into inventory_reservations" in normalized_sql:
            return self._upsert_inventory_reservation(statement.params)
        if "delete from inventory_reservations" in normalized_sql:
            return self._delete_missing_inventory_reservations(statement.params)
        if "from product_variant_inventory" in normalized_sql and "select" in normalized_sql:
            return self._select_product_variant_inventory(statement.params)
        if "from product_inventory" in normalized_sql and "select" in normalized_sql:
            return self._select_product_inventory(statement.params)
        if "from inventory_reservations" in normalized_sql and "select" in normalized_sql:
            return self._select_inventory_reservations(statement.params)
        if "insert into payments" in normalized_sql:
            return self._upsert_payment(statement.params)
        if "from orders" in normalized_sql and "select" in normalized_sql:
            return self._select_order(statement.params)
        if "from payments p" in normalized_sql and "join order_customers" in normalized_sql:
            return self._select_payment_history(statement.params)
        if "from payments" in normalized_sql and "select" in normalized_sql:
            return self._select_payment(statement.params)
        if "insert into payment_authorizations" in normalized_sql:
            return self._upsert_payment_authorization(statement.params)
        if "from payment_authorizations" in normalized_sql and "select" in normalized_sql:
            return self._select_payment_authorization(statement.params)
        if "from order_items" in normalized_sql and "select" in normalized_sql and "from payments" not in normalized_sql:
            return self._select_order_items(statement.params)
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
                "available": product.available,
            }

    def seed_order_customer(self, user_id: UserId, customer_id: CustomerId) -> None:
        self.order_customers[str(user_id)] = {
            "user_id": str(user_id),
            "customer_id": str(customer_id),
        }

    def seed_order(
        self,
        order_id: OrderId,
        tracking_id: TrackingId,
        *,
        store_id: StoreId = STORE_ID,
        status: str = "PENDING",
    ) -> None:
        self.orders[str(order_id)] = {
            "order_id": str(order_id),
            "tracking_id": str(tracking_id),
            "store_id": str(store_id),
            "status": status,
        }

    def seed_order_item(
        self,
        *,
        order_id: OrderId,
        product_id: ProductId,
        product_snapshot_name: str,
        unit_price: Crypto,
        quantity: int,
        public_variant_id: str | None = None,
        selected_options: Mapping[str, Any] | None = None,
        line_key: str | None = None,
    ) -> None:
        subtotal_amount = unit_price.amount * Decimal(quantity)
        rows = self.order_items.setdefault(str(order_id), [])
        rows.append(
            {
                "order_item_id": f"018f33aa-9e6d-73d8-9dc3-47d6cdcc6f{len(rows):02d}",
                "order_id": str(order_id),
                "product_id": str(product_id),
                "public_variant_id": public_variant_id,
                "selected_options": dict(selected_options or {}),
                "line_key": line_key,
                "product_snapshot_name": product_snapshot_name,
                "unit_price_numeric": unit_price.amount,
                "unit_price_symbol": unit_price.symbol,
                "unit_price_chain_id": unit_price.chain_id,
                "unit_price_token_address": (
                    str(unit_price.token_address) if unit_price.token_address is not None else None
                ),
                "unit_price_decimals": unit_price.decimals,
                "quantity": quantity,
                "subtotal_numeric": subtotal_amount,
                "subtotal_symbol": unit_price.symbol,
                "subtotal_chain_id": unit_price.chain_id,
                "subtotal_token_address": (
                    str(unit_price.token_address) if unit_price.token_address is not None else None
                ),
                "subtotal_decimals": unit_price.decimals,
            }
        )

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

    def _upsert_product_variant_inventory(self, params: Mapping[str, Any]) -> FakeResult:
        key = (str(params["product_id"]), str(params["store_id"]), str(params["public_variant_id"]))
        self.product_variant_inventory[key] = dict(params)
        return FakeResult(rowcount=1)

    def _select_product_inventory(self, params: Mapping[str, Any]) -> FakeResult:
        key = (str(params["product_id"]), str(params["store_id"]))
        row = self.product_inventory.get(key)
        return FakeResult(rows=[dict(row)] if row is not None else [], rowcount=1 if row is not None else 0)

    def _select_product_variant_inventory(self, params: Mapping[str, Any]) -> FakeResult:
        key = (str(params["product_id"]), str(params["store_id"]), str(params["public_variant_id"]))
        row = self.product_variant_inventory.get(key)
        return FakeResult(rows=[dict(row)] if row is not None else [], rowcount=1 if row is not None else 0)

    def _select_inventory_reservations(self, params: Mapping[str, Any]) -> FakeResult:
        requested_variant = params.get("public_variant_id")
        rows = [
            dict(row)
            for row in self.inventory_reservations.values()
            if row["product_id"] == str(params["product_id"])
            and row["store_id"] == str(params["store_id"])
            and row.get("public_variant_id") == requested_variant
        ]
        rows.sort(key=lambda row: (row["created_at"], row["reservation_id"]))
        return FakeResult(rows=rows, rowcount=len(rows))

    def _upsert_payment(self, params: Mapping[str, Any]) -> FakeResult:
        self.payments[str(params["payment_id"])] = dict(params)
        return FakeResult(rowcount=1)

    def _select_payment(self, params: Mapping[str, Any]) -> FakeResult:
        if "limit" in params and "payment_id" not in params:
            rows = [
                self._payment_row_with_item_fallback(row)
                for row in self.payments.values()
                if row["status"] in {"SUBMITTED", "CONFIRMING"}
                and row["tx_hash"] is not None
                and row["receipt_block_number"] is None
            ]
            rows.sort(key=lambda row: row["payment_id"])
            limit = int(params["limit"])
            return FakeResult(rows=rows[:limit], rowcount=len(rows[:limit]))
        row = self.payments.get(str(params["payment_id"]))
        if row is not None:
            row = self._payment_row_with_item_fallback(row)
        return FakeResult(rows=[dict(row)] if row is not None else [], rowcount=1 if row is not None else 0)

    def _select_payment_history(self, params: Mapping[str, Any]) -> FakeResult:
        customer = self.order_customers.get(str(params["user_id"]))
        if customer is None:
            return FakeResult()
        statuses = set(params.get("statuses") or [])
        rows = []
        for row in self.payments.values():
            if row["customer_id"] != customer["customer_id"]:
                continue
            if statuses and row["status"] not in statuses:
                continue
            order = self.orders.get(row["order_id"])
            if order is None:
                continue
            rows.append({**row, "tracking_id": order["tracking_id"], "updated_at": row.get("updated_at", NOW)})
        rows.sort(key=lambda row: (row["updated_at"], row["payment_id"]), reverse=True)
        limit = int(params["limit"])
        return FakeResult(rows=rows[:limit], rowcount=len(rows[:limit]))

    def _upsert_payment_authorization(self, params: Mapping[str, Any]) -> FakeResult:
        self.payment_authorizations[str(params["payment_id"])] = dict(params)
        return FakeResult(rowcount=1)

    def _select_payment_authorization(self, params: Mapping[str, Any]) -> FakeResult:
        row = self.payment_authorizations.get(str(params["payment_id"]))
        return FakeResult(rows=[dict(row)] if row is not None else [], rowcount=1 if row is not None else 0)

    def _select_order(self, params: Mapping[str, Any]) -> FakeResult:
        order_id = str(params["order_id"])
        row = self.orders.get(order_id)
        if row is None:
            return FakeResult()
        selected = dict(row)
        selected["order_status"] = (
            "PAID"
            if selected["status"] == "PENDING" and self._has_confirmed_payment(order_id)
            else selected["status"]
        )
        return FakeResult(rows=[selected], rowcount=1)

    def _select_order_items(self, params: Mapping[str, Any]) -> FakeResult:
        rows = [dict(row) for row in self.order_items.get(str(params["order_id"]), [])]
        rows.sort(key=lambda row: row["order_item_id"])
        return FakeResult(rows=rows, rowcount=len(rows))

    def _has_confirmed_payment(self, order_id: str) -> bool:
        return any(row["order_id"] == order_id and row["status"] == "CONFIRMED" for row in self.payments.values())

    def _payment_row_with_item_fallback(self, row: Mapping[str, Any]) -> dict[str, Any]:
        items = row.get("items")
        if items not in (None, "[]", []):
            return dict(row)
        fallback_items = [_payment_item_from_order_item(item) for item in self.order_items.get(str(row["order_id"]), [])]
        return {**row, "items": fallback_items}

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
