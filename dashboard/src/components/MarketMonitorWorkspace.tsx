import { type FormEvent, useEffect, useMemo, useState } from 'react';
import {
  fetchMarketAnomalyContext,
  fetchMarketMonitorEod,
  fetchMarketOverview,
  fetchSectorDetail,
  fetchSectorFundFlow,
  fetchSectorHeatmap,
  fetchStockHeatmap
} from '../api/client';
import type { MarketAnomalyContextPayload, MarketAnomalyStock, MarketMonitorPayload, StockHeatmapPayload } from '../api/types';
import type { StockEntryContext } from './StockWorkspace';
import { MarketAnomalyContextPanel } from './market-monitor/MarketAnomalyContextPanel';
import { MarketEmotionMiniPanel } from './market-monitor/MarketEmotionMiniPanel';
import { MarketEmotionStatusStrip } from './market-monitor/MarketEmotionStatusStrip';
import { MarketOverviewCards } from './market-monitor/MarketOverviewCards';
import { SectorDetailPanel } from './market-monitor/SectorDetailPanel';
import { SectorFundRankingPanel } from './market-monitor/SectorFundRankingPanel';
import { SectorHeatmapPanel } from './market-monitor/SectorHeatmapPanel';
import { StockHeatmapPanel } from './market-monitor/StockHeatmapPanel';
import {
  createEmptyMarketOverview,
  createEmptySectorFundFlow,
  hasMarketOverviewContent,
  hasSectorFundFlowContent,
  hasSectorHeatmapContent,
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
  emotionPresentation?: 'strip' | 'panel';
  onOpenAsset?: (assetId: string, context: StockEntryContext) => void;
};

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
  emotionPresentation = 'strip',
  onOpenAsset
}: MarketMonitorWorkspaceProps = {}) {
  const [tradeDate, setTradeDate] = useState(initialTradeDate ?? '');
  const [tradeDateInput, setTradeDateInput] = useState(initialTradeDate ?? '');
  const [resolvedTradeDate, setResolvedTradeDate] = useState(initialTradeDate ?? '');
  const [sectorType, setSectorType] = useState<SectorType>(initialMonitorTab === 'concept' ? 'concept' : 'industry');
  const [heatmapView, setHeatmapView] = useState<'sector' | 'stock'>('sector');
  const [selectedSectorId, setSelectedSectorId] = useState<string | null>(null);
  const [overviewData, setOverviewData] = useState<MarketOverview | null>(null);
  const [heatmapData, setHeatmapData] = useState<SectorHeatmapItem[] | null>(null);
  const [heatmapWarnings, setHeatmapWarnings] = useState<string[]>([]);
  const [stockHeatmapData, setStockHeatmapData] = useState<StockHeatmapPayload | null>(null);
  const [stockHeatmapLoading, setStockHeatmapLoading] = useState(false);
  const [stockHeatmapError, setStockHeatmapError] = useState<string | null>(null);
  const [anomalyContext, setAnomalyContext] = useState<MarketAnomalyContextPayload | null>(null);
  const [anomalyContextLoading, setAnomalyContextLoading] = useState(false);
  const [anomalyContextError, setAnomalyContextError] = useState<string | null>(null);
  const [rankingData, setRankingData] = useState<SectorFundFlowSet | null>(null);
  const [detailData, setDetailData] = useState<SectorDetail | null>(null);
  const [emotionPayload, setEmotionPayload] = useState<MarketMonitorPayload | null>(null);
  const [emotionLoading, setEmotionLoading] = useState(false);
  const [emotionError, setEmotionError] = useState<string | null>(null);
  const [emotionWarnings, setEmotionWarnings] = useState<string[]>([]);
  const [emotionRequestVersion, setEmotionRequestVersion] = useState(0);
  const activeTradeDate = tradeDate || resolvedTradeDate;

  useEffect(() => {
    const nextTradeDate = initialTradeDate ?? '';
    setTradeDate(nextTradeDate);
    setTradeDateInput(nextTradeDate);
    setResolvedTradeDate(nextTradeDate);
    setOverviewData(null);
    setHeatmapData(null);
    setHeatmapWarnings([]);
    setStockHeatmapData(null);
    setStockHeatmapError(null);
    setAnomalyContext(null);
    setAnomalyContextError(null);
    setRankingData(null);
    setDetailData(null);
    setEmotionPayload(null);
    setEmotionError(null);
    setEmotionWarnings([]);
  }, [initialTradeDate]);

  useEffect(() => {
    setSelectedSectorId(null);
  }, [activeTradeDate, sectorType]);

  useEffect(() => {
    let cancelled = false;
    setOverviewData(null);
    if (!activeTradeDate) return undefined;

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
    setHeatmapWarnings([]);
    setRankingData(null);
    if (!activeTradeDate) return undefined;

    void Promise.allSettled([
      fetchSectorHeatmap(activeTradeDate, sectorType),
      fetchSectorFundFlow(activeTradeDate, sectorType)
    ]).then(([heatmapResult, rankingResult]) => {
      if (cancelled) return;

      if (heatmapResult.status === 'fulfilled') {
        setHeatmapData(mapApiSectorHeatmapItems(heatmapResult.value.items));
        setHeatmapWarnings(heatmapResult.value.warnings ?? []);
      } else {
        setHeatmapData(null);
        setHeatmapWarnings([]);
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
    if (heatmapView !== 'stock' || !activeTradeDate) {
      if (!activeTradeDate) {
        setStockHeatmapData(null);
        setStockHeatmapError(null);
        setStockHeatmapLoading(false);
      }
      return undefined;
    }

    let cancelled = false;
    setStockHeatmapLoading(true);
    setStockHeatmapError(null);
    setStockHeatmapData(null);

    void fetchStockHeatmap(activeTradeDate)
      .then((payload) => {
        if (cancelled) return;
        setStockHeatmapData(payload);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setStockHeatmapError(error instanceof Error ? error.message : String(error));
      })
      .finally(() => {
        if (!cancelled) {
          setStockHeatmapLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activeTradeDate, heatmapView]);

  useEffect(() => {
    let cancelled = false;

    if (!activeTradeDate || !selectedSectorId) {
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
        const nextTradeDate = payload.trade_date?.trim() || '';
        setEmotionPayload(payload);
        setEmotionWarnings(payload.warnings ?? []);
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

  useEffect(() => {
    let cancelled = false;
    setAnomalyContext(null);
    setAnomalyContextError(null);
    if (!activeTradeDate) {
      setAnomalyContextLoading(false);
      return undefined;
    }
    setAnomalyContextLoading(true);

    void fetchMarketAnomalyContext(activeTradeDate)
      .then((payload) => {
        if (cancelled) return;
        setAnomalyContext(payload);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setAnomalyContextError(error instanceof Error ? error.message : String(error));
      })
      .finally(() => {
        if (!cancelled) {
          setAnomalyContextLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activeTradeDate]);

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
  const hasPrimaryMarketData =
    hasMarketOverviewContent(overviewData) ||
    hasSectorHeatmapContent(heatmapData) ||
    hasSectorFundFlowContent(rankingData);

  const handleTradeDateSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextTradeDate = tradeDateInput.trim();
    setTradeDate(nextTradeDate);
    setResolvedTradeDate(nextTradeDate);
    setTradeDateInput(nextTradeDate);
    setEmotionRequestVersion((current) => current + 1);
  };

  const handleLoadLatest = () => {
    setTradeDate('');
    setResolvedTradeDate('');
    setTradeDateInput('');
    setEmotionRequestVersion((current) => current + 1);
  };

  const handleSelectStockFromHeatmap = (assetId: string) => {
    onOpenAsset?.(assetId, {
      sourceWorkspace: 'market',
      monitorTab: 'stock_heatmap',
      tradeDate: activeTradeDate,
      matchReason: 'stock_heatmap'
    });
  };

  const handleOpenAnomalyStock = (stock: MarketAnomalyStock) => {
    onOpenAsset?.(stock.asset_id, {
      sourceWorkspace: 'market',
      monitorTab: 'anomaly_context',
      tradeDate: activeTradeDate,
      matchReason: 'market_anomaly_context',
      query: stock.name
    });
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

      <MarketOverviewCards overview={activeOverview} />

      {emotionPresentation === 'panel' && (hasPrimaryMarketData || emotionPayload) ? (
        <MarketEmotionMiniPanel
          error={emotionError}
          isLoading={emotionLoading}
          payload={emotionPayload}
          requestedTradeDate={activeTradeDate}
          warnings={emotionWarnings}
        />
      ) : (
        <MarketEmotionStatusStrip
          error={emotionError}
          isLoading={emotionLoading}
          payload={emotionPayload}
          requestedTradeDate={activeTradeDate}
          warnings={emotionWarnings}
        />
      )}

      <section className="market-monitor-main-grid">
        <div className="market-monitor-heatmap-stack">
          <MarketAnomalyContextPanel
            payload={anomalyContext}
            loading={anomalyContextLoading}
            error={anomalyContextError}
            onOpenStock={handleOpenAnomalyStock}
          />
          <div className="market-monitor-heatmap-view-toggle" role="group" aria-label="热力图视图">
            <button
              type="button"
              className={heatmapView === 'sector' ? 'active' : undefined}
              aria-pressed={heatmapView === 'sector'}
              onClick={() => setHeatmapView('sector')}
            >
              板块热力
            </button>
            <button
              type="button"
              className={heatmapView === 'stock' ? 'active' : undefined}
              aria-pressed={heatmapView === 'stock'}
              onClick={() => setHeatmapView('stock')}
            >
              个股云图
            </button>
          </div>
          {heatmapView === 'sector' ? (
            <SectorHeatmapPanel
              items={activeHeatmap}
              sectorType={sectorType}
              warnings={heatmapWarnings}
              selectedSectorId={selectedSectorId}
              onSectorTypeChange={setSectorType}
              onSelectSector={setSelectedSectorId}
            />
          ) : (
            <StockHeatmapPanel
              payload={stockHeatmapData}
              loading={stockHeatmapLoading}
              error={stockHeatmapError}
              onSelectStock={handleSelectStockFromHeatmap}
            />
          )}
        </div>
        <div className="market-monitor-right-rail">
          <SectorFundRankingPanel
            ranking={activeRanking}
            selectedSectorId={selectedSectorId}
            onSelectSector={setSelectedSectorId}
          />
          <SectorDetailPanel
            detail={selectedDetail}
            tradeDate={activeTradeDate}
            initialAssetId={initialAssetId}
            onOpenAsset={onOpenAsset}
          />
        </div>
      </section>
    </section>
  );
}
