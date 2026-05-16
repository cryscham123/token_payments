from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

INFRASTRUCTURE_SERVICES = {"postgres", "kafka", "kafka-ui", "pgweb", "test_network"}
RUNTIME_SERVICES = {
    "token_payments_health": ["python", "-m", "token_payments", "health"],
    "token_payments_worker": ["python", "-m", "token_payments", "worker"],
    "token_payments_smoke": ["python", "-m", "token_payments", "smoke", "compose-readiness"],
}
REQUIRED_DEPENDENCIES = {"postgres", "kafka", "test_network"}
ONE_SHOT_RESTART_VALUES = {"no", "false", "0", "none"}


def test_compose_keeps_existing_infrastructure_services() -> None:
    services = _compose_services()

    assert INFRASTRUCTURE_SERVICES <= set(services)
    assert _list_for_key(services["postgres"], "env_file") == [".env"]
    assert _nested_scalar(services["test_network"], "build", "context") == "app/test_network"
    assert _list_for_key(services["test_network"], "env_file") == [".env"]
    assert "postgres" in _depends_on_conditions(services["pgweb"])
    assert "kafka" in _depends_on_conditions(services["kafka-ui"])


def test_runtime_services_share_root_runtime_image_and_env_contract() -> None:
    services = _compose_services()
    images: set[str] = set()

    for service_name in RUNTIME_SERVICES:
        service = services[service_name]
        images.add(_scalar_for_key(service, "image") or "")

        assert _nested_scalar(service, "build", "context") == "."
        assert _nested_scalar(service, "build", "dockerfile") == "Dockerfile"
        assert _list_for_key(service, "env_file") == [".env"]
        assert "PYTHONPATH=/workspace/app" in _list_for_key(service, "environment")

    assert images == {"token_payments_runtime"}


def test_runtime_services_use_bounded_one_shot_commands() -> None:
    services = _compose_services()

    for service_name, expected_command in RUNTIME_SERVICES.items():
        service = services[service_name]

        assert _json_list_for_key(service, "command") == expected_command
        assert (_scalar_for_key(service, "restart") or "").lower() in ONE_SHOT_RESTART_VALUES
        assert not _long_running_command(expected_command)


def test_runtime_services_depend_on_required_infrastructure() -> None:
    services = _compose_services()

    for service_name in RUNTIME_SERVICES:
        dependencies = _depends_on_conditions(services[service_name])

        assert REQUIRED_DEPENDENCIES <= set(dependencies)
        assert dependencies["postgres"] == "service_healthy"
        assert dependencies["kafka"] == "service_started"
        assert dependencies["test_network"] == "service_started"


def _compose_services() -> dict[str, tuple[str, ...]]:
    path = ROOT / "docker-compose.yml"
    assert path.exists(), "docker-compose.yml must exist"

    services: dict[str, list[str]] = {}
    in_services = False
    current_service: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = _indent_width(raw_line)
        if indent == 0 and stripped == "services:":
            in_services = True
            current_service = None
            continue
        if not in_services:
            continue
        if indent == 0:
            break
        if indent == 2 and stripped.endswith(":") and not stripped.startswith("- "):
            current_service = stripped[:-1]
            services[current_service] = []
            continue
        if current_service is not None:
            services[current_service].append(raw_line)

    assert in_services, "docker-compose.yml must have a services block"
    return {name: tuple(block) for name, block in services.items()}


def _base_indent(block: tuple[str, ...]) -> int | None:
    indents = [
        _indent_width(line)
        for line in block
        if line.strip() and not line.strip().startswith("#") and not line.strip().startswith("- ")
    ]
    return min(indents) if indents else None


def _scalar_for_key(block: tuple[str, ...], key: str) -> str | None:
    base_indent = _base_indent(block)
    if base_indent is None:
        return None
    prefix = f"{key}:"
    for line in block:
        stripped = line.strip()
        if _indent_width(line) == base_indent and stripped.startswith(prefix):
            value = stripped[len(prefix) :].strip()
            return _unquote(value) if value else None
    return None


def _list_for_key(block: tuple[str, ...], key: str) -> list[str]:
    base_indent = _base_indent(block)
    if base_indent is None:
        return []
    prefix = f"{key}:"
    for index, line in enumerate(block):
        stripped = line.strip()
        indent = _indent_width(line)
        if indent != base_indent or not stripped.startswith(prefix):
            continue
        scalar_value = stripped[len(prefix) :].strip()
        if scalar_value:
            parsed = json.loads(scalar_value) if scalar_value.startswith("[") else [_unquote(scalar_value)]
            return [str(value) for value in parsed]

        values: list[str] = []
        for nested in block[index + 1 :]:
            nested_stripped = nested.strip()
            if not nested_stripped or nested_stripped.startswith("#"):
                continue
            nested_indent = _indent_width(nested)
            if nested_indent <= indent:
                break
            if nested_stripped.startswith("- "):
                values.append(_list_item_value(nested_stripped[2:].strip()))
        return values
    return []


def _list_item_value(value: str) -> str:
    if value.startswith("path:"):
        return _unquote(value[len("path:") :].strip())
    return _unquote(value)


def _json_list_for_key(block: tuple[str, ...], key: str) -> list[str]:
    value = _scalar_for_key(block, key)
    assert value is not None, f"{key} must be present"
    parsed = json.loads(value)
    assert isinstance(parsed, list)
    return [str(item) for item in parsed]


def _nested_scalar(block: tuple[str, ...], parent_key: str, child_key: str) -> str | None:
    base_indent = _base_indent(block)
    if base_indent is None:
        return None
    parent_prefix = f"{parent_key}:"
    child_prefix = f"{child_key}:"
    for index, line in enumerate(block):
        stripped = line.strip()
        indent = _indent_width(line)
        if indent != base_indent or not stripped.startswith(parent_prefix):
            continue
        for nested in block[index + 1 :]:
            nested_stripped = nested.strip()
            if not nested_stripped or nested_stripped.startswith("#"):
                continue
            nested_indent = _indent_width(nested)
            if nested_indent <= indent:
                break
            if nested_stripped.startswith(child_prefix):
                return _unquote(nested_stripped[len(child_prefix) :].strip())
    return None


def _depends_on_conditions(block: tuple[str, ...]) -> dict[str, str | None]:
    base_indent = _base_indent(block)
    if base_indent is None:
        return {}
    for index, line in enumerate(block):
        stripped = line.strip()
        indent = _indent_width(line)
        if indent != base_indent or not stripped.startswith("depends_on:"):
            continue

        dependencies: dict[str, str | None] = {}
        current_dependency: str | None = None
        for nested in block[index + 1 :]:
            nested_stripped = nested.strip()
            if not nested_stripped or nested_stripped.startswith("#"):
                continue
            nested_indent = _indent_width(nested)
            if nested_indent <= indent:
                break
            if nested_stripped.endswith(":") and not nested_stripped.startswith("- "):
                current_dependency = nested_stripped[:-1]
                dependencies[current_dependency] = None
                continue
            if current_dependency and nested_stripped.startswith("condition:"):
                dependencies[current_dependency] = _unquote(nested_stripped[len("condition:") :].strip())
        return dependencies
    return {}


def _long_running_command(command: list[str]) -> bool:
    lowered = " ".join(command).lower()
    return any(term in lowered for term in ("uvicorn", "gunicorn", "flask run", "runserver", "serve-api"))


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
