import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ThemeResearchWorkspace } from '../src/components/ThemeResearchWorkspace';

const apiMocks = vi.hoisted(() => ({
  fetchThemeResearchThemes: vi.fn(),
  fetchThemeResearchTheme: vi.fn(),
  fetchThemeResearchNodes: vi.fn(),
  fetchThemeResearchSources: vi.fn(),
  fetchThemeResearchClaims: vi.fn(),
  fetchThemeResearchCompanies: vi.fn()
}));

vi.mock('../src/api/themeResearch', () => apiMocks);

const theme = {
  theme_id: 'ai_power_value_capture_v1',
  theme_name: 'AI供电产业链：谁在拿走价值量',
  theme_type: 'ai_power',
  summary: 'AI 数据中心供电深度研究。',
  status: 'reviewed',
  created_from: 'mixed',
  last_updated: '2026-07-14',
  research_only: true,
  used_for_signal: false,
  used_for_admission: false
};

const nodes = [
  {
    theme_id: theme.theme_id,
    node_id: 'liquid_cooling',
    node_name: '液冷系统',
    node_type: 'subsystem',
    parent_node_id: '',
    description: '高密度机柜的热管理环节。',
    value_capture_score: 4,
    bottleneck_score: 3,
    localization_gap_score: 2,
    supply_tightness_score: 3,
    evidence_strength: 4,
    node_review_status: 'reviewed',
    priority_score: 78,
    priority_band: 'high',
    priority_class: 'deep_research_priority',
    recommended_action: 'deep_node_research',
    rationale_codes: [],
    research_only: true,
    used_for_signal: false,
    used_for_admission: false
  }
];

const sources = [
  {
    theme_id: theme.theme_id,
    source_id: 'source_1',
    source_type: 'company_filing',
    title: '英维克2025年年度报告',
    publisher: '英维克',
    author: '',
    publish_date: '2026-04-21',
    url_or_ref: 'https://example.com/report.pdf',
    access_level: 'public',
    reliability_level: 'S0',
    review_status: 'accepted',
    notes: '',
    claim_count: 2,
    claim_ids: ['catalyst_1', 'risk_1'],
    research_only: true,
    used_for_signal: false,
    used_for_admission: false
  }
];

const claims = [
  {
    theme_id: theme.theme_id,
    claim_id: 'catalyst_1',
    source_id: 'source_1',
    claim_text: '高密度算力提升液冷和高效供电需求。',
    claim_type: 'catalyst',
    confidence: 0.9,
    evidence_status: 'verified',
    platform_use_status: 'reviewed',
    supporting_source_ids: [],
    supporting_sources: [],
    affected_theme_nodes: ['liquid_cooling'],
    source_title: '英维克2025年年度报告',
    source_reliability_level: 'S0',
    source_review_status: 'accepted',
    research_only: true,
    used_for_signal: false,
    used_for_admission: false
  },
  {
    theme_id: theme.theme_id,
    claim_id: 'risk_1',
    source_id: 'source_1',
    claim_text: '项目建设延迟会推迟设备需求兑现。',
    claim_type: 'risk',
    confidence: 0.8,
    evidence_status: 'partially_verified',
    platform_use_status: 'draft',
    supporting_source_ids: [],
    supporting_sources: [],
    affected_theme_nodes: ['liquid_cooling'],
    source_title: '英维克2025年年度报告',
    source_reliability_level: 'S0',
    source_review_status: 'accepted',
    research_only: true,
    used_for_signal: false,
    used_for_admission: false
  }
];

