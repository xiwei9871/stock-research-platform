# Stock Workspace Watchlist Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 2 of the redesigned dashboard: a usable single-stock investigation page, a read-only research queue watchlist, and navigation links from news/watchlist into the Stock Workspace.

**Architecture:** Reuse existing FastAPI dashboard endpoints instead of adding a new backend domain model. The frontend gets two small client additions, then composes `AssetProfile`, public news, and watchlist signals into focused React workspaces with request guards and tests.

**Tech Stack:** FastAPI backend, React + TypeScript frontend, Vitest + Testing Library, Playwright smoke coverage where existing tests already exercise navigation.

---

## Scope

Phase 2 includes:

- Stock Workspace as the single-stock hub for price, volume, factor score, factor components, related public news, current watchlist signals, strategy/review history, outcomes, generated evidence links, and a clear Research Reports Phase 3 panel.
- Watchlist as an EOD research queue with status, priority, signal, risk tags, reason, next action, and Open Stock navigation.
- Cross-workspace navigation from Watchlist and eligible News rows into Stock Workspace.
- Client support for `/api/assets/search` and `/api/watchlists/{watchlist_id}`.

Phase 2 excludes:

- External broker/institution research report ingestion. The Stock Workspace should show a Phase 3 panel with no fake data.
- Full global search.
- Realtime market monitor. Watchlist remains EOD and date-driven.
- Durable manual watchlist editing. The queue is read-only over existing signal data.

## File Structure

- Modify `dashboard/src/api/types.ts`
  - Add `WatchlistResponse`.
  - Add `AssetSearchResponse` if the plan implementer wants to type the raw API response, but expose `searchAssets()` as `Promise<AssetSummary[]>`.
- Modify `dashboard/src/api/client.ts`
  - Add `searchAssets(q, limit)`.
  - Add `fetchWatchlistSignals(watchlistId, tradeDate)`.
- Modify `dashboard/src/components/AppShell.tsx`
  - Own `selectedAssetId`.
  - Add `openStockWorkspace(assetId)`.
  - Pass `selectedAssetId` to `StockWorkspace`.
  - Pass `onOpenAsset` to `NewsWorkspace` and `WatchlistWorkspace`.
- Replace `dashboard/src/components/StockWorkspace.tsx`
  - Build the full single-stock page.
  - Reuse `AssetChart` and `fetchAssetProfile`.
  - Fetch related Sina public news by stock code/name keyword.
- Replace `dashboard/src/components/WatchlistWorkspace.tsx`
  - Build the EOD research queue over `/api/watchlists/default`.
  - Add filters and Open Stock actions.
- Modify `dashboard/src/components/NewsWorkspace.tsx`
  - Accept `onOpenAsset?: (assetId: string) => void`.
  - Add a deterministic 6-digit stock-code extractor.
  - Render Open Stock only when an item contains a code candidate.
- Modify `dashboard/src/styles.css`
  - Add compact workspace styles for stock header, metric strips, evidence grids, queue filters, queue table, and action buttons.
- Create `dashboard/tests/stock-workspace.test.tsx`.
- Create `dashboard/tests/watchlist-workspace.test.tsx`.
- Modify `dashboard/tests/news-workspace.test.tsx`.
- Modify `dashboard/tests/platform-client.test.ts`.
- Modify `dashboard/tests/platform-full-flow.spec.ts` only if the existing navigation smoke test asserts the old planned-panel text.

## Shared Implementation Details

Use these constants in the new workspaces unless a nearby file already exports them:

```ts
const DEFAULT_ASSET_ID = '000001.SZ';
const DEFAULT_TRADE_DATE = '2026-06-08';
const DEFAULT_START_DATE = '2025-12-10';
const DEFAULT_END_DATE = '2026-06-08';
const DEFAULT_SCORE_VERSION = 'manual_v1';
const DEFAULT_ADJUST_TYPE = 'qfq';
const DEFAULT_WATCHLIST_ID = 'default';
```

Normalize direct user input with:

```ts
function normalizeAssetId(value: string) {
  const trimmed = value.trim();
  if (/^\d{6}$/.test(trimmed)) {
    return `${trimmed}.${trimmed.startsWith('6') ? 'SH' : 'SZ'}`;
  }
  return trimmed.toUpperCase();
}
```

Format unknown values with:

```ts
function formatValue(value: unknown) {
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(4);
  if (typeof value === 'string' && value.length > 0) return value;
  if (value == null || value === '') return '-';
  return JSON.stringify(value);
}
```

Extract candidate stock IDs from public news with:

```ts
export function getNewsAssetCandidate(item: PublicNewsItem) {
  const rawCandidates = [
    item.raw_payload.asset_id,
    item.raw_payload.stock_code,
    item.raw_payload.symbol,
    item.raw_payload.code,
    item.title,
    item.summary,
    item.url
  ];
  for (const candidate of rawCandidates) {
    if (typeof candidate !== 'string') continue;
    const fullMatch = candidate.match(/\b\d{6}\.(SH|SZ)\b/i);
    if (fullMatch) return fullMatch[0].toUpperCase();
    const sixDigitMatch = candidate.match(/\b\d{6}\b/);
    if (sixDigitMatch) return normalizeAssetId(sixDigitMatch[0]);
  }
  return null;
}
```

## Task 1: Add Client Methods for Asset Search and Watchlist Signals

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/tests/platform-client.test.ts`

- [ ] **Step 1: Write failing client tests**

Add imports in `dashboard/tests/platform-client.test.ts`:

```ts
import { fetchWatchlistSignals, searchAssets } from '../src/api/client';
```

Add tests:

```ts
it('searches assets through the dashboard API', async () => {
  fetchMock.mockResolvedValueOnce({
    ok: true,
    json: async () => ({
      items: [{ asset_id: '000001.SZ', symbol: '000001', name: '平安银行', exchange: 'SZ', board: null, is_active: true }]
    })
  } as Response);

  const items = await searchAssets('平安', 5);

  expect(fetchMock).toHaveBeenCalledWith('/api/assets/search?q=%E5%B9%B3%E5%AE%89&limit=5');
  expect(items).toEqual([
    { asset_id: '000001.SZ', symbol: '000001', name: '平安银行', exchange: 'SZ', board: null, is_active: true }
  ]);
});

