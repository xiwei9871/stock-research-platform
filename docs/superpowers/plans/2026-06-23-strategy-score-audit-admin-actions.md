# Strategy Score Audit Admin Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an operator-facing anomaly handling layer for strategy score audit warnings so the home dashboard explains what kind of anomaly occurred and what safe next action to take.

**Architecture:** Keep the existing score-audit API unchanged for Phase 1 and add a small frontend classification layer in the home cockpit. This layer maps anomaly types to severity, treatment class, operator copy, and safe actions, then renders a handling panel only when `overall_status = warning`.

**Tech Stack:** React, TypeScript, Vitest, existing dashboard API client, existing Home cockpit UI.

---

## File Structure

- Create: `docs/superpowers/specs/2026-06-23-strategy-score-audit-admin-actions-design.md`
  Purpose: product/design contract for anomaly classes and actions.
- Modify: `dashboard/src/components/HomeCockpit.tsx`
  Purpose: anomaly classification helpers and home handling panel UI.
- Modify: `dashboard/src/styles.css`
  Purpose: operator-facing panel layout and responsive treatment.
- Modify: `dashboard/tests/home-cockpit-score-audit.test.tsx`
  Purpose: verify warning summary, handling panel content, and safe navigation actions.

---

### Task 1: Add Home Cockpit Handling Panel Tests

**Files:**
- Modify: `dashboard/tests/home-cockpit-score-audit.test.tsx`
- Test: `dashboard/tests/home-cockpit-score-audit.test.tsx`

- [ ] **Step 1: Write the failing test for known-observation handling**

```tsx
it('shows an admin-facing anomaly handling panel for known LHB score anomalies', async () => {
  const onNavigate = vi.fn();
  apiMocks.fetchStrategyScoreAudit.mockResolvedValue({
    trade_date: '2026-06-22',
    status: 'success',
    overall_status: 'warning',
    summary_path: '/tmp/strategy_score_audit_summary.json',
    detail_path: '/tmp/strategy_score_audit_detail.csv',
    total_rows: 15,
    selected_rows: 15,
    anomaly_row_count: 5,
    anomaly_counts_by_type: { mapped_score_without_raw_score: 5 },
    strategies: [
      { strategy_id: 'lhb_shortline', anomaly_count: 5, row_count: 5, selected_count: 5 },
      { strategy_id: 'mid_trend', anomaly_count: 0, row_count: 5, selected_count: 5 },
      { strategy_id: 'tech_bottleneck', anomaly_count: 0, row_count: 5, selected_count: 5 }
    ],
    sample_rows: [
      { asset_id: '000960.SZ', anomaly_flags: ['mapped_score_without_raw_score'], strategy_id: 'lhb_shortline' },
      { asset_id: '002691.SZ', anomaly_flags: ['mapped_score_without_raw_score'], strategy_id: 'lhb_shortline' }
    ]
  });

  render(<HomeCockpit onNavigate={onNavigate} />);

  const panel = await screen.findByRole('region', { name: '策略打分审计处理建议' });
  expect(within(panel).getByText('已知观察项')).toBeInTheDocument();
  expect(within(panel).getAllByText('LHB Shortline Combo').length).toBeGreaterThan(0);
  expect(within(panel).getByText('5 条异常')).toBeInTheDocument();
  expect(within(panel).getAllByText('映射分存在但原始分缺失').length).toBeGreaterThan(0);
  expect(within(panel).getByText('000960.SZ')).toBeInTheDocument();
  expect(within(panel).getByText('002691.SZ')).toBeInTheDocument();

  fireEvent.click(within(panel).getByRole('button', { name: '查看复盘队列' }));
  fireEvent.click(within(panel).getByRole('button', { name: '打开策略实验室' }));
  fireEvent.click(within(panel).getByRole('button', { name: '查看生成报告' }));

  expect(onNavigate).toHaveBeenNthCalledWith(1, 'reviewQueue');
  expect(onNavigate).toHaveBeenNthCalledWith(2, 'strategyLab');
  expect(onNavigate).toHaveBeenNthCalledWith(3, 'generatedReports');
});
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm test -- home-cockpit-score-audit.test.tsx
```

