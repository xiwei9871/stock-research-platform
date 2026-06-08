# Evidence Unit Contract

This contract borrows the QuantMind-style idea of normalizing unstructured research material, but it remains a local `stock_research` schema. It does not add an external knowledge graph, external runtime, or production dependency.

## Purpose

An evidence unit is a small, point-in-time source-backed record that can connect reports, news, PDFs, announcements, macro context, external papers, or manual review notes to Agent observations and report artifacts.

## Fields

- `evidence_id`: stable local identifier
- `source_type`: one of `stock_report`, `pdf`, `public_news`, `announcement`, `macro_series`, `external_paper`, `manual_review`
- `source_id`: source-specific identifier
- `asset_id`: local asset identifier, usually `asset:<ts_code>`
- `ts_code`: A-share code when asset-specific
- `available_at`: timestamp or date when the material became usable
- `trade_date`: reviewed trade date
- `title`: source title
- `summary`: short source summary
- `claims`: source-backed claims extracted from the material
- `risks`: source-backed risks extracted from the material
- `source_path`: local artifact path
- `confidence`: extraction confidence from `0.0` to `1.0`
- `metadata`: local metadata such as `missing_fields`, `source_converter`, or `post_close_review`

## Validation Rules

- `evidence_id`, `source_type`, and `available_at` must be non-empty.
- `source_type` must be one of the allowed local values.
- `available_at` must be on or before `trade_date`.
- Later availability is allowed only when `metadata["post_close_review"] == True`.
- Missing title, summary, or source path in converter inputs must be recorded in `metadata["missing_fields"]`.

## Current Converters

- `evidence_unit_from_news_record(record)` converts small public-news dictionaries.
- `evidence_unit_from_stock_report_record(record)` converts small stock-report dictionaries.

These converters are thin and read-only. They do not modify existing news, report, scoring, watchlist, dashboard, or delivery pipelines.

## Boundary

Evidence units are supplemental evidence infrastructure. They do not replace PostgreSQL source-of-truth tables, point-in-time finance rules, factor scoring, backtests, watchlist decisions, or human operator review.
