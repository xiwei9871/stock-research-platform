# Review Queue Runtime Consistency and Date Decoupling Design

## Goal

Eliminate repeated Review Queue and Stock Workspace date regressions by making review dates, strategy-data dates, chart dates, runtime code versions, and deployed artifacts explicit and independently verifiable.

The external dashboard must never combine a current platform date with stale strategy artifacts or silently rewrite an operator's requested replay date.

## Confirmed Failure

On 2026-07-27, the external dashboard returned:

- platform market date: `2026-07-24`;
- Review Queue date: `2026-06-01`;
- LHB Shortline: no rows;
- Mid Trend: five rows from `2026-05-18`;
- Tech Bottleneck: five rows from `2026-06-01`.

Explicit requests for `trade_date=2026-07-24` and `trade_date=2026-07-23` still returned `trade_date=2026-06-01`. Local API responses, however, returned all three strategies with five rows for `2026-07-24`.

The investigation established five interacting causes:

1. Review Queue response construction replaces the requested date with the maximum date found in fallback rows.
2. The external deployment is serving older Review Queue code and older strategy artifacts while reading current platform summary data.
3. The external daily sync service is disabled and its configured source is an obsolete worktree.
4. Local frontend, API, and editable Python installation point to different worktrees.
5. The scheduled strategy EOD job is all-or-nothing: a BaoStock minute-5 login failure caused all three strategies to be skipped, although the later auto-repair eventually published a valid `2026-07-24` manifest.

## Scope

Included:

- Review Queue requested-date semantics.
- Strategy group freshness and unavailable-state semantics.
- Stock Workspace review-date/chart-date separation.
- Strategy EOD dependency isolation and recovery publication.
- Canonical runtime provenance for local and external deployments.
- External artifact synchronization and post-deploy smoke gates.
- Tests covering API, React state, scripts, runtime provenance, and release checks.

Excluded:

- Strategy formula changes.
- Trading recommendations or automated execution.
- Replacing BaoStock as the minute-data provider.
- Reworking unrelated research pipelines.
- Publishing an unreviewed branch directly to the external host.

## 1. Review Queue Date Contract

The top-level Review Queue date represents the operator's requested review date, not the newest date found in returned rows.

Response fields:

```json
{
  "requested_trade_date": "2026-07-24",
  "trade_date": "2026-07-24",
  "platform_market_date": "2026-07-24",
  "data_status": "ready",
  "groups": [
    {
      "strategy_id": "mid_trend",
      "requested_trade_date": "2026-07-24",
      "data_trade_date": "2026-07-24",
      "freshness_status": "current",
      "count": 5,
      "items": []
    }
  ],
  "warnings": []
}
```

Rules:

- `trade_date` remains compatible with existing frontend consumers and always equals `requested_trade_date`.
- `data_trade_date` is computed per strategy group from the actual rows.
- `freshness_status` is `current`, `stale`, or `missing`.
- An explicit replay request is never rewritten to `data_trade_date`.
- The frontend keeps the operator's requested input after loading, even when strategy data is stale or missing.
- Warnings name the affected strategy and its actual data date.

## 2. Fail-Closed Strategy Data Selection

For the default/latest Review Queue:

1. Load a successful, contract-valid strategy manifest for the requested date.
2. If the exact-date manifest is unavailable, return the strategy group as `missing` with zero rows.
3. Do not silently substitute unrelated legacy artifact directories for the latest queue.

For explicit historical replay:

1. Load exact-date manifest/snapshot data when available.
2. A legacy artifact may be used only when its row date equals the requested historical date and its provenance is reported.
3. Older rows may be shown only as a clearly labeled stale diagnostic, not as the requested day's official queue.

This preserves forensic replay without presenting stale candidates as current output.

## 3. Stock Workspace Date Decoupling

Stock Workspace uses separate initial dates:

```ts
const initialReviewDate = entryContext?.tradeDate ?? defaultTradeDate ?? DEFAULT_TRADE_DATE;
const initialChartEndDate = defaultTradeDate ?? DEFAULT_TRADE_DATE;
```

Responsibilities:

- `tradeDate`: evidence, decision, and review context.
- `endDate`: chart/profile market-data cutoff.
- Historical entry context never silently truncates the chart.
- Submitting the existing settings form is the explicit action that permits historical chart replay.
- When `endDate` is earlier than the latest platform date, show `历史回放中 · 截至 YYYY-MM-DD`.

## 4. Strategy EOD Dependency Isolation

The scheduler must not turn one minute-data provider failure into an unexplained three-strategy outage.

Dependency classes:

- Common daily dependencies: daily bars, technical features, factor/score dependencies, and database availability.
- Intraday dependency: minute-5 completeness.
- Strategy-specific dependencies are evaluated independently.

Behavior:

- Each strategy records `success`, `failed`, or `blocked`, with explicit dependency reasons.
- Strategies that do not consume minute-5 data may publish when common daily dependencies are ready.
- A strategy that consumes minute-5 data remains blocked until minute-5 is ready or repaired.
- The aggregate run is `success` only when all required official strategy modules are publishable; otherwise it is `partial` or `failed` and cannot pass the display gate.
- Auto-repair may retry missing dependencies and then republish one atomic, contract-valid official manifest.
- Recovery clears dashboard response caches only after the official manifest is committed.

