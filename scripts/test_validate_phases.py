import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import validate_phases as vp


def write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def make_valid_phase(root: Path):
    write_json(
        root / "phases" / "index.json",
        {"phases": [{"dir": "0-test", "status": "pending"}]},
    )
    write_json(
        root / "phases" / "0-test" / "index.json",
        {
            "project": "Token Payments",
            "phase": "0-test",
            "steps": [
                {"step": 0, "name": "first-step", "status": "pending"},
                {"step": 1, "name": "second-step", "status": "completed", "summary": "done"},
            ],
        },
    )
    (root / "phases" / "0-test" / "step0.md").write_text("# Step 0\n", encoding="utf-8")
    (root / "phases" / "0-test" / "step1.md").write_text("# Step 1\n", encoding="utf-8")


def messages(errors):
    return [error.message for error in errors]


def test_valid_phase_metadata(tmp_path):
    make_valid_phase(tmp_path)

    assert vp.validate(tmp_path) == []


def test_rejects_invalid_top_level_status(tmp_path):
    make_valid_phase(tmp_path)
    write_json(
        tmp_path / "phases" / "index.json",
        {"phases": [{"dir": "0-test", "status": "running"}]},
    )

    assert any("status" in message for message in messages(vp.validate(tmp_path)))


def test_requires_step_file(tmp_path):
    make_valid_phase(tmp_path)
    (tmp_path / "phases" / "0-test" / "step1.md").unlink()

    assert "step file is missing" in messages(vp.validate(tmp_path))


def test_completed_step_requires_summary(tmp_path):
    make_valid_phase(tmp_path)
    index_path = tmp_path / "phases" / "0-test" / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["steps"][1].pop("summary")
    write_json(index_path, index)

    assert any("completed status requires `summary`" in message for message in messages(vp.validate(tmp_path)))


def test_requires_contiguous_step_numbers(tmp_path):
    make_valid_phase(tmp_path)
    index_path = tmp_path / "phases" / "0-test" / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["steps"][1]["step"] = 3
    write_json(index_path, index)
    (tmp_path / "phases" / "0-test" / "step3.md").write_text("# Step 3\n", encoding="utf-8")

    assert any("contiguous" in message for message in messages(vp.validate(tmp_path)))
