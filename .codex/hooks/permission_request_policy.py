#!/usr/bin/env python3
"""Deny approval requests for commands that should never run unsandboxed."""

from __future__ import annotations

import json
import re
import sys
from typing import Any


DENY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brm\s+-[^\n;]*[rR][^\n;]*[fF]\b|\brm\s+-[^\n;]*[fF][^\n;]*[rR]\b"), "rm -rf is not allowed"),
    (re.compile(r"\bgit\s+reset\s+--hard\b"), "git reset --hard is not allowed"),
    (re.compile(r"\bgit\s+push\b[^\n;]*\s--force(?:-with-lease)?\b"), "force push is not allowed"),
    (re.compile(r"\bdrop\s+table\b", re.IGNORECASE), "DROP TABLE is not allowed"),
]


def main() -> int:
    event = _read_event()
    command = _extract_command(event.get("tool_input", {}))

    for pattern, message in DENY_PATTERNS:
        if pattern.search(command):
            _deny(f"{message}: {command}")
            return 0

    return 0


def _read_event() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_command(tool_input: Any) -> str:
    if isinstance(tool_input, dict):
        for key in ("command", "cmd"):
            value = tool_input.get(key)
            if isinstance(value, str):
                return value
    return tool_input if isinstance(tool_input, str) else ""


def _deny(message: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": {
                        "behavior": "deny",
                        "message": message,
                    },
                }
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
