import type { WatchlistSignalRow } from '../api/types';

type WatchlistListProps = {
  rows: WatchlistSignalRow[];
  selectedAssetId: string;
  onSelectAsset: (assetId: string) => void;
};

export function WatchlistList({ rows, selectedAssetId, onSelectAsset }: WatchlistListProps) {
  return (
    <section className="list-section">
      <h2>Watchlist</h2>
      <div className="dense-list">
        {rows.map((row) => (
          <button
            key={`${row.watchlist_id}-${row.asset_id}`}
            className={row.asset_id === selectedAssetId ? 'list-row active' : 'list-row'}
            type="button"
            onClick={() => onSelectAsset(row.asset_id)}
          >
            <span>{row.must_watch ? 'Must' : row.priority}</span>
            <strong>{row.stock_name || row.asset_id}</strong>
            <span>{row.primary_signal}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
