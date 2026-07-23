import { type FormEvent, useEffect, useMemo, useState } from 'react';
import {
  fetchMarketMonitorEod,
  fetchMarketOverview,
  fetchSectorDetail,
  fetchSectorFundFlow,
  fetchSectorHeatmap
} from '../api/client';
import type { MarketMonitorPayload } from '../api/types';
import type { StockEntryContext } from './StockWorkspace';
import { MarketEmotionMiniPanel } from './market-monitor/MarketEmotionMiniPanel';
import { MarketOverviewCards } from './market-monitor/MarketOverviewCards';
import { SectorDetailPanel } from './market-monitor/SectorDetailPanel';
import { SectorFundRankingPanel } from './market-monitor/SectorFundRankingPanel';
import { SectorHeatmapPanel } from './market-monitor/SectorHeatmapPanel';
import {
  DEFAULT_MARKET_MONITOR_TRADE_DATE,
  createEmptyMarketOverview,
  createEmptySectorFundFlow,
  mapApiMarketOverview,
  mapApiSectorDetail,
  mapApiSectorFundFlow,
  mapApiSectorHeatmapItems,
  type MarketMonitorMockData,
  type MarketOverview,
  type SectorDetail,
  type SectorFundFlowSet,
  type SectorHeatmapItem,
  type SectorType
} from './market-monitor/mockData';

type MarketMonitorWorkspaceProps = {
  initialTradeDate?: string;
  initialMonitorTab?: SectorType;
  initialAssetId?: string;
  onOpenAsset?: (assetId: string, context: StockEntryContext) => void;
};

const DEFAULT_TRADE_DATE = DEFAULT_MARKET_MONITOR_TRADE_DATE;

function createFallbackDetail(item: SectorHeatmapItem, tradeDate: string): SectorDetail {
  return {
    ...item,
    updatedAt: `${tradeDate} 15:10`,
    summary: '该板块详情暂未返回完整成分股数据，后续会补齐更细的资金解释。',
    leadingStocks: []
  };
}

function resolveSelectedDetail(
  selectedSectorId: string | null,
  sectorType: SectorType,
  tradeDate: string,
  data: MarketMonitorMockData
) {
  if (!selectedSectorId) return null;
  const activeHeatmap = sectorType === 'industry' ? data.industryHeatmap : data.conceptHeatmap;
  const fallback = activeHeatmap.find((item) => item.sectorId === selectedSectorId);
  return data.sectorDetails[selectedSectorId] ?? (fallback ? createFallbackDetail(fallback, tradeDate) : null);
}

