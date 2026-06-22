import { useEffect, useState } from 'react';
import { DailyReviewLiteWorkspace } from '../workspaces/DailyReviewLiteWorkspace';
import { WorkbenchWorkspace } from '../workspaces/WorkbenchWorkspace';

const NAV_ITEMS = [
  { label: '复盘队列', workspace: 'review-queue' },
  { label: 'Daily Review Lite', workspace: 'daily-review-lite' },
  { label: '市场监控', workspace: 'market-monitor' }
] as const;

type Workspace = (typeof NAV_ITEMS)[number]['workspace'];
type ShellUrlState = {
  workspace: Workspace;
  tradeDate?: string;
};

const DEFAULT_WORKSPACE: Workspace = 'review-queue';

export function DashboardShell() {
  const [urlState, setUrlState] = useState<ShellUrlState>(() => {
    const { workspace, tradeDate } = readUrlStateFromUrl();
    return { workspace, tradeDate };
  });

  useEffect(() => {
    syncUrlStateWithUrl();

    const handlePopState = () => {
      syncUrlStateWithUrl();
    };

    window.addEventListener('popstate', handlePopState);
    return () => {
      window.removeEventListener('popstate', handlePopState);
    };
  }, []);

  function syncUrlStateWithUrl() {
    const { workspace, tradeDate, shouldCanonicalize } = readUrlStateFromUrl();
    if (shouldCanonicalize) {
      writeUrlStateToUrl({ workspace, tradeDate }, { replace: true });
    }
    setUrlState({ workspace, tradeDate });
  }

  function handleWorkspaceSelect(nextWorkspace: Workspace) {
    const nextState = {
      workspace: nextWorkspace,
      tradeDate: urlState.tradeDate
    };
    writeUrlStateToUrl(nextState);
    setUrlState(nextState);
  }

  function handleTradeDateChange(nextTradeDate: string) {
    const nextState = {
      workspace: 'daily-review-lite' as Workspace,
      tradeDate: nextTradeDate
    };
    writeUrlStateToUrl(nextState);
    setUrlState(nextState);
  }

  const WorkspaceComponent =
    urlState.workspace === 'daily-review-lite' ? DailyReviewLiteWorkspace : WorkbenchWorkspace;

  return (
    <div className="dashboard-shell">
      <nav className="dashboard-shell-nav" aria-label="Dashboard workspaces">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.workspace}
            type="button"
            aria-pressed={urlState.workspace === item.workspace}
            onClick={() => handleWorkspaceSelect(item.workspace)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <div className="dashboard-shell-content">
        {urlState.workspace === 'daily-review-lite' ? (
          <WorkspaceComponent tradeDate={urlState.tradeDate} onTradeDateChange={handleTradeDateChange} />
        ) : (
          <WorkspaceComponent />
        )}
      </div>
    </div>
  );
}

function readUrlStateFromUrl(): ShellUrlState & { shouldCanonicalize: boolean } {
  if (typeof window === 'undefined') {
    return { workspace: DEFAULT_WORKSPACE, tradeDate: undefined, shouldCanonicalize: false };
  }

  const params = new URLSearchParams(window.location.search);
  const rawWorkspace = params.get('workspace');
  const tradeDate = normalizeTradeDate(params.get('trade_date'));
  const workspace = rawWorkspace === null && tradeDate ? ('daily-review-lite' as Workspace) : normalizeWorkspace(rawWorkspace);

  return {
    workspace,
    tradeDate,
    shouldCanonicalize: (rawWorkspace === null && tradeDate !== undefined) || (rawWorkspace !== null && !isWorkspace(rawWorkspace))
  };
}

function writeUrlStateToUrl({ workspace, tradeDate }: ShellUrlState, options?: { replace?: boolean }) {
  const url = new URL(window.location.href);
  url.searchParams.set('workspace', workspace);
  if (tradeDate) {
    url.searchParams.set('trade_date', tradeDate);
  } else {
    url.searchParams.delete('trade_date');
  }
  const nextUrl = `${url.pathname}${url.search}`;

  if (options?.replace) {
    window.history.replaceState({}, '', nextUrl);
    return;
  }

  window.history.pushState({}, '', nextUrl);
}

function normalizeWorkspace(workspace: string | null): Workspace {
  return isWorkspace(workspace) ? workspace : DEFAULT_WORKSPACE;
}

function isWorkspace(workspace: string | null): workspace is Workspace {
  return NAV_ITEMS.some((item) => item.workspace === workspace);
}

function hasValidTradeDate(value: string | null): value is string {
  return value !== null && /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function normalizeTradeDate(value: string | null): string | undefined {
  if (!hasValidTradeDate(value)) {
    return undefined;
  }

  return value;
}
