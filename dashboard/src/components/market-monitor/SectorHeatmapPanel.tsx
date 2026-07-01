import { useEffect, useRef, useState } from 'react';
import * as echarts from 'echarts';
import type { SectorHeatmapItem, SectorType } from './mockData';

function formatSignedPercent(value: number) {
  const sign = value > 0 ? '+' : '';
  return `${sign}${(value * 100).toFixed(2)}%`;
}

function formatAmountYi(value: number) {
  return `${(value / 100000000).toFixed(2)}亿`;
}

type HeatmapDirection = 'up' | 'down';

function treemapColor(value: number, direction: HeatmapDirection) {
  const strength = Math.abs(value);
  if (direction === 'up') {
    if (strength >= 0.04) return '#7f1d1d';
    if (strength >= 0.025) return '#991b1b';
    if (strength >= 0.015) return '#b91c1c';
    return '#dc2626';
  }

  if (strength >= 0.04) return '#052e16';
  if (strength >= 0.025) return '#14532d';
  if (strength >= 0.015) return '#166534';
  return '#15803d';
}

function buildTreemapOption(items: SectorHeatmapItem[], selectedSectorId: string | null, direction: HeatmapDirection) {
  return {
    tooltip: {
      formatter: (params: { data?: SectorHeatmapItem }) => {
        const item = params.data;
        if (!item) return '';
        return [
          item.sectorName,
          `涨跌幅 ${formatSignedPercent(item.pctChange)}`,
          `成交额 ${formatAmountYi(item.amount)}`,
          `上涨/下跌 ${item.upCount}/${item.downCount}`,
          `主力净流入 ${formatAmountYi(item.mainNetInflow)}`
        ].join('<br/>');
      }
    },
    series: [
      {
        type: 'treemap',
        roam: false,
        nodeClick: false,
        breadcrumb: { show: false },
        leafDepth: 1,
        label: {
          show: true,
          formatter: (params: { data?: SectorHeatmapItem }) => {
            const item = params.data;
            if (!item) return '';
            return `${item.sectorName}\n${formatSignedPercent(item.pctChange)}`;
          },
          color: '#ffffff',
          fontSize: 12,
          overflow: 'break'
        },
        upperLabel: { show: false },
        levels: [
          {
            itemStyle: {
              borderColor: '#eef2f6',
              borderWidth: 3,
              gapWidth: 3
            }
          }
        ],
        data: items.map((item) => ({
          ...item,
          value: Math.max(item.amount, 1),
          itemStyle: {
            color: treemapColor(item.pctChange, direction),
            borderColor: item.sectorId === selectedSectorId ? '#17202a' : '#eef2f6',
            borderWidth: item.sectorId === selectedSectorId ? 4 : 2
          }
        }))
      }
    ]
  };
}

type SectorHeatmapPanelProps = {
  items: SectorHeatmapItem[];
  sectorType: SectorType;
  warnings?: string[];
  selectedSectorId: string | null;
  onSectorTypeChange: (sectorType: SectorType) => void;
  onSelectSector: (sectorId: string) => void;
};

const HEATMAP_SIDE_LIMIT = 10;
const CHART_SIZE_RETRY_LIMIT = 24;

function extractSectorId(params: unknown) {
  if (!params || typeof params !== 'object' || !('data' in params)) return null;
  const data = (params as { data?: unknown }).data;
  if (!data || typeof data !== 'object' || !('sectorId' in data)) return null;
  const sectorId = (data as { sectorId?: unknown }).sectorId;
  return typeof sectorId === 'string' ? sectorId : null;
}

function directionalScore(item: SectorHeatmapItem) {
  const amountWeight = Math.log10(Math.max(item.amount, 1));
  return Math.abs(item.pctChange) * amountWeight;
}

function selectDirectionalItems(items: SectorHeatmapItem[], direction: HeatmapDirection) {
  return items
    .filter((item) => (direction === 'up' ? item.pctChange > 0 : item.pctChange < 0))
    .sort((left, right) => directionalScore(right) - directionalScore(left) || right.amount - left.amount)
    .slice(0, HEATMAP_SIDE_LIMIT);
}

