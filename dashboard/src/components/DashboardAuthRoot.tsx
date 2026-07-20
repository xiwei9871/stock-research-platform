import { useEffect, useRef, useState } from 'react';
import { DASHBOARD_AUTH_EXPIRED_EVENT, fetchCurrentUser, loginDashboardUser, logoutDashboardUser } from '../api/client';
import type { CurrentUser } from '../api/types';
import { AppShell } from './AppShell';
import { LoginView } from './LoginView';

export function DashboardAuthRoot() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [loginPending, setLoginPending] = useState(false);
  const [logoutError, setLogoutError] = useState('');
  const [logoutPending, setLogoutPending] = useState(false);
  const loginInFlight = useRef(false);
  const logoutInFlight = useRef(false);
  const authGeneration = useRef(0);

  useEffect(() => {
    let cancelled = false;
    const generation = authGeneration.current;
    const handleAuthExpired = () => {
      if (!cancelled) {
        authGeneration.current += 1;
        setUser(null);
        setError('');
        setLoginPending(false);
        setLogoutError('');
        setLogoutPending(false);
        loginInFlight.current = false;
        logoutInFlight.current = false;
        setLoading(false);
      }
    };

    window.addEventListener(DASHBOARD_AUTH_EXPIRED_EVENT, handleAuthExpired);
    fetchCurrentUser()
      .then((payload) => {
        if (!cancelled && generation === authGeneration.current) setUser(payload.user);
      })
      .catch(() => {
        if (!cancelled && generation === authGeneration.current) setUser(null);
      })
      .finally(() => {
        if (!cancelled && generation === authGeneration.current) setLoading(false);
      });
    return () => {
      cancelled = true;
      window.removeEventListener(DASHBOARD_AUTH_EXPIRED_EVENT, handleAuthExpired);
    };
  }, []);

  if (loading) {
    return <main className="login-shell">加载中</main>;
  }

  if (!user) {
    return (
      <LoginView
        error={error}
        pending={loginPending}
        onSubmit={(username, password) => {
          if (loginInFlight.current) return;

          loginInFlight.current = true;
          const generation = authGeneration.current + 1;
          authGeneration.current = generation;
          setError('');
          setLoginPending(true);
          loginDashboardUser({ username, password })
            .then((payload) => {
              if (generation === authGeneration.current) setUser(payload.user);
            })
            .catch((err) => {
              if (generation === authGeneration.current) {
                setError(`登录失败：${err instanceof Error ? err.message : 'unknown'}`);
              }
            })
            .finally(() => {
              if (generation === authGeneration.current) {
                loginInFlight.current = false;
                setLoginPending(false);
              }
            });
        }}
      />
    );
  }

  const handleLogout = () => {
    if (logoutInFlight.current) return;

    logoutInFlight.current = true;
    const generation = authGeneration.current + 1;
    authGeneration.current = generation;
    setLogoutError('');
    setLogoutPending(true);
    logoutDashboardUser()
      .then(() => {
        if (generation === authGeneration.current) {
          setLogoutError('');
          setUser(null);
        }
      })
      .catch((err) => {
        if (generation === authGeneration.current) {
          setLogoutError(`退出登录失败：${err instanceof Error ? err.message : 'unknown'}`);
        }
      })
      .finally(() => {
        if (generation === authGeneration.current) {
          logoutInFlight.current = false;
          setLogoutPending(false);
        }
      });
  };

  return (
    <AppShell
      currentUser={user}
      onLogout={handleLogout}
      logoutPending={logoutPending}
      logoutError={logoutError}
    />
  );
}
