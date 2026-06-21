import { useEffect, useState } from 'react';
import { fetchDailyReviewLite } from '../api/client';
import type { DailyReviewLiteArtifactHealth, DailyReviewLiteResponse, DailyReviewLiteSectionStatus } from '../api/types';
import { ArtifactLinks } from '../components/daily-review-lite/ArtifactLinks';
import { ChecklistTable } from '../components/daily-review-lite/ChecklistTable';
import { SectionCard } from '../components/daily-review-lite/SectionCard';
import { StatusBanner } from '../components/daily-review-lite/StatusBanner';
import { StrategySummaryGrid } from '../components/daily-review-lite/StrategySummaryGrid';

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; payload: DailyReviewLiteResponse | null };

type DailyReviewLitePageProps = {
  initialTradeDate?: string;
};

export function DailyReviewLitePage({ initialTradeDate }: DailyReviewLitePageProps) {
  const [tradeDate, setTradeDate] = useState(() => resolveInitialTradeDate(initialTradeDate));
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

  return (
    <main className="daily-review-lite-page">
      <header className="daily-review-lite-header">
        <h1>Daily Review Lite</h1>
        <p>Structured read-only review of the Daily Review v1 report package</p>
      </header>
      <label className="daily-review-lite-date-field">
        <span>Trade Date</span>
        <input type="date" value={tradeDate} onChange={(event) => setTradeDate(event.target.value)} />
      </label>
      {loadState.status === 'ready' && loadState.payload !== null ? <StatusBanner payload={loadState.payload} /> : null}
      {renderPageBody(loadState)}
    </main>
  );
}

function renderPageBody(loadState: LoadState) {
  if (loadState.status === 'loading') {
    return renderStateMessage('Loading Daily Review Lite...');
  }

  if (loadState.status === 'error') {
    return renderStateMessage(`Failed to load Daily Review Lite: ${loadState.message}`);
  }

  if (loadState.payload === null) {
    return renderStateMessage('No data returned.');
  }

  return renderPageContent(loadState.payload);
}

function renderStateMessage(message: string) {
  return (
    <section className="daily-review-lite-message-card" aria-label="Daily Review Lite state">
      <p>{message}</p>
    </section>
  );
}

function renderPageContent(payload: DailyReviewLiteResponse) {
  if (payload.state === 'empty') {
    return renderStateMessage('No report found for selected date');
  }

  if (payload.state === 'failed') {
    return (
      <div className="daily-review-lite-sections">
        <section className="daily-review-lite-message-card" aria-label="Daily Review Lite state">
          <p>Package artifacts could not be read or parsed.</p>
        </section>
        {payload.artifacts.length > 0 ? (
          <SectionCard title="Artifacts" status={artifactStatus(payload)}>
            <ArtifactLinks artifacts={payload.artifacts} />
          </SectionCard>
        ) : null}
      </div>
    );
  }

  return (
    <div className="daily-review-lite-sections">
      <SectionCard
        title="Data Readiness"
        status={payload.sections.data_readiness.status}
        warnings={payload.sections.data_readiness.warnings}
      >
        <pre>{JSON.stringify(payload.sections.data_readiness.sources, null, 2)}</pre>
      </SectionCard>
      <SectionCard
        title="Market Review"
        status={payload.sections.market_review.status}
        warnings={payload.sections.market_review.warnings}
      >
        <pre>{JSON.stringify(payload.sections.market_review.payload, null, 2)}</pre>
      </SectionCard>
      <SectionCard title="Strategy Summaries" status={strategyStatus(payload)} warnings={[]}>
        <div className="daily-review-lite-section-grid">
          <StrategySummaryGrid strategySummaries={payload.sections.strategy_summaries} />
        </div>
      </SectionCard>
      <SectionCard
        title="Holding Review"
        status={payload.sections.holding_review.status}
        warnings={payload.sections.holding_review.warnings}
      >
        <pre>{JSON.stringify(payload.sections.holding_review.items, null, 2)}</pre>
      </SectionCard>
      <SectionCard
        title="Operator Plan"
        status={payload.sections.operator_plan.status}
        warnings={payload.sections.operator_plan.warnings}
      >
        <pre>{JSON.stringify(payload.sections.operator_plan.payload, null, 2)}</pre>
      </SectionCard>
      <SectionCard
        title="Next-day Checklist"
        status={payload.sections.next_day_checklist.status}
        warnings={payload.sections.next_day_checklist.warnings}
      >
        <ChecklistTable items={payload.sections.next_day_checklist.must_review_items} />
        <pre>{JSON.stringify(payload.sections.next_day_checklist.forbidden_actions, null, 2)}</pre>
        <pre>{JSON.stringify(payload.sections.next_day_checklist.data_warnings, null, 2)}</pre>
      </SectionCard>
      <SectionCard title="Artifacts" status={artifactStatus(payload)}>
        <ArtifactLinks artifacts={payload.artifacts} />
      </SectionCard>
    </div>
  );
}

function strategyStatus(payload: DailyReviewLiteResponse) {
  const statuses = Object.values(payload.sections.strategy_summaries).map((section) => section.status);
  const uniqueStatuses = new Set(statuses);
  if (uniqueStatuses.has('partial')) {
    return 'partial';
  }
  if (uniqueStatuses.size === 1 && uniqueStatuses.has('empty')) {
    return 'empty';
  }
  if (uniqueStatuses.size === 1 && uniqueStatuses.has('success')) {
    return 'success';
  }
  return 'partial';
}

function artifactStatus(payload: DailyReviewLiteResponse): DailyReviewLiteSectionStatus {
  if (payload.artifacts.length === 0) {
    return 'empty';
  }

  const health = payload.selected_run?.artifact_health;
  if (health && mapArtifactHealthToSectionStatus(health) === 'partial') {
    return 'partial';
  }

  return payload.artifacts.every((artifact) => artifact.available) ? 'success' : 'partial';
}

function mapArtifactHealthToSectionStatus(health: DailyReviewLiteArtifactHealth): DailyReviewLiteSectionStatus {
  return health === 'healthy' ? 'success' : 'partial';
}

function resolveInitialTradeDate(initialTradeDate?: string) {
  if (initialTradeDate) {
    return initialTradeDate;
  }

  const tradeDateParam = getTradeDateQueryParam();
  if (tradeDateParam) {
    return tradeDateParam;
  }

  return getDefaultTradeDateForToday();
}

function getTradeDateQueryParam() {
  if (typeof window === 'undefined') {
    return null;
  }

  const value = new URLSearchParams(window.location.search).get('trade_date');
  return value && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : null;
}

function getDefaultTradeDateForToday() {
  const candidate = new Date();
  candidate.setHours(0, 0, 0, 0);

  const dayOfWeek = candidate.getDay();
  if (dayOfWeek === 6) {
    candidate.setDate(candidate.getDate() - 1);
  } else if (dayOfWeek === 0) {
    candidate.setDate(candidate.getDate() - 2);
  }

  return formatLocalDate(candidate);
}

function formatLocalDate(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}
