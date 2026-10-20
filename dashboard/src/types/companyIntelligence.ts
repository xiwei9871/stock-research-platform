export type CompanyIntelligenceVerdict =
  | 'confirmed'
  | 'partially_supported'
  | 'contested'
  | 'contradicted'
  | 'needs_evidence'
  | 'unknown'
  | string;

export interface CompanyIntelligenceDimension {
  verdict: CompanyIntelligenceVerdict;
  label?: string;
  confidence: number;
  support_count: number;
  refute_count: number;
  unclear_count?: number;
  missing_checklist_items?: string[];
  evidence_ids?: string[];
  conflicts?: string[];
}

export interface CompanyIntelligenceEvidence {
  evidence_id: string;
  source_id?: string;
  source_type?: string;
  dimension?: string;
  direction?: string;
  excerpt?: string;
  page_or_section?: string;
  published_at?: string;
  available_at?: string;
  ingested_at?: string;
  confidence?: string;
  review_status?: string;
  checklist_item?: string;
  claim_ids?: string[];
}

export interface CompanyIntelligenceClaim {
  claim_id: string;
  dimension: string;
  claim_text: string;
  review_status?: string;
  support_count?: number;
  refute_count?: number;
  evidence_ids?: string[];
}

export interface CompanyIntelligenceGap {
  dimension?: string;
  missing_item?: string;
  needed_source_types?: string[];
  reason?: string;
  priority?: string;
}

export interface CompanyIntelligenceBearCaseItem {
  dimension?: string;
  evidence_id?: string;
  excerpt?: string;
  page_or_section?: string;
  published_at?: string;
  source_id?: string;
  source_type?: string;
}

export interface CompanyIntelligenceReviewRecord {
  stock_code: string;
  claim_id: string;
  review_status: string;
  reviewer: string;
  comment: string;
  dimension?: string;
  recorded_at?: string;
}

export interface CompanyIntelligenceDossier {
  company_code: string;
  company_name: string;
  as_of: string;
  profile?: { summary?: string; products?: string[]; competitors?: string[] };
  conclusion?: {
    overall_verdict?: CompanyIntelligenceVerdict;
    confidence?: number;
    main_uncertainties?: string[];
    verification_conditions?: string[];
  };
  dimensions: Record<string, CompanyIntelligenceDimension>;
  claims?: CompanyIntelligenceClaim[];
  evidence_matrix?: CompanyIntelligenceEvidence[];
  research_gaps?: CompanyIntelligenceGap[];
  bull_case?: unknown;
  bear_case?: CompanyIntelligenceBearCaseItem[];
  guardrails?: Record<string, unknown>;
  input_snapshot?: { code_sha?: string; evidence_set_sha256?: string; [key: string]: unknown };
  theme_context?: Record<string, unknown>;
  post_asof_excluded?: unknown;
  reviews?: CompanyIntelligenceReviewRecord[];
  markdown_available?: boolean;
}

export interface CompanyIntelligenceDossierSummary {
  stock_code: string;
  company_name: string;
  as_of: string;
  overall_verdict: string;
  confidence?: number;
  generated_at?: string;
  code_sha?: string;
}

export interface CompanyIntelligenceDossierListResponse {
  items: CompanyIntelligenceDossierSummary[];
}
