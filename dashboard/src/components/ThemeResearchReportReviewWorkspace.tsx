import { Check, Download, RefreshCw, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  adminThemeResearchReportPdfUrl,
  fetchAdminThemeResearchReport,
  fetchAdminThemeResearchReports,
  publishThemeResearchReport,
  rejectThemeResearchReport
} from '../api/client';
import type {
  AdminThemeResearchReport,
  AdminThemeResearchReportDocument
} from '../api/types';

type MutationKind = 'publish' | 'reject';
type MutationFeedback = {
  text: string;
  tone: 'success' | 'error' | 'conflict';
};

function displayTimestamp(value: string) {
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return '时间未知';
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'short',
    hour12: false
  }).format(timestamp);
}

function isStatus(error: unknown, status: number) {
  const message = error instanceof Error ? error.message : String(error);
  return new RegExp(`failed with ${status}(?:\\D|$)`).test(message);
}

function previewErrorMessage(error: unknown) {
  if (isStatus(error, 404)) return '报告预览不存在或已离开待审核队列';
  if (isStatus(error, 503)) return '报告预览暂不可用';
  return '报告预览加载失败';
}

function mutationErrorMessage(error: unknown) {
  if (isStatus(error, 404)) return '报告不存在或已离开待审核队列，请刷新后重试';
  if (isStatus(error, 503)) return '报告审核服务暂不可用，请稍后重试';
  return '审核操作失败，请重试';
}

