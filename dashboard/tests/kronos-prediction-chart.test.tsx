import '@testing-library/jest-dom/vitest';
import { render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { KronosPredictionChart } from '../src/components/stock-workspace/KronosPredictionChart';

const chartMocks = vi.hoisted(() => ({
  init: vi.fn()
}));

vi.mock('echarts', () => ({
  init: chartMocks.init
}));

function makeChart() {
  return {
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn()
  };
}

describe('KronosPredictionChart', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chartMocks.init.mockImplementation(() => makeChart());
  });

  it('uses ECharts-compatible empty points for candlestick gaps', async () => {
    render(
      <KronosPredictionChart
        historyBars={[{ time: '2026-08-05', open: 9, high: 10, low: 8.5, close: 9.5, volume: 1000, amount: 9000 }]}
        forecast={{
          representative_path: [{ timestamp: '2026-08-06', open: 10, high: 11, low: 9, close: 10.5, volume: 1100, amount: 11000 }]
        }}
        overlayHistory
      />
    );

    await waitFor(() => expect(chartMocks.init).toHaveBeenCalledTimes(1));
    const chart = chartMocks.init.mock.results[0]?.value as ReturnType<typeof makeChart>;
    const option = chart.setOption.mock.calls[0]?.[0];
    const candlestickSeries = option.series.filter((series: { type: string }) => series.type === 'candlestick');

    expect(candlestickSeries).toHaveLength(2);
    expect(candlestickSeries.flatMap((series: { data: unknown[] }) => series.data)).not.toContain(null);
  });
});