export function MarketMonitorWorkspace({
  initialTradeDate,
  initialMonitorTab,
  initialAssetId,
  onOpenAsset
}: MarketMonitorWorkspaceProps = {}) {
  const initialDate = initialTradeDate ?? DEFAULT_TRADE_DATE;
  const [tradeDate, setTradeDate] = useState(initialTradeDate ?? '');
  const [tradeDateInput, setTradeDateInput] = useState(initialDate);
  const [resolvedTradeDate, setResolvedTradeDate] = useState(initialDate);
  const [latestAvailableTradeDate, setLatestAvailableTradeDate] = useState(initialDate);
  const [sectorType, setSectorType] = useState<SectorType>(initialMonitorTab === 'concept' ? 'concept' : 'industry');
  const [selectedSectorId, setSelectedSectorId] = useState<string | null>(null);
  const [overviewData, setOverviewData] = useState<MarketOverview | null>(null);
  const [heatmapData, setHeatmapData] = useState<SectorHeatmapItem[] | null>(null);
  const [rankingData, setRankingData] = useState<SectorFundFlowSet | null>(null);
  const [detailData, setDetailData] = useState<SectorDetail | null>(null);
  const [emotionPayload, setEmotionPayload] = useState<MarketMonitorPayload | null>(null);
  const [emotionLoading, setEmotionLoading] = useState(false);
  const [emotionError, setEmotionError] = useState<string | null>(null);
  const [emotionWarnings, setEmotionWarnings] = useState<string[]>([]);
  const [emotionRequestVersion, setEmotionRequestVersion] = useState(0);
  const activeTradeDate = tradeDate || resolvedTradeDate || DEFAULT_TRADE_DATE;

  useEffect(() => {
    setSelectedSectorId(null);
  }, [activeTradeDate, sectorType]);

  useEffect(() => {
    let cancelled = false;
    setOverviewData(null);

    void fetchMarketOverview(activeTradeDate)
      .then((overview) => {
        if (cancelled) return;
        setOverviewData(mapApiMarketOverview(overview));
      })
      .catch(() => {
        if (!cancelled) {
          setOverviewData(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activeTradeDate]);

  useEffect(() => {
    let cancelled = false;
    setHeatmapData(null);
    setRankingData(null);

    void Promise.allSettled([
      fetchSectorHeatmap(activeTradeDate, sectorType),
      fetchSectorFundFlow(activeTradeDate, sectorType)
    ]).then(([heatmapResult, rankingResult]) => {
      if (cancelled) return;

      if (heatmapResult.status === 'fulfilled') {
        setHeatmapData(mapApiSectorHeatmapItems(heatmapResult.value.items));
      } else {
        setHeatmapData(null);
      }

      if (rankingResult.status === 'fulfilled') {
        setRankingData(
          mapApiSectorFundFlow({
            inflow: rankingResult.value.inflow,
            outflow: rankingResult.value.outflow
          })
        );
      } else {
        setRankingData(null);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [activeTradeDate, sectorType]);

  useEffect(() => {
    let cancelled = false;

    if (!selectedSectorId) {
      setDetailData(null);
      return () => {
        cancelled = true;
      };
    }

    setDetailData(null);

    void fetchSectorDetail(activeTradeDate, selectedSectorId)
      .then((detail) => {
        if (cancelled) return;
        setDetailData(mapApiSectorDetail(detail));
      })
      .catch(() => {
        if (!cancelled) {
          setDetailData(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activeTradeDate, selectedSectorId]);

  useEffect(() => {
    let cancelled = false;
    setEmotionLoading(true);
    setEmotionError(null);

    void fetchMarketMonitorEod(tradeDate ? { topN: 5, tradeDate } : { topN: 5 })
      .then((payload) => {
        if (cancelled) return;
        const latestMarketDate =
          payload.freshness?.latest_market_date?.trim() || payload.trade_date?.trim() || DEFAULT_TRADE_DATE;
        const nextTradeDate = payload.trade_date?.trim() || latestMarketDate;
        setEmotionPayload(payload);
        setEmotionWarnings(payload.warnings ?? []);
        setLatestAvailableTradeDate(latestMarketDate);
        setResolvedTradeDate(nextTradeDate);
        setTradeDateInput(nextTradeDate);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setEmotionError(error instanceof Error ? error.message : String(error));
      })
      .finally(() => {
        if (!cancelled) {
          setEmotionLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [emotionRequestVersion, tradeDate]);

  const workspaceData = useMemo(
    () => ({
      marketOverview: createEmptyMarketOverview(activeTradeDate),
      industryHeatmap: [],
      conceptHeatmap: [],
      sectorFundFlow: {
        industry: createEmptySectorFundFlow(),
        concept: createEmptySectorFundFlow()
      },
      sectorDetails: {}
    }),
    [activeTradeDate]
  );
  const fallbackHeatmap = sectorType === 'industry' ? workspaceData.industryHeatmap : workspaceData.conceptHeatmap;
  const fallbackRanking = workspaceData.sectorFundFlow[sectorType] ?? createEmptySectorFundFlow();
  const activeOverview = overviewData ?? workspaceData.marketOverview;
  const activeHeatmap = heatmapData ?? fallbackHeatmap;
  const activeRanking = rankingData ?? fallbackRanking;
  const detailFallbackData = useMemo(
    () => ({
      ...workspaceData,
      industryHeatmap: sectorType === 'industry' ? activeHeatmap : workspaceData.industryHeatmap,
      conceptHeatmap: sectorType === 'concept' ? activeHeatmap : workspaceData.conceptHeatmap
    }),
    [activeHeatmap, sectorType, workspaceData]
  );
  const selectedDetail = useMemo(
    () => detailData ?? resolveSelectedDetail(selectedSectorId, sectorType, activeTradeDate, detailFallbackData),
    [activeTradeDate, detailData, detailFallbackData, selectedSectorId, sectorType]
  );

  const handleTradeDateSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextTradeDate = tradeDateInput.trim() || DEFAULT_TRADE_DATE;
    setTradeDate(nextTradeDate);
    setResolvedTradeDate(nextTradeDate);
    setTradeDateInput(nextTradeDate);
    setEmotionRequestVersion((current) => current + 1);
  };

  const handleLoadLatest = () => {
    const nextTradeDate = latestAvailableTradeDate || DEFAULT_TRADE_DATE;
    setTradeDate('');
    setResolvedTradeDate(nextTradeDate);
    setTradeDateInput(nextTradeDate);
    setEmotionRequestVersion((current) => current + 1);
  };

  return (
    <section className="workspace-stack" aria-label="Market Monitor workspace">
      <header className="workspace-header workspace-header-row">
        <div>
          <h1>Market Monitor</h1>
          <p className="muted">盘后板块与资金复盘工作区，主舞台聚焦板块强弱、资金方向和可操作细节。</p>
        </div>
        <button type="button" aria-label="Load Latest EOD" onClick={handleLoadLatest}>
          最新收盘日
        </button>
      </header>

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
        <button type="submit" aria-label="Load Date">
          载入日期
        </button>
      </form>

      <div className="market-monitor-toggle-bar" role="toolbar" aria-label="板块类型切换">
        <button
          type="button"
          aria-pressed={sectorType === 'industry'}
          className={sectorType === 'industry' ? 'active' : ''}
          onClick={() => setSectorType('industry')}
        >
          行业
        </button>
        <button
          type="button"
          aria-pressed={sectorType === 'concept'}
          className={sectorType === 'concept' ? 'active' : ''}
          onClick={() => setSectorType('concept')}
        >
          概念
        </button>
      </div>

      <MarketOverviewCards overview={activeOverview} />

      <section className="market-monitor-main-grid">
        <SectorHeatmapPanel
          items={activeHeatmap}
          selectedSectorId={selectedSectorId}
          onSelectSector={setSelectedSectorId}
        />
        <SectorFundRankingPanel
          ranking={activeRanking}
          selectedSectorId={selectedSectorId}
          onSelectSector={setSelectedSectorId}
        />
      </section>

      <section className="market-monitor-bottom-grid">
        <SectorDetailPanel
          detail={selectedDetail}
          tradeDate={activeTradeDate}
          initialAssetId={initialAssetId}
          onOpenAsset={onOpenAsset}
        />
        <MarketEmotionMiniPanel
          error={emotionError}
          isLoading={emotionLoading}
          payload={emotionPayload}
          requestedTradeDate={tradeDate || latestAvailableTradeDate}
          warnings={emotionWarnings}
        />
      </section>
    </section>
  );
}
