import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { ThemeResearchContextSection } from '../src/components/stock-workspace/ThemeResearchContextSection';
import type { AssetThemeResearchContext } from '../src/api/types';

function reviewedContext(): AssetThemeResearchContext {
  return {
    asset_id: 'CN:SZ:002837',
    company_code: '002837.SZ',
    status: 'reviewed_context_available',
    driver_assessment: 'mixed_or_uncertain',
    theme_count: 1,
    mapping_count: 1,
    evidence_gap_count: 0,
    themes: [
      {
        theme_id: 'ai_power_value_capture_v1',
        theme_name: 'AI供电产业链',
        theme_type: 'ai_power',
        summary: 'AI power delivery chain',
        status: 'draft',
        dashboard_path: '/theme-research/ai_power_value_capture_v1',
        research_only: true,
        used_for_signal: false,
        used_for_admission: false
      }
    ],
    mappings: [
      {
        mapping_id: 'ai_power_liquid_cooling_002837_v1',
        theme_id: 'ai_power_value_capture_v1',
        company_code: '002837.SZ',
        company_name: '英维克',
        mapping_type: 'direct_product',
        confidence: 0.94,
        revenue_relevance: 'undisclosed',
        bottleneck_relevance: 'core',
        business_materiality: 'emerging_segment',
        business_stage: 'primary_business',
        product_or_service: '液冷系统',
        relationship_summary: '直接供应数据中心液冷产品。',
        review_status: 'reviewed',
        node: {
          node_id: 'liquid_cooling',
          theme_id: 'ai_power_value_capture_v1',
          parent_node_id: 'ai_server_integration',
          node_name: '液冷',
          node_type: 'subsystem',
          description: '高密度机柜液冷。',
          value_capture_score: 5,
          bottleneck_score: 4,
          localization_gap_score: 3,
          supply_tightness_score: 4,
          evidence_strength: 3,
          node_review_status: 'reviewed'
        },
        evidence_items: [
          {
            evidence_id: 'evidence-1',
            source_id: 'source-1',
            evidence_type: 'product_relationship',
            excerpt_locator: 'annual report p9',
            evidence_summary: '主营业务覆盖液冷产品。',
            related_company_codes: ['002837.SZ'],
            related_node_ids: ['liquid_cooling'],
            source: {
              source_id: 'source-1',
              source_type: 'company_filing',
              title: '2025年年度报告',
              publisher: '英维克',
              publish_date: '2026-03-30',
              url_or_ref: 'https://example.com/report',
              access_level: 'public',
              reliability_level: 'S0',
              review_status: 'accepted'
            }
          }
        ],
        reviewed_claims: [],
        company_relevance_score: 4.7,
        company_research_priority_score: 78.8,
        priority_band: 'high',
        recommended_action: 'deep_company_research',
        research_only: true,
        used_for_signal: false,
        used_for_admission: false
      }
    ],
    excluded_mappings: [],
    research_only: true,
    used_for_signal: false,
    used_for_admission: false,
    source: 'research.theme_research_company_mapping',
    warnings: []
  };
}

afterEach(() => cleanup());

describe('ThemeResearchContextSection', () => {
  it('shows reviewed theme, node scores, evidence and guardrails', () => {
    render(<ThemeResearchContextSection context={reviewedContext()} />);

    expect(screen.getByRole('heading', { name: '主题研究' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'AI供电产业链' })).toHaveAttribute(
      'href',
      '/theme-research/ai_power_value_capture_v1'
    );
    expect(screen.getByText('液冷')).toBeInTheDocument();
    expect(screen.getByText('价值量 5/5')).toBeInTheDocument();
    expect(screen.getByText('卡脖子 4/5')).toBeInTheDocument();
    expect(screen.getByText('证据 1 条 · 已审核观点 0 条')).toBeInTheDocument();
    expect(screen.getByText('仅用于研究，不参与评分、信号或准入')).toBeInTheDocument();
  });

  it('distinguishes evidence gaps, no mapping and unavailable context', () => {
    const { rerender } = render(
      <ThemeResearchContextSection
        context={{
          ...reviewedContext(),
          status: 'evidence_gap',
          mappings: [],
          themes: [],
          mapping_count: 0,
          theme_count: 0,
          evidence_gap_count: 1
        }}
      />
    );
    expect(screen.getByText('存在候选映射，但证据或审核状态尚未达到工作流门槛。')).toBeInTheDocument();

    rerender(
      <ThemeResearchContextSection
        context={{
          ...reviewedContext(),
          status: 'not_mapped',
          mappings: [],
          themes: [],
          mapping_count: 0,
          theme_count: 0
        }}
      />
    );
    expect(screen.getByText('当前公司尚未建立审核通过的主题节点映射。')).toBeInTheDocument();

    rerender(<ThemeResearchContextSection context={undefined} />);
    expect(screen.getByText('主题研究上下文暂不可用。')).toBeInTheDocument();
  });
});

