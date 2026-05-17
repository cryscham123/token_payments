from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_auth_docs_define_postgresql_as_auth_source_of_truth() -> None:
    combined = "\n".join(
        _read(path)
        for path in (
            "docs/ARCHITECTURE.md",
            "docs/DOMAIN_MODEL.md",
            "docs/API_SPEC.md",
            "README.md",
            "app/README.md",
        )
    )

    assert "PostgreSQL is the source of truth for auth users, login challenges, and sessions" in combined
    assert "refresh reuse detection uses the PostgreSQL session repository hash/salt/rotation model" in combined
    assert "Redis is optional cache-aside/TTL optimization, not a live required dependency" in combined


def test_env_example_documents_local_secret_override_and_live_placeholder_rejection() -> None:
    env_example = _read(".env.example")
    docs = "\n".join(_read(path) for path in ("README.md", "app/README.md", "docs/API_SPEC.md"))

    assert "Local dev only signing values below are committed only for localhost use" in env_example
    assert "live/prod startup rejects committed local dev signing values" in docs
    assert "SESSION_SIGNING_KEYS=local-dev-2026=local_dev_only_session_signing_key" in env_example
    assert "CSRF_SIGNING_KEY=local_dev_only_csrf_signing_key" in env_example


def test_env_example_does_not_commit_real_secret_material() -> None:
    values = {
        key: value
        for key, value in _parse_env(_read(".env.example")).items()
        if any(token in key for token in ("KEY", "SECRET", "PASSWORD", "TOKEN", "DSN"))
        and not key.endswith("_KEY_ID")
    }

    assert values
    for key, value in values.items():
        lowered = value.lower()
        assert (
            "replace_with_local_dev_only" in lowered
            or "local_dev_only" in lowered
            or key in {
                "ADAPTER_POSTGRES_DSN",
                "ADAPTER_BLOCKCHAIN_RPC_URL",
                "ADAPTER_BLOCKCHAIN_RPC_PATH",
            }
        ), key
        assert "prod" not in lowered
        assert "mainnet" not in lowered
        assert "seed phrase" not in lowered

    private_key = _parse_env(_read(".env.example"))["TEST_NETWORK_PRIVATE_KEY"]
    assert private_key == "0xreplace_with_local_dev_only_private_key"


def _parse_env(text: str) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        entries[key] = value
    return entries


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")
