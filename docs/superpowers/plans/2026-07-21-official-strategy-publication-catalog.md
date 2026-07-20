# Official Strategy Publication Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/api/strategies/catalog` expose the same validated publication identity and performance fields as the official review queue for all runnable official strategies.

**Architecture:** Keep the descriptive static catalog as the source for names, factors, inputs, and defaults. Overlay the validated `list_backtest_strategies()` read model by `strategy_id` at the API boundary so runnable official rows receive fail-closed publication metrics while diagnostic catalog rows remain present and unchanged.

**Tech Stack:** FastAPI, Python, pytest, Playwright.

---

## File Structure

- `src/stock_research/dashboard/backtests.py`: adds the merged published-catalog read model.
- `src/stock_research/dashboard/app.py`: serves the merged catalog.
- `tests/test_dashboard_backtests.py`: proves identity overlay, diagnostic preservation, and fail-closed rows.
- `dashboard/tests/e2e/real/authoritativeSnapshot.ts`: remains the browser acceptance parser.

### Task 1: Add Failing Read-Model Tests

**Files:**
- Modify: `tests/test_dashboard_backtests.py`

- [ ] **Step 1: Add a complete overlay test**

Create a static catalog fixture containing one diagnostic row plus `lhb_shortline`, `mid_trend`, and `tech_bottleneck`. Stub `list_backtest_strategies()` dependencies so each official row has:

```python
{
    "performance_as_of_date": "2026-07-18",
    "total_return_pct": 52.4,
    "contract_id": "lhb_shortline:balanced:v1",
    "publish_id": "lhb-shortline-20260718",
    "artifact_version": "strategy_artifact_v1",
    "contract_status": "success",
}
```

Assert the merged catalog preserves descriptive fields, projects every identity field, retains the diagnostic row, and never emits `175.29` for LHB.

- [ ] **Step 2: Add a fail-closed overlay test**

When an official enriched row has `contract_status="contract_mismatch"`, assert the merged catalog does not restore static `total_return_pct`, `publish_id`, or performance date values.

- [ ] **Step 3: Run focused tests and verify RED**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_dashboard_backtests.py -q
```

Expected: FAIL because no published-catalog merger exists.

### Task 2: Implement The Published Catalog Merger

**Files:**
- Modify: `src/stock_research/dashboard/backtests.py`
- Modify: `src/stock_research/dashboard/app.py`

- [ ] **Step 1: Add `list_published_strategy_catalog`**

```python
def list_published_strategy_catalog() -> list[dict[str, Any]]:
    catalog = list_strategy_catalog()
    published = {row["strategy_id"]: row for row in list_backtest_strategies()}
    return [deepcopy(published.get(row["strategy_id"], row)) for row in catalog]
```

Use existing `deepcopy`; do not mutate static catalog objects. `list_backtest_strategies()` remains the only logic that reads DB/EOD publication artifacts and validates contract identity.

- [ ] **Step 2: Serve the merged read model**

Change `/api/strategies/catalog` in `app.py` to return `list_published_strategy_catalog()`. Keep `/api/backtests/strategies` unchanged.

- [ ] **Step 3: Add an endpoint contract test**

In `tests/test_dashboard_app.py`, monkeypatch `list_published_strategy_catalog` and assert `/api/strategies/catalog` returns its exact rows.

- [ ] **Step 4: Run backend regressions**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_dashboard_backtests.py \
  tests/test_dashboard_review_queue.py \
  tests/test_dashboard_app.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the read model**

```bash
git add src/stock_research/dashboard/backtests.py src/stock_research/dashboard/app.py tests/test_dashboard_backtests.py tests/test_dashboard_app.py
git commit -m "fix: publish official strategy catalog identity"
```

### Task 3: Verify End-To-End Publication Consistency

**Files:**
- No test relaxation allowed.

- [ ] **Step 1: Run the authoritative snapshot test**

```bash
cd dashboard
PLAYWRIGHT_PROFILE=real \
PLAYWRIGHT_DASHBOARD_PORT=5374 \
PLAYWRIGHT_API_PORT=8966 \
pnpm exec playwright test tests/e2e/real/critical-journeys.spec.ts \
  --grep "authoritative publication snapshot" \
  --project=chromium-desktop
```

Expected: PASS for all three official strategy IDs.

- [ ] **Step 2: Run the publication P0 suite**

```bash
cd dashboard
PLAYWRIGHT_PROFILE=mock pnpm exec playwright test tests/e2e/p0/review-publication.spec.ts
```

Expected: PASS, including `+52.40%` and absence of `+175.29%`.

- [ ] **Step 3: Run full affected verification**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_dashboard_backtests.py tests/test_dashboard_review_queue.py -q
cd dashboard && rtk pnpm test -- --run && rtk pnpm build
```

Expected: all commands exit 0.

- [ ] **Step 4: Re-run the frozen Real and Audit profiles under a new audit ID**

The new report must show matching catalog/queue publication identity before baseline promotion.

