# tech-bottleneck-discovery Runbook

`tech-bottleneck-discovery` is an automated research lens for hard-technology chokepoint candidates. The system generates research packets; humans review the generated evidence and record approve, reject, or needs-more-evidence.

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
