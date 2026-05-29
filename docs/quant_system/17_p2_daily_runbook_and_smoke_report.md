# P2 Daily Runbook And Smoke Report

Date: 2026-05-29

## Purpose

This document records the daily P2 operator flow and the first operational smoke run.
It validates that P2-1 through P2-3 can be chained through the real CLI without adding
database tables, schedulers, broker adapters, or automatic trading hooks.

## Daily Runbook

### 1. Prepare Source Artifacts

Prepare or locate the daily source artifacts:

- delivery preview JSON, such as Feishu/OpenClaw/local delivery preview
- agent report JSON
- simulation state JSON files
- optional trade advice CSV
- factor validation review JSON
- technical feature performance review JSON
- watchlist diagnostics Markdown or JSON

Every artifact path should be local and reviewable. Do not include webhook URLs,
tokens, credentials, broker account data, or order execution payloads.

### 2. Generate Virtual Portfolio Review

Run:

```bash
.venv/bin/stock-research p2-simulation-review \
  --trade-date <YYYY-MM-DD> \
  --portfolio-id <portfolio_id> \
  --simulation-state <state_1.json> \
  --simulation-state <state_2.json> \
  --trade-advice <trade_advice.csv> \
  --output-dir outputs/p2/<YYYY-MM-DD>/simulation
```

Expected output lines:

```text
p2_simulation_review|status|manual_review_required
p2_simulation_review|json|...
p2_simulation_review|markdown|...
p2_simulation_review|history_csv|...
p2_simulation_review|positions_csv|...
```

Operator check:

- `status` should remain `manual_review_required`.
- `auto_trade_enabled` should remain `false`.
- `human_confirmation_required` should remain `true`.
- Latest risk level, drawdown, exposure, and advice issue count should be inspected
  before any manual decision.

### 3. Build P2 Rollup Manifest

Create a manifest with this shape:

```json
{
  "trade_date": "<YYYY-MM-DD>",
  "run_id": "p2-<YYYY-MM-DD>",
  "artifacts": [
    {
      "group": "delivery",
      "name": "feishu_preview",
      "path": "path/to/feishu_preview.json",
      "required": true
    },
    {
      "group": "agent",
      "name": "agent_report",
      "path": "path/to/agent_report.json",
      "required": true
    },
    {
      "group": "simulation",
      "name": "virtual_portfolio_review",
      "path": "path/to/virtual_portfolio_review.json",
      "required": true
    },
    {
      "group": "factor_validation",
      "name": "factor_validation_review",
      "path": "path/to/factor_validation_review.json",
      "required": true
    },
    {
      "group": "technical_performance",
      "name": "technical_feature_performance_review",
      "path": "path/to/technical_feature_performance_review.json",
      "required": true
    },
    {
      "group": "watchlist",
      "name": "watchlist_diagnostics",
      "path": "path/to/watchlist_diagnostics.md",
      "required": false
    }
  ]
}
```

Operator check:

- Required artifacts should be the minimum set needed to decide whether the day is
  reviewable.
- Optional artifacts should produce warnings, not crashes.
- Source paths are part of the audit trail and should not be rewritten casually.

### 4. Generate Artifact Rollup

Run:

```bash
.venv/bin/stock-research p2-artifact-rollup \
  --manifest outputs/p2/<YYYY-MM-DD>/inputs/p2_rollup_manifest.json \
  --output-dir outputs/p2/<YYYY-MM-DD>/rollup
```

Expected output lines:

```text
p2_artifact_rollup|status|ready
p2_artifact_rollup|json|...
p2_artifact_rollup|markdown|...
```

Operator check:

- `status = ready` means all required artifacts exist.
- `status = warning` means required artifacts exist but optional artifacts are missing.
- `status = blocked` means at least one required artifact is missing and the day should
  not proceed to normal review.

### 5. Generate Aggregate Review

Run:

```bash
.venv/bin/stock-research p2-aggregate-review \
  --trade-date <YYYY-MM-DD> \
  --rollup outputs/p2/<YYYY-MM-DD>/rollup/p2_artifact_rollup_<...>.json \
  --output-dir outputs/p2/<YYYY-MM-DD>/aggregate
```

Expected output lines:

```text
p2_aggregate_review|status|review_required
p2_aggregate_review|json|...
p2_aggregate_review|markdown|...
```

Operator check:

- Review blockers must be inspected first.
- `review_required` is expected when simulation advice or risk remains manual-review
  gated.
- `blocked` should stop the daily process until the blocker is resolved.
- `auto_trade_enabled` must remain `false`.
- `human_confirmation_required` must remain `true`.

## Smoke Run

### Scope

