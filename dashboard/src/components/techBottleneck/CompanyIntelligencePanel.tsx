import { useEffect, useMemo, useState } from 'react';
import {
  companyIntelligenceMarkdownUrl,
  fetchCompanyIntelligenceDossier,
  recordCompanyIntelligenceReview
} from '../../api/companyIntelligence';
import type {
  CompanyIntelligenceDossier,
  CompanyIntelligenceEvidence
} from '../../types/companyIntelligence';

type Props = {
  stockCode: string;
};

const DIMENSION_ORDER = [
  'tech_moat',
  'chain_position',
  'commercialization',
  'competitive_edge',
  'financial_realization',
  'risk_counter'
];

const VERDICT_LABELS: Record<string, string> = {
  confirmed: '已证实',
  partially_supported: '部分支持',
  contested: '正反冲突',
  contradicted: '存在反证',
  needs_evidence: '需补证据',
  unknown: '未知'
};

const DIRECTION_LABELS: Record<string, string> = {
  support: '支持',
  refute: '反证',
  unclear: '不明确'
};

const REVIEW_STATUSES = ['accepted', 'disagreed', 'needs_more_evidence', 'rejected'];

function verdictLabel(verdict: string) {
  return VERDICT_LABELS[verdict] ?? verdict;
}

function evidenceTimestamp(item: CompanyIntelligenceEvidence) {
  const stamps = [item.published_at, item.available_at, item.ingested_at].filter(Boolean);
  return stamps.length ? stamps.join(' / ') : '时间未知';
}

function EvidenceRow({ item }: { item: CompanyIntelligenceEvidence }) {
  return (
    <li className="ci-evidence-row" data-direction={item.direction ?? 'unclear'}>
      <span className="ci-evidence-direction">{DIRECTION_LABELS[item.direction ?? ''] ?? item.direction}</span>
      <span className="ci-evidence-excerpt">{item.excerpt}</span>
      <span className="ci-evidence-meta muted">
        {item.source_type ?? item.source_id} · {item.page_or_section || '页码缺失'} · {evidenceTimestamp(item)}
      </span>
    </li>
  );
}

