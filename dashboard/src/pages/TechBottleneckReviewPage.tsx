import { useEffect, useMemo, useState } from 'react';
import {
  createTechBottleneckReviewUniverseDecision,
  fetchTechBottleneckReviewUniverseEvidence,
  fetchTechBottleneckReviewUniverseDecisions,
  fetchTechBottleneckReviewUniverseDecisionSummary,
  fetchTechBottleneckReviewUniverseFilterOptions,
  fetchTechBottleneckReviewUniverseSources,
  fetchTechBottleneckReviewUniverseStocks,
  fetchTechBottleneckReviewUniverseSummary
} from '../api/techBottleneckReview';
import {
  techBottleneckWorkbenchAdjacentWatchlist,
  techBottleneckWorkbenchCoreCandidates,
  techBottleneckWorkbenchEvidenceBackfillQueue,
  techBottleneckWorkbenchRejectedCandidates
} from '../features/techBottleneckWatchlistReview/techBottleneckCandidateUniverseData';
import { TechBottleneckEvidencePanel } from '../components/techBottleneck/TechBottleneckEvidencePanel';
import {
  EMPTY_TECH_BOTTLENECK_REVIEW_FILTERS,
  TechBottleneckFilterBar,
  type TechBottleneckReadableFilterOptions,
  type TechBottleneckReviewFilters
} from '../components/techBottleneck/TechBottleneckFilterBar';
import { TechBottleneckReviewTable } from '../components/techBottleneck/TechBottleneckReviewTable';
import { TechBottleneckSummaryCards } from '../components/techBottleneck/TechBottleneckSummaryCards';
import type {
  TechBottleneckReviewEvidence,
  TechBottleneckReviewDecisionSummary,
  TechBottleneckReviewDecisionRecord,
  TechBottleneckReviewSource,
  TechBottleneckReviewStock,
  TechBottleneckReviewSummary,
  TechBottleneckReviewerDecision
} from '../types/techBottleneckReview';

type Props = {
  onOpenStock?: (stock: TechBottleneckReviewStock) => void;
};

const LEGACY_CANDIDATE_META = new Map(
  [
    ...techBottleneckWorkbenchCoreCandidates,
    ...techBottleneckWorkbenchAdjacentWatchlist,
    ...techBottleneckWorkbenchEvidenceBackfillQueue,
    ...techBottleneckWorkbenchRejectedCandidates
  ].map((candidate) => [candidate.stockCode, candidate])
);

function conceptTags(row: TechBottleneckReviewStock) {
  if (Array.isArray(row.concept_tags)) return row.concept_tags;
  return String(row.concept_tags || '')
    .split(/[;,，、|/]/)
    .map((tag) => tag.trim())
    .filter(Boolean);
}

function evidenceStrength(row: TechBottleneckReviewStock) {
  if (row.evidence_strength) return row.evidence_strength;
  const evidenceCount = Number(row.evidence_count || 0);
  const pageCitationCount = Number(row.page_citation_count || 0);
  if (pageCitationCount >= 20 || evidenceCount >= 40) return 'strong';
  if (pageCitationCount >= 10 || evidenceCount >= 20) return 'sufficient';
  if (pageCitationCount > 0 || evidenceCount > 0) return 'moderate';
  return 'missing';
}

function bottleneckRelevance(row: TechBottleneckReviewStock) {
  if (row.bottleneck_relevance) return row.bottleneck_relevance;
  const hint = String(row.bottleneck_or_chokepoint_hint || '').toLowerCase();
  if (hint.includes('strong') || hint.includes('core')) return 'core';
  if (hint.includes('supported') || hint.includes('moderate')) return 'core_pending';
  if (hint.includes('weak')) return 'adjacent';
  return 'unclear';
}

