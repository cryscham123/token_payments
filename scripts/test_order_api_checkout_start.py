from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import ApiRequest  # noqa: E402
from token_payments.api.orders import OrdersApi  # noqa: E402
from token_payments.contexts.order.adapter import (  # noqa: E402
    PostgresCustomerRepository,
    PostgresOrderRepository,
    PostgresStoreRepository,
)
from token_payments.contexts.order.application import (  # noqa: E402
    CreateOrderCommand,
    CreateOrderItem,
    OrderApplicationError,
    OrderApplicationService,
    OrderErrorCode,
)
from token_payments.contexts.order.domain import (  # noqa: E402
    Address,
    Customer,
    Order,
    Product,
    ProductOptionValuePrice,
    ProductVariantPrice,
    Store,
)
from token_payments.shared.adapter.postgres import PostgresOutboxMessageRepository  # noqa: E402
from token_payments.shared.domain import (  # noqa: E402
    CheckoutEventName,
    Crypto,
    CustomerId,
    MessageId,
    OrderId,
    OutboxMessage,
    OutboxMessageKind,
    ProductId,
    StoreId,
    UserId,
    WalletAddress,
)


NOW = datetime(2026, 5, 10, 6, 30, tzinfo=UTC)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")
TRACKING_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22"
CUSTOMER_ID = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c23")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c24")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25")
USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c26")
OWNER_USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c27")
MESSAGE_ID = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c28")
CUSTOMER_WALLET = WalletAddress("0x1111111111111111111111111111111111111111")
STORE_WALLET = WalletAddress("0x2222222222222222222222222222222222222222")
TOKEN_ADDRESS = WalletAddress("0x3333333333333333333333333333333333333333")
USDC = Crypto(
    amount=Decimal("12.50"),
    symbol="USDC",
    chain_id=11155111,
    token_address=TOKEN_ADDRESS,
    decimals=6,
)


def test_order_use_case_creates_order_snapshot_and_order_created_outbox_event() -> None:
    service, repositories = _service()

    result = service.createOrder(
        CreateOrderCommand(
            authenticated_user_id=USER_ID,
            store_id=STORE_ID,
            delivery_address=Address(id="ship-to", street="2 River Rd"),
            items=(CreateOrderItem(product_id=PRODUCT_ID, quantity=2),),
            order_id=ORDER_ID,
            tracking_id=TRACKING_ID,
            event_message_id=MESSAGE_ID,
            requested_at=NOW,
            causation_id="req-1",
        )
    )

    assert result.order == repositories.orders.saved[0]
    assert result.order.customer_id == CUSTOMER_ID
    assert result.order.tracking_id.value.hex == TRACKING_ID.replace("-", "")
    assert result.order.items[0].product_snapshot.name == "Ledger Mug"
    assert result.order.items[0].product_snapshot.price == USDC
    assert result.order.items[0].quantity == 2
    assert result.order.items[0].sub_total.amount == Decimal("25.00")
    assert result.total_amount == Crypto(
        amount=Decimal("25.00"),
        symbol="USDC",
        chain_id=11155111,
        token_address=TOKEN_ADDRESS,
        decimals=6,
    )

    outbox = repositories.outbox.saved[0]
    assert outbox.kind is OutboxMessageKind.EVENT
    assert outbox.identity == str(MESSAGE_ID)
    assert outbox.name == CheckoutEventName.ORDER_CREATED.value
    assert outbox.topic == "order.events"
    assert outbox.key == str(ORDER_ID)
    assert outbox.headers == {
        "correlationId": str(ORDER_ID),
        "causationId": "req-1",
        "userId": str(USER_ID),
    }
    assert outbox.payload["eventName"] == CheckoutEventName.ORDER_CREATED.value
    assert outbox.payload["orderId"] == str(ORDER_ID)
    assert outbox.payload["customerId"] == str(CUSTOMER_ID)
    assert outbox.payload["userId"] == str(USER_ID)
    assert outbox.payload["storeId"] == str(STORE_ID)
    assert outbox.payload["trackingId"] == str(result.order.tracking_id)
    assert outbox.payload["productId"] == str(PRODUCT_ID)
    assert outbox.payload["quantity"] == 2
    assert outbox.payload["amount"] == {
        "amount": "25.00",
        "symbol": "USDC",
        "chainId": 11155111,
        "tokenAddress": str(TOKEN_ADDRESS),
        "decimals": 6,
    }
    assert outbox.payload["walletFrom"] == str(CUSTOMER_WALLET)
    assert outbox.payload["walletTo"] == str(STORE_WALLET)
    assert outbox.payload["chain"] == {"chainId": 11155111, "name": "chain-11155111"}
    assert outbox.payload["items"] == [
        {
            "orderItemId": str(result.order.items[0].order_item_id),
            "productId": str(PRODUCT_ID),
            "name": "Ledger Mug",
            "quantity": 2,
            "unitPrice": {
                "amount": "12.50",
                "symbol": "USDC",
                "chainId": 11155111,
                "tokenAddress": str(TOKEN_ADDRESS),
                "decimals": 6,
            },
            "subTotal": {
                "amount": "25.00",
                "symbol": "USDC",
                "chainId": 11155111,
                "tokenAddress": str(TOKEN_ADDRESS),
                "decimals": 6,
            },
        }
    ]
    assert outbox.payload["correlationId"] == str(ORDER_ID)
    assert outbox.payload["causationId"] == "req-1"


