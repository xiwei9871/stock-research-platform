import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ResearchReportsWorkspace } from '../src/components/ResearchReportsWorkspace';
import type { ResearchReportItem } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchResearchReportSummary: vi.fn(),
  fetchResearchReports: vi.fn(),
  fetchResearchReportDocument: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

function makeReport(overrides: Partial<ResearchReportItem> = {}): ResearchReportItem {
  return {
    event_key: 'r1:600519.SH',
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
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(new Date('2026-06-12T10:00:00Z'));
  vi.resetAllMocks();
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
  apiMocks.fetchResearchReportDocument.mockResolvedValue({
    report_id: 'r1',
    report_title: '贵州茅台深度报告',
    has_pdf: true,
    pdf_url: '/api/research-reports/r1/pdf',
    source_url: 'https://example.com/r1',
    file_name: 'r1.pdf',
    public_access: false,
    copyright_note: 'internal pdf',
    warnings: []
  });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  cleanup();
});

describe('ResearchReportsWorkspace', () => {
  it('uses the initial query and loads matching reports', async () => {
    const { rerender } = render(<ResearchReportsWorkspace initialQuery="茅台" />);

    expect(screen.getByDisplayValue('茅台')).toBeInTheDocument();
    await waitFor(() => {
      expect(apiMocks.fetchResearchReports).toHaveBeenLastCalledWith(expect.objectContaining({ q: '茅台' }));
    });

    rerender(<ResearchReportsWorkspace initialQuery="平安" />);
    expect(screen.getByDisplayValue('平安')).toBeInTheDocument();
    await waitFor(() => {
      expect(apiMocks.fetchResearchReports).toHaveBeenLastCalledWith(expect.objectContaining({ q: '平安' }));
    });
  });

  it('loads summary and report rows', async () => {
    render(<ResearchReportsWorkspace />);
    const results = screen.getByLabelText('Research report results');

    expect(await screen.findByText('57,418')).toBeInTheDocument();
    expect(await within(results).findByRole('button', { name: 'Open report 贵州茅台深度报告' })).toBeInTheDocument();
    expect(within(results).getByText('华泰证券')).toBeInTheDocument();
    expect(within(results).getByText('买入')).toBeInTheDocument();
  });

  it('defaults the report end date to today', async () => {
    render(<ResearchReportsWorkspace />);

    await waitFor(() => {
      expect(apiMocks.fetchResearchReports).toHaveBeenCalledWith(
        expect.objectContaining({
          start_date: '2026-03-01',
          end_date: '2026-06-12'
        })
      );
    });
  });

  it('defaults the report end date to the local calendar date near a UTC boundary', async () => {
    vi.stubEnv('TZ', 'America/Los_Angeles');
    vi.setSystemTime(new Date(2026, 5, 12, 23, 30, 0));

    render(<ResearchReportsWorkspace />);

    await waitFor(() => {
      expect(apiMocks.fetchResearchReports).toHaveBeenCalledWith(
        expect.objectContaining({
          start_date: '2026-03-01',
          end_date: '2026-06-12'
        })
      );
    });
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

  it('opens full-screen report details from a selected row', async () => {
    render(<ResearchReportsWorkspace />);

    fireEvent.click(await screen.findByRole('button', { name: 'Open report 贵州茅台深度报告' }));

    expect(screen.getByLabelText('Research report full-screen reader')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '贵州茅台深度报告' })).toBeInTheDocument();
    expect(screen.getByText('贵州茅台 600519.SH')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '来源链接' })).toHaveAttribute('href', 'https://example.com/r1');
  });

  it('renders a full-screen PDF reader for the selected research report', async () => {
    render(<ResearchReportsWorkspace />);

    fireEvent.click(await screen.findByRole('button', { name: 'Open report 贵州茅台深度报告' }));

    await waitFor(() => {
      expect(apiMocks.fetchResearchReportDocument).toHaveBeenCalledWith('r1');
    });
    expect(await screen.findByTitle('贵州茅台深度报告 PDF')).toHaveAttribute(
      'src',
      '/api/research-reports/r1/pdf'
    );
    expect(screen.getByRole('link', { name: '打开PDF' })).toHaveAttribute('href', '/api/research-reports/r1/pdf');
    expect(screen.getByLabelText('Research report full-screen reader')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '返回研报列表' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Research report results')).not.toBeInTheDocument();
  });

  it('toggles the PDF reader between normal and fill-screen layouts', async () => {
    render(<ResearchReportsWorkspace />);

    fireEvent.click(await screen.findByRole('button', { name: 'Open report 贵州茅台深度报告' }));
    const reader = await screen.findByLabelText('Research report full-screen reader');

    expect(reader).not.toHaveClass('is-fill-screen');
    fireEvent.click(screen.getByRole('button', { name: '铺满屏幕' }));

    expect(reader).toHaveClass('is-fill-screen');
    expect(screen.getByRole('button', { name: '退出铺满' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '退出铺满' }));

    expect(reader).not.toHaveClass('is-fill-screen');
    expect(screen.getByRole('button', { name: '铺满屏幕' })).toBeInTheDocument();
  });

  it('returns from the full-screen reader to the report list', async () => {
    render(<ResearchReportsWorkspace />);

    fireEvent.click(await screen.findByRole('button', { name: 'Open report 贵州茅台深度报告' }));
    expect(await screen.findByLabelText('Research report full-screen reader')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '返回研报列表' }));

    expect(screen.getByLabelText('Research report results')).toBeInTheDocument();
    expect(screen.queryByLabelText('Research report full-screen reader')).not.toBeInTheDocument();
  });

  it('shows a clear fallback when the selected research report has no local PDF', async () => {
    apiMocks.fetchResearchReportDocument.mockResolvedValue({
      report_id: 'r1',
      report_title: '贵州茅台深度报告',
      has_pdf: false,
      pdf_url: '',
      source_url: 'https://example.com/r1',
      file_name: '',
      public_access: true,
      copyright_note: 'metadata only',
      warnings: ['local pdf is unavailable or outside allowed report directories']
    });

    render(<ResearchReportsWorkspace />);

    fireEvent.click(await screen.findByRole('button', { name: 'Open report 贵州茅台深度报告' }));

    expect(await screen.findByText('暂无本地PDF')).toBeInTheDocument();
    expect(screen.getByText('可打开来源链接查看原文，或等待研报同步任务补齐PDF文件。')).toBeInTheDocument();
  });

  it('opens stock detail from a report row with report context', async () => {
    const onOpenAsset = vi.fn();
    render(<ResearchReportsWorkspace onOpenAsset={onOpenAsset} />);

    await screen.findByText('贵州茅台深度报告');
    fireEvent.click(
      within(screen.getByLabelText('Research report results')).getByRole('button', {
        name: 'Open Stock Detail for 贵州茅台'
      })
    );

    expect(onOpenAsset).toHaveBeenCalledWith('CN:SH:600519', {
      sourceWorkspace: 'researchReports',
      assetId: 'CN:SH:600519',
      eventKey: 'r1:600519.SH',
      reportId: 'r1',
      query: '贵州茅台深度报告'
    });
  });

  it('opens stock detail from selected report detail with report context', async () => {
    const onOpenAsset = vi.fn();
    render(<ResearchReportsWorkspace onOpenAsset={onOpenAsset} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Open report 贵州茅台深度报告' }));
    fireEvent.click(
      within(screen.getByLabelText('Research report full-screen reader')).getByRole('button', {
        name: 'Open Stock Detail for 贵州茅台'
      })
    );

    expect(onOpenAsset).toHaveBeenLastCalledWith('CN:SH:600519', {
      sourceWorkspace: 'researchReports',
      assetId: 'CN:SH:600519',
      eventKey: 'r1:600519.SH',
      reportId: 'r1',
      query: '贵州茅台深度报告'
    });
  });

  it('opens the selected event when rows share a report id', async () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    apiMocks.fetchResearchReports.mockResolvedValueOnce({
      items: [
        makeReport({
          event_key: 'r1:600519.SH',
          report_title: '同名报告',
          stock_name: '贵州茅台',
          ts_code: '600519.SH',
          company_view: 'A'
        }),
        makeReport({
          event_key: 'r1:000001.SZ',
          report_title: '同名报告',
          stock_name: '平安银行',
          ts_code: '000001.SZ',
          company_view: 'B'
        })
      ],
      total: 2,
      limit: 50,
      offset: 0,
      warnings: []
    });

    render(<ResearchReportsWorkspace />);

    const buttons = await screen.findAllByRole('button', { name: 'Open report 同名报告' });
    fireEvent.click(buttons[1]);

    const reader = screen.getByLabelText('Research report full-screen reader');
    expect(within(reader).getByText(/平安银行/)).toBeInTheDocument();
    expect(within(reader).getByRole('heading', { name: '同名报告' })).toBeInTheDocument();
    expect(
      consoleErrorSpy.mock.calls.some((call) => call.join(' ').includes('Encountered two children with the same key'))
    ).toBe(false);
    consoleErrorSpy.mockRestore();
  });

  it('selects the initial event key after reports load', async () => {
    apiMocks.fetchResearchReports.mockResolvedValueOnce({
      items: [
        {
          event_key: 'r-old:CN:SH:600519',
          report_id: 'r-old',
          asset_id: 'CN:SH:600519',
          ts_code: '600519.SH',
          stock_name: '贵州茅台',
          report_title: '贵州茅台旧报告',
          broker: '中信证券',
          analyst: '张三',
          industry_name: '白酒',
          published_at: '2026-06-01T10:00:00+08:00',
          rating: '买入',
          target_price: null,
          summary: '旧报告'
        },
        {
          event_key: 'r-new:CN:SH:600519',
          report_id: 'r-new',
          asset_id: 'CN:SH:600519',
          ts_code: '600519.SH',
          stock_name: '贵州茅台',
          report_title: '贵州茅台深度跟踪',
          broker: '国泰君安',
          analyst: '李四',
          industry_name: '白酒',
          published_at: '2026-06-12T10:00:00+08:00',
          rating: '增持',
          target_price: null,
          summary: '新报告'
        }
      ],
      count: 2,
      warnings: []
    });

    render(<ResearchReportsWorkspace initialQuery="茅台" initialEventKey="r-new:CN:SH:600519" />);

    expect(await screen.findByRole('heading', { name: '贵州茅台深度跟踪' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '贵州茅台旧报告' })).not.toBeInTheDocument();
  });

  it('falls back to the initial report id when the event key is missing', async () => {
    apiMocks.fetchResearchReports.mockResolvedValueOnce({
      items: [
        makeReport({
          event_key: 'r-old:CN:SH:600519',
          report_id: 'r-old',
          report_title: '贵州茅台旧报告',
          company_view: '旧报告视角'
        }),
        makeReport({
          event_key: 'r-new:CN:SH:600519',
          report_id: 'r-new',
          report_title: '贵州茅台深度跟踪',
          company_view: '新报告视角'
        })
      ],
      total: 2,
      limit: 50,
      offset: 0,
      warnings: []
    });

    render(
      <ResearchReportsWorkspace
        initialQuery="茅台"
        initialEventKey="missing:CN:SH:600519"
        initialReportId="r-new"
      />
    );

    expect(await screen.findByRole('heading', { name: '贵州茅台深度跟踪' })).toBeInTheDocument();
    expect(screen.getByText('新报告视角')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '贵州茅台旧报告' })).not.toBeInTheDocument();
  });

  it('preserves a manual selection across reloads after initial deep-link selection', async () => {
    const oldReport = makeReport({
      event_key: 'r-old:CN:SH:600519',
      report_id: 'r-old',
      report_title: '贵州茅台旧报告',
      company_view: '旧报告视角'
    });
    const newReport = makeReport({
      event_key: 'r-new:CN:SH:600519',
      report_id: 'r-new',
      report_title: '贵州茅台深度跟踪',
      company_view: '新报告视角'
    });

    apiMocks.fetchResearchReports
      .mockResolvedValueOnce({
        items: [oldReport, newReport],
        total: 2,
        limit: 50,
        offset: 0,
        warnings: []
      })
      .mockResolvedValueOnce({
        items: [oldReport, newReport],
        total: 2,
        limit: 50,
        offset: 0,
        warnings: []
      });

    render(<ResearchReportsWorkspace initialQuery="茅台" initialEventKey="r-new:CN:SH:600519" />);

    expect(await screen.findByRole('heading', { name: '贵州茅台深度跟踪' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Open report 贵州茅台旧报告' }));
    expect(screen.getByRole('heading', { name: '贵州茅台旧报告' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '返回研报列表' }));

    fireEvent.click(screen.getByRole('button', { name: 'Search Reports' }));

    expect(await screen.findByRole('heading', { name: '贵州茅台旧报告' })).toBeInTheDocument();
    expect(screen.getByText('旧报告视角')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '贵州茅台深度跟踪' })).not.toBeInTheDocument();
  });

  it('shows an empty state', async () => {
    apiMocks.fetchResearchReports.mockResolvedValueOnce({ items: [], total: 0, limit: 50, offset: 0, warnings: [] });

    render(<ResearchReportsWorkspace />);

    expect(await screen.findByText('No matching research reports.')).toBeInTheDocument();
  });
});
