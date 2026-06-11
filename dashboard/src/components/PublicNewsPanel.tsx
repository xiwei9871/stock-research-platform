import { ExternalLink, RefreshCw, Search } from 'lucide-react';
import { useMemo, useState } from 'react';
import type { PublicNewsItem } from '../api/types';

type Props = {
  items: PublicNewsItem[];
  warnings: string[];
  isLoading?: boolean;
  onRefresh: () => Promise<void>;
};

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

export function PublicNewsPanel({ items, warnings, isLoading = false, onRefresh }: Props) {
  const [category, setCategory] = useState('all');
  const [query, setQuery] = useState('');
  const [refreshing, setRefreshing] = useState(false);

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
    setRefreshing(true);
    try {
      await onRefresh();
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <section className="inspector-section public-news-panel">
      <div className="section-header">
        <h2>Public News</h2>
        <button
          aria-label="Refresh news"
          className="icon-button"
          type="button"
          onClick={handleRefresh}
          disabled={refreshing}
          title="Refresh news"
        >
          <RefreshCw size={15} />
        </button>
      </div>
      <div className="news-toolbar">
        <span className="source-pill">新浪财经</span>
        <label className="search-box">
          <Search size={14} />
          <input
            aria-label="news search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search"
          />
        </label>
      </div>
      <div className="category-rail">
        {CATEGORIES.map((item) => (
          <button
            key={item.id}
            className={item.id === category ? 'category-button active' : 'category-button'}
            type="button"
            onClick={() => setCategory(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      {warnings.length > 0 ? <p className="muted">{warnings[0]}</p> : null}
      {isLoading ? (
        <p className="muted">Loading public news...</p>
      ) : visibleItems.length === 0 ? (
        <p className="muted">No public news for current filters.</p>
      ) : (
        <div className="news-list">
          {visibleItems.map((item) => (
            <article className="news-row" key={item.news_id}>
              <div className="news-row-meta">
                <span>{formatTime(item.published_at)}</span>
                <span>{labelForCategory(item.category)}</span>
                <span>{item.source_channel}</span>
              </div>
              <a href={item.url || '#'} target="_blank" rel="noreferrer">
                <strong>{item.title}</strong>
                {item.url ? <ExternalLink size={13} /> : null}
              </a>
              {item.summary ? <p>{item.summary}</p> : null}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function labelForCategory(category: string) {
  return CATEGORIES.find((item) => item.id === category)?.label ?? category;
}

function formatTime(value: string) {
  if (!value) return '';
  return value.slice(5, 16);
}
