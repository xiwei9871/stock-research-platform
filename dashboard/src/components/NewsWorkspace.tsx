import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchPublicNews, fetchPublicNewsStatus, refreshPublicNews } from '../api/client';
import type { PublicNewsCollectorStatus, PublicNewsItem, PublicNewsSummary } from '../api/types';

const CATEGORIES = [
  { id: 'all', label: '全部' },
  { id: 'live', label: '7x24' },
  { id: 'focus', label: '焦点' },
  { id: 'company', label: '公司' },
  { id: 'market', label: '市场' },
  { id: 'macro', label: '宏观' },
  { id: 'international', label: '国际' },
  { id: 'opinion', label: '观点' },
  { id: 'original', label: '原创' },
  { id: 'other', label: '其他' }
];

const NEWS_REFRESH_INTERVAL_MS = 30 * 60 * 1000;

type NewsWorkspaceProps = {
  initialQuery?: string;
  initialNewsId?: string;
  onOpenAsset?: (assetId: string) => void;
};

function normalizeCandidate(value: string) {
  const withExchange = value.match(/\b(\d{6})\.(SZ|SH)\b/i);
  if (withExchange) {
    return `${withExchange[1]}.${withExchange[2].toUpperCase()}`;
  }
  const bareCode = value.match(/\b(\d{6})\b/);
  if (bareCode) {
    return `${bareCode[1]}.${bareCode[1].startsWith('6') ? 'SH' : 'SZ'}`;
  }
  return null;
}

function candidateSource(value: unknown) {
  if (typeof value === 'string' || typeof value === 'number') {
    return normalizeCandidate(String(value));
  }
  return null;
}

export function getNewsAssetCandidate(item: PublicNewsItem) {
  const rawPayloadKeys = ['asset_id', 'stock_code', 'symbol', 'code'];
  for (const key of rawPayloadKeys) {
    const candidate = candidateSource(item.raw_payload[key]);
    if (candidate) return candidate;
  }
  for (const value of [item.title, item.summary, item.url]) {
    const candidate = candidateSource(value);
    if (candidate) return candidate;
  }
  return null;
}

