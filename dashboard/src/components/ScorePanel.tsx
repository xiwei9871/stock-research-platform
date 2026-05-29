import type { ScoreRow, WatchlistSignalRow } from '../api/types';

type ScorePanelProps = {
  score: ScoreRow | null;
  signals: WatchlistSignalRow[];
};

export function ScorePanel({ score, signals }: ScorePanelProps) {
  return (
    <section className="inspector-section">
      <h2>Asset Review</h2>
      {score ? (
        <div className="metric-grid">
          <span>Rank</span>
          <strong>{score.rank}</strong>
          <span>Score</span>
          <strong>{score.score_total.toFixed(1)}</strong>
        </div>
      ) : (
        <p className="muted">No score for selected date.</p>
      )}
      <div className="tag-stack">
        {signals.flatMap((signal) =>
          signal.risk_tags.map((tag) => (
            <span className="risk-tag" key={`${signal.watchlist_id}-${tag}`}>
              {tag}
            </span>
          ))
        )}
      </div>
    </section>
  );
}
