# Stock Workspace Dual-Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有 `StockWorkspace` 扩展成一个真正可复盘的统一个股页，在普通看票和科技卡脖子看票两种入口下都先回答 `明天怎么处理这只票`，并补齐公司基础信息、主营构成、经营质量三类核心信息。

**Architecture:** 保留现有 `/api/assets/:id/profile` 和统一 `StockWorkspace` 路由，不再新增第二个个股页面，而是在后端把基础画像、主营构成、财务质量聚合进 `AssetProfile`，再在前端按决策优先顺序重排页面。科技卡脖子入口继续走 `entryContext.sourceWorkspace === "techBottleneck"`，但只决定内容抬升顺序，不复制一套页面实现。

**Tech Stack:** Python dashboard backend, PostgreSQL, React, TypeScript, Vite, Vitest, Testing Library, existing dashboard CSS

---

## File Map

- Create: `/Users/xiwei/stock_research/src/stock_research/dashboard/asset_profile_fundamentals.py`
  Responsibility: 聚合行业/概念/主营构成/财务质量，给 `build_asset_profile` 提供可直接渲染的 overview 数据。
- Modify: `/Users/xiwei/stock_research/src/stock_research/dashboard/asset_profile.py`
  Responsibility: 把新的基础画像、主营构成、经营质量挂进现有 `AssetProfile` 返回值。
- Modify: `/Users/xiwei/stock_research/tests/test_dashboard_asset_profile.py`
  Responsibility: 锁定 backend profile 合同，保证 overview / composition / financial snapshot 都能稳定返回和降级。
- Modify: `/Users/xiwei/stock_research/dashboard/src/api/types.ts`
  Responsibility: 扩展前端 `AssetProfile` 类型，新增 `company_overview`、`business_composition`、`financial_snapshot`。
- Create: `/Users/xiwei/stock_research/dashboard/src/components/stock-workspace/CompanyBasicsSection.tsx`
  Responsibility: 渲染“公司基础信息”。
- Create: `/Users/xiwei/stock_research/dashboard/src/components/stock-workspace/BusinessQualitySection.tsx`
  Responsibility: 渲染“主营构成与经营质量”。
- Modify: `/Users/xiwei/stock_research/dashboard/src/components/StockWorkspace.tsx`
  Responsibility: 删除旧的重复摘要块，按新顺序接入新 section，并让科技卡脖子模式只抬升 thesis，而不是复制页面。
- Modify: `/Users/xiwei/stock_research/dashboard/src/styles.css`
  Responsibility: 调整个股页密度、桌面 16:9 布局和手机竖屏堆叠规则，让基础信息和主营构成优先于大面积行情块。
- Modify: `/Users/xiwei/stock_research/dashboard/tests/stock-workspace.test.tsx`
  Responsibility: 锁定新 section 顺序、科技卡脖子 mode 抬升顺序、空数据降级和按钮裁剪行为。

Do not create a second stock page. Do not move this work to `main/dashboard`. The target is the current unified dashboard front end that already serves `/`, `/review-queue`, `/market`, `/stock`, and `/tech-bottleneck/...`.

### Task 1: Extend Asset Profile With Review-Grade Basics And Fundamentals

**Files:**
- Create: `/Users/xiwei/stock_research/src/stock_research/dashboard/asset_profile_fundamentals.py`
- Modify: `/Users/xiwei/stock_research/src/stock_research/dashboard/asset_profile.py`
- Modify: `/Users/xiwei/stock_research/tests/test_dashboard_asset_profile.py`
- Modify: `/Users/xiwei/stock_research/dashboard/src/api/types.ts`

- [ ] **Step 1: Write the failing backend contract test**

Add this test after the existing `test_build_asset_profile_includes_quote_and_company_snapshots` in `/Users/xiwei/stock_research/tests/test_dashboard_asset_profile.py`:

