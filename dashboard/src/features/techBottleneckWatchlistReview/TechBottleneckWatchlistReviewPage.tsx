import { useMemo, useState } from 'react';
import {
  techBottleneckPipelineClosureGuardrails,
  techBottleneckPipelineClosureSummary,
  techBottleneckWorkbenchAdjacentWatchlist,
  techBottleneckWorkbenchCoreCandidates,
  techBottleneckWorkbenchEvidenceBackfillQueue,
  techBottleneckWorkbenchGuardrails,
  techBottleneckWorkbenchRejectedCandidates,
  techBottleneckWorkbenchSummary
} from './techBottleneckCandidateUniverseData';
import type { TechBottleneckWorkbenchCandidate } from './types';

type CandidateTab = 'core' | 'adjacent' | 'evidence_backfill' | 'rejected' | 'guardrails';
type SortKey =
  | 'researchPriorityScore'
  | 'stockName'
  | 'industry'
  | 'evidenceStrength'
  | 'bottleneckRelevance'
  | 'sourceGroup'
  | 'previousTier'
  | 'reviewStatus';
type SortDirection = 'asc' | 'desc';

type Filters = {
  query: string;
  industry: string;
  conceptTag: string;
  evidenceStrength: string;
  bottleneckRelevance: string;
  sourceGroup: string;
  previousTier: string;
  reviewStatus: string;
  minScore: string;
  maxScore: string;
};

const emptyFilters: Filters = {
  query: '',
  industry: '',
  conceptTag: '',
  evidenceStrength: '',
  bottleneckRelevance: '',
  sourceGroup: '',
  previousTier: '',
  reviewStatus: '',
  minScore: '',
  maxScore: ''
};

const tabs: Array<{ key: CandidateTab; label: string; count?: number; regionLabel: string }> = [
  {
    key: 'core',
    label: `Hard-Tech Review Pool ${techBottleneckWorkbenchSummary.workbench_core_candidate_count}`,
    count: techBottleneckWorkbenchSummary.workbench_core_candidate_count,
    regionLabel: 'Core candidate table'
  },
  {
    key: 'adjacent',
    label: `Adjacent Watchlist ${techBottleneckWorkbenchSummary.workbench_adjacent_watchlist_count}`,
    count: techBottleneckWorkbenchSummary.workbench_adjacent_watchlist_count,
    regionLabel: 'Adjacent watchlist table'
  },
  {
    key: 'evidence_backfill',
    label: `Evidence Backfill ${techBottleneckWorkbenchSummary.workbench_evidence_backfill_count}`,
    count: techBottleneckWorkbenchSummary.workbench_evidence_backfill_count,
    regionLabel: 'Evidence backfill table'
  },
  {
    key: 'rejected',
    label: `Rejected / Downgrade ${techBottleneckWorkbenchSummary.workbench_rejected_candidate_count}`,
    count: techBottleneckWorkbenchSummary.workbench_rejected_candidate_count,
    regionLabel: 'Rejected downgrade table'
  },
  { key: 'guardrails', label: 'Guardrails', regionLabel: 'Guardrails table' }
];

const evidenceRank: Record<string, number> = {
  strong: 5,
  sufficient: 4,
  moderate: 3,
  pending_primary_source: 2,
  weak: 2,
  missing: 1
};

const bottleneckRank: Record<string, number> = {
  core: 4,
  core_pending: 3,
  likely_core_pending: 3,
  adjacent: 3,
  unclear: 2,
  not_relevant: 1
};

const sortableColumnLabels: Record<SortKey, string> = {
  researchPriorityScore: 'research_priority_score',
  stockName: 'stock_name',
  industry: 'industry',
  evidenceStrength: 'evidence_strength',
  bottleneckRelevance: 'bottleneck_relevance',
  sourceGroup: 'source_group',
  previousTier: 'previous_tier',
  reviewStatus: 'review_status'
};

function formatScore(score: number | null) {
  return score === null || Number.isNaN(score) ? '-' : score.toFixed(2);
}

function formatOptionalScore(score: number | null | undefined) {
  return score === null || score === undefined || Number.isNaN(score) ? '-' : score.toFixed(0);
}

function reportLink(path?: string) {
  return path && path.trim() ? `/${path}` : '';
}

function uniqueValues(candidates: TechBottleneckWorkbenchCandidate[], getValue: (candidate: TechBottleneckWorkbenchCandidate) => string) {
  return Array.from(new Set(candidates.map(getValue).filter(Boolean))).sort((a, b) => a.localeCompare(b));
}

