import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchPublicNews, refreshPublicNews } from '../api/client';
import type { PublicNewsItem, PublicNewsSummary } from '../api/types';

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

const NEWS_REFRESH_INTERVAL_MS = 60000;

type NewsWorkspaceProps = {
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

export function NewsWorkspace({ onOpenAsset }: NewsWorkspaceProps) {
  const [items, setItems] = useState<PublicNewsItem[]>([]);
  const [summary, setSummary] = useState<PublicNewsSummary | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [category, setCategory] = useState('all');
  const [query, setQuery] = useState('');
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

  const loadInitialNews = useCallback(async () => {
    const requestId = nextRequestId();
    setIsLoading(true);
    try {
      const payload = await fetchPublicNews({ source: 'sina_finance', limit: 200 });
      if (isLatestRequest(requestId)) {
        setItems(payload.items);
        setSummary(payload.summary ?? null);
        setWarnings(payload.warnings ?? []);
        setLastUpdatedAt(payload.summary?.latest_collected_at ?? new Date().toLocaleTimeString());
      }
    } catch (err: unknown) {
      if (isLatestRequest(requestId)) {
        setWarnings([err instanceof Error ? err.message : String(err)]);
      }
    } finally {
      if (isLatestRequest(requestId)) setIsLoading(false);
    }
  }, [isLatestRequest, nextRequestId]);

  const refreshNews = useCallback(async () => {
    const requestId = nextRequestId();
    try {
      const refreshResult = await refreshPublicNews();
      const payload = await fetchPublicNews({ source: 'sina_finance', limit: 200 });
      if (isLatestRequest(requestId)) {
        setItems(payload.items);
        setSummary(payload.summary ?? null);
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
  }, [isLatestRequest, nextRequestId]);

  useEffect(() => {
    isMountedRef.current = true;
    void loadInitialNews();

    const timer = window.setInterval(() => {
      void refreshNews();
    }, NEWS_REFRESH_INTERVAL_MS);

    return () => {
      window.clearInterval(timer);
      isMountedRef.current = false;
      requestIdRef.current += 1;
    };
  }, [loadInitialNews, refreshNews]);

  const visibleItems = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return items.filter((item) => {
      const categoryMatch = category === 'all' || item.category === category;
      const queryMatch =
        !needle ||
        item.title.toLowerCase().includes(needle) ||
        item.summary.toLowerCase().includes(needle);
      return categoryMatch && queryMatch;
    });
  }, [category, items, query]);

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
          {summary?.total_news !== undefined ? <span className="metric-chip">{summary.total_news} rows</span> : null}
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
        ) : visibleItems.length === 0 ? (
          <p className="muted">No news for current filters.</p>
        ) : (
          <div className="news-feed">
            {visibleItems.map((item) => (
              <article key={item.news_id} className="news-feed-row">
                <div className="news-feed-meta">
                  <span>{item.published_at.slice(5, 16)}</span>
                  <span>{labelForCategory(item.category)}</span>
                  <span>{item.source_channel}</span>
                </div>
                {item.url ? (
                  <a href={item.url} target="_blank" rel="noreferrer">
                    {item.title}
                  </a>
                ) : (
                  <strong>{item.title}</strong>
                )}
                {item.summary ? <p>{item.summary}</p> : null}
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
            ))}
          </div>
        )}
      </section>
    </section>
  );
}

function labelForCategory(category: string) {
  return CATEGORIES.find((item) => item.id === category)?.label ?? category;
}
