"""Runtime command dispatch without starting long-running processes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Sequence

from .config import RuntimeConfig
from .contracts import CommandDispatchResult, HealthState, HealthStatus, RuntimeContainer


class ContractRuntimeContainer:
    """Minimal composition root used until concrete API/worker wiring exists."""

    def __init__(self, config: RuntimeConfig | None = None) -> None:
        self._config = config or RuntimeConfig.from_env()

    @property
    def config(self) -> RuntimeConfig:
        return self._config

    def health(self) -> HealthStatus:
        return HealthStatus(
            component="runtime",
            state=HealthState.OK,
            checked_at=datetime.now(UTC),
            details=self.config.to_dict(),
        )

    def dispatch_command(self, command: str) -> CommandDispatchResult:
        command_name = _normalize_command(command)
        if command_name == "health":
            return CommandDispatchResult.succeeded(
                command=command_name,
                summary="runtime config loaded",
                details={"health": self.health()},
            )
        if command_name in {"api", "serve-api", "worker", "run-worker"}:
            return CommandDispatchResult.succeeded(
                command=command_name,
                summary=f"{command_name} command accepted; long-running startup is not wired in this phase",
                details={"config": self.config.to_dict()},
            )
        return CommandDispatchResult.failed(
            command=command_name,
            summary=f"unknown runtime command: {command_name}",
            exit_code=64,
        )


def dispatch_runtime_command(
    argv: Sequence[str] | None = None,
    *,
    container: RuntimeContainer | None = None,
) -> CommandDispatchResult:
    args = list(argv or [])
    command = args[0] if args else "health"
    runtime_container = container or ContractRuntimeContainer()
    return runtime_container.dispatch_command(command)


def _normalize_command(command: str) -> str:
    if not isinstance(command, str) or not command.strip():
        return "health"
    return command.strip()
