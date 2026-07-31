import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ThemeResearchReportReader } from '../src/components/ThemeResearchReportReader';

const api = vi.hoisted(() => ({
  fetchThemeResearchReports: vi.fn(),
  fetchThemeResearchReportDocument: vi.fn(),
  themeResearchReportPdfUrl: vi.fn(
    (themeId: string, reportVersionId: string) =>
      `/api/research/theme-decomposition/themes/${themeId}/reports/${reportVersionId}/pdf`
  )
}));

vi.mock('../src/api/client', () => api);

const reports = {
  total: 2,
  items: [
    {
      report_version_id: 'report-v2',
      theme_id: 'theme-a',
      version: '2.0',
      title: 'AI 供电主题研究（第二版）',
      summary: '第二版摘要',
      status: 'published',
      generated_at: '2026-07-30T08:00:00+08:00',
      indexed_at: '2026-07-30T09:00:00+08:00',
      published_at: '2026-07-31T10:00:00+08:00',
      published_by_user_id: 'admin',
      row_version: 4,
      metadata: {},
      created_at: '2026-07-30T08:00:00+08:00',
      updated_at: '2026-07-31T10:00:00+08:00'
    },
    {
      report_version_id: 'report-v1',
      theme_id: 'theme-a',
      version: '1.0',
      title: 'AI 供电主题研究（第一版）',
      summary: '第一版摘要',
      status: 'archived',
      generated_at: '2026-07-20T08:00:00+08:00',
      indexed_at: '2026-07-20T09:00:00+08:00',
      published_at: '2026-07-21T10:00:00+08:00',
      published_by_user_id: 'admin',
      row_version: 5,
      metadata: {},
      created_at: '2026-07-20T08:00:00+08:00',
      updated_at: '2026-07-31T10:00:00+08:00'
    }
  ]
};

function documentFor(reportVersionId: string, title = 'AI 供电主题研究（第二版）') {
  return {
    report_version_id: reportVersionId,
    theme_id: 'theme-a',
    version: reportVersionId === 'report-v1' ? '1.0' : '2.0',
    title,
    summary: '研究摘要',
    status: reportVersionId === 'report-v1' ? 'archived' : 'published',
    generated_at: '2026-07-30T08:00:00+08:00',
    indexed_at: '2026-07-30T09:00:00+08:00',
    published_at: '2026-07-31T10:00:00+08:00',
    has_pdf: true,
    html: '<h2>核心结论</h2><p>服务器电源价值量提升。</p><table><tbody><tr><td>液冷</td></tr></tbody></table>'
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((nextResolve) => {
    resolve = nextResolve;
  });
  return { promise, resolve };
}

describe('ThemeResearchReportReader', () => {
  beforeEach(() => {
    api.fetchThemeResearchReports.mockResolvedValue(reports);
    api.fetchThemeResearchReportDocument.mockResolvedValue(documentFor('report-v2'));
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('shows loading before rendering the backend-sanitized report and approved history', async () => {
    const pendingDocument = deferred<ReturnType<typeof documentFor>>();
    api.fetchThemeResearchReportDocument.mockReturnValueOnce(pendingDocument.promise);
    const navigate = vi.fn();

    render(<ThemeResearchReportReader themeId="theme-a" reportVersionId="report-v2" onNavigate={navigate} />);

    expect(screen.getByText('正在加载分析报告...')).toBeInTheDocument();
    pendingDocument.resolve(documentFor('report-v2'));

    expect(await screen.findByRole('heading', { name: 'AI 供电主题研究（第二版）' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '核心结论' })).toBeInTheDocument();
    expect(screen.getByText('服务器电源价值量提升。')).toBeInTheDocument();
    expect(screen.getByText('液冷')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: '报告历史版本' })).toHaveTextContent('2.0');
    expect(screen.getByRole('combobox', { name: '报告历史版本' })).toHaveTextContent('1.0');
    expect(screen.getByRole('link', { name: '下载 PDF' })).toHaveAttribute(
      'href',
      '/api/research/theme-decomposition/themes/theme-a/reports/report-v2/pdf'
    );
    expect(screen.queryByText('生成报告')).not.toBeInTheDocument();
    expect(screen.queryByText('上传报告')).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole('combobox', { name: '报告历史版本' }), {
      target: { value: 'report-v1' }
    });
    expect(navigate).toHaveBeenCalledWith('/theme-research/theme-a/report/report-v1');
  });

  it('shows a not-found state with a route back to the theme overview', async () => {
    api.fetchThemeResearchReportDocument.mockRejectedValueOnce(new Error('GET report failed with 404'));
    const navigate = vi.fn();

    render(<ThemeResearchReportReader themeId="theme-a" reportVersionId="missing" onNavigate={navigate} />);

    expect(await screen.findByRole('heading', { name: '报告不存在' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '返回主题概览' }));
    expect(navigate).toHaveBeenCalledWith('/theme-research/theme-a');
  });

  it('shows a retryable service-unavailable state instead of a blank screen', async () => {
    api.fetchThemeResearchReportDocument
      .mockRejectedValueOnce(new Error('GET report failed with 503'))
      .mockResolvedValueOnce(documentFor('report-v2'));

    render(<ThemeResearchReportReader themeId="theme-a" reportVersionId="report-v2" onNavigate={vi.fn()} />);

    expect(await screen.findByRole('heading', { name: '报告服务暂不可用' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    expect(await screen.findByRole('heading', { name: 'AI 供电主题研究（第二版）' })).toBeInTheDocument();
    expect(api.fetchThemeResearchReportDocument).toHaveBeenCalledTimes(2);
  });

  it('does not let an obsolete request replace the newly selected report', async () => {
    const staleDocument = deferred<ReturnType<typeof documentFor>>();
    api.fetchThemeResearchReportDocument
      .mockReturnValueOnce(staleDocument.promise)
      .mockResolvedValueOnce(documentFor('report-v1', 'AI 供电主题研究（第一版）'));
    const { rerender } = render(
      <ThemeResearchReportReader themeId="theme-a" reportVersionId="report-v2" onNavigate={vi.fn()} />
    );

    rerender(<ThemeResearchReportReader themeId="theme-a" reportVersionId="report-v1" onNavigate={vi.fn()} />);
    expect(await screen.findByRole('heading', { name: 'AI 供电主题研究（第一版）' })).toBeInTheDocument();

    staleDocument.resolve(documentFor('report-v2', '不应出现的旧报告'));
    await Promise.resolve();
    expect(screen.queryByRole('heading', { name: '不应出现的旧报告' })).not.toBeInTheDocument();
  });
});
