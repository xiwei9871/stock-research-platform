import { useEffect, useState } from 'react';
import { createMyReviewSession, fetchMyReviewSessions } from '../api/client';
import type { UserReviewSession } from '../api/types';

function getDefaultTradeDate() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function getErrorMessage(error: unknown) {
  if (typeof error === 'object' && error !== null && 'message' in error) {
    const message = (error as { message?: unknown }).message;
    if (typeof message === 'string' && message.length > 0) {
      return message;
    }
  }
  return '加载复盘失败';
}

export function MyReviewsView() {
  const [sessions, setSessions] = useState<UserReviewSession[]>([]);
  const [tradeDate, setTradeDate] = useState(getDefaultTradeDate);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadSessions() {
    setLoading(true);
    try {
      const nextSessions = await fetchMyReviewSessions();
      setSessions(nextSessions);
      setError(null);
    } catch (nextError: unknown) {
      setError(getErrorMessage(nextError));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadSessions();
  }, []);

  async function handleCreateSession() {
    setCreating(true);
    try {
      await createMyReviewSession({ trade_date: tradeDate, title: '盘后复盘' });
      await loadSessions();
    } catch (nextError: unknown) {
      setError(getErrorMessage(nextError));
    } finally {
      setCreating(false);
    }
  }

  return (
    <section className="view-shell">
      <header className="view-header">
        <div>
          <h1>我的复盘</h1>
          <p className="muted">按交易日创建并查看个人复盘。</p>
        </div>
      </header>

      <div className="inline-form">
        <label className="field-group" htmlFor="review-trade-date">
          <span>交易日</span>
          <input
            id="review-trade-date"
            name="trade_date"
            type="date"
            value={tradeDate}
            onChange={(event) => setTradeDate(event.target.value)}
          />
        </label>
        <button className="primary-button" type="button" disabled={creating} onClick={() => void handleCreateSession()}>
          {creating ? '创建中...' : '新建我的复盘'}
        </button>
      </div>

      {error ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="muted">加载复盘中...</p>
      ) : sessions.length === 0 ? (
        <p className="muted">暂无复盘记录。</p>
      ) : (
        <div className="entity-list">
          {sessions.map((session) => (
            <article key={session.id} className="entity-row">
              <div className="entity-copy">
                <strong>{session.title}</strong>
                <span>{session.trade_date}</span>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
