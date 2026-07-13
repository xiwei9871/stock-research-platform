import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { StockMarketContextHeatmapPayload } from '../src/api/types';
import { StockMarketContextHeatmap } from '../src/components/stock-workspace/StockMarketContextHeatmap';

class TestResizeObserver {
  observe = vi.fn();
  disconnect = vi.fn();
}

const canvasContext = {
  clearRect: vi.fn(),
  fillRect: vi.fn(),
  strokeRect: vi.fn(),
  fillText: vi.fn(),
  measureText: vi.fn((text: string) => ({ width: text.length * 8 })),
  save: vi.fn(),
  restore: vi.fn(),
  scale: vi.fn()
};

function makePayload(overrides: Partial<StockMarketContextHeatmapPayload> = {}): StockMarketContextHeatmapPayload {
  return {
    asset_id: '000001.SZ',
    canonical_asset_id: 'CN:SZ:000001',
    trade_date: '2026-07-07',
    industry: { industry_id: 'bank', industry_name: '银行', industry_system: 'csrc' },
    selected: {
      asset_id: 'CN:SZ:000001',
      symbol: '000001',
      name: '平安银行',
      price: 12.5,
      change_pct: 0.02,
      amount: 3000000000,
      amount_rank: 1,
      change_rank: 1,
      amount_percentile: 1,
      change_percentile: 1
    },
    summary: {
      peer_count: 2,
      up_count: 1,
      flat_count: 0,
      down_count: 1,
      total_amount: 4000000000,
      selected_in_peer_set: true
    },
    peers: [
      {
        asset_id: 'CN:SZ:000001',
        symbol: '000001',
        name: '平安银行',
        price: 12.5,
        change_pct: 0.02,
        amount: 3000000000,
        value: 3000000000,
        is_selected: true
      },
      {
        asset_id: 'CN:SH:600000',
        symbol: '600000',
        name: '浦发银行',
        price: 9,
        change_pct: -0.01,
        amount: 1000000000,
        value: 1000000000,
        is_selected: false
      }
    ],
    data_status: 'completed',
    warnings: [],
    ...overrides
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  globalThis.ResizeObserver = TestResizeObserver as unknown as typeof ResizeObserver;
  Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
    configurable: true,
    value: vi.fn((contextId: string) => (contextId === '2d' ? canvasContext : null)) as unknown as HTMLCanvasElement['getContext']
  });
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, value: 460 });
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, value: 240 });
});

afterEach(() => {
  cleanup();
});

