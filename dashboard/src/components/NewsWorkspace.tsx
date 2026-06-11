import { useEffect, useMemo, useState } from 'react';
import { fetchPublicNews, refreshPublicNews } from '../api/client';
import type { PublicNewsItem } from '../api/types';

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

export function NewsWorkspace() {
  const [items, setItems] = useState<PublicNewsItem[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [category, setCategory] = useState('all');
  const [query, setQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  useEffect(() => {
    let ignore = false;
    setIsLoading(true);
    fetchPublicNews({ source: 'sina_finance', limit: 200 })
      .then((payload) => {
        if (!ignore) {
          setItems(payload.items);
          setWarnings(payload.warnings ?? []);
          setIsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setWarnings([err instanceof Error ? err.message : String(err)]);
          setIsLoading(false);
        }
      });
    return () => {
      ignore = true;
    };
  }, []);

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
      const refreshResult = await refreshPublicNews();
      const payload = await fetchPublicNews({ source: 'sina_finance', limit: 200 });
      setItems(payload.items);
      setWarnings([...(refreshResult.warnings ?? []), ...(payload.warnings ?? [])]);
    } finally {
      setIsRefreshing(false);
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
        {warnings.length > 0 ? <p className="muted">{warnings[0]}</p> : null}
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
