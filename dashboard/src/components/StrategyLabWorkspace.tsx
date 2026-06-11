import { useState } from 'react';
import { BacktestLabWorkspace } from './BacktestLabWorkspace';
import { StrategyValidationWorkspace } from './StrategyValidationWorkspace';

type StrategyLabTab = 'backtest' | 'validation';
const BACKTEST_TAB_ID = 'strategy-lab-tab-backtest';
const VALIDATION_TAB_ID = 'strategy-lab-tab-validation';
const BACKTEST_PANEL_ID = 'strategy-lab-panel-backtest';
const VALIDATION_PANEL_ID = 'strategy-lab-panel-validation';

export function StrategyLabWorkspace() {
  const [tab, setTab] = useState<StrategyLabTab>('backtest');
  const isBacktest = tab === 'backtest';
  const activePanelId = isBacktest ? BACKTEST_PANEL_ID : VALIDATION_PANEL_ID;
  const activeTabId = isBacktest ? BACKTEST_TAB_ID : VALIDATION_TAB_ID;

  return (
    <section className="workspace-stack" aria-label="Strategy Lab workspace">
      <header className="workspace-header">
        <h1>Strategy Lab</h1>
        <p className="muted">Run local backtests and inspect existing strategy validation evidence.</p>
      </header>
      <div className="segmented-control" role="tablist" aria-label="Strategy Lab sections">
        <button
          type="button"
          role="tab"
          id={BACKTEST_TAB_ID}
          className={isBacktest ? 'active' : ''}
          aria-selected={isBacktest}
          aria-controls={BACKTEST_PANEL_ID}
          tabIndex={isBacktest ? 0 : -1}
          onClick={() => setTab('backtest')}
        >
          Run Backtest
        </button>
        <button
          type="button"
          role="tab"
          id={VALIDATION_TAB_ID}
          className={!isBacktest ? 'active' : ''}
          aria-selected={!isBacktest}
          aria-controls={VALIDATION_PANEL_ID}
          tabIndex={!isBacktest ? 0 : -1}
          onClick={() => setTab('validation')}
        >
          Validation Replay
        </button>
      </div>
      <div role="tabpanel" id={activePanelId} aria-labelledby={activeTabId}>
        {isBacktest ? <BacktestLabWorkspace embedded /> : <StrategyValidationWorkspace />}
      </div>
    </section>
  );
}