```python
def test_build_asset_profile_includes_overview_business_and_financial_sections(monkeypatch):
    monkeypatch.setattr(asset_profile, "connect", lambda service: DummyConnection())
    monkeypatch.setattr(asset_profile, "load_daily_bars", lambda *args, **kwargs: [])
    monkeypatch.setattr(asset_profile, "load_asset_detail", lambda *args, **kwargs: None)
    monkeypatch.setattr(asset_profile, "load_asset_score_for_dashboard", lambda *args, **kwargs: None)
    monkeypatch.setattr(asset_profile, "load_asset_watchlist_signals_for_dashboard", lambda *args, **kwargs: [])
    monkeypatch.setattr(asset_profile, "load_asset_decision_history", lambda *args, **kwargs: [])
    monkeypatch.setattr(asset_profile, "load_asset_outcome_history", lambda *args, **kwargs: [])

    def fake_fetch_all(conn, sql, params):
        normalized_sql = " ".join(sql.split())
        if "FROM core.asset_master" in normalized_sql:
            return [
                {
                    "asset_id": "CN:SZ:002371",
                    "ts_code": "002371.SZ",
                    "symbol": "002371",
                    "name": "北方华创",
                    "exchange": "SZ",
                    "board": "主板",
                    "list_date": "2010-03-16",
                    "is_active": True,
                    "is_beijing": False,
                    "is_star": False,
                    "is_chinext": False,
                    "region": "北京",
                    "source": "test",
                }
            ]
        if "FROM core.industry_membership" in normalized_sql:
            return [{"industry_name": "半导体设备"}]
        if "FROM core.concept_membership" in normalized_sql:
            return [{"concept_name": "先进封装"}, {"concept_name": "国产替代"}]
        if "FROM finance.main_business_composition" in normalized_sql:
            return [
                {
                    "report_period": "2026-03-31",
                    "classify_type": "按产品",
                    "item_name": "刻蚀设备",
                    "revenue": 5200000000,
                    "revenue_ratio": 0.41,
                    "gross_margin": 0.43,
                },
                {
                    "report_period": "2026-03-31",
                    "classify_type": "按产品",
                    "item_name": "薄膜沉积设备",
                    "revenue": 3100000000,
                    "revenue_ratio": 0.24,
                    "gross_margin": 0.39,
                },
                {
                    "report_period": "2026-03-31",
                    "classify_type": "按行业",
                    "item_name": "集成电路装备",
                    "revenue": 9800000000,
                    "revenue_ratio": 0.77,
                    "gross_margin": 0.41,
                },
            ]
        if "FROM finance.indicator_quarter" in normalized_sql:
            return [
                {
                    "asset_id": "CN:SZ:002371",
                    "report_period": "2026-03-31",
                    "announcement_date": "2026-04-28",
                    "roe": 0.128,
                    "gross_margin": 0.412,
                    "net_margin": 0.183,
                    "debt_ratio": 0.342,
                    "revenue_yoy": 0.218,
                    "np_yoy": 0.267,
                    "deduct_np_yoy": 0.251,
                    "ocf_to_np": 1.09,
                }
            ]
        if "FROM finance.cash_flow" in normalized_sql:
            return [
                {
                    "asset_id": "CN:SZ:002371",
                    "report_period": "2026-03-31",
                    "announcement_date": "2026-04-28",
                    "net_operate_cash_flow": 1860000000,
                }
            ]
        if "FROM finance.income_statement" in normalized_sql:
            return [
                {
                    "asset_id": "CN:SZ:002371",
                    "report_period": "2026-03-31",
                    "announcement_date": "2026-04-28",
                    "revenue": 12600000000,
                    "np_parent": 2280000000,
                },
                {
                    "asset_id": "CN:SZ:002371",
                    "report_period": "2025-12-31",
                    "announcement_date": "2026-03-28",
                    "revenue": 41800000000,
                    "np_parent": 7200000000,
                },
                {
                    "asset_id": "CN:SZ:002371",
                    "report_period": "2025-03-31",
                    "announcement_date": "2025-04-29",
                    "revenue": 9800000000,
                    "np_parent": 1680000000,
                },
            ]
        if "ORDER BY trade_date DESC LIMIT 20" in normalized_sql:
            return []
        if "min(trade_date)" in normalized_sql:
            return [{"min_date": None, "max_date": None, "row_count": 0}]
        if "max(trade_date)" in normalized_sql and "factor.factor_daily" in normalized_sql:
            return [{"latest_factor_date": None, "factor_count": 0}]
        return []

    monkeypatch.setattr(asset_profile, "fetch_all", fake_fetch_all)

    profile = asset_profile.build_asset_profile(
        "002371.SZ",
        "2026-06-30",
        "2026-01-01",
        "2026-06-30",
        service="test",
    )

    assert profile["company_overview"]["industry"] == "半导体设备"
    assert profile["company_overview"]["concept_tags"] == ["先进封装", "国产替代"]
    assert "刻蚀设备" in profile["company_overview"]["primary_products"]
    assert profile["business_composition"]["report_period"] == "2026-03-31"
    assert profile["business_composition"]["groups"][0]["classify_type"] == "按产品"
    assert profile["financial_snapshot"]["revenue_ttm"] == pytest.approx(44600000000)
    assert profile["financial_snapshot"]["np_parent_ttm"] == pytest.approx(7800000000)
    assert profile["financial_snapshot"]["operating_cash_flow"] == pytest.approx(1860000000)
    assert profile["financial_snapshot"]["roe"] == pytest.approx(0.128)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/xiwei/stock_research && rtk python -m pytest tests/test_dashboard_asset_profile.py -k "overview_business_and_financial_sections" -q
```

Expected: FAIL because `build_asset_profile()` does not yet return `company_overview`, `business_composition`, or `financial_snapshot`.

- [ ] **Step 3: Write the minimal backend aggregation and type contract**

Create `/Users/xiwei/stock_research/src/stock_research/dashboard/asset_profile_fundamentals.py` with these helpers:

```python
from collections import defaultdict
from typing import Any

from stock_research.db import fetch_all
from stock_research.services.finance_ttm import load_income_ttm_rows
from stock_research.services.point_in_time_finance import get_latest_cash_flow, get_latest_indicator


def load_company_overview(conn, asset_id: str, trade_date: str, company_profile: dict[str, Any] | None) -> dict[str, Any]:
    industry_sql = """
    SELECT industry_name
    FROM core.industry_membership
    WHERE asset_id = %s
      AND start_date <= %s
      AND (end_date IS NULL OR end_date >= %s)
    ORDER BY start_date DESC
    LIMIT 1
    """
    concept_sql = """
    SELECT concept_name
    FROM core.concept_membership
    WHERE asset_id = %s
      AND start_date <= %s
      AND (end_date IS NULL OR end_date >= %s)
    ORDER BY concept_name
    LIMIT 6
    """
    composition_sql = """
    SELECT report_period::text AS report_period,
           classify_type,
           item_name,
           revenue_ratio
    FROM finance.main_business_composition
    WHERE asset_id = %s
      AND report_period <= %s
    ORDER BY report_period DESC, revenue_ratio DESC NULLS LAST, item_name
    LIMIT 20
    """
    industry_rows = fetch_all(conn, industry_sql, [asset_id, trade_date, trade_date])
    concept_rows = fetch_all(conn, concept_sql, [asset_id, trade_date, trade_date])
    composition_rows = fetch_all(conn, composition_sql, [asset_id, trade_date])

    industry = str(industry_rows[0]["industry_name"]) if industry_rows else None
    concept_tags = [str(row["concept_name"]) for row in concept_rows if str(row.get("concept_name") or "").strip()]
    product_names = [
        str(row["item_name"])
        for row in composition_rows
        if str(row.get("classify_type") or "") == "按产品"
    ][:3]
    business_summary = "、".join(product_names) if product_names else None
    profile_summary = " / ".join(
        value for value in [industry, company_profile.get("board") if company_profile else None, business_summary] if value
    ) or None
    missing_fields = [
        field
        for field, value in {
            "industry": industry,
            "concept_tags": concept_tags,
            "business_summary": business_summary,
            "primary_products": product_names,
            "profile_summary": profile_summary,
        }.items()
        if value in (None, [], "")
    ]
    return {
        "industry": industry,
        "concept_tags": concept_tags,
        "business_summary": business_summary,
        "primary_products": product_names,
        "profile_summary": profile_summary,
        "data_status": "available" if not missing_fields else "partial",
        "missing_fields": missing_fields,
    }


def load_business_composition(conn, asset_id: str, trade_date: str) -> dict[str, Any]:
    sql = """
    SELECT report_period::text AS report_period,
           classify_type,
           item_name,
           revenue,
           revenue_ratio,
           gross_margin
    FROM finance.main_business_composition
    WHERE asset_id = %s
      AND report_period <= %s
    ORDER BY report_period DESC, classify_type, revenue_ratio DESC NULLS LAST, item_name
    """
    rows = fetch_all(conn, sql, [asset_id, trade_date])
    if not rows:
        return {"report_period": None, "groups": [], "data_status": "missing", "missing_fields": ["groups"]}

    latest_period = str(rows[0]["report_period"])[:10]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if str(row["report_period"])[:10] != latest_period:
            continue
        grouped[str(row["classify_type"])].append(
            {
                "item_name": str(row["item_name"]),
                "revenue": float(row["revenue"]) if row.get("revenue") is not None else None,
                "revenue_ratio": float(row["revenue_ratio"]) if row.get("revenue_ratio") is not None else None,
                "gross_margin": float(row["gross_margin"]) if row.get("gross_margin") is not None else None,
            }
        )
    groups = [{"classify_type": key, "items": value[:6]} for key, value in grouped.items()]
    return {
        "report_period": latest_period,
        "groups": groups,
        "data_status": "available" if groups else "partial",
        "missing_fields": [] if groups else ["groups"],
    }


def load_financial_snapshot(conn, asset_id: str, trade_date: str) -> dict[str, Any]:
    indicator = get_latest_indicator(conn, asset_id, trade_date) or {}
    cash_flow = get_latest_cash_flow(conn, asset_id, trade_date) or {}
    income_ttm = load_income_ttm_rows(
        conn,
        [asset_id],
        trade_date,
        value_columns=["revenue", "np_parent"],
    ).get(asset_id, {})
    values = {
        "report_period": str(indicator.get("report_period") or "")[:10] or None,
        "announcement_date": str(indicator.get("announcement_date") or "")[:10] or None,
        "revenue_ttm": income_ttm.get("revenue_ttm"),
        "np_parent_ttm": income_ttm.get("np_parent_ttm"),
        "gross_margin": indicator.get("gross_margin"),
        "roe": indicator.get("roe"),
        "operating_cash_flow": cash_flow.get("net_operate_cash_flow"),
        "debt_ratio": indicator.get("debt_ratio"),
        "ocf_to_np": indicator.get("ocf_to_np"),
    }
    missing_fields = [key for key, value in values.items() if value is None]
    return {
        **values,
        "data_status": "available" if len(missing_fields) <= 1 else "partial" if len(missing_fields) < len(values) else "missing",
        "missing_fields": missing_fields,
    }
```

