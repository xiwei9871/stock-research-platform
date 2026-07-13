import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { fetchResearchReportDocument, fetchResearchReportSummary, fetchResearchReports } from '../api/client';
import type {
  ResearchReportDocument,
  ResearchReportItem,
  ResearchReportResponse,
  ResearchReportSummary
} from '../api/types';
import type { StockEntryContext } from './StockWorkspace';

const DEFAULT_START_DATE = '2026-03-01';
const PAGE_LIMIT = 50;

type ReportFilters = {
  q: string;
  broker: string;
  rating: string;
  sourceName: string;
  startDate: string;
  endDate: string;
  hasTargetPrice: boolean;
};

type ResearchReportsWorkspaceProps = {
  initialQuery?: string;
  initialEventKey?: string;
  initialReportId?: string;
  initialTradeDate?: string;
  onOpenAsset?: (assetId: string, context: StockEntryContext) => void;
};

function formatCount(value: number | null | undefined) {
  return typeof value === 'number' ? value.toLocaleString('en-US') : '-';
}

function getTodayDate() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function formatText(value: string | null | undefined) {
  return value?.trim() ? value : '-';
}

function formatCurrency(value: number | null | undefined) {
  return typeof value === 'number' ? value.toFixed(2) : '-';
}

function formatPercent(value: number | null | undefined) {
  return typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : '-';
}

function formatInlineSummary(report: ResearchReportItem) {
  const summary =
    report.company_view?.trim() ||
    report.raw_summary?.trim() ||
    report.industry_view?.trim() ||
    report.risk_summary?.trim() ||
    deriveSummaryFromReportTitle(report.report_title) ||
    '';
  if (!summary) {
    return '摘要：暂无摘要，点击标题阅读全文。';
  }
  const normalized = summary.replace(/\s+/g, ' ');
  return `摘要：${normalized.length > 120 ? `${normalized.slice(0, 120)}...` : normalized}`;
}

function deriveSummaryFromReportTitle(title: string | null | undefined) {
  const cleanedTitle = String(title || '')
    .replace(/\.(pdf|PDF)$/u, '')
    .replace(/[：:]/gu, '_')
    .trim();
  if (!cleanedTitle) return '';

  const rawParts = cleanedTitle
    .split(/[_／/]+/u)
    .map((part) => part.trim())
    .filter(Boolean);
  const parts = rawParts.length ? rawParts : [cleanedTitle];
  const semanticParts = parts
    .map((part, index) => {
      const normalized = part.replace(/\s+/g, ' ').trim();
      if (isReportTitleNoise(normalized)) return '';
      if (index === 0 && normalized.includes('-')) {
        return normalized
          .split('-')
          .map((segment) => segment.trim())
          .filter((segment) => segment && !isReportTitleNoise(segment))
          .at(-1) || '';
      }
      return normalized;
    })
    .filter((part) => part && !isReportTitleNoise(part));

  return semanticParts.slice(0, 3).join('；');
}

function isReportTitleNoise(part: string) {
  const normalized = part.trim();
  if (!normalized) return true;
  if (/^\d{4}[-.]?\d{2}[-.]?\d{2}$/u.test(normalized)) return true;
  if (/^\d{1,4}$/u.test(normalized)) return true;
  if (/^\d{6,8}$/u.test(normalized)) return true;
  if (/^\d+(?:\.\d+)?\s*(?:页|mb|MB|Mb)$/u.test(normalized)) return true;
  if (/^\d{6}\.(?:SH|SZ|BJ)$/u.test(normalized)) return true;
  if (/^[\u4e00-\u9fa5]{2,8}证券$/u.test(normalized)) return true;
  if (/^[\u4e00-\u9fa5A-Za-z]+[（(]?\d{6}[）)]?$/u.test(normalized)) return true;
  return [
    '深度报告',
    '深度研究报告',
    '公司深度报告',
    '公司研究报告',
    '首次覆盖',
    '首次覆盖报告',
    '公司首次覆盖报告',
    '跟踪报告',
    '点评报告',
    '研究报告'
  ].includes(normalized);
}

function buildReportParams(filters: ReportFilters) {
  const params: {
    q?: string;
    broker?: string;
    rating?: string;
    source_name?: string;
    start_date?: string;
    end_date?: string;
    has_target_price?: boolean;
    limit: number;
    offset: number;
  } = {
    limit: PAGE_LIMIT,
    offset: 0
  };

  if (filters.q.trim()) params.q = filters.q.trim();
  if (filters.broker.trim()) params.broker = filters.broker.trim();
  if (filters.rating.trim()) params.rating = filters.rating.trim();
  if (filters.sourceName.trim()) params.source_name = filters.sourceName.trim();
  if (filters.startDate) params.start_date = filters.startDate;
  if (filters.endDate) params.end_date = filters.endDate;
  if (filters.hasTargetPrice) params.has_target_price = true;

  return params;
}

