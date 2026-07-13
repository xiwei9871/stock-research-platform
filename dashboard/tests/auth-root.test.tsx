import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DashboardAuthRoot } from '../src/components/DashboardAuthRoot';

const apiMocks = vi.hoisted(() => ({
  DASHBOARD_AUTH_EXPIRED_EVENT: 'dashboard-auth-expired',
  fetchCurrentUser: vi.fn(),
  loginDashboardUser: vi.fn(),
  logoutDashboardUser: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);
vi.mock('../src/components/AppShell', () => ({
  AppShell: ({ currentUser }: { currentUser?: { username: string } }) => (
    <div>Official Dashboard {currentUser?.username}</div>
  )
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('DashboardAuthRoot', () => {
  it('shows login when current user is not authenticated', async () => {
    apiMocks.fetchCurrentUser.mockRejectedValueOnce(new Error('not_authenticated'));

    render(<DashboardAuthRoot />);

    expect(await screen.findByRole('heading', { name: '登录' })).toBeVisible();
  });

  it('renders official dashboard after login succeeds', async () => {
    apiMocks.fetchCurrentUser.mockRejectedValueOnce(new Error('not_authenticated'));
    apiMocks.loginDashboardUser.mockResolvedValueOnce({
      user: { user_id: 'user:1', username: 'admin', display_name: 'Admin', role: 'admin', is_active: true }
    });

    render(<DashboardAuthRoot />);
    fireEvent.change(await screen.findByLabelText('用户名'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'secret' } });
    fireEvent.click(screen.getByRole('button', { name: '登录' }));

    expect(await screen.findByText('Official Dashboard admin')).toBeVisible();
    expect(apiMocks.loginDashboardUser).toHaveBeenCalledWith({ username: 'admin', password: 'secret' });
  });

  it('returns to login when the active session expires after the dashboard has rendered', async () => {
    apiMocks.fetchCurrentUser.mockResolvedValueOnce({
      user: { user_id: 'user:1', username: 'admin', display_name: 'Admin', role: 'admin', is_active: true }
    });

    render(<DashboardAuthRoot />);

    expect(await screen.findByText('Official Dashboard admin')).toBeVisible();

    window.dispatchEvent(new CustomEvent('dashboard-auth-expired'));

    expect(await screen.findByRole('heading', { name: '登录' })).toBeVisible();
  });
});