Wire it in `/Users/xiwei/stock_research/src/stock_research/dashboard/asset_profile.py`:

```python
from stock_research.dashboard.asset_profile_fundamentals import (
    load_business_composition,
    load_company_overview,
    load_financial_snapshot,
)
```

Then replace the `return { ... }` inside `build_asset_profile()` with:

```python
    with connect(service) as conn:
        company_profile = _load_company_profile(canonical_asset_id, service=service)
        return {
            "asset_id": asset_id,
            "canonical_asset_id": canonical_asset_id,
            "asset": load_asset_detail(canonical_asset_id, service=service) or load_asset_detail(asset_id, service=service),
            "quote_snapshot": quote_snapshot,
            "company_profile": company_profile,
            "company_overview": load_company_overview(conn, canonical_asset_id, trade_date, company_profile),
            "business_composition": load_business_composition(conn, canonical_asset_id, trade_date),
            "financial_snapshot": load_financial_snapshot(conn, canonical_asset_id, trade_date),
            "valuation_snapshot": _load_valuation_snapshot(
                quote_snapshot=quote_snapshot,
                share_snapshot=share_snapshot,
                spot_snapshot=spot_snapshot,
                factor_valuation=factor_valuation,
            ),
            "bars": load_daily_bars(asset_id, start_date, end_date, adjust_type, service=service),
            "score": load_asset_score_for_dashboard(canonical_asset_id, trade_date, score_version, service=service),
            "signals": load_asset_watchlist_signals_for_dashboard(canonical_asset_id, trade_date, service=service),
            "decisions": load_asset_decision_history(canonical_asset_id, start_date, end_date, 50, service=service),
            "outcomes": load_asset_outcome_history(canonical_asset_id, start_date, end_date, None, 50, service=service),
            "factor_values": _load_factor_values(canonical_asset_id, trade_date, service=service),
            "coverage": _load_data_coverage(canonical_asset_id, service=service),
        }
```

Extend `/Users/xiwei/stock_research/dashboard/src/api/types.ts`:

```ts
export type CompanyOverview = {
  industry: string | null;
  concept_tags: string[];
  business_summary: string | null;
  primary_products: string[];
  profile_summary: string | null;
  data_status: 'available' | 'partial' | 'missing' | string;
  missing_fields: string[];
};

export type BusinessCompositionGroup = {
  classify_type: string;
  items: Array<{
    item_name: string;
    revenue: number | null;
    revenue_ratio: number | null;
    gross_margin: number | null;
  }>;
};

export type BusinessCompositionSnapshot = {
  report_period: string | null;
  groups: BusinessCompositionGroup[];
  data_status: 'available' | 'partial' | 'missing' | string;
  missing_fields: string[];
};

export type FinancialSnapshot = {
  report_period: string | null;
  announcement_date: string | null;
  revenue_ttm: number | null;
  np_parent_ttm: number | null;
  gross_margin: number | null;
  roe: number | null;
  operating_cash_flow: number | null;
  debt_ratio: number | null;
  ocf_to_np: number | null;
  data_status: 'available' | 'partial' | 'missing' | string;
  missing_fields: string[];
};
```

And add these fields inside `AssetProfile`:

```ts
  company_overview?: CompanyOverview | null;
  business_composition?: BusinessCompositionSnapshot | null;
  financial_snapshot?: FinancialSnapshot | null;
```

- [ ] **Step 4: Run backend test to verify it passes**

Run:

```bash
cd /Users/xiwei/stock_research && rtk python -m pytest tests/test_dashboard_asset_profile.py -q
```

