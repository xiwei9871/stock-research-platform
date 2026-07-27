# Review Queue Runtime Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make local and external Review Queue results date-correct, fail-closed on stale strategy data, independent from Stock Workspace chart dates, and verifiably served from one canonical release.

**Architecture:** Introduce an explicit Review Queue date contract with per-strategy data dates, then update React consumers to preserve requested replay state. Split strategy dependency checks by declared requirements, add runtime provenance validation, and replace obsolete-worktree deployment with a guarded canonical release script plus external smoke gates.

**Tech Stack:** Python 3.14, FastAPI, PostgreSQL, pandas, pytest, React 19, TypeScript, Vitest, Vite, Bash, Docker Compose, Nginx, OpenClaw cron/launchd.

---

## File Structure

- `src/stock_research/dashboard/review_queue.py`: requested-date contract, exact-date manifest selection, per-group freshness metadata.
- `dashboard/src/api/types.ts`: Review Queue response/group fields.
- `dashboard/src/components/ReviewQueueWorkspace.tsx`: requested date retention and strategy data-date presentation.
- `dashboard/src/components/StockWorkspace.tsx`: review/chart date decoupling and explicit historical chart state.
- `src/stock_research/strategy_daily_eod.py`: strategy-specific dependency declarations and partial status.
- `src/stock_research/runtime_provenance.py`: release/source/import-root validation.
- `src/stock_research/dashboard/readiness.py`: runtime provenance in readiness output.
- `deploy/sync_dashboard_release.sh`: canonical external sync and restart workflow.
- `deploy/check_dashboard_release.sh`: local/external release and Review Queue smoke gate.
- `deploy/launchd/com.stockresearch.dashboard-daily-sync.plist`: canonical sync schedule template.
- `scripts/run_strategy_daily_eod_cron.sh`: per-strategy status output and canonical import guard.
- `scripts/run_platform_ready_check_cron.sh`: repair-to-publish-to-cache-clear ordering.
- Backend, frontend, script, and deployment tests listed in each task.

### Task 1: Preserve Requested Review Date and Expose Strategy Data Dates

**Files:**
- Modify: `src/stock_research/dashboard/review_queue.py:762-834`
- Test: `tests/test_dashboard_review_queue.py`

- [ ] **Step 1: Write the failing backend tests**

Add tests that call `_strategy_review_queue` with requested date `2026-07-24` and stale rows dated `2026-06-01`:

```python
def test_strategy_review_queue_preserves_requested_date_and_reports_group_data_date():
    rows = [
        {
            "trade_date": "2026-06-01",
            "asset_id": "000001.SZ",
            "strategy_id": "mid_trend",
            "strategy_name": "Mid Trend Combo",
            "rank": 1,
            "score_total": 88.0,
        }
    ]

    result = review_queue._strategy_review_queue(
        rows=rows,
        selected_trade_date="2026-07-24",
        platform_market_date="2026-07-24",
        score_version="strategy_topn",
        lookback_days=90,
    )

    assert result["requested_trade_date"] == "2026-07-24"
    assert result["trade_date"] == "2026-07-24"
    group = next(group for group in result["groups"] if group["strategy_id"] == "mid_trend")
    assert group["data_trade_date"] == "2026-06-01"
    assert group["freshness_status"] == "stale"


def test_strategy_review_queue_marks_empty_official_group_missing():
    result = review_queue._strategy_review_queue(
        rows=[],
        selected_trade_date="2026-07-24",
        platform_market_date="2026-07-24",
        score_version="strategy_topn",
        lookback_days=90,
    )

    assert result["trade_date"] == "2026-07-24"
    assert all(group["freshness_status"] == "missing" for group in result["groups"])
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_review_queue.py -q
```

Expected: failures because `requested_trade_date`, `strategy_id`, `data_trade_date`, and `freshness_status` are absent and the top-level date is rewritten.

- [ ] **Step 3: Implement the date contract**

Add `platform_market_date: str` to `_strategy_review_queue`, pass `summary["latest_market_date"]` from `build_review_queue`, keep `selected_trade_date` as the response date, and enrich every official group:

```python
def _group_freshness(data_trade_date: str, requested_trade_date: str) -> str:
    if not data_trade_date:
        return "missing"
    return "current" if data_trade_date == requested_trade_date else "stale"


groups = []
for strategy_id in ordered_strategy_ids:
    sorted_items = sorted(by_strategy[strategy_id], key=_sort_key)
    data_trade_date = max(
        (str(item.get("latest_trade_date") or item.get("trade_date") or "")[:10] for item in sorted_items),
        default="",
    )
    groups.append(
        {
            "bucket": f"strategy:{strategy_id}",
            "strategy_id": strategy_id,
            "label": labels.get(strategy_id, strategy_id),
            "requested_trade_date": selected_trade_date,
            "data_trade_date": data_trade_date,
            "freshness_status": _group_freshness(data_trade_date, selected_trade_date),
            "count": len(sorted_items),
            "items": sorted_items,
        }
    )

return {
    "requested_trade_date": selected_trade_date,
    "trade_date": selected_trade_date,
    "platform_market_date": platform_market_date or selected_trade_date,
    "data_status": "ready" if groups and all(group["freshness_status"] == "current" for group in groups) else "partial",
    "score_version": score_version,
    "review_mode": "strategy_topn",
    "generated_at": _generated_at(selected_trade_date),
    "groups": groups,
    "warnings": warnings,
}
```

- [ ] **Step 4: Run focused and route tests and verify GREEN**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_review_queue.py tests/test_dashboard_app.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
rtk git add src/stock_research/dashboard/review_queue.py tests/test_dashboard_review_queue.py
rtk git commit -m "fix: preserve review queue requested dates"
```

### Task 2: Fail Closed Instead of Substituting Stale Latest Artifacts

**Files:**
- Modify: `src/stock_research/dashboard/review_queue.py:42-180`
- Test: `tests/test_dashboard_review_queue.py`

- [ ] **Step 1: Write failing selection tests**

```python
def test_default_strategy_queue_does_not_use_stale_fallback_rows(monkeypatch):
    monkeypatch.setattr(review_queue, "load_platform_summary", lambda **_kwargs: {"latest_market_date": "2026-07-24"})
    monkeypatch.setattr(review_queue, "_load_manifest_strategy_rows", lambda **_kwargs: [])
    monkeypatch.setattr(review_queue, "_load_strategy_snapshot_rows", lambda **_kwargs: [])
    monkeypatch.setattr(
        review_queue,
        "load_active_strategy_topn_rows",
        lambda **_kwargs: [{"trade_date": "2026-06-01", "asset_id": "000001.SZ", "strategy_id": "mid_trend"}],
    )

    result = review_queue.build_review_queue()

    assert result["trade_date"] == "2026-07-24"
    assert all(group["count"] == 0 for group in result["groups"])
    assert any("exact-date official strategy manifest unavailable" in warning for warning in result["warnings"])


def test_explicit_historical_replay_accepts_only_exact_date_fallback(monkeypatch):
    monkeypatch.setattr(review_queue, "_load_manifest_strategy_rows", lambda **_kwargs: [])
    monkeypatch.setattr(review_queue, "_load_strategy_snapshot_rows", lambda **_kwargs: [])
    monkeypatch.setattr(
        review_queue,
        "load_active_strategy_topn_rows",
        lambda **_kwargs: [{"trade_date": "2026-06-01", "asset_id": "000001.SZ", "strategy_id": "mid_trend"}],
    )

    result = review_queue.build_review_queue(trade_date="2026-07-24")

    assert all(group["count"] == 0 for group in result["groups"])
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_review_queue.py -q
```

Expected: stale fallback rows are currently returned.

- [ ] **Step 3: Add exact-date filtering and missing groups**

Introduce one helper and call it before returning fallback rows:

```python
def _exact_trade_date_rows(rows: list[dict[str, Any]], trade_date: str) -> list[dict[str, Any]]:
    return [row for row in rows if str(row.get("trade_date") or "")[:10] == trade_date]
```

For strategy mode, use only exact-date rows. When none exist, call:

```python
result = _strategy_review_queue(
    rows=[],
    selected_trade_date=selected_trade_date,
    platform_market_date=str(summary.get("latest_market_date") or selected_trade_date),
    score_version="strategy_topn",
    lookback_days=bounded_lookback_days,
)
```

and append:

```python
warnings = [f"exact-date official strategy manifest unavailable for {selected_trade_date}"]
```

Do not fall through to score Top-N when `review_mode="strategy_topn"`; missing official strategies must remain visibly unavailable.

- [ ] **Step 4: Run tests and verify GREEN**

```bash
rtk .venv/bin/pytest tests/test_dashboard_review_queue.py tests/test_dashboard_readiness.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit Task 2**