it('fetches watchlist signal rows for an EOD date', async () => {
  fetchMock.mockResolvedValueOnce({
    ok: true,
    json: async () => ({
      watchlist_id: 'default',
      trade_date: '2026-06-08',
      items: [
        {
          watchlist_id: 'default',
          trade_date: '2026-06-08',
          asset_id: '000001.SZ',
          stock_code: '000001',
          stock_name: '平安银行',
          priority: 8,
          signal_score: 82.4,
          primary_signal: 'candidate',
          signal_tags: ['momentum'],
          risk_tags: ['earnings'],
          must_watch: true,
          reason_json: { next_action: 'review close above 10d high' }
        }
      ]
    })
  } as Response);

  const items = await fetchWatchlistSignals('default', '2026-06-08');

  expect(fetchMock).toHaveBeenCalledWith('/api/watchlists/default?trade_date=2026-06-08');
  expect(items[0].asset_id).toBe('000001.SZ');
});
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
npm --prefix dashboard test -- platform-client.test.ts
```

Expected: TypeScript/Vitest fails because `searchAssets` and `fetchWatchlistSignals` are not exported.

- [ ] **Step 3: Add response types**

Add to `dashboard/src/api/types.ts` after `WatchlistSignalRow`:

```ts
export type WatchlistResponse = {
  watchlist_id: string;
  trade_date: string;
  items: WatchlistSignalRow[];
};
```

Add after `AssetSummary`:

```ts
export type AssetSearchResponse = {
  items: AssetSummary[];
};
```

- [ ] **Step 4: Add client methods**

Update the type import in `dashboard/src/api/client.ts`:

```ts
import type {
  AssetProfile,
  AssetSearchResponse,
  BarPoint,
  BacktestRunRequest,
  BacktestRunResult,
  DashboardOverview,
  DecisionEventRow,
  DecisionOutcomeRow,
  ExperimentProposalRow,
  ExperimentReplayRow,
  FactorLibraryRow,
  FactorScorePreview,
  FactorSelection,
  MarketMonitorPayload,
  OutcomeAnalyticsRow,
  PlatformSummary,
  PublicNewsRefreshResponse,
  PublicNewsResponse,
  ScoreRow,
  ShadowAnalyticsReviewRow,
  ShadowFollowUpRow,
  ShadowFollowUpResolutionRow,
  ShadowReviewDecisionRow,
  ShadowOutcomeAnalyticsRow,
  ShadowOutcomeRow,
  ShadowWatchlistRow,
  StrategyCatalogItem,
  StrategyEvidenceArtifact,
  StrategyMetricRow,
  StrategyPositionSnapshot,
  StrategyReplayPayload,
  StrategySignal,
  StrategyTrade,
  StrategyValidationRun,
  WatchlistResponse,
  WatchlistSignalRow
} from './types';
```

Add after `fetchPublicNews`:

```ts
export async function searchAssets(q: string, limit = 10) {
  const payload = await getJson<AssetSearchResponse>(
    `/api/assets/search?q=${encodeURIComponent(q)}&limit=${limit}`
  );
  return payload.items;
}

export async function fetchWatchlistSignals(watchlistId: string, tradeDate: string): Promise<WatchlistSignalRow[]> {
  const payload = await getJson<WatchlistResponse>(
    `/api/watchlists/${encodeURIComponent(watchlistId)}?trade_date=${encodeURIComponent(tradeDate)}`
  );
  return payload.items;
}
```

- [ ] **Step 5: Run tests and commit**

Run:

```bash
npm --prefix dashboard test -- platform-client.test.ts
```

Expected: tests pass.

Commit:

```bash
git add dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/tests/platform-client.test.ts
git commit -m "feat: add stock workspace client APIs"
```

## Task 2: Build the Stock Workspace

**Files:**
- Replace: `dashboard/src/components/StockWorkspace.tsx`
- Create: `dashboard/tests/stock-workspace.test.tsx`
- Modify: `dashboard/src/styles.css`

- [ ] **Step 1: Write the failing Stock Workspace tests**

Create `dashboard/tests/stock-workspace.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { StockWorkspace } from '../src/components/StockWorkspace';
import type { AssetProfile, PublicNewsResponse } from '../src/api/types';
import * as api from '../src/api/client';

vi.mock('../src/api/client', () => ({
  fetchAssetProfile: vi.fn(),
  fetchPublicNews: vi.fn(),
  searchAssets: vi.fn()
}));

const apiMocks = vi.mocked(api);