Expected: FAIL because `策略打分审计处理建议` is not rendered yet.

- [ ] **Step 3: Commit the failing test**

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
git add dashboard/tests/home-cockpit-score-audit.test.tsx
git commit -m "test: cover strategy audit anomaly handling panel"
```

---

### Task 2: Implement Anomaly Classification And Panel UI

**Files:**
- Modify: `dashboard/src/components/HomeCockpit.tsx`
- Modify: `dashboard/src/styles.css`
- Test: `dashboard/tests/home-cockpit-score-audit.test.tsx`

- [ ] **Step 1: Add anomaly dictionary and helper functions**

```tsx
const STRATEGY_LABELS: Record<string, string> = {
  lhb_shortline: 'LHB Shortline Combo',
  mid_trend: 'Mid Trend Combo',
  tech_bottleneck: 'Tech Bottleneck Combo'
};

function strategyScoreAuditAnomalyLabel(anomalyType: string) {
  const labels: Record<string, string> = {
    mapped_score_without_raw_score: '映射分存在但原始分缺失',
    missing_candidate_source: '候选来源缺失',
    missing_raw_candidate_score: '原始候选分缺失',
    published_score_mismatch: '发布分与规则映射不一致',
    published_display_score_mismatch: '发布分与展示分不一致',
    stale_source: '来源数据过期'
  };
  return labels[anomalyType] ?? anomalyType;
}

function isKnownLhbMappingObservation(audit: StrategyScoreAuditSummary | null) {
  if (!audit || audit.overall_status !== 'warning') return false;
  const anomalyTypes = Object.keys(audit.anomaly_counts_by_type ?? {});
  if (anomalyTypes.length !== 1 || anomalyTypes[0] !== 'mapped_score_without_raw_score') return false;
  return (audit.strategies ?? []).every((strategy) =>
    strategy.strategy_id === 'lhb_shortline' ? strategy.anomaly_count > 0 : strategy.anomaly_count === 0
  );
}
```

- [ ] **Step 2: Render the warning-only handling panel**

```tsx
{scoreAudit?.overall_status === 'warning' ? (
  <section className="workspace-panel audit-action-panel" aria-label="策略打分审计处理建议">
    <div className="section-heading">
      <div>
        <h2>策略打分审计处理建议</h2>
        <p className="muted">
          {isKnownLhbMappingObservation(scoreAudit)
            ? '当前异常集中在 LHB 的已知观察项，可继续使用系统，同时跟踪原始分审计链补齐。'
            : '审计发现异常，请先确认影响范围，再决定是按已知观察项处理还是按系统问题排查。'}
        </p>
      </div>
      <span className={`status-chip ${isKnownLhbMappingObservation(scoreAudit) ? 'neutral' : 'warning'}`}>
        {isKnownLhbMappingObservation(scoreAudit) ? '已知观察项' : '需人工处理'}
      </span>
    </div>

    <div className="audit-action-grid">
      <div className="audit-action-card">
        <span>异常总数</span>
        <strong>{scoreAudit.anomaly_row_count} 条</strong>
      </div>
      {scoreAudit.strategies.filter((strategy) => strategy.anomaly_count > 0).map((strategy) => (
        <div className="audit-action-card" key={strategy.strategy_id}>
          <span>{STRATEGY_LABELS[strategy.strategy_id] ?? strategy.strategy_id}</span>
          <strong>{strategy.anomaly_count} 条异常</strong>
        </div>
      ))}
    </div>

    <div className="tag-stack">
      {Object.entries(scoreAudit.anomaly_counts_by_type ?? {}).map(([anomalyType, count]) => (
        <span className="status-chip warning" key={anomalyType}>
          {`${strategyScoreAuditAnomalyLabel(anomalyType)} ${count} 条`}
        </span>
      ))}
    </div>
  </section>
) : null}
```

- [ ] **Step 3: Add safe action buttons and sample rows**

```tsx
<div className="audit-sample-list" aria-label="审计异常样本">
  {scoreAudit.sample_rows.slice(0, 5).map((row) => (
    <div className="audit-sample-row" key={`${row.strategy_id ?? ''}:${row.asset_id}`}>
      <strong>{row.asset_id}</strong>
      <span>{STRATEGY_LABELS[row.strategy_id ?? ''] ?? row.strategy_id ?? '未知策略'}</span>
      <span>{(row.anomaly_flags ?? []).map((flag) => strategyScoreAuditAnomalyLabel(flag)).join(' / ') || '异常待确认'}</span>
    </div>
  ))}