describe('StockMarketContextHeatmap', () => {
  it('renders loading and empty states', () => {
    const { rerender } = render(<StockMarketContextHeatmap payload={null} loading error={null} onSelectStock={vi.fn()} />);
    expect(screen.getByText('同业热力加载中')).toBeInTheDocument();

    rerender(
      <StockMarketContextHeatmap
        payload={makePayload({
          selected: null,
          peers: [],
          data_status: 'missing',
          summary: {
            peer_count: 0,
            up_count: 0,
            flat_count: 0,
            down_count: 0,
            total_amount: 0,
            selected_in_peer_set: false
          }
        })}
        loading={false}
        error={null}
        onSelectStock={vi.fn()}
      />
    );

    expect(screen.getByText('暂无同业市场定位数据')).toBeInTheDocument();
  });

  it('renders selected stock summary and canvas', () => {
    render(<StockMarketContextHeatmap payload={makePayload()} loading={false} error={null} onSelectStock={vi.fn()} />);

    expect(screen.getByRole('img', { name: '同业市场定位热力图' })).toBeInTheDocument();
    expect(screen.getByText('银行')).toBeInTheDocument();
    expect(screen.getByText(/同业\s*2/)).toBeInTheDocument();
    expect(screen.getByText('涨跌排名 #1')).toBeInTheDocument();
    expect(screen.getByText('成交额排名 #1')).toBeInTheDocument();
    expect(screen.getByText('热力图与样本卡片仅展示成交额靠前的 12 只同业股票。')).toBeInTheDocument();
    expect(screen.getAllByText('平安银行').length).toBeGreaterThan(0);
    expect(canvasContext.strokeRect).toHaveBeenCalled();
  });

  it('calls onSelectStock when a peer is selected', () => {
    const onSelectStock = vi.fn();
    render(<StockMarketContextHeatmap payload={makePayload()} loading={false} error={null} onSelectStock={onSelectStock} />);

    fireEvent.click(screen.getByRole('button', { name: /打开同业 浦发银行/ }));

    expect(onSelectStock).toHaveBeenCalledWith('CN:SH:600000');
  });

  it('separates peer card identity from metrics so narrow cards do not overlap text', () => {
    render(
      <StockMarketContextHeatmap
        payload={makePayload({
          peers: [
            {
              asset_id: 'CN:SH:603931',
              symbol: '603931',
              name: '格林达',
              price: 18,
              change_pct: 0.0375,
              amount: 2000000,
              value: 2000000,
              is_selected: true
            },
            {
              asset_id: 'CN:SZ:300285',
              symbol: '300285',
              name: '国瓷材料',
              price: 28,
              change_pct: 0.0294,
              amount: 9000000,
              value: 9000000,
              is_selected: false
            }
          ]
        })}
        loading={false}
        error={null}
        onSelectStock={vi.fn()}
      />
    );

    const card = screen.getByRole('button', { name: /打开同业 国瓷材料/ });
    expect(card.querySelector('.stock-market-context-peer-identity')).toHaveTextContent('国瓷材料');
    expect(card.querySelector('.stock-market-context-peer-code')).toHaveTextContent('代码 300285');
    expect(card.querySelector('.stock-market-context-peer-change')).toHaveTextContent('涨跌幅 +2.94%');
    expect(card.querySelector('.stock-market-context-peer-amount')).toHaveTextContent('成交额 0.09亿');
  });

  it('truncates canvas labels when heatmap tiles are too narrow for full stock names', () => {
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, value: 150 });
    Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, value: 120 });

    render(
      <StockMarketContextHeatmap
        payload={makePayload({
          selected: {
            asset_id: 'CN:SZ:002049',
            symbol: '002049',
            name: '紫光国微超长股票名称',
            price: 68,
            change_pct: 0.0429,
            amount: 5709000000,
            amount_rank: 1,
            change_rank: 1,
            amount_percentile: 1,
            change_percentile: 1
          },
          peers: [
            {
              asset_id: 'CN:SZ:002049',
              symbol: '002049',
              name: '紫光国微超长股票名称',
              price: 68,
              change_pct: 0.0429,
              amount: 5709000000,
              value: 5709000000,
              is_selected: true
            },
            {
              asset_id: 'CN:SZ:000063',
              symbol: '000063',
              name: '中兴通讯超长股票名称',
              price: 44,
              change_pct: 0.02,
              amount: 5709000000,
              value: 5709000000,
              is_selected: false
            }
          ]
        })}
        loading={false}
        error={null}
        onSelectStock={vi.fn()}
      />
    );

    expect(canvasContext.fillText).toHaveBeenCalledWith(expect.stringContaining('…'), expect.any(Number), expect.any(Number));
    expect(canvasContext.fillText).not.toHaveBeenCalledWith(
      '紫光国微超长股票名称',
      expect.any(Number),
      expect.any(Number)
    );
  });

  it('orders the heatmap sample by traded amount instead of stale value fields', () => {
    render(
      <StockMarketContextHeatmap
        payload={makePayload({
          selected: null,
          peers: [
            {
              asset_id: 'CN:SZ:000001',
              symbol: '000001',
              name: '低成交额高旧值',
              price: 10,
              change_pct: 0.02,
              amount: 1000000,
              value: 9000000000,
              is_selected: false
            },
            {
              asset_id: 'CN:SZ:000002',
              symbol: '000002',
              name: '高成交额低旧值',
              price: 10,
              change_pct: 0.01,
              amount: 8000000000,
              value: 1,
              is_selected: false
            }
          ]
        })}
        loading={false}
        error={null}
        onSelectStock={vi.fn()}
      />
    );

    const cards = screen.getAllByRole('button', { name: /打开同业/ });
    expect(cards[0]).toHaveAccessibleName('打开同业 高成交额低旧值');
    expect(cards[1]).toHaveAccessibleName('打开同业 低成交额高旧值');
  });

  it('does not force a low-amount selected stock into the top traded-amount heatmap sample', () => {
    const peers = Array.from({ length: 25 }, (_, index) => ({
      asset_id: `CN:SZ:${String(index + 1).padStart(6, '0')}`,
      symbol: String(index + 1).padStart(6, '0'),
      name: `成交额样本${index + 1}`,
      price: 10 + index,
      change_pct: index % 2 === 0 ? 0.02 : -0.01,
      amount: 1000000000 - index * 10000000,
      value: 1000000000 - index * 10000000,
      is_selected: false
    }));
    const selectedPeer = {
      asset_id: 'CN:SZ:999999',
      symbol: '999999',
      name: '低成交额当前股',
      price: 10,
      change_pct: 0.03,
      amount: 100000,
      value: 100000,
      is_selected: true
    };

    render(
      <StockMarketContextHeatmap
        payload={makePayload({
          selected: {
            asset_id: selectedPeer.asset_id,
            symbol: selectedPeer.symbol,
            name: selectedPeer.name,
            price: selectedPeer.price,
            change_pct: selectedPeer.change_pct,
            amount: selectedPeer.amount,
            amount_rank: 26,
            change_rank: 1,
            amount_percentile: 0.01,
            change_percentile: 1
          },
          peers: [...peers, selectedPeer]
        })}
        loading={false}
        error={null}
        onSelectStock={vi.fn()}
      />
    );

    expect(screen.getAllByRole('button', { name: /打开同业/ })).toHaveLength(12);
    expect(screen.queryByRole('button', { name: '打开同业 低成交额当前股' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('同业热力悬停信息')).toHaveTextContent('低成交额当前股');
    expect(screen.getByText('当前股票未进入成交额前 12，热力图按同业成交额前 12 展示。')).toBeInTheDocument();
  });

  it('dedupes repeated peer asset ids without duplicate key warnings', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    render(
      <StockMarketContextHeatmap
        payload={makePayload({
          peers: [
            {
              asset_id: 'CN:SZ:000001',
              symbol: '000001',
              name: '平安银行',
              price: 12.5,
              change_pct: 0.02,
              amount: 3000000000,
              value: 3000000000,
              is_selected: true
            },
            {
              asset_id: 'CN:SZ:000001',
              symbol: '000001',
              name: '平安银行',
              price: 12.5,
              change_pct: 0.02,
              amount: 3000000000,
              value: 3000000000,
              is_selected: false
            },
            {
              asset_id: 'CN:SH:600000',
              symbol: '600000',
              name: '浦发银行',
              price: 9,
              change_pct: -0.01,
              amount: 1000000000,
              value: 1000000000,
              is_selected: false
            }
          ]
        })}
        loading={false}
        error={null}
        onSelectStock={vi.fn()}
      />
    );

    expect(screen.getAllByRole('button', { name: /打开同业/ })).toHaveLength(2);
    const messages = consoleError.mock.calls.map((call) => call.join(' ')).join('\n');
    expect(messages).not.toContain('Encountered two children with the same key');
    consoleError.mockRestore();
  });

  it('renders local error state', () => {
    render(<StockMarketContextHeatmap payload={null} loading={false} error="GET failed" onSelectStock={vi.fn()} />);
    expect(screen.getByText('GET failed')).toBeInTheDocument();
  });

  it('caps the heatmap to 20 peers while keeping summary counts based on the full deduped peer universe', () => {
    const peers = Array.from({ length: 25 }, (_, index) => {
      const isPositive = index < 12;
      return {
        asset_id: `CN:SZ:${String(index + 1).padStart(6, '0')}`,
        symbol: String(index + 1).padStart(6, '0'),
        name: `样本${index + 1}`,
        price: 10 + index,
        change_pct: isPositive ? 0.02 : -0.01,
        amount: 1000000000 - index * 10000000,
        value: 1000000000 - index * 10000000,
        is_selected: index === 0
      };
    });

    render(
      <StockMarketContextHeatmap
        payload={makePayload({
          selected: {
            asset_id: peers[0].asset_id,
            symbol: peers[0].symbol,
            name: peers[0].name,
            price: peers[0].price,
            change_pct: peers[0].change_pct,
            amount: peers[0].amount,
            amount_rank: 12,
            change_rank: 16,
            amount_percentile: 0.7,
            change_percentile: 0.6
          },
          summary: {
            peer_count: 32246,
            up_count: 16573,
            flat_count: 0,
            down_count: 13755,
            total_amount: 999999999999,
            selected_in_peer_set: true
          },
          peers
        })}
        loading={false}
        error={null}
        onSelectStock={vi.fn()}
      />
    );

    expect(screen.getByText(/同业\s*25/)).toBeInTheDocument();
    expect(screen.getByText(/上涨\s*12/)).toBeInTheDocument();
    expect(screen.getByText(/下跌\s*13/)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /打开同业/ })).toHaveLength(12);
    expect(screen.queryByRole('button', { name: /打开同业 样本13/ })).not.toBeInTheDocument();
  });
});
