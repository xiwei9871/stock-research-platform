import { type FormEvent, type KeyboardEvent, useCallback, useEffect, useRef, useState } from 'react';
import { fetchMarketMonitorEod } from '../api/client';
import type { EmotionStockListRow, MarketMonitorPayload } from '../api/types';

function formatCount(value: number | null | undefined) {
  return typeof value === 'number' ? value.toLocaleString() : '-';
}

function formatScore(value: number | null | undefined) {
  return typeof value === 'number' ? value.toFixed(1) : '-';
}

function formatPercent(value: number | null | undefined, digits = 2) {
  return typeof value === 'number' ? `${(value * 100).toFixed(digits)}%` : '-';
}

function formatPercentPoints(value: number | null | undefined, digits = 2) {
  return typeof value === 'number' ? `${value.toFixed(digits)}%` : '-';
}

function formatAmountYi(value: number | null | undefined) {
  return typeof value === 'number' ? `${(value / 100000000).toFixed(2)}亿` : '-';
}

function formatRatio(value: number | null | undefined) {
  return typeof value === 'number' ? `${value.toFixed(2)}x` : '-';
}

type StockTabKey = 'auction' | 'limit_up' | 'broken_limit_up' | 'limit_down';

const STOCK_TABS: Array<{ key: StockTabKey; label: string }> = [
  { key: 'auction', label: '竞价' },
  { key: 'limit_up', label: '涨停' },
  { key: 'broken_limit_up', label: '炸板' },
  { key: 'limit_down', label: '跌停' }
];