Expected: PASS, including the new assertions for overview, composition, and financial snapshot.

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
rtk git add src/stock_research/dashboard/asset_profile_fundamentals.py src/stock_research/dashboard/asset_profile.py tests/test_dashboard_asset_profile.py dashboard/src/api/types.ts
rtk git commit -m "feat: enrich asset profile with company and fundamentals"
```

### Task 2: Render Company Basics And Business Quality As First-Class Sections

**Files:**
- Create: `/Users/xiwei/stock_research/dashboard/src/components/stock-workspace/CompanyBasicsSection.tsx`
- Create: `/Users/xiwei/stock_research/dashboard/src/components/stock-workspace/BusinessQualitySection.tsx`
- Modify: `/Users/xiwei/stock_research/dashboard/src/components/StockWorkspace.tsx`
- Modify: `/Users/xiwei/stock_research/dashboard/src/styles.css`
- Modify: `/Users/xiwei/stock_research/dashboard/tests/stock-workspace.test.tsx`

- [ ] **Step 1: Write the failing UI test**

Add this test near the existing section-order coverage in `/Users/xiwei/stock_research/dashboard/tests/stock-workspace.test.tsx`:

```tsx
it('renders company basics and business quality before price behavior', async () => {
  apiMocks.fetchAssetProfile.mockResolvedValueOnce(
    makeProfile({
      company_overview: {
        industry: '半导体设备',
        concept_tags: ['先进封装', '国产替代'],
        business_summary: '主营聚焦刻蚀设备、薄膜沉积设备。',
        primary_products: ['刻蚀设备', '薄膜沉积设备'],
        profile_summary: '半导体设备 / 主板 / 主营聚焦刻蚀设备、薄膜沉积设备。',
        data_status: 'available',
        missing_fields: []
      },
      business_composition: {
        report_period: '2026-03-31',
        data_status: 'available',
        missing_fields: [],
        groups: [
          {
            classify_type: '按产品',
            items: [
              { item_name: '刻蚀设备', revenue: 5200000000, revenue_ratio: 0.41, gross_margin: 0.43 },
              { item_name: '薄膜沉积设备', revenue: 3100000000, revenue_ratio: 0.24, gross_margin: 0.39 }
            ]
          }
        ]
      },
      financial_snapshot: {
        report_period: '2026-03-31',
        announcement_date: '2026-04-28',
        revenue_ttm: 44600000000,
        np_parent_ttm: 7800000000,
        gross_margin: 0.412,
        roe: 0.128,
        operating_cash_flow: 1860000000,
        debt_ratio: 0.342,
        ocf_to_np: 1.09,
        data_status: 'available',
        missing_fields: []
      }
    })
  );

  render(<StockWorkspace initialAssetId="002371.SZ" />);

  const basics = await screen.findByRole('region', { name: '公司基础信息' });
  const quality = await screen.findByRole('region', { name: '主营构成与经营质量' });
  const price = await screen.findByRole('region', { name: '今日价格行为' });

  expect(within(basics).getByText('半导体设备')).toBeVisible();
  expect(within(basics).getByText('先进封装')).toBeVisible();
  expect(within(quality).getByText('刻蚀设备')).toBeVisible();
  expect(within(quality).getByText('TTM营收')).toBeVisible();

  expect(basics.compareDocumentPosition(price) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(quality.compareDocumentPosition(price) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard && rtk npm test -- --run tests/stock-workspace.test.tsx -t "renders company basics and business quality before price behavior"
```

Expected: FAIL because the page still renders `基本面与档案`, not the new `公司基础信息` and `主营构成与经营质量` sections.

- [ ] **Step 3: Write minimal presentational components and wire them in**

Create `/Users/xiwei/stock_research/dashboard/src/components/stock-workspace/CompanyBasicsSection.tsx`:

```tsx
import type { CompanyOverview, CompanyProfile } from '../../api/types';

type CompanyBasicsSectionProps = {
  companyProfile: CompanyProfile | null | undefined;
  companyOverview: CompanyOverview | null | undefined;
};

export function CompanyBasicsSection({ companyProfile, companyOverview }: CompanyBasicsSectionProps) {
  return (
    <section className="workspace-band stock-company-basics" role="region" aria-label="公司基础信息">
      <div className="section-heading">
        <div>
          <h2>公司基础信息</h2>
          <p className="muted">先回答“这家公司到底是做什么的”。</p>
        </div>
        <span className="status-chip neutral">{companyOverview?.data_status ?? 'missing'}</span>
      </div>
      <div className="stock-basics-grid">
        <article className="stock-mini-panel">
          <span>行业</span>
          <strong>{companyOverview?.industry ?? '-'}</strong>
        </article>
        <article className="stock-mini-panel">
          <span>细分赛道</span>
          <strong>{companyOverview?.concept_tags?.join(' / ') || '-'}</strong>
        </article>
        <article className="stock-mini-panel stock-mini-panel-wide">
          <span>主营业务简介</span>
          <strong>{companyOverview?.business_summary ?? '暂无主营构成来源'}</strong>
        </article>
        <article className="stock-mini-panel stock-mini-panel-wide">
          <span>主要产品 / 解决方案</span>
          <strong>{companyOverview?.primary_products?.join('、') || '-'}</strong>
        </article>
        <article className="stock-mini-panel">
          <span>上市板块</span>
          <strong>{companyProfile?.board ?? '-'}</strong>
        </article>
        <article className="stock-mini-panel">
          <span>交易所</span>
          <strong>{companyProfile?.exchange ?? '-'}</strong>
        </article>
        <article className="stock-mini-panel">
          <span>上市日期</span>
          <strong>{companyProfile?.list_date ?? '-'}</strong>
        </article>
        <article className="stock-mini-panel">
          <span>地区</span>
          <strong>{companyProfile?.region ?? '-'}</strong>
        </article>
        <article className="stock-mini-panel stock-mini-panel-full">
          <span>公司简况摘要</span>
          <strong>{companyOverview?.profile_summary ?? '暂无结构化公司摘要'}</strong>
        </article>
      </div>
    </section>
  );
}
```

Create `/Users/xiwei/stock_research/dashboard/src/components/stock-workspace/BusinessQualitySection.tsx`:

```tsx
import type { BusinessCompositionSnapshot, FinancialSnapshot } from '../../api/types';

function formatChineseAmount(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '-';
  if (Math.abs(value) >= 100000000) return `${(value / 100000000).toFixed(2)}亿`;
  if (Math.abs(value) >= 10000) return `${(value / 10000).toFixed(2)}万`;
  return value.toFixed(2);
}

function formatPct(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '-';
  return `${(value * 100).toFixed(1)}%`;
}

type BusinessQualitySectionProps = {
  businessComposition: BusinessCompositionSnapshot | null | undefined;
  financialSnapshot: FinancialSnapshot | null | undefined;
};

export function BusinessQualitySection({ businessComposition, financialSnapshot }: BusinessQualitySectionProps) {
  return (
    <section className="workspace-band stock-business-quality" role="region" aria-label="主营构成与经营质量">
      <div className="section-heading">
        <div>
          <h2>主营构成与经营质量</h2>
          <p className="muted">解释这家公司靠什么赚钱，以及这些业务的质量如何。</p>
        </div>
        <span className="status-chip neutral">{businessComposition?.report_period ?? '无分部数据'}</span>
      </div>
      <div className="stock-business-layout">
        <div className="stock-composition-groups">
          {(businessComposition?.groups ?? []).map((group) => (
            <article key={group.classify_type} className="stock-mini-panel">
              <div className="section-heading compact-heading">
                <h3>{group.classify_type}</h3>
              </div>
              <div className="stock-composition-list">
                {group.items.map((item) => (
                  <div key={`${group.classify_type}-${item.item_name}`} className="stock-composition-row">
                    <strong>{item.item_name}</strong>
                    <span>{formatPct(item.revenue_ratio)}</span>
                    <span>{formatChineseAmount(item.revenue)}</span>
                    <span>{formatPct(item.gross_margin)}</span>
                  </div>
                ))}
              </div>
            </article>
          ))}
          {(businessComposition?.groups ?? []).length === 0 ? <p className="muted">暂无主营构成数据，保留经营质量摘要。</p> : null}
        </div>
        <article className="stock-mini-panel stock-financial-quality-panel">
          <div className="section-heading compact-heading">
            <h3>经营质量摘要</h3>
            <span className="muted">{financialSnapshot?.report_period ?? 'missing'}</span>
          </div>
          <div className="stock-summary-strip compact">
            <div><span>TTM营收</span><strong>{formatChineseAmount(financialSnapshot?.revenue_ttm)}</strong></div>
            <div><span>TTM归母净利</span><strong>{formatChineseAmount(financialSnapshot?.np_parent_ttm)}</strong></div>
            <div><span>毛利率</span><strong>{formatPct(financialSnapshot?.gross_margin)}</strong></div>
            <div><span>ROE</span><strong>{formatPct(financialSnapshot?.roe)}</strong></div>
            <div><span>经营现金流</span><strong>{formatChineseAmount(financialSnapshot?.operating_cash_flow)}</strong></div>
            <div><span>资产负债率</span><strong>{formatPct(financialSnapshot?.debt_ratio)}</strong></div>
            <div><span>OCF / NP</span><strong>{financialSnapshot?.ocf_to_np != null ? `${financialSnapshot.ocf_to_np.toFixed(2)}x` : '-'}</strong></div>
          </div>
        </article>
      </div>
    </section>
  );
}
```

Import and render both in `/Users/xiwei/stock_research/dashboard/src/components/StockWorkspace.tsx`:

```tsx
import { BusinessQualitySection } from './stock-workspace/BusinessQualitySection';
import { CompanyBasicsSection } from './stock-workspace/CompanyBasicsSection';
```

Then replace the current `基本面与档案` section with:

```tsx
<CompanyBasicsSection
  companyProfile={companyProfile}
  companyOverview={profile?.company_overview}
/>

<BusinessQualitySection
  businessComposition={profile?.business_composition}
  financialSnapshot={profile?.financial_snapshot}
/>
```

Add CSS in `/Users/xiwei/stock_research/dashboard/src/styles.css`:

```css
.stock-company-basics,
.stock-business-quality {
  border: 1px solid var(--line-soft);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.96));
}

.stock-basics-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.stock-mini-panel-wide {
  grid-column: span 2;
}

.stock-mini-panel-full {
  grid-column: 1 / -1;
}

.stock-business-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(320px, 0.9fr);
  gap: 16px;
}

.stock-composition-groups {
  display: grid;
  gap: 12px;
}

.stock-composition-row {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) repeat(3, minmax(72px, auto));
  gap: 8px;
  align-items: center;
}

