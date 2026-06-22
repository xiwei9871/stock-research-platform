import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { UserManagementView } from '../src/views/UserManagementView';
import type { AdminUser } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchUsers: vi.fn(),
  createUser: vi.fn(),
  resetUserPassword: vi.fn(),
  disableUser: vi.fn(),
  enableUser: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

function makeUser(id: number, overrides: Partial<AdminUser> = {}): AdminUser {
  return {
    id,
    username: `user-${id}`,
    email: `user-${id}@example.com`,
    display_name: `User ${id}`,
    role: 'user',
    is_active: true,
    disabled_at: null,
    ...overrides
  };
}

describe('UserManagementView', () => {
  const promptSpy = vi.spyOn(window, 'prompt');

  beforeEach(() => {
    promptSpy.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('hides the self-disable action for the current user row', async () => {
    apiMocks.fetchUsers.mockResolvedValueOnce([
      makeUser(1, { username: 'admin', display_name: 'Admin User', role: 'admin' }),
      makeUser(2, { username: 'analyst' })
    ]);

    render(<UserManagementView currentUserId={1} />);

    const currentUserRow = await screen.findByTestId('user-row-1');
    expect(within(currentUserRow).queryByRole('button', { name: '禁用' })).not.toBeInTheDocument();
    expect(within(currentUserRow).getByRole('button', { name: '重置密码' })).toBeVisible();

    const otherUserRow = await screen.findByTestId('user-row-2');
    expect(within(otherUserRow).getByRole('button', { name: '禁用' })).toBeVisible();
  });

  it('creates a new user and refreshes the list', async () => {
    apiMocks.fetchUsers
      .mockResolvedValueOnce([makeUser(1)])
      .mockResolvedValueOnce([makeUser(1), makeUser(2, { username: 'analyst', display_name: 'Analyst', role: 'admin' })]);
    apiMocks.createUser.mockResolvedValue(
      makeUser(2, { username: 'analyst', display_name: 'Analyst', role: 'admin' })
    );

    render(<UserManagementView />);

    expect(await screen.findByText('user-1')).toBeVisible();

    fireEvent.change(screen.getByLabelText('用户名'), { target: { value: 'analyst' } });
    fireEvent.change(screen.getByLabelText('显示名称'), { target: { value: 'Analyst' } });
    fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'analyst@example.com' } });
    fireEvent.change(screen.getByLabelText('初始密码'), { target: { value: 'Secret123!' } });
    fireEvent.change(screen.getByLabelText('角色'), { target: { value: 'admin' } });
    fireEvent.click(screen.getByRole('button', { name: '创建用户' }));

    await waitFor(() => {
      expect(apiMocks.createUser).toHaveBeenCalledWith({
        username: 'analyst',
        display_name: 'Analyst',
        email: 'analyst@example.com',
        password: 'Secret123!',
        role: 'admin'
      });
    });
    await waitFor(() => {
      expect(apiMocks.fetchUsers).toHaveBeenCalledTimes(2);
    });
    expect(await screen.findByText('analyst')).toBeVisible();
  });

  it('supports password reset and enable-disable actions', async () => {
    apiMocks.fetchUsers
      .mockResolvedValueOnce([
        makeUser(1),
        makeUser(2, { username: 'disabled-user', is_active: false, disabled_at: '2026-06-20T00:00:00Z' })
      ])
      .mockResolvedValueOnce([
        makeUser(1, { is_active: false, disabled_at: '2026-06-21T00:00:00Z' }),
        makeUser(2, { username: 'disabled-user', is_active: false, disabled_at: '2026-06-20T00:00:00Z' })
      ])
      .mockResolvedValueOnce([
        makeUser(1, { is_active: false, disabled_at: '2026-06-21T00:00:00Z' }),
        makeUser(2, { username: 'disabled-user', is_active: true, disabled_at: null })
      ]);
    apiMocks.resetUserPassword.mockResolvedValue({ ok: true });
    apiMocks.disableUser.mockResolvedValue({ ok: true });
    apiMocks.enableUser.mockResolvedValue({ ok: true });
    promptSpy.mockReturnValue('NewSecret123!');

    render(<UserManagementView />);

    const activeRow = await screen.findByTestId('user-row-1');
    fireEvent.click(within(activeRow).getByRole('button', { name: '重置密码' }));

    await waitFor(() => {
      expect(apiMocks.resetUserPassword).toHaveBeenCalledWith(1, 'NewSecret123!');
    });

    fireEvent.click(within(activeRow).getByRole('button', { name: '禁用' }));

    await waitFor(() => {
      expect(apiMocks.disableUser).toHaveBeenCalledWith(1);
    });

    const disabledRow = await screen.findByTestId('user-row-2');
    fireEvent.click(within(disabledRow).getByRole('button', { name: '启用' }));

    await waitFor(() => {
      expect(apiMocks.enableUser).toHaveBeenCalledWith(2);
    });
    await waitFor(() => {
      expect(apiMocks.fetchUsers).toHaveBeenCalledTimes(3);
    });
  });
});