function getReportAssetId(report: ResearchReportItem) {
  return report.asset_id || report.ts_code;
}

function buildReportStockContext(report: ResearchReportItem): StockEntryContext {
  const assetId = getReportAssetId(report);
  return {
    sourceWorkspace: 'researchReports',
    assetId,
    eventKey: report.event_key,
    reportId: report.report_id,
    query: report.report_title || report.stock_name || report.ts_code || assetId
  };
}

export function ResearchReportsWorkspace({
  initialQuery = '',
  initialEventKey,
  initialReportId,
  initialTradeDate,
  onOpenAsset
}: ResearchReportsWorkspaceProps = {}) {
  const [summary, setSummary] = useState<ResearchReportSummary | null>(null);
  const [reportsPayload, setReportsPayload] = useState<ResearchReportResponse | null>(null);
  const [readerReport, setReaderReport] = useState<ResearchReportItem | null>(null);
  const [isReaderFillScreen, setIsReaderFillScreen] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<ResearchReportDocument | null>(null);
  const [q, setQ] = useState(initialQuery);
  const [broker, setBroker] = useState('');
  const [rating, setRating] = useState('');
  const [sourceName, setSourceName] = useState('');
  const [startDate, setStartDate] = useState(DEFAULT_START_DATE);
  const [endDate, setEndDate] = useState(getTodayDate);
  const [hasTargetPrice, setHasTargetPrice] = useState(false);
  const [isSummaryLoading, setIsSummaryLoading] = useState(false);
  const [isReportsLoading, setIsReportsLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [reportsError, setReportsError] = useState<string | null>(null);
  const [documentError, setDocumentError] = useState<string | null>(null);
  const [isDocumentLoading, setIsDocumentLoading] = useState(false);
  const mountedRef = useRef(false);
  const reportsRequestIdRef = useRef(0);
  const documentRequestIdRef = useRef(0);
  const consumedDeepLinkRef = useRef('');
  const filtersRef = useRef<ReportFilters>({
    q: initialQuery,
    broker: '',
    rating: '',
    sourceName: '',
    startDate: DEFAULT_START_DATE,
    endDate: getTodayDate(),
    hasTargetPrice: false
  });

  const isLatestReportsRequest = useCallback((requestId: number) => {
    return mountedRef.current && requestId === reportsRequestIdRef.current;
  }, []);

  const loadReports = useCallback(
    async (nextFilters: ReportFilters) => {
      const requestId = reportsRequestIdRef.current + 1;
      reportsRequestIdRef.current = requestId;

      setIsReportsLoading(true);
      setReportsError(null);

      try {
        const nextPayload = await fetchResearchReports(buildReportParams(nextFilters));
        if (!isLatestReportsRequest(requestId)) {
          return;
        }
        setReportsPayload(nextPayload);
      } catch (err: unknown) {
        if (!isLatestReportsRequest(requestId)) {
          return;
        }
        setReportsError(err instanceof Error ? err.message : String(err));
        setReportsPayload(null);
      } finally {
        if (isLatestReportsRequest(requestId)) {
          setIsReportsLoading(false);
        }
      }
    },
    [isLatestReportsRequest]
  );

  useEffect(() => {
    mountedRef.current = true;
    setIsSummaryLoading(true);
    setSummaryError(null);

    fetchResearchReportSummary()
      .then((nextSummary) => {
        if (mountedRef.current) {
          setSummary(nextSummary);
        }
      })
      .catch((err: unknown) => {
        if (mountedRef.current) {
          setSummaryError(err instanceof Error ? err.message : String(err));
          setSummary(null);
        }
      })
      .finally(() => {
        if (mountedRef.current) {
          setIsSummaryLoading(false);
        }
      });

    return () => {
      mountedRef.current = false;
      reportsRequestIdRef.current += 1;
      documentRequestIdRef.current += 1;
    };
  }, []);

  useEffect(() => {
    filtersRef.current = { q, broker, rating, sourceName, startDate, endDate, hasTargetPrice };
  });

  useEffect(() => {
    const nextFilters = { ...filtersRef.current, q: initialQuery };
    filtersRef.current = nextFilters;
    setQ(initialQuery);
    void loadReports(nextFilters);
  }, [initialQuery, loadReports]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextFilters = { q, broker, rating, sourceName, startDate, endDate, hasTargetPrice };
    filtersRef.current = nextFilters;
    void loadReports(nextFilters);
  };

  const reports = reportsPayload?.items ?? [];

  useEffect(() => {
    const deepLinkToken = `${initialEventKey ?? ''}|${initialReportId ?? ''}`;
    const shouldConsumeDeepLink = deepLinkToken !== '|' && consumedDeepLinkRef.current !== deepLinkToken;

    if (!reports.length) return;

    if (shouldConsumeDeepLink) {
      const eventMatch = initialEventKey
        ? reports.find((report) => report.event_key === initialEventKey)
        : undefined;
      const reportIdMatch = initialReportId
        ? reports.find((report) => report.report_id === initialReportId)
        : undefined;
      const deepLinkedReport = eventMatch ?? reportIdMatch;

      if (deepLinkedReport) {
        consumedDeepLinkRef.current = deepLinkToken;
        setReaderReport(deepLinkedReport);
        return;
      }

      consumedDeepLinkRef.current = deepLinkToken;
    }
  }, [reports, initialEventKey, initialReportId]);

  useEffect(() => {
    const reportId = readerReport?.report_id;
    const requestId = documentRequestIdRef.current + 1;
    documentRequestIdRef.current = requestId;

    if (!reportId) {
      setSelectedDocument(null);
      setDocumentError(null);
      setIsDocumentLoading(false);
      return;
    }

    setSelectedDocument(null);
    setDocumentError(null);
    setIsDocumentLoading(true);

    fetchResearchReportDocument(reportId)
      .then((document) => {
        if (mountedRef.current && requestId === documentRequestIdRef.current) {
          setSelectedDocument(document);
        }
      })
      .catch((err: unknown) => {
        if (mountedRef.current && requestId === documentRequestIdRef.current) {
          setDocumentError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (mountedRef.current && requestId === documentRequestIdRef.current) {
          setIsDocumentLoading(false);
        }
      });
  }, [readerReport]);

  if (readerReport) {
    const readerAssetId = getReportAssetId(readerReport);
    return (
      <section
        className={`research-report-fullscreen${isReaderFillScreen ? ' is-fill-screen' : ''}`}
        aria-label="Research report full-screen reader"
      >
        <header className="research-report-reader-toolbar">
          <button
            type="button"
            className="link-chip"
            onClick={() => {
              setIsReaderFillScreen(false);
              setReaderReport(null);
            }}
          >
            返回研报列表
          </button>
          <div className="research-report-reader-title">
            <span>
              {formatText(readerReport.stock_name)} {formatText(readerReport.ts_code)}
            </span>
            <h1>{readerReport.report_title}</h1>
            <small>
              {formatText(readerReport.broker)} / {formatText(readerReport.publish_date)}
            </small>
          </div>
          <div className="research-report-reader-actions">
            <button
              type="button"
              className="link-chip"
              aria-pressed={isReaderFillScreen}
              onClick={() => setIsReaderFillScreen((current) => !current)}
            >
              {isReaderFillScreen ? '退出铺满' : '铺满屏幕'}
            </button>
            {readerAssetId ? (
              <button
                type="button"
                className="link-chip"
                aria-label={`Open Stock Detail for ${readerReport.stock_name || readerReport.ts_code}`}
                onClick={() => {
                  onOpenAsset?.(readerAssetId, { ...buildReportStockContext(readerReport), tradeDate: initialTradeDate });
                }}
              >
                个股工作台
              </button>
            ) : null}
            {selectedDocument?.has_pdf && selectedDocument.pdf_url ? (
              <a href={selectedDocument.pdf_url} target="_blank" rel="noreferrer">
                打开PDF
              </a>
            ) : null}
            {(selectedDocument?.source_url || readerReport.source_url) ? (
              <a href={selectedDocument?.source_url || readerReport.source_url} target="_blank" rel="noreferrer">
                来源链接
              </a>
            ) : null}
          </div>
        </header>

        <main className="research-report-reader-main">
          {isDocumentLoading ? <p className="muted">正在加载研报文档...</p> : null}
          {documentError ? <p className="error-text">{documentError}</p> : null}
          {!isDocumentLoading && selectedDocument?.has_pdf && selectedDocument.pdf_url ? (
            <iframe
              className="research-report-fullscreen-frame"
              src={selectedDocument.pdf_url}
              title={`${readerReport.report_title} PDF`}
            />
          ) : null}
          {!isDocumentLoading && selectedDocument && !selectedDocument.has_pdf ? (
            <div className="research-report-fullscreen-empty">
              <strong>暂无本地PDF</strong>
              <p>可打开来源链接查看原文，或等待研报同步任务补齐PDF文件。</p>
              {selectedDocument.warnings.map((warning) => (
                <span className="muted" key={warning}>
                  {warning}
                </span>
              ))}
            </div>
          ) : null}
        </main>
      </section>
    );
  }

  return (
    <section className="workspace-stack" aria-label="Research Reports workspace">
      <header className="workspace-header">
        <h1>研报</h1>
        <p className="muted">只读研报工作台；可读研报指已绑定本地 PDF、可打开正文的研报。</p>
      </header>

      <section className="stock-summary-strip" aria-label="Research report summary">
        <div>
          <span>可读研报</span>
          <strong>{formatCount(summary?.readable_report_count ?? summary?.pdf_report_count)}</strong>
        </div>
        <div>
          <span>覆盖股票</span>
          <strong>{formatCount(summary?.covered_stocks)}</strong>
        </div>
        <div>
          <span>网页索引</span>
          <strong>{formatCount(summary?.web_index_report_count)}</strong>
        </div>
        <div>
          <span>最新发布</span>
          <strong>{formatText(summary?.latest_publish_date)}</strong>
        </div>
        <div>
          <span>来源</span>
          <strong>{formatCount(summary?.source_count)}</strong>
        </div>
        <div>
          <span>最新特征</span>
          <strong>{formatText(summary?.latest_feature_date)}</strong>
        </div>
      </section>

      <form className="compact-toolbar research-report-toolbar" onSubmit={handleSubmit}>
        <label>
          股票/标题关键词
          <input
            aria-label="股票/标题关键词"
            placeholder="股票代码、名称、标题关键词"
            value={q}
            onChange={(event) => setQ(event.target.value)}
          />
        </label>
        <label>
          券商
          <input aria-label="券商" value={broker} onChange={(event) => setBroker(event.target.value)} />
        </label>
        <label>
          评级
          <input aria-label="评级" value={rating} onChange={(event) => setRating(event.target.value)} />
        </label>
        <label>
          来源
          <input
            aria-label="来源"
            value={sourceName}
            onChange={(event) => setSourceName(event.target.value)}
          />
        </label>
        <label>
          开始日期
          <input
            aria-label="开始日期"
            type="date"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
          />
        </label>
        <label>
          结束日期
          <input
            aria-label="结束日期"
            type="date"
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
          />
        </label>
        <label className="research-report-inline-check">
          <input
            aria-label="仅看有目标价"
            type="checkbox"
            checked={hasTargetPrice}
            onChange={(event) => setHasTargetPrice(event.target.checked)}
          />
          仅看有目标价
        </label>
        <button type="submit">搜索研报</button>
        {isReportsLoading ? <span className="muted">正在加载研报...</span> : null}
      </form>

      {summaryError ? <p className="error-text">{summaryError}</p> : null}
      {reportsError ? <p className="error-text">{reportsError}</p> : null}
      {isSummaryLoading ? <p className="muted">正在加载统计...</p> : null}

      <section className="research-report-layout">
        <article className="workspace-band" aria-label="Research report results">
          <div className="section-heading">
            <h2>研报列表</h2>
            <span className="muted">
              共 {formatCount(reportsPayload?.total)} 条 / 当前显示 {reports.length}
            </span>
          </div>
          {reports.length > 0 ? (
            <div className="research-report-table-scroll">
              <table className="compact-table research-report-table">
                <thead>
                  <tr>
                    <th>发布日期</th>
                    <th>研报</th>
                    <th>券商</th>
                    <th>评级</th>
                    <th>目标价</th>
                  </tr>
                </thead>
                <tbody>
                  {reports.map((item) => (
                    <tr key={item.event_key}>
                      <td>{formatText(item.publish_date)}</td>
                      <td>
                        <button
                          type="button"
                          aria-label={`Open report ${item.report_title}`}
                          onClick={() => setReaderReport(item)}
                        >
                          {item.report_title}
                        </button>
                        <span>
                          {formatText(item.ts_code)} / {formatText(item.stock_name)}
                        </span>
                        <span className="research-report-inline-summary">{formatInlineSummary(item)}</span>
                        {getReportAssetId(item) ? (
                          <button
                            type="button"
                            className="link-chip"
                            aria-label={`Open Stock Detail for ${item.stock_name || item.ts_code}`}
                            onClick={(event) => {
                              event.stopPropagation();
                              const assetId = getReportAssetId(item);
                              onOpenAsset?.(assetId, { ...buildReportStockContext(item), tradeDate: initialTradeDate });
                            }}
                          >
                            个股工作台
                          </button>
                        ) : null}
                      </td>
                      <td>{formatText(item.broker)}</td>
                      <td>
                        <span className="status-chip neutral">{formatText(item.rating)}</span>
                      </td>
                      <td>
                        {formatCurrency(item.target_price)}
                        <span className="muted"> {formatPercent(item.target_upside)}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          {!isReportsLoading && reports.length === 0 ? <p className="muted">No matching research reports.</p> : null}
          {reportsPayload?.warnings.map((warning) => (
            <p className="muted" key={warning}>
              {warning}
            </p>
          ))}
        </article>

      </section>
    </section>
  );
}
