import type { ReactNode } from 'react';
import type { DailyReviewLiteSectionStatus } from '../../api/types';

type SectionCardProps = {
  title: string;
  status: DailyReviewLiteSectionStatus;
  warnings?: string[];
  headingLevel?: 2 | 3;
  children?: ReactNode;
};

export function SectionCard({
  title,
  status,
  warnings = [],
  headingLevel = 2,
  children
}: SectionCardProps) {
  const HeadingTag = headingLevel === 2 ? 'h2' : 'h3';

  return (
    <section aria-labelledby={toHeadingId(title)}>
      <header>
        <HeadingTag id={toHeadingId(title)}>{title}</HeadingTag>
        <p>Status: {status}</p>
      </header>
      {warnings.length > 0 ? (
        <>
          <p>Warnings</p>
          <ul>
            {warnings.map((warning, index) => (
              <li key={`${title}-${index}-${warning}`}>{warning}</li>
            ))}
          </ul>
        </>
      ) : null}
      {children}
    </section>
  );
}

function toHeadingId(title: string) {
  return `daily-review-lite-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
}
