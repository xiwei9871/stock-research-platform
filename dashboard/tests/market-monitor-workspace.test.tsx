import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MarketMonitorWorkspace } from '../src/components/MarketMonitorWorkspace';
import type { MarketMonitorPayload } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchMarketMonitorEod: vi.fn()
}));

const echartsMocks = vi.hoisted(() => {
  const handlers = new Map<string, (params: unknown) => void>();
  const chart = {
    dispose: vi.fn(),
    off: vi.fn((eventName?: string) => {
      if (eventName) handlers.delete(eventName);
    }),
    on: vi.fn((eventName: string, handler: (params: unknown) => void) => {
      handlers.set(eventName, handler);
    }),
    resize: vi.fn(),
    setOption: vi.fn()
  };

  return {
    chart,
    handlers,
    init: vi.fn(() => chart)
  };
});

vi.mock('../src/api/client', () => apiMocks);
vi.mock('echarts', () => echartsMocks);

function makeMarketMonitorPayload(overrides: Partial<MarketMonitorPayload> = {}): MarketMonitorPayload {
  return {
    trade_date: '2026-06-12',
    freshness: {
      mode: 'eod',
      label: 'Last Completed Trading Day',
      is_realtime: false,
      latest_market_date: '2026-06-12',
      latest_factor_date: '2026-06-12',
      latest_score_date: '2026-06-12'
    },
    coverage: { market_assets: 5300, score_assets: 3100, factor_count: 42 },
    market_breadth: {
      advancers: null,
      decliners: null,
      limit_up: null,
      limit_down: null,
      advancing_ratio: null,
      turnover_change_pct: null,
      status: 'pending_source'
    },
    index_snapshot: [],
    sector_strength: { strongest: [], weakest: [], status: 'pending_source' },
    unusual_moves: [],
    watchlist_alerts: [],
    strategy_signal_summary: {
      topn_preview_count: 0,
      topn_preview: [],
      risk_filter_counts: {}
    },
    generated_reports: [],
    market_emotion: {
      summary: {
        score: 73.6,
        state: 'hot',
        risk_state: 'medium',
        style_signal_hint: 'growth_favorable',
        position_budget_hint: 'reduced',
        status: 'available'
      },
      components: [
        { key: 'breadth', label: '涨跌家数', score: 68.2 },
        { key: 'limit', label: '涨停表现', score: 75.4 }
      ],
      breadth: {
        traded_count: 5207,
        up_count: 3610,
        down_count: 1492,
        strong_up_count: 269,
        strong_down_count: 55,
        status: 'available'
      },
      liquidity: {
        total_amount: 1280000000000,
        amount_ratio_5_20: 1.18,
        status: 'available'
      },
      limit_performance: {
        limit_up_count: 90,
        limit_down_count: 10,
        broken_limit_up_count: 55,
        broken_limit_up_rate: 0.3793,
        first_board_count: 58,
        second_board_count: 21,
        third_board_plus_count: 11,
        high_board_height: 6,
        status: 'available'
      },
      profit_effect: {
        limit_up_success_rate: 0.7361,
        limit_up_profit_rate: 0.026,
        limit_up_limit_down_rate: 0.026,
        relay_profit_rate: 0.018,
        relay_success_rate: 0.615,
        relay_continue_rate: 0.312,
        broken_profit_rate: 0.007,
        broken_success_rate: 0.564,
        broken_limit_down_rate: 0.073,
        status: 'available'
      },
      drawdown_pressure: {
        strong_down_count: 55,
        limit_down_count: 10,
        broken_limit_up_rate: 0.3793,
        yesterday_limit_up_limit_down_rate: 0.026,
        status: 'available'
      },
      weight_performance: { status: 'pending_source' }
    },
    emotion_stock_lists: {
      auction_status: 'pending_source',
      auction: [],
      limit_up: [],
      broken_limit_up: [],
      limit_down: []
    },
    warnings: [],
    ...overrides
  };
}

function renderWorkspace(extraProps?: Record<string, unknown>) {
  render(<MarketMonitorWorkspace {...(extraProps as never)} />);
}

function overrideChartSize(width: number, height: number) {
  const widthDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientWidth');
  const heightDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientHeight');

  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    get() {
      return width;
    }
  });

  Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
    configurable: true,
    get() {
      return height;
    }
  });

  return () => {
    if (widthDescriptor) {
      Object.defineProperty(HTMLElement.prototype, 'clientWidth', widthDescriptor);
    } else {
      delete (HTMLElement.prototype as { clientWidth?: number }).clientWidth;
    }

    if (heightDescriptor) {
      Object.defineProperty(HTMLElement.prototype, 'clientHeight', heightDescriptor);
    } else {
      delete (HTMLElement.prototype as { clientHeight?: number }).clientHeight;
    }
  };
}