def test_order_use_case_prices_variant_and_add_on_selection_server_side() -> None:
    service, repositories = _service(store=_variant_store())

    result = service.createOrder(
        CreateOrderCommand(
            authenticated_user_id=USER_ID,
            store_id=STORE_ID,
            delivery_address=Address(id="ship-to", street="2 River Rd"),
            items=(
                CreateOrderItem(
                    product_id=PRODUCT_ID,
                    quantity=2,
                    public_variant_id="hoodie-l",
                    selected_options={"size": "L", "giftWrap": ["premium"]},
                ),
            ),
            order_id=ORDER_ID,
            tracking_id=TRACKING_ID,
            event_message_id=MESSAGE_ID,
            requested_at=NOW,
            causation_id="req-variant",
        )
    )

    item = result.order.items[0]
    assert item.product_snapshot.public_variant_id == "hoodie-l"
    assert dict(item.product_snapshot.selected_options) == {"giftWrap": ["premium"], "size": "L"}
    assert item.product_snapshot.price.amount == Decimal("15.50")
    assert item.sub_total.amount == Decimal("31.00")
    assert result.total_amount.amount == Decimal("31.00")

    payload_item = repositories.outbox.saved[0].payload["items"][0]
    assert payload_item["publicVariantId"] == "hoodie-l"
    assert payload_item["selectedOptions"] == {"giftWrap": ["premium"], "size": "L"}
    assert payload_item["unitPrice"]["amount"] == "15.50"
    assert payload_item["subTotal"]["amount"] == "31.00"
    assert repositories.outbox.saved[0].payload["publicVariantId"] == "hoodie-l"


def test_order_use_case_rejects_mismatched_variant_option_selection() -> None:
    service, _repositories = _service(store=_variant_store())

    with pytest.raises(OrderApplicationError) as exc_info:
        service.createOrder(
            CreateOrderCommand(
                authenticated_user_id=USER_ID,
                store_id=STORE_ID,
                delivery_address=Address(id="ship-to", street="2 River Rd"),
                items=(
                    CreateOrderItem(
                        product_id=PRODUCT_ID,
                        quantity=1,
                        public_variant_id="hoodie-l",
                        selected_options={"size": "M"},
                    ),
                ),
                order_id=ORDER_ID,
                tracking_id=TRACKING_ID,
                event_message_id=MESSAGE_ID,
                requested_at=NOW,
            )
        )

    assert exc_info.value.code is OrderErrorCode.VALIDATION_ERROR
    assert "selected option size does not match variant hoodie-l" in str(exc_info.value)