export function CompanyIntelligencePanel({ stockCode }: Props) {
  const [dossier, setDossier] = useState<CompanyIntelligenceDossier | null>(null);
  const [error, setError] = useState('');
  const [openDimension, setOpenDimension] = useState<string>('');
  const [reviewClaimId, setReviewClaimId] = useState('');
  const [reviewStatus, setReviewStatus] = useState(REVIEW_STATUSES[0]);
  const [reviewComment, setReviewComment] = useState('');
  const [reviewMessage, setReviewMessage] = useState('');

  useEffect(() => {
    if (!stockCode) {
      setDossier(null);
      return;
    }
    let cancelled = false;
    setError('');
    setDossier(null);
    setOpenDimension('');
    setReviewMessage('');
    fetchCompanyIntelligenceDossier(stockCode)
      .then((payload) => {
        if (!cancelled) {
          setDossier(payload);
          setReviewClaimId(payload.claims?.[0]?.claim_id ?? '');
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [stockCode]);

  const evidenceByDimension = useMemo(() => {
    const groups: Record<string, CompanyIntelligenceEvidence[]> = {};
    (dossier?.evidence_matrix ?? []).forEach((item) => {
      const key = item.dimension || 'other';
      groups[key] = [...(groups[key] ?? []), item];
    });
    return groups;
  }, [dossier]);

  async function submitReview() {
    if (!stockCode || !reviewClaimId || !reviewComment.trim()) return;
    setReviewMessage('');
    try {
      await recordCompanyIntelligenceReview(stockCode, {
        claim_id: reviewClaimId,
        review_status: reviewStatus,
        reviewer: 'operator',
        comment: reviewComment.trim()
      });
      const refreshed = await fetchCompanyIntelligenceDossier(stockCode);
      setDossier(refreshed);
      setReviewComment('');
      setReviewMessage('复核意见已记录');
    } catch (err) {
      setReviewMessage(err instanceof Error ? err.message : '记录失败');
    }
  }

  if (!stockCode) return null;

  return (
    <section className="workspace-band company-intelligence-panel" aria-label="企业研究画像">
      <header className="workspace-header">
        <div>
          <h2>企业研究画像 {dossier ? `${dossier.company_name} ${dossier.company_code}` : stockCode}</h2>
          <p className="muted">
            research-only 六维竞争力分析。结论可追溯至页级证据；不足处显式标记 UNKNOWN / NEEDS_EVIDENCE。
          </p>
        </div>
        {dossier ? (
          <span className="status-pill" data-verdict={dossier.conclusion?.overall_verdict}>
            {verdictLabel(dossier.conclusion?.overall_verdict ?? '')}
          </span>
        ) : null}
      </header>

      {error ? <p className="muted">暂无该代码的企业研究画像（{error}）</p> : null}

      {dossier ? (
        <>
          <div className="ci-meta muted">
            研究截止 {dossier.as_of} · 代码版本 {dossier.input_snapshot?.code_sha ?? '未知'} · 证据集指纹{' '}
            {String(dossier.input_snapshot?.evidence_set_sha256 ?? '').slice(0, 12) || '未知'} ·{' '}
            <a href={companyIntelligenceMarkdownUrl(stockCode)} target="_blank" rel="noreferrer">
              导出 Markdown
            </a>
          </div>

          <div className="ci-dimension-grid">
            {DIMENSION_ORDER.map((key) => {
              const dim = dossier.dimensions[key];
              if (!dim) return null;
              const missing = dim.missing_checklist_items ?? [];
              const expanded = openDimension === key;
              return (
                <article key={key} className="ci-dimension-card" data-verdict={dim.verdict}>
                  <header>
                    <strong>{dim.label ?? key}</strong>
                    <span className="status-pill">{verdictLabel(dim.verdict)}</span>
                  </header>
                  <p className="muted">
                    置信度 {dim.confidence.toFixed(2)} · 支持 {dim.support_count} / 反证 {dim.refute_count} / 不明确{' '}
                    {dim.unclear_count ?? 0}
                  </p>
                  {missing.length ? <p className="ci-missing">缺失项: {missing.join('、')}</p> : null}
                  <button type="button" className="link-button" onClick={() => setOpenDimension(expanded ? '' : key)}>
                    {expanded ? '收起证据' : `展开证据 (${(evidenceByDimension[key] ?? []).length})`}
                  </button>
                  {expanded ? (
                    <ul className="ci-evidence-list">
                      {(evidenceByDimension[key] ?? []).map((item) => (
                        <EvidenceRow key={item.evidence_id} item={item} />
                      ))}
                      {(evidenceByDimension[key] ?? []).length === 0 ? <li className="muted">无可用证据</li> : null}
                    </ul>
                  ) : null}
                </article>
              );
            })}
          </div>

          {dossier.claims?.length ? (
            <details className="ci-claims">
              <summary>关键论点矩阵 ({dossier.claims.length})</summary>
              <ul>
                {dossier.claims.map((claim) => (
                  <li key={claim.claim_id}>
                    <code>{claim.claim_id}</code> [{claim.dimension}] {claim.claim_text}
                    <span className="muted">
                      {' '}
                      支持 {claim.support_count ?? 0} / 反证 {claim.refute_count ?? 0} · {claim.review_status}
                    </span>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}

          {dossier.research_gaps?.length ? (
            <details className="ci-gaps">
              <summary>研究缺口 ({dossier.research_gaps.length})</summary>
              <ul>
                {dossier.research_gaps.map((gap, index) => (
                  <li key={`${gap.dimension}-${index}`}>
                    [{gap.priority}] {gap.dimension} → {gap.missing_item}
                    <span className="muted">（{gap.reason}）</span>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}

          <details className="ci-review">
            <summary>人工复核 / 记录不同意见</summary>
            <div className="ci-review-form">
              <label>
                论点
                <select value={reviewClaimId} onChange={(event) => setReviewClaimId(event.target.value)}>
                  {(dossier.claims ?? []).map((claim) => (
                    <option key={claim.claim_id} value={claim.claim_id}>
                      {claim.claim_id}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                复核结论
                <select value={reviewStatus} onChange={(event) => setReviewStatus(event.target.value)}>
                  {REVIEW_STATUSES.map((status) => (
                    <option key={status} value={status}>
                      {status}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                意见
                <textarea value={reviewComment} onChange={(event) => setReviewComment(event.target.value)} rows={2} />
              </label>
              <button type="button" onClick={submitReview} disabled={!reviewClaimId || !reviewComment.trim()}>
                提交复核
              </button>
              {reviewMessage ? <p className="muted">{reviewMessage}</p> : null}
            </div>
            {dossier.reviews?.length ? (
              <ul className="ci-review-log">
                {dossier.reviews.map((item, index) => (
                  <li key={`${item.claim_id}-${index}`}>
                    [{item.review_status}] {item.claim_id} — {item.comment}
                    <span className="muted">（{item.reviewer} · {item.recorded_at}）</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </details>

          <p className="muted ci-guardrail-note">
            research_only={String(dossier.guardrails?.research_only)} · used_for_signal=
            {String(dossier.guardrails?.used_for_signal)} · used_for_admission=
            {String(dossier.guardrails?.used_for_admission)} · price_inputs_used=
            {String(dossier.guardrails?.price_inputs_used)}
          </p>
        </>
      ) : null}
    </section>
  );
}
