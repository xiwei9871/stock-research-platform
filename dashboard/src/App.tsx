import { useEffect, useMemo, useState } from 'react';
import { fetchAssetScore, fetchAssetSignals, fetchDailyBars, fetchOverview } from './api/client';
import type { BarPoint, DashboardOverview, ScoreRow, WatchlistSignalRow } from './api/types';
import { AssetChart } from './charts/AssetChart';
import { ReportPanel } from './components/ReportPanel';
import { ScorePanel } from './components/ScorePanel';
import { TopNList } from './components/TopNList';
import { WatchlistList } from './components/WatchlistList';

const DEFAULT_TRADE_DATE = '2026-05-29';
const DEFAULT_ASSET_ID = '000001.SZ';

export function App() {
  const [tradeDate, setTradeDate] = useState(DEFAULT_TRADE_DATE);
  const [selectedAssetId, setSelectedAssetId] = useState(DEFAULT_ASSET_ID);
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [bars, setBars] = useState<BarPoint[]>([]);
  const [score, setScore] = useState<ScoreRow | null>(null);
  const [signals, setSignals] = useState<WatchlistSignalRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  const startDate = useMemo(() => {
    const date = new Date(`${tradeDate}T00:00:00`);
    date.setDate(date.getDate() - 180);
    return date.toISOString().slice(0, 10);
  }, [tradeDate]);

  useEffect(() => {
    setError(null);
    fetchOverview({
      tradeDate,
      scoreVersion: 'manual_v1',
      watchlistId: 'default',
      topN: 30
    })
      .then(setOverview)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, [tradeDate]);

  useEffect(() => {
    setError(null);
    Promise.all([
      fetchDailyBars(selectedAssetId, startDate, tradeDate),
      fetchAssetScore(selectedAssetId, tradeDate),
      fetchAssetSignals(selectedAssetId, tradeDate)
    ])
      .then(([barRows, scoreRow, signalRows]) => {
        setBars(barRows);
        setScore(scoreRow);
        setSignals(signalRows);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, [selectedAssetId, startDate, tradeDate]);

  return (
    <main className="workbench">
      <aside className="sidebar">
        <div className="panel-title">Stock Research</div>
        <TopNList
          rows={overview?.top_scores ?? []}
          selectedAssetId={selectedAssetId}
          onSelectAsset={setSelectedAssetId}
        />
        <WatchlistList
          rows={overview?.watchlist_signals ?? []}
          selectedAssetId={selectedAssetId}
          onSelectAsset={setSelectedAssetId}
        />
      </aside>
      <section className="workspace">
        <header className="toolbar">
          <input
            aria-label="trade date"
            type="date"
            value={tradeDate}
            onChange={(event) => setTradeDate(event.target.value)}
          />
          <input
            aria-label="asset id"
            value={selectedAssetId}
            onChange={(event) => setSelectedAssetId(event.target.value.trim())}
          />
          {error ? <span className="error-text">{error}</span> : null}
        </header>
        <section className="chart-panel">
          <AssetChart bars={bars} />
        </section>
      </section>
      <aside className="inspector">
        <ScorePanel score={score} signals={signals} />
        <ReportPanel reports={overview?.reports ?? []} />
      </aside>
    </main>
  );
}