The implementation must derive dependency declarations from the actual strategy runners. It must not assume all strategies require minute-5 merely because the current global preflight does.

## 5. Canonical Runtime Provenance

Local and external services must run one selected release revision.

Add a runtime provenance payload to platform readiness:

```json
{
  "runtime_provenance": {
    "release_id": "<git-sha-or-release-id>",
    "source_root": "/path/to/release",
    "python_package_root": "/path/to/release/src/stock_research",
    "frontend_build_id": "<build-id>",
    "strategy_artifact_date": "2026-07-24"
  }
}
```

Guardrails:

- The Python environment used by API and scheduled jobs must resolve `stock_research` from the selected release root.
- Startup validation fails with a clear error if `source_root` and `python_package_root` disagree.
- Frontend and API services use the same release ID.
- Scheduled jobs use the same release root and Python environment as the API.
- LaunchAgent/OpenClaw commands must not reference disposable validation worktrees.
- Editable-install `.pth` files pointing at another worktree are rejected by the runtime check.

## 6. External Deployment

Replace the disabled obsolete-worktree sync path with one canonical release command owned by the current repository.

Deployment sequence:

1. Verify clean, explicitly selected release revision.
2. Run focused and full tests.
3. Build the frontend once.
4. Sync backend source, frontend build, and only official strategy manifests/artifacts required by Review Queue.
5. Restart API and frontend containers.
6. Poll readiness until API and frontend release IDs match.
7. Run external smoke gates.
8. Mark deployment successful only after every gate passes.

Required external smoke gates:

- platform market date equals expected latest completed trade date;
- default Review Queue date equals platform market date;
- three official strategy groups are present;
- each official group has five rows for the expected date;
- explicit replay preserves the requested date;
- Stock Workspace historical review context does not truncate the default chart;
- runtime release IDs match;
- no stale-artifact warning is present for a ready release.

The sync job must fail before restart if the source tree is dirty, the strategy manifest is missing, or runtime provenance cannot be generated.

## 7. Frontend Review Queue Behavior

- Date input displays the API's `requested_trade_date`/`trade_date`.
- Clicking `回放该日复盘队列` sends the input date and retains it after the response.
- Group headers show `数据日期 YYYY-MM-DD` separately.
- `stale` and `missing` groups use warning/unavailable presentation and cannot look like current official candidates.
- `回到最新复盘队列` makes a request without `trade_date` and resets the input to the returned requested date.
- Freshness lag is calculated from the requested review date to the platform market date; strategy-level lag is calculated from each group's data date.

## 8. Error Handling and Observability

- BaoStock connection failures retain the provider error code and affected dependency in task status.
- Strategy task output lists every strategy status, not only aggregate row count.
- Auto-repair records whether it repaired minute-5, strategy publication, external sync, or cache invalidation.
- External deployment never reports success when the release check receives a transient `502`; it retries within a bounded readiness window and then fails.
- The dashboard shows a controlled unavailable state instead of silently displaying stale candidates.

## Testing

### Backend

- Explicit `2026-07-24` request with rows dated `2026-06-01` returns top-level `trade_date=2026-07-24` and group `data_trade_date=2026-06-01`.
- Default current queue rejects stale fallback artifacts.
- Historical exact-date replay can load an exact legacy artifact with provenance.
- Missing strategy manifest produces empty official groups with warnings.
- Runtime provenance rejects mismatched source/package roots.

### Strategy pipeline

- Minute-5 failure blocks only runners that declare the intraday dependency.
- Common dependency failure blocks all official strategies.
- Partial runs do not pass the display gate.
- Successful repair republishes all required manifest modules atomically.
- Cache clear occurs after publication, never before.

### Frontend

- Replay input does not reset to a stale data date.
- Group data dates and stale/missing states render separately from the requested date.
- Historical Review Queue handoff preserves the review date while Stock Workspace chart defaults to the latest platform date.
- Explicit chart replay shows the historical replay indicator.

### Deployment

- Deployment scripts refuse obsolete worktree roots.
- Deployment scripts verify Python import provenance.
- Release check fails on Review Queue/platform date mismatch, missing groups, non-five counts, or release-ID mismatch.
- Release check passes against a fixture representing three current five-row strategy groups.

## Rollout

1. Land backend date contract and tests.
2. Land frontend Review Queue and Stock Workspace state changes.
3. Land strategy dependency/status changes.
4. Land provenance and deployment guardrails.
5. Select and build one canonical release revision.
6. Repair local editable install and restart local API/frontend from that release.
7. Publish current official artifacts and release to the external host.
8. Run local and external smoke gates.
9. Re-enable only the canonical sync schedule; keep obsolete LaunchAgents disabled or remove them after verification.

## Acceptance Criteria

- External and local platform summaries and Review Queues agree on the latest completed trade date.
- All three official strategy groups show five current rows when the release is ready.
- Explicit replay never changes the requested date.
- Stale strategy data is visibly stale or unavailable and is never presented as current output.
- Stock Workspace review dates do not silently truncate K-line charts.
- API, frontend, scheduled jobs, and deployment report one matching release identity.
- No enabled schedule or Python editable install points to a disposable worktree.
- A minute-5 provider failure has explicit, strategy-scoped impact and a verified repair path.
