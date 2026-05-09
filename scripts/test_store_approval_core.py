from __future__ import annotations

import ast
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import get_type_hints


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.store_approval.application import (  # noqa: E402
    OrderDetailRepository,
    OutboxMessageRepository,
    ProcessedCommandRepository,
    RequestStoreApprovalCommand,
    StoreApprovalResultStatus,
    StoreApprovalService,
    StoreRepository,
)
from token_payments.contexts.store_approval.domain import (  # noqa: E402
    ApprovalStatus,
    OrderApprovedEvent,
    OrderDetail,
    OrderRejectedEvent,
    Product,
    Store,
)
from token_payments.shared.domain import (  # noqa: E402
    CheckoutCommandName,
    CheckoutEventName,
    CommandId,
    Crypto,
    IdempotencyDecision,
    MessageId,
    OrderId,
    OutboxMessage,
    OutboxMessageKind,
    ProcessedCommand,
    ProductId,
    StoreId,
    UserId,
    WalletAddress,
)


NOW = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c23")
OWNER_USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c24")
OTHER_USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25")
COMMAND_ID = CommandId.for_order_action(ORDER_ID, CheckoutCommandName.REQUEST_STORE_APPROVAL)
EVENT_MESSAGE_ID = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c26")
TOKEN_ADDRESS = WalletAddress("0x3333333333333333333333333333333333333333")


def test_store_constructs_approved_event_when_owner_store_and_products_match() -> None:
    event = _store().construct_order_approval(
        order_detail=_order_detail(),
        owner_user_id=OWNER_USER_ID,
        decided_at=NOW,
    )

    assert event == OrderApprovedEvent(order=_order_detail().approve(), created_at=NOW)
    assert event.order.approval_status == ApprovalStatus.APPROVED


def test_approval_service_saves_approved_order_detail_outbox_and_processed_command() -> None:
    order_details = FakeOrderDetailRepository(_order_detail())
    processed_commands = FakeProcessedCommandRepository()
    outbox_messages = FakeOutboxMessageRepository()
    service = StoreApprovalService(
        store_repository=FakeStoreRepository(_store()),
        order_detail_repository=order_details,
        processed_commands=processed_commands,
        outbox_messages=outbox_messages,
    )

    result = service.request_store_approval(_command())

    assert result.status == StoreApprovalResultStatus.APPROVED
    assert result.duplicate_decision is None
    assert result.order_detail is not None
    assert result.order_detail.approval_status == ApprovalStatus.APPROVED
    assert result.event == OrderApprovedEvent(order=result.order_detail, created_at=NOW)
    assert order_details.saved == [result.order_detail]

    outbox = outbox_messages.saved[0]
    assert outbox.kind == OutboxMessageKind.EVENT
    assert outbox.name == CheckoutEventName.ORDER_APPROVED.value
    assert outbox.topic == "store-approval.events"
    assert outbox.key == str(ORDER_ID)
    assert outbox.identity == str(EVENT_MESSAGE_ID)
    assert outbox.headers["correlationId"] == str(ORDER_ID)
    assert outbox.headers["causationId"] == str(COMMAND_ID)
    assert outbox.headers["sourceCausationId"] == "payment-confirmed-message"
    assert outbox.payload["orderId"] == str(ORDER_ID)
    assert outbox.payload["storeId"] == str(STORE_ID)
    assert outbox.payload["ownerUserId"] == str(OWNER_USER_ID)
    assert outbox.payload["approvalStatus"] == ApprovalStatus.APPROVED.value
    assert outbox.payload["productIds"] == [str(PRODUCT_ID)]
    assert outbox.payload["occurredAt"] == NOW.isoformat()

    assert processed_commands.records == [
        ProcessedCommand.record(
            command_id=COMMAND_ID,
            handler=StoreApprovalService.HANDLER_NAME,
            processed_at=NOW,
            order_id=ORDER_ID,
        )
    ]


