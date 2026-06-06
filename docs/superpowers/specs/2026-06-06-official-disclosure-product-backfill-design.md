# official-disclosure Product Backfill Design

## Purpose

`official-disclosure-product-backfill` fills the strict point-in-time product exposure gap for `tech-bottleneck-discovery`.

The current evidence backfill can generate text evidence, but strict readiness still blocks all 2025 top50 candidates because product revenue exposure has no visible disclosure date:

```text
has_product_revenue_exposure = 0/1100
ready_for_scoring = 0/1100
```

The immediate goal is to generate safe `product_revenue_exposure` evidence rows from official annual and semiannual disclosures, then rerun readiness and only then continue 20D / 60D / 120D / 250D testing.

## Current Constraint

`finance.main_business_composition` stores:

- `asset_id`
- `ts_code`
- `report_period`
- `classify_type`
- `item_name`
- revenue fields
- source metadata

It does not store `announcement_date`, `publish_date`, `disclosure_date`, or source document URL. Therefore rows from this table are not enough for strict PIT readiness even when `report_period <= candidate_date`.

The existing `free_enrichment_data` `stock_zygc_em` loader is useful as a product table source, but it is not sufficient for strict testing unless it can be joined to a reliable official disclosure date and source document.

## Scope

Version 1 is candidate-scoped and artifact-based.

Input:

- Current weekly top50 candidate CSV from 2025-01-01 onward.
- Candidate assets: 647.
- Candidate rows: 1100.

Output:

- `product_evidence.csv`: evidence rows compatible with `tech-bottleneck-data-readiness-audit --evidence-csv`.
- `disclosure_manifest.csv`: official disclosure records considered for each asset.
- `document_cache_index.csv`: local cached documents and extraction status.
- `coverage_summary.md`: safe product evidence coverage by candidate date, report period, and extraction status.
- `source_gap_report.csv`: candidates still missing safe product exposure evidence.

It does not:

- Promote candidates.
- Score alpha.
- Generate buy/sell decisions.
- Require manual data entry.
- Treat unparsed documents as successful evidence.
- Use disclosure documents published after the candidate `as_of_date`.

## Workflow

```text
Candidate CSV
-> build candidate disclosure windows
-> query official disclosure index
-> cache annual/semiannual report documents
-> extract main business by product tables
-> normalize product_revenue_exposure evidence
-> rerun data readiness audit with --evidence-csv
-> run bottleneck discovery test only if readiness improves
```

## Disclosure Selection

For each candidate row:

```text
asset_id
candidate_trade_date
as_of_date
lookback_days
```

The backfill selects official disclosures satisfying:

```text
publish_date <= as_of_date
report_period <= as_of_date
publish_date >= as_of_date - lookback_days_for_documents
```

Version 1 uses a wider document lookback than text evidence because product exposure can legitimately come from the last annual or semiannual report:

```text
document_lookback_days = 900
```

For the 2025-01 to 2025-05 pilot, this allows:

- 2023 annual reports.
- 2024 semiannual reports.
- 2024 annual reports only after their actual publish dates.

## Source Strategy

### Primary Source: Official Disclosure Index

The source adapter must query an official disclosure index by asset and date range, then keep only report documents whose title clearly indicates:

- annual report
- semiannual report
- corrected annual report
- corrected semiannual report

Chinese title filters:

- `年度报告`
- `半年度报告`
- `年报`
- `半年报`

Exclusions:

- `摘要`
- `取消`
- `英文版`
- `审计报告` when not part of the annual/semiannual report document
- unrelated announcement titles

The adapter stores raw index responses and normalized rows. If the live source is unavailable, the run records a source gap and does not fabricate product evidence.

### Secondary Source: Existing Main Business Table Join

When `finance.main_business_composition` has a matching row for:

```text
asset_id
report_period
classify_type = '按产品分类'
item_name present
```

and the official disclosure manifest provides a safe `publish_date` for the same report period, the backfill may combine:

- product/revenue values from `finance.main_business_composition`
- `publish_date`, `source_url`, `source_title`, and `source_id` from the official disclosure manifest

This is the fastest path to improve coverage without first parsing every PDF table.

Rows created by this join are strong evidence only when:

```text
publish_date <= candidate as_of_date
report_period <= candidate as_of_date
source document is annual/semiannual official disclosure
```

### Tertiary Source: Document Table Extraction

If existing main-business rows do not cover the document, the extractor attempts to parse cached annual/semiannual documents and identify product tables.

Version 1 extraction is intentionally conservative. The current project dependencies do not include a dedicated PDF table extraction library, so the implementation should first prove the manifest + existing-main-business join path. PDF/table extraction can use fixture text documents in tests and should become a later enhancement before relying on broad live PDF parsing.

When document extraction is enabled, it should:

