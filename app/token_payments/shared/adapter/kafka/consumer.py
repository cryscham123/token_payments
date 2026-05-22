from __future__ import annotations

import importlib
import logging
from collections.abc import Iterator, Sequence
from typing import Any

logger = logging.getLogger(__name__)


class LazyKafkaConsumerClient:
    """Lazy kafka.KafkaConsumer client wrapper.

    This client does not establish any network connection or perform any imports
    until it is iterated or polled.
    """

    def __init__(
        self,
        bootstrap_servers: Sequence[str],
        client_id: str,
        group_id: str,
        topics: Sequence[str],
        request_timeout_ms: int = 3000,
    ) -> None:
        self.bootstrap_servers = tuple(bootstrap_servers)
        self.client_id = client_id
        self.group_id = group_id
        self.topics = tuple(topics)
        self.request_timeout_ms = request_timeout_ms
        self._consumer: Any | None = None

    def _client(self) -> Any:
        if self._consumer is None:
            kafka = importlib.import_module("kafka")
            self._consumer = kafka.KafkaConsumer(
                *self.topics,
                bootstrap_servers=list(self.bootstrap_servers),
                client_id=self.client_id,
                group_id=self.group_id,
                request_timeout_ms=self.request_timeout_ms,
                enable_auto_commit=False,
                auto_offset_reset="earliest",
            )
        return self._consumer

    def __iter__(self) -> Iterator[Any]:
        return self

    def __next__(self) -> Any:
        return next(self._client())

    def commit(self) -> None:
        client = self._client()
        if hasattr(client, "commit"):
            client.commit()
