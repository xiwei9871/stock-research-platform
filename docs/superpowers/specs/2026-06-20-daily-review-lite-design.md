# Daily Review Lite Design

## Goal

Build a dashboard page for structured read-only review of the `Daily Review v1 report package`. The page must present a stable Lite view model for a selected `trade_date`, prefer `report.report_run` as the package resolver, and remain strictly non-mutating.

The page is a dashboard-facing review surface, not a strategy engine, not a writeback console, and not a trading entrypoint.

## Scope

Daily Review Lite includes:

- A dedicated dashboard page: `DailyReviewLitePage`
- A dedicated backend API that resolves the latest eligible `daily_review_v1` package for a selected `trade_date`
- A Lite mapper that converts raw package artifacts into a stable dashboard view model
- Controlled artifact links returned as backend-generated URLs, not raw filesystem paths
- Explicit support for `ready`, `partial`, `empty`, and `failed` page states

The page shows:

- Run/source status
- Summary and warnings
- Data readiness
- Market review
- Strategy summaries split into `LHB`, `Mid Trend`, and `Technical Bottleneck`
- Holding review
- Operator plan
- Next-day checklist
- Registered artifact links

## Non-Goals

This phase does not:

- Write operator decisions
- Trigger broker, cash, order, or real position mutation
- Recompute strategy outputs
- Accept user-provided file paths
- Turn the dashboard into a report-generation or strategy-calculation entrypoint
- Modify `daily_review_report_workflow.py` main report-generation flow

## Source Resolution

### Primary Resolver

The backend must resolve the package from `report.report_run` first.

Selection rules:

- `report_type = 'daily_review_v1'`
- `trade_date = selected trade_date`
- `status IN ('success', 'partial')`
- choose the latest row by `updated_at DESC`

The resolver reads only paths already registered in `report_paths` and optionally augmented by manifest metadata derived from those paths.

### Fallback Resolver

Fallback package scanning is compatibility-only and must run only when no eligible `report.report_run` row is found.

Fallback behavior:

- scan known Daily Review package locations for the selected `trade_date`
- choose the newest valid package candidate by file timestamp or equivalent deterministic rule
- mark the resolved source as `fallback`

When fallback is used, the page must explicitly show:

- `Loaded from fallback package scan`

### Resolver Guarantees

The resolver must not:

- read arbitrary paths from frontend input
- allow artifact access outside registered package files
- reinterpret the dashboard page as a package browser

## Artifact Model

Artifact links must be derived only from:

- `report.report_run.report_paths`
- package manifest entries loaded from already-registered paths

The Lite payload must not expose raw filesystem paths. Instead it returns controlled descriptors:

```json
{
  "key": "daily_review_json",
  "label": "Daily Review JSON",
  "kind": "json",
  "url": "/api/daily-review-lite/artifacts?trade_date=2026-06-20&key=daily_review_json&run_id=daily_review_v1:2026-06-20:abc123"
}
```

Artifact endpoint requirements:

- include `trade_date` and `key`
- support `run_id` to avoid collisions across multiple runs for the same date
- resolve the actual file server-side from the selected registered package
- reject unknown keys with `404`

## Backend Architecture

Daily Review Lite uses three layers.

### Resolver

Responsibilities:

- find the selected package from `report.report_run`
- fallback only when required
- emit trusted run metadata and trusted artifact registry

Output:

- selected run metadata
- trusted artifact references
- source indicator: `report_run` or `fallback`

### Loader

Responsibilities:

- read trusted package artifacts
- parse core files when present:
  - `daily_review.json`
  - `manifest.json`
  - `operator_plan_template.json`
- register artifact health issues instead of treating every missing file as a transport exception

The loader should classify artifact health at minimum as:

- `healthy`
- `missing`
- `invalid`

If first version does not expose per-artifact health detail in the public payload, keep internal detail and leave a documented TODO for a future `artifact_health_detail` field.

### Mapper

Responsibilities:

- convert raw package content into a stable Lite view model
- derive page `state`
- attach section-level warnings
- preserve read-only semantics

Top-level page `state` is derived by the mapper, not copied blindly from package status.

`selected_run.status` may contain:

- `success`
- `partial`
- `failed`

But final page `state` is:

- `ready`: package resolved and core artifacts mapped successfully
- `partial`: package resolved and mapped, but source gaps or partial artifact content affect one or more sections
- `empty`: no eligible report package found
- `failed`: a run or fallback package was found, but required artifact loading or parsing failed

## API Contract

Endpoint:

- `GET /api/daily-review-lite?trade_date=YYYY-MM-DD`

Suggested response:

```json
{
  "trade_date": "2026-06-20",
  "state": "partial",
  "selected_run": {
    "run_id": "daily_review_v1:2026-06-20:abc123",
    "report_type": "daily_review_v1",
    "status": "partial",
    "updated_at": "2026-06-20T22:05:00+08:00",
    "source": "report_run",
    "artifact_health": "healthy"
  },
  "summary": {
    "market_status": "defensive",
    "overall_position_bias": "defensive",
    "lhb_conclusion": "trial",
    "mid_trend_conclusion": "hold core names",
    "technical_bottleneck_conclusion": "monitor upgrades only",
    "must_review_asset_ids": ["CN:SH:600000"],
    "warning_count": 1
  },
  "warnings": ["source_missing:lhb_feed"],
  "missing_sources": [
    {
      "source_key": "lhb_feed",
      "summary": "lhb payload missing for trade date",
      "affected_sections": ["data_readiness", "strategy_summaries.lhb", "next_day_checklist"],
      "confidence_impact": "LHB conclusion confidence reduced"
    }
  ],
  "sections": {},
  "artifacts": []
}
```

### Top-Level Fields

- `trade_date`
- `state`
- `selected_run`
- `summary`
- `warnings`
- `missing_sources`
- `sections`
- `artifacts`

### selected_run

```json
{
  "run_id": "daily_review_v1:2026-06-20:abc123",
  "report_type": "daily_review_v1",
  "status": "success",
  "updated_at": "2026-06-20T22:05:00+08:00",
  "source": "report_run",
  "artifact_health": "healthy"
}
```

Rules:

- `status` is compatible with `success`, `partial`, and `failed`
- `artifact_health` is an overall status for the selected package
- TODO: add `artifact_health_detail` or equivalent per-artifact health breakdown in a later version if not exposed initially

### summary

`summary` is the compact top-of-page review:

- `market_status`
- `overall_position_bias`
- `lhb_conclusion`
- `mid_trend_conclusion`
- `technical_bottleneck_conclusion`
- `must_review_asset_ids`
- `warning_count`

### missing_sources

Each item contains:

- `source_key`
- `summary`
- `affected_sections`
- `confidence_impact`

`affected_sections` is intentionally broader than a strict blocking list. Missing data may reduce confidence without preventing rendering.

## Sections Contract

Each section must carry:

- `status`
- `warnings`

Common values:

- `success`
- `partial`
- `empty`

### Data Readiness

```json
{
  "status": "partial",
  "warnings": ["source_missing:lhb_feed"],
  "items": [
    {
      "source_key": "lhb_feed",
      "status": "missing",
      "summary": "lhb payload missing for trade date",
      "freshness_label": "latest 2026-06-19, expected 2026-06-20",
      "confidence_impact": "LHB conclusion confidence reduced",
      "affected_sections": ["strategy_summaries.lhb", "next_day_checklist"]
    }
  ]
}
```

### Market Review

Fields:

- `emotion_state`
- `risk_state`
- `trend_environment`
- `style_bias`
- `target_exposure`
- `market_comment`

### Strategy Summaries

This section must be fixed, not generic.

It always splits into:

- `lhb`
- `mid_trend`
- `technical_bottleneck`

Each strategy card contains:

- `conclusion`
- strategy-specific summary metrics
- `warnings`
- `top_items`

`top_items` exists to preserve review value beyond counts. Keep the list short, for example the top 3 items.

Suggested item shape:

```json
{
  "asset_id": "CN:SH:600000",
  "stock_name": "浦发银行",
  "action": "manual_review",
  "review_priority": "P0",
  "reason_summary": "bank rotation leader"
}
```

Strategy-specific fields:

- `lhb`: `short_allowed`, `watch_count`, `forbidden_actions`
- `mid_trend`: `portfolio_health`, `holding_count`
- `technical_bottleneck`: `upgraded_count`, `research_required_count`

### Holding Review

The holding review preserves explicit strategy ownership and must not merge rows across strategies.

Suggested row fields:

- `strategy_id`
- `asset_id`
- `current_state`
- `action`
- `risk_status`
- `exit_condition`

### Operator Plan

Read-only projection of the package plan:

- `mode`
- `overall_position_bias`
- `must_check_before_open`
- `forbidden_actions`

No decision writeback is allowed from this page.

### Next-Day Checklist

`must_review_items` must preserve cross-strategy review intent after deduplication.

Use:

```json
{
  "asset_id": "CN:SH:600000",
  "ts_code": "600000.SH",
  "stock_name": "浦发银行",
  "strategy_ids": ["lhb", "mid_trend"],
  "review_priority": "P0",
  "actions": ["manual_review", "add_candidate"],
  "reasons": [
    {
      "strategy_id": "lhb",
      "summary": "shortline rebound",
      "detail": {
        "setup": "shortline rebound"
      }
    },
    {
      "strategy_id": "mid_trend",
      "summary": "trend continuation",
      "detail": {
        "setup": "trend continuation"
      }
    }
  ]
}
```

