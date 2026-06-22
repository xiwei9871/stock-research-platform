import { FormEvent, useEffect, useState } from 'react';
import { createUser, disableUser, enableUser, fetchUsers, resetUserPassword } from '../api/client';
import type { AdminUser, CreateUserPayload, UserRole } from '../api/types';

function getErrorMessage(error: unknown) {
  if (typeof error === 'object' && error !== null && 'message' in error) {
    const message = (error as { message?: unknown }).message;
    if (typeof message === 'string' && message.length > 0) {
      return message;
    }
  }
  return '用户操作失败';
}

const defaultFormState: CreateUserPayload = {
  username: '',
  display_name: '',
  email: '',
  password: '',
  role: 'user'
};

type UserManagementViewProps = {
  currentUserId?: number | null;
};

export function UserManagementView({ currentUserId = null }: UserManagementViewProps) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [formState, setFormState] = useState<CreateUserPayload>(defaultFormState);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [actingUserId, setActingUserId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadUsers() {
    setLoading(true);
    try {
      const nextUsers = await fetchUsers();
      setUsers(nextUsers);
      setError(null);
    } catch (nextError: unknown) {
      setError(getErrorMessage(nextError));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadUsers();
  }, []);

  function updateField<Key extends keyof CreateUserPayload>(key: Key, value: CreateUserPayload[Key]) {
    setFormState((current) => ({ ...current, [key]: value }));
  }

  async function handleCreateUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    try {
      await createUser({
        username: formState.username.trim(),
        display_name: formState.display_name.trim(),
        email: formState.email?.trim() ? formState.email.trim() : null,
        password: formState.password,
        role: formState.role
      });
      setFormState(defaultFormState);
      await loadUsers();
    } catch (nextError: unknown) {
      setError(getErrorMessage(nextError));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleResetPassword(userId: number) {
    const password = window.prompt('请输入新密码');
    if (!password) {
      return;
    }

    setActingUserId(userId);
    try {
      await resetUserPassword(userId, password);
      setError(null);
    } catch (nextError: unknown) {
      setError(getErrorMessage(nextError));
    } finally {
      setActingUserId(null);
    }
  }

  async function handleToggleUser(user: AdminUser) {
    setActingUserId(user.id);
    try {
      if (user.is_active) {
        await disableUser(user.id);
      } else {
        await enableUser(user.id);
      }
      await loadUsers();
    } catch (nextError: unknown) {
      setError(getErrorMessage(nextError));
    } finally {
      setActingUserId(null);
    }
  }

  return (
    <section className="view-shell">
      <header className="view-header">
        <div>
          <h1>用户管理</h1>
          <p className="muted">创建账户并维护启用状态。</p>
        </div>
      </header>

      <form className="stack-form" onSubmit={handleCreateUser}>
        <div className="field-grid">
          <label className="field-group" htmlFor="user-username">
            <span>用户名</span>
            <input
              id="user-username"
              name="username"
              value={formState.username}
              onChange={(event) => updateField('username', event.target.value)}
            />
          </label>
          <label className="field-group" htmlFor="user-display-name">
            <span>显示名称</span>
            <input
              id="user-display-name"
              name="display_name"
              value={formState.display_name}
              onChange={(event) => updateField('display_name', event.target.value)}
            />
          </label>
          <label className="field-group" htmlFor="user-email">
            <span>邮箱</span>
            <input
              id="user-email"
              name="email"
              type="email"
              value={formState.email ?? ''}
              onChange={(event) => updateField('email', event.target.value)}
            />
          </label>
          <label className="field-group" htmlFor="user-password">
            <span>初始密码</span>
            <input
              id="user-password"
              name="password"
              type="password"
              value={formState.password}
              onChange={(event) => updateField('password', event.target.value)}
            />
          </label>
          <label className="field-group" htmlFor="user-role">
            <span>角色</span>
            <select
              id="user-role"
              name="role"
              value={formState.role}
              onChange={(event) => updateField('role', event.target.value as UserRole)}
            >
              <option value="user">user</option>
              <option value="admin">admin</option>
            </select>
          </label>
        </div>
        <button className="primary-button" type="submit" disabled={submitting}>
          {submitting ? '创建中...' : '创建用户'}
        </button>
      </form>

      {error ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="muted">加载用户中...</p>
      ) : users.length === 0 ? (
        <p className="muted">暂无用户。</p>
      ) : (
        <div className="entity-list">
          {users.map((user) => (
            <article key={user.id} className="entity-row user-row" data-testid={`user-row-${user.id}`}>
              <div className="entity-copy">
                <strong>{user.username}</strong>
                <span>{user.display_name}</span>
                <span className="muted">
                  {user.role} · {user.is_active ? '已启用' : '已禁用'}
                </span>
              </div>
              <div className="row-actions">
                <button
                  className="secondary-button"
                  type="button"
                  disabled={actingUserId === user.id}
                  onClick={() => {
                    void handleResetPassword(user.id);
                  }}
                >
                  重置密码
                </button>
                {user.is_active && user.id === currentUserId ? null : (
                  <button
                    className="secondary-button"
                    type="button"
                    disabled={actingUserId === user.id}
                    onClick={() => {
                      void handleToggleUser(user);
                    }}
                  >
                    {user.is_active ? '禁用' : '启用'}
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
