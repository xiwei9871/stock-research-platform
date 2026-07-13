# Tech Bottleneck Review Universe Report PDF Parse

## Objective

Build a research-only parse layer for broker-report PDFs tied to the 378-stock tech bottleneck review universe. The output will support a later reassessment, but this task must not reassess stocks, write review decisions, freeze pools, or connect to signal/admission/scoring/strategy.

## Scope

- Input the 378-stock frontend review universe.
- Input Yanbaoke/report backfill coverage and downloaded report PDFs.
- Parse available report PDFs into page-level text citations and evidence chunks.
- Preserve stock code, stock name, report title, source path, parser status, and page provenance.
- Explicitly record missing report PDFs and parse failures.
- Keep broker reports separate from primary-source evidence.

## Outputs

Output directory:

`outputs/research/tech_bottleneck_review_universe_report_pdf_docling_parse_v1/`

Files:

- `review_universe_report_pdf_parse_summary.json`
- `review_universe_report_pdf_parse_manifest.csv`
- `review_universe_report_pdf_parse_audit.csv`
- `review_universe_report_pdf_evidence_chunks.csv`
- `review_universe_report_pdf_page_citations.csv`
- `review_universe_report_pdf_parse_failures.csv`
- `review_universe_report_pdf_docling_guardrails.json`
- `tech_bottleneck_review_universe_report_pdf_docling_parse_v1_report.md`

## Implementation Plan

1. Add a focused test file for the new parser task.
2. Add a parser module that builds a selected report-PDF manifest from coverage data.
3. Reuse the existing text-first PDF page extractor for efficient page-level citations, with Docling availability recorded for follow-up targeted parsing.
4. Add a CLI script with conservative defaults and guardrails.
5. Run the parser against the current local artifacts.
6. Verify outputs, relevant regression tests, formal strategy diff, and `git diff --check`.

## Guardrails

- `research_only = true`
- `primary_source_collection_performed = false`
- `evidence_backfill_performed = false`
- `core_equivalence_performed = false`
- `reassessment_performed = false`
- `frozen_quality_pool_generated = false`
- `used_for_signal_count = 0`
- `used_for_admission_count = 0`
- No changes to `src/stock_research/tech_bottleneck_v1.py`
- No changes to `src/stock_research/tech_bottleneck_candidates.py`

## Acceptance

- `review_universe_report_pdf_docling_parse_ready`
- `conditionally_ready_with_parse_failures`
- `blocked_due_to_guardrail_violation`
