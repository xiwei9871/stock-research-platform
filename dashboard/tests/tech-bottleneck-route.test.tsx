import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppShell } from '../src/components/AppShell';

vi.mock('../src/api/client', () => ({
  fetchPlatformReadiness: vi.fn().mockResolvedValue({ display_trade_date: '2026-07-02' }),
  fetchPlatformSummary: vi.fn().mockResolvedValue({ latest_market_date: '2026-07-02' })
}));

const routeTestState = vi.hoisted(() => ({
  stockWorkspaceRenders: [] as Array<{ initialAssetId?: string; entryContext?: Record<string, unknown> }>
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

const routePath = '/tech-bottleneck/watchlist-review';

describe('Tech Bottleneck candidate universe route integration', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/');
    routeTestState.stockWorkspaceRenders.length = 0;
  });

  afterEach(() => {
    cleanup();
  });

  it('opens the candidate review workbench from navigation and updates the path', () => {
    render(<AppShell />);

    fireEvent.click(screen.getByRole('button', { name: 'Open Tech Bottleneck Watchlist Review workspace' }));

    expect(screen.getByRole('heading', { name: '技术瓶颈候选复盘队列' })).toBeInTheDocument();
    expect(screen.getByText(/Research-only/)).toBeInTheDocument();
    expect(window.location.pathname).toBe(routePath);
  });

  it('renders the compact review queue first screen at the route path', () => {
    window.history.pushState({}, '', routePath);

    render(<AppShell />);

    expect(screen.getByRole('heading', { name: '技术瓶颈候选复盘队列' })).toBeInTheDocument();
    const status = within(screen.getByRole('region', { name: '候选队列状态条' }));
    expect(status.getByText('Hard-Tech Pool 90')).toBeInTheDocument();
    expect(status.getByText('Verified Core 28')).toBeInTheDocument();
    expect(status.getByText('Manual Anchor Pending 2')).toBeInTheDocument();
    expect(status.getByText('Likely Pending Evidence 60')).toBeInTheDocument();
    expect(status.getByText('Adjacent Pending 9')).toBeInTheDocument();
    expect(status.getByText('Low Priority Backfill 3')).toBeInTheDocument();
    expect(status.getByText('Reject / Pollution 12')).toBeInTheDocument();
    expect(status.getByText('Legacy 114 deprecated')).toBeInTheDocument();
    expect(status.getByText('Signal disabled')).toBeInTheDocument();
    expect(status.getByText('Admission disabled')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Core candidate table' })).toHaveTextContent('京泉华');
    expect(screen.queryByText('Pipeline closure')).not.toBeInTheDocument();
  });

  it('renders the candidate queue tabs and core table columns', () => {
    window.history.pushState({}, '', routePath);

    render(<AppShell />);

    const tabs = within(screen.getByRole('region', { name: 'Candidate queue tabs' }));
    expect(tabs.getByRole('tab', { name: 'Hard-Tech Review Pool 90' })).toBeInTheDocument();
    expect(tabs.getByRole('tab', { name: 'Adjacent Watchlist 14' })).toBeInTheDocument();
    expect(tabs.getByRole('tab', { name: 'Evidence Backfill 11' })).toBeInTheDocument();
    expect(tabs.getByRole('tab', { name: 'Rejected / Downgrade 3' })).toBeInTheDocument();
    expect(tabs.getByRole('tab', { name: 'Guardrails' })).toBeInTheDocument();

    const tableRegion = within(screen.getByRole('region', { name: 'Core candidate table' }));
    for (const column of [
      'stock_code',
      'concept_tags',
      'evidence_category',
      'rationale'
    ]) {
      expect(tableRegion.getByRole('columnheader', { name: column })).toBeInTheDocument();
    }
    for (const column of [
      'stock_name',
      'industry',
      'research_priority_score',
      'evidence_strength',
      'bottleneck_relevance',
      'source_group',
      'previous_tier',
      'review_status'
    ]) {
      expect(tableRegion.getByRole('button', { name: `Sort by ${column}` })).toBeInTheDocument();
    }
  });

  it('opens tech bottleneck stock routes in the existing stock workspace with candidate context', () => {
    window.history.pushState({}, '', routePath);

    render(<AppShell />);

    fireEvent.change(screen.getByLabelText('来源'), { target: { value: 'verified_rescue_extension_proposal' } });
    fireEvent.click(screen.getByRole('button', { name: '打开 京泉华 个股复盘工作台' }));

    expect(window.location.pathname).toBe('/tech-bottleneck/stock/002885');
    expect(screen.getByRole('heading', { name: 'Stock Workspace' })).toBeInTheDocument();
    expect(screen.getByText('002885.SZ')).toBeInTheDocument();
    expect(screen.getByText('techBottleneck')).toBeInTheDocument();
    expect(screen.getByText('tech_bottleneck_candidate_universe_pipeline_closure_v2')).toBeInTheDocument();
    expect(routeTestState.stockWorkspaceRenders.at(-1)).toMatchObject({
      initialAssetId: '002885.SZ',
      entryContext: expect.objectContaining({
        assetId: '002885.SZ',
        sourceWorkspace: 'techBottleneck',
        query: '京泉华',
        stockName: '京泉华',
        techBottleneckSource: 'tech_bottleneck_candidate_universe_pipeline_closure_v2',
        allowedForSignal: false,
        allowedForAdmission: false
      })
    });
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

  it('keeps guardrails visible and production paths disabled', () => {
    window.history.pushState({}, '', routePath);

    render(<AppShell />);

    fireEvent.click(screen.getByRole('tab', { name: 'Guardrails' }));
    const guardrails = within(screen.getByRole('region', { name: 'Guardrails table' }));
    expect(guardrails.getByText('used_for_signal_count')).toBeInTheDocument();
    expect(guardrails.getByText('used_for_admission_count')).toBeInTheDocument();
    expect(guardrails.getByText('baseline_admission_changed_count')).toBeInTheDocument();
    expect(guardrails.getByText('production_candidate_universe_modified')).toBeInTheDocument();
    expect(guardrails.getByText('dashboard_workbench_integration_modified')).toBeInTheDocument();
  });
});
