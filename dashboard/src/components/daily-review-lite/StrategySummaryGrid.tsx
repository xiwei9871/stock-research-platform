import type { DailyReviewLiteSections } from '../../api/types';
import { SectionCard } from './SectionCard';

type StrategySummaryGridProps = {
  strategySummaries: DailyReviewLiteSections['strategy_summaries'];
};

const STRATEGY_CARDS = [
  { key: 'lhb', label: 'LHB' },
  { key: 'mid_trend', label: 'Mid Trend' },
  { key: 'technical_bottleneck', label: 'Technical Bottleneck' }
] as const;

export function StrategySummaryGrid({ strategySummaries }: StrategySummaryGridProps) {
  return (
    <>
      {STRATEGY_CARDS.map(({ key, label }) => {
        const section = strategySummaries[key];
        return (
          <SectionCard
            key={key}
            title={label}
            status={section.status}
            warnings={section.warnings}
            headingLevel={3}
          >
            <pre>{JSON.stringify(section.summary, null, 2)}</pre>
            <pre>{JSON.stringify(section.top_items, null, 2)}</pre>
          </SectionCard>
        );
      })}
    </>
  );
}