function company(mappingId: string, name: string, tier: string, code: string) {
  return {
    theme_id: theme.theme_id,
    mapping_id: mappingId,
    company_code: code,
    company_name: name,
    market: 'CN',
    mapped_node_id: 'liquid_cooling',
    mapping_type: 'direct_product',
    business_stage: 'primary_business',
    confidence: 0.9,
    evidence_ids: ['evidence_1'],
    revenue_relevance: 'meaningful',
    bottleneck_relevance: 'core',
    business_materiality: 'meaningful_segment',
    product_or_service: '数据中心液冷产品',
    relationship_summary: '公司直接提供液冷产品并通过该节点受益。',
    review_status: tier === 'concept_association' ? 'draft' : 'reviewed',
    notes: '',
    mapped_node: { node_id: 'liquid_cooling', node_name: '液冷系统', evidence_strength: 4 },
    company_research_priority_score: 80,
    company_relevance_score: 4,
    business_materiality_score: 4,
    priority_band: 'high',
    recommended_action: 'company_deep_research',
    rationale_codes: [],
    integration_status: 'linked_existing_universe',
    integration_ref: code,
    existing_review_context: { status: 'pending_review', reviewer_decision: '' },
    tech_bottleneck_stock_path: `/tech-bottleneck/stock/${code}?source=theme_research`,
    beneficiary_tier: tier,
    mapping_evidence: [
      {
        evidence_id: 'evidence_1', evidence_type: 'product_relationship', evidence_summary: '年报披露直接产品关系。',
        excerpt_locator: 'p9', related_company_codes: [code], related_node_ids: ['liquid_cooling'],
        source: sources[0]
      }
    ],
    research_only: true,
    used_for_signal: false,
    used_for_admission: false
  };
}

const companies = [
  company('core_1', '核心公司', 'core_beneficiary', '000001.SZ'),
  company('elastic_1', '弹性公司', 'elastic_beneficiary', '000002.SZ'),
  company('indirect_1', '间接公司', 'indirect_beneficiary', '000003.SZ'),
  company('concept_1', '概念公司', 'concept_association', '000004.SZ')
];

const detail = {
  theme,
  node_summary: { total: 1, by_priority_class: { deep_research_priority: 1 }, by_review_status: { reviewed: 1 } },
  source_summary: { total: 1, by_review_status: { accepted: 1 } },
  claim_summary: { total: 2, by_platform_use_status: { reviewed: 1, draft: 1 } },
  company_summary: { total: 4, by_priority_band: { high: 4 }, by_integration_status: { linked_existing_universe: 4 } },
  evidence_gap_summary: { total: 1, by_priority_band: { high: 1 } },
  source_reliability_distribution: { S0: 1 },
  claim_evidence_status_distribution: { verified: 1, partially_verified: 1 },
  review_queue_action_distribution: {},
  top_node_priorities: nodes,
  evidence_gaps: nodes,
  top_company_priorities: companies,
  catalog_context: {
    chain_id: 'ai_data_center_power', chain_name: 'AI Data Center Power', sector_id: 'energy',
    catalog_route: '/theme-research/catalog/ai_data_center_power'
  },
  research_profile: {
    catalog_chain_id: 'ai_data_center_power',
    research_kind: 'industry_chain_deep_research',
    industry_stage: 'commercial_scaling',
    central_conflict: '算力密度提升速度快于传统供电与散热架构升级。',
    investment_summary: '价值量从传统机房设备向高效供电、液冷和系统交付迁移。',
    value_flow_summary: '电网接入 → UPS/HVDC → 机架配电 → 服务器电源 → 液冷 → 运维',
    profit_pool_summary: '认证、可靠性、系统集成和持续运维构成主要壁垒。',
    catalyst_claim_ids: ['catalyst_1'],
    risk_claim_ids: ['risk_1'],
    validation_signals: ['机柜功率密度', '液冷订单', '数据中心资本开支'],
    evidence_gap_summary: '部分公司尚未披露 AI 数据中心收入占比。'
  },
  beneficiary_summary: {
    total: 4,
    by_tier: { core_beneficiary: 1, elastic_beneficiary: 1, indirect_beneficiary: 1, concept_association: 1 },
    reviewed_beneficiary_count: 3
  },
  research_only: true,
  used_for_signal: false,
  used_for_admission: false
};

