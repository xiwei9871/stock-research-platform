# Strategy Publication Authority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the official four-runner EOD command the single atomic publication authority, guarantee an exact 5/5/5 Review Queue contract, resolve artifacts from an explicit release root, and allow a publishable strategy date to trail the latest market date.

**Architecture:** `run_strategy_daily_eod` will call the mature `publish_strategy_eod` inside its existing same-filesystem staging directory while collecting manifest entries instead of committing them. It will validate four runner/dependency status plus the exact Review Queue contract, atomically switch the canonical date directory, relocate paths, and then persist manifest/status state. Runtime readers and release scripts will consume an explicit strategy output root and will never use the process CWD or a hard-coded checkout.

**Tech Stack:** Python 3.12+, pandas, PostgreSQL manifest/status stores, FastAPI, Bash 3.2+, jq, pytest.

---

## File Map

- `src/stock_research/strategy_eod_publish.py`: mature staged publisher; add an explicit result/manifest collection boundary and strict 5/5/5 result metadata.
- `src/stock_research/strategy_daily_eod.py`: official four-runner adapter, staging validation, atomic switch, manifest relocation, and final status persistence.
- `src/stock_research/data_run_manifest.py`: add pure path-relocation support if existing manifest helpers cannot rewrite staged artifact paths safely.
- `src/stock_research/dashboard/review_queue.py`: resolve manifest artifacts from an explicit output root with containment checks.
- `src/stock_research/dashboard/app.py`: pass the validated release/output root into Review Queue loading.
- `deploy/check_dashboard_release.sh`: separate market-date freshness from expected strategy-artifact date.
- `deploy/sync_dashboard_release.sh`: pass the expected strategy date consistently to local and external gates.
- `tests/test_strategy_eod_publish.py`: mature publisher result and manifest-collector tests.
- `tests/test_strategy_daily_eod.py`: official adapter, strict counts, atomic failure, and relocation tests.
- `tests/test_dashboard_review_queue.py`: clean-release artifact-root tests.
- `tests/test_dashboard_release_scripts.py`: release-date semantics and regression tests.
- `tests/test_eod_auto_repair.py`: single publication authority and finalizer regression tests.

### Task 1: Define the Mature Publisher Result Contract

**Files:**
- Modify: `src/stock_research/strategy_eod_publish.py`
- Test: `tests/test_strategy_eod_publish.py`

- [ ] **Step 1: Write failing tests for exact strategy counts and collected manifests**

Add tests that invoke `publish_strategy_eod` with injected strategy/Tech results and a collecting `manifest_upsert`:

```python
def test_publish_strategy_eod_returns_exact_review_counts_and_collected_entries(monkeypatch, tmp_path):
    collected = []
    summary = publish_strategy_eod(
        trade_date="2026-07-24",
        output_root=tmp_path,
        runner=fake_fresh_runner_with_five_rows,
        manifest_upsert=collected.append,
    )

    assert summary["strategy_counts"] == {
        "lhb_shortline": 5,
        "mid_trend": 5,
        "tech_bottleneck": 5,
    }
    assert summary["review_rows"] == 15
    assert summary["publishable"] is True
    assert {entry["module"] for entry in collected} >= {
        "strategy_lhb_shortline",
        "strategy_mid_trend",
        "strategy_tech_bottleneck",
        "review_queue_strategy_manifest",
    }
```

Add a zero-row regression:

```python
def test_publish_strategy_eod_rejects_successful_engine_with_zero_review_rows(monkeypatch, tmp_path):
    with pytest.raises(RuntimeError, match="strategy review contract requires exactly 5 rows"):
        publish_strategy_eod(
            trade_date="2026-07-24",
            output_root=tmp_path,
            runner=fake_runner_with_zero_lhb_rows,
            manifest_upsert=lambda entry: None,
        )
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_strategy_eod_publish.py -q
```

Expected: the new assertions fail because the summary lacks `strategy_counts`/`publishable`, and zero-row results are not rejected at the mature publisher boundary.

