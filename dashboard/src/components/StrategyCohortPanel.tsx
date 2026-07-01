import type { StrategyMetricRow } from '../api/types';

type StrategyCohortPanelProps = {
  rows: StrategyMetricRow[];
};

function formatNumber(value: number | null) {
  return value === null ? '-' : value.toFixed(2);
}

export function StrategyCohortPanel({ rows }: StrategyCohortPanelProps) {
  if (rows.length === 0) {
    return <p className="muted">No cohort metrics for this run.</p>;
  }

  return (
    <table className="strategy-table">
      <thead>
        <tr>
          <th>Group</th>
          <th>Samples</th>
          <th>Complete</th>
          <th>Win Rate</th>
          <th>Forward Mean</th>
          <th>Max Drawdown</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={`${row.run_id}-${row.metric_level}-${row.group_key}`}>
            <td>{row.group_key}</td>
            <td>{row.sample_count}</td>
            <td>{row.complete_count}</td>
            <td>{formatNumber(row.win_rate)}</td>
            <td>{formatNumber(row.forward_return_mean)}</td>
            <td>{formatNumber(row.max_drawdown_worst)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
