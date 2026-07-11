import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WatchlistWorkspace } from '../src/components/WatchlistWorkspace';
import type { WatchlistSignalRow } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchWatchlistSignals: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

const reviewedThemeContext = {
  asset_id: '000001.SZ',
  company_code: '000001.SZ',
  status: 'reviewed_context_available',
  driver_assessment: 'mixed_or_uncertain',
  theme_count: 1,
  mapping_count: 1,
  evidence_gap_count: 0,
  themes: [
    {
      theme_id: 'ai_power_value_capture_v1',
      theme_name: 'AI供电产业链',
      theme_type: 'ai_power',
      summary: 'reviewed context',
      status: 'reviewed',
      dashboard_path: '/theme-research/ai_power_value_capture_v1',
      research_only: true as const,
      used_for_signal: false as const,
      used_for_admission: false as const
    }
  ],
  mappings: [
    {
      mapping_id: 'mapping-1',
      theme_id: 'ai_power_value_capture_v1',
      company_code: '000001.SZ',
      company_name: '平安银行',
      mapping_type: 'direct_product',
      confidence: 0.9,
      revenue_relevance: 'material',
      bottleneck_relevance: 'core',
      business_materiality: 'core_business',
      business_stage: 'primary_business',
      product_or_service: '液冷',
      relationship_summary: '已审核映射',
      review_status: 'reviewed',
      node: {
        node_id: 'liquid_cooling',
        theme_id: 'ai_power_value_capture_v1',
        parent_node_id: null,
        node_name: '液冷',
        node_type: 'subsystem',
        description: '液冷节点',
        value_capture_score: 5,
        bottleneck_score: 4,
        localization_gap_score: 3,
        supply_tightness_score: 4,
        evidence_strength: 3,
        node_review_status: 'reviewed'
      },
      evidence_items: [],
      reviewed_claims: [],
      company_relevance_score: 4.5,
      company_research_priority_score: 78.8,
      priority_band: 'high',
      recommended_action: 'deep_research',
      research_only: true as const,
      used_for_signal: false as const,
      used_for_admission: false as const
    }
  ],
  excluded_mappings: [],
  research_only: true as const,
  used_for_signal: false as const,
  used_for_admission: false as const,
  source: 'research.theme_research_company_mapping',
  warnings: []
};

const rows: WatchlistSignalRow[] = [
  {
    watchlist_id: 'default',
    trade_date: '2026-06-08',
    asset_id: '000001.SZ',
    stock_code: '000001',
    stock_name: '平安银行',
    priority: 8,
    signal_score: 82.4,
    primary_signal: 'candidate',
    signal_tags: ['breakout', 'volume'],
    risk_tags: ['earnings'],
    must_watch: true,
    reason_json: {
      next_action: 'review close above 10d high',
      reason: 'score breakout'
    },
    theme_research_context: reviewedThemeContext
  },
  {
    watchlist_id: 'default',
    trade_date: '2026-06-08',
    asset_id: '600000.SH',
    stock_code: '600000',
    stock_name: '浦发银行',
    priority: 3,
    signal_score: 52,
    primary_signal: 'observe',
    signal_tags: ['base'],
    risk_tags: ['liquidity'],
    must_watch: false,
    reason_json: {}
  }
];

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.fetchWatchlistSignals.mockResolvedValue(rows);
});

afterEach(() => {
  cleanup();
});

describe('WatchlistWorkspace', () => {
  it('renders the EOD queue and opens a selected stock', async () => {
    const onOpenAsset = vi.fn();
    render(<WatchlistWorkspace onOpenAsset={onOpenAsset} />);

    expect(await screen.findByText('平安银行')).toBeInTheDocument();
    expect(screen.getByText('review close above 10d high')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'AI供电产业链' })).toHaveAttribute(
      'href',
      '/theme-research/ai_power_value_capture_v1'
    );
    expect(screen.getByText('液冷 · 价值量 5/5 · 卡脖子 4/5')).toBeInTheDocument();
    expect(screen.getByText('已审核研究')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Open 000001.SZ' }));

    expect(onOpenAsset).toHaveBeenCalledWith('000001.SZ');
    expect(apiMocks.fetchWatchlistSignals).toHaveBeenCalledWith('default', '2026-06-18');
  });

  it('shows evidence-gap and no-mapping states without creating signals', async () => {
    apiMocks.fetchWatchlistSignals.mockResolvedValueOnce([
      {
        ...rows[1],
        theme_research_context: {
          ...reviewedThemeContext,
          asset_id: rows[1].asset_id,
          company_code: rows[1].asset_id,
          status: 'evidence_gap',
          theme_count: 0,
          mapping_count: 0,
          evidence_gap_count: 1,
          themes: [],
          mappings: [],
          excluded_mappings: [
            {
              mapping_id: 'draft-1',
              theme_id: 'humanoid_robotics_head_to_toe_v1',
              node_id: 'harmonic_reducer',
              reasons: ['mapping_not_reviewed']
            }
          ]
        }
      }
    ]);

    render(<WatchlistWorkspace />);

    expect(await screen.findByText('证据待补')).toBeInTheDocument();
    expect(screen.getByText('不参与信号或准入')).toBeInTheDocument();
  });

  it('uses the supplied latest trade date instead of the legacy hard-coded date', async () => {
    render(<WatchlistWorkspace defaultTradeDate="2026-06-18" />);

    expect(await screen.findByText('平安银行')).toBeInTheDocument();
    expect(screen.getByLabelText('trade date')).toHaveValue('2026-06-18');
    expect(apiMocks.fetchWatchlistSignals).toHaveBeenCalledWith('default', '2026-06-18');
  });

  it('filters by status and minimum priority', async () => {
    render(<WatchlistWorkspace />);

    expect(await screen.findByText('平安银行')).toBeInTheDocument();
    expect(screen.getByText('浦发银行')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('watchlist status'), { target: { value: 'candidate' } });
    fireEvent.change(screen.getByLabelText('minimum priority'), { target: { value: '5' } });

    await waitFor(() => {
      expect(screen.getByText('平安银行')).toBeInTheDocument();
      expect(screen.queryByText('浦发银行')).not.toBeInTheDocument();
    });
  });

  it('explains an empty manual observation queue', async () => {
    apiMocks.fetchWatchlistSignals.mockResolvedValueOnce([]);

    render(<WatchlistWorkspace />);

    expect(await screen.findByText('当前观察池暂无记录。')).toBeInTheDocument();
    expect(screen.getByText('当前日期暂无观察记录。你可以在个股工作台点击“观察”创建人工观察项；如果想看策略候选池，请切换到复盘队列。')).toBeInTheDocument();
    expect(screen.getByText('当前查询：default / 2026-06-18')).toBeInTheDocument();
  });
});
