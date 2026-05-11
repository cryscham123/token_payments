from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


PUBLIC_EXPORTS = {
    "DEFAULT_BROWSER_PREVIEW_HOST",
    "DEFAULT_BROWSER_PREVIEW_PORT",
    "BrowserPreviewHttpServer",
    "BrowserPreviewRequestHandler",
    "build_browser_preview_server",
    "render_browser_preview_document",
    "serve_browser_preview",
}

DOCUMENTED_BROWSER_COMMANDS = (
    "PYTHONPATH=app python3 scripts/browser_preview_server.py --host 127.0.0.1 --port 8765",
    "PYTHONPATH=app python3 scripts/browser_preview_smoke.py",
    "http://127.0.0.1:8765/customer",
    "http://127.0.0.1:8765/operator",
)

DOCUMENTED_BROWSER_PHRASES = (
    "Browser Preview Runtime",
    "local-only preview fixture",
    "does not connect to DB, Kafka, Docker, Blockchain RPC, or local `.env`",
    "Ctrl-C",
)


def test_runtime_public_exports_include_browser_preview_helpers() -> None:
    import token_payments.runtime as runtime

    assert PUBLIC_EXPORTS <= set(runtime.__all__)
    assert runtime.DEFAULT_BROWSER_PREVIEW_HOST == "127.0.0.1"
    assert runtime.DEFAULT_BROWSER_PREVIEW_PORT == 8765
    assert all(hasattr(runtime, name) for name in PUBLIC_EXPORTS)


def test_readmes_document_browser_preview_runtime_commands_urls_and_boundaries() -> None:
    for path in (ROOT / "README.md", ROOT / "app" / "README.md"):
        text = path.read_text(encoding="utf-8")

        for command in DOCUMENTED_BROWSER_COMMANDS:
            assert command in text, f"{path.relative_to(ROOT)} must document {command!r}"
        for phrase in DOCUMENTED_BROWSER_PHRASES:
            assert phrase in text, f"{path.relative_to(ROOT)} must document {phrase!r}"

        section = _section(text, "## Browser Preview Runtime")
        lower_section = section.lower()
        for blocked in _tool_specific_terms():
            assert blocked not in lower_section


def test_browser_preview_source_and_public_docs_avoid_tool_specific_paths_and_committed_secrets() -> None:
    browser_files = (
        ROOT / "app/token_payments/runtime/browser_preview.py",
        ROOT / "scripts/browser_preview_server.py",
        ROOT / "scripts/browser_preview_smoke.py",
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in browser_files).lower()
    browser_doc_sections = "\n".join(
        _section(path.read_text(encoding="utf-8"), "## Browser Preview Runtime").lower()
        for path in (ROOT / "README.md", ROOT / "app" / "README.md")
    )

    for blocked in _tool_specific_terms():
        assert blocked not in source
        assert blocked not in browser_doc_sections

    for blocked in _committed_secret_terms():
        assert blocked not in source
        assert blocked not in browser_doc_sections


def test_phase_11_metadata_closes_browser_preview_public_contracts() -> None:
    phase_index = json.loads((ROOT / "phases/11-browser-preview-runtime/index.json").read_text(encoding="utf-8"))
    top_index = json.loads((ROOT / "phases/index.json").read_text(encoding="utf-8"))
    step2 = next(step for step in phase_index["steps"] if step["step"] == 2)

    assert step2["status"] == "completed"
    summary = step2.get("summary", "")
    assert len(summary) >= 80
    for term in (
        "public contract",
        "README",
        "Browser Preview Runtime",
        "scripts/test_browser_preview_public_contracts.py",
        "browser preview smoke",
    ):
        assert term in summary

    completed_summary_text = " ".join(
        step.get("summary", "") for step in phase_index["steps"] if step["status"] == "completed"
    )
    for term in ("browser preview server", "smoke runner", "public contract"):
        assert term in completed_summary_text.lower()

    phase11 = next(phase for phase in top_index["phases"] if phase["dir"] == "11-browser-preview-runtime")
    assert phase11["status"] == "completed"
    assert phase11.get("completed_at")


def _section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start == -1:
        return ""
    next_heading = text.find("\n## ", start + len(heading))
    if next_heading == -1:
        return text[start:]
    return text[start:next_heading]


def _tool_specific_terms() -> tuple[str, ...]:
    return (
        "cla" + "ude",
        ".cla" + "ude",
        "anth" + "ropic",
    )


def _committed_secret_terms() -> tuple[str, ...]:
    return (
        "private" + "_key",
        "private" + " key value",
        "seed" + " phrase value",
        "mnemon" + "ic value",
        "committed" + " secret",
    )
