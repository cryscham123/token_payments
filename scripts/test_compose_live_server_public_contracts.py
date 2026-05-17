from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = "17-docker-compose-live-server"
DOC_PATHS = (ROOT / "README.md", ROOT / "app" / "README.md", ROOT / "docs" / "API_SPEC.md")


def test_docs_publish_plain_local_live_stack_path_without_profile_requirement() -> None:
    for path in DOC_PATHS:
        text = path.read_text(encoding="utf-8")
        assert "cp .env.example .env" in text
        assert "docker compose up" in text
        assert "docker compose --env-file .env --profile api up" not in text
        assert "docker compose --env-file .env --profile api build" not in text
        assert "docker compose --env-file .env.example config --services" in text
        assert "daemon-less compose config" in text
        assert "does not start Docker" in text


def test_docs_publish_seed_postman_readiness_security_smoke_and_cleanup_order() -> None:
    required_phrases = (
        "token-payments.local.seed-plan.json",
        "token-payments.local.postman_collection.json",
        "token-payments.local.postman_environment.json",
        "python3 scripts/docker_live_smoke.py --api-readiness --plan",
        "python3 scripts/docker_live_smoke.py --api-readiness --execute --confirm-live-docker",
        "curl --fail http://localhost:8000/healthz",
        "curl --fail http://localhost:8000/readyz",
        "docker compose down",
    )

    for path in DOC_PATHS:
        text = path.read_text(encoding="utf-8")
        for phrase in required_phrases:
            assert phrase in text, f"{path.relative_to(ROOT)} missing {phrase!r}"


def test_docs_and_env_explain_local_dev_secret_boundary_without_exposing_secret_values() -> None:
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    docs = "\n".join(path.read_text(encoding="utf-8") for path in DOC_PATHS)

    assert "local dev only" in env.lower()
    assert "RUNTIME_ENVIRONMENT=local" in env
    assert "live/prod startup rejects committed local dev signing values" in docs
    assert "production-ready" not in docs.lower()


def test_phase_17_metadata_closes_all_steps_and_top_level_status() -> None:
    phase = json.loads((ROOT / "phases" / PHASE_DIR / "index.json").read_text(encoding="utf-8"))
    top = json.loads((ROOT / "phases" / "index.json").read_text(encoding="utf-8"))
    top_phase = next(item for item in top["phases"] if item["dir"] == PHASE_DIR)

    assert top_phase["status"] == "completed"
    assert "completed_at" in top_phase
    assert all(step["status"] == "completed" for step in phase["steps"])
    for step in phase["steps"]:
        assert len(step.get("summary", "")) >= 80
    assert "plain docker compose up" in phase["steps"][0]["summary"]
    assert "driver factory" in phase["steps"][1]["summary"]
    assert "local dev" in phase["steps"][2]["summary"]
    assert "/readyz" in phase["steps"][3]["summary"]
    assert "public contract" in phase["steps"][4]["summary"]
