import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AssetChart } from '../src/charts/AssetChart';

const chartMocks = vi.hoisted(() => {
  const timeScale = {
    setVisibleLogicalRange: vi.fn(),
    fitContent: vi.fn()
  };
  const candleSeries = {
    setData: vi.fn(),
    priceScale: vi.fn(() => ({
      applyOptions: vi.fn()
    }))
  };
  const volumeSeries = {
    setData: vi.fn(),
    priceScale: vi.fn(() => ({
      applyOptions: vi.fn()
    }))
  };
  const panes = [{ setStretchFactor: vi.fn() }, { setStretchFactor: vi.fn() }];
  const chart = {
    addSeries: vi.fn((definition: string) => (definition === 'HistogramSeries' ? volumeSeries : candleSeries)),
    applyOptions: vi.fn(),
    panes: vi.fn(() => panes),
    remove: vi.fn(),
    subscribeCrosshairMove: vi.fn(),
    unsubscribeCrosshairMove: vi.fn(),
    timeScale: vi.fn(() => timeScale)
  };
  return {
    chart,
    candleSeries,
    volumeSeries,
    panes,
    timeScale,
    createChart: vi.fn(() => chart),
    createSeriesMarkers: vi.fn()
  };
});

vi.mock('lightweight-charts', () => ({
  CandlestickSeries: 'CandlestickSeries',
  HistogramSeries: 'HistogramSeries',
  createChart: chartMocks.createChart,
  createSeriesMarkers: chartMocks.createSeriesMarkers
}));

class TestResizeObserver {
  observe = vi.fn();
  disconnect = vi.fn();
}

function latestTickMarkFormatter() {
  const [, chartOptions] = chartMocks.createChart.mock.calls.at(-1) as unknown as [
    HTMLDivElement,
    { timeScale: { tickMarkFormatter: (time: string) => string } }
  ];
  return chartOptions.timeScale.tickMarkFormatter;
}

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    value: 720
  });
  globalThis.ResizeObserver = TestResizeObserver as unknown as typeof ResizeObserver;
});

afterEach(() => {
  cleanup();
});