function uniqueTags(candidates: TechBottleneckWorkbenchCandidate[]) {
  return Array.from(new Set(candidates.flatMap((candidate) => candidate.conceptTags))).sort((a, b) => a.localeCompare(b));
}

function candidatesForTab(tab: CandidateTab): TechBottleneckWorkbenchCandidate[] {
  if (tab === 'adjacent') return techBottleneckWorkbenchAdjacentWatchlist;
  if (tab === 'evidence_backfill') return techBottleneckWorkbenchEvidenceBackfillQueue;
  if (tab === 'rejected') return techBottleneckWorkbenchRejectedCandidates;
  return techBottleneckWorkbenchCoreCandidates;
}

function comparePriority(
  a: TechBottleneckWorkbenchCandidate,
  b: TechBottleneckWorkbenchCandidate,
  sortDirection: SortDirection
) {
  const aScore = a.researchPriorityScore;
  const bScore = b.researchPriorityScore;
  if (aScore !== null || bScore !== null) {
    const diff = (aScore ?? Number.NEGATIVE_INFINITY) - (bScore ?? Number.NEGATIVE_INFINITY);
    if (diff !== 0) return sortDirection === 'desc' ? -diff : diff;
  }

  const rankDiff = a.reviewPriorityRank - b.reviewPriorityRank;
  if (rankDiff !== 0) return sortDirection === 'desc' ? rankDiff : -rankDiff;

  const evidenceDiff = (evidenceRank[b.evidenceStrength] ?? 0) - (evidenceRank[a.evidenceStrength] ?? 0);
  if (evidenceDiff !== 0) return sortDirection === 'desc' ? evidenceDiff : -evidenceDiff;

  const bottleneckDiff = (bottleneckRank[b.bottleneckRelevance] ?? 0) - (bottleneckRank[a.bottleneckRelevance] ?? 0);
  if (bottleneckDiff !== 0) return sortDirection === 'desc' ? bottleneckDiff : -bottleneckDiff;

  return a.stockCode.localeCompare(b.stockCode);
}

function compareBySortKey(a: TechBottleneckWorkbenchCandidate, b: TechBottleneckWorkbenchCandidate, sortKey: SortKey) {
  if (sortKey === 'researchPriorityScore') {
    return comparePriority(a, b, 'asc');
  }
  if (sortKey === 'evidenceStrength') {
    return (evidenceRank[a.evidenceStrength] ?? 0) - (evidenceRank[b.evidenceStrength] ?? 0) || a.stockCode.localeCompare(b.stockCode);
  }
  if (sortKey === 'bottleneckRelevance') {
    return (
      (bottleneckRank[a.bottleneckRelevance] ?? 0) - (bottleneckRank[b.bottleneckRelevance] ?? 0) ||
      a.stockCode.localeCompare(b.stockCode)
    );
  }
  return String(a[sortKey]).localeCompare(String(b[sortKey])) || a.stockCode.localeCompare(b.stockCode);
}

function sortCandidates(candidates: TechBottleneckWorkbenchCandidate[], sortKey: SortKey, sortDirection: SortDirection) {
  return [...candidates].sort((a, b) => {
    if (sortKey === 'researchPriorityScore') {
      return comparePriority(a, b, sortDirection);
    }
    const result = compareBySortKey(a, b, sortKey);
    return sortDirection === 'desc' ? -result : result;
  });
}

function filterCandidates(candidates: TechBottleneckWorkbenchCandidate[], filters: Filters, sortKey: SortKey, sortDirection: SortDirection) {
  const query = filters.query.trim().toLowerCase();
  const minScore = filters.minScore === '' ? null : Number(filters.minScore);
  const maxScore = filters.maxScore === '' ? null : Number(filters.maxScore);
  const filtered = candidates.filter((candidate) => {
    const searchable = [candidate.stockCode, candidate.stockName].join(' ').toLowerCase();
    if (query && !searchable.includes(query)) return false;
    if (filters.industry && candidate.industry !== filters.industry) return false;
    if (filters.conceptTag && !candidate.conceptTags.includes(filters.conceptTag)) return false;
    if (filters.evidenceStrength && candidate.evidenceStrength !== filters.evidenceStrength) return false;
    if (filters.bottleneckRelevance && candidate.bottleneckRelevance !== filters.bottleneckRelevance) return false;
    if (filters.sourceGroup && candidate.sourceGroup !== filters.sourceGroup) return false;
    if (filters.previousTier && candidate.previousTier !== filters.previousTier) return false;
    if (filters.reviewStatus && candidate.reviewStatus !== filters.reviewStatus) return false;
    if (candidate.researchPriorityScore !== null && minScore !== null && candidate.researchPriorityScore < minScore) return false;
    if (candidate.researchPriorityScore !== null && maxScore !== null && candidate.researchPriorityScore > maxScore) return false;
    return true;
  });
  return sortCandidates(filtered, sortKey, sortDirection);
}