function FallbackTreemap({
  direction,
  items,
  onSelectSector
}: {
  direction: HeatmapDirection;
  items: SectorHeatmapItem[];
  onSelectSector: (sectorId: string) => void;
}) {
  const totalAmount = items.reduce((total, item) => total + Math.max(item.amount, 1), 0);
  const directionLabel = direction === 'up' ? '上涨' : '下跌';

  return (
    <div className="market-monitor-heatmap-fallback" aria-label={`${directionLabel}板块兼容热力图`}>
      {items.map((item) => {
        const share = totalAmount > 0 ? Math.max(item.amount, 1) / totalAmount : 0;
        const basis = `${Math.min(72, Math.max(16, share * 100))}%`;

        return (
          <button
            key={`fallback-${item.sectorId}`}
            type="button"
            className="market-monitor-heatmap-fallback-tile"
            style={{
              backgroundColor: treemapColor(item.pctChange, direction),
              flexBasis: basis,
              flexGrow: Math.max(1, share * 100)
            }}
            aria-label={`兼容热力块 ${directionLabel} ${item.sectorName}`}
            onClick={() => onSelectSector(item.sectorId)}
          >
            <strong>{item.sectorName}</strong>
            <small>{formatSignedPercent(item.pctChange)}</small>
          </button>
        );
      })}
    </div>
  );
}

function DirectionalHeatmap({
  direction,
  items,
  selectedSectorId,
  onSelectSector
}: {
  direction: HeatmapDirection;
  items: SectorHeatmapItem[];
  selectedSectorId: string | null;
  onSelectSector: (sectorId: string) => void;
}) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chartInstanceRef = useRef<echarts.EChartsType | null>(null);
  const [chartReady, setChartReady] = useState(false);
  const title = direction === 'up' ? '上涨板块热力图' : '下跌板块热力图';
  const emptyText = direction === 'up' ? '暂无上涨板块热力图数据' : '暂无下跌板块热力图数据';
  const labelPrefix = direction === 'up' ? '上涨热力图' : '下跌热力图';

  useEffect(() => {
    return () => {
      chartInstanceRef.current?.dispose();
      chartInstanceRef.current = null;
    };
  }, []);

  useEffect(() => {
    const node = chartRef.current;
    if (!node) return undefined;

    let resizeObserver: ResizeObserver | null = null;
    let frameId: number | null = null;
    let retryCount = 0;

    if (items.length === 0) {
      chartInstanceRef.current?.dispose();
      chartInstanceRef.current = null;
      setChartReady(false);
      return undefined;
    }

    const cancelFrame = () => {
      if (frameId != null) {
        window.cancelAnimationFrame(frameId);
        frameId = null;
      }
    };

    const scheduleRenderRetry = () => {
      if (frameId != null || retryCount >= CHART_SIZE_RETRY_LIMIT) {
        return;
      }

      frameId = window.requestAnimationFrame(() => {
        frameId = null;
        retryCount += 1;
        renderChart();
      });
    };

    const renderChart = () => {
      if (node.clientWidth === 0 || node.clientHeight === 0) {
        scheduleRenderRetry();
        return;
      }

      retryCount = 0;
      cancelFrame();
      const chart = chartInstanceRef.current ?? echarts.init(node);
      chartInstanceRef.current = chart;
      chart.setOption(buildTreemapOption(items, selectedSectorId, direction));
      chart.off('click');
      chart.on('click', (params: unknown) => {
        const sectorId = extractSectorId(params);
        if (sectorId) {
          onSelectSector(sectorId);
        }
      });
      chart.resize();
      setChartReady(node.children.length > 0);
    };

    renderChart();

    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(() => {
        renderChart();
      });
      resizeObserver.observe(node);
    } else {
      scheduleRenderRetry();
    }

    const handleResize = () => {
      renderChart();
      chartInstanceRef.current?.resize();
    };
    window.addEventListener('resize', handleResize);

    return () => {
      cancelFrame();
      resizeObserver?.disconnect();
      window.removeEventListener('resize', handleResize);
      chartInstanceRef.current?.off('click');
    };
  }, [direction, items, onSelectSector, selectedSectorId]);

  return (
    <article className={`market-monitor-directional-heatmap ${direction}`}>
      <div className="market-monitor-directional-heading">
        <h3>{title}</h3>
        <span>{items.length > 0 ? `Top ${items.length}` : 'No Data'}</span>
      </div>
      {items.length > 0 ? (
        <>
          <div className={`market-monitor-heatmap-chart market-monitor-heatmap-chart-${direction}`}>
            <div className="market-monitor-heatmap-echarts-layer" ref={chartRef} aria-label={`${title}图表`} />
            {!chartReady ? (
              <FallbackTreemap direction={direction} items={items} onSelectSector={onSelectSector} />
            ) : null}
          </div>
          <div className="market-monitor-heatmap-summary" aria-label={`${title}摘要`}>
            {items.map((item) => (
              <button
                key={item.sectorId}
                type="button"
                className={
                  item.sectorId === selectedSectorId
                    ? `market-monitor-heatmap-chip ${direction} active`
                    : `market-monitor-heatmap-chip ${direction}`
                }
                aria-label={`从${labelPrefix}摘要查看 ${item.sectorName}`}
                onClick={() => onSelectSector(item.sectorId)}
              >
                <strong>{item.sectorName}</strong>
                <small>
                  {formatSignedPercent(item.pctChange)} / 成交额 {formatAmountYi(item.amount)}
                </small>
              </button>
            ))}
          </div>
        </>
      ) : (
        <p className="pending-note">{emptyText}</p>
      )}
    </article>
  );
}

