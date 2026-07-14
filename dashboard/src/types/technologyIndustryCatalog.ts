export type TechnologyIndustryCatalogGuardrails = {
  readonly research_only: true;
  readonly used_for_signal: false;
  readonly used_for_admission: false;
};

export type TechnologyIndustryCatalogStatus =
  | 'skeleton'
  | 'draft'
  | 'reviewed'
  | 'published';

export type TechnologyIndustryChainKind =
  | 'canonical_industry_chain'
  | 'application_theme_chain'
  | 'frontier_technology_chain';

export type TechnologyIndustryDecompositionMethod =
  | 'manufacturing_process'
  | 'system_architecture'
  | 'infrastructure_flow'
  | 'technical_route';

export type TechnologyIndustryNodeLevel = 'L3' | 'L4';

export type TechnologyIndustryNodeKind =
  | 'canonical'
  | 'application_role'
  | 'frontier_route';

export type TechnologyIndustryRelationshipType =
  | 'depends_on'
  | 'enables'
  | 'supplies'
  | 'uses'
  | 'substitutes'
  | 'competes_with'
  | 'downstream_of';

export type TechnologyIndustryCatalogSummary = {
  readonly sector_count: number;
  readonly chain_count: number;
  readonly l3_node_count: number;
  readonly l4_node_count: number;
  readonly edge_count: number;
  readonly theme_composition_count: number;
  readonly chains_by_kind: Readonly<
    Partial<Record<TechnologyIndustryChainKind, number>>
  >;
  readonly chains_by_decomposition_method: Readonly<
    Partial<Record<TechnologyIndustryDecompositionMethod, number>>
  >;
  readonly chains_by_status: Readonly<
    Partial<Record<TechnologyIndustryCatalogStatus, number>>
  >;
  readonly chains_by_sector: Readonly<Record<string, number>>;
  readonly nodes_by_status: Readonly<
    Partial<Record<TechnologyIndustryCatalogStatus, number>>
  >;
  readonly detailed_chain_count: number;
  readonly skeleton_chain_count: number;
  readonly structural_completeness_percent: number;
  readonly unexpanded_chain_ids: readonly string[];
  readonly deep_research_chain_count?: number;
};

export type TechnologyIndustryDeepResearchSummary = {
  readonly chain_id: string;
  readonly chain_name: string;
  readonly theme_id: string;
  readonly theme_title: string;
  readonly theme_route: string;
  readonly research_status: 'not_started' | 'researching' | 'reviewed' | 'needs_update';
  readonly freshness_status: 'not_available' | 'unknown' | 'current' | 'needs_update';
  readonly source_count: number;
  readonly claim_count: number;
  readonly reviewed_company_count: number;
  readonly evidence_gap_count: number;
  readonly last_updated: string;
};

export type TechnologyIndustrySector = {
  readonly sector_id: string;
  readonly sector_name: string;
  readonly description: string;
  readonly status: TechnologyIndustryCatalogStatus;
  readonly order: number;
};

export type TechnologyIndustryChain = {
  readonly chain_id: string;
  readonly sector_id: string;
  readonly chain_name: string;
  readonly chain_kind: TechnologyIndustryChainKind;
  readonly decomposition_method: TechnologyIndustryDecompositionMethod;
  readonly description: string;
  readonly scope: string;
  readonly exclusions: readonly string[];
  readonly aliases: readonly string[];
  readonly status: TechnologyIndustryCatalogStatus;
  readonly order: number;
  readonly deep_research?: TechnologyIndustryDeepResearchSummary | null;
};

export type TechnologyIndustryNode = {
  readonly node_id: string;
  readonly chain_id: string;
  readonly parent_node_id: string | null;
  readonly level: TechnologyIndustryNodeLevel;
  readonly node_name: string;
  readonly node_kind: TechnologyIndustryNodeKind;
  readonly node_type: string;
  readonly description: string;
  readonly status: TechnologyIndustryCatalogStatus;
  readonly primary_path: readonly string[];
  readonly canonical_key: string;
  readonly canonical_node_refs: readonly string[];
};

export type TechnologyIndustryEdge = {
  readonly edge_id: string;
  readonly source_node_id: string;
  readonly target_node_id: string;
  readonly relationship_type: TechnologyIndustryRelationshipType;
  readonly notes: string;
  readonly source_ids: readonly string[];
};

export type TechnologyIndustryThemeComposition = {
  readonly composition_id: string;
  readonly chain_id: string;
  readonly role_node_id: string;
  readonly canonical_node_refs: readonly string[];
  readonly relationship_type: TechnologyIndustryRelationshipType;
  readonly notes: string;
};

export type TechnologyIndustryThemeNodeLink = {
  readonly theme_node_id: string;
  readonly catalog_node_id: string;
};

export type TechnologyIndustryThemeLink = {
  readonly theme_id: string;
  readonly chain_id: string;
  readonly node_links: readonly TechnologyIndustryThemeNodeLink[];
  readonly unmapped_theme_node_ids: readonly string[];
};

export type TechnologyIndustryCatalogIndex = TechnologyIndustryCatalogGuardrails & {
  readonly summary: TechnologyIndustryCatalogSummary;
  readonly sectors: readonly TechnologyIndustrySector[];
  readonly chains: readonly TechnologyIndustryChain[];
};

export type TechnologyIndustryChainDetail = TechnologyIndustryCatalogGuardrails & {
  readonly chain: TechnologyIndustryChain;
  readonly nodes: readonly TechnologyIndustryNode[];
  readonly edges: readonly TechnologyIndustryEdge[];
  readonly theme_compositions: readonly TechnologyIndustryThemeComposition[];
  readonly theme_links: readonly TechnologyIndustryThemeLink[];
  readonly deep_research?: TechnologyIndustryDeepResearchSummary | null;
};