describe('deep industry-chain Theme Research overview', () => {
  beforeEach(() => {
    apiMocks.fetchThemeResearchThemes.mockReset().mockResolvedValue({
      total: 1,
      items: [
        {
          ...theme,
          research_kind: 'industry_chain_deep_research',
          catalog_context: detail.catalog_context,
          node_count: 1,
          source_count: 1,
          claim_count: 2,
          company_count: 4,
          evidence_gap_count: 1,
          deep_research_node_count: 1,
          review_queue_count: 1
        }
      ]
    });
    apiMocks.fetchThemeResearchTheme.mockReset().mockResolvedValue(detail);
    apiMocks.fetchThemeResearchNodes.mockReset().mockResolvedValue({ total: nodes.length, items: nodes });
    apiMocks.fetchThemeResearchSources.mockReset().mockResolvedValue({ total: sources.length, items: sources });
    apiMocks.fetchThemeResearchClaims.mockReset().mockResolvedValue({ total: claims.length, items: claims });
    apiMocks.fetchThemeResearchCompanies.mockReset().mockResolvedValue({ total: companies.length, items: companies });
  });

  afterEach(() => cleanup());

  it('identifies selected records as industry-chain deep research in the theme index', async () => {
    render(<ThemeResearchWorkspace pathname="/theme-research" onNavigate={vi.fn()} onOpenStock={vi.fn()} />);

    expect(await screen.findByText('产业链深度研究')).toBeInTheDocument();
    expect(screen.getByText('AI Data Center Power')).toBeInTheDocument();
  });

  it('renders the seven readable research sections from one deep theme route', async () => {
    render(<ThemeResearchWorkspace pathname="/theme-research/ai_power_value_capture_v1" onNavigate={vi.fn()} onOpenStock={vi.fn()} />);

    expect(await screen.findByRole('heading', { name: '研究结论' })).toBeInTheDocument();
    for (const name of ['价值链', '利润池与竞争壁垒', '催化、验证信号与风险', '受益公司', '来源证据', '证据缺口与更新']) {
      expect(screen.getByRole('heading', { name })).toBeInTheDocument();
    }
    expect(screen.getByText(detail.research_profile.value_flow_summary)).toBeInTheDocument();
    expect(screen.getByText(claims[0].claim_text)).toBeInTheDocument();
    expect(screen.getByText(sources[0].title)).toBeInTheDocument();
  });

  it('keeps concept associations out of the default beneficiary list and supports tier filters', async () => {
    render(<ThemeResearchWorkspace pathname="/theme-research/ai_power_value_capture_v1" onNavigate={vi.fn()} onOpenStock={vi.fn()} />);

    const section = await screen.findByRole('region', { name: '受益公司' });
    expect(within(section).getByText('核心公司')).toBeInTheDocument();
    expect(within(section).getByText('弹性公司')).toBeInTheDocument();
    expect(within(section).getByText('间接公司')).toBeInTheDocument();
    expect(within(section).queryByText('概念公司')).not.toBeInTheDocument();

    fireEvent.click(within(section).getByRole('button', { name: '概念关联' }));
    expect(within(section).getByText('概念公司')).toBeInTheDocument();
    expect(within(section).queryByText('核心公司')).not.toBeInTheDocument();
  });

  it('opens a reviewed beneficiary in the existing Stock Workspace route', async () => {
    const onOpenStock = vi.fn();
    render(<ThemeResearchWorkspace pathname="/theme-research/ai_power_value_capture_v1" onNavigate={vi.fn()} onOpenStock={onOpenStock} />);

    const section = await screen.findByRole('region', { name: '受益公司' });
    fireEvent.click(within(section).getByRole('button', { name: '打开核心公司个股工作台' }));
    expect(onOpenStock).toHaveBeenCalledWith('/tech-bottleneck/stock/000001.SZ?source=theme_research');
  });
});
