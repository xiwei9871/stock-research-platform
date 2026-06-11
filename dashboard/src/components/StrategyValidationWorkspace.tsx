import { useEffect, useMemo, useState } from 'react';
import { fetchStrategyValidationReplay, fetchStrategyValidationRuns } from '../api/client';
import type { StrategyReplayPayload, StrategyValidationRun } from '../api/types';
import { StrategyCohortPanel } from './StrategyCohortPanel';
import { StrategyEvidencePanel } from './StrategyEvidencePanel';
import { StrategyPortfolioRiskPanel } from './StrategyPortfolioRiskPanel';
import { StrategyReplayPanel } from './StrategyReplayPanel';

type StrategyTab = 'replay' | 'cohort' | 'risk' | 'evidence';

const DEFAULT_ASSET_ID = '000001.SZ';

export function StrategyValidationWorkspace() {
  const [runs, setRuns] = useState<StrategyValidationRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState('');
  const [selectedAssetId, setSelectedAssetId] = useState(DEFAULT_ASSET_ID);
  const [activeTab, setActiveTab] = useState<StrategyTab>('replay');
  const [replay, setReplay] = useState<StrategyReplayPayload | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isReplayLoading, setIsReplayLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedRun = useMemo(
    () => runs.find((run) => run.run_id === selectedRunId) ?? null,
    [runs, selectedRunId]
  );

  useEffect(() => {
    let ignore = false;
    setIsLoading(true);
    setError(null);
    fetchStrategyValidationRuns()
      .then((rows) => {
        if (!ignore) {
          setRuns(rows);
          setSelectedRunId(rows[0]?.run_id ?? '');
          setIsReplayLoading(rows.length > 0);
          setIsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : String(err));
          setIsReplayLoading(false);
          setIsLoading(false);
        }
      });
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedRun) {
      setReplay(null);
      setIsReplayLoading(false);
      return;
    }
    let ignore = false;
    setError(null);
    setIsReplayLoading(true);
    fetchStrategyValidationReplay(selectedRun.run_id, selectedAssetId, selectedRun.start_date, selectedRun.end_date)
      .then((payload) => {
        if (!ignore) {
          setReplay(payload);
          setIsReplayLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : String(err));
          setReplay(null);
          setIsReplayLoading(false);
        }
      });
    return () => {
      ignore = true;
    };
  }, [selectedRun, selectedAssetId]);

  if (isLoading || isReplayLoading) {
    return <p className="muted">Loading strategy validation...</p>;
  }

  if (error && runs.length === 0) {
    return <p className="error-text">{error}</p>;
  }

  if (runs.length === 0) {
    return <p className="muted">No strategy validation runs found.</p>;
  }

  return (
    <section className="strategy-workspace">
      <header className="strategy-toolbar">
        <select aria-label="strategy validation run" value={selectedRunId} onChange={(event) => setSelectedRunId(event.target.value)}>
          {runs.map((run) => (
            <option key={run.run_id} value={run.run_id}>
              {run.strategy_name}
            </option>
          ))}
        </select>
        <input aria-label="strategy asset id" value={selectedAssetId} onChange={(event) => setSelectedAssetId(event.target.value.trim())} />
        {error ? <span className="error-text">{error}</span> : null}
      </header>
      <nav className="strategy-tabs" aria-label="strategy validation tabs">
        <button type="button" className={activeTab === 'replay' ? 'active' : ''} onClick={() => setActiveTab('replay')}>Replay</button>
        <button type="button" className={activeTab === 'cohort' ? 'active' : ''} onClick={() => setActiveTab('cohort')}>Cohort</button>
        <button type="button" className={activeTab === 'risk' ? 'active' : ''} onClick={() => setActiveTab('risk')}>Portfolio Risk</button>
        <button type="button" className={activeTab === 'evidence' ? 'active' : ''} onClick={() => setActiveTab('evidence')}>Evidence</button>
      </nav>
      {selectedRun && replay ? (
        <>
          {activeTab === 'replay' ? <StrategyReplayPanel replay={replay} /> : null}
          {activeTab === 'cohort' ? <StrategyCohortPanel rows={replay.metrics} /> : null}
          {activeTab === 'risk' ? <StrategyPortfolioRiskPanel rows={replay.positions} /> : null}
          {activeTab === 'evidence' ? <StrategyEvidencePanel run={selectedRun} artifacts={replay.artifacts} /> : null}
        </>
      ) : (
        <p className="muted">No replay rows for selected asset in this run.</p>
      )}
    </section>
  );
}
