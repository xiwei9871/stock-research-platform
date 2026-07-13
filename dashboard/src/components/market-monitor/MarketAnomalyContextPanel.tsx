import type { MarketAnomalyContextPayload, MarketAnomalyStock } from '../../api/types';

type MarketAnomalyContextPanelProps = {
  payload: MarketAnomalyContextPayload | null;
  loading: boolean;
  error: string | null;
  onOpenStock: (stock: MarketAnomalyStock) => void;
};

function formatPercent(value: number | null) {
  if (value === null || Number.isNaN(value)) return '-';
  const sign = value > 0 ? '+' : '';
  return `${sign}${(value * 100).toFixed(2)}%`;
}

function formatAmountYi(value: number | null) {
  if (value === null || Number.isNaN(value)) return '-';
  return `${(value / 100000000).toFixed(2)}亿`;
}

function tagLabel(tag: string) {
  const labels: Record<string, string> = {
    volume_spike: '放量',
    strong_up: '强涨',
    strong_down: '强跌',
    limit_up: '涨停',
    limit_down: '跌停',
    industry_leader: '行业领涨'
  };
  return labels[tag] ?? tag;
}

export function MarketAnomalyContextPanel({ payload, loading, error, onOpenStock }: MarketAnomalyContextPanelProps) {
  if (loading) {
    return (
      <section className="workspace-panel market-anomaly-context-panel" aria-label="异常热区解释">
        <p className="pending-note">异常热区解释加载中</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="workspace-panel market-anomaly-context-panel" aria-label="异常热区解释">
        <p className="error-text">{error}</p>
      </section>
    );
  }

  if (!payload || payload.data_status === 'missing') {
    return (
      <section className="workspace-panel market-anomaly-context-panel" aria-label="异常热区解释">
        <div className="section-heading">
          <h2>异常热区解释</h2>
          <span className="status-chip neutral">暂无数据</span>
        </div>
        <p className="pending-note">暂无异常热区解释数据。</p>
      </section>
    );
  }

  return (
    <section className="workspace-panel market-anomaly-context-panel" aria-label="异常热区解释">
      <div className="section-heading">
        <h2>异常热区解释</h2>
        <span className="status-chip neutral">盘后监控</span>
      </div>
      <div className="market-anomaly-summary">
        <span>热区 {payload.summary.hot_industry_count}</span>
        <span>异动股 {payload.summary.hot_stock_count}</span>
        <span>放量 {payload.summary.volume_spike_count}</span>
        <span>强波动 {payload.summary.strong_move_count}</span>
      </div>
      <div className="market-anomaly-grid">
        <article className="market-anomaly-block">
          <h3>行业联动排序</h3>
          <div className="market-anomaly-list">
            {payload.hot_industries.slice(0, 5).map((industry) => (
              <div className="market-anomaly-industry-row" key={industry.industry_id}>
                <div>
                  <strong>{industry.industry_name}</strong>
                  <span>{formatPercent(industry.change_pct)} / {formatAmountYi(industry.amount)}</span>
                </div>
                <small>
                  上涨 {industry.up_count} / 下跌 {industry.down_count} / 分数 {industry.anomaly_score.toFixed(1)}
                </small>
                <ul>
                  {industry.explanation_bullets.slice(0, 2).map((bullet) => (
                    <li key={bullet}>{bullet}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </article>
        <article className="market-anomaly-block">
          <h3>异常个股标签</h3>
          <div className="market-anomaly-stock-list">
            {payload.hot_stocks.slice(0, 6).map((stock) => (
              <button
                key={stock.asset_id}
                type="button"
                aria-label={`打开异常个股 ${stock.name}`}
                className="market-anomaly-stock-row"
                onClick={() => onOpenStock(stock)}
              >
                <strong>{stock.name}</strong>
                <span>{stock.symbol} / {stock.industry_name}</span>
                <span>{formatPercent(stock.change_pct)} / {formatAmountYi(stock.amount)}</span>
                <span className="market-anomaly-tags">
                  {stock.anomaly_tags.map((tag) => (
                    <em key={tag}>{tagLabel(tag)}</em>
                  ))}
                </span>
              </button>
            ))}
          </div>
        </article>
      </div>
    </section>
  );
}
