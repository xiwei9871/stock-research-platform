import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppShell } from '../src/components/AppShell';

vi.mock('../src/api/client', () => ({
  fetchPlatformReadiness: vi.fn().mockResolvedValue({ display_trade_date: '2026-07-02' }),
  fetchPlatformSummary: vi.fn().mockResolvedValue({ latest_market_date: '2026-07-02' })
}));

const routeTestState = vi.hoisted(() => ({
  stockWorkspaceRenders: [] as Array<{ initialAssetId?: string; entryContext?: Record<string, unknown> }>
}));

vi.mock('../src/pages/TechBottleneckReviewPage', () => ({
  TechBottleneckReviewPage: () => (
    <section>
      <h1>科技卡脖子复盘</h1>
      <p>复盘全集 378</p>
    </section>
  )
}));
vi.mock('../src/components/FactorLabWorkspace', () => ({ FactorLabWorkspace: () => <div>Factor Lab</div> }));
vi.mock('../src/components/DailyReviewLiteWorkspace', () => ({
  DailyReviewLiteWorkspace: () => <div>Daily Review Lite</div>
}));
vi.mock('../src/components/GeneratedReportsWorkspace', () => ({ GeneratedReportsWorkspace: () => <div>Generated Reports</div> }));
vi.mock('../src/components/GlobalSearchBox', () => ({ GlobalSearchBox: () => <div>Search</div> }));
vi.mock('../src/components/HomeCockpit', () => ({ HomeCockpit: () => <div>Home</div> }));
vi.mock('../src/components/MarketMonitorWorkspace', () => ({ MarketMonitorWorkspace: () => <div>Market</div> }));
vi.mock('../src/components/NewsWorkspace', () => ({ NewsWorkspace: () => <div>News</div> }));
vi.mock('../src/components/ResearchReportsWorkspace', () => ({ ResearchReportsWorkspace: () => <div>Reports</div> }));
vi.mock('../src/components/ReviewQueueWorkspace', () => ({ ReviewQueueWorkspace: () => <div>Review Queue</div> }));
vi.mock('../src/components/StockWorkspace', () => ({
  StockWorkspace: (props: { initialAssetId?: string; entryContext?: Record<string, unknown> }) => {
    routeTestState.stockWorkspaceRenders.push(props);
    return (
      <div>
        <h1>Stock Workspace</h1>
        <span>{props.initialAssetId}</span>
        <span>{String(props.entryContext?.sourceWorkspace ?? 'none')}</span>
        <span>{String(props.entryContext?.techBottleneckSource ?? 'none')}</span>
      </div>
    );
  }
}));
vi.mock('../src/components/StrategyLabWorkspace', () => ({ StrategyLabWorkspace: () => <div>Strategy Lab</div> }));
vi.mock('../src/components/WatchlistWorkspace', () => ({ WatchlistWorkspace: () => <div>Watchlist</div> }));

const legacyRoutePath = '/tech-bottleneck/watchlist-review';
const reviewUniversePath = '/research/tech-bottleneck/review-universe';

describe('Tech Bottleneck review universe route integration', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/');
    routeTestState.stockWorkspaceRenders.length = 0;
  });

  afterEach(() => {
    cleanup();
  });

  it('opens the 378-stock review universe from navigation and updates the path', () => {
    render(<AppShell />);

    fireEvent.click(screen.getByRole('button', { name: 'Open Tech Bottleneck review universe workspace' }));

    expect(screen.getByRole('heading', { name: '科技卡脖子复盘' })).toBeInTheDocument();
    expect(screen.getByText('复盘全集 378')).toBeInTheDocument();
    expect(window.location.pathname).toBe(reviewUniversePath);
    expect(screen.queryByText('Hard-Tech Pool 90')).not.toBeInTheDocument();
  });

  it('routes the legacy watchlist-review URL to the 378-stock review universe, not the old 90-stock page', () => {
    window.history.pushState({}, '', legacyRoutePath);

    render(<AppShell />);

    expect(screen.getByRole('heading', { name: '科技卡脖子复盘' })).toBeInTheDocument();
    expect(screen.getByText('复盘全集 378')).toBeInTheDocument();
    expect(window.location.pathname).toBe(reviewUniversePath);
    expect(screen.queryByText('Hard-Tech Pool 90')).not.toBeInTheDocument();
  });

  it('opens direct tech bottleneck stock URLs in the existing stock workspace', () => {
    window.history.pushState(
      {},
      '',
      '/tech-bottleneck/stock/002371?source=tech_bottleneck_seed_tier_a_requalification_v2_review_pool_refinement'
    );

    render(<AppShell />);

    expect(screen.getByRole('heading', { name: 'Stock Workspace' })).toBeInTheDocument();
    expect(screen.getByText('002371.SZ')).toBeInTheDocument();
    expect(screen.getByText('techBottleneck')).toBeInTheDocument();
    expect(routeTestState.stockWorkspaceRenders.at(-1)).toMatchObject({
      initialAssetId: '002371.SZ',
      entryContext: expect.objectContaining({
        assetId: '002371.SZ',
        sourceWorkspace: 'techBottleneck',
        query: '北方华创',
        stockName: '北方华创',
        techBottleneckSource: 'tech_bottleneck_seed_tier_a_requalification_v2_review_pool_refinement'
      })
    });
  });
});
