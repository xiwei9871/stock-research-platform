import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { UserManagementView } from '../src/views/UserManagementView';
import type { AdminUser } from '../src/api/types';

type ImportMetaWithGlob = ImportMeta & {
  glob: (
    pattern: string,
    options: { query: string; import: string; eager: boolean }
  ) => Record<string, string>;
};

const userManagementViewSource = (import.meta as ImportMetaWithGlob).glob('../src/views/UserManagementView.tsx', {
  query: '?raw',
  import: 'default',
  eager: true
})['../src/views/UserManagementView.tsx'] as string;

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

  it('imports user management helpers directly', () => {
    expect(userManagementViewSource).toContain("from '../api/client'");
    expect(userManagementViewSource).toContain('fetchUsers');
    expect(userManagementViewSource).toContain('createUser');
    expect(userManagementViewSource).toContain('resetUserPassword');
    expect(userManagementViewSource).toContain('disableUser');
    expect(userManagementViewSource).toContain('enableUser');
    expect(userManagementViewSource).not.toContain('import * as client');
    expect(userManagementViewSource).not.toContain('Record<string, unknown>');
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