```bash
rtk git add src/stock_research/dashboard/review_queue.py tests/test_dashboard_review_queue.py
rtk git commit -m "fix: reject stale strategy queue fallbacks"
```

### Task 3: Keep Replay Input Separate from Strategy Data Freshness

**Files:**
- Modify: `dashboard/src/api/types.ts:2309-2323`
- Modify: `dashboard/src/components/ReviewQueueWorkspace.tsx:14-390`
- Test: `dashboard/tests/review-queue-workspace.test.tsx`

- [ ] **Step 1: Extend the test fixture and add failing UI tests**

Update `makeQueue` with:

```ts
requested_trade_date: '2026-06-08',
platform_market_date: '2026-06-15',
data_status: 'partial',
```

Add group metadata and a replay regression test:

```ts
it('retains the requested replay date when strategy data is stale', async () => {
  apiMocks.fetchReviewQueue
    .mockResolvedValueOnce(makeQueue())
    .mockResolvedValueOnce(
      makeQueue({
        requested_trade_date: '2026-07-24',
        trade_date: '2026-07-24',
        groups: [
          {
            ...makeQueue().groups[0],
            requested_trade_date: '2026-07-24',
            data_trade_date: '2026-06-01',
            freshness_status: 'stale'
          }
        ]
      })
    );

  render(<ReviewQueueWorkspace />);
  await screen.findByText('Strong evidence');
  fireEvent.change(screen.getByLabelText('选择复盘日期'), { target: { value: '2026-07-24' } });
  fireEvent.click(screen.getByRole('button', { name: '回放该日复盘队列' }));

  await waitFor(() => expect(screen.getByLabelText('选择复盘日期')).toHaveValue('2026-07-24'));
  expect(screen.getByText('数据日期 2026-06-01')).toBeInTheDocument();
  expect(screen.getByText('数据过期')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the frontend test and verify RED**

```bash
rtk pnpm --dir dashboard test -- review-queue-workspace.test.tsx
```

Expected: type errors or missing data-date/status elements.

- [ ] **Step 3: Extend types and render requested/data dates separately**

```ts
export type ReviewQueueFreshnessStatus = 'current' | 'stale' | 'missing';

export type ReviewQueueGroup = {
  bucket: string;
  strategy_id?: string;
  label: string;
  requested_trade_date?: string;
  data_trade_date?: string;
  freshness_status?: ReviewQueueFreshnessStatus;
  count: number;
  items: ReviewQueueItem[];
};

export type ReviewQueueResponse = {
  requested_trade_date?: string;
  trade_date: string;
  platform_market_date?: string;
  data_status?: 'ready' | 'partial' | 'missing' | string;
  // existing fields remain
};
```

In `loadQueue`, set the input from the requested date:

```ts
setReplayTradeDate(nextQueue.requested_trade_date ?? nextQueue.trade_date);
```

Render each group with `数据日期`, `数据过期`, or `数据缺失` using `data_trade_date` and `freshness_status`.

- [ ] **Step 4: Run frontend tests and verify GREEN**

```bash
rtk pnpm --dir dashboard test -- review-queue-workspace.test.tsx client.test.ts
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 3**

```bash
rtk git add dashboard/src/api/types.ts dashboard/src/components/ReviewQueueWorkspace.tsx dashboard/tests/review-queue-workspace.test.tsx
rtk git commit -m "fix: separate review request and strategy data dates"
```

### Task 4: Decouple Stock Workspace Review and Chart Dates

**Files:**
- Modify: `dashboard/src/components/StockWorkspace.tsx:474-743`
- Test: `dashboard/tests/stock-workspace.test.tsx`

- [ ] **Step 1: Write the failing historical-handoff test**

```ts
it('keeps a historical review date while loading the chart through the latest platform date', async () => {
  render(
    <StockWorkspace
      initialAssetId="000001.SZ"
      defaultTradeDate="2026-07-24"
      entryContext={{ sourceWorkspace: 'reviewQueue', tradeDate: '2026-05-18' }}
    />
  );

  await waitFor(() =>
    expect(apiMocks.fetchAssetProfile).toHaveBeenCalledWith(
      '000001.SZ',
      '2026-05-18',
      expect.any(String),
      '2026-07-24',
      expect.any(String),
      expect.any(String)
    )
  );
  expect(apiMocks.fetchDailyBars).toHaveBeenCalledWith(
    expect.any(String),
    undefined,
    '2026-07-24',
    expect.any(Object)
  );
  expect(screen.getByLabelText('stock workspace trade date')).toHaveValue('2026-05-18');
  expect(screen.getByLabelText('stock workspace end date')).toHaveValue('2026-07-24');
});
```

