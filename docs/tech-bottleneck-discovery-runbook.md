# tech-bottleneck-discovery Runbook

`tech-bottleneck-discovery` is an automated research lens for hard-technology chokepoint candidates. The system generates research packets; humans review the generated evidence and record approve, reject, or needs-more-evidence.

## Evidence Backfill

Run this when readiness shows data gaps. It builds candidate-scoped evidence artifacts without changing the candidate pool.

```bash
stock-research tech-bottleneck-evidence-backfill \
  --candidates-csv outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/candidates.csv \
  --output-dir outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/evidence \
  --run-id pilot-top50-2025-evidence \
  --start-date 2025-01-01 \
  --lookback-days 365 \
  --service stock_research
```

Then rerun readiness with:

```bash
stock-research tech-bottleneck-data-readiness-audit \
  --candidates-csv outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/candidates.csv \
  --evidence-csv outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/evidence/evidence.csv \
  --output-dir outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/readiness_after_backfill \
  --run-id pilot-top50-2025-readiness-after-backfill \
  --lookback-days 365 \
  --service stock_research
```

## Official Product Revenue Backfill

Run this when readiness shows product revenue exposure gaps and official disclosure product rows are needed for an existing candidate pool.

```bash
stock-research tech-bottleneck-official-disclosure-product-backfill \
  --candidates-csv outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/candidates.csv \
  --output-dir outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_backfill \
  --run-id pilot-top50-2025-official-product-backfill \
  --start-date 2025-01-01 \
  --end-date 2025-12-31 \
  --service stock_research
```

Use `--no-db` when the PostgreSQL service is unavailable and you still need CNINFO manifest, query error, source gap, and coverage artifacts. In that mode, product revenue rows are empty unless injected by a caller outside the CLI.

Then run the official product data alignment audit below. Do not feed `product_evidence.csv` into readiness until the alignment audit confirms PIT-safe product evidence is available for the intended window.

Artifacts:

- `product_evidence.csv`
- `disclosure_manifest.csv`
- `manifest_query_errors.csv`
- `product_join_diagnostics.csv`
- `source_gap_report.csv`
- `coverage_summary.md`

PIT rule: product rows are safe only when `publish_date <= as_of_date` and `report_period <= as_of_date`.

## Official Product Data Alignment Audit

Run this after official product revenue backfill and before readiness or return testing. It decides whether official product evidence is aligned to the candidate as-of dates, or whether the test window/source backfill needs more work first.

```bash
stock-research tech-bottleneck-official-product-data-alignment-audit \
  --candidates-csv outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/candidates.csv \
  --official-product-backfill-dir outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_backfill \
  --output-dir outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_alignment_audit \
  --run-id pilot-top50-2025-official-product-alignment-audit
```

Outputs:

- `alignment_audit.csv`: one row per candidate with PIT alignment status and recommended action.
- `alignment_audit.json`: structured copy of the audit rows.
- `alignment_status_summary.csv`: overall, month, status, and action counts.
- `alignment_summary.md`: operator-readable status counts, reasons, and next-action guidance.

Do not run return tests from a window where `pit_safe_product_evidence_available` is zero and the dominant action is `shift_test_window_later` or `backfill_historical_product_rows`. Use this audit to decide data alignment before readiness/return testing.

Only after the alignment audit shows usable PIT-safe product evidence for the intended window, rerun readiness with the generated product evidence:

```bash
stock-research tech-bottleneck-data-readiness-audit \
  --candidates-csv outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/candidates.csv \
  --evidence-csv outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_backfill/product_evidence.csv \
  --output-dir outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/readiness_after_official_product_backfill \
  --run-id pilot-top50-2025-readiness-after-official-product-backfill \
  --lookback-days 365 \
  --service stock_research
```

## Data Readiness Audit

Run this before generating research packets. It checks whether an existing topN candidate pool has enough industry, product, report, bottleneck, capacity, customer, technical-barrier, catalyst, and invalidation evidence.

```bash
stock-research tech-bottleneck-data-readiness-audit \
  --candidates-csv data/manual/tech_bottleneck_readiness_candidates_example.csv \
  --output-dir outputs/tech_bottleneck_discovery/readiness_example \
  --run-id tech-bottleneck-readiness-example \
  --lookback-days 365 \
  --service stock_research
```

Outputs:

- `readiness.csv`: one row per candidate with boolean coverage flags.
- `readiness.json`: structured evidence counts and snippets.
- `summary.md`: pool-level coverage gaps and status counts.

Only candidates with `coverage_status=ready_for_scoring` should move into `tech-bottleneck-discovery` packet generation.

## Inputs

- Candidate CSV: one row per existing candidate with trend, chokepoint, underpricing, and risk score dimensions.
- Evidence CSV: one row per cited evidence item with tier, source, date, claim, and support text.

## Command

```bash
stock-research tech-bottleneck-discovery \
  --candidates-csv data/manual/tech_bottleneck_candidates_example.csv \
  --evidence-csv data/manual/tech_bottleneck_evidence_example.csv \
  --output-dir outputs/tech_bottleneck_discovery/example \
  --run-id tech-bottleneck-example
```

## Outputs

- `packets.json`: structured packet list.
- `packets.csv`: spreadsheet-friendly packet summary.
- `<asset_id>.md`: one markdown research packet per candidate.
- `summary.md`: run summary for review.

## Review Boundary

The command does not produce trading instructions, broker actions, or production watchlist promotion. Reviewers inspect the generated packet and record the review decision separately.

## Historical Re-Score Experiment

Use this after packet generation to evaluate scored candidates against future bars. The 20D and 60D horizons are diagnostics only. The main validation horizons are 120D and 250D; 500D is a long-cycle observation horizon.

```bash
stock-research tech-bottleneck-historical-rescore \
  --packets-csv outputs/tech_bottleneck_discovery/example/packets.csv \
  --bars-csv data/manual/tech_bottleneck_bars_example.csv \
  --output-dir outputs/tech_bottleneck_discovery/historical_rescore_example \
  --run-id tech-bottleneck-historical-example \
  --horizons 1,2,4,5
```

Outputs:

- `outcomes.csv`
- `bucket_summary.csv`
- `summary.md`
