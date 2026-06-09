import { useEffect, useState } from 'react';
import { fetchPlatformSummary, fetchStrategyCatalog } from '../api/client';
import type { PlatformSummary, ScoreRow, StrategyCatalogItem } from '../api/types';

type WorkspaceMode = 'data' | 'factors' | 'backtests' | 'strategy' | 'reports';

type HomeCockpitProps = {
  onNavigate: (mode: WorkspaceMode) => void;
};

function formatCount(value: number | undefined) {
  return typeof value === 'number' ? value.toLocaleString() : '-';
}

function formatScore(row: ScoreRow) {
  return typeof row.score_total === 'number' ? row.score_total.toFixed(1) : '-';
}

export function HomeCockpit({ onNavigate }: HomeCockpitProps) {
  const [summary, setSummary] = useState<PlatformSummary | null>(null);
  const [strategies, setStrategies] = useState<StrategyCatalogItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;
    setIsLoading(true);
    setError(null);

    Promise.all([fetchPlatformSummary(), fetchStrategyCatalog()])
      .then(([summaryPayload, strategyRows]) => {
        if (!ignore) {
          setSummary(summaryPayload);
          setStrategies(strategyRows);
          setIsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : String(err));
          setIsLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, []);

  return (
    <section className="home-cockpit" aria-label="Research Cockpit">
      <header className="workspace-header">
        <h1>Research Cockpit</h1>
        <p className="muted">Workspace summary for data coverage, research signals, and validation entry points.</p>
      </header>

      <nav className="quick-actions" aria-label="Quick actions">
        <button type="button" onClick={() => onNavigate('data')}>
          Data Explorer
        </button>
        <button type="button" onClick={() => onNavigate('factors')}>
          Factor Lab
        </button>
        <button type="button" onClick={() => onNavigate('backtests')}>
          Backtest Lab
        </button>
        <button type="button" onClick={() => onNavigate('strategy')}>
          Strategy Validation
        </button>
        <button type="button" onClick={() => onNavigate('reports')}>
          Reports
        </button>
      </nav>

      {error ? <p className="error-text">{error}</p> : null}

      <section className="cockpit-grid" aria-label="Platform summary">
        <div className="metric-card">
          <span>Latest Market Data</span>
          <strong>{summary?.latest_market_date ?? '-'}</strong>
        </div>
        <div className="metric-card">
          <span>Latest Factor Data</span>
          <strong>{summary?.latest_factor_date ?? '-'}</strong>
        </div>
        <div className="metric-card">
          <span>Latest Score Data</span>
          <strong>{summary?.latest_score_date ?? '-'}</strong>
        </div>
        <div className="metric-card">
          <span>Market Coverage</span>
          <strong>{formatCount(summary?.market_asset_count)}</strong>
        </div>
        <div className="metric-card">
          <span>Score Coverage</span>
          <strong>{formatCount(summary?.score_asset_count)}</strong>
        </div>
        <div className="metric-card">
          <span>Factor Coverage</span>
          <strong>{formatCount(summary?.factor_count)}</strong>
        </div>
      </section>

      <section className="workspace-band">
        <div className="section-heading">
          <h2>Built-in Strategies</h2>
          {isLoading ? <span className="muted">Loading...</span> : null}
        </div>
        <div className="strategy-card-grid">
          {strategies.map((strategy) => {
            const inputs = strategy.factor_groups.length > 0 ? strategy.factor_groups : strategy.signal_inputs;
            return (
              <article className="strategy-summary-card" key={strategy.strategy_id}>
                <div className="strategy-card-header">
                  <strong>{strategy.strategy_name}</strong>
                  <span>{strategy.status}</span>
                </div>
                <p>{strategy.description}</p>
                <small>{inputs.join(', ') || 'No signal inputs listed'}</small>
              </article>
            );
          })}
        </div>
      </section>

      <section className="workspace-band">
        <div className="section-heading">
          <h2>TopN Preview</h2>
          <span className="muted">candidate pool, not buy signal</span>
        </div>
        <div className="dense-list topn-preview-list">
          {(summary?.topn_preview ?? []).map((row) => (
            <div className="list-row" key={`${row.trade_date}-${row.asset_id}`}>
              <span>{row.rank}</span>
              <strong>{row.asset_id}</strong>
              <span>{formatScore(row)}</span>
            </div>
          ))}
          {!isLoading && (summary?.topn_preview ?? []).length === 0 ? (
            <p className="muted">No TopN preview rows available.</p>
          ) : null}
        </div>
      </section>
    </section>
  );
}
