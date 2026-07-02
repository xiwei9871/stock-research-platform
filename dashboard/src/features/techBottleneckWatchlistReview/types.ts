export type TechBottleneckReviewMode = 'read_only_research_review';

export type TechBottleneckSummary = {
  snapshotDate: string;
  pageName: string;
  mode: TechBottleneckReviewMode;
  watchlistCount: number;
  v2CandidatesCount: number;
  reviewPriorityRows: number;
  riskQueueRows: number;
  manualTemplateRows: number;
  consolidatedReportLinks: number;
  warningCount: number;
  baselineAdmissionChangedCount: number;
  writebackAllowed: boolean;
  usedForSignal: boolean;
};

export type TechBottleneckPrioritySummary = {
  label: string;
  count: number;
  reviewUse: string;
};

export type TechBottleneckSectionSpec = {
  title: string;
  purpose: string;
  displayFields: string[];
  interactionsAllowed: string[];
  writebackAllowed: boolean;
  usedForSignal: boolean;
};

export type TechBottleneckWatchlistRow = {
  assetId: string;
  symbol: string;
  name: string;
  reviewPriority: string;
  reviewPriorityReason: string;
  fundamentalQualityBadge: string;
  recoveryBadge: string;
  riskReviewBadge: string;
  valuationContextBadge: string;
  baiduValidationBadge: string;
  dataGapBadge: string;
  sourceQualityWarning: string;
  consolidatedReportPath: string;
  usedForSignal: boolean;
};

export type TechBottleneckRiskRow = {
  assetId: string;
  symbol: string;
  name: string;
  riskType: string;
  severity: string;
  riskReason: string;
  recommendedReviewAction: string;
  autoExclude: boolean;
  usedForSignal: boolean;
};

export type TechBottleneckManualTemplateStatus = {
  templateRows: number;
  notReviewedCount: number;
  historyRows: number;
  writebackEnabled: boolean;
  nextStep: string;
  usedForSignal: boolean;
};

export type TechBottleneckReportLink = {
  assetId: string;
  symbol: string;
  name: string;
  path: string;
  reportExists: boolean;
  usedForSignal: boolean;
};

export type TechBottleneckFinancialStatementSummary = {
  sectionName: string;
  sectionStatus: 'passed';
  watchlistCount: number;
  supportedCount: number;
  missingCount: number;
  pitStrongCount: number;
  pitDegradedCount: number;
  lookaheadViolationRows: number;
  writebackEnabled: boolean;
  manualReviewWritebackEnabled: boolean;
  usedForSignal: boolean;
  usedForAdmission: boolean;
  researchOnly: boolean;
};

export type TechBottleneckFinancialStatementRow = {
  assetId: string;
  symbol: string;
  name: string;
  support: 'supported' | 'missing';
  quality: string;
  reportPeriod: string;
  announceDate: string;
  pitStatus: string;
  sourceQuality: string;
  revenue: string;
  netProfit: string;
  operatingCashflow: string;
  inventory: string;
  accountsReceivable: string;
  rdExpense: string;
  capex: string;
  totalAssets: string;
  totalLiabilities: string;
  totalEquity: string;
  grossMargin: string;
  netMargin: string;
  roe: string;
  roa: string;
  assetLiabilityRatio: string;
  cashflowQualityContext: string;
  balanceSheetPressureContext: string;
  rdIntensityContext: string;
  dataGapNote: string;
  usedForSignal: boolean;
  usedForAdmission: boolean;
  researchOnly: boolean;
  writebackEnabled: boolean;
};
