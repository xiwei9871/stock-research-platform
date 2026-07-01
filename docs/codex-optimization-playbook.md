# Codex Optimization Playbook

This playbook standardizes how to reduce Codex token waste without making the
agent brittle.

## Goal

Use small, durable instructions plus selective command compression so Codex
spends fewer tokens on shell noise and more on reasoning.

## What To Optimize First

Prioritize these in order:

1. Keep `AGENTS.md` short and practical.
2. Route noisy shell commands through `rtk`.
3. Enforce the routing with a conservative project-level hook.
4. Disable low-frequency plugins and skills.
5. Keep MCP limited to tools that remove real manual loops.

Do not start by writing a large skill or a long global instruction file.

## Configuration Layers

Use the smallest surface that matches the scope:

- `~/.codex/`: personal defaults across repositories
- `<repo>/AGENTS.md`: repository map, verification commands, token discipline
- `<repo>/.codex/hooks.json`: project-level command rewriting or enforcement
- `~/.codex/config.toml`: global plugin, skill, and MCP defaults

Use global config for personal habits. Use project config for repository-specific
rules.

## Standard Rollout

### 1. Install RTK

```bash
brew install rtk
rtk init -g --codex
rtk --version
rtk gain
```

`rtk init -g --codex` adds a global Codex reference so the agent knows RTK is
available. It does not replace a project hook.

### 2. Add A Short Project `AGENTS.md`

Keep it focused on:

- repo map
- common checks
- token discipline
- done criteria

Good example:

```md
# Project Guidance For Codex

Keep context lean. Do not scan the whole repository unless the task requires it.
Use `rtk` for noisy shell commands when compressed output is sufficient.
Prefer targeted reads over full-file reads.

## Repo Map
- `src/`: application code
- `tests/`: automated checks
- `dashboard/`: frontend
- `scripts/`: cron and utility scripts
- `docs/`: runbooks and task references

## Common Checks
- backend tests: `.venv/bin/pytest`
- focused backend test: `.venv/bin/pytest tests/test_<name>.py -q`
- frontend tests: `cd dashboard && pnpm test`

## Token Discipline
- Prefer `rtk git status`, `rtk git diff`, `rtk rg`, `rtk pytest`, `rtk pnpm test`, and `rtk docker logs`.
- Use raw commands only when exact uncompressed output matters.

## Done Means
- Relevant checks ran, or blockers are reported precisely.
- Changes stay within scope.
- Summaries cite modified files and verification commands.
```

Do not put long design notes or broad engineering policy in `AGENTS.md`. Move
those into `docs/`.

### 3. Add A Conservative Project Hook

Use a project-level hook to rewrite only the highest-noise commands:

- `git diff`
- `git status`
- `git show`
- `rg`
- `pytest`
- `pnpm test`
- `docker logs`

Avoid rewriting:

- chained commands like `&&` and `||`
- pipelines
- redirections
- destructive commands

Keep a raw escape hatch such as `NO_RTK`.

In this repository the hook lives at:

- `AGENTS.md`
- `.codex/hooks.json`
- `.codex/hooks/rtk_rewrite.py`

The script should prefer `rtk rewrite` when possible so RTK owns the command
mapping logic.

### 4. Disable Low-Frequency Features

Disable plugins and skills that are rarely used in normal coding sessions.

Examples from this repository:

- disabled plugins: `documents`, `pdf`, `spreadsheets`, `presentations`
- disabled skills: `finishing-a-development-branch`, `receiving-code-review`,
  `using-git-worktrees`, `writing-skills`

Keep the browser and core coding skills enabled if they are used regularly.

### 5. Keep MCP Minimal

Only keep MCP servers that remove real work. If a server is rarely used or does
not save actual operator time, disable it.

For this repository the current setup is intentionally small. `node_repl`
remains enabled because it supports browser and local runtime workflows.

## Validation Checklist

After rollout, verify all of this:

```bash
rtk --version
rtk gain
codex --strict-config -C /path/to/repo --help >/dev/null
codex plugin list
codex mcp list
```

Then test one repository task that naturally triggers:

- one targeted file read
- one focused test command
- one search command

For example:

```text
In /path/to/repo:
1. Read project AGENTS.md and focus only on Common Checks and Done Means.
2. Run the most relevant focused test for the target area.
3. Find the main implementation file and corresponding test file.
4. Output only commands run, test result, implementation path, test path, and whether RTK was clearly used.
```

## A/B Test Method

Use the same repository, same model, and same prompt.

Recommended comparison:

- Window A: existing session without the new project hook
- Window B: fresh session in the target repo with the project hook trusted and enabled

Record:

- Codex session token total, if the surface exposes it
- completion time
- `rtk gain` before and after
- result quality

Tasks that best expose differences include:

- focused `pytest`
- `rg` or grep-based symbol lookup
- `git diff` or `git status`

Pure discussion tasks are poor RTK benchmarks because shell compression is not
the bottleneck.

## Measured Result In This Repository

The current `stock_research` setup showed clear benefit on a small verification
task:

- `rtk pytest tests/test_daily_close_pipeline.py -q`
- `rtk grep ... daily_close_pipeline ...`

Observed result:

- focused test passed: `21 passed`
- RTK savings increased during the task
- compressed output remained sufficient for the task outcome

The main savings came from `pytest`, not from short search output.

## Common Mistakes

- Writing a huge `AGENTS.md`
- Enabling many low-value skills
- Installing many MCP servers before validating need
- Rewriting every shell command through RTK
- Forcing RTK on pipelines and complex chained commands
- Measuring only subjective feel instead of token and timing data

## Team Recommendation

For new repositories, use this rollout order:

1. Install `rtk` globally.
2. Add a short repository `AGENTS.md`.
3. Add a conservative project hook.
4. Disable low-frequency plugins and skills.
5. Run one small A/B test before rolling out broadly.

That sequence gives most of the savings with low risk.
