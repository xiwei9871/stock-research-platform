import { FormEvent, useState } from 'react';

type LoginViewProps = {
  error?: string | null;
  isSubmitting?: boolean;
  onSubmit: (identifier: string, password: string) => Promise<void>;
};

const pageStyle = {
  minHeight: '100vh',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '24px',
  boxSizing: 'border-box' as const
};

const panelStyle = {
  width: '100%',
  maxWidth: '420px',
  padding: '24px',
  border: '1px solid rgba(148, 163, 184, 0.35)',
  borderRadius: '16px',
  backgroundColor: '#ffffff',
  boxShadow: '0 18px 40px rgba(15, 23, 42, 0.08)'
};

const formStyle = {
  display: 'grid',
  gap: '16px'
};

const fieldStyle = {
  display: 'grid',
  gap: '6px'
};

const inputStyle = {
  width: '100%',
  padding: '10px 12px',
  border: '1px solid #cbd5e1',
  borderRadius: '10px',
  boxSizing: 'border-box' as const
};

const buttonStyle = {
  padding: '10px 14px',
  border: 'none',
  borderRadius: '10px',
  backgroundColor: '#0f172a',
  color: '#ffffff',
  cursor: 'pointer'
};

export function LoginView({ error = null, isSubmitting = false, onSubmit }: LoginViewProps) {
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSubmit(identifier, password);
  }

  return (
    <main style={pageStyle}>
      <section style={panelStyle}>
        <header>
          <h1>登录</h1>
        </header>
        <form onSubmit={handleSubmit} style={formStyle}>
          <div style={fieldStyle}>
              <label htmlFor="login-identifier">用户名或邮箱</label>
              <input
                id="login-identifier"
                name="identifier"
                value={identifier}
                onChange={(event) => setIdentifier(event.target.value)}
                autoComplete="username"
                style={inputStyle}
              />
          </div>
          <div style={fieldStyle}>
              <label htmlFor="login-password">密码</label>
              <input
                id="login-password"
                name="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                style={inputStyle}
              />
          </div>
          {error ? (
            <p role="alert" className="error-text">
              {error}
            </p>
          ) : null}
          <button type="submit" disabled={isSubmitting} style={buttonStyle}>
            {isSubmitting ? '登录中...' : '登录'}
          </button>
        </form>
      </section>
    </main>
  );
}
