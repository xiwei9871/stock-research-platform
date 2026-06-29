import { type KeyboardEvent, useRef, useState } from 'react';
import type { MarketMonitorPayload } from '../../api/types';

function formatScore(value: number | null | undefined) {
  return typeof value === 'number' ? value.toFixed(1) : '--';
}

function formatCount(value: number | null | undefined) {
  return typeof value === 'number' ? value.toLocaleString() : '--';
}

function formatPercent(value: number | null | undefined) {
  return typeof value === 'number' ? `${(value * 100).toFixed(2)}%` : '--';
}

function formatAmountYi(value: number | null | undefined) {
  return typeof value === 'number' ? `${(value / 100000000).toFixed(2)}亿` : '--';
}

function formatMultiple(value: number | null | undefined) {
  return typeof value === 'number' ? `${value.toFixed(2)}x` : '--';
}

const STOCK_TABS = [
  { key: 'auction', label: '竞价' },
  { key: 'limit_up', label: '涨停' },
  { key: 'broken_limit_up', label: '炸板' },
  { key: 'limit_down', label: '跌停' }
] as const;

type StockTabKey = (typeof STOCK_TABS)[number]['key'];

type MarketEmotionMiniPanelProps = {
  error: string | null;
  isLoading: boolean;
  payload: MarketMonitorPayload | null;
  requestedTradeDate?: string;
  warnings?: string[];
};

