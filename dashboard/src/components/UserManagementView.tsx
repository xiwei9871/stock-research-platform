import { useEffect, useState } from 'react';
import { createAdminUser, disableAdminUser, enableAdminUser, fetchAdminUsers, resetAdminUserPassword } from '../api/client';
import type { AdminUser } from '../api/types';

export function UserManagementView() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [creating, setCreating] = useState(false);
  const [resetPasswords, setResetPasswords] = useState<Record<string, string>>({});

  function loadUsers() {
    setLoading(true);
    setError('');
    fetchAdminUsers()
      .then((payload) => setUsers(payload.items))
      .catch((err) => setError(`用户列表加载失败：${err instanceof Error ? err.message : 'unknown'}`))
      .finally(() => setLoading(false));
  }

  function recordAction(action: Promise<unknown>) {
    setError('');
    action
      .then(() => loadUsers())
      .catch((err) => setError(`用户操作失败：${err instanceof Error ? err.message : 'unknown'}`));
  }

  useEffect(() => {
    loadUsers();
  }, []);

  return (
    <section className="workspace-band user-management-view">
      <div className="workspace-heading">
        <div>
          <p className="eyebrow">Admin</p>
          <h1>用户管理</h1>
        </div>
      </div>

      <form
        className="user-management-form"
        onSubmit={(event) => {
          event.preventDefault();
          const formElement = event.currentTarget;
          const form = new FormData(formElement);
          const username = String(form.get('username') ?? '').trim();
          const password = String(form.get('password') ?? '');
          const displayName = String(form.get('display_name') ?? '').trim();
          const role = String(form.get('role') ?? 'user') === 'admin' ? 'admin' : 'user';
          setCreating(true);
          setError('');
          createAdminUser({ username, password, role, display_name: displayName })
            .then(() => {
              formElement.reset();
              loadUsers();
            })
            .catch((err) => setError(`创建用户失败：${err instanceof Error ? err.message : 'unknown'}`))
            .finally(() => setCreating(false));
        }}
      >
        <label>
          新用户名
          <input name="username" required autoComplete="off" />
        </label>
        <label>
          显示名
          <input name="display_name" autoComplete="off" />
        </label>
        <label>
          初始密码
          <input name="password" type="password" required autoComplete="new-password" />
        </label>
        <label>
          角色
          <select name="role" defaultValue="user">
            <option value="user">user</option>
            <option value="admin">admin</option>
          </select>
        </label>
        <button type="submit" disabled={creating}>
          创建用户
        </button>
      </form>

      {error ? <p role="alert" className="status-error">{error}</p> : null}
      {loading ? <p className="muted">加载用户列表...</p> : null}
      {!loading && users.length === 0 ? <p className="muted">暂无用户</p> : null}
      {users.length > 0 ? (
        <div className="table-scroll">
          <table className="data-table" aria-label="Dashboard users">
            <thead>
              <tr>
                <th>用户名</th>
                <th>显示名</th>
                <th>角色</th>
                <th>状态</th>
                <th>创建时间</th>
                <th>最近登录</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.user_id}>
                  <td>{user.username}</td>
                  <td>{user.display_name || '-'}</td>
                  <td>{user.role}</td>
                  <td>{user.is_active ? 'active' : 'disabled'}</td>
                  <td>{user.created_at || '-'}</td>
                  <td>{user.last_login_at || '-'}</td>
                  <td>
                    <div className="user-management-actions">
                      <button type="button" onClick={() => recordAction(disableAdminUser(user.user_id))}>
                        停用 {user.username}
                      </button>
                      <button type="button" onClick={() => recordAction(enableAdminUser(user.user_id))}>
                        启用 {user.username}
                      </button>
                      <label>
                        <span className="sr-only">重置 {user.username} 密码</span>
                        <input
                          aria-label={`重置 ${user.username} 密码`}
                          type="password"
                          value={resetPasswords[user.user_id] ?? ''}
                          onChange={(event) =>
                            setResetPasswords((current) => ({ ...current, [user.user_id]: event.currentTarget.value }))
                          }
                        />
                      </label>
                      <button
                        type="button"
                        onClick={() => recordAction(resetAdminUserPassword(user.user_id, resetPasswords[user.user_id] ?? ''))}
                      >
                        重置 {user.username} 密码
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
