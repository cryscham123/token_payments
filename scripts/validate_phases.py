#!/usr/bin/env python3
"""Validate Harness phase and step metadata."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


VALID_STATUSES = {"pending", "completed", "error", "blocked"}


@dataclass(frozen=True)
class ValidationError:
    path: Path
    message: str

    def format(self, root: Path) -> str:
        try:
            rel = self.path.relative_to(root)
        except ValueError:
            rel = self.path
        return f"{rel}: {self.message}"


def validate(root: Path) -> list[ValidationError]:
    root = root.resolve()
    phases_dir = root / "phases"
    errors: list[ValidationError] = []

    if not phases_dir.is_dir():
        return [ValidationError(phases_dir, "phases directory is missing")]

    top_index_path = phases_dir / "index.json"
    top_index = _read_object(top_index_path, errors)
    if top_index is None:
        return errors

    phases = top_index.get("phases")
    if not isinstance(phases, list):
        errors.append(ValidationError(top_index_path, "`phases` must be a list"))
        return errors

    seen_dirs: set[str] = set()
    for idx, phase in enumerate(phases):
        if not isinstance(phase, dict):
            errors.append(ValidationError(top_index_path, f"`phases[{idx}]` must be an object"))
            continue

        phase_dir_name = phase.get("dir")
        if not isinstance(phase_dir_name, str) or not phase_dir_name.strip():
            errors.append(ValidationError(top_index_path, f"`phases[{idx}].dir` must be a non-empty string"))
            continue

        if phase_dir_name in seen_dirs:
            errors.append(ValidationError(top_index_path, f"duplicate phase dir `{phase_dir_name}`"))
        seen_dirs.add(phase_dir_name)

        status = phase.get("status")
        if status not in VALID_STATUSES:
            errors.append(
                ValidationError(
                    top_index_path,
                    f"`phases[{idx}].status` must be one of {sorted(VALID_STATUSES)}",
                )
            )

        _validate_phase_dir(phases_dir / phase_dir_name, errors)

    return errors


def _validate_phase_dir(phase_dir: Path, errors: list[ValidationError]) -> None:
    if not phase_dir.is_dir():
        errors.append(ValidationError(phase_dir, "phase directory is missing"))
        return

    index_path = phase_dir / "index.json"
    index = _read_object(index_path, errors)
    if index is None:
        return

    for field in ("project", "phase"):
        if not isinstance(index.get(field), str) or not index.get(field, "").strip():
            errors.append(ValidationError(index_path, f"`{field}` must be a non-empty string"))

    steps = index.get("steps")
    if not isinstance(steps, list):
        errors.append(ValidationError(index_path, "`steps` must be a list"))
        return

    seen_numbers: set[int] = set()
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(ValidationError(index_path, f"`steps[{idx}]` must be an object"))
            continue

        step_num = step.get("step")
        if not isinstance(step_num, int) or step_num < 0:
            errors.append(ValidationError(index_path, f"`steps[{idx}].step` must be a non-negative integer"))
            continue

        if step_num in seen_numbers:
            errors.append(ValidationError(index_path, f"duplicate step number `{step_num}`"))
        seen_numbers.add(step_num)

        if not isinstance(step.get("name"), str) or not step.get("name", "").strip():
            errors.append(ValidationError(index_path, f"`steps[{idx}].name` must be a non-empty string"))

        status = step.get("status")
        if status not in VALID_STATUSES:
            errors.append(
                ValidationError(
                    index_path,
                    f"`steps[{idx}].status` must be one of {sorted(VALID_STATUSES)}",
                )
            )
            continue

        if status == "completed" and not _has_text(step.get("summary")):
            errors.append(ValidationError(index_path, f"`steps[{idx}]` completed status requires `summary`"))
        if status == "error" and not _has_text(step.get("error_message")):
            errors.append(ValidationError(index_path, f"`steps[{idx}]` error status requires `error_message`"))
        if status == "blocked" and not _has_text(step.get("blocked_reason")):
            errors.append(ValidationError(index_path, f"`steps[{idx}]` blocked status requires `blocked_reason`"))

        step_file = phase_dir / f"step{step_num}.md"
        if not step_file.exists():
            errors.append(ValidationError(step_file, "step file is missing"))

    expected = list(range(len(seen_numbers)))
    actual = sorted(seen_numbers)
    if actual != expected:
        errors.append(ValidationError(index_path, f"step numbers must be contiguous from 0: got {actual}"))


def _read_object(path: Path, errors: list[ValidationError]) -> dict[str, Any] | None:
    if not path.exists():
        errors.append(ValidationError(path, "JSON file is missing"))
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(ValidationError(path, f"invalid JSON: {exc}"))
        return None
    if not isinstance(payload, dict):
        errors.append(ValidationError(path, "JSON root must be an object"))
        return None
    return payload


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Harness phase metadata")
    parser.add_argument("root", nargs="?", default=".", help="Repository root")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    errors = validate(root)
    if errors:
        for error in errors:
            print(error.format(root), file=sys.stderr)
        return 1

    print("phase metadata is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
