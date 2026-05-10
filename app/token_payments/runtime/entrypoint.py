"""Runtime command dispatch without starting long-running processes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable, Sequence

from .config import RuntimeConfig
from .contracts import CommandDispatchResult, HealthState, HealthStatus, RuntimeContainer, WorkerLoopOptions
from .workers import WorkerRuntime


class ContractRuntimeContainer:
    """Minimal composition root used until concrete API/worker wiring exists."""

    def __init__(
        self,
        config: RuntimeConfig | None = None,
        worker_runtime_factory: Callable[[WorkerLoopOptions], WorkerRuntime] | None = None,
    ) -> None:
        self._config = config or RuntimeConfig.from_env()
        self._worker_runtime_factory = worker_runtime_factory

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
        command_parts = _normalize_command(command).split()
        command_name = command_parts[0]
        if command_name == "health":
            return CommandDispatchResult.succeeded(
                command=command_name,
                summary="runtime config loaded",
                details={"health": self.health()},
            )
        if command_name in {"worker", "run-worker"}:
            runtime = self._build_worker_runtime()
            summary = runtime.run_until_idle(max_batches=1)
            return CommandDispatchResult.succeeded(
                command=command_name,
                summary=(
                    f"{command_name} runtime ran {summary.batches} bounded batch(es) "
                    f"and processed {summary.processed} item(s)"
                ),
                details={"config": self.config.to_dict(), "worker": summary.to_dict()},
            )
        if command_name in {"api", "serve-api"}:
            return CommandDispatchResult.succeeded(
                command=command_name,
                summary=f"{command_name} command accepted; long-running startup is not wired in this phase",
                details={"config": self.config.to_dict()},
            )
        if command_name == "ui":
            return self._dispatch_ui_preview(command_parts[1] if len(command_parts) > 1 else None)
        return CommandDispatchResult.failed(
            command=command_name,
            summary=f"unknown runtime command: {command_name}",
            exit_code=64,
        )

    def _build_worker_runtime(self) -> WorkerRuntime:
        options = self.config.worker_loop_options()
        if self._worker_runtime_factory is None:
            return WorkerRuntime([])
        return self._worker_runtime_factory(options)

    def _dispatch_ui_preview(self, view: str | None) -> CommandDispatchResult:
        from token_payments.ui.preview import UnknownUiPreviewView, render_ui_preview

        try:
            preview = render_ui_preview(view)
        except UnknownUiPreviewView as exc:
            return CommandDispatchResult.failed(
                command="ui",
                summary=f"unknown ui preview view: {exc.view}",
                exit_code=64,
                details={"error": exc.to_error()},
            )

        sample_count = len(preview.get("samples", ()))
        return CommandDispatchResult.succeeded(
            command="ui",
            summary=f"rendered {preview['view']} ui preview with {sample_count} sample(s)",
            details={"preview": preview},
        )


def dispatch_runtime_command(
    argv: Sequence[str] | None = None,
    *,
    container: RuntimeContainer | None = None,
) -> CommandDispatchResult:
    args = list(argv or [])
    command = _command_from_args(args)
    runtime_container = container or ContractRuntimeContainer()
    return runtime_container.dispatch_command(command)


def _command_from_args(args: Sequence[str]) -> str:
    if not args:
        return "health"
    command = _normalize_command(args[0])
    if command == "ui" and len(args) > 1:
        selector = args[1].strip() if isinstance(args[1], str) else ""
        if selector:
            return f"{command} {selector}"
    return command


def _normalize_command(command: str) -> str:
    if not isinstance(command, str) or not command.strip():
        return "health"
    return command.strip()
