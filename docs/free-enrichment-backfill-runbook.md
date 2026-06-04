# Free Enrichment Backfill Runbook

Date: 2026-06-04

This runbook covers the free AkShare enrichment backfill command:

```bash
./.venv/bin/python -m stock_research.cli free-enrichment-backfill \
  --dataset DATASET \
  --start-date YYYY-MM-DD \
  --end-date YYYY-MM-DD \
  --output-dir outputs/research/free_enrichment_RUN \
  --batch-size 100 \
  --sleep-seconds 1
```

Supported datasets are `all`, `lhb`, `holder`, `repurchase`, `survey`, `forecast`, `express`, and `mainbiz`.

## Smoke Checks

Use small dry-runs before a live run:

```bash
./.venv/bin/python -m stock_research.cli free-enrichment-backfill \
  --dataset forecast \
  --start-date 2025-01-01 \
  --end-date 2025-03-31 \
  --output-dir outputs/research/free_enrichment_smoke/forecast \
  --batch-size 1 \
  --sleep-seconds 0 \
  --limit 1 \
  --dry-run
```

Validated dry-runs on 2026-06-04:

| Dataset | Window | Result |
| --- | --- | --- |
| forecast | 2025-01-01 to 2025-03-31 | 715 fetched, 715 normalized, 0 failures |
| express | 2025-01-01 to 2025-03-31 | 66 fetched, 66 normalized, 0 failures |
| mainbiz | 2025-01-01 to 2025-12-31, `--limit 1` | 200 fetched, 36 normalized, 0 failures |
| survey | 2026-06-03 to 2026-06-04 | 341 fetched, 341 normalized, 0 failures |

Do not use `--dataset all --start-date 2025-01-01` as a quick smoke. Even with `--limit 1`, the holder dataset still includes the full `stock_ggcg_em(symbol=全部)` feed, and survey from 2025-01-01 had 9152 AkShare pages in the smoke attempt.

## Operational Split

Run lightweight datasets first:

```bash
for dataset in forecast express repurchase mainbiz; do
  ./.venv/bin/python -m stock_research.cli free-enrichment-backfill \
    --dataset "$dataset" \
    --start-date 2025-01-01 \
    --end-date 2026-06-04 \
    --output-dir "outputs/research/free_enrichment_${dataset}_20260604" \
    --batch-size 20 \
    --sleep-seconds 1
done
```

Run heavy datasets separately:

```bash
./.venv/bin/python -m stock_research.cli free-enrichment-backfill \
  --dataset holder \
  --start-date 2025-01-01 \
  --end-date 2026-06-04 \
  --output-dir outputs/research/free_enrichment_holder_20260604 \
  --batch-size 20 \
  --sleep-seconds 1
```

```bash
./.venv/bin/python -m stock_research.cli free-enrichment-backfill \
  --dataset survey \
  --start-date 2025-01-01 \
  --end-date 2026-06-04 \
  --output-dir outputs/research/free_enrichment_survey_20260604 \
  --batch-size 1 \
  --sleep-seconds 1
```

## Reading Results

Each run writes:

- `run_summary.json`
- `dataset_coverage.csv`
- `dataset_failures.csv`

The progress line is:

```text
free_enrichment_batch|dataset=...|status=...|fetched=...|normalized=...|upserted=...|failed=...
```

For `holder`, `batch_controls_applied=partial` is expected because the per-stock holder requests are batched, but the shareholder-trade feed uses `stock_ggcg_em(symbol=全部)` as an uncontrolled full-feed request.
