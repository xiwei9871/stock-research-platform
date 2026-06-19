import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MarketMonitorWorkspace } from '../src/components/MarketMonitorWorkspace';
import type { MarketMonitorPayload } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchMarketMonitorEod: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

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
      limit_up: [
        {
          name: '贵州茅台',
          asset_id: 'CN:SH:600519',
          symbol: '600519',
          amount: 1200000000,
          pct_chg: 10,
          board: '白酒',
          tab: 'limit_up',
          limit_up_streak: 1
        }
      ],
      broken_limit_up: [],
      limit_down: []
    },
    warnings: [],
    ...overrides
  };
}

describe('MarketMonitorWorkspace', () => {
  beforeEach(() => {
    apiMocks.fetchMarketMonitorEod.mockResolvedValue(makeMarketMonitorPayload());
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('opens stock detail from an EOD stock row with market context', async () => {
    const onOpenAsset = vi.fn();

    render(<MarketMonitorWorkspace onOpenAsset={onOpenAsset} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Open Stock Detail for 贵州茅台 from 涨停' }));

    expect(onOpenAsset).toHaveBeenCalledWith('CN:SH:600519', {
      sourceWorkspace: 'market',
      assetId: 'CN:SH:600519',
      tradeDate: '2026-06-12',
      monitorTab: 'limit_up',
      query: '贵州茅台'
    });
  });

  it('restores the initial date and tab', async () => {
    render(<MarketMonitorWorkspace initialTradeDate="2026-06-11" initialMonitorTab="broken_limit_up" />);

    await waitFor(() => expect(apiMocks.fetchMarketMonitorEod).toHaveBeenCalledWith({ topN: 5, tradeDate: '2026-06-11' }));
    expect(screen.getByRole('tab', { name: /炸板/ })).toHaveAttribute('aria-selected', 'true');
  });

  it('explains stock list pending and empty states without implying market emotion is missing', async () => {
    apiMocks.fetchMarketMonitorEod.mockResolvedValueOnce(
      makeMarketMonitorPayload({
        emotion_stock_lists: {
          auction_status: 'pending_source',
          auction: [],
          limit_up: [],
          broken_limit_up: [],
          limit_down: []
        }
      })
    );

    render(<MarketMonitorWorkspace />);

    expect(await screen.findByText('综合强度')).toBeInTheDocument();
    expect(screen.getByText('股票名单源未接入或当日未产出；上方市场情绪指标仍可用于判断市场热度。')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /涨停 0/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('当前日期暂无涨停股票。')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: /竞价 0/ }));
    expect(screen.getByText('竞价数据源未接入。')).toBeInTheDocument();
  });
});
