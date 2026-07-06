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

export type TechBottleneckNewsSummary = {
  sectionName: string;
  sectionStatus: 'passed';
  watchlistCount: number;
  supportedCount: number;
  partialCount: number;
  missingCount: number;
  pitAvailableEventCount: number;
  postAdmissionEventCount: number;
  dateMissingEventCount: number;
  lookaheadViolationRows: number;
  writebackEnabled: boolean;
  manualReviewWritebackEnabled: boolean;
  usedForSignal: boolean;
  usedForAdmission: boolean;
  researchOnly: boolean;
};

export type TechBottleneckNewsRow = {
  assetId: string;
  symbol: string;
  name: string;
  support: 'supported' | 'partial' | 'missing';
  eventCount: number;
  pitAvailableEventCount: number;
  postAdmissionEventCount: number;
  dateMissingEventCount: number;
  riskEventCount: number;
  sourceQuality: string;
  dataGap: boolean;
  dataGapNote: string;
  partialCoverageNote: string;
  usedForSignal: boolean;
  usedForAdmission: boolean;
  researchOnly: boolean;
  writebackEnabled: boolean;
};

export type TechBottleneckNewsEventCard = {
  assetId: string;
  symbol: string;
  name: string;
  publishDate: string;
  eventType: string;
  sourceType: string;
  title: string;
  matchedTopic: string;
  pitStatus: 'pit_available' | 'post_admission_context' | 'date_missing';
  sourceQuality: string;
  cardGroup: string;
  eventNote: string;
  usedForSignal: boolean;
  usedForAdmission: boolean;
  researchOnly: boolean;
  writebackEnabled: boolean;
};

export type TechBottleneckManualReviewWritebackContract = {
  sectionName: 'Manual Review Research-Only Writeback';
  sectionStatus: 'passed';
  manualReviewWritebackEnabled: boolean;
  manualReviewWritebackScope: 'manual_review_only';
  strategyWritebackEnabled: boolean;
  baselineAdmissionChangeEnabled: boolean;
  researchOnly: boolean;
  usedForSignal: boolean;
  usedForAdmission: boolean;
  allowedFields: string[];
  auditRequired: boolean;
  saveButtonLabel: '保存研究复盘';
};

export type TechBottleneckManualReviewDraft = {
  reviewStatus: string;
  manualReviewConclusion: string;
  selectedLabels: string;
  evidenceQualityReview: string;
  financialStatementReview: string;
  newsContextReview: string;
  riskReview: string;
  dataGapConfirmation: boolean;
  reviewNote: string;
  reviewer: string;
  reviewedAt: string;
};

export type TechBottleneckWorkbenchQueue = 'core' | 'adjacent' | 'evidence_backfill' | 'rejected';

export type TechBottleneckWorkbenchCandidate = {
  stockCode: string;
  stockName: string;
  queue: TechBottleneckWorkbenchQueue;
  sourceGroup: string;
  previousTier: string;
  finalManualApprovalCategory: string;
  industry: string;
  conceptTags: string[];
  evidenceCategory: string;
  businessRelevanceCategory: string;
  researchPriorityScore: number | null;
  reviewPriorityRank: number;
  evidenceStrength: string;
  bottleneckRelevance: string;
  reviewDecisionSource: string;
  primarySourceUrl: string;
  manualApprovalRequired: boolean;
  allowedForWorkbenchCandidatePool: boolean;
  allowedForSignal: boolean;
  allowedForAdmission: boolean;
  rationale: string;
  reviewStatus: string;
  notes: string;
  nextAction: string;
  evidenceExcerpt: string;
  reportStatus?: string;
  bottleneckConfidenceScore?: number | null;
  evidenceQualityScore?: number | null;
  reportReviewDecision?: string;
  reportUpdatedAt?: string;
  reportMdPath?: string;
  reportHtmlPath?: string;
  reportPdfPath?: string;
  evidenceMatrixPath?: string;
  reportSourcesPath?: string;
  evidenceGapNote?: string;
};

export type TechBottleneckStockEntryContext = {
  stockName?: string;
  techBottleneckSource?: string;
  sourceGroup?: string;
  previousTier?: string;
  finalManualApprovalCategory?: string;
  industry?: string;
  conceptTags?: string[];
  evidenceCategory?: string;
  businessRelevanceCategory?: string;
  researchPriorityScore?: number | null;
  reviewPriorityRank?: number;
  evidenceStrength?: string;
  bottleneckRelevance?: string;
  reviewDecisionSource?: string;
  primarySourceUrl?: string;
  manualApprovalRequired?: boolean;
  allowedForWorkbenchCandidatePool?: boolean;
  allowedForSignal?: boolean;
  allowedForAdmission?: boolean;
  rationale?: string;
  reviewStatus?: string;
  notes?: string;
  nextAction?: string;
  evidenceExcerpt?: string;
  reportStatus?: string;
  bottleneckConfidenceScore?: number | null;
  evidenceQualityScore?: number | null;
  reportReviewDecision?: string;
  reportUpdatedAt?: string;
  reportMdPath?: string;
  reportHtmlPath?: string;
  reportPdfPath?: string;
  evidenceMatrixPath?: string;
  reportSourcesPath?: string;
  evidenceGapNote?: string;
};