- [ ] **Step 3: Implement strict publisher result metadata**

After `_write_review_queue`, compute counts from the final review rows:

```python
strategy_counts = (
    pd.DataFrame(review_rows)
    .groupby("strategy_id")["asset_id"]
    .nunique()
    .astype(int)
    .to_dict()
)
expected_counts = {
    "lhb_shortline": 5,
    "mid_trend": 5,
    "tech_bottleneck": 5,
}
if strategy_counts != expected_counts:
    raise RuntimeError(
        f"strategy review contract requires exactly 5 rows per strategy: {strategy_counts}"
    )
```

Return these fields in the summary:

```python
summary.update(
    {
        "strategy_counts": expected_counts,
        "review_rows": 15,
        "publishable": True,
        "manifest_entries": entries,
    }
)
```

Keep `manifest_upsert` injectable. The official adapter will pass a collector so staged paths are not written to the database before the atomic switch.

- [ ] **Step 4: Run the publisher tests and verify GREEN**

Run the command from Step 2.

Expected: all `tests/test_strategy_eod_publish.py` tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
rtk git add src/stock_research/strategy_eod_publish.py tests/test_strategy_eod_publish.py
rtk git commit -m "fix: enforce mature strategy review contract"
```

### Task 2: Make the Official Four-Runner Command the Atomic Publisher

**Files:**
- Modify: `src/stock_research/strategy_daily_eod.py`
- Modify: `src/stock_research/data_run_manifest.py` only if a focused relocation helper is required
- Test: `tests/test_strategy_daily_eod.py`
- Test: `tests/test_eod_auto_repair.py`

- [ ] **Step 1: Write failing official-adapter tests**

Add a mature-publisher injection to `run_strategy_daily_eod` and test a successful staged release:

```python
def test_official_runner_uses_mature_publisher_once_and_publishes_5x3(tmp_path, monkeypatch):
    calls = []

    def fake_publisher(**kwargs):
        calls.append(kwargs)
        return write_complete_staged_release(kwargs["output_root"], "2026-07-24")

    summary = run_strategy_daily_eod(
        trade_date="2026-07-24",
        output_root=tmp_path,
        dependency_checker=successful_dependency_check,
        publisher=fake_publisher,
        service="test",
    )

    assert len(calls) == 1
    assert summary["status"] == "success"
    assert summary["publishable"] is True
    assert summary["review_rows"] == 15
    assert summary["strategy_status"] == {
        "lhb_shortline": "success",
        "mid_trend": "success",
        "midtrend_artifacts": "success",
        "tech_bottleneck": "success",
    }
```

Add failure/atomicity tests:

```python
def test_official_runner_does_not_replace_canonical_for_zero_row_strategy(tmp_path):
    old = seed_canonical_release(tmp_path, marker="old")
    summary = run_strategy_daily_eod(
        trade_date="2026-07-24",
        output_root=tmp_path,
        dependency_checker=successful_dependency_check,
        publisher=publisher_with_zero_tech_rows,
        service="test",
    )

    assert summary["status"] == "partial"
    assert read_canonical_marker(tmp_path) == old
    assert summary["summary_path"].startswith(str(tmp_path / ".failures"))
```

Add a path-relocation test asserting every persisted manifest `artifact_path` belongs to the canonical date directory and no path contains `.versions`.

Add/adjust an auto-repair test asserting the finalizer calls only `run-strategy-daily-eod`, never `publish_strategy_eod` directly.

- [ ] **Step 2: Run the tests and verify RED**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_strategy_daily_eod.py tests/test_eod_auto_repair.py -q
```

Expected: new mature-publisher injection/count/path assertions fail against the simplified builders.

- [ ] **Step 3: Replace simplified strategy builders with the mature publisher adapter**

Change the official signature to accept the mature publisher for tests:

```python
Publisher = Callable[..., dict[str, Any]]

def run_strategy_daily_eod(
    *,
    trade_date: str,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    dependency_checker: DependencyChecker | None = None,
    publisher: Publisher = publish_strategy_eod,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
```