function makeProfile(overrides: Partial<AssetProfile> = {}): AssetProfile {
  return {
    asset_id: '000001.SZ',
    canonical_asset_id: '000001.SZ',
    asset: { asset_id: '000001.SZ', symbol: '000001', name: '平安银行', exchange: 'SZ', board: null, is_active: true },
    bars: [
      { time: '2026-06-05', open: 10, high: 11, low: 9.8, close: 10.6, volume: 1000, amount: 10600 },
      { time: '2026-06-08', open: 10.6, high: 11.2, low: 10.4, close: 11, volume: 1300, amount: 14300 }
    ],
    score: {
      trade_date: '2026-06-08',
      asset_id: '000001.SZ',
      rank: 3,
      score_total: 82.4,
      score_version: 'manual_v1',
      score_components: { momentum: 31.2, quality: 18.4 }
    },
    signals: [
      {
        watchlist_id: 'default',
        trade_date: '2026-06-08',
        asset_id: '000001.SZ',
        stock_code: '000001',
        stock_name: '平安银行',
        priority: 8,
        signal_score: 82.4,
        primary_signal: 'candidate',
        signal_tags: ['momentum'],
        risk_tags: ['earnings'],
        must_watch: true,
        reason_json: { next_action: 'review close above 10d high' }
      }
    ],
    decisions: [
      {
        review_date: '2026-06-08',
        review_session_id: 'session-1',
        event_id: 'event-1',
        asset_id: '000001.SZ',
        stock_code: '000001',
        stock_name: '平安银行',
        decision_label: 'watch',
        evidence_artifact_id: 'artifact-1',
        evidence_path: 'reports/evidence/000001.md',
        source_context: 'strategy_lab',
        requires_follow_up: true,
        follow_up_note: 'check next close',
        notes: 'strong score',
        manual_review_required: true,
        auto_trade_enabled: false
      }
    ],
    outcomes: [],
    factor_values: [{ factor_name: 'momentum_20d', factor_group: 'momentum', factor_value: 0.21 }],
    coverage: { bars: { start: '2026-06-05', end: '2026-06-08' } },
    ...overrides
  };
}

const newsPayload: PublicNewsResponse = {
  warnings: [],
  items: [
    {
      news_id: 'n1',
      source: 'sina_finance',
      source_channel: 'company',
      category: 'company',
      title: '000001 平安银行公告',
      summary: '公司新闻',
      url: 'https://example.com/news/1',
      published_at: '2026-06-08T09:30:00',
      collected_at: '2026-06-08T09:31:00',
      raw_id: 'n1',
      raw_payload: {},
      status: 'active'
    }
  ]
};

beforeEach(() => {
  apiMocks.fetchAssetProfile.mockResolvedValue(makeProfile());
  apiMocks.fetchPublicNews.mockResolvedValue(newsPayload);
  apiMocks.searchAssets.mockResolvedValue([]);
});

describe('StockWorkspace', () => {
  it('loads a stock dossier with factors, news, watchlist, and evidence', async () => {
    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
    expect(screen.getByText(/Score 82.4/)).toBeInTheDocument();
    expect(screen.getByText('momentum')).toBeInTheDocument();
    expect(screen.getByText('000001 平安银行公告')).toBeInTheDocument();
    expect(screen.getByText('candidate')).toBeInTheDocument();
    expect(screen.getByText('reports/evidence/000001.md')).toBeInTheDocument();
  });

  it('normalizes six digit stock input before loading', async () => {
    const user = userEvent.setup();
    render(<StockWorkspace initialAssetId="000001.SZ" />);

    await user.clear(screen.getByLabelText('stock workspace asset'));
    await user.type(screen.getByLabelText('stock workspace asset'), '600000');
    await user.click(screen.getByRole('button', { name: 'Load Stock' }));

    await waitFor(() => {
      expect(apiMocks.fetchAssetProfile).toHaveBeenLastCalledWith(
        '600000.SH',
        '2026-06-08',
        '2025-12-10',
        '2026-06-08',
        'manual_v1',
        'qfq'
      );
    });
  });
});
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```bash
npm --prefix dashboard test -- stock-workspace.test.tsx
```

Expected: tests fail because the current Stock Workspace is a planned panel.

- [ ] **Step 3: Replace Stock Workspace implementation**

Replace `dashboard/src/components/StockWorkspace.tsx` with:

```tsx
import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { fetchAssetProfile, fetchPublicNews, searchAssets } from '../api/client';
import type { AssetProfile, AssetSummary, PublicNewsItem } from '../api/types';
import { AssetChart } from '../charts/AssetChart';

const DEFAULT_ASSET_ID = '000001.SZ';
const DEFAULT_TRADE_DATE = '2026-06-08';
const DEFAULT_START_DATE = '2025-12-10';
const DEFAULT_END_DATE = '2026-06-08';
const DEFAULT_SCORE_VERSION = 'manual_v1';
const DEFAULT_ADJUST_TYPE = 'qfq';

type StockWorkspaceProps = {
  initialAssetId?: string;
};

export function normalizeAssetId(value: string) {
  const trimmed = value.trim();
  if (/^\d{6}$/.test(trimmed)) return `${trimmed}.${trimmed.startsWith('6') ? 'SH' : 'SZ'}`;
  return trimmed.toUpperCase();
}

function formatValue(value: unknown) {
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(4);
  if (typeof value === 'string' && value.length > 0) return value;
  if (value == null || value === '') return '-';
  return JSON.stringify(value);
}

function getNewsQuery(profile: AssetProfile | null, assetId: string) {
  const symbol = profile?.asset?.symbol ?? assetId.split('.')[0];
  const name = profile?.asset?.name ?? '';
  return [symbol, name].filter(Boolean).join(' ');
}

function getFactorRows(profile: AssetProfile | null) {
  const componentRows = Object.entries(profile?.score?.score_components ?? {}).map(([name, value]) => ({
    group: 'score',
    name,
    value
  }));
  const valueRows = (profile?.factor_values ?? []).flatMap((row) => {
    if ('factor_name' in row) {
      return [{ group: formatValue(row.factor_group), name: formatValue(row.factor_name), value: row.factor_value }];
    }
    return Object.entries(row)
      .filter(([key]) => key !== 'asset_id' && key !== 'trade_date')
      .map(([name, value]) => ({ group: 'factor', name, value }));
  });
  return [...componentRows, ...valueRows].slice(0, 24);
}

export function StockWorkspace({ initialAssetId = DEFAULT_ASSET_ID }: StockWorkspaceProps) {
  const [assetInput, setAssetInput] = useState(initialAssetId);
  const [tradeDate, setTradeDate] = useState(DEFAULT_TRADE_DATE);
  const [startDate, setStartDate] = useState(DEFAULT_START_DATE);
  const [endDate, setEndDate] = useState(DEFAULT_END_DATE);
  const [profile, setProfile] = useState<AssetProfile | null>(null);
  const [newsItems, setNewsItems] = useState<PublicNewsItem[]>([]);
  const [assetMatches, setAssetMatches] = useState<AssetSummary[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(false);
  const requestIdRef = useRef(0);

  function loadStock(nextAssetId = assetInput) {
    const normalized = normalizeAssetId(nextAssetId);
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setAssetInput(normalized);
    setIsLoading(true);
    setError(null);

    fetchAssetProfile(normalized, tradeDate, startDate, endDate, DEFAULT_SCORE_VERSION, DEFAULT_ADJUST_TYPE)
      .then(async (nextProfile) => {
        const newsQuery = getNewsQuery(nextProfile, normalized);
        const [newsPayload, matches] = await Promise.all([
          fetchPublicNews({ source: 'sina_finance', q: newsQuery, limit: 20 }),
          searchAssets(normalized, 5).catch(() => [])
        ]);
        if (!mountedRef.current || requestIdRef.current !== requestId) return;
        setProfile(nextProfile);
        setNewsItems(newsPayload.items);
        setAssetMatches(matches);
        setIsLoading(false);
      })
      .catch((err: unknown) => {
        if (!mountedRef.current || requestIdRef.current !== requestId) return;
        setError(err instanceof Error ? err.message : String(err));
        setIsLoading(false);
      });
  }

  useEffect(() => {
    mountedRef.current = true;
    loadStock(initialAssetId);
    return () => {
      mountedRef.current = false;
      requestIdRef.current += 1;
    };
  }, [initialAssetId]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    loadStock();
  }

  const identity = profile?.asset?.name ?? profile?.asset_id ?? assetInput;
  const score = profile?.score?.score_total;
  const latestClose = profile?.bars.at(-1)?.close;
  const factorRows = useMemo(() => getFactorRows(profile), [profile]);

  return (
    <section className="stock-workspace" aria-label="Stock Workspace workspace">
      <header className="workspace-header">
        <h1>{identity}</h1>
        <p className="muted">Single-stock evidence hub for EOD price, factors, news, watchlist state, and strategy review history.</p>
      </header>

      <form className="workspace-toolbar compact-toolbar" onSubmit={handleSubmit}>
        <label>
          Stock
          <input aria-label="stock workspace asset" value={assetInput} onChange={(event) => setAssetInput(event.target.value)} />
        </label>
        <label>
          Trade Date
          <input aria-label="stock workspace trade date" type="date" value={tradeDate} onChange={(event) => setTradeDate(event.target.value)} />
        </label>
        <label>
          Start
          <input aria-label="stock workspace start date" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
        </label>
        <label>
          End
          <input aria-label="stock workspace end date" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
        </label>
        <button type="submit">Load Stock</button>
        {isLoading ? <span className="muted">Loading stock...</span> : null}
      </form>

      {error ? <p className="error-text">{error}</p> : null}

      {profile ? (
        <>
          <section className="stock-summary-strip" aria-label="Stock identity">
            <div><span>Asset</span><strong>{profile.canonical_asset_id}</strong></div>
            <div><span>Score</span><strong>{typeof score === 'number' ? `Score ${score.toFixed(1)}` : '-'}</strong></div>
            <div><span>Rank</span><strong>{profile.score?.rank ?? '-'}</strong></div>
            <div><span>Latest Close</span><strong>{formatValue(latestClose)}</strong></div>
            <div><span>Signals</span><strong>{profile.signals.length}</strong></div>
          </section>

          <section className="workspace-band data-chart-panel" aria-label="Stock price and volume">
            <div className="section-heading">
              <h2>Price / Volume</h2>
              <span className="muted">{profile.bars.length} EOD bars</span>
            </div>
            {profile.bars.length > 0 ? <AssetChart bars={profile.bars} /> : <p className="muted">No bars available.</p>}
          </section>

          <section className="stock-evidence-grid">
            <article className="workspace-band">
              <div className="section-heading"><h2>Factor Breakdown</h2></div>
              <table className="data-table compact-table">
                <thead><tr><th>Group</th><th>Name</th><th>Value</th></tr></thead>
                <tbody>{factorRows.map((row) => <tr key={`${row.group}-${row.name}`}><td>{row.group}</td><td>{row.name}</td><td>{formatValue(row.value)}</td></tr>)}</tbody>
              </table>
              {factorRows.length === 0 ? <p className="muted">No factor values available.</p> : null}
            </article>

            <article className="workspace-band">
              <div className="section-heading"><h2>Related News</h2><span className="muted">keyword match</span></div>
              {newsItems.map((item) => (
                <a className="evidence-link-row" key={item.news_id} href={item.url} target="_blank" rel="noreferrer">
                  <span>{item.published_at.slice(5, 16)}</span>
                  <strong>{item.title}</strong>
                </a>
              ))}
              {newsItems.length === 0 ? <p className="muted">No related public news found.</p> : null}
            </article>

            <article className="workspace-band">
              <div className="section-heading"><h2>Watchlist State</h2></div>
              {profile.signals.map((signal) => (
                <div className="signal-card" key={`${signal.watchlist_id}-${signal.trade_date}-${signal.primary_signal}`}>
                  <strong>{signal.primary_signal}</strong>
                  <span>Priority {signal.priority}</span>
                  <span>{signal.signal_tags.join(', ') || '-'}</span>
                  <span>{signal.risk_tags.join(', ') || '-'}</span>
                </div>
              ))}
              {profile.signals.length === 0 ? <p className="muted">No watchlist signal on this date.</p> : null}
            </article>

            <article className="workspace-band">
              <div className="section-heading"><h2>Strategy / Review History</h2></div>
              {profile.decisions.map((decision) => (
                <div className="evidence-row" key={decision.event_id}>
                  <strong>{decision.review_date} / {decision.decision_label}</strong>
                  <span>{decision.source_context}</span>
                  <span>{decision.evidence_path}</span>
                </div>
              ))}
              {profile.decisions.length === 0 ? <p className="muted">No decision evidence for this window.</p> : null}
            </article>

            <article className="workspace-band">
              <div className="section-heading"><h2>Research Reports</h2><span className="status-chip neutral">Phase 3</span></div>
              <p className="muted">External broker and institution reports will use a separate adapter and API shape.</p>
            </article>

            <article className="workspace-band">
              <div className="section-heading"><h2>Asset Search Matches</h2></div>
              {assetMatches.map((asset) => <span className="status-chip" key={asset.asset_id}>{asset.asset_id} {asset.name}</span>)}
              {assetMatches.length === 0 ? <p className="muted">No alternate matches.</p> : null}
            </article>
          </section>
        </>
      ) : null}
    </section>
  );
}
```