const SECTOR_MODE_COPY: Record<SectorType, { title: string; status: string; value: string; caption: string }> = {
  industry: {
    title: '行业板块热力图',
    status: '行业',
    value: '产业链权重',
    caption: '行业模式看产业链权重、成交额集中度和真实资金承接；每侧精选最多 10 个板块。'
  },
  concept: {
    title: '概念板块热力图',
    status: '概念',
    value: '题材弹性',
    caption: '概念模式看题材弹性、短线扩散和资金偏好；每侧精选最多 10 个主题。'
  }
};

export function SectorHeatmapPanel({
  items,
  sectorType,
  warnings = [],
  selectedSectorId,
  onSectorTypeChange,
  onSelectSector
}: SectorHeatmapPanelProps) {
  const upItems = selectDirectionalItems(items, 'up');
  const downItems = selectDirectionalItems(items, 'down');
  const copy = SECTOR_MODE_COPY[sectorType];

  return (
    <section className="workspace-panel market-monitor-heatmap-panel">
      <div className="market-monitor-heatmap-heading">
        <div>
          <h2>{copy.title}</h2>
          <div className="market-monitor-heatmap-mode-meta">
            <span>{copy.value}</span>
            <span>面积=成交额</span>
            <span>颜色=涨跌幅</span>
          </div>
        </div>
        <div className="market-monitor-toggle-bar market-monitor-heatmap-toggle" role="toolbar" aria-label="板块类型切换">
          <button
            type="button"
            aria-pressed={sectorType === 'industry'}
            className={sectorType === 'industry' ? 'active' : ''}
            onClick={() => onSectorTypeChange('industry')}
          >
            行业
          </button>
          <button
            type="button"
            aria-pressed={sectorType === 'concept'}
            className={sectorType === 'concept' ? 'active' : ''}
            onClick={() => onSectorTypeChange('concept')}
          >
            概念
          </button>
        </div>
      </div>
      {warnings.length > 0 || (sectorType === 'concept' && items.length === 0) ? (
        <div className="market-monitor-heatmap-warnings">
          {(warnings.length > 0 ? warnings : ['concept sector heatmap rows are unavailable']).map((warning) => (
            <span key={warning}>
              {warning.includes('concept sector source') || warning.includes('concept sector heatmap rows')
                ? '概念板块数据表已接入，但当前暂无概念成分股/日度聚合数据。'
                : warning}
            </span>
          ))}
        </div>
      ) : null}
      <div className="market-monitor-heatmap-split">
        <DirectionalHeatmap
          direction="up"
          items={upItems}
          selectedSectorId={selectedSectorId}
          onSelectSector={onSelectSector}
        />
        <DirectionalHeatmap
          direction="down"
          items={downItems}
          selectedSectorId={selectedSectorId}
          onSelectSector={onSelectSector}
        />
      </div>
      <p className="market-monitor-panel-caption">{copy.caption}</p>
    </section>
  );
}
