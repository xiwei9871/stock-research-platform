import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { fetchOverview } from '../api/client';
import type { ReportLink } from '../api/types';
import { ReportPanel } from './ReportPanel';

const DEFAULT_TRADE_DATE = '2026-06-08';
const SCORE_VERSION = 'manual_v1';
const WATCHLIST_ID = 'default';
const TOP_N = 5;

type ReportsWorkspaceProps = {
  title?: string;
  description?: string;
};

export function ReportsWorkspace({
  title = 'Reports',
  description = 'Local research artifacts and generated reports.'
}: ReportsWorkspaceProps = {}) {
  const [tradeDate, setTradeDate] = useState(DEFAULT_TRADE_DATE);
  const [reports, setReports] = useState<ReportLink[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isMountedRef = useRef(false);
  const requestIdRef = useRef(0);

  const loadReports = useCallback((nextTradeDate: string) => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setIsLoading(true);
    setError(null);

    fetchOverview({
      tradeDate: nextTradeDate,
      scoreVersion: SCORE_VERSION,
      watchlistId: WATCHLIST_ID,
      topN: TOP_N
    })
      .then((overview) => {
        if (isMountedRef.current && requestId === requestIdRef.current) {
          setReports(overview.reports);
        }
      })
      .catch((err: unknown) => {
        if (isMountedRef.current && requestId === requestIdRef.current) {
          setError(err instanceof Error ? err.message : String(err));
          setReports([]);
        }
      })
      .finally(() => {
        if (isMountedRef.current && requestId === requestIdRef.current) {
          setIsLoading(false);
        }
      });
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    loadReports(DEFAULT_TRADE_DATE);

    return () => {
      isMountedRef.current = false;
      requestIdRef.current += 1;
    };
  }, [loadReports]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    loadReports(tradeDate);
  }

  return (
    <section className="reports-workspace" aria-label="Reports workspace">
      <header className="workspace-header">
        <h1>{title}</h1>
        <p className="muted">{description}</p>
      </header>

      <form className="reports-toolbar" onSubmit={handleSubmit}>
        <input
          aria-label="report trade date"
          type="date"
          value={tradeDate}
          onChange={(event) => setTradeDate(event.target.value)}
        />
        <button type="submit">Load Reports</button>
        {isLoading ? <span className="muted">Loading reports...</span> : null}
      </form>

      {error ? <p className="error-text">{error}</p> : null}
      <ReportPanel reports={reports} isLoading={isLoading} />
    </section>
  );
}
