import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { fetchAssetNews, fetchAssetProfile, fetchAssetResearchReports, searchAssets } from '../api/client';
import type { AssetNewsResponse, AssetProfile, AssetResearchReportResponse, AssetSummary } from '../api/types';
import { AssetChart } from '../charts/AssetChart';

const DEFAULT_ASSET_ID = '000001.SZ';
const DEFAULT_TRADE_DATE = '2026-06-08';
const DEFAULT_START_DATE = '2025-12-10';
const DEFAULT_END_DATE = '2026-06-08';
const SCORE_VERSION = 'manual_v1';
const ADJUST_TYPE = 'qfq';

type StockWorkspaceProps = {
  initialAssetId?: string;
  entryContext?: StockEntryContext;
  onOpenNews?: (context: StockEntryContext) => void;
  onOpenResearchReports?: (context: StockEntryContext) => void;
  onOpenMarketMonitor?: (context: StockEntryContext) => void;
};

type FactorDisplayRow = {
  group: string;
  name: string;
  value: unknown;
};

export type StockEntryContext = {
  sourceWorkspace?: 'search' | 'news' | 'watchlist' | 'researchReports' | 'market';
  assetId?: string;
  query?: string;
  matchReason?: string;
  newsId?: string;
  eventKey?: string;
  reportId?: string;
  monitorTab?: string;
};

function formatSourceWorkspace(sourceWorkspace: NonNullable<StockEntryContext['sourceWorkspace']>) {
  if (sourceWorkspace === 'search') return 'Search';
  if (sourceWorkspace === 'news') return 'News';
  if (sourceWorkspace === 'watchlist') return 'Watchlist';
  if (sourceWorkspace === 'researchReports') return 'Research Reports';
  return 'Market Monitor';
}

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

