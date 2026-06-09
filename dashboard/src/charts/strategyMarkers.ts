import type { SeriesMarker, Time } from 'lightweight-charts';
import type { StrategySignal, StrategyTrade } from '../api/types';

export type StrategyChartMarker = SeriesMarker<Time>;

export function toStrategyChartMarkers(signals: StrategySignal[], trades: StrategyTrade[]): StrategyChartMarker[] {
  const signalMarkers = signals.map((signal) => ({
    time: signal.trade_date as Time,
    position: 'aboveBar' as const,
    color: signal.risk_bucket === 'high' ? '#d64545' : '#2563eb',
    shape: 'circle' as const,
    text: signal.signal_type
  }));

  const tradeMarkers = trades.flatMap((trade) => {
    const markers: StrategyChartMarker[] = [];
    if (trade.entry_time) {
      markers.push({
        time: trade.entry_time as Time,
        position: 'belowBar',
        color: '#1f9d55',
        shape: 'arrowUp',
        text: 'entry'
      });
    }
    if (trade.exit_time) {
      markers.push({
        time: trade.exit_time as Time,
        position: 'aboveBar',
        color: '#d64545',
        shape: 'arrowDown',
        text: 'exit'
      });
    }
    return markers;
  });

  return [...signalMarkers, ...tradeMarkers].sort((left, right) => String(left.time).localeCompare(String(right.time)));
}