def test_order_api_returns_tracking_response_and_maps_validation_errors() -> None:
    service, _repositories = _service(store=_variant_store())
    api = OrdersApi(service)

    response = api.create_order(
        ApiRequest(
            request_id="req-1",
            method="POST",
            path="/orders",
            headers={"X-User-Id": str(USER_ID)},
            body={
                "storeId": str(STORE_ID),
                "deliveryAddress": {"id": "ship-to", "street": "2 River Rd"},
                "items": [
                    {
                        "productId": str(PRODUCT_ID),
                        "quantity": 2,
                        "publicVariantId": "hoodie-l",
                        "selectedOptions": {"size": "L", "giftWrap": ["premium"]},
                    }
                ],
            },
            received_at=NOW,
        )
    )

    assert response.status_code == 201
    assert response.request_id == "req-1"
    assert response.body["order"]["orderId"]
    assert response.body["order"]["trackingId"]
    assert response.body["order"]["status"] == "PENDING"
    assert response.body["order"]["totalAmount"] == {
        "amount": "31.00",
        "symbol": "USDC",
        "chainId": 11155111,
        "tokenAddress": str(TOKEN_ADDRESS),
        "decimals": 6,
    }
    assert response.body["order"]["items"][0]["productId"] == str(PRODUCT_ID)
    assert response.body["order"]["items"][0]["publicVariantId"] == "hoodie-l"
    assert response.body["order"]["items"][0]["selectedOptions"] == {"giftWrap": ["premium"], "size": "L"}

    validation_response = api.create_order(
        ApiRequest(
            request_id="req-2",
            method="POST",
            path="/orders",
            headers={"X-User-Id": str(USER_ID)},
            body={
                "storeId": str(STORE_ID),
                "deliveryAddress": {"id": "ship-to", "street": "2 River Rd"},
                "items": [],
            },
            received_at=NOW,
        )
    )

    assert validation_response.status_code == 400
    assert validation_response.body["error"]["code"] == "VALIDATION_ERROR"

    missing_customer = api.create_order(
        ApiRequest(
            request_id="req-3",
            method="POST",
            path="/orders",
            headers={"X-User-Id": str(OWNER_USER_ID)},
            body={
                "storeId": str(STORE_ID),
                "deliveryAddress": {"id": "ship-to", "street": "2 River Rd"},
                "items": [{"productId": str(PRODUCT_ID), "quantity": 1}],
            },
            received_at=NOW,
        )
    )

    assert missing_customer.status_code == 404
    assert missing_customer.body["error"]["code"] == "CUSTOMER_NOT_FOUND"


@pytest.mark.parametrize(
    ("code", "expected_status"),
    [
        (OrderErrorCode.CUSTOMER_NOT_FOUND, 404),
        (OrderErrorCode.STORE_NOT_FOUND, 404),
        (OrderErrorCode.VALIDATION_ERROR, 400),
    ],
)
def test_order_api_maps_all_order_error_codes(code: OrderErrorCode, expected_status: int) -> None:
    api = OrdersApi(RejectingUseCase(code))

    response = api.create_order(
        ApiRequest(
            request_id="req-error",
            method="POST",
            path="/orders",
            headers={"X-User-Id": str(USER_ID)},
            body={
                "storeId": str(STORE_ID),
                "deliveryAddress": {"id": "ship-to", "street": "2 River Rd"},
                "items": [{"productId": str(PRODUCT_ID), "quantity": 1}],
            },
            received_at=NOW,
        )
    )

    assert response.status_code == expected_status
    assert response.body["error"]["code"] == code.value


def test_order_api_resolves_public_store_and_product_ids_via_resolver() -> None:
    service, _repositories = _service()
    resolver = FakeOrderTargetResolver(store_id=str(STORE_ID), product_ids={"prd_demo_001": str(PRODUCT_ID)})
    api = OrdersApi(service, target_resolver=resolver)

    response = api.create_order(
        ApiRequest(
            request_id="req-public",
            method="POST",
            path="/orders",
            headers={"X-User-Id": str(USER_ID)},
            body={
                "publicStoreId": "st_demo_store_001",
                "deliveryAddress": {"id": "ship-to", "street": "2 River Rd"},
                "items": [{"publicProductId": "prd_demo_001", "quantity": 1}],
            },
            received_at=NOW,
        )
    )

    assert response.status_code == 201
    assert resolver.calls == [("st_demo_store_001", ["prd_demo_001"])]
    assert response.body["order"]["items"][0]["productId"] == str(PRODUCT_ID)


def test_order_api_rejects_unresolvable_public_product_id_without_internal_uuid() -> None:
    service, _repositories = _service()
    resolver = FakeOrderTargetResolver(store_id=str(STORE_ID), product_ids={})
    api = OrdersApi(service, target_resolver=resolver)

    response = api.create_order(
        ApiRequest(
            request_id="req-unresolvable",
            method="POST",
            path="/orders",
            headers={"X-User-Id": str(USER_ID)},
            body={
                "publicStoreId": "st_demo_store_001",
                "deliveryAddress": {"id": "ship-to", "street": "2 River Rd"},
                "items": [{"publicProductId": "prd_missing", "quantity": 1}],
            },
            received_at=NOW,
        )
    )

    assert response.status_code == 400
    assert response.body["error"]["code"] == "VALIDATION_ERROR"