- [ ] **Step 4: Add focused Stock Workspace styles**

Append to `dashboard/src/styles.css`:

```css
.compact-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: end;
}

.compact-toolbar label {
  min-width: 138px;
}

.stock-summary-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 8px;
}

.stock-summary-strip > div {
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 10px;
  background: var(--panel-bg);
}

.stock-summary-strip span,
.signal-card span,
.evidence-row span,
.evidence-link-row span {
  display: block;
  color: var(--muted-text);
  font-size: 12px;
}

.stock-evidence-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 12px;
}

.compact-table th,
.compact-table td {
  padding: 6px 8px;
}

.signal-card,
.evidence-row,
.evidence-link-row {
  display: grid;
  gap: 3px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border-color);
}

.evidence-link-row {
  color: inherit;
  text-decoration: none;
}
```

- [ ] **Step 5: Run tests and commit**

Run:

```bash
npm --prefix dashboard test -- stock-workspace.test.tsx
```

Expected: tests pass.

Commit:

```bash
git add dashboard/src/components/StockWorkspace.tsx dashboard/src/styles.css dashboard/tests/stock-workspace.test.tsx
git commit -m "feat: build stock workspace"
```

## Task 3: Wire AppShell Asset Navigation

**Files:**
- Modify: `dashboard/src/components/AppShell.tsx`
- Modify: `dashboard/tests/platform-full-flow.spec.ts` only if needed

- [ ] **Step 1: Update AppShell state and props**

Modify `dashboard/src/components/AppShell.tsx`:

```tsx
export function AppShell() {
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>('home');
  const [selectedAssetId, setSelectedAssetId] = useState('000001.SZ');

  function openStockWorkspace(assetId: string) {
    setSelectedAssetId(assetId);
    setWorkspaceMode('stock');
  }

  return (
    <main className="platform-shell">
      <aside className="platform-nav" aria-label="Workspace navigation">
        <div className="panel-title">Stock Research</div>
        {NAV_ITEMS.map((item) => (
          <button
            type="button"
            key={item.mode}
            aria-current={workspaceMode === item.mode ? 'page' : undefined}
            aria-label={`Open ${item.label} workspace`}
            className={workspaceMode === item.mode ? 'active' : ''}
            onClick={() => setWorkspaceMode(item.mode)}
          >
            {item.label}
          </button>
        ))}
      </aside>
      <section className="platform-workspace">
        {workspaceMode === 'home' ? <HomeCockpit onNavigate={(mode) => setWorkspaceMode(mode)} /> : null}
        {workspaceMode === 'market' ? <MarketMonitorWorkspace /> : null}
        {workspaceMode === 'researchReports' ? <ResearchReportsWorkspace /> : null}
        {workspaceMode === 'stock' ? <StockWorkspace initialAssetId={selectedAssetId} /> : null}
        {workspaceMode === 'watchlist' ? <WatchlistWorkspace onOpenAsset={openStockWorkspace} /> : null}
        {workspaceMode === 'strategyLab' ? <StrategyLabWorkspace /> : null}
        {workspaceMode === 'generatedReports' ? <GeneratedReportsWorkspace /> : null}
        {workspaceMode === 'data' ? <DataExplorerWorkspace /> : null}
        {workspaceMode === 'factors' ? <FactorLabWorkspace /> : null}
        {workspaceMode === 'news' ? <NewsWorkspace onOpenAsset={openStockWorkspace} /> : null}
      </section>
    </main>
  );
}
```

- [ ] **Step 2: Run compile/test subset**

Run:

```bash
npm --prefix dashboard test -- stock-workspace.test.tsx
```

Expected: TypeScript compile fails until Task 4 and Task 5 add props to `WatchlistWorkspace` and `NewsWorkspace`.

Do not commit this task until Tasks 4 and 5 compile.

## Task 4: Build the Watchlist Research Queue

**Files:**
- Replace: `dashboard/src/components/WatchlistWorkspace.tsx`
- Create: `dashboard/tests/watchlist-workspace.test.tsx`
- Modify: `dashboard/src/styles.css`

- [ ] **Step 1: Write failing watchlist tests**