Add a second test that edits chart end to `2026-05-18`, submits, and expects `历史回放中 · 截至 2026-05-18`.

- [ ] **Step 2: Run the component test and verify RED**

```bash
rtk pnpm --dir dashboard test -- stock-workspace.test.tsx
```

Expected: the old implementation calls profile/chart APIs with `end_date=2026-05-18`.

- [ ] **Step 3: Split initial review and chart dates**

```ts
const initialReviewDate = entryContext?.tradeDate ?? defaultTradeDate ?? DEFAULT_TRADE_DATE;
const initialChartEndDate = defaultTradeDate ?? DEFAULT_TRADE_DATE;
const initialStartDate = offsetDate(initialChartEndDate, -180);
const [tradeDate, setTradeDate] = useState(initialReviewDate);
const [startDate, setStartDate] = useState(initialStartDate);
const [endDate, setEndDate] = useState(initialChartEndDate);
const historicalChartReplay = endDate < initialChartEndDate;
```

Render the replay chip only when `historicalChartReplay` is true.

- [ ] **Step 4: Run component and AppShell tests and verify GREEN**

```bash
rtk pnpm --dir dashboard test -- stock-workspace.test.tsx app-shell.test.tsx
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 4**

```bash
rtk git add dashboard/src/components/StockWorkspace.tsx dashboard/tests/stock-workspace.test.tsx
rtk git commit -m "fix: decouple stock review and chart dates"
```

### Task 5: Isolate Strategy Dependencies and Report Partial Runs

**Files:**
- Modify: `src/stock_research/strategy_daily_eod.py:20-160`
- Modify: `scripts/run_strategy_daily_eod_cron.sh:20-70`
- Test: `tests/test_strategy_daily_eod.py`
- Test: `tests/test_strategy_daily_eod_scripts.py`

- [ ] **Step 1: Write failing per-strategy dependency tests**

```python
def test_minute5_failure_blocks_only_intraday_strategy(tmp_path, monkeypatch):
    calls = []

    def runner(name):
        def run(**_kwargs):
            calls.append(name)
            return {"status": "success", "review_rows": 5}
        return run

    result = eod.run_strategy_daily_eod(
        trade_date="2026-07-24",
        output_root=tmp_path,
        dependency_checker=lambda **_kwargs: {
            "common": {"status": "success"},
            "intraday": {"status": "failed", "reason": "baostock login failed: 10002007"},
        },
        lhb_runner=runner("lhb"),
        mid_runner=runner("mid"),
        tech_runner=runner("tech"),
        midtrend_artifact_builder=runner("midtrend_artifacts"),
    )

    assert result["strategy_status"]["lhb_shortline"] == "blocked"
    assert result["strategy_status"]["mid_trend"] == "success"
    assert result["strategy_status"]["tech_bottleneck"] == "success"
    assert result["status"] == "partial"
    assert calls == ["mid", "midtrend_artifacts", "tech"]
```

- [ ] **Step 2: Run strategy tests and verify RED**

```bash
rtk .venv/bin/pytest tests/test_strategy_daily_eod.py tests/test_strategy_daily_eod_scripts.py -q
```

Expected: current global dependency check skips every strategy and has no `partial` status.

- [ ] **Step 3: Declare requirements and execute runners independently**

```python
STRATEGY_DEPENDENCIES = {
    "lhb_shortline": frozenset({"common", "intraday"}),
    "mid_trend": frozenset({"common"}),
    "midtrend_artifacts": frozenset({"common"}),
    "tech_bottleneck": frozenset({"common"}),
}


def _blocked_reason(required: frozenset[str], dependency_check: dict[str, Any]) -> str | None:
    failed = [
        f"{name}:{dependency_check[name].get('reason') or dependency_check[name].get('status')}"
        for name in sorted(required)
        if dependency_check.get(name, {}).get("status") != "success"
    ]
    return "; ".join(failed) or None
```

Run each strategy only when `_blocked_reason` returns `None`; otherwise record `blocked` and its reason. Aggregate status is `success`, `partial`, or `failed`.

Update cron summary parsing to print each strategy status and dependency reason.

- [ ] **Step 4: Run strategy tests and verify GREEN**

```bash
rtk .venv/bin/pytest tests/test_strategy_daily_eod.py tests/test_strategy_daily_eod_cli.py tests/test_strategy_daily_eod_scripts.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit Task 5**

