import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  AppShell: ({
    currentUser,
    onLogout,
    logoutPending,
    logoutError
  }: {
    currentUser?: { username: string };
    onLogout?: () => void;
    logoutPending?: boolean;
    logoutError?: string;
  }) => (
    <div>
      Official Dashboard {currentUser?.username}
      {logoutError ? <p role="alert">{logoutError}</p> : null}
      <button type="button" disabled={logoutPending} onClick={onLogout}>
        退出登录
      </button>
    </div>
  )
}));

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
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

  it('disables login while pending and blocks duplicate submissions', async () => {
    let resolveLogin: ((value: { user: { user_id: string; username: string; display_name: string; role: 'admin'; is_active: boolean } }) => void) | undefined;
    apiMocks.fetchCurrentUser.mockRejectedValueOnce(new Error('not_authenticated'));
    apiMocks.loginDashboardUser.mockImplementation(
      () => new Promise((resolve) => {
        resolveLogin = resolve;
      })
    );

    render(<DashboardAuthRoot />);
    fireEvent.change(await screen.findByLabelText('用户名'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'secret' } });
    const loginButton = screen.getByRole('button', { name: '登录' });
    fireEvent.click(loginButton);
    fireEvent.click(loginButton);

    expect(loginButton).toBeDisabled();
    expect(loginButton).toHaveTextContent('登录中…');
    expect(apiMocks.loginDashboardUser).toHaveBeenCalledTimes(1);

    resolveLogin?.({
      user: { user_id: 'user:1', username: 'admin', display_name: 'Admin', role: 'admin', is_active: true }
    });
    expect(await screen.findByText('Official Dashboard admin')).toBeVisible();
  });

  it('keeps a newer login pending when an older login settles after session expiry', async () => {
    type LoginPayload = {
      user: { user_id: string; username: string; display_name: string; role: 'user'; is_active: boolean };
    };
    let resolveOldLogin: ((value: LoginPayload) => void) | undefined;
    let resolveNewLogin: ((value: LoginPayload) => void) | undefined;
    const oldLogin = new Promise<LoginPayload>((resolve) => {
      resolveOldLogin = resolve;
    });
    const newLogin = new Promise<LoginPayload>((resolve) => {
      resolveNewLogin = resolve;
    });
    apiMocks.fetchCurrentUser.mockRejectedValueOnce(new Error('not_authenticated'));
    apiMocks.loginDashboardUser.mockReturnValueOnce(oldLogin).mockReturnValueOnce(newLogin);

    render(<DashboardAuthRoot />);
    fireEvent.change(await screen.findByLabelText('用户名'), { target: { value: 'analyst' } });
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'secret' } });
    fireEvent.click(screen.getByRole('button', { name: '登录' }));
    window.dispatchEvent(new CustomEvent('dashboard-auth-expired'));

    await waitFor(() => expect(screen.getByRole('button', { name: '登录' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '登录' }));
    const currentLoginButton = screen.getByRole('button', { name: '登录' });
    expect(currentLoginButton).toBeDisabled();
    expect(apiMocks.loginDashboardUser).toHaveBeenCalledTimes(2);

    await act(async () => {
      resolveOldLogin?.({
        user: { user_id: 'user:old', username: 'old', display_name: 'Old', role: 'user', is_active: true }
      });
      await oldLogin;
    });

    expect(screen.getByRole('button', { name: '登录' })).toBeDisabled();
    expect(screen.queryByText('Official Dashboard old')).not.toBeInTheDocument();

    resolveNewLogin?.({
      user: { user_id: 'user:new', username: 'analyst', display_name: 'Analyst', role: 'user', is_active: true }
    });
    expect(await screen.findByText('Official Dashboard analyst')).toBeVisible();
  });

  it('returns to login after logout succeeds and calls the API once', async () => {
    apiMocks.fetchCurrentUser.mockResolvedValueOnce({
      user: { user_id: 'user:1', username: 'admin', display_name: 'Admin', role: 'admin', is_active: true }
    });
    apiMocks.logoutDashboardUser.mockResolvedValueOnce({ status: 'ok' });

    render(<DashboardAuthRoot />);

    fireEvent.click(await screen.findByRole('button', { name: '退出登录' }));

    expect(await screen.findByRole('heading', { name: '登录' })).toBeVisible();
    expect(apiMocks.logoutDashboardUser).toHaveBeenCalledTimes(1);
  });

  it('keeps the dashboard visible and shows an alert when logout fails', async () => {
    apiMocks.fetchCurrentUser.mockResolvedValueOnce({
      user: { user_id: 'user:1', username: 'admin', display_name: 'Admin', role: 'admin', is_active: true }
    });
    apiMocks.logoutDashboardUser.mockRejectedValueOnce(new Error('network unavailable'));

    render(<DashboardAuthRoot />);

    fireEvent.click(await screen.findByRole('button', { name: '退出登录' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('退出登录失败：network unavailable');
    expect(screen.getByText('Official Dashboard admin')).toBeVisible();
    expect(screen.queryByRole('heading', { name: '登录' })).not.toBeInTheDocument();
  });

  it('clears a previous logout error when retrying and after success', async () => {
    let resolveRetry: ((value: { status: string }) => void) | undefined;
    apiMocks.fetchCurrentUser.mockResolvedValueOnce({
      user: { user_id: 'user:1', username: 'admin', display_name: 'Admin', role: 'admin', is_active: true }
    });
    apiMocks.logoutDashboardUser
      .mockRejectedValueOnce(new Error('network unavailable'))
      .mockImplementationOnce(
        () => new Promise((resolve) => {
          resolveRetry = resolve;
        })
      );

    render(<DashboardAuthRoot />);

    fireEvent.click(await screen.findByRole('button', { name: '退出登录' }));
    expect(await screen.findByRole('alert')).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: '退出登录' }));

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '退出登录' })).toBeDisabled();

    resolveRetry?.({ status: 'ok' });
    expect(await screen.findByRole('heading', { name: '登录' })).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('disables logout while pending and blocks duplicate API calls', async () => {
    let resolveLogout: ((value: { status: string }) => void) | undefined;
    apiMocks.fetchCurrentUser.mockResolvedValueOnce({
      user: { user_id: 'user:1', username: 'admin', display_name: 'Admin', role: 'admin', is_active: true }
    });
    apiMocks.logoutDashboardUser.mockImplementationOnce(
      () => new Promise((resolve) => {
        resolveLogout = resolve;
      })
    );

    render(<DashboardAuthRoot />);

    const logoutButton = await screen.findByRole('button', { name: '退出登录' });
    fireEvent.click(logoutButton);
    fireEvent.click(logoutButton);

    expect(logoutButton).toBeDisabled();
    expect(apiMocks.logoutDashboardUser).toHaveBeenCalledTimes(1);

    resolveLogout?.({ status: 'ok' });
    await waitFor(() => expect(screen.getByRole('heading', { name: '登录' })).toBeVisible());
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

  it('ignores an initial auth response that resolves after session expiry', async () => {
    let resolveCurrentUser: ((value: { user: { user_id: string; username: string; display_name: string; role: 'admin'; is_active: boolean } }) => void) | undefined;
    const currentUserRequest = new Promise<{ user: { user_id: string; username: string; display_name: string; role: 'admin'; is_active: boolean } }>((resolve) => {
      resolveCurrentUser = resolve;
    });
    apiMocks.fetchCurrentUser.mockReturnValueOnce(currentUserRequest);

    render(<DashboardAuthRoot />);
    window.dispatchEvent(new CustomEvent('dashboard-auth-expired'));

    expect(await screen.findByRole('heading', { name: '登录' })).toBeVisible();

    await act(async () => {
      resolveCurrentUser?.({
        user: { user_id: 'user:1', username: 'admin', display_name: 'Admin', role: 'admin', is_active: true }
      });
      await currentUserRequest;
    });

    expect(screen.getByRole('heading', { name: '登录' })).toBeVisible();
    expect(screen.queryByText('Official Dashboard admin')).not.toBeInTheDocument();
  });

  it('ignores a stale logout result after session expiry and a new login', async () => {
    let resolveLogout: ((value: { status: string }) => void) | undefined;
    const logoutRequest = new Promise<{ status: string }>((resolve) => {
      resolveLogout = resolve;
    });
    apiMocks.fetchCurrentUser.mockResolvedValueOnce({
      user: { user_id: 'user:1', username: 'admin', display_name: 'Admin', role: 'admin', is_active: true }
    });
    apiMocks.logoutDashboardUser.mockReturnValueOnce(logoutRequest);
    apiMocks.loginDashboardUser.mockResolvedValueOnce({
      user: { user_id: 'user:2', username: 'analyst', display_name: 'Analyst', role: 'user', is_active: true }
    });

    render(<DashboardAuthRoot />);
    fireEvent.click(await screen.findByRole('button', { name: '退出登录' }));
    window.dispatchEvent(new CustomEvent('dashboard-auth-expired'));

    fireEvent.change(await screen.findByLabelText('用户名'), { target: { value: 'analyst' } });
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'secret' } });
    fireEvent.click(screen.getByRole('button', { name: '登录' }));
    expect(await screen.findByText('Official Dashboard analyst')).toBeVisible();

    await act(async () => {
      resolveLogout?.({ status: 'ok' });
      await logoutRequest;
    });

    expect(screen.getByText('Official Dashboard analyst')).toBeVisible();
    expect(screen.queryByRole('heading', { name: '登录' })).not.toBeInTheDocument();
  });
});
