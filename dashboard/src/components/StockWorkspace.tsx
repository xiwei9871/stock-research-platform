import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { fetchAssetProfile, fetchAssetResearchReports, fetchPublicNews, searchAssets } from '../api/client';
import type { AssetProfile, AssetResearchReportResponse, AssetSummary, PublicNewsItem } from '../api/types';
import { AssetChart } from '../charts/AssetChart';

const DEFAULT_ASSET_ID = '000001.SZ';
const DEFAULT_TRADE_DATE = '2026-06-08';
const DEFAULT_START_DATE = '2025-12-10';
const DEFAULT_END_DATE = '2026-06-08';
const SCORE_VERSION = 'manual_v1';
const ADJUST_TYPE = 'qfq';

type StockWorkspaceProps = {
  initialAssetId?: string;
};

type FactorDisplayRow = {
  group: string;
  name: string;
  value: unknown;
};

function normalizeAssetId(value: string) {
  const trimmed = value.trim().toUpperCase();
  if (/^\d{6}$/.test(trimmed)) {
    return `${trimmed}.${trimmed.startsWith('6') ? 'SH' : 'SZ'}`;
  }
  return trimmed;
}

function formatValue(value: unknown) {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  }
  if (typeof value === 'string') {
    return value;
  }
  if (typeof value === 'boolean') {
    return value ? 'yes' : 'no';
  }
  if (value == null) {
    return '-';
  }
  return JSON.stringify(value);
}

function formatScore(profile: AssetProfile | null) {
  const score = profile?.score?.score_total;
  return typeof score === 'number' ? score.toFixed(1) : '-';
}

function getFactorRows(profile: AssetProfile | null): FactorDisplayRow[] {
  const rawFactorRows = (profile?.factor_values ?? []).map((row) => ({
    group: formatValue(row.factor_group ?? '-'),
    name: formatValue(row.factor_name ?? '-'),
    value: row.factor_value ?? '-'
  }));
  const scoreComponentRows = Object.entries(profile?.score?.score_components ?? {}).map(([name, value]) => ({
    group: 'Score Component',
    name,
    value
  }));
  return [...rawFactorRows, ...scoreComponentRows];
}

function formatReason(reason: Record<string, unknown>) {
  return Object.entries(reason)
    .map(([key, value]) => `${key}: ${formatValue(value)}`)
    .join(' / ');
}

function latestClose(profile: AssetProfile | null) {
  const bars = profile?.bars ?? [];
  const lastBar = bars.length > 0 ? bars[bars.length - 1] : null;
  return lastBar?.close ?? null;
}