export function NewsWorkspace({ initialQuery = '', initialNewsId, onOpenAsset }: NewsWorkspaceProps) {
  const [items, setItems] = useState<PublicNewsItem[]>([]);
  const [summary, setSummary] = useState<PublicNewsSummary | null>(null);
  const [collectorStatus, setCollectorStatus] = useState<PublicNewsCollectorStatus | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [category, setCategory] = useState('all');
  const [query, setQuery] = useState(initialQuery);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string>('');
  const isMountedRef = useRef(false);
  const requestIdRef = useRef(0);

  const nextRequestId = useCallback(() => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    return requestId;
  }, []);

  const isLatestRequest = useCallback(
    (requestId: number) => isMountedRef.current && requestId === requestIdRef.current,
    []
  );

  const newsParams = useCallback(() => {
    const params: Parameters<typeof fetchPublicNews>[0] = {
      source: 'sina_finance',
      limit: 3,
      minQualityScore: 70
    };
    if (category !== 'all') params.category = category;
    const trimmedQuery = query.trim();
    if (trimmedQuery) params.q = trimmedQuery;
    return params;
  }, [category, query]);

  const loadCollectorStatus = useCallback(
    async (requestId: number, fallbackSummary?: PublicNewsSummary | null) => {
      try {
        const status = await fetchPublicNewsStatus();
        if (isLatestRequest(requestId)) setCollectorStatus(status);
      } catch {
        if (isLatestRequest(requestId) && fallbackSummary?.collector_status) {
          setCollectorStatus(fallbackSummary.collector_status);
        }
      }
    },
    [isLatestRequest]
  );

  const loadAcceptedNews = useCallback(async () => {
    const requestId = nextRequestId();
    setIsLoading(true);
    try {
      const payload = await fetchPublicNews(newsParams());
      if (isLatestRequest(requestId)) {
        setItems(payload.items);
        setSummary(payload.summary ?? null);
        setWarnings(payload.warnings ?? []);
        setLastUpdatedAt(payload.summary?.latest_collected_at ?? new Date().toLocaleTimeString());
        void loadCollectorStatus(requestId, payload.summary);
      }
    } catch (err: unknown) {
      if (isLatestRequest(requestId)) {
        setItems([]);
        setSummary(null);
        setWarnings([err instanceof Error ? err.message : String(err)]);
      }
    } finally {
      if (isLatestRequest(requestId)) setIsLoading(false);
    }
  }, [isLatestRequest, loadCollectorStatus, newsParams, nextRequestId]);

  const reloadAcceptedNews = useCallback(async () => {
    const requestId = nextRequestId();
    try {
      const payload = await fetchPublicNews(newsParams());
      if (isLatestRequest(requestId)) {
        setItems(payload.items);
        setSummary(payload.summary ?? null);
        setWarnings(payload.warnings ?? []);
        setLastUpdatedAt(payload.summary?.latest_collected_at ?? new Date().toLocaleTimeString());
        void loadCollectorStatus(requestId, payload.summary);
        setIsLoading(false);
      }
    } catch (err: unknown) {
      if (isLatestRequest(requestId)) {
        setWarnings([err instanceof Error ? err.message : String(err)]);
        setIsLoading(false);
      }
    }
  }, [isLatestRequest, loadCollectorStatus, newsParams, nextRequestId]);

  const refreshNews = useCallback(async () => {
    const requestId = nextRequestId();
    try {
      const refreshResult = await refreshPublicNews();
      const payload = await fetchPublicNews(newsParams());
      if (isLatestRequest(requestId)) {
        setItems(payload.items);
        setSummary(payload.summary ?? null);
        void loadCollectorStatus(requestId, payload.summary);
        setWarnings([...(refreshResult.warnings ?? []), ...(payload.warnings ?? [])]);
        setLastUpdatedAt(payload.summary?.latest_collected_at ?? new Date().toLocaleTimeString());
        setIsLoading(false);
      }
    } catch (err: unknown) {
      if (isLatestRequest(requestId)) {
        setWarnings([err instanceof Error ? err.message : String(err)]);
        setIsLoading(false);
      }
    }
  }, [isLatestRequest, loadCollectorStatus, newsParams, nextRequestId]);

  useEffect(() => {
    isMountedRef.current = true;
    void loadAcceptedNews();

    const timer = window.setInterval(() => {
      void reloadAcceptedNews();
    }, NEWS_REFRESH_INTERVAL_MS);

    return () => {
      window.clearInterval(timer);
      isMountedRef.current = false;
      requestIdRef.current += 1;
    };
  }, [loadAcceptedNews, reloadAcceptedNews]);

  useEffect(() => {
    setQuery(initialQuery);
  }, [initialQuery]);

  async function handleRefresh() {
    setIsRefreshing(true);
    try {
      await refreshNews();
    } finally {
      if (isMountedRef.current) setIsRefreshing(false);
    }
  }

  return (
    <section className="news-workspace" aria-label="News workspace">
      <header className="workspace-header">
        <h1>News</h1>
        <p className="muted">公开财经新闻聚合，当前来源为新浪财经，点击标题跳转原文。</p>
      </header>

      <section className="workspace-panel">
        <div className="section-heading">
          <h2>新浪财经</h2>
          {summary?.latest_collected_at ? (
            <span className="muted">DB collected {summary.latest_collected_at}</span>
          ) : lastUpdatedAt ? (
            <span className="muted">Last updated {lastUpdatedAt}</span>
          ) : null}
          <span className="metric-chip">{items.length}/3 accepted</span>
          {collectorStatus?.next_run_at ? <span className="muted">next run {collectorStatus.next_run_at}</span> : null}
          {collectorStatus && !collectorStatus.enabled ? <span className="metric-chip">collector off</span> : null}
          <button type="button" onClick={handleRefresh} disabled={isRefreshing}>
            {isRefreshing ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
        <div className="news-controls">
          <input
            aria-label="news search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search news"
          />
          <div className="news-category-row">
            {CATEGORIES.map((item) => (
              <button
                key={item.id}
                className={category === item.id ? 'active' : ''}
                type="button"
                onClick={() => setCategory(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
        {warnings.length > 0 ? (
          <div className="warning-strip">
            {warnings.map((warning) => (
              <span key={warning}>{warning}</span>
            ))}
          </div>
        ) : null}
        {isLoading ? (
          <p className="muted">Loading news...</p>
        ) : items.length === 0 ? (
          <p className="muted">本轮无高质量新闻</p>
        ) : (
          <div className="news-feed">
            {items.map((item) => {
              const isSelected = initialNewsId ? item.news_id === initialNewsId : false;

              return (
                <article
                  key={item.news_id}
                  className={`news-feed-row${isSelected ? ' news-feed-row--selected' : ''}`}
                >
                  <div className="news-feed-meta">
                    <span>{item.published_at.slice(5, 16)}</span>
                    <span>{labelForCategory(item.category)}</span>
                    <span>{item.source_channel}</span>
                    {item.quality_score !== undefined && item.quality_score !== null ? (
                      <span>quality {item.quality_score}</span>
                    ) : null}
                  </div>
                  {item.url ? (
                    <a href={item.url} target="_blank" rel="noreferrer">
                      {item.title}
                    </a>
                  ) : (
                    <strong>{item.title}</strong>
                  )}
                  {item.summary ? <p>{item.summary}</p> : null}
                  {(item.quality_reasons ?? []).length > 0 ? (
                    <div className="news-stock-row">
                      {(item.quality_reasons ?? []).map((reason) => (
                        <span key={reason} className="metric-chip">
                          {reason}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  {(item.stocks ?? []).length > 0 ? (
                    <div className="news-stock-row">
                      {(item.stocks ?? []).map((stock) => (
                        <button
                          key={stock.asset_id || stock.ts_code}
                          type="button"
                          className="link-chip"
                          aria-label={`Open ${stock.stock_name || stock.ts_code} in Stock Workspace`}
                          onClick={() => onOpenAsset?.(stock.asset_id || stock.ts_code)}
                        >
                          {stock.stock_name || stock.ts_code}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        )}
      </section>
    </section>
  );
}

function labelForCategory(category: string) {
  return CATEGORIES.find((item) => item.id === category)?.label ?? category;
}
