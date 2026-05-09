# Harness Codex Plugin

Harness is a repo-local Codex plugin for phased implementation work.

## Skills
- `harness-phase-planner` plans and scaffolds `phases/{task}` step files.
- `harness-review` reviews current changes against `AGENTS.md` and `docs/*.md`.

## Runtime
The phase executor calls Codex non-interactively:

```bash
python3 scripts/execute.py <phase-dir>
python3 scripts/execute.py <phase-dir> --push
```

## Hooks
Project-local Codex hooks live under `.codex/`:

- `.codex/config.toml` enables `codex_hooks`.
- `.codex/hooks.json` wires `PreToolUse` and `PermissionRequest`.
- `.codex/hooks/*.py` contains the hook policies.

Git pre-commit checks live under `.githooks/`:

- `.githooks/pre-commit` delegates to `.githooks/pre_commit_check.py`.
- `core.hooksPath` is set to `.githooks` for this local repository.
- Node projects run `npm run lint`, `npm run build`, and `npm run test`; this Harness repo runs Python/JSON validation and pytest when pytest is installed.

To add this repo as a local Codex marketplace, run from any directory:

```bash
codex plugin marketplace add /home/cryscham123/demo/payments
```
