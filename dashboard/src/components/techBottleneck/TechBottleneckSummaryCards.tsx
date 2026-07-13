import type { TechBottleneckReviewDecisionSummary, TechBottleneckReviewSummary } from '../../types/techBottleneckReview';

export function TechBottleneckSummaryCards({
  summary,
  decisionSummary
}: {
  summary: TechBottleneckReviewSummary;
  decisionSummary?: TechBottleneckReviewDecisionSummary | null;
}) {
  const reviewedCount = decisionSummary?.reviewed_count ?? 0;
  const pendingCount = decisionSummary?.pending_count ?? summary.frontend_dataset_count;

  return (
    <section className="stock-summary-strip compact" aria-label="科技卡脖子复盘指标">
      <span className="metric-chip">复盘全集 {summary.frontend_dataset_count}</span>
      <span className="metric-chip">待复盘 {pendingCount}</span>
      <span className="metric-chip">已复盘 {reviewedCount}</span>
      <span className="metric-chip">剩余缺口 {summary.remaining_evidence_gap_count}</span>
      {decisionSummary && reviewedCount > 0 ? (
        <>
          <span className="metric-chip">保留 {decisionSummary.keep_count}</span>
          <span className="metric-chip">暂缓 {decisionSummary.hold_count}</span>
          <span className="metric-chip">需更多证据 {decisionSummary.need_more_evidence_count}</span>
          <span className="metric-chip">降级 {decisionSummary.downgrade_count}</span>
          <span className="metric-chip">拒绝 {decisionSummary.reject_count}</span>
        </>
      ) : null}
    </section>
  );
}
