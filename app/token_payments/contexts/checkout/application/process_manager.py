"""Pure command-decision logic for the checkout process manager."""

from __future__ import annotations

from dataclasses import dataclass

from token_payments.shared.domain import (
    CheckoutCommandName,
    CheckoutEventName,
    CommandId,
    CommandMetadata,
    EventMetadata,
    OrderId,
)


@dataclass(frozen=True)
class CheckoutProcessEvent:
    metadata: EventMetadata
    order_id: OrderId

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, EventMetadata):
            raise ValueError("CheckoutProcessEvent.metadata must be an EventMetadata")
        _coerce_event_name(self.metadata.name)
        if not isinstance(self.order_id, OrderId):
            raise ValueError("CheckoutProcessEvent.order_id must be an OrderId")

    @property
    def name(self) -> CheckoutEventName:
        return _coerce_event_name(self.metadata.name)


@dataclass(frozen=True)
class CheckoutCommandDecision:
    metadata: CommandMetadata
    order_id: OrderId

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, CommandMetadata):
            raise ValueError("CheckoutCommandDecision.metadata must be a CommandMetadata")
        _coerce_command_name(self.metadata.name)
        if not isinstance(self.order_id, OrderId):
            raise ValueError("CheckoutCommandDecision.order_id must be an OrderId")

    @property
    def command_id(self) -> CommandId:
        return self.metadata.command_id

    @property
    def name(self) -> CheckoutCommandName:
        return _coerce_command_name(self.metadata.name)


class CheckoutProcessManager:
    _COMMANDS_BY_EVENT: dict[CheckoutEventName, tuple[CheckoutCommandName, ...]] = {
        CheckoutEventName.ORDER_CREATED: (CheckoutCommandName.RESERVE_INVENTORY,),
        CheckoutEventName.INVENTORY_RESERVED: (CheckoutCommandName.INITIATE_PAYMENT,),
        CheckoutEventName.PAYMENT_CONFIRMED: (CheckoutCommandName.REQUEST_STORE_APPROVAL,),
        CheckoutEventName.PAYMENT_FAILED: (
            CheckoutCommandName.RELEASE_INVENTORY,
            CheckoutCommandName.CANCEL_ORDER,
        ),
        CheckoutEventName.PAYMENT_EXPIRED: (
            CheckoutCommandName.RELEASE_INVENTORY,
            CheckoutCommandName.CANCEL_ORDER,
        ),
        CheckoutEventName.ORDER_APPROVED: (),
        CheckoutEventName.ORDER_REJECTED: (
            CheckoutCommandName.REFUND_PAYMENT,
            CheckoutCommandName.RELEASE_INVENTORY,
            CheckoutCommandName.CANCEL_ORDER,
        ),
    }

    def handle(self, event: CheckoutProcessEvent) -> tuple[CheckoutCommandDecision, ...]:
        if not isinstance(event, CheckoutProcessEvent):
            raise ValueError("CheckoutProcessManager.handle requires a CheckoutProcessEvent")
        return tuple(self._decision(event, command_name) for command_name in self._COMMANDS_BY_EVENT[event.name])

    def _decision(
        self,
        event: CheckoutProcessEvent,
        command_name: CheckoutCommandName,
    ) -> CheckoutCommandDecision:
        metadata = CommandMetadata(
            command_id=CommandId.for_order_action(event.order_id, command_name),
            name=command_name,
            aggregate_id=str(event.order_id),
            issued_at=event.metadata.occurred_at,
            correlation_id=event.metadata.correlation_id,
            causation_id=str(event.metadata.message_id),
        )
        return CheckoutCommandDecision(metadata=metadata, order_id=event.order_id)


def _coerce_event_name(value: CheckoutEventName | str) -> CheckoutEventName:
    if isinstance(value, CheckoutEventName):
        return value
    try:
        return CheckoutEventName(str(value))
    except ValueError as exc:
        raise ValueError("CheckoutProcessEvent.metadata.name must be a CheckoutEventName") from exc


def _coerce_command_name(value: CheckoutCommandName | str) -> CheckoutCommandName:
    if isinstance(value, CheckoutCommandName):
        return value
    try:
        return CheckoutCommandName(str(value))
    except ValueError as exc:
        raise ValueError("CheckoutCommandDecision.metadata.name must be a CheckoutCommandName") from exc
