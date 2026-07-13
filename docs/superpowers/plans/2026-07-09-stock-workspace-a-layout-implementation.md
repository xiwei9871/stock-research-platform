# Stock Workspace A Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the stock workspace so quote-first stock reading is the default flow, with tech-bottleneck thesis content compressed into a secondary summary layer and evidence wording made user-comprehensible.

**Architecture:** Keep the existing stock workspace route and data contracts, but rearrange visual hierarchy around a quote/chart-first shell. Reuse current data-fetching paths, add small presentation helpers, and tighten component boundaries by making header/tooling, thesis summary, company/business blocks, and evidence wording each independently testable.

**Tech Stack:** React, TypeScript, Vite, Vitest, Testing Library, existing dashboard CSS.

---

## File Structure

**Existing files to modify**

- `dashboard/src/components/StockWorkspace.tsx`
  - Reorder the main page sections.
  - Demote replay/source tooling.
  - Compress thesis summary.
  - Scope evidence wording and tomorrow decision wording.
- `dashboard/src/components/stock-workspace/CompanyBasicsSection.tsx`
  - Keep only human-readable company summaries.
- `dashboard/src/components/stock-workspace/BusinessQualitySection.tsx`
  - Keep compact 60/40 composition/quality layout with expand behavior.
- `dashboard/src/styles.css`
  - Add responsive layout rules for desktop and mobile.
  - Reduce oversized cards and spacing.
- `dashboard/tests/stock-workspace.test.tsx`
  - Add and update page-order, wording, and collapsed-tooling coverage.
- `dashboard/tests/company-basics-section.test.tsx`
  - Keep company summary filtering coverage.
- `dashboard/tests/business-quality-section.test.tsx`
  - Keep top-4-and-expand coverage.

**New test file to create**

- `dashboard/tests/stock-workspace-layout.test.tsx`
  - Focused tests for A-layout ordering, hidden source banner, collapsed replay tools, and mobile-friendly compressed thesis content.

**Reference documents**

- `docs/superpowers/specs/2026-07-09-stock-workspace-a-layout-design.md`
- `docs/superpowers/plans/2026-07-08-stock-workspace-review-redesign.md`
- `docs/superpowers/plans/2026-07-09-stock-workspace-dual-mode-implementation.md`

---

### Task 1: Lock A-layout behavior with focused failing tests

**Files:**
- Create: `dashboard/tests/stock-workspace-layout.test.tsx`
- Modify: `dashboard/tests/stock-workspace.test.tsx`
- Reference: `docs/superpowers/specs/2026-07-09-stock-workspace-a-layout-design.md`

- [ ] **Step 1: Write the failing layout-order and hidden-source tests**

```tsx
import '@testing-library/jest-dom/vitest';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { StockWorkspace } from '../src/components/StockWorkspace';

describe('StockWorkspace A layout', () => {
  it('keeps quote and chart before thesis and evidence sections', async () => {
    const { container } = render(<StockWorkspace initialAssetId="000049.SZ" />);
    await screen.findByRole('region', { name: '今日价格行为' });
    const text = container.textContent ?? '';
    expect(text.indexOf('今日价格行为')).toBeLessThan(text.indexOf('科技卡脖子 thesis 复盘'));
    expect(text.indexOf('科技卡脖子 thesis 复盘')).toBeLessThan(text.indexOf('策略证据摘要'));
  });

  it('does not show verbose source workspace text in the primary header', async () => {
    render(<StockWorkspace initialAssetId="000049.SZ" />);
    await screen.findByRole('heading', { name: /德赛电池/ });
    expect(screen.queryByText(/Tech Bottleneck Candidate Review/)).not.toBeInTheDocument();
    expect(screen.queryByText(/tech_bottleneck_review_universe_frontend_dataset_v1/)).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard
rtk npm test -- --run tests/stock-workspace-layout.test.tsx
```

Expected:

- FAIL because the page still shows the source banner and current section order does not yet match A-layout.

- [ ] **Step 3: Extend existing stock workspace tests for wording expectations**

