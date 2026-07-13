# EOD Auto Repair Hardening Design

## Context

The first EOD auto repair implementation added useful checks and a few repair actions, but the 2026-07-01 incident showed it is not yet reliable as an unattended close-repair system.

Observed failures:

- `scripts/run_eod_auto_repair_cron.sh` used `flock`, which is not available in the current macOS host environment, so direct cron execution failed before running repair.
- Platform ready build failed earlier at `ImportError: cannot import name 'run_lhb_cutoff_audit_v1'`, so downstream score, watchlist, strategy, report, and dashboard freshness artifacts were not produced at the normal time.
- Auto repair started later and repaired LHB data, but `strategy_publish` raised `RuntimeError: base data checks did not all pass`.
- That exception escaped the orchestrator, so top-level repair `run_summary.json` and `run_report.md` were not written for the failed repair run.
- The repair registry did not include direct actions for score rebuild, watchlist rebuild, generated reports, or review evidence snapshots.
- Readiness semantics were inconsistent: auto repair treated small daily bar gaps as non-blocking `degraded`, while strategy publish treated every base check not equal to `success` as fatal.
- After manual and later automated work, the same trade date reached `degraded` with no blockers, which proves the platform was repairable but the orchestrator could not drive the chain end to end.

## Goal

Make EOD auto repair a dependency-aware, crash-resistant repair orchestrator that can recover the daily close chain after missing minute bars, missing scores, missing watchlists, missing market monitor data, and interrupted strategy publication, while always leaving an actionable report.

## Non-Goals

- Replace the underlying daily close pipeline, strategy publisher, or market monitor builders.
- Make every optional content source mandatory. Generated reports and research report freshness remain non-blocking unless explicitly promoted later.
- Add a web UI in this phase. The output contract remains JSON, Markdown, logs, and exit codes.
- Hide data quality gaps. `degraded` remains visible when the platform is publishable but imperfect.

## Recommended Approach

Implement v2 as a hardening layer around the current modules:

1. Keep the existing check functions as the source of diagnostics.
2. Add a stage graph that maps checks to repair actions and prerequisites.
3. Run repair stage by stage, rechecking after each stage.
4. Isolate all action exceptions and record them as failed action results.
5. Always write summary and report files, including partial summaries after check or action exceptions.

This is preferable to a large rewrite because the platform already has working builders for daily factors, watchlists, market monitor payloads, strategy publishing, reports, and evidence snapshots. The missing piece is orchestration, not new data generation logic.

## Stages And Dependencies

The repair flow should use these ordered stages:

| Stage | Checks | Repair actions | Continue condition |
|---|---|---|---|
| Base bars | `daily_bars`, `minute5_bars` | repair daily bars when supported, repair minute5 bars with one worker, refresh quality rows | no blocker remains in base bars |
| Features | `technical_features`, `lhb_source`, `lhb_features` | rebuild technical features, refresh LHB source, rebuild LHB event features | no blocker remains in features |
| Scores and watchlists | `score_topn`, `watchlist` | run daily factor score build, rebuild default and diagnostics watchlists | no blocker remains in scores/watchlists |
| Market monitor | `market_monitor` | rebuild market emotion, index/industry coverage where available, sector heatmap/fund-flow proxy | no blocker remains in market monitor |
| Strategy EOD | `strategy_publish`, `review_queue`, `strategy_score_audit` | publish full strategy EOD, write review queue manifest, build score audit | no blocker remains in strategy EOD |
| Presentation | `reports`, `review_evidence_snapshots`, `ops_health`, `dashboard_surface_freshness` | generate reports, evidence snapshots, readiness/platform refresh | dashboard freshness has no blocker |

Each stage writes a stage result with:

- checks before the stage
- actions attempted
- action exceptions, if any
- checks after the stage
- remaining blockers
- next recommended operator command when blocked

## Action Registry

The default action registry should include these action keys:

- `daily_bars`: refresh daily bar quality and, where a safe loader exists, reload missing symbols for the date.
- `minute5_bars`: run Baostock minute backfill for raw and qfq 5-minute bars with `workers=1`, then refresh minute quality.
- `technical_features`: run `build_and_store_stock_technical_features_daily` for the target trade date.
- `lhb_source`: run free enrichment LHB backfill for the target trade date.
- `lhb_features`: run LHB event feature build for the target trade date.
- `score_topn`: run daily factor/score build so `factor.stock_score_daily` has nonzero `manual_v1` rows.
- `watchlist`: rebuild default and diagnostics watchlists after scores exist.
- `market_monitor`: run the market monitor EOD builder and record row counts for emotion, index, industry, sector, and fund-flow inputs.
- `strategy_publish`: run full `publish_strategy_eod` only after prerequisite stages are publishable.
- `review_queue`: alias to full strategy publish when the review manifest is missing.
- `strategy_score_audit`: rebuild audit if missing after strategy publish.
- `reports`: generate or refresh generated reports for the trade date.
- `review_evidence_snapshots`: build review/evidence snapshots after review queue exists.
- `dashboard_surface_freshness`: run final dashboard readiness check and record served/display trade dates.

