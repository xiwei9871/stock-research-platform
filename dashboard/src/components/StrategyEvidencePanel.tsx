import type { StrategyEvidenceArtifact, StrategyValidationRun } from '../api/types';

type StrategyEvidencePanelProps = {
  run: StrategyValidationRun;
  artifacts: StrategyEvidenceArtifact[];
};

function formatConfig(value: unknown) {
  return JSON.stringify(value, null, 2);
}

export function StrategyEvidencePanel({ run, artifacts }: StrategyEvidencePanelProps) {
  const runConfigs = [
    { label: 'Data Window', value: run.data_window },
    { label: 'Cost Config', value: run.cost_config },
    { label: 'Slippage Config', value: run.slippage_config },
    { label: 'Risk Config', value: run.risk_config },
    { label: 'Position Config', value: run.position_config }
  ];

  return (
    <section className="strategy-evidence">
      <div className="strategy-summary-card">
        <strong>{run.run_id}</strong>
        <span>{run.strategy_version} / {run.run_type}</span>
        <span>{run.start_date} to {run.end_date}</span>
        <span>Benchmark {run.benchmark}</span>
      </div>
      {run.warnings.length > 0 ? (
        <div className="strategy-warning-list">
          {run.warnings.map((warning) => (
            <span key={warning}>{warning}</span>
          ))}
        </div>
      ) : null}
      <div className="strategy-card-grid">
        {runConfigs.map((config) => (
          <div className="strategy-summary-card" key={config.label}>
            <strong>{config.label}</strong>
            <pre>{formatConfig(config.value)}</pre>
          </div>
        ))}
      </div>
      <table className="strategy-table">
        <thead>
          <tr>
            <th>Artifact</th>
            <th>Format</th>
            <th>Path</th>
          </tr>
        </thead>
        <tbody>
          {artifacts.map((artifact) => (
            <tr key={`${artifact.run_id}-${artifact.path}`}>
              <td>{artifact.title}</td>
              <td>{artifact.format}</td>
              <td>{artifact.path}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
