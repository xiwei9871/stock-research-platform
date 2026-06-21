import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DashboardShell } from '../src/shell/DashboardShell';

vi.mock('../src/workspaces/WorkbenchWorkspace', () => ({
  WorkbenchWorkspace: () => <div data-testid="workbench-workspace">workbench workspace</div>
}));

vi.mock('../src/workspaces/DailyReviewLiteWorkspace', () => ({
  DailyReviewLiteWorkspace: () => <div data-testid="daily-review-lite-workspace">lite workspace</div>
}));

afterEach(() => {
  cleanup();
  window.history.replaceState({}, '', '/');
});

describe('DashboardShell', () => {
  it('renders the workspace nav order and switches to the lite workspace via URL state', () => {
    render(<DashboardShell />);

    expect(screen.getByTestId('workbench-workspace')).toBeInTheDocument();

    const navigation = screen.getByRole('navigation', { name: 'Dashboard workspaces' });
    const navButtons = within(navigation).getAllByRole('button');
    const navLabels = navButtons.map((button) => button.textContent?.trim());

    expect(navLabels).toContain('复盘队列');
    expect(navLabels).toContain('Daily Review Lite');
    expect(navLabels).toContain('市场监控');

    const reviewQueueIndex = navLabels.indexOf('复盘队列');
    expect(navLabels[reviewQueueIndex + 1]).toBe('Daily Review Lite');
    expect(navLabels[reviewQueueIndex + 2]).toBe('市场监控');

    fireEvent.click(screen.getByRole('button', { name: 'Daily Review Lite' }));

    expect(screen.getByTestId('daily-review-lite-workspace')).toBeInTheDocument();
    expect(new URLSearchParams(window.location.search).get('workspace')).toBe('daily-review-lite');
  });
});
