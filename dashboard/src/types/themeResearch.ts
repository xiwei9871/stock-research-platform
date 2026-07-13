export type ThemeResearchGuardrails = {
  research_only: boolean;
  used_for_signal: boolean;
  used_for_admission: boolean;
};

export type ThemeResearchTheme = ThemeResearchGuardrails & {
  theme_id: string;
  theme_name: string;
  theme_type: string;
  summary: string;
  status: string;
  created_from: string;
  last_updated: string;
};

export type ThemeResearchThemeIndexItem = ThemeResearchTheme & {
  node_count: number;
  source_count: number;
  claim_count: number;
  company_count: number;
  evidence_gap_count: number;
  deep_research_node_count: number;
  review_queue_count: number;
};

export type ThemeResearchNode = ThemeResearchGuardrails & {
  theme_id: string;
  node_id: string;
  node_name: string;
  node_type: string;
  parent_node_id: string;
  description: string;
  value_capture_score: number;
  bottleneck_score: number;
  localization_gap_score: number;
  supply_tightness_score: number;
  evidence_strength: number;
  node_review_status: string;
  priority_score: number;
  priority_band: string;
  priority_class: string;
  recommended_action: string;
  rationale_codes: string[];
};

export type ThemeResearchSource = ThemeResearchGuardrails & {
  theme_id: string;
  source_id: string;
  source_type: string;
  title: string;
  publisher: string;
  author: string;
  publish_date: string;
  url_or_ref: string;
  access_level: string;
  reliability_level: string;
  review_status: string;
  notes: string;
  claim_count: number;
  claim_ids: string[];
};

export type ThemeResearchClaim = ThemeResearchGuardrails & {
  theme_id: string;
  claim_id: string;
  source_id: string;
  claim_text: string;
  claim_type: string;
  confidence: number;
  evidence_status: string;
  platform_use_status: string;
  supporting_source_ids: string[];
  supporting_sources: Array<{
    source_id: string;
    title: string;
    reliability_level: string;
    review_status: string;
  }>;
  affected_theme_nodes: string[];
  source_title: string;
  source_reliability_level: string;
  source_review_status: string;
};

export type ThemeResearchCompany = ThemeResearchGuardrails & {
  theme_id: string;
  mapping_id: string;
  company_code: string;
  company_name: string;
  market: string;
  mapped_node_id: string;
  mapping_type: string;
  business_stage: string;
  confidence: number;
  evidence_ids: string[];
  revenue_relevance: string;
  bottleneck_relevance: string;
  business_materiality: string;
  product_or_service: string;
  relationship_summary: string;
  review_status: string;
  notes: string;
  mapped_node: {
    node_id: string;
    node_name: string;
    evidence_strength: number;
  };
  company_research_priority_score: number;
  company_relevance_score: number;
  business_materiality_score: number;
  priority_band: string;
  recommended_action: string;
  rationale_codes: string[];
  integration_status: string;
  integration_ref: string;
  existing_review_context: {
    status: string;
    reviewer_decision: string;
  };
  tech_bottleneck_stock_path: string;
};

export type ThemeResearchCollection<T> = {
  total: number;
  items: T[];
};

export type ThemeResearchThemeDetail = ThemeResearchGuardrails & {
  theme: ThemeResearchTheme;
  node_summary: {
    total: number;
    by_priority_class: Record<string, number>;
    by_review_status: Record<string, number>;
  };
  source_summary: {
    total: number;
    by_review_status: Record<string, number>;
  };
  claim_summary: {
    total: number;
    by_platform_use_status: Record<string, number>;
  };
  company_summary: {
    total: number;
    by_priority_band: Record<string, number>;
    by_integration_status: Record<string, number>;
  };
  evidence_gap_summary: {
    total: number;
    by_priority_band: Record<string, number>;
  };
  source_reliability_distribution: Record<string, number>;
  claim_evidence_status_distribution: Record<string, number>;
  review_queue_action_distribution: Record<string, number>;
  top_node_priorities: ThemeResearchNode[];
  evidence_gaps: ThemeResearchNode[];
  top_company_priorities: ThemeResearchCompany[];
};

export type ThemeResearchThemeCollection = ThemeResearchCollection<ThemeResearchThemeIndexItem>;
export type ThemeResearchNodeCollection = ThemeResearchCollection<ThemeResearchNode>;
export type ThemeResearchSourceCollection = ThemeResearchCollection<ThemeResearchSource>;
export type ThemeResearchClaimCollection = ThemeResearchCollection<ThemeResearchClaim>;
export type ThemeResearchCompanyCollection = ThemeResearchCollection<ThemeResearchCompany>;
