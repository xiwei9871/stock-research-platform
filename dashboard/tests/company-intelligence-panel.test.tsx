import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CompanyIntelligencePanel } from '../src/components/techBottleneck/CompanyIntelligencePanel';

const dossierPayload = vi.hoisted(() => ({
  company_code: '002837',
  company_name: '英维克',
  as_of: '2026-10-20',
  profile: {},
  conclusion: {
    overall_verdict: 'contested',
    confidence: 0.35,
    main_uncertainties: ['竞争优势:存在反驳证据'],
    verification_conditions: ['补证:竞争优势->性能/成本/交付对比']
  },
  dimensions: {
    tech_moat: {
      verdict: 'partially_supported',
      label: '技术壁垒',
      confidence: 0.5,
      support_count: 5,
      refute_count: 0,
      unclear_count: 1,
      missing_checklist_items: ['性能参数对比'],
      evidence_ids: ['ru_002837_768']
    },
    competitive_edge: {
      verdict: 'contradicted',
      label: '竞争优势',
      confidence: 0.4,
      support_count: 0,
      refute_count: 4,
      unclear_count: 0,
      missing_checklist_items: ['性能/成本/交付对比', '客户认证'],
      evidence_ids: ['ev_shenling_full_stack']
    }
  },
  claims: [
    {
      claim_id: 'c_edge_uniqueness',
      dimension: 'competitive_edge',
      claim_text: '液冷全链条供给能力在国内具有稀缺性/独占性',
      review_status: 'pending',
      support_count: 0,
      refute_count: 4,
      evidence_ids: ['ev_shenling_full_stack']
    }
  ],
  evidence_matrix: [
    {
      evidence_id: 'ru_002837_768',
      source_id: 'ru_002837_ar_2025_p12_14',
      source_type: 'company_filing',
      dimension: 'tech_moat',
      direction: 'support',
      excerpt: '公司掌握Coolinside全链条液冷技术',
      page_or_section: '第 12-14 页',
      published_at: '2026',
      available_at: '',
      ingested_at: '',
      confidence: 'high',
      review_status: 'pending'
    },
    {
      evidence_id: 'ev_shenling_full_stack',
      source_id: 'B_shenling_huaxin_20261012',
      source_type: 'broker_report',
      dimension: 'competitive_edge',
      direction: 'refute',
      excerpt: '申菱环境被研报称为液冷全方案出海先锋',
      page_or_section: '第 2 页',
      published_at: '2026-10-12',
      available_at: '2026-10-19',
      ingested_at: '2026-10-19',
      confidence: 'medium',
      review_status: 'lead_only'
    }
  ],
  research_gaps: [
    { dimension: 'competitive_edge', missing_item: '客户认证', needed_source_types: ['announcement'], reason: 'checklist_item_uncovered', priority: 'high' }
  ],
  bear_case: [],
  bull_case: {},
  guardrails: { research_only: true, used_for_signal: false, used_for_admission: false, price_inputs_used: false, requires_human_review: true },
  input_snapshot: { code_sha: '8f29ac36', evidence_set_sha256: '49b300805c0c' },
  theme_context: {},
  post_asof_excluded: [],
  reviews: [],
  markdown_available: true
}));

vi.mock('../src/api/companyIntelligence', () => ({
  fetchCompanyIntelligenceDossier: vi.fn().mockResolvedValue(dossierPayload),
  recordCompanyIntelligenceReview: vi.fn().mockResolvedValue({ stock_code: '002837' }),
  companyIntelligenceMarkdownUrl: (code: string) => `/api/research/company-intelligence/stocks/${code}/dossier.md`
}));

afterEach(() => cleanup());

describe('CompanyIntelligencePanel', () => {
  it('renders six-dimension verdicts and overall state', async () => {
    render(<CompanyIntelligencePanel stockCode="002837" />);
    await waitFor(() => expect(screen.getByText(/英维克/)).toBeInTheDocument());
    expect(screen.getByText('技术壁垒')).toBeInTheDocument();
    expect(screen.getByText('竞争优势')).toBeInTheDocument();
    expect(screen.getByText('部分支持')).toBeInTheDocument();
    expect(screen.getByText('存在反证')).toBeInTheDocument();
    expect(screen.getByText(/研究截止 2026-10-20/)).toBeInTheDocument();
    expect(screen.getByText(/8f29ac36/)).toBeInTheDocument();
  });

  it('expands evidence with direction, page and timestamps', async () => {
    render(<CompanyIntelligencePanel stockCode="002837" />);
    await waitFor(() => expect(screen.getByText('竞争优势')).toBeInTheDocument());
    const expandButtons = screen.getAllByRole('button', { name: /展开证据/ });
    fireEvent.click(expandButtons[1]);
    await waitFor(() => expect(screen.getByText(/申菱环境被研报称为/)).toBeInTheDocument());
    expect(screen.getByText('第 2 页 · 2026-10-12 / 2026-10-19 / 2026-10-19', { exact: false })).toBeInTheDocument();
    expect(screen.getAllByText('反证').length).toBeGreaterThan(0);
  });

  it('shows missing checklist items and research gaps', async () => {
    render(<CompanyIntelligencePanel stockCode="002837" />);
    await waitFor(() => expect(screen.getByText('竞争优势')).toBeInTheDocument());
    expect(screen.getAllByText(/缺失项:/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByText(/研究缺口/));
    expect(screen.getAllByText(/客户认证/).length).toBeGreaterThan(0);
    expect(screen.getByText(/checklist_item_uncovered/)).toBeInTheDocument();
  });

  it('shows research-only guardrail footnote', async () => {
    render(<CompanyIntelligencePanel stockCode="002837" />);
    await waitFor(() => expect(screen.getByText(/research_only=true/)).toBeInTheDocument());
    expect(screen.getByText(/used_for_signal=false/)).toBeInTheDocument();
  });
});
