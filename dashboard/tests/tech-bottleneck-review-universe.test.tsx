import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppShell } from '../src/components/AppShell';

const reviewPayload = vi.hoisted(() => ({
  summary: {
    frontend_dataset_count: 378,
    v5_hydrated_count: 271,
    v7_proposal_new_count: 78,
    v5_targeted_hydrated_count: 29,
    remaining_evidence_gap_count: 0,
    evidence_index_row_count: 8583,
    source_index_row_count: 1071,
    used_for_signal_count: 0,
    used_for_admission_count: 0,
    readonly_page: true,
    reviewer_decision_write_enabled: false,
    database_write_enabled: false,
    csv_writeback_enabled: false,
    acceptance_decision: 'tech_bottleneck_review_universe_frontend_dataset_ready'
  },
  decisionSummary: {
    total_review_universe_count: 378,
    reviewed_count: 0,
    pending_count: 378,
    keep_count: 0,
    hold_count: 0,
    need_more_evidence_count: 0,
    downgrade_count: 0,
    reject_count: 0,
    last_reviewed_at: '',
    used_for_signal_count: 0,
    used_for_admission_count: 0,
    frozen_v7_generated: false
  },
  stocks: [
    {
      stock_code: '000777',
      stock_name: '中核科技',
      review_universe_source: 'v7_proposal_new',
      current_layer_status: 'latent_manual_review_standard_core_equivalent_proposal',
      manual_approval_status: 'pending',
      frontend_review_status: 'pending_review',
      evidence_count: 18,
      page_citation_count: 18,
      source_pdf_count: 3,
      primary_source_supported: true,
      hard_tech_domain: 'supported',
      supply_chain_role_hint: 'supported',
      business_relevance_hint: 'supported',
      bottleneck_or_chokepoint_hint: 'supported',
      concept_pollution_risk: 'not_detected_in_chunk',
      route_around_or_substitution_risk: 'needs_manual_review',
      value_capture_risk: 'needs_manual_review',
      disconfirmation_trigger: false,
      next_primary_source_to_check: 'manual review',
      strongest_primary_source_claim: 'Primary-source evidence supports the hard-tech exposure.',
      weakest_or_riskiest_claim: 'Route-around risk needs manual review.',
      evidence_summary_for_review: 'evidence=18; page_citations=18; sources=3',
      industry: 'nuclear_valve_equipment',
      concept_tags: ['nuclear_power', 'high_end_equipment'],
      evidence_strength: 'strong',
      bottleneck_relevance: 'core',
      source_group: 'latent_standard',
      previous_tier: 'latent_manual_review',
      review_status: 'pending_review',
      reviewer_decision: '',
      reviewer_note: '',
      used_for_signal: false,
      used_for_admission: false,
      auto_added_to_quality_pool: false
    },
    {
      stock_code: '002028',
      stock_name: '思源电气',
      review_universe_source: 'v5_targeted_hydrated',
      current_layer_status: 'internal_quality_pool',
      manual_approval_status: 'pending_manual_approval',
      frontend_review_status: 'pending_review',
      evidence_count: 13,
      page_citation_count: 13,
      source_pdf_count: 1,
      primary_source_supported: true,
      hard_tech_domain: 'strong',
      supply_chain_role_hint: 'evidence_required',
      business_relevance_hint: 'evidence_required',
      bottleneck_or_chokepoint_hint: 'strong',
      concept_pollution_risk: 'low',
      route_around_or_substitution_risk: 'missing_route_around',
      value_capture_risk: 'needs_manual_review',
      disconfirmation_trigger: true,
      next_primary_source_to_check: 'review mapped Docling page-level evidence',
      strongest_primary_source_claim: 'Docling page evidence supports product exposure.',
      weakest_or_riskiest_claim: 'Competition risk remains visible.',
      evidence_summary_for_review: 'evidence=13; page_citations=13; sources=1',
      industry: 'power_electronics_or_grid_equipment',
      concept_tags: ['smart_grid'],
      evidence_strength: 'moderate',
      bottleneck_relevance: 'core_pending',
      source_group: 'v5_targeted',
      previous_tier: 'quality_pool_v5',
      review_status: 'pending_review',
      reviewer_decision: '',
      reviewer_note: '',
      used_for_signal: false,
      used_for_admission: false,
      auto_added_to_quality_pool: false
    },
    {
      stock_code: '000551',
      stock_name: '创元科技',
      review_universe_source: 'v5_hydrated',
      current_layer_status: 'false_negative_rescue_core_equivalent_quality_pool',
      manual_approval_status: 'pending_manual_approval',
      frontend_review_status: 'pending_review',
      evidence_count: 42,
      page_citation_count: 21,
      source_pdf_count: 3,
      primary_source_supported: true,
      hard_tech_domain: 'strong',
      supply_chain_role_hint: 'moderate',
      business_relevance_hint: 'core_hard_tech_evidence_supported',
      bottleneck_or_chokepoint_hint: 'strong',
      concept_pollution_risk: 'not_detected_in_existing_artifacts',
      route_around_or_substitution_risk: 'moderate',
      value_capture_risk: 'strong',
      disconfirmation_trigger: false,
      next_primary_source_to_check: 'manual review',
      strongest_primary_source_claim: 'Primary-source evidence supports equipment exposure.',
      weakest_or_riskiest_claim: 'Route-around risk needs manual review.',
      evidence_summary_for_review: 'evidence=42; page_citations=21; sources=3',
      industry: '专用设备制造业',
      concept_tags: '高端制造装备 / 专用设备宽口径 / concept_only',
      evidence_strength: 'strong',
      bottleneck_relevance: 'core',
      source_group: 'false_negative_rescue_backfilled',
      previous_tier: 'Excluded',
      bottleneck_confidence_score: 73,
      evidence_quality_score: 64,
      review_status: 'pending_review',
      reviewer_decision: '',
      reviewer_note: '',
      used_for_signal: false,
      used_for_admission: false,
      auto_added_to_quality_pool: false
    }
  ],
  filters: {
    review_universe_source: ['v5_targeted_hydrated', 'v7_proposal_new'],
    current_layer_status: ['internal_quality_pool', 'latent_manual_review_standard_core_equivalent_proposal'],
    manual_approval_status: ['pending', 'pending_manual_approval'],
    hard_tech_domain: ['strong', 'supported'],
    supply_chain_role_hint: ['evidence_required', 'supported'],
    concept_pollution_risk: ['low', 'not_detected_in_chunk'],
    primary_source_supported: [true],
    frontend_review_status: ['pending_review'],
    reviewer_decision: ['']
  },
  evidence: [
    {
      stock_code: '000777',
      stock_name: '中核科技',
      review_universe_source: 'v7_proposal_new',
      source_file: '/tmp/000777.pdf',
      source_type: 'announcement',
      source_title: '关于参加中核集团集体投资者交流会的公告',
      source_date: '2026-05-28',
      page: '1',
      evidence_text: 'Page-level evidence text for 中核科技.',
      evidence_claim_type: 'general_context',
      citation_quality: 'page_level',
      research_only: true,
      used_for_signal: false,
      used_for_admission: false
    }
  ],
  sources: [
    {
      stock_code: '000777',
      stock_name: '中核科技',
      review_universe_source: 'v7_proposal_new',
      source_file: '/tmp/000777.pdf',
      source_type: 'announcement',
      source_title: '关于参加中核集团集体投资者交流会的公告',
      research_only: true,
      used_for_signal: false,
      used_for_admission: false
    }
  ]
}));