export function StockWorkspace({
  initialAssetId = DEFAULT_ASSET_ID,
  entryContext,
  onOpenNews,
  onOpenResearchReports,
  onOpenMarketMonitor
}: StockWorkspaceProps) {
  const [assetId, setAssetId] = useState(initialAssetId);
  const [tradeDate, setTradeDate] = useState(DEFAULT_TRADE_DATE);
  const [startDate, setStartDate] = useState(DEFAULT_START_DATE);
  const [endDate, setEndDate] = useState(DEFAULT_END_DATE);
  const [profile, setProfile] = useState<AssetProfile | null>(null);
  const [assetNews, setAssetNews] = useState<AssetNewsResponse | null>(null);
  const [researchReports, setResearchReports] = useState<AssetResearchReportResponse | null>(null);
  const [assetMatches, setAssetMatches] = useState<AssetSummary[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isNewsLoading, setIsNewsLoading] = useState(false);
  const [isResearchReportsLoading, setIsResearchReportsLoading] = useState(false);
  const [isSearchLoading, setIsSearchLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newsError, setNewsError] = useState<{ assetId: string; message: string } | null>(null);
  const [newsLoadingAssetId, setNewsLoadingAssetId] = useState<string | null>(null);
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
    if (!profile?.canonical_asset_id) {
      newsRequestIdRef.current += 1;
      setAssetNews(null);
      setIsNewsLoading(false);
      setNewsLoadingAssetId(null);
      setNewsError(null);
      return;
    }

    const newsAssetId = profile.canonical_asset_id;
    const requestId = newsRequestIdRef.current + 1;
    newsRequestIdRef.current = requestId;

    setIsNewsLoading(true);
    setNewsLoadingAssetId(newsAssetId);
    setNewsError(null);
    setAssetNews(null);

    fetchAssetNews(newsAssetId, { limit: 8, lookbackDays: 7 })
      .then((payload) => {
        if (mountedRef.current && requestId === newsRequestIdRef.current) {
          setAssetNews(payload);
        }
      })
      .catch((err: unknown) => {
        if (mountedRef.current && requestId === newsRequestIdRef.current) {
          setNewsError({ assetId: newsAssetId, message: err instanceof Error ? err.message : String(err) });
          setAssetNews(null);
        }
      })
      .finally(() => {
        if (mountedRef.current && requestId === newsRequestIdRef.current) {
          setIsNewsLoading(false);
          setNewsLoadingAssetId(null);
        }
      });
  }, [profile?.canonical_asset_id]);

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
    setResearchReports(null);

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
  const visibleAssetNews =
    assetNews && profile && assetNews.asset_id === profile.canonical_asset_id ? assetNews : null;
  const visibleNewsError =
    newsError && profile && newsError.assetId === profile.canonical_asset_id ? newsError.message : null;
  const isVisibleNewsLoading = Boolean(
    isNewsLoading && profile && newsLoadingAssetId === profile.canonical_asset_id
  );
  const visibleResearchReports =
    researchReports && profile && researchReports.asset_id === profile.canonical_asset_id ? researchReports : null;
  const latestNewsDate = visibleAssetNews?.summary.latest_published_at?.slice(0, 10) ?? '-';
  const latestReportDate = visibleResearchReports?.summary.latest_report_date ?? '-';
  const currentEntryContext: StockEntryContext = {
    ...entryContext,
    assetId: profile?.canonical_asset_id ?? entryContext?.assetId ?? assetId,
    query: entryContext?.query ?? profile?.asset?.symbol ?? profile?.canonical_asset_id ?? assetId
  };
  const sourceObjectIds = [
    entryContext?.newsId ? `newsId: ${entryContext.newsId}` : null,
    entryContext?.eventKey ? `eventKey: ${entryContext.eventKey}` : null,
    entryContext?.reportId ? `reportId: ${entryContext.reportId}` : null,
    entryContext?.monitorTab ? `monitorTab: ${entryContext.monitorTab}` : null
  ].filter((value): value is string => Boolean(value));

  return (
    <section className="workspace-stack" aria-label="Stock Workspace workspace">
      <header className="workspace-header">
        <h1>{profile ? `${identityName} ${profile.canonical_asset_id}` : 'Stock Workspace'}</h1>
        <p className="muted">Single-stock evidence hub for price, factors, news, research reports, and strategy history.</p>
        {entryContext?.sourceWorkspace ? (
          <p className="muted">
            Opened from {formatSourceWorkspace(entryContext.sourceWorkspace)}
            {entryContext.matchReason ? (
              <>
                {' '}
                <span>{entryContext.matchReason}</span>
              </>
            ) : null}
          </p>
        ) : null}
        {sourceObjectIds.length > 0 ? (
          <div className="tag-stack" aria-label="Source object IDs">
            {sourceObjectIds.map((sourceObjectId) => (
              <span key={sourceObjectId} className="status-chip neutral">
                {sourceObjectId}
              </span>
            ))}
          </div>
        ) : null}
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
          <section className="stock-summary-strip" aria-label="Stock identity region">
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

          <section className="stock-summary-strip" aria-label="Stock evidence summary region">
            <div>
              <span>Signals</span>
              <strong>{profile.signals.length}</strong>
            </div>
            <div>
              <span>Decisions</span>
              <strong>{profile.decisions.length}</strong>
            </div>
            <div>
              <span>Outcomes</span>
              <strong>{profile.outcomes.length}</strong>
            </div>
            <div>
              <span>News 7d</span>
              <strong>{visibleAssetNews?.summary.news_count_7d ?? '-'}</strong>
            </div>
            <div>
              <span>Latest Report</span>
              <strong>{latestReportDate}</strong>
            </div>
          </section>

          <section className="workspace-band" aria-label="Context Rail Actions">
            <div className="section-heading">
              <h2>Context Actions</h2>
              <span className="muted">{profile.canonical_asset_id}</span>
            </div>
            <div className="compact-toolbar">
              <button type="button" onClick={() => onOpenNews?.(currentEntryContext)}>
                Open News workspace
              </button>
              <button type="button" onClick={() => onOpenResearchReports?.(currentEntryContext)}>
                Open Research Reports workspace
              </button>
              <button type="button" onClick={() => onOpenMarketMonitor?.(currentEntryContext)}>
                Open Market Monitor workspace
              </button>
            </div>
          </section>

          <section className="workspace-band" aria-label="Price & Events">
            <div className="section-heading">
              <h2>Price & Events</h2>
              <span className="muted">
                {profile.bars.length} bars / {startDate} to {endDate}
              </span>
            </div>
            {profile.bars.length > 0 ? <AssetChart bars={profile.bars} /> : <p className="muted">No bars available.</p>}
          </section>

          <section className="stock-evidence-grid">
            <article className="workspace-band" role="region" aria-label="Market Monitor State">
              <div className="section-heading">
                <h2>Market Monitor State</h2>
                <span className="muted">{profile.canonical_asset_id}</span>
              </div>
              <p className="muted">EOD monitor stock-list context will appear when opened from Market Monitor.</p>
            </article>

            <article className="workspace-band" role="region" aria-label="Strategy Signal">
              <div className="section-heading">
                <h2>Strategy Signal</h2>
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

            <article className="workspace-band" role="region" aria-label="Research Coverage">
              <div className="section-heading">
                <h2>Research Coverage</h2>
                {isResearchReportsLoading ? <span className="muted">Loading...</span> : null}
              </div>
              {researchReportsError ? <p className="error-text">{researchReportsError}</p> : null}
              {visibleResearchReports ? (
                <section className="stock-summary-strip" aria-label="Stock research report summary">
                  <div>
                    <span>Coverage</span>
                    <strong>90d reports {visibleResearchReports.summary.report_count_90d}</strong>
                  </div>
                  <div>
                    <span>30d Reports</span>
                    <strong>{visibleResearchReports.summary.report_count_30d}</strong>
                  </div>
                  <div>
                    <span>Brokers</span>
                    <strong>{visibleResearchReports.summary.broker_coverage_count_90d} brokers</strong>
                  </div>
                  <div>
                    <span>Latest Rating</span>
                    <strong>{formatValue(visibleResearchReports.summary.latest_rating)}</strong>
                  </div>
                  <div>
                    <span>Target Price</span>
                    <strong>{formatValue(visibleResearchReports.summary.latest_target_price)}</strong>
                  </div>
                </section>
              ) : null}
            </article>

            <article className="workspace-band" role="region" aria-label="Related News">
              <div className="section-heading">
                <h2>Related News</h2>
                {isVisibleNewsLoading ? <span className="muted">Loading...</span> : null}
              </div>
              {visibleAssetNews ? (
                <div className="metric-grid compact">
                  <span>
                    <span>1d News</span>
                    <strong>{visibleAssetNews.summary.news_count_1d}</strong>
                  </span>
                  <span>
                    <span>7d News</span>
                    <strong>{visibleAssetNews.summary.news_count_7d}</strong>
                  </span>
                  <span>
                    <span>Sources</span>
                    <strong>{visibleAssetNews.summary.source_count ?? 0}</strong>
                  </span>
                </div>
              ) : null}
              {visibleNewsError ? <p className="error-text">{visibleNewsError}</p> : null}
              {visibleAssetNews?.warnings?.length ? <p className="muted">{visibleAssetNews.warnings.join(' | ')}</p> : null}
              <div className="compact-news-list">
                {(visibleAssetNews?.items ?? []).map((item) => (
                  <a key={item.news_id} className="evidence-link-row" href={item.url} target="_blank" rel="noreferrer">
                    <strong>{item.title}</strong>
                    <span>{item.published_at.slice(0, 10)}</span>
                  </a>
                ))}
              </div>
              {!isVisibleNewsLoading && !visibleNewsError && (visibleAssetNews?.items.length ?? 0) === 0 ? (
                <p className="muted">No related news found.</p>
              ) : null}
            </article>

            <article className="workspace-band" role="region" aria-label="Research Reports">
              <div className="section-heading">
                <h2>Research Reports</h2>
                {isResearchReportsLoading ? <span className="muted">Loading...</span> : null}
              </div>
              <div className="compact-news-list">
                {(visibleResearchReports?.items ?? []).map((report) =>
                  report.source_url ? (
                    <a
                      key={report.event_key}
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
                    <div key={report.event_key} className="evidence-link-row">
                      <strong>{report.report_title}</strong>
                      <span>
                        {formatValue(report.broker)} / {formatValue(report.publish_date ?? report.report_date)}
                      </span>
                    </div>
                  )
                )}
              </div>
              {!isResearchReportsLoading && !researchReportsError && (visibleResearchReports?.items.length ?? 0) === 0 ? (
                <p className="muted">No research reports found.</p>
              ) : null}
            </article>

            <article className="workspace-band" role="region" aria-label="Factor / Score Breakdown">
              <div className="section-heading">
                <h2>Factor / Score Breakdown</h2>
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

            <article className="workspace-band" role="region" aria-label="Review / Outcomes">
              <div className="section-heading">
                <h2>Review / Outcomes</h2>
                <span className="muted">
                  {profile.decisions.length} decisions / {profile.outcomes.length} outcomes
                </span>
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
              {profile.outcomes.map((outcome) => (
                <div key={outcome.outcome_event_id} className="evidence-row">
                  <div>
                    <strong>{outcome.outcome_status}</strong>
                    <span>{outcome.review_date}</span>
                  </div>
                  <p>
                    {outcome.decision_label} / {outcome.available_future_bars} future bars
                  </p>
                  <span>{outcome.outcome_artifact_path}</span>
                </div>
              ))}
              {profile.decisions.length === 0 && profile.outcomes.length === 0 ? (
                <p className="muted">No review decisions or outcomes recorded.</p>
              ) : null}
            </article>

            <article className="workspace-band" role="region" aria-label="Evidence Timeline">
              <div className="section-heading">
                <h2>Evidence Timeline</h2>
                <span className="muted">Current loaded evidence</span>
              </div>
              <div className="report-list compact">
                <div className="evidence-row">
                  <div>
                    <strong>Price coverage</strong>
                    <span>{profile.coverage?.bars?.end ?? endDate}</span>
                  </div>
                  <p>{profile.bars.length} loaded bars</p>
                </div>
                {profile.decisions.map((decision) => (
                  <div key={`timeline-${decision.event_id}`} className="evidence-row">
                    <div>
                      <strong>Review decision</strong>
                      <span>{decision.review_date}</span>
                    </div>
                    <p>{decision.decision_label}</p>
                  </div>
                ))}
                {profile.outcomes.map((outcome) => (
                  <div key={`timeline-${outcome.outcome_event_id}`} className="evidence-row">
                    <div>
                      <strong>Decision outcome</strong>
                      <span>{outcome.review_date}</span>
                    </div>
                    <p>{outcome.outcome_status}</p>
                    <span>{outcome.outcome_artifact_path}</span>
                  </div>
                ))}
                {(visibleAssetNews?.items ?? []).map((item) => (
                  <div key={`timeline-${item.news_id}`} className="evidence-row">
                    <div>
                      <strong>News item</strong>
                      <span>{item.published_at.slice(0, 10)}</span>
                    </div>
                    <p>News: {item.title}</p>
                  </div>
                ))}
                {(visibleResearchReports?.items ?? []).map((report) => (
                  <div key={`timeline-${report.event_key}`} className="evidence-row">
                    <div>
                      <strong>Research report</strong>
                      <span>{formatValue(report.publish_date ?? report.report_date)}</span>
                    </div>
                    <p>Research: {report.report_title}</p>
                  </div>
                ))}
                {(visibleAssetNews?.items.length ?? 0) === 0 ? (
                  <div className="evidence-row">
                    <div>
                      <strong>Latest news</strong>
                      <span>{latestNewsDate}</span>
                    </div>
                    <p>No loaded related news</p>
                  </div>
                ) : null}
                {(visibleResearchReports?.items.length ?? 0) === 0 ? (
                  <div className="evidence-row">
                    <div>
                      <strong>Latest research</strong>
                      <span>{latestReportDate}</span>
                    </div>
                    <p>No loaded research coverage</p>
                  </div>
                ) : null}
              </div>
            </article>

            <article className="workspace-band" role="region" aria-label="Search Matches">
              <div className="section-heading">
                <h2>Search Matches</h2>
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
