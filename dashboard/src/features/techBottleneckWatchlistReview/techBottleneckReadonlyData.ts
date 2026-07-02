import type {
  TechBottleneckFinancialStatementRow,
  TechBottleneckFinancialStatementSummary,
  TechBottleneckManualTemplateStatus,
  TechBottleneckPrioritySummary,
  TechBottleneckReportLink,
  TechBottleneckRiskRow,
  TechBottleneckSectionSpec,
  TechBottleneckSummary,
  TechBottleneckWatchlistRow
} from './types';

export const techBottleneckSummary: TechBottleneckSummary = {
  snapshotDate: '2026-07-02',
  pageName: 'Tech Bottleneck Watchlist Review',
  mode: 'read_only_research_review',
  watchlistCount: 102,
  v2CandidatesCount: 102,
  reviewPriorityRows: 223,
  riskQueueRows: 345,
  manualTemplateRows: 102,
  consolidatedReportLinks: 102,
  warningCount: 6,
  baselineAdmissionChangedCount: 0,
  writebackAllowed: false,
  usedForSignal: false
};

export const techBottleneckFinancialStatementSummary: TechBottleneckFinancialStatementSummary = {
  sectionName: 'Full Financial Statement Review Context',
  sectionStatus: 'passed',
  watchlistCount: 102,
  supportedCount: 63,
  missingCount: 39,
  pitStrongCount: 63,
  pitDegradedCount: 0,
  lookaheadViolationRows: 0,
  writebackEnabled: false,
  manualReviewWritebackEnabled: false,
  usedForSignal: false,
  usedForAdmission: false,
  researchOnly: true
};

export const techBottleneckWarnings = [
  'Research-only review page.',
  'No automated execution output is produced.',
  'Baseline admission remains unchanged.',
  'Manual review template is display-only in this page.',
  'Fundamental fields are derived research features.',
  'External source coverage requires ongoing validation.'
];

export const techBottleneckPrioritySummary: TechBottleneckPrioritySummary[] = [
  {
    label: 'High fundamental review',
    count: 41,
    reviewUse: 'Review whether derived fundamental quality is supported by source material.'
  },
  {
    label: 'Recovery review',
    count: 26,
    reviewUse: 'Review whether recovery evidence is consistent across research sources.'
  },
  {
    label: 'High quality review queue',
    count: 64,
    reviewUse: 'Use for deeper manual research review.'
  },
  {
    label: 'Risk review',
    count: 29,
    reviewUse: 'Review source-specific risk evidence and data quality context.'
  },
  {
    label: 'Data gap review',
    count: 72,
    reviewUse: 'Review missing source coverage before drawing research conclusions.'
  }
];

export const techBottleneckSections: TechBottleneckSectionSpec[] = [
  {
    title: 'Snapshot Summary',
    purpose: 'Show observation pool coverage and read-only controls.',
    displayFields: ['watchlistCount', 'v2CandidatesCount', 'reviewPriorityRows', 'riskQueueRows'],
    interactionsAllowed: ['filter', 'sort', 'open report', 'copy report path'],
    writebackAllowed: false,
    usedForSignal: false
  },
  {
    title: 'Watchlist Table',
    purpose: 'Display v2 research priority, source warnings, and report links.',
    displayFields: ['symbol', 'name', 'v2_review_priority', 'source_quality_warning', 'consolidated_report_path'],
    interactionsAllowed: ['filter', 'sort', 'open report', 'copy report path'],
    writebackAllowed: false,
    usedForSignal: false
  },
  {
    title: 'Risk Review Queue',
    purpose: 'Display risk review rows without automatic exclusion.',
    displayFields: ['risk_type', 'risk_reason', 'severity', 'recommended_review_action'],
    interactionsAllowed: ['filter', 'sort'],
    writebackAllowed: false,
    usedForSignal: false
  },
  {
    title: 'Manual Review Template Status',
    purpose: 'Display template readiness without review label writeback.',
    displayFields: ['templateRows', 'notReviewedCount', 'historyRows'],
    interactionsAllowed: ['view template fields'],
    writebackAllowed: false,
    usedForSignal: false
  }
];