const apiMocks = vi.hoisted(() => ({
  fetchTechBottleneckReviewUniverseSummary: vi.fn().mockResolvedValue(reviewPayload.summary),
  fetchTechBottleneckReviewUniverseStocks: vi.fn().mockResolvedValue({
    total: reviewPayload.stocks.length,
    limit: 500,
    offset: 0,
    items: reviewPayload.stocks
  }),
  fetchTechBottleneckReviewUniverseStock: vi.fn().mockImplementation(async (stockCode: string) => {
    const item = reviewPayload.stocks.find((row) => row.stock_code === stockCode);
    if (!item) {
      throw new Error(`missing stock ${stockCode}`);
    }
    return item;
  }),
  fetchTechBottleneckReviewUniverseFilterOptions: vi.fn().mockResolvedValue(reviewPayload.filters),
  fetchTechBottleneckReviewUniverseEvidence: vi.fn().mockResolvedValue({
    stock_code: '000777',
    total: reviewPayload.evidence.length,
    items: reviewPayload.evidence
  }),
  fetchTechBottleneckReviewUniverseSources: vi.fn().mockResolvedValue({
    stock_code: '000777',
    total: reviewPayload.sources.length,
    items: reviewPayload.sources
  }),
  fetchTechBottleneckReviewUniverseDecisions: vi.fn().mockResolvedValue({
    total: 0,
    limit: 5,
    items: []
  }),
  fetchTechBottleneckReviewUniverseDecisionSummary: vi.fn().mockResolvedValue(reviewPayload.decisionSummary),
  createTechBottleneckReviewUniverseDecision: vi.fn().mockResolvedValue({
    status: 'recorded',
    decision_id: 'tech_bottleneck_review_decision:000777:1',
    stock_code: '000777',
    reviewer_decision: 'need_more_evidence',
    reviewed_at: '2026-07-08T00:00:00Z'
  })
}));