def test_owner_mismatch_is_rejected_with_specific_reason_and_outbox_event() -> None:
    service = _service(store=_store(), order_detail=_order_detail())

    result = service.request_store_approval(_command(owner_user_id=OTHER_USER_ID))

    assert result.status == StoreApprovalResultStatus.REJECTED
    assert isinstance(result.event, OrderRejectedEvent)
    assert result.order_detail is not None
    assert result.order_detail.approval_status == ApprovalStatus.REJECTED
    assert result.event.rejection_reasons == (f"OWNER_MISMATCH: user {OTHER_USER_ID} cannot approve store {STORE_ID}",)
    assert result.outbox_message is not None
    assert result.outbox_message.name == CheckoutEventName.ORDER_REJECTED.value
    assert result.outbox_message.payload["rejectionReasons"] == [
        f"OWNER_MISMATCH: user {OTHER_USER_ID} cannot approve store {STORE_ID}"
    ]


def test_inactive_store_is_rejected_without_approving_order_detail() -> None:
    store = _store(active=False)
    service = _service(store=store, order_detail=_order_detail())

    result = service.request_store_approval(_command())

    assert result.status == StoreApprovalResultStatus.REJECTED
    assert isinstance(result.event, OrderRejectedEvent)
    assert result.order_detail is not None
    assert result.order_detail.approval_status == ApprovalStatus.REJECTED
    assert result.event.rejection_reasons == (f"INACTIVE_STORE: store {STORE_ID} is inactive",)


def test_product_mismatch_and_inactive_product_are_rejected_with_all_reasons() -> None:
    order_detail = _order_detail(product=_product(name="Ledger Mug v2"))
    inactive_store_product = _product(available=False)
    service = _service(store=_store(product=inactive_store_product), order_detail=order_detail)

    result = service.request_store_approval(_command())

    assert result.status == StoreApprovalResultStatus.REJECTED
    assert isinstance(result.event, OrderRejectedEvent)
    assert result.event.rejection_reasons == (
        f"PRODUCT_INACTIVE: product {PRODUCT_ID} is inactive",
        f"PRODUCT_MISMATCH: product {PRODUCT_ID} snapshot does not match store catalog",
    )
    assert result.outbox_message is not None
    assert result.outbox_message.payload["approvalStatus"] == ApprovalStatus.REJECTED.value
    assert result.outbox_message.payload["rejectionReasons"] == list(result.event.rejection_reasons)


def test_duplicate_approval_command_is_ignored_before_loading_or_saving_aggregates() -> None:
    stores = FakeStoreRepository(_store())
    order_details = FakeOrderDetailRepository(_order_detail())
    processed_commands = FakeProcessedCommandRepository(
        existing={(StoreApprovalService.HANDLER_NAME, str(COMMAND_ID))}
    )
    outbox_messages = FakeOutboxMessageRepository()
    service = StoreApprovalService(
        store_repository=stores,
        order_detail_repository=order_details,
        processed_commands=processed_commands,
        outbox_messages=outbox_messages,
    )

    result = service.request_store_approval(_command())

    assert result.status == StoreApprovalResultStatus.DUPLICATE_IGNORED
    assert result.order_detail is None
    assert result.event is None
    assert result.outbox_message is None
    assert result.duplicate_decision == IdempotencyDecision.IGNORE_DUPLICATE
    assert stores.get_calls == []
    assert order_details.get_calls == []
    assert order_details.saved == []
    assert outbox_messages.saved == []
    assert processed_commands.records == []


def test_store_approval_public_contracts_are_protocols_and_exports() -> None:
    import token_payments.contexts.store_approval.application as application
    import token_payments.contexts.store_approval.domain as domain

    for port in (StoreRepository, OrderDetailRepository, ProcessedCommandRepository, OutboxMessageRepository):
        assert getattr(port, "_is_protocol", False), f"{port.__name__} must be a Protocol"

    hints = get_type_hints(StoreRepository.get)
    assert hints["return"] == Store | None

    assert {
        "ApprovalStatus",
        "OrderApprovedEvent",
        "OrderDetail",
        "OrderRejectedEvent",
        "Product",
        "Store",
    } <= set(domain.__all__)
    assert {
        "OrderDetailRepository",
        "OutboxMessageRepository",
        "ProcessedCommandRepository",
        "RequestStoreApprovalCommand",
        "StoreApprovalResultStatus",
        "StoreApprovalService",
        "StoreRepository",
    } <= set(application.__all__)


