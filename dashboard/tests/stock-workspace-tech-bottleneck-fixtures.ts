import type { StockEntryContext } from '../src/components/StockWorkspace';

export const reviewUniverseTechBottleneckEntryContext: StockEntryContext = {
  sourceWorkspace: 'techBottleneck',
  assetId: '000049.SZ',
  stockName: '德赛电池',
  query: '德赛电池',
  techBottleneckSource: 'tech_bottleneck_review_universe_frontend_dataset_v1',
  reviewStatus: '待复盘',
  sourceGroup: 'seed_tier_b_reconciliation_evidence',
  previousTier: 'Tier B',
  evidenceStrength: '充分',
  bottleneckRelevance: '核心瓶颈',
  nextAction: 'manual review of upgraded primary-source evidence before any future core-pool action',
  rationale: 'evidence=48; page_citations=18; sources=3; domain=strong; role=moderate; bottleneck=strong',
  evidenceExcerpt:
    '深圳市德赛电池科技股份有限公司 2025 年半年度报告全文 9 产计划并组织生产。储能电芯产品为标准化产品，公司综合评估客户需求与产能利用情况，制定生产计划并组织生产。',
  bottleneckConfidenceScore: 88,
  evidenceQualityScore: 62,
  evidenceGapNote:
    '深圳市德赛电池科技股份有限公司 2025 年半年度报告全文 9 产计划并组织生产。储能电芯产品为标准化产品，公司综合评估客户需求与产能利用情况，制定生产计划并组织生产。'
};
