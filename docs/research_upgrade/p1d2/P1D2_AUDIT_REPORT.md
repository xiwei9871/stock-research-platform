# DATA-R3-P1d.2 Audit Report — Consumer Gate & Final Safety Validation

Baseline: `7fe99ee8` (`fix/p1d1-historical-tradeability-gate`)
Branch: `fix/p1d2-backtest-consumer-gate`

## What P1d.1 found vs what P1d.2 fixed

| P1d.1 Gate-2 degrade cause | P1d.2 resolution |
|---|---|
| `vectorized_topn` loader crashed (`UndefinedColumn`) | status join + `limit_state_missing` (Gate-2 PASS) |
| retention/backtest limit gate silently inert | flags now flow from `core.asset_status_daily`; `use_status_flags` corrected path added (PASS) |
| `false AS is_limit_*` in 5 loaders | all joined to status table (PASS) |
| no per-case DB assertions | `p1d2_db_assertions.py`: 16/16 explicit `expected/actual/pass` checks, nonzero exit on failure (PASS) |
| mislabel count mixed segment overlap | dedup by (asset,date,side): 162,119 → 161,200 unique, **62,937 unique mislabels** (FP 19,198 / FN 43,739), 0 conflicts (PASS) |

## A1 — minute source qualification

Unified (asset, date, source, version) qualification; required-source
absence returns `required_source_missing`; 59 alt-covered gaps qualify with
audit marker `factor_gap_covered_by_alt_source` (gap info preserved);
15 no-done-key assets and 600153 fail closed. Detail: MINUTE_SOURCE_QUALIFICATION.md.

## A2 — deduplicated mislabel census

`scripts/p1d2_dedup.py` + LIMIT_MISLABEL_DEDUP_REPORT.md/JSON:
162,119 scanned rows → 161,200 unique keys, 919 duplicate rows, 911 keys in
multiple segments, **0 conflicting classifications**. The 162k figure is a
targeted scan of rule-divergence segments, not a census of all 17.29M
status rows. Unique confirmed mislabels: **62,937** (revises the P1d.1
63,821 figure — overlap was all on the FP side; FN 43,739 unchanged).

## A3 — trade-time PIT

Open-tier decisions no longer consume high/low/close; results carry
`information_tier` + `ex_post_execution_assumption` so conservative fill
models are labeled, never mistaken for PIT knowledge. Detail: TRADE_TIME_PIT_AUDIT.md.

## A4 — DB edge assertions

`scripts/p1d2_db_assertions.py`: 16 cases × per-field
expected/actual/pass; exits nonzero on any mismatch. Current: **16/16
pass** → DB_EDGE_ASSERTIONS.json.

## B — consumer chain

All loaders now supply real flags + explicit missing marker;
`block_missing_limit_state` constraint added (default off = legacy parity,
on = fail-closed). Detail: BACKTEST_CONSUMER_FIX_REPORT.md.

## C — rule consistency

`dragon_case_library._is_limit_up` rewritten onto the shared rule engine
(board/date/status aware, `limit_rule_id`/`limit_day_verified` output);
`market_emotion_state_v1` flagged NEEDS_REVALIDATION (consumes stored
flags); Beijing-ST stays `rule_unknown`; zero COALESCE-flag fallbacks exist.

## D — shadow matrix

See BACKTEST_SHADOW_MATRIX.csv / BACKTEST_SHADOW_REPORT.md. Windows without
score coverage keep NEEDS_REVALIDATION with decision-diff evidence
(REGIME_WINDOW_DECISION_AUDIT.csv).

## E — migration readiness

STORAGE_MIGRATION_READINESS.md: v2-column design, explicit state machine
(no COALESCE), batch/rollback plan, cost estimate. Not executed.

## Gate summary

| Gate | Status |
|---|---|
| 1 data & rules | PASS |
| 2 consumers | PASS |
| 3 shadow | PASS (all diffs rule-attributed, zero rule_unknown pass-through) |
| 4 migration readiness | PASS (design+isolated tests; production untouched) |

Overall: **READY_FOR_DEPLOYMENT_REVIEW** — not PRODUCTION_READY; awaiting
human authorization before any production switch.
