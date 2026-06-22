import { FormEvent, useState } from 'react';

type LoginViewProps = {
  error?: string | null;
  isSubmitting?: boolean;
  onSubmit: (identifier: string, password: string) => Promise<void>;
};

export function LoginView({ error = null, isSubmitting = false, onSubmit }: LoginViewProps) {
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSubmit(identifier, password);
  }

  return (
    <div className="workbench">
      <section className="workspace">
        <header className="toolbar">
          <h1>登录</h1>
        </header>
        <section className="chart-panel">
          <form onSubmit={handleSubmit}>
            <div>
              <label htmlFor="login-identifier">用户名或邮箱</label>
              <input
                id="login-identifier"
                name="identifier"
                value={identifier}
                onChange={(event) => setIdentifier(event.target.value)}
                autoComplete="username"
              />
            </div>
            <div>
              <label htmlFor="login-password">密码</label>
              <input
                id="login-password"
                name="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
              />
            </div>
            {error ? (
              <p role="alert" className="error-text">
                {error}
              </p>
            ) : null}
            <button type="submit" disabled={isSubmitting}>
              {isSubmitting ? '登录中...' : '登录'}
            </button>
          </form>
        </section>
      </section>
    </div>
  );
}
