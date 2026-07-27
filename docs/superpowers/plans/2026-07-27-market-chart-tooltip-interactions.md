# Market Chart Tooltip Interactions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make sector heatmap hover behavior consistent across ECharts and fallback rendering, and keep stock K-line tooltips fully visible at every chart edge.

**Architecture:** Add one pure boundary-position helper shared by chart components. Keep sector tooltip formatting in the sector heatmap module, preserve nullable API values, and render an explicit fallback hover/focus tooltip while retaining the existing click-to-detail flow. Measure the stock tooltip after render and use the shared helper to flip and clamp it inside the chart region.

**Tech Stack:** React 19, TypeScript, ECharts 6, lightweight-charts 5, Vitest, Testing Library, Playwright Chromium, pnpm.

---

## File Map

- Create `dashboard/src/charts/chartTooltipPosition.ts`: pure tooltip flip/clamp calculation.
- Create `dashboard/tests/chart-tooltip-position.test.ts`: edge-case unit tests for the pure calculation.
- Modify `dashboard/src/charts/AssetChart.tsx`: measure and position the K-line tooltip.
- Modify `dashboard/tests/asset-chart.test.tsx`: K-line integration tests and all-field assertions.
- Modify `dashboard/src/components/market-monitor/mockData.ts`: preserve nullable heatmap counts and flow values; map `stock_count`.
- Modify `dashboard/src/components/market-monitor/SectorFundRankingPanel.tsx`: format nullable flow values safely after the shared type correction.
- Modify `dashboard/src/components/market-monitor/SectorDetailPanel.tsx`: format nullable detail values safely after the shared type correction.
- Modify `dashboard/src/components/market-monitor/SectorHeatmapPanel.tsx`: shared tooltip content, ECharts readiness, fallback hover/focus tooltip.
- Modify `dashboard/tests/market-monitor-workspace.test.tsx`: heatmap interaction, readiness, null semantics, and sector-switch regression tests.
- Modify `dashboard/src/styles.css`: fallback and K-line tooltip positioning/presentation.
- Modify `dashboard/tests/app-smoke.spec.ts`: Chromium hover geometry acceptance for concept heatmap and rightmost K-line bar.

### Task 1: Add the shared boundary-aware tooltip position helper

**Files:**
- Create: `dashboard/src/charts/chartTooltipPosition.ts`
- Create: `dashboard/tests/chart-tooltip-position.test.ts`

- [ ] **Step 1: Write the failing unit tests**

Create `dashboard/tests/chart-tooltip-position.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { resolveChartTooltipPosition } from '../src/charts/chartTooltipPosition';

describe('resolveChartTooltipPosition', () => {
  it('keeps the tooltip to the right of a centered pointer', () => {
    expect(resolveChartTooltipPosition({
      pointerX: 300,
      pointerY: 180,
      containerWidth: 800,
      containerHeight: 460,
      tooltipWidth: 180,
      tooltipHeight: 110
    })).toEqual({ left: 314, top: 98 });
  });

  it('flips the tooltip to the left at the right edge', () => {
    expect(resolveChartTooltipPosition({
      pointerX: 760,
      pointerY: 180,
      containerWidth: 800,
      containerHeight: 460,
      tooltipWidth: 180,
      tooltipHeight: 110
    })).toEqual({ left: 566, top: 98 });
  });

  it('clamps the tooltip at every container edge', () => {
    expect(resolveChartTooltipPosition({
      pointerX: 4,
      pointerY: 4,
      containerWidth: 200,
      containerHeight: 120,
      tooltipWidth: 190,
      tooltipHeight: 100
    })).toEqual({ left: 12, top: 12 });
  });
});
```

- [ ] **Step 2: Run the test and verify the missing-module failure**

Run:

```bash
cd dashboard && rtk pnpm test -- chart-tooltip-position.test.ts
```

Expected: FAIL because `../src/charts/chartTooltipPosition` does not exist.

- [ ] **Step 3: Add the minimal pure implementation**

