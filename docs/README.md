# Stock Research Documentation Index

Use this page to find current operating instructions without treating every
dated design or completion record as an active runbook. Historical documents
remain in place for audit and provenance.

## Start Here

- [Repository overview](../README.md) — product scope, safety boundaries, and
  current release entry points.
- [Project instructions](../AGENTS.md) — canonical checkout, production
  inputs, external sync, and operational constraints.
- [Platform architecture](astock-research-platform-v1.md) — major data and
  service layers.
- [Canonical frontend](canonical-frontend.md) — supported dashboard bundle
  and frontend boundaries.

## Active Operations

### Daily Data and Repair

- [Stock daily data pipeline](stock-daily-data-pipeline-runbook.md)
- [Daily close pipeline](daily-close-pipeline-runbook.md)
- [Daily factor pipeline](daily-factor-pipeline-runbook.md)
- [Intraday pipeline](intraday-pipeline-runbook.md)
- [Open-auction minute collection](open-auction-minute-collect-runbook.md)
- [Platform hardening](ops/platform-hardening-runbook.md)

### Dashboard and External Service

- [Dashboard workbench](dashboard-workbench-runbook.md)
- [Dashboard ops snapshot](dashboard-ops-snapshot-runbook.md)
- [External access runbook](platform_external_access_runbook.md)
- [External auth-proxy smoke](platform_external_access_auth_proxy_smoke_runbook.md)

The production dashboard is `https://stock.manqiaotechnology.com` on
stock-prod. The old local launchd dashboard services are retired; a manually
started `127.0.0.1:8765` API is for development only. Use
`deploy/sync_dashboard_release.sh` for a full release and
`deploy/sync_dashboard_artifacts.sh` only for its configured artifact set.
The artifact-only script does not mirror arbitrary directories under
`outputs/research`.

### Reports and Research

- [Yanbaoke report backfill](ops/yanbaoke-report-backfill-runbook.md)
- [Tech Bottleneck review-universe operations](tech_bottleneck_review_universe_operator_runbook.md)
- [Theme Research ingestion](theme_research_ingestion_v1.md)
- [Theme Research priority](theme_research_priority_v1.md)
- [Theme Research dashboard](theme_research_dashboard_v1.md)
- [Theme Research workflow integration](theme_research_workflow_integration_v1.md)
- [Theme-to-Tech-Bottleneck crosswalk](theme_tech_bottleneck_crosswalk_v1.md)
- [Theme company mapping](theme_company_mapping_v1.md)
- [Theme Research database](theme_research_database_v1.md)
- [Theme report publication analysis](ops/theme-research-analysis-report-publication.md)

The stock report workspace reads `research.stock_report_source` and
`research.stock_report_event`; Yanbaoke imports also run the existing PDF-field
backfill. The Tech Bottleneck candidate-universe workflow consumes report
metadata as secondary research evidence. A report title or broker forecast is
not a verified primary-source claim, and these imports do not promote
admission or trading signals automatically.

### Storage and Retention

- [Storage retention policy](ops/stock_research_storage_retention.md)
- [Storage cleanup execution plan](ops/stock_research_storage_cleanup_execution_plan_2026-06-12.md)

The cleanup SQL in these documents is not a routine cleanup command. Archive
and verify data before any deletion. `outputs/` is gitignored but contains
production-critical inputs listed in `AGENTS.md`; do not bulk-delete or move
it. `reports/` is also synced to stock-prod and must be preserved.

## Historical and Decision Records

- [`quant_system/`](quant_system/) contains the P0-P19 design, scope-freeze,
  completion, and audit trail. Use
  [the P19 phase index](quant_system/65_p19_platform_phase_index.md) and
  [the P19 release closure](quant_system/69_p19_final_platform_closure_completion.md)
  for current platform-foundation context; earlier phase files are historical
  records, not a single current implementation plan.
- `p6-dashboard-*` files are dashboard branch and integration reviews.
- `real-data-flow-smoke-2026-05-10.md` and dated restore/analysis documents are
  point-in-time records; check their dates before treating them as current
  operating instructions.

## Code Entry Points

- Yanbaoke source import and PDF-field backfill:
  [`src/stock_research/yanbaoke_reports.py`](../src/stock_research/yanbaoke_reports.py)
- Tech Bottleneck A-share candidate discovery:
  [`scripts/run_tech_bottleneck_a_share_candidate_universe.py`](../scripts/run_tech_bottleneck_a_share_candidate_universe.py)
- Tech Bottleneck evidence workflow:
  [`src/stock_research/tech_bottleneck_evidence_workflow.py`](../src/stock_research/tech_bottleneck_evidence_workflow.py)
- Theme Research ingestion and review: see
  [Theme Research ingestion](theme_research_ingestion_v1.md) and the related
  source files under `src/stock_research/theme_research*`.