def test_order_postgres_repositories_and_outbox_share_injected_connection_boundary() -> None:
    connection = FakePostgresConnection()
    connection.customers[str(USER_ID)] = {
        "customer_id": str(CUSTOMER_ID),
        "user_id": str(USER_ID),
        "wallet_address": str(CUSTOMER_WALLET),
    }
    connection.stores[str(STORE_ID)] = {
        "store_id": str(STORE_ID),
        "owner_user_id": str(OWNER_USER_ID),
        "active": True,
        "store_address_id": "store-address",
        "store_address_street": "1 Market St",
        "store_wallet_address": str(STORE_WALLET),
        "supported_chain_ids": [11155111],
    }
    connection.products[str(STORE_ID)] = [
        {
            "store_id": str(STORE_ID),
            "product_id": str(PRODUCT_ID),
            "name": "Ledger Mug",
            "price_numeric": Decimal("12.50"),
            "price_symbol": "USDC",
            "price_chain_id": 11155111,
            "price_token_address": str(TOKEN_ADDRESS),
            "price_decimals": 6,
        }
    ]
    service = OrderApplicationService(
        customers=PostgresCustomerRepository(connection),
        stores=PostgresStoreRepository(connection),
        orders=PostgresOrderRepository(connection),
        outbox_messages=PostgresOutboxMessageRepository(connection),
    )

    result = service.createOrder(
        CreateOrderCommand(
            authenticated_user_id=USER_ID,
            store_id=STORE_ID,
            delivery_address=Address(id="ship-to", street="2 River Rd"),
            items=(CreateOrderItem(product_id=PRODUCT_ID, quantity=2),),
            order_id=ORDER_ID,
            tracking_id=TRACKING_ID,
            event_message_id=MESSAGE_ID,
            requested_at=NOW,
            causation_id="req-1",
        )
    )

    assert connection.orders[str(ORDER_ID)]["tracking_id"] == str(result.order.tracking_id)
    assert len(connection.order_items) == 1
    assert next(iter(connection.order_items.values()))["product_snapshot_name"] == "Ledger Mug"
    assert connection.outbox_messages[str(MESSAGE_ID)]["name"] == CheckoutEventName.ORDER_CREATED.value
    assert connection.outbox_messages[str(MESSAGE_ID)]["payload"]["amount"]["amount"] == "25.00"
    normalized_sql = _normalize_sql("\n".join(statement.sql for statement in connection.statements))
    assert "from order_customers" in normalized_sql
    assert "from order_stores" in normalized_sql
    assert "from order_store_products" in normalized_sql
    assert "insert into orders" in normalized_sql
    assert "insert into order_items" in normalized_sql
    assert "insert into outbox_messages" in normalized_sql
    assert "commit" not in normalized_sql
    assert "rollback" not in normalized_sql


def test_postgres_order_repository_round_trip() -> None:
    from token_payments.contexts.order.domain import OrderItem, OrderItemId, ProductSnapshot, OrderStatus, TrackingId
    connection = FakePostgresConnection()
    repository = PostgresOrderRepository(connection)

    crypto = Crypto(amount=Decimal("10.00"), symbol="USDC", chain_id=11155111, token_address=TOKEN_ADDRESS, decimals=6)
    item = OrderItem(
        order_item_id=OrderItemId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c2c"),
        order_id=ORDER_ID,
        product_snapshot=ProductSnapshot(
            product_id=PRODUCT_ID,
            created_date=NOW,
            name="Ledger Mug",
            price=crypto,
            public_variant_id="var-1",
            selected_options={"color": "red"},
        ),
        quantity=1,
        sub_total=crypto,
        line_key="lk-1",
    )

    order = Order(
        order_id=ORDER_ID,
        customer_id=CUSTOMER_ID,
        store_id=STORE_ID,
        delivery_address=Address(id="ship-to", street="2 River Rd"),
        items=(item,),
        tracking_id=TrackingId(TRACKING_ID),
        status=OrderStatus.PENDING,
        payment_id=None,
        failure_messages=(),
    )

    repository.save(order)
    retrieved = repository.get(ORDER_ID)

    assert retrieved is not None
    assert retrieved.order_id == ORDER_ID
    assert len(retrieved.items) == 1
    assert retrieved.items[0].product_snapshot.selected_options == {"color": "red"}


