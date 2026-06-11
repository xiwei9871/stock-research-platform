import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchMarketMonitorEod } from '../api/client';
import type { MarketMonitorPayload } from '../api/types';

function formatCount(value: number | null | undefined) {
  return typeof value === 'number' ? value.toLocaleString() : '-';
}

function formatScore(value: number | null | undefined) {
  return typeof value === 'number' ? value.toFixed(1) : '-';
}

export function MarketMonitorWorkspace() {
  const [payload, setPayload] = useState<MarketMonitorPayload | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const isMountedRef = useRef(false);
  const requestIdRef = useRef(0);

  const loadLatest = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setIsLoading(true);
    setError(null);
    try {
      const latestPayload = await fetchMarketMonitorEod({ topN: 5 });
      if (isMountedRef.current && requestId === requestIdRef.current) {
        setPayload(latestPayload);
      }
    } catch (err: unknown) {
      if (isMountedRef.current && requestId === requestIdRef.current) {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      if (isMountedRef.current && requestId === requestIdRef.current) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    void loadLatest();

    return () => {
      isMountedRef.current = false;
      requestIdRef.current += 1;
    };
  }, [loadLatest]);

  return (
    <section className="workspace-stack" aria-label="Market Monitor workspace">
      <header className="workspace-header workspace-header-row">
        <div>
          <h1>Market Monitor</h1>
          <p className="muted">EOD market state for the latest completed trading day.</p>
        </div>
        <button type="button" onClick={loadLatest} aria-label="Load Latest EOD">
          {isLoading ? 'Loading...' : 'Load Latest EOD'}
        </button>
      </header>

      {error ? <p className="error-text">{error}</p> : null}
      {payload?.warnings.map((warning) => <p className="warning-text" key={warning}>{warning}</p>)}

      <section className="status-strip" aria-label="Market monitor freshness">
        <div>
          <span>Mode</span>
          <strong>{payload?.freshness.label ?? 'Last Completed Trading Day'}</strong>
        </div>
        <div>
          <span>Trade Date</span>
          <strong>{payload?.trade_date || '-'}</strong>
        </div>
        <div>
          <span>Realtime</span>
          <strong>{payload?.freshness.is_realtime ? 'Yes' : 'No'}</strong>
        </div>
      </section>

      <section className="cockpit-grid">
        <div className="metric-card compact">
          <span>Market Assets</span>
          <strong>{formatCount(payload?.coverage.market_assets)}</strong>
        </div>
        <div className="metric-card compact">
          <span>Score Assets</span>
          <strong>{formatCount(payload?.coverage.score_assets)}</strong>
        </div>
        <div className="metric-card compact">
          <span>Factor Count</span>
          <strong>{formatCount(payload?.coverage.factor_count)}</strong>
        </div>
        <div className="metric-card compact">
          <span>TopN Preview</span>
          <strong>{formatCount(payload?.strategy_signal_summary.topn_preview_count)}</strong>
        </div>
      </section>

      <section className="workspace-panel">
        <div className="section-heading">
          <h2>Strategy Signal Summary</h2>
          <span className="status-chip neutral">EOD</span>
        </div>
        <div className="data-table">
          <div className="data-table-header three-col">
            <span>Rank</span>
            <span>Asset</span>
            <span>Score</span>
          </div>
          {(payload?.strategy_signal_summary.topn_preview ?? []).map((row) => (
            <div className="data-table-row three-col" key={`${row.trade_date}-${row.asset_id}`}>
              <span>{row.rank}</span>
              <strong>{row.asset_id}</strong>
              <span>{formatScore(row.score_total)}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="workspace-panel">
        <div className="section-heading">
          <h2>Generated Reports</h2>
          <span className="status-chip neutral">local artifacts</span>
        </div>
        <div className="report-list compact">
          {(payload?.generated_reports ?? []).map((report) => (
            <a href={report.path} key={report.path}>
              <span>{report.report_type}</span>
              <strong>{report.title}</strong>
            </a>
          ))}
        </div>
      </section>
    </section>
  );
}
