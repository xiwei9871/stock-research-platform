import type { MarketMonitorPayload } from '../../api/types';

function formatScore(value: number | null | undefined) {
  return typeof value === 'number' ? value.toFixed(1) : '--';
}

function formatCount(value: number | null | undefined) {
  return typeof value === 'number' ? value.toLocaleString() : '--';
}

function formatMultiple(value: number | null | undefined) {
  return typeof value === 'number' ? `${value.toFixed(2)}x` : '--';
}

type MarketEmotionStatusStripProps = {
  error: string | null;
  isLoading: boolean;
  payload: MarketMonitorPayload | null;
  requestedTradeDate?: string;
  warnings?: string[];
};

export function MarketEmotionStatusStrip({
  error,
  isLoading,
  payload,
  requestedTradeDate,
  warnings = []
}: MarketEmotionStatusStripProps) {
  const emotion = payload?.market_emotion;
  const summary = emotion?.summary;
  const breadth = emotion?.breadth;
  const liquidity = emotion?.liquidity;
  const limitPerformance = emotion?.limit_performance;
  const latestMarketDate = payload?.freshness?.latest_market_date || payload?.trade_date || requestedTradeDate || '--';

  return (
    <section className="market-monitor-emotion-strip" aria-label="市场情绪状态条">
      <div className="market-monitor-emotion-strip-head">
        <strong>市场状态</strong>
        <span>{isLoading && requestedTradeDate ? `加载 ${requestedTradeDate}...` : latestMarketDate}</span>
      </div>
      <div className="market-monitor-emotion-strip-grid">
        <div>
          <span>综合强度</span>
          <strong>{formatScore(summary?.score)}</strong>
          <small>{summary?.state || '--'}</small>
        </div>
        <div>
          <span>涨跌家数</span>
          <strong>
            {formatCount(breadth?.up_count)} / {formatCount(breadth?.down_count)}
          </strong>
          <small>强涨 {formatCount(breadth?.strong_up_count)} / 强跌 {formatCount(breadth?.strong_down_count)}</small>
        </div>
        <div>
          <span>涨停 / 跌停</span>
          <strong>
            {formatCount(limitPerformance?.limit_up_count)} / {formatCount(limitPerformance?.limit_down_count)}
          </strong>
          <small>炸板 {formatCount(limitPerformance?.broken_limit_up_count)}</small>
        </div>
        <div>
          <span>量能</span>
          <strong>{formatMultiple(liquidity?.amount_ratio_5_20)}</strong>
          <small>成交额 {formatCount(liquidity?.total_amount ? liquidity.total_amount / 100000000 : undefined)}亿</small>
        </div>
      </div>
      {error ? <p className="error-text">{error}</p> : null}
      {warnings.slice(0, 2).map((warning) => (
        <p className="warning-text" key={warning}>
          {warning}
        </p>
      ))}
    </section>
  );
}