The production flow must:

```python
manifest_entries: list[dict[str, Any]] = []
publisher_summary = publisher(
    trade_date=trade_date,
    output_root=_publisher_output_root_for_staging(output_dir),
    manifest_upsert=manifest_entries.append,
)
strategy_counts = dict(publisher_summary.get("strategy_counts") or {})
contract_valid = strategy_counts == EXPECTED_STRATEGY_COUNTS
```

Derive the three review runner statuses from exact counts, not from engine return labels:

```python
strategy_status = {
    strategy_id: "success" if strategy_counts.get(strategy_id) == 5 else "failed"
    for strategy_id in ("lhb_shortline", "mid_trend", "tech_bottleneck")
}
strategy_status["midtrend_artifacts"] = (
    "success" if _midtrend_artifacts_valid(publisher_summary, output_dir) else "failed"
)
```

Before committing database manifests, atomically publish the directory and relocate each entry:

```python
_atomic_publish_directory(staged_date_dir, canonical_output_dir)
canonical_entries = [
    relocate_manifest_entry(entry, staging=staged_date_dir, canonical=canonical_output_dir)
    for entry in manifest_entries
]
for entry in canonical_entries:
    upsert_data_run_manifest(entry, service=service)
```

On any exception or invalid count, preserve the previous canonical directory, write a retained failure summary, record failed/partial status, and do not persist successful staged manifest entries.

- [ ] **Step 4: Run the official adapter and repair tests**

Run the command from Step 2.

Expected: all tests pass and the injected publisher is called once per official run.

- [ ] **Step 5: Commit Task 2**

```bash
rtk git add src/stock_research/strategy_daily_eod.py src/stock_research/data_run_manifest.py \
  tests/test_strategy_daily_eod.py tests/test_eod_auto_repair.py
rtk git commit -m "fix: unify official strategy publication"
```

### Task 3: Resolve Review Queue Artifacts from the Release Root

**Files:**
- Modify: `src/stock_research/dashboard/review_queue.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_review_queue.py`
- Test: `tests/test_dashboard_app.py`

- [ ] **Step 1: Write failing clean-release-root tests**

Create a temporary release root containing a copied `outputs/research/strategy_daily_eod/2026-07-24` release and a manifest with relative paths. Change the process CWD to an unrelated empty directory.

```python
def test_review_queue_resolves_relative_artifacts_from_explicit_release_root(tmp_path, monkeypatch):
    release_root = build_release_fixture(tmp_path, trade_date="2026-07-24")
    monkeypatch.chdir(tmp_path / "unrelated-cwd")

    payload = load_review_queue(
        trade_date="2026-07-24",
        strategy_output_root=release_root / "outputs" / "research" / "strategy_daily_eod",
    )

    assert [group["count"] for group in payload["groups"]] == [5, 5, 5]
    assert all(group["data_trade_date"] == "2026-07-24" for group in payload["groups"])
```

Add a traversal test where a manifest path resolves outside the explicit root; it must be rejected and the group must remain missing.

- [ ] **Step 2: Run the tests and verify RED**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_dashboard_review_queue.py tests/test_dashboard_app.py -q
```

Expected: the clean-release fixture returns missing rows or reads from the main checkout because the loader still depends on CWD/hard-coded roots.

- [ ] **Step 3: Add an explicit artifact-root boundary**

Add an optional root parameter at the public loading boundary and thread it into manifest resolution:

```python
def load_review_queue(
    *,
    trade_date: str | None = None,
    score_version: str = "manual_v1",
    limit: int = 10,
    lookback_days: int = 90,
    strategy_output_root: str | Path | None = None,
) -> dict[str, Any]:
```

Resolve relative paths safely:

```python
def _resolve_strategy_artifact(path_value: str, *, strategy_output_root: Path) -> Path:
    candidate = Path(path_value)
    if not candidate.is_absolute():
        candidate = strategy_output_root / candidate
    resolved = candidate.resolve(strict=True)
    resolved.relative_to(strategy_output_root.resolve(strict=True))
    return resolved
