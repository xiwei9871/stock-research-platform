# Stock Workspace Review Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the stock workspace into an action-first review page that answers `明天怎么处理这只票`, while elevating Tech Bottleneck thesis review when the page is opened from the Tech Bottleneck workflow.

**Architecture:** Keep the existing `StockWorkspace` data-fetching flows intact and redesign the page through source-aware presentation helpers, section regrouping, and scoped CSS updates. Use the existing `entryContext` contract to switch between generic review mode and Tech Bottleneck enhanced mode, and validate the new reading order through React tests instead of introducing a second stock page.

**Tech Stack:** React, TypeScript, Vite, Vitest, Testing Library, existing dashboard CSS

---

## File Map

- Modify: `/Users/xiwei/stock_research/dashboard/src/components/StockWorkspace.tsx`
  Responsibility: compute source-aware review summary data, merge Tech Bottleneck top panels, and reorder sections into the approved reading flow.
- Modify: `/Users/xiwei/stock_research/dashboard/src/styles.css`
  Responsibility: add layout and typography rules for the new action-first stock workspace sections on desktop and mobile.
- Modify: `/Users/xiwei/stock_research/dashboard/tests/stock-workspace.test.tsx`
  Responsibility: assert heading order, Tech Bottleneck enhanced mode behavior, and preserved decision-rail workflows.

No new runtime files are required for this phase. Do not add a second stock page.

### Task 1: Add Source-Aware Review Summary Helpers

**Files:**
- Modify: `/Users/xiwei/stock_research/dashboard/tests/stock-workspace.test.tsx`
- Modify: `/Users/xiwei/stock_research/dashboard/src/components/StockWorkspace.tsx`

- [ ] **Step 1: Write the failing test**

Add this test near the existing `StockWorkspace` review-layout coverage in `/Users/xiwei/stock_research/dashboard/tests/stock-workspace.test.tsx`:

```tsx
it('renders an action-first review summary before quote and evidence sections', async () => {
  render(<StockWorkspace initialAssetId="000001.SZ" />);

  const summary = await screen.findByRole('region', { name: '明日处理结论' });
  const quote = await screen.findByRole('region', { name: '今日价格行为' });
  const evidence = await screen.findByRole('region', { name: '支撑证据' });

  expect(summary).toBeInTheDocument();
  expect(within(summary).getByText('明日处理建议')).toBeVisible();
  expect(within(summary).getByText('一句话结论')).toBeVisible();
  expect(within(summary).getByText('结论置信度')).toBeVisible();

  const summaryOrder = summary.compareDocumentPosition(quote);
  const quoteOrder = quote.compareDocumentPosition(evidence);
  expect(summaryOrder & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(quoteOrder & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard && rtk npm test -- --run tests/stock-workspace.test.tsx -t "renders an action-first review summary before quote and evidence sections"
```

Expected: FAIL because `明日处理结论`, `今日价格行为`, and `支撑证据` regions do not exist yet.

- [ ] **Step 3: Write minimal implementation**

In `/Users/xiwei/stock_research/dashboard/src/components/StockWorkspace.tsx`, add focused helpers above `export function StockWorkspace(...)`:

```ts
function isTechBottleneckEnhanced(entryContext: StockEntryContext) {
  return entryContext.sourceWorkspace === 'techBottleneck';
}

function reviewActionLabel(reviewMetrics: ReturnType<typeof buildReviewMetrics>, digest: EvidenceDigestResponse | null) {
  if (digest?.bucket === 'risk_heavy') return '等待确认';
  if (reviewMetrics.highDrawdown != null && reviewMetrics.highDrawdown <= -0.08) return '降级观察';
  if (reviewMetrics.dayReturn != null && reviewMetrics.dayReturn > 0.015) return '继续跟踪';
  return '继续观察';
}

function reviewConfidenceLabel(
  reviewMetrics: ReturnType<typeof buildReviewMetrics>,
  entryContext: StockEntryContext,
  digest: EvidenceDigestResponse | null
) {
  const digestScore = typeof digest?.score === 'number' ? digest.score : null;
  const bottleneckScore =
    typeof entryContext.bottleneckConfidenceScore === 'number' ? entryContext.bottleneckConfidenceScore : null;
  const baseline = digestScore ?? bottleneckScore ?? 50;
  if (baseline >= 75) return '较高';
  if (baseline >= 55) return '中等';
  if (reviewMetrics.highDrawdown != null && reviewMetrics.highDrawdown <= -0.08) return '偏低';
  return '待确认';
}

function reviewConclusionText(
  reviewMetrics: ReturnType<typeof buildReviewMetrics>,
  entryContext: StockEntryContext,
  digest: EvidenceDigestResponse | null
) {
  if (entryContext.sourceWorkspace === 'techBottleneck' && entryContext.evidenceGapNote) {
    return '卡脖子 thesis 仍可跟踪，但明日优先验证缺失证据。';
  }
  if (reviewMetrics.state === '加速') return '走势仍在强化，明日优先观察延续性与量价匹配。';
  if (reviewMetrics.state === '回撤') return '高位回撤压力较大，明日先判断是否转弱再决定是否继续跟踪。';
  if (digest?.bucket === 'strong') return '证据面偏强，明日重点看价格是否确认。';
  return '暂无单边结论，明日结合价格行为与证据变化继续复盘。';
}
```

