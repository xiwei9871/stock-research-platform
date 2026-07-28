# Dashboard Inner/Outer Network Sync Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the 2026-07-27 official Review Queue locally and externally, then prevent stale strategy artifacts from passing readiness or automatic deployment.

**Architecture:** Keep code and strategy artifacts as one immutable release snapshot. Add a publication-policy freshness gate to readiness, make the deployment resolver reject market/artifact date mismatches, and schedule external synchronization after strategy publication and auto-repair. Repair the current runtime using the same validated artifact directory and release revision on both endpoints.

**Tech Stack:** Python/FastAPI, pytest, Bash, launchd, rsync/SSH, Docker Compose, curl/jq.

---

### Task 1: Fail Closed When Strategy Artifacts Lag the Market

**Files:**
- Modify: `src/stock_research/dashboard/readiness.py`
- Test: `tests/test_dashboard_readiness.py`

- [ ] **Step 1: Write the failing readiness test**

Add a test that creates a trusted `2026-07-24` strategy artifact under the selected release root while the platform summary and manifest readiness report `2026-07-27`:

```python
def test_readiness_blocks_publication_when_strategy_artifact_lags_market(tmp_path, monkeypatch):
    release_root = tmp_path / "release"
    status = _write_publishable_strategy_summary(release_root, "2026-07-24")
    manifests = _write_official_manifest_artifacts(release_root, "2026-07-24")
    monkeypatch.setattr(readiness, "load_latest_successful_strategy_daily_eod_status", lambda: status)
    monkeypatch.setattr(readiness, "load_strategy_publication_manifest", lambda **_kwargs: manifests)
    monkeypatch.setattr(
        readiness,
        "load_platform_summary",
        lambda score_version, top_n: {
            "latest_market_date": "2026-07-27",
            "topn_preview": [{"asset_id": "A"}],
        },
    )
    monkeypatch.setattr(readiness, "_load_manifest_modules", lambda: [{"module": "daily_bars"}])
    monkeypatch.setattr(
        readiness,
        "_build_manifest_readiness",
        lambda **_kwargs: {
            "status": "OK",
            "policy": {
                "status": "ready",
                "ready_for_dashboard": True,
                "ready_for_publication": True,
                "blocking_reasons": [],
                "warnings": [],
            },
            "latest_market_date": "2026-07-27",
            "display_trade_date": "2026-07-27",
            "warnings": [],
        },
    )

    payload = readiness.build_platform_readiness(
        runtime_provenance_data={"source_root": str(release_root)}
    )

    assert payload["policy"]["ready_for_dashboard"] is True
    assert payload["policy"]["ready_for_publication"] is False
    assert payload["policy"]["status"] == "blocked"
    assert "strategy_artifact_date=2026-07-24" in payload["policy"]["blocking_reasons"][0]
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_readiness.py::test_readiness_blocks_publication_when_strategy_artifact_lags_market -q
```

Expected: FAIL because the current policy remains publishable.

- [ ] **Step 3: Implement the minimal freshness gate**

Add a helper and apply it after runtime provenance is attached on both readiness return paths:

```python
def _apply_strategy_artifact_freshness_gate(
    payload: dict[str, Any],
    *,
    latest_market_date: str,
    strategy_artifact_date: str,
) -> dict[str, Any]:
    if not latest_market_date or latest_market_date == strategy_artifact_date:
        return payload
    reason = (
        "official strategy artifact is not current: "
        f"latest_market_date={latest_market_date}, "
        f"strategy_artifact_date={strategy_artifact_date or 'missing'}"
    )
    policy = dict(payload.get("policy") or {})
    policy.update(
        {
            "status": "blocked",
            "ready_for_dashboard": True,
            "ready_for_publication": False,
            "blocking_reasons": _dedupe([*(policy.get("blocking_reasons") or []), reason]),
            "warnings": _dedupe([*(policy.get("warnings") or []), reason]),
        }
    )
    payload["policy"] = policy
    payload["warnings"] = _dedupe([*(payload.get("warnings") or []), reason])
    return payload
```

Wrap the two `_with_runtime_provenance(...)` results with this helper.

- [ ] **Step 4: Run focused readiness tests and verify GREEN**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_readiness.py -q
```

Expected: all readiness tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
rtk git add src/stock_research/dashboard/readiness.py tests/test_dashboard_readiness.py
rtk git commit -m "fix: block stale strategy publication readiness"
```