def test_store_approval_layers_do_not_import_external_adapters_or_clients() -> None:
    forbidden_roots = {
        "blockchain",
        "kafka",
        "metamask",
        "psycopg",
        "requests",
        "sqlalchemy",
        "web3",
    }

    for context_path in (
        ROOT / "app/token_payments/contexts/store_approval/domain",
        ROOT / "app/token_payments/contexts/store_approval/application",
    ):
        for path in context_path.glob("**/*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])

            assert imports.isdisjoint(forbidden_roots), f"{path} imports adapter dependency: {imports}"


def _command(owner_user_id: UserId = OWNER_USER_ID) -> RequestStoreApprovalCommand:
    return RequestStoreApprovalCommand(
        command_id=COMMAND_ID,
        order_id=ORDER_ID,
        store_id=STORE_ID,
        owner_user_id=owner_user_id,
        requested_at=NOW,
        causation_id="payment-confirmed-message",
        event_message_id=EVENT_MESSAGE_ID,
    )


def _service(store: Store, order_detail: OrderDetail) -> StoreApprovalService:
    return StoreApprovalService(
        store_repository=FakeStoreRepository(store),
        order_detail_repository=FakeOrderDetailRepository(order_detail),
        processed_commands=FakeProcessedCommandRepository(),
        outbox_messages=FakeOutboxMessageRepository(),
    )


def _store(*, active: bool = True, product: Product | None = None) -> Store:
    return Store(
        store_id=STORE_ID,
        owner_user_id=OWNER_USER_ID,
        products=(product or _product(),),
        active=active,
    )


def _order_detail(*, product: Product | None = None) -> OrderDetail:
    return OrderDetail(
        order_id=ORDER_ID,
        store_id=STORE_ID,
        order_status="PAID",
        total_amount=_amount(),
        products=(product or _product(),),
    )


def _product(*, name: str = "Ledger Mug", available: bool = True) -> Product:
    return Product(product_id=PRODUCT_ID, name=name, price=_amount(), available=available)


def _amount() -> Crypto:
    return Crypto(
        amount=Decimal("12.50"),
        symbol="USDC",
        chain_id=11155111,
        token_address=TOKEN_ADDRESS,
        decimals=6,
    )


class FakeStoreRepository:
    def __init__(self, store: Store | None = None) -> None:
        self.stores: dict[StoreId, Store] = {}
        if store is not None:
            self.stores[store.store_id] = store
        self.get_calls: list[StoreId] = []

    def get(self, store_id: StoreId) -> Store | None:
        self.get_calls.append(store_id)
        return self.stores.get(store_id)


class FakeOrderDetailRepository:
    def __init__(self, order_detail: OrderDetail | None = None) -> None:
        self.order_details: dict[OrderId, OrderDetail] = {}
        if order_detail is not None:
            self.order_details[order_detail.order_id] = order_detail
        self.get_calls: list[OrderId] = []
        self.saved: list[OrderDetail] = []

    def get(self, order_id: OrderId) -> OrderDetail | None:
        self.get_calls.append(order_id)
        return self.order_details.get(order_id)

    def save(self, order_detail: OrderDetail) -> None:
        self.saved.append(order_detail)
        self.order_details[order_detail.order_id] = order_detail


class FakeProcessedCommandRepository:
    def __init__(self, existing: set[tuple[str, str]] | None = None) -> None:
        self.existing = existing or set()
        self.records: list[ProcessedCommand] = []

    def was_processed(self, command_id: CommandId, handler: str) -> bool:
        return (handler, str(command_id)) in self.existing

    def record(self, processed_command: ProcessedCommand) -> None:
        self.records.append(processed_command)
        self.existing.add(processed_command.idempotency_key)


class FakeOutboxMessageRepository:
    def __init__(self) -> None:
        self.saved: list[OutboxMessage] = []

    def save(self, message: OutboxMessage) -> None:
        self.saved.append(message)
