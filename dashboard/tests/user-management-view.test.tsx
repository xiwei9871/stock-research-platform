import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ChangeEvent, Dispatch, SetStateAction } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { buildResetPasswordChangeHandler, UserManagementView } from '../src/components/UserManagementView';

const apiMocks = vi.hoisted(() => ({
  fetchAdminUsers: vi.fn(),
  createAdminUser: vi.fn(),
  disableAdminUser: vi.fn(),
  enableAdminUser: vi.fn(),
  resetAdminUserPassword: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('UserManagementView', () => {
  it('captures autofilled password before a deferred state updater runs', () => {
    let deferredUpdater: SetStateAction<Record<string, string>> | undefined;
    const setResetPasswords = vi.fn((updater: SetStateAction<Record<string, string>>) => {
      deferredUpdater = updater;
    }) as unknown as Dispatch<SetStateAction<Record<string, string>>>;
    const event = {
      currentTarget: { value: 'autofilled-secret' }
    } as unknown as ChangeEvent<HTMLInputElement>;

    buildResetPasswordChangeHandler('user:2', setResetPasswords)(event);
    Object.defineProperty(event, 'currentTarget', { value: null });

    let nextState: Record<string, string> | undefined;
    expect(() => {
      nextState = typeof deferredUpdater === 'function' ? deferredUpdater({}) : undefined;
    }).not.toThrow();
    expect(nextState).toEqual({ 'user:2': 'autofilled-secret' });
  });

  it('lists users and creates a user', async () => {
    apiMocks.fetchAdminUsers
      .mockResolvedValueOnce({
        items: [{ user_id: 'user:1', username: 'admin', display_name: 'Admin', role: 'admin', is_active: true }]
      })
      .mockResolvedValueOnce({
        items: [
          { user_id: 'user:1', username: 'admin', display_name: 'Admin', role: 'admin', is_active: true },
          { user_id: 'user:2', username: 'analyst', display_name: 'Analyst', role: 'user', is_active: true }
        ]
      });
    apiMocks.createAdminUser.mockResolvedValueOnce({
      user: { user_id: 'user:2', username: 'analyst', display_name: 'Analyst', role: 'user', is_active: true }
    });

    render(<UserManagementView />);

    expect(await screen.findByText('admin')).toBeVisible();
    fireEvent.change(screen.getByLabelText('新用户名'), { target: { value: 'analyst' } });
    fireEvent.change(screen.getByLabelText('初始密码'), { target: { value: 'secret123' } });
    fireEvent.click(screen.getByRole('button', { name: '创建用户' }));

    expect(apiMocks.createAdminUser).toHaveBeenCalledWith({
      username: 'analyst',
      password: 'secret123',
      role: 'user',
      display_name: ''
    });
    expect(await screen.findByText('analyst')).toBeVisible();
  });

  it('records disable enable and reset password actions', async () => {
    apiMocks.fetchAdminUsers.mockResolvedValue({
      items: [{ user_id: 'user:2', username: 'analyst', display_name: 'Analyst', role: 'user', is_active: true }]
    });
    apiMocks.disableAdminUser.mockResolvedValueOnce({ status: 'disabled', user_id: 'user:2' });
    apiMocks.enableAdminUser.mockResolvedValueOnce({ status: 'enabled', user_id: 'user:2' });
    apiMocks.resetAdminUserPassword.mockResolvedValueOnce({ status: 'password_reset', user_id: 'user:2' });

    render(<UserManagementView />);

    expect(await screen.findByText('analyst')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '停用 analyst' }));
    fireEvent.click(screen.getByRole('button', { name: '启用 analyst' }));
    fireEvent.change(screen.getByLabelText('重置 analyst 密码'), { target: { value: 'next-secret' } });
    fireEvent.click(screen.getByRole('button', { name: '重置 analyst 密码' }));

    expect(apiMocks.disableAdminUser).toHaveBeenCalledWith('user:2');
    expect(apiMocks.enableAdminUser).toHaveBeenCalledWith('user:2');
    expect(apiMocks.resetAdminUserPassword).toHaveBeenCalledWith('user:2', 'next-secret');
  });
});
