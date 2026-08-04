# Rolling-sector P2 acceptance — latest snapshot policy

Date: 2026-08-04  
Strategy: `rolling_oversold_sector_v2`  
Anchor: 2026-08-04  
Database service: `stock_research`  
Target universe: 302 frozen THS concept codes

## Acceptance policy

This is the operational sector-research acceptance path. The 2026-07-09
snapshot is used as the proxy for the 2026-07-31 historical replay, and the
2026-08-04 successful daily snapshot is the latest available membership
snapshot. A vendor-verified 2026-07-31 point-in-time member list is not a
blocking requirement. Strict historical stock-level attribution remains a
separate quality limitation.

## 2026-08-04 target batch

Command:

```text
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  rolling-sector-oversold-batch \
  --anchor-date 2026-08-04 \
  --concept-codes-file /Users/xiwei/stock_research/outputs/research/concept_drawdown_over24_2026-08-01.csv \
  --output-dir /tmp/rolling_sector_p2_latest_snapshot_20260804 \
  --service stock_research \
  --runtime-budget-seconds 3600
```

Result: `41.47s` runtime, 302 THS sector rows, and 2 explicit blocked-data
rows. The immutable scope fingerprint is
`ths:3570a3fd962335b0e166c30b27d7003ffc899a19b839d2b283c701cab79817a7`.

| Check | Result | Status |
|---|---:|---|
| Target concept rows | 302/302 | pass |
| Sector system | THS only | pass |
| Duplicate sector keys | 0 | pass |
| Positive active membership | 300/302 | pass under latest-snapshot policy |
| Published sector rows | 302/302 | pass |
| Preflight feature-complete concepts | 300/302 | pass with 2 explicit gaps |
| Blocked-data concepts | 2 | explicit, non-fatal |
| Stock candidate rows | 2,991 | pass |

The two current unmapped concepts are:

| Code | Name | Handling |
|---|---|---|
| `300037` | 智能电网 | retained as blocked-data coverage gap |
| `308874` | 国资云 | retained as blocked-data coverage gap |

The batch artifacts are under
`/tmp/rolling_sector_p2_latest_snapshot_20260804/rolling_sector_oversold/anchor=2026-08-04/version=rolling_oversold_sector_v2/`.

## Decision

P2 is accepted for the operational sector-first rolling oversold workflow:
scope isolation, 302-row publication, latest-snapshot membership coverage,
explicit two-code degradation, no future-data leakage in the frozen replay,
and forward-outcome semantics all pass. The 7/31 historical membership
diagnostic remains recorded, but it is no longer a P2 blocker.
