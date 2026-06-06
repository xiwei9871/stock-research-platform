# tech-bottleneck-discovery Runbook

`tech-bottleneck-discovery` is an automated research lens for hard-technology chokepoint candidates. The system generates research packets; humans review the generated evidence and record approve, reject, or needs-more-evidence.

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
