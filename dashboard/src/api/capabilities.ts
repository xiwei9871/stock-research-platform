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
  theme_node?: string;
  status?: string;
  error?: string;
  node_verdict?: string;
  cap_statuses?: Record<string, string>;
  companies?: CapWorkbenchCompany[];
  synthesis?: {
    favorable_support: CapBucketEntry[];
    market_structure: CapBucketEntry[];
    counter_evidence: CapBucketEntry[];
    hype_risks: CapBucketEntry[];
    unresolved: CapBucketEntry[];
  };
  evidence_refs?: string[];
  upstream_fingerprints?: string[];
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