```bash
rtk git add src/stock_research/strategy_daily_eod.py scripts/run_strategy_daily_eod_cron.sh tests/test_strategy_daily_eod.py tests/test_strategy_daily_eod_scripts.py
rtk git commit -m "fix: isolate strategy eod dependencies"
```

### Task 6: Add Canonical Runtime Provenance and Import-Root Guard

**Files:**
- Create: `src/stock_research/runtime_provenance.py`
- Modify: `src/stock_research/dashboard/readiness.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_runtime_provenance.py`
- Test: `tests/test_dashboard_readiness.py`

- [ ] **Step 1: Write failing provenance tests**

```python
def test_runtime_provenance_rejects_package_outside_release_root(tmp_path):
    release_root = tmp_path / "release"
    package_file = tmp_path / "other" / "src" / "stock_research" / "__init__.py"
    package_file.parent.mkdir(parents=True)
    package_file.write_text("")

    with pytest.raises(RuntimeError, match="python package root does not match release root"):
        build_runtime_provenance(
            release_root=release_root,
            package_file=package_file,
            release_id="abc123",
            frontend_build_id="abc123",
        )


def test_readiness_contains_runtime_provenance(monkeypatch):
    monkeypatch.setattr(
        readiness,
        "load_platform_summary",
        lambda **_kwargs: {"latest_market_date": "2026-07-24", "topn_preview": [{"asset_id": "A"}]},
    )
    monkeypatch.setattr(readiness, "_load_manifest_modules", lambda: [])
    monkeypatch.setattr(readiness, "runtime_provenance", lambda: {"release_id": "abc123"})
    payload = readiness.build_platform_readiness()
    assert payload["runtime_provenance"]["release_id"] == "abc123"
```

- [ ] **Step 2: Run provenance/readiness tests and verify RED**

```bash
rtk .venv/bin/pytest tests/test_runtime_provenance.py tests/test_dashboard_readiness.py -q
```

Expected: module/function missing.

- [ ] **Step 3: Implement provenance**

```python
from pathlib import Path
import os
import stock_research


def build_runtime_provenance(*, release_root: Path, package_file: Path, release_id: str, frontend_build_id: str) -> dict[str, str]:
    resolved_release = release_root.resolve()
    resolved_package = package_file.resolve()
    expected_source = resolved_release / "src" / "stock_research"
    if expected_source not in resolved_package.parents:
        raise RuntimeError(
            f"python package root does not match release root: release={resolved_release} package={resolved_package}"
        )
    if release_id and frontend_build_id and release_id != frontend_build_id:
        raise RuntimeError(f"frontend/API release mismatch: api={release_id} frontend={frontend_build_id}")
    return {
        "release_id": release_id,
        "source_root": str(resolved_release),
        "python_package_root": str(resolved_package.parent),
        "frontend_build_id": frontend_build_id,
    }


def runtime_provenance() -> dict[str, str]:
    return build_runtime_provenance(
        release_root=Path(os.environ.get("STOCK_RESEARCH_RELEASE_ROOT", Path(__file__).resolve().parents[2])),
        package_file=Path(stock_research.__file__ or ""),
        release_id=os.environ.get("STOCK_RESEARCH_RELEASE_ID", ""),
        frontend_build_id=os.environ.get("STOCK_RESEARCH_FRONTEND_BUILD_ID", ""),
    )
```

Call `runtime_provenance()` during API startup and include its result in readiness responses.

- [ ] **Step 4: Run tests and verify GREEN**

```bash
rtk .venv/bin/pytest tests/test_runtime_provenance.py tests/test_dashboard_readiness.py tests/test_dashboard_app.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit Task 6**

```bash
rtk git add src/stock_research/runtime_provenance.py src/stock_research/dashboard/readiness.py src/stock_research/dashboard/app.py tests/test_runtime_provenance.py tests/test_dashboard_readiness.py
rtk git commit -m "feat: expose and validate runtime provenance"
```

### Task 7: Add Canonical Deployment and Release Smoke Gates

**Files:**
- Create: `deploy/sync_dashboard_release.sh`
- Create: `deploy/check_dashboard_release.sh`
- Create: `deploy/launchd/com.stockresearch.dashboard-daily-sync.plist`
- Test: `tests/test_dashboard_release_scripts.py`
- Modify: `docs/platform_external_access_runbook.md`
- Modify: `docs/canonical-frontend.md`

- [ ] **Step 1: Write failing script-content tests**

```python
from pathlib import Path