export function MarketEmotionMiniPanel({
  error,
  isLoading,
  payload,
  requestedTradeDate,
  warnings = []
}: MarketEmotionMiniPanelProps) {
  const [activeTab, setActiveTab] = useState<StockTabKey>('limit_up');
  const tabRefs = useRef<Record<StockTabKey, HTMLButtonElement | null>>({
    auction: null,
    limit_up: null,
    broken_limit_up: null,
    limit_down: null
  });

  const emotion = payload?.market_emotion;
  const summary = emotion?.summary;
  const breadth = emotion?.breadth;
  const liquidity = emotion?.liquidity;
  const limitPerformance = emotion?.limit_performance;
  const profitEffect = emotion?.profit_effect;
  const freshnessLabel = payload?.freshness?.label || 'Last Completed Trading Day';
  const latestMarketDate = payload?.freshness?.latest_market_date || payload?.trade_date || '--';
  const stockLists = payload?.emotion_stock_lists;
  const tabCounts = {
    auction: stockLists?.auction?.length ?? 0,
    limit_up: stockLists?.limit_up?.length ?? 0,
    broken_limit_up: stockLists?.broken_limit_up?.length ?? 0,
    limit_down: stockLists?.limit_down?.length ?? 0
  };
  const hasWeightPlaceholder = emotion?.weight_performance?.status !== 'available';
  const hasComponentsPlaceholder = !emotion?.components?.length;
  const topPreview = payload?.strategy_signal_summary?.topn_preview ?? [];

  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, tabIndex: number) => {
    let nextIndex = tabIndex;

    if (event.key === 'ArrowRight') nextIndex = (tabIndex + 1) % STOCK_TABS.length;
    if (event.key === 'ArrowLeft') nextIndex = (tabIndex - 1 + STOCK_TABS.length) % STOCK_TABS.length;
    if (event.key === 'Home') nextIndex = 0;
    if (event.key === 'End') nextIndex = STOCK_TABS.length - 1;

    if (nextIndex === tabIndex) return;

    event.preventDefault();
    const nextTab = STOCK_TABS[nextIndex].key;
    setActiveTab(nextTab);
    tabRefs.current[nextTab]?.focus();
  };

  return (
    <aside className="workspace-panel market-monitor-emotion-panel">
      <div className="section-heading">
        <h2>市场情绪摘要</h2>
        <span className="status-chip neutral">EOD</span>
      </div>
      <div className="market-monitor-emotion-meta">
        <strong>{freshnessLabel}</strong>
        <span>Data Mode</span>
        <span>EOD Snapshot</span>
        <span>{latestMarketDate}</span>
        {isLoading && requestedTradeDate ? <span>Loading {requestedTradeDate}...</span> : null}
      </div>
      {error ? <p className="error-text">{error}</p> : null}
      {warnings.map((warning) => (
        <p className="warning-text" key={warning}>
          {warning}
        </p>
      ))}
      {isLoading && !payload ? <p className="pending-note">正在加载情绪摘要...</p> : null}

      <div className="market-monitor-emotion-list">
        <div className="market-monitor-emotion-item">
          <span>综合强度</span>
          <strong>{formatScore(summary?.score)}</strong>
          <small>{summary?.state || '--'}</small>
        </div>
        <div className="market-monitor-emotion-item">
          <span>涨跌家数</span>
          <strong>{formatCount(breadth?.up_count)}</strong>
          <small>
            下跌 {formatCount(breadth?.down_count)} / 强涨 {formatCount(breadth?.strong_up_count)} / 强跌{' '}
            {formatCount(breadth?.strong_down_count)}
          </small>
        </div>
        <div className="market-monitor-emotion-item">
          <span>市场量能</span>
          <strong>{formatMultiple(liquidity?.amount_ratio_5_20)}</strong>
          <small>成交额 {formatAmountYi(liquidity?.total_amount)}</small>
        </div>
        <div className="market-monitor-emotion-item">
          <span>涨停 / 跌停</span>
          <strong>
            {formatCount(limitPerformance?.limit_up_count)} / {formatCount(limitPerformance?.limit_down_count)}
          </strong>
          <small>炸板 {formatCount(limitPerformance?.broken_limit_up_count)}</small>
        </div>
        <div className="market-monitor-emotion-item">
          <span>炸板率</span>
          <strong>{formatPercent(limitPerformance?.broken_limit_up_rate)}</strong>
          <small>接力情绪参考</small>
        </div>
        <div className="market-monitor-emotion-item">
          <span>最高连板</span>
          <strong>{formatCount(limitPerformance?.high_board_height)}</strong>
          <small>位置预算 {summary?.position_budget_hint || '--'}</small>
        </div>
      </div>

      <div className="market-monitor-emotion-flags">
        <div className="market-monitor-emotion-flag">
          <span>涨停表现</span>
          <strong>最高 {formatCount(limitPerformance?.high_board_height)} 板</strong>
        </div>
        <div className="market-monitor-emotion-flag">
          <span>赚钱效应</span>
          <strong>{formatPercent(profitEffect?.limit_up_success_rate)}</strong>
          <small>{formatPercent(profitEffect?.limit_up_limit_down_rate)}</small>
        </div>
      </div>

      <div className="market-monitor-emotion-footnotes">
        {hasWeightPlaceholder ? <span>权重表现待接入</span> : null}
        {hasComponentsPlaceholder ? <span>情绪拆解待接入</span> : null}
      </div>

      <div className="market-monitor-topn-strip">
        <strong>策略预览</strong>
        {topPreview.length > 0 ? (
          <div className="market-monitor-topn-list">
            {topPreview.slice(0, 3).map((row) => (
              <span key={`${row.trade_date}-${row.asset_id}`}>{row.asset_id}</span>
            ))}
          </div>
        ) : (
          <span className="muted">TopN 预览待接入</span>
        )}
      </div>

      <div className="market-monitor-mini-stock-panel">
        <div className="stock-tabs" role="tablist" aria-label="情绪股票名单">
          {STOCK_TABS.map((tab, index) => {
            const isSelected = activeTab === tab.key;
            const tabId = `market-emotion-tab-${tab.key}`;
            const panelId = `market-emotion-panel-${tab.key}`;

            return (
              <button
                key={tab.key}
                ref={(node) => {
                  tabRefs.current[tab.key] = node;
                }}
                type="button"
                id={tabId}
                role="tab"
                aria-controls={panelId}
                aria-selected={isSelected}
                tabIndex={isSelected ? 0 : -1}
                onClick={() => setActiveTab(tab.key)}
                onKeyDown={(event) => handleTabKeyDown(event, index)}
              >
                {tab.label} {tabCounts[tab.key]}
              </button>
            );
          })}
        </div>

        {STOCK_TABS.map((tab) => {
          const tabRows = stockLists?.[tab.key] ?? [];
          const isSelected = activeTab === tab.key;

          return (
            <div
              key={tab.key}
              id={`market-emotion-panel-${tab.key}`}
              className="market-monitor-mini-stock-list"
              role="tabpanel"
              aria-labelledby={`market-emotion-tab-${tab.key}`}
              hidden={!isSelected}
            >
              {isSelected
                ? tabRows.length > 0
                  ? tabRows.slice(0, 3).map((row) => (
                      <div className="market-monitor-mini-stock-row" key={`${tab.key}-${row.asset_id}`}>
                        <div>
                          <strong>{row.name}</strong>
                          <span>
                            {row.asset_id} / {row.symbol}
                          </span>
                        </div>
                        <div>
                          <strong>{formatPercent(row.pct_chg == null ? null : row.pct_chg / 100)}</strong>
                          <span>{formatAmountYi(row.amount)}</span>
                        </div>
                      </div>
                    ))
                  : (
                      <p className="pending-note">
                        {stockLists ? '暂无入选股票。' : '股票名单源未接入。'}
                      </p>
                    )
                : null}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
