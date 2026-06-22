import { FormEvent, useEffect, useState } from 'react';
import { createMyWatchlistItem, fetchMyWatchlist, removeMyWatchlistItem } from '../api/client';
import type { UserWatchlistItem } from '../api/types';

function getErrorMessage(error: unknown) {
  if (typeof error === 'object' && error !== null && 'message' in error) {
    const message = (error as { message?: unknown }).message;
    if (typeof message === 'string' && message.length > 0) {
      return message;
    }
  }
  return '加载自选失败';
}

export function MyWatchlistView() {
  const [items, setItems] = useState<UserWatchlistItem[]>([]);
  const [assetId, setAssetId] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadItems() {
    setLoading(true);
    try {
      const nextItems = await fetchMyWatchlist();
      setItems(nextItems);
      setError(null);
    } catch (nextError: unknown) {
      setError(getErrorMessage(nextError));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadItems();
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextAssetId = assetId.trim();
    if (!nextAssetId) {
      return;
    }

    setSaving(true);
    try {
      await createMyWatchlistItem({ asset_id: nextAssetId });
      setAssetId('');
      await loadItems();
    } catch (nextError: unknown) {
      setError(getErrorMessage(nextError));
    } finally {
      setSaving(false);
    }
  }

  async function handleRemove(nextAssetId: string) {
    setSaving(true);
    try {
      await removeMyWatchlistItem(nextAssetId);
      await loadItems();
    } catch (nextError: unknown) {
      setError(getErrorMessage(nextError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="view-shell">
      <header className="view-header">
        <div>
          <h1>我的观察池</h1>
          <p className="muted">管理个人关注资产。</p>
        </div>
      </header>

      <form className="inline-form" onSubmit={handleSubmit}>
        <label className="field-group" htmlFor="watchlist-asset-id">
          <span>资产代码</span>
          <input
            id="watchlist-asset-id"
            name="asset_id"
            value={assetId}
            onChange={(event) => setAssetId(event.target.value)}
            placeholder="000001.SZ"
          />
        </label>
        <button className="primary-button" type="submit" disabled={saving}>
          {saving ? '提交中...' : '添加到观察池'}
        </button>
      </form>

      {error ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="muted">加载观察池中...</p>
      ) : items.length === 0 ? (
        <p className="muted">暂无观察资产。</p>
      ) : (
        <div className="entity-list">
          {items.map((item) => (
            <article key={item.id} className="entity-row" data-testid={`watchlist-item-${item.asset_id}`}>
              <div className="entity-copy">
                <strong>{item.asset_id}</strong>
                <span className="muted">添加日期 {item.trade_date_added}</span>
              </div>
              <button
                className="secondary-button"
                type="button"
                disabled={saving}
                onClick={() => {
                  void handleRemove(item.asset_id);
                }}
              >
                移除
              </button>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
