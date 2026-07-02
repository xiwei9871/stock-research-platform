import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppShell } from '../src/components/AppShell';

vi.mock('../src/api/client', () => ({
  fetchPlatformReadiness: vi.fn().mockResolvedValue({ display_trade_date: '2026-07-02' }),
  fetchPlatformSummary: vi.fn().mockResolvedValue({ latest_market_date: '2026-07-02' })
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
vi.mock('../src/components/StockWorkspace', () => ({ StockWorkspace: () => <div>Stock Workspace</div> }));
vi.mock('../src/components/StrategyLabWorkspace', () => ({ StrategyLabWorkspace: () => <div>Strategy Lab</div> }));
vi.mock('../src/components/WatchlistWorkspace', () => ({ WatchlistWorkspace: () => <div>Watchlist</div> }));

describe('Tech Bottleneck read-only route integration', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/');
  });

  afterEach(() => {
    cleanup();
  });

  it('opens the read-only review workspace from navigation and updates the path', () => {
    render(<AppShell />);

    fireEvent.click(screen.getByRole('button', { name: 'Open Tech Bottleneck Watchlist Review workspace' }));

    expect(screen.getByRole('heading', { name: 'Read-only research review' })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/tech-bottleneck/watchlist-review');
  });

  it('renders the read-only review workspace when loaded at the route path', () => {
    window.history.pushState({}, '', '/tech-bottleneck/watchlist-review');

    render(<AppShell />);

    expect(screen.getByRole('heading', { name: 'Read-only research review' })).toBeInTheDocument();
    expect(screen.getByText('Writeback allowed')).toBeInTheDocument();
    expect(screen.getAllByText('Baseline admission remains unchanged.').length).toBeGreaterThan(0);
  });

  it('renders enhanced read-only review tables and template status', () => {
    window.history.pushState({}, '', '/tech-bottleneck/watchlist-review');

    render(<AppShell />);

    const watchlistTable = within(screen.getByRole('region', { name: 'Watchlist Table' }));
    expect(watchlistTable.getByRole('heading', { name: 'Watchlist Table' })).toBeInTheDocument();
    expect(watchlistTable.getByRole('columnheader', { name: 'Symbol' })).toBeInTheDocument();
    expect(watchlistTable.getByRole('cell', { name: '600098' })).toBeInTheDocument();
    expect(watchlistTable.getAllByText('priority_data_gap_review').length).toBeGreaterThan(0);

    const riskQueue = within(screen.getByRole('region', { name: 'Risk Review Queue' }));
    expect(riskQueue.getByRole('heading', { name: 'Risk Review Queue' })).toBeInTheDocument();
    expect(riskQueue.getAllByText('auto_exclude = false').length).toBeGreaterThan(0);

    const templateStatus = within(screen.getByRole('region', { name: 'Manual Review Template Status' }));
    expect(templateStatus.getByRole('heading', { name: 'Manual Review Template Status' })).toBeInTheDocument();
    expect(templateStatus.getByText('manual_review_conclusion = not_reviewed')).toBeInTheDocument();
    expect(templateStatus.getByText('writeback disabled')).toBeInTheDocument();

    const reportLinks = within(screen.getByRole('region', { name: 'Consolidated Report Links' }));
    expect(reportLinks.getByRole('heading', { name: 'Consolidated Report Links' })).toBeInTheDocument();
    expect(reportLinks.getByText(/CN_SH_600098_/)).toBeInTheDocument();
  });

  it('renders financial statement context as read-only research support', () => {
    window.history.pushState({}, '', '/tech-bottleneck/watchlist-review');

    render(<AppShell />);

    const financialStatement = within(screen.getByRole('region', { name: 'Full Financial Statement Review Context' }));
    expect(financialStatement.getByRole('heading', { name: 'Full Financial Statement Review Context' })).toBeInTheDocument();
    expect(financialStatement.getByText('Financial Statement Support: 63 / 102')).toBeInTheDocument();
    expect(financialStatement.getByText('Missing Financial Statement: 39')).toBeInTheDocument();
    expect(
      financialStatement.getAllByText('Financial statement data unavailable before first admission date').length
    ).toBeGreaterThan(0);
    expect(financialStatement.getAllByText('writeback_enabled = false').length).toBeGreaterThan(0);
  });
});