Create `dashboard/src/charts/chartTooltipPosition.ts`:

```ts
export type ChartTooltipPositionInput = {
  pointerX: number;
  pointerY: number;
  containerWidth: number;
  containerHeight: number;
  tooltipWidth: number;
  tooltipHeight: number;
  gap?: number;
  margin?: number;
  verticalOffset?: number;
};

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

export function resolveChartTooltipPosition({
  pointerX,
  pointerY,
  containerWidth,
  containerHeight,
  tooltipWidth,
  tooltipHeight,
  gap = 14,
  margin = 12,
  verticalOffset = 82
}: ChartTooltipPositionInput) {
  const rightCandidate = pointerX + gap;
  const leftCandidate = pointerX - gap - tooltipWidth;
  const preferredLeft = rightCandidate + tooltipWidth <= containerWidth - margin
    ? rightCandidate
    : leftCandidate;
  const maxLeft = Math.max(margin, containerWidth - tooltipWidth - margin);
  const maxTop = Math.max(margin, containerHeight - tooltipHeight - margin);

  return {
    left: clamp(preferredLeft, margin, maxLeft),
    top: clamp(pointerY - verticalOffset, margin, maxTop)
  };
}
```

- [ ] **Step 4: Run the focused test**

Run:

```bash
cd dashboard && rtk pnpm test -- chart-tooltip-position.test.ts
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit the helper**

```bash
rtk git add dashboard/src/charts/chartTooltipPosition.ts dashboard/tests/chart-tooltip-position.test.ts
rtk git commit -m "test: define chart tooltip boundaries"
```

### Task 2: Keep K-line tooltips inside the stock chart

**Files:**
- Modify: `dashboard/src/charts/AssetChart.tsx`
- Modify: `dashboard/tests/asset-chart.test.tsx`
- Modify: `dashboard/src/styles.css`

- [ ] **Step 1: Add a failing right-edge integration test**

Extend `dashboard/tests/asset-chart.test.tsx` with a geometry mock and test:

```ts
it('flips the tooltip left so the rightmost bar keeps every field visible', async () => {
  render(<AssetChart bars={[
    { time: '2026-06-01', open: 10, high: 11, low: 9.8, close: 10.5, volume: 100000, amount: 1050000 }
  ]} />);

  const shell = document.querySelector('.asset-chart-shell') as HTMLDivElement;
  const tooltipSize = { width: 180, height: 110 };
  Object.defineProperty(shell, 'clientWidth', { configurable: true, value: 720 });
  Object.defineProperty(shell, 'clientHeight', { configurable: true, value: 460 });
  const originalRect = HTMLElement.prototype.getBoundingClientRect;
  HTMLElement.prototype.getBoundingClientRect = function () {
    if (this.classList.contains('asset-chart-tooltip')) {
      return { width: tooltipSize.width, height: tooltipSize.height } as DOMRect;
    }
    return originalRect.call(this);
  };

  const handler = chartMocks.chart.subscribeCrosshairMove.mock.calls.at(-1)?.[0];
  act(() => handler?.({
    time: '2026-06-01',
    point: { x: 700, y: 120 },
    seriesData: new Map([
      [chartMocks.candleSeries, { open: 10, high: 11, low: 9.8, close: 10.5 }],
      [chartMocks.volumeSeries, { value: 100000 }]
    ])
  }));

  const tooltip = await screen.findByRole('tooltip', { name: 'K线数据' });
  await waitFor(() => expect(tooltip).toHaveStyle({ left: '506px' }));
  expect(tooltip).toHaveTextContent('开 10');
  expect(tooltip).toHaveTextContent('高 11');
  expect(tooltip).toHaveTextContent('低 9.8');
  expect(tooltip).toHaveTextContent('收 10.5');
  expect(tooltip).toHaveTextContent('量 10.00万');
  expect(tooltip).toHaveTextContent('额 105.00万');

  HTMLElement.prototype.getBoundingClientRect = originalRect;
});
```

Move the prototype restoration into `try/finally` during implementation so a failed assertion cannot leak state.

- [ ] **Step 2: Run the focused test and verify the current fixed-offset failure**

Run:

```bash
cd dashboard && rtk pnpm test -- asset-chart.test.tsx
```

Expected: FAIL because the tooltip still uses `left: hoverData.x + 14`, yielding `714px`.

- [ ] **Step 3: Measure and position the tooltip**

In `dashboard/src/charts/AssetChart.tsx`:

```ts
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { resolveChartTooltipPosition } from './chartTooltipPosition';
```

Add refs and position state beside the existing chart refs:

```ts
const tooltipRef = useRef<HTMLDivElement | null>(null);
const [tooltipPosition, setTooltipPosition] = useState<{ left: number; top: number } | null>(null);
```

Add the layout effect:

```ts
useLayoutEffect(() => {
  if (!hoverData || !containerRef.current || !tooltipRef.current) {
    setTooltipPosition(null);
    return;
  }
  const tooltipRect = tooltipRef.current.getBoundingClientRect();
  setTooltipPosition(resolveChartTooltipPosition({
    pointerX: hoverData.x,
    pointerY: hoverData.y,
    containerWidth: containerRef.current.clientWidth,
    containerHeight: containerRef.current.clientHeight,
    tooltipWidth: tooltipRect.width,
    tooltipHeight: tooltipRect.height
  }));
}, [hoverData]);
```

Attach the tooltip ref and replace the fixed style:

```tsx
<div className="asset-chart-shell">
  ...
  <div
    ref={tooltipRef}
    className="asset-chart-tooltip"
    role="tooltip"
    aria-label="K线数据"
    style={{
      left: tooltipPosition?.left ?? 12,
      top: tooltipPosition?.top ?? 12,
      visibility: tooltipPosition ? 'visible' : 'hidden'
    }}
  >
