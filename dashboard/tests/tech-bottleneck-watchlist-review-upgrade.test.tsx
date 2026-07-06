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
vi.mock('../src/components/StockWorkspace', () => ({
  StockWorkspace: (props: { initialAssetId?: string; entryContext?: Record<string, unknown> }) => (
    <div>
      <h1>Stock Workspace</h1>
      <span>{props.initialAssetId}</span>
      <span>{String(props.entryContext?.sourceWorkspace ?? 'none')}</span>
      <span>{String(props.entryContext?.techBottleneckSource ?? 'none')}</span>
      <span>{String(props.entryContext?.stockName ?? 'none')}</span>
      <span>{String(props.entryContext?.reportStatus ?? 'no-report-status')}</span>
      <span>{String(props.entryContext?.reportHtmlPath ?? 'no-report-html')}</span>
    </div>
  )
}));
vi.mock('../src/components/StrategyLabWorkspace', () => ({ StrategyLabWorkspace: () => <div>Strategy Lab</div> }));
vi.mock('../src/components/WatchlistWorkspace', () => ({ WatchlistWorkspace: () => <div>Watchlist</div> }));

const routePath = '/tech-bottleneck/watchlist-review';

describe('Tech Bottleneck candidate universe review page upgrade', () => {
  beforeEach(() => {
    window.history.pushState({}, '', routePath);
  });

  afterEach(() => {
    cleanup();
  });

  it('shows a compact status strip and keeps audit text out of the default queue view', () => {
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
    expect(screen.queryByRole('heading', { name: 'research_workbench_pool_ready' })).not.toBeInTheDocument();
    expect(screen.queryByText('Pipeline closure')).not.toBeInTheDocument();
    expect(screen.queryByText(/canonical core pool:/)).not.toBeInTheDocument();
  });

  it('renders core candidates and keeps rescue/reject candidates in the right tabs', () => {
    render(<AppShell />);

    const coreTab = screen.getByRole('tab', { name: 'Hard-Tech Review Pool 90' });
    expect(coreTab).toHaveAttribute('aria-selected', 'true');
    const table = within(screen.getByRole('region', { name: 'Core candidate table' }));
    expect(table.getAllByRole('row').length).toBeGreaterThan(5);
    expect(table.getByText('京泉华')).toBeInTheDocument();
    expect(table.getByText('浙江力诺')).toBeInTheDocument();
    expect(table.getByText('北方华创')).toBeInTheDocument();
    expect(table.getByText('中微公司')).toBeInTheDocument();
    expect(table.getByText('report_status')).toBeInTheDocument();
    expect(table.getByText('bottleneck_confidence_score')).toBeInTheDocument();
    expect(table.getByText('evidence_quality_score')).toBeInTheDocument();
    expect(table.getByText('review_decision')).toBeInTheDocument();
    expect(table.getAllByText('打开HTML报告').length).toBeGreaterThan(0);
    expect(table.getAllByText('打开PDF报告').length).toBeGreaterThan(0);
    expect(table.getAllByText('查看证据矩阵').length).toBeGreaterThan(0);
    expect(table.queryByText('道恩股份')).not.toBeInTheDocument();
    expect(table.queryByText('神农集团')).not.toBeInTheDocument();
    expect(table.queryByText('佛山照明')).not.toBeInTheDocument();
    expect(table.queryByText('通宝能源')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Evidence Backfill 11' }));
    expect(screen.getByRole('region', { name: 'Evidence backfill table' })).toHaveTextContent('道恩股份');

    fireEvent.click(screen.getByRole('tab', { name: 'Rejected / Downgrade 3' }));
    expect(screen.getByRole('region', { name: 'Rejected downgrade table' })).toHaveTextContent('神农集团');
  });

  it('sorts core rows by priority fallback and supports filters', () => {
    render(<AppShell />);

    const coreTable = screen.getByRole('table', { name: 'Hard-Tech Review Pool Table' });
    const firstBodyRow = within(coreTable).getAllByRole('row')[1];
    expect(within(firstBodyRow).getByText('000400')).toBeInTheDocument();

    fireEvent.click(within(coreTable).getByRole('button', { name: 'Sort by research_priority_score' }));
    const resortedFirstBodyRow = within(coreTable).getAllByRole('row')[1];
    expect(within(resortedFirstBodyRow).queryByText('000400')).not.toBeInTheDocument();

    fireEvent.click(within(coreTable).getByRole('button', { name: 'Sort by research_priority_score' }));
    expect(within(coreTable).getAllByRole('row')[1]).toHaveTextContent('000400');

    fireEvent.change(screen.getByLabelText('证据强度'), { target: { value: 'moderate' } });
    expect(screen.getByRole('region', { name: 'Core candidate table' })).toHaveTextContent('moderate');
    expect(screen.queryByText('000400')).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('证据强度'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('瓶颈相关性'), { target: { value: 'core' } });
    expect(screen.getByRole('region', { name: 'Core candidate table' })).toHaveTextContent('core');

    fireEvent.change(screen.getByLabelText('来源'), { target: { value: 'verified_rescue_extension_proposal' } });
    expect(screen.getByRole('region', { name: 'Core candidate table' })).toHaveTextContent('京泉华');
    expect(screen.getByRole('region', { name: 'Core candidate table' })).toHaveTextContent('浙江力诺');

    fireEvent.change(screen.getByLabelText('股票代码/名称搜索'), { target: { value: '京泉华' } });
    expect(screen.getByRole('region', { name: 'Core candidate table' })).toHaveTextContent('京泉华');
    expect(screen.getByRole('region', { name: 'Core candidate table' })).not.toHaveTextContent('浙江力诺');
  });

  it('navigates from a clickable candidate row to the individual stock workbench with source context', () => {
    render(<AppShell />);

    fireEvent.change(screen.getByLabelText('来源'), { target: { value: 'verified_rescue_extension_proposal' } });
    fireEvent.click(screen.getByRole('row', { name: /002885 京泉华/ }));

    expect(window.location.pathname).toBe('/tech-bottleneck/stock/002885');
    expect(window.location.search).toContain('source=tech_bottleneck_candidate_universe_pipeline_closure_v2');
    expect(screen.getByRole('heading', { name: 'Stock Workspace' })).toBeInTheDocument();
    expect(screen.getByText('002885.SZ')).toBeInTheDocument();
    expect(screen.getByText('techBottleneck')).toBeInTheDocument();
    expect(screen.getByText('tech_bottleneck_candidate_universe_pipeline_closure_v2')).toBeInTheDocument();
    expect(screen.getByText('京泉华')).toBeInTheDocument();
    expect(
      screen.getByText((content) => content.includes('outputs/research/tech_bottleneck_candidate_reports_enriched_v1/reports/002885_'))
    ).toBeInTheDocument();
    expect(screen.queryByText('入选策略')).not.toBeInTheDocument();
    expect(screen.queryByText('生成信号')).not.toBeInTheDocument();
    expect(screen.queryByText('加入准入池')).not.toBeInTheDocument();
  });

  it('shows audit details only inside the Guardrails tab', () => {
    render(<AppShell />);

    expect(screen.queryByText('Pipeline closure')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Guardrails' }));
    expect(screen.getByText('Pipeline closure')).toBeInTheDocument();
    expect(screen.getByText(/canonical default pool:/)).toBeInTheDocument();
    expect(screen.getByText('legacy_unverified_pool / deprecated_for_default_core_use')).toBeInTheDocument();
    expect(screen.getByText('Old 114 pool is not the default dashboard pool.')).toBeInTheDocument();
    expect(screen.getByText('Tier A pass was pass-by-construction, not independent validation.')).toBeInTheDocument();
    expect(screen.getByText('Tier B high_quality=0 was threshold/data-gap driven.')).toBeInTheDocument();
    expect(screen.getByText('allowed_for_signal=0')).toBeInTheDocument();
    expect(screen.getByText('allowed_for_admission=0')).toBeInTheDocument();
  });
});