function openStockWorkbench(candidate: TechBottleneckWorkbenchCandidate) {
  const source = 'tech_bottleneck_candidate_universe_pipeline_closure_v2';
  window.history.pushState({}, '', `/tech-bottleneck/stock/${candidate.stockCode}?source=${source}`);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

function CandidateFilters({
  candidates,
  filters,
  onChange
}: {
  candidates: TechBottleneckWorkbenchCandidate[];
  filters: Filters;
  onChange: (filters: Filters) => void;
}) {
  const update = (field: keyof Filters, value: string) => onChange({ ...filters, [field]: value });
  return (
    <section className="tech-bottleneck-filter-toolbar" aria-label="筛选工具条">
      <label>
        股票代码/名称搜索
        <input type="search" value={filters.query} onChange={(event) => update('query', event.target.value)} />
      </label>
      <label>
        行业
        <select value={filters.industry} onChange={(event) => update('industry', event.target.value)}>
          <option value="">全部</option>
          {uniqueValues(candidates, (candidate) => candidate.industry).map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      <label>
        概念板块
        <select value={filters.conceptTag} onChange={(event) => update('conceptTag', event.target.value)}>
          <option value="">全部</option>
          {uniqueTags(candidates).map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      <label>
        证据强度
        <select value={filters.evidenceStrength} onChange={(event) => update('evidenceStrength', event.target.value)}>
          <option value="">全部</option>
          {uniqueValues(candidates, (candidate) => candidate.evidenceStrength).map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      <label>
        瓶颈相关性
        <select value={filters.bottleneckRelevance} onChange={(event) => update('bottleneckRelevance', event.target.value)}>
          <option value="">全部</option>
          {uniqueValues(candidates, (candidate) => candidate.bottleneckRelevance).map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      <label>
        来源
        <select value={filters.sourceGroup} onChange={(event) => update('sourceGroup', event.target.value)}>
          <option value="">全部</option>
          {uniqueValues(candidates, (candidate) => candidate.sourceGroup).map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      <label>
        原Tier
        <select value={filters.previousTier} onChange={(event) => update('previousTier', event.target.value)}>
          <option value="">全部</option>
          {uniqueValues(candidates, (candidate) => candidate.previousTier).map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      <label>
        复盘状态
        <select value={filters.reviewStatus} onChange={(event) => update('reviewStatus', event.target.value)}>
          <option value="">全部</option>
          {uniqueValues(candidates, (candidate) => candidate.reviewStatus).map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      <label>
        分数下限
        <input type="number" value={filters.minScore} onChange={(event) => update('minScore', event.target.value)} />
      </label>
      <label>
        分数上限
        <input type="number" value={filters.maxScore} onChange={(event) => update('maxScore', event.target.value)} />
      </label>
      <button type="button" onClick={() => onChange(emptyFilters)}>
        重置筛选
      </button>
    </section>
  );
}

function CandidateTable({
  label,
  tableLabel,
  candidates,
  sortKey,
  sortDirection,
  onSort
}: {
  label: string;
  tableLabel: string;
  candidates: TechBottleneckWorkbenchCandidate[];
  sortKey: SortKey;
  sortDirection: SortDirection;
  onSort: (sortKey: SortKey) => void;
}) {
  const sortableHeader = (key: SortKey) => (
    <button type="button" onClick={() => onSort(key)} aria-label={`Sort by ${sortableColumnLabels[key]}`}>
      {sortableColumnLabels[key]}
      {sortKey === key ? (sortDirection === 'desc' ? ' ↓' : ' ↑') : ''}
    </button>
  );

  return (
    <section aria-label={label}>
      <div className="tech-bottleneck-table-summary">当前显示 {candidates.length} 条 · research_priority_score 缺失显示 “-” 并使用 review_priority_rank fallback</div>
      <div className="tech-bottleneck-table-scroll">
        <table className="tech-bottleneck-candidate-table" aria-label={tableLabel}>
          <thead>
            <tr>
              <th>#</th>
              <th>stock_code</th>
              <th>{sortableHeader('stockName')}</th>
              <th>{sortableHeader('industry')}</th>
              <th>concept_tags</th>
              <th>evidence_category</th>
              <th>{sortableHeader('researchPriorityScore')}</th>
              <th>{sortableHeader('evidenceStrength')}</th>
              <th>{sortableHeader('bottleneckRelevance')}</th>
              <th>{sortableHeader('sourceGroup')}</th>
              <th>{sortableHeader('previousTier')}</th>
              <th>{sortableHeader('reviewStatus')}</th>
              <th>report_status</th>
              <th>bottleneck_confidence_score</th>
              <th>evidence_quality_score</th>
              <th>review_decision</th>
              <th>report_updated_at</th>
              <th>rationale</th>
              <th>报告</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((candidate, index) => (
              <tr
                key={`${candidate.queue}-${candidate.stockCode}`}
                className="tech-bottleneck-clickable-row"
                tabIndex={0}
                onClick={() => openStockWorkbench(candidate)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    openStockWorkbench(candidate);
                  }
                }}
              >
                <td>{index + 1}</td>
                <td>{candidate.stockCode}</td>
                <td>{candidate.stockName}</td>
                <td>{candidate.industry}</td>
                <td>{candidate.conceptTags.join(', ')}</td>
                <td>{candidate.evidenceCategory || candidate.businessRelevanceCategory}</td>
                <td>{formatScore(candidate.researchPriorityScore)}</td>
                <td>{candidate.evidenceStrength}</td>
                <td>{candidate.bottleneckRelevance}</td>
                <td>{candidate.sourceGroup}</td>
                <td>{candidate.previousTier}</td>
                <td>{candidate.reviewStatus}</td>
                <td>{candidate.reportStatus ?? '-'}</td>
                <td>{formatOptionalScore(candidate.bottleneckConfidenceScore)}</td>
                <td>{formatOptionalScore(candidate.evidenceQualityScore)}</td>
                <td>{candidate.reportReviewDecision ?? '-'}</td>
                <td>{candidate.reportUpdatedAt ?? '-'}</td>
                <td>{candidate.rationale}</td>
                <td className="tech-bottleneck-report-actions">
                  {candidate.reportHtmlPath ? (
                    <a href={reportLink(candidate.reportHtmlPath)} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>
                      打开HTML报告
                    </a>
                  ) : (
                    <span>-</span>
                  )}
                  {candidate.reportPdfPath ? (
                    <a href={reportLink(candidate.reportPdfPath)} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>
                      打开PDF报告
                    </a>
                  ) : (
                    <span>-</span>
                  )}
                  {candidate.evidenceMatrixPath ? (
                    <a href={reportLink(candidate.evidenceMatrixPath)} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>
                      查看证据矩阵
                    </a>
                  ) : (
                    <span>-</span>
                  )}
                </td>
                <td>
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      openStockWorkbench(candidate);
                    }}
                    aria-label={`打开 ${candidate.stockName} 个股复盘工作台`}
                  >
                    进入个股工作台
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function TechBottleneckWatchlistReviewPage() {
  const [activeTab, setActiveTab] = useState<CandidateTab>('core');
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [sortKey, setSortKey] = useState<SortKey>('researchPriorityScore');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const activeCandidates = candidatesForTab(activeTab);
  const filteredCandidates = useMemo(
    () => filterCandidates(activeCandidates, filters, sortKey, sortDirection),
    [activeCandidates, filters, sortDirection, sortKey]
  );
  const tableRegion = tabs.find((tab) => tab.key === activeTab)?.regionLabel ?? 'Core candidate table';

  const updateSort = (nextSortKey: SortKey) => {
    if (nextSortKey === sortKey) {
      setSortDirection((current) => (current === 'desc' ? 'asc' : 'desc'));
      return;
    }
    setSortKey(nextSortKey);
    setSortDirection('desc');
  };

  return (
    <section className="tech-bottleneck-review-queue" aria-label="技术瓶颈候选复盘队列">
      <header className="tech-bottleneck-review-header">
        <h1>技术瓶颈候选复盘队列</h1>
        <p>Research-only · Manual review only · No production signal/admission</p>
      </header>

      <section className="tech-bottleneck-status-strip" aria-label="候选队列状态条">
        <span>Hard-Tech Pool {techBottleneckWorkbenchSummary.workbench_core_candidate_count}</span>
        <span>Verified Core {techBottleneckWorkbenchSummary.verified_core_count}</span>
        <span>Manual Anchor Pending {techBottleneckWorkbenchSummary.manual_anchor_core_pending_evidence_count}</span>
        <span>Likely Pending Evidence {techBottleneckWorkbenchSummary.likely_hard_tech_pending_evidence_count}</span>
        <span>Adjacent Pending {techBottleneckWorkbenchSummary.adjacent_pending_evidence_count}</span>
        <span>Low Priority Backfill {techBottleneckWorkbenchSummary.low_priority_evidence_backfill_count}</span>
        <span>Reject / Pollution {techBottleneckWorkbenchSummary.reject_seed_pollution_count}</span>
        <span>Legacy {techBottleneckWorkbenchSummary.legacy_pool_count} deprecated</span>
        <span>Signal disabled</span>
        <span>Admission disabled</span>
      </section>

      <section className="tech-bottleneck-tabs" aria-label="Candidate queue tabs">
        <div role="tablist" aria-label="候选复盘队列">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.key}
              onClick={() => {
                setActiveTab(tab.key);
                setFilters(emptyFilters);
                setSortKey('researchPriorityScore');
                setSortDirection('desc');
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </section>

      {activeTab === 'guardrails' ? (
        <section className="tech-bottleneck-guardrails-panel" aria-label="Guardrails table">
          <h2>Guardrails</h2>
          <h3>Pipeline closure</h3>
          <p>canonical default pool: {techBottleneckPipelineClosureSummary.canonical_default_pool_path}</p>
          <p>legacy pool: {techBottleneckPipelineClosureSummary.legacy_pool_path}</p>
          <p>legacy_unverified_pool / deprecated_for_default_core_use</p>
          <p>Old 114 pool is not the default dashboard pool.</p>
          <p>v2 default pool 90 removes obvious pollution but keeps hard-tech pending evidence.</p>
          <p>北方华创 and 中微公司 are manual anchor core pending evidence.</p>
          <p>佛山照明、通宝能源、银行股 are excluded from default hard-tech review pool.</p>
          <p>Tier A pass was pass-by-construction, not independent validation.</p>
          <p>Tier B high_quality=0 was threshold/data-gap driven.</p>
          <dl>
            <dt>used_for_signal_count</dt>
            <dd>{techBottleneckWorkbenchGuardrails.used_for_signal_count}</dd>
            <dt>used_for_admission_count</dt>
            <dd>{techBottleneckWorkbenchGuardrails.used_for_admission_count}</dd>
            <dt>allowed_for_signal</dt>
            <dd>{techBottleneckPipelineClosureGuardrails.allowed_for_signal_count}</dd>
            <dt>allowed_for_admission</dt>
            <dd>{techBottleneckPipelineClosureGuardrails.allowed_for_admission_count}</dd>
            <dt>baseline_admission_changed_count</dt>
            <dd>{techBottleneckWorkbenchGuardrails.baseline_admission_changed_count}</dd>
            <dt>production_candidate_universe_modified</dt>
            <dd>false</dd>
            <dt>dashboard_workbench_integration_modified</dt>
            <dd>false</dd>
          </dl>
          <p>allowed_for_signal={techBottleneckPipelineClosureGuardrails.allowed_for_signal_count}</p>
          <p>allowed_for_admission={techBottleneckPipelineClosureGuardrails.allowed_for_admission_count}</p>
        </section>
      ) : (
        <>
          <CandidateFilters candidates={activeCandidates} filters={filters} onChange={setFilters} />
          <CandidateTable
            label={tableRegion}
            tableLabel={activeTab === 'core' ? 'Hard-Tech Review Pool Table' : `${tabs.find((tab) => tab.key === activeTab)?.label.split(' ')[0]} Candidates Table`}
            candidates={filteredCandidates}
            sortKey={sortKey}
            sortDirection={sortDirection}
            onSort={updateSort}
          />
        </>
      )}

      <section aria-label="Forbidden production actions">
        <h2>Production boundaries</h2>
        <p>Formal strategy files, signal logic, admission logic, scoring logic, and production candidate universe are unchanged.</p>
      </section>
    </section>
  );
}