- Search extracted text/table rows for table headers containing product classification language.
- Extract rows with product item, revenue, revenue ratio, cost, gross profit, or gross margin when available.
- Save partial product rows if product item is clear and source document is official.
- Mark rows without numeric revenue fields as strong product exposure only if the product table structure is clear.

Unparsed or low-confidence documents do not set readiness flags. They appear in `source_gap_report.csv` with extraction status.

## Evidence Contract

Each product evidence row uses the existing evidence schema:

```text
run_id
asset_id
stock_name
candidate_trade_date
as_of_date
evidence_date
source_type
source_id
source_title
source_url
evidence_type
matched_keyword
evidence_snippet
source_confidence
is_proxy
as_of_safe
metadata_json
```

For this backfill:

```text
evidence_type = product_revenue_exposure
source_confidence = strong
is_proxy = false
evidence_date = publish_date
as_of_safe = publish_date <= as_of_date and report_period <= as_of_date
```

`metadata_json` must include:

- `report_period`
- `publish_date`
- `classify_type`
- `item_name`
- `revenue`
- `revenue_ratio`
- `cost`
- `gross_profit`
- `gross_margin`
- `source_document_id`
- `source_document_url`
- `extraction_method`
- `extraction_confidence`

## Candidate-Scoped Safety

Evidence rows must include:

- `candidate_trade_date`
- `as_of_date`

Readiness already requires candidate-scoped evidence rows to match the current candidate. This backfill must preserve those columns exactly from the input candidate row.

## Document Cache

Documents are cached under:

```text
outputs/tech_bottleneck_discovery/disclosures/<run_id>/documents/
```

The cache index records:

- `asset_id`
- `ts_code`
- `report_period`
- `publish_date`
- `document_title`
- `document_url`
- `local_path`
- `payload_hash`
- `download_status`
- `extract_status`
- `error_message`

Downloaded files are never manually edited.

## Output Artifacts

### `product_evidence.csv`

Safe and unsafe product evidence rows. Readiness consumes only safe rows.

### `disclosure_manifest.csv`

One row per official disclosure document considered.

### `document_cache_index.csv`

One row per download/extraction attempt.

### `coverage_summary.md`

Includes:

- Candidate count.
- Asset count.
- Disclosure documents found.
- Documents downloaded.
- Documents parsed.
- Safe product evidence count.
- Safe product evidence candidate coverage.
- Top missing reasons.

### `source_gap_report.csv`

One row per candidate without safe product evidence:

- no official disclosure found
- document download failed
- document parse failed
- product table not found
- product rows found but unsafe by publish date
- existing main-business row has no matching official disclosure

## Success Criteria

The first implementation is successful when, on the current 2025 top50 pilot:

- `product_evidence.csv` is generated automatically.
- Every safe row has `publish_date`, `report_period`, and source document trace.
- Readiness with `--evidence-csv product_evidence.csv` increases `has_product_revenue_exposure` from `0/1100` to at least `30%`.
- `source_gap_report.csv` explains remaining missing product exposure candidates.
- No row with `publish_date > as_of_date` or `report_period > as_of_date` is marked safe.

If coverage remains below 30%, the output is still useful if the source gap report identifies whether the blocker is discovery lookup, download, parsing, or true missing data.

## Testing Strategy

Unit tests:

- Disclosure title filtering includes annual/semiannual reports and excludes summaries.
- Candidate disclosure window generation uses document lookback and candidate `as_of_date`.
- Existing main-business rows join to official disclosure manifest by `asset_id/report_period`.
- Rows without official publish date are unsafe.
- Rows with future publish date are unsafe.
- Rows with future report period are unsafe.
- Candidate-scoped evidence does not leak across repeated same-asset candidate dates.
- Source gap reasons are deterministic.

Fixture integration:

- Use small fixture disclosure manifest and fixture main-business rows.
- Use local fixture text/table documents instead of live network.
- Verify `product_evidence.csv` can be consumed by `tech-bottleneck-data-readiness-audit --evidence-csv`.

Live smoke:

- Run on 5 to 10 candidate assets first.
- Then run on the 647-asset pilot pool.
- Never let a live source failure become synthetic evidence.

## Risks

### Official Source Instability

The official disclosure index may rate-limit or change response shape. The adapter must cache raw responses and fail closed.

### PDF Table Extraction Quality

Annual report tables are not uniformly structured. Version 1 should prefer joining existing main-business rows to official disclosure dates before relying on PDF table extraction.

### Overstated Coverage

Product evidence is strong only when backed by official disclosure date and product table row. Text-only product descriptions are not enough for `has_product_revenue_exposure`.

### Runtime

Downloading and parsing hundreds of annual reports can be slow. The first implementation should support `--limit-assets` or equivalent smoke scope before full-pool execution.