```

If existing manifests store paths beginning with `outputs/research/strategy_daily_eod`, strip that known prefix before joining to `strategy_output_root`; do not join the prefix twice.

At app creation, derive the root once from validated runtime provenance:

```python
app.state.strategy_output_root = (
    Path(app.state.runtime_provenance["source_root"])
    / "outputs/research/strategy_daily_eod"
)
```

Pass it to Review Queue requests. Do not recompute provenance per request.

- [ ] **Step 4: Run Review Queue and app tests**

Run the command from Step 2.

Expected: all tests pass, including unrelated-CWD and traversal cases.

- [ ] **Step 5: Commit Task 3**

```bash
rtk git add src/stock_research/dashboard/review_queue.py src/stock_research/dashboard/app.py \
  tests/test_dashboard_review_queue.py tests/test_dashboard_app.py
rtk git commit -m "fix: bind review artifacts to release root"
```

### Task 4: Correct Release-Date Gate Semantics

**Files:**
- Modify: `deploy/check_dashboard_release.sh`
- Modify: `deploy/sync_dashboard_release.sh`
- Test: `tests/test_dashboard_release_scripts.py`
- Modify: `docs/platform_external_access_runbook.md`

- [ ] **Step 1: Write failing gate tests**

Add a fixture where readiness reports market date `2026-07-27`, display/artifact date `2026-07-24`, and Queue is current 5/5/5 for `2026-07-24`:

```python
def test_release_gate_accepts_market_date_after_expected_strategy_date(tmp_path):
    result = run_release_gate_fixture(
        tmp_path,
        latest_market_date="2026-07-27",
        display_trade_date="2026-07-24",
        strategy_artifact_date="2026-07-24",
        expected_trade_date="2026-07-24",
        queue_counts=[5, 5, 5],
    )
    assert result.returncode == 0
```

Add rejection cases for artifact date `2026-06-01`, Queue date rewrite, and a market date earlier than the expected strategy date.

- [ ] **Step 2: Run tests and verify RED**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_dashboard_release_scripts.py -q
```

Expected: the valid 7/27 market + 7/24 strategy fixture fails because the script requires equality.

- [ ] **Step 3: Implement separate market and strategy date checks**

Change the readiness jq predicate to compare ISO dates lexically and require the artifact/display date:

```jq
(.latest_market_date >= $expected)
and (
  .display_trade_date == $strategy_date
  or .runtime_provenance.strategy_artifact_date == $strategy_date
)
and .runtime_provenance.strategy_artifact_date == $strategy_date
```

Keep the Queue predicate exact for the requested strategy date. The sync script must set:

```bash
EXPECTED_STRATEGY_ARTIFACT_DATE="$EXPECTED_TRADE_DATE"
```

for both early and final checks, while allowing readiness `latest_market_date` to be newer.

Update the runbook to state that market date and publishable strategy date are separate concepts.

- [ ] **Step 4: Run script tests and syntax checks**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_dashboard_release_scripts.py -q
rtk bash -n deploy/check_dashboard_release.sh
rtk bash -n deploy/sync_dashboard_release.sh
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit Task 4**

```bash
rtk git add deploy/check_dashboard_release.sh deploy/sync_dashboard_release.sh \
  tests/test_dashboard_release_scripts.py docs/platform_external_access_runbook.md
rtk git commit -m "fix: separate market and strategy release dates"
```

### Task 5: Generate, Verify, and Roll Out the Correct 2026-07-24 Release

**Files:**
- Modify only files above if verification exposes a defect.
- Operational state: local PostgreSQL strategy status, local ports 8765/5174, remote host configured by `.stock_research_dashboard_sync.env`.

- [ ] **Step 1: Run focused regression suites**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_strategy_eod_publish.py \
  tests/test_strategy_daily_eod.py \
  tests/test_eod_auto_repair.py \
  tests/test_dashboard_review_queue.py \
  tests/test_dashboard_app.py \
  tests/test_dashboard_release_scripts.py -q