describe('MarketMonitorWorkspace', () => {
  beforeEach(() => {
    apiMocks.fetchMarketMonitorEod.mockResolvedValue(makeMarketMonitorPayload());
    echartsMocks.handlers.clear();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('renders the mock-first market monitor stage with overview, heatmap, ranking, and compact emotion', async () => {
    renderWorkspace();

    expect(screen.getByRole('heading', { name: '市场总览' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '板块热力图' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '板块资金排行' })).toBeInTheDocument();
    expect(screen.getByText('点击热力图或资金榜查看板块详情')).toBeInTheDocument();

    await waitFor(() => expect(apiMocks.fetchMarketMonitorEod).toHaveBeenCalled());
    expect(screen.getByRole('heading', { name: '市场情绪摘要' })).toBeInTheDocument();
  });

  it('updates the detail panel when a ranking row is selected', () => {
    const onOpenAsset = vi.fn();
    renderWorkspace({ onOpenAsset });

    fireEvent.click(screen.getByRole('button', { name: '查看板块详情 半导体' }));

    const detailPanel = screen.getByRole('heading', { name: '板块详情' }).closest('section');
    expect(detailPanel).not.toBeNull();

    const scoped = within(detailPanel as HTMLElement);
    expect(scoped.getByRole('heading', { level: 3, name: '半导体' })).toBeInTheDocument();
    expect(scoped.getByText('行业板块')).toBeInTheDocument();

    fireEvent.click(scoped.getByRole('button', { name: '打开领涨股 北方华创' }));

    expect(onOpenAsset).toHaveBeenCalledWith(
      'CN:SZ:002371',
      expect.objectContaining({
        sourceWorkspace: 'market',
        monitorTab: 'industry',
        query: '北方华创',
        tradeDate: '2026-06-12'
      })
    );
  });

  it('switches between 行业 and 概念 and updates the primary content', () => {
    renderWorkspace();

    expect(screen.getByRole('button', { name: '行业' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '查看板块详情 半导体' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '查看板块详情 AI算力' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '概念' }));

    expect(screen.getByRole('button', { name: '概念' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '查看板块详情 AI算力' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '查看板块详情 半导体' })).not.toBeInTheDocument();
  });

  it('keeps the compact emotion panel visible even when the main mock data is empty', async () => {
    renderWorkspace({
      mockDataOverride: {
        marketOverview: {
          tradeDate: '2026-06-12',
          updatedAt: '2026-06-12 15:10',
          dataStatus: 'missing',
          totalAmount: null,
          upCount: null,
          downCount: null,
          limitUpCount: null,
          limitDownCount: null,
          indices: []
        },
        industryHeatmap: [],
        conceptHeatmap: [],
        sectorFundFlow: {
          industry: { inflow: [], outflow: [] },
          concept: { inflow: [], outflow: [] }
        },
        sectorDetails: {}
      }
    });

    expect(screen.getByText('暂无板块热力图数据')).toBeInTheDocument();
    expect(screen.getByText('暂无板块资金排行数据')).toBeInTheDocument();

    await waitFor(() => expect(apiMocks.fetchMarketMonitorEod).toHaveBeenCalled());
    expect(screen.getByRole('heading', { name: '市场情绪摘要' })).toBeInTheDocument();
    expect(screen.getByText('综合强度')).toBeInTheDocument();
  });

  it('skips echarts initialization when the heatmap container has no measurable size', () => {
    renderWorkspace();

    expect(screen.getByRole('heading', { name: '板块热力图' })).toBeInTheDocument();
    expect(echartsMocks.init).not.toHaveBeenCalled();
  });

  it('initializes an echarts treemap when the heatmap container can be measured', async () => {
    const restoreChartSize = overrideChartSize(960, 360);

    try {
      renderWorkspace();

      await waitFor(() => expect(echartsMocks.init).toHaveBeenCalledTimes(1));

      const latestOption = echartsMocks.chart.setOption.mock.calls.at(-1)?.[0];
      const treemapSeries = Array.isArray(latestOption?.series) ? latestOption.series[0] : null;

      expect(treemapSeries?.type).toBe('treemap');
      expect(treemapSeries?.data).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            sectorId: 'industry-semiconductor',
            sectorName: '半导体'
          })
        ])
      );
    } finally {
      restoreChartSize();
    }
  });
});
