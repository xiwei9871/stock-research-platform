import { createChart, HistogramSeries, LineSeries, type IChartApi, type Time } from 'lightweight-charts';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { BacktestRunResult } from '../api/types';

type BacktestChartsProps = {
  result: BacktestRunResult;
};

type BacktestChartPoint = {
  time: Time;
  timeKey: string;
  equity: number;
  drawdown: number | null;
  dailyReturn: number;
};

type ChartTooltip = {
  left: number;
  top: number;
  lines: string[];
};

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function asTime(value: unknown): string | null {
  return typeof value === 'string' && value.length >= 10 ? value.slice(0, 10) : null;
}

function formatPercent(value: number) {
  const sign = value > 0 ? '+' : '';
  return `${sign}${(value * 100).toFixed(2)}%`;
}

function getExplicitDailyReturn(row: Record<string, unknown>) {
  return asNumber(
    row.net_return ??
      row.daily_return ??
      row.day_return ??
      row.account_return ??
      row.daily_realized_return ??
      row.return
  );
}

function timeKey(value: Time | undefined): string | null {
  if (typeof value === 'string') {
    return value.slice(0, 10);
  }
  if (typeof value === 'number') {
    return new Date(value * 1000).toISOString().slice(0, 10);
  }
  if (value && typeof value === 'object') {
    const month = String(value.month).padStart(2, '0');
    const day = String(value.day).padStart(2, '0');
    return `${value.year}-${month}-${day}`;
  }
  return null;
}

export function buildBacktestChartPoints(result: BacktestRunResult): BacktestChartPoint[] {
  const points: BacktestChartPoint[] = [];
  let previousEquity: number | null = null;

  result.equity_curve.forEach((row) => {
    const time = asTime(row.date ?? row.trade_date ?? row.rebalance_date);
    const equity = asNumber(row.equity ?? row.account_equity ?? row.final_equity);
    if (!time || equity === null) {
      return;
    }

    const explicitDailyReturn = getExplicitDailyReturn(row);
    const dailyReturn =
      explicitDailyReturn ??
      (previousEquity !== null && previousEquity !== 0 ? equity / previousEquity - 1 : 0);
    const drawdown = asNumber(row.drawdown ?? row.max_drawdown);
    points.push({
      time,
      timeKey: time,
      equity,
      drawdown,
      dailyReturn
    });
    previousEquity = equity;
  });

  return points;
}

export function formatBacktestChartTooltip(point: BacktestChartPoint): string[] {
  const riskLine =
    point.drawdown !== null && point.drawdown < 0
      ? `Drawdown ${formatPercent(point.drawdown)}`
      : `Daily Return ${formatPercent(point.dailyReturn)}`;
  return [point.timeKey, `Equity ${point.equity.toFixed(4)}x`, riskLine];
}

export function BacktestCharts({ result }: BacktestChartsProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [tooltip, setTooltip] = useState<ChartTooltip | null>(null);
  const chartPoints = useMemo(() => buildBacktestChartPoints(result), [result]);
  const chartPointByTime = useMemo(
    () => new Map(chartPoints.map((point) => [point.timeKey, point])),
    [chartPoints]
  );
  const equityData = useMemo(
    () =>
      chartPoints.map((point) => ({
        time: point.time,
        value: point.equity
      })),
    [chartPoints]
  );
  const drawdownData = useMemo(
    () =>
      chartPoints
        .filter((point) => point.drawdown !== null)
        .map((point) => ({
          time: point.time,
          value: point.drawdown as number,
          color: '#d64545'
        })),
    [chartPoints]
  );

  useEffect(() => {
    if (!containerRef.current || equityData.length === 0) {
      return;
    }
    if (typeof window.matchMedia !== 'function') {
      return;
    }

    const chart = createChart(containerRef.current, {
      height: 300,
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
        borderColor: '#d9dee7'
      },
      handleScroll: {
        mouseWheel: false
      },
      handleScale: {
        mouseWheel: false
      }
    });

    const equitySeries = chart.addSeries(LineSeries, {
      color: '#2d6cdf',
      lineWidth: 2,
      priceLineVisible: false
    });
    equitySeries.setData(equityData);

    if (drawdownData.length > 0) {
      const drawdownSeries = chart.addSeries(HistogramSeries, {
        priceScaleId: '',
        priceLineVisible: false
      });
      drawdownSeries.priceScale().applyOptions({
        scaleMargins: {
          top: 0.78,
          bottom: 0
        }
      });
      drawdownSeries.setData(drawdownData);
    }

    chart.subscribeCrosshairMove((param) => {
      if (!containerRef.current || !param.point || param.point.x < 0 || param.point.y < 0) {
        setTooltip(null);
        return;
      }

      const key = timeKey(param.time);
      const point = key ? chartPointByTime.get(key) : null;
      if (!point) {
        setTooltip(null);
        return;
      }

      const tooltipWidth = 170;
      const tooltipHeight = 72;
      const containerWidth = containerRef.current.clientWidth;
      const left = Math.min(Math.max(8, param.point.x + 12), Math.max(8, containerWidth - tooltipWidth - 8));
      const top = Math.max(8, Math.min(param.point.y - tooltipHeight - 8, 220));
      setTooltip({
        left,
        top,
        lines: formatBacktestChartTooltip(point)
      });
    });

    chart.timeScale().fitContent();
    chartRef.current = chart;

    let resizeObserver: ResizeObserver | null = null;
    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(() => {
        if (containerRef.current) {
          chart.applyOptions({ width: containerRef.current.clientWidth });
        }
      });
      resizeObserver.observe(containerRef.current);
    }

    return () => {
      resizeObserver?.disconnect();
      chart.remove();
      chartRef.current = null;
      setTooltip(null);
    };
  }, [chartPointByTime, drawdownData, equityData]);

  if (equityData.length === 0) {
    return <p className="muted">No equity curve available for charting.</p>;
  }

  return (
    <div className="backtest-chart-wrap">
      <div className="backtest-chart" aria-label="Equity and drawdown chart" ref={containerRef} />
      {tooltip ? (
        <div className="backtest-chart-tooltip" style={{ left: tooltip.left, top: tooltip.top }}>
          {tooltip.lines.map((line) => (
            <span key={line}>{line}</span>
          ))}
        </div>
      ) : null}
      <div className="backtest-chart-legend" aria-label="Chart legend">
        <span>
          <i className="legend-dot legend-dot-equity" /> Equity
        </span>
        <span>
          <i className="legend-dot legend-dot-drawdown" /> Drawdown
        </span>
      </div>
    </div>
  );
}
