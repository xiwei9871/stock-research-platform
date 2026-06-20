import { useEffect, useState } from 'react';
import { fetchDailyReviewLite } from '../api/client';
import type { DailyReviewLiteResponse } from '../api/types';
import { ArtifactLinks } from '../components/daily-review-lite/ArtifactLinks';
import { ChecklistTable } from '../components/daily-review-lite/ChecklistTable';
import { SectionCard } from '../components/daily-review-lite/SectionCard';
import { StatusBanner } from '../components/daily-review-lite/StatusBanner';
import { StrategySummaryGrid } from '../components/daily-review-lite/StrategySummaryGrid';

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
      <SectionCard
        title="Data Readiness"
        status={loadState.payload.sections.data_readiness.status}
        warnings={loadState.payload.sections.data_readiness.warnings}
      >
        <pre>{JSON.stringify(loadState.payload.sections.data_readiness.sources, null, 2)}</pre>
      </SectionCard>
      <SectionCard
        title="Market Review"
        status={loadState.payload.sections.market_review.status}
        warnings={loadState.payload.sections.market_review.warnings}
      >
        <pre>{JSON.stringify(loadState.payload.sections.market_review.payload, null, 2)}</pre>
      </SectionCard>
      <SectionCard title="Strategy Summaries" status={strategyStatus(loadState.payload)} warnings={[]}>
        <StrategySummaryGrid strategySummaries={loadState.payload.sections.strategy_summaries} />
      </SectionCard>
      <SectionCard
        title="Holding Review"
        status={loadState.payload.sections.holding_review.status}
        warnings={loadState.payload.sections.holding_review.warnings}
      >
        <pre>{JSON.stringify(loadState.payload.sections.holding_review.items, null, 2)}</pre>
      </SectionCard>
      <SectionCard
        title="Operator Plan"
        status={loadState.payload.sections.operator_plan.status}
        warnings={loadState.payload.sections.operator_plan.warnings}
      >
        <pre>{JSON.stringify(loadState.payload.sections.operator_plan.payload, null, 2)}</pre>
      </SectionCard>
      <SectionCard
        title="Next-day Checklist"
        status={loadState.payload.sections.next_day_checklist.status}
        warnings={loadState.payload.sections.next_day_checklist.warnings}
      >
        <ChecklistTable items={loadState.payload.sections.next_day_checklist.must_review_items} />
        <pre>{JSON.stringify(loadState.payload.sections.next_day_checklist.forbidden_actions, null, 2)}</pre>
        <pre>{JSON.stringify(loadState.payload.sections.next_day_checklist.data_warnings, null, 2)}</pre>
      </SectionCard>
      <SectionCard title="Artifacts" status={loadState.payload.state === 'partial' ? 'partial' : 'success'}>
        <ArtifactLinks artifacts={loadState.payload.artifacts} />
      </SectionCard>
    </main>
  );
}

function strategyStatus(payload: DailyReviewLiteResponse) {
  const statuses = Object.values(payload.sections.strategy_summaries).map((section) => section.status);
  if (statuses.includes('partial')) {
    return 'partial';
  }
  if (statuses.every((status) => status === 'empty')) {
    return 'empty';
  }
  return 'success';
}
