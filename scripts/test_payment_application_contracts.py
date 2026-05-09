from __future__ import annotations

import ast
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import get_type_hints


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.payment.application import (  # noqa: E402
    BlockchainAdapter,
    ConfirmPaymentReceiptCommand,
    ExpireAwaitingSignatureCommand,
    InitiatePaymentCommand,
    OutboxMessageRepository,
    PaymentAuthorizationRepository,
    PaymentCommandHandler,
    PaymentCommandStatus,
    PaymentRepository,
    PaymentTimeoutScheduler,
    ProcessedCommandRepository,
    RefundPaymentCommand,
    SubmitTransactionHashCommand,
    TransactionService,
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
from token_payments.shared.domain import (  # noqa: E402
    ChainNetwork,
    CheckoutCommandName,
    CheckoutEventName,
    CommandId,
    Crypto,
    CustomerId,
    IdempotencyDecision,
    MessageId,
    OrderId,
    OutboxMessage,
    OutboxMessageKind,
    PaymentId,
    ProcessedCommand,
    TransactionHash,
    UserId,
    WalletAddress,
)


NOW = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
SUBMITTED_AT = NOW + timedelta(minutes=3)
CHECKED_AT = NOW + timedelta(minutes=5)
EXPIRES_AT = NOW + timedelta(minutes=15)
PAYMENT_ID = PaymentId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22")
CUSTOMER_ID = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c23")
USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c24")
WALLET_FROM = WalletAddress("0x1111111111111111111111111111111111111111")
WALLET_TO = WalletAddress("0x2222222222222222222222222222222222222222")
TOKEN_ADDRESS = WalletAddress("0x3333333333333333333333333333333333333333")
CHAIN = ChainNetwork(chain_id=11155111, name="Sepolia")
TX_HASH = TransactionHash("0x" + "ab" * 32)
REFUND_TX_HASH = TransactionHash("0x" + "cd" * 32)
INITIATE_COMMAND_ID = CommandId.for_order_action(ORDER_ID, CheckoutCommandName.INITIATE_PAYMENT)
SUBMIT_COMMAND_ID = CommandId(f"{ORDER_ID}:SubmitTransactionHashCommand")
CONFIRM_COMMAND_ID = CommandId(f"{ORDER_ID}:ConfirmPaymentReceiptCommand")
EXPIRE_COMMAND_ID = CommandId(f"{ORDER_ID}:ExpireAwaitingSignatureCommand")
REFUND_COMMAND_ID = CommandId.for_order_action(ORDER_ID, CheckoutCommandName.REFUND_PAYMENT)
INITIATE_EVENT_ID = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25")
CONFIRM_EVENT_ID = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c26")
FAILURE_EVENT_ID = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c27")
EXPIRED_EVENT_ID = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c28")
REFUNDED_EVENT_ID = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c29")


def test_initiate_payment_saves_payment_authorization_timeout_outbox_and_processed_command() -> None:
    payment_repository = FakePaymentRepository()
    authorization_repository = FakePaymentAuthorizationRepository()
    processed_commands = FakeProcessedCommandRepository()
    outbox_messages = FakeOutboxMessageRepository()
    blockchain = FakeBlockchainAdapter()
    timeout_scheduler = FakePaymentTimeoutScheduler()
    transaction_service = FakeTransactionService()
    handler = PaymentCommandHandler(
        payment_repository=payment_repository,
        authorization_repository=authorization_repository,
        processed_commands=processed_commands,
        outbox_messages=outbox_messages,
        blockchain_adapter=blockchain,
        timeout_scheduler=timeout_scheduler,
        transaction_service=transaction_service,
    )

    result = handler.initiate_payment(_initiate_command())

    assert result.status == PaymentCommandStatus.AWAITING_SIGNATURE
    assert result.duplicate_decision is None
    assert result.payment is not None
    assert result.payment.status == PaymentStatus.AWAITING_SIGNATURE
    assert result.payment.gas_estimate == _gas_estimate().apply_buffer()
    assert result.authorization is not None
    assert result.authorization.status == AuthorizationStatus.REQUESTED
    assert result.payment_request == transaction_service.signature_request
    assert result.gas_estimate == _gas_estimate().apply_buffer()

    assert blockchain.estimate_gas_calls == [(_amount(), WALLET_FROM, WALLET_TO, CHAIN)]
    assert transaction_service.signature_request_calls == [(PAYMENT_ID, _amount(), WALLET_TO, EXPIRES_AT)]
    assert timeout_scheduler.scheduled == [(PAYMENT_ID, EXPIRES_AT)]
    assert payment_repository.saved == [result.payment]
    assert authorization_repository.saved == [result.authorization]

    outbox = outbox_messages.saved[0]
    assert outbox.kind == OutboxMessageKind.EVENT
    assert outbox.name == "PaymentProcessingStartedEvent"
    assert outbox.topic == "payment.events"
    assert outbox.key == str(ORDER_ID)
    assert outbox.identity == str(INITIATE_EVENT_ID)
    assert outbox.headers["correlationId"] == str(ORDER_ID)
    assert outbox.headers["causationId"] == str(INITIATE_COMMAND_ID)
    assert outbox.headers["sourceCausationId"] == "inventory-reserved-message"
    assert outbox.payload["paymentId"] == str(PAYMENT_ID)
    assert outbox.payload["orderId"] == str(ORDER_ID)
    assert outbox.payload["customerId"] == str(CUSTOMER_ID)
    assert outbox.payload["status"] == PaymentStatus.AWAITING_SIGNATURE.value
    assert outbox.payload["signatureRequest"]["requestId"] == "payment-request-123"
    assert outbox.payload["gasEstimate"]["maxFee"]["amount"] == "0.011000"
    assert outbox.payload["occurredAt"] == NOW.isoformat()

    assert processed_commands.records == [
        ProcessedCommand.record(
            command_id=INITIATE_COMMAND_ID,
            handler=PaymentCommandHandler.HANDLER_NAME,
            processed_at=NOW,
            order_id=ORDER_ID,
        )
    ]


def test_submit_transaction_hash_authorizes_request_without_outbox_event() -> None:
    payment_repository = FakePaymentRepository(_awaiting_payment())
    authorization_repository = FakePaymentAuthorizationRepository(_requested_authorization())
    outbox_messages = FakeOutboxMessageRepository()
    handler = _handler(payment_repository, authorization_repository, outbox_messages=outbox_messages)

    result = handler.submit_transaction_hash(_submit_command())

    assert result.status == PaymentCommandStatus.TX_SUBMITTED
    assert result.payment is not None
    assert result.payment.status == PaymentStatus.SUBMITTED
    assert result.payment.tx_hash == TX_HASH
    assert result.authorization is not None
    assert result.authorization.status == AuthorizationStatus.AUTHORIZED
    assert result.authorization.tx_hash == TX_HASH
    assert outbox_messages.saved == []
    assert payment_repository.saved == [result.payment]
    assert authorization_repository.saved == [result.authorization]


def test_confirm_payment_receipt_saves_checkout_consumable_confirmed_event() -> None:
    payment_repository = FakePaymentRepository(_submitted_payment())
    outbox_messages = FakeOutboxMessageRepository()
    blockchain = FakeBlockchainAdapter(receipt=_receipt())
    timeout_scheduler = FakePaymentTimeoutScheduler()
    handler = _handler(
        payment_repository,
        FakePaymentAuthorizationRepository(),
        outbox_messages=outbox_messages,
        blockchain=blockchain,
        timeout_scheduler=timeout_scheduler,
    )

    result = handler.confirm_payment_receipt(_confirm_command())

    assert result.status == PaymentCommandStatus.CONFIRMED
    assert result.payment is not None
    assert result.payment.status == PaymentStatus.CONFIRMED
    assert result.payment.receipt == _receipt()
    assert blockchain.receipt_calls == [TX_HASH]
    assert timeout_scheduler.cancelled == [PAYMENT_ID]

    outbox = outbox_messages.saved[0]
    assert outbox.name == CheckoutEventName.PAYMENT_CONFIRMED.value
    assert outbox.key == str(ORDER_ID)
    assert outbox.identity == str(CONFIRM_EVENT_ID)
    assert outbox.headers["correlationId"] == str(ORDER_ID)
    assert outbox.headers["causationId"] == str(CONFIRM_COMMAND_ID)
    assert outbox.payload["paymentId"] == str(PAYMENT_ID)
    assert outbox.payload["orderId"] == str(ORDER_ID)
    assert outbox.payload["txHash"] == str(TX_HASH)
    assert outbox.payload["receipt"]["blockNumber"] == 12345
    assert outbox.payload["occurredAt"] == CHECKED_AT.isoformat()


def test_confirm_receipt_failure_emits_payment_failed_event_without_compensation_commands() -> None:
    payment_repository = FakePaymentRepository(_submitted_payment())
    outbox_messages = FakeOutboxMessageRepository()
    blockchain = FakeBlockchainAdapter(receipt=None)
    handler = _handler(
        payment_repository,
        FakePaymentAuthorizationRepository(),
        outbox_messages=outbox_messages,
        blockchain=blockchain,
    )

    result = handler.confirm_payment_receipt(
        _confirm_command(event_message_id=FAILURE_EVENT_ID, failure_reason="receipt reverted")
    )

    assert result.status == PaymentCommandStatus.FAILED
    assert result.payment is not None
    assert result.payment.status == PaymentStatus.FAILED
    assert result.payment.failure_reason == "receipt reverted"

    outbox = outbox_messages.saved[0]
    assert outbox.kind == OutboxMessageKind.EVENT
    assert outbox.name == CheckoutEventName.PAYMENT_FAILED.value
    assert outbox.key == str(ORDER_ID)
    assert outbox.payload["paymentId"] == str(PAYMENT_ID)
    assert outbox.payload["orderId"] == str(ORDER_ID)
    assert outbox.payload["failureReason"] == "receipt reverted"
    assert outbox.payload["occurredAt"] == CHECKED_AT.isoformat()
    assert outbox.name not in {
        CheckoutCommandName.RELEASE_INVENTORY.value,
        CheckoutCommandName.CANCEL_ORDER.value,
    }


def test_expire_awaiting_signature_saves_expired_payment_authorization_and_event() -> None:
    payment_repository = FakePaymentRepository(_awaiting_payment())
    authorization_repository = FakePaymentAuthorizationRepository(_requested_authorization())
    outbox_messages = FakeOutboxMessageRepository()
    handler = _handler(payment_repository, authorization_repository, outbox_messages=outbox_messages)

    result = handler.expire_awaiting_signature(_expire_command())

    assert result.status == PaymentCommandStatus.EXPIRED
    assert result.payment is not None
    assert result.payment.status == PaymentStatus.EXPIRED
    assert result.payment.failure_reason == "signature timeout"
    assert result.authorization is not None
    assert result.authorization.status == AuthorizationStatus.EXPIRED

    outbox = outbox_messages.saved[0]
    assert outbox.name == CheckoutEventName.PAYMENT_EXPIRED.value
    assert outbox.key == str(ORDER_ID)
    assert outbox.identity == str(EXPIRED_EVENT_ID)
    assert outbox.payload["paymentId"] == str(PAYMENT_ID)
    assert outbox.payload["orderId"] == str(ORDER_ID)
    assert outbox.payload["reason"] == "signature timeout"
    assert outbox.payload["expiredAt"] == EXPIRES_AT.isoformat()


def test_refund_payment_uses_transaction_service_and_records_refunded_event() -> None:
    confirmed = _confirmed_payment()
    payment_repository = FakePaymentRepository(confirmed)
    outbox_messages = FakeOutboxMessageRepository()
    transaction_service = FakeTransactionService()
    handler = _handler(
        payment_repository,
        FakePaymentAuthorizationRepository(),
        outbox_messages=outbox_messages,
        transaction_service=transaction_service,
    )

    result = handler.refund_payment(_refund_command())

    assert result.status == PaymentCommandStatus.REFUNDED
    assert result.payment is not None
    assert result.payment.status == PaymentStatus.REFUNDED
    assert result.payment.refund_receipt == _refund_receipt()
    assert transaction_service.refund_calls == [confirmed]

    outbox = outbox_messages.saved[0]
    assert outbox.name == "PaymentRefundedEvent"
    assert outbox.key == str(ORDER_ID)
    assert outbox.identity == str(REFUNDED_EVENT_ID)
    assert outbox.payload["paymentId"] == str(PAYMENT_ID)
    assert outbox.payload["orderId"] == str(ORDER_ID)
    assert outbox.payload["refundReceipt"]["hash"] == str(REFUND_TX_HASH)
    assert outbox.payload["occurredAt"] == CHECKED_AT.isoformat()


def test_duplicate_command_is_ignored_before_loading_or_calling_external_ports() -> None:
    payment_repository = FakePaymentRepository(_awaiting_payment())
    authorization_repository = FakePaymentAuthorizationRepository(_requested_authorization())
    processed_commands = FakeProcessedCommandRepository(
        existing={(PaymentCommandHandler.HANDLER_NAME, str(INITIATE_COMMAND_ID))}
    )
    outbox_messages = FakeOutboxMessageRepository()
    blockchain = FakeBlockchainAdapter()
    timeout_scheduler = FakePaymentTimeoutScheduler()
    transaction_service = FakeTransactionService()
    handler = PaymentCommandHandler(
        payment_repository=payment_repository,
        authorization_repository=authorization_repository,
        processed_commands=processed_commands,
        outbox_messages=outbox_messages,
        blockchain_adapter=blockchain,
        timeout_scheduler=timeout_scheduler,
        transaction_service=transaction_service,
    )

    result = handler.initiate_payment(_initiate_command())

    assert result.status == PaymentCommandStatus.DUPLICATE_IGNORED
    assert result.payment is None
    assert result.authorization is None
    assert result.outbox_message is None
    assert result.duplicate_decision == IdempotencyDecision.IGNORE_DUPLICATE
    assert payment_repository.get_calls == []
    assert payment_repository.saved == []
    assert authorization_repository.get_calls == []
    assert authorization_repository.saved == []
    assert outbox_messages.saved == []
    assert processed_commands.records == []
    assert blockchain.estimate_gas_calls == []
    assert transaction_service.signature_request_calls == []
    assert timeout_scheduler.scheduled == []


def test_payment_application_public_contracts_are_protocols_and_exports() -> None:
    import token_payments.contexts.payment.application as application

    for port in (
        PaymentRepository,
        PaymentAuthorizationRepository,
        ProcessedCommandRepository,
        OutboxMessageRepository,
        BlockchainAdapter,
        PaymentTimeoutScheduler,
        TransactionService,
    ):
        assert getattr(port, "_is_protocol", False), f"{port.__name__} must be a Protocol"

    payment_hints = get_type_hints(PaymentRepository.get)
    assert payment_hints["return"] == Payment | None

    assert {
        "BlockchainAdapter",
        "ConfirmPaymentReceiptCommand",
        "ExpireAwaitingSignatureCommand",
        "InitiatePaymentCommand",
        "OutboxMessageRepository",
        "PaymentAuthorizationRepository",
        "PaymentCommandHandler",
        "PaymentCommandStatus",
        "PaymentRepository",
        "PaymentTimeoutScheduler",
        "ProcessedCommandRepository",
        "RefundPaymentCommand",
        "SubmitTransactionHashCommand",
        "TransactionService",
    } <= set(application.__all__)


def test_payment_application_does_not_import_external_adapters_or_clients() -> None:
    forbidden_roots = {
        "blockchain",
        "kafka",
        "metamask",
        "psycopg",
        "requests",
        "sqlalchemy",
        "web3",
    }

    for path in (ROOT / "app/token_payments/contexts/payment/application").glob("**/*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])

        assert imports.isdisjoint(forbidden_roots), f"{path} imports adapter dependency: {imports}"


def _handler(
    payment_repository: FakePaymentRepository,
    authorization_repository: FakePaymentAuthorizationRepository,
    *,
    outbox_messages: FakeOutboxMessageRepository | None = None,
    processed_commands: FakeProcessedCommandRepository | None = None,
    blockchain: FakeBlockchainAdapter | None = None,
    timeout_scheduler: FakePaymentTimeoutScheduler | None = None,
    transaction_service: FakeTransactionService | None = None,
) -> PaymentCommandHandler:
    return PaymentCommandHandler(
        payment_repository=payment_repository,
        authorization_repository=authorization_repository,
        processed_commands=processed_commands or FakeProcessedCommandRepository(),
        outbox_messages=outbox_messages or FakeOutboxMessageRepository(),
        blockchain_adapter=blockchain or FakeBlockchainAdapter(),
        timeout_scheduler=timeout_scheduler or FakePaymentTimeoutScheduler(),
        transaction_service=transaction_service or FakeTransactionService(),
    )


def _initiate_command() -> InitiatePaymentCommand:
    return InitiatePaymentCommand(
        command_id=INITIATE_COMMAND_ID,
        payment_id=PAYMENT_ID,
        order_id=ORDER_ID,
        customer_id=CUSTOMER_ID,
        user_id=USER_ID,
        amount=_amount(),
        wallet_from=WALLET_FROM,
        wallet_to=WALLET_TO,
        chain_network=CHAIN,
        expires_at=EXPIRES_AT,
        requested_at=NOW,
        causation_id="inventory-reserved-message",
        event_message_id=INITIATE_EVENT_ID,
    )


def _submit_command() -> SubmitTransactionHashCommand:
    return SubmitTransactionHashCommand(
        command_id=SUBMIT_COMMAND_ID,
        payment_id=PAYMENT_ID,
        order_id=ORDER_ID,
        tx_hash=TX_HASH,
        submitted_at=SUBMITTED_AT,
    )


def _confirm_command(
    *,
    event_message_id: MessageId = CONFIRM_EVENT_ID,
    failure_reason: str = "receipt not confirmed",
) -> ConfirmPaymentReceiptCommand:
    return ConfirmPaymentReceiptCommand(
        command_id=CONFIRM_COMMAND_ID,
        payment_id=PAYMENT_ID,
        order_id=ORDER_ID,
        checked_at=CHECKED_AT,
        failure_reason=failure_reason,
        event_message_id=event_message_id,
    )


def _expire_command() -> ExpireAwaitingSignatureCommand:
    return ExpireAwaitingSignatureCommand(
        command_id=EXPIRE_COMMAND_ID,
        payment_id=PAYMENT_ID,
        order_id=ORDER_ID,
        expired_at=EXPIRES_AT,
        reason="signature timeout",
        event_message_id=EXPIRED_EVENT_ID,
    )


def _refund_command() -> RefundPaymentCommand:
    return RefundPaymentCommand(
        command_id=REFUND_COMMAND_ID,
        payment_id=PAYMENT_ID,
        order_id=ORDER_ID,
        requested_at=CHECKED_AT,
        event_message_id=REFUNDED_EVENT_ID,
    )


def _awaiting_payment() -> Payment:
    return Payment.initialize_payment(
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


def _submitted_payment() -> Payment:
    return _awaiting_payment().submit_tx_hash(TX_HASH)


def _confirmed_payment() -> Payment:
    return _submitted_payment().confirm_payment(_receipt())


def _requested_authorization() -> PaymentAuthorization:
    return PaymentAuthorization.request_transaction_signature(
        payment_id=PAYMENT_ID,
        user_id=USER_ID,
        wallet=WALLET_FROM,
        chain_network=CHAIN,
        signature_request=_signature_request(),
    )


def _amount() -> Crypto:
    return Crypto(
        amount="1.25",
        symbol="USDC",
        chain_id=11155111,
        token_address=TOKEN_ADDRESS,
        decimals=6,
    )


def _gas_estimate() -> GasEstimate:
    return GasEstimate(
        estimated_fee=Crypto(
            amount="0.0100",
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


def _refund_receipt() -> TransactionReceipt:
    return TransactionReceipt(hash=REFUND_TX_HASH, block_number=12355, gas_used=31000)


class FakePaymentRepository:
    def __init__(self, payment: Payment | None = None) -> None:
        self.payments: dict[PaymentId, Payment] = {}
        if payment is not None:
            self.payments[payment.payment_id] = payment
        self.get_calls: list[PaymentId] = []
        self.saved: list[Payment] = []

    def get(self, payment_id: PaymentId) -> Payment | None:
        self.get_calls.append(payment_id)
        return self.payments.get(payment_id)

    def save(self, payment: Payment) -> None:
        self.saved.append(payment)
        self.payments[payment.payment_id] = payment


class FakePaymentAuthorizationRepository:
    def __init__(self, authorization: PaymentAuthorization | None = None) -> None:
        self.authorizations: dict[PaymentId, PaymentAuthorization] = {}
        if authorization is not None:
            self.authorizations[authorization.payment_id] = authorization
        self.get_calls: list[PaymentId] = []
        self.saved: list[PaymentAuthorization] = []

    def get(self, payment_id: PaymentId) -> PaymentAuthorization | None:
        self.get_calls.append(payment_id)
        return self.authorizations.get(payment_id)

    def save(self, authorization: PaymentAuthorization) -> None:
        self.saved.append(authorization)
        self.authorizations[authorization.payment_id] = authorization


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


class FakeBlockchainAdapter:
    def __init__(self, receipt: TransactionReceipt | None = _receipt()) -> None:
        self.receipt = receipt
        self.estimate_gas_calls: list[tuple[Crypto, WalletAddress, WalletAddress, ChainNetwork]] = []
        self.receipt_calls: list[TransactionHash] = []

    def estimate_gas(
        self,
        amount: Crypto,
        wallet_from: WalletAddress,
        wallet_to: WalletAddress,
        chain_network: ChainNetwork,
    ) -> GasEstimate:
        self.estimate_gas_calls.append((amount, wallet_from, wallet_to, chain_network))
        return _gas_estimate()

    def get_transaction_receipt(self, tx_hash: TransactionHash) -> TransactionReceipt | None:
        self.receipt_calls.append(tx_hash)
        return self.receipt


class FakePaymentTimeoutScheduler:
    def __init__(self) -> None:
        self.scheduled: list[tuple[PaymentId, datetime]] = []
        self.cancelled: list[PaymentId] = []

    def schedule_expiration(self, payment_id: PaymentId, expires_at: datetime) -> None:
        self.scheduled.append((payment_id, expires_at))

    def cancel_expiration(self, payment_id: PaymentId) -> None:
        self.cancelled.append(payment_id)


class FakeTransactionService:
    def __init__(self) -> None:
        self.signature_request = _signature_request()
        self.signature_request_calls: list[tuple[PaymentId, Crypto, WalletAddress, datetime]] = []
        self.refund_calls: list[Payment] = []

    def create_signature_request(
        self,
        payment_id: PaymentId,
        amount: Crypto,
        wallet_to: WalletAddress,
        expires_at: datetime,
    ) -> TransactionSignatureRequest:
        self.signature_request_calls.append((payment_id, amount, wallet_to, expires_at))
        return self.signature_request

    def refund_payment(self, payment: Payment) -> TransactionReceipt:
        self.refund_calls.append(payment)
        return _refund_receipt()
