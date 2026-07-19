import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ThemeResearchWorkspace } from '../src/components/ThemeResearchWorkspace';

const payload = vi.hoisted(() => ({
  themes: {
    total: 2,
    items: [
      {
        theme_id: 'ai_power_value_capture_v1',
        theme_name: 'AI供电产业链：谁在拿走价值量',
        theme_type: 'ai_power',
        summary: '从算力需求到供电瓶颈与价值量。',
        status: 'draft',
        created_from: 'mixed',
        last_updated: '2026-07-10',
        node_count: 13,
        source_count: 10,
        claim_count: 8,
        company_count: 4,
        evidence_gap_count: 3,
        deep_research_node_count: 2,
        review_queue_count: 9,
        research_only: true,
        used_for_signal: false,
        used_for_admission: false
      },
      {
        theme_id: 'humanoid_robotics_head_to_toe_v1',
        theme_name: '人形机器人从头到脚拆解',
        theme_type: 'humanoid_robotics',
        summary: '从人体结构到核心零部件。',
        status: 'draft',
        created_from: 'mixed',
        last_updated: '2026-07-10',
        node_count: 21,
        source_count: 7,
        claim_count: 4,
        company_count: 0,
        evidence_gap_count: 12,
        deep_research_node_count: 0,
        review_queue_count: 12,
        research_only: true,
        used_for_signal: false,
        used_for_admission: false
      }
    ]
  },
  detail: {
    theme: {
      theme_id: 'ai_power_value_capture_v1',
      theme_name: 'AI供电产业链：谁在拿走价值量',
      theme_type: 'ai_power',
      summary: '从算力需求到供电瓶颈与价值量。',
      status: 'draft',
      created_from: 'mixed',
      last_updated: '2026-07-10',
      research_only: true,
      used_for_signal: false,
      used_for_admission: false
    },
    node_summary: {
      total: 13,
      by_priority_class: { deep_research_priority: 2, evidence_collection_priority: 3, monitor: 8 },
      by_review_status: { draft: 1, needs_evidence: 8, reviewed: 4 }
    },
    source_summary: { total: 10, by_review_status: { accepted: 7, lead_only: 2, needs_full_text: 1 } },
    claim_summary: { total: 8, by_platform_use_status: { draft: 3, research_lead: 5 } },
    company_summary: {
      total: 4,
      by_priority_band: { high: 3, medium: 1 },
      by_integration_status: { coverage_gap: 2, linked_existing_universe: 2 }
    },
    evidence_gap_summary: { total: 3, by_priority_band: { high: 1, medium: 2 } },
    source_reliability_distribution: { S1: 7, S2: 1, S3: 1, S4: 1 },
    claim_evidence_status_distribution: { verified: 2, partially_verified: 3, contradicted: 2, unverified: 1 },
    review_queue_action_distribution: { collect_node_evidence: 3, deep_node_research: 2 },
    top_node_priorities: [
      {
        theme_id: 'ai_power_value_capture_v1',
        node_id: 'liquid_cooling',
        node_name: '液冷',
        node_type: 'infrastructure',
        parent_node_id: '',
        description: '数据中心液冷系统。',
        value_capture_score: 4,
        bottleneck_score: 4,
        localization_gap_score: 3,
        supply_tightness_score: 3,
        evidence_strength: 4,
        node_review_status: 'reviewed',
        priority_score: 77,
        priority_band: 'high',
        priority_class: 'deep_research_priority',
        recommended_action: 'deep_node_research',
        rationale_codes: ['high_value_capture', 'high_bottleneck'],
        research_only: true,
        used_for_signal: false,
        used_for_admission: false
      }
    ],
    evidence_gaps: [],
    top_company_priorities: [],
    research_only: true,
    used_for_signal: false,
    used_for_admission: false
  },
  nodes: {
    total: 2,
    items: [
      {
        theme_id: 'ai_power_value_capture_v1',
        node_id: 'transformer',
        node_name: '变压器',
        node_type: 'equipment',
        parent_node_id: 'grid_connection',
        description: '电压转换与容量扩张。',
        value_capture_score: 4,
        bottleneck_score: 4,
        localization_gap_score: 2,
        supply_tightness_score: 4,
        evidence_strength: 2,
        node_review_status: 'needs_evidence',
        priority_score: 73,
        priority_band: 'medium',
        priority_class: 'evidence_collection_priority',
        recommended_action: 'collect_node_evidence',
        rationale_codes: ['high_value_capture', 'high_bottleneck', 'low_evidence'],
        research_only: true,
        used_for_signal: false,
        used_for_admission: false
      },
      {
        theme_id: 'ai_power_value_capture_v1',
        node_id: 'liquid_cooling',
        node_name: '液冷',
        node_type: 'infrastructure',
        parent_node_id: '',
        description: '数据中心液冷系统。',
        value_capture_score: 4,
        bottleneck_score: 4,
        localization_gap_score: 3,
        supply_tightness_score: 3,
        evidence_strength: 4,
        node_review_status: 'reviewed',
        priority_score: 77,
        priority_band: 'high',
        priority_class: 'deep_research_priority',
        recommended_action: 'deep_node_research',
        rationale_codes: ['strong_evidence'],
        research_only: true,
        used_for_signal: false,
        used_for_admission: false
      }
    ]
  },
  sources: {
    total: 2,
    items: [
      {
        theme_id: 'ai_power_value_capture_v1',
        source_id: 'ai_power_doe_data_center_demand_2024',
        source_type: 'official_report',
        title: 'Data Centers and Electricity Demand',
        publisher: 'US DOE',
        author: 'DOE',
        publish_date: '2024-12-01',
        url_or_ref: 'https://example.com/doe',
        access_level: 'public',
        reliability_level: 'S1',
        review_status: 'accepted',
        notes: '',
        claim_count: 2,
        claim_ids: ['claim-demand', 'claim-grid'],
        research_only: true,
        used_for_signal: false,
        used_for_admission: false
      },
      {
        theme_id: 'ai_power_value_capture_v1',
        source_id: 'ai_power_video_claim_lead',
        source_type: 'video_claim',
        title: '老郑说AI前瞻口播线索',
        publisher: '短视频平台',
        author: '老郑说AI前瞻',
        publish_date: '',
        url_or_ref: 'manual-ref',
        access_level: 'unknown',
        reliability_level: 'S4',
        review_status: 'lead_only',
        notes: '仅作为线索',
        claim_count: 1,
        claim_ids: ['claim-video'],
        research_only: true,
        used_for_signal: false,
        used_for_admission: false
      }
    ]
  },
  claims: {
    total: 1,
    items: [
      {
        theme_id: 'ai_power_value_capture_v1',
        claim_id: 'claim-video',
        source_id: 'ai_power_video_claim_lead',
        claim_text: '供电环节可能重新分配价值量。',
        claim_type: 'value_capture',
        confidence: 0.4,
        evidence_status: 'unverified',
        platform_use_status: 'research_lead',
        supporting_source_ids: ['ai_power_doe_data_center_demand_2024'],
        supporting_sources: [
          {
            source_id: 'ai_power_doe_data_center_demand_2024',
            title: 'Data Centers and Electricity Demand',
            reliability_level: 'S1',
            review_status: 'accepted'
          }
        ],
        affected_theme_nodes: ['server_power_supply'],
        source_title: '老郑说AI前瞻口播线索',
        source_reliability_level: 'S4',
        source_review_status: 'lead_only',
        research_only: true,
        used_for_signal: false,
        used_for_admission: false
      }
    ]
  },
  companies: {
    total: 2,
    items: [
      {
        theme_id: 'ai_power_value_capture_v1',
        mapping_id: 'mapping-envicool',
        company_code: '002837.SZ',
        company_name: '英维克',
        market: 'CN',
        mapped_node_id: 'liquid_cooling',
        mapping_type: 'direct_product',
        business_stage: 'primary_business',
        confidence: 0.94,
        evidence_ids: ['evidence-1'],
        revenue_relevance: 'undisclosed',
        bottleneck_relevance: 'core',
        business_materiality: 'emerging_segment',
        product_or_service: '液冷产品和交付',
        relationship_summary: '直接映射液冷节点。',
        review_status: 'reviewed',
        notes: '',
        mapped_node: { node_id: 'liquid_cooling', node_name: '液冷', evidence_strength: 4 },
        company_research_priority_score: 78.8,
        company_relevance_score: 4.7,
        business_materiality_score: 3,
        priority_band: 'high',
        recommended_action: 'deep_company_research',
        rationale_codes: ['high_company_relevance'],
        integration_status: 'linked_existing_universe',
        integration_ref: 'crosswalk-1',
        existing_review_context: { status: 'pending_review', reviewer_decision: '' },
        tech_bottleneck_stock_path: '/tech-bottleneck/stock/002837.SZ?source=theme_research',
        research_only: true,
        used_for_signal: false,
        used_for_admission: false
      },
      {
        theme_id: 'ai_power_value_capture_v1',
        mapping_id: 'mapping-ollu',
        company_code: '300870.SZ',
        company_name: '欧陆通',
        market: 'CN',
        mapped_node_id: 'server_power_supply',
        mapping_type: 'direct_product',
        business_stage: 'primary_business',
        confidence: 0.98,
        evidence_ids: ['evidence-2'],
        revenue_relevance: 'meaningful',
        bottleneck_relevance: 'core',
        business_materiality: 'meaningful_segment',
        product_or_service: '服务器电源',
        relationship_summary: '直接映射服务器电源。',
        review_status: 'reviewed',
        notes: '',
        mapped_node: { node_id: 'server_power_supply', node_name: '服务器电源', evidence_strength: 2 },
        company_research_priority_score: 75.6,
        company_relevance_score: 4.9,
        business_materiality_score: 4,
        priority_band: 'high',
        recommended_action: 'review_crosswalk_coverage_gap',
        rationale_codes: ['crosswalk_coverage_gap'],
        integration_status: 'coverage_gap',
        integration_ref: 'gap-1',
        existing_review_context: { status: 'not_in_existing_universe', reviewer_decision: '' },
        tech_bottleneck_stock_path: '/tech-bottleneck/stock/300870.SZ?source=theme_research',
        research_only: true,
        used_for_signal: false,
        used_for_admission: false
      }
    ]
  }
}));