```

Use the chart element's dimensions because `hoverData.x/y` are relative to that element.

- [ ] **Step 4: Constrain oversized tooltip content in CSS**

Keep the existing `.asset-chart-tooltip` rules and add:

```css
.asset-chart-tooltip {
  max-height: calc(460px - 24px);
  overflow: hidden;
}
```

- [ ] **Step 5: Run K-line tests and build**

Run:

```bash
cd dashboard && rtk pnpm test -- asset-chart.test.tsx chart-tooltip-position.test.ts
cd dashboard && rtk pnpm build
```

Expected: focused tests PASS and TypeScript/Vite build succeeds.

- [ ] **Step 6: Commit the K-line fix**

```bash
rtk git add dashboard/src/charts/AssetChart.tsx dashboard/src/styles.css dashboard/tests/asset-chart.test.tsx
rtk git commit -m "fix: keep stock chart tooltip in bounds"
```

### Task 3: Preserve nullable sector values and define one tooltip content contract

**Files:**
- Modify: `dashboard/src/components/market-monitor/mockData.ts`
- Modify: `dashboard/src/components/market-monitor/SectorFundRankingPanel.tsx`
- Modify: `dashboard/src/components/market-monitor/SectorDetailPanel.tsx`
- Modify: `dashboard/src/components/market-monitor/SectorHeatmapPanel.tsx`
- Modify: `dashboard/tests/market-monitor-workspace.test.tsx`

- [ ] **Step 1: Add failing null-semantics and content tests**

Add a heatmap fixture with `main_net_inflow: null`, `up_count: null`, `down_count: null`, and `stock_count: null`. Assert the heatmap formatter produces:

```ts
expect(tooltipFormatter({ data: renderedItem })).toContain('上涨/下跌 --/--');
expect(tooltipFormatter({ data: renderedItem })).toContain('成分股 --');
expect(tooltipFormatter({ data: renderedItem })).toContain('主力净流入 --');
expect(tooltipFormatter({ data: { ...renderedItem, mainNetInflow: 0 } })).toContain('主力净流入 0.00亿');
```

Also assert mapped heatmap items preserve `stockCount` and nullable values rather than converting them to zero.

- [ ] **Step 2: Run the market monitor test and verify failure**

Run:

```bash
cd dashboard && rtk pnpm test -- market-monitor-workspace.test.tsx
```

Expected: FAIL because `coerceNumber` currently converts null values to `0` and `stock_count` is not mapped.

- [ ] **Step 3: Correct the shared sector snapshot types and mapper**

In `dashboard/src/components/market-monitor/mockData.ts`, change the optional metrics:

```ts
export type SectorSnapshot = {
  sectorId: string;
  sectorName: string;
  sectorType: SectorType;
  pctChange: number;
  amount: number;
  upCount: number | null;
  downCount: number | null;
  stockCount: number | null;
  mainNetInflow: number | null;
  netInflowRatio: number | null;
  leadingStockName: string | null;
};

