import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StockWorkspace } from '../src/components/StockWorkspace';
import { reviewUniverseTechBottleneckEntryContext } from './stock-workspace-tech-bottleneck-fixtures';

const apiMocks = vi.hoisted(() => ({
  fetchEvidenceDigest: vi.fn(),
  fetchAssetNews: vi.fn(),
  fetchAssetProfile: vi.fn(),
  fetchAssetResearchReports: vi.fn(),
  fetchDailyBars: vi.fn(),
  fetchStockMarketContextHeatmap: vi.fn(),
  searchAssets: vi.fn(),
  createOperatorDecision: vi.fn(),
  updateOperatorDecision: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

vi.mock('../src/charts/AssetChart', () => ({
  AssetChart: ({ bars, timeAxisMode }: { bars: unknown[]; timeAxisMode?: string }) => (
    <div data-testid="asset-chart">
      {bars.length} bars / {timeAxisMode}
    </div>
  )
}));

function renderTechBottleneckWorkspace() {
  return render(<StockWorkspace initialAssetId="000049.SZ" entryContext={reviewUniverseTechBottleneckEntryContext} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.fetchAssetProfile.mockResolvedValue({
    asset_id: '000049.SZ',
    canonical_asset_id: '000049.SZ',
    asset: { asset_id: '000049.SZ', symbol: '000049', name: '德赛电池', exchange: 'SZ', board: null, is_active: true },
    bars: [
      { time: '2026-06-05', open: 26, high: 27, low: 25.6, close: 26.4, volume: 1000, amount: 26400 },
      { time: '2026-06-08', open: 26.4, high: 27.4, low: 26.1, close: 27, volume: 1300, amount: 35100 }
    ],
    score: {
      trade_date: '2026-06-08',
      asset_id: '000049.SZ',
      rank: 7,
      score_total: 80.1,
      score_version: 'manual_v1',
      score_components: { momentum: 28.2, quality: 18.8 }
    },
    signals: [
      {
        watchlist_id: 'default',
        trade_date: '2026-06-08',
        asset_id: '000049.SZ',
        stock_code: '000049',
        stock_name: '德赛电池',
        priority: 6,
        signal_score: 80.1,
        primary_signal: 'candidate',
        signal_tags: ['momentum'],
        risk_tags: ['crowded'],
        must_watch: true,
        reason_json: { next_action: 'review follow-through' }
      }
    ],
    decisions: [],
    outcomes: [],
    factor_values: [{ factor_name: 'momentum_20d', factor_group: 'momentum', factor_value: 0.17 }],
    coverage: { bars: { start: '2026-06-05', end: '2026-06-08' } }
  });
  apiMocks.fetchAssetResearchReports.mockResolvedValue({
    asset_id: '000049.SZ',
    summary: {
      report_count_30d: 0,
      report_count_90d: 0,
      broker_coverage_count_90d: 0,
      latest_report_date: null,
      latest_rating: null,
      latest_target_price: null
    },
    items: [],
    warnings: []
  });
  apiMocks.fetchAssetNews.mockResolvedValue({
    asset_id: '000049.SZ',
    items: [],
    summary: {
      news_count_1d: 0,
      news_count_3d: 0,
      news_count_7d: 0,
      latest_published_at: null,
      source_count: 0,
      category_counts: []
    },
    warnings: []
  });
  apiMocks.fetchEvidenceDigest.mockResolvedValue({
    asset_id: '000049.SZ',
    canonical_asset_id: '000049.SZ',
    trade_date: '2026-06-18',
    title: '德赛电池 evidence digest',
    score: 58,
    bucket: 'thin',
    facts: [{ kind: 'news', key: 'news-1', label: 'Recent company news is available' }],
    risk_flags: [],
    source_refs: { workspace: 'stock', asset_id: '000049.SZ' },
    next_actions: [],
    warnings: []
  });
  apiMocks.fetchDailyBars.mockResolvedValue([]);
  apiMocks.fetchStockMarketContextHeatmap.mockResolvedValue({
    asset_id: '000049.SZ',
    canonical_asset_id: '000049.SZ',
    trade_date: '2026-06-18',
    industry: { industry_id: 'battery', industry_name: '电池', industry_system: 'csrc' },
    selected: null,
    summary: {
      peer_count: 0,
      up_count: 0,
      flat_count: 0,
      down_count: 0,
      total_amount: 0,
      selected_in_peer_set: false
    },
    peers: [],
    data_status: 'missing',
    warnings: []
  });
  apiMocks.searchAssets.mockResolvedValue([]);
  apiMocks.createOperatorDecision.mockResolvedValue({
    event_id: 'operator_decision:layout-test',
    asset_id: '000049.SZ',
    stock_code: '000049',
    stock_name: '德赛电池',
    decision_date: '2026-06-08',
    operator_action: 'watch',
    decision_status: 'open',
    decision_label: 'observe',
    run_id: 'layout-test',
    digest_key: '2026-06-18:manual_v1:000049.SZ',
    review_item_snapshot_id: 'review_item_snapshot:layout-test',
    evidence_digest_snapshot_id: 'evidence_digest_snapshot:layout-test',
    snapshot_linkage_status: 'linked',
    snapshot_linkage_warnings: [],
    warnings: []
  });
});

afterEach(() => {
  cleanup();
});

describe('StockWorkspace A layout', () => {
  it('keeps quote before thesis and strategy evidence digest sections', async () => {
    renderTechBottleneckWorkspace();

    const quote = await screen.findByRole('region', { name: '今日价格行为' });
    const thesis = await screen.findByRole('region', { name: '科技卡脖子复盘摘要' });
    const strategyEvidence = await screen.findByRole('region', { name: '策略证据摘要' });

    expect(quote.compareDocumentPosition(thesis) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(quote.compareDocumentPosition(strategyEvidence) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('does not show verbose tech source workspace text in the default reading path', async () => {
    renderTechBottleneckWorkspace();

    await screen.findByRole('heading', { name: /德赛电池/ });
    expect(screen.queryByText('来源工作台：科技卡脖子复盘')).not.toBeInTheDocument();
    expect(screen.queryByText('科技卡脖子来源 tech_bottleneck_review_universe_frontend_dataset_v1')).not.toBeInTheDocument();
  });

  it('keeps replay controls collapsed and below the primary evidence block', async () => {
    renderTechBottleneckWorkspace();

    const strategyEvidence = await screen.findByRole('region', { name: '策略证据摘要' });
    const workspaceTools = await screen.findByRole('region', { name: '工作台工具' });
    const replayControls = screen.getByText('回放 / 切换设置').closest('details');

    expect(replayControls).not.toBeNull();
    expect(replayControls).not.toHaveAttribute('open');
    expect(strategyEvidence.compareDocumentPosition(replayControls as Node) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(workspaceTools.compareDocumentPosition(replayControls as Node) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
