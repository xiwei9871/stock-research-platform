import { useEffect, useState } from 'react';
import { DailyReviewLiteWorkspace } from '../workspaces/DailyReviewLiteWorkspace';
import { WorkbenchWorkspace } from '../workspaces/WorkbenchWorkspace';

const NAV_ITEMS = [
  { label: '复盘队列', workspace: 'review-queue' },
  { label: 'Daily Review Lite', workspace: 'daily-review-lite' },
  { label: '市场监控', workspace: 'market-monitor' }
] as const;

export function DashboardShell() {
  const [workspace, setWorkspace] = useState(() => readWorkspaceFromUrl());

  useEffect(() => {
    const handlePopState = () => {
      setWorkspace(readWorkspaceFromUrl());
    };

    window.addEventListener('popstate', handlePopState);
    return () => {
      window.removeEventListener('popstate', handlePopState);
    };
  }, []);

  function handleWorkspaceSelect(nextWorkspace: string) {
    writeWorkspaceToUrl(nextWorkspace);
    setWorkspace(nextWorkspace);
  }

  const WorkspaceComponent =
    workspace === 'daily-review-lite' ? DailyReviewLiteWorkspace : WorkbenchWorkspace;

  return (
    <>
      <nav aria-label="Dashboard workspaces">
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
      <WorkspaceComponent />
    </>
  );
}

function readWorkspaceFromUrl() {
  if (typeof window === 'undefined') {
    return null;
  }

  return new URLSearchParams(window.location.search).get('workspace');
}

function writeWorkspaceToUrl(workspace: string) {
  const url = new URL(window.location.href);
  url.searchParams.set('workspace', workspace);
  window.history.pushState({}, '', `${url.pathname}${url.search}`);
}
