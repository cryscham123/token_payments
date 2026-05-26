from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_ui_package_browser_preview_runtime_and_scripts_are_absent() -> None:
    assert importlib.util.find_spec("token_payments.ui") is None
    assert importlib.util.find_spec("token_payments.runtime.browser_preview") is None
    assert not (ROOT / "app" / "token_payments" / "ui").exists()
    assert not (ROOT / "app" / "token_payments" / "runtime" / "browser_preview.py").exists()
    assert not (ROOT / "scripts" / "browser_preview_server.py").exists()
    assert not (ROOT / "scripts" / "browser_preview_smoke.py").exists()


def test_ui_runtime_command_is_not_part_of_backend_contract() -> None:
    from token_payments.runtime import dispatch_runtime_command

    payload = dispatch_runtime_command(["ui"]).to_dict()

    assert payload["status"] == "FAILED"
    assert payload["exitCode"] == 64
    assert payload["summary"] == "unknown runtime command: ui"


def test_ui_cli_command_returns_unknown_command_json() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "app")

    completed = subprocess.run(
        [sys.executable, "-m", "token_payments", "ui"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )

    payload = json.loads(completed.stdout)

    assert completed.returncode == 64
    assert completed.stderr == ""
    assert payload["command"] == "ui"
    assert payload["status"] == "FAILED"
    assert payload["summary"] == "unknown runtime command: ui"


def test_public_docs_document_backend_only_scope_without_active_ui_commands() -> None:
    docs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ROOT / "README.md",
            ROOT / "SUMMARY.md",
            ROOT / "app" / "README.md",
            ROOT / "docs" / "SUMMARY.md",
            ROOT / "docs" / "PRD.md",
        )
    )

    assert "backend-only" in docs
    assert "PYTHONPATH=app python3 -m token_payments ui" not in docs
    assert "scripts/browser_preview" not in docs
    assert "docs/UI_GUIDE.md" not in docs
    assert "UI_GUIDE.md" not in docs
