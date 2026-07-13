import { useState } from 'react';
import type {
  TechBottleneckReviewEvidence,
  TechBottleneckReviewDecisionRecord,
  TechBottleneckReviewSource,
  TechBottleneckReviewStock,
  TechBottleneckReviewerDecision
} from '../../types/techBottleneckReview';
import { TechBottleneckSourcePanel } from './TechBottleneckSourcePanel';

type Props = {
  stock: TechBottleneckReviewStock | null;
  evidence: TechBottleneckReviewEvidence[];
  sources: TechBottleneckReviewSource[];
  onRecordManualDecision?: (decision: TechBottleneckReviewerDecision, reviewComment: string, evidenceChecked: boolean) => Promise<void>;
  decisionMessage?: string;
  decisionHistory?: TechBottleneckReviewDecisionRecord[];
};

function groupedEvidence(evidence: TechBottleneckReviewEvidence[]) {
  return evidence.reduce<Record<string, TechBottleneckReviewEvidence[]>>((groups, item) => {
    const key = item.evidence_claim_type || 'uncategorized';
    groups[key] = [...(groups[key] ?? []), item];
    return groups;
  }, {});
}

const DECISIONS: TechBottleneckReviewerDecision[] = ['keep', 'hold', 'need_more_evidence', 'downgrade', 'reject'];

const DECISION_LABELS: Record<TechBottleneckReviewerDecision, string> = {
  keep: '保留',
  hold: '暂缓',
  need_more_evidence: '需更多证据',
  downgrade: '降级',
  reject: '拒绝'
};

const RUBRIC_ITEMS = [
  '硬科技属性',
  '瓶颈 / 卡点角色',
  '业务相关性',
  '一手来源证据',
  '页级证据可核验',
  '价值捕获能力',
  '绕开 / 替代风险',
  '反证 / 概念污染风险'
];

function displayValue(value: unknown, fallback = '缺失') {
  return String(value || fallback);
}

function decisionLabel(decision?: string | null) {
  if (!decision) return '待复盘';
  return DECISION_LABELS[decision as TechBottleneckReviewerDecision] ?? decision;
}

export function TechBottleneckEvidencePanel({
  stock,
  evidence,
  sources,
  onRecordManualDecision,
  decisionMessage,
  decisionHistory = []
}: Props) {
  const [reviewComment, setReviewComment] = useState('');
  const [evidenceChecked, setEvidenceChecked] = useState(false);
  const hasWriteToken =
    typeof window !== 'undefined' && Boolean(window.localStorage.getItem('dashboardWriteToken'));
  if (!stock) {
    return (
      <section className="workspace-band" aria-label="科技卡脖子证据占位">
        <h2>证据详情</h2>
        <p className="muted">请选择一只股票查看页级证据和来源记录。</p>
      </section>
    );
  }

  const groups = groupedEvidence(evidence);

  return (
    <section className="workspace-band" role="region" aria-label={`${stock.stock_code} 证据和来源详情`}>
      <h2>
        {stock.stock_code} {stock.stock_name}
      </h2>
      <div className="stock-secondary-grid">
        <p>
          <strong>最强一手证据</strong>
          <br />
          {displayValue(stock.strongest_primary_source_claim)}
        </p>
        <p>
          <strong>最弱 / 风险证据</strong>
          <br />
          {displayValue(stock.weakest_or_riskiest_claim)}
        </p>
        <p>
          <strong>复盘证据摘要</strong>
          <br />
          {displayValue(stock.evidence_summary_for_review)}
        </p>
        <p>
          <strong>下一步一手来源核查</strong>
          <br />
          {displayValue(stock.next_primary_source_to_check)}
        </p>
      </div>
      <h3>页级证据</h3>
      {evidence.length ? (
        Object.entries(groups).map(([claimType, rows]) => (
          <section key={claimType} className="workspace-stack" aria-label={`${claimType} 证据`}>
            <h4>{claimType}</h4>
            {rows.map((item, index) => (
              <article className="workspace-band compact" key={`${item.source_file}:${item.page}:${index}`}>
                <p>
                  <strong>{item.source_title || '缺失来源标题'}</strong> · {item.source_type || '缺失来源类型'} · 页码{' '}
                  {item.page || '缺失'}
                </p>
                {item.citation_quality !== 'page_level' ? (
                  <p className="muted">警告：citation_quality 为 {item.citation_quality || '缺失'}</p>
                ) : null}
                <p>{item.evidence_text || '缺失证据文本'}</p>
              </article>
            ))}
          </section>
        ))
      ) : (
        <p className="muted">该股票暂无页级证据记录。</p>
      )}
      <h3>来源</h3>
      <TechBottleneckSourcePanel sources={sources} />
      <section className="workspace-band compact" role="region" aria-label={`${stock.stock_code} 人工复盘决策`}>
        <h3>人工复盘决策 overlay</h3>
        <p className="muted">
          分数只用于排序和提示；人工结论写入独立 overlay ledger，不用于 signal、admission 或 frozen quality pool 生成。
        </p>
        <p className="status-pill">写入状态：{hasWriteToken ? '可写 / 已配置令牌' : '只读 / 未配置令牌'}</p>
        <div className="stock-secondary-grid" aria-label="人工复盘判断点">
          {RUBRIC_ITEMS.map((item) => (
            <span key={item} className="metric-chip">
              {item}
            </span>
          ))}
        </div>
        <p>
          当前结论：{decisionLabel(stock.reviewer_decision)} · 复盘人：{stock.reviewer || 'operator'} · 复盘时间：
          {stock.reviewed_at || '空'}
        </p>
        <label>
          已核验证据
          <input type="checkbox" checked={evidenceChecked} onChange={(event) => setEvidenceChecked(event.target.checked)} />
        </label>
        <label>
          复盘备注
          <textarea value={reviewComment} onChange={(event) => setReviewComment(event.target.value)} />
        </label>
        <div className="tech-bottleneck-tabs" aria-label="人工复盘决策动作">
          {DECISIONS.map((decision) => (
            <button
              key={decision}
              type="button"
              onClick={() => {
                void onRecordManualDecision?.(decision, reviewComment, evidenceChecked);
              }}
            >
              {DECISION_LABELS[decision]}
            </button>
          ))}
        </div>
        {decisionMessage ? <p className="status-pill">{decisionMessage}</p> : null}
        <h4>决策历史</h4>
        {decisionHistory.length ? (
          decisionHistory.slice(0, 5).map((item) => (
            <p key={item.decision_id}>
              {item.recorded_at} · {decisionLabel(item.reviewer_decision)} · {item.reviewer} · {item.review_comment}
            </p>
          ))
        ) : (
          <p className="muted">该股票暂无人工 overlay 决策记录。</p>
        )}
      </section>
    </section>
  );
}
