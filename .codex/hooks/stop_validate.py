#!/usr/bin/env python3
"""Run lightweight validation when a Codex turn stops."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    failures: list[str] = []

    python_files = [p for p in (ROOT / "scripts").glob("*.py") if p.exists()]
    if python_files:
        result = subprocess.run(
            ["python3", "-m", "py_compile", *[str(p) for p in python_files]],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            failures.append(_compact("py_compile failed", result.stderr or result.stdout))

    json_files = [
        ROOT / ".agents/plugins/marketplace.json",
        ROOT / ".codex/hooks.json",
        ROOT / "plugins/harness/.codex-plugin/plugin.json",
    ]
    for path in json_files:
        if path.exists():
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                failures.append(f"{path.relative_to(ROOT)} JSON parse failed: {exc}")

    if failures:
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": "\n".join(failures),
                },
                ensure_ascii=False,
            )
        )
    else:
        print(json.dumps({"continue": True}))

    return 0


def _compact(label: str, output: str) -> str:
    lines = [line for line in output.strip().splitlines() if line.strip()]
    detail = "\n".join(lines[-8:])
    return f"{label}:\n{detail}" if detail else label


if __name__ == "__main__":
    raise SystemExit(main())
