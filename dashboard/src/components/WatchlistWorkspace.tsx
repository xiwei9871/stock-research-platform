import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchWatchlistSignals } from '../api/client';
import type { WatchlistSignalRow } from '../api/types';

const DEFAULT_WATCHLIST_ID = 'default';
const DEFAULT_TRADE_DATE = '2026-06-08';

type WatchlistWorkspaceProps = {
  onOpenAsset?: (assetId: string) => void;
};

function formatTags(tags: string[]) {
  return tags.length > 0 ? tags.join(', ') : '-';
}

function reasonField(row: WatchlistSignalRow, key: string) {
  const value = row.reason_json[key];
  return typeof value === 'string' ? value : '-';
}

function rowMatchesQuery(row: WatchlistSignalRow, query: string) {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return [
    row.asset_id,
    row.stock_code,
    row.stock_name,
    row.primary_signal,
    ...row.signal_tags,
    ...row.risk_tags
  ].some((value) => value.toLowerCase().includes(needle));
}

export function WatchlistWorkspace({ onOpenAsset }: WatchlistWorkspaceProps) {
  const [watchlistId, setWatchlistId] = useState(DEFAULT_WATCHLIST_ID);
  const [tradeDate, setTradeDate] = useState(DEFAULT_TRADE_DATE);
  const [status, setStatus] = useState('all');
  const [minPriority, setMinPriority] = useState(0);
  const [query, setQuery] = useState('');
  const [rows, setRows] = useState<WatchlistSignalRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(false);
  const requestIdRef = useRef(0);

  const loadQueue = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setIsLoading(true);
    setError(null);

    try {
      const nextRows = await fetchWatchlistSignals(watchlistId, tradeDate);
      if (mountedRef.current && requestId === requestIdRef.current) {
        setRows(nextRows);
      }
    } catch (err: unknown) {
      if (mountedRef.current && requestId === requestIdRef.current) {
        setRows([]);
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      if (mountedRef.current && requestId === requestIdRef.current) {
        setIsLoading(false);
      }
    }
  }, [tradeDate, watchlistId]);

  useEffect(() => {
    mountedRef.current = true;
    void loadQueue();
    return () => {
      mountedRef.current = false;
      requestIdRef.current += 1;
    };
  }, [loadQueue]);

  const visibleRows = useMemo(
    () =>
      rows.filter((row) => {
        const statusMatch = status === 'all' || row.primary_signal === status;
        const priorityMatch = row.priority >= minPriority;
        return statusMatch && priorityMatch && rowMatchesQuery(row, query);
      }),
    [minPriority, query, rows, status]
  );

  return (
    <section className="workspace-stack" aria-label="Watchlist workspace">
      <header className="workspace-header">
        <h1>Watchlist</h1>
        <p className="muted">Read-only EOD research queue for status, priority, signal, risk, and next action.</p>
      </header>
      <section className="workspace-panel">
        <div className="section-heading">
          <h2>EOD Queue</h2>
          <span className="status-chip neutral">{visibleRows.length} rows</span>
        </div>
        <div className="queue-filters">
          <label>
            Watchlist
            <input
              aria-label="watchlist id"
              value={watchlistId}
              onChange={(event) => setWatchlistId(event.target.value)}
            />
          </label>
          <label>
            Trade date
            <input
              aria-label="trade date"
              type="date"
              value={tradeDate}
              onChange={(event) => setTradeDate(event.target.value)}
            />
          </label>
          <label>
            Status
            <select
              aria-label="watchlist status"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="all">All</option>
              <option value="candidate">candidate</option>
              <option value="observe">observe</option>
              <option value="holding">holding</option>
              <option value="review">review</option>
            </select>
          </label>
          <label>
            Min priority
            <input
              aria-label="minimum priority"
              type="number"
              min="0"
              value={minPriority}
              onChange={(event) => setMinPriority(Number(event.target.value) || 0)}
            />
          </label>
          <label>
            Signal/risk query
            <input
              aria-label="signal risk query"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="asset, signal, risk"
            />
          </label>
          <button type="button" onClick={() => void loadQueue()} disabled={isLoading}>
            Load EOD Queue
          </button>
        </div>
        {error ? <p className="muted">{error}</p> : null}
        {isLoading ? (
          <p className="muted">Loading EOD queue...</p>
        ) : visibleRows.length === 0 ? (
          <p className="muted">No queue rows match current filters.</p>
        ) : (
          <div className="queue-table-wrap">
            <table className="queue-table">
              <thead>
                <tr>
                  <th>Stock</th>
                  <th>Status</th>
                  <th>Priority</th>
                  <th>Signal</th>
                  <th>Risk</th>
                  <th>Reason</th>
                  <th>Next Action</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row) => (
                  <tr key={`${row.trade_date}:${row.asset_id}`}>
                    <td>
                      <strong>{row.stock_name}</strong>
                      <span className="muted">{row.asset_id}</span>
                    </td>
                    <td>{row.primary_signal}</td>
                    <td>{row.priority}</td>
                    <td>{formatTags(row.signal_tags)}</td>
                    <td>{formatTags(row.risk_tags)}</td>
                    <td>{reasonField(row, 'reason')}</td>
                    <td>{reasonField(row, 'next_action')}</td>
                    <td>
                      <button
                        className="compact-action-button"
                        type="button"
                        aria-label={`Open ${row.asset_id}`}
                        onClick={() => onOpenAsset?.(row.asset_id)}
                      >
                        Open
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </section>
  );
}