function coerceNullableNumber(value: number | null | undefined) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}
```

Map fields with `coerceNullableNumber`, including:

```ts
const stockCount = 'stock_count' in item ? item.stock_count : null;
...
upCount: coerceNullableNumber(upCount),
downCount: coerceNullableNumber(downCount),
stockCount: coerceNullableNumber(stockCount),
mainNetInflow: coerceNullableNumber(mainNetInflow),
netInflowRatio: coerceNullableNumber(netInflowRatio),
```

Update mock sector objects to include `stockCount`, normally `null` when the source does not provide it.

- [ ] **Step 4: Make ranking and detail formatters null-safe**

Update local formatters in `SectorFundRankingPanel.tsx` and `SectorDetailPanel.tsx`:

```ts
function formatSignedAmountYi(value: number | null) {
  if (value === null) return '--';
  const sign = value > 0 ? '+' : '';
  return `${sign}${(value / 100000000).toFixed(2)}亿`;
}

function formatRatio(value: number | null) {
  if (value === null) return '--';
  const sign = value > 0 ? '+' : '';
  return `${sign}${(value * 100).toFixed(1)}%`;
}
```

Render detail counts with `detail.upCount ?? '--'` and `detail.downCount ?? '--'`.

- [ ] **Step 5: Add one sector tooltip formatter**

In `SectorHeatmapPanel.tsx`, add:

```ts
function formatOptionalAmountYi(value: number | null) {
  return value === null ? '--' : formatAmountYi(value);
}

function formatOptionalCount(value: number | null) {
  return value === null ? '--' : String(value);
}

export function formatSectorTooltipLines(item: SectorHeatmapItem) {
  return [
    item.sectorName,
    `涨跌幅 ${formatSignedPercent(item.pctChange)}`,
    `成交额 ${formatAmountYi(item.amount)}`,
    `上涨/下跌 ${formatOptionalCount(item.upCount)}/${formatOptionalCount(item.downCount)}`,
    `成分股 ${formatOptionalCount(item.stockCount)}`,
    `主力净流入 ${formatOptionalAmountYi(item.mainNetInflow)}`
  ];
}
```

Replace the ECharts formatter body with `formatSectorTooltipLines(item).join('<br/>')`.

- [ ] **Step 6: Run focused tests and build**

Run:

```bash
cd dashboard && rtk pnpm test -- market-monitor-workspace.test.tsx
cd dashboard && rtk pnpm build
```

Expected: tests PASS and TypeScript accepts nullable sector metrics throughout the market monitor.

- [ ] **Step 7: Commit the sector data contract**

```bash
rtk git add dashboard/src/components/market-monitor/mockData.ts dashboard/src/components/market-monitor/SectorFundRankingPanel.tsx dashboard/src/components/market-monitor/SectorDetailPanel.tsx dashboard/src/components/market-monitor/SectorHeatmapPanel.tsx dashboard/tests/market-monitor-workspace.test.tsx
rtk git commit -m "fix: preserve sector tooltip data semantics"
```

### Task 4: Unify ECharts and fallback heatmap interactions

**Files:**
- Modify: `dashboard/src/components/market-monitor/SectorHeatmapPanel.tsx`
- Modify: `dashboard/src/styles.css`
- Modify: `dashboard/tests/market-monitor-workspace.test.tsx`

- [ ] **Step 1: Add failing fallback hover/focus tests**

Use the existing zero-size chart setup so the compatibility layer remains active. Assert:

```ts
const tile = await screen.findByRole('button', { name: '兼容热力块 上涨 API半导体' });
fireEvent.pointerEnter(tile, { clientX: 120, clientY: 80 });
expect(screen.getByRole('tooltip', { name: '板块数据' })).toHaveTextContent('API半导体');
expect(screen.getByRole('tooltip', { name: '板块数据' })).toHaveTextContent('上涨/下跌 96/12');
expect(screen.getByRole('tooltip', { name: '板块数据' })).toHaveTextContent('成分股 118');
fireEvent.pointerLeave(tile);
expect(screen.queryByRole('tooltip', { name: '板块数据' })).not.toBeInTheDocument();