Create `dashboard/tests/watchlist-workspace.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WatchlistWorkspace } from '../src/components/WatchlistWorkspace';
import * as api from '../src/api/client';

vi.mock('../src/api/client', () => ({
  fetchWatchlistSignals: vi.fn()
}));

const apiMocks = vi.mocked(api);

beforeEach(() => {
  apiMocks.fetchWatchlistSignals.mockResolvedValue([
    {
      watchlist_id: 'default',
      trade_date: '2026-06-08',
      asset_id: '000001.SZ',
      stock_code: '000001',
      stock_name: '平安银行',
      priority: 8,
      signal_score: 82.4,
      primary_signal: 'candidate',
      signal_tags: ['momentum'],
      risk_tags: ['earnings'],
      must_watch: true,
      reason_json: { next_action: 'review close above 10d high', reason: 'score breakout' }
    },
    {
      watchlist_id: 'default',
      trade_date: '2026-06-08',
      asset_id: '600000.SH',
      stock_code: '600000',
      stock_name: '浦发银行',
      priority: 3,
      signal_score: 44,
      primary_signal: 'observe',
      signal_tags: ['value'],
      risk_tags: [],
      must_watch: false,
      reason_json: { reason: 'low volatility' }
    }
  ]);
});

describe('WatchlistWorkspace', () => {
  it('renders the EOD research queue and opens a stock', async () => {
    const onOpenAsset = vi.fn();
    const user = userEvent.setup();
    render(<WatchlistWorkspace onOpenAsset={onOpenAsset} />);

    expect(await screen.findByText('平安银行')).toBeInTheDocument();
    expect(screen.getByText('review close above 10d high')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Open 000001.SZ' }));
    expect(onOpenAsset).toHaveBeenCalledWith('000001.SZ');
  });

  it('filters by status and priority', async () => {
    const user = userEvent.setup();
    render(<WatchlistWorkspace onOpenAsset={vi.fn()} />);

    await screen.findByText('平安银行');
    await user.selectOptions(screen.getByLabelText('watchlist status'), 'candidate');
    await user.clear(screen.getByLabelText('minimum priority'));
    await user.type(screen.getByLabelText('minimum priority'), '5');

    await waitFor(() => {
      expect(screen.getByText('平安银行')).toBeInTheDocument();
      expect(screen.queryByText('浦发银行')).not.toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```bash
npm --prefix dashboard test -- watchlist-workspace.test.tsx
```

Expected: fails because current Watchlist Workspace is a static panel.

- [ ] **Step 3: Replace Watchlist Workspace implementation**

Replace `dashboard/src/components/WatchlistWorkspace.tsx` with:

```tsx
import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchWatchlistSignals } from '../api/client';
import type { WatchlistSignalRow } from '../api/types';

const DEFAULT_TRADE_DATE = '2026-06-08';
const DEFAULT_WATCHLIST_ID = 'default';

type WatchlistWorkspaceProps = {
  onOpenAsset?: (assetId: string) => void;
};

function formatReason(reason: Record<string, unknown>, key: string) {
  const value = reason[key];
  return typeof value === 'string' && value.length > 0 ? value : '-';
}

function matchesText(row: WatchlistSignalRow, query: string) {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return [row.asset_id, row.stock_code, row.stock_name, row.primary_signal, ...row.signal_tags, ...row.risk_tags]
    .join(' ')
    .toLowerCase()
    .includes(needle);
}

export function WatchlistWorkspace({ onOpenAsset }: WatchlistWorkspaceProps) {
  const [tradeDate, setTradeDate] = useState(DEFAULT_TRADE_DATE);
  const [watchlistId, setWatchlistId] = useState(DEFAULT_WATCHLIST_ID);
  const [rows, setRows] = useState<WatchlistSignalRow[]>([]);
  const [status, setStatus] = useState('all');
  const [minPriority, setMinPriority] = useState('0');
  const [query, setQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(false);
  const requestIdRef = useRef(0);

  function loadRows(nextWatchlistId = watchlistId, nextTradeDate = tradeDate) {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setIsLoading(true);
    setError(null);
    fetchWatchlistSignals(nextWatchlistId, nextTradeDate)
      .then((items) => {
        if (!mountedRef.current || requestIdRef.current !== requestId) return;
        setRows(items);
        setIsLoading(false);
      })
      .catch((err: unknown) => {
        if (!mountedRef.current || requestIdRef.current !== requestId) return;
        setError(err instanceof Error ? err.message : String(err));
        setIsLoading(false);
      });
  }

  useEffect(() => {
    mountedRef.current = true;
    loadRows(DEFAULT_WATCHLIST_ID, DEFAULT_TRADE_DATE);
    return () => {
      mountedRef.current = false;
      requestIdRef.current += 1;
    };
  }, []);

  const visibleRows = useMemo(() => {
    const min = Number(minPriority || 0);
    return rows.filter((row) => {
      const statusMatch = status === 'all' || row.primary_signal === status;
      const priorityMatch = row.priority >= min;
      return statusMatch && priorityMatch && matchesText(row, query);
    });
  }, [minPriority, query, rows, status]);

  return (
    <section className="watchlist-workspace" aria-label="Watchlist workspace">
      <header className="workspace-header">
        <h1>Watchlist</h1>
        <p className="muted">EOD research queue for status, priority, signal, risk, and next action.</p>
      </header>

      <section className="workspace-band">
        <div className="queue-filters">
          <label>
            Watchlist
            <input aria-label="watchlist id" value={watchlistId} onChange={(event) => setWatchlistId(event.target.value)} />
          </label>
          <label>
            Trade Date
            <input aria-label="watchlist trade date" type="date" value={tradeDate} onChange={(event) => setTradeDate(event.target.value)} />
          </label>
          <label>
            Status
            <select aria-label="watchlist status" value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="all">All</option>
              <option value="candidate">Candidate</option>
              <option value="observe">Observe</option>
              <option value="holding">Holding</option>
              <option value="avoid">Avoid</option>
              <option value="review">Review</option>
            </select>
          </label>
          <label>
            Min Priority
            <input aria-label="minimum priority" type="number" min="0" max="10" value={minPriority} onChange={(event) => setMinPriority(event.target.value)} />
          </label>
          <label>
            Signal / Risk
            <input aria-label="watchlist query" value={query} onChange={(event) => setQuery(event.target.value)} />
          </label>
          <button type="button" onClick={() => loadRows()}>Load EOD Queue</button>
        </div>
        {isLoading ? <p className="muted">Loading watchlist...</p> : null}
        {error ? <p className="error-text">{error}</p> : null}
      </section>

      <section className="workspace-band">
        <div className="section-heading">
          <h2>Research Queue</h2>
          <span className="muted">{visibleRows.length} of {rows.length} rows</span>
        </div>
        <table className="data-table queue-table">
          <thead>
            <tr>
              <th>Stock</th>
              <th>Status</th>
              <th>Priority</th>
              <th>Signal</th>
              <th>Risk</th>
              <th>Reason</th>
              <th>Next Action</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row) => (
              <tr key={`${row.asset_id}-${row.trade_date}-${row.primary_signal}`}>
                <td><strong>{row.stock_name}</strong><span>{row.asset_id}</span></td>
                <td>{row.primary_signal}</td>
                <td>{row.priority}</td>
                <td>{row.signal_tags.join(', ') || '-'}</td>
                <td>{row.risk_tags.join(', ') || '-'}</td>
                <td>{formatReason(row.reason_json, 'reason')}</td>
                <td>{formatReason(row.reason_json, 'next_action')}</td>
                <td><button type="button" onClick={() => onOpenAsset?.(row.asset_id)} aria-label={`Open ${row.asset_id}`}>Open Stock</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        {visibleRows.length === 0 ? <p className="muted">No watchlist rows match current filters.</p> : null}
      </section>
    </section>
  );
}
```

- [ ] **Step 4: Add watchlist styles**

Append to `dashboard/src/styles.css`:

```css
.queue-filters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
  align-items: end;
}