function normalizedScore(value: unknown) {
  if (value === null || value === undefined || value === '') return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function enrichReviewRow(row: TechBottleneckReviewStock): TechBottleneckReviewStock {
  const legacy = LEGACY_CANDIDATE_META.get(row.stock_code);
  const legacyConceptTags = legacy?.conceptTags ?? [];
  const datasetBottleneckScore = normalizedScore(row.bottleneck_confidence_score);
  const datasetEvidenceScore = normalizedScore(row.evidence_quality_score);
  return {
    ...row,
    industry: row.industry || legacy?.industry || '未映射',
    concept_tags: conceptTags(row).length ? conceptTags(row) : legacyConceptTags.length ? legacyConceptTags : ['未映射'],
    evidence_strength: row.evidence_strength || legacy?.evidenceStrength || evidenceStrength(row),
    bottleneck_relevance: row.bottleneck_relevance || legacy?.bottleneckRelevance || bottleneckRelevance(row),
    bottleneckConfidenceScore: row.bottleneckConfidenceScore ?? datasetBottleneckScore ?? legacy?.bottleneckConfidenceScore ?? null,
    evidenceQualityScore: row.evidenceQualityScore ?? datasetEvidenceScore ?? legacy?.evidenceQualityScore ?? null,
    source_group: row.source_group || legacy?.sourceGroup || row.review_universe_source,
    previous_tier: row.previous_tier || legacy?.previousTier || row.current_layer_status,
    review_status: row.review_status || legacy?.reviewStatus || row.frontend_review_status || 'pending_review'
  };
}

function uniqueSorted(values: string[]) {
  return Array.from(new Set(values.filter(Boolean))).sort((a, b) => a.localeCompare(b));
}

function readableFilterOptions(rows: TechBottleneckReviewStock[]): TechBottleneckReadableFilterOptions {
  return {
    industry: uniqueSorted(rows.map((row) => row.industry || '')),
    concept_tag: uniqueSorted(rows.flatMap(conceptTags)),
    evidence_strength: uniqueSorted(rows.map((row) => row.evidence_strength || '')),
    bottleneck_relevance: uniqueSorted(rows.map((row) => row.bottleneck_relevance || '')),
    concept_pollution_risk: uniqueSorted(rows.map((row) => row.concept_pollution_risk || '')),
    route_around_or_substitution_risk: uniqueSorted(rows.map((row) => row.route_around_or_substitution_risk || '')),
    value_capture_risk: uniqueSorted(rows.map((row) => row.value_capture_risk || '')),
    review_status: uniqueSorted(['pending_review', ...rows.map((row) => row.review_status || row.frontend_review_status || '')]),
    reviewer_decision: uniqueSorted(['pending', ...rows.map((row) => row.reviewer_decision || '')])
  };
}

function reviewerDecisionValue(row: TechBottleneckReviewStock) {
  return row.reviewer_decision || 'pending';
}

function matchesFilter(row: TechBottleneckReviewStock, filters: TechBottleneckReviewFilters) {
  const query = filters.q.trim().toLowerCase();
  if (query && !`${row.stock_code} ${row.stock_name}`.toLowerCase().includes(query)) {
    return false;
  }
  return (
    (!filters.industry || row.industry === filters.industry) &&
    (!filters.concept_tag || conceptTags(row).includes(filters.concept_tag)) &&
    (!filters.evidence_strength || row.evidence_strength === filters.evidence_strength) &&
    (!filters.bottleneck_relevance || row.bottleneck_relevance === filters.bottleneck_relevance) &&
    (!filters.concept_pollution_risk || row.concept_pollution_risk === filters.concept_pollution_risk) &&
    (!filters.route_around_or_substitution_risk ||
      row.route_around_or_substitution_risk === filters.route_around_or_substitution_risk) &&
    (!filters.value_capture_risk || row.value_capture_risk === filters.value_capture_risk) &&
    (!filters.review_status || row.review_status === filters.review_status || row.frontend_review_status === filters.review_status) &&
    (!filters.reviewer_decision || reviewerDecisionValue(row) === filters.reviewer_decision)
  );
}

function friendlyDecisionError(error: unknown) {
  const message = error instanceof Error ? error.message : '人工复盘写入失败';
  if (message.includes('missing_dashboard_write_token')) {
    return '人工复盘写入失败：缺少写入令牌';
  }
  if (message.includes('invalid_dashboard_write_token')) {
    return '人工复盘写入失败：写入令牌无效';
  }
  if (message.includes('review_comment_required')) {
    return '人工复盘写入失败：需要填写复盘备注';
  }
  if (message.includes('evidence_checked_required')) {
    return '人工复盘写入失败：需要勾选已核验证据';
  }
  return message;
}

function reviewerDecisionLabel(decision: TechBottleneckReviewerDecision) {
  const labels: Record<TechBottleneckReviewerDecision, string> = {
    keep: '保留',
    hold: '暂缓',
    need_more_evidence: '需更多证据',
    downgrade: '降级',
    reject: '拒绝'
  };
  return labels[decision];
}

export function TechBottleneckReviewPage({ onOpenStock }: Props) {
  const [summary, setSummary] = useState<TechBottleneckReviewSummary | null>(null);
  const [decisionSummary, setDecisionSummary] = useState<TechBottleneckReviewDecisionSummary | null>(null);
  const [rows, setRows] = useState<TechBottleneckReviewStock[]>([]);
  const [filters, setFilters] = useState<TechBottleneckReviewFilters>(EMPTY_TECH_BOTTLENECK_REVIEW_FILTERS);
  const [selectedStock, setSelectedStock] = useState<TechBottleneckReviewStock | null>(null);
  const [evidence, setEvidence] = useState<TechBottleneckReviewEvidence[]>([]);
  const [sources, setSources] = useState<TechBottleneckReviewSource[]>([]);
  const [decisionHistory, setDecisionHistory] = useState<TechBottleneckReviewDecisionRecord[]>([]);
  const [decisionMessage, setDecisionMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetchTechBottleneckReviewUniverseSummary(),
      fetchTechBottleneckReviewUniverseStocks({ limit: 500 }),
      fetchTechBottleneckReviewUniverseFilterOptions(),
      fetchTechBottleneckReviewUniverseDecisionSummary()
    ])
      .then(([nextSummary, stockPayload, _nextFilterOptions, nextDecisionSummary]) => {
        if (cancelled) return;
        setSummary(nextSummary);
        setRows(stockPayload.items);
        setDecisionSummary(nextDecisionSummary);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const enrichedRows = useMemo(() => rows.map(enrichReviewRow), [rows]);
  const filterOptions = useMemo(() => readableFilterOptions(enrichedRows), [enrichedRows]);
  const filteredRows = useMemo(() => enrichedRows.filter((row) => matchesFilter(row, filters)), [filters, enrichedRows]);

  function openEvidence(stockCode: string) {
    const row = enrichedRows.find((candidate) => candidate.stock_code === stockCode) ?? null;
    setSelectedStock(row);
    Promise.all([
      fetchTechBottleneckReviewUniverseEvidence(stockCode),
      fetchTechBottleneckReviewUniverseSources(stockCode),
      fetchTechBottleneckReviewUniverseDecisions(stockCode, 5)
    ])
      .then(([evidencePayload, sourcePayload, decisionPayload]) => {
        setEvidence(evidencePayload.items);
        setSources(sourcePayload.items);
        setDecisionHistory(decisionPayload.items);
      })
      .catch((err: Error) => setError(err.message));
  }

  function refreshReviewReadModels() {
    return Promise.all([fetchTechBottleneckReviewUniverseStocks({ limit: 500 }), fetchTechBottleneckReviewUniverseDecisionSummary()]).then(
      ([stockPayload, nextDecisionSummary]) => {
        setRows(stockPayload.items);
        setDecisionSummary(nextDecisionSummary);
        setSelectedStock((current) => {
          if (!current) return current;
          return stockPayload.items.map(enrichReviewRow).find((item) => item.stock_code === current.stock_code) ?? current;
        });
      }
    );
  }

  async function recordManualDecision(decision: TechBottleneckReviewerDecision, reviewComment: string, evidenceChecked: boolean) {
    if (!selectedStock) return;
    setDecisionMessage('');
    try {
      const response = await createTechBottleneckReviewUniverseDecision({
        stock_code: selectedStock.stock_code,
        stock_name: selectedStock.stock_name,
        reviewer_decision: decision,
        reviewer: 'operator',
        review_comment: reviewComment,
        rubric_flags: {
          hard_tech: true,
          bottleneck_role: true,
          business_relevance: 'needs_review',
          primary_source_evidence: 'checked_in_panel',
          page_level_evidence: true,
          value_capture: 'needs_review',
          route_around_risk: 'needs_review',
          disconfirmation_risk: 'needs_review'
        },
        evidence_checked: evidenceChecked,
        source_context: {
          from: 'tech_bottleneck_review_universe_page',
          page_route: '/research/tech-bottleneck/review-universe'
        }
      });
      await refreshReviewReadModels();
      const decisionPayload = await fetchTechBottleneckReviewUniverseDecisions(selectedStock.stock_code, 5);
      setDecisionHistory(decisionPayload.items);
      setDecisionMessage(`人工复盘已记录：${reviewerDecisionLabel(response.reviewer_decision)}`);
    } catch (err) {
      setDecisionMessage(friendlyDecisionError(err));
    }
  }

  if (error) {
    return (
      <section className="workspace-band" role="alert">
        <h1>科技卡脖子复盘加载异常</h1>
        <p className="muted">{error}</p>
      </section>
    );
  }

  if (!summary) {
    return (
      <section className="workspace-band">
        <h1>科技卡脖子复盘加载中</h1>
        <p className="muted">正在加载 research-only 复盘全集数据...</p>
      </section>
    );
  }

  return (
    <section className="workspace-page" aria-label="科技卡脖子复盘工作台">
      <header className="workspace-header">
        <div>
          <h1>科技卡脖子复盘</h1>
          <p className="muted">
            research-only 人工复盘工作台。分数只用于排序提示，reviewer_decision 只通过独立 overlay / ingest 流程写入。
          </p>
        </div>
        <span className="status-pill">{summary.acceptance_decision}</span>
      </header>
      <TechBottleneckSummaryCards summary={summary} decisionSummary={decisionSummary} />
      <TechBottleneckFilterBar filters={filters} options={filterOptions} onChange={setFilters} />
      <TechBottleneckReviewTable
        rows={filteredRows}
        total={rows.length}
        onOpenEvidence={openEvidence}
        onOpenStock={(stock) => onOpenStock?.(stock)}
      />
      <TechBottleneckEvidencePanel
        stock={selectedStock}
        evidence={evidence}
        sources={sources}
        onRecordManualDecision={recordManualDecision}
        decisionMessage={decisionMessage}
        decisionHistory={decisionHistory}
      />
    </section>
  );
}
