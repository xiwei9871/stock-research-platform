import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppShell } from '../src/components/AppShell';

vi.mock('../src/api/client', () => ({
  fetchPlatformReadiness: vi.fn().mockResolvedValue({ display_trade_date: '2026-07-10' }),
  fetchPlatformSummary: vi.fn().mockResolvedValue({ latest_market_date: '2026-07-10' })
}));

vi.mock('../src/api/techBottleneckReview', () => ({
  fetchTechBottleneckReviewUniverseStock: vi.fn().mockRejectedValue(new Error('not needed'))
}));

vi.mock('../src/components/ThemeResearchWorkspace', () => ({
  ThemeResearchWorkspace: ({ pathname, onNavigate, onOpenStock }: {
    pathname: string;
    onNavigate: (path: string) => void;
    onOpenStock: (path: string) => void;
  }) => (
    <section>
      <h1>Theme Research Mock</h1>
      <span>{pathname}</span>
      <button type="button" onClick={() => onNavigate('/theme-research/ai_power_value_capture_v1/nodes')}>Open nodes route</button>
      <button type="button" onClick={() => onOpenStock('/tech-bottleneck/stock/002837.SZ?source=theme_research')}>Open mapped stock</button>
    </section>
  )
}));

vi.mock('../src/components/IndustryCatalogWorkspace', () => ({
  IndustryCatalogWorkspace: ({ pathname, onNavigate }: {
    pathname: string;
    onNavigate: (path: string) => void;
  }) => (
    <section>
      <h1>Industry Catalog Mock</h1>
      <span>{pathname}</span>
      <button type="button" onClick={() => onNavigate('/theme-research/catalog/grid%20storage')}>Open catalog detail</button>
    </section>
  )
}));

vi.mock('../src/pages/TechBottleneckReviewPage', () => ({ TechBottleneckReviewPage: () => <div>Tech Bottleneck</div> }));
vi.mock('../src/components/FactorLabWorkspace', () => ({ FactorLabWorkspace: () => <div>Factor Lab</div> }));
vi.mock('../src/components/DailyReviewLiteWorkspace', () => ({ DailyReviewLiteWorkspace: () => <div>Daily Review</div> }));
vi.mock('../src/components/DataToBriefDocling90ReviewWorkspace', () => ({ DataToBriefDocling90ReviewWorkspace: () => <div>Docling</div> }));
vi.mock('../src/components/GeneratedReportsWorkspace', () => ({ GeneratedReportsWorkspace: () => <div>Generated Reports</div> }));
vi.mock('../src/components/GlobalSearchBox', () => ({ GlobalSearchBox: () => <div>Search</div> }));
vi.mock('../src/components/HomeCockpit', () => ({ HomeCockpit: () => <div>Home</div> }));
vi.mock('../src/components/MarketMonitorWorkspace', () => ({ MarketMonitorWorkspace: () => <div>Market</div> }));
vi.mock('../src/components/NewsWorkspace', () => ({ NewsWorkspace: () => <div>News</div> }));
vi.mock('../src/components/ResearchReportsWorkspace', () => ({ ResearchReportsWorkspace: () => <div>Reports</div> }));
vi.mock('../src/components/ReviewQueueWorkspace', () => ({ ReviewQueueWorkspace: () => <div>Review Queue</div> }));
vi.mock('../src/components/StrategyLabWorkspace', () => ({ StrategyLabWorkspace: () => <div>Strategy Lab</div> }));
vi.mock('../src/components/WatchlistWorkspace', () => ({ WatchlistWorkspace: () => <div>Watchlist</div> }));
vi.mock('../src/components/UserManagementView', () => ({ UserManagementView: () => <div>Users</div> }));
vi.mock('../src/components/StockWorkspace', () => ({
  StockWorkspace: ({ initialAssetId, entryContext }: { initialAssetId?: string; entryContext?: Record<string, unknown> }) => (
    <section>
      <h1>Stock Workspace Mock</h1>
      <span>{initialAssetId}</span>
      <span>{String(entryContext?.techBottleneckSource ?? '')}</span>
    </section>
  )
}));