.queue-table td:first-child span {
  display: block;
  color: var(--muted-text);
  font-size: 12px;
}

.queue-table button {
  white-space: nowrap;
}
```

- [ ] **Step 5: Run tests**

Run:

```bash
npm --prefix dashboard test -- watchlist-workspace.test.tsx
```

Expected: tests pass.

Do not commit until Task 5 compiles with AppShell.

## Task 5: Add News-to-Stock Navigation

**Files:**
- Modify: `dashboard/src/components/NewsWorkspace.tsx`
- Modify: `dashboard/tests/news-workspace.test.tsx`

- [ ] **Step 1: Add failing tests for news asset extraction**

In `dashboard/tests/news-workspace.test.tsx`, add:

```tsx
import { getNewsAssetCandidate } from '../src/components/NewsWorkspace';
```

Add tests:

```tsx
it('extracts a stock candidate from news text', () => {
  expect(
    getNewsAssetCandidate({
      news_id: 'n1',
      source: 'sina_finance',
      source_channel: 'company',
      category: 'company',
      title: '600000 浦发银行公告',
      summary: '',
      url: '',
      published_at: '2026-06-08T09:30:00',
      collected_at: '2026-06-08T09:31:00',
      raw_id: 'n1',
      raw_payload: {},
      status: 'active'
    })
  ).toBe('600000.SH');
});

it('opens Stock Workspace from a news row with a stock code', async () => {
  const onOpenAsset = vi.fn();
  render(<NewsWorkspace onOpenAsset={onOpenAsset} />);

  await screen.findByText(/600000 浦发银行公告/);
  await userEvent.click(screen.getByRole('button', { name: 'Open 600000.SH' }));

  expect(onOpenAsset).toHaveBeenCalledWith('600000.SH');
});
```

Update the mocked news item in that test file so at least one title contains `600000`.

- [ ] **Step 2: Run test and confirm failure**

Run:

```bash
npm --prefix dashboard test -- news-workspace.test.tsx
```

Expected: fails because `NewsWorkspace` has no props and no exported candidate extractor.

- [ ] **Step 3: Update NewsWorkspace implementation**

Change the function signature and add helper exports in `dashboard/src/components/NewsWorkspace.tsx`:

```tsx
type NewsWorkspaceProps = {
  onOpenAsset?: (assetId: string) => void;
};

function normalizeAssetId(value: string) {
  const trimmed = value.trim();
  if (/^\d{6}$/.test(trimmed)) return `${trimmed}.${trimmed.startsWith('6') ? 'SH' : 'SZ'}`;
  return trimmed.toUpperCase();
}

export function getNewsAssetCandidate(item: PublicNewsItem) {
  const rawCandidates = [
    item.raw_payload.asset_id,
    item.raw_payload.stock_code,
    item.raw_payload.symbol,
    item.raw_payload.code,
    item.title,
    item.summary,
    item.url
  ];
  for (const candidate of rawCandidates) {
    if (typeof candidate !== 'string') continue;
    const fullMatch = candidate.match(/\b\d{6}\.(SH|SZ)\b/i);
    if (fullMatch) return fullMatch[0].toUpperCase();
    const sixDigitMatch = candidate.match(/\b\d{6}\b/);
    if (sixDigitMatch) return normalizeAssetId(sixDigitMatch[0]);
  }
  return null;
}

