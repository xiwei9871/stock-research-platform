import { useState } from 'react';
import { BacktestLabWorkspace } from './BacktestLabWorkspace';
import { StrategyValidationWorkspace } from './StrategyValidationWorkspace';

type StrategyLabTab = 'backtest' | 'validation';

export function StrategyLabWorkspace() {
  const [tab, setTab] = useState<StrategyLabTab>('backtest');

  return (
    <section className="workspace-stack" aria-label="Strategy Lab workspace">
      <header className="workspace-header">
        <h1>Strategy Lab</h1>
        <p className="muted">Run local backtests and inspect existing strategy validation evidence.</p>
      </header>
      <div className="segmented-control" role="tablist" aria-label="Strategy Lab sections">
        <button type="button" role="tab" aria-selected={tab === 'backtest'} onClick={() => setTab('backtest')}>
          Run Backtest
        </button>
        <button type="button" role="tab" aria-selected={tab === 'validation'} onClick={() => setTab('validation')}>
          Validation Replay
        </button>
      </div>
      {tab === 'backtest' ? <BacktestLabWorkspace embedded /> : <StrategyValidationWorkspace embedded />}
    </section>
  );
}
