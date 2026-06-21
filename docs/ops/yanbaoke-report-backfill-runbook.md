# Yanbaoke Report Backfill Runbook

## Purpose

Generate a quota-aware Yanbaoke candidate inventory and pilot queue for reports dated `2025-01-01` through `2026-06-12`.

## Inputs

- `inputs/yanbaoke_candidates.csv`: exported Yanbaoke metadata, one row per candidate report.
- `inputs/existing_report_coverage.csv`: existing internal coverage metadata.

Minimum candidate columns:

- `report_id`
- `report_date`
- `title`
- `broker`
- `stock_code`
- `stock_name`
- `industry_lv1`
- `industry_lv2`
- `theme`

## First Run

```bash
./.venv/bin/stock-research yanbaoke-report-backfill-plan \
  --candidate-path inputs/yanbaoke_candidates.csv \
  --existing-coverage-path inputs/existing_report_coverage.csv \
  --start-date 2025-01-01 \
  --end-date 2026-06-12 \
  --output-dir outputs/research/yanbaoke_backfill_20250101_20260612
```

## Outputs

- `yanbaoke_candidate_reports.csv`: normalized scored candidates.
- `existing_report_coverage.csv`: normalized existing coverage snapshot used for scoring.
- `yanbaoke_gap_matrix.csv`: month/broker/industry/asset/report-type/source-status gap matrix.
- `yanbaoke_sector_gap_matrix.csv`: board and theme coverage matrix.
- `yanbaoke_asset_gap_matrix.csv`: stock-level gap matrix.
- `yanbaoke_priority_queue.csv`: full sorted queue.
- `yanbaoke_pilot_queue_top3000.csv`: first pilot download/import queue.
- `yanbaoke_backfill_inventory_report.md`: human review report.

## Review Gates

Before any large download:

- Confirm P0/P1 sectors dominate the pilot queue.
- Confirm Priority 3 reports are not more than 20% of the pilot queue.
- Confirm duplicate candidates are excluded from the pilot queue.
- Confirm unknown or misclassified sectors are reviewed from the sector gap matrix.

## Next Step After Review

Use `yanbaoke_pilot_queue_top3000.csv` as the approved input for the first controlled download/import batch. Recompute this plan after every 1,000 imported reports using refreshed existing coverage.
