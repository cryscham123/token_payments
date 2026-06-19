"""Pure payment command handler."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Mapping

from token_payments.contexts.payment.domain import (
    GasEstimate,
    Payment,
    PaymentAuthorization,
    PaymentConfirmedEvent,
    PaymentExpiredEvent,
    PaymentFailedEvent,
    PaymentProcessingStartedEvent,
    PaymentRefundedEvent,
    PaymentStatus,
    TransactionReceipt,
    TransactionSignatureRequest,
)
from token_payments.shared.domain import (
    CheckoutEventName,
    CommandId,
    Crypto,
    EventMetadata,
    IdempotencyDecision,
    OrderId,
    OutboxMessage,
    PaymentId,
    ProcessedCommand,
)

from .commands import (
    ConfirmPaymentReceiptCommand,
    ExpireAwaitingSignatureCommand,
    InitiatePaymentCommand,
    PaymentCommand,
    RefundPaymentCommand,
    SubmitTransactionHashCommand,
)
from .ports import (
    BlockchainAdapter,
    OutboxMessageRepository,
    PaymentAuthorizationRepository,
    PaymentRepository,
    PaymentTimeoutScheduler,
    ProcessedCommandRepository,
    TransactionService,
)


PAYMENT_EVENT_TOPIC = "payment.events"
PAYMENT_PROCESSING_STARTED_EVENT = "PaymentProcessingStartedEvent"
PAYMENT_REFUNDED_EVENT = "PaymentRefundedEvent"


class PaymentCommandStatus(StrEnum):
    AWAITING_SIGNATURE = "AWAITING_SIGNATURE"
    TX_SUBMITTED = "TX_SUBMITTED"
    CONFIRMING = "CONFIRMING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    REFUNDED = "REFUNDED"
    DUPLICATE_IGNORED = "DUPLICATE_IGNORED"


class PaymentCommandRejectionReason(StrEnum):
    PAYMENT_NOT_FOUND = "PAYMENT_NOT_FOUND"
    AUTHORIZATION_NOT_FOUND = "AUTHORIZATION_NOT_FOUND"
    INVALID_STATE = "INVALID_STATE"


class PaymentCommandRejected(Exception):
    def __init__(
        self,
        reason: PaymentCommandRejectionReason,
        command_id: CommandId,
        order_id: OrderId,
        payment_id: PaymentId,
        message: str,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.command_id = command_id
        self.order_id = order_id
        self.payment_id = payment_id


@dataclass(frozen=True)
class PaymentCommandResult:
    command_id: CommandId
    order_id: OrderId
    status: PaymentCommandStatus
    payment: Payment | None = None
    authorization: PaymentAuthorization | None = None
    outbox_message: OutboxMessage | None = None
    duplicate_decision: IdempotencyDecision | None = None
    payment_request: TransactionSignatureRequest | None = None
    gas_estimate: GasEstimate | None = None


class PaymentCommandHandler:
    HANDLER_NAME = "payment-command-handler"

    def __init__(
        self,
        payment_repository: PaymentRepository,
        authorization_repository: PaymentAuthorizationRepository,
        processed_commands: ProcessedCommandRepository,
        outbox_messages: OutboxMessageRepository,
        blockchain_adapter: BlockchainAdapter,
        timeout_scheduler: PaymentTimeoutScheduler,
        transaction_service: TransactionService,
    ) -> None:
        self._payment_repository = payment_repository
        self._authorization_repository = authorization_repository
        self._processed_commands = processed_commands
        self._outbox_messages = outbox_messages
        self._blockchain_adapter = blockchain_adapter
        self._timeout_scheduler = timeout_scheduler
        self._transaction_service = transaction_service

    def initiate_payment(self, command: InitiatePaymentCommand) -> PaymentCommandResult:
        if self._is_duplicate(command.command_id):
            return self._duplicate_result(command.command_id, command.order_id)

        gas_estimate = self._blockchain_adapter.estimate_gas(
            command.amount,
            command.wallet_from,
            command.wallet_to,
            command.chain_network,
        ).apply_buffer()
        payment = Payment.initialize_payment(
            payment_id=command.payment_id,
            order_id=command.order_id,
            customer_id=command.customer_id,
            amount=command.amount,
            wallet_from=command.wallet_from,
            wallet_to=command.wallet_to,
            chain_network=command.chain_network,
            gas_estimate=gas_estimate,
            expires_at=command.expires_at,
            status=PaymentStatus.AWAITING_SIGNATURE,
            payer_wallet_id=command.payer_wallet_id,
            payment_asset_id=command.payment_asset_id,
            items=command.items,
        )
        payment_request = self._transaction_service.create_signature_request(
            command.payment_id,
            command.amount,
            command.wallet_to,
            command.expires_at,
        )
        payment_request = _signature_request_with_terms(payment_request, command)
        authorization = PaymentAuthorization.request_transaction_signature(
            payment_id=command.payment_id,
            user_id=command.user_id,
            wallet=command.wallet_from,
            chain_network=command.chain_network,
            signature_request=payment_request,
            payer_wallet_id=command.payer_wallet_id,
            payment_asset_id=command.payment_asset_id,
            expected_amount_minor_units=(
                _crypto_minor_units(command.amount) if command.payment_asset_id is not None else None
            ),
        )
        event = payment.record_processing_started(created_at=command.requested_at)
        outbox_message = _record_event(
            command=command,
            event_name=PAYMENT_PROCESSING_STARTED_EVENT,
            aggregate_id=str(payment.payment_id),
            occurred_at=event.created_at,
            payload=_processing_started_payload(event, authorization),
        )

        self._payment_repository.save(payment)
        self._authorization_repository.save(authorization)
        self._outbox_messages.save(outbox_message)
        self._timeout_scheduler.schedule_expiration(payment.payment_id, payment.expires_at)
        self._record_processed(command, command.requested_at)
        return PaymentCommandResult(
            command_id=command.command_id,
            order_id=command.order_id,
            status=PaymentCommandStatus.AWAITING_SIGNATURE,
            payment=payment,
            authorization=authorization,
            outbox_message=outbox_message,
            payment_request=payment_request,
            gas_estimate=gas_estimate,
        )

    def submit_transaction_hash(self, command: SubmitTransactionHashCommand) -> PaymentCommandResult:
        if self._is_duplicate(command.command_id):
            return self._duplicate_result(command.command_id, command.order_id)

        payment = self._load_payment(command)
        authorization = self._load_authorization(command)
        try:
            updated_payment = payment.submit_tx_hash(command.tx_hash)
            updated_authorization = authorization.authorize_tx_hash(command.tx_hash, authorized_at=command.submitted_at)
        except ValueError as exc:
            raise self._invalid_state(command, exc) from exc

        self._payment_repository.save(updated_payment)
        self._authorization_repository.save(updated_authorization)
        self._record_processed(command, command.submitted_at)
        return PaymentCommandResult(
            command_id=command.command_id,
            order_id=command.order_id,
            status=PaymentCommandStatus.TX_SUBMITTED,
            payment=updated_payment,
            authorization=updated_authorization,
        )

    def confirm_payment_receipt(self, command: ConfirmPaymentReceiptCommand) -> PaymentCommandResult:
        if self._is_duplicate(command.command_id):
            return self._duplicate_result(command.command_id, command.order_id)

        payment = self._load_payment(command)
        if payment.tx_hash is None:
            raise self._invalid_state(command, ValueError("submitted payment requires tx_hash before receipt check"))

        receipt_payload = self._blockchain_adapter.get_transaction_receipt(payment.tx_hash)
        try:
            if receipt_payload is None:
                updated_payment = payment.mark_confirming()
                self._payment_repository.save(updated_payment)
                self._record_processed(command, command.checked_at)
                return PaymentCommandResult(
                    command_id=command.command_id,
                    order_id=command.order_id,
                    status=PaymentCommandStatus.CONFIRMING,
                    payment=updated_payment,
                )
            else:
                authorization = self._authorization_repository.get(command.payment_id)
                receipt, mismatch_reason = _verified_receipt_or_mismatch(payment, authorization, receipt_payload)
                if mismatch_reason is not None:
                    updated_payment = payment.fail_payment(f"ERC20_TRANSFER_MISMATCH: {mismatch_reason}")
                    event = updated_payment.record_failed(created_at=command.checked_at)
                    outbox_message = _record_event(
                        command=command,
                        event_name=CheckoutEventName.PAYMENT_FAILED,
                        aggregate_id=str(updated_payment.payment_id),
                        occurred_at=event.created_at,
                        payload=_failed_payload(event, updated_payment),
                    )
                    status = PaymentCommandStatus.FAILED
                else:
                    updated_payment = payment.confirm_payment(receipt)
                    event = updated_payment.record_confirmed(created_at=command.checked_at)
                    outbox_message = _record_event(
                        command=command,
                        event_name=CheckoutEventName.PAYMENT_CONFIRMED,
                        aggregate_id=str(updated_payment.payment_id),
                        occurred_at=event.created_at,
                        payload=_confirmed_payload(event, updated_payment),
                    )
                    self._timeout_scheduler.cancel_expiration(updated_payment.payment_id)
                    status = PaymentCommandStatus.CONFIRMED
        except ValueError as exc:
            raise self._invalid_state(command, exc) from exc

        return self._commit_payment_event(
            command=command,
            payment=updated_payment,
            outbox_message=outbox_message,
            status=status,
            processed_at=command.checked_at,
        )

    def expire_awaiting_signature(self, command: ExpireAwaitingSignatureCommand) -> PaymentCommandResult:
        if self._is_duplicate(command.command_id):
            return self._duplicate_result(command.command_id, command.order_id)

        payment = self._load_payment(command)
        authorization = self._load_authorization(command)
        try:
            updated_payment = payment.expire_awaiting_signature(now=command.expired_at, reason=command.reason)
            updated_authorization = authorization.expire(now=command.expired_at)
            event = updated_payment.record_expired(expired_at=command.expired_at)
        except ValueError as exc:
            raise self._invalid_state(command, exc) from exc

        outbox_message = _record_event(
            command=command,
            event_name=CheckoutEventName.PAYMENT_EXPIRED,
            aggregate_id=str(updated_payment.payment_id),
            occurred_at=event.expired_at,
            payload=_expired_payload(event, updated_payment),
        )
        self._payment_repository.save(updated_payment)
        self._authorization_repository.save(updated_authorization)
        self._outbox_messages.save(outbox_message)
        self._record_processed(command, command.expired_at)
        return PaymentCommandResult(
            command_id=command.command_id,
            order_id=command.order_id,
            status=PaymentCommandStatus.EXPIRED,
            payment=updated_payment,
            authorization=updated_authorization,
            outbox_message=outbox_message,
        )

    def refund_payment(self, command: RefundPaymentCommand) -> PaymentCommandResult:
        if self._is_duplicate(command.command_id):
            return self._duplicate_result(command.command_id, command.order_id)

        payment = self._load_payment(command)
        refund_receipt = self._transaction_service.refund_payment(payment)
        try:
            updated_payment = payment.refund_payment(refund_receipt)
            event = updated_payment.record_refunded(created_at=command.requested_at)
        except ValueError as exc:
            raise self._invalid_state(command, exc) from exc

        outbox_message = _record_event(
            command=command,
            event_name=PAYMENT_REFUNDED_EVENT,
            aggregate_id=str(updated_payment.payment_id),
            occurred_at=event.created_at,
            payload=_refunded_payload(event),
        )
        return self._commit_payment_event(
            command=command,
            payment=updated_payment,
            outbox_message=outbox_message,
            status=PaymentCommandStatus.REFUNDED,
            processed_at=command.requested_at,
        )

    def _is_duplicate(self, command_id: CommandId) -> bool:
        return self._processed_commands.was_processed(command_id, self.HANDLER_NAME)

    def _duplicate_result(self, command_id: CommandId, order_id: OrderId) -> PaymentCommandResult:
        return PaymentCommandResult(
            command_id=command_id,
            order_id=order_id,
            status=PaymentCommandStatus.DUPLICATE_IGNORED,
            duplicate_decision=IdempotencyDecision.IGNORE_DUPLICATE,
        )

    def _load_payment(
        self,
        command: SubmitTransactionHashCommand
        | ConfirmPaymentReceiptCommand
        | ExpireAwaitingSignatureCommand
        | RefundPaymentCommand,
    ) -> Payment:
        payment = self._payment_repository.get(command.payment_id)
        if payment is None:
            raise PaymentCommandRejected(
                reason=PaymentCommandRejectionReason.PAYMENT_NOT_FOUND,
                command_id=command.command_id,
                order_id=command.order_id,
                payment_id=command.payment_id,
                message=f"payment {command.payment_id} was not found",
            )
        if payment.order_id != command.order_id:
            raise PaymentCommandRejected(
                reason=PaymentCommandRejectionReason.INVALID_STATE,
                command_id=command.command_id,
                order_id=command.order_id,
                payment_id=command.payment_id,
                message=f"payment {command.payment_id} does not belong to order {command.order_id}",
            )
        return payment

    def _load_authorization(
        self,
        command: SubmitTransactionHashCommand | ExpireAwaitingSignatureCommand,
    ) -> PaymentAuthorization:
        authorization = self._authorization_repository.get(command.payment_id)
        if authorization is None:
            raise PaymentCommandRejected(
                reason=PaymentCommandRejectionReason.AUTHORIZATION_NOT_FOUND,
                command_id=command.command_id,
                order_id=command.order_id,
                payment_id=command.payment_id,
                message=f"payment authorization {command.payment_id} was not found",
            )
        return authorization

    def _commit_payment_event(
        self,
        command: ConfirmPaymentReceiptCommand | RefundPaymentCommand,
        payment: Payment,
        outbox_message: OutboxMessage,
        status: PaymentCommandStatus,
        processed_at: datetime,
    ) -> PaymentCommandResult:
        self._payment_repository.save(payment)
        self._outbox_messages.save(outbox_message)
        self._record_processed(command, processed_at)
        return PaymentCommandResult(
            command_id=command.command_id,
            order_id=command.order_id,
            status=status,
            payment=payment,
            outbox_message=outbox_message,
        )

    def _record_processed(self, command: PaymentCommand, processed_at: datetime) -> None:
        self._processed_commands.record(
            ProcessedCommand.record(
                command_id=command.command_id,
                handler=self.HANDLER_NAME,
                processed_at=processed_at,
                order_id=command.order_id,
            )
        )

    def _invalid_state(self, command: PaymentCommand, exc: ValueError) -> PaymentCommandRejected:
        return PaymentCommandRejected(
            reason=PaymentCommandRejectionReason.INVALID_STATE,
            command_id=command.command_id,
            order_id=command.order_id,
            payment_id=command.payment_id,
            message=str(exc),
        )


def _record_event(
    command: InitiatePaymentCommand | ConfirmPaymentReceiptCommand | ExpireAwaitingSignatureCommand | RefundPaymentCommand,
    event_name: CheckoutEventName | str,
    aggregate_id: str,
    occurred_at: datetime,
    payload: Mapping[str, Any],
) -> OutboxMessage:
    metadata = EventMetadata(
        message_id=command.event_message_id,
        name=event_name,
        aggregate_id=aggregate_id,
        occurred_at=occurred_at,
        correlation_id=str(command.order_id),
        causation_id=str(command.command_id),
    )
    headers = {
        "correlationId": str(command.order_id),
        "causationId": str(command.command_id),
    }
    if command.causation_id is not None:
        headers["sourceCausationId"] = command.causation_id

    payload_dict = dict(payload)
    name_str = event_name.value if hasattr(event_name, "value") else str(event_name)
    payload_dict.setdefault("eventName", name_str)

    return OutboxMessage.record_event(
        metadata=metadata,
        topic=PAYMENT_EVENT_TOPIC,
        key=str(command.order_id),
        payload=payload_dict,
        headers=headers,
    )


def _processing_started_payload(
    event: PaymentProcessingStartedEvent,
    authorization: PaymentAuthorization,
) -> dict[str, Any]:
    payment = event.payment
    payload: dict[str, Any] = {
        "paymentId": str(payment.payment_id),
        "orderId": str(payment.order_id),
        "customerId": str(payment.customer_id),
        "userId": str(authorization.user_id),
        "status": payment.status.value,
        "amount": _crypto_payload(payment.amount),
        "paymentAssetId": payment.payment_asset_id,
        "payerWalletId": str(payment.payer_wallet_id) if payment.payer_wallet_id is not None else None,
        "walletFrom": str(payment.wallet_from),
        "walletTo": str(payment.wallet_to),
        "chain": _chain_payload(payment),
        "gasEstimate": _gas_estimate_payload(payment.gas_estimate),
        "signatureRequest": _signature_request_payload(authorization.signature_request),
        "expiresAt": payment.expires_at.isoformat(),
        "occurredAt": event.created_at.isoformat(),
    }
    _add_items_payload(payload, payment)
    return payload


def _confirmed_payload(event: PaymentConfirmedEvent, payment: Payment) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "paymentId": str(event.payment_id),
        "orderId": str(event.order_id),
        "txHash": str(event.tx_hash),
        "receipt": _receipt_payload(event.receipt),
        "occurredAt": event.created_at.isoformat(),
    }
    _add_items_payload(payload, payment)
    return payload


def _failed_payload(event: PaymentFailedEvent, payment: Payment) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "paymentId": str(event.payment_id),
        "orderId": str(event.order_id),
        "failureReason": event.failure_reason,
        "occurredAt": event.created_at.isoformat(),
    }
    _add_items_payload(payload, payment)
    return payload


def _expired_payload(event: PaymentExpiredEvent, payment: Payment) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "paymentId": str(event.payment_id),
        "orderId": str(event.order_id),
        "reason": event.reason,
        "expiredAt": event.expired_at.isoformat(),
    }
    _add_items_payload(payload, payment)
    return payload


def _refunded_payload(event: PaymentRefundedEvent) -> dict[str, Any]:
    return {
        "paymentId": str(event.payment_id),
        "orderId": str(event.order_id),
        "refundReceipt": _receipt_payload(event.refund_receipt),
        "occurredAt": event.created_at.isoformat(),
    }


def _chain_payload(payment: Payment) -> dict[str, Any]:
    return {
        "chainId": payment.chain_network.chain_id,
        "name": payment.chain_network.name,
    }


def _gas_estimate_payload(gas_estimate: GasEstimate | None) -> dict[str, Any] | None:
    if gas_estimate is None:
        return None
    return {
        "estimatedFee": _crypto_payload(gas_estimate.estimated_fee),
        "gasLimit": gas_estimate.gas_limit,
        "bufferRate": str(gas_estimate.buffer_rate),
        "maxFee": _crypto_payload(gas_estimate.max_fee) if gas_estimate.max_fee is not None else None,
    }


def _signature_request_payload(signature_request: TransactionSignatureRequest) -> dict[str, Any]:
    payload = {
        "requestId": signature_request.request_id,
        "amount": _crypto_payload(signature_request.amount),
        "to": str(signature_request.to),
        "expiresAt": signature_request.expires_at.isoformat(),
    }
    if signature_request.payment_asset_id is not None:
        payload["paymentAssetId"] = signature_request.payment_asset_id
    if signature_request.transfer_type is not None:
        payload["transferType"] = signature_request.transfer_type
    if signature_request.token_address is not None:
        payload["tokenAddress"] = str(signature_request.token_address)
    if signature_request.amount_minor_units is not None:
        payload["amountMinorUnits"] = str(signature_request.amount_minor_units)
    if signature_request.chain_id is not None:
        payload["chainId"] = signature_request.chain_id
    return payload


def _receipt_payload(receipt: TransactionReceipt) -> dict[str, Any]:
    return {
        "hash": str(receipt.hash),
        "blockNumber": receipt.block_number,
        "gasUsed": receipt.gas_used,
    }


def _crypto_payload(value: Crypto) -> dict[str, Any]:
    return {
        "amount": format(value.amount, "f"),
        "symbol": value.symbol,
        "chainId": value.chain_id,
        "tokenAddress": str(value.token_address) if value.token_address is not None else None,
        "decimals": value.decimals,
    }


def _add_items_payload(payload: dict[str, Any], payment: Payment) -> None:
    if payment.items:
        payload["items"] = [dict(item) for item in payment.items]


def _signature_request_with_terms(
    request: TransactionSignatureRequest,
    command: InitiatePaymentCommand,
) -> TransactionSignatureRequest:
    if command.payment_asset_id is None:
        return request
    return TransactionSignatureRequest.for_payment_terms(
        request_id=request.request_id,
        amount=request.amount,
        to=request.to,
        expires_at=request.expires_at,
        payment_asset_id=command.payment_asset_id,
    )


def _crypto_minor_units(value: Crypto) -> int:
    scale = Decimal("10") ** value.decimals
    scaled = value.amount * scale
    integral = scaled.to_integral_value()
    if scaled != integral:
        raise ValueError("payment amount precision exceeds asset decimals")
    return int(integral)


def _verified_receipt_or_mismatch(
    payment: Payment,
    authorization: PaymentAuthorization | None,
    receipt_payload: TransactionReceipt | Mapping[str, Any] | object,
) -> tuple[TransactionReceipt, str | None]:
    receipt = _receipt_from_payload(receipt_payload, payment.tx_hash)
    status = _receipt_status(receipt_payload)
    if status is False:
        return receipt, "REVERTED"
    if payment.amount.token_address is None:
        return receipt, None
    if payment.payment_asset_id is None and (authorization is None or authorization.payment_asset_id is None):
        return receipt, None
    if authorization is None:
        return receipt, "AUTHORIZATION_NOT_FOUND"
    verification = _verify_erc20_transfer(
        receipt_payload,
        token_address=payment.amount.token_address,
        wallet_from=payment.wallet_from,
        wallet_to=payment.wallet_to,
        amount_minor_units=authorization.expected_amount_minor_units or _crypto_minor_units(payment.amount),
    )
    if verification is None:
        return receipt, None
    return receipt, verification


def _receipt_from_payload(
    payload: TransactionReceipt | Mapping[str, Any] | object,
    default_hash: object,
) -> TransactionReceipt:
    if isinstance(payload, TransactionReceipt):
        return payload
    return TransactionReceipt(
        hash=str(_payload_field(payload, "hash", "tx_hash", "txHash", "transactionHash", default=default_hash)),
        block_number=_int_field(_payload_field(payload, "block_number", "blockNumber", default=0), "block_number"),
        gas_used=_int_field(_payload_field(payload, "gas_used", "gasUsed", default=1), "gas_used"),
    )


def _receipt_status(payload: TransactionReceipt | Mapping[str, Any] | object) -> bool | None:
    value = _payload_field(payload, "status", default=None)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return int(value, 16) != 0 if value.startswith("0x") else value not in {"0", "false", "False"}
    return bool(value)


def _verify_erc20_transfer(
    payload: TransactionReceipt | Mapping[str, Any] | object,
    *,
    token_address: WalletAddress,
    wallet_from: WalletAddress,
    wallet_to: WalletAddress,
    amount_minor_units: int,
) -> str | None:
    logs = _payload_field(payload, "logs", default=())
    if not isinstance(logs, list | tuple):
        return "TRANSFER_LOG_MISSING"
    for log in logs:
        if not isinstance(log, Mapping):
            continue
        token = str(log.get("address") or "").lower()
        if token != str(token_address):
            continue
        topics = log.get("topics")
        if not isinstance(topics, list | tuple) or len(topics) < 3:
            continue
        if str(topics[0]).lower() != "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef":
            continue
        observed_from = _topic_address(str(topics[1]))
        observed_to = _topic_address(str(topics[2]))
        observed_amount = _hex_int(log.get("data"))
        if observed_from != str(wallet_from):
            return "WRONG_PAYER"
        if observed_to != str(wallet_to):
            return "WRONG_RECIPIENT"
        if observed_amount < amount_minor_units:
            return "INSUFFICIENT_AMOUNT"
        return None
    if any(isinstance(log, Mapping) and str(log.get("address") or "").lower() != str(token_address) for log in logs):
        return "WRONG_TOKEN"
    return "TRANSFER_LOG_MISSING"


def _topic_address(topic: str) -> str:
    value = topic.removeprefix("0x").removeprefix("0X")
    return "0x" + value[-40:].lower()


def _hex_int(value: object) -> int:
    if isinstance(value, str):
        return int(value, 16) if value.startswith("0x") else int(value)
    return int(value)


def _payload_field(payload: Mapping[str, Any] | object, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(payload, Mapping) and name in payload:
            return payload[name]
        if not isinstance(payload, Mapping) and hasattr(payload, name):
            return getattr(payload, name)
    return default


def _int_field(value: object, field_name: str) -> int:
    if isinstance(value, str):
        return int(value, 16) if value.startswith("0x") else int(value)
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    return int(value)
