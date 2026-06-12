import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { fetchResearchReportSummary, fetchResearchReports } from '../api/client';
import type { ResearchReportItem, ResearchReportResponse, ResearchReportSummary } from '../api/types';

const DEFAULT_START_DATE = '2026-03-01';
const DEFAULT_END_DATE = '2026-06-11';
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

function formatCount(value: number | null | undefined) {
  return typeof value === 'number' ? value.toLocaleString('en-US') : '-';
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

export function ResearchReportsWorkspace() {
  const [summary, setSummary] = useState<ResearchReportSummary | null>(null);
  const [reportsPayload, setReportsPayload] = useState<ResearchReportResponse | null>(null);
  const [selectedReport, setSelectedReport] = useState<ResearchReportItem | null>(null);
  const [q, setQ] = useState('');
  const [broker, setBroker] = useState('');
  const [rating, setRating] = useState('');
  const [sourceName, setSourceName] = useState('');
  const [startDate, setStartDate] = useState(DEFAULT_START_DATE);
  const [endDate, setEndDate] = useState(DEFAULT_END_DATE);
  const [hasTargetPrice, setHasTargetPrice] = useState(false);
  const [isSummaryLoading, setIsSummaryLoading] = useState(false);
  const [isReportsLoading, setIsReportsLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [reportsError, setReportsError] = useState<string | null>(null);
  const mountedRef = useRef(false);
  const reportsRequestIdRef = useRef(0);

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
        setSelectedReport((current) => {
          if (!current) {
            return null;
          }
          return nextPayload.items.find((item) => item.report_id === current.report_id) ?? null;
        });
      } catch (err: unknown) {
        if (!isLatestReportsRequest(requestId)) {
          return;
        }
        setReportsError(err instanceof Error ? err.message : String(err));
        setReportsPayload(null);
        setSelectedReport(null);
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

    void loadReports({
      q: '',
      broker: '',
      rating: '',
      sourceName: '',
      startDate: DEFAULT_START_DATE,
      endDate: DEFAULT_END_DATE,
      hasTargetPrice: false
    });

    return () => {
      mountedRef.current = false;
      reportsRequestIdRef.current += 1;
    };
  }, [loadReports]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void loadReports({ q, broker, rating, sourceName, startDate, endDate, hasTargetPrice });
  };

  const reports = reportsPayload?.items ?? [];

  return (
    <section className="workspace-stack" aria-label="Research Reports workspace">
      <header className="workspace-header">
        <h1>Research Reports</h1>
        <p className="muted">Read-only broker research metadata workspace for report search, coverage, and source review.</p>
      </header>

      <section className="stock-summary-strip" aria-label="Research report summary">
        <div>
          <span>Total Reports</span>
          <strong>{formatCount(summary?.total_reports)}</strong>
        </div>
        <div>
          <span>Covered Stocks</span>
          <strong>{formatCount(summary?.covered_stocks)}</strong>
        </div>
        <div>
          <span>Latest Publish</span>
          <strong>{formatText(summary?.latest_publish_date)}</strong>
        </div>
        <div>
          <span>Sources</span>
          <strong>{formatCount(summary?.source_count)}</strong>
        </div>
        <div>
          <span>Latest Feature</span>
          <strong>{formatText(summary?.latest_feature_date)}</strong>
        </div>
      </section>

      <form className="compact-toolbar research-report-toolbar" onSubmit={handleSubmit}>
        <label>
          Query
          <input aria-label="research report query" value={q} onChange={(event) => setQ(event.target.value)} />
        </label>
        <label>
          Broker
          <input aria-label="research report broker" value={broker} onChange={(event) => setBroker(event.target.value)} />
        </label>
        <label>
          Rating
          <input aria-label="research report rating" value={rating} onChange={(event) => setRating(event.target.value)} />
        </label>
        <label>
          Source
          <input
            aria-label="research report source"
            value={sourceName}
            onChange={(event) => setSourceName(event.target.value)}
          />
        </label>
        <label>
          Start
          <input
            aria-label="research report start date"
            type="date"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
          />
        </label>
        <label>
          End
          <input
            aria-label="research report end date"
            type="date"
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
          />
        </label>
        <label className="research-report-inline-check">
          <input
            aria-label="research report has target price"
            type="checkbox"
            checked={hasTargetPrice}
            onChange={(event) => setHasTargetPrice(event.target.checked)}
          />
          Has target price
        </label>
        <button type="submit">Search Reports</button>
        {isReportsLoading ? <span className="muted">Loading reports...</span> : null}
      </form>

      {summaryError ? <p className="error-text">{summaryError}</p> : null}
      {reportsError ? <p className="error-text">{reportsError}</p> : null}
      {isSummaryLoading ? <p className="muted">Loading summary...</p> : null}

      <section className="research-report-layout">
        <article className="workspace-band" aria-label="Research report results">
          <div className="section-heading">
            <h2>Report Results</h2>
            <span className="muted">
              {formatCount(reportsPayload?.total)} total / showing {reports.length}
            </span>
          </div>
          {reports.length > 0 ? (
            <div className="research-report-table-scroll">
              <table className="compact-table research-report-table">
                <thead>
                  <tr>
                    <th>Publish</th>
                    <th>Report</th>
                    <th>Broker</th>
                    <th>Rating</th>
                    <th>Target</th>
                  </tr>
                </thead>
                <tbody>
                  {reports.map((item) => (
                    <tr key={item.report_id}>
                      <td>{formatText(item.publish_date)}</td>
                      <td>
                        <button
                          type="button"
                          aria-label={`Open report ${item.report_title}`}
                          onClick={() => setSelectedReport(item)}
                        >
                          {item.report_title}
                        </button>
                        <span>
                          {formatText(item.ts_code)} / {formatText(item.stock_name)}
                        </span>
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

        <aside className="workspace-band research-report-detail" aria-label="Research report detail">
          {selectedReport ? (
            <>
              <div className="section-heading">
                <h2>{selectedReport.report_title}</h2>
                <span className="status-chip neutral">{formatText(selectedReport.source_name)}</span>
              </div>
              <dl className="research-report-detail-grid">
                <div>
                  <dt>Stock</dt>
                  <dd>
                    {formatText(selectedReport.stock_name)} {formatText(selectedReport.ts_code)}
                  </dd>
                </div>
                <div>
                  <dt>Broker</dt>
                  <dd>{formatText(selectedReport.broker)}</dd>
                </div>
                <div>
                  <dt>Analyst</dt>
                  <dd>{formatText(selectedReport.analyst)}</dd>
                </div>
                <div>
                  <dt>Rating</dt>
                  <dd>
                    {formatText(selectedReport.rating)} / {formatText(selectedReport.rating_change)}
                  </dd>
                </div>
                <div>
                  <dt>Target</dt>
                  <dd>
                    {formatCurrency(selectedReport.target_price)} / {formatPercent(selectedReport.target_upside)}
                  </dd>
                </div>
                <div>
                  <dt>Published</dt>
                  <dd>{formatText(selectedReport.publish_date)}</dd>
                </div>
              </dl>
              <section>
                <h3>Company View</h3>
                <p>{formatText(selectedReport.company_view || selectedReport.raw_summary)}</p>
              </section>
              <section>
                <h3>Industry View</h3>
                <p>{formatText(selectedReport.industry_view)}</p>
              </section>
              <section>
                <h3>Risk Summary</h3>
                <p>{formatText(selectedReport.risk_summary)}</p>
              </section>
              <div className="research-report-button-row">
                {selectedReport.source_url ? (
                  <a href={selectedReport.source_url} target="_blank" rel="noreferrer">
                    Open Source
                  </a>
                ) : null}
                <span className="muted">{formatText(selectedReport.copyright_note)}</span>
              </div>
            </>
          ) : (
            <p className="muted">Select a report to view metadata and notes.</p>
          )}
        </aside>
      </section>
    </section>
  );
}
