# Stock Workspace Quote Dossier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a truthful stock-page-style quote dossier to Stock Workspace without fabricating unavailable valuation fields.

**Architecture:** Extend the asset profile backend with `quote_snapshot`, `company_profile`, and `valuation_snapshot`, then render those sections at the top of the existing canonical Stock Workspace. Keep existing news, research, chart, and review flows intact.

**Tech Stack:** Python/FastAPI service layer, PostgreSQL through existing `connect/fetch_all`, React + TypeScript, Vitest + Testing Library.

---

## File Structure

- Modify `src/stock_research/dashboard/asset_profile.py`: add quote/company/valuation loaders and include them in `build_asset_profile()`.
- Modify `dashboard/src/api/types.ts`: add `AssetQuoteSnapshot`, `CompanyProfile`, `ValuationSnapshot`, and extend `AssetProfile`.
- Modify `dashboard/src/components/StockWorkspace.tsx`: render `行情快照`, `规模估值`, and `股票简况`; rename existing review summary to `策略复盘摘要`.
- Modify `dashboard/src/styles.css`: add compact quote-dossier layout styles using existing visual language.
- Modify `dashboard/tests/stock-workspace.test.tsx`: add frontend regression coverage for quote and unavailable valuation display.
- Add or modify backend tests under `tests/`: verify asset profile quote snapshot from database query results.

## Task 1: Frontend Contract And Rendering

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/components/StockWorkspace.tsx`
- Modify: `dashboard/src/styles.css`
- Test: `dashboard/tests/stock-workspace.test.tsx`

- [ ] **Step 1: Write the failing frontend test**

Add a test that creates a profile with `quote_snapshot`, `company_profile`, and unavailable `valuation_snapshot`, then expects Chinese labels and values:

```tsx
it('renders a stock-page quote dossier without fabricating unavailable valuation fields', async () => {
  apiMocks.fetchAssetProfile.mockResolvedValueOnce(
    makeProfile({
      quote_snapshot: {
        trade_date: '2026-06-08',
        open: 10.6,
        high: 11.2,
        low: 10.4,
        close: 11,
        preclose: 10.6,
        volume: 1300,
        amount: 14300,
        turnover_rate: 2.35,
        pct_chg: 3.77,
        amount_ratio_20d: 1.23,
        data_status: 'available',
        missing_fields: []
      },
      company_profile: {
        asset_id: '000001.SZ',
        ts_code: '000001.SZ',
        symbol: '000001',
        name: '平安银行',
        exchange: 'SZ',
        board: '主板',
        list_date: '1991-04-03',
        is_active: true,
        is_beijing: false,
        is_star: false,
        is_chinext: false,
        region: '深圳',
        source: 'core.asset_master'
      },
      valuation_snapshot: {
        total_market_cap: null,
        float_market_cap: null,
        pe_ttm: null,
        pb: null,
        volume_ratio: null,
        data_status: 'unavailable',
        missing_fields: ['total_market_cap', 'float_market_cap', 'pe_ttm', 'pb', 'volume_ratio']
      }
    })
  );

  render(<StockWorkspace initialAssetId="000001.SZ" />);

  const quote = await screen.findByRole('region', { name: '行情快照' });
  expect(within(quote).getByText('最新价')).toBeInTheDocument();
  expect(within(quote).getByText('11.00')).toBeInTheDocument();
  expect(within(quote).getByText('今开')).toBeInTheDocument();
  expect(within(quote).getByText('10.60')).toBeInTheDocument();
  expect(within(quote).getByText('最高')).toBeInTheDocument();
  expect(within(quote).getByText('最低')).toBeInTheDocument();
  expect(within(quote).getByText('成交额')).toBeInTheDocument();
  expect(within(quote).getByText('1.43万')).toBeInTheDocument();
  expect(within(quote).getByText('换手率')).toBeInTheDocument();
  expect(within(quote).getByText('2.35%')).toBeInTheDocument();
  expect(within(quote).getByText('量能/20日均额')).toBeInTheDocument();
  expect(within(quote).getByText('1.23x')).toBeInTheDocument();

  const company = screen.getByRole('region', { name: '股票简况' });
  expect(within(company).getByText('主板')).toBeInTheDocument();
  expect(within(company).getByText('1991-04-03')).toBeInTheDocument();
  expect(within(company).getByText('深圳')).toBeInTheDocument();

  const valuation = screen.getByRole('region', { name: '规模估值' });
  expect(within(valuation).getAllByText('待接入').length).toBeGreaterThanOrEqual(4);
  expect(within(valuation).queryByText('0')).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/xiwei/stock_research/dashboard && rtk pnpm exec vitest run tests/stock-workspace.test.tsx -t "quote dossier"`

Expected: FAIL because `AssetProfile` lacks the new fields and the UI does not render `行情快照`.

- [ ] **Step 3: Implement minimal frontend types and UI**

Add TypeScript types for the three snapshots and render the quote dossier above the existing review summary. Add formatting helpers for price, percent, amount, volume, and unavailable values.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/xiwei/stock_research/dashboard && rtk pnpm exec vitest run tests/stock-workspace.test.tsx -t "quote dossier"`

Expected: PASS.

## Task 2: Backend Quote Snapshot

**Files:**
- Modify: `src/stock_research/dashboard/asset_profile.py`
- Test: `tests/test_dashboard_asset_profile.py` or existing closest asset profile test

- [ ] **Step 1: Write the failing backend test**

Mock `fetch_all` responses or use the existing test DB helper to assert `build_asset_profile()` returns `quote_snapshot` with daily quote values and `company_profile` from `core.asset_master`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/xiwei/stock_research && rtk pytest tests/test_dashboard_asset_profile.py -q`

Expected: FAIL because quote/company/valuation sections do not exist.

- [ ] **Step 3: Implement backend loaders**

Add `_load_quote_snapshot()`, `_load_company_profile()`, and `_empty_valuation_snapshot()` to `asset_profile.py`. Compute `amount_ratio_20d` from the latest available daily bar amount divided by the average positive amount in the latest 20 bars ending at or before `end_date`.

- [ ] **Step 4: Run backend test to verify it passes**

Run: `cd /Users/xiwei/stock_research && rtk pytest tests/test_dashboard_asset_profile.py -q`

Expected: PASS.

## Task 3: Full Regression And Browser Check

**Files:**
- No new files unless tests expose a defect.

- [ ] **Step 1: Run focused frontend tests**

Run: `cd /Users/xiwei/stock_research/dashboard && rtk pnpm exec vitest run tests/stock-workspace.test.tsx`

Expected: all Stock Workspace tests pass.

- [ ] **Step 2: Run focused backend tests**

Run: `cd /Users/xiwei/stock_research && rtk pytest tests/test_dashboard_asset_profile.py -q`

Expected: all asset profile tests pass.

- [ ] **Step 3: Run build**

Run: `cd /Users/xiwei/stock_research/dashboard && rtk pnpm build`

Expected: Vite build exits 0.

- [ ] **Step 4: Playwright smoke check**

Open `http://127.0.0.1:5174/`, navigate to 个股工作台, and verify `行情快照`, `规模估值`, and `股票简况` are visible without console errors.

## Self-Review

- Spec coverage: quote snapshot, company profile, unavailable valuation state, and existing review workflow are covered.
- Placeholder scan: no implementation placeholders are left in the task steps.
- Type consistency: frontend type names match the proposed `AssetProfile` fields and backend keys.
