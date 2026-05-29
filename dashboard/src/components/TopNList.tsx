import type { ScoreRow } from '../api/types';

type TopNListProps = {
  rows: ScoreRow[];
  selectedAssetId: string;
  onSelectAsset: (assetId: string) => void;
};

export function TopNList({ rows, selectedAssetId, onSelectAsset }: TopNListProps) {
  return (
    <section className="list-section">
      <h2>TopN</h2>
      <div className="dense-list">
        {rows.map((row) => (
          <button
            key={row.asset_id}
            className={row.asset_id === selectedAssetId ? 'list-row active' : 'list-row'}
            type="button"
            onClick={() => onSelectAsset(row.asset_id)}
          >
            <span>{row.rank}</span>
            <strong>{row.asset_id}</strong>
            <span>{row.score_total.toFixed(1)}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
