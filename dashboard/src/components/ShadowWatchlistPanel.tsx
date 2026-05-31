import type { ShadowWatchlistRow } from '../api/types';

type ShadowWatchlistPanelProps = {
  rows: ShadowWatchlistRow[];
  isLoading?: boolean;
};

export function ShadowWatchlistPanel({ rows, isLoading = false }: ShadowWatchlistPanelProps) {
  return (
    <section className="inspector-section">
      <h2>Shadow Watchlist</h2>
      {isLoading ? (
        <p className="muted">Loading shadow watchlist...</p>
      ) : rows.length === 0 ? (
        <p className="muted">No shadow watchlist candidates for selected range.</p>
      ) : (
        <div className="decision-list">
          {rows.map((row) => (
            <article className="decision-row analytics-row" key={row.shadow_candidate_id}>
              <div>
                <strong>{row.stock_name || row.asset_id}</strong>
                <span>{row.status}</span>
              </div>
              <div className="outcome-metrics">
                <span>{row.candidate_date}</span>
                <span>{row.shadow_layer}</span>
                <span>Asset {row.asset_id}</span>
              </div>
              <p>{row.candidate_reason}</p>
              <p>{row.source_p11_replay_run_id}</p>
              <p>{row.source_p10_proposal_run_id}</p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
