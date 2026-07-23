# Prod Publish Wrapper Design

**Goal**

Add a tiny operator-facing publish wrapper so daily production sync becomes one command with a trade date argument instead of manually stitching environment variables together.

**Scope**

The wrapper will:

- require one trade-date argument in `YYYY-MM-DD` format;
- load the existing local dashboard sync env file for secrets and overrides;
- call `deploy/sync_dashboard_systemd.sh` with `LATEST_STRATEGY_DAILY_EOD` derived from the trade date;
- run `deploy/check_dashboard_release.sh` against the public site for the same trade date.

The wrapper will not:

- duplicate rsync/systemd publish logic;
- replace `deploy/sync_dashboard_daily.sh`;
- add scheduling or locking behavior.

**Approach Options**

1. Recommended: add `deploy/publish_prod.sh` as a thin shell wrapper around the existing scripts.
This keeps production publish behavior in one place and minimizes new failure modes.

2. Fold the wrapper behavior into `deploy/sync_dashboard_systemd.sh`.
This would reduce file count but mixes “do the sync” with “operator UX and release verification,” which is less clean.

3. Reuse `deploy/sync_dashboard_daily.sh` and switch it to systemd deploy.
This adds extra guards and logging, but it is heavier than the user asked for and less convenient for manual daily publishing.

**Chosen Design**

Create `deploy/publish_prod.sh <trade-date>`. It will source the same local env file used by daily sync, validate that `DASHBOARD_AUTH` exists unless release checks are explicitly skipped, set `LATEST_STRATEGY_DAILY_EOD="strategy_daily_eod/<trade-date>"`, invoke `deploy/sync_dashboard_systemd.sh`, and then run `deploy/check_dashboard_release.sh` with `TRADE_DATE`, `END_DATE`, and the configured `BASE_URL`.

**Testing**

Add a deployment asset test that asserts the new wrapper exists, is executable, validates the date argument, calls the systemd sync script, and wires through the release check.
