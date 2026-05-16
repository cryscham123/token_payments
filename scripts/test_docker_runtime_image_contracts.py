from __future__ import annotations

import fnmatch
import json
import re
import shlex
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DOCKERIGNORE_PATTERNS = {
    ".env",
    ".venv",
    "**/data",
    "phases/**/step*-output.json",
    "phases/**/phase*-output.json",
    ".git",
    "__pycache__",
    ".pytest_cache",
}
FORBIDDEN_DOCKERFILE_COPY_SOURCES = {
    ".",
    "./",
    ".env",
    ".git",
    ".venv",
    "phases",
    "phases/",
}
REQUIRED_DOCKERFILE_COPY_SOURCES = {
    "app/token_payments",
    "Dockerfile",
    ".dockerignore",
    "docker-compose.yml",
    ".env.example",
    "app/postgres/init.d/001-token-payments-schema.sql",
    "app/test_network/Dockerfile",
}
FORBIDDEN_DOCKERFILE_TERMS = {
    "claude",
    ".claude",
    "anthropic",
    "private_key",
    "seed_phrase",
    "api_key",
    "password",
    "replace_with_local_dev_only",
}
LONG_RUNNING_COMMAND_TERMS = {
    "uvicorn",
    "gunicorn",
    "flask run",
    "runserver",
    "serve-api",
    "worker",
    "run-worker",
}


def test_dockerfile_exists_and_uses_python_312_runtime_base() -> None:
    dockerfile = _read_required(ROOT / "Dockerfile")

    assert re.search(r"(?m)^FROM\s+python:3\.12(?:[-\w.]*)(?:\s+AS\s+\w+)?\s*$", dockerfile)
    assert "pip install" not in dockerfile.lower()


def test_dockerfile_sets_internal_app_pythonpath_and_bounded_health_command() -> None:
    dockerfile = _read_required(ROOT / "Dockerfile")
    env = _instruction_values(dockerfile, "ENV")
    cmd = _json_instruction(dockerfile, "CMD")

    assert any(value == "PYTHONPATH=/workspace/app" for value in env)
    assert cmd == ["python", "-m", "token_payments", "health"]

    lowered = dockerfile.lower()
    for term in LONG_RUNNING_COMMAND_TERMS:
        assert term not in lowered


def test_dockerfile_copies_runtime_package_and_static_smoke_contracts_without_local_artifacts() -> None:
    dockerfile = _read_required(ROOT / "Dockerfile")

    assert _instruction_values(dockerfile, "ADD") == []

    copy_sources = _copy_sources(dockerfile)
    assert copy_sources
    assert set(copy_sources).isdisjoint(FORBIDDEN_DOCKERFILE_COPY_SOURCES)
    assert REQUIRED_DOCKERFILE_COPY_SOURCES <= set(copy_sources)
    assert not any("data" in source.split("/") for source in copy_sources)
    assert not any("step" in source and "output" in source for source in copy_sources)
    assert not any("phase" in source and "output" in source for source in copy_sources)


def test_dockerfile_has_no_claude_commands_or_sensitive_placeholder_values() -> None:
    dockerfile = _read_required(ROOT / "Dockerfile")
    lowered = dockerfile.lower()

    for term in FORBIDDEN_DOCKERFILE_TERMS:
        assert term not in lowered


def test_dockerignore_excludes_local_secrets_cache_git_and_phase_artifacts() -> None:
    dockerignore = _read_required(ROOT / ".dockerignore")
    patterns = _dockerignore_patterns(dockerignore)

    assert REQUIRED_DOCKERIGNORE_PATTERNS <= set(patterns)

    for committed_contract_path in (
        "app/postgres/init.d/001-token-payments-schema.sql",
        "app/test_network/Dockerfile",
    ):
        assert not _dockerignore_excludes(patterns, committed_contract_path)


def _read_required(path: Path) -> str:
    assert path.exists(), f"{path.relative_to(ROOT)} must exist"
    return path.read_text(encoding="utf-8")


def _instruction_values(dockerfile: str, instruction: str) -> list[str]:
    prefix = instruction.upper()
    values: list[str] = []
    for raw_line in dockerfile.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        command, _, payload = line.partition(" ")
        if command.upper() == prefix:
            values.append(payload.strip())
    return values


def _json_instruction(dockerfile: str, instruction: str) -> list[str]:
    values = _instruction_values(dockerfile, instruction)
    assert len(values) == 1
    return json.loads(values[0])


def _copy_sources(dockerfile: str) -> list[str]:
    sources: list[str] = []
    for value in _instruction_values(dockerfile, "COPY"):
        if value.startswith("["):
            parts = json.loads(value)
        else:
            parts = [part for part in shlex.split(value) if not part.startswith("--")]
        assert len(parts) >= 2
        sources.extend(_normalize_source(part) for part in parts[:-1])
    return sources


def _normalize_source(source: str) -> str:
    return source.rstrip("/")


def _dockerignore_patterns(dockerignore: str) -> list[str]:
    patterns: list[str] = []
    for raw_line in dockerignore.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line.rstrip("/"))
    return patterns


def _dockerignore_excludes(patterns: list[str], path: str) -> bool:
    return any(
        fnmatch.fnmatch(path, pattern)
        or fnmatch.fnmatch(path, f"{pattern}/**")
        or fnmatch.fnmatch(Path(path).name, pattern)
        for pattern in patterns
    )
