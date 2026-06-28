import type { SectorFundFlowItem, SectorFundFlowSet } from './mockData';

function formatSignedPercent(value: number) {
  const sign = value > 0 ? '+' : '';
  return `${sign}${(value * 100).toFixed(2)}%`;
}

function formatSignedAmountYi(value: number) {
  const sign = value > 0 ? '+' : '';
  return `${sign}${(value / 100000000).toFixed(2)}亿`;
}

function formatRatio(value: number) {
  const sign = value > 0 ? '+' : '';
  return `${sign}${(value * 100).toFixed(1)}%`;
}

function RankingList({
  items,
  selectedSectorId,
  title,
  onSelectSector
}: {
  items: SectorFundFlowItem[];
  selectedSectorId: string | null;
  title: string;
  onSelectSector: (sectorId: string) => void;
}) {
  return (
    <div className="market-monitor-ranking-group">
      <div className="market-monitor-ranking-subheading">
        <strong>{title}</strong>
      </div>
      {items.length > 0 ? (
        <div className="market-monitor-ranking-list">
          {items.map((item, index) => (
            <button
              key={`${title}-${item.sectorId}`}
              type="button"
              className={item.sectorId === selectedSectorId ? 'market-monitor-ranking-row active' : 'market-monitor-ranking-row'}
              aria-label={`查看板块详情 ${item.sectorName}`}
              onClick={() => onSelectSector(item.sectorId)}
            >
              <span className="market-monitor-ranking-rank">{index + 1}</span>
              <div className="market-monitor-ranking-main">
                <strong>{item.sectorName}</strong>
                <small>
                  涨跌幅 {formatSignedPercent(item.pctChange)} / 领涨股 {item.leadingStockName || '--'}
                </small>
              </div>
              <div className="market-monitor-ranking-side">
                <strong>{formatSignedAmountYi(item.mainNetInflow)}</strong>
                <small>占成交额 {formatRatio(item.netInflowRatio)}</small>
              </div>
            </button>
          ))}
        </div>
      ) : (
        <p className="pending-note">暂无{title}数据</p>
      )}
    </div>
  );
}

export function SectorFundRankingPanel({
  ranking,
  selectedSectorId,
  onSelectSector
}: {
  ranking: SectorFundFlowSet;
  selectedSectorId: string | null;
  onSelectSector: (sectorId: string) => void;
}) {
  const hasData = ranking.inflow.length > 0 || ranking.outflow.length > 0;

  return (
    <section className="workspace-panel market-monitor-ranking-panel">
      <div className="section-heading">
        <h2>板块资金排行</h2>
        <span className="status-chip neutral">Top 10</span>
      </div>
      {hasData ? (
        <div className="market-monitor-ranking-grid">
          <RankingList
            items={ranking.inflow}
            selectedSectorId={selectedSectorId}
            title="净流入 Top 10"
            onSelectSector={onSelectSector}
          />
          <RankingList
            items={ranking.outflow}
            selectedSectorId={selectedSectorId}
            title="净流出 Top 10"
            onSelectSector={onSelectSector}
          />
        </div>
      ) : (
        <p className="pending-note">暂无板块资金排行数据</p>
      )}
    </section>
  );
}