vi.mock('../src/api/techBottleneckReview', () => apiMocks);
vi.mock('../src/api/client', () => ({
  fetchPlatformReadiness: vi.fn().mockResolvedValue({ display_trade_date: '2026-07-06' }),
  fetchPlatformSummary: vi.fn().mockResolvedValue({ latest_market_date: '2026-07-06' }),
  fetchDataToBriefDocling90Review: vi.fn()
}));

vi.mock('../src/components/FactorLabWorkspace', () => ({ FactorLabWorkspace: () => <div>Factor Lab</div> }));
vi.mock('../src/components/DailyReviewLiteWorkspace', () => ({ DailyReviewLiteWorkspace: () => <div>Daily Review</div> }));
vi.mock('../src/components/DataToBriefDocling90ReviewWorkspace', () => ({
  DataToBriefDocling90ReviewWorkspace: () => <div>Docling 90</div>
}));
vi.mock('../src/components/GeneratedReportsWorkspace', () => ({ GeneratedReportsWorkspace: () => <div>Generated</div> }));
vi.mock('../src/components/GlobalSearchBox', () => ({ GlobalSearchBox: () => <div>Search</div> }));
vi.mock('../src/components/HomeCockpit', () => ({ HomeCockpit: () => <div>Home</div> }));
vi.mock('../src/components/MarketMonitorWorkspace', () => ({ MarketMonitorWorkspace: () => <div>Market</div> }));
vi.mock('../src/components/NewsWorkspace', () => ({ NewsWorkspace: () => <div>News</div> }));
vi.mock('../src/components/ResearchReportsWorkspace', () => ({ ResearchReportsWorkspace: () => <div>Reports</div> }));
vi.mock('../src/components/ReviewQueueWorkspace', () => ({ ReviewQueueWorkspace: () => <div>Queue</div> }));
vi.mock('../src/components/StockWorkspace', () => ({
  StockWorkspace: ({
    entryContext
  }: {
    entryContext?: {
      bottleneckConfidenceScore?: number;
      evidenceQualityScore?: number;
      evidenceStrength?: string;
      bottleneckRelevance?: string;
      sourceGroup?: string;
      previousTier?: string;
    };
  }) => (
    <div>
      Stock
      <span>bottleneck_confidence_score {entryContext?.bottleneckConfidenceScore ?? '-'}</span>
      <span>evidence_quality_score {entryContext?.evidenceQualityScore ?? '-'}</span>
      <span>evidence_strength {entryContext?.evidenceStrength ?? '-'}</span>
      <span>bottleneck_relevance {entryContext?.bottleneckRelevance ?? '-'}</span>
      <span>source_group {entryContext?.sourceGroup ?? '-'}</span>
      <span>previous_tier {entryContext?.previousTier ?? '-'}</span>
    </div>
  )
}));
vi.mock('../src/components/StrategyLabWorkspace', () => ({ StrategyLabWorkspace: () => <div>Strategy Lab</div> }));
vi.mock('../src/components/WatchlistWorkspace', () => ({ WatchlistWorkspace: () => <div>Watchlist</div> }));
vi.mock('../src/features/techBottleneckWatchlistReview/TechBottleneckWatchlistReviewPage', () => ({
  TechBottleneckWatchlistReviewPage: () => <div>Old watchlist review</div>
}));

