import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppShell } from '../src/components/AppShell';

vi.mock('../src/api/client', () => ({
  fetchPlatformReadiness: vi.fn().mockResolvedValue({ display_trade_date: '2026-07-02' }),
  fetchPlatformSummary: vi.fn().mockResolvedValue({ latest_market_date: '2026-07-02' })
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
vi.mock('../src/components/DailyReviewLiteWorkspace', () => ({ DailyReviewLiteWorkspace: () => <div>Daily Review Lite</div> }));
vi.mock('../src/components/GeneratedReportsWorkspace', () => ({ GeneratedReportsWorkspace: () => <div>Generated Reports</div> }));
vi.mock('../src/components/GlobalSearchBox', () => ({ GlobalSearchBox: () => <div>Search</div> }));
vi.mock('../src/components/HomeCockpit', () => ({ HomeCockpit: () => <div>Home</div> }));
vi.mock('../src/components/MarketMonitorWorkspace', () => ({ MarketMonitorWorkspace: () => <div>Market</div> }));
vi.mock('../src/components/NewsWorkspace', () => ({ NewsWorkspace: () => <div>News</div> }));
vi.mock('../src/components/ResearchReportsWorkspace', () => ({ ResearchReportsWorkspace: () => <div>Reports</div> }));
vi.mock('../src/components/ReviewQueueWorkspace', () => ({ ReviewQueueWorkspace: () => <div>Review Queue</div> }));
vi.mock('../src/components/StockWorkspace', () => ({ StockWorkspace: () => <div>Stock Workspace</div> }));
vi.mock('../src/components/StrategyLabWorkspace', () => ({ StrategyLabWorkspace: () => <div>Strategy Lab</div> }));
vi.mock('../src/components/WatchlistWorkspace', () => ({ WatchlistWorkspace: () => <div>Watchlist</div> }));

describe('Tech Bottleneck legacy watchlist route migration', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/tech-bottleneck/watchlist-review');
  });

  afterEach(() => {
    cleanup();
  });

  it('serves the 378-stock review universe instead of the deprecated hard-tech core 90 view', () => {
    render(<AppShell />);

    expect(screen.getByRole('heading', { name: '科技卡脖子复盘' })).toBeInTheDocument();
    expect(screen.getByText('复盘全集 378')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/research/tech-bottleneck/review-universe');
    expect(screen.queryByText('Hard-Tech Review Pool 90')).not.toBeInTheDocument();
    expect(screen.queryByText('技术瓶颈候选复盘队列')).not.toBeInTheDocument();
  });
});