export const techBottleneckWatchlistRows: TechBottleneckWatchlistRow[] = [
  {
    assetId: 'CN:SH:600098',
    symbol: '600098',
    name: '广州发展',
    reviewPriority: 'priority_data_gap_review',
    reviewPriorityReason: 'source gap requires more research context',
    fundamentalQualityBadge: 'quality_missing',
    recoveryBadge: 'recovery_missing',
    riskReviewBadge: 'standard_risk_review',
    valuationContextBadge: 'valuation_mixed_context',
    baiduValidationBadge: 'consistent',
    dataGapBadge: 'data_gap_review',
    sourceQualityWarning: 'pit_replay_candidate',
    consolidatedReportPath:
      '/Users/xiwei/stock_research/outputs/research/tech_bottleneck_watchlist_report_consolidated_v1/reports_consolidated/latest/CN_SH_600098_广州发展.md',
    usedForSignal: false
  },
  {
    assetId: 'CN:SH:600219',
    symbol: '600219',
    name: '南山铝业',
    reviewPriority: 'priority_high_fundamental_review',
    reviewPriorityReason: 'PIT replay favored fundamental quality or recovery context',
    fundamentalQualityBadge: 'quality_medium',
    recoveryBadge: 'recovery_neutral',
    riskReviewBadge: 'risk_review',
    valuationContextBadge: 'valuation_high_context',
    baiduValidationBadge: 'consistent',
    dataGapBadge: 'source_context_available',
    sourceQualityWarning: 'pit_replay_candidate',
    consolidatedReportPath:
      '/Users/xiwei/stock_research/outputs/research/tech_bottleneck_watchlist_report_consolidated_v1/reports_consolidated/latest/CN_SH_600219_南山铝业.md',
    usedForSignal: false
  },
  {
    assetId: 'CN:SH:600312',
    symbol: '600312',
    name: '平高电气',
    reviewPriority: 'priority_data_gap_review',
    reviewPriorityReason: 'source gap requires more research context',
    fundamentalQualityBadge: 'quality_missing',
    recoveryBadge: 'recovery_missing',
    riskReviewBadge: 'standard_risk_review',
    valuationContextBadge: 'valuation_mid_context',
    baiduValidationBadge: 'consistent',
    dataGapBadge: 'data_gap_review',
    sourceQualityWarning: 'pit_replay_candidate',
    consolidatedReportPath:
      '/Users/xiwei/stock_research/outputs/research/tech_bottleneck_watchlist_report_consolidated_v1/reports_consolidated/latest/CN_SH_600312_平高电气.md',
    usedForSignal: false
  },
  {
    assetId: 'CN:SH:600388',
    symbol: '600388',
    name: '龙净环保',
    reviewPriority: 'priority_high_fundamental_review',
    reviewPriorityReason: 'PIT replay favored fundamental quality or recovery context',
    fundamentalQualityBadge: 'quality_high',
    recoveryBadge: 'recovery_positive',
    riskReviewBadge: 'standard_risk_review',
    valuationContextBadge: 'valuation_mixed_context',
    baiduValidationBadge: 'consistent',
    dataGapBadge: 'data_gap_review',
    sourceQualityWarning: 'pit_replay_candidate',
    consolidatedReportPath:
      '/Users/xiwei/stock_research/outputs/research/tech_bottleneck_watchlist_report_consolidated_v1/reports_consolidated/latest/CN_SH_600388_龙净环保.md',
    usedForSignal: false
  }
];

