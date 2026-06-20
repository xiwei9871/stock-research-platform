import { useEffect, useState } from 'react';
import { fetchDailyReviewLite } from '../api/client';
import type { DailyReviewLiteResponse } from '../api/types';
import { StatusBanner } from '../components/daily-review-lite/StatusBanner';

const DEFAULT_TRADE_DATE = '2026-06-20';

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; payload: DailyReviewLiteResponse | null };

export function DailyReviewLitePage() {
  const [tradeDate, setTradeDate] = useState(DEFAULT_TRADE_DATE);
  const [loadState, setLoadState] = useState<LoadState>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;

    setLoadState({ status: 'loading' });

    fetchDailyReviewLite(tradeDate, undefined)
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setLoadState({ status: 'ready', payload: payload ?? null });
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        const message = error instanceof Error ? error.message : String(error);
        setLoadState({ status: 'error', message });
      });

    return () => {
      cancelled = true;
    };
  }, [tradeDate]);

  if (loadState.status === 'loading') {
    return <p>Loading Daily Review Lite...</p>;
  }

  if (loadState.status === 'error') {
    return <p>Failed to load Daily Review Lite: {loadState.message}</p>;
  }

  if (loadState.payload === null) {
    return <p>No data returned.</p>;
  }

  return (
    <main>
      <header>
        <h1>Daily Review Lite</h1>
        <p>Structured read-only review of the Daily Review v1 report package</p>
      </header>
      <label>
        Trade Date
        <input type="date" value={tradeDate} onChange={(event) => setTradeDate(event.target.value)} />
      </label>
      <StatusBanner payload={loadState.payload} />
    </main>
  );
}