```tsx
expect(screen.queryByText('来源工作台：Tech Bottleneck Candidate Review')).not.toBeInTheDocument();
expect(screen.queryByText('Tech Bottleneck Source tech_bottleneck_review_universe_frontend_dataset_v1')).not.toBeInTheDocument();
expect(screen.getByText('策略证据摘要')).toBeVisible();
```

- [ ] **Step 4: Run the current stock workspace regression suite**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard
rtk npm test -- --run tests/stock-workspace.test.tsx tests/stock-workspace-layout.test.tsx
```

Expected:

- FAIL in the new layout assertions.
- Existing stock workspace tests may still pass.

- [ ] **Step 5: Commit the failing-test baseline**

```bash
cd /Users/xiwei/stock_research
git add dashboard/tests/stock-workspace-layout.test.tsx dashboard/tests/stock-workspace.test.tsx
git commit -m "test: lock stock workspace A layout expectations"
```

---

### Task 2: Demote source/replay tooling and reorder the main reading flow

**Files:**
- Modify: `dashboard/src/components/StockWorkspace.tsx`
- Modify: `dashboard/src/styles.css`
- Test: `dashboard/tests/stock-workspace-layout.test.tsx`

- [ ] **Step 1: Identify the blocks to move and collapse**

Use the existing `StockWorkspace` structure as the edit target:

```tsx
<header className="workspace-header">...</header>
<details className="stock-load-settings">...</details>
<section className="stock-review-summary">...</section>
```

Target state:

- Remove the verbose source workspace paragraph and duplicate source chip from the default header.
- Keep replay controls in `details`, but collapse them by default and move them below the primary reading blocks.
- Ensure the visual order becomes:
  1. header
  2. quote + tomorrow decision
  3. chart
  4. thesis summary
  5. company/business
  6. evidence
  7. utilities

- [ ] **Step 2: Implement the minimal reorder in `StockWorkspace.tsx`**

```tsx
<section className="stock-primary-stack">
  <section className="workspace-band stock-review-conclusion" role="region" aria-label="明日处理结论">...</section>
  <section className="workspace-band stock-price-behavior" role="region" aria-label="今日价格行为">...</section>
</section>

{isTechBottleneckEntry ? (
  <section className="workspace-band stock-tech-thesis" role="region" aria-label="科技卡脖子 thesis 复盘">...</section>
) : null}

<CompanyBasicsSection ... />
<BusinessQualitySection ... />

<section className="workspace-band stock-evidence-zone" role="region" aria-label="策略证据摘要">...</section>

<details className="stock-load-settings">
  <summary>回放 / 切换设置</summary>
  ...
</details>
```

- [ ] **Step 3: Add the matching CSS shell so the reordered blocks read correctly on desktop and mobile**

```css
.stock-primary-stack {
  display: grid;
  gap: 12px;
}

@media (min-width: 981px) {
  .stock-primary-stack {
    grid-template-columns: minmax(0, 1.5fr) minmax(320px, 0.9fr);
    align-items: start;
  }
}