def test_release_sync_rejects_worktrees_and_runs_release_gate():
    script = Path("deploy/sync_dashboard_release.sh").read_text()
    assert ".worktrees" in script
    assert "Refusing disposable worktree release root" in script
    assert "deploy/check_dashboard_release.sh" in script
    assert "STOCK_RESEARCH_RELEASE_ID" in script


def test_release_gate_checks_review_queue_counts_and_dates():
    script = Path("deploy/check_dashboard_release.sh").read_text()
    assert "/api/review-queue" in script
    assert "requested_trade_date" in script
    assert "data_trade_date" in script
    assert "runtime_provenance" in script
    assert "count == 5" in script


def test_launchd_template_uses_canonical_repo_not_worktree():
    plist = Path("deploy/launchd/com.stockresearch.dashboard-daily-sync.plist").read_text()
    assert "/Users/xiwei/stock_research/deploy/sync_dashboard_release.sh" in plist
    assert ".worktrees" not in plist
```

- [ ] **Step 2: Run script tests and verify RED**

```bash
rtk .venv/bin/pytest tests/test_dashboard_release_scripts.py -q
```

Expected: files are missing.

- [ ] **Step 3: Implement the guarded deployment script**

The sync script must:

```bash
ROOT="${STOCK_RESEARCH_RELEASE_ROOT:-/Users/xiwei/stock_research}"
case "$ROOT" in
  */.worktrees/*) echo "Refusing disposable worktree release root: $ROOT" >&2; exit 2 ;;
esac

release_id="$(git -C "$ROOT" rev-parse HEAD)"
test -z "$(git -C "$ROOT" status --porcelain --untracked-files=all)" || {
  echo "Refusing dirty release root" >&2
  exit 2
}

package_root="$(STOCK_RESEARCH_RELEASE_ROOT="$ROOT" "$ROOT/.venv/bin/python" -c 'import stock_research; print(stock_research.__file__)')"
case "$package_root" in
  "$ROOT"/src/stock_research/*) ;;
  *) echo "Python import root mismatch: $package_root" >&2; exit 2 ;;
esac

STOCK_RESEARCH_RELEASE_ID="$release_id" VITE_RELEASE_ID="$release_id" rtk pnpm --dir "$ROOT/dashboard" build
```

Then sync backend source, built frontend, and `outputs/research/strategy_daily_eod/<expected-date>` using the existing `REMOTE_USER`, `REMOTE_HOST`, `REMOTE_DIR`, and `SSH_OPTS` environment contract. Restart the two Docker Compose services and call the release check.

The release check must poll readiness for up to 120 seconds, then use `jq -e` to require:

```jq
.latest_market_date == $expected
and .runtime_provenance.release_id == $release
```

For Review Queue require:

```jq
.requested_trade_date == $expected
and .trade_date == $expected
and ([.groups[] | select(.strategy_id == "lhb_shortline" or .strategy_id == "mid_trend" or .strategy_id == "tech_bottleneck")] | length) == 3
and all(.groups[] | select(.strategy_id == "lhb_shortline" or .strategy_id == "mid_trend" or .strategy_id == "tech_bottleneck"); .count == 5 and .data_trade_date == $expected and .freshness_status == "current")
```

- [ ] **Step 4: Run tests, shell syntax, and fixture smoke checks**

```bash
rtk .venv/bin/pytest tests/test_dashboard_release_scripts.py tests/test_platform_external_access_deploy_docs.py -q
rtk bash -n deploy/sync_dashboard_release.sh
rtk bash -n deploy/check_dashboard_release.sh
```

Expected: all pass with exit code 0.

- [ ] **Step 5: Commit Task 7**

```bash
rtk git add deploy/sync_dashboard_release.sh deploy/check_dashboard_release.sh deploy/launchd/com.stockresearch.dashboard-daily-sync.plist tests/test_dashboard_release_scripts.py docs/platform_external_access_runbook.md docs/canonical-frontend.md
rtk git commit -m "feat: add canonical dashboard release gate"
```

### Task 8: Make Repair Publication Atomic and Cache-Safe

**Files:**
- Modify: `src/stock_research/eod_auto_repair.py`
- Modify: `scripts/run_platform_ready_check_cron.sh`
- Modify: `scripts/run_eod_auto_repair_cron.sh`
- Test: `tests/test_eod_auto_repair.py`
- Test: `tests/test_platform_ready_scripts.py`
- Test: `tests/test_eod_auto_repair_scripts.py`

- [ ] **Step 1: Write failing ordering tests**

```python
def test_finalize_repair_publication_orders_publish_cache_and_sync():
    events = []
    result = repair.finalize_repair_publication(
        publish=lambda: events.append("publish") or {"status": "success"},
        clear_cache=lambda: events.append("cache") or True,
        sync_external=lambda: events.append("sync") or True,
    )

    assert result["status"] == "success"
    assert events == ["publish", "cache", "sync"]


def test_finalize_repair_publication_stops_before_cache_when_publish_fails():
    events = []
    result = repair.finalize_repair_publication(
        publish=lambda: events.append("publish") or {"status": "partial"},
        clear_cache=lambda: events.append("cache") or True,
        sync_external=lambda: events.append("sync") or True,
    )

    assert result["status"] == "failed"
    assert events == ["publish"]
```

Extend script tests to require that a failed/partial publication does not call `/api/dashboard/cache/clear` and does not call external sync.

- [ ] **Step 2: Run tests and verify RED**

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair.py tests/test_platform_ready_scripts.py tests/test_eod_auto_repair_scripts.py -q
```

Expected: current orchestration cannot prove publication-before-cache ordering.

- [ ] **Step 3: Implement explicit repair phases**

Record these phases in the repair summary:

```python
repair_phases = {
    "minute5": "pending",
    "strategy_publication": "pending",
    "cache_invalidation": "pending",
    "external_sync": "pending",
}
```

Add `finalize_repair_publication(*, publish, clear_cache, sync_external)` to execute the three callables in order. It returns immediately with `status="failed"` when publication is not successful, and it records the exact phase statuses. Only set `cache_invalidation=success` after `strategy_publication=success`. Only invoke the canonical external sync when platform readiness is `ready` and all official strategy modules are contract-valid.

- [ ] **Step 4: Run repair tests and verify GREEN**

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair.py tests/test_eod_auto_repair_checks.py tests/test_platform_ready_scripts.py tests/test_eod_auto_repair_scripts.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit Task 8**

```bash
rtk git add src/stock_research/eod_auto_repair.py scripts/run_platform_ready_check_cron.sh scripts/run_eod_auto_repair_cron.sh tests/test_eod_auto_repair.py tests/test_platform_ready_scripts.py tests/test_eod_auto_repair_scripts.py
rtk git commit -m "fix: publish repaired strategy data atomically"
```

### Task 9: Full Verification, Runtime Repair, and External Rollout

**Files:**
- Modify only if verification exposes defects in files already listed above.
- Operational inputs: `/Users/xiwei/.stock_research_dashboard_sync.env`, OpenClaw cron job `6c215e10-6963-41bf-9f9b-8bd7a924ca0d`, LaunchAgent `com.stockresearch.dashboard-daily-sync`.

- [ ] **Step 1: Run the complete automated suite**

```bash
rtk .venv/bin/pytest -q
rtk pnpm --dir dashboard test
rtk pnpm --dir dashboard build
rtk git diff --check
```

Expected: every command exits 0.

- [ ] **Step 2: Create a clean canonical release worktree and environment**

```bash
rtk git worktree add /Users/xiwei/stock_research_release_20260727 HEAD
rtk /Users/xiwei/stock_research/.venv/bin/pip install -e /Users/xiwei/stock_research_release_20260727
rtk /Users/xiwei/stock_research/.venv/bin/python -c "import stock_research; print(stock_research.__file__)"
```

Expected: the printed package path is inside the selected release worktree. Before external deployment, set `STOCK_RESEARCH_RELEASE_ROOT` to this exact selected release root; do not use the dirty main tree or an unrelated validation worktree.

- [ ] **Step 3: Restart local API/frontend from the same release**

Stop only the known dashboard PIDs after confirming their commands, then start:

```bash
STOCK_RESEARCH_RELEASE_ROOT=/Users/xiwei/stock_research_release_20260727 \
STOCK_RESEARCH_RELEASE_ID="$(rtk git -C /Users/xiwei/stock_research_release_20260727 rev-parse HEAD)" \
rtk /Users/xiwei/stock_research/.venv/bin/stock-research dashboard-api --host 127.0.0.1 --port 8765
```

and:

```bash
VITE_RELEASE_ID="$(rtk git -C /Users/xiwei/stock_research_release_20260727 rev-parse HEAD)" \
rtk pnpm --dir /Users/xiwei/stock_research_release_20260727/dashboard dev
```

Run them under the existing service supervisor rather than leaving ad-hoc terminal processes after verification.

- [ ] **Step 4: Verify local release**

```bash
EXPECTED_TRADE_DATE=2026-07-24 \
EXPECTED_RELEASE_ID="$(rtk git -C /Users/xiwei/stock_research_release_20260727 rev-parse HEAD)" \
BASE_URL=http://127.0.0.1:5174 \
rtk deploy/check_dashboard_release.sh
```

Expected: release gate passes, with three current five-row groups and matching release IDs.

- [ ] **Step 5: Publish and verify external release**

With the existing sync environment loaded:

```bash
STOCK_RESEARCH_RELEASE_ROOT=/Users/xiwei/stock_research_release_20260727 \
EXPECTED_TRADE_DATE=2026-07-24 \
BASE_URL=https://stock.manqiaotechnology.com \
rtk deploy/sync_dashboard_release.sh
```

Expected: sync, container restart, readiness polling, and external release gate all succeed.

- [ ] **Step 6: Replace obsolete schedules**

Install the canonical plist and enable it only after external verification:

```bash
rtk cp deploy/launchd/com.stockresearch.dashboard-daily-sync.plist /Users/xiwei/Library/LaunchAgents/com.stockresearch.dashboard-daily-sync.plist
rtk launchctl bootstrap gui/$(id -u) /Users/xiwei/Library/LaunchAgents/com.stockresearch.dashboard-daily-sync.plist
rtk launchctl enable gui/$(id -u)/com.stockresearch.dashboard-daily-sync
rtk launchctl print gui/$(id -u)/com.stockresearch.dashboard-daily-sync
```

Keep `com.stockresearch.strategy-eod-publish` disabled because the OpenClaw strategy EOD/repair pipeline owns publication.

- [ ] **Step 7: Verify scheduler state and final external behavior**

```bash
rtk openclaw cron list
rtk curl -sS "https://stock.manqiaotechnology.com/api/review-queue?trade_date=2026-07-24&limit=10&lookback_days=90" | rtk jq '{requested_trade_date,trade_date,groups:[.groups[]|{strategy_id,count,data_trade_date,freshness_status}],warnings}'
rtk curl -sS "https://stock.manqiaotechnology.com/api/platform/readiness" | rtk jq '{latest_market_date,runtime_provenance}'
```

Expected: requested/trade dates are `2026-07-24`, all three groups have five current rows, warnings are empty, and provenance matches the deployed release.

- [ ] **Step 8: Commit any verification-only corrections**

If verification required code corrections, stage only files from Tasks 1-8 and commit:

```bash
rtk git add \
  src/stock_research/dashboard/review_queue.py \
  src/stock_research/dashboard/readiness.py \
  src/stock_research/dashboard/app.py \
  src/stock_research/strategy_daily_eod.py \
  src/stock_research/runtime_provenance.py \
  src/stock_research/eod_auto_repair.py \
  dashboard/src/api/types.ts \
  dashboard/src/components/ReviewQueueWorkspace.tsx \
  dashboard/src/components/StockWorkspace.tsx \
  scripts/run_strategy_daily_eod_cron.sh \
  scripts/run_platform_ready_check_cron.sh \
  scripts/run_eod_auto_repair_cron.sh \
  deploy/sync_dashboard_release.sh \
  deploy/check_dashboard_release.sh \
  deploy/launchd/com.stockresearch.dashboard-daily-sync.plist \
  tests/test_dashboard_review_queue.py \
  tests/test_strategy_daily_eod.py \
  tests/test_strategy_daily_eod_scripts.py \
  tests/test_runtime_provenance.py \
  tests/test_dashboard_readiness.py \
  tests/test_dashboard_release_scripts.py \
  tests/test_eod_auto_repair.py \
  tests/test_platform_ready_scripts.py \
  tests/test_eod_auto_repair_scripts.py \
  dashboard/tests/review-queue-workspace.test.tsx \
  dashboard/tests/stock-workspace.test.tsx \
  docs/platform_external_access_runbook.md \
  docs/canonical-frontend.md
rtk git commit -m "fix: close review queue release verification gaps"
```

If no corrections were needed, do not create an empty commit.
