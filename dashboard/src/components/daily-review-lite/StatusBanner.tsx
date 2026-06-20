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
    <section aria-label="Review status">
      <p>{sourceLabel}</p>
      <p>State: {payload.state}</p>
      {payload.selected_run?.run_id ? <p>{payload.selected_run.run_id}</p> : null}
      {payload.selected_run?.artifact_health ? (
        <p>Artifact health: {payload.selected_run.artifact_health}</p>
      ) : null}
      {payload.warnings.length > 0 ? (
        <ul aria-label="Warnings">
          {payload.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
