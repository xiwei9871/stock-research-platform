import type { TechBottleneckReviewDecisionSummary, TechBottleneckReviewSummary } from '../../types/techBottleneckReview';

export function TechBottleneckSummaryCards({
  summary,
  decisionSummary
}: {
  summary: TechBottleneckReviewSummary;
  decisionSummary?: TechBottleneckReviewDecisionSummary | null;
}) {
  return (
    <section className="stock-summary-strip compact" aria-label="科技卡脖子复盘指标">
      <span className="metric-chip">复盘全集 {summary.frontend_dataset_count}</span>
      <span className="metric-chip">v5 已水合 {summary.v5_hydrated_count}</span>
      <span className="metric-chip">v7 提案 {summary.v7_proposal_new_count}</span>
      <span className="metric-chip">定向补证 {summary.v5_targeted_hydrated_count}</span>
      <span className="metric-chip">剩余缺口 {summary.remaining_evidence_gap_count}</span>
      <span className="metric-chip">证据行 {summary.evidence_index_row_count}</span>
      <span className="metric-chip">来源行 {summary.source_index_row_count}</span>
      <span className="metric-chip">used_for_signal {summary.used_for_signal_count}</span>
      <span className="metric-chip">used_for_admission {summary.used_for_admission_count}</span>
      {decisionSummary ? (
        <>
          <span className="metric-chip">已复盘 {decisionSummary.reviewed_count}</span>
          <span className="metric-chip">待复盘 {decisionSummary.pending_count}</span>
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
