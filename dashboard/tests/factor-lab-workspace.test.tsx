import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppShell } from '../src/components/AppShell';
import { FactorLabWorkspace } from '../src/components/FactorLabWorkspace';
import type { FactorLibraryRow, FactorScorePreview } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchFactorLibrary: vi.fn(),
  fetchFactorScorePreview: vi.fn(),
  fetchPlatformSummary: vi.fn(),
  fetchStrategyCatalog: vi.fn(),
  fetchBacktestStrategies: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

vi.mock('../src/charts/AssetChart', () => ({
  AssetChart: ({ bars }: { bars: unknown[] }) => <div data-testid="asset-chart">{bars.length} bars</div>
}));

function makeLibrary(): FactorLibraryRow[] {
  return [
    {
      factor_name: 'ret_20',
      factor_group: 'momentum',
      direction: 'higher',
      description: '20 day return',
      source: 'daily_bars',
      calc_version: 'v1',
      status: 'active',
      availability_start_date: '2020-01-01',
      availability_reason: null,
      latest_available_date: '2026-06-08',
      coverage_count: 5120,
      used_in_manual_v1: true,
      manual_v1_weight: 1
    },
    {
      factor_name: 'volatility_20',
      factor_group: 'risk',
      direction: 'lower',
      description: '20 day realized volatility',
      source: 'daily_bars',
      calc_version: 'v1',
      status: 'active',
      availability_start_date: '2020-01-01',
      availability_reason: null,
      latest_available_date: '2026-06-08',
      coverage_count: 5110,
      used_in_manual_v1: false,
      manual_v1_weight: null
    }
  ];
}

function makePreview(): FactorScorePreview {
  return {
    trade_date: '2026-06-08',
    selected_factors: [{ factor_name: 'ret_20', direction: 'higher', weight: 1 }],
    items: [
      {
        trade_date: '2026-06-08',
        asset_id: 'CN:SZ:300951',
        rank: 1,
        score_total: 98.25,
        score_components: { ret_20: 0.82 }
      }
    ]
  };
}

function deferredPreview() {
  let resolve!: (preview: FactorScorePreview) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<FactorScorePreview>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

describe('FactorLabWorkspace', () => {
  beforeEach(() => {
    apiMocks.fetchFactorLibrary.mockResolvedValue(makeLibrary());
    apiMocks.fetchFactorScorePreview.mockResolvedValue(makePreview());
    apiMocks.fetchPlatformSummary.mockResolvedValue({
      latest_market_date: '2026-06-08',
      latest_factor_date: '2026-06-08',
      latest_score_date: '2026-06-08',
      market_asset_count: 1,
      score_asset_count: 1,
      factor_count: 2,
      score_versions: ['manual_v1'],
      topn_preview: []
    });
    apiMocks.fetchStrategyCatalog.mockResolvedValue([]);
    apiMocks.fetchBacktestStrategies.mockResolvedValue([
      {
        strategy_id: 'lhb_shortline',
        strategy_name: 'LHB Shortline Combo',
        status: 'runnable',
        description: 'LHB combo',
        factor_groups: ['资金行为'],
        signal_inputs: ['龙虎榜'],
        default_parameters: { top_n: 20 },
        latest_evidence: '',
        primary_action: 'Run backtest'
      }
    ]);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('loads factors, previews selected score rankings, and uses default preview inputs', async () => {
    render(<FactorLabWorkspace />);

    expect(screen.getByRole('heading', { name: 'Factor Lab' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Preview Scores' })).toBeDisabled();

    await waitFor(() => expect(screen.getByRole('cell', { name: 'ret_20' })).toBeInTheDocument());
    const ret20Row = screen.getByRole('row', { name: /ret_20/ });
    expect(within(ret20Row).getByRole('cell', { name: 'momentum' })).toBeInTheDocument();
    expect(within(ret20Row).getByRole('cell', { name: 'active' })).toBeInTheDocument();
    expect(within(ret20Row).getByRole('cell', { name: 'higher' })).toBeInTheDocument();
    expect(within(ret20Row).getByText('Manual V1')).toBeInTheDocument();
    expect(within(ret20Row).getByText('Weight 1')).toBeInTheDocument();
    expect(within(ret20Row).getByRole('cell', { name: '2026-06-08' })).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('select ret_20'));
    fireEvent.click(screen.getByRole('button', { name: 'Preview Scores' }));

    await waitFor(() =>
      expect(apiMocks.fetchFactorScorePreview).toHaveBeenCalledWith(
        '2026-06-08',
        [{ factor_name: 'ret_20', direction: 'higher', weight: 1 }],
        30
      )
    );
    expect(await screen.findByRole('cell', { name: 'CN:SZ:300951' })).toBeInTheDocument();
    const previewRow = screen.getByRole('row', { name: /CN:SZ:300951/ });
    expect(within(previewRow).getByRole('cell', { name: '1' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '98.25' })).toBeInTheDocument();
  });

  it('keeps preview disabled until a factor is selected', async () => {
    render(<FactorLabWorkspace />);

    const previewButton = screen.getByRole('button', { name: 'Preview Scores' });
    expect(previewButton).toBeDisabled();

    await screen.findByRole('cell', { name: 'ret_20' });
    expect(previewButton).toBeDisabled();

    fireEvent.click(screen.getByLabelText('select ret_20'));
    expect(previewButton).toBeEnabled();
  });

  it('disables preview for non-positive selected weights', async () => {
    render(<FactorLabWorkspace />);
    await screen.findByRole('cell', { name: 'ret_20' });

    fireEvent.click(screen.getByLabelText('select ret_20'));
    fireEvent.change(screen.getByLabelText('ret_20 weight'), { target: { value: '-1' } });

    expect(screen.getByRole('button', { name: 'Preview Scores' })).toBeDisabled();
    expect(apiMocks.fetchFactorScorePreview).not.toHaveBeenCalled();
  });

  it('ignores pending preview responses after selected factors change', async () => {
    const pendingPreview = deferredPreview();
    apiMocks.fetchFactorScorePreview.mockReturnValueOnce(pendingPreview.promise);

    render(<FactorLabWorkspace />);
    await screen.findByRole('cell', { name: 'ret_20' });

    fireEvent.click(screen.getByLabelText('select ret_20'));
    fireEvent.click(screen.getByRole('button', { name: 'Preview Scores' }));
    fireEvent.click(screen.getByLabelText('select ret_20'));

    await act(async () => {
      pendingPreview.resolve(makePreview());
    });

    expect(screen.queryByRole('cell', { name: 'CN:SZ:300951' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Preview Scores' })).toBeDisabled();
  });

  it('opens Factor Lab from AppShell side navigation', async () => {
    render(<AppShell />);

    const navigation = within(screen.getByRole('complementary', { name: 'Workspace navigation' }));
    fireEvent.click(navigation.getByRole('button', { name: 'Open Factor Lab workspace' }));

    expect(await screen.findByRole('heading', { name: 'Factor Lab' })).toBeInTheDocument();
    expect(await screen.findByRole('cell', { name: 'ret_20' })).toBeInTheDocument();
  });

  it('shows library load errors', async () => {
    apiMocks.fetchFactorLibrary.mockRejectedValueOnce(new Error('library failed'));

    render(<FactorLabWorkspace />);

    expect(await screen.findByText('library failed')).toBeInTheDocument();
  });
});