export function NewsWorkspace({ onOpenAsset }: NewsWorkspaceProps) {
```

Inside `visibleItems.map`, calculate the candidate and render the button:

```tsx
{visibleItems.map((item) => {
  const assetCandidate = getNewsAssetCandidate(item);
  return (
    <article key={item.news_id} className="news-feed-row">
      <div className="news-feed-meta">
        <span>{item.published_at.slice(5, 16)}</span>
        <span>{labelForCategory(item.category)}</span>
        <span>{item.source_channel}</span>
        {assetCandidate ? (
          <button type="button" onClick={() => onOpenAsset?.(assetCandidate)} aria-label={`Open ${assetCandidate}`}>
            Open Stock
          </button>
        ) : null}
      </div>
      {item.url ? (
        <a href={item.url} target="_blank" rel="noreferrer">
          {item.title}
        </a>
      ) : (
        <strong>{item.title}</strong>
      )}
      {item.summary ? <p>{item.summary}</p> : null}
    </article>
  );
})}
```

- [ ] **Step 4: Run tests and commit AppShell, Watchlist, News together**

Run:

```bash
npm --prefix dashboard test -- news-workspace.test.tsx watchlist-workspace.test.tsx stock-workspace.test.tsx
```

Expected: tests pass and AppShell TypeScript props compile.

Commit:

```bash
git add dashboard/src/components/AppShell.tsx dashboard/src/components/NewsWorkspace.tsx dashboard/src/components/WatchlistWorkspace.tsx dashboard/src/styles.css dashboard/tests/news-workspace.test.tsx dashboard/tests/watchlist-workspace.test.tsx
git commit -m "feat: connect stock workspace navigation"
```

## Task 6: Run Integrated Verification and Adjust Smoke Tests

**Files:**
- Modify: `dashboard/tests/platform-full-flow.spec.ts` only if its assertions still refer to old planned-panel text.

- [ ] **Step 1: Run frontend unit tests for touched workspaces**

Run:

```bash
npm --prefix dashboard test -- platform-client.test.ts stock-workspace.test.tsx watchlist-workspace.test.tsx news-workspace.test.tsx data-explorer-workspace.test.tsx home-cockpit.test.tsx
```

Expected: all listed tests pass.

- [ ] **Step 2: Run backend asset profile tests**

Run:

```bash
pytest tests/test_dashboard_asset_profile.py -q
```

Expected: tests pass. This verifies the existing backend profile contract used by Stock Workspace.

- [ ] **Step 3: Run dashboard build**

Run:

```bash
npm --prefix dashboard run build
```

Expected: build passes without TypeScript errors.

- [ ] **Step 4: Update full-flow smoke assertions if needed**

If `dashboard/tests/platform-full-flow.spec.ts` fails because it expects the old Stock Workspace or Watchlist planned-panel copy, replace those expectations with stable labels:

```ts
await page.getByRole('button', { name: 'Open Stock Workspace workspace' }).click();
await expect(page.getByRole('heading', { name: /平安银行|Stock Workspace/ })).toBeVisible();

await page.getByRole('button', { name: 'Open Watchlist workspace' }).click();
await expect(page.getByRole('heading', { name: 'Watchlist' })).toBeVisible();
await expect(page.getByText('EOD research queue')).toBeVisible();
```

Run the smoke test command already documented in that file or:

```bash
npm --prefix dashboard test:e2e -- platform-full-flow.spec.ts
```

Expected: smoke test passes against mocked routes.

- [ ] **Step 5: Commit verification-only test updates**

If Step 4 modified the smoke test:

```bash
git add dashboard/tests/platform-full-flow.spec.ts
git commit -m "test: update phase 2 dashboard smoke coverage"
```

If Step 4 did not modify files, no commit is needed.

## Task 7: Manual Localhost Check

**Files:**
- No source edits expected.

- [ ] **Step 1: Start or reuse localhost dashboard**

Run:

```bash
npm --prefix dashboard run dev -- --host 127.0.0.1
```

Expected: Vite reports a local URL such as `http://127.0.0.1:5173/`. If the port is busy, use the next offered port.

- [ ] **Step 2: Check Stock Workspace**

Open the Vite URL and click `Stock Workspace`.

Expected visible results:

- Header shows `平安银行` or the loaded asset ID.
- Summary strip shows asset, score, rank, latest close, and signal count.
- Price chart is visible when mocked/local bars exist.
- Related News panel either shows keyword-matched public news or a clear empty state.
- Research Reports panel says Phase 3.

- [ ] **Step 3: Check Watchlist**

Click `Watchlist`.

Expected visible results:

- `EOD research queue` copy appears.
- Queue filters are visible.
- Rows appear if `/api/watchlists/default?trade_date=2026-06-08` has data.
- `Open Stock` on a row navigates to Stock Workspace and loads that asset.

- [ ] **Step 4: Check News to Stock**

Click `News`.

Expected visible results:

- News feed still loads and refreshes.
- Rows containing a 6-digit stock code show `Open Stock`.
- `Open Stock` navigates to Stock Workspace with the normalized asset ID.

- [ ] **Step 5: Stop dev server and summarize**

Stop the Vite process with `Ctrl-C`.

No commit is needed unless manual checking discovers a defect and a source fix is made.

## Self-Review

Spec coverage:

- Section 9 Stock Workspace is covered by Task 2 and Task 3. It includes stock search/input, identity, chart, volume-capable bars, score components, public news, watchlist state, strategy/review history, and generated evidence paths. External research reports are represented honestly as a Phase 3 panel because the separate adapter is outside this phase.
- Section 10 Watchlist is covered by Task 4. It includes status, priority, reason, latest signal fields, risk tags, next action, and filters for status, priority, signal/risk text, and date.
- Section 7 News future link into Stock Workspace is covered by Task 5 using deterministic code extraction. Full entity extraction is intentionally not included.
- Section 6 Market Monitor realtime concerns are unaffected. Phase 2 remains EOD and does not add high-frequency data fetching.
- Section 8 Research Reports is not implemented in this plan because the approved design assigns it a separate adapter/store/API phase.

Placeholder scan:

- The plan has no unspecified tasks. Each code-changing task lists exact files, test commands, expected outcomes, and concrete code.

Type consistency:

- `WatchlistResponse` wraps existing `WatchlistSignalRow[]`.
- `searchAssets()` returns existing `AssetSummary[]`.
- `StockWorkspace`, `WatchlistWorkspace`, and `NewsWorkspace` props match `AppShell` usage.
- The news asset candidate helper returns normalized `000001.SZ`/`600000.SH` strings compatible with `fetchAssetProfile`.
