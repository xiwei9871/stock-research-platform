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
      {
        key: 'theme_research',
        title: 'Theme Research',
        status: 'ready',
        items: [
          { label: '已审核主题', value: '1' },
          { label: '映射公司', value: '2' },
          { label: '近期审核更新', value: '1' },
          { label: '证据缺口', value: '15' },
          { label: '未完成证据轨道', value: 'humanoid_robotics_source_pack_v1' }
        ]
      },
      { key: 'holding_review', title: 'Holding Review', status: 'empty', items: [] },
      { key: 'operator_plan', title: 'Operator Plan', status: 'empty', items: [] },
      { key: 'next_day_checklist', title: 'Next-day Checklist', status: 'empty', items: [] },
      { key: 'artifacts', title: 'Artifacts', status: 'empty', items: [] }
    ],
    artifacts: [],
    theme_research: {
      trade_date: '2026-06-18',
      status: 'ready',
      reviewed_theme_count: 1,
      mapped_company_count: 2,
      reviewed_mapping_count: 2,
      recent_reviewed_update_count: 1,
      evidence_gap_count: 15,
      incomplete_evidence_tracks: ['humanoid_robotics_source_pack_v1'],
      mapped_companies: [
        {
          company_code: '002837.SZ',
          company_name: '英维克',
          theme_id: 'ai_power_value_capture_v1',
          theme_name: 'AI供电产业链',
          node_id: 'liquid_cooling',
          node_name: '液冷',
          company_research_priority_score: 78.8,
          stock_workspace_path: '/tech-bottleneck/stock/002837.SZ?source=theme_research',
          theme_dashboard_path: '/theme-research/ai_power_value_capture_v1'
        },
        {
          company_code: '300274.SZ',
          company_name: '阳光电源',
          theme_id: 'ai_power_value_capture_v1',
          theme_name: 'AI供电产业链',
          node_id: 'ups',
          node_name: 'UPS',
          company_research_priority_score: 76.2,
          stock_workspace_path: '/tech-bottleneck/stock/300274.SZ?source=theme_research',
          theme_dashboard_path: '/theme-research/ai_power_value_capture_v1'
        }
      ],
      recent_updates: [
        {
          update_id: 'review-1',
          theme_id: 'ai_power_value_capture_v1',
          object_type: 'claim',
          object_id: 'claim-1',
          from_status: 'draft',
          to_status: 'reviewed',
          decision: 'accept',
          summary: '完成公开证据复核',
          created_at: '2026-06-18T10:00:00+08:00'
        }
      ],
      research_only: true,
      used_for_signal: false,
      used_for_admission: false,
      source: 'research.theme_research_company_mapping',
      warnings: []
    },
    warnings: ['no registered daily review run selected']
  });
});

afterEach(() => {
  cleanup();
});

describe('DailyReviewLiteWorkspace', () => {
  it('does not request or substitute today while the initial date is unresolved', async () => {
    render(<DailyReviewLiteWorkspace />);

    expect(screen.getByLabelText('daily review trade date')).toHaveValue('');
    await waitFor(() => expect(apiMocks.fetchDailyReviewLite).not.toHaveBeenCalled());
  });

  it('uses the backend default endpoint when the resolved display date is empty', async () => {
    render(<DailyReviewLiteWorkspace initialTradeDate="" />);

    await waitFor(() => expect(apiMocks.fetchDailyReviewLite).toHaveBeenCalledWith({}));
    expect(screen.getByLabelText('daily review trade date')).toHaveValue('');
  });

  it('synchronizes a resolved date becoming blocked empty without retaining the old date', async () => {
    const { rerender } = render(<DailyReviewLiteWorkspace initialTradeDate="2026-06-20" />);

    await waitFor(() => {
      expect(apiMocks.fetchDailyReviewLite).toHaveBeenCalledWith({ tradeDate: '2026-06-20' });
    });
    apiMocks.fetchDailyReviewLite.mockClear();

    rerender(<DailyReviewLiteWorkspace initialTradeDate="" />);

    await waitFor(() => expect(apiMocks.fetchDailyReviewLite).toHaveBeenCalledWith({}));
    expect(screen.getByLabelText('daily review trade date')).toHaveValue('');
    expect(apiMocks.fetchDailyReviewLite).not.toHaveBeenCalledWith({ tradeDate: '2026-06-20' });
  });

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
      'Theme Research',
      'Holding Review',
      'Operator Plan',
      'Next-day Checklist',
      'Artifacts'
    ]) {
      expect(screen.getByRole('heading', { name: title })).toBeInTheDocument();
    }
    expect(screen.getAllByRole('link', { name: 'AI供电产业链主题详情' })).toHaveLength(2);
    for (const link of screen.getAllByRole('link', { name: 'AI供电产业链主题详情' })) {
      expect(link).toHaveAttribute('href', '/theme-research/ai_power_value_capture_v1');
    }
    expect(screen.getByText('英维克 · 液冷')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '打开英维克个股工作台' })).toHaveAttribute(
      'href',
      '/tech-bottleneck/stock/002837.SZ?source=theme_research'
    );
    expect(screen.getByRole('link', { name: '打开阳光电源个股工作台' })).toHaveAttribute(
      'href',
      '/tech-bottleneck/stock/300274.SZ?source=theme_research'
    );
    expect(screen.getByText('完成公开证据复核')).toBeInTheDocument();
    expect(screen.getByText('仅用于研究，不参与信号或准入')).toBeInTheDocument();
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
