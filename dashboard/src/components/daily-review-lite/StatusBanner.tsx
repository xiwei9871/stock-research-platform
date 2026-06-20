import type { DailyReviewLiteResponse } from '../../api/types';

type StatusBannerProps = {
  payload: DailyReviewLiteResponse;
};

export function StatusBanner({ payload }: StatusBannerProps) {
  const sourceLabel =
    payload.selected_run?.source === 'fallback'
      ? 'Loaded from fallback package scan'
      : 'Loaded from report.run';

  return (
    <section className="daily-review-lite-banner" aria-label="Review status">
      <p>{sourceLabel}</p>
      <p>State: {payload.state}</p>
      {payload.selected_run?.run_id ? <p>{payload.selected_run.run_id}</p> : null}
      {payload.selected_run?.artifact_health ? (
        <p>Artifact health: {payload.selected_run.artifact_health}</p>
      ) : null}
      {payload.warnings.length > 0 ? (
        <ul aria-label="Warnings">
          {payload.warnings.map((warning, index) => (
            <li key={`${warning}-${index}`}>{warning}</li>
          ))}
        </ul>
      ) : null}
      {payload.missing_sources.length > 0 ? (
        <ul aria-label="Missing sources">
          {payload.missing_sources.map((missingSource, index) => (
            <li
              key={`${missingSource.source_key ?? 'unknown'}-${missingSource.summary ?? 'no-summary'}-${index}`}
            >
              {missingSource.source_key ? <p>{missingSource.source_key}</p> : null}
              {missingSource.summary ? <p>{missingSource.summary}</p> : null}
              {missingSource.affected_sections.length > 0 ? (
                <p>Affected sections: {missingSource.affected_sections.join(', ')}</p>
              ) : null}
              {missingSource.confidence_impact ? (
                <p>Confidence impact: {missingSource.confidence_impact}</p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
