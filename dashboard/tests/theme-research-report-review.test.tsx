import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ThemeResearchReportReviewWorkspace } from '../src/components/ThemeResearchReportReviewWorkspace';
import type {
  AdminThemeResearchReport,
  AdminThemeResearchReportDocument
} from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchAdminThemeResearchReports: vi.fn(),
  fetchAdminThemeResearchReport: vi.fn(),
  adminThemeResearchReportPdfUrl: vi.fn((id: string) => `/api/admin/theme-research/reports/${id}/pdf`),
  publishThemeResearchReport: vi.fn(),
  rejectThemeResearchReport: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

function report(overrides: Partial<AdminThemeResearchReport> = {}): AdminThemeResearchReport {
  return {
    report_version_id: 'report-1',
    theme_id: 'theme-ai-power',
    version: 'v1.0',
    title: 'AI 电力主题分析报告',
    summary: '研究摘要',
    status: 'pending_review',
    generated_at: '2026-07-30T08:00:00+08:00',
    indexed_at: '2026-07-30T08:05:00+08:00',
    published_at: null,
    published_by_user_id: null,
    rejected_at: null,
    rejected_by_user_id: null,
    rejection_reason: null,
    row_version: 7,
    metadata: {},
    created_at: '2026-07-30T08:05:00+08:00',
    updated_at: '2026-07-30T08:05:00+08:00',
    ...overrides
  };
}

function document(overrides: Partial<AdminThemeResearchReportDocument> = {}): AdminThemeResearchReportDocument {
  return {
    report_version_id: 'report-1',
    theme_id: 'theme-ai-power',
    version: 'v1.0',
    title: 'AI 电力主题分析报告',
    summary: '研究摘要',
    status: 'pending_review',
    generated_at: '2026-07-30T08:00:00+08:00',
    indexed_at: '2026-07-30T08:05:00+08:00',
    published_at: null,
    has_pdf: true,
    html: '<h2>安全预览</h2><p>报告正文</p>',
    generator_name: 'theme-research-agent',
    generator_version: '2026.07',
    ...overrides
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });
  return { promise, resolve, reject };
}

