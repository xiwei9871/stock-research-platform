import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DashboardShell } from '../src/shell/DashboardShell';

vi.mock('../src/workspaces/WorkbenchWorkspace', () => ({
  WorkbenchWorkspace: () => <div data-testid="workbench-workspace">workbench workspace</div>
}));

vi.mock('../src/pages/DailyReviewLitePage', () => ({
  DailyReviewLitePage: ({ initialTradeDate }: { initialTradeDate?: string }) => (
    <div data-testid="daily-review-lite-workspace">
      <label>
        <span>Trade Date</span>
        <input type="date" value={initialTradeDate ?? ''} readOnly />
      </label>
    </div>
  )
}));

afterEach(() => {
  cleanup();
  window.history.replaceState({}, '', '/');
});

describe('DashboardShell', () => {
  it('renders the workspace nav order and switches to the lite workspace via URL state', () => {
    const { container } = render(<DashboardShell />);

    expect(screen.getByTestId('workbench-workspace')).toBeInTheDocument();

    expect(container.firstElementChild).toHaveClass('dashboard-shell');
    const shellContent = container.querySelector('.dashboard-shell-content');
    expect(shellContent?.tagName).toBe('DIV');
    expect(shellContent).toContainElement(screen.getByTestId('workbench-workspace'));

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

  it('mounts the lite workspace from the workspace and trade_date query params', () => {
    window.history.replaceState({}, '', '/?workspace=daily-review-lite&trade_date=2026-06-19');

    const { container } = render(<DashboardShell />);

    expect(container.firstElementChild).toHaveClass('dashboard-shell');
    expect(container.querySelector('.dashboard-shell-nav')).toHaveAttribute(
      'aria-label',
      'Dashboard workspaces'
    );
    expect(container.querySelector('.dashboard-shell-content')).toBeInTheDocument();
    expect(screen.getByTestId('daily-review-lite-workspace')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Daily Review Lite' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByLabelText('Trade Date')).toHaveValue('2026-06-19');
  });

  it('infers the lite workspace from a valid trade_date query param when workspace is omitted', () => {
    window.history.replaceState({}, '', '/?trade_date=2026-06-19');

    render(<DashboardShell />);

    expect(screen.getByTestId('daily-review-lite-workspace')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Daily Review Lite' })).toHaveAttribute('aria-pressed', 'true');
    expect(new URLSearchParams(window.location.search).get('workspace')).toBeNull();
    expect(screen.getByLabelText('Trade Date')).toHaveValue('2026-06-19');
  });

  it('normalizes unknown workspace query params to the canonical workbench fallback', () => {
    window.history.replaceState({}, '', '/?workspace=unknown-workspace');

    render(<DashboardShell />);

    expect(screen.getByTestId('workbench-workspace')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '复盘队列' })).toHaveAttribute('aria-pressed', 'true');
    expect(new URLSearchParams(window.location.search).get('workspace')).toBe('review-queue');
  });

  it('syncs workspace state from popstate events after the URL changes', () => {
    render(<DashboardShell />);

    window.history.pushState({}, '', '/?workspace=daily-review-lite');
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate'));
    });

    expect(screen.getByTestId('daily-review-lite-workspace')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Daily Review Lite' })).toHaveAttribute('aria-pressed', 'true');

    window.history.pushState({}, '', '/?workspace=not-real');
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate'));
    });

    expect(screen.getByTestId('workbench-workspace')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '复盘队列' })).toHaveAttribute('aria-pressed', 'true');
    expect(new URLSearchParams(window.location.search).get('workspace')).toBe('review-queue');
  });
});
