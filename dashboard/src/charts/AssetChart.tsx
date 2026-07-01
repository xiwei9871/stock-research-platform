import {
  CandlestickSeries,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  type IChartApi,
  type SeriesMarker,
  type Time
} from 'lightweight-charts';
import { useEffect, useRef } from 'react';
import type { BarPoint } from '../api/types';
import { toCandlestickData, toVolumeData } from './chartData';

type ChartTimeAxisMode = 'daily' | 'intraday';

type AssetChartProps = {
  bars: BarPoint[];
  markers?: SeriesMarker<Time>[];
  visibleBarCount?: number;
  timeAxisMode?: ChartTimeAxisMode;
};

const EMPTY_MARKERS: SeriesMarker<Time>[] = [];
const DAILY_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const TIME_WITHOUT_ZONE_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/;
const SYNTHETIC_INTRADAY_START = 1780448400;

function timeKey(time: Time) {
  return String(time);
}

function normalizeBarTime(input: string): Time | null {
  if (DAILY_DATE_PATTERN.test(input)) {
    return input;
  }

  const normalized = input.replace(' ', 'T');
  const parseTarget = TIME_WITHOUT_ZONE_PATTERN.test(normalized) ? `${normalized}+08:00` : normalized;
  const milliseconds = Date.parse(parseTarget);

  if (Number.isNaN(milliseconds)) {
    return null;
  }

  return Math.floor(milliseconds / 1000) as Time;
}

type ChartTimeContext = {
  dateBoundaryKeys: Set<string>;
  originalTimeByChartKey: Map<string, string>;
  resolveTime: (point: BarPoint, index: number) => Time | null;
};

function syntheticIntradayTime(index: number): Time {
  return (SYNTHETIC_INTRADAY_START + index * 60) as Time;
}

function buildChartTimeContext(bars: BarPoint[], mode: ChartTimeAxisMode, visibleBarCount?: number): ChartTimeContext {
  if (mode !== 'intraday') {
    return {
      dateBoundaryKeys: new Set<string>(),
      originalTimeByChartKey: new Map<string, string>(),
      resolveTime: (point) => normalizeBarTime(point.time)
    };
  }

  const keys = new Set<string>();
  const originalTimeByChartKey = new Map<string, string>();
  const seenDates = new Set<string>();
  const firstVisibleIndex = visibleBarCount && bars.length > visibleBarCount ? bars.length - visibleBarCount : 0;

  for (const [index, bar] of bars.entries()) {
    const chartTime = syntheticIntradayTime(index);
    const chartKey = timeKey(chartTime);
    originalTimeByChartKey.set(chartKey, bar.time);

    const dateText = bar.time.slice(0, 10);
    if (!seenDates.has(dateText)) {
      keys.add(chartKey);
      seenDates.add(dateText);
    }
    if (index === firstVisibleIndex) {
      keys.add(chartKey);
    }
  }

  return {
    dateBoundaryKeys: keys,
    originalTimeByChartKey,
    resolveTime: (_point, index) => syntheticIntradayTime(index)
  };
}

function partsFromExchangeTime(input: string) {
  const match = input.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/);
  if (!match) {
    return null;
  }
  const [, year, month, day, hour = '', minute = ''] = match;
  return { year, month, day, hour, minute };
}

function chinaDateParts(time: Time, originalTimeByChartKey?: Map<string, string>) {
  const originalTime = originalTimeByChartKey?.get(timeKey(time));
  if (originalTime) {
    const originalParts = partsFromExchangeTime(originalTime);
    if (originalParts) {
      return originalParts;
    }
  }

  if (typeof time === 'string') {
    const [year, month, day] = time.slice(0, 10).split('-');
    return { year, month, day, hour: '', minute: '' };
  }
  const date = new Date(Number(time) * 1000);
  const parts = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  }).formatToParts(date);
  const byType = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return {
    year: byType.year ?? '',
    month: byType.month ?? '',
    day: byType.day ?? '',
    hour: byType.hour ?? '',
    minute: byType.minute ?? ''
  };
}

function formatAxisTick(
  time: Time,
  mode: ChartTimeAxisMode,
  dateBoundaryKeys: Set<string>,
  originalTimeByChartKey: Map<string, string>
) {
  const parts = chinaDateParts(time, originalTimeByChartKey);
  if (mode === 'daily') {
    return `${parts.month}-${parts.day}`;
  }
  if (dateBoundaryKeys.has(timeKey(time))) {
    return `${parts.month}-${parts.day}`;
  }
  if (!parts.hour || !parts.minute) {
    return `${parts.month}-${parts.day}`;
  }
  return `${parts.hour}:${parts.minute}`;
}

function formatCrosshairTime(time: Time, mode: ChartTimeAxisMode, originalTimeByChartKey: Map<string, string>) {
  const parts = chinaDateParts(time, originalTimeByChartKey);
  if (mode === 'daily' || !parts.hour || !parts.minute) {
    return `${parts.year}-${parts.month}-${parts.day}`;
  }
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
}

export function AssetChart({ bars, markers, visibleBarCount, timeAxisMode = 'daily' }: AssetChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    const chartMarkers = markers ?? EMPTY_MARKERS;
    const chartTimeContext = buildChartTimeContext(bars, timeAxisMode, visibleBarCount);
    const chart = createChart(containerRef.current, {
      height: 460,
      width: containerRef.current.clientWidth,
      layout: {
        background: { color: '#ffffff' },
        textColor: '#202936'
      },
      grid: {
        vertLines: { color: '#eef1f5' },
        horzLines: { color: '#eef1f5' }
      },
      rightPriceScale: {
        borderColor: '#d9dee7'
      },
      timeScale: {
        borderColor: '#d9dee7',
        timeVisible: timeAxisMode === 'intraday',
        secondsVisible: false,
        tickMarkMaxCharacterLength: timeAxisMode === 'intraday' ? 8 : 5,
        tickMarkFormatter: (time: Time) =>
          formatAxisTick(time, timeAxisMode, chartTimeContext.dateBoundaryKeys, chartTimeContext.originalTimeByChartKey)
      },
      localization: {
        locale: 'zh-CN',
        timeFormatter: (time: Time) => formatCrosshairTime(time, timeAxisMode, chartTimeContext.originalTimeByChartKey)
      },
      handleScroll: {
        mouseWheel: false
      },
      handleScale: {
        mouseWheel: false
      }
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#d64545',
      downColor: '#1f9d55',
      borderVisible: false,
      wickUpColor: '#d64545',
      wickDownColor: '#1f9d55'
    });
    candleSeries.setData(toCandlestickData(bars, chartTimeContext.resolveTime));
    if (chartMarkers.length > 0) {
      createSeriesMarkers(candleSeries, chartMarkers);
    }

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: ''
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.8,
        bottom: 0
      }
    });
    volumeSeries.setData(toVolumeData(bars, chartTimeContext.resolveTime));

    if (visibleBarCount && bars.length > visibleBarCount) {
      chart.timeScale().setVisibleLogicalRange({
        from: bars.length - visibleBarCount,
        to: bars.length - 1
      });
    } else {
      chart.timeScale().fitContent();
    }
    chartRef.current = chart;

    const resizeObserver = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [bars, markers, timeAxisMode, visibleBarCount]);

  return <div className="asset-chart" ref={containerRef} />;
}
