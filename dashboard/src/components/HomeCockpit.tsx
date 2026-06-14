import { useEffect, useState } from 'react';
import {
  fetchBacktestStrategies,
  fetchEvidenceDigest,
  fetchMarketMonitorEod,
  fetchPlatformSummary,
  fetchPublicNews
} from '../api/client';
import type {
  EvidenceDigestResponse,
  MarketMonitorPayload,
  PlatformSummary,
  PublicNewsItem,
  ScoreRow,
  StrategyCatalogItem
} from '../api/types';

type WorkspaceMode =
  | 'market'
  | 'news'
  | 'researchReports'
  | 'stock'
  | 'watchlist'
  | 'factors'
  | 'strategyLab'
  | 'data'
  | 'generatedReports';

type HomeCockpitProps = {
  onNavigate: (mode: WorkspaceMode) => void;
};

const QUICK_ACTIONS: Array<{ mode: WorkspaceMode; label: string }> = [
  { mode: 'market', label: 'Market Monitor' },
  { mode: 'news', label: 'News' },
  { mode: 'researchReports', label: 'Research Reports' },
  { mode: 'stock', label: 'Stock Workspace' },
  { mode: 'watchlist', label: 'Watchlist' },
  { mode: 'factors', label: 'Factor Lab' },
  { mode: 'strategyLab', label: 'Strategy Lab' },
  { mode: 'data', label: 'Data Explorer' },
  { mode: 'generatedReports', label: 'Generated Reports' }
];

function formatCount(value: number | null | undefined) {
  return typeof value === 'number' ? value.toLocaleString() : '-';
}

function formatScore(row: ScoreRow) {
  return typeof row.score_total === 'number' ? row.score_total.toFixed(1) : '-';
}

function errorMessage(err: unknown) {
  return err instanceof Error ? err.message : String(err);
}