export function StockWorkspace({ initialAssetId = DEFAULT_ASSET_ID }: StockWorkspaceProps) {
  const [assetId, setAssetId] = useState(initialAssetId);
  const [tradeDate, setTradeDate] = useState(DEFAULT_TRADE_DATE);
  const [startDate, setStartDate] = useState(DEFAULT_START_DATE);
  const [endDate, setEndDate] = useState(DEFAULT_END_DATE);
  const [profile, setProfile] = useState<AssetProfile | null>(null);
  const [newsItems, setNewsItems] = useState<PublicNewsItem[]>([]);
  const [researchReports, setResearchReports] = useState<AssetResearchReportResponse | null>(null);
  const [assetMatches, setAssetMatches] = useState<AssetSummary[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isNewsLoading, setIsNewsLoading] = useState(false);
  const [isResearchReportsLoading, setIsResearchReportsLoading] = useState(false);
  const [isSearchLoading, setIsSearchLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newsError, setNewsError] = useState<string | null>(null);
  const [researchReportsError, setResearchReportsError] = useState<string | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const mountedRef = useRef(false);
  const profileRequestIdRef = useRef(0);
  const newsRequestIdRef = useRef(0);
  const researchReportsRequestIdRef = useRef(0);
  const searchRequestIdRef = useRef(0);

  const isLatestProfileRequest = useCallback((requestId: number) => {
    return mountedRef.current && requestId === profileRequestIdRef.current;
  }, []);

  const loadAssetMatches = useCallback(async (query: string, profileRequestId: number) => {
    const requestId = searchRequestIdRef.current + 1;
    searchRequestIdRef.current = requestId;

    if (!query) {
      setAssetMatches([]);
      return;
    }

    setIsSearchLoading(true);
    setSearchError(null);

    try {
      const items = await searchAssets(query, 8);
      if (mountedRef.current && profileRequestId === profileRequestIdRef.current && requestId === searchRequestIdRef.current) {
        setAssetMatches(items);
      }
    } catch (err: unknown) {
      if (mountedRef.current && profileRequestId === profileRequestIdRef.current && requestId === searchRequestIdRef.current) {
        setSearchError(err instanceof Error ? err.message : String(err));
        setAssetMatches([]);
      }
    } finally {
      if (mountedRef.current && profileRequestId === profileRequestIdRef.current && requestId === searchRequestIdRef.current) {
        setIsSearchLoading(false);
      }
    }
  }, []);

  const loadProfile = useCallback(
    async (
      nextAssetId = assetId,
      nextTradeDate = tradeDate,
      nextStartDate = startDate,
      nextEndDate = endDate
    ) => {
      const requestId = profileRequestIdRef.current + 1;
      profileRequestIdRef.current = requestId;
      const normalizedAssetId = normalizeAssetId(nextAssetId);

      setIsLoading(true);
      setError(null);
      setNewsError(null);
      setAssetId(normalizedAssetId);

      try {
        const nextProfile = await fetchAssetProfile(
          normalizedAssetId,
          nextTradeDate,
          nextStartDate,
          nextEndDate,
          SCORE_VERSION,
          ADJUST_TYPE
        );
        if (!isLatestProfileRequest(requestId)) {
          return;
        }
        setProfile(nextProfile);
        void loadAssetMatches(normalizedAssetId, requestId);
      } catch (err: unknown) {
        if (!isLatestProfileRequest(requestId)) {
          return;
        }
        setError(err instanceof Error ? err.message : String(err));
        setProfile(null);
        setAssetMatches([]);
      } finally {
        if (isLatestProfileRequest(requestId)) {
          setIsLoading(false);
        }
      }
    },
    [assetId, endDate, isLatestProfileRequest, loadAssetMatches, startDate, tradeDate]
  );

  useEffect(() => {
    mountedRef.current = true;
    void loadProfile(initialAssetId, DEFAULT_TRADE_DATE, DEFAULT_START_DATE, DEFAULT_END_DATE);
    return () => {
      mountedRef.current = false;
      profileRequestIdRef.current += 1;
      newsRequestIdRef.current += 1;
      researchReportsRequestIdRef.current += 1;
      searchRequestIdRef.current += 1;
    };
  }, [initialAssetId]);

  useEffect(() => {
    if (!profile) {
      newsRequestIdRef.current += 1;
      setNewsItems([]);
      setIsNewsLoading(false);
      setNewsError(null);
      return;
    }

    const requestId = newsRequestIdRef.current + 1;
    newsRequestIdRef.current = requestId;
    const symbol = profile.asset?.symbol ?? profile.asset_id;
    const name = profile.asset?.name ?? profile.asset_id;

    setIsNewsLoading(true);
    setNewsError(null);

    fetchPublicNews({ source: 'sina_finance', q: `${symbol} ${name}`, limit: 20 })
      .then((payload) => {
        if (mountedRef.current && requestId === newsRequestIdRef.current) {
          setNewsItems(payload.items);
        }
      })
      .catch((err: unknown) => {
        if (mountedRef.current && requestId === newsRequestIdRef.current) {
          setNewsError(err instanceof Error ? err.message : String(err));
          setNewsItems([]);
        }
      })
      .finally(() => {
        if (mountedRef.current && requestId === newsRequestIdRef.current) {
          setIsNewsLoading(false);
        }
      });
  }, [profile]);

  useEffect(() => {
    if (!profile) {
      researchReportsRequestIdRef.current += 1;
      setResearchReports(null);
      setIsResearchReportsLoading(false);
      setResearchReportsError(null);
      return;
    }

    const requestId = researchReportsRequestIdRef.current + 1;
    researchReportsRequestIdRef.current = requestId;

    setIsResearchReportsLoading(true);
    setResearchReportsError(null);

    fetchAssetResearchReports(profile.canonical_asset_id, { limit: 5, lookbackDays: 90 })
      .then((payload) => {
        if (mountedRef.current && requestId === researchReportsRequestIdRef.current) {
          setResearchReports(payload);
        }
      })
      .catch((err: unknown) => {
        if (mountedRef.current && requestId === researchReportsRequestIdRef.current) {
          setResearchReportsError(err instanceof Error ? err.message : String(err));
          setResearchReports(null);
        }
      })
      .finally(() => {
        if (mountedRef.current && requestId === researchReportsRequestIdRef.current) {
          setIsResearchReportsLoading(false);
        }
      });
  }, [profile]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void loadProfile();
  };

  const identityName = profile?.asset?.name ?? profile?.asset_id ?? assetId;
  const identitySymbol = profile?.asset?.symbol ?? profile?.asset_id ?? assetId;
  const factorRows = getFactorRows(profile);
  const close = latestClose(profile);

  return (
    <section className="workspace-stack" aria-label="Stock Workspace workspace">
      <header className="workspace-header">
        <h1>{profile ? `${identityName} ${profile.canonical_asset_id}` : 'Stock Workspace'}</h1>
        <p className="muted">Single-stock evidence hub for price, factors, news, research reports, and strategy history.</p>
      </header>

      <form className="compact-toolbar" onSubmit={handleSubmit}>
        <label>
          Stock
          <input
            aria-label="stock workspace asset"
            value={assetId}
            onChange={(event) => setAssetId(event.target.value)}
          />
        </label>
        <label>
          Trade Date
          <input
            aria-label="stock workspace trade date"
            type="date"
            value={tradeDate}
            onChange={(event) => setTradeDate(event.target.value)}
          />
        </label>
        <label>
          Start
          <input
            aria-label="stock workspace start date"
            type="date"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
          />
        </label>
        <label>
          End
          <input
            aria-label="stock workspace end date"
            type="date"
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
          />
        </label>
        <button type="submit">Load Stock</button>
        {isLoading ? <span className="muted">Loading stock profile...</span> : null}
      </form>

      {error ? <p className="error-text">{error}</p> : null}

      {profile ? (
        <>
          <section className="stock-summary-strip" aria-label="Stock identity">
            <div>
              <span>Symbol</span>
              <strong>{identitySymbol}</strong>
            </div>
            <div>
              <span>Name</span>
              <strong>{identityName}</strong>
            </div>
            <div>
              <span>Score</span>
              <strong>Score {formatScore(profile)}</strong>
            </div>
            <div>
              <span>Rank</span>
              <strong>{profile.score?.rank ?? '-'}</strong>
            </div>
            <div>
              <span>Latest Close</span>
              <strong>{formatValue(close)}</strong>
            </div>
          </section>

          <section className="workspace-band" aria-label="Price chart">
            <div className="section-heading">
              <h2>Price Chart</h2>
              <span className="muted">
                {profile.bars.length} bars / {startDate} to {endDate}
              </span>
            </div>
            {profile.bars.length > 0 ? <AssetChart bars={profile.bars} /> : <p className="muted">No bars available.</p>}
          </section>

          <section className="stock-evidence-grid">
            <article className="workspace-band">
              <div className="section-heading">
                <h2>Factor Breakdown</h2>
                <span className="muted">{SCORE_VERSION}</span>
              </div>
              <table className="compact-table">
                <thead>
                  <tr>
                    <th>Group</th>
                    <th>Factor</th>
                    <th>Value</th>
                  </tr>
                </thead>
                <tbody>
                  {factorRows.map((row) => (
                    <tr key={`${row.group}-${row.name}`}>
                      <td>{row.group}</td>
                      <td>{row.name}</td>
                      <td>{formatValue(row.value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {factorRows.length === 0 ? <p className="muted">No factor values available.</p> : null}
            </article>

            <article className="workspace-band">
              <div className="section-heading">
                <h2>Related News</h2>
                {isNewsLoading ? <span className="muted">Loading...</span> : null}
              </div>
              {newsError ? <p className="error-text">{newsError}</p> : null}
              <div className="compact-news-list">
                {newsItems.map((item) => (
                  <a key={item.news_id} className="evidence-link-row" href={item.url} target="_blank" rel="noreferrer">
                    <strong>{item.title}</strong>
                    <span>{item.published_at.slice(0, 10)}</span>
                  </a>
                ))}
              </div>
              {!isNewsLoading && newsItems.length === 0 ? <p className="muted">No related news found.</p> : null}
            </article>

            <article className="workspace-band">
              <div className="section-heading">
                <h2>Watchlist State</h2>
                <span className="muted">{profile.signals.length} signals</span>
              </div>
              {profile.signals.map((signal) => (
                <div key={`${signal.watchlist_id}-${signal.asset_id}-${signal.primary_signal}`} className="signal-card">
                  <div>
                    <strong>{signal.primary_signal}</strong>
                    <span>Priority {signal.priority}</span>
                  </div>
                  <p>{formatReason(signal.reason_json)}</p>
                  <div className="tag-stack">
                    {signal.signal_tags.map((tag) => (
                      <span key={tag} className="status-chip neutral">
                        {tag}
                      </span>
                    ))}
                    {signal.risk_tags.map((tag) => (
                      <span key={tag} className="risk-tag">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
              {profile.signals.length === 0 ? <p className="muted">No active watchlist signal.</p> : null}
            </article>

            <article className="workspace-band">
              <div className="section-heading">
                <h2>Strategy / Review History</h2>
                <span className="muted">{profile.decisions.length} decisions</span>
              </div>
              {profile.decisions.map((decision) => (
                <div key={decision.event_id} className="evidence-row">
                  <div>
                    <strong>{decision.decision_label}</strong>
                    <span>{decision.review_date}</span>
                  </div>
                  <p>{decision.notes || decision.follow_up_note}</p>
                  <span>{decision.evidence_path}</span>
                </div>
              ))}
              {profile.decisions.length === 0 ? <p className="muted">No review decisions available.</p> : null}
            </article>

            <article className="workspace-band">
              <div className="section-heading">
                <h2>Research Reports</h2>
                {isResearchReportsLoading ? <span className="muted">Loading...</span> : null}
              </div>
              {researchReportsError ? <p className="error-text">{researchReportsError}</p> : null}
              {researchReports ? (
                <section className="stock-summary-strip" aria-label="Stock research report summary">
                  <div>
                    <span>Coverage</span>
                    <strong>90d reports {researchReports.summary.report_count_90d}</strong>
                  </div>
                  <div>
                    <span>30d Reports</span>
                    <strong>{researchReports.summary.report_count_30d}</strong>
                  </div>
                  <div>
                    <span>Brokers</span>
                    <strong>{researchReports.summary.broker_coverage_count_90d} brokers</strong>
                  </div>
                  <div>
                    <span>Latest Rating</span>
                    <strong>{formatValue(researchReports.summary.latest_rating)}</strong>
                  </div>
                  <div>
                    <span>Target Price</span>
                    <strong>{formatValue(researchReports.summary.latest_target_price)}</strong>
                  </div>
                </section>
              ) : null}
              <div className="compact-news-list">
                {(researchReports?.items ?? []).map((report) =>
                  report.source_url ? (
                    <a
                      key={report.report_id}
                      className="evidence-link-row"
                      href={report.source_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <strong>{report.report_title}</strong>
                      <span>
                        {formatValue(report.broker)} / {formatValue(report.publish_date ?? report.report_date)}
                      </span>
                    </a>
                  ) : (
                    <div key={report.report_id} className="evidence-link-row">
                      <strong>{report.report_title}</strong>
                      <span>
                        {formatValue(report.broker)} / {formatValue(report.publish_date ?? report.report_date)}
                      </span>
                    </div>
                  )
                )}
              </div>
              {!isResearchReportsLoading && !researchReportsError && (researchReports?.items.length ?? 0) === 0 ? (
                <p className="muted">No research reports found.</p>
              ) : null}
            </article>

            <article className="workspace-band">
              <div className="section-heading">
                <h2>Asset Search Matches</h2>
                {isSearchLoading ? <span className="muted">Searching...</span> : null}
              </div>
              {searchError ? <p className="error-text">{searchError}</p> : null}
              <div className="report-list compact">
                {assetMatches.map((match) => (
                  <button
                    key={match.asset_id}
                    className="list-row"
                    type="button"
                    onClick={() => setAssetId(match.asset_id)}
                  >
                    <span>{match.symbol}</span>
                    <strong>{match.name}</strong>
                    <span>{match.exchange}</span>
                  </button>
                ))}
              </div>
              {!isSearchLoading && assetMatches.length === 0 ? <p className="muted">No asset matches.</p> : null}
            </article>
          </section>
        </>
      ) : null}
    </section>
  );
}
