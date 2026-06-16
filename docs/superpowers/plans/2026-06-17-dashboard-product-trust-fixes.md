# Dashboard Product Trust Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dashboard feel trustworthy by explaining stale data, long-running jobs, empty states, and user-facing evidence language clearly in Chinese.

**Architecture:** Keep the current React/FastAPI structure. Add small presentation helpers in existing frontend components, add narrow backend metadata only where the frontend needs source/date/reason fields, and keep technical diagnostics available but not prominent.

**Tech Stack:** FastAPI backend, React + TypeScript frontend, Vitest component tests, pytest backend tests, Vite build.

---

## File Structure

- Modify `dashboard/src/components/StockWorkspace.tsx`: translate user-facing stock workspace copy, map evidence buckets to Chinese, hide snapshot linkage technical warnings behind human-readable wording.
- Modify `dashboard/src/components/FactorLabWorkspace.tsx`: explain why preview is disabled and how to start.
- Modify `dashboard/src/components/WatchlistWorkspace.tsx`: add empty-state explanations for default/system/manual watchlists.
- Modify `dashboard/src/components/GeneratedReportsWorkspace.tsx` and `dashboard/src/components/ReportPanel.tsx`: show report empty-state reasons and current checked date.
- Modify `dashboard/src/components/ReviewQueueWorkspace.tsx`: show platform date, per-strategy data date, source label, and stale warnings.
- Modify `src/stock_research/dashboard/review_queue.py`: include per-group freshness metadata derived from item dates/source types.
- Modify `tests/test_dashboard_review_queue.py` and `dashboard/tests/review-queue-workspace.test.tsx`: cover per-strategy freshness.
- Modify `dashboard/src/components/BacktestLabWorkspace.tsx`: surface background job status, cached-result copy, and disable synchronous-feeling wording.
- Modify `dashboard/src/api/client.ts` and `dashboard/src/api/types.ts`: expose optional job status helpers if the component needs visible job state.
- Modify `dashboard/tests/stock-workspace.test.tsx`, `dashboard/tests/factor-lab-workspace.test.tsx`, `dashboard/tests/watchlist-workspace.test.tsx`, `dashboard/tests/app-shell.test.tsx`, and `dashboard/tests/backtest-lab-workspace.test.tsx`: test the product-facing states.

## Task 1: Stock Workspace Chinese Copy And Diagnostics

**Files:**
- Modify: `dashboard/src/components/StockWorkspace.tsx`
- Test: `dashboard/tests/stock-workspace.test.tsx`

- [ ] **Step 1: Write failing tests**

Add assertions in `renders the stock detail evidence hub sections` or a new focused test:

```tsx
expect(screen.getByText('个股复盘工作台：集中查看走势、策略证据、新闻研报和人工复盘记录。')).toBeInTheDocument();
expect(screen.getByText('证据较薄')).toBeInTheDocument();
expect(screen.queryByText('Single-stock evidence hub for price, factors, news, research reports, and strategy history.')).not.toBeInTheDocument();
expect(screen.queryByText('Thin evidence')).not.toBeInTheDocument();
expect(screen.getByText('未找到复盘快照关联，本次决策仍会保存，但无法追溯到原始复盘队列快照。')).toBeInTheDocument();
expect(screen.queryByText('No review_item_snapshot lookup keys available')).not.toBeInTheDocument();
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pnpm --dir dashboard test -- stock-workspace.test.tsx -t "stock detail evidence hub" --runInBand
```

Expected: FAIL because old English text and technical warnings are still visible.

- [ ] **Step 3: Implement copy mapping**

In `StockWorkspace.tsx`, add helpers:

```ts
function formatEvidenceBucket(bucket: string) {
  if (bucket === 'strong') return '证据较强';
  if (bucket === 'mixed') return '证据混合';
  if (bucket === 'risk_heavy') return '风险较多';
  if (bucket === 'thin') return '证据较薄';
  return bucket;
}

function formatSnapshotWarning(warning: string) {
  if (warning.includes('No review_item_snapshot lookup keys available')) {
    return '未找到复盘快照关联，本次决策仍会保存，但无法追溯到原始复盘队列快照。';
  }
  if (warning.includes('No evidence_digest_snapshot lookup keys available')) {
    return '未找到证据摘要快照关联，本次决策仍会保存，但证据摘要无法做完整追溯。';
  }
  return warning;
}
```

