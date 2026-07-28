# Dashboard Inner/Outer Network Sync Repair Design

## Goal

Restore the `2026-07-27` official Review Queue on the local dashboard and publish the same release and strategy artifacts to the external dashboard. Prevent a platform whose market date is newer than its official strategy artifacts from reporting itself as ready.

This repair extends the runtime consistency contract in `2026-07-27-review-queue-runtime-consistency-design.md`; it does not change strategy formulas or candidate selection.

## Confirmed Failure

The investigation on `2026-07-28` established:

- the canonical EOD pipeline successfully produced a contract-valid `2026-07-27` strategy release with 15 Review Queue rows, five for each official strategy;
- the local API/frontend release is revision `7a383247bcb1ecec9b914880041e9513df96f8b2`, but its release-local strategy directory contains artifacts only through `2026-07-24`;
- local readiness reports market date `2026-07-27`, strategy artifact date `2026-07-24`, and nevertheless reports `ready`;
- the external dashboard is still serving an older API/frontend without runtime provenance and returns strategy data from May and June;
- `com.stockresearch.dashboard-daily-sync` is not installed;
- its checked-in schedule is `18:30`, which is earlier than strategy publication at `21:40` and auto-repair at `22:00`, so installing it unchanged would still race ahead of official publication.

## Selected Approach

Use one atomic publication sequence owned by the canonical release:

1. validate the official strategy artifact directory for the target date;
2. synchronize those artifacts into the selected local release root;
3. verify the local API returns the same target date and three current five-row groups;
4. synchronize the identical code revision, frontend build, and artifact directory to the external host;
5. verify local and external release identity, strategy date, and Review Queue contents;
6. install a post-EOD daily synchronization schedule;
7. make readiness fail closed when the market date is newer than the trusted strategy artifact date.

Directly pointing the release API at the mutable main-tree output directory is rejected. The release keeps an immutable, release-local artifact snapshot so local and external runtime provenance remain reproducible.

## Runtime and Artifact Contract

For a publishable dashboard:

```text
latest_market_date == display_trade_date == strategy_artifact_date
frontend_build_id == API release_id
Review Queue requested date == strategy_artifact_date
each official strategy group count == 5
each official strategy group freshness_status == current
```

If `latest_market_date > strategy_artifact_date`, readiness must return a blocked/degraded publication policy with an explicit strategy-artifact freshness reason. It must not report `ready_for_publication=true`.

The Review Queue continues to fail closed: it returns empty `missing` groups for an exact date without an official manifest and never substitutes older candidates as current.

## Local Repair

- Source artifacts: `/Users/xiwei/stock_research/outputs/research/strategy_daily_eod/2026-07-27`.
- Selected release root: `/Users/xiwei/stock_research_release_20260727`.
- Validate the source with `deploy/validate_strategy_release.py` before copying.
- Copy only the target official artifact directory into the release-local canonical strategy root.
- Do not copy unrelated outputs, caches, logs, or the three user-owned modified research CSV files.
- Recheck `/api/platform/readiness`, `/api/review-queue`, and `/release.json` after the local artifact snapshot is present.

## External Publication

Run `deploy/sync_dashboard_release.sh` with:

- `STOCK_RESEARCH_RELEASE_ROOT` set to the selected clean release root;
- `STRATEGY_OUTPUT_ROOT` set to the canonical main output root containing the validated target artifact;
- `EXPECTED_TRADE_DATE=2026-07-27`;
- the existing private sync environment for remote connection and authentication.

The sync command remains responsible for validation, frontend build, source/artifact transfer, container recreation, bounded readiness polling, and final external release checks. A failed gate leaves the deployment reported as failed; it must not be converted to success merely because file transfer completed.

## Daily Synchronization

Install `com.stockresearch.dashboard-daily-sync` only after the manual repair and external verification pass.

Change its schedule from `18:30` to `22:15` Asia/Shanghai, after:

- strategy EOD publication at `21:40`;
- platform auto-repair at `22:00`.

The job uses the canonical release/sync environment and resolves the expected artifact date from readiness only when the trusted artifact is contract-valid. If official artifacts are absent, it exits non-zero without deploying stale data.

## TDD and Verification

### Automated tests

- readiness blocks publication when market date is newer than strategy artifact date;
- readiness remains ready when the dates match;
- the sync script rejects a missing or stale artifact date before any remote mutation;
- the LaunchAgent schedule is `22:15` and points at the canonical sync command;
- existing exact-date Review Queue tests remain green.

### Runtime acceptance

Both local and external endpoints must show:

- release ID `7a383247bcb1ecec9b914880041e9513df96f8b2`;
- market/display/strategy artifact date `2026-07-27`;
- three official Review Queue groups with five current rows each;
- no exact-date manifest warning;
- matching frontend and API release identities.

The installed LaunchAgent must be enabled and visible in `launchctl print`.

## Rollback

- Local: remove only the newly copied `2026-07-27` release-local artifact directory if validation unexpectedly fails; the prior `2026-07-24` snapshot remains intact.
- External: retain the remote release directory and previous container images until the final gate passes; if the gate fails after restart, restore the previously verified release rather than serving a mixed state.
- Scheduler: do not enable the LaunchAgent until both endpoints pass. If its first scheduled run fails, disable it and preserve logs for diagnosis.
