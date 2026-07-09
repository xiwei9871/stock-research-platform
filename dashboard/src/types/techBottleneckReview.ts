export type TechBottleneckReviewSummary = {
  frontend_dataset_count: number;
  v5_hydrated_count: number;
  v7_proposal_new_count: number;
  v5_targeted_hydrated_count: number;
  remaining_evidence_gap_count: number;
  evidence_index_row_count: number;
  source_index_row_count: number;
  used_for_signal_count: number;
  used_for_admission_count: number;
  readonly_page: boolean;
  reviewer_decision_write_enabled: boolean;
  database_write_enabled: boolean;
  csv_writeback_enabled: boolean;
  acceptance_decision: string;
};

export type TechBottleneckReviewStock = {
  stock_code: string;
  stock_name: string;
  review_universe_source: string;
  current_layer_status: string;
  manual_approval_status: string;
  frontend_review_status: string;
  evidence_count: number | string;
  page_citation_count: number | string;
  source_pdf_count: number | string;
  primary_source_supported: boolean;
  hard_tech_domain: string;
  supply_chain_role_hint: string;
  business_relevance_hint: string;
  bottleneck_or_chokepoint_hint: string;
  concept_pollution_risk: string;
  route_around_or_substitution_risk: string;
  value_capture_risk: string;
  disconfirmation_trigger: boolean | string;
  next_primary_source_to_check: string;
  strongest_primary_source_claim: string;
  weakest_or_riskiest_claim: string;
  evidence_summary_for_review: string;
  industry?: string;
  concept_tags?: string[] | string;
  evidence_strength?: string;
  bottleneck_relevance?: string;
  bottleneck_confidence_score?: number | string | null;
  evidence_quality_score?: number | string | null;
  bottleneckConfidenceScore?: number | null;
  evidenceQualityScore?: number | null;
  source_group?: string;
  previous_tier?: string;
  review_status?: string;
  reviewer_decision: string;
  reviewer?: string;
  review_comment?: string;
  reviewed_at?: string;
  decision_source?: string;
  reviewer_note: string;
  used_for_signal: boolean;
  used_for_admission: boolean;
  auto_added_to_quality_pool: boolean;
};

export type TechBottleneckReviewEvidence = {
  stock_code: string;
  stock_name: string;
  review_universe_source: string;
  source_file: string;
  source_type: string;
  source_title: string;
  source_date?: string;
  page: string;
  evidence_text: string;
  evidence_claim_type: string;
  citation_quality: string;
  research_only: boolean;
  used_for_signal: boolean;
  used_for_admission: boolean;
};

export type TechBottleneckReviewSource = {
  stock_code: string;
  stock_name: string;
  review_universe_source: string;
  source_file: string;
  source_type: string;
  source_title: string;
  research_only: boolean;
  used_for_signal: boolean;
  used_for_admission: boolean;
};

export type TechBottleneckReviewFilterOptions = Record<string, Array<string | boolean>>;

export type TechBottleneckReviewerDecision = 'keep' | 'hold' | 'need_more_evidence' | 'downgrade' | 'reject';

export type TechBottleneckReviewDecisionSummary = {
  total_review_universe_count: number;
  reviewed_count: number;
  pending_count: number;
  keep_count: number;
  hold_count: number;
  need_more_evidence_count: number;
  downgrade_count: number;
  reject_count: number;
  last_reviewed_at: string;
  used_for_signal_count: number;
  used_for_admission_count: number;
  frozen_v7_generated: boolean;
};

export type TechBottleneckReviewDecisionPayload = {
  stock_code: string;
  stock_name: string;
  reviewer_decision: TechBottleneckReviewerDecision;
  reviewer: string;
  review_comment: string;
  rubric_flags: Record<string, string | boolean>;
  evidence_checked: boolean;
  source_context: Record<string, string>;
};

export type TechBottleneckReviewDecisionResponse = {
  status: string;
  decision_id: string;
  stock_code: string;
  reviewer_decision: TechBottleneckReviewerDecision;
  reviewed_at: string;
};

export type TechBottleneckReviewDecisionRecord = {
  decision_id: string;
  stock_code: string;
  stock_name: string;
  reviewer_decision: TechBottleneckReviewerDecision;
  reviewer: string;
  review_comment: string;
  rubric_flags: Record<string, string | boolean>;
  evidence_checked: boolean;
  source_context: Record<string, string>;
  recorded_at: string;
  decision_source: string;
  review_status: string;
  used_for_signal: boolean;
  used_for_admission: boolean;
};

export type TechBottleneckReviewDecisionsResponse = {
  total: number;
  limit: number;
  items: TechBottleneckReviewDecisionRecord[];
};

export type TechBottleneckReviewStocksResponse = {
  total: number;
  limit: number;
  offset: number;
  items: TechBottleneckReviewStock[];
};

export type TechBottleneckReviewEvidenceResponse = {
  stock_code: string;
  total: number;
  items: TechBottleneckReviewEvidence[];
};

export type TechBottleneckReviewSourceResponse = {
  stock_code: string;
  total: number;
  items: TechBottleneckReviewSource[];
};

export type TechBottleneckReviewStockParams = {
  industry?: string;
  concept_tag?: string;
  evidence_strength?: string;
  bottleneck_relevance?: string;
  concept_pollution_risk?: string;
  route_around_or_substitution_risk?: string;
  value_capture_risk?: string;
  frontend_review_status?: string;
  review_status?: string;
  reviewer_decision?: string;
  q?: string;
  limit?: number;
  offset?: number;
};
