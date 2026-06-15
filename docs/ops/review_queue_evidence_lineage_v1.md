# Review Queue / Evidence Digest Lineage v1

## Scope

Batch B adds lineage and partial-evidence structure to the daily review path:

- Review Queue items expose where a candidate came from, which EOD run produced it, and which Evidence Digest it maps to.
- Evidence Digest responses expose stable evidence sections with status, warnings, and missing/partial source lists.
- Dashboard API shapes remain backward compatible with the existing `facts`, `risk_flags`, `source_refs`, and `next_actions` fields.

## Out Of Scope

This batch does not add strategies, factors, data sources, trading actions, broker integration, or HomeCockpit layout work. It does not resolve existing Strategy Command Center, Backtest Lab, or vectorized backtest dirty worktree changes. Candidate outputs remain research review items, not execution instructions.

## Current Chain

`dashboard/review_queue.py` builds grouped queue items from `load_platform_summary(...).topn_preview` or `load_top_scores_for_dashboard(...)`. It calls `build_evidence_digest(...)` for each asset and currently returns `queue_id`, `asset_id`, `trade_date`, `score_version`, `rank`, `score`, `digest_title`, `bucket`, source kind counts, warnings, and the embedded digest.

`dashboard/evidence_digest.py` builds a digest from `build_asset_profile`, public news, research reports, and the EOD market monitor. It already degrades optional source failures into warnings, but the response is a legacy flat shape: `facts`, `risk_flags`, `source_refs`, `next_actions`, and `warnings`.

Operator decision and outcome APIs already expose evidence and lineage-like fields such as `event_id`, `review_date`, `evidence_artifact_id`, `evidence_path`, `source_context`, `outcome_event_id`, and outcome `run_id`. This batch does not create new decision tables; it exposes those histories inside digest sections where available.

Batch A added `ops.data_run_manifest`, `run_summary.json`, and readiness v2. Batch B consumes the latest manifest when available, but does not duplicate readiness logic.

## Review Queue Lineage Shape

Each queue item keeps existing fields and adds:

```json
{
  "run_id": "eod-2026-06-12-local",
  "latest_trade_date": "2026-06-12",
  "generated_at": "2026-06-12T00:00:00+00:00",
  "source_type": "score_topn",
  "source_name": "manual_v1_topn",
  "source_rank": 3,
  "score_components": {},
  "topn_rank": 3,
  "strategy_name": null,
  "strategy_run_id": null,
  "factor_as_of": "2026-06-12",
  "digest_key": "2026-06-12:manual_v1:000001.SZ",
  "digest_url_path": "/api/evidence-digest?asset_id=000001.SZ&trade_date=2026-06-12&score_version=manual_v1",
  "stock_workspace_url_path": "/stock/000001.SZ?trade_date=2026-06-12",
  "evidence_status": "PARTIAL",
  "missing_evidence": ["financial"],
  "partial_evidence": ["news"],
  "missing_evidence_count": 1,
  "partial_evidence_count": 1,
  "warnings_count": 2,
  "manifest_modules": []
}
```

If `strategy_run_id` is unavailable, the field is `null` and the item adds a warning. This does not imply a missing strategy implementation; current TopN candidates are score-derived research outputs.

## Evidence Sections Shape

Digest responses keep legacy fields and add:

```json
{
  "stock_code": "000001.SZ",
  "stock_name": "平安银行",
  "latest_trade_date": "2026-06-12",
  "run_id": "eod-2026-06-12-local",
  "digest_key": "2026-06-12:manual_v1:000001.SZ",
  "generated_at": "2026-06-12T00:00:00+00:00",
  "overall_status": "PARTIAL",
  "sections": {
    "asset_profile": {
      "status": "available",
      "as_of": "2026-06-12",
      "source": "asset_profile",
      "item_count": 1,
      "warnings": [],
      "error_message": "",
      "data": {},
      "artifact_path": ""
    }
  },
  "missing_evidence": [],
  "partial_evidence": ["news"],
  "lineage": {},
  "errors": []
}
```

Section keys:

- `asset_profile`
- `score_snapshot`
- `factor_contributions`
- `strategy_context`
- `market_monitor`
- `news`
- `research_reports`
- `lhb`
- `industry`
- `financial`
- `technical_features`
- `generated_reports`
- `operator_history`
- `follow_up_history`
- `risk_flags`

Allowed section statuses are `available`, `partial`, `missing`, `unavailable`, `skipped`, and `error`.

## Status Rules

Evidence Digest `overall_status` is independent from platform readiness:

- `OK`: asset profile and score snapshot are available, and no main evidence section is partial/missing/error.
- `PARTIAL`: asset profile and score snapshot are usable, but optional evidence such as news, research reports, LHB, industry, financial, technical features, or generated reports is partial, missing, skipped, or unavailable.
- `BLOCKED`: asset profile is missing/error, or score snapshot is missing/error, so the digest cannot explain the candidate.

Manifest module status maps to section status only when a matching module exists. Tier 2/Tier 3 manifest failures become section warnings and `partial` or `unavailable`; they do not block a digest if core sections are usable.

## Manifest Relationship

Batch B reads the latest `ops.data_run_manifest` via Batch A helpers. It exposes:

- `run_id`
- `latest_trade_date`
- `manifest_modules`
- module warnings/errors as section warnings

If manifest is unavailable, responses still build from current dashboard sources and include a warning instead of failing.

## API Examples

Review Queue remains:

```json
{
  "trade_date": "2026-06-12",
  "score_version": "manual_v1",
  "generated_at": "2026-06-12T00:00:00+00:00",
  "groups": [{"bucket": "strong", "items": []}],
  "warnings": []
}
```

Each item adds lineage fields listed above. Evidence Digest remains callable through `/api/evidence-digest` and adds the structured fields without removing legacy fields.

## Test Plan

- Review Queue item includes `run_id`, `latest_trade_date`, `score_version`, `topn_rank`, `digest_key`, and evidence status counts.
- Review Queue degrades missing `strategy_run_id` into a warning.
- Evidence Digest includes all expected section keys and statuses.
- News and research report absence produce `PARTIAL`, not an exception.
- Core asset profile or score absence produces digest-level `BLOCKED`.
- Dashboard endpoint tests verify response shape.
- Frontend type/client tests accept the expanded response shape.
- Batch A readiness tests continue passing.

## Smoke Test

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_dashboard_review_queue.py \
  tests/test_dashboard_evidence_digest.py \
  tests/test_dashboard_app.py \
  tests/test_dashboard_readiness.py -q

cd dashboard && pnpm exec vitest run --exclude "**/*.spec.ts" \
  tests/client.test.ts tests/review-queue-workspace.test.tsx tests/stock-workspace.test.tsx

cd dashboard && pnpm build
```

## Batch C/D Reserve

Batch C can persist review item snapshots and decision-to-digest IDs. Batch D can add UI presentation for section status and operator decision capture. Neither is implemented here.
