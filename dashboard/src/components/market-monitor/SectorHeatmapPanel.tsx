import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';
import type { SectorHeatmapItem } from './mockData';

function formatSignedPercent(value: number) {
  const sign = value > 0 ? '+' : '';
  return `${sign}${(value * 100).toFixed(2)}%`;
}

function formatAmountYi(value: number) {
  return `${(value / 100000000).toFixed(2)}亿`;
}

function treemapColor(value: number) {
  if (value >= 0.03) return '#d23c3c';
  if (value >= 0.015) return '#e06a50';
  if (value >= 0) return '#f1b9a8';
  if (value > -0.015) return '#9ec7a7';
  return '#4f8a63';
}

function buildTreemapOption(items: SectorHeatmapItem[], selectedSectorId: string | null) {
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
            color: treemapColor(item.pctChange),
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
  selectedSectorId: string | null;
  onSelectSector: (sectorId: string) => void;
};

export function SectorHeatmapPanel({ items, selectedSectorId, onSelectSector }: SectorHeatmapPanelProps) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chartInstanceRef = useRef<echarts.EChartsType | null>(null);

  useEffect(() => {
    return () => {
      chartInstanceRef.current?.dispose();
      chartInstanceRef.current = null;
    };
  }, []);

  useEffect(() => {
    const node = chartRef.current;
    if (!node) return undefined;

    if (items.length === 0) {
      chartInstanceRef.current?.dispose();
      chartInstanceRef.current = null;
      return undefined;
    }

    if (node.clientWidth === 0 || node.clientHeight === 0) {
      return undefined;
    }

    const chart = chartInstanceRef.current ?? echarts.init(node);
    chartInstanceRef.current = chart;
    chart.setOption(buildTreemapOption(items, selectedSectorId));

    chart.off('click');
    chart.on('click', (params: { data?: { sectorId?: string } }) => {
      const sectorId = params.data?.sectorId;
      if (sectorId) {
        onSelectSector(sectorId);
      }
    });

    const handleResize = () => chart.resize();
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.off('click');
    };
  }, [items, onSelectSector, selectedSectorId]);

  return (
    <section className="workspace-panel market-monitor-heatmap-panel">
      <div className="section-heading">
        <h2>板块热力图</h2>
        <span className="status-chip neutral">Treemap</span>
      </div>
      {items.length > 0 ? (
        <>
          <div className="market-monitor-heatmap-chart" ref={chartRef} aria-label="板块热力图图表" />
          <div className="market-monitor-heatmap-summary" aria-label="板块热力图摘要">
            {items.map((item) => (
              <button
                key={item.sectorId}
                type="button"
                className={
                  item.sectorId === selectedSectorId
                    ? 'market-monitor-heatmap-chip active'
                    : 'market-monitor-heatmap-chip'
                }
                aria-label={`从热力图摘要查看 ${item.sectorName}`}
                onClick={() => onSelectSector(item.sectorId)}
              >
                <strong>{item.sectorName}</strong>
                <small>
                  {formatSignedPercent(item.pctChange)} / 成交额 {formatAmountYi(item.amount)}
                </small>
              </button>
            ))}
          </div>
          <p className="market-monitor-panel-caption">面积按成交额，颜色按涨跌幅；摘要列表用于快速选择和无图环境兜底。</p>
        </>
      ) : (
        <p className="pending-note">暂无板块热力图数据</p>
      )}
    </section>
  );
}
