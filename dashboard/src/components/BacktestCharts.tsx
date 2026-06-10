import { createChart, HistogramSeries, LineSeries, type IChartApi, type Time } from 'lightweight-charts';
import { useEffect, useMemo, useRef } from 'react';
import type { BacktestRunResult } from '../api/types';

type BacktestChartsProps = {
  result: BacktestRunResult;
};

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function asTime(value: unknown): Time | null {
  return typeof value === 'string' && value.length >= 10 ? value.slice(0, 10) : null;
}

export function BacktestCharts({ result }: BacktestChartsProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const equityData = useMemo(
    () =>
      result.equity_curve
        .map((row) => {
          const time = asTime(row.date ?? row.trade_date ?? row.rebalance_date);
          const value = asNumber(row.equity ?? row.account_equity ?? row.final_equity);
          return time && value !== null ? { time, value } : null;
        })
        .filter((row): row is { time: Time; value: number } => row !== null),
    [result.equity_curve]
  );
  const drawdownData = useMemo(
    () =>
      result.equity_curve
        .map((row) => {
          const time = asTime(row.date ?? row.trade_date ?? row.rebalance_date);
          const value = asNumber(row.drawdown ?? row.max_drawdown);
          return time && value !== null ? { time, value, color: '#d64545' } : null;
        })
        .filter((row): row is { time: Time; value: number; color: string } => row !== null),
    [result.equity_curve]
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
    };
  }, [drawdownData, equityData]);

  if (equityData.length === 0) {
    return <p className="muted">No equity curve available for charting.</p>;
  }

  return <div className="backtest-chart" aria-label="Equity and drawdown chart" ref={containerRef} />;
}