describe('Tech bottleneck review universe route', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/research/tech-bottleneck/review-universe');
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it('routes the legacy watchlist-review path to the 378-stock review universe workspace', async () => {
    window.history.pushState({}, '', '/tech-bottleneck/watchlist-review');

    render(<AppShell />);

    expect(await screen.findByRole('heading', { name: '科技卡脖子复盘' })).toBeVisible();
    expect(screen.getByText('复盘全集 378')).toBeVisible();
    expect(screen.queryByText('Old watchlist review')).not.toBeInTheDocument();
  });

  it('renders read-only summary, filters, and 378-row universe metrics', async () => {
    render(<AppShell />);

    expect(await screen.findByRole('heading', { name: '科技卡脖子复盘' })).toBeVisible();
    expect(screen.getByText('复盘全集 378')).toBeVisible();
    expect(screen.getByText('v5 已水合 271')).toBeVisible();
    expect(screen.getByText('v7 提案 78')).toBeVisible();
    expect(screen.getByText('定向补证 29')).toBeVisible();
    expect(screen.getByText('证据行 8583')).toBeVisible();
    expect(screen.getByText('来源行 1071')).toBeVisible();
    expect(screen.getByText('used_for_signal 0')).toBeVisible();
    expect(screen.getByText('used_for_admission 0')).toBeVisible();
    expect(screen.getByText('已复盘 0')).toBeVisible();
    expect(screen.getByText('待复盘 378')).toBeVisible();

    expect(screen.getByLabelText('股票代码/名称搜索')).toBeVisible();
    expect(screen.getByLabelText('行业')).toBeVisible();
    expect(screen.getByLabelText('概念板块')).toBeVisible();
    expect(screen.getByLabelText('证据强度')).toBeVisible();
    expect(screen.getByLabelText('瓶颈相关性')).toBeVisible();
    expect(screen.getByLabelText('污染风险')).toBeVisible();
    expect(screen.getByLabelText('替代风险')).toBeVisible();
    expect(screen.getByLabelText('价值捕获风险')).toBeVisible();
    expect(screen.getByLabelText('复盘状态')).toBeVisible();
    expect(screen.getByLabelText('人工结论')).toBeVisible();
    expect(screen.queryByLabelText('来源')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('原Tier')).not.toBeInTheDocument();
    expect(within(screen.getByLabelText('行业')).getByRole('option', { name: '核电阀门装备' })).toBeVisible();
    expect(within(screen.getByLabelText('概念板块')).getByRole('option', { name: '核电' })).toBeVisible();
    expect(within(screen.getByLabelText('概念板块')).getByRole('option', { name: '高端装备' })).toBeVisible();
    expect(within(screen.getByLabelText('证据强度')).getByRole('option', { name: '强' })).toBeVisible();
    expect(within(screen.getByLabelText('瓶颈相关性')).getByRole('option', { name: '核心瓶颈' })).toBeVisible();
    expect(within(screen.getByLabelText('污染风险')).getByRole('option', { name: '低风险' })).toBeVisible();
    expect(within(screen.getByLabelText('替代风险')).getByRole('option', { name: '需要人工复核' })).toBeVisible();
    expect(within(screen.getByLabelText('价值捕获风险')).getByRole('option', { name: '强' })).toBeVisible();
    expect(within(screen.getByLabelText('复盘状态')).getByRole('option', { name: '待复盘' })).toBeVisible();
    expect(within(screen.getByLabelText('人工结论')).getByRole('option', { name: '待复盘' })).toBeVisible();
    const table = within(screen.getByRole('table', { name: '科技卡脖子复盘股票表' }));
    expect(table.getByText('中核科技')).toBeVisible();
    expect(table.getByText('思源电气')).toBeVisible();
    expect(table.getByText('创元科技')).toBeVisible();
    expect(table.getByRole('columnheader', { name: '股票代码' })).toBeVisible();
    expect(table.getByRole('columnheader', { name: '股票名称' })).toBeVisible();
    expect(table.getByRole('columnheader', { name: '瓶颈分' })).toBeVisible();
    expect(table.getByRole('columnheader', { name: '证据分' })).toBeVisible();
    expect(table.queryByRole('columnheader', { name: '来源' })).not.toBeInTheDocument();
    expect(table.queryByRole('columnheader', { name: '原Tier' })).not.toBeInTheDocument();
    const columns = screen.getByRole('table', { name: '科技卡脖子复盘股票表' }).querySelectorAll('col');
    expect(columns).toHaveLength(13);
    expect(columns[0]).toHaveStyle({ width: '88px' });
    expect(columns[1]).toHaveStyle({ width: '96px' });
    expect(columns[3]).toHaveStyle({ width: '260px' });
    expect(columns[9]).toHaveStyle({ width: '72px' });
    expect(columns[10]).toHaveStyle({ width: '72px' });
    expect(screen.getByRole('row', { name: /002028 思源电气/ })).toHaveTextContent('55');
    expect(screen.getByRole('row', { name: /002028 思源电气/ })).toHaveTextContent('23');
    expect(screen.getByRole('row', { name: /000551 创元科技/ })).toHaveTextContent('专用设备制造业');
    expect(screen.getByRole('row', { name: /000551 创元科技/ })).toHaveTextContent('高端制造装备 / 专用设备宽口径 / 概念映射风险');
    expect(screen.getByRole('row', { name: /000551 创元科技/ })).toHaveTextContent('73');
    expect(screen.getByRole('row', { name: /000551 创元科技/ })).toHaveTextContent('64');
    expect(screen.queryByRole('button', { name: '打开 中核科技 个股复盘工作台' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /approve|reject|keep|downgrade|need_more_evidence/i })).not.toBeInTheDocument();
  });

  it('filters rows and opens read-only evidence/source detail', async () => {
    render(<AppShell />);
    await screen.findByRole('heading', { name: '科技卡脖子复盘' });

    fireEvent.change(screen.getByLabelText('替代风险'), { target: { value: 'needs_manual_review' } });
    const table = within(screen.getByRole('table', { name: '科技卡脖子复盘股票表' }));
    expect(table.getByText('中核科技')).toBeVisible();
    expect(table.queryByText('思源电气')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '查看证据 000777' }));
    expect(await screen.findByRole('region', { name: '000777 证据和来源详情' })).toHaveTextContent(
      'Page-level evidence text for 中核科技.'
    );
    expect(screen.getByRole('region', { name: '000777 证据和来源详情' })).toHaveTextContent(
      '关于参加中核集团集体投资者交流会的公告'
    );
    expect(screen.getByText('写入状态：只读 / 未配置令牌')).toBeVisible();
    expect(screen.queryByRole('textbox', { name: /reviewer/i })).not.toBeInTheDocument();
  });

  it('opens the individual stock workspace from the review universe table', async () => {
    render(<AppShell />);
    await screen.findByRole('heading', { name: '科技卡脖子复盘' });

    const table = within(screen.getByRole('table', { name: '科技卡脖子复盘股票表' }));
    expect(table.getByRole('columnheader', { name: '股票代码' })).toBeVisible();
    expect(table.getByRole('columnheader', { name: '股票名称' })).toBeVisible();
    expect(table.queryByRole('button', { name: '打开 中核科技 个股复盘工作台' })).not.toBeInTheDocument();

    const row = screen.getByRole('row', { name: /000777 中核科技/ });
    expect(row).toHaveClass('tech-bottleneck-clickable-row');
    fireEvent.click(row);

    expect(window.location.pathname).toBe('/tech-bottleneck/stock/000777');
    expect(screen.getByText('Stock')).toBeVisible();
  });

  it('passes enriched report scores through the review universe stock handoff', async () => {
    render(<AppShell />);
    await screen.findByRole('heading', { name: '科技卡脖子复盘' });

    fireEvent.click(screen.getByRole('row', { name: /002028 思源电气/ }));

    expect(window.location.pathname).toBe('/tech-bottleneck/stock/002028');
    expect(screen.getByText('bottleneck_confidence_score 55')).toBeVisible();
    expect(screen.getByText('evidence_quality_score 23')).toBeVisible();
  });

  it('prefers review-universe enriched semantics over legacy candidate metadata in stock handoff', async () => {
    apiMocks.fetchTechBottleneckReviewUniverseStocks.mockResolvedValueOnce({
      total: 1,
      limit: 500,
      offset: 0,
      items: [
        {
          stock_code: '000049',
          stock_name: '德赛电池',
          review_universe_source: 'tech_bottleneck_review_universe_frontend_dataset_v1',
          current_layer_status: 'pending_review',
          manual_approval_status: 'pending',
          frontend_review_status: 'pending_review',
          evidence_count: 48,
          page_citation_count: 18,
          source_pdf_count: 3,
          primary_source_supported: true,
          hard_tech_domain: 'supported',
          supply_chain_role_hint: 'supported',
          business_relevance_hint: 'supported',
          bottleneck_or_chokepoint_hint: 'supported',
          concept_pollution_risk: 'low',
          route_around_or_substitution_risk: 'needs_manual_review',
          value_capture_risk: 'needs_manual_review',
          disconfirmation_trigger: false,
          next_primary_source_to_check: 'manual review and evidence backfill',
          strongest_primary_source_claim: '德赛电池在能源与电力电子关键环节具备充分证据。',
          weakest_or_riskiest_claim: '需继续回填页级证据映射。',
          evidence_summary_for_review: 'evidence=48; page_citations=18; sources=3',
          industry: '电气机械和器材制造业',
          concept_tags: '能源与电力电子关键环节 / 电网 / 能源基础设施 / 瓶颈环节 / 潜在标准等价质量层',
          evidence_strength: '充分',
          bottleneck_relevance: '核心瓶颈',
          source_group: '',
          previous_tier: '',
          bottleneck_confidence_score: 88,
          evidence_quality_score: 62,
          review_status: '待复盘',
          reviewer_decision: '',
          reviewer_note: '',
          used_for_signal: false,
          used_for_admission: false,
          auto_added_to_quality_pool: false
        }
      ]
    });

    render(<AppShell />);
    await screen.findByRole('heading', { name: '科技卡脖子复盘' });

    fireEvent.click(screen.getByRole('row', { name: /000049 德赛电池/ }));

    expect(window.location.pathname).toBe('/tech-bottleneck/stock/000049');
    expect(screen.getByText('bottleneck_confidence_score 88')).toBeVisible();
    expect(screen.getByText('evidence_quality_score 62')).toBeVisible();
    expect(screen.getByText('bottleneck_relevance 核心瓶颈')).toBeVisible();
    expect(screen.getByText('evidence_strength 充分')).toBeVisible();
  });

  it('re-hydrates review-universe stock context from the read model on direct stock routes', async () => {
    apiMocks.fetchTechBottleneckReviewUniverseStock.mockResolvedValueOnce({
      stock_code: '000049',
      stock_name: '德赛电池',
      review_universe_source: 'tech_bottleneck_review_universe_frontend_dataset_v1',
      current_layer_status: 'pending_review',
      manual_approval_status: 'pending',
      frontend_review_status: 'pending_review',
      evidence_count: 48,
      page_citation_count: 18,
      source_pdf_count: 3,
      primary_source_supported: true,
      hard_tech_domain: 'supported',
      supply_chain_role_hint: 'supported',
      business_relevance_hint: 'supported',
      bottleneck_or_chokepoint_hint: 'supported',
      concept_pollution_risk: 'low',
      route_around_or_substitution_risk: 'needs_manual_review',
      value_capture_risk: 'needs_manual_review',
      disconfirmation_trigger: false,
      next_primary_source_to_check: 'manual review and evidence backfill',
      strongest_primary_source_claim: '德赛电池在能源与电力电子关键环节具备充分证据。',
      weakest_or_riskiest_claim: '需继续回填页级证据映射。',
      evidence_summary_for_review: 'evidence=48; page_citations=18; sources=3',
      industry: '电气机械和器材制造业',
      concept_tags: '能源与电力电子关键环节 / 电网 / 能源基础设施 / 瓶颈环节 / 潜在标准等价质量层',
      evidence_strength: '充分',
      bottleneck_relevance: '核心瓶颈',
      source_group: '',
      previous_tier: '',
      bottleneck_confidence_score: 88,
      evidence_quality_score: 62,
      review_status: '待复盘',
      reviewer_decision: '',
      reviewer_note: '',
      used_for_signal: false,
      used_for_admission: false,
      auto_added_to_quality_pool: false
    });

    window.history.pushState({}, '', '/tech-bottleneck/stock/000049?source=tech_bottleneck_review_universe_frontend_dataset_v1');

    render(<AppShell />);

    expect(await screen.findByText('bottleneck_confidence_score 88')).toBeVisible();
    expect(screen.getByText('evidence_quality_score 62')).toBeVisible();
    expect(screen.getByText('bottleneck_relevance 核心瓶颈')).toBeVisible();
    expect(screen.getByText('evidence_strength 充分')).toBeVisible();
  });

  it('shows writable status when a dashboard write token is configured', async () => {
    window.localStorage.setItem('dashboardWriteToken', 'secret');
    render(<AppShell />);
    await screen.findByRole('heading', { name: '科技卡脖子复盘' });

    fireEvent.click(screen.getByRole('button', { name: '查看证据 000777' }));

    expect(await screen.findByText('写入状态：可写 / 已配置令牌')).toBeVisible();
  });

  it('records a manual overlay decision from the detail panel and refreshes read models', async () => {
    render(<AppShell />);
    await screen.findByRole('heading', { name: '科技卡脖子复盘' });

    fireEvent.click(screen.getByRole('button', { name: '查看证据 000777' }));
    const manualDecision = await screen.findByRole('region', { name: '000777 人工复盘决策' });
    fireEvent.change(within(manualDecision).getByLabelText('复盘备注'), {
      target: { value: '需要补充收入占比、客户验证和核心环节一手证据。' }
    });
    fireEvent.click(within(manualDecision).getByLabelText('已核验证据'));
    fireEvent.click(within(manualDecision).getByRole('button', { name: '需更多证据' }));

    expect(apiMocks.createTechBottleneckReviewUniverseDecision).toHaveBeenCalledWith({
      stock_code: '000777',
      stock_name: '中核科技',
      reviewer_decision: 'need_more_evidence',
      reviewer: 'operator',
      review_comment: '需要补充收入占比、客户验证和核心环节一手证据。',
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
      evidence_checked: true,
      source_context: {
        from: 'tech_bottleneck_review_universe_page',
        page_route: '/research/tech-bottleneck/review-universe'
      }
    });
    expect(await screen.findByText('人工复盘已记录：需更多证据')).toBeVisible();
    expect(apiMocks.fetchTechBottleneckReviewUniverseStocks).toHaveBeenCalledTimes(2);
    expect(apiMocks.fetchTechBottleneckReviewUniverseDecisionSummary).toHaveBeenCalledTimes(2);
  });
});
