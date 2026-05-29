import { useEffect, useMemo, useState } from 'react';
import { fetchAssetDecisions, fetchAssetScore, fetchAssetSignals, fetchDailyBars, fetchOverview } from './api/client';
import type { BarPoint, DashboardOverview, DecisionEventRow, ScoreRow, WatchlistSignalRow } from './api/types';
import { AssetChart } from './charts/AssetChart';
import { DecisionHistoryPanel } from './components/DecisionHistoryPanel';
import { ReportPanel } from './components/ReportPanel';
import { ScorePanel } from './components/ScorePanel';
import { TopNList } from './components/TopNList';
import { WatchlistList } from './components/WatchlistList';

const DEFAULT_TRADE_DATE = '2026-05-29';
const DEFAULT_ASSET_ID = '000001.SZ';

function dateNDaysBefore(dateText: string, days: number) {
  const [year, month, day] = dateText.split('-').map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() - days);
  const utcYear = date.getUTCFullYear();
  const utcMonth = String(date.getUTCMonth() + 1).padStart(2, '0');
  const utcDay = String(date.getUTCDate()).padStart(2, '0');
  return `${utcYear}-${utcMonth}-${utcDay}`;
}

export function App() {
  const [tradeDate, setTradeDate] = useState(DEFAULT_TRADE_DATE);
  const [selectedAssetId, setSelectedAssetId] = useState(DEFAULT_ASSET_ID);
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [bars, setBars] = useState<BarPoint[]>([]);
  const [score, setScore] = useState<ScoreRow | null>(null);
  const [signals, setSignals] = useState<WatchlistSignalRow[]>([]);
  const [decisions, setDecisions] = useState<DecisionEventRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [assetLoading, setAssetLoading] = useState(false);

  const startDate = useMemo(() => dateNDaysBefore(tradeDate, 180), [tradeDate]);

  useEffect(() => {
    let ignore = false;
    setError(null);
    setOverviewLoading(true);
    fetchOverview({
      tradeDate,
      scoreVersion: 'manual_v1',
      watchlistId: 'default',
      topN: 30
    })
      .then((overviewRows) => {
        if (!ignore) {
          setOverview(overviewRows);
          setOverviewLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : String(err));
          setOverviewLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [tradeDate]);

  useEffect(() => {
    let ignore = false;
    setError(null);
    setAssetLoading(true);
    Promise.all([
      fetchDailyBars(selectedAssetId, startDate, tradeDate),
      fetchAssetScore(selectedAssetId, tradeDate),
      fetchAssetSignals(selectedAssetId, tradeDate),
      fetchAssetDecisions(selectedAssetId, startDate, tradeDate)
    ])
      .then(([barRows, scoreRow, signalRows, decisionRows]) => {
        if (!ignore) {
          setBars(barRows);
          setScore(scoreRow);
          setSignals(signalRows);
          setDecisions(decisionRows);
          setAssetLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : String(err));
          setAssetLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [selectedAssetId, startDate, tradeDate]);

  return (
    <main className="workbench">
      <aside className="sidebar">
        <div className="panel-title">Stock Research</div>
        <TopNList
          rows={overview?.top_scores ?? []}
          selectedAssetId={selectedAssetId}
          onSelectAsset={setSelectedAssetId}
          isLoading={overviewLoading}
        />
        <WatchlistList
          rows={overview?.watchlist_signals ?? []}
          selectedAssetId={selectedAssetId}
          onSelectAsset={setSelectedAssetId}
          isLoading={overviewLoading}
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
          {assetLoading ? (
            <p className="muted">Loading asset review...</p>
          ) : bars.length > 0 ? (
            <AssetChart bars={bars} />
          ) : (
            <p className="muted">No chart bars for selected range.</p>
          )}
        </section>
      </section>
      <aside className="inspector">
        <ScorePanel score={score} signals={signals} />
        <DecisionHistoryPanel decisions={decisions} />
        <ReportPanel reports={overview?.reports ?? []} isLoading={overviewLoading} />
      </aside>
    </main>
  );
}
