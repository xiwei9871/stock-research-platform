export interface CapWorkbenchTheme {
  theme_id: string;
  as_of: string;
  run_id: string;
  node_count: number;
  gap_count: number;
}

export interface CapWorkbenchThemesResponse {
  themes: CapWorkbenchTheme[];
}

export interface CapBucketEntry {
  claim_id: string;
  role: string;
  verdict: string;
  hypothesis?: string;
  evidence_ids: string[];
  source_ids: string[];
  capability: string;
}

export interface CapWorkbenchCompany {
  stock_code: string;
  dashboard_link?: string;
  overall_verdict?: string;
  delivery?: string;
  revenue?: string;
  order?: string;
  scope_class?: string;
  evidence_coverage?: number;
  comparable_with?: string[];
}

export interface CapHypothesis {
  hypothesis_id: string;
  subject_scope: string;
  claim_role: string;
  verdict: string;
  assessment_state: string;
  supporting_claim_ids: string[];
  counter_claim_ids: string[];
  alternative_explanations: string[];
  decisive_gaps: string[];
  revision_triggers: string[];
  evidence_refs: string[];
  independent_source_count?: number;
}

export interface CapTechnicalArea {
  assessment?: string;
  sub_checks?: Record<string, string>;
}

export interface CapPairwise {
  a: string;
  b: string;
  comparison_scope: string;
  reason: string;
}

export interface CapThemeSynthesis {
  key_findings: string[];
  competing_hypotheses: Array<{
    node_id: string;
    hypothesis_id: string;
    state: string;
    independent_source_count?: number;
  }>;
  core_unresolved: Array<{ node_id: string; claim_id: string; verdict?: string }>;
  next_verification: string[];
  coverage?: {
    theme_nodes?: number;
    nodes_with_cases?: number;
    coverage_gap_nodes?: string[];
    read_source?: string;
  };
  note?: string;
}

export interface CapWorkbenchNode {
  node_id: string;
  theme_node_id?: string;
  theme_node?: string;
  status?: string;
  coverage?: string;
  coverage_owner?: string;
  error?: string;
  node_verdict?: string;
  node_review_status?: string;
  bottleneck_score?: number;
  value_capture_score?: number;
  cap_statuses?: Record<string, string>;
  companies?: CapWorkbenchCompany[];
  mapped_companies?: Array<{ stock_code: string; review_status?: string; dashboard_link?: string }>;
  pairwise_scope?: CapPairwise[];
  technical_assessment?: Record<string, CapTechnicalArea>;
  hypothesis_assessment?: CapHypothesis[];
  synthesis?: {
    favorable_support: CapBucketEntry[];
    market_structure: CapBucketEntry[];
    counter_evidence: CapBucketEntry[];
    hype_risks: CapBucketEntry[];
    unresolved: CapBucketEntry[];
  };
  evidence_refs?: string[];
  upstream_fingerprints?: string[];
  theme_link?: string;
  changes?: {
    baseline_found?: boolean;
    baseline_version?: number;
    state_changed?: boolean;
    added?: number;
    removed?: number;
    changed?: number;
    items?: Array<{ kind: string; field: string; from: unknown; to: unknown }>;
  } | null;
}

export interface CapWorkbenchGap {
  node_id: string;
  capability: string;
  kind: string;
  item: string;
  owner: string;
  note?: string;
  source_capabilities?: string[];
}

export interface CapWorkbenchIndex {
  theme_id: string;
  as_of: string;
  run_id: string;
  theme_link?: string;
  read_source?: string;
  pit_note?: string;
  theme_node_count?: number;
  covered_node_count?: number;
  theme_synthesis?: CapThemeSynthesis;
  nodes: CapWorkbenchNode[];
  gap_summary?: Record<string, number>;
  gap_backlog: CapWorkbenchGap[];
  research_only?: boolean;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function listCapabilityWorkbenches(): Promise<CapWorkbenchThemesResponse> {
  return getJson('/api/research/capabilities/workbench');
}

export function loadCapabilityWorkbench(themeId: string): Promise<CapWorkbenchIndex> {
  return getJson(`/api/research/capabilities/workbench/${encodeURIComponent(themeId)}`);
}