export const techBottleneckFinancialStatementRows: TechBottleneckFinancialStatementRow[] = [
  {
    assetId: 'CN:SH:600098',
    symbol: '600098',
    name: '广州发展',
    support: 'missing',
    quality: 'missing_source',
    reportPeriod: '',
    announceDate: '',
    pitStatus: 'source_missing',
    sourceQuality: 'missing_source',
    revenue: '',
    netProfit: '',
    operatingCashflow: '',
    inventory: '',
    accountsReceivable: '',
    rdExpense: '',
    capex: '',
    totalAssets: '',
    totalLiabilities: '',
    totalEquity: '',
    grossMargin: '',
    netMargin: '',
    roe: '',
    roa: '',
    assetLiabilityRatio: '',
    cashflowQualityContext: 'not_available',
    balanceSheetPressureContext: 'not_available',
    rdIntensityContext: 'not_available',
    dataGapNote: 'Financial statement data unavailable before first admission date',
    usedForSignal: false,
    usedForAdmission: false,
    researchOnly: true,
    writebackEnabled: false
  },
  {
    assetId: 'CN:SH:600219',
    symbol: '600219',
    name: '南山铝业',
    support: 'supported',
    quality: 'degraded_sparse_statement_fields',
    reportPeriod: '2025-09-30',
    announceDate: '2025-10-30',
    pitStatus: 'pit_strong',
    sourceQuality: 'degraded_sparse_statement_fields',
    revenue: '',
    netProfit: '',
    operatingCashflow: '',
    inventory: '',
    accountsReceivable: '',
    rdExpense: '',
    capex: '',
    totalAssets: '',
    totalLiabilities: '',
    totalEquity: '',
    grossMargin: '0.266309',
    netMargin: '',
    roe: '',
    roa: '',
    assetLiabilityRatio: '0.001756',
    cashflowQualityContext: 'cashflow_context_positive',
    balanceSheetPressureContext: 'balance_sheet_pressure_low',
    rdIntensityContext: 'neutral_context',
    dataGapNote: '',
    usedForSignal: false,
    usedForAdmission: false,
    researchOnly: true,
    writebackEnabled: false
  },
  {
    assetId: 'CN:SH:600312',
    symbol: '600312',
    name: '平高电气',
    support: 'missing',
    quality: 'missing_source',
    reportPeriod: '',
    announceDate: '',
    pitStatus: 'source_missing',
    sourceQuality: 'missing_source',
    revenue: '',
    netProfit: '',
    operatingCashflow: '',
    inventory: '',
    accountsReceivable: '',
    rdExpense: '',
    capex: '',
    totalAssets: '',
    totalLiabilities: '',
    totalEquity: '',
    grossMargin: '',
    netMargin: '',
    roe: '',
    roa: '',
    assetLiabilityRatio: '',
    cashflowQualityContext: 'not_available',
    balanceSheetPressureContext: 'not_available',
    rdIntensityContext: 'not_available',
    dataGapNote: 'Financial statement data unavailable before first admission date',
    usedForSignal: false,
    usedForAdmission: false,
    researchOnly: true,
    writebackEnabled: false
  },
  {
    assetId: 'CN:SH:600388',
    symbol: '600388',
    name: '龙净环保',
    support: 'supported',
    quality: 'degraded_sparse_statement_fields',
    reportPeriod: '2025-12-31',
    announceDate: '2026-03-21',
    pitStatus: 'pit_strong',
    sourceQuality: 'degraded_sparse_statement_fields',
    revenue: '',
    netProfit: '',
    operatingCashflow: '',
    inventory: '',
    accountsReceivable: '',
    rdExpense: '',
    capex: '',
    totalAssets: '',
    totalLiabilities: '',
    totalEquity: '',
    grossMargin: '0.251666',
    netMargin: '',
    roe: '',
    roa: '',
    assetLiabilityRatio: '0.006065',
    cashflowQualityContext: 'cashflow_context_positive',
    balanceSheetPressureContext: 'balance_sheet_pressure_low',
    rdIntensityContext: 'neutral_context',
    dataGapNote: '',
    usedForSignal: false,
    usedForAdmission: false,
    researchOnly: true,
    writebackEnabled: false
  }
];

export const techBottleneckRiskRows: TechBottleneckRiskRow[] = [
  {
    assetId: 'CN:SH:600098',
    symbol: '600098',
    name: '广州发展',
    riskType: 'missing_announcement_support',
    severity: 'low',
    riskReason: 'announcement support missing',
    recommendedReviewAction: 'review_data_gap',
    autoExclude: false,
    usedForSignal: false
  },
  {
    assetId: 'CN:SH:600098',
    symbol: '600098',
    name: '广州发展',
    riskType: 'missing_fundamental_support',
    severity: 'low',
    riskReason: 'fundamental support missing',
    recommendedReviewAction: 'review_full_financial_statement',
    autoExclude: false,
    usedForSignal: false
  },
  {
    assetId: 'CN:SH:600219',
    symbol: '600219',
    name: '南山铝业',
    riskType: 'announcement_specific_risk_event',
    severity: 'medium',
    riskReason: 'specific risk event count > 0',
    recommendedReviewAction: 'review_specific_risk_event',
    autoExclude: false,
    usedForSignal: false
  }
];

export const techBottleneckManualTemplateStatus: TechBottleneckManualTemplateStatus = {
  templateRows: 102,
  notReviewedCount: 102,
  historyRows: 0,
  writebackEnabled: false,
  nextStep: 'research-only offline review or later research-only writeback',
  usedForSignal: false
};

export const techBottleneckReportLinks: TechBottleneckReportLink[] = techBottleneckWatchlistRows.map((row) => ({
  assetId: row.assetId,
  symbol: row.symbol,
  name: row.name,
  path: row.consolidatedReportPath,
  reportExists: true,
  usedForSignal: false
}));
