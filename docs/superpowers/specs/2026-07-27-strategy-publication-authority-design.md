# Strategy Publication Authority and Release-Date Semantics

Date: 2026-07-27

## Context

The review queue root-cause work exposed two competing strategy publication paths:

- `strategy_eod_publish.publish_strategy_eod` is the mature publisher that can produce the required LHB, Mid Trend, and Tech Bottleneck review datasets.
- `strategy_daily_eod.run_strategy_daily_eod` reports four runner statuses but currently uses simplified builders that can report success with zero review rows.

This split permits a false-success state: dependency and runner statuses can be successful while the published review contract is incomplete. It also leaves review-queue artifact paths dependent on the process working directory or a hard-coded main checkout.

On 2026-07-27 before the daily cutoff, the platform market date is 2026-07-27 while the latest publishable strategy date is 2026-07-24. A release gate that requires those dates to be equal incorrectly blocks a valid 2026-07-24 publication.

## Decision

`run_strategy_daily_eod` becomes the single official publication authority. It will adapt the mature publisher into the four-runner status and atomic-publication contract. The finalizer, repair workflow, cron jobs, release scripts, and runtime readers will consume only this authority.

No second publisher may independently write the canonical strategy date directory.

## Publication Flow

1. Resolve an explicit release root and strategy output root. Do not derive artifact locations from the current working directory or a hard-coded checkout.
2. Create a run-ID staging directory on the same filesystem as the canonical date directory.
3. Run the mature fresh strategy engines in staging:
   - `lhb_shortline`
   - `mid_trend`
   - `tech_bottleneck`
   - `midtrend_artifacts`
4. Collect manifest writes until staging validation succeeds. Do not publish successful canonical manifest rows while artifacts are still staged.
5. Require the exact review contract:
   - LHB: 5 unique assets
   - Mid Trend: 5 unique assets
   - Tech Bottleneck: 5 unique assets
   - Each row has the requested trade date, correct strategy ID, rank 1-5, and top-5 tier.
   - Midtrend artifact dependencies are complete and contract-valid.
   - Score audit and module summaries are successful.
6. A runner with zero or fewer than five valid rows is failed or partial; it may never be reported as success.
7. Validate the complete staged release with the same contract used by the deployment gate.
8. Atomically switch the canonical date directory using the existing directory-exchange/current-pointer mechanism.
9. Relocate manifest artifact paths to the canonical output root and persist the data-run manifest only after the atomic switch succeeds.
10. Write the four-runner summary and database status from the final canonical result. Partial or failed runs reference the retained failure audit summary and never replace the previous canonical directory.

## Artifact Root Contract

Artifact paths are resolved against an explicit configured strategy output root.

- Runtime readers receive the release/output root from application state or configuration.
- Relative manifest paths are interpreted relative to that root, then resolved and containment-checked.
- Paths escaping the root, paths that exist only under another checkout, or paths that rely on the process CWD are rejected.
- Tests and release worktrees can use copied artifacts without referring to `/Users/xiwei/stock_research`.

## Finalization and Repair

- Auto-repair fixes prerequisite data, then invokes the single official publication authority at most once.
- A current-run publication receipt binds the canonical summary path, date, run ID, file identity, hash, four runner statuses, and 5/5/5 contract.
- The finalizer validates or safely creates that receipt, validates readiness and the release contract, clears cache, and invokes canonical sync.
- Failure or partial status stops before cache and sync.
- A successful canonical publication must overwrite the temporary partial `ops.strategy_daily_eod_status` state created during diagnosis.

## Release-Date Semantics

The release gate receives an explicit expected strategy date.

Readiness requirements:

- `latest_market_date >= expected_strategy_date`
- `display_trade_date == expected_strategy_date` or `runtime_provenance.strategy_artifact_date == expected_strategy_date`
- Runtime release ID, frontend build ID, source root, package root, and base-image identities match the release.

Review Queue requirements:

- `requested_trade_date == expected_strategy_date`
- top-level `trade_date == expected_strategy_date`
- exactly the three official groups are present
- every group has `count == 5`
- every group has `data_trade_date == expected_strategy_date`
- every group has `freshness_status == "current"`

The gate must not rewrite a request for a newer date to an older artifact date. A request for 2026-07-27 before that date is publishable should remain a 2026-07-27 request with missing data, while the deployment target may still be 2026-07-24.

## Testing

Required regression coverage:

- A runner returning success with zero rows fails the official publication.
- The mature publisher produces an exact 5/5/5 staged release.
- A partial staged run does not replace the previous canonical directory or write successful manifest state.
- Manifest paths are relocated from staging to the canonical root after publication.
- A clean release worktree with copied artifacts returns 5/5/5 without using the main checkout or CWD.
- Finalization calls only one publication authority.
- Release gates accept `latest_market_date > expected_strategy_date` when the display/artifact and Queue dates equal the expected strategy date.
- Release gates reject stale Queue group dates, missing groups, wrong counts, mismatched provenance, or a newer requested date silently rewritten to an older date.

## Rollout

1. Implement and review the unified publication authority and artifact-root contract.
2. Generate a fresh 2026-07-24 canonical publication and verify 5/5/5 locally.
3. Correct the diagnostic partial database status through the successful official publication.
4. Run the complete automated suite and classify only independently verified historical/environmental failures.
5. Create a clean release worktree, install it into the selected Python environment, and start local API/frontend from the same release.
6. Pass local readiness, public `release.json`, and Review Queue gates for 2026-07-24.
7. Remove or migrate the known remote non-Docker process occupying port 8765 only after confirming its command and rollback path.
8. Run the canonical external sync and require the full external release gate before considering rollout complete.
