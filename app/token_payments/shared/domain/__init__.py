"""Shared domain kernel for cross-context value objects and identifiers."""

from .ids import CustomerId, MessageId, OrderId, PaymentId, ProductId, StoreId, UserId
from .messaging import (
    CheckoutCommandName,
    CheckoutEventName,
    CommandId,
    CommandMetadata,
    EventMetadata,
    IdempotencyDecision,
    OutboxMessage,
    OutboxMessageKind,
    OutboxPublishStatus,
    ProcessedCommand,
    ProcessedMessage,
)
from .value_objects import ChainNetwork, Crypto, TransactionHash, WalletAddress

__all__ = [
    "ChainNetwork",
    "CheckoutCommandName",
    "CheckoutEventName",
    "CommandId",
    "CommandMetadata",
    "Crypto",
    "CustomerId",
    "EventMetadata",
    "IdempotencyDecision",
    "MessageId",
    "OrderId",
    "OutboxMessage",
    "OutboxMessageKind",
    "OutboxPublishStatus",
    "PaymentId",
    "ProcessedCommand",
    "ProcessedMessage",
    "ProductId",
    "StoreId",
    "TransactionHash",
    "UserId",
    "WalletAddress",
]