export function MarketMonitorWorkspace() {
  const [payload, setPayload] = useState<MarketMonitorPayload | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tradeDateInput, setTradeDateInput] = useState('');
  const [loadingTradeDate, setLoadingTradeDate] = useState<string | null>(null);
  const [activeStockTab, setActiveStockTab] = useState<StockTabKey>('limit_up');
  const isMountedRef = useRef(false);
  const requestIdRef = useRef(0);
  const stockTabRefs = useRef<Record<StockTabKey, HTMLButtonElement | null>>({
    auction: null,
    limit_up: null,
    broken_limit_up: null,
    limit_down: null
  });

  const loadMarketMonitor = useCallback(async (tradeDate?: string) => {
    const requestedTradeDate = tradeDate?.trim();
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setIsLoading(true);
    setLoadingTradeDate(requestedTradeDate || null);
    setError(null);
    try {
      const latestPayload = await fetchMarketMonitorEod(
        requestedTradeDate ? { topN: 5, tradeDate: requestedTradeDate } : { topN: 5 }
      );
      if (isMountedRef.current && requestId === requestIdRef.current) {
        setPayload(latestPayload);
        setTradeDateInput(latestPayload.trade_date || requestedTradeDate || '');
      }
    } catch (err: unknown) {
      if (isMountedRef.current && requestId === requestIdRef.current) {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      if (isMountedRef.current && requestId === requestIdRef.current) {
        setIsLoading(false);
        setLoadingTradeDate(null);
      }
    }
  }, []);

  const loadLatest = useCallback(async () => {
    await loadMarketMonitor();
  }, [loadMarketMonitor]);

  useEffect(() => {
    isMountedRef.current = true;
    void loadLatest();

    return () => {
      isMountedRef.current = false;
      requestIdRef.current += 1;
    };
  }, [loadLatest]);

  const emotion = payload?.market_emotion;
  const summary = emotion?.summary;
  const breadth = emotion?.breadth;
  const liquidity = emotion?.liquidity;
  const limitPerformance = emotion?.limit_performance;
  const profitEffect = emotion?.profit_effect;
  const drawdownPressure = emotion?.drawdown_pressure;
  const weightPerformance = emotion?.weight_performance;
  const emotionComponents = emotion?.components ?? [];
  const stockLists = payload?.emotion_stock_lists;
  const stockCount = (tab: StockTabKey) => stockLists?.[tab]?.length ?? 0;
  const dataModeLabel = payload?.freshness?.label?.toLowerCase().includes('historical')
    ? 'Historical EOD Snapshot'
    : 'EOD Snapshot';
  const topnPreview = payload?.strategy_signal_summary?.topn_preview ?? [];
  const generatedReports = payload?.generated_reports ?? [];
  const activeStockTabIndex = STOCK_TABS.findIndex((tab) => tab.key === activeStockTab);
  const handleTradeDateSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const tradeDateField = event.currentTarget.elements.namedItem('market-monitor-trade-date');
    const selectedTradeDate = tradeDateField instanceof HTMLInputElement ? tradeDateField.value : tradeDateInput;
    void loadMarketMonitor(selectedTradeDate);
  };
  const selectStockTab = (nextTab: StockTabKey) => {
    setActiveStockTab(nextTab);
    stockTabRefs.current[nextTab]?.focus();
  };
  const handleStockTabKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
      event.preventDefault();
      const direction = event.key === 'ArrowRight' ? 1 : -1;
      const nextIndex = (activeStockTabIndex + direction + STOCK_TABS.length) % STOCK_TABS.length;
      selectStockTab(STOCK_TABS[nextIndex].key);
      return;
    }
    if (event.key === 'Home') {
      event.preventDefault();
      selectStockTab(STOCK_TABS[0].key);
      return;
    }
    if (event.key === 'End') {
      event.preventDefault();
      selectStockTab(STOCK_TABS[STOCK_TABS.length - 1].key);
    }
  };

  return (
    <section className="workspace-stack" aria-label="Market Monitor workspace">
      <header className="workspace-header workspace-header-row">
        <div>
          <h1>Market Monitor</h1>
          <p className="muted">EOD market state for the latest completed trading day.</p>
        </div>
        <button type="button" onClick={loadLatest} aria-label="Load Latest EOD">
          {isLoading ? 'Loading...' : 'Load Latest EOD'}
        </button>
      </header>

      {error ? <p className="error-text">{error}</p> : null}
      {isLoading && loadingTradeDate ? <p className="pending-note">Loading {loadingTradeDate}...</p> : null}
      {(payload?.warnings ?? []).map((warning) => <p className="warning-text" key={warning}>{warning}</p>)}

      <form className="market-date-controls" aria-label="Market monitor date controls" onSubmit={handleTradeDateSubmit}>
        <label>
          <span>Trade Date</span>
          <input
            aria-label="Market monitor trade date"
            name="market-monitor-trade-date"
            type="date"
            value={tradeDateInput}
            onChange={(event) => setTradeDateInput(event.target.value)}
          />
        </label>
        <button type="submit" disabled={isLoading || !tradeDateInput}>
          {isLoading ? 'Loading...' : 'Load Date'}
        </button>
      </form>

      <section className="status-strip" aria-label="Market monitor freshness">
        <div>
          <span>Mode</span>
          <strong>{payload?.freshness?.label ?? 'Last Completed Trading Day'}</strong>
        </div>
        <div>
          <span>Trade Date</span>
          <strong>{payload?.trade_date || '-'}</strong>
        </div>
        <div>
          <span>Data Mode</span>
          <strong>{dataModeLabel}</strong>
        </div>
      </section>

      <section className="market-emotion-summary" aria-label="EOD market emotion summary">
        <div className="emotion-score-panel">
          <span>综合强度</span>
          <strong>{formatScore(summary?.score)}</strong>
          <em>{summary?.state || '-'}</em>
        </div>
        <div className="emotion-card">
          <span>涨跌家数</span>
          <strong>{formatCount(breadth?.up_count)}</strong>
          <small>上涨 / 下跌 {formatCount(breadth?.up_count)} / {formatCount(breadth?.down_count)}</small>
        </div>
        <div className="emotion-card">
          <span>市场量能</span>
          <strong>{formatRatio(liquidity?.amount_ratio_5_20)}</strong>
          <small>成交额 {formatAmountYi(liquidity?.total_amount)}</small>
        </div>
        <div className="emotion-card">
          <span>涨停表现</span>
          <strong>最高 {formatCount(limitPerformance?.high_board_height)} 板</strong>
          <small>涨停 {formatCount(limitPerformance?.limit_up_count)} / 炸板 {formatCount(limitPerformance?.broken_limit_up_count)}</small>
        </div>
        <div className="emotion-card">
          <span>大幅回撤</span>
          <strong>{formatCount(drawdownPressure?.strong_down_count)}</strong>
          <small>跌停 {formatCount(drawdownPressure?.limit_down_count)} / 炸板率 {formatPercent(drawdownPressure?.broken_limit_up_rate)}</small>
        </div>
        <div className="emotion-card pending">
          <span>权重表现</span>
          <strong>权重表现待接入</strong>
          <small>{weightPerformance?.status || 'pending_source'}</small>
        </div>
      </section>

      <section className="emotion-dashboard-grid">
        <section className="workspace-panel">
          <div className="section-heading">
            <h2>赚钱效应</h2>
            <span className="status-chip neutral">{profitEffect?.status || 'pending_source'}</span>
          </div>
          <div className="emotion-metric-grid">
            <div>
              <span>昨日涨停成功</span>
              <strong>{formatPercent(profitEffect?.limit_up_success_rate)}</strong>
            </div>
            <div>
              <span>昨日涨停收益</span>
              <strong>{formatPercent(profitEffect?.limit_up_profit_rate)}</strong>
            </div>
            <div>
              <span>接力成功</span>
              <strong>{formatPercent(profitEffect?.relay_success_rate)}</strong>
            </div>
            <div>
              <span>接力收益</span>
              <strong>{formatPercent(profitEffect?.relay_profit_rate)}</strong>
            </div>
            <div>
              <span>炸板修复</span>
              <strong>{formatPercent(profitEffect?.broken_success_rate)}</strong>
            </div>
            <div>
              <span>炸板收益</span>
              <strong>{formatPercent(profitEffect?.broken_profit_rate)}</strong>
            </div>
          </div>
        </section>

        <section className="workspace-panel">
          <div className="section-heading">
            <h2>情绪拆解</h2>
            <span className="status-chip neutral">components</span>
          </div>
          <div className="emotion-component-list">
            {emotionComponents.map((component) => (
              <div key={component.key}>
                <span>{component.label}</span>
                <strong>{formatScore(component.score)}</strong>
              </div>
            ))}
            {emotionComponents.length ? null : <p className="pending-note">情绪拆解待接入</p>}
          </div>
        </section>
      </section>

      <section className="workspace-panel">
        <div className="section-heading">
          <h2>股票列表</h2>
          <span className="status-chip neutral">EOD</span>
        </div>
        <div className="stock-tabs" role="tablist" aria-label="Market emotion stock lists" onKeyDown={handleStockTabKeyDown}>
          {STOCK_TABS.map((tab) => (
            <button
              ref={(node) => {
                stockTabRefs.current[tab.key] = node;
              }}
              aria-controls={`stock-panel-${tab.key}`}
              aria-selected={activeStockTab === tab.key}
              id={`stock-tab-${tab.key}`}
              key={tab.key}
              onClick={() => selectStockTab(tab.key)}
              role="tab"
              tabIndex={activeStockTab === tab.key ? 0 : -1}
              type="button"
            >
              {tab.label} {stockCount(tab.key)}
            </button>
          ))}
        </div>
        {STOCK_TABS.map((tab) => {
          const isActivePanel = activeStockTab === tab.key;
          const tabRows: EmotionStockListRow[] = stockLists?.[tab.key] ?? [];
          return (
            <div
              aria-labelledby={`stock-tab-${tab.key}`}
              className="stock-table-wrap"
              hidden={!isActivePanel}
              id={`stock-panel-${tab.key}`}
              key={tab.key}
              role="tabpanel"
            >
              {isActivePanel ? (
                tab.key === 'auction' && tabRows.length === 0 ? (
                  <p className="pending-note">竞价数据待接入</p>
                ) : (
                  <table className="emotion-stock-table">
                    <thead>
                      <tr>
                        <th>股票名称</th>
                        <th>成交额</th>
                        <th>涨幅</th>
                        <th>板块</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tabRows.map((row) => (
                        <tr key={`${row.tab}-${row.asset_id}`}>
                          <td>
                            <strong>{row.name || row.symbol}</strong>
                            <span>{row.symbol}</span>
                          </td>
                          <td>{formatAmountYi(row.amount)}</td>
                          <td>{formatPercentPoints(row.pct_chg)}</td>
                          <td>{row.board || '-'}</td>
                        </tr>
                      ))}
                      {tabRows.length === 0 ? (
                        <tr>
                          <td colSpan={4}>暂无股票</td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                )
              ) : null}
            </div>
          );
        })}
      </section>

      <section className="workspace-panel">
        <div className="section-heading">
          <h2>Strategy Signal Summary</h2>
          <span className="status-chip neutral">EOD</span>
        </div>
        <div className="data-table">
          <div className="data-table-header three-col">
            <span>Rank</span>
            <span>Asset</span>
            <span>Score</span>
          </div>
          {topnPreview.map((row) => (
            <div className="data-table-row three-col" key={`${row.trade_date}-${row.asset_id}`}>
              <span>{row.rank}</span>
              <strong>{row.asset_id}</strong>
              <span>{formatScore(row.score_total)}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="workspace-panel">
        <div className="section-heading">
          <h2>Generated Reports</h2>
          <span className="status-chip neutral">local artifacts</span>
        </div>
        <div className="report-list compact">
          {generatedReports.map((report) => (
            <a href={report.path} key={report.path}>
              <span>{report.report_type}</span>
              <strong>{report.title}</strong>
            </a>
          ))}
        </div>
      </section>
    </section>
  );
}