</div>

<div className="compact-toolbar">
  <button type="button" onClick={() => onNavigate('reviewQueue')}>查看复盘队列</button>
  <button type="button" onClick={() => onNavigate('strategyLab')}>打开策略实验室</button>
  <button type="button" onClick={() => onNavigate('generatedReports')}>查看生成报告</button>
</div>
```

- [ ] **Step 4: Add focused styles**

```css
.audit-action-panel {
  display: grid;
  gap: 10px;
}

.audit-action-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.audit-sample-row {
  display: grid;
  grid-template-columns: 120px minmax(180px, 1fr) minmax(220px, 1.2fr);
  align-items: center;
  gap: 10px;
  border: 1px solid #d6dde6;
  border-radius: 5px;
  background: #ffffff;
  padding: 8px 10px;
}
```

- [ ] **Step 5: Run the focused tests to verify they pass**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm test -- home-cockpit-score-audit.test.tsx home-cockpit.test.tsx app-shell.test.tsx
```

Expected: PASS with the new handling panel test green and no regression in home/app-shell behavior.

- [ ] **Step 6: Commit the UI implementation**

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
git add dashboard/src/components/HomeCockpit.tsx dashboard/src/styles.css dashboard/tests/home-cockpit-score-audit.test.tsx
git commit -m "feat: add strategy audit handling panel on home"
```

---

### Task 3: Verify In Browser

**Files:**
- Test: browser verification only

- [ ] **Step 1: Open the local dashboard and confirm the panel appears**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
node - <<'NODE'
const { chromium } = require('@playwright/test');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });
  await page.goto('http://127.0.0.1:5174/', { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: 'Open Home workspace' }).click();
  await page.getByRole('heading', { name: '策略指挥中心' }).waitFor({ timeout: 10000 });
  const body = await page.locator('body').innerText();
  console.log(JSON.stringify({
    hasAuditCell: body.includes('策略打分审计'),
    hasAuditPanel: body.includes('策略打分审计处理建议'),
    hasKnownObservation: body.includes('已知观察项'),
    hasReviewQueueButton: body.includes('查看复盘队列'),
    hasStrategyLabButton: body.includes('打开策略实验室'),
    hasGeneratedReportsButton: body.includes('查看生成报告')
  }));
  await browser.close();
})().catch((err) => { console.error(err); process.exit(1); });
NODE
```

Expected output:

```json
{"hasAuditCell":true,"hasAuditPanel":true,"hasKnownObservation":true,"hasReviewQueueButton":true,"hasStrategyLabButton":true,"hasGeneratedReportsButton":true}
```

- [ ] **Step 2: Commit after browser verification**

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
git add dashboard/src/components/HomeCockpit.tsx dashboard/src/styles.css dashboard/tests/home-cockpit-score-audit.test.tsx
git commit -m "test: verify score audit handling panel"
```

---

## Self-Review

- Spec coverage:
  - anomaly classification headline: Task 2
  - sample row visibility: Task 2
  - safe actions only: Task 2
  - browser confirmation: Task 3
- Placeholder scan:
  - no TODO/TBD placeholders remain
- Type consistency:
  - `StrategyScoreAuditSummary`, anomaly labels, and `WorkspaceMode` action targets remain aligned with current code
