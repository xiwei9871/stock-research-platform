import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchWatchlistSignals } from '../api/client';
import type { AssetThemeResearchContext, WatchlistSignalRow } from '../api/types';

const DEFAULT_WATCHLIST_ID = 'default';
const DEFAULT_TRADE_DATE = '2026-06-18';

type WatchlistWorkspaceProps = {
  onOpenAsset?: (assetId: string) => void;
  defaultTradeDate?: string;
};

function formatTags(tags: string[]) {
  return tags.length > 0 ? tags.join(', ') : '-';
}

function reasonField(row: WatchlistSignalRow, key: string) {
  const value = row.reason_json[key];
  return typeof value === 'string' ? value : '-';
}

function rowMatchesQuery(row: WatchlistSignalRow, query: string) {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return [
    row.asset_id,
    row.stock_code,
    row.stock_name,
    row.primary_signal,
    ...row.signal_tags,
    ...row.risk_tags,
    ...(row.theme_research_context?.themes.map((theme) => theme.theme_name) ?? []),
    ...(row.theme_research_context?.mappings.map((mapping) => mapping.node.node_name) ?? [])
  ].some((value) => value.toLowerCase().includes(needle));
}

function ThemeResearchCell({ context }: { context?: AssetThemeResearchContext }) {
  if (!context || context.status === 'unavailable') {
    return <span className="muted">主题研究暂不可用</span>;
  }
  if (context.status === 'evidence_gap') {
    return (
      <div className="watchlist-theme-context">
        <strong>证据待补</strong>
        <span>{context.evidence_gap_count} 条映射未通过审核门槛</span>
        <small>不参与信号或准入</small>
      </div>
    );
  }
  const theme = context.themes[0];
  const mapping = context.mappings[0];
  if (!theme || !mapping) {
    return (
      <div className="watchlist-theme-context">
        <span className="muted">未建立审核映射</span>
        <small>不参与信号或准入</small>
      </div>
    );
  }
  return (
    <div className="watchlist-theme-context">
      <a href={theme.dashboard_path}>{theme.theme_name}</a>
      <span>
        {mapping.node.node_name} · 价值量 {mapping.node.value_capture_score}/5 · 卡脖子{' '}
        {mapping.node.bottleneck_score}/5
      </span>
      <small>已审核研究</small>
    </div>
  );
}

export function WatchlistWorkspace({ onOpenAsset, defaultTradeDate = DEFAULT_TRADE_DATE }: WatchlistWorkspaceProps) {
  const [watchlistId, setWatchlistId] = useState(DEFAULT_WATCHLIST_ID);
  const [tradeDate, setTradeDate] = useState(defaultTradeDate || DEFAULT_TRADE_DATE);
  const [status, setStatus] = useState('all');
  const [minPriority, setMinPriority] = useState(0);
  const [query, setQuery] = useState('');
  const [rows, setRows] = useState<WatchlistSignalRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(false);
  const requestIdRef = useRef(0);

  const loadQueue = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setIsLoading(true);
    setError(null);

    try {
      const nextRows = await fetchWatchlistSignals(watchlistId, tradeDate);
      if (mountedRef.current && requestId === requestIdRef.current) {
        setRows(nextRows);
      }
    } catch (err: unknown) {
      if (mountedRef.current && requestId === requestIdRef.current) {
        setRows([]);
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      if (mountedRef.current && requestId === requestIdRef.current) {
        setIsLoading(false);
      }
    }
  }, [tradeDate, watchlistId]);

  useEffect(() => {
    mountedRef.current = true;
    void loadQueue();
    return () => {
      mountedRef.current = false;
      requestIdRef.current += 1;
    };
  }, [loadQueue]);

  const visibleRows = useMemo(
    () =>
      rows.filter((row) => {
        const statusMatch = status === 'all' || row.primary_signal === status;
        const priorityMatch = row.priority >= minPriority;
        return statusMatch && priorityMatch && rowMatchesQuery(row, query);
      }),
    [minPriority, query, rows, status]
  );

  return (
    <section className="workspace-stack" aria-label="Watchlist workspace">
      <header className="workspace-header">
        <h1>观察池</h1>
        <p className="muted">人工复盘后需要继续跟踪的标的，会按日期、状态、优先级和下一步动作集中展示。</p>
      </header>
      <section className="workspace-panel">
        <div className="section-heading">
          <h2>EOD 观察队列</h2>
          <span className="status-chip neutral">{visibleRows.length} 条</span>
        </div>
        <div className="queue-filters">
          <label>
            观察池
            <input
              aria-label="watchlist id"
              value={watchlistId}
              onChange={(event) => setWatchlistId(event.target.value)}
            />
          </label>
          <label>
            交易日期
            <input
              aria-label="trade date"
              type="date"
              value={tradeDate}
              onChange={(event) => setTradeDate(event.target.value)}
            />
          </label>
          <label>
            状态
            <select
              aria-label="watchlist status"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="all">全部</option>
              <option value="candidate">candidate</option>
              <option value="observe">observe</option>
              <option value="holding">holding</option>
              <option value="review">review</option>
            </select>
          </label>
          <label>
            最低优先级
            <input
              aria-label="minimum priority"
              type="number"
              min="0"
              value={minPriority}
              onChange={(event) => setMinPriority(Number(event.target.value) || 0)}
            />
          </label>
          <label>
            信号/风险搜索
            <input
              aria-label="signal risk query"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="股票、信号、风险"
            />
          </label>
          <button type="button" onClick={() => void loadQueue()} disabled={isLoading}>
            刷新队列
          </button>
        </div>
        {error ? <p className="muted">{error}</p> : null}
        {isLoading ? (
          <p className="muted">正在加载 EOD 观察队列...</p>
        ) : visibleRows.length === 0 ? (
          <div className="empty-state">
            <strong>当前观察池暂无记录。</strong>
            <p className="muted">当前日期暂无观察记录。你可以在个股工作台点击“观察”创建人工观察项；如果想看策略候选池，请切换到复盘队列。</p>
            <p className="muted">{`当前查询：${watchlistId} / ${tradeDate}`}</p>
          </div>
        ) : (
          <div className="queue-table-wrap">
            <table className="queue-table">
              <thead>
                <tr>
                  <th>股票</th>
                  <th>状态</th>
                  <th>优先级</th>
                  <th>信号</th>
                  <th>风险</th>
                  <th>主题研究</th>
                  <th>原因</th>
                  <th>下一步</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row) => (
                  <tr key={`${row.trade_date}:${row.asset_id}`}>
                    <td>
                      <strong>{row.stock_name}</strong>
                      <span className="muted">{row.asset_id}</span>
                    </td>
                    <td>{row.primary_signal}</td>
                    <td>{row.priority}</td>
                    <td>{formatTags(row.signal_tags)}</td>
                    <td>{formatTags(row.risk_tags)}</td>
                    <td>
                      <ThemeResearchCell context={row.theme_research_context} />
                    </td>
                    <td>{reasonField(row, 'reason')}</td>
                    <td>{reasonField(row, 'next_action')}</td>
                    <td>
                      <button
                        className="compact-action-button"
                        type="button"
                        aria-label={`Open ${row.asset_id}`}
                        onClick={() => onOpenAsset?.(row.asset_id)}
                      >
                        打开
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </section>
  );
}