def test_order_schema_exports_and_import_boundaries() -> None:
    import token_payments.contexts.order.adapter as order_adapter

    schema = (ROOT / "app/postgres/init.d/001-token-payments-schema.sql").read_text(encoding="utf-8")
    normalized = schema.lower()

    assert {
        "PostgresCustomerRepository",
        "PostgresStoreRepository",
        "PostgresOrderRepository",
    } <= set(order_adapter.__all__)
    for table in ("order_customers", "order_stores", "order_store_products", "orders", "order_items"):
        assert f"create table if not exists {table}" in normalized

    violations: dict[str, list[str]] = {}
    for layer in ("domain", "application"):
        for path in (ROOT / f"app/token_payments/contexts/order/{layer}").glob("**/*.py"):
            illegal = sorted(
                module
                for module in _imported_modules(path)
                if module.startswith("token_payments.api")
                or module.startswith("token_payments.contexts.order.adapter")
                or module.startswith("token_payments.shared.adapter")
                or ".adapter" in module
            )
            if illegal:
                violations[str(path.relative_to(ROOT))] = illegal

    assert violations == {}


@dataclass
class FakeRepositories:
    customers: "FakeCustomerRepository"
    stores: "FakeStoreRepository"
    orders: "FakeOrderRepository"
    outbox: "FakeOutboxMessageRepository"


def _service(store: Store | None = None) -> tuple[OrderApplicationService, FakeRepositories]:
    repositories = FakeRepositories(
        customers=FakeCustomerRepository(),
        stores=FakeStoreRepository(store=store),
        orders=FakeOrderRepository(),
        outbox=FakeOutboxMessageRepository(),
    )
    service = OrderApplicationService(
        customers=repositories.customers,
        stores=repositories.stores,
        orders=repositories.orders,
        outbox_messages=repositories.outbox,
    )
    return service, repositories


def _customer() -> Customer:
    customer = Customer(customer_id=CUSTOMER_ID, user_id=USER_ID)
    object.__setattr__(customer, "_customer_wallet", CUSTOMER_WALLET)
    return customer


def _store() -> Store:
    return Store(
        store_id=STORE_ID,
        owner_user_id=OWNER_USER_ID,
        products=(Product(product_id=PRODUCT_ID, name="Ledger Mug", price=USDC),),
        active=True,
        store_address=Address(id="store-address", street="1 Market St"),
        store_wallet=STORE_WALLET,
        supported_chain_ids=(11155111,),
    )


def _variant_store() -> Store:
    product = Product(
        product_id=PRODUCT_ID,
        name="Ledger Hoodie",
        price=USDC,
        variants={
            "hoodie-m": ProductVariantPrice(
                public_variant_id="hoodie-m",
                option_values={"size": "M"},
                price_delta=Crypto("0.00", "USDC", 11155111, TOKEN_ADDRESS, 6),
            ),
            "hoodie-l": ProductVariantPrice(
                public_variant_id="hoodie-l",
                option_values={"size": "L"},
                price_delta=Crypto("2.00", "USDC", 11155111, TOKEN_ADDRESS, 6),
            ),
        },
        option_values={
            "size:M": ProductOptionValuePrice(
                option_key="size",
                value_key="M",
                display_value="M",
                option_type="VARIANT",
                price_delta=None,
            ),
            "size:L": ProductOptionValuePrice(
                option_key="size",
                value_key="L",
                display_value="L",
                option_type="VARIANT",
                price_delta=None,
            ),
            "giftWrap:premium": ProductOptionValuePrice(
                option_key="giftWrap",
                value_key="premium",
                display_value="Premium wrap",
                option_type="ADD_ON",
                selection_type="MULTI",
                price_delta=Crypto("1.00", "USDC", 11155111, TOKEN_ADDRESS, 6),
            ),
        },
    )
    return Store(
        store_id=STORE_ID,
        owner_user_id=OWNER_USER_ID,
        products=(product,),
        active=True,
        store_address=Address(id="store-address", street="1 Market St"),
        store_wallet=STORE_WALLET,
        supported_chain_ids=(11155111,),
    )


class FakeCustomerRepository:
    def __init__(self) -> None:
        self.customers_by_user_id = {str(USER_ID): _customer()}

    def get_by_user_id(self, user_id: UserId) -> Customer | None:
        return self.customers_by_user_id.get(str(user_id))


class FakeStoreRepository:
    def __init__(self, store: Store | None = None) -> None:
        self.stores_by_id = {str(STORE_ID): store or _store()}

    def get(self, store_id: StoreId) -> Store | None:
        return self.stores_by_id.get(str(store_id))


