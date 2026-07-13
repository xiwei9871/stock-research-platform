import type { StrategyReplayPayload } from '../api/types';
import { AssetChart } from '../charts/AssetChart';
import { toStrategyChartMarkers } from '../charts/strategyMarkers';

type StrategyReplayPanelProps = {
  replay: StrategyReplayPayload;
};

function formatPercent(value: number | null) {
  return value === null ? '-' : `${(value * 100).toFixed(2)}%`;
}

export function StrategyReplayPanel({ replay }: StrategyReplayPanelProps) {
  const markers = toStrategyChartMarkers(replay.signals, replay.trades);

  return (
    <section className="strategy-replay">
      <div className="strategy-chart-panel">
        {replay.bars.length > 0 ? (
          <AssetChart bars={replay.bars} markers={markers} />
        ) : (
          <p className="muted">Bars are unavailable for selected range.</p>
        )}
      </div>
      <aside className="strategy-detail-panel">
        <h3>Signals</h3>
        {replay.signals.length === 0 ? (
          <p className="muted">No replay rows for selected asset in this run.</p>
        ) : (
          replay.signals.map((signal) => (
            <div className="strategy-row" key={`${signal.run_id}-${signal.asset_id}-${signal.signal_time}-${signal.signal_type}`}>
              <strong>{signal.signal_type}</strong>
              <span>{signal.reason}</span>
              <small>{signal.rule_id} / {signal.risk_bucket}</small>
            </div>
          ))
        )}
        <h3>Trades</h3>
        {replay.trades.map((trade) => (
          <div className="strategy-row" key={`${trade.run_id}-${trade.asset_id}-${trade.entry_time}-${trade.exit_time}`}>
            <strong>{trade.entry_reason}</strong>
            <span>{trade.exit_reason}</span>
            <small>{trade.outcome_status} / {formatPercent(trade.return_pct)}</small>
          </div>
        ))}
      </aside>
    </section>
  );
}
