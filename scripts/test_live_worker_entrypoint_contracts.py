from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import pytest

from token_payments.runtime import CommandDispatchStatus, dispatch_runtime_command
from token_payments.runtime.composition import LiveRuntimeConfig, LiveRuntimeDependencies


def test_worker_preview_runs_without_live_mode() -> None:
    # Running worker without --live should run preview mode (not build live runtime)
    with patch("token_payments.runtime.entrypoint.ContractRuntimeContainer._build_worker_runtime") as mock_build:
        mock_runtime = MagicMock()
        mock_build.return_value = mock_runtime
        mock_runtime.run_until_idle.return_value = MagicMock(batches=1, processed=0, to_dict=lambda: {"processed": 0})
        
        result = dispatch_runtime_command(["worker"])
        assert result.status is CommandDispatchStatus.SUCCEEDED
        assert "preview" in result.summary or "ran" in result.summary
        mock_build.assert_called_once()


def test_worker_live_dry_run() -> None:
    # worker --live --dry-run should return dry run plan with details of workers
    result = dispatch_runtime_command(["worker", "--live", "--dry-run"])
    assert result.status is CommandDispatchStatus.SUCCEEDED
    assert "dry run" in result.summary.lower()
    details = result.details
    assert "liveWorkerPlan" in details
    plan = details["liveWorkerPlan"]
    assert "workers" in plan
    assert {worker["name"] for worker in plan["workers"]} == {
        "outbox-relay",
        "checkout-process-manager",
        "inventory-command-listener",
        "payment-command-listener",
        "store-approval-command-listener",
        "order-command-listener",
        "order-status-listener",
        "auth-rbac-projector",
        "payment-receipt-polling",
    }
    assert "config" in plan


def test_worker_live_requires_once_or_loop() -> None:
    # worker --live without --once or --loop should fail
    result = dispatch_runtime_command(["worker", "--live"])
    assert result.status is CommandDispatchStatus.FAILED
    assert "either --once or --loop must be specified" in result.summary.lower()


def test_worker_live_loop_requires_confirmation() -> None:
    # worker --live --loop without --confirm-live-worker should fail/refuse with exit_code=0
    result = dispatch_runtime_command(["worker", "--live", "--loop"])
    assert result.status is CommandDispatchStatus.FAILED
    assert result.exit_code == 0
    assert "confirmation required" in result.summary.lower()


def test_worker_live_once_runs_one_batch() -> None:
    # worker --live --once runs build_live_worker_runtime_from_env and run_once()
    with patch("token_payments.runtime.composition.build_live_worker_runtime_from_env") as mock_build:
        mock_runtime = MagicMock()
        mock_build.return_value = mock_runtime
        mock_runtime.run_once.return_value = MagicMock(batches=1, processed=5, to_dict=lambda: {"processed": 5})

        result = dispatch_runtime_command(["worker", "--live", "--once"])
        assert result.status is CommandDispatchStatus.SUCCEEDED
        assert "ran live worker runtime once" in result.summary.lower()
        mock_build.assert_called_once()
        mock_runtime.run_once.assert_called_once()


def test_worker_live_loop_with_confirmation_runs_loop() -> None:
    # worker --live --loop --confirm-live-worker runs build_live_worker_runtime_from_env and run_until_idle
    with patch("token_payments.runtime.composition.build_live_worker_runtime_from_env") as mock_build:
        mock_runtime = MagicMock()
        mock_build.return_value = mock_runtime
        mock_runtime.run_until_idle.return_value = MagicMock(batches=10, processed=20, to_dict=lambda: {"processed": 20})

        result = dispatch_runtime_command(["worker", "--live", "--loop", "--confirm-live-worker"])
        assert result.status is CommandDispatchStatus.SUCCEEDED
        assert "live worker loop execution completed" in result.summary.lower()
        mock_build.assert_called_once()
        mock_runtime.run_until_idle.assert_called_once_with(max_batches=999999)
