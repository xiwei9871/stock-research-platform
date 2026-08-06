import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { KronosPredictionPanel } from '../src/components/stock-workspace/KronosPredictionPanel';

const apiMocks = vi.hoisted(() => ({
  createKronosPrediction: vi.fn(),
  fetchKronosRun: vi.fn(),
  fetchLatestKronosPrediction: vi.fn()
}));

vi.mock('../src/api/kronos', () => apiMocks);

vi.mock('../src/components/stock-workspace/KronosPredictionChart', () => ({
  KronosPredictionChart: () => <div data-testid="kronos-prediction-chart" />
}));

function makeRun() {
  return {
    run_id: 'run-1',
    code: '600418',
    status: 'succeeded' as const,
    created_at: '2026-08-06T00:00:00Z',
    updated_at: '2026-08-06T00:00:01Z',
    snapshot: { data_as_of: '2026-08-05 15:00:00' },
    periods: { daily: { status: 'succeeded' } },
    result: {
      status: 'succeeded',
      sample_count: 20,
      daily: {
        representative_path: [
          { timestamp: '2026-08-06', open: 10, high: 11, low: 9, close: 10.5 }
        ]
      },
      intraday: null,
      aggregated: {}
    }
  };
}

describe('KronosPredictionPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.fetchLatestKronosPrediction.mockRejectedValue(new Error('no cached prediction'));
    apiMocks.createKronosPrediction.mockResolvedValue(makeRun());
  });

  afterEach(() => {
    cleanup();
  });

  it('uses an existing completed prediction instead of starting a new run', async () => {
    const cachedRun = makeRun();
    apiMocks.fetchLatestKronosPrediction.mockResolvedValue(cachedRun);

    render(<KronosPredictionPanel assetId="CN:SH:600418" />);

    expect(await screen.findByText('已完成')).toBeInTheDocument();
    expect(apiMocks.fetchLatestKronosPrediction).toHaveBeenCalledWith('600418');
    expect(apiMocks.createKronosPrediction).not.toHaveBeenCalled();
  });

  it('automatically submits the six-digit stock code and renders the completed prediction', async () => {
    const onDailyForecastChange = vi.fn();
    render(
      <KronosPredictionPanel
        assetId="CN:SH:600418"
        historyBars={[{ time: '2026-08-05', open: 9, high: 10, low: 8.5, close: 9.5, volume: 1, amount: 2 }]}
        onDailyForecastChange={onDailyForecastChange}
        showHistory
      />
    );

    expect(await screen.findByText('已完成')).toBeInTheDocument();
    expect(screen.getByText('数据截至 2026-08-05 15:00:00 · 20条采样路径')).toBeInTheDocument();
    expect(screen.getByTestId('kronos-prediction-chart')).toBeInTheDocument();
    expect(apiMocks.createKronosPrediction).toHaveBeenCalledWith('600418', { force: false });
    expect(onDailyForecastChange).toHaveBeenLastCalledWith(makeRun().result.daily);
  });

  it('shows a clear diagnostic when the asset is not an A-share code', async () => {
    render(<KronosPredictionPanel assetId="US:AAPL" />);

    await waitFor(() => expect(screen.getByText('Kronos预测目前仅支持6位A股代码')).toBeInTheDocument());
    expect(apiMocks.createKronosPrediction).not.toHaveBeenCalled();
  });
});
