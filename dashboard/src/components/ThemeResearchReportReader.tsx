import { ArrowLeft, Download, RefreshCw } from 'lucide-react';
import { useEffect, useState } from 'react';
import {
  fetchThemeResearchReportDocument,
  fetchThemeResearchReports,
  themeResearchReportPdfUrl
} from '../api/client';
import type { ThemeResearchReportDocument, ThemeResearchReportVersion } from '../api/types';

type Props = {
  themeId: string;
  reportVersionId: string;
  onNavigate: (path: string) => void;
};

type ReportError = 'not_found' | 'unavailable' | 'general';

function reportPath(themeId: string, reportVersionId: string) {
  return `/theme-research/${encodeURIComponent(themeId)}/report/${encodeURIComponent(reportVersionId)}`;
}

function displayTimestamp(value: string) {
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return '时间未知';
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'short',
    hour12: false
  }).format(timestamp);
}

function errorKind(reason: unknown): ReportError {
  const message = reason instanceof Error ? reason.message : String(reason);
  if (/failed with 404(?:\D|$)/.test(message)) return 'not_found';
  if (/failed with 503(?:\D|$)/.test(message)) return 'unavailable';
  return 'general';
}

export function ThemeResearchReportReader({ themeId, reportVersionId, onNavigate }: Props) {
  const [reports, setReports] = useState<ThemeResearchReportVersion[] | null>(null);
  const [historyError, setHistoryError] = useState(false);
  const [document, setDocument] = useState<ThemeResearchReportDocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ReportError | null>(null);
  const [retryVersion, setRetryVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setReports(null);
    setHistoryError(false);
    fetchThemeResearchReports(themeId)
      .then((history) => {
        if (cancelled) return;
        setReports(history.items);
      })
      .catch(() => {
        if (!cancelled) setHistoryError(true);
      });

    return () => {
      cancelled = true;
    };
  }, [themeId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setDocument(null);
    fetchThemeResearchReportDocument(themeId, reportVersionId)
      .then((nextDocument) => {
        if (!cancelled) setDocument(nextDocument);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(errorKind(reason));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [themeId, reportVersionId, retryVersion]);

  const backToTheme = () => onNavigate(`/theme-research/${encodeURIComponent(themeId)}`);

  if (loading) {
    return (
      <section className="workspace-band theme-report-reader theme-research-state" aria-busy="true">
        正在加载分析报告...
      </section>
    );
  }

  if (error) {
    const title = error === 'not_found'
      ? '报告不存在'
      : error === 'unavailable'
        ? '报告服务暂不可用'
        : '分析报告加载失败';
    const detail = error === 'not_found'
      ? '该报告版本不存在，或尚未通过审核发布。'
      : '暂时无法读取报告，请稍后重试。';
    return (
      <section className="workspace-band theme-report-reader theme-research-state" role="alert">
        <h1>{title}</h1>
        <p>{detail}</p>
        <div className="theme-report-actions">
          {error !== 'not_found' ? (
            <button className="icon-text-button" type="button" onClick={() => setRetryVersion((value) => value + 1)}>
              <RefreshCw size={16} aria-hidden="true" /> 重试
            </button>
          ) : null}
          <button className="icon-text-button" type="button" onClick={backToTheme}>
            <ArrowLeft size={16} aria-hidden="true" /> 返回主题概览
          </button>
        </div>
      </section>
    );
  }

  if (!document) {
    return (
      <section className="workspace-band theme-report-reader theme-research-state" role="alert">
        <h1>分析报告加载失败</h1>
        <p>报告响应不完整，请返回主题概览后重试。</p>
        <button className="icon-text-button" type="button" onClick={backToTheme}>返回主题概览</button>
      </section>
    );
  }

  return (
    <section className="theme-report-reader" aria-label="主题分析报告">
      <header className="theme-report-reader-header">
        <button className="icon-button" type="button" onClick={backToTheme} aria-label="返回主题概览">
          <ArrowLeft size={18} aria-hidden="true" />
        </button>
        <div>
          <span className={`theme-research-status ${document.status === 'published' ? 'is-positive' : 'is-neutral'}`}>
            {document.status === 'published' ? '已发布' : '历史版本'}
          </span>
          <h1>{document.title}</h1>
          <p>{document.summary}</p>
        </div>
        <div className="theme-report-reader-controls">
          {reports ? (
            <label className="theme-report-version-select">
              <span>报告历史版本</span>
              <select
                aria-label="报告历史版本"
                value={reportVersionId}
                onChange={(event) => onNavigate(reportPath(themeId, event.target.value))}
              >
                {reports.map((report) => (
                  <option key={report.report_version_id} value={report.report_version_id}>
                    {report.version} · {report.status === 'published' ? '当前发布' : '历史归档'} · {report.title}
                  </option>
                ))}
              </select>
            </label>
          ) : historyError ? (
            <span className="theme-report-history-error" role="status">历史版本暂不可用</span>
          ) : (
            <span className="theme-report-history-loading" role="status">正在加载历史版本...</span>
          )}
          {document.has_pdf ? (
            <a className="icon-text-button" href={themeResearchReportPdfUrl(themeId, reportVersionId)}>
              <Download size={16} aria-hidden="true" /> 下载 PDF
            </a>
          ) : null}
        </div>
      </header>
      <div className="theme-report-meta">
        <span>版本 {document.version}</span>
        <time aria-label="生成时间" dateTime={document.generated_at}>
          生成时间 {displayTimestamp(document.generated_at)}
        </time>
        <time aria-label="发布时间" dateTime={document.published_at}>
          发布时间 {displayTimestamp(document.published_at)}
        </time>
      </div>
      {/* Trust boundary: this HTML has been sanitized by the authenticated report service. */}
      <article className="theme-report-article" dangerouslySetInnerHTML={{ __html: document.html }} />
    </section>
  );
}
