#!/usr/bin/env python3
"""Block obviously destructive Codex tool calls before they run."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


DANGEROUS_COMMAND_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\brm\s+-[^\n;]*[rR][^\n;]*[fF]\b|\brm\s+-[^\n;]*[fF][^\n;]*[rR]\b"),
        "recursive force removal is blocked",
    ),
    (re.compile(r"\bgit\s+reset\s+--hard\b"), "git reset --hard is blocked"),
    (re.compile(r"\bgit\s+checkout\s+--\b"), "destructive git checkout is blocked"),
    (re.compile(r"\bgit\s+push\b[^\n;]*\s--force(?:-with-lease)?\b"), "force push is blocked"),
    (re.compile(r"\bchmod\s+-R\s+777\b"), "recursive chmod 777 is blocked"),
    (re.compile(r"\bdrop\s+table\b", re.IGNORECASE), "DROP TABLE is blocked"),
]

PROTECTED_EDIT_PATHS = {
    ".git/",
}


def main() -> int:
    event = _read_event()
    tool_name = str(event.get("tool_name", ""))
    tool_input = event.get("tool_input", {})

    if tool_name == "Bash":
        command = _extract_command(tool_input)
        reason = _dangerous_command_reason(command)
        if reason:
            _deny(f"{reason}: {command}")
            return 0

    if tool_name == "apply_patch":
        patch = _extract_command(tool_input)
        reason = _protected_edit_reason(patch)
        if reason:
            _deny(reason)
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
        for key in ("command", "cmd", "patch"):
            value = tool_input.get(key)
            if isinstance(value, str):
                return value
    if isinstance(tool_input, str):
        return tool_input
    return ""


def _dangerous_command_reason(command: str) -> str | None:
    for pattern, reason in DANGEROUS_COMMAND_PATTERNS:
        if pattern.search(command):
            return reason
    return None


def _protected_edit_reason(patch: str) -> str | None:
    touched = _paths_from_patch(patch)
    for path in touched:
        normalized = path.replace("\\", "/")
        for protected in PROTECTED_EDIT_PATHS:
            if normalized == protected.rstrip("/") or normalized.startswith(protected):
                return f"Protected path edit blocked by hook: {normalized}"
    return None


def _paths_from_patch(patch: str) -> set[str]:
    paths: set[str] = set()
    for line in patch.splitlines():
        for prefix in ("*** Add File: ", "*** Update File: ", "*** Delete File: ", "*** Move to: "):
            if line.startswith(prefix):
                paths.add(str(Path(line.removeprefix(prefix)).as_posix()))
    return paths


def _deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
