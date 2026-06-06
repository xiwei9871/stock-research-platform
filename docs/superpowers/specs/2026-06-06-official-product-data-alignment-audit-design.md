# official-product Data Alignment Audit Design

## Purpose

`official-product-data-alignment-audit` explains why official product revenue evidence is or is not point-in-time usable for each `tech-bottleneck-discovery` candidate row.

The official disclosure backfill now works end to end, but the 2025-01 to 2025-05 pilot still has:

```text
candidate_rows = 1100
candidate_assets = 647
manifest_rows = 1055
main_business_rows = 13303
product_main_business_rows = 6308
joinable_product_report_periods = 158
evidence_rows = 1480
safe_evidence_rows = 0
has_product_revenue_exposure = 0/1100
```

The immediate question is no longer whether the source pipeline can fetch official disclosures. It can. The question is whether the candidate dates, disclosure publish dates, product report periods, and local product rows are aligned enough to run a fair tech bottleneck test.

## Scope

Version 1 is candidate-scoped and artifact-based.

Inputs:

- candidate CSV, usually `outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/candidates.csv`
- official backfill output directory containing:
  - `disclosure_manifest.csv`
  - `product_join_diagnostics.csv`
  - `product_evidence.csv`
  - `source_gap_report.csv`
- optional readiness CSV for before/after comparison

Outputs:

- `alignment_audit.csv`: one row per candidate with the best available product/disclosure alignment status.
- `alignment_audit.json`: structured per-candidate details for debugging.
- `alignment_summary.md`: human-readable counts and recommended next action.
- `alignment_status_summary.csv`: counts by status, candidate month, and report period.

It does not:

- fetch new disclosures
- parse PDFs
- create new product evidence
- score candidates
- run returns
- override strict PIT rules

## Candidate-Time Contract

Each candidate row is normalized to:

```text
asset_id
ts_code
stock_name
candidate_trade_date
as_of_date
```

If the input has only `trade_date`, that becomes both `candidate_trade_date` and `as_of_date`.

All alignment decisions are made from the candidate row's `as_of_date`.

## Alignment Statuses

Each candidate row receives exactly one primary `alignment_status`.

Statuses are ordered from most actionable to least actionable:

1. `pit_safe_product_evidence_available`
   - A product evidence row exists for the same candidate row.
   - `as_of_safe = true`.
   - This candidate can set `has_product_revenue_exposure`.

2. `joinable_but_future_disclosure`
   - Product evidence exists or a manifest/product join is possible.
   - The disclosure `publish_date` is after the candidate `as_of_date`.
   - This means the data may become usable for later candidate windows, but not this one.

3. `joinable_but_report_period_future`
   - Product rows and official manifest can join.
   - The report period itself is after the candidate `as_of_date`.
   - This is future financial-period leakage and must stay blocked.

4. `manifest_available_no_joinable_product_period`
   - Official disclosure manifest exists for the asset.
   - Local product rows exist somewhere in the product table.
   - No matching `asset_id + ts_code + report_period` product rows exist for the relevant manifest rows.

5. `manifest_available_no_product_rows`
   - Official disclosure manifest exists for the asset.
   - No product-classified main-business rows exist for the asset in the backfill window.

6. `product_rows_available_no_official_manifest`
   - Product rows exist.
   - No supported annual/semiannual official disclosure manifest exists for the asset in the queried window.

7. `no_official_manifest_or_product_rows`
   - Neither supported official manifest nor product rows exist for the asset.

8. `manifest_query_error`
   - The official source query failed for the asset.
   - This must be separated from genuine no-data.

## Per-Candidate Fields

`alignment_audit.csv` columns:

```text
run_id
asset_id
ts_code
stock_name
candidate_trade_date
as_of_date
alignment_status
alignment_reason
has_pit_safe_product_evidence
safe_product_evidence_count
unsafe_product_evidence_count
best_report_period
best_publish_date
best_disclosure_type
best_source_document_id
best_source_document_url
best_source_title
best_product_main_business_rows
best_manifest_rows
manifest_rows_for_asset
product_main_business_rows_for_asset
joinable_report_periods_for_asset
manifest_query_error_count_for_asset
max_safe_report_period
min_future_publish_date
days_until_first_future_disclosure
recommended_action
```

`recommended_action` is deterministic:

- `use_for_readiness` for `pit_safe_product_evidence_available`
- `shift_test_window_later` for `joinable_but_future_disclosure`
- `ignore_future_period` for `joinable_but_report_period_future`
- `backfill_historical_product_rows` for `manifest_available_no_joinable_product_period`
- `backfill_product_table_source` for `manifest_available_no_product_rows`
- `extend_or_fix_manifest_source` for `product_rows_available_no_official_manifest`
- `investigate_source_coverage` for `no_official_manifest_or_product_rows`
- `rerun_manifest_source` for `manifest_query_error`

## Selection Rules

The audit picks the best product/disclosure explanation per candidate row:

1. Prefer candidate-scoped safe product evidence.
2. Else prefer unsafe product evidence tied to the same candidate row, because it directly explains PIT failure.
3. Else inspect join diagnostics for the asset and choose the report period closest to but not after `as_of_date`.
4. Else inspect future joinable report periods and compute `days_until_first_future_disclosure`.
5. Else fall back to asset-level manifest/product coverage.
6. Else use manifest query errors when present.

The audit must not mark a candidate safe based on asset-level evidence alone. Safe status requires candidate-row alignment on:

```text
asset_id
candidate_trade_date
as_of_date
as_of_safe = true
```

## Summary Rules

`alignment_status_summary.csv` includes:

```text
run_id
group
group_value
candidate_rows
candidate_assets
pit_safe_rows
future_disclosure_rows
missing_product_period_rows
manifest_query_error_rows
```

Groups:

- `overall`
- `candidate_month`
- `alignment_status`
- `recommended_action`

`alignment_summary.md` includes:

- overall row count and asset count
- status counts
- recommended action counts
- earliest month where future disclosures become usable
- whether the next experiment should:
  - backfill historical product rows first
  - move candidate window later
  - fix official manifest source
  - proceed to readiness scoring

## Current Pilot Interpretation

For the current 2025-01 to 2025-05 pilot, the expected result is:

- many rows should be `joinable_but_future_disclosure`
- some rows may be `manifest_available_no_joinable_product_period`
- `pit_safe_product_evidence_available` should remain zero unless historical product rows and matching safe disclosures are found

If the audit confirms that all joinable product evidence is from disclosures after 2025-05-26, the next experiment should shift the candidate window to after 2025-08 instead of testing returns on the current window.

If the audit finds many 2023/2024 official disclosures but no matching product rows, the next data task should backfill historical `finance.main_business_composition` for 2022-2024 report periods.

## Testing

Unit tests cover:

- safe evidence produces `pit_safe_product_evidence_available`
- unsafe evidence after `as_of_date` produces `joinable_but_future_disclosure`
- future report period produces `joinable_but_report_period_future`
- manifest with no product rows produces `manifest_available_no_product_rows`
- product rows without manifest produces `product_rows_available_no_official_manifest`
- source errors produce `manifest_query_error`
- real pilot-shaped candidate CSV with only `trade_date` is normalized correctly

Integration test:

- run the audit against the existing official product backfill artifacts
- verify outputs are written
- verify no row is marked PIT-safe unless evidence has `as_of_safe = true`

## Acceptance Criteria

- The audit produces one row per candidate.
- Every row has one non-empty `alignment_status`.
- Safe rows are candidate-scoped and strict PIT-safe.
- Source failures are distinguishable from genuine no-data.
- The summary recommends either data backfill, later-window testing, source repair, or readiness scoring based only on artifact evidence.