Smoke date: `2026-05-29`

Input/output root:

```text
outputs/p2_smoke/2026-05-29/
```

The smoke used controlled local input artifacts under the ignored `outputs/` tree.
These files are not committed. The CLI commands and generated P2 outputs are real.

### Smoke Commands

Generate virtual portfolio review:

```bash
.venv/bin/stock-research p2-simulation-review \
  --trade-date 2026-05-29 \
  --portfolio-id p2_smoke_demo \
  --simulation-state outputs/p2_smoke/2026-05-29/inputs/portfolio_state_2026-05-28.json \
  --simulation-state outputs/p2_smoke/2026-05-29/inputs/portfolio_state_2026-05-29.json \
  --trade-advice outputs/p2_smoke/2026-05-29/inputs/trade_advice.csv \
  --output-dir outputs/p2_smoke/2026-05-29/simulation
```

Generate rollup:

```bash
.venv/bin/stock-research p2-artifact-rollup \
  --manifest outputs/p2_smoke/2026-05-29/inputs/p2_rollup_manifest.json \
  --output-dir outputs/p2_smoke/2026-05-29/rollup
```

Generate aggregate review:

```bash
.venv/bin/stock-research p2-aggregate-review \
  --trade-date 2026-05-29 \
  --rollup outputs/p2_smoke/2026-05-29/rollup/p2_artifact_rollup_2026-05-29_p2-smoke-2026-05-29.json \
  --output-dir outputs/p2_smoke/2026-05-29/aggregate
```

### Smoke Results

Simulation output:

```text
p2_simulation_review|status|manual_review_required
p2_simulation_review|json|outputs/p2_smoke/2026-05-29/simulation/virtual_portfolio_review_2026-05-29_p2_smoke_demo.json
p2_simulation_review|markdown|outputs/p2_smoke/2026-05-29/simulation/virtual_portfolio_review_2026-05-29_p2_smoke_demo.md
p2_simulation_review|history_csv|outputs/p2_smoke/2026-05-29/simulation/virtual_portfolio_review_2026-05-29_p2_smoke_demo_history.csv
p2_simulation_review|positions_csv|outputs/p2_smoke/2026-05-29/simulation/virtual_portfolio_review_2026-05-29_p2_smoke_demo_positions.csv
```

Rollup output:

```text
p2_artifact_rollup|status|ready
p2_artifact_rollup|json|outputs/p2_smoke/2026-05-29/rollup/p2_artifact_rollup_2026-05-29_p2-smoke-2026-05-29.json
p2_artifact_rollup|markdown|outputs/p2_smoke/2026-05-29/rollup/p2_artifact_rollup_2026-05-29_p2-smoke-2026-05-29.md
```

Aggregate output:

```text
p2_aggregate_review|status|review_required
p2_aggregate_review|json|outputs/p2_smoke/2026-05-29/aggregate/p2_aggregate_review_2026-05-29.json
p2_aggregate_review|markdown|outputs/p2_smoke/2026-05-29/aggregate/p2_aggregate_review_2026-05-29.md
```

### Smoke Observations

Rollup summary:

```text
status=ready
artifact_count=6
missing_required_count=0
warning_count=0
groups=agent,delivery,factor_validation,simulation,technical_performance,watchlist
```

Simulation summary:

```text
status=manual_review_required
state_count=2
latest_risk_level=warning
max_drawdown=-0.11
warning_state_count=1
advice_count=1
advice_issue_count=0
auto_trade_enabled=false
human_confirmation_required=true
```

Aggregate summary:

```text
status=review_required
source_rollup_status=ready
blocker_count=0
warning_count=1
auto_trade_enabled=false
human_confirmation_required=true
```

Aggregate section statuses:

| Section | Status |
| --- | --- |
| delivery | `present` |
| agent | `passed` |
| simulation | `manual_review_required` |
| factor_validation | `approved_candidate` |
| technical_performance | `passed` |
| watchlist | `present` |

## Conclusion

The P2 CLI chain works as an operational review flow:

1. P2 simulation review generates review-only portfolio artifacts.
2. P2 artifact rollup verifies required source artifacts and writes a daily package.
3. P2 aggregate review produces a single operator-facing JSON/Markdown entrypoint.

The expected final state for this smoke is `review_required`, not `ready`, because
simulation remains explicitly gated for human review. No automatic trading path is
enabled.

## Follow-Up

- Add a production manifest template once the daily artifact directory convention is
  stable.
- Decide whether P3 starts with dashboard/read-model work or scheduler integration.
- Resolve the existing unrelated watchlist diagnostics worktree changes before starting
  a larger P3 implementation branch.
