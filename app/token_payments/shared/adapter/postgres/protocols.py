"""Minimal PostgreSQL connection protocol used by repository adapters."""

from __future__ import annotations

from typing import Any, Mapping, Protocol


class PostgresConnection(Protocol):
    """Connection/session boundary supplied by an outer transaction owner."""

    def execute(self, sql: str, params: Mapping[str, Any] | None = None) -> Any:
        ...

