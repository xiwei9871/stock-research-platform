# 02 — Historical Universe PIT / Survivorship Audit (M0.6, task E)

Date: 2026-10-20. Branch: `audit/tech-strategy-m0-20261019` @ `1149c763`.
Subject: frozen formal pool `strict_153_st_only_financial_state` (148 unique `asset_id`)
and the reproduced replay ending at equity `1.6562725546299535` (+65.63%).

## Verdict: BIAS CONFIRMED — the +65.63% must NOT be cited as verified strategy alpha

Two distinct questions were separated as instructed:

| Question | Answer |
|---|---|
| Is *scoring* on the existing pool PIT-clean? | **Yes at field level.** 23,952 daily snapshot rows: 0 rows where `trade_date < first_hit_date`; `candidate/financial/technical_as_of_date ≤ trade_date` on every row. |
| Was the *pool itself* rebuilt from a historical full-market scan? | **No.** It is a static hindsight-selected universe — see evidence below. |

## Evidence

1. **Membership needs 2025–2026 knowledge; trading pretends none.**
   Every member's `first_hit_date` ∈ [2025-01-03, 2026-06-05]; `analysis_start/end` =
   2025-01-01→2026-06-05 for all 148 rows. Knowability: **0/148 by 2023-12-31, 0/148 by
   2024-12-31, 14/148 by 2025-06-30, 83/148 by 2025-12-31** — the remaining 65 members were
   only identifiable during 2026.

2. **The replay's actual trading window is 2026-01-05 → 2026-10-19, not 2023.**
   Reproduced backtest: first equity row 2026-01-01, first trade 2026-01-05, 72 trades,
   189 equity rows, first position non-zero 2026-01-05. The "2023-01-03" in artifact names
   is the *regime-input* window. **The entire +65.63% accrues over ~9.5 months in 2026** —
   on a pool whose members were, by construction, names that generated bottleneck-keyword
   hits and survived through mid-2026.

3. **Survivorship is structural.** All 148 have `period_last_date = 2026-06-05` with live
   prices; any stock that hit the scan then died/suspended before that date is absent by
   construction. The 5 exclusions (`st_or_delisting_risk_name`) were judged on ~2026 status
   — correct for today's pool, but it demonstrates the membership audit used
   window-end information.

4. **`candidate_source_mode = legacy_static_seed_daily_pit`** — the pipeline itself labels
   this a legacy static seed replayed under daily-PIT *field* rules; it never claimed
   universe-level PIT.

5. What remains clean: entry gating (65 members enter exactly on `first_hit_date`; the 83
   "delayed" are window-start truncations, not violations), field as-of discipline, and the
   equity endpoint reproducibility (sha-verified, `1.6562725546299535`).

## Impact statement

The replay validates **pipeline mechanics** (order execution, exposure overlay, PIT field
gating, cost model). It does **not** validate alpha: the held universe was selected with
information that could not exist at trade time, in a window where every member was already
a hindsight survivor. Statements of the form "+65.63% since 2023" are additionally wrong in
span — it is +65.63% over 2026-01→2026-10.

## What a real validation needs (M2 precondition — designed, not executed)

Rebuild the universe PIT-faithfully: at each historical rebalance date, run the hit scan +
financial filter over **all stocks alive at that date** (including later-delisted names),
with no reference to the frozen 148. Requires: (a) historical hit-event source coverage
back to ≥2023 with `available_at` discipline; (b) a delisting-complete security master —
status: **not yet verified available**; (c) re-run replay on that universe; only then may
returns be called alpha. Until then: label all baseline numbers
`mechanical_validation_only`.

## Distinction preserved (per task wording)

- "PIT score on existing pool" = implemented and clean — keep using it for mechanics.
- "Independently rebuilt historical universe" = **missing** — the blocking gap for M2
  efficacy claims.
