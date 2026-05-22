from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_docker_compose_has_live_worker_service() -> None:
    compose_path = ROOT / "docker-compose.yml"
    assert compose_path.exists()
    
    # We parse the docker-compose file in a simple way or check string presence
    content = compose_path.read_text(encoding="utf-8")
    assert "token_payments_live_worker:" in content
    
    # Let's verify the configuration using helper function or direct assertions
    from test_docker_compose_runtime_services import _compose_services, _json_list_for_key, _scalar_for_key, _list_for_key
    services = _compose_services()
    assert "token_payments_live_worker" in services
    
    worker_service = services["token_payments_live_worker"]
    assert _scalar_for_key(worker_service, "image") == "token_payments_runtime"
    assert _json_list_for_key(worker_service, "command") == [
        "python", "-m", "token_payments", "worker", "--live", "--loop", "--confirm-live-worker"
    ]
    assert _list_for_key(worker_service, "profiles") == ["runtime"]
    assert _scalar_for_key(worker_service, "restart") == "unless-stopped"


def test_documentation_details_live_worker_flags() -> None:
    readme_path = ROOT / "README.md"
    harness_path = ROOT / "docs/HARNESS.md"
    
    assert readme_path.exists()
    assert harness_path.exists()
    
    readme_content = readme_path.read_text(encoding="utf-8")
    harness_content = harness_path.read_text(encoding="utf-8")
    
    # Ensure live worker flags and commands are documented
    assert "--live" in readme_content
    assert "--once" in readme_content
    assert "--loop" in readme_content
    assert "--confirm-live-worker" in readme_content
    assert "token_payments_live_worker" in readme_content
    
    assert "--live" in harness_content
    assert "--once" in harness_content
    assert "--loop" in harness_content
    assert "--confirm-live-worker" in harness_content
    assert "token_payments_live_worker" in harness_content


def test_phase_24_metadata_completes_step3() -> None:
    phase_index_path = ROOT / "phases/24-live-kafka-worker-runtime/index.json"
    assert phase_index_path.exists()
    
    with open(phase_index_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    step3 = next(s for s in data["steps"] if s["step"] == 3)
    assert step3["status"] == "completed"
    assert "summary" in step3
    assert len(step3["summary"]) > 20