describe('AssetChart', () => {
  it('configures the built-in time axis to avoid clipped edge labels and uneven tick density', () => {
    render(
      <AssetChart
        bars={[
          { time: '2026-06-01', open: 10, high: 11, low: 9.8, close: 10.5, volume: 100, amount: 1000 },
          { time: '2026-06-02', open: 10.5, high: 11.2, low: 10.2, close: 11, volume: 120, amount: 1300 }
        ]}
      />
    );

    expect(chartMocks.createChart).toHaveBeenCalledWith(
      expect.any(HTMLDivElement),
      expect.objectContaining({
        timeScale: expect.objectContaining({
          barSpacing: expect.any(Number),
          fixLeftEdge: true,
          minBarSpacing: expect.any(Number),
          rightOffsetPixels: 24,
          visible: false,
          uniformDistribution: true,
          ticksVisible: true
        })
      })
    );
  });

  it('renders a fixed-width time-window handle that shifts the visible logical range', async () => {
    render(
      <AssetChart
        bars={[
          { time: '2026-06-01', open: 10, high: 11, low: 9.8, close: 10.5, volume: 100, amount: 1000 },
          { time: '2026-06-02', open: 10.5, high: 11.2, low: 10.2, close: 11, volume: 120, amount: 1300 },
          { time: '2026-06-03', open: 11, high: 11.5, low: 10.8, close: 11.2, volume: 130, amount: 1450 },
          { time: '2026-06-04', open: 11.2, high: 11.8, low: 11, close: 11.6, volume: 140, amount: 1600 },
          { time: '2026-06-05', open: 11.6, high: 12, low: 11.4, close: 11.9, volume: 150, amount: 1750 }
        ]}
        visibleBarCount={3}
      />
    );

    await waitFor(() => {
      expect(chartMocks.timeScale.setVisibleLogicalRange).toHaveBeenCalledWith({ from: 2, to: 4 });
    });

    expect(screen.getByRole('group', { name: '时间窗口' })).toBeInTheDocument();
    expect(screen.getByText('2026-06-03 - 2026-06-05 / 3 bars')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: '窗口刻度' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '向左移动时间窗口' }));

    await waitFor(() => {
      expect(chartMocks.timeScale.setVisibleLogicalRange).toHaveBeenLastCalledWith({ from: 1, to: 3 });
    });
    expect(screen.getByText('2026-06-02 - 2026-06-04 / 3 bars')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('拖动时间窗口'), { target: { value: '0' } });

    await waitFor(() => {
      expect(chartMocks.timeScale.setVisibleLogicalRange).toHaveBeenLastCalledWith({ from: 0, to: 2 });
    });
    expect(screen.getByText('2026-06-01 - 2026-06-03 / 3 bars')).toBeInTheDocument();
  });

  it('renders a window strip without a second set of date ticks', () => {
    render(
      <AssetChart
        bars={[
          { time: '2026-06-01', open: 10, high: 11, low: 9.8, close: 10.5, volume: 100, amount: 1000 },
          { time: '2026-06-02', open: 10.5, high: 11.2, low: 10.2, close: 11, volume: 120, amount: 1300 },
          { time: '2026-06-03', open: 11, high: 11.5, low: 10.8, close: 11.2, volume: 130, amount: 1450 },
          { time: '2026-06-04', open: 11.2, high: 11.8, low: 11, close: 11.6, volume: 140, amount: 1600 },
          { time: '2026-06-05', open: 11.6, high: 12, low: 11.4, close: 11.9, volume: 150, amount: 1750 }
        ]}
        visibleBarCount={5}
      />
    );

    expect(screen.getByRole('group', { name: '时间窗口' })).toHaveTextContent('2026-06-01 - 2026-06-05 / 5 bars');
    expect(screen.getByRole('slider', { name: '拖动时间窗口' })).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: '窗口刻度' })).not.toBeInTheDocument();
  });

  it('renders one evenly distributed readable horizontal axis for the fixed weekly window', () => {
    const weeklyBars = Array.from({ length: 120 }, (_, index) => {
      const date = new Date(Date.UTC(2024, 2, 15 + index * 7));
      return {
        time: date.toISOString().slice(0, 10),
        open: 10,
        high: 11,
        low: 9,
        close: 10.5,
        volume: 100,
        amount: 1000
      };
    });

    render(<AssetChart bars={weeklyBars} timeAxisPeriod="1W" visibleBarCount={120} />);

    const axis = screen.getByRole('list', { name: '横轴刻度' });
    const labels = within(axis).getAllByRole('listitem').map((item) => item.textContent);

    expect(labels).toHaveLength(6);
    expect(labels[0]).toBe('24-03');
    expect(labels.at(-1)).toBe('26-06');
    expect(screen.queryByRole('list', { name: '窗口刻度' })).not.toBeInTheDocument();
  });

  it('formats weekly axis ticks with compact year-month labels so more ticks fit without losing the year', () => {
    render(
      <AssetChart
        bars={[
          { time: '2025-12-26', open: 10, high: 11, low: 9.8, close: 10.5, volume: 100, amount: 1000 },
          { time: '2026-01-02', open: 10.5, high: 11.2, low: 10.2, close: 11, volume: 120, amount: 1300 }
        ]}
        timeAxisPeriod="1W"
      />
    );

    const formatter = latestTickMarkFormatter();

    expect(formatter('2025-12-26')).toBe('25-12');
    expect(formatter('2026-01-02')).toBe('26-01');
  });

  it('formats daily axis ticks with compact year-month labels instead of ambiguous month-day labels', () => {
    render(
      <AssetChart
        bars={[
          { time: '2026-06-01', open: 10, high: 11, low: 9.8, close: 10.5, volume: 100, amount: 1000 },
          { time: '2026-07-01', open: 10.5, high: 11.2, low: 10.2, close: 11, volume: 120, amount: 1300 }
        ]}
        timeAxisPeriod="1D"
      />
    );

    const formatter = latestTickMarkFormatter();

    expect(formatter('2026-06-01')).toBe('26-06');
    expect(formatter('2026-07-01')).toBe('26-07');
  });

  it('formats monthly axis and range labels by year-month instead of month-day', () => {
    render(
      <AssetChart
        bars={[
          { time: '2025-11-28', open: 10, high: 11, low: 9.8, close: 10.5, volume: 100, amount: 1000 },
          { time: '2025-12-31', open: 10.5, high: 11.2, low: 10.2, close: 11, volume: 120, amount: 1300 },
          { time: '2026-01-30', open: 11, high: 11.5, low: 10.8, close: 11.2, volume: 130, amount: 1450 },
          { time: '2026-02-27', open: 11.2, high: 11.8, low: 11, close: 11.6, volume: 140, amount: 1600 }
        ]}
        timeAxisPeriod="1M"
        visibleBarCount={4}
      />
    );

    const formatter = latestTickMarkFormatter();

    expect(formatter('2026-01-30')).toBe('2026');
    expect(formatter('2026-02-27')).toBe('26-02');
    expect(screen.getByRole('group', { name: '时间窗口' })).toHaveTextContent('2025-11 - 2026-02 / 4 bars');
    expect(screen.queryByRole('list', { name: '窗口刻度' })).not.toBeInTheDocument();
  });

  it('puts volume bars in a separate lower pane aligned to the same time scale', () => {
    render(
      <AssetChart
        bars={[
          { time: '2026-06-01', open: 10, high: 11, low: 9.8, close: 10.5, volume: 100, amount: 1000 },
          { time: '2026-06-02', open: 10.5, high: 11.2, low: 10.2, close: 11, volume: 120, amount: 1300 }
        ]}
      />
    );

    expect(chartMocks.chart.addSeries).toHaveBeenCalledWith(
      'HistogramSeries',
      expect.objectContaining({
        lastValueVisible: false,
        priceLineVisible: false,
        priceScaleId: 'right'
      }),
      1
    );
    expect(chartMocks.panes[0].setStretchFactor).toHaveBeenCalledWith(4);
    expect(chartMocks.panes[1].setStretchFactor).toHaveBeenCalledWith(1);
  });

  it('shows OHLCV and turnover details in a chart tooltip when hovering a bar', () => {
    render(
      <AssetChart
        bars={[
          { time: '2026-06-01', open: 10, high: 11, low: 9.8, close: 10.5, volume: 100000, amount: 1050000 }
        ]}
      />
    );

    const handler = chartMocks.chart.subscribeCrosshairMove.mock.calls.at(-1)?.[0] as
      | ((param: {
          time?: string;
          point?: { x: number; y: number };
          seriesData: Map<object, object>;
        }) => void)
      | undefined;
    expect(handler).toBeDefined();

    act(() => {
      handler?.({
        time: '2026-06-01',
        point: { x: 240, y: 120 },
        seriesData: new Map<object, object>([
          [chartMocks.candleSeries, { open: 10, high: 11, low: 9.8, close: 10.5 }],
          [chartMocks.volumeSeries, { value: 100000 }]
        ])
      });
    });

    expect(screen.getByRole('tooltip', { name: 'K线数据' })).toHaveTextContent('2026-06-01');
    expect(screen.getByRole('tooltip', { name: 'K线数据' })).toHaveTextContent('开 10');
    expect(screen.getByRole('tooltip', { name: 'K线数据' })).toHaveTextContent('高 11');
    expect(screen.getByRole('tooltip', { name: 'K线数据' })).toHaveTextContent('低 9.8');
    expect(screen.getByRole('tooltip', { name: 'K线数据' })).toHaveTextContent('收 10.5');
    expect(screen.getByRole('tooltip', { name: 'K线数据' })).toHaveTextContent('量 10.00万');
    expect(screen.getByRole('tooltip', { name: 'K线数据' })).toHaveTextContent('额 105.00万');
  });
});
