import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { DailyReviewLiteResponse } from '../src/api/types';
import { DailyReviewLitePage } from '../src/pages/DailyReviewLitePage';

const apiMocks = vi.hoisted(() => ({
  fetchDailyReviewLite: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

function makeResponse(): DailyReviewLiteResponse {
  return {
    trade_date: '2026-06-20',
    state: 'ready',
    selected_run: {
      run_id: 'daily_review_v1:2026-06-20:abc123',
      report_type: 'daily_review_v1',
      status: 'success',
      updated_at: '2026-06-20T22:00:00Z',
      source: 'report_run',
      artifact_health: 'healthy',
      artifact_health_detail: {
        daily_review_json: 'healthy'
      }
    },
    summary: {
      market_status: 'neutral',
      overall_position_bias: 'balanced',
      lhb_conclusion: 'observe',
      mid_trend_conclusion: 'hold',
      technical_bottleneck_conclusion: 'watch',
      must_review_asset_ids: [],
      warning_count: 0
    },
    warnings: [],
    missing_sources: [],
    sections: {
      data_readiness: {
        status: 'success',
        warnings: [],
        sources: {}
      },
      market_review: {
        status: 'success',
        warnings: [],
        payload: {}
      },
      strategy_summaries: {
        lhb: {
          strategy_id: 'lhb',
          status: 'success',
          warnings: [],
          summary: {},
          top_items: []
        },
        mid_trend: {
          strategy_id: 'mid_trend',
          status: 'success',
          warnings: [],
          summary: {},
          top_items: []
        },
        technical_bottleneck: {
          strategy_id: 'technical_bottleneck',
          status: 'success',
          warnings: [],
          summary: {},
          top_items: []
        }
      },
      holding_review: {
        status: 'empty',
        warnings: [],
        items: []
      },
      operator_plan: {
        status: 'success',
        warnings: [],
        payload: {}
      },
      next_day_checklist: {
        status: 'success',
        warnings: [],
        must_review_items: [],
        forbidden_actions: [],
        data_warnings: []
      }
    },
    artifacts: []
  };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('DailyReviewLitePage', () => {
  it('renders the ready-state shell after loading the default trade date', async () => {
    const request = createDeferred<DailyReviewLiteResponse>();
    apiMocks.fetchDailyReviewLite.mockReturnValueOnce(request.promise);

    render(<DailyReviewLitePage />);

    expect(screen.getByText('Loading Daily Review Lite...')).toBeInTheDocument();
    expect(apiMocks.fetchDailyReviewLite).toHaveBeenCalledWith('2026-06-20', undefined);

    request.resolve(makeResponse());

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Daily Review Lite' })).toBeInTheDocument();
    });

    expect(
      screen.getByText('Structured read-only review of the Daily Review v1 report package')
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Trade Date')).toHaveValue('2026-06-20');
    expect(screen.getByText('Loaded from report.run')).toBeInTheDocument();
    expect(screen.getByText('daily_review_v1:2026-06-20:abc123')).toBeInTheDocument();
  });
});