fireEvent.focus(tile);
expect(screen.getByRole('tooltip', { name: '板块数据' })).toBeInTheDocument();
fireEvent.blur(tile);
expect(screen.queryByRole('tooltip', { name: '板块数据' })).not.toBeInTheDocument();
```

Add a concept-switch test that hovers `API算力`, switches back to industry, and asserts the stale concept tooltip is gone.

- [ ] **Step 2: Add a failing ECharts readiness test**

Change the ECharts mock to append a canvas to the supplied chart node when configured as rendered. Assert that after an animation frame:

```ts
expect(screen.queryByLabelText('上涨板块兼容热力图')).not.toBeInTheDocument();
expect(document.querySelector('.market-monitor-heatmap-chart-up canvas')).not.toBeNull();
```

Keep the zero-size test proving fallback availability.

- [ ] **Step 3: Run the focused test and verify failures**

Run:

```bash
cd dashboard && rtk pnpm test -- market-monitor-workspace.test.tsx
```

Expected: FAIL because fallback tiles have no hover state and chart readiness is checked before the renderer settles.

- [ ] **Step 4: Implement fallback hover/focus state**

Extend `FallbackTreemap` with a container ref, tooltip ref, hovered item/pointer state, and `resolveChartTooltipPosition`:

```ts
const containerRef = useRef<HTMLDivElement | null>(null);
const tooltipRef = useRef<HTMLDivElement | null>(null);
const [hoveredItem, setHoveredItem] = useState<SectorHeatmapItem | null>(null);
const [tooltipPointer, setTooltipPointer] = useState<{ x: number; y: number } | null>(null);
const [tooltipPosition, setTooltipPosition] = useState<{ left: number; top: number } | null>(null);

const setPointerFromClient = (item: SectorHeatmapItem, clientX: number, clientY: number) => {
  const rect = containerRef.current?.getBoundingClientRect();
  if (!rect) return;
  setHoveredItem(item);
  setTooltipPointer({ x: clientX - rect.left, y: clientY - rect.top });
};

