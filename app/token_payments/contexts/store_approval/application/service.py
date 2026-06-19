"""Pure store approval application service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

from token_payments.contexts.store_approval.domain import (
    ApprovalStatus,
    OrderApprovedEvent,
    OrderDetail,
    OrderRejectedEvent,
    Store,
    StoreApprovalEvent,
)
from token_payments.shared.domain import (
    CheckoutEventName,
    CommandId,
    Crypto,
    EventMetadata,
    IdempotencyDecision,
    OrderId,
    OutboxMessage,
    ProcessedCommand,
    StoreId,
)

from .commands import RequestStoreApprovalCommand
from .ports import OrderDetailRepository, OutboxMessageRepository, ProcessedCommandRepository, StoreRepository


STORE_APPROVAL_EVENT_TOPIC = "store-approval.events"


class StoreApprovalResultStatus(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DUPLICATE_IGNORED = "DUPLICATE_IGNORED"


class StoreApprovalRejectionReason(StrEnum):
    STORE_NOT_FOUND = "STORE_NOT_FOUND"
    ORDER_DETAIL_NOT_FOUND = "ORDER_DETAIL_NOT_FOUND"


class StoreApprovalRejected(Exception):
    def __init__(
        self,
        reason: StoreApprovalRejectionReason,
        command_id: CommandId,
        order_id: OrderId,
        message: str,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.command_id = command_id
        self.order_id = order_id


@dataclass(frozen=True)
class StoreApprovalResult:
    command_id: CommandId
    order_id: OrderId
    status: StoreApprovalResultStatus
    order_detail: OrderDetail | None = None
    event: StoreApprovalEvent | None = None
    outbox_message: OutboxMessage | None = None
    duplicate_decision: IdempotencyDecision | None = None


class StoreApprovalService:
    HANDLER_NAME = "store-approval-service"

    def __init__(
        self,
        store_repository: StoreRepository,
        order_detail_repository: OrderDetailRepository,
        processed_commands: ProcessedCommandRepository,
        outbox_messages: OutboxMessageRepository,
    ) -> None:
        self._store_repository = store_repository
        self._order_detail_repository = order_detail_repository
        self._processed_commands = processed_commands
        self._outbox_messages = outbox_messages

    def request_store_approval(self, command: RequestStoreApprovalCommand) -> StoreApprovalResult:
        if self._is_duplicate(command.command_id):
            return StoreApprovalResult(
                command_id=command.command_id,
                order_id=command.order_id,
                status=StoreApprovalResultStatus.DUPLICATE_IGNORED,
                duplicate_decision=IdempotencyDecision.IGNORE_DUPLICATE,
            )

        store = self._load_store(command)
        order_detail = self._load_order_detail(command)
        event = store.construct_order_approval(
            order_detail=order_detail,
            owner_user_id=command.owner_user_id,
            decided_at=command.requested_at,
            rejection_reason=command.rejection_reason,
        )
        event_name = (
            CheckoutEventName.ORDER_APPROVED
            if isinstance(event, OrderApprovedEvent)
            else CheckoutEventName.ORDER_REJECTED
        )
        outbox_message = _record_event(
            command=command,
            event_name=event_name,
            aggregate_id=str(event.order.order_id),
            occurred_at=event.created_at,
            payload=_approval_payload(event, command.owner_user_id, command.items),
        )

        self._order_detail_repository.save(event.order)
        self._outbox_messages.save(outbox_message)
        self._processed_commands.record(
            ProcessedCommand.record(
                command_id=command.command_id,
                handler=self.HANDLER_NAME,
                processed_at=command.requested_at,
                order_id=command.order_id,
            )
        )
        return StoreApprovalResult(
            command_id=command.command_id,
            order_id=command.order_id,
            status=(
                StoreApprovalResultStatus.APPROVED
                if isinstance(event, OrderApprovedEvent)
                else StoreApprovalResultStatus.REJECTED
            ),
            order_detail=event.order,
            event=event,
            outbox_message=outbox_message,
        )

    def _is_duplicate(self, command_id: CommandId) -> bool:
        return self._processed_commands.was_processed(command_id, self.HANDLER_NAME)

    def _load_store(self, command: RequestStoreApprovalCommand) -> Store:
        store = self._store_repository.get(command.store_id)
        if store is None:
            raise StoreApprovalRejected(
                reason=StoreApprovalRejectionReason.STORE_NOT_FOUND,
                command_id=command.command_id,
                order_id=command.order_id,
                message=f"store {command.store_id} was not found",
            )
        return store

    def _load_order_detail(self, command: RequestStoreApprovalCommand) -> OrderDetail:
        order_detail = self._order_detail_repository.get(command.order_id)
        if order_detail is None:
            raise StoreApprovalRejected(
                reason=StoreApprovalRejectionReason.ORDER_DETAIL_NOT_FOUND,
                command_id=command.command_id,
                order_id=command.order_id,
                message=f"order detail {command.order_id} was not found",
            )
        return order_detail


def _record_event(
    command: RequestStoreApprovalCommand,
    event_name: CheckoutEventName,
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

    return OutboxMessage.record_event(
        metadata=metadata,
        topic=STORE_APPROVAL_EVENT_TOPIC,
        key=str(command.order_id),
        payload=payload,
        headers=headers,
    )


def _approval_payload(
    event: StoreApprovalEvent,
    owner_user_id: object,
    items: tuple[Mapping[str, Any], ...],
) -> dict[str, Any]:
    order = event.order
    payload: dict[str, Any] = {
        "orderId": str(order.order_id),
        "storeId": str(order.store_id),
        "ownerUserId": str(owner_user_id),
        "orderStatus": order.order_status,
        "approvalStatus": order.approval_status.value,
        "totalAmount": _crypto_payload(order.total_amount),
        "productIds": [str(product.product_id) for product in order.products],
        "occurredAt": event.created_at.isoformat(),
    }
    if items:
        payload["items"] = [dict(item) for item in items]
    if order.approval_status is ApprovalStatus.REJECTED:
        payload["rejectionReasons"] = list(order.rejection_reasons)
    return payload


def _crypto_payload(value: Crypto) -> dict[str, Any]:
    return {
        "amount": format(value.amount, "f"),
        "symbol": value.symbol,
        "chainId": value.chain_id,
        "tokenAddress": str(value.token_address) if value.token_address is not None else None,
        "decimals": value.decimals,
    }
