import { useEffect, useState } from 'react';
import { DailyReviewLiteWorkspace } from '../workspaces/DailyReviewLiteWorkspace';
import { WorkbenchWorkspace } from '../workspaces/WorkbenchWorkspace';

const NAV_ITEMS = [
  { label: '复盘队列', workspace: 'review-queue' },
  { label: 'Daily Review Lite', workspace: 'daily-review-lite' },
  { label: '市场监控', workspace: 'market-monitor' }
] as const;

type Workspace = (typeof NAV_ITEMS)[number]['workspace'];

const DEFAULT_WORKSPACE: Workspace = 'review-queue';

export function DashboardShell() {
  const [workspace, setWorkspace] = useState<Workspace>(() => readWorkspaceFromUrl().workspace);

  useEffect(() => {
    syncWorkspaceWithUrl();

    const handlePopState = () => {
      syncWorkspaceWithUrl();
    };

    window.addEventListener('popstate', handlePopState);
    return () => {
      window.removeEventListener('popstate', handlePopState);
    };
  }, []);

  function syncWorkspaceWithUrl() {
    const { workspace: nextWorkspace, shouldCanonicalize } = readWorkspaceFromUrl();
    if (shouldCanonicalize) {
      writeWorkspaceToUrl(nextWorkspace, { replace: true });
    }
    setWorkspace(nextWorkspace);
  }

  function handleWorkspaceSelect(nextWorkspace: Workspace) {
    writeWorkspaceToUrl(nextWorkspace);
    setWorkspace(nextWorkspace);
  }

  const WorkspaceComponent =
    workspace === 'daily-review-lite' ? DailyReviewLiteWorkspace : WorkbenchWorkspace;

  return (
    <div className="dashboard-shell">
      <nav className="dashboard-shell-nav" aria-label="Dashboard workspaces">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.workspace}
            type="button"
            aria-pressed={workspace === item.workspace}
            onClick={() => handleWorkspaceSelect(item.workspace)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <div className="dashboard-shell-content">
        <WorkspaceComponent />
      </div>
    </div>
  );
}

function readWorkspaceFromUrl() {
  if (typeof window === 'undefined') {
    return { workspace: DEFAULT_WORKSPACE, shouldCanonicalize: false };
  }

  const params = new URLSearchParams(window.location.search);
  const rawWorkspace = params.get('workspace');
  if (rawWorkspace === null && hasValidTradeDate(params.get('trade_date'))) {
    return { workspace: 'daily-review-lite' as Workspace, shouldCanonicalize: false };
  }

  return {
    workspace: normalizeWorkspace(rawWorkspace),
    shouldCanonicalize: rawWorkspace !== null && !isWorkspace(rawWorkspace)
  };
}

function writeWorkspaceToUrl(workspace: Workspace, options?: { replace?: boolean }) {
  const url = new URL(window.location.href);
  url.searchParams.set('workspace', workspace);
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

function hasValidTradeDate(value: string | null) {
  return value !== null && /^\d{4}-\d{2}-\d{2}$/.test(value);
}