useLayoutEffect(() => {
  if (!hoveredItem || !tooltipPointer || !containerRef.current || !tooltipRef.current) {
    setTooltipPosition(null);
    return;
  }
  const tooltipRect = tooltipRef.current.getBoundingClientRect();
  setTooltipPosition(resolveChartTooltipPosition({
    pointerX: tooltipPointer.x,
    pointerY: tooltipPointer.y,
    containerWidth: containerRef.current.clientWidth,
    containerHeight: containerRef.current.clientHeight,
    tooltipWidth: tooltipRect.width,
    tooltipHeight: tooltipRect.height,
    verticalOffset: 24
  }));
}, [hoveredItem, tooltipPointer]);
```

Attach `ref={containerRef}` to the fallback root. Add these handlers to each tile while retaining the existing `onClick`:

```tsx
onPointerEnter={(event) => setPointerFromClient(item, event.clientX, event.clientY)}
onPointerMove={(event) => setPointerFromClient(item, event.clientX, event.clientY)}
onPointerLeave={() => {
  setHoveredItem(null);
  setTooltipPointer(null);
}}
onFocus={(event) => {
  const tileRect = event.currentTarget.getBoundingClientRect();
  setPointerFromClient(item, tileRect.left + tileRect.width / 2, tileRect.top + tileRect.height / 2);
}}
onBlur={() => {
  setHoveredItem(null);
  setTooltipPointer(null);
}}
```

Render the tooltip inside the fallback root:

```tsx
{hoveredItem ? (
  <div
    ref={tooltipRef}
    className="market-monitor-sector-tooltip"
    role="tooltip"
    aria-label="板块数据"
    style={{
      left: tooltipPosition?.left ?? 12,
      top: tooltipPosition?.top ?? 12,
      visibility: tooltipPosition ? 'visible' : 'hidden'
    }}
  >
    {formatSectorTooltipLines(hoveredItem).map((line, index) =>
      index === 0 ? <strong key={line}>{line}</strong> : <span key={line}>{line}</span>
    )}
  </div>
) : null}
```

The tooltip has `pointer-events: none`. Keep the existing tile `onClick` unchanged.

- [ ] **Step 5: Make ECharts readiness asynchronous and truthful**

After `setOption` and `resize`, schedule one animation-frame readiness check:

```ts
const updateChartReady = () => {
  setChartReady(Boolean(node.querySelector('canvas, svg')));
};
frameId = window.requestAnimationFrame(updateChartReady);
```

If the node has no canvas/SVG after the bounded retry sequence, keep `chartReady=false` and leave the fallback interactive. Set ECharts tooltip options to HTML mode with a stable class:

```ts
tooltip: {
  renderMode: 'html',
  appendToBody: false,
  className: 'market-monitor-sector-tooltip',
  confine: true,
  formatter: ...
}
```

Clear fallback hover state when sector type or item identity changes.

- [ ] **Step 6: Add fallback tooltip CSS**

Add:

```css
.market-monitor-sector-tooltip {
  position: absolute;
  z-index: 4;
  display: grid;
  gap: 3px;
  max-width: min(260px, calc(100% - 24px));
  border: 1px solid #c8d3e3;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.14);
  padding: 8px 10px;
  color: #1f2937;
  font-size: 12px;
  line-height: 1.35;
  pointer-events: none;
}
```

- [ ] **Step 7: Run market-monitor tests and dashboard build**

Run:

```bash
cd dashboard && rtk pnpm test -- market-monitor-workspace.test.tsx
cd dashboard && rtk pnpm build
```

Expected: fallback hover/focus, ECharts readiness, sector switch, and existing click/detail tests PASS.

- [ ] **Step 8: Commit the unified heatmap interaction**

```bash
rtk git add dashboard/src/components/market-monitor/SectorHeatmapPanel.tsx dashboard/src/styles.css dashboard/tests/market-monitor-workspace.test.tsx
rtk git commit -m "fix: unify sector heatmap interactions"
```

### Task 5: Add Chromium acceptance and run the regression suite

**Files:**
- Modify: `dashboard/tests/app-smoke.spec.ts`

- [ ] **Step 1: Add deterministic market-monitor route fixtures**

Extend `mockDashboardApi` with completed overview, concept heatmap, fund-flow, and sector-detail routes. The concept heatmap fixture contains one positive tile named `ST板块` and one negative tile so the positive treemap area is deterministic:

```ts
const conceptStItem = {
  sector_id: 'concept-st', sector_name: 'ST板块', sector_type: 'concept',
  change_pct: 0.0989, amount: 2923611417.92,
  up_count: 5, down_count: 12, stock_count: 20, main_net_inflow: null
};
const conceptDownItem = {
  sector_id: 'concept-down', sector_name: '概念回调', sector_type: 'concept',
  change_pct: -0.02, amount: 1500000000,
  up_count: 2, down_count: 18, stock_count: 20, main_net_inflow: -100000000
};

