import type { StockEntryContext } from '../StockWorkspace';
import type { SectorDetail } from './mockData';

function formatSignedPercent(value: number) {
  const sign = value > 0 ? '+' : '';
  return `${sign}${(value * 100).toFixed(2)}%`;
}

function formatSignedAmountYi(value: number) {
  const sign = value > 0 ? '+' : '';
  return `${sign}${(value / 100000000).toFixed(2)}亿`;
}

function formatAmountYi(value: number) {
  return `${(value / 100000000).toFixed(2)}亿`;
}

function formatRatio(value: number) {
  const sign = value > 0 ? '+' : '';
  return `${sign}${(value * 100).toFixed(1)}%`;
}

function sectorTypeLabel(detail: SectorDetail) {
  return detail.sectorType === 'industry' ? '行业板块' : '概念板块';
}

type SectorDetailPanelProps = {
  detail: SectorDetail | null;
  tradeDate: string;
  initialAssetId?: string;
  onOpenAsset?: (assetId: string, context: StockEntryContext) => void;
};

export function SectorDetailPanel({
  detail,
  tradeDate,
  initialAssetId,
  onOpenAsset
}: SectorDetailPanelProps) {
  return (
    <section className="workspace-panel market-monitor-detail-panel">
      <div className="section-heading">
        <h2>板块详情</h2>
        {detail ? <span className="status-chip neutral">{sectorTypeLabel(detail)}</span> : null}
      </div>
      {detail ? (
        <div className="market-monitor-detail-content">
          <div className="market-monitor-detail-header">
            <div>
              <h3>{detail.sectorName}</h3>
              <p className="muted">{detail.summary}</p>
            </div>
            <div className="market-monitor-detail-meta">
              <span>更新时间</span>
              <strong>{detail.updatedAt}</strong>
            </div>
          </div>

          <div className="market-monitor-detail-metrics">
            <article className="metric-card compact">
              <span>涨跌幅</span>
              <strong>{formatSignedPercent(detail.pctChange)}</strong>
            </article>
            <article className="metric-card compact">
              <span>成交额</span>
              <strong>{formatAmountYi(detail.amount)}</strong>
            </article>
            <article className="metric-card compact">
              <span>上涨 / 下跌</span>
              <strong>
                {detail.upCount} / {detail.downCount}
              </strong>
            </article>
            <article className="metric-card compact">
              <span>主力净流入</span>
              <strong>{formatSignedAmountYi(detail.mainNetInflow)}</strong>
            </article>
            <article className="metric-card compact">
              <span>净流入占比</span>
              <strong>{formatRatio(detail.netInflowRatio)}</strong>
            </article>
          </div>

          <div className="market-monitor-leading-section">
            <div className="market-monitor-leading-header">
              <strong>领涨股</strong>
              <span>优先从这里进入个股详情</span>
            </div>
            {detail.leadingStocks.length > 0 ? (
              <div className="market-monitor-leading-list">
                {detail.leadingStocks.map((stock) => (
                  <div className="market-monitor-leading-row" key={`${detail.sectorId}-${stock.assetId}`}>
                    <div>
                      {stock.assetId && onOpenAsset ? (
                        <button
                          type="button"
                          className={stock.assetId === initialAssetId ? 'link-chip active' : 'link-chip'}
                          aria-label={`打开领涨股 ${stock.name}`}
                          onClick={() =>
                            onOpenAsset(stock.assetId, {
                              sourceWorkspace: 'market',
                              assetId: stock.assetId,
                              tradeDate,
                              monitorTab: detail.sectorType,
                              query: stock.name
                            })
                          }
                        >
                          {stock.name}
                        </button>
                      ) : (
                        <strong>{stock.name}</strong>
                      )}
                      <span>{stock.symbol}</span>
                    </div>
                    <div>
                      <strong>{formatSignedPercent(stock.pctChange)}</strong>
                      <span>成交额 {(stock.turnover / 100000000).toFixed(2)}亿</span>
                    </div>
                    <p>{stock.reason}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="pending-note">领涨股明细待补充</p>
            )}
          </div>
        </div>
      ) : (
        <p className="pending-note">点击热力图或资金榜查看板块详情</p>
      )}
    </section>
  );
}
