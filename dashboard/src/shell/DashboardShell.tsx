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
      <main className="dashboard-shell-content">
        <WorkspaceComponent />
      </main>
    </div>
  );
}

function readWorkspaceFromUrl() {
  if (typeof window === 'undefined') {
    return { workspace: DEFAULT_WORKSPACE, shouldCanonicalize: false };
  }

  const rawWorkspace = new URLSearchParams(window.location.search).get('workspace');
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