await page.route('/api/market-monitor/overview**', (route) => route.fulfill({ json: {
  trade_date: '2026-07-24', updated_at: '2026-07-24 15:10', source: 'fixture',
  data_status: 'completed', warnings: [], indices: [], total_amount: 10000000000,
  up_count: 532, down_count: 4629, limit_up_count: 42, limit_down_count: 28
} }));
await page.route('/api/market-monitor/sectors/heatmap**', (route) => {
  const type = new URL(route.request().url()).searchParams.get('type');
  const items = type === 'concept' ? [conceptStItem, conceptDownItem] : [{ ...conceptStItem, sector_type: 'industry', sector_name: '运输设备制造业' }];
  return route.fulfill({ json: {
    trade_date: '2026-07-24', updated_at: '2026-07-24 15:10', source: 'fixture',
    data_status: 'completed', warnings: [], items
  } });
});
await page.route('/api/market-monitor/sectors/fund-flow**', (route) => route.fulfill({ json: {
  trade_date: '2026-07-24', updated_at: '2026-07-24 15:10', source: 'fixture',
  data_status: 'completed', warnings: [], inflow: [], outflow: []
} }));
await page.route('/api/market-monitor/sectors/*', (route) => route.fulfill({ json: {
  trade_date: '2026-07-24', updated_at: '2026-07-24 15:10', source: 'fixture',
  data_status: 'completed', warnings: [], ...conceptStItem,
  summary: 'ST板块 fixture', main_net_inflow_ratio: null,
  leading_stock_name: null, leading_stocks: []
} }));
```

- [ ] **Step 2: Add the concept heatmap hover acceptance test**

Append this Playwright test, using the exact navigation labels already present in `app-smoke.spec.ts`:

```ts
test('concept heatmap exposes complete hover information and click detail', async ({ page }) => {
  await mockDashboardApi(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'Open Market Monitor workspace' }).click();
  await page.getByRole('button', { name: '概念', exact: true }).click();

  const chart = page.getByLabel('上涨板块热力图图表');
  await expect(chart).toBeVisible();
  const chartBox = await chart.boundingBox();
  expect(chartBox).not.toBeNull();
  await page.mouse.move(chartBox!.x + chartBox!.width / 2, chartBox!.y + chartBox!.height / 2);

  const tooltip = page.locator('.market-monitor-sector-tooltip');
  await expect(tooltip).toContainText('ST板块');
  await expect(tooltip).toContainText('上涨/下跌 5/12');
  await expect(tooltip).toContainText('成分股 20');
  await expect(tooltip).toContainText('主力净流入 --');

  await page.mouse.click(chartBox!.x + chartBox!.width / 2, chartBox!.y + chartBox!.height / 2);
  await expect(page.getByRole('heading', { level: 3, name: 'ST板块' })).toBeVisible();
});
```

The visible tooltip text is:

```text
ST板块
涨跌幅 +9.89%
成交额 29.24亿
上涨/下跌 5/12
成分股 20
主力净流入 --
```

Click the same tile and assert the existing detail panel heading becomes `ST板块`.

- [ ] **Step 3: Add the rightmost K-line geometry acceptance test**

Add a helper and test. The helper retries concrete crosshair positions from right to left until the real chart emits the tooltip; it does not use a fixed sleep:

```ts
async function hoverRightmostChartBar(page: Page) {
  const chart = page.locator('.asset-chart');
  const chartBox = await chart.boundingBox();
  expect(chartBox).not.toBeNull();
  for (const offset of [72, 84, 96, 108]) {
    await page.mouse.move(chartBox!.x + chartBox!.width - offset, chartBox!.y + 140);
    if (await page.getByRole('tooltip', { name: 'K线数据' }).isVisible().catch(() => false)) {
      return chartBox!;
    }
  }
  throw new Error('rightmost chart bar did not emit a tooltip');
}

