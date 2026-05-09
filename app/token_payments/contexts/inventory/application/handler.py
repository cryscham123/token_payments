"""Pure inventory command handler."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

from token_payments.contexts.inventory.domain import (
    InventoryConfirmedEvent,
    InventoryReleasedEvent,
    InventoryReservation,
    InventoryReservedEvent,
    ProductInventory,
)
from token_payments.shared.domain import (
    CheckoutEventName,
    CommandId,
    EventMetadata,
    IdempotencyDecision,
    OrderId,
    OutboxMessage,
    ProcessedCommand,
)

from .commands import ConfirmInventoryCommand, ReleaseInventoryCommand, ReserveInventoryCommand
from .ports import InventoryRepository, OutboxMessageRepository, ProcessedCommandRepository


INVENTORY_EVENT_TOPIC = "inventory.events"


class InventoryCommandStatus(StrEnum):
    RESERVED = "RESERVED"
    RELEASED = "RELEASED"
    CONFIRMED = "CONFIRMED"
    DUPLICATE_IGNORED = "DUPLICATE_IGNORED"


class InventoryCommandRejectionReason(StrEnum):
    INVENTORY_NOT_FOUND = "INVENTORY_NOT_FOUND"
    INSUFFICIENT_STOCK = "INSUFFICIENT_STOCK"
    INVALID_STATE = "INVALID_STATE"


class InventoryCommandRejected(Exception):
    def __init__(
        self,
        reason: InventoryCommandRejectionReason,
        command_id: CommandId,
        order_id: OrderId,
        message: str,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.command_id = command_id
        self.order_id = order_id


@dataclass(frozen=True)
class InventoryCommandResult:
    command_id: CommandId
    order_id: OrderId
    status: InventoryCommandStatus
    inventory: ProductInventory | None = None
    outbox_message: OutboxMessage | None = None
    duplicate_decision: IdempotencyDecision | None = None


class InventoryCommandHandler:
    HANDLER_NAME = "inventory-command-handler"

    def __init__(
        self,
        inventory_repository: InventoryRepository,
        processed_commands: ProcessedCommandRepository,
        outbox_messages: OutboxMessageRepository,
    ) -> None:
        self._inventory_repository = inventory_repository
        self._processed_commands = processed_commands
        self._outbox_messages = outbox_messages

    def reserve_inventory(self, command: ReserveInventoryCommand) -> InventoryCommandResult:
        if self._is_duplicate(command.command_id):
            return self._duplicate_result(command.command_id, command.order_id)

        inventory = self._load_inventory(command)
        try:
            updated = inventory.reserve_inventory(command.order_id, command.quantity)
        except ValueError as exc:
            raise self._rejection_from_domain_error(command, exc) from exc

        event = updated.record_reserved(command.order_id, created_at=command.requested_at)
        outbox_message = _record_event(
            command=command,
            event_name=CheckoutEventName.INVENTORY_RESERVED,
            aggregate_id=_aggregate_id(updated),
            occurred_at=event.created_at,
            payload=_reserved_payload(event),
        )
        return self._commit_success(command, updated, outbox_message, InventoryCommandStatus.RESERVED)

    def release_inventory(self, command: ReleaseInventoryCommand) -> InventoryCommandResult:
        if self._is_duplicate(command.command_id):
            return self._duplicate_result(command.command_id, command.order_id)

        inventory = self._load_inventory(command)
        try:
            updated = inventory.release_reservation(command.order_id)
        except ValueError as exc:
            raise self._rejection_from_domain_error(command, exc) from exc

        event = updated.record_released(command.order_id, created_at=command.requested_at)
        outbox_message = _record_event(
            command=command,
            event_name="InventoryReleasedEvent",
            aggregate_id=_aggregate_id(updated),
            occurred_at=event.created_at,
            payload=_reservation_state_payload(event),
        )
        return self._commit_success(command, updated, outbox_message, InventoryCommandStatus.RELEASED)

    def confirm_inventory(self, command: ConfirmInventoryCommand) -> InventoryCommandResult:
        if self._is_duplicate(command.command_id):
            return self._duplicate_result(command.command_id, command.order_id)

        inventory = self._load_inventory(command)
        try:
            updated = inventory.confirm_reservation(command.order_id)
        except ValueError as exc:
            raise self._rejection_from_domain_error(command, exc) from exc

        event = updated.record_confirmed(command.order_id, created_at=command.requested_at)
        outbox_message = _record_event(
            command=command,
            event_name="InventoryConfirmedEvent",
            aggregate_id=_aggregate_id(updated),
            occurred_at=event.created_at,
            payload=_reservation_state_payload(event),
        )
        return self._commit_success(command, updated, outbox_message, InventoryCommandStatus.CONFIRMED)

    def _is_duplicate(self, command_id: CommandId) -> bool:
        return self._processed_commands.was_processed(command_id, self.HANDLER_NAME)

    def _duplicate_result(self, command_id: CommandId, order_id: OrderId) -> InventoryCommandResult:
        return InventoryCommandResult(
            command_id=command_id,
            order_id=order_id,
            status=InventoryCommandStatus.DUPLICATE_IGNORED,
            duplicate_decision=IdempotencyDecision.IGNORE_DUPLICATE,
        )

    def _load_inventory(
        self,
        command: ReserveInventoryCommand | ReleaseInventoryCommand | ConfirmInventoryCommand,
    ) -> ProductInventory:
        inventory = self._inventory_repository.get(command.product_id, command.store_id)
        if inventory is None:
            raise InventoryCommandRejected(
                reason=InventoryCommandRejectionReason.INVENTORY_NOT_FOUND,
                command_id=command.command_id,
                order_id=command.order_id,
                message=f"inventory {command.store_id}:{command.product_id} was not found",
            )
        return inventory

    def _commit_success(
        self,
        command: ReserveInventoryCommand | ReleaseInventoryCommand | ConfirmInventoryCommand,
        inventory: ProductInventory,
        outbox_message: OutboxMessage,
        status: InventoryCommandStatus,
    ) -> InventoryCommandResult:
        self._inventory_repository.save(inventory)
        self._outbox_messages.save(outbox_message)
        self._processed_commands.record(
            ProcessedCommand.record(
                command_id=command.command_id,
                handler=self.HANDLER_NAME,
                processed_at=command.requested_at,
                order_id=command.order_id,
            )
        )
        return InventoryCommandResult(
            command_id=command.command_id,
            order_id=command.order_id,
            status=status,
            inventory=inventory,
            outbox_message=outbox_message,
        )

    def _rejection_from_domain_error(
        self,
        command: ReserveInventoryCommand | ReleaseInventoryCommand | ConfirmInventoryCommand,
        exc: ValueError,
    ) -> InventoryCommandRejected:
        message = str(exc)
        reason = InventoryCommandRejectionReason.INVALID_STATE
        if "insufficient" in message.lower():
            reason = InventoryCommandRejectionReason.INSUFFICIENT_STOCK
        return InventoryCommandRejected(
            reason=reason,
            command_id=command.command_id,
            order_id=command.order_id,
            message=message,
        )


def _record_event(
    command: ReserveInventoryCommand | ReleaseInventoryCommand | ConfirmInventoryCommand,
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

    return OutboxMessage.record_event(
        metadata=metadata,
        topic=INVENTORY_EVENT_TOPIC,
        key=str(command.order_id),
        payload=payload,
        headers=headers,
    )


def _reserved_payload(event: InventoryReservedEvent) -> dict[str, Any]:
    reservation = _reservation_for_order(event.inventory, event.order_id)
    return _base_payload(event.inventory, event.order_id, event.created_at.isoformat()) | {
        "eventName": CheckoutEventName.INVENTORY_RESERVED.value,
        "reservationId": str(reservation.reservation_id),
        "reservedQuantity": reservation.reserved_qty.value,
        "reservationStatus": reservation.status.value,
    }


def _reservation_state_payload(event: InventoryConfirmedEvent | InventoryReleasedEvent) -> dict[str, Any]:
    reservation = _reservation_for_order(event.inventory, event.order_id)
    return _base_payload(event.inventory, event.order_id, event.created_at.isoformat()) | {
        "eventName": type(event).__name__,
        "reservationId": str(reservation.reservation_id),
        "reservedQuantity": reservation.reserved_qty.value,
        "reservationStatus": reservation.status.value,
    }


def _base_payload(inventory: ProductInventory, order_id: OrderId, occurred_at: str) -> dict[str, Any]:
    return {
        "orderId": str(order_id),
        "productId": str(inventory.product_id),
        "storeId": str(inventory.store_id),
        "availableStock": inventory.available_stock.value,
        "reservedStock": inventory.reserved_stock.value,
        "totalStock": inventory.total_stock.value,
        "occurredAt": occurred_at,
    }


def _reservation_for_order(inventory: ProductInventory, order_id: OrderId) -> InventoryReservation:
    for reservation in inventory.reservations:
        if reservation.order_id == order_id:
            return reservation
    raise ValueError(f"inventory reservation for order {order_id} was not recorded")


def _aggregate_id(inventory: ProductInventory) -> str:
    return f"{inventory.store_id}:{inventory.product_id}"