Replace the workspace header paragraph with Chinese copy, render `formatEvidenceBucket(...)`, and wrap warning display through `formatSnapshotWarning(...)`.

- [ ] **Step 4: Run test to verify pass**

Run:

```bash
pnpm --dir dashboard test -- stock-workspace.test.tsx --runInBand
```

Expected: PASS.

## Task 2: Factor Lab, Watchlist, Generated Reports Empty States

**Files:**
- Modify: `dashboard/src/components/FactorLabWorkspace.tsx`
- Modify: `dashboard/src/components/WatchlistWorkspace.tsx`
- Modify: `dashboard/src/components/GeneratedReportsWorkspace.tsx`
- Modify: `dashboard/src/components/ReportPanel.tsx`
- Test: `dashboard/tests/factor-lab-workspace.test.tsx`
- Test: `dashboard/tests/watchlist-workspace.test.tsx`
- Test: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Write failing tests**

Add Factor Lab assertion:

```tsx
expect(screen.getByText('请先选择至少 1 个因子，再预览评分。')).toBeInTheDocument();
expect(screen.getByRole('button', { name: 'Preview Scores' })).toBeDisabled();
```

Add Watchlist empty-state assertion:

```tsx
expect(screen.getByText('当前观察池暂无记录。人工观察标的会在个股工作台点击“观察”后进入这里。')).toBeInTheDocument();
expect(screen.getByText('当前查询：default / 2026-06-08')).toBeInTheDocument();
```

Add Generated Reports empty-state assertion:

```tsx
expect(screen.getByText('当前日期没有生成报告。可能是报告生成任务尚未运行，或报告目录没有命中该日期。')).toBeInTheDocument();
expect(screen.getByText('请尝试查看最近可用报告，或运行报告生成任务。')).toBeInTheDocument();
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pnpm --dir dashboard test -- factor-lab-workspace.test.tsx watchlist-workspace.test.tsx app-shell.test.tsx --runInBand
```

Expected: FAIL on missing explanatory copy.

- [ ] **Step 3: Implement empty-state copy**

In Factor Lab, render the factor-selection instruction when selected factor count is zero. In Watchlist, render the query state and manual-observation explanation when rows are empty and not loading. In ReportPanel/GeneratedReports, replace generic “No reports” with the two-sentence reason copy.

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
pnpm --dir dashboard test -- factor-lab-workspace.test.tsx watchlist-workspace.test.tsx app-shell.test.tsx --runInBand
```

Expected: PASS.

## Task 3: Review Queue Per-Strategy Freshness

**Files:**
- Modify: `src/stock_research/dashboard/review_queue.py`
- Modify: `dashboard/src/components/ReviewQueueWorkspace.tsx`
- Test: `tests/test_dashboard_review_queue.py`
- Test: `dashboard/tests/review-queue-workspace.test.tsx`

- [ ] **Step 1: Write failing backend test**

Add a test asserting each strategy group includes metadata:

```python
assert payload["groups"][0]["data_date"] == "2026-06-05"
assert payload["groups"][0]["source_types"] == ["strategy_artifact"]
assert payload["groups"][0]["freshness_status"] == "stale"
assert "晚于平台日期" in payload["groups"][0]["freshness_note"]
```

- [ ] **Step 2: Write failing frontend test**

Assert Review Queue renders:

```tsx
expect(screen.getByText('平台日期 2026-06-15')).toBeInTheDocument();
expect(screen.getByText('LHB Shortline Combo · 数据日期 2026-06-05 · 历史 artifact')).toBeInTheDocument();
expect(screen.getByText('该策略候选晚于平台日期，请检查候选生成任务。')).toBeInTheDocument();
```

- [ ] **Step 3: Run tests to verify fail**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_dashboard_review_queue.py -q
pnpm --dir dashboard test -- review-queue-workspace.test.tsx --runInBand
```

Expected: FAIL on missing metadata/copy.

- [ ] **Step 4: Implement metadata and UI**

In `_strategy_review_queue`, compute each group’s latest item date and source types. Add:

```python
"data_date": latest_group_date,
"source_types": source_types,
"freshness_status": "stale" if latest_group_date < selected_trade_date else "fresh",
"freshness_note": note,
```

In `ReviewQueueWorkspace.tsx`, show platform date, per-group data date, translated source labels, and stale note.

- [ ] **Step 5: Run tests to verify pass**

Run the same backend and frontend tests. Expected: PASS.

## Task 4: Strategy Lab Background Job Status And Cache Copy

**Files:**
- Modify: `dashboard/src/components/BacktestLabWorkspace.tsx`
- Test: `dashboard/tests/backtest-lab-workspace.test.tsx`

- [ ] **Step 1: Write failing test**

Add a test using a deferred `runBacktest` promise:

```tsx
fireEvent.click(screen.getByRole('button', { name: '提交回测任务' }));
expect(screen.getByText('后台回测任务已提交，运行中请勿重复点击。')).toBeInTheDocument();
expect(screen.getByText('如参数近期已运行，系统会优先返回缓存结果；需要重算时可重新提交。')).toBeInTheDocument();
```

- [ ] **Step 2: Run test to verify fail**

Run:

```bash
pnpm --dir dashboard test -- backtest-lab-workspace.test.tsx -t "background" --runInBand
```

Expected: FAIL on missing Chinese job-status copy.

- [ ] **Step 3: Implement UI copy**

Rename button text to `提交回测任务` / `后台运行中...`. Add a run status panel when `isRunning || isComparing`:

```tsx
<section className="workspace-band backtest-job-status" aria-label="回测任务状态">
  <strong>后台回测任务已提交，运行中请勿重复点击。</strong>
  <p className="muted">如参数近期已运行，系统会优先返回缓存结果；需要重算时可重新提交。</p>
</section>
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
pnpm --dir dashboard test -- backtest-lab-workspace.test.tsx --runInBand
```

Expected: PASS.

## Task 5: Full Text Scan And Regression Verification

**Files:**
- Modify: affected frontend files only if text scan finds remaining high-impact English copy.
- Test: all modified frontend/backend tests.

- [ ] **Step 1: Scan for high-impact leftovers**

Run:

```bash
rg -n "Single-stock evidence hub|Thin evidence|No review_item_snapshot|No evidence_digest|No reports for selected date|No factor values available|Preview Scores|Watchlist" dashboard/src/components src/stock_research/dashboard -S
```

Expected: Remaining matches are either internal names, test-compatible labels, or intentionally preserved English strategy/product names.

- [ ] **Step 2: Run full verification**

Run:

```bash
git diff --check
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_dashboard_review_queue.py tests/test_dashboard_app.py tests/test_dashboard_deployment_assets.py -q
pnpm --dir dashboard test -- --runInBand
pnpm --dir dashboard build
```

Expected: all pass; Vite chunk size warning is acceptable.

- [ ] **Step 3: Browser smoke**

Open `http://127.0.0.1:5174/`, reload, and verify:

- Home loads without API 404 copy.
- Review Queue shows per-strategy dates.
- Stock Workspace shows Chinese intro and review log.
- Factor Lab explains factor selection.
- Watchlist empty state explains what empty means.
- Generated Reports empty state explains why there may be no reports.

- [ ] **Step 4: Commit**

Run:

```bash
git add dashboard/src/components dashboard/tests src/stock_research/dashboard tests docs/superpowers/plans/2026-06-17-dashboard-product-trust-fixes.md
git commit -m "fix: improve dashboard trust and empty states"
```

Expected: one focused commit containing plan, tests, and implementation.

## Self-Review

Spec coverage:
-复盘队列数据偏旧: Task 3.
-Strategy Lab 回测体感: Task 4.
-个股工作台中英混杂和技术提示: Task 1.
-因子实验室前置条件: Task 2.
-Watchlist 0 rows: Task 2.
-Generated Reports 无报告: Task 2.

Placeholder scan:
- No TBD/TODO placeholders are present.

Type consistency:
- Backend metadata names are `data_date`, `source_types`, `freshness_status`, `freshness_note`.
- Frontend decision edit and backtest job types remain unchanged from the previous commit.
