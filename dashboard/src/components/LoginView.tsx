type LoginViewProps = {
  error: string;
  onSubmit: (username: string, password: string) => void;
};

export function LoginView({ error, onSubmit }: LoginViewProps) {
  return (
    <main className="login-shell">
      <section className="login-panel">
        <h1>登录</h1>
        <form
          className="login-form"
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            onSubmit(String(form.get('username') ?? ''), String(form.get('password') ?? ''));
          }}
        >
          <label>
            用户名
            <input name="username" autoComplete="username" />
          </label>
          <label>
            密码
            <input name="password" type="password" autoComplete="current-password" />
          </label>
          {error ? <p role="alert">{error}</p> : null}
          <button type="submit">登录</button>
        </form>
      </section>
    </main>
  );
}
