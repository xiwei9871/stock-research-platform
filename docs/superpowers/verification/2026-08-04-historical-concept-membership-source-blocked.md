# Historical concept-membership P0 source check — 2026-08-04

## Status

`Archived strict-PIT check / non-blocking under the operational latest-snapshot policy`.

No database write was performed in this strict-source check. The report
remains valid for users who require vendor-verified 2026-07-31 stock-level
attribution, but that requirement is no longer a blocker for the operational
sector-first P2 workflow. That workflow uses the 2026-07-09 snapshot as the
historical proxy and the 2026-08-04 snapshot as the latest snapshot.

The reproducible inventory for this check is
`/tmp/historical_membership_inventory_20260731.json` (SHA-256
`a273daae80728b87ff518ebd140886393c6b4a74e6a1a5b03d1c43653617073a`). It
records the database grouping, local-file search, provider probe counts, and
the zero-write decision.

## Target universe

- Target file: `/Users/xiwei/stock_research/outputs/research/concept_drawdown_over24_2026-08-01.csv`
- SHA-256: `ea206864f86dabf6339c16240f9d4b15ef28ea29954d0cce2d7cf962ac5d5cc5`
- Target concepts: 302 unique `ths` codes

## Database evidence before import

The database currently has 192 target concepts with an active, eligible
membership interval at 2026-07-31 and 110 without one. There are zero target
membership rows whose `start_date` is 2026-07-31. This is intentional: the
previous unverified current-member write was rolled back.

The 192 rows are sourced from the 2026-07-09 THS current-page capture. That
capture has no proof that the membership was observed or effective on
2026-07-31, so it is not accepted as a PIT snapshot.

## Provider checks

### THS BackTest `historypick`

Endpoint:
`https://backtest.10jqka.com.cn/tradebacktest/historypick`

Request boundary: `query=概念:<concept_name>`, `hold_num=5000`,
`trade_date=20260731`.

- The endpoint returns an explicit result date for the historical request.
- 290 of the 302 target names return a non-empty result with result date
  `2026-07-31`.
- 12 targets cannot be used as a complete snapshot source:

  `309182 小红书概念`, `308697 注册制次新股`, `309058 ERP概念`,
  `308467 柔性屏(折叠屏)`, `308885 家庭医生`, `301669 供销社`,
  `301292 染料`, `308537 动物疫苗`, `301402 上海国企改革`,
  `301455 摘帽`, `301171 深圳国企改革`, `300316 燃料电池`.

  Ten return a dated empty result; two return a request error. Empty/error
  responses cannot be interpreted as an exact historical membership set,
  because the same concepts have non-empty current THS member pages.

### THS web/AkShare and EastMoney

The accessible THS and AkShare constituent pages expose current pagination
only. Adding `date`, `trade_date`, `start_date`, or equivalent parameters does
not change the returned member set. EastMoney's available constituent API is
also current-only in this environment. Neither source declares an effective
date for a historical membership response.

The exact-name provider probe is therefore not silently widened with aliases:
`折叠屏`, `上海国企`, and `深圳国企` return broader/different result sets and
are retained only as rejected evidence, not substituted for the target codes.

### Other sources

- Tushare `ths_member` is unavailable for the configured token (permission
  error).
- iWenCai historical/query endpoints require an authenticated session or
  return an empty/forbidden response.
- No local serialized PIT membership file with an explicit date and complete
  302-code coverage was found.

## Strict-PIT acceptance consequence (optional attribution path)

The import contract requires all 302 target concepts, a uniform explicit
`source_asof`/`source_effective_date` no later than 2026-07-31, and non-empty
eligible member coverage. The available evidence satisfies neither the
complete-source nor the complete-coverage requirement. Therefore:

- no `core.concept_board` or `core.concept_membership` rows were written;
- no SCD2 intervals were closed;
- no 2026-07-31 replay is claimed as complete;
- the strict-PIT attribution path remains open until a dated snapshot export
  or an authorized provider endpoint is supplied.

## Optional strict-PIT unblock

Provide a CSV/JSON/Parquet snapshot containing
`concept_code`, `concept_name`, `asset_id`, and one uniform
`source_asof`/`source_effective_date` at or before 2026-07-31. The implemented
loader will then validate it, run a dry-run, import transactionally, verify
the 302-code/BSE/master/SCD2 invariants, and replay the frozen date.
