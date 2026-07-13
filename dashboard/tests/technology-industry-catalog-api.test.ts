import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  fetchTechnologyIndustryCatalog,
  fetchTechnologyIndustryChain
} from '../src/api/technologyIndustryCatalog';
import type {
  TechnologyIndustryCatalogIndex,
  TechnologyIndustryChainDetail
} from '../src/types/technologyIndustryCatalog';

const catalogPayload = {
  summary: {
    sector_count: 1,
    chain_count: 1,
    l3_node_count: 1,
    l4_node_count: 1,
    edge_count: 1,
    theme_composition_count: 1,
    chains_by_kind: { application_theme_chain: 1 },
    chains_by_decomposition_method: { infrastructure_flow: 1 },
    chains_by_status: { draft: 1 },
    chains_by_sector: { energy_technology_new_power_system: 1 },
    nodes_by_status: { draft: 2 },
    detailed_chain_count: 1,
    skeleton_chain_count: 0,
    structural_completeness_percent: 100,
    unexpanded_chain_ids: []
  },
  sectors: [
    {
      sector_id: 'energy_technology_new_power_system',
      sector_name: 'Energy Technology and New Power Systems',
      description: 'Energy technology sector.',
      status: 'draft',
      order: 1
    }
  ],
  chains: [
    {
      chain_id: 'ai_data_center_power',
      sector_id: 'energy_technology_new_power_system',
      chain_name: 'AI Data Center Power',
      chain_kind: 'application_theme_chain',
      decomposition_method: 'infrastructure_flow',
      description: 'AI data center power chain.',
      scope: 'Power infrastructure and operations.',
      exclusions: ['Compute hardware'],
      aliases: ['AI Power'],
      status: 'draft',
      order: 1
    }
  ],
  research_only: true,
  used_for_signal: false,
  used_for_admission: false
} satisfies TechnologyIndustryCatalogIndex;

const chainPayload = {
  chain: catalogPayload.chains[0],
  nodes: [
    {
      node_id: 'ai_power_distribution',
      chain_id: 'ai_data_center_power',
      parent_node_id: null,
      level: 'L3',
      node_name: 'Power Distribution',
      node_kind: 'application_role',
      node_type: 'infrastructure_flow_stage',
      description: 'Power distribution stage.',
      status: 'draft',
      primary_path: [
        'energy_technology_new_power_system',
        'ai_data_center_power',
        'ai_power_distribution'
      ],
      canonical_key: '',
      canonical_node_refs: []
    }
  ],
  edges: [
    {
      edge_id: 'ai_power_distribution_uses_switchgear',
      source_node_id: 'ai_power_distribution',
      target_node_id: 'switchgear',
      relationship_type: 'uses',
      notes: 'Distribution uses switchgear.',
      source_ids: []
    }
  ],
  theme_compositions: [
    {
      composition_id: 'ai_power_distribution_composition',
      chain_id: 'ai_data_center_power',
      role_node_id: 'ai_power_distribution',
      canonical_node_refs: ['switchgear'],
      relationship_type: 'depends_on',
      notes: 'Maps the application role to the canonical node.'
    }
  ],
  theme_links: [
    {
      theme_id: 'ai_power_value_capture_v1',
      chain_id: 'ai_data_center_power',
      node_links: [
        {
          theme_node_id: 'switchgear',
          catalog_node_id: 'ai_power_distribution'
        }
      ],
      unmapped_theme_node_ids: []
    }
  ],
  research_only: true,
  used_for_signal: false,
  used_for_admission: false
} satisfies TechnologyIndustryChainDetail;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('technology industry catalog API client', () => {
  it('fetches the catalog index from the exact read-only path and returns the payload', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => catalogPayload
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchTechnologyIndustryCatalog();

    expect(fetchMock).toHaveBeenCalledWith('/api/research/technology-industry-catalog');
    expect(result).toBe(catalogPayload);
  });

  it('encodes the chain id, fetches the exact detail path, and returns the payload', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => chainPayload
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchTechnologyIndustryChain('ai power/primary');

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/research/technology-industry-catalog/chains/ai%20power%2Fprimary'
    );
    expect(result).toBe(chainPayload);
  });

  it('rejects with the backend error detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ detail: 'chain_not_found' })
      })
    );

    await expect(fetchTechnologyIndustryChain('missing-chain')).rejects.toEqual(
      new Error('chain_not_found')
    );
  });

  it('falls back to the response status when the error detail cannot be read', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => {
          throw new Error('invalid json');
        }
      })
    );

    await expect(fetchTechnologyIndustryCatalog()).rejects.toEqual(
      new Error('request_failed_503')
    );
  });
});
