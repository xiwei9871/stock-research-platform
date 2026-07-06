import type {
  TechBottleneckFinancialStatementRow,
  TechBottleneckFinancialStatementSummary,
  TechBottleneckManualReviewDraft,
  TechBottleneckManualReviewWritebackContract,
  TechBottleneckManualTemplateStatus,
  TechBottleneckNewsEventCard,
  TechBottleneckNewsRow,
  TechBottleneckNewsSummary,
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

export const techBottleneckNewsSummary: TechBottleneckNewsSummary = {
  sectionName: 'News and Event Review Context',
  sectionStatus: 'passed',
  watchlistCount: 102,
  supportedCount: 30,
  partialCount: 1,
  missingCount: 71,
  pitAvailableEventCount: 189,
  postAdmissionEventCount: 11,
  dateMissingEventCount: 71,
  lookaheadViolationRows: 0,
  writebackEnabled: false,
  manualReviewWritebackEnabled: false,
  usedForSignal: false,
  usedForAdmission: false,
  researchOnly: true
};

export const techBottleneckManualReviewWritebackContract: TechBottleneckManualReviewWritebackContract = {
  sectionName: 'Manual Review Research-Only Writeback',
  sectionStatus: 'passed',
  manualReviewWritebackEnabled: true,
  manualReviewWritebackScope: 'manual_review_only',
  strategyWritebackEnabled: false,
  baselineAdmissionChangeEnabled: false,
  researchOnly: true,
  usedForSignal: false,
  usedForAdmission: false,
  allowedFields: [
    'review_status',
    'manual_review_conclusion',
    'selected_labels',
    'evidence_quality_review',
    'financial_statement_review',
    'news_context_review',
    'risk_review',
    'data_gap_confirmation',
    'review_note',
    'reviewer',
    'reviewed_at'
  ],
  auditRequired: true,
  saveButtonLabel: '保存研究复盘'
};

export const techBottleneckManualReviewDefaultDraft: TechBottleneckManualReviewDraft = {
  reviewStatus: 'not_reviewed',
  manualReviewConclusion: 'not_reviewed',
  selectedLabels: '',
  evidenceQualityReview: 'not_reviewed',
  financialStatementReview: '',
  newsContextReview: '',
  riskReview: '',
  dataGapConfirmation: false,
  reviewNote: '',
  reviewer: '',
  reviewedAt: ''
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
  },
  {
    title: 'News and Event Review Context',
    purpose: 'Display dated news and disclosure context with source quality warnings.',
    displayFields: ['news_support', 'pit_available_event_count', 'source_quality', 'news_data_gap'],
    interactionsAllowed: ['filter', 'sort', 'view event cards'],
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

export const techBottleneckNewsRows: TechBottleneckNewsRow[] = [
  {
    assetId: 'CN:SH:600098',
    symbol: '600098',
    name: '广州发展',
    support: 'missing',
    eventCount: 0,
    pitAvailableEventCount: 0,
    postAdmissionEventCount: 0,
    dateMissingEventCount: 1,
    riskEventCount: 0,
    sourceQuality: 'missing',
    dataGap: true,
    dataGapNote: 'News context unavailable or date-missing before first admission date.',
    partialCoverageNote: '',
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
    eventCount: 4,
    pitAvailableEventCount: 4,
    postAdmissionEventCount: 0,
    dateMissingEventCount: 0,
    riskEventCount: 2,
    sourceQuality: 'high',
    dataGap: false,
    dataGapNote: '',
    partialCoverageNote: '',
    usedForSignal: false,
    usedForAdmission: false,
    researchOnly: true,
    writebackEnabled: false
  },
  {
    assetId: 'CN:SZ:002028',
    symbol: '002028',
    name: '思源电气',
    support: 'partial',
    eventCount: 1,
    pitAvailableEventCount: 0,
    postAdmissionEventCount: 1,
    dateMissingEventCount: 0,
    riskEventCount: 0,
    sourceQuality: 'low',
    dataGap: true,
    dataGapNote: '',
    partialCoverageNote: 'Partial news coverage only; manual review should verify event completeness.',
    usedForSignal: false,
    usedForAdmission: false,
    researchOnly: true,
    writebackEnabled: false
  },
  {
    assetId: 'CN:SH:688002',
    symbol: '688002',
    name: '睿创微纳',
    support: 'supported',
    eventCount: 12,
    pitAvailableEventCount: 8,
    postAdmissionEventCount: 4,
    dateMissingEventCount: 0,
    riskEventCount: 3,
    sourceQuality: 'high',
    dataGap: false,
    dataGapNote: '',
    partialCoverageNote: '',
    usedForSignal: false,
    usedForAdmission: false,
    researchOnly: true,
    writebackEnabled: false
  }
];

export const techBottleneckNewsEventCards: TechBottleneckNewsEventCard[] = [
  {
    assetId: 'CN:SH:600219',
    symbol: '600219',
    name: '南山铝业',
    publishDate: '2026-01-20',
    eventType: 'capacity_expansion',
    sourceType: 'announcement',
    title: '南山铝业:山东南山铝业股份有限公司第十一届董事会第二十五次会议决议公告',
    matchedTopic: 'capacity_project',
    pitStatus: 'pit_available',
    sourceQuality: 'high',
    cardGroup: 'PIT-Available Events',
    eventNote: 'Available at first admission cutoff.',
    usedForSignal: false,
    usedForAdmission: false,
    researchOnly: true,
    writebackEnabled: false
  },
  {
    assetId: 'CN:SH:688002',
    symbol: '688002',
    name: '睿创微纳',
    publishDate: '2026-04-28',
    eventType: 'financial_risk',
    sourceType: 'announcement',
    title: '睿创微纳:关于开展外汇套期保值业务的公告',
    matchedTopic: 'risk_disclosure',
    pitStatus: 'post_admission_context',
    sourceQuality: 'high',
    cardGroup: 'Post-Admission Review Context',
    eventNote: 'Post-admission review context only; not PIT evidence.',
    usedForSignal: false,
    usedForAdmission: false,
    researchOnly: true,
    writebackEnabled: false
  },
  {
    assetId: 'CN:SH:600098',
    symbol: '600098',
    name: '广州发展',
    publishDate: '',
    eventType: 'data_gap',
    sourceType: 'unknown',
    title: 'News source mapping data gap',
    matchedTopic: 'missing_news_source',
    pitStatus: 'date_missing',
    sourceQuality: 'degraded',
    cardGroup: 'Date-Missing / Degraded Events',
    eventNote: 'Date missing or source gap; degraded and not strong PIT evidence.',
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
