import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MarketMonitorWorkspace } from '../src/components/MarketMonitorWorkspace';
import type { MarketMonitorPayload } from '../src/api/types';
import type { ComponentProps } from 'react';

const apiMocks = vi.hoisted(() => ({
  fetchMarketMonitorEod: vi.fn(),
  fetchMarketOverview: vi.fn(),
  fetchSectorHeatmap: vi.fn(),
  fetchSectorFundFlow: vi.fn(),
  fetchSectorDetail: vi.fn()
}));

const echartsMocks = vi.hoisted(() => {
  const charts: Array<{
    dispose: ReturnType<typeof vi.fn>;
    off: ReturnType<typeof vi.fn>;
    on: ReturnType<typeof vi.fn>;
    resize: ReturnType<typeof vi.fn>;
    setOption: ReturnType<typeof vi.fn>;
  }> = [];
  const handlers = new Map<string, (params: unknown) => void>();

  function makeChart() {
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
    charts.push(chart);
    return chart;
  }

  return {
    charts,
    handlers,
    init: vi.fn(() => makeChart())
  };
});

vi.mock('../src/api/client', () => apiMocks);
vi.mock('echarts', () => echartsMocks);

const resizeObserverMocks = vi.hoisted(() => {
  const instances: Array<{
    observe: ReturnType<typeof vi.fn>;
    disconnect: ReturnType<typeof vi.fn>;
    callback: ResizeObserverCallback;
  }> = [];

  class MockResizeObserver {
    observe = vi.fn();
    disconnect = vi.fn();
    callback: ResizeObserverCallback;

    constructor(callback: ResizeObserverCallback) {
      this.callback = callback;
      instances.push(this);
    }
  }

  return {
    instances,
    MockResizeObserver
  };
});

const animationFrameMocks = vi.hoisted(() => {
  let nextFrameId = 1;
  const callbacks = new Map<number, FrameRequestCallback>();

  return {
    callbacks,
    requestAnimationFrame: vi.fn((callback: FrameRequestCallback) => {
      const frameId = nextFrameId;
      nextFrameId += 1;
      callbacks.set(frameId, callback);
      return frameId;
    }),
    cancelAnimationFrame: vi.fn((frameId: number) => {
      callbacks.delete(frameId);
    }),
    flushNextFrame() {
      const [frameId, callback] = callbacks.entries().next().value ?? [];
      if (!frameId || !callback) return false;
      callbacks.delete(frameId);
      callback(performance.now());
      return true;
    },
    reset() {
      nextFrameId = 1;
      callbacks.clear();
      this.requestAnimationFrame.mockClear();
      this.cancelAnimationFrame.mockClear();
    }
  };
});

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

function makeOverviewResponse(overrides: Record<string, unknown> = {}) {
  return {
    trade_date: '2026-06-12',
    updated_at: '2026-06-12 15:10',
    source: 'api',
    data_status: 'completed',
    warnings: [],
    indices: [
      {
        code: '000001',
        name: 'API上证指数',
        close: 3201.88,
        change_pct: 0.0123
      }
    ],
    total_amount: 1666000000000,
    up_count: 3988,
    down_count: 1102,
    limit_up_count: 118,
    limit_down_count: 7,
    ...overrides
  };
}

function makeHeatmapItems(sectorType: 'industry' | 'concept') {
  if (sectorType === 'concept') {
    return [
      {
        sector_id: 'concept-api-compute',
        sector_name: 'API算力',
        sector_type: 'concept',
        change_pct: 0.0412,
        amount: 188800000000,
        up_count: 103,
        down_count: 19,
        main_net_inflow: 25600000000,
        stock_count: 132
      },
      {
        sector_id: 'concept-api-fade',
        sector_name: 'API退潮',
        sector_type: 'concept',
        change_pct: -0.0268,
        amount: 98800000000,
        up_count: 21,
        down_count: 88,
        main_net_inflow: -14600000000,
        stock_count: 119
      }
    ];
  }

  return [
    {
      sector_id: 'industry-api-chip',
      sector_name: 'API半导体',
      sector_type: 'industry',
      change_pct: 0.0315,
      amount: 146600000000,
      up_count: 96,
      down_count: 12,
      main_net_inflow: 22100000000,
      stock_count: 118
    },
    {
      sector_id: 'industry-api-down',
      sector_name: 'API回调',
      sector_type: 'industry',
      change_pct: -0.0242,
      amount: 86600000000,
      up_count: 18,
      down_count: 92,
      main_net_inflow: -15100000000,
      stock_count: 114
    }
  ];
}