export function HomeCockpit({ onNavigate }: HomeCockpitProps) {
  const [summary, setSummary] = useState<PlatformSummary | null>(null);
  const [strategies, setStrategies] = useState<StrategyCatalogItem[]>([]);
  const [marketMonitor, setMarketMonitor] = useState<MarketMonitorPayload | null>(null);
  const [newsItems, setNewsItems] = useState<PublicNewsItem[]>([]);
  const [digestByAsset, setDigestByAsset] = useState<Record<string, EvidenceDigestResponse>>({});
  const [digestErrors, setDigestErrors] = useState<Record<string, string>>({});
  const [widgetWarnings, setWidgetWarnings] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;
    setIsLoading(true);
    setError(null);
    setWidgetWarnings([]);
    setDigestByAsset({});
    setDigestErrors({});

    const addWidgetWarning = (warning: string) => {
      setWidgetWarnings((current) => [...current, warning]);
    };

    Promise.allSettled([
      fetchPlatformSummary(),
      fetchBacktestStrategies()
    ]).then(([summaryResult, strategiesResult]) => {
      if (ignore) return;

      const criticalErrors: string[] = [];

      if (summaryResult.status === 'fulfilled') {
        setSummary(summaryResult.value);
        const focusRows = summaryResult.value.topn_preview.slice(0, 5);
        void Promise.allSettled(
          focusRows.map((row) =>
            fetchEvidenceDigest(row.asset_id, {
              tradeDate: summaryResult.value.latest_market_date,
              lookbackDays: 90
            }).then((digest) => ({ assetId: row.asset_id, digest }))
          )
        ).then((results) => {
          if (ignore) return;
          const nextDigests: Record<string, EvidenceDigestResponse> = {};
          const nextErrors: Record<string, string> = {};
          results.forEach((result, index) => {
            const assetId = focusRows[index].asset_id;
            if (result.status === 'fulfilled') nextDigests[assetId] = result.value.digest;
            else nextErrors[assetId] = 'Digest unavailable';
          });
          setDigestByAsset(nextDigests);
          setDigestErrors(nextErrors);
        });
      } else {
        setSummary(null);
        criticalErrors.push(`Platform summary unavailable: ${errorMessage(summaryResult.reason)}`);
      }

      if (strategiesResult.status === 'fulfilled') {
        setStrategies(strategiesResult.value);
      } else {
        setStrategies([]);
        criticalErrors.push(`Strategies unavailable: ${errorMessage(strategiesResult.reason)}`);
      }

      setError(criticalErrors.length > 0 ? criticalErrors.join('; ') : null);
      setIsLoading(false);
    });

    void fetchMarketMonitorEod({ topN: 5 }).then(
      (marketPayload) => {
        if (!ignore) setMarketMonitor(marketPayload);
      },
      (err: unknown) => {
        if (!ignore) {
          setMarketMonitor(null);
          addWidgetWarning(`Market pulse unavailable: ${errorMessage(err)}`);
        }
      }
    );

    void fetchPublicNews({ source: 'sina_finance', limit: 5 }).then(
      (newsPayload) => {
        if (!ignore) setNewsItems(newsPayload.items);
      },
      (err: unknown) => {
        if (!ignore) {
          setNewsItems([]);
          addWidgetWarning(`News flow unavailable: ${errorMessage(err)}`);
        }
      }
    );

    return () => {
      ignore = true;
    };
  }, []);

  return (
    <section className="home-cockpit" aria-label="Research Cockpit">
      <header className="workspace-header">
        <h1>Research Cockpit</h1>
        <p className="muted">Workspace summary for data coverage, research signals, and validation entry points.</p>
      </header>

      <nav className="quick-actions" aria-label="Quick actions">
        {QUICK_ACTIONS.map((item) => (
          <button type="button" key={item.mode} onClick={() => onNavigate(item.mode)}>
            {item.label}
          </button>
        ))}
      </nav>

      {error ? <p className="error-text">{error}</p> : null}
      {widgetWarnings.map((warning) => (
        <p className="error-text" key={warning}>
          {warning}
        </p>
      ))}

      <section className="status-strip" aria-label="Dashboard status">
        <div>
          <span>Market Date</span>
          <strong>{summary?.latest_market_date ?? '-'}</strong>
        </div>
        <div>
          <span>Factor Date</span>
          <strong>{summary?.latest_factor_date ?? '-'}</strong>
        </div>
        <div>
          <span>EOD Monitor</span>
          <strong>{marketMonitor?.trade_date || '-'}</strong>
        </div>
        <div>
          <span>Strategies</span>
          <strong>{formatCount(strategies.length)}</strong>
        </div>
      </section>

      <section className="cockpit-layout">
        <section className="workspace-panel">
          <div className="section-heading">
            <h2>Today Focus</h2>
            <span className="status-chip neutral">candidate pool</span>
          </div>
          <div className="data-table">
            {(summary?.topn_preview ?? []).slice(0, 5).map((row) => {
              const digest = digestByAsset[row.asset_id];
              const digestError = digestErrors[row.asset_id];
              return (
                <div
                  className="data-table-row"
                  style={{ gridTemplateColumns: '56px minmax(0, 1fr) 80px minmax(120px, 0.8fr)' }}
                  key={`${row.trade_date}-${row.asset_id}`}
                >
                  <span>{row.rank}</span>
                  <strong>{row.asset_id}</strong>
                  <span>{formatScore(row)}</span>
                  <span className="status-chip neutral">{digest?.title ?? digestError ?? 'Digest pending'}</span>
                </div>
              );
            })}
          </div>
        </section>

        <section className="workspace-panel">
          <div className="section-heading">
            <h2>Market Pulse</h2>
            <span className="status-chip neutral">EOD</span>
          </div>
          <div className="metric-row">
            <span>Market Assets</span>
            <strong>{formatCount(marketMonitor?.coverage.market_assets)}</strong>
          </div>
          <div className="metric-row">
            <span>Score Assets</span>
            <strong>{formatCount(marketMonitor?.coverage.score_assets)}</strong>
          </div>
          <div className="metric-row">
            <span>Factor Count</span>
            <strong>{formatCount(marketMonitor?.coverage.factor_count)}</strong>
          </div>
        </section>

        <section className="workspace-panel">
          <div className="section-heading">
            <h2>News Flow</h2>
            <button type="button" onClick={() => onNavigate('news')}>
              Open
            </button>
          </div>
          <div className="compact-news-list">
            {newsItems.map((item) => (
              <span key={item.news_id}>{item.title}</span>
            ))}
          </div>
        </section>
      </section>

      <section className="workspace-panel">
        <div className="section-heading">
          <h2>Strategy Health</h2>
          {isLoading ? (
            <span className="muted">Loading...</span>
          ) : (
            <button type="button" onClick={() => onNavigate('strategyLab')}>
              Open Strategy Lab
            </button>
          )}
        </div>
        <div className="strategy-card-grid">
          {strategies.slice(0, 4).map((strategy) => (
            <article className="strategy-summary-card" key={strategy.strategy_id}>
              <div className="strategy-card-header">
                <strong>{strategy.strategy_name}</strong>
              </div>
              <p>{strategy.description}</p>
            </article>
          ))}
        </div>
      </section>
    </section>
  );
}