export function ThemeResearchReportReviewWorkspace() {
  const [queue, setQueue] = useState<AdminThemeResearchReport[] | null>(null);
  const [queueError, setQueueError] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [preview, setPreview] = useState<AdminThemeResearchReportDocument | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState('');
  const [previewRetryVersion, setPreviewRetryVersion] = useState(0);
  const [comment, setComment] = useState('');
  const [rejectionReason, setRejectionReason] = useState('');
  const [rejectionValidation, setRejectionValidation] = useState('');
  const [mutationKind, setMutationKind] = useState<MutationKind | null>(null);
  const [mutationFeedback, setMutationFeedback] = useState<MutationFeedback | null>(null);
  const mountedRef = useRef(false);
  const queueRequestRef = useRef(0);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      queueRequestRef.current += 1;
    };
  }, []);

  const loadQueue = useCallback(async () => {
    const requestId = queueRequestRef.current + 1;
    queueRequestRef.current = requestId;
    setQueueError(false);
    try {
      const response = await fetchAdminThemeResearchReports('pending_review');
      if (!mountedRef.current || queueRequestRef.current !== requestId) return;
      setQueue(response.items);
      setSelectedId((current) =>
        response.items.some((item) => item.report_version_id === current)
          ? current
          : response.items[0]?.report_version_id ?? null
      );
    } catch {
      if (!mountedRef.current || queueRequestRef.current !== requestId) return;
      setQueue([]);
      setSelectedId(null);
      setQueueError(true);
    }
  }, []);

  useEffect(() => {
    void loadQueue();
  }, [loadQueue]);

  const selectedReport = useMemo(
    () => queue?.find((item) => item.report_version_id === selectedId) ?? null,
    [queue, selectedId]
  );

  useEffect(() => {
    if (!selectedId) {
      setPreview(null);
      setPreviewLoading(false);
      setPreviewError('');
      return;
    }

    let cancelled = false;
    const requestedId = selectedId;
    setPreview(null);
    setPreviewLoading(true);
    setPreviewError('');
    fetchAdminThemeResearchReport(requestedId)
      .then((nextPreview) => {
        if (cancelled) return;
        if (
          nextPreview.report_version_id !== requestedId ||
          (selectedReport && nextPreview.theme_id !== selectedReport.theme_id)
        ) {
          setPreviewError('报告预览身份校验失败');
          return;
        }
        setPreview(nextPreview);
      })
      .catch((error: unknown) => {
        if (!cancelled) setPreviewError(previewErrorMessage(error));
      })
      .finally(() => {
        if (!cancelled) setPreviewLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedId, selectedReport?.theme_id, previewRetryVersion]);

  const currentPreview =
    preview &&
    selectedReport &&
    preview.report_version_id === selectedReport.report_version_id &&
    preview.theme_id === selectedReport.theme_id
      ? preview
      : null;
  const mutationPending = mutationKind !== null;
  const canReview = Boolean(
    selectedReport?.status === 'pending_review' &&
      currentPreview?.status === 'pending_review' &&
      !previewLoading &&
      !previewError &&
      !mutationPending
  );

  function selectReport(reportVersionId: string) {
    if (mutationPending || reportVersionId === selectedId) return;
    setSelectedId(reportVersionId);
    setMutationFeedback(null);
    setRejectionValidation('');
    setComment('');
    setRejectionReason('');
  }

  async function mutate(kind: MutationKind) {
    if (!selectedReport || !canReview) return;
    const trimmedReason = rejectionReason.trim();
    if (kind === 'reject' && !trimmedReason) {
      setRejectionValidation('请填写驳回原因');
      return;
    }

    setRejectionValidation('');
    setMutationFeedback(null);
    setMutationKind(kind);
    try {
      const idempotencyKey = crypto.randomUUID();
      if (kind === 'publish') {
        const trimmedComment = comment.trim();
        await publishThemeResearchReport(selectedReport.report_version_id, {
          expected_row_version: selectedReport.row_version,
          idempotency_key: idempotencyKey,
          ...(trimmedComment ? { comment: trimmedComment } : {})
        });
      } else {
        await rejectThemeResearchReport(selectedReport.report_version_id, {
          expected_row_version: selectedReport.row_version,
          idempotency_key: idempotencyKey,
          reason: trimmedReason
        });
      }
      if (!mountedRef.current) return;
      setMutationFeedback({
        text: kind === 'publish' ? '报告已批准发布' : '报告已驳回',
        tone: 'success'
      });
      setComment('');
      setRejectionReason('');
      await loadQueue();
    } catch (error: unknown) {
      if (!mountedRef.current) return;
      if (isStatus(error, 409)) {
        setMutationFeedback({
          text: '报告状态已被其他管理员更新，请刷新后重试',
          tone: 'conflict'
        });
        setPreviewRetryVersion((value) => value + 1);
        await loadQueue();
      } else {
        setMutationFeedback({ text: mutationErrorMessage(error), tone: 'error' });
      }
    } finally {
      if (mountedRef.current) setMutationKind(null);
    }
  }

  return (
    <section className="theme-report-review-workspace" aria-label="主题报告审核工作台">
      <header className="workspace-header theme-report-review-header">
        <div>
          <h1>主题报告审核</h1>
          <p className="muted">审核后台生成的主题研究报告；批准后全员可见。</p>
        </div>
        <button className="icon-text-button" type="button" onClick={() => void loadQueue()} disabled={mutationPending}>
          <RefreshCw size={16} aria-hidden="true" /> 刷新队列
        </button>
      </header>

      {mutationFeedback ? (
        <div
          className={`theme-report-review-message theme-report-review-workspace-message is-${mutationFeedback.tone}`}
          role={mutationFeedback.tone === 'success' ? 'status' : 'alert'}
        >
          {mutationFeedback.text}
        </div>
      ) : null}

      {queue === null ? (
        <section className="workspace-band theme-research-state" aria-busy="true">正在加载待审核报告...</section>
      ) : queueError ? (
        <section className="workspace-band theme-research-state" role="alert">
          <h2>待审核报告加载失败</h2>
          <p>无法读取审核队列，请稍后重试。</p>
          <button className="icon-text-button" type="button" onClick={() => void loadQueue()}>
            <RefreshCw size={16} aria-hidden="true" /> 重试加载队列
          </button>
        </section>
      ) : queue.length === 0 ? (
        <section className="workspace-band theme-research-empty">
          <h2>当前没有待审核报告</h2>
          <p>后台生成并完成索引的报告会自动进入这里。</p>
        </section>
      ) : (
        <div className="theme-report-review-layout">
          <aside className="theme-report-review-queue" aria-label="待审核报告队列">
            <div className="theme-report-review-section-heading">
              <h2>待审核</h2>
              <span>{queue.length} 份</span>
            </div>
            <div className="theme-report-review-queue-items">
              {queue.map((item) => (
                <button
                  key={item.report_version_id}
                  type="button"
                  aria-label={`审核${item.title}`}
                  aria-pressed={item.report_version_id === selectedId}
                  className={item.report_version_id === selectedId ? 'active' : ''}
                  onClick={() => selectReport(item.report_version_id)}
                  disabled={mutationPending}
                >
                  <strong>{item.title}</strong>
                  <span>{item.theme_id} · {item.version}</span>
                  <small>生成于 {displayTimestamp(item.generated_at)}</small>
                </button>
              ))}
            </div>
          </aside>

          <section className="theme-report-review-preview" aria-label="报告审核预览">
            {selectedReport ? (
              <header className="theme-report-review-preview-header">
                <div>
                  <span className="theme-research-status is-warning">待审核</span>
                  <h2>{selectedReport.title}</h2>
                  <p>{selectedReport.summary}</p>
                </div>
                {currentPreview?.has_pdf ? (
                  <a className="icon-text-button" href={adminThemeResearchReportPdfUrl(selectedReport.report_version_id)}>
                    <Download size={16} aria-hidden="true" /> 下载 PDF
                  </a>
                ) : null}
              </header>
            ) : null}

            {selectedReport ? (
              <dl className="theme-report-review-meta">
                <div><dt>主题</dt><dd>{selectedReport.theme_id}</dd></div>
                <div><dt>版本</dt><dd>{selectedReport.version}</dd></div>
                <div><dt>生成时间</dt><dd>{displayTimestamp(selectedReport.generated_at)}</dd></div>
                <div><dt>行版本</dt><dd>行版本 {selectedReport.row_version}</dd></div>
                {currentPreview ? (
                  <div><dt>生成器</dt><dd>{currentPreview.generator_name} · {currentPreview.generator_version}</dd></div>
                ) : null}
              </dl>
            ) : null}

            {previewLoading ? (
              <div className="theme-report-review-preview-state" aria-busy="true">正在加载安全预览...</div>
            ) : previewError ? (
              <div className="theme-report-review-preview-state" role="alert">
                <strong>{previewError}</strong>
                <button className="icon-text-button" type="button" onClick={() => setPreviewRetryVersion((value) => value + 1)}>
                  <RefreshCw size={16} aria-hidden="true" /> 重试加载预览
                </button>
              </div>
            ) : currentPreview ? (
              // Trust boundary: the authenticated admin report endpoint returns sanitized HTML.
              <article className="theme-report-article theme-report-review-article" dangerouslySetInnerHTML={{ __html: currentPreview.html }} />
            ) : null}

            {selectedReport ? (
              <div className="theme-report-review-controls">
                <label>
                  <span>审核备注（可选）</span>
                  <textarea value={comment} onChange={(event) => setComment(event.target.value)} disabled={!canReview} />
                </label>
                <label>
                  <span>驳回原因</span>
                  <textarea
                    value={rejectionReason}
                    onChange={(event) => {
                      setRejectionReason(event.target.value);
                      if (event.target.value.trim()) setRejectionValidation('');
                    }}
                    disabled={!canReview}
                  />
                </label>
                {rejectionValidation ? <span className="theme-report-review-validation" role="alert">{rejectionValidation}</span> : null}
                {!canReview && !mutationPending ? (
                  <span className="theme-report-review-gate" role="status">
                    {previewLoading ? '安全预览加载完成后才能审核' : '请先成功加载安全预览后再审核'}
                  </span>
                ) : null}
                <div className="theme-report-review-actions">
                  <button className="theme-report-review-publish" type="button" onClick={() => void mutate('publish')} disabled={!canReview}>
                    <Check size={16} aria-hidden="true" /> {mutationKind === 'publish' ? '批准中…' : '批准发布'}
                  </button>
                  <button className="theme-report-review-reject" type="button" onClick={() => void mutate('reject')} disabled={!canReview}>
                    <X size={16} aria-hidden="true" /> {mutationKind === 'reject' ? '驳回中…' : '驳回'}
                  </button>
                </div>
              </div>
            ) : null}
          </section>
        </div>
      )}
    </section>
  );
}
