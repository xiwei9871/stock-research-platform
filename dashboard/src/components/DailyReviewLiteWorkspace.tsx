import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchDailyReviewLite } from '../api/client';
import type { DailyReviewLitePayload } from '../api/types';

type DailyReviewLiteWorkspaceProps = {
  initialTradeDate?: string;
};

function todayDate() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    ready: '就绪',
    partial: '部分就绪',
    empty: '暂无产物',
    failed: '失败'
  };
  return labels[status] ?? status;
}

function statusClass(status: string) {
  if (status === 'ready') return 'success';
  if (status === 'failed') return 'warning';
  if (status === 'partial') return 'neutral';
  return 'neutral';
}

export function DailyReviewLiteWorkspace({ initialTradeDate }: DailyReviewLiteWorkspaceProps) {
  const [tradeDate, setTradeDate] = useState(initialTradeDate || todayDate());
  const [payload, setPayload] = useState<DailyReviewLitePayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const loadReview = useCallback(async (nextTradeDate: string) => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setLoading(true);
    setError(null);
    try {
      const nextPayload = await fetchDailyReviewLite({ tradeDate: nextTradeDate });
      if (requestIdRef.current === requestId) {
        setPayload(nextPayload);
      }
    } catch (caught) {
      if (requestIdRef.current === requestId) {
        setError(caught instanceof Error ? caught.message : String(caught));
        setPayload(null);
      }
    } finally {
      if (requestIdRef.current === requestId) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadReview(tradeDate);
    return () => {
      requestIdRef.current += 1;
    };
  }, [loadReview, tradeDate]);

  return (
    <section className="workspace-stack daily-review-lite" aria-label="每日复盘">
      <header className="workspace-header">
        <h1>每日复盘</h1>
        <p className="muted">按固定结构查看每天的 operator review：数据、市场、策略、持仓、计划和产物。</p>
      </header>

      <section className="workspace-band daily-review-toolbar" aria-label="每日复盘控制栏">
        <label>
          复盘日期
          <input
            aria-label="daily review trade date"
            type="date"
            value={tradeDate}
            onChange={(event) => setTradeDate(event.target.value)}
          />
        </label>
        <div>
          <span className="muted">页面状态</span>
          <strong>{payload ? statusLabel(payload.status) : loading ? '加载中' : '-'}</strong>
        </div>
        <div>
          <span className="muted">数据来源</span>
          <strong>{payload?.run.source || '-'}</strong>
        </div>
        <div>
          <span className="muted">Run</span>
          <strong>{payload?.run.run_id || 'no run selected'}</strong>
        </div>
      </section>

      {loading ? <p className="muted">正在加载每日复盘...</p> : null}
      {error ? <p className="error-text">{error}</p> : null}

      {payload?.warnings.length ? (
        <section className="workspace-band" aria-label="每日复盘提醒">
          {payload.warnings.map((warning) => (
            <p className="error-text" key={warning}>
              {warning}
            </p>
          ))}
        </section>
      ) : null}

      {payload ? (
        <section className="daily-review-section-grid" aria-label="每日复盘报告结构">
          {payload.sections.map((section) => (
            <article className="workspace-band daily-review-section" key={section.key}>
              <div className="section-heading">
                <h2>{section.title}</h2>
                <span className={`status-chip ${statusClass(section.status)}`}>{statusLabel(section.status)}</span>
              </div>
              {section.items.length > 0 ? (
                <dl className="daily-review-item-grid">
                  {section.items.map((item) => (
                    <div key={`${section.key}:${item.label}`}>
                      <dt>{item.label}</dt>
                      <dd>{item.value || '-'}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="muted">暂无该部分复盘内容。</p>
              )}
            </article>
          ))}
        </section>
      ) : null}
    </section>
  );
}
