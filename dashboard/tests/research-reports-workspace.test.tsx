import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ResearchReportsWorkspace } from '../src/components/ResearchReportsWorkspace';
import type { ResearchReportItem } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchResearchReportSummary: vi.fn(),
  fetchResearchReports: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

function makeReport(overrides: Partial<ResearchReportItem> = {}): ResearchReportItem {
  return {
    report_id: 'r1',
    asset_id: 'CN:SH:600519',
    ts_code: '600519.SH',
    stock_name: '贵州茅台',
    industry_name: '白酒',
    report_title: '贵州茅台深度报告',
    publish_date: '2026-06-03',
    report_date: '2026-06-03',
    broker: '华泰证券',
    analyst: '张三',
    rating: '买入',
    rating_change: '维持',
    target_price: 1900,
    target_upside: 0.15,
    source_type: 'public_web_search_result',
    source_name: 'cfi_ybyl',
    source_confidence: 0.8,
    public_access: true,
    copyright_note: 'metadata only',
    source_url: 'https://example.com/r1',
    raw_summary: 'summary',
    company_view: 'company view',
    industry_view: 'industry view',
    risk_summary: 'risk',
    metadata: {},
    ...overrides
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.fetchResearchReportSummary.mockResolvedValue({
    total_reports: 57418,
    covered_stocks: 3367,
    latest_publish_date: '2026-06-03',
    latest_feature_date: '2026-06-02',
    source_count: 6,
    source_counts: [{ source_name: 'cfi_ybyl', rows: 29228 }],
    rating_counts: [{ rating: '买入', rows: 10065 }],
    broker_counts: [{ broker: '华泰证券', rows: 1041 }]
  });
  apiMocks.fetchResearchReports.mockResolvedValue({
    items: [makeReport()],
    total: 1,
    limit: 50,
    offset: 0,
    warnings: []
  });
});

afterEach(() => {
  cleanup();
});

describe('ResearchReportsWorkspace', () => {
  it('loads summary and report rows', async () => {
    render(<ResearchReportsWorkspace />);

    expect(await screen.findByText('57,418')).toBeInTheDocument();
    expect(await screen.findByText('贵州茅台深度报告')).toBeInTheDocument();
    expect(screen.getByText('华泰证券')).toBeInTheDocument();
    expect(screen.getByText('买入')).toBeInTheDocument();
  });

  it('submits filters to the API', async () => {
    render(<ResearchReportsWorkspace />);

    await screen.findByText('贵州茅台深度报告');
    fireEvent.change(screen.getByLabelText('research report query'), { target: { value: '茅台' } });
    fireEvent.change(screen.getByLabelText('research report broker'), { target: { value: '华泰' } });
    fireEvent.change(screen.getByLabelText('research report rating'), { target: { value: '买入' } });
    fireEvent.change(screen.getByLabelText('research report source'), { target: { value: 'cfi_ybyl' } });
    fireEvent.change(screen.getByLabelText('research report start date'), { target: { value: '2026-04-01' } });
    fireEvent.change(screen.getByLabelText('research report end date'), { target: { value: '2026-06-01' } });
    fireEvent.click(screen.getByLabelText('research report has target price'));
    fireEvent.click(screen.getByRole('button', { name: 'Search Reports' }));

    await waitFor(() => {
      expect(apiMocks.fetchResearchReports).toHaveBeenLastCalledWith(
        expect.objectContaining({
          q: '茅台',
          broker: '华泰',
          rating: '买入',
          source_name: 'cfi_ybyl',
          start_date: '2026-04-01',
          end_date: '2026-06-01',
          limit: 50,
          offset: 0,
          has_target_price: true
        })
      );
    });
  });

  it('omits has_target_price when the target checkbox is unchecked', async () => {
    render(<ResearchReportsWorkspace />);

    await screen.findByText('贵州茅台深度报告');
    fireEvent.click(screen.getByRole('button', { name: 'Search Reports' }));

    await waitFor(() => {
      const lastCall = apiMocks.fetchResearchReports.mock.calls.at(-1);
      expect(lastCall).toBeDefined();
      expect(lastCall?.[0].has_target_price).toBeUndefined();
    });
  });

  it('opens report details from a selected row', async () => {
    render(<ResearchReportsWorkspace />);

    fireEvent.click(await screen.findByRole('button', { name: 'Open report 贵州茅台深度报告' }));

    expect(screen.getByRole('heading', { name: '贵州茅台深度报告' })).toBeInTheDocument();
    expect(screen.getByText('company view')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open Source' })).toHaveAttribute('href', 'https://example.com/r1');
  });

  it('shows an empty state', async () => {
    apiMocks.fetchResearchReports.mockResolvedValueOnce({ items: [], total: 0, limit: 50, offset: 0, warnings: [] });

    render(<ResearchReportsWorkspace />);

    expect(await screen.findByText('No matching research reports.')).toBeInTheDocument();
  });
});
