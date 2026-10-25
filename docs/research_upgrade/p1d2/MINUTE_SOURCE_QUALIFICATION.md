# P1d.2 A1 — Minute Source Qualification

## Rules implemented (all in `src/stock_research/tradeability.py`)

| Asset class | Rule | Result |
|---|---|---|
| 59 baostock-gap assets covered by an alternate source | qualify ONLY via the completed source+version key | `data_ready_minute=True` + audit reason `factor_gap_covered_by_alt_source` |
| 15 assets with no done key | never qualified by raw minute row counts | `data_ready_minute=False`, reason `factor_gap_residual` |
| CN:SH:600153 (post-diff isolated) | stays isolated regardless of keys | `minute_version=post_diff_isolated`, fail-closed |
| Alternate-source coverage | must not erase the baostock gap from audit output | gap block preserved in `restriction_reasons` |
| Asset-level "complete" | does not replace date/key-level readiness | verdicts stay per (asset, date, source, version) |

## Provider fixes

- `LedgerMinuteQualificationProvider.verdict()`: a `required_source` request that is absent from the ledger now returns `required_source_missing` instead of falling through to `factor_gap_residual`.
- Legacy list-format ledgers are still parsed (asset-set form tolerated).
- When a provider is configured, a `None` verdict no longer falls back to
  `minute_bar_rows > 0` — absence of a verdict is fail-closed.
- The factor-gap block is applied explicitly when minute state is UNKNOWN so
  `data_ready_minute` cannot silently stay True.

## Verified set relationships (real ledgers, 2026-10-20 snapshot)

- 2,308 R2 COMPLETE (daily/technical-factor set)
- 2,293 minute-qualified keys
- 74 terminal baostock factor gaps: 59 covered by alternate source, 15 with no done key
- 600153: isolated

## Evidence

- `tests/test_tradeability_p1d2.py` — 8 real-ledger adversarial cases + 10
  pure-Python cases, all passing.
- `DB_EDGE_ASSERTIONS.json` case `factor_gap_residual` (CN:SH:603213,
  akshare-covered gap asset): asserts qualified=True with the audit marker
  preserved — the asset whose P1d-era expectation (`False`) was corrected
  after round-2 rebuild added its akshare key.
- `DB_EDGE_ASSERTIONS.json` case `no_done_key_blocked` (CN:SH:600590):
  asserts `data_ready_minute=False` + `factor_gap_residual` reason.
