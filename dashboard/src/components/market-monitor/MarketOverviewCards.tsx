import type { MarketOverview } from './mockData';

function formatSignedPercent(value: number | null | undefined) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '--';
  const sign = value > 0 ? '+' : '';
  return `${sign}${(value * 100).toFixed(2)}%`;
}

function formatAmountYi(value: number | null | undefined) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '--';
  return `${(value / 100000000).toFixed(2)}亿`;
}

function movementClassName(value: number | null | undefined) {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'market-monitor-negative';
  return value >= 0 ? 'market-monitor-positive' : 'market-monitor-negative';
}

function statusLabel(status: MarketOverview['dataStatus']) {
  if (status === 'completed') return '已完成';
  if (status === 'partial') return '部分完成';
  if (status === 'stale') return '数据偏旧';
  return '缺失';
}

function statusClassName(status: MarketOverview['dataStatus']) {
  if (status === 'completed') return 'status-chip success';
  if (status === 'partial') return 'status-chip warning';
  if (status === 'stale') return 'status-chip neutral';
  return 'status-chip danger';
}

export function MarketOverviewCards({ overview }: { overview: MarketOverview }) {
  const hasOverviewData = overview.indices.length > 0 || overview.totalAmount != null;

  return (
    <section className="workspace-panel market-monitor-overview-panel">
      <div className="section-heading">
        <h2>市场总览</h2>
        <span className={statusClassName(overview.dataStatus)}>{statusLabel(overview.dataStatus)}</span>
      </div>
      <div className="market-monitor-overview-meta">
        <span>交易日 {overview.tradeDate || '--'}</span>
        <span>更新时间 {overview.updatedAt || '--'}</span>
      </div>
      {hasOverviewData ? (
        <>
          <div className="market-monitor-index-grid">
            {overview.indices.map((index) => (
              <article className="metric-card compact" key={index.id}>
                <span>{index.name}</span>
                <strong>{index.close?.toFixed(2) ?? '--'}</strong>
                <small className={movementClassName(index.pctChange)}>
                  {formatSignedPercent(index.pctChange)}
                </small>
              </article>
            ))}
          </div>
          <div className="market-monitor-overview-grid">
            <article className="metric-card compact">
              <span>全市场成交额</span>
              <strong>{formatAmountYi(overview.totalAmount)}</strong>
            </article>
            <article className="metric-card compact">
              <span>上涨 / 下跌</span>
              <strong>
                {overview.upCount ?? '--'} / {overview.downCount ?? '--'}
              </strong>
            </article>
            <article className="metric-card compact">
              <span>涨停 / 跌停</span>
              <strong>
                {overview.limitUpCount ?? '--'} / {overview.limitDownCount ?? '--'}
              </strong>
            </article>
          </div>
        </>
      ) : (
        <p className="pending-note">暂无市场总览数据</p>
      )}
    </section>
  );
}