@media (max-width: 900px) {
  .stock-basics-grid,
  .stock-business-layout {
    grid-template-columns: 1fr;
  }

  .stock-mini-panel-wide,
  .stock-mini-panel-full {
    grid-column: auto;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard && rtk npm test -- --run tests/stock-workspace.test.tsx -t "renders company basics and business quality before price behavior"
```

Expected: PASS, and the page now exposes `公司基础信息` and `主营构成与经营质量` ahead of price behavior.

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
rtk git add dashboard/src/components/stock-workspace/CompanyBasicsSection.tsx dashboard/src/components/stock-workspace/BusinessQualitySection.tsx dashboard/src/components/StockWorkspace.tsx dashboard/src/styles.css dashboard/tests/stock-workspace.test.tsx
rtk git commit -m "feat: add company basics and business quality sections"
```

### Task 3: Finalize Decision-First Dual-Mode Layout And Simplify The Right Rail

**Files:**
- Modify: `/Users/xiwei/stock_research/dashboard/src/components/StockWorkspace.tsx`
- Modify: `/Users/xiwei/stock_research/dashboard/src/styles.css`
- Modify: `/Users/xiwei/stock_research/dashboard/tests/stock-workspace.test.tsx`

- [ ] **Step 1: Write the failing integration test**

Add this test in `/Users/xiwei/stock_research/dashboard/tests/stock-workspace.test.tsx` near the existing Tech Bottleneck enhanced-mode tests:

```tsx
it('elevates tech bottleneck thesis after the decision band and removes external evidence buttons', async () => {
  const entryContext: StockEntryContext = {
    sourceWorkspace: 'techBottleneck',
    assetId: '002371.SZ',
    stockName: '北方华创',
    bottleneckRelevance: 'likely_core_pending',
    bottleneckConfidenceScore: 69,
    evidenceQualityScore: 33,
    reportStatus: 'partial_primary_source_missing',
    evidenceGapNote: '缺少订单与客户验证页级证据',
    nextAction: '先补订单/认证，再判断是否继续跟踪',
    reviewStatus: 'pending_review'
  };

  render(<StockWorkspace initialAssetId="002371.SZ" entryContext={entryContext} />);

  const conclusion = await screen.findByRole('region', { name: '明日处理结论' });
  const thesis = await screen.findByRole('region', { name: '科技卡脖子 thesis 复盘' });
  const basics = await screen.findByRole('region', { name: '公司基础信息' });

  expect(conclusion.compareDocumentPosition(thesis) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(thesis.compareDocumentPosition(basics) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.queryByRole('button', { name: '打开新闻' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '打开研报' })).not.toBeInTheDocument();
  expect(screen.queryByRole('region', { name: '复盘摘要' })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard && rtk npm test -- --run tests/stock-workspace.test.tsx -t "elevates tech bottleneck thesis after the decision band and removes external evidence buttons"
```

Expected: FAIL because the old `复盘摘要` region still exists, the thesis section is still rendered above the decision band, and the right rail still shows `打开新闻` / `打开研报`.

- [ ] **Step 3: Reorder the page and simplify the control rail**

In `/Users/xiwei/stock_research/dashboard/src/components/StockWorkspace.tsx`, make these structural changes:

1. Keep `明日处理结论` as the first major block.
2. Move `科技卡脖子 thesis 复盘` so it renders immediately after `明日处理结论` only when `isTechBottleneckEntry` is true.
3. Delete the standalone `复盘摘要` section.
4. Fold its useful content into the top band as “三大决策驱动”.
5. Remove the `外部证据入口` button row from the right rail.

Replace the top summary block with:

```tsx
const decisionDrivers = [
  reviewMetrics.state ? `价格状态：${reviewMetrics.state}` : null,
  quoteSnapshot?.amount_ratio_20d != null ? `量能比：${formatRatio(quoteSnapshot.amount_ratio_20d)}` : null,
  visibleEvidenceDigest?.bucket ? `证据分桶：${formatEvidenceBucket(visibleEvidenceDigest.bucket)}` : null
].filter((value): value is string => Boolean(value)).slice(0, 3);
```

And inside `明日处理结论` add:

```tsx
<div className="tag-stack" aria-label="三大决策驱动">
  {decisionDrivers.map((driver) => (
    <span key={driver} className="status-chip neutral">
      {driver}
    </span>
  ))}
</div>
```

Then place the sections in this order inside the `profile ? (...) : null` block:

```tsx
<>
  <section className="workspace-band stock-review-summary stock-review-conclusion" role="region" aria-label="明日处理结论">
    {/* existing conclusion content + decisionDrivers */}
  </section>

  {isTechBottleneckEntry ? (
    <section className="workspace-band stock-tech-thesis" role="region" aria-label="科技卡脖子 thesis 复盘">
      {/* existing thesis content */}
    </section>
  ) : null}

  <CompanyBasicsSection
    companyProfile={companyProfile}
    companyOverview={profile?.company_overview}
  />

  <BusinessQualitySection
    businessComposition={profile?.business_composition}
    financialSnapshot={profile?.financial_snapshot}
  />

  <section className="workspace-band stock-price-behavior" role="region" aria-label="今日价格行为">
    {/* existing price behavior section */}
  </section>

  <div className="stock-detail-layout">
    <aside className="workspace-band stock-context-rail" role="region" aria-label="复盘决策栏">
      {/* OperatorDecisionPanel + 复盘日志 only */}
    </aside>
    <div className="stock-detail-main">
      <section className="stock-evidence-zone" role="region" aria-label="支撑证据">
        {/* existing evidence sections */}
      </section>
    </div>
  </div>
</>
```

Update CSS in `/Users/xiwei/stock_research/dashboard/src/styles.css`:

```css
.stock-review-conclusion .tag-stack {
  margin-top: 12px;
}

.stock-detail-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(280px, 0.78fr);
  gap: 16px;
  align-items: start;
}

.stock-context-rail {
  position: sticky;
  top: 16px;
}

.stock-price-behavior .stock-dossier-grid {
  grid-template-columns: 1fr;
}

@media (max-width: 900px) {
  .stock-detail-layout {
    grid-template-columns: 1fr;
  }

  .stock-context-rail {
    position: static;
  }
}
```

- [ ] **Step 4: Run tests and build to verify the dual-mode layout**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard && rtk npm test -- --run tests/stock-workspace.test.tsx
cd /Users/xiwei/stock_research/dashboard && rtk npm run build
```

Expected:

- Vitest PASS for `tests/stock-workspace.test.tsx`
- Vite build PASS, with only the existing chunk-size warning if it already exists

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
rtk git add dashboard/src/components/StockWorkspace.tsx dashboard/src/styles.css dashboard/tests/stock-workspace.test.tsx
rtk git commit -m "feat: finalize decision-first stock workspace layout"
```

### Task 4: Full Regression Across Generic And Tech Bottleneck Entry Paths

**Files:**
- Modify: `/Users/xiwei/stock_research/dashboard/tests/stock-workspace.test.tsx`

- [ ] **Step 1: Add final regression tests for empty-state fallbacks**

Append this test in `/Users/xiwei/stock_research/dashboard/tests/stock-workspace.test.tsx`:

```tsx
it('keeps review flow readable when overview and composition data are missing', async () => {
  apiMocks.fetchAssetProfile.mockResolvedValueOnce(
    makeProfile({
      company_overview: {
        industry: null,
        concept_tags: [],
        business_summary: null,
        primary_products: [],
        profile_summary: null,
        data_status: 'missing',
        missing_fields: ['industry', 'concept_tags', 'business_summary', 'primary_products', 'profile_summary']
      },
      business_composition: {
        report_period: null,
        groups: [],
        data_status: 'missing',
        missing_fields: ['groups']
      },
      financial_snapshot: {
        report_period: null,
        announcement_date: null,
        revenue_ttm: null,
        np_parent_ttm: null,
        gross_margin: null,
        roe: null,
        operating_cash_flow: null,
        debt_ratio: null,
        ocf_to_np: null,
        data_status: 'missing',
        missing_fields: ['revenue_ttm', 'np_parent_ttm', 'gross_margin', 'roe', 'operating_cash_flow', 'debt_ratio', 'ocf_to_np']
      }
    })
  );

  render(<StockWorkspace initialAssetId="000001.SZ" />);

  expect(await screen.findByRole('region', { name: '公司基础信息' })).toBeInTheDocument();
  expect(screen.getByText('暂无主营构成来源')).toBeVisible();
  expect(screen.getByText('暂无主营构成数据，保留经营质量摘要。')).toBeVisible();
  expect(screen.getByRole('region', { name: '今日价格行为' })).toBeInTheDocument();
  expect(screen.getByRole('region', { name: '支撑证据' })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the focused regression test**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard && rtk npm test -- --run tests/stock-workspace.test.tsx -t "keeps review flow readable when overview and composition data are missing"
```

Expected: PASS and confirms the page still reads well even without enriched fundamentals.

- [ ] **Step 3: Run the complete relevant test suite**

Run:

```bash
cd /Users/xiwei/stock_research && rtk python -m pytest tests/test_dashboard_asset_profile.py -q
cd /Users/xiwei/stock_research/dashboard && rtk npm test -- --run tests/stock-workspace.test.tsx tests/tech-bottleneck-route.test.tsx tests/tech-bottleneck-watchlist-review-upgrade.test.tsx
cd /Users/xiwei/stock_research/dashboard && rtk npm run build
```

Expected:

- Python tests PASS
- Frontend tests PASS
- Build PASS

- [ ] **Step 4: Manually verify the two real reading modes**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard && rtk npm run dev -- --host 127.0.0.1 --port 5174
```

Then verify in browser:

- Generic stock path shows `明日处理结论 -> 公司基础信息 -> 主营构成与经营质量 -> 今日价格行为 -> 支撑证据 -> 复盘操作`
- Tech Bottleneck stock path shows `明日处理结论 -> 科技卡脖子 thesis 复盘 -> 公司基础信息 -> 主营构成与经营质量 -> 今日价格行为 -> 支撑证据 -> 复盘操作`
- No duplicate stock page exists
- No `打开新闻` / `打开研报` buttons remain in the right rail

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
rtk git add dashboard/tests/stock-workspace.test.tsx
rtk git commit -m "test: cover stock workspace dual-mode fallbacks"
```
