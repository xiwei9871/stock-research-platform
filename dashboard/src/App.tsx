import { useEffect, useMemo, useState } from 'react';
import {
  fetchAssetDecisions,
  fetchAssetOutcomes,
  fetchAssetScore,
  fetchAssetSignals,
  fetchDailyBars,
  fetchExperimentProposals,
  fetchExperimentReplay,
  fetchOutcomeAnalytics,
  fetchOverview,
  fetchShadowAnalyticsReview,
  fetchShadowFollowUpQueue,
  fetchShadowFollowUpResolution,
  fetchShadowReviewDecisions,
  fetchShadowOutcomeAnalytics,
  fetchShadowOutcomes,
  fetchShadowWatchlist
} from './api/client';
import type {
  BarPoint,
  DashboardOverview,
  DecisionEventRow,
  DecisionOutcomeRow,
  ExperimentProposalRow,
  ExperimentReplayRow,
  OutcomeAnalyticsRow,
  ScoreRow,
  ShadowAnalyticsReviewRow,
  ShadowFollowUpRow,
  ShadowFollowUpResolutionRow,
  ShadowReviewDecisionRow,
  ShadowOutcomeAnalyticsRow,
  ShadowOutcomeRow,
  ShadowWatchlistRow,
  WatchlistSignalRow
} from './api/types';
import { AssetChart } from './charts/AssetChart';
import { DecisionHistoryPanel } from './components/DecisionHistoryPanel';
import { ExperimentProposalsPanel } from './components/ExperimentProposalsPanel';
import { ExperimentReplayPanel } from './components/ExperimentReplayPanel';
import { OutcomeAnalyticsPanel } from './components/OutcomeAnalyticsPanel';
import { OutcomeHistoryPanel } from './components/OutcomeHistoryPanel';
import { ReportPanel } from './components/ReportPanel';
import { ScorePanel } from './components/ScorePanel';
import { ShadowOutcomesPanel } from './components/ShadowOutcomesPanel';
import { ShadowAnalyticsReviewPanel } from './components/ShadowAnalyticsReviewPanel';
import { ShadowFollowUpQueuePanel } from './components/ShadowFollowUpQueuePanel';
import { ShadowFollowUpResolutionPanel } from './components/ShadowFollowUpResolutionPanel';
import { ShadowReviewDecisionsPanel } from './components/ShadowReviewDecisionsPanel';
import { ShadowOutcomeAnalyticsPanel } from './components/ShadowOutcomeAnalyticsPanel';
import { ShadowWatchlistPanel } from './components/ShadowWatchlistPanel';
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
  const [outcomes, setOutcomes] = useState<DecisionOutcomeRow[]>([]);
  const [outcomeAnalytics, setOutcomeAnalytics] = useState<OutcomeAnalyticsRow[]>([]);
  const [experimentProposals, setExperimentProposals] = useState<ExperimentProposalRow[]>([]);
  const [experimentReplay, setExperimentReplay] = useState<ExperimentReplayRow[]>([]);
  const [shadowWatchlist, setShadowWatchlist] = useState<ShadowWatchlistRow[]>([]);
  const [shadowOutcomes, setShadowOutcomes] = useState<ShadowOutcomeRow[]>([]);
  const [shadowOutcomeAnalytics, setShadowOutcomeAnalytics] = useState<ShadowOutcomeAnalyticsRow[]>([]);
  const [shadowAnalyticsReview, setShadowAnalyticsReview] = useState<ShadowAnalyticsReviewRow[]>([]);
  const [shadowReviewDecisions, setShadowReviewDecisions] = useState<ShadowReviewDecisionRow[]>([]);
  const [shadowFollowUpQueue, setShadowFollowUpQueue] = useState<ShadowFollowUpRow[]>([]);
  const [shadowFollowUpResolution, setShadowFollowUpResolution] = useState<ShadowFollowUpResolutionRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [assetLoading, setAssetLoading] = useState(false);
  const [experimentReplayLoading, setExperimentReplayLoading] = useState(false);
  const [shadowWatchlistLoading, setShadowWatchlistLoading] = useState(false);
  const [shadowOutcomesLoading, setShadowOutcomesLoading] = useState(false);
  const [shadowOutcomeAnalyticsLoading, setShadowOutcomeAnalyticsLoading] = useState(false);
  const [shadowAnalyticsReviewLoading, setShadowAnalyticsReviewLoading] = useState(false);
  const [shadowReviewDecisionsLoading, setShadowReviewDecisionsLoading] = useState(false);
  const [shadowFollowUpQueueLoading, setShadowFollowUpQueueLoading] = useState(false);
  const [shadowFollowUpResolutionLoading, setShadowFollowUpResolutionLoading] = useState(false);

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
    fetchOutcomeAnalytics(startDate, tradeDate, { limit: 20 })
      .then((rows) => {
        if (!ignore) {
          setOutcomeAnalytics(rows);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : String(err));
          setOutcomeAnalytics([]);
        }
      });

    return () => {
      ignore = true;
    };
  }, [startDate, tradeDate]);

  useEffect(() => {
    let ignore = false;
    setError(null);
    fetchExperimentProposals(startDate, tradeDate, { limit: 20 })
      .then((rows) => {
        if (!ignore) {
          setExperimentProposals(rows);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : String(err));
          setExperimentProposals([]);
        }
      });

    return () => {
      ignore = true;
    };
  }, [startDate, tradeDate]);

  useEffect(() => {
    let ignore = false;
    setError(null);
    setExperimentReplayLoading(true);
    fetchExperimentReplay(startDate, tradeDate, { limit: 20 })
      .then((rows) => {
        if (!ignore) {
          setExperimentReplay(rows);
          setExperimentReplayLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : String(err));
          setExperimentReplay([]);
          setExperimentReplayLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [startDate, tradeDate]);

  useEffect(() => {
    let ignore = false;
    setError(null);
    setShadowWatchlistLoading(true);
    fetchShadowWatchlist(startDate, tradeDate, { limit: 20 })
      .then((rows) => {
        if (!ignore) {
          setShadowWatchlist(rows);
          setShadowWatchlistLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : String(err));
          setShadowWatchlist([]);
          setShadowWatchlistLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [startDate, tradeDate]);

  useEffect(() => {
    let ignore = false;
    setError(null);
    setShadowOutcomesLoading(true);
    fetchShadowOutcomes(startDate, tradeDate, { limit: 20 })
      .then((rows) => {
        if (!ignore) {
          setShadowOutcomes(rows);
          setShadowOutcomesLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : String(err));
          setShadowOutcomes([]);
          setShadowOutcomesLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [startDate, tradeDate]);

  useEffect(() => {
    let ignore = false;
    setError(null);
    setShadowOutcomeAnalyticsLoading(true);
    fetchShadowOutcomeAnalytics(startDate, tradeDate, { limit: 20 })
      .then((rows) => {
        if (!ignore) {
          setShadowOutcomeAnalytics(rows);
          setShadowOutcomeAnalyticsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : String(err));
          setShadowOutcomeAnalytics([]);
          setShadowOutcomeAnalyticsLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [startDate, tradeDate]);

  useEffect(() => {
    let ignore = false;
    setError(null);
    setShadowAnalyticsReviewLoading(true);
    fetchShadowAnalyticsReview(startDate, tradeDate, { limit: 20 })
      .then((rows) => {
        if (!ignore) {
          setShadowAnalyticsReview(rows);
          setShadowAnalyticsReviewLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : String(err));
          setShadowAnalyticsReview([]);
          setShadowAnalyticsReviewLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [startDate, tradeDate]);

  useEffect(() => {
    let ignore = false;
    setError(null);
    setShadowReviewDecisionsLoading(true);
    fetchShadowReviewDecisions(startDate, tradeDate, { limit: 20 })
      .then((rows) => {
        if (!ignore) {
          setShadowReviewDecisions(rows);
          setShadowReviewDecisionsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : String(err));
          setShadowReviewDecisions([]);
          setShadowReviewDecisionsLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [startDate, tradeDate]);

  useEffect(() => {
    let ignore = false;
    setError(null);
    setShadowFollowUpQueueLoading(true);
    fetchShadowFollowUpQueue(startDate, tradeDate, { limit: 20 })
      .then((rows) => {
        if (!ignore) {
          setShadowFollowUpQueue(rows);
          setShadowFollowUpQueueLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : String(err));
          setShadowFollowUpQueue([]);
          setShadowFollowUpQueueLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [startDate, tradeDate]);

  useEffect(() => {
    let ignore = false;
    setError(null);
    setShadowFollowUpResolutionLoading(true);
    fetchShadowFollowUpResolution(startDate, tradeDate, { limit: 20 })
      .then((rows) => {
        if (!ignore) {
          setShadowFollowUpResolution(rows);
          setShadowFollowUpResolutionLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : String(err));
          setShadowFollowUpResolution([]);
          setShadowFollowUpResolutionLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [startDate, tradeDate]);

  useEffect(() => {
    let ignore = false;
    setError(null);
    setAssetLoading(true);
    Promise.all([
      fetchDailyBars(selectedAssetId, startDate, tradeDate),
      fetchAssetScore(selectedAssetId, tradeDate),
      fetchAssetSignals(selectedAssetId, tradeDate),
      fetchAssetDecisions(selectedAssetId, startDate, tradeDate),
      fetchAssetOutcomes(selectedAssetId, startDate, tradeDate)
    ])
      .then(([barRows, scoreRow, signalRows, decisionRows, outcomeRows]) => {
        if (!ignore) {
          setBars(barRows);
          setScore(scoreRow);
          setSignals(signalRows);
          setDecisions(decisionRows);
          setOutcomes(outcomeRows);
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
        <OutcomeHistoryPanel outcomes={outcomes} />
        <OutcomeAnalyticsPanel rows={outcomeAnalytics} />
        <ExperimentProposalsPanel rows={experimentProposals} />
        <ExperimentReplayPanel rows={experimentReplay} isLoading={experimentReplayLoading} />
        <ShadowWatchlistPanel rows={shadowWatchlist} isLoading={shadowWatchlistLoading} />
        <ShadowOutcomesPanel rows={shadowOutcomes} isLoading={shadowOutcomesLoading} />
        <ShadowOutcomeAnalyticsPanel
          rows={shadowOutcomeAnalytics}
          isLoading={shadowOutcomeAnalyticsLoading}
        />
        <ShadowAnalyticsReviewPanel
          rows={shadowAnalyticsReview}
          isLoading={shadowAnalyticsReviewLoading}
        />
        <ShadowReviewDecisionsPanel
          rows={shadowReviewDecisions}
          isLoading={shadowReviewDecisionsLoading}
        />
        <ShadowFollowUpQueuePanel
          rows={shadowFollowUpQueue}
          isLoading={shadowFollowUpQueueLoading}
        />
        <ShadowFollowUpResolutionPanel
          rows={shadowFollowUpResolution}
          isLoading={shadowFollowUpResolutionLoading}
        />
        <ReportPanel reports={overview?.reports ?? []} isLoading={overviewLoading} />
      </aside>
    </main>
  );
}