function makeHeatmapResponse(sectorType: 'industry' | 'concept', overrides: Record<string, unknown> = {}) {
  return {
    trade_date: '2026-06-12',
    updated_at: '2026-06-12 15:10',
    source: 'api',
    data_status: 'completed',
    warnings: [],
    items: makeHeatmapItems(sectorType),
    ...overrides
  };
}

function makeManyHeatmapItems(count: number, sectorType: 'industry' | 'concept' = 'industry') {
  return Array.from({ length: count }, (_, index) => ({
    sector_id: `${sectorType}-many-${index + 1}`,
    sector_name: `${sectorType === 'industry' ? '行业' : '概念'}板块${index + 1}`,
    sector_type: sectorType,
    change_pct: index % 2 === 0 ? 0.03 - index * 0.0005 : -0.01 - index * 0.0004,
    amount: 100000000000 - index * 1000000000,
    up_count: 80 - index,
    down_count: 20 + index,
    main_net_inflow: 3000000000 - index * 100000000,
    stock_count: 100 + index
  }));
}

function makeFundFlowResponse(sectorType: 'industry' | 'concept', overrides: Record<string, unknown> = {}) {
  const [item, outflowItem] = makeHeatmapItems(sectorType);
  return {
    trade_date: '2026-06-12',
    updated_at: '2026-06-12 15:10',
    source: 'api',
    data_status: 'completed',
    warnings: [],
    inflow: [
      {
        rank: 1,
        sector_id: item.sector_id,
        sector_name: item.sector_name,
        sector_type: item.sector_type,
        change_pct: item.change_pct,
        amount: item.amount,
        main_net_inflow: item.main_net_inflow,
        main_net_inflow_ratio: 0.153,
        leading_stock_name: sectorType === 'concept' ? '真实算力龙头' : '真实半导体龙头'
      }
    ],
    outflow: [
      {
        rank: 1,
        sector_id: outflowItem.sector_id,
        sector_name: outflowItem.sector_name,
        sector_type: outflowItem.sector_type,
        change_pct: outflowItem.change_pct,
        amount: outflowItem.amount,
        main_net_inflow: outflowItem.main_net_inflow,
        main_net_inflow_ratio: -0.121,
        leading_stock_name: sectorType === 'concept' ? '真实退潮龙头' : '真实回调龙头'
      }
    ],
    ...overrides
  };
}

function makeManyFundFlowResponse(sectorType: 'industry' | 'concept' = 'industry') {
  const inflow = makeManyHeatmapItems(14, sectorType);
  const outflow = makeManyHeatmapItems(14, sectorType).map((item, index) => ({
    ...item,
    sector_id: `${sectorType}-outflow-${index + 1}`,
    sector_name: `${sectorType === 'industry' ? '行业' : '概念'}流出${index + 1}`,
    main_net_inflow: -Math.abs(item.main_net_inflow)
  }));

  return {
    trade_date: '2026-06-12',
    updated_at: '2026-06-12 15:10',
    source: 'api',
    data_status: 'completed',
    warnings: [],
    inflow: inflow.map((item, index) => ({
      rank: index + 1,
      sector_id: item.sector_id,
      sector_name: item.sector_name,
      sector_type: item.sector_type,
      change_pct: item.change_pct,
      amount: item.amount,
      main_net_inflow: item.main_net_inflow,
      main_net_inflow_ratio: 0.12 - index * 0.002,
      leading_stock_name: `流入龙头${index + 1}`
    })),
    outflow: outflow.map((item, index) => ({
      rank: index + 1,
      sector_id: item.sector_id,
      sector_name: item.sector_name,
      sector_type: item.sector_type,
      change_pct: item.change_pct,
      amount: item.amount,
      main_net_inflow: item.main_net_inflow,
      main_net_inflow_ratio: -0.08 - index * 0.002,
      leading_stock_name: `流出龙头${index + 1}`
    }))
  };
}

function makeSectorDetailResponse(overrides: Record<string, unknown> = {}) {
  return {
    trade_date: '2026-06-12',
    updated_at: '2026-06-12 15:20',
    source: 'api',
    data_status: 'completed',
    warnings: [],
    sector_id: 'industry-api-chip',
    sector_name: 'API半导体',
    sector_type: 'industry',
    change_pct: 0.0315,
    amount: 146600000000,
    up_count: 96,
    down_count: 12,
    main_net_inflow: 22100000000,
    main_net_inflow_ratio: 0.153,
    leading_stocks: [
      {
        asset_id: 'CN:SH:688981',
        name: '真实龙头',
        change_pct: 0.0521
      }
    ],
    ...overrides
  };
}