describe('Theme research AppShell routing', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/');
  });

  afterEach(() => {
    cleanup();
  });

  it('opens the combined workspace from the renamed primary navigation item', () => {
    render(<AppShell />);

    const navigationButton = screen.getByRole('button', { name: 'Open Theme Research and Industry Catalog workspace' });
    expect(navigationButton).toHaveTextContent('主题研究与产业目录');
    fireEvent.click(navigationButton);

    expect(screen.getByRole('heading', { name: 'Theme Research Mock' })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/theme-research');
  });

  it('restores the catalog index directly and switches top-level views by browser path', () => {
    window.history.replaceState({}, '', '/theme-research/catalog');
    render(<AppShell />);

    expect(screen.getByRole('button', { name: '产业目录' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('button', { name: '主题研究' })).not.toHaveAttribute('aria-current');
    expect(screen.getByRole('heading', { name: 'Industry Catalog Mock' })).toBeInTheDocument();
    expect(screen.getByText('/theme-research/catalog')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '主题研究' }));

    expect(window.location.pathname).toBe('/theme-research');
    expect(screen.getByRole('heading', { name: 'Theme Research Mock' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '主题研究' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('button', { name: '产业目录' })).not.toHaveAttribute('aria-current');

    fireEvent.click(screen.getByRole('button', { name: '产业目录' }));

    expect(window.location.pathname).toBe('/theme-research/catalog');
    expect(screen.getByRole('heading', { name: 'Industry Catalog Mock' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '产业目录' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('button', { name: '主题研究' })).not.toHaveAttribute('aria-current');
  });

  it('restores and updates catalog detail routes without handing catalog to theme research', () => {
    window.history.replaceState({}, '', '/theme-research/catalog/ai_data_center_power');
    render(<AppShell />);

    expect(screen.getByRole('heading', { name: 'Industry Catalog Mock' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Theme Research Mock' })).not.toBeInTheDocument();
    expect(screen.getByText('/theme-research/catalog/ai_data_center_power')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Open catalog detail' }));

    expect(window.location.pathname).toBe('/theme-research/catalog/grid%20storage');
    expect(screen.getByText('/theme-research/catalog/grid%20storage')).toBeInTheDocument();
  });

  it('restores a direct child route and updates route-backed tabs', () => {
    window.history.replaceState({}, '', '/theme-research/ai_power_value_capture_v1/companies');
    render(<AppShell />);

    expect(screen.getByText('/theme-research/ai_power_value_capture_v1/companies')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Open nodes route' }));

    expect(window.location.pathname).toBe('/theme-research/ai_power_value_capture_v1/nodes');
    expect(screen.getByText('/theme-research/ai_power_value_capture_v1/nodes')).toBeInTheDocument();
  });

  it('restores generic direct theme routes without route-specific registration', () => {
    window.history.replaceState({}, '', '/theme-research/ai_logic_compute_chips_value_chain_v1');
    render(<AppShell />);

    expect(screen.getByRole('heading', { name: 'Theme Research Mock' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Industry Catalog Mock' })).not.toBeInTheDocument();
    expect(screen.getByText('/theme-research/ai_logic_compute_chips_value_chain_v1')).toBeInTheDocument();
  });

  it('hands a mapped company to the existing tech-bottleneck stock route', () => {
    window.history.replaceState({}, '', '/theme-research/ai_power_value_capture_v1/companies');
    render(<AppShell />);

    fireEvent.click(screen.getByRole('button', { name: 'Open mapped stock' }));

    expect(window.location.pathname).toBe('/tech-bottleneck/stock/002837.SZ');
    expect(window.location.search).toBe('?source=theme_research');
    expect(screen.getByRole('heading', { name: 'Stock Workspace Mock' })).toBeInTheDocument();
    expect(screen.getByText('002837.SZ')).toBeInTheDocument();
    expect(screen.getByText('theme_research')).toBeInTheDocument();
  });

  it('returns to the theme index when primary navigation is clicked from a child route', () => {
    window.history.replaceState({}, '', '/theme-research/ai_power_value_capture_v1/sources');
    render(<AppShell />);

    fireEvent.click(screen.getByRole('button', { name: 'Open Theme Research and Industry Catalog workspace' }));

    expect(window.location.pathname).toBe('/theme-research');
    expect(screen.getByText('/theme-research')).toBeInTheDocument();
  });

  it('restores theme child routes on browser popstate', () => {
    window.history.replaceState({}, '', '/theme-research/ai_power_value_capture_v1/nodes');
    render(<AppShell />);

    window.history.pushState({}, '', '/theme-research/ai_power_value_capture_v1/sources');
    fireEvent(window, new PopStateEvent('popstate'));

    expect(screen.getByText('/theme-research/ai_power_value_capture_v1/sources')).toBeInTheDocument();
  });
});
