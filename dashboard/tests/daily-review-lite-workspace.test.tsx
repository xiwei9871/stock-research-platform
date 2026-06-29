import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DailyReviewLiteWorkspace } from '../src/components/DailyReviewLiteWorkspace';

const apiMocks = vi.hoisted(() => ({
  fetchDailyReviewLite: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.fetchDailyReviewLite.mockResolvedValue({
    trade_date: '2026-06-18',
    status: 'partial',
    run: {
      run_id: '',
      source: 'fallback',
      report_type: 'daily_review_lite',
      status: ''
    },
    fallback: true,
    sections: [
      { key: 'data_readiness', title: 'Data Readiness', status: 'ready', items: [{ label: '市场日期', value: '2026-06-18' }] },
      { key: 'market_review', title: 'Market Review', status: 'ready', items: [{ label: '上涨/下跌', value: '2494 / 2388' }] },
      { key: 'strategy_summaries', title: 'Strategy Summaries', status: 'partial', items: [{ label: 'LHB', value: '3 只' }] },
      { key: 'holding_review', title: 'Holding Review', status: 'empty', items: [] },
      { key: 'operator_plan', title: 'Operator Plan', status: 'empty', items: [] },
      { key: 'next_day_checklist', title: 'Next-day Checklist', status: 'empty', items: [] },
      { key: 'artifacts', title: 'Artifacts', status: 'empty', items: [] }
    ],
    artifacts: [],
    warnings: ['no registered daily review run selected']
  });
});

afterEach(() => {
  cleanup();
});

describe('DailyReviewLiteWorkspace', () => {
  it('renders the independent daily review report structure', async () => {
    render(<DailyReviewLiteWorkspace initialTradeDate="2026-06-18" />);

    expect(await screen.findByRole('heading', { name: '每日复盘' })).toBeInTheDocument();
    expect(screen.getByLabelText('daily review trade date')).toHaveValue('2026-06-18');
    expect(screen.getByText('fallback')).toBeInTheDocument();
    expect(screen.getByText('no registered daily review run selected')).toBeInTheDocument();
    for (const title of [
      'Data Readiness',
      'Market Review',
      'Strategy Summaries',
      'Holding Review',
      'Operator Plan',
      'Next-day Checklist',
      'Artifacts'
    ]) {
      expect(screen.getByRole('heading', { name: title })).toBeInTheDocument();
    }
  });

  it('reloads the report when the review date changes', async () => {
    render(<DailyReviewLiteWorkspace initialTradeDate="2026-06-18" />);

    await screen.findByRole('heading', { name: '每日复盘' });
    fireEvent.change(screen.getByLabelText('daily review trade date'), { target: { value: '2026-06-17' } });

    await waitFor(() => {
      expect(apiMocks.fetchDailyReviewLite).toHaveBeenLastCalledWith({ tradeDate: '2026-06-17' });
    });
  });
});