```

Expected: all pass.

- [ ] **Step 2: Generate a fresh canonical 2026-07-24 publication**

Run the official command from the selected release root with an explicit output root:

```bash
rtk env \
  PYTHONPATH=src \
  STOCK_RESEARCH_RELEASE_ROOT="$PWD" \
  /Users/xiwei/stock_research/.venv/bin/python -m stock_research.strategy_daily_eod \
  --trade-date 2026-07-24 \
  --output-root "$PWD/outputs/research/strategy_daily_eod"
```

Expected: exit 0; summary reports `status=success`, `publishable=true`, `review_rows=15`, four runner statuses success, and the database status is overwritten from the diagnostic partial state.

- [ ] **Step 3: Validate local artifacts and runtime payloads**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python \
  deploy/validate_strategy_release.py \
  --release-root "$PWD" \
  --trade-date 2026-07-24
```

Start a temporary API from the same release on port `8876` and require:

```bash
rtk curl -fsS 'http://127.0.0.1:8876/api/review-queue?trade_date=2026-07-24&limit=10&lookback_days=90' \
  | rtk jq -e '.trade_date == "2026-07-24" and all(.groups[]; .count == 5 and .freshness_status == "current")'
```

Also request `trade_date=2026-07-27` and require the request date remains `2026-07-27` with missing groups; it must not fall back to 2026-07-24.

- [ ] **Step 4: Run full verification on the final HEAD**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest -q
rtk pnpm --dir dashboard test
rtk env \
  VITE_RELEASE_ID="$(rtk git rev-parse HEAD)" \
  VITE_API_BASE_IMAGE='python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7' \
  VITE_FRONTEND_BASE_IMAGE='nginx:1.27.5-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10' \
  pnpm --dir dashboard build
rtk git diff --check
```

Expected: branch-owned regressions are zero. Any remaining failures must be reproduced on the base commit or proven to depend on absent external/history fixtures before rollout.

- [ ] **Step 5: Create and select a clean release worktree**

```bash
rtk git worktree add /Users/xiwei/stock_research_release_20260727 HEAD
rtk /Users/xiwei/stock_research/.venv/bin/pip install -e /Users/xiwei/stock_research_release_20260727
rtk /Users/xiwei/stock_research/.venv/bin/python -c 'import stock_research; print(stock_research.__file__)'
```

Expected: the import path is inside `/Users/xiwei/stock_research_release_20260727/src/stock_research`.

- [ ] **Step 6: Switch local services from the verified release**

Confirm the existing 8765/5174 process commands before stopping only those known PIDs. Start API and frontend from the same release with the same release ID and base-image metadata. Run `deploy/check_dashboard_release.sh` against the local base URL for `2026-07-24`.

Expected: readiness provenance, public `release.json`, and Queue 5/5/5 all pass.

- [ ] **Step 7: Perform guarded external rollout**

Run the canonical sync script with:

```bash
rtk env \
  STOCK_RESEARCH_RELEASE_ROOT=/Users/xiwei/stock_research_release_20260727 \
  STOCK_RESEARCH_PYTHON=/Users/xiwei/stock_research/.venv/bin/python \
  EXPECTED_TRADE_DATE=2026-07-24 \
  deploy/sync_dashboard_release.sh
```

The remote preflight must identify the non-Docker process occupying 8765. Confirm its command and rollback information before stopping it; never stop an unknown process automatically. Re-run canonical sync and require the external release gate to pass.

- [ ] **Step 8: Commit any verification-only defect fixes and record evidence**

If Steps 1-7 expose a code defect, add a failing regression test first, implement the minimal fix, rerun the relevant suite, and commit separately. Do not commit generated outputs unless the repository already versions that exact artifact class.

Record final evidence: release SHA, local/external readiness dates and provenance, Queue group counts/dates, test counts, build result, and any independently verified historical test failures.
