import { KeyboardEvent, useRef, useState } from 'react';
import { BacktestLabWorkspace } from './BacktestLabWorkspace';
import { StrategyValidationWorkspace } from './StrategyValidationWorkspace';

type StrategyLabTab = 'backtest' | 'validation';
const BACKTEST_TAB_ID = 'strategy-lab-tab-backtest';
const VALIDATION_TAB_ID = 'strategy-lab-tab-validation';
const BACKTEST_PANEL_ID = 'strategy-lab-panel-backtest';
const VALIDATION_PANEL_ID = 'strategy-lab-panel-validation';

type StrategyLabWorkspaceProps = {
  defaultEndDate?: string;
};

export function StrategyLabWorkspace({ defaultEndDate }: StrategyLabWorkspaceProps = {}) {
  const [tab, setTab] = useState<StrategyLabTab>('backtest');
  const backtestTabRef = useRef<HTMLButtonElement>(null);
  const validationTabRef = useRef<HTMLButtonElement>(null);
  const isBacktest = tab === 'backtest';
  const activePanelId = isBacktest ? BACKTEST_PANEL_ID : VALIDATION_PANEL_ID;
  const activeTabId = isBacktest ? BACKTEST_TAB_ID : VALIDATION_TAB_ID;
  const selectTab = (nextTab: StrategyLabTab) => {
    setTab(nextTab);
    if (nextTab === 'backtest') {
      backtestTabRef.current?.focus();
    } else {
      validationTabRef.current?.focus();
    }
  };
  const handleTabKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
      event.preventDefault();
      selectTab(isBacktest ? 'validation' : 'backtest');
      return;
    }
    if (event.key === 'Home') {
      event.preventDefault();
      selectTab('backtest');
      return;
    }
    if (event.key === 'End') {
      event.preventDefault();
      selectTab('validation');
    }
  };

  return (
    <section className="workspace-stack" aria-label="Strategy Lab workspace">
      <header className="workspace-header">
        <h1>Strategy Lab</h1>
        <p className="muted">Run local backtests and inspect existing strategy validation evidence.</p>
      </header>
      <div className="segmented-control" role="tablist" aria-label="Strategy Lab sections" onKeyDown={handleTabKeyDown}>
        <button
          ref={backtestTabRef}
          type="button"
          role="tab"
          id={BACKTEST_TAB_ID}
          className={isBacktest ? 'active' : ''}
          aria-selected={isBacktest}
          aria-controls={BACKTEST_PANEL_ID}
          tabIndex={isBacktest ? 0 : -1}
          onClick={() => selectTab('backtest')}
        >
          Run Backtest
        </button>
        <button
          ref={validationTabRef}
          type="button"
          role="tab"
          id={VALIDATION_TAB_ID}
          className={!isBacktest ? 'active' : ''}
          aria-selected={!isBacktest}
          aria-controls={VALIDATION_PANEL_ID}
          tabIndex={!isBacktest ? 0 : -1}
          onClick={() => selectTab('validation')}
        >
          Validation Replay
        </button>
      </div>
      <div role="tabpanel" id={activePanelId} aria-labelledby={activeTabId}>
        {isBacktest ? <BacktestLabWorkspace embedded defaultEndDate={defaultEndDate} /> : <StrategyValidationWorkspace />}
      </div>
    </section>
  );
}
