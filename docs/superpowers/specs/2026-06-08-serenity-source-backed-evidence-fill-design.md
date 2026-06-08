# Serenity Source-Backed Evidence Fill Design

## Goal

Add a separate source-backed evidence layer for Serenity bottleneck methodology fields. The layer must not overwrite heuristic labels; it should identify which fields are actually supported by original evidence and which remain artifact-only or missing.

## Scope

First pass covers the three weakest high-priority fields:

- `revenue_exposure_bucket`
- `customer_certification_stage`
- `supplier_concentration_evidence`

The existing heuristic outputs remain unchanged. This module consumes those outputs plus an optional evidence seed CSV and writes a new audit layer.

## Evidence Model

Each candidate-field pair receives:

- `inferred_value`: value from the current structured fill or heuristic layer.
- `source_backed_value`: value supported by source evidence; empty if no source evidence exists.
- `evidence_grade`: one of `primary_strong`, `primary_partial`, `artifact_only`, `missing`.
- `evidence_refs`: JSON list of source references.
- `evidence_limit`: short explanation of what is still missing.

Only original or near-original sources can upgrade a row above `artifact_only`: company announcements, annual reports, investor Q&A, broker reports, research reports, or structured extracts from those files. Local artifacts can explain lineage, but cannot by themselves become strong evidence.

## Inputs

Required:

- Serenity P1 structured detail CSV.

Optional:

- Evidence seed CSV with one row per evidence item. Required columns are flexible, but the module recognizes `asset_id`, `field`, `source_type`, `source_path`, `source_date`, `claim`, `supports_value`, `evidence_tier`, and `excerpt`.

## Outputs

- `serenity_source_backed_evidence_detail.csv`: one row per candidate.
- `serenity_source_backed_evidence_long.csv`: one row per candidate-field.
- `serenity_source_backed_gap_summary.csv`: field-level grade summary.
- `top_priority_manual_evidence_queue.csv`: rows still requiring human/source collection.
- `serenity_source_backed_evidence_report.md`: readable report.

## Rules

- No evidence seed and no artifact provenance: `missing`.
- Local artifact provenance only: `artifact_only`.
- One source item without direct value support: `primary_partial`.
- One source item with `supports_value` or strong evidence tier: `primary_strong`.
- Revenue exposure evidence prefers annual report segment revenue, product revenue split, order backlog, and broker product breakdown.
- Customer certification evidence prefers customer validation, design-in, qualification, fixed-point, order, delivery, or mass-production language.
- Supplier concentration evidence prefers market share, import dependency, domestic substitute scarcity, supplier count, or single/leading supplier claims.

## Non-Goals

- No backtest change.
- No scoring change.
- No automatic web search in this module.
- No claim that weak fields are solved unless source evidence exists.