function renderWorkspace(extraProps?: Partial<ComponentProps<typeof MarketMonitorWorkspace>>) {
  render(<MarketMonitorWorkspace {...extraProps} />);
}

function overrideChartSize(initialWidth: number, initialHeight: number) {
  let width = initialWidth;
  let height = initialHeight;
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

  return {
    setSize(nextWidth: number, nextHeight: number) {
      width = nextWidth;
      height = nextHeight;
    },
    restore() {
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
    }
  };
}

describe('MarketMonitorWorkspace', () => {
  beforeEach(() => {
    apiMocks.fetchMarketMonitorEod.mockResolvedValue(makeMarketMonitorPayload());
    apiMocks.fetchMarketOverview.mockResolvedValue(makeOverviewResponse());
    apiMocks.fetchSectorHeatmap.mockImplementation((tradeDate: string, sectorType: 'industry' | 'concept') =>
      Promise.resolve(makeHeatmapResponse(sectorType, { trade_date: tradeDate }))
    );
    apiMocks.fetchSectorFundFlow.mockImplementation((tradeDate: string, sectorType: 'industry' | 'concept') =>
      Promise.resolve(makeFundFlowResponse(sectorType, { trade_date: tradeDate }))
    );
    apiMocks.fetchSectorDetail.mockResolvedValue(makeSectorDetailResponse());
    echartsMocks.handlers.clear();
    echartsMocks.charts.length = 0;
    resizeObserverMocks.instances.length = 0;
    animationFrameMocks.reset();
    vi.stubGlobal('ResizeObserver', resizeObserverMocks.MockResizeObserver);
    vi.stubGlobal('requestAnimationFrame', animationFrameMocks.requestAnimationFrame);
    vi.stubGlobal('cancelAnimationFrame', animationFrameMocks.cancelAnimationFrame);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it('orchestrates overview, heatmap, ranking, and emotion APIs without letting mock data overwrite real results', async () => {
    renderWorkspace();

    await waitFor(() => {
      expect(apiMocks.fetchMarketOverview).toHaveBeenCalledWith('2026-06-12');
      expect(apiMocks.fetchSectorHeatmap).toHaveBeenCalledWith('2026-06-12', 'industry');
      expect(apiMocks.fetchSectorFundFlow).toHaveBeenCalledWith('2026-06-12', 'industry');
      expect(apiMocks.fetchMarketMonitorEod).toHaveBeenCalledWith({ topN: 5 });
    });

    expect(screen.getByRole('heading', { name: '市场总览' })).toBeInTheDocument();
    expect(screen.getByText('API上证指数')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '行业板块热力图' })).toBeInTheDocument();
    expect(screen.getByText('产业链权重')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '上涨板块热力图' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '下跌板块热力图' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '从上涨热力图摘要查看 API半导体' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '从下跌热力图摘要查看 API回调' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '板块资金排行' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '查看板块详情 API半导体' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '查看板块详情 半导体' })).not.toBeInTheDocument();
    expect(screen.getByText('点击热力图或资金榜查看板块详情')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: '市场情绪状态条' })).toBeInTheDocument();
    expect(screen.getByText('综合强度')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '市场情绪摘要' })).not.toBeInTheDocument();
  });

  it('updates the detail panel and starts real detail orchestration when a ranking row is selected', async () => {
    const onOpenAsset = vi.fn();
    renderWorkspace({ onOpenAsset });

    await waitFor(() => expect(apiMocks.fetchSectorFundFlow).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: '查看板块详情 API半导体' }));

    await waitFor(() => {
      expect(apiMocks.fetchSectorDetail).toHaveBeenCalledWith('2026-06-12', 'industry-api-chip');
    });

    const detailPanel = screen.getByRole('heading', { name: '板块详情' }).closest('section');
    expect(detailPanel).not.toBeNull();
    expect(detailPanel?.closest('.market-monitor-right-rail')).not.toBeNull();
    expect(detailPanel?.closest('.market-monitor-bottom-grid')).toBeNull();

    const scoped = within(detailPanel as HTMLElement);
    expect(scoped.getByRole('heading', { level: 3, name: 'API半导体' })).toBeInTheDocument();
    expect(scoped.getByText('行业板块')).toBeInTheDocument();
    expect(await scoped.findByRole('button', { name: '打开领涨股 真实龙头' })).toBeInTheDocument();

    fireEvent.click(scoped.getByRole('button', { name: '打开领涨股 真实龙头' }));

    expect(onOpenAsset).toHaveBeenCalledWith(
      'CN:SH:688981',
      expect.objectContaining({
        sourceWorkspace: 'market',
        monitorTab: 'industry',
        query: '真实龙头',
        tradeDate: '2026-06-12'
      })
    );
  });

  it('switches between 行业 and 概念 and reloads heatmap plus fund-flow without refetching overview', async () => {
    renderWorkspace();

    await waitFor(() => {
      expect(apiMocks.fetchMarketOverview).toHaveBeenCalledTimes(1);
      expect(apiMocks.fetchSectorHeatmap).toHaveBeenCalledWith('2026-06-12', 'industry');
      expect(apiMocks.fetchSectorFundFlow).toHaveBeenCalledWith('2026-06-12', 'industry');
    });

    const heatmapPanel = screen.getByRole('heading', { name: '行业板块热力图' }).closest('section');
    expect(heatmapPanel).not.toBeNull();
    const heatmapScope = within(heatmapPanel as HTMLElement);

    expect(heatmapScope.getByRole('button', { name: '行业' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '查看板块详情 API半导体' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '查看板块详情 API算力' })).not.toBeInTheDocument();

    fireEvent.click(heatmapScope.getByRole('button', { name: '概念' }));

    await waitFor(() => {
      expect(apiMocks.fetchMarketOverview).toHaveBeenCalledTimes(1);
      expect(apiMocks.fetchSectorHeatmap).toHaveBeenLastCalledWith('2026-06-12', 'concept');
      expect(apiMocks.fetchSectorFundFlow).toHaveBeenLastCalledWith('2026-06-12', 'concept');
    });

    expect(screen.getByRole('heading', { name: '概念板块热力图' })).toBeInTheDocument();
    expect(screen.getByText('题材弹性')).toBeInTheDocument();
    expect(within(screen.getByRole('heading', { name: '概念板块热力图' }).closest('section') as HTMLElement).getByRole('button', { name: '概念' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '查看板块详情 API算力' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '查看板块详情 API半导体' })).not.toBeInTheDocument();
  });

  it('shows a localized concept empty-source warning when concept daily rows are missing', async () => {
    apiMocks.fetchSectorHeatmap.mockImplementation((tradeDate: string, sectorType: 'industry' | 'concept') =>
      Promise.resolve(
        sectorType === 'concept'
          ? makeHeatmapResponse('concept', {
              trade_date: tradeDate,
              data_status: 'missing',
              warnings: ['concept sector heatmap rows are unavailable'],
              items: []
            })
          : makeHeatmapResponse('industry', { trade_date: tradeDate })
      )
    );

    renderWorkspace();

    const heatmapPanel = await screen.findByRole('heading', { name: '行业板块热力图' });
    fireEvent.click(within(heatmapPanel.closest('section') as HTMLElement).getByRole('button', { name: '概念' }));

    expect(await screen.findByRole('heading', { name: '概念板块热力图' })).toBeInTheDocument();
    expect(screen.getByText('概念板块数据表已接入，但当前暂无概念成分股/日度聚合数据。')).toBeInTheDocument();
  });

  it('keeps the market monitor stage compact when sector datasets are long', async () => {
    apiMocks.fetchSectorHeatmap.mockResolvedValueOnce(
      makeHeatmapResponse('industry', {
        items: makeManyHeatmapItems(60)
      })
    );
    apiMocks.fetchSectorFundFlow.mockResolvedValueOnce(makeManyFundFlowResponse());

    renderWorkspace();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '从上涨热力图摘要查看 行业板块1' })).toBeInTheDocument();
    });

    expect(screen.getAllByRole('button', { name: /^从上涨热力图摘要查看 / })).toHaveLength(10);
    expect(screen.getAllByRole('button', { name: /^从下跌热力图摘要查看 / })).toHaveLength(10);
    expect(screen.queryByRole('button', { name: '从上涨热力图摘要查看 行业板块21' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '从下跌热力图摘要查看 行业板块2' })).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /^查看板块详情 / })).toHaveLength(20);
    expect(screen.queryByRole('button', { name: '查看板块详情 行业板块11' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '查看板块详情 行业流出11' })).not.toBeInTheDocument();
  });

  it('keeps a lightweight emotion strip visible without showing mock market data when main requests are empty or failing', async () => {
    apiMocks.fetchMarketOverview.mockRejectedValueOnce(new Error('overview failed'));
    apiMocks.fetchSectorHeatmap.mockResolvedValueOnce(
      makeHeatmapResponse('industry', {
        data_status: 'missing',
        items: []
      })
    );
    apiMocks.fetchSectorFundFlow.mockRejectedValueOnce(new Error('fund flow failed'));

    renderWorkspace();

    expect(screen.getByText('暂无上涨板块热力图数据')).toBeInTheDocument();
    expect(screen.getByText('暂无下跌板块热力图数据')).toBeInTheDocument();
    expect(screen.getByText('暂无板块资金排行数据')).toBeInTheDocument();

    await waitFor(() => {
      expect(apiMocks.fetchMarketOverview).toHaveBeenCalledWith('2026-06-12');
      expect(apiMocks.fetchSectorHeatmap).toHaveBeenCalledWith('2026-06-12', 'industry');
      expect(apiMocks.fetchSectorFundFlow).toHaveBeenCalledWith('2026-06-12', 'industry');
      expect(apiMocks.fetchMarketMonitorEod).toHaveBeenCalledWith({ topN: 5 });
    });
    expect(screen.getByText('暂无市场总览数据')).toBeInTheDocument();
    expect(screen.queryByText('3168.44')).not.toBeInTheDocument();
    expect(screen.queryByText('15260.00亿')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '从上涨热力图摘要查看 半导体' })).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: '市场情绪状态条' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '市场情绪摘要' })).not.toBeInTheDocument();
    expect(screen.getByText('综合强度')).toBeInTheDocument();
  });

  it('skips echarts initialization when the heatmap container has no measurable size', async () => {
    renderWorkspace();

    expect(screen.getByRole('heading', { name: '行业板块热力图' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('heading', { name: '上涨板块热力图' })).toBeInTheDocument());
    expect(echartsMocks.init).not.toHaveBeenCalled();
    expect(screen.getByLabelText('兼容热力块 上涨 API半导体')).toBeInTheDocument();
    expect(screen.getByLabelText('兼容热力块 下跌 API回调')).toBeInTheDocument();
  });

  it('initializes an echarts treemap when the heatmap container can be measured', async () => {
    const chartSize = overrideChartSize(960, 360);

    try {
      renderWorkspace();

      await waitFor(() => expect(echartsMocks.init).toHaveBeenCalledTimes(2));

      const renderedOptions = echartsMocks.charts.map((chart) => chart.setOption.mock.calls.at(-1)?.[0]);
      const renderedData = renderedOptions.flatMap((option) => (Array.isArray(option?.series) ? option.series[0]?.data ?? [] : []));
      const treemapSeries = Array.isArray(renderedOptions[0]?.series) ? renderedOptions[0].series[0] : null;

      expect(treemapSeries?.type).toBe('treemap');
      expect(renderedData).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            sectorId: 'industry-api-chip',
            sectorName: 'API半导体'
          }),
          expect.objectContaining({
            sectorId: 'industry-api-down',
            sectorName: 'API回调'
          })
        ])
      );
    } finally {
      chartSize.restore();
    }
  });

  it('recovers echarts initialization after the chart container becomes measurable later', async () => {
    const chartSize = overrideChartSize(0, 0);

    try {
      renderWorkspace();

      expect(echartsMocks.init).not.toHaveBeenCalled();
      await waitFor(() => expect(resizeObserverMocks.instances).toHaveLength(2));

      chartSize.setSize(960, 360);
      resizeObserverMocks.instances[0]?.callback([], {} as ResizeObserver);
      resizeObserverMocks.instances[1]?.callback([], {} as ResizeObserver);

      await waitFor(() => expect(echartsMocks.init).toHaveBeenCalledTimes(2));
    } finally {
      chartSize.restore();
    }
  });

  it('retries echarts initialization on animation frames when WebKit does not notify ResizeObserver', async () => {
    const chartSize = overrideChartSize(0, 0);

    try {
      renderWorkspace();

      expect(echartsMocks.init).not.toHaveBeenCalled();
      await waitFor(() => expect(resizeObserverMocks.instances).toHaveLength(2));
      expect(animationFrameMocks.requestAnimationFrame).toHaveBeenCalled();

      chartSize.setSize(960, 360);
      animationFrameMocks.flushNextFrame();
      animationFrameMocks.flushNextFrame();

      await waitFor(() => expect(echartsMocks.init).toHaveBeenCalledTimes(2));
    } finally {
      chartSize.restore();
    }
  });
});
