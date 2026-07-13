import {
  CandlestickSeries,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  type IChartApi,
  type SeriesMarker,
  type Time
} from 'lightweight-charts';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';
import type { BarPoint } from '../api/types';
import { toAlignedPriceVolumeData } from './chartData';

type ChartTimeAxisMode = 'daily' | 'intraday';
type ChartTimeAxisPeriod = '1D' | '1W' | '1M' | 'intraday';

type AssetChartProps = {
  bars: BarPoint[];
  markers?: SeriesMarker<Time>[];
  visibleBarCount?: number;
  timeAxisMode?: ChartTimeAxisMode;
  timeAxisPeriod?: ChartTimeAxisPeriod;
};

type ChartHoverData = {
  x: number;
  y: number;
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number | null;
};

type WindowDragState = {
  trackLeft: number;
  trackWidth: number;
  pointerOffset: number;
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

function buildChartTimeContext(bars: BarPoint[], period: ChartTimeAxisPeriod, visibleBarCount?: number): ChartTimeContext {
  if (period !== 'intraday') {
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
  period: ChartTimeAxisPeriod,
  dateBoundaryKeys: Set<string>,
  originalTimeByChartKey: Map<string, string>
) {
  const parts = chinaDateParts(time, originalTimeByChartKey);
  const shortYearMonth = `${parts.year.slice(-2)}-${parts.month}`;
  if (period === '1W') {
    return shortYearMonth;
  }
  if (period === '1M') {
    return parts.month === '01' ? parts.year : shortYearMonth;
  }
  if (period === '1D') {
    return shortYearMonth;
  }
  if (period === 'intraday' && dateBoundaryKeys.has(timeKey(time))) {
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

function formatWindowTime(time: Time, period: ChartTimeAxisPeriod, originalTimeByChartKey: Map<string, string>) {
  const parts = chinaDateParts(time, originalTimeByChartKey);
  if (period === '1M') {
    return `${parts.year}-${parts.month}`;
  }
  if (period === 'intraday' && parts.hour && parts.minute) {
    return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
  }
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function formatAxisWindowTime(time: Time, period: ChartTimeAxisPeriod, originalTimeByChartKey: Map<string, string>) {
  const parts = chinaDateParts(time, originalTimeByChartKey);
  const shortYearMonth = `${parts.year.slice(-2)}-${parts.month}`;
  if (period === '1M') {
    return parts.month === '01' ? parts.year : shortYearMonth;
  }
  if (period === '1D' || period === '1W') {
    return shortYearMonth;
  }
  if (period === 'intraday' && parts.hour && parts.minute) {
    return `${parts.hour}:${parts.minute}`;
  }
  return `${parts.month}-${parts.day}`;
}

function buildAxisTickLabels(
  candles: { time: Time }[],
  start: number,
  end: number,
  period: ChartTimeAxisPeriod,
  originalTimeByChartKey: Map<string, string>
) {
  if (candles.length === 0 || end < start) {
    return [];
  }
  const labelCount = Math.min(6, end - start + 1);
  if (labelCount <= 1) {
    return [formatAxisWindowTime(candles[start].time, period, originalTimeByChartKey)];
  }

  const positions = new Set<number>();
  for (let index = 0; index < labelCount; index += 1) {
    positions.add(start + Math.round(((end - start) * index) / (labelCount - 1)));
  }
  return Array.from(positions)
    .sort((left, right) => left - right)
    .map((position) => formatAxisWindowTime(candles[position].time, period, originalTimeByChartKey));
}

function formatCompactNumber(value: number) {
  const absoluteValue = Math.abs(value);
  if (absoluteValue >= 100000000) {
    return `${(value / 100000000).toFixed(2)}亿`;
  }
  if (absoluteValue >= 10000) {
    return `${(value / 10000).toFixed(2)}万`;
  }
  if (absoluteValue >= 1000) {
    return `${(value / 1000).toFixed(2)}K`;
  }
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

export function AssetChart({ bars, markers, visibleBarCount, timeAxisMode = 'daily', timeAxisPeriod }: AssetChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const windowDragRef = useRef<WindowDragState | null>(null);
  const windowDragCleanupRef = useRef<(() => void) | null>(null);
  const [hoverData, setHoverData] = useState<ChartHoverData | null>(null);
  const activeAxisPeriod = timeAxisPeriod ?? (timeAxisMode === 'intraday' ? 'intraday' : '1D');
  const chartTimeContext = useMemo(
    () => buildChartTimeContext(bars, activeAxisPeriod, visibleBarCount),
    [bars, activeAxisPeriod, visibleBarCount]
  );
  const priceVolumeData = useMemo(
    () => toAlignedPriceVolumeData(bars, chartTimeContext.resolveTime),
    [bars, chartTimeContext]
  );
  const windowSize =
    visibleBarCount && priceVolumeData.chartPointCount > visibleBarCount
      ? visibleBarCount
      : priceVolumeData.chartPointCount;
  const maxRangeStart = Math.max(0, priceVolumeData.chartPointCount - windowSize);
  const [rangeStart, setRangeStart] = useState(maxRangeStart);
  const safeRangeStart = Math.min(rangeStart, maxRangeStart);
  const rangeEnd = priceVolumeData.chartPointCount > 0 ? Math.min(priceVolumeData.chartPointCount - 1, safeRangeStart + windowSize - 1) : 0;
  const rangeStartLabel = priceVolumeData.candles[safeRangeStart]
    ? formatWindowTime(priceVolumeData.candles[safeRangeStart].time, activeAxisPeriod, chartTimeContext.originalTimeByChartKey)
    : '';
  const rangeEndLabel = priceVolumeData.candles[rangeEnd]
    ? formatWindowTime(priceVolumeData.candles[rangeEnd].time, activeAxisPeriod, chartTimeContext.originalTimeByChartKey)
    : '';
  const axisTickLabels = buildAxisTickLabels(
    priceVolumeData.candles,
    safeRangeStart,
    rangeEnd,
    activeAxisPeriod,
    chartTimeContext.originalTimeByChartKey
  );
  const windowBarCount = priceVolumeData.chartPointCount > 0 ? rangeEnd - safeRangeStart + 1 : 0;
  const windowWidthPercent =
    priceVolumeData.chartPointCount > 0 ? Math.min(100, (windowBarCount / priceVolumeData.chartPointCount) * 100) : 100;
  const windowLeftPercent =
    priceVolumeData.chartPointCount > 0 ? (safeRangeStart / priceVolumeData.chartPointCount) * 100 : 0;
  const windowStep = Math.max(1, Math.round((visibleBarCount ?? windowBarCount) / 6));
  const shiftWindow = (delta: number) => {
    setRangeStart((current) => clamp(current + delta, 0, maxRangeStart));
  };
  const updateWindowFromPointer = (clientX: number) => {
    const dragState = windowDragRef.current;
    if (!dragState || priceVolumeData.chartPointCount === 0) {
      return;
    }
    const rawStart = ((clientX - dragState.trackLeft - dragState.pointerOffset) / dragState.trackWidth) * priceVolumeData.chartPointCount;
    setRangeStart(clamp(Math.round(rawStart), 0, maxRangeStart));
  };
  const stopWindowDrag = () => {
    windowDragCleanupRef.current?.();
    windowDragCleanupRef.current = null;
    windowDragRef.current = null;
  };
  const handleWindowPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (maxRangeStart === 0 || priceVolumeData.chartPointCount === 0) {
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    const selectionLeft = (safeRangeStart / priceVolumeData.chartPointCount) * rect.width;
    const selectionWidth = (windowBarCount / priceVolumeData.chartPointCount) * rect.width;
    const pointerX = event.clientX - rect.left;
    const isPointerInsideSelection = pointerX >= selectionLeft && pointerX <= selectionLeft + selectionWidth;
    windowDragRef.current = {
      trackLeft: rect.left,
      trackWidth: rect.width,
      pointerOffset: isPointerInsideSelection ? pointerX - selectionLeft : selectionWidth / 2
    };
    const handleDocumentPointerMove = (moveEvent: PointerEvent) => {
      moveEvent.preventDefault();
      updateWindowFromPointer(moveEvent.clientX);
    };
    const handleDocumentPointerUp = () => {
      stopWindowDrag();
    };
    window.addEventListener('pointermove', handleDocumentPointerMove);
    window.addEventListener('pointerup', handleDocumentPointerUp, { once: true });
    windowDragCleanupRef.current = () => {
      window.removeEventListener('pointermove', handleDocumentPointerMove);
      window.removeEventListener('pointerup', handleDocumentPointerUp);
    };
    updateWindowFromPointer(event.clientX);
  };

  useEffect(() => {
    setRangeStart(maxRangeStart);
  }, [maxRangeStart]);

  useEffect(() => {
    return () => {
      windowDragCleanupRef.current?.();
    };
  }, []);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    const chartMarkers = markers ?? EMPTY_MARKERS;
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
        barSpacing: 6,
        fixLeftEdge: true,
        minBarSpacing: 4,
        visible: false,
        timeVisible: timeAxisMode === 'intraday',
        secondsVisible: false,
        rightOffsetPixels: 24,
        ticksVisible: true,
        uniformDistribution: true,
        tickMarkMaxCharacterLength: activeAxisPeriod === '1D' || activeAxisPeriod === '1W' ? 5 : activeAxisPeriod === '1M' ? 5 : 8,
        tickMarkFormatter: (time: Time) =>
          formatAxisTick(time, activeAxisPeriod, chartTimeContext.dateBoundaryKeys, chartTimeContext.originalTimeByChartKey)
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
    }, 0);
    candleSeries.setData(priceVolumeData.candles);
    if (chartMarkers.length > 0) {
      createSeriesMarkers(candleSeries, chartMarkers);
    }

    const volumeSeries = chart.addSeries(HistogramSeries, {
      lastValueVisible: false,
      priceFormat: { type: 'volume' },
      priceLineVisible: false,
      priceScaleId: 'right'
    }, 1);
    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.1,
        bottom: 0
      }
    });
    volumeSeries.setData(priceVolumeData.volumes);
    const panes = typeof chart.panes === 'function' ? chart.panes() : [];
    panes[0]?.setStretchFactor?.(4);
    panes[1]?.setStretchFactor?.(1);
    const handleCrosshairMove = (param: {
      point?: { x: number; y: number };
      time?: Time;
      seriesData: Map<object, unknown>;
    }) => {
      const candle = param.seriesData.get(candleSeries) as
        | { open?: number; high?: number; low?: number; close?: number }
        | undefined;
      const volume = param.seriesData.get(volumeSeries) as { value?: number } | undefined;
      if (
        !param.point ||
        param.time === undefined ||
        candle?.open === undefined ||
        candle.high === undefined ||
        candle.low === undefined ||
        candle.close === undefined ||
        volume?.value === undefined
      ) {
        setHoverData(null);
        return;
      }
      setHoverData({
        x: param.point.x,
        y: param.point.y,
        time: formatCrosshairTime(param.time, timeAxisMode, chartTimeContext.originalTimeByChartKey),
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
        volume: volume.value,
        amount: priceVolumeData.detailsByTimeKey.get(timeKey(param.time))?.amount ?? null
      });
    };
    chart.subscribeCrosshairMove?.(handleCrosshairMove);

    chart.timeScale().fitContent();
    chartRef.current = chart;

    const resizeObserver = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      chart.unsubscribeCrosshairMove?.(handleCrosshairMove);
      setHoverData(null);
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [activeAxisPeriod, chartTimeContext, markers, priceVolumeData, timeAxisMode]);

  useEffect(() => {
    if (!chartRef.current || priceVolumeData.chartPointCount === 0) {
      return;
    }
    if (windowSize < priceVolumeData.chartPointCount) {
      chartRef.current.timeScale().setVisibleLogicalRange({
        from: safeRangeStart,
        to: safeRangeStart + windowSize - 1
      });
    } else {
      chartRef.current.timeScale().fitContent();
    }
  }, [priceVolumeData.chartPointCount, safeRangeStart, windowSize]);

  return (
    <div className="asset-chart-shell">
      <div className="asset-chart" ref={containerRef} />
      {hoverData ? (
        <div
          className="asset-chart-tooltip"
          role="tooltip"
          aria-label="K线数据"
          style={{ left: hoverData.x + 14, top: Math.max(12, hoverData.y - 82) }}
        >
          <strong>{hoverData.time}</strong>
          <span>开 {hoverData.open}</span>
          <span>高 {hoverData.high}</span>
          <span>低 {hoverData.low}</span>
          <span>收 {hoverData.close}</span>
          <span>量 {formatCompactNumber(hoverData.volume)}</span>
          <span>额 {hoverData.amount === null ? '-' : formatCompactNumber(hoverData.amount)}</span>
        </div>
      ) : null}
      {axisTickLabels.length > 0 ? (
        <ol
          className="chart-axis-ticks"
          aria-label="横轴刻度"
          style={{ gridTemplateColumns: `repeat(${axisTickLabels.length}, minmax(0, 1fr))` }}
        >
          {axisTickLabels.map((label, index) => (
            <li key={`${label}-${index}`}>{label}</li>
          ))}
        </ol>
      ) : null}
      {priceVolumeData.chartPointCount > 0 ? (
        <div className="chart-range-tool" role="group" aria-label="时间窗口">
          <span>{rangeStartLabel && rangeEndLabel ? `${rangeStartLabel} - ${rangeEndLabel} / ${windowBarCount} bars` : 'No range'}</span>
          <div className="chart-window-controls">
            <button
              type="button"
              aria-label="向左移动时间窗口"
              title="向左移动时间窗口"
              disabled={safeRangeStart === 0}
              onClick={() => shiftWindow(-windowStep)}
            >
              <ChevronLeft aria-hidden="true" size={16} />
            </button>
            <div
              className="chart-window-track"
              onPointerDown={handleWindowPointerDown}
              onPointerCancel={stopWindowDrag}
            >
              <div
                className="chart-window-selection"
                aria-hidden="true"
                style={{ left: `${windowLeftPercent}%`, width: `${windowWidthPercent}%` }}
              />
              <input
                aria-label="拖动时间窗口"
                className="chart-window-slider"
                type="range"
                min={0}
                max={maxRangeStart}
                value={safeRangeStart}
                disabled={maxRangeStart === 0}
                onChange={(event) => setRangeStart(Number(event.target.value))}
              />
            </div>
            <button
              type="button"
              aria-label="向右移动时间窗口"
              title="向右移动时间窗口"
              disabled={safeRangeStart === maxRangeStart}
              onClick={() => shiftWindow(windowStep)}
            >
              <ChevronRight aria-hidden="true" size={16} />
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