test('rightmost stock bars keep the full tooltip inside the chart', async ({ page }) => {
  await mockDashboardApi(page);
  await page.goto('/stock/000001.SZ');

  for (const period of ['日K', '周K', '月K', '分时']) {
    await page.getByRole('button', { name: period, exact: true }).click();
    const chartBox = await hoverRightmostChartBar(page);
    const tooltip = page.getByRole('tooltip', { name: 'K线数据' });
    const tooltipBox = await tooltip.boundingBox();
    expect(tooltipBox).not.toBeNull();
    expect(tooltipBox!.x).toBeGreaterThanOrEqual(chartBox.x);
    expect(tooltipBox!.x + tooltipBox!.width).toBeLessThanOrEqual(chartBox.x + chartBox.width);
    for (const label of ['开', '高', '低', '收', '量', '额']) {
      await expect(tooltip).toContainText(label);
    }
  }
});
```

The core geometry assertion is:

```ts
const chartBox = await page.locator('.asset-chart').boundingBox();
const tooltipBox = await page.getByRole('tooltip', { name: 'K线数据' }).boundingBox();
expect(tooltipBox!.x).toBeGreaterThanOrEqual(chartBox!.x);
expect(tooltipBox!.x + tooltipBox!.width).toBeLessThanOrEqual(chartBox!.x + chartBox!.width);
await expect(page.getByRole('tooltip', { name: 'K线数据' })).toContainText('开');
await expect(page.getByRole('tooltip', { name: 'K线数据' })).toContainText('高');
await expect(page.getByRole('tooltip', { name: 'K线数据' })).toContainText('低');
await expect(page.getByRole('tooltip', { name: 'K线数据' })).toContainText('收');
await expect(page.getByRole('tooltip', { name: 'K线数据' })).toContainText('量');
await expect(page.getByRole('tooltip', { name: 'K线数据' })).toContainText('额');
```

Repeat the geometry assertion after selecting `周K`, `月K`, and `分时`. Use the visible chart box after each data request completes rather than a fixed delay.

- [ ] **Step 4: Run focused Chromium acceptance**

Run:

```bash
cd dashboard && PLAYWRIGHT_REUSE_EXISTING=false rtk pnpm exec playwright test tests/app-smoke.spec.ts --project=chromium
```

Expected: all app-smoke Chromium tests PASS.

- [ ] **Step 5: Run the complete relevant regression set**

Run:

```bash
cd dashboard && rtk pnpm test -- chart-tooltip-position.test.ts asset-chart.test.tsx market-monitor-workspace.test.tsx stock-workspace.test.tsx
cd dashboard && rtk pnpm build
cd dashboard && PLAYWRIGHT_REUSE_EXISTING=false rtk pnpm test:e2e
```

Expected: focused Vitest suite PASS, dashboard build succeeds, and the complete Chromium Playwright suite PASS.

- [ ] **Step 6: Inspect the live local pages from the stable worktree**

Start or restart the dashboard from the stable integration worktree only after its runtime integration prerequisite is satisfied. Verify:

- `/market-monitor`: industry and concept tiles show identical hover and click behavior;
- `/stock/000001.SZ`: rightmost tooltips remain inside the chart for daily, weekly, monthly, and intraday modes;
- no console errors are emitted during sector switching or chart hovering.

- [ ] **Step 7: Commit the acceptance coverage**

```bash
rtk git add dashboard/tests/app-smoke.spec.ts
rtk git commit -m "test: cover chart tooltip interactions"
```

### Task 6: Final verification and handoff

**Files:**
- No planned source changes.

- [ ] **Step 1: Confirm the worktree contains only intended commits**

Run:

```bash
rtk git status --short --branch
rtk git log --oneline -8
rtk git diff --check 505cdfb..HEAD
```

Expected: clean worktree; only tooltip interaction implementation/test commits after the plan commit; no whitespace errors.

- [ ] **Step 2: Confirm the dirty main research files remain untouched**

Run from `/Users/xiwei/stock_research`:

```bash
rtk git status --short -- outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1
```

Expected: the same three pre-existing modified CSV files remain unstaged and were not changed by this implementation.

- [ ] **Step 3: Record verification evidence**

Report the exact Vitest, build, and Playwright commands, their exit status, the implementation commit ids, and any remaining non-blocking warnings. Do not claim the live page is fixed until the stable runtime is actually serving these commits.
