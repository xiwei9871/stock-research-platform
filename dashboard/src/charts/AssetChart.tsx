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

type AssetChartProps = {
  bars: BarPoint[];
  markers?: SeriesMarker<Time>[];
};

const EMPTY_MARKERS: SeriesMarker<Time>[] = [];

export function AssetChart({ bars, markers }: AssetChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);

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
        borderColor: '#d9dee7'
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
    candleSeries.setData(toCandlestickData(bars));
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
    volumeSeries.setData(toVolumeData(bars));

    chart.timeScale().fitContent();
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
  }, [bars, markers]);

  return <div className="asset-chart" ref={containerRef} />;
}