describe('ThemeResearchReportReviewWorkspace', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'uuid-review-1') });
    apiMocks.adminThemeResearchReportPdfUrl.mockImplementation(
      (id: string) => `/api/admin/theme-research/reports/${id}/pdf`
    );
    apiMocks.fetchAdminThemeResearchReports.mockResolvedValue({ total: 1, items: [report()] });
    apiMocks.fetchAdminThemeResearchReport.mockResolvedValue(document());
    apiMocks.publishThemeResearchReport.mockResolvedValue({ report: report({ status: 'published', row_version: 8 }) });
    apiMocks.rejectThemeResearchReport.mockResolvedValue({
      report: report({ status: 'rejected', row_version: 8, rejection_reason: '证据不足' })
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('loads the pending queue and renders only safe review metadata and sanitized preview', async () => {
    render(<ThemeResearchReportReviewWorkspace />);

    expect(screen.getByText('正在加载待审核报告...')).toBeVisible();
    expect(await screen.findByRole('heading', { name: 'AI 电力主题分析报告' })).toBeVisible();
    expect(apiMocks.fetchAdminThemeResearchReports).toHaveBeenCalledWith('pending_review');
    expect(apiMocks.fetchAdminThemeResearchReport).toHaveBeenCalledWith('report-1');
    expect(await screen.findByRole('heading', { name: '安全预览' })).toBeVisible();
    expect(screen.getByText('theme-ai-power')).toBeVisible();
    expect(screen.getByText('theme-research-agent · 2026.07')).toBeVisible();
    expect(screen.getByText('行版本 7')).toBeVisible();
    expect(screen.queryByText(/checksum|manifest|markdown_path|pdf_path|文件系统/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /生成|上传|编辑正文/ })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '下载 PDF' })).toHaveAttribute(
      'href',
      '/api/admin/theme-research/reports/report-1/pdf'
    );
  });

  it('shows clear empty and retryable queue error states', async () => {
    apiMocks.fetchAdminThemeResearchReports.mockResolvedValueOnce({ total: 0, items: [] });
    render(<ThemeResearchReportReviewWorkspace />);
    expect(await screen.findByText('当前没有待审核报告')).toBeVisible();

    cleanup();
    apiMocks.fetchAdminThemeResearchReports.mockRejectedValueOnce(new Error('GET failed with 503'));
    apiMocks.fetchAdminThemeResearchReports.mockResolvedValueOnce({ total: 1, items: [report()] });
    render(<ThemeResearchReportReviewWorkspace />);
    expect(await screen.findByRole('alert')).toHaveTextContent('待审核报告加载失败');
    fireEvent.click(screen.getByRole('button', { name: '重试加载队列' }));
    expect(await screen.findByRole('heading', { name: 'AI 电力主题分析报告' })).toBeVisible();
  });

  it('requires and trims the rejection reason before submitting', async () => {
    render(<ThemeResearchReportReviewWorkspace />);
    await screen.findByRole('heading', { name: '安全预览' });

    fireEvent.change(screen.getByLabelText('驳回原因'), { target: { value: '   ' } });
    fireEvent.click(screen.getByRole('button', { name: '驳回' }));
    expect(await screen.findByText('请填写驳回原因')).toBeVisible();
    expect(apiMocks.rejectThemeResearchReport).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText('驳回原因'), { target: { value: '  证据不足  ' } });
    fireEvent.click(screen.getByRole('button', { name: '驳回' }));
    await waitFor(() => {
      expect(apiMocks.rejectThemeResearchReport).toHaveBeenCalledWith('report-1', {
        expected_row_version: 7,
        idempotency_key: 'uuid-review-1',
        reason: '证据不足'
      });
    });
  });

  it('publishes with the current row version, UUID and trimmed optional comment, then removes the departed item', async () => {
    apiMocks.fetchAdminThemeResearchReports
      .mockResolvedValueOnce({ total: 1, items: [report()] })
      .mockResolvedValueOnce({ total: 0, items: [] });
    render(<ThemeResearchReportReviewWorkspace />);
    await screen.findByRole('heading', { name: '安全预览' });

    fireEvent.change(screen.getByLabelText('审核备注（可选）'), { target: { value: '  同意发布  ' } });
    fireEvent.click(screen.getByRole('button', { name: '批准发布' }));

    await waitFor(() => {
      expect(apiMocks.publishThemeResearchReport).toHaveBeenCalledWith('report-1', {
        expected_row_version: 7,
        idempotency_key: 'uuid-review-1',
        comment: '同意发布'
      });
    });
    expect(await screen.findByText('当前没有待审核报告')).toBeVisible();
    expect(screen.queryByText('安全预览')).not.toBeInTheDocument();
  });

  it('disables mutations to prevent double submit', async () => {
    const pending = deferred<{ report: AdminThemeResearchReport }>();
    apiMocks.publishThemeResearchReport.mockReturnValueOnce(pending.promise);
    render(<ThemeResearchReportReviewWorkspace />);
    await screen.findByRole('heading', { name: '安全预览' });

    fireEvent.click(screen.getByRole('button', { name: '批准发布' }));
    const pendingButton = screen.getByRole('button', { name: '批准中…' });
    expect(pendingButton).toBeDisabled();
    expect(screen.getByRole('button', { name: '驳回' })).toBeDisabled();
    fireEvent.click(pendingButton);
    expect(apiMocks.publishThemeResearchReport).toHaveBeenCalledTimes(1);
  });

  it('allows review only after the matching safe preview loads successfully', async () => {
    const pendingPreview = deferred<AdminThemeResearchReportDocument>();
    apiMocks.fetchAdminThemeResearchReport.mockReturnValueOnce(pendingPreview.promise);
    render(<ThemeResearchReportReviewWorkspace />);
    await screen.findByRole('heading', { name: 'AI 电力主题分析报告' });

    expect(screen.getByRole('button', { name: '批准发布' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '驳回' })).toBeDisabled();
    expect(await screen.findByText('安全预览加载完成后才能审核')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '批准发布' }));
    fireEvent.click(screen.getByRole('button', { name: '驳回' }));
    expect(apiMocks.publishThemeResearchReport).not.toHaveBeenCalled();
    expect(apiMocks.rejectThemeResearchReport).not.toHaveBeenCalled();

    pendingPreview.resolve(document());
    expect(await screen.findByRole('heading', { name: '安全预览' })).toBeVisible();
    expect(screen.getByRole('button', { name: '批准发布' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '驳回' })).toBeEnabled();
  });

  it.each([
    ['preview error', () => Promise.reject(new Error('GET failed with 404'))],
    ['preview identity mismatch', () => Promise.resolve(document({ report_version_id: 'wrong-report' }))],
    ['preview theme mismatch', () => Promise.resolve(document({ theme_id: 'wrong-theme' }))]
  ])('keeps review disabled after %s', async (_scenario, previewResult) => {
    apiMocks.fetchAdminThemeResearchReport.mockImplementationOnce(() => previewResult());
    render(<ThemeResearchReportReviewWorkspace />);

    expect(await screen.findByText('请先成功加载安全预览后再审核')).toBeVisible();
    expect(screen.getByRole('button', { name: '批准发布' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '驳回' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '批准发布' }));
    expect(apiMocks.publishThemeResearchReport).not.toHaveBeenCalled();
  });

  it('reports a 409 conflict exactly and refreshes the queue and selected preview', async () => {
    apiMocks.publishThemeResearchReport.mockRejectedValueOnce(new Error('POST failed with 409: conflict'));
    apiMocks.fetchAdminThemeResearchReports
      .mockResolvedValueOnce({ total: 1, items: [report()] })
      .mockResolvedValueOnce({ total: 1, items: [report({ row_version: 8 })] });
    apiMocks.fetchAdminThemeResearchReport
      .mockResolvedValueOnce(document())
      .mockResolvedValueOnce(document({ summary: '已刷新预览' }));
    render(<ThemeResearchReportReviewWorkspace />);
    await screen.findByRole('heading', { name: '安全预览' });

    fireEvent.click(screen.getByRole('button', { name: '批准发布' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('报告状态已被其他管理员更新，请刷新后重试');
    await waitFor(() => expect(apiMocks.fetchAdminThemeResearchReports).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(apiMocks.fetchAdminThemeResearchReport).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('行版本 8')).toBeVisible();
  });

  it('keeps the 409 conflict visible when the refreshed queue no longer contains the report', async () => {
    apiMocks.publishThemeResearchReport.mockRejectedValueOnce(new Error('POST failed with 409: conflict'));
    apiMocks.fetchAdminThemeResearchReports
      .mockResolvedValueOnce({ total: 1, items: [report()] })
      .mockResolvedValueOnce({ total: 0, items: [] });
    render(<ThemeResearchReportReviewWorkspace />);
    await screen.findByRole('heading', { name: '安全预览' });

    fireEvent.click(screen.getByRole('button', { name: '批准发布' }));

    expect(await screen.findByText('当前没有待审核报告')).toBeVisible();
    expect(screen.getByText('报告状态已被其他管理员更新，请刷新后重试')).toBeVisible();
  });

  it('keeps the 409 conflict visible alongside an automatic queue refresh failure', async () => {
    apiMocks.publishThemeResearchReport.mockRejectedValueOnce(new Error('POST failed with 409: conflict'));
    apiMocks.fetchAdminThemeResearchReports
      .mockResolvedValueOnce({ total: 1, items: [report()] })
      .mockRejectedValueOnce(new Error('GET failed with 503'));
    render(<ThemeResearchReportReviewWorkspace />);
    await screen.findByRole('heading', { name: '安全预览' });

    fireEvent.click(screen.getByRole('button', { name: '批准发布' }));

    expect(await screen.findByText('待审核报告加载失败')).toBeVisible();
    expect(screen.getByText('报告状态已被其他管理员更新，请刷新后重试')).toBeVisible();
    expect(screen.getByRole('button', { name: '重试加载队列' })).toBeEnabled();
  });

  it('announces successful review with success semantics instead of an error alert', async () => {
    apiMocks.fetchAdminThemeResearchReports
      .mockResolvedValueOnce({ total: 1, items: [report()] })
      .mockResolvedValueOnce({ total: 0, items: [] });
    render(<ThemeResearchReportReviewWorkspace />);
    await screen.findByRole('heading', { name: '安全预览' });

    fireEvent.click(screen.getByRole('button', { name: '批准发布' }));

    const status = await screen.findByRole('status');
    expect(status).toHaveTextContent('报告已批准发布');
    expect(status).toHaveClass('is-success');
    expect(screen.queryByRole('alert', { name: '报告已批准发布' })).not.toBeInTheDocument();
  });

  it('keeps preview errors retryable without blanking the workspace', async () => {
    apiMocks.fetchAdminThemeResearchReport
      .mockRejectedValueOnce(new Error('GET failed with 503'))
      .mockResolvedValueOnce(document());
    render(<ThemeResearchReportReviewWorkspace />);

    expect(await screen.findByRole('alert')).toHaveTextContent('报告预览暂不可用');
    expect(screen.getByRole('heading', { name: 'AI 电力主题分析报告' })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '重试加载预览' }));
    expect(await screen.findByRole('heading', { name: '安全预览' })).toBeVisible();
  });

  it.each([
    ['POST failed with 404', '报告不存在或已离开待审核队列，请刷新后重试'],
    ['POST failed with 503', '报告审核服务暂不可用，请稍后重试'],
    ['network failed', '审核操作失败，请重试']
  ])('keeps the workspace retryable after mutation error %s', async (failure, message) => {
    apiMocks.publishThemeResearchReport.mockRejectedValueOnce(new Error(failure));
    render(<ThemeResearchReportReviewWorkspace />);
    await screen.findByRole('heading', { name: '安全预览' });

    fireEvent.click(screen.getByRole('button', { name: '批准发布' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(message);
    expect(screen.getByRole('heading', { name: 'AI 电力主题分析报告' })).toBeVisible();
    expect(screen.getByRole('button', { name: '批准发布' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '批准发布' }));
    await waitFor(() => expect(apiMocks.publishThemeResearchReport).toHaveBeenCalledTimes(2));
  });

  it('does not flash an old preview after selection changes', async () => {
    const firstPreview = deferred<AdminThemeResearchReportDocument>();
    const second = report({ report_version_id: 'report-2', theme_id: 'theme-robot', title: '机器人主题报告' });
    apiMocks.fetchAdminThemeResearchReports.mockResolvedValueOnce({ total: 2, items: [report(), second] });
    apiMocks.fetchAdminThemeResearchReport.mockImplementation((id: string) =>
      id === 'report-1'
        ? firstPreview.promise
        : Promise.resolve(document({
            report_version_id: 'report-2',
            theme_id: 'theme-robot',
            title: '机器人主题报告',
            html: '<h2>机器人安全预览</h2>'
          }))
    );
    render(<ThemeResearchReportReviewWorkspace />);
    await screen.findByText('机器人主题报告');

    fireEvent.click(screen.getByRole('button', { name: /审核机器人主题报告/ }));
    expect(await screen.findByRole('heading', { name: '机器人安全预览' })).toBeVisible();
    firstPreview.resolve(document({ html: '<h2>迟到的旧预览</h2>' }));
    await waitFor(() => expect(screen.queryByText('迟到的旧预览')).not.toBeInTheDocument());
    expect(screen.getByRole('heading', { name: '机器人安全预览' })).toBeVisible();
  });
});