### Task 2: Reject Stale Automatic Deployment and Move Sync After EOD

**Files:**
- Modify: `deploy/sync_dashboard_release.sh`
- Modify: `deploy/launchd/com.stockresearch.dashboard-daily-sync.plist`
- Test: `tests/test_dashboard_release_scripts.py`

- [ ] **Step 1: Change the deployment-resolution test to require exact freshness**

Replace the test that currently accepts artifact date `2026-07-24` while market/display are `2026-07-27` with:

```python
def test_release_sync_rejects_stale_date_from_matching_local_readiness(tmp_path):
    _root, env, log_file = _release_fixture(tmp_path)
    fake_bin = Path(env["PATH"].split(":", 1)[0])
    _write_executable(
        fake_bin / "curl",
        """
        #!/bin/bash
        release_id="$(git -C "$FAKE_RELEASE_ROOT" rev-parse HEAD)"
        printf '{"latest_market_date":"2026-07-27","display_trade_date":"2026-07-27","runtime_provenance":{"release_id":"%s","source_root":"%s","python_package_root":"%s/src/stock_research","strategy_artifact_date":"2026-07-24"}}\n' \
          "$release_id" "$FAKE_RELEASE_ROOT" "$FAKE_RELEASE_ROOT"
        """,
    )

    result = subprocess.run(
        [str(REPO_ROOT / "deploy/sync_dashboard_release.sh")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Unable to resolve a valid EXPECTED_TRADE_DATE" in result.stderr
    assert not log_file.exists() or "rsync" not in log_file.read_text(encoding="utf-8")
```

Extend `test_launchd_template_uses_canonical_repo_not_worktree`:

```python
assert "<integer>22</integer>" in plist
assert "<integer>15</integer>" in plist
assert "<integer>18</integer>" not in plist
```

- [ ] **Step 2: Run the two tests and verify RED**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_dashboard_release_scripts.py::test_release_sync_rejects_stale_date_from_matching_local_readiness \
  tests/test_dashboard_release_scripts.py::test_launchd_template_uses_canonical_repo_not_worktree -q
```

Expected: stale readiness is accepted and the schedule remains 18:30.

- [ ] **Step 3: Tighten the deployment date resolver**

In both the jq resolver and Python fallback in `sync_dashboard_release.sh`, require:

```text
latest_market_date == display_trade_date == strategy_artifact_date
```

The jq selection must include:

```jq
and .latest_market_date == $artifact
and .display_trade_date == $artifact
```

The Python fallback prints the artifact only when market, display, and artifact are all valid and equal.

- [ ] **Step 4: Move the LaunchAgent schedule**

Set:

```xml
<key>Hour</key>
<integer>22</integer>
<key>Minute</key>
<integer>15</integer>
```

- [ ] **Step 5: Run release-script tests and verify GREEN**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_release_scripts.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 2**

```bash
rtk git add deploy/sync_dashboard_release.sh deploy/launchd/com.stockresearch.dashboard-daily-sync.plist tests/test_dashboard_release_scripts.py
rtk git commit -m "fix: synchronize dashboard only after current strategy publication"
```

### Task 3: Repair and Verify the Local Release

**Files:**
- Operational artifact snapshot: `/Users/xiwei/stock_research_release_20260727/outputs/research/strategy_daily_eod/2026-07-27`

- [ ] **Step 1: Validate the source artifact**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python deploy/validate_strategy_release.py \
  --output-dir /Users/xiwei/stock_research/outputs/research/strategy_daily_eod/2026-07-27 \
  --trade-date 2026-07-27
```

Expected: `strategy release contract valid: 2026-07-27`.

- [ ] **Step 2: Copy the immutable artifact snapshot**

```bash
rtk mkdir -p /Users/xiwei/stock_research_release_20260727/outputs/research/strategy_daily_eod/2026-07-27
rtk rsync -a --delete \
  /Users/xiwei/stock_research/outputs/research/strategy_daily_eod/2026-07-27/ \
  /Users/xiwei/stock_research_release_20260727/outputs/research/strategy_daily_eod/2026-07-27/
```

- [ ] **Step 3: Build and restart the complete local release**

