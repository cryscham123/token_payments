from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_feature_api_companion_guardrail_is_documented_across_harness_inputs() -> None:
    required_phrase = "Feature API Companion Rule"
    for path in (
        "AGENTS.md",
        "docs/HARNESS.md",
        "docs/API_SPEC.md",
        "plugins/harness/skills/harness-phase-planner/SKILL.md",
        "plugins/harness/skills/harness-review/SKILL.md",
    ):
        text = _read(path)
        assert required_phrase in text, f"{path} must preserve the feature/API companion guardrail"


def test_phase_planner_template_requires_api_contract_files_for_feature_work() -> None:
    planner = _read("plugins/harness/skills/harness-phase-planner/SKILL.md")

    for required in (
        "/docs/API_SPEC.md",
        "route manifest",
        "API tests",
        "intentional internal-only exception",
    ):
        assert required in planner
