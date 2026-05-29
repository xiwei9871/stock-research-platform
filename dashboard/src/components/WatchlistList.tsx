import type { WatchlistSignalRow } from '../api/types';

type WatchlistListProps = {
  rows: WatchlistSignalRow[];
  selectedAssetId: string;
  onSelectAsset: (assetId: string) => void;
  isLoading?: boolean;
};

export function WatchlistList({ rows, selectedAssetId, onSelectAsset, isLoading = false }: WatchlistListProps) {
  return (
    <section className="list-section">
      <h2>Watchlist</h2>
      {isLoading ? (
        <p className="muted">Loading watchlist...</p>
      ) : rows.length > 0 ? (
        <div className="dense-list">
          {rows.map((row) => (
            <button
              key={`${row.watchlist_id}-${row.asset_id}`}
              className={row.asset_id === selectedAssetId ? 'list-row active' : 'list-row'}
              type="button"
              onClick={() => onSelectAsset(row.asset_id)}
            >
              <span>{row.must_watch ? '必看' : row.priority}</span>
              <strong>{row.stock_name || row.asset_id}</strong>
              <span>{row.primary_signal}</span>
            </button>
          ))}
        </div>
      ) : (
        <p className="muted">No watchlist signals for selected date.</p>
      )}
    </section>
  );
}
