# Project Guidance For Codex

Keep context lean. Do not scan the whole repository unless the task requires it.
Use `rtk` for noisy shell commands when compressed output is sufficient.
Prefer targeted reads over full-file reads.

## Repo Map
- `src/stock_research/`: Python application and CLI code
- `tests/`: pytest suite for backend, scripts, and dashboard APIs
- `dashboard/`: Vite/React frontend with `pnpm`
- `scripts/`: cron wrappers, watchdogs, and batch utilities
- `docs/`: runbooks, design notes, and task-specific references
- `config/`: runtime configuration inputs

## Common Checks
- backend tests: `.venv/bin/pytest`
- focused backend test: `.venv/bin/pytest tests/test_<name>.py -q`
- dashboard tests: `cd dashboard && pnpm test`
- dashboard build: `cd dashboard && pnpm build`

## Token Discipline
- Prefer `rtk git status`, `rtk git diff`, `rtk git show`, `rtk rg`, `rtk pytest`, `rtk pnpm test`, and `rtk docker logs`.
- Use raw commands only when exact uncompressed output matters.
- Summarize failures instead of pasting large logs.

## Done Means
- Changes stay within the requested scope.
- Relevant tests or builds are run, or blockers are reported precisely.
- Summaries cite modified files and verification commands.
