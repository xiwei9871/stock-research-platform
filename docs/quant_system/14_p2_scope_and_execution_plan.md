# P2 Scope And Execution Plan

Date: 2026-05-28

## Status

P2 first scoped pass completed.

P1 was completed in:

- `27084bd feat: complete p1 research platform layers`

P2-0 workspace cleanup was completed in:

- `fad6dd3 docs: add planning backlog artifacts`

## Why P2 Starts With Scope Freeze

P2 sits between research artifacts and daily operations. Without a frozen first scope, it is easy to mix four different concerns:

- daily artifact orchestration
- virtual portfolio state
- aggregate review reports
- live or semi-live trading hooks

The first P2 scope freezes the execution order and explicitly keeps live trading out of the implementation path.

## P2 In Scope

### P2-1 Artifact Operationalization

Goal: turn P1 artifacts into one daily, repeatable review package.

Deliver:

- A daily rollup manifest for P1 artifacts.
- A Markdown review entrypoint that links delivery, agent, simulation, factor validation, technical performance, and watchlist diagnostics artifacts.
- CLI support for generating the rollup from existing local outputs.
- Tests for missing optional artifacts, required artifact summaries, and CLI output.

Boundary:

- File-based artifacts first.
- No new database tables in P2-1.
- No scheduler dependency in P2-1.

### P2-2 Simulation Productization

Goal: turn P1 simulation artifacts into a persistent virtual portfolio review layer.

Deliver:

- Rolling simulation state history.
- Position/risk summary over time.
- Review-grade drawdown and exposure summaries.
- Explicit "manual review required" trade advice state.

Boundary:

- Still no broker connection.
- Still no automatic order generation.

Implementation status: implemented and ready for review.

Delivered:

- `stock_research.simulation.virtual_portfolio.load_simulation_states`
- `stock_research.simulation.virtual_portfolio.build_virtual_portfolio_review`
- `stock_research.simulation.virtual_portfolio.write_virtual_portfolio_review`
- CLI command:
  - `p2-simulation-review`
- Module tests:
  - `tests/test_virtual_portfolio_review.py`
- CLI tests:
  - `tests/test_factor_cli.py -k p2_simulation_review`

Review boundary:

- Consumes P1 simulation review/state JSON and optional trade advice CSV.
- Writes file-based JSON, Markdown, rolling history CSV, and latest positions CSV.
- Keeps `status = manual_review_required`.
- Keeps `auto_trade_enabled = false`.

### P2-3 Aggregate Review Report

Goal: produce one operator-facing daily review report.

Deliver:

- One Markdown/JSON aggregate report.
- Sections for market/readiness, watchlist, agent observations, simulation state, factor validation, technical performance, and delivery status.
- Review blockers surfaced at the top.

Boundary:

- No Web dashboard until the report contract is stable.

Implementation status: implemented and ready for review.

Delivered:

- `stock_research.p2.aggregate_review.load_aggregate_artifact_payloads`
- `stock_research.p2.aggregate_review.build_p2_aggregate_review`
- `stock_research.p2.aggregate_review.write_p2_aggregate_review`
- CLI command:
  - `p2-aggregate-review`
- Module tests:
  - `tests/test_p2_aggregate_review.py`
- CLI tests:
  - `tests/test_factor_cli.py -k p2_aggregate_review`

Review boundary:

- Consumes the P2 artifact rollup JSON.
- Reads JSON artifact payloads when available and preserves source paths.
- Writes one aggregate JSON report and one operator-facing Markdown report.
- Surfaces missing required artifacts and blocked source sections at the top.
- Keeps `auto_trade_enabled = false` and `human_confirmation_required = true`.

### P2-4 Durable Storage Decision

Goal: decide which P2 artifacts deserve durable tables.

Deliver:

- A schema proposal only after P2-1 to P2-3 artifact contracts stabilize.
- Migration plan for selected rollup metadata if needed.

Boundary:

- Do not add tables before the file contracts prove useful.

Implementation status: decision completed and ready for review.

Delivered:

- Durable storage decision:
  - `docs/quant_system/15_p2_durable_storage_decision.md`

Decision summary:

- Do not add new P2 database tables in P2-4.
- Keep P2-1 through P2-3 artifacts as the source of truth for the rest of P2.
- Use existing `report.report_run` only as an optional report-path index if needed.
- Promote selected aggregate review and virtual portfolio metadata into future tables
  only after repeated daily runs prove the file contracts stable.

## Out Of Scope For P2

- Live trading.
- Broker adapters.
- Automatic order placement.
- Complex Web dashboard.
- Rewriting the factor, backtest, or technical indicator engines.
- Replacing existing P0/P1 CLI flows.

## Execution Order

1. P2-0: clean workspace and commit planning backlog.
2. P2-1: implement artifact operationalization.
3. P2-2: productize virtual portfolio state.
4. P2-3: build aggregate review report.
5. P2-4: decide durable storage needs.

## P2-1 Acceptance Criteria

P2-1 is ready for review when:

- A CLI command can generate a daily P2 rollup from local P1 artifact paths.
- The rollup writes JSON and Markdown artifacts.
- Missing optional artifacts are reported as warnings, not crashes.
- Missing required identity fields fail with actionable errors.
- Tests cover the module and CLI.
- `.venv/bin/pytest -q` passes.

## P2-1 Implementation Status

Status: implemented and ready for review.

Delivered:

- `stock_research.p2.artifact_rollup.build_p2_artifact_rollup`
- `stock_research.p2.artifact_rollup.write_p2_artifact_rollup`
- CLI command:
  - `p2-artifact-rollup`
- Module tests:
  - `tests/test_p2_artifact_rollup.py`
- CLI tests:
  - `tests/test_factor_cli.py -k p2_artifact_rollup`

Verification:

```text
.venv/bin/pytest tests/test_p2_artifact_rollup.py tests/test_factor_cli.py -q -k "p2_artifact_rollup"
5 passed, 118 deselected, 2 warnings

.venv/bin/pytest -q
1161 passed, 2 warnings
```

The warnings are existing dependency deprecation warnings from `py_mini_racer`.

## Safety Rules

- Every P2 artifact must preserve source paths.
- Every generated recommendation must remain review-only.
- Any trading-adjacent output must include manual review status.
- No token, webhook URL, or credential may be written to generated artifacts.