class FakeOrderRepository:
    def __init__(self) -> None:
        self.saved: list[Order] = []

    def save(self, order: Order) -> None:
        self.saved.append(order)


class FakeOutboxMessageRepository:
    def __init__(self) -> None:
        self.saved: list[OutboxMessage] = []

    def save(self, message: OutboxMessage) -> None:
        self.saved.append(message)


class FakeOrderTargetResolver:
    def __init__(self, *, store_id: str | None, product_ids: dict[str, str]) -> None:
        self._store_id = store_id
        self._product_ids = product_ids
        self.calls: list[tuple[str, list[str]]] = []

    def resolve(self, public_store_id: str, public_product_ids: Any) -> tuple[str | None, dict[str, str]]:
        self.calls.append((public_store_id, list(public_product_ids)))
        return self._store_id, dict(self._product_ids)


class RejectingUseCase:
    def __init__(self, code: OrderErrorCode) -> None:
        self._code = code

    def createOrder(self, command: object) -> object:
        raise OrderApplicationError(self._code, "rejected for test")


@dataclass(frozen=True)
class ExecutedStatement:
    sql: str
    params: Mapping[str, Any]


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, rowcount: int = 0) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class FakePostgresConnection:
    def __init__(self) -> None:
        self.statements: list[ExecutedStatement] = []
        self.customers: dict[str, dict[str, Any]] = {}
        self.stores: dict[str, dict[str, Any]] = {}
        self.products: dict[str, list[dict[str, Any]]] = {}
        self.product_variants: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.product_option_values: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.orders: dict[str, dict[str, Any]] = {}
        self.order_items: dict[str, dict[str, Any]] = {}
        self.outbox_messages: dict[str, dict[str, Any]] = {}

    def execute(self, sql: str, params: Mapping[str, Any] | None = None) -> FakeResult:
        params = dict(params or {})
        self.statements.append(ExecutedStatement(sql=sql, params=params))
        normalized = _normalize_sql(sql)

        if "from order_customers" in normalized and "user_id" in params:
            row = self.customers.get(str(params["user_id"]))
            return FakeResult([dict(row)] if row else [], rowcount=1 if row else 0)
        if "from order_stores" in normalized and "store_id" in params:
            row = self.stores.get(str(params["store_id"]))
            return FakeResult([dict(row)] if row else [], rowcount=1 if row else 0)
        if "from order_store_products" in normalized and "store_id" in params:
            rows = [dict(row) for row in self.products.get(str(params["store_id"]), [])]
            return FakeResult(rows, rowcount=len(rows))
        if "from store_catalog_product_variants" in normalized:
            rows = [dict(row) for row in self.product_variants.get((str(params["store_id"]), str(params["product_id"])), [])]
            return FakeResult(rows, rowcount=len(rows))
        if "from store_catalog_product_option_values" in normalized:
            rows = [dict(row) for row in self.product_option_values.get((str(params["store_id"]), str(params["product_id"])), [])]
            return FakeResult(rows, rowcount=len(rows))
        if "from orders" in normalized and "select" in normalized:
            row = self.orders.get(str(params["order_id"]))
            return FakeResult([dict(row)] if row else [], rowcount=1 if row else 0)
        if "from order_items" in normalized and "select" in normalized:
            rows = [dict(row) for row in self.order_items.values() if str(row.get("order_id")) == str(params["order_id"])]
            return FakeResult(rows, rowcount=len(rows))
        if "insert into orders" in normalized:
            stored_params = dict(params)
            if "failure_messages" in stored_params and isinstance(stored_params["failure_messages"], str):
                import json
                try:
                    stored_params["failure_messages"] = json.loads(stored_params["failure_messages"])
                except Exception:
                    pass
            self.orders[str(params["order_id"])] = stored_params
            return FakeResult(rowcount=1)
        if "insert into order_items" in normalized:
            self.order_items[str(params["order_item_id"])] = params
            return FakeResult(rowcount=1)
        if "insert into outbox_messages" in normalized:
            stored_params = dict(params)
            for field in ("payload", "headers"):
                if field in stored_params and isinstance(stored_params[field], str):
                    import json
                    try:
                        stored_params[field] = json.loads(stored_params[field])
                    except Exception:
                        pass
            self.outbox_messages[str(params["message_identity"])] = stored_params
            return FakeResult(rowcount=1)

        raise AssertionError(f"unexpected SQL: {sql}")


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
