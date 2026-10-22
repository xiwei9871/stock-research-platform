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