Then compute these values inside `StockWorkspace` before `return (...)`:

```ts
const isTechBottleneckMode = isTechBottleneckEnhanced(currentEntryContext);
const reviewAction = reviewActionLabel(reviewMetrics, visibleEvidenceDigest);
const reviewConfidence = reviewConfidenceLabel(reviewMetrics, currentEntryContext, visibleEvidenceDigest);
const reviewConclusion = reviewConclusionText(reviewMetrics, currentEntryContext, visibleEvidenceDigest);
```

Replace the current `策略复盘摘要` section with a new top section:

```tsx
<section className="workspace-band stock-review-conclusion" role="region" aria-label="明日处理结论">
  <div className="section-heading">
    <div>
      <h2>明日处理结论</h2>
      <p className="muted">
        {identityName} · {profile.canonical_asset_id} · 复盘日 {tradeDate}
      </p>
    </div>
    <span className="status-chip">{reviewAction}</span>
  </div>
  <div className="stock-summary-strip stock-review-conclusion-metrics">
    <div>
      <span>明日处理建议</span>
      <strong>{reviewAction}</strong>
    </div>
    <div>
      <span>一句话结论</span>
      <strong>{reviewConclusion}</strong>
    </div>
    <div>
      <span>结论置信度</span>
      <strong>{reviewConfidence}</strong>
    </div>
  </div>
</section>
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard && rtk npm test -- --run tests/stock-workspace.test.tsx -t "renders an action-first review summary before quote and evidence sections"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add dashboard/src/components/StockWorkspace.tsx dashboard/tests/stock-workspace.test.tsx
git commit -m "feat: add action-first stock review summary"
```

### Task 2: Merge Tech Bottleneck Top Panels Into One Thesis Section

**Files:**
- Modify: `/Users/xiwei/stock_research/dashboard/tests/stock-workspace.test.tsx`
- Modify: `/Users/xiwei/stock_research/dashboard/src/components/StockWorkspace.tsx`

- [ ] **Step 1: Write the failing test**

Add this test near the existing Tech Bottleneck entry tests:

```tsx
it('renders a single tech bottleneck thesis section in enhanced mode', async () => {
  const entryContext = {
    sourceWorkspace: 'techBottleneck' as const,
    stockName: '北方华创',
    reviewStatus: 'not_reviewed',
    sourceGroup: 'seed_tier_a',
    previousTier: 'Tier A',
    evidenceStrength: 'pending_primary_source',
    bottleneckRelevance: 'likely_core_pending',
    researchPriorityScore: 92,
    finalManualApprovalCategory: 'likely_hard_tech_pending_evidence',
    evidenceCategory: 'semiconductor_equipment_or_material',
    nextAction: 'manual review and evidence backfill',
    rationale: '核心设备链条相关，但一手来源待补齐。',
    reportStatus: 'partial_primary_source_missing',
    bottleneckConfidenceScore: 69,
    evidenceQualityScore: 33,
    reportReviewDecision: 'evidence_required',
    evidenceGapNote: 'primary source fields require follow-up'
  };

  render(<StockWorkspace initialAssetId="002371.SZ" entryContext={entryContext} />);

  const thesis = await screen.findByRole('region', { name: '科技卡脖子 thesis 复盘' });
  expect(thesis).toBeInTheDocument();
  expect(within(thesis).getByText('thesis 判断')).toBeVisible();
  expect(within(thesis).getByText('证据缺口')).toBeVisible();
  expect(within(thesis).getByText('下一步验证')).toBeVisible();
  expect(screen.queryByRole('region', { name: '技术瓶颈候选上下文' })).not.toBeInTheDocument();
  expect(screen.queryByRole('region', { name: 'Tech Bottleneck Report panel' })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard && rtk npm test -- --run tests/stock-workspace.test.tsx -t "renders a single tech bottleneck thesis section in enhanced mode"
```

Expected: FAIL because the page still renders two separate Tech Bottleneck panels.

- [ ] **Step 3: Write minimal implementation**

In `/Users/xiwei/stock_research/dashboard/src/components/StockWorkspace.tsx`, remove the two top-level Tech Bottleneck sections and replace them with one merged section rendered when `isTechBottleneckMode` is true:

```tsx
{isTechBottleneckMode ? (
  <section className="workspace-band stock-tech-thesis" role="region" aria-label="科技卡脖子 thesis 复盘">
    <div className="section-heading">
      <div>
        <h2>科技卡脖子 thesis 复盘</h2>
        <p className="muted">Research-only · manual review only · no production signal/admission</p>
      </div>
      <span className="status-chip neutral">{currentEntryContext.reviewStatus ?? 'not_reviewed'}</span>
    </div>
    <div className="stock-summary-strip stock-tech-thesis-metrics">
      <div>
        <span>thesis 判断</span>
        <strong>{currentEntryContext.bottleneckRelevance ?? '-'}</strong>
      </div>
      <div>
        <span>bottleneck_confidence_score</span>
        <strong>{formatReportScore(currentEntryContext.bottleneckConfidenceScore)}</strong>
      </div>
      <div>
        <span>evidence_quality_score</span>
        <strong>{formatReportScore(currentEntryContext.evidenceQualityScore)}</strong>
      </div>
      <div>
        <span>report_status</span>
        <strong>{currentEntryContext.reportStatus ?? '-'}</strong>
      </div>
      <div>
        <span>证据缺口</span>
        <strong>{currentEntryContext.evidenceGapNote ?? '-'}</strong>
      </div>
      <div>
        <span>下一步验证</span>
        <strong>{currentEntryContext.nextAction ?? '-'}</strong>
      </div>
    </div>
    <div className="stock-thesis-grid">
      <article>
        <span>来源</span>
        <strong>{currentEntryContext.sourceGroup ?? '-'}</strong>
      </article>
      <article>
        <span>原 Tier</span>
        <strong>{currentEntryContext.previousTier ?? '-'}</strong>
      </article>
      <article>
        <span>研究优先级</span>
        <strong>{formatResearchPriorityScore(currentEntryContext.researchPriorityScore)}</strong>
      </article>
      <article>
        <span>人工审批分类</span>
        <strong>{currentEntryContext.finalManualApprovalCategory ?? '-'}</strong>
      </article>
    </div>
    {currentEntryContext.rationale ? <p>{currentEntryContext.rationale}</p> : null}
    {currentEntryContext.primarySourceUrl ? (
      <a href={currentEntryContext.primarySourceUrl} target="_blank" rel="noreferrer">
        打开 primary source
      </a>
    ) : null}
  </section>
) : null}
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard && rtk npm test -- --run tests/stock-workspace.test.tsx -t "renders a single tech bottleneck thesis section in enhanced mode"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add dashboard/src/components/StockWorkspace.tsx dashboard/tests/stock-workspace.test.tsx
git commit -m "feat: merge tech bottleneck thesis review section"
```

### Task 3: Reframe Quote, Evidence, And Context Into Review Order

**Files:**
- Modify: `/Users/xiwei/stock_research/dashboard/tests/stock-workspace.test.tsx`
- Modify: `/Users/xiwei/stock_research/dashboard/src/components/StockWorkspace.tsx`

- [ ] **Step 1: Write the failing test**

Add this test:

```tsx
it('groups quote, evidence, and background sections by review flow', async () => {
  render(<StockWorkspace initialAssetId="000001.SZ" />);

  const behavior = await screen.findByRole('region', { name: '今日价格行为' });
  const evidence = await screen.findByRole('region', { name: '支撑证据' });
  const background = await screen.findByRole('region', { name: '基本面与档案' });

  expect(within(behavior).getByText('今日价格行为')).toBeVisible();
  expect(within(evidence).getByText('相关新闻')).toBeVisible();
  expect(within(evidence).getByText('Evidence Digest')).toBeVisible();
  expect(within(background).getByText('规模估值')).toBeVisible();
  expect(within(background).getByText('股票简况')).toBeVisible();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard && rtk npm test -- --run tests/stock-workspace.test.tsx -t "groups quote, evidence, and background sections by review flow"
```

Expected: FAIL because the current sections still use `行情快照`, `Price & Events`, and separate article blocks without the new region structure.

- [ ] **Step 3: Write minimal implementation**

In `/Users/xiwei/stock_research/dashboard/src/components/StockWorkspace.tsx`:

1. Rename and keep the quote dossier as `今日价格行为`
2. Wrap digest/news/reports/market/signal cards inside one shared `支撑证据` region
3. Wrap valuation/company profile cards inside `基本面与档案`

Use this structure:

```tsx
<section className="workspace-band stock-price-behavior" role="region" aria-label="今日价格行为">
  <div className="section-heading">
    <div>
      <h2>今日价格行为</h2>
      <p className="muted">{quoteSnapshot?.trade_date ?? endDate} · {reviewMetrics.state}</p>
    </div>
    <span className="status-chip">{reviewMetrics.state}</span>
  </div>
  {/* keep quote metrics + chart here */}
</section>

<section className="stock-evidence-zone" role="region" aria-label="支撑证据">
  <div className="section-heading">
    <div>
      <h2>支撑证据</h2>
      <p className="muted">用新闻、研报、Digest、策略信号和市场环境解释明日处理建议。</p>
    </div>
  </div>
  {/* move Evidence Digest, 相关新闻, 研报覆盖, 个股市场环境, 策略信号 into this section */}
</section>

<section className="stock-background-zone" role="region" aria-label="基本面与档案">
  <div className="section-heading">
    <div>
      <h2>基本面与档案</h2>
      <p className="muted">用于判断这只票是否值得继续投入研究时间。</p>
    </div>
  </div>
  {/* move 规模估值 and 股票简况 here */}
</section>
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard && rtk npm test -- --run tests/stock-workspace.test.tsx -t "groups quote, evidence, and background sections by review flow"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add dashboard/src/components/StockWorkspace.tsx dashboard/tests/stock-workspace.test.tsx
git commit -m "feat: reorder stock workspace into review evidence flow"
```

### Task 4: Update CSS And Preserve Decision Rail Usability

**Files:**
- Modify: `/Users/xiwei/stock_research/dashboard/tests/stock-workspace.test.tsx`
- Modify: `/Users/xiwei/stock_research/dashboard/src/styles.css`
- Modify: `/Users/xiwei/stock_research/dashboard/src/components/StockWorkspace.tsx`

- [ ] **Step 1: Write the failing test**

Add this test:

```tsx
it('keeps the review action rail available after the redesign', async () => {
  render(<StockWorkspace initialAssetId="000001.SZ" />);

  const decisionRail = await screen.findByRole('region', { name: '复盘决策栏' });
  expect(within(decisionRail).getByText('复盘操作')).toBeVisible();
  expect(within(decisionRail).getByText('复盘日志')).toBeVisible();
  expect(within(decisionRail).getByRole('button', { name: /打开新闻/ })).toBeVisible();
  expect(within(decisionRail).getByRole('button', { name: /打开研报/ })).toBeVisible();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard && rtk npm test -- --run tests/stock-workspace.test.tsx -t "keeps the review action rail available after the redesign"
```

Expected: FAIL if the rail structure or labels drift during the regrouping.

- [ ] **Step 3: Write minimal implementation**

In `/Users/xiwei/stock_research/dashboard/src/styles.css`, add focused styles:

```css
.stock-review-conclusion,
.stock-tech-thesis,
.stock-price-behavior,
.stock-evidence-zone,
.stock-background-zone {
  display: grid;
  gap: 12px;
}

.stock-review-conclusion-metrics,
.stock-tech-thesis-metrics {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.stock-thesis-grid,
.stock-background-zone .stock-dossier-support,
.stock-evidence-zone .stock-evidence-grid {
  display: grid;
  gap: 12px;
}

.stock-evidence-zone .stock-evidence-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

@media (max-width: 900px) {
  .stock-review-conclusion-metrics,
  .stock-tech-thesis-metrics,
  .stock-evidence-zone .stock-evidence-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .stock-detail-layout {
    grid-template-columns: minmax(0, 1fr);
  }
}
```

In `/Users/xiwei/stock_research/dashboard/src/components/StockWorkspace.tsx`, keep the existing `aside` with `aria-label="复盘决策栏"` and preserve `OperatorDecisionPanel`, review log, and external-evidence buttons.

- [ ] **Step 4: Run tests to verify it passes**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard && rtk npm test -- --run tests/stock-workspace.test.tsx
```

Expected: PASS

Then run:

```bash
cd /Users/xiwei/stock_research/dashboard && rtk npm run build
```

Expected: build succeeds

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add dashboard/src/components/StockWorkspace.tsx dashboard/src/styles.css dashboard/tests/stock-workspace.test.tsx
git commit -m "feat: redesign stock workspace review layout"
```

## Spec Coverage Check

- Action-first page goal: covered by Task 1
- Tech Bottleneck enhanced mode: covered by Task 2
- Reordered sections by review reading flow: covered by Task 3
- Preserved decision recording workflow and responsive layout: covered by Task 4

No spec sections are left without a task.

## Placeholder Scan

- No `TODO`, `TBD`, or deferred placeholders remain in the plan.
- Every task includes exact file paths, test code, run commands, and expected outcomes.

## Type Consistency Check

- `StockEntryContext` is the existing source-aware input object throughout the plan.
- New region labels are consistent across tasks:
  - `明日处理结论`
  - `科技卡脖子 thesis 复盘`
  - `今日价格行为`
  - `支撑证据`
  - `基本面与档案`
  - `复盘决策栏`

Plan complete and saved to `/Users/xiwei/stock_research/docs/superpowers/plans/2026-07-08-stock-workspace-review-redesign.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
