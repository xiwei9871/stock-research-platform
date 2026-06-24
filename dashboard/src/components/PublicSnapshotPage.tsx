import { useEffect, useState } from 'react';

import { fetchPublicSnapshot } from '../api/client';
import type { PublicSnapshot } from '../api/types';

function formatValue(value: unknown): string {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? String(value) : 'n/a';
  }
  if (typeof value === 'string' && value.trim()) {
    return value;
  }
  return 'n/a';
}

export function PublicSnapshotPage() {
  const [snapshot, setSnapshot] = useState<PublicSnapshot | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetchPublicSnapshot().then((nextSnapshot) => {
      if (!cancelled) {
        setSnapshot(nextSnapshot);
      }
    });

    return () => {
      cancelled = true;
    };
  }, []);

  if (!snapshot) {
    return <main className="public-shell">Loading public snapshot...</main>;
  }

  const topPreview = snapshot.topn_preview.slice(0, 5);
  const marketState = formatValue(snapshot.market_state?.state);
  const coverageSummary = formatValue(snapshot.coverage_summary?.core);
  const approvedCount = formatValue(snapshot.factor_gate_summary?.approved_count);

  return (
    <main className="public-shell">
      <div className="public-layout">
        <section className="public-hero">
          <span className={`public-badge public-badge--${snapshot.status}`}>{snapshot.status}</span>
          <span className="public-kicker">Release-safe daily market view</span>
          <h1>Daily A-share Snapshot</h1>
          <p>{snapshot.status_text}</p>
        </section>

        <section className="public-meta-grid" aria-label="Public snapshot metadata">
          <article className="public-card">
            <h2>Release window</h2>
            <dl>
              <div>
                <dt>Trade date</dt>
                <dd>{snapshot.trade_date}</dd>
              </div>
              <div>
                <dt>Latest ready trade date</dt>
                <dd>{snapshot.latest_ready_trade_date ?? 'n/a'}</dd>
              </div>
              <div>
                <dt>Published at</dt>
                <dd>{snapshot.published_at ?? 'Pending publish'}</dd>
              </div>
            </dl>
          </article>

          <article className="public-card">
            <h2>Market pulse</h2>
            <dl>
              <div>
                <dt>Market state</dt>
                <dd>{marketState}</dd>
              </div>
              <div>
                <dt>Coverage</dt>
                <dd>{coverageSummary}</dd>
              </div>
              <div>
                <dt>Approved count</dt>
                <dd>{approvedCount}</dd>
              </div>
            </dl>
          </article>
        </section>

        <section className="public-summary-grid">
          <article className="public-card">
            <h3>Top preview</h3>
            <ul className="public-preview-list">
              {topPreview.length > 0 ? (
                topPreview.map((row, index) => (
                  <li
                    key={`${formatValue(row.asset_id)}-${index}`}
                    className="public-preview-item"
                  >
                    <strong>{formatValue(row.stock_name)}</strong>
                    <span>{formatValue(row.asset_id)}</span>
                    <span>Score {formatValue(row.score_total)}</span>
                  </li>
                ))
              ) : (
                <li className="public-notes-empty">No preview available.</li>
              )}
            </ul>
          </article>

          <article className="public-card">
            <h3>Notes</h3>
            {snapshot.notes.length > 0 ? (
              <ul className="public-notes-list">
                {snapshot.notes.map((note, index) => (
                  <li key={`${note}-${index}`}>{note}</li>
                ))}
              </ul>
            ) : (
              <p className="public-notes-empty">No additional public notes.</p>
            )}
          </article>
        </section>
      </div>
    </main>
  );
}