Frontend rendering uses `summary`. `detail` preserves the original structure for future expansion.

## Frontend Structure

Create a dedicated `DailyReviewLitePage`.

It should remain separate from the current dashboard workbench data assembly and only depend on the Lite endpoint.

Page structure:

1. Header/status strip
2. Summary and warning banner
3. Section stack
4. Artifact links

### Header

Show:

- title: `Daily Review Lite`
- subtitle: `Structured read-only review of the Daily Review v1 report package`
- `trade_date` control
- source label:
  - `Loaded from report.run`
  - `Loaded from fallback package scan`
- run metadata
- artifact health

### Summary and Warning Banner

Show:

- overall warnings
- missing source explanations
- page `state`

For `failed`, keep run metadata visible if available and explain that package artifacts could not be read or parsed.

### Section Stack

Render fixed sections in order:

1. `Data Readiness`
2. `Market Review`
3. `Strategy Summaries`
4. `Holding Review`
5. `Operator Plan`
6. `Next-day Checklist`

Each partial section must show local warnings in that section, not only at page top.

### Artifact Links

Render only server-provided artifact descriptors:

- `key`
- `label`
- `kind`
- `url`

The frontend must never:

- construct a local filesystem path
- accept an arbitrary path from the user
- expose raw `report_paths`

## State Handling

### ready

- resolved package
- core artifacts valid
- render all available sections

### partial

- resolved package
- mapper can produce the Lite model
- one or more source gaps, stale inputs, or incomplete artifacts affect confidence or completeness

Render the page normally with:

- top warning banner
- section-level warnings

### empty

- no eligible `report.report_run`
- no compatible fallback package

Render a normal empty state:

- `No report found for selected date`

### failed

- a run or fallback package was found
- required artifact missing or invalid
- mapper cannot safely produce a full Lite projection

Render:

- failed banner
- run/source metadata if known
- artifact health
- any surviving artifact links that remain safe to expose

## HTTP Semantics

The endpoint returns `200` for:

- `ready`
- `partial`
- `empty`
- `failed`

Return `400` when:

- `trade_date` is invalid

Return `500` only for API/service failures such as:

- database connection failure
- unhandled backend exception

Package absence, partial package content, and artifact invalidity are report availability states, not server exceptions.

## Testing Boundary

### Backend Unit Tests

Resolver tests:

- prefer `report.report_run`
- filter by `report_type = daily_review_v1`
- filter by `status IN ('success', 'partial')`
- choose latest `updated_at`
- fallback only when no eligible run exists
- mark fallback source explicitly

Loader tests:

- load trusted registered artifacts only
- classify artifact health as `healthy`, `missing`, or `invalid`
- reject unknown artifact keys

Mapper tests:

- derive `ready`
- derive `partial`
- derive `empty`
- derive `failed`
- attach section warnings
- preserve fixed `LHB`, `Mid Trend`, and `Technical Bottleneck` cards
- preserve `must_review_items.reasons` as `{ strategy_id, summary, detail? }`

### Backend API Tests

- `GET /api/daily-review-lite` returns `200` for `ready`
- returns `200` with `state=partial` for partial packages
- returns `200` with `state=empty` when no package exists
- returns `200` with `state=failed` when artifacts are missing or invalid
- returns `400` for invalid `trade_date`
- returns `404` for unknown artifact key
- does not expose raw filesystem paths in payload

### Frontend Tests

Client tests:

- request URL for `fetchDailyReviewLite(tradeDate)` is correct

Page tests:

- renders all fixed sections for `ready`
- renders `No report found for selected date` for `empty`
- renders top and local warnings for `partial`
- renders failed banner for `failed`
- renders fallback banner when source is `fallback`
- renders fixed strategy cards for `LHB`, `Mid Trend`, and `Technical Bottleneck`
- uses only backend-provided artifact `url` values

## Implementation Notes

- Keep Lite logic additive to the current dashboard codebase
- Reuse existing dashboard API patterns and test style
- Do not couple the Lite page to current TopN, watchlist, or outcomes workbench data loads
- Do not mutate the report-generation workflow to fit page concerns

## Open Decisions Resolved

- Independent dashboard view: yes
- Resolution key: `trade_date`
- Package selection: latest eligible `report.report_run`
- Fallback package scan: compatibility only
- Frontend input path support: no
- View model: dedicated Lite contract, not raw `daily_review.json`
- Strategy summary layout: fixed `LHB`, `Mid Trend`, `Technical Bottleneck`
- Page behavior: read-only
