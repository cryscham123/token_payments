#!/usr/bin/env python3
"""Run project checks before creating a git commit."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    checks: list[tuple[str, list[str], bool]] = []

    package_json = ROOT / "package.json"
    if package_json.exists():
        scripts = _package_scripts(package_json)
        missing = [name for name in ("lint", "build", "test") if name not in scripts]
        if missing:
            _error(f"package.json is missing required scripts: {', '.join(missing)}")
            return 1
        checks.extend(
            [
                ("lint", ["npm", "run", "lint"], True),
                ("build", ["npm", "run", "build"], True),
                ("test", ["npm", "run", "test"], True),
            ]
        )
    else:
        _info("package.json not found; npm lint/build/test checks are skipped.")

    python_files = sorted((ROOT / "scripts").glob("*.py"))
    python_files.extend(sorted((ROOT / ".codex/hooks").glob("*.py")))
    if python_files:
        checks.append(
            (
                "python compile",
                [
                    "python3",
                    "-c",
                    _py_compile_snippet([str(path.relative_to(ROOT)) for path in python_files]),
                ],
                True,
            )
        )

    for json_path in _json_files():
        checks.append(
            (
                f"json parse {json_path.relative_to(ROOT)}",
                [
                    "python3",
                    "-c",
                    "import json, pathlib; "
                    f"json.loads(pathlib.Path({str(json_path)!r}).read_text(encoding='utf-8'))",
                ],
                True,
            )
        )

    pytest_file = ROOT / "scripts/test_execute.py"
    if pytest_file.exists():
        if _module_available("pytest"):
            checks.append(("pytest", ["python3", "-m", "pytest", "scripts/test_execute.py"], True))
        else:
            _info("pytest is not installed; scripts/test_execute.py is skipped.")

    for label, command, enabled in checks:
        if not enabled:
            _info(f"{label} script not found; skipped.")
            continue
        if _run(label, command) != 0:
            return 1

    _info("pre-commit checks passed.")
    return 0


def _package_scripts(package_json: Path) -> set[str]:
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _error(f"package.json is invalid JSON: {exc}")
        raise SystemExit(1)
    scripts = payload.get("scripts", {})
    return set(scripts) if isinstance(scripts, dict) else set()


def _json_files() -> list[Path]:
    candidates = [
        ROOT / ".agents/plugins/marketplace.json",
        ROOT / ".codex/hooks.json",
        ROOT / "plugins/harness/.codex-plugin/plugin.json",
    ]
    return [path for path in candidates if path.exists()]


def _module_available(name: str) -> bool:
    result = subprocess.run(
        ["python3", "-c", f"import importlib.util; raise SystemExit(importlib.util.find_spec({name!r}) is None)"],
        cwd=ROOT,
    )
    return result.returncode == 0


def _py_compile_snippet(paths: list[str]) -> str:
    return (
        "import py_compile, tempfile; "
        f"files={paths!r}; "
        "[py_compile.compile(f, cfile=tempfile.NamedTemporaryFile(suffix='.pyc').name, doraise=True) for f in files]"
    )


def _run(label: str, command: list[str]) -> int:
    if shutil.which(command[0]) is None:
        _error(f"{command[0]} not found while running {label}.")
        return 1

    _info(f"running {label}: {' '.join(command)}")
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        _error(f"{label} failed with exit code {result.returncode}.")
    return result.returncode


def _info(message: str) -> None:
    print(f"[pre-commit] {message}", file=sys.stderr)


def _error(message: str) -> None:
    print(f"[pre-commit] ERROR: {message}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