Actions must be idempotent for the same trade date. Re-running an action may overwrite deterministic outputs or upsert rows, but must not duplicate watchlist or manifest records.

## Readiness Semantics

Use one readiness model across auto repair, strategy publish, platform ready, and dashboard freshness:

- `success`: complete and publishable.
- `degraded`: publishable with explicit warning, such as a small daily bar gap under the configured tolerance.
- `failed` with `blocker=true`: not publishable; downstream stages must not run.
- `failed` with `blocker=false`: publishable optional gap; report and surface it.
- `skipped`: action was intentionally not run because prerequisites were blocked or mode was `check`.

`strategy_publish` should not use an independent all-success gate for base data. It should accept the same publishable base readiness contract used by auto repair. If a prerequisite is `degraded`, the strategy publish manifest should include the warning instead of raising a fatal base-data exception.

## Failure Handling

The orchestrator must not crash on action exceptions.

Required behavior:

- Wrap every action runner in `try/except Exception`.
- Convert exceptions to `RepairActionResult(status=failed, message=<exception type and safe message>)`.
- Continue to the stage recheck if the exception may have partially written artifacts.
- Stop before downstream stages when any current stage blocker remains.
- Always call report writing in a `finally` path.
- Return exit code `2` when blockers remain after repair.
- Return exit code `0` when final status is `success` or `degraded`.
- Return exit code `3` only for explicit unsafe-action blocks, such as minute backfill configured with workers greater than one.

Reports must be written even if checks fail before any action runs. In that case the report should include the check exception as a synthetic failed check named `check_plan`.

## Cron And Locking

The cron wrapper must be portable on the project host.

Replace direct `flock` usage with one of:

- existing `scripts/stock_cron_guard.sh` if it can represent this job and trade date, or
- a Python lock helper using atomic file create and PID validation.

The wrapper should:

- clear proxy environment through the existing cron guard helper when appropriate
- write one log per trade date under `logs/eod_auto_repair`
- print summary/report paths even on failure
- preserve the orchestrator exit code
- never depend on tools absent from macOS base install

## Operator Output

`run_summary.json` should include:

- `trade_date`
- `mode`
- `final_status`
- `stages`
- `checks_before`
- `actions`
- `checks_after`
- `remaining_blockers`
- `remaining_non_blockers`
- `next_actions`

`run_report.md` should be a human-first incident report:

- final status in the first screen
- timeline of stages
- table of blockers before and after
- action results with artifact paths
- exception summaries
- specific manual commands for unresolved blockers

The report should answer: "What did auto repair do, what did it fix, what is still broken, and what should I run next?"

## Incident Acceptance Criteria

The 2026-07-01 pattern is the regression suite:

- When direct cron runs on macOS, it must not fail because `flock` is missing.
- When platform ready build stops before score/watchlist generation, auto repair must rebuild `score_topn` and `watchlist` before attempting strategy publish.
- When minute5 is missing, auto repair must run single-worker minute backfill, refresh quality, and continue to downstream stages if the recheck passes.
- When strategy publish raises, auto repair must write summary/report files and record the exception.
- When daily bars are `degraded` within tolerance, strategy publish must treat them as publishable and carry the warning.
- When generated reports are missing but non-blocking, final status may be `degraded` and dashboard freshness must still pass if all blocking surfaces are current.

## Testing Strategy

Add tests at three levels:

- Unit tests for stage ordering, prerequisite gating, final status aggregation, and exception-to-action-result conversion.
- Action tests using injected runners for minute5, score, watchlist, market monitor, strategy publish, reports, and snapshots.
- Script tests proving the cron wrapper does not require `flock` and preserves the orchestrator exit code.

The key end-to-end test should simulate:

1. minute5 failed
2. score and watchlist missing
3. strategy publish initially skipped because prerequisites are blocked
4. minute5 repair succeeds
5. score and watchlist repair succeed
6. strategy publish succeeds
7. generated reports remain non-blocking
8. final status is `degraded`, not `failed`

## Rollout

Roll out in small commits:

1. portable cron lock and always-write reports
2. action exception isolation
3. stage graph and prerequisite gating
4. score/watchlist/report/snapshot actions
5. shared readiness semantics between strategy publish and auto repair
6. operator report improvements

After rollout, run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair.py tests/test_eod_auto_repair_actions.py tests/test_eod_auto_repair_checks.py tests/test_eod_auto_repair_scripts.py -q
rtk .venv/bin/python -m stock_research.eod_auto_repair --trade-date 2026-07-01 --output-dir /private/tmp/eod_auto_repair_20260701_check --mode check
```

The second command should finish with exit code `0` when the date is currently publishable or degraded-ready.
