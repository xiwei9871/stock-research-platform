import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { UserManagementView } from '../src/components/UserManagementView';

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
