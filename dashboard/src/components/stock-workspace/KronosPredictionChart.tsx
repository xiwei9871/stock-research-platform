import * as echarts from 'echarts';
import { useEffect, useRef } from 'react';
import type { BarPoint } from '../../api/types';
import type { KronosForecastPeriod } from '../../api/kronos';

type KronosPredictionChartProps = {
  historyBars: BarPoint[];
  forecast: KronosForecastPeriod | null;
  overlayHistory: boolean;
};

function finiteValues(value: unknown): number[] | null {
  if (!Array.isArray(value)) return null;
  const values = value.map((item) => Number(item));
  return values.every((item) => Number.isFinite(item)) ? values : null;
}

function forecastQuantile(forecast: KronosForecastPeriod, name: 'p10' | 'p50' | 'p90') {
  return finiteValues(forecast[name] ?? forecast.summary?.close?.[name]);
}

function shortTime(value: string) {
  const normalized = String(value || '').replace('T', ' ');
  return normalized.length > 16 ? normalized.slice(5, 16) : normalized;
}

function normalizeHistoryBar(bar: BarPoint) {
  if ([bar.open, bar.high, bar.low, bar.close].some((value) => value == null)) return null;
  return [bar.open, bar.close, bar.low, bar.high];
}

function normalizeForecastBar(bar: { open: number; high: number; low: number; close: number }) {
  return [bar.open, bar.close, bar.low, bar.high];
}

export function KronosPredictionChart({ historyBars, forecast, overlayHistory }: KronosPredictionChartProps) {
  const chartRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const node = chartRef.current;
    if (!node || !forecast?.representative_path?.length) return undefined;

    const chart = echarts.init(node);
    const history = overlayHistory
      ? historyBars.map(normalizeHistoryBar).filter((value): value is number[] => value !== null)
      : [];
    const futureBars = forecast.representative_path;
    const categories = [
      ...historyBars.slice(-history.length).map((bar) => shortTime(bar.time)),
      ...futureBars.map((bar) => shortTime(bar.timestamp))
    ];
    const prefix = Array.from({ length: history.length }, () => '-');
    const p10 = forecastQuantile(forecast, 'p10');
    const p50 = forecastQuantile(forecast, 'p50');
    const p90 = forecastQuantile(forecast, 'p90');
    const series: any[] = [];

    if (history.length > 0) {
      series.push({
        type: 'candlestick',
        name: '历史K线',
        data: [...history, ...Array.from({ length: futureBars.length }, () => '-')],
        itemStyle: {
          color: '#ef4444',
          color0: '#16a34a',
          borderColor: '#ef4444',
          borderColor0: '#16a34a'
        }
      });
    }

    series.push({
      type: 'candlestick',
      name: 'Kronos预测代表路径',
      data: [...prefix, ...futureBars.map(normalizeForecastBar)],
      itemStyle: {
        color: '#8b5cf6',
        color0: '#8b5cf6',
        borderColor: '#7c3aed',
        borderColor0: '#7c3aed'
      },
      markLine:
        history.length > 0
          ? {
              silent: true,
              symbol: ['none', 'none'],
              label: { formatter: '预测起点', color: '#64748b' },
              lineStyle: { type: 'dashed', color: '#94a3b8' },
              data: [{ xAxis: categories[history.length] }]
            }
          : undefined
    });

    const addQuantile = (name: string, values: number[] | null, color: string, type: 'dashed' | 'dotted') => {
      if (!values || values.length !== futureBars.length) return;
      series.push({
        type: 'line',
        name,
        data: [...prefix, ...values],
        symbol: 'none',
        connectNulls: false,
        lineStyle: { type, color, width: name === 'P50收盘' ? 1.6 : 1.2 }
      });
    };
    addQuantile('P10收盘', p10, '#f59e0b', 'dashed');
    addQuantile('P50收盘', p50, '#7c3aed', 'dotted');
    addQuantile('P90收盘', p90, '#0ea5e9', 'dashed');

    chart.setOption({
      animation: false,
      grid: { left: 48, right: 20, top: 42, bottom: 52 },
      legend: { top: 4, type: 'scroll' },
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
      dataZoom: [
        { type: 'inside', start: history.length > 0 ? 70 : 0, end: 100 },
        { start: history.length > 0 ? 70 : 0, end: 100 }
      ],
      xAxis: { type: 'category', data: categories, boundaryGap: true },
      yAxis: { type: 'value', scale: true },
      series
    });

    const resizeObserver = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => chart.resize()) : null;
    resizeObserver?.observe(node);
    return () => {
      resizeObserver?.disconnect();
      chart.dispose();
    };
  }, [forecast, historyBars, overlayHistory]);

  return <div ref={chartRef} className="kronos-prediction-chart" aria-label="Kronos预测K线图" />;
}
