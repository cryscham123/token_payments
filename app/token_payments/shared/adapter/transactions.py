"""Transaction/session protocols owned by adapter implementations."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol, runtime_checkable


@runtime_checkable
class TransactionBoundary(Protocol):
    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...


@runtime_checkable
class TransactionalSession(Protocol):
    def begin(self) -> AbstractContextManager[TransactionBoundary]:
        ...