@media (max-width: 980px) {
  .stock-primary-stack {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 4: Run the focused tests**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard
rtk npm test -- --run tests/stock-workspace-layout.test.tsx tests/stock-workspace.test.tsx
```

Expected:

- PASS for hidden source banner and new section order.

- [ ] **Step 5: Commit the reorder**

```bash
cd /Users/xiwei/stock_research
git add dashboard/src/components/StockWorkspace.tsx dashboard/src/styles.css dashboard/tests/stock-workspace-layout.test.tsx dashboard/tests/stock-workspace.test.tsx
git commit -m "feat: reorder stock workspace to quote-first layout"
```

---

### Task 3: Compress the thesis section for desktop and mobile

**Files:**
- Modify: `dashboard/src/components/StockWorkspace.tsx`
- Modify: `dashboard/src/styles.css`
- Test: `dashboard/tests/stock-workspace.test.tsx`

- [ ] **Step 1: Write the failing thesis-density test**

Add a test that proves the section no longer renders oversized explanatory text:

```tsx
expect(within(thesis).getByText('thesis结论')).toBeVisible();
expect(within(thesis).getByText('瓶颈置信分')).toBeVisible();
expect(within(thesis).getByText('证据质量分')).toBeVisible();
expect(within(thesis).queryByText('research-only · manual review only · no production signal/admission')).not.toBeInTheDocument();
expect(within(thesis).queryByText('pending')).not.toBeInTheDocument();
```

- [ ] **Step 2: Run the test and confirm the old verbose thesis header still fails**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard
rtk npm test -- --run tests/stock-workspace.test.tsx
```

Expected:

- FAIL because the current thesis card still shows verbose helper copy or oversized header content.

- [ ] **Step 3: Replace the thesis header and summary layout with the compact version**

```tsx
<div className="section-heading compact-heading">
  <h2>科技卡脖子复盘摘要</h2>
</div>

<div className="stock-summary-strip compact stock-tech-thesis-metrics">
  <div><span>thesis结论</span><strong>{...}</strong></div>
  <div><span>瓶颈置信分</span><strong>{...}</strong></div>
  <div><span>证据质量分</span><strong>{...}</strong></div>
  <div><span>证据强度</span><strong>{...}</strong></div>
</div>
```

Keep only:

- thesis结论
- 瓶颈置信分
- 证据质量分
- 证据强度
- 当前缺口
- 建议动作
- 研究优先级

- [ ] **Step 4: Add responsive CSS so the thesis card does not overgrow on mobile**

```css
.stock-tech-thesis {
  gap: 10px;
}

.stock-tech-thesis-metrics {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

@media (max-width: 980px) {
  .stock-tech-thesis-metrics,
  .stock-tech-thesis-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .stock-tech-thesis-metrics,
  .stock-tech-thesis-summary-grid {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 5: Run tests**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard
rtk npm test -- --run tests/stock-workspace.test.tsx
```

Expected:

- PASS with compact thesis wording and no verbose raw text.

- [ ] **Step 6: Commit the thesis compression**

```bash
cd /Users/xiwei/stock_research
git add dashboard/src/components/StockWorkspace.tsx dashboard/src/styles.css dashboard/tests/stock-workspace.test.tsx
git commit -m "feat: compress stock workspace thesis summary"
```

---

### Task 4: Make quote + valuation the first-class stock-reading block

**Files:**
- Modify: `dashboard/src/components/StockWorkspace.tsx`
- Test: `dashboard/tests/stock-workspace.test.tsx`

- [ ] **Step 1: Write the failing expectation for quote-first data density**

```tsx
const quote = await screen.findByRole('region', { name: '今日价格行为' });
expect(within(quote).getByText('最新价')).toBeVisible();
expect(within(quote).getByText('换手率')).toBeVisible();
expect(within(quote).getByText('量能/20日均额')).toBeVisible();
expect(within(quote).getByText('总市值')).toBeVisible();
expect(within(quote).getByText('流通市值')).toBeVisible();
expect(within(quote).getByText('PE')).toBeVisible();
expect(within(quote).getByText('PB')).toBeVisible();
```

- [ ] **Step 2: Run the test to confirm quote block is still missing part of the first-screen density**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard
rtk npm test -- --run tests/stock-workspace.test.tsx
```

Expected:

- FAIL if the quote block still splits too much valuation content into later sections.

- [ ] **Step 3: Move valuation metrics into the same quote summary block**

```tsx
const valuationSnapshot = profile?.valuation_snapshot;

<section className="stock-summary-strip compact stock-quote-metrics">
  <div><span>最新价</span><strong>{formatPrice(quoteSnapshot?.close)}</strong></div>
  <div><span>涨跌幅</span><strong>{formatPercentPoints(quoteSnapshot?.pct_chg)}</strong></div>
  <div><span>换手率</span><strong>{formatUnsignedPercentPoints(quoteSnapshot?.turnover_rate)}</strong></div>
  <div><span>量能/20日均额</span><strong>{formatRatio(quoteSnapshot?.amount_ratio_20d)}</strong></div>
  <div><span>总市值</span><strong>{formatChineseAmount(valuationSnapshot?.total_market_cap)}</strong></div>
  <div><span>流通市值</span><strong>{formatChineseAmount(valuationSnapshot?.float_market_cap)}</strong></div>
  <div><span>PE</span><strong>{formatOptionalMetric(valuationSnapshot?.pe_ttm, (value) => value.toFixed(2))}</strong></div>
  <div><span>PB</span><strong>{formatOptionalMetric(valuationSnapshot?.pb, (value) => value.toFixed(2))}</strong></div>
</section>
```

- [ ] **Step 4: Run tests**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard
rtk npm test -- --run tests/stock-workspace.test.tsx
```

Expected:

- PASS with valuation now reading as part of the quote-first block.

- [ ] **Step 5: Commit the quote-density change**

```bash
cd /Users/xiwei/stock_research
git add dashboard/src/components/StockWorkspace.tsx dashboard/tests/stock-workspace.test.tsx
git commit -m "feat: merge valuation into stock quote summary"
```

---

### Task 5: Keep company/business blocks compact and filter raw text

**Files:**
- Modify: `dashboard/src/components/stock-workspace/CompanyBasicsSection.tsx`
- Modify: `dashboard/src/components/stock-workspace/BusinessQualitySection.tsx`
- Modify: `dashboard/src/styles.css`
- Test: `dashboard/tests/company-basics-section.test.tsx`
- Test: `dashboard/tests/business-quality-section.test.tsx`

- [ ] **Step 1: Keep the existing failing tests for clean summary and top-4 composition**

Use these tests as the guardrail:

```tsx
expect(within(overviewCard).getByText('聚焦锂电池封装集成与储能电芯业务，核心客户稳定。')).toBeVisible();
expect(within(overviewCard).queryByText(/深圳市德赛电池科技股份有限公司 2025 年半年度报告全文/)).not.toBeInTheDocument();

expect(within(compositionCard).queryByText('E产品')).not.toBeInTheDocument();
fireEvent.click(within(compositionCard).getByRole('button', { name: '展开更多' }));
expect(within(compositionCard).getByText('E产品')).toBeVisible();
```

- [ ] **Step 2: Run the narrow tests**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard
rtk npm test -- --run tests/company-basics-section.test.tsx tests/business-quality-section.test.tsx
```

Expected:

- PASS if no regressions were introduced by the broader page changes.

- [ ] **Step 3: If needed, keep company summary filtering logic minimal**

```tsx
const overviewLines = [businessSummary, profileSummary]
  .filter((line, index, array) => Boolean(line) && array.indexOf(line) === index && isReadableCompanySummary(line));

{overviewLines.length > 0 ? overviewLines.map((line) => <p key={line}>{line}</p>) : <p>暂无公司业务摘要。</p>}
```

- [ ] **Step 4: If needed, keep business composition in compact 60/40 mode**

```tsx
<div className="stock-business-quality-grid">
  <article className="stock-mini-panel" role="group" aria-label="主营构成卡片">...</article>
  <article className="stock-mini-panel" role="group" aria-label="经营质量卡片">...</article>
</div>
```

```css
.stock-business-quality-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(280px, 1fr);
}
```

- [ ] **Step 5: Commit the compact company/business pass**

```bash
cd /Users/xiwei/stock_research
git add dashboard/src/components/stock-workspace/CompanyBasicsSection.tsx dashboard/src/components/stock-workspace/BusinessQualitySection.tsx dashboard/src/styles.css dashboard/tests/company-basics-section.test.tsx dashboard/tests/business-quality-section.test.tsx
git commit -m "feat: compact company and business sections"
```

---

### Task 6: Scope evidence wording and resolve thesis-vs-evidence ambiguity

**Files:**
- Modify: `dashboard/src/components/StockWorkspace.tsx`
- Test: `dashboard/tests/stock-workspace.test.tsx`

- [ ] **Step 1: Write the failing wording-scope test**

```tsx
const evidence = await screen.findByRole('region', { name: '策略证据摘要' });
expect(within(evidence).getByText('策略证据摘要')).toBeVisible();
expect(screen.queryByText('证据摘要')).not.toBeInTheDocument();
```

Add one assertion that the thesis section still says `证据强度 充分` while the evidence panel label is explicitly strategy-scoped.

- [ ] **Step 2: Run the test and confirm the old generic wording fails**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard
rtk npm test -- --run tests/stock-workspace.test.tsx
```

Expected:

- FAIL because the evidence block is still named too generically.

- [ ] **Step 3: Rename the evidence panel and supporting copy**

```tsx
<section className="workspace-band stock-evidence-zone" role="region" aria-label="策略证据摘要">
  <div className="section-heading">
    <h2>策略证据摘要</h2>
    <span className="muted">仅表示策略证据摘要口径，不等同于科技卡脖子 thesis 证据强度。</span>
  </div>
</section>
```

- [ ] **Step 4: Run tests**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard
rtk npm test -- --run tests/stock-workspace.test.tsx
```

Expected:

- PASS with scoped evidence wording.

- [ ] **Step 5: Commit the evidence wording fix**

```bash
cd /Users/xiwei/stock_research
git add dashboard/src/components/StockWorkspace.tsx dashboard/tests/stock-workspace.test.tsx
git commit -m "feat: scope stock workspace evidence wording"
```

---

### Task 7: Full verification and polish pass

**Files:**
- Modify: `dashboard/src/styles.css`
- Test: `dashboard/tests/stock-workspace-layout.test.tsx`
- Test: `dashboard/tests/company-basics-section.test.tsx`
- Test: `dashboard/tests/business-quality-section.test.tsx`
- Test: `dashboard/tests/stock-workspace.test.tsx`

- [ ] **Step 1: Run the complete stock workspace test set**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard
rtk npm test -- --run tests/stock-workspace-layout.test.tsx tests/company-basics-section.test.tsx tests/business-quality-section.test.tsx tests/stock-workspace.test.tsx
```

Expected:

- PASS with no failures.

- [ ] **Step 2: Run the full dashboard build**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard
rtk npm run build
```

Expected:

- `tsc` succeeds
- `vite build` succeeds
- chunk-size warning may remain, but no build failure

- [ ] **Step 3: Browser-smoke the localhost stock page**

Run:

```bash
cd /Users/xiwei/stock_research
rtk echo "Open http://127.0.0.1:5174/tech-bottleneck/stock/000049?source=tech_bottleneck_review_universe_frontend_dataset_v1 and verify layout"
```

Manual browser checks:

- No source workspace string in the header
- Replay settings collapsed
- Quote/valuation block before thesis
- Chart before company/evidence blocks
- Thesis summary compact on desktop
- No raw report excerpt
- No machine summary string
- No English action sentence
- Evidence block labeled as strategy-scoped

- [ ] **Step 4: Final commit**

```bash
cd /Users/xiwei/stock_research
git add dashboard/src/components/StockWorkspace.tsx dashboard/src/components/stock-workspace/CompanyBasicsSection.tsx dashboard/src/components/stock-workspace/BusinessQualitySection.tsx dashboard/src/styles.css dashboard/tests/stock-workspace-layout.test.tsx dashboard/tests/company-basics-section.test.tsx dashboard/tests/business-quality-section.test.tsx dashboard/tests/stock-workspace.test.tsx
git commit -m "feat: implement stock workspace A layout"
```

---

## Self-Review

### Spec coverage

- Quote-first layout: covered in Task 2 and Task 4
- Desktop/mobile hierarchy: covered in Task 2 and Task 3 CSS steps
- Source/replay demotion: covered in Task 2
- Thesis compression: covered in Task 3
- Company/business compression: covered in Task 5
- Evidence wording clarification: covered in Task 6
- Raw text filtering: covered in Task 3 and Task 5

No uncovered spec section remains.

### Placeholder scan

- No `TODO`, `TBD`, or “appropriate handling” placeholders remain.
- Every task includes explicit files, commands, and code snippets.

### Type consistency

- Stock workspace layout assertions consistently use:
  - `科技卡脖子 thesis 复盘`
  - `今日价格行为`
  - `策略证据摘要`
- Existing helpers retained:
  - `summarizeTechBottleneckNextStep`
  - `reviewConclusionText`
  - `CompanyBasicsSection`
  - `BusinessQualitySection`

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-09-stock-workspace-a-layout-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