const api = vi.hoisted(() => ({
  fetchThemeResearchThemes: vi.fn(),
  fetchThemeResearchTheme: vi.fn(),
  fetchThemeResearchNodes: vi.fn(),
  fetchThemeResearchSources: vi.fn(),
  fetchThemeResearchClaims: vi.fn(),
  fetchThemeResearchCompanies: vi.fn()
}));

vi.mock('../src/api/themeResearch', () => api);

describe('ThemeResearchWorkspace', () => {
  beforeEach(() => {
    api.fetchThemeResearchThemes.mockResolvedValue(payload.themes);
    api.fetchThemeResearchTheme.mockResolvedValue(payload.detail);
    api.fetchThemeResearchNodes.mockResolvedValue(payload.nodes);
    api.fetchThemeResearchSources.mockResolvedValue(payload.sources);
    api.fetchThemeResearchClaims.mockResolvedValue(payload.claims);
    api.fetchThemeResearchCompanies.mockResolvedValue(payload.companies);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('shows the theme index and opens a theme overview', async () => {
    const navigate = vi.fn();
    render(<ThemeResearchWorkspace pathname="/theme-research" onNavigate={navigate} onOpenStock={vi.fn()} />);

    expect(await screen.findByRole('heading', { name: '主题研究' })).toBeInTheDocument();
    expect(screen.getByText('2 个主题')).toBeInTheDocument();
    expect(screen.getByText('13')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /AI供电产业链：谁在拿走价值量/ }));

    expect(navigate).toHaveBeenCalledWith('/theme-research/ai_power_value_capture_v1');
  });

  it('renders the nodes route with evidence and priority states', async () => {
    render(
      <ThemeResearchWorkspace
        pathname="/theme-research/ai_power_value_capture_v1/nodes"
        onNavigate={vi.fn()}
        onOpenStock={vi.fn()}
      />
    );

    expect(await screen.findByRole('heading', { name: 'AI供电产业链：谁在拿走价值量' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '产业链节点' })).toHaveAttribute('aria-selected', 'true');
    const transformerRow = screen.getByRole('row', { name: /变压器/ });
    expect(within(transformerRow).getByText('证据补齐优先')).toBeInTheDocument();
    expect(within(transformerRow).getByText('待补证据')).toBeInTheDocument();
    expect(within(transformerRow).getByText('73')).toBeInTheDocument();
  });

  it('separates sources from extracted claims on the sources route', async () => {
    render(
      <ThemeResearchWorkspace
        pathname="/theme-research/ai_power_value_capture_v1/sources"
        onNavigate={vi.fn()}
        onOpenStock={vi.fn()}
      />
    );

    expect(await screen.findByRole('heading', { name: '来源证据' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '来源清单' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '观点与证据状态' })).toBeInTheDocument();
    expect(screen.getAllByText('S4').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('仅作线索').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('未验证')).toBeInTheDocument();
    expect(screen.getByText('公开')).toBeInTheDocument();
    expect(screen.getAllByText('Data Centers and Electricity Demand').length).toBeGreaterThanOrEqual(2);
  });

  it('shows coverage gaps and opens mapped companies in the existing stock workflow', async () => {
    const openStock = vi.fn();
    render(
      <ThemeResearchWorkspace
        pathname="/theme-research/ai_power_value_capture_v1/companies"
        onNavigate={vi.fn()}
        onOpenStock={openStock}
      />
    );

    expect(await screen.findByRole('heading', { name: '公司映射' })).toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: '操作' })).not.toBeInTheDocument();
    const olluRow = screen.getByRole('row', { name: /欧陆通/ });
    expect(within(olluRow).getByText('覆盖缺口')).toBeInTheDocument();
    expect(within(olluRow).queryByRole('button', { name: '打开欧陆通个股工作台' })).not.toBeInTheDocument();
    fireEvent.click(olluRow);

    expect(openStock).toHaveBeenCalledWith('/tech-bottleneck/stock/300870.SZ?source=theme_research');
  });

  it('shows a retryable error without stale theme content', async () => {
    api.fetchThemeResearchThemes.mockRejectedValueOnce(new Error('network unavailable'));
    const { rerender } = render(
      <ThemeResearchWorkspace pathname="/theme-research" onNavigate={vi.fn()} onOpenStock={vi.fn()} />
    );

    expect(await screen.findByRole('alert')).toHaveTextContent('主题研究加载失败');
    api.fetchThemeResearchThemes.mockResolvedValueOnce(payload.themes);
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    rerender(<ThemeResearchWorkspace pathname="/theme-research" onNavigate={vi.fn()} onOpenStock={vi.fn()} />);

    expect(await screen.findByText('2 个主题')).toBeInTheDocument();
  });

  it('shows explicit empty and not-found states', async () => {
    api.fetchThemeResearchCompanies.mockResolvedValueOnce({ total: 0, items: [] });
    const { unmount } = render(
      <ThemeResearchWorkspace
        pathname="/theme-research/humanoid_robotics_head_to_toe_v1/companies"
        onNavigate={vi.fn()}
        onOpenStock={vi.fn()}
      />
    );

    expect(await screen.findByText('当前主题还没有公司映射。')).toBeInTheDocument();
    unmount();

    api.fetchThemeResearchTheme.mockRejectedValueOnce(new Error('theme_not_found'));
    render(
      <ThemeResearchWorkspace pathname="/theme-research/missing-theme" onNavigate={vi.fn()} onOpenStock={vi.fn()} />
    );
    expect(await screen.findByRole('heading', { name: '主题不存在' })).toBeInTheDocument();
  });

  it('shows evidence gaps and priority companies on the overview', async () => {
    api.fetchThemeResearchTheme.mockResolvedValueOnce({
      ...payload.detail,
      evidence_gaps: [payload.nodes.items[0]],
      top_company_priorities: [payload.companies.items[1]]
    });
    render(
      <ThemeResearchWorkspace
        pathname="/theme-research/ai_power_value_capture_v1"
        onNavigate={vi.fn()}
        onOpenStock={vi.fn()}
      />
    );

    expect(await screen.findByRole('heading', { name: '待补证据缺口' })).toBeInTheDocument();
    expect(screen.getByText('变压器')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '重点公司' })).toBeInTheDocument();
    expect(screen.getByText('欧陆通')).toBeInTheDocument();
    expect(screen.getByText('覆盖缺口')).toBeInTheDocument();
  });
});