Build the frontend with the new branch HEAD as `STOCK_RESEARCH_RELEASE_ID` and `VITE_RELEASE_ID`. Stop only the confirmed API process on port `8765` and static frontend process on port `5174`, then restart both from the selected release root with the same new release ID and frontend metadata file. Do not leave the API and frontend on different commit identities.

- [ ] **Step 4: Run the local release gate**

```bash
BASE_URL=http://127.0.0.1:5174 \
EXPECTED_TRADE_DATE=2026-07-27 \
EXPECTED_RELEASE_ID="$(rtk git rev-parse HEAD)" \
EXPECTED_REMOTE_SOURCE_ROOT=/Users/xiwei/stock_research_release_20260727 \
EXPECTED_REMOTE_PYTHON_PACKAGE_ROOT=/Users/xiwei/stock_research_release_20260727/src/stock_research \
rtk deploy/check_dashboard_release.sh
```

Expected: release metadata, readiness, and three five-row current strategy groups all pass.

### Task 4: Publish and Verify the External Release

**Files:**
- Operational environment: `/Users/xiwei/.stock_research_dashboard_sync.env`

- [ ] **Step 1: Run the canonical external synchronization**

```bash
STOCK_RESEARCH_RELEASE_ROOT=/Users/xiwei/stock_research_release_20260727 \
STRATEGY_OUTPUT_ROOT=/Users/xiwei/stock_research/outputs/research \
EXPECTED_TRADE_DATE=2026-07-27 \
BASE_URL=https://stock.manqiaotechnology.com \
rtk deploy/sync_dashboard_release.sh
```

Expected: artifact validation, frontend build, rsync, Docker Compose recreation, and external release gate all succeed.

- [ ] **Step 2: Compare local and external contracts**

For both endpoints, fetch `/release.json`, `/api/platform/readiness`, and `/api/review-queue?trade_date=2026-07-27&limit=10&lookback_days=90`. Verify identical release IDs and dates, and groups `lhb_shortline`, `mid_trend`, and `tech_bottleneck` each contain five current rows.

### Task 5: Install and Verify the Daily Synchronization Schedule

**Files:**
- Install: `/Users/xiwei/Library/LaunchAgents/com.stockresearch.dashboard-daily-sync.plist`
- Update operational env without displaying secrets: `/Users/xiwei/.stock_research_dashboard_sync.env`

- [ ] **Step 1: Add canonical roots to the private environment**

Ensure these keys exist without printing other values:

```text
STOCK_RESEARCH_RELEASE_ROOT=/Users/xiwei/stock_research_release_20260727
STRATEGY_OUTPUT_ROOT=/Users/xiwei/stock_research/outputs/research
```

- [ ] **Step 2: Install the checked-in LaunchAgent**

```bash
rtk cp deploy/launchd/com.stockresearch.dashboard-daily-sync.plist \
  /Users/xiwei/Library/LaunchAgents/com.stockresearch.dashboard-daily-sync.plist
rtk launchctl bootstrap gui/$(id -u) \
  /Users/xiwei/Library/LaunchAgents/com.stockresearch.dashboard-daily-sync.plist
rtk launchctl enable gui/$(id -u)/com.stockresearch.dashboard-daily-sync
```

If an old service exists, boot it out first and then bootstrap the new plist.

- [ ] **Step 3: Verify scheduler state**

```bash
rtk launchctl print gui/$(id -u)/com.stockresearch.dashboard-daily-sync
```

Expected: the service is enabled and points to the canonical sync entrypoint; the plist schedule is 22:15.

### Task 6: Final Verification and Handoff

**Files:**
- No additional production files unless verification exposes an in-scope defect.

- [ ] **Step 1: Run automated verification**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_dashboard_readiness.py \
  tests/test_dashboard_release_scripts.py \
  tests/test_dashboard_review_queue.py -q
rtk pnpm --dir dashboard test -- --run
rtk pnpm --dir dashboard build
rtk git diff --check
```

Expected: every command exits zero.

- [ ] **Step 2: Verify repository isolation**

Confirm the release branch is clean and the three modified files under `outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1` in the main workspace remain untouched.

- [ ] **Step 3: Record final runtime evidence**

Report:

- local and external release IDs;
- local and external market/display/artifact dates;
- three Review Queue group counts and freshness states;
- LaunchAgent status and schedule;
- commits created and verification commands.
