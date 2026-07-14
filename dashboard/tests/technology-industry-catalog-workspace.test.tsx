import '@testing-library/jest-dom/vitest';
import { useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { IndustryCatalogWorkspace } from '../src/components/IndustryCatalogWorkspace';
import { ThemeResearchAndIndustryCatalogWorkspace } from '../src/components/ThemeResearchAndIndustryCatalogWorkspace';
import type {
  TechnologyIndustryCatalogIndex,
  TechnologyIndustryChainDetail
} from '../src/types/technologyIndustryCatalog';

const apiMocks = vi.hoisted(() => ({
  fetchTechnologyIndustryCatalog: vi.fn(),
  fetchTechnologyIndustryChain: vi.fn()
}));

vi.mock('../src/api/technologyIndustryCatalog', () => apiMocks);

const catalogPayload = {
  summary: {
    sector_count: 10,
    chain_count: 82,
    l3_node_count: 24,
    l4_node_count: 46,
    edge_count: 12,
    theme_composition_count: 2,
    chains_by_kind: { canonical_industry_chain: 40, application_theme_chain: 30, frontier_technology_chain: 12 },
    chains_by_decomposition_method: { manufacturing_process: 30, system_architecture: 20, infrastructure_flow: 20, technical_route: 12 },
    chains_by_status: { skeleton: 69, draft: 13 },
    chains_by_sector: { robotics: 1, energy: 2 },
    nodes_by_status: { draft: 70 },
    detailed_chain_count: 13,
    skeleton_chain_count: 69,
    structural_completeness_percent: 15.85,
    unexpanded_chain_ids: ['grid_storage']
  },
  sectors: [
    { sector_id: 'energy', sector_name: '能源科技', description: '新能源与电力系统。', status: 'draft', order: 2 },
    { sector_id: 'robotics', sector_name: '机器人', description: '机器人本体与零部件。', status: 'draft', order: 1 }
  ],
  chains: [
    {
      chain_id: 'grid_storage',
      sector_id: 'energy',
      chain_name: '电网储能',
      chain_kind: 'canonical_industry_chain',
      decomposition_method: 'system_architecture',
      description: '电网侧储能系统。',
      scope: '电网侧储能。',
      exclusions: [],
      aliases: ['大储'],
      status: 'draft',
      order: 2
    },
    {
      chain_id: 'ai_data_center_power',
      sector_id: 'energy',
      chain_name: 'AI 数据中心供电',
      chain_kind: 'application_theme_chain',
      decomposition_method: 'infrastructure_flow',
      description: '从并网到机架配电和液冷的供电基础设施。',
      scope: '数据中心供电基础设施。',
      exclusions: ['算力芯片'],
      aliases: ['AI Power', '智算中心电力'],
      status: 'skeleton',
      order: 1,
      deep_research: {
        chain_id: 'ai_data_center_power', chain_name: 'AI 数据中心供电', theme_id: 'ai_power_value_capture_v1',
        theme_title: 'AI供电产业链：谁在拿走价值量', theme_route: '/theme-research/ai_power_value_capture_v1',
        research_status: 'researching', freshness_status: 'current', source_count: 10, claim_count: 8,
        reviewed_company_count: 4, evidence_gap_count: 3, last_updated: '2026-07-14'
      }
    },
    {
      chain_id: 'humanoid_robot',
      sector_id: 'robotics',
      chain_name: '人形机器人',
      chain_kind: 'frontier_technology_chain',
      decomposition_method: 'technical_route',
      description: '人形机器人技术路线。',
      scope: '机器人本体。',
      exclusions: [],
      aliases: ['具身智能'],
      status: 'reviewed',
      order: 1
    }
  ],
  research_only: true,
  used_for_signal: false,
  used_for_admission: false
} satisfies TechnologyIndustryCatalogIndex;

const aiPowerDetail = {
  chain: catalogPayload.chains[1],
  nodes: [
    {
      node_id: 'power_distribution', chain_id: 'ai_data_center_power', parent_node_id: null, level: 'L3',
      node_name: '供配电系统', node_kind: 'application_role', node_type: 'infrastructure_stage',
      description: '园区到机架的供配电。', status: 'draft', primary_path: [], canonical_key: '', canonical_node_refs: []
    },
    {
      node_id: 'switchgear', chain_id: 'ai_data_center_power', parent_node_id: 'power_distribution', level: 'L4',
      node_name: '开关柜', node_kind: 'canonical', node_type: 'equipment',
      description: '配电开关设备。', status: 'draft', primary_path: [], canonical_key: 'switchgear', canonical_node_refs: []
    },
    {
      node_id: 'liquid_cooling', chain_id: 'ai_data_center_power', parent_node_id: null, level: 'L3',
      node_name: '液冷系统', node_kind: 'application_role', node_type: 'thermal_stage',
      description: '数据中心液冷环节。', status: 'reviewed', primary_path: [], canonical_key: '', canonical_node_refs: []
    }
  ],
  edges: [
    {
      edge_id: 'distribution_enables_cooling', source_node_id: 'power_distribution', target_node_id: 'liquid_cooling',
      relationship_type: 'enables', notes: '稳定供电支持液冷运行。', source_ids: []
    }
  ],
  theme_compositions: [],
  theme_links: [
    {
      theme_id: 'ai_power_value_capture_v1', chain_id: 'ai_data_center_power',
      node_links: [{ theme_node_id: 'theme_switchgear', catalog_node_id: 'switchgear' }],
      unmapped_theme_node_ids: ['theme_backup_generator']
    }
  ],
  deep_research: catalogPayload.chains[1].deep_research,
  research_only: true,
  used_for_signal: false,
  used_for_admission: false
} satisfies TechnologyIndustryChainDetail;

const skeletonDetail = {
  ...aiPowerDetail,
  chain: catalogPayload.chains[0],
  nodes: [],
  edges: [],
  theme_links: []
} satisfies TechnologyIndustryChainDetail;

function CatalogNavigationHarness() {
  const [pathname, setPathname] = useState('/theme-research/catalog');
  return (
    <ThemeResearchAndIndustryCatalogWorkspace
      pathname={pathname}
      onNavigate={setPathname}
      onOpenStock={vi.fn()}
    />
  );
}

describe('IndustryCatalogWorkspace', () => {
  beforeEach(() => {
    apiMocks.fetchTechnologyIndustryCatalog.mockReset().mockResolvedValue(catalogPayload);
    apiMocks.fetchTechnologyIndustryChain.mockReset().mockImplementation((chainId: string) => {
      if (chainId === 'ai_data_center_power') return Promise.resolve(aiPowerDetail);
      if (chainId === 'grid_storage') return Promise.resolve(skeletonDetail);
      return Promise.reject(new Error('chain_not_found'));
    });
  });

  afterEach(() => cleanup());

  it('renders API summary metrics and groups chains in stable sector and chain order', async () => {
    render(<IndustryCatalogWorkspace pathname="/theme-research/catalog" onNavigate={vi.fn()} />);

    expect(screen.getByText('正在加载科技产业目录...')).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: '科技产业目录' })).toBeInTheDocument();
    expect(screen.getByText(/只读/)).toBeInTheDocument();
    expect(within(screen.getByLabelText('产业目录概况')).getByText('10')).toBeInTheDocument();
    expect(within(screen.getByLabelText('产业目录概况')).getByText('82')).toBeInTheDocument();
    expect(within(screen.getByLabelText('产业目录概况')).getByText('13')).toBeInTheDocument();
    expect(within(screen.getByLabelText('产业目录概况')).getByText('69')).toBeInTheDocument();
    expect(within(screen.getByLabelText('产业目录概况')).getByText('15.85%')).toBeInTheDocument();

    const groups = screen.getAllByRole('heading', { level: 2 });
    expect(groups.map((heading) => heading.textContent)).toEqual(['机器人', '能源科技']);
    const energyGroup = screen.getByRole('region', { name: '能源科技产业链' });
    expect(within(energyGroup).getAllByRole('button').map((button) => button.textContent)).toEqual([
      expect.stringContaining('AI 数据中心供电'),
      expect.stringContaining('电网储能')
    ]);
    const aiChainRow = screen.getByRole('button', { name: /打开AI 数据中心供电产业链/ }).closest('tr');
    expect(aiChainRow).not.toBeNull();
    expect(within(aiChainRow as HTMLTableRowElement).getByText('应用主题链')).toBeInTheDocument();
    expect(within(aiChainRow as HTMLTableRowElement).getByText('基础设施流')).toBeInTheDocument();
  });

  it('renders stable styling hooks without replacing accessible catalog labels', async () => {
    const indexRender = render(<IndustryCatalogWorkspace pathname="/theme-research/catalog" onNavigate={vi.fn()} />);

    const indexRoot = (await screen.findByRole('heading', { name: '科技产业目录' })).closest('section');
    expect(indexRoot).toHaveClass('industry-catalog-workspace', 'industry-catalog-index');
    expect(screen.getByRole('region', { name: '能源科技产业链' })).toHaveClass('industry-catalog-sector');
    expect(indexRoot?.querySelector('.industry-catalog-table-wrap')).toBeInTheDocument();
    expect(indexRoot?.querySelector('.industry-catalog-table')).toBeInTheDocument();

    indexRender.unmount();
    render(<IndustryCatalogWorkspace pathname="/theme-research/catalog/ai_data_center_power" onNavigate={vi.fn()} />);

    const detailRoot = (await screen.findByRole('heading', { name: 'AI 数据中心供电' })).closest('section');
    expect(detailRoot).toHaveClass('industry-catalog-workspace', 'industry-catalog-detail-grid');
    expect(screen.getByLabelText('产业链定义')).toHaveClass('industry-catalog-definition');
    expect(screen.getByLabelText('L3和L4节点')).toHaveClass('industry-catalog-node-groups');
    expect(screen.getByRole('region', { name: '供配电系统节点组' })).toHaveClass('industry-catalog-node-group');
    expect(screen.getByLabelText('产业链边关系')).toHaveClass('industry-catalog-edges');
    expect(screen.getByLabelText('关联主题')).toHaveClass('industry-catalog-theme-links');
    expect(detailRoot?.querySelector('.industry-catalog-table-wrap')).toBeInTheDocument();
    expect(detailRoot?.querySelector('.industry-catalog-table')).toBeInTheDocument();
  });

  it('treats a trailing slash catalog path as the index', async () => {
    render(<IndustryCatalogWorkspace pathname="/theme-research/catalog/" onNavigate={vi.fn()} />);

    expect(await screen.findByRole('heading', { name: '科技产业目录' })).toBeInTheDocument();
    expect(apiMocks.fetchTechnologyIndustryCatalog).toHaveBeenCalledTimes(1);
    expect(apiMocks.fetchTechnologyIndustryChain).not.toHaveBeenCalled();
  });

  it('searches names, aliases and descriptions and supports an empty filter state', async () => {
    render(<IndustryCatalogWorkspace pathname="/theme-research/catalog" onNavigate={vi.fn()} />);
    await screen.findByRole('heading', { name: '科技产业目录' });

    fireEvent.change(screen.getByRole('textbox', { name: '搜索产业目录' }), { target: { value: 'AI 数据中心供电' } });
    expect(screen.getByRole('button', { name: /打开AI 数据中心供电产业链/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /打开电网储能产业链/ })).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole('textbox', { name: '搜索产业目录' }), { target: { value: '大储' } });
    expect(screen.getByRole('button', { name: /打开电网储能产业链/ })).toBeInTheDocument();

    fireEvent.change(screen.getByRole('textbox', { name: '搜索产业目录' }), { target: { value: '新能源与电力系统' } });
    expect(screen.getByRole('button', { name: /打开AI 数据中心供电产业链/ })).toBeInTheDocument();

    fireEvent.change(screen.getByRole('textbox', { name: '搜索产业目录' }), { target: { value: '机架配电和液冷' } });
    expect(screen.getByRole('button', { name: /打开AI 数据中心供电产业链/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /打开电网储能产业链/ })).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole('textbox', { name: '搜索产业目录' }), { target: { value: '不存在的产业' } });
    expect(screen.getByText('当前筛选条件下没有产业链。')).toBeInTheDocument();
  });

  it('filters by sector and derives expansion independently from chain status', async () => {
    render(<IndustryCatalogWorkspace pathname="/theme-research/catalog" onNavigate={vi.fn()} />);
    await screen.findByRole('heading', { name: '科技产业目录' });

    fireEvent.change(screen.getByRole('combobox', { name: '产业板块筛选' }), { target: { value: 'energy' } });
    expect(screen.queryByRole('heading', { name: '机器人' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '能源科技' })).toBeInTheDocument();

    const aiRow = screen.getByRole('button', { name: /打开AI 数据中心供电产业链/ });
    expect(aiRow).toHaveTextContent('骨架');
    expect(aiRow).toHaveTextContent('已展开');
    const storageRow = screen.getByRole('button', { name: /打开电网储能产业链/ });
    expect(storageRow).toHaveTextContent('草稿');
    expect(storageRow).toHaveTextContent('未展开');
  });

  it('navigates from a chain row to its encoded catalog detail route', async () => {
    const onNavigate = vi.fn();
    render(<IndustryCatalogWorkspace pathname="/theme-research/catalog" onNavigate={onNavigate} />);
    await screen.findByRole('heading', { name: '科技产业目录' });

    fireEvent.click(screen.getByRole('button', { name: /打开AI 数据中心供电产业链/ }));
    expect(onNavigate).toHaveBeenCalledWith('/theme-research/catalog/ai_data_center_power');
  });

  it('shows deep-research status in the directory and opens the linked Theme Research page', async () => {
    const onNavigate = vi.fn();
    const indexRender = render(<IndustryCatalogWorkspace pathname="/theme-research/catalog" onNavigate={onNavigate} />);
    await screen.findByRole('heading', { name: '科技产业目录' });

    const aiRow = screen.getByRole('button', { name: /打开AI 数据中心供电产业链/ }).closest('tr');
    expect(aiRow).not.toBeNull();
    expect(within(aiRow as HTMLTableRowElement).getByText('研究中')).toBeInTheDocument();

    indexRender.unmount();
    render(<IndustryCatalogWorkspace pathname="/theme-research/catalog/ai_data_center_power" onNavigate={onNavigate} />);
    const card = await screen.findByRole('region', { name: '产业链深度研究' });
    expect(within(card).getByText('AI供电产业链：谁在拿走价值量')).toBeInTheDocument();
    expect(within(card).getByText('10 个来源')).toBeInTheDocument();
    expect(within(card).getByText('4 家已审核公司')).toBeInTheDocument();

    fireEvent.click(within(card).getByRole('button', { name: '进入深度研究' }));
    expect(onNavigate).toHaveBeenCalledWith('/theme-research/ai_power_value_capture_v1');
  });

  it('preserves index search and sector filters after opening a chain and returning', async () => {
    render(<CatalogNavigationHarness />);
    await screen.findByRole('heading', { name: '科技产业目录' });

    fireEvent.change(screen.getByRole('textbox', { name: '搜索产业目录' }), { target: { value: '供电' } });
    fireEvent.change(screen.getByRole('combobox', { name: '产业板块筛选' }), { target: { value: 'energy' } });
    fireEvent.click(screen.getByRole('button', { name: /打开AI 数据中心供电产业链/ }));

    expect(await screen.findByRole('heading', { name: 'AI 数据中心供电' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '返回产业目录' }));

    expect(await screen.findByRole('heading', { name: '科技产业目录' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '搜索产业目录' })).toHaveValue('供电');
    expect(screen.getByRole('combobox', { name: '产业板块筛选' })).toHaveValue('energy');
    expect(screen.getByRole('button', { name: /打开AI 数据中心供电产业链/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /打开人形机器人产业链/ })).not.toBeInTheDocument();
  });

  it('decodes the exact detail route and renders scope, grouped nodes, edges and linked themes', async () => {
    const onNavigate = vi.fn();
    render(<IndustryCatalogWorkspace pathname="/theme-research/catalog/ai_data_center_power" onNavigate={onNavigate} />);

    expect(await screen.findByRole('heading', { name: 'AI 数据中心供电' })).toBeInTheDocument();
    expect(apiMocks.fetchTechnologyIndustryChain).toHaveBeenCalledWith('ai_data_center_power');
    expect(screen.getByText('数据中心供电基础设施。')).toBeInTheDocument();
    expect(screen.getByText('算力芯片')).toBeInTheDocument();
    expect(screen.getByText(/AI Power/)).toBeInTheDocument();
    const chainDefinition = screen.getByLabelText('产业链定义');
    expect(within(chainDefinition).getByText('骨架')).toBeInTheDocument();
    expect(within(chainDefinition).getByText('基础设施流')).toBeInTheDocument();
    const distribution = screen.getByRole('region', { name: '供配电系统节点组' });
    expect(within(distribution).getByText('开关柜')).toBeInTheDocument();
    expect(screen.getByText('稳定供电支持液冷运行。')).toBeInTheDocument();
    expect(screen.getByText('已映射 1')).toBeInTheDocument();
    expect(screen.getByText('未映射 1')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '打开关联主题 ai_power_value_capture_v1' }));
    expect(onNavigate).toHaveBeenCalledWith('/theme-research/ai_power_value_capture_v1');
    fireEvent.click(screen.getByRole('button', { name: '返回产业目录' }));
    expect(onNavigate).toHaveBeenCalledWith('/theme-research/catalog');
  });

  it('exposes explicit mapped pairs and unmapped theme node IDs in a compact disclosure', async () => {
    render(<IndustryCatalogWorkspace pathname="/theme-research/catalog/ai_data_center_power" onNavigate={vi.fn()} />);

    await screen.findByRole('heading', { name: 'AI 数据中心供电' });
    const summary = screen.getByLabelText('查看 ai_power_value_capture_v1 节点映射详情');
    expect(summary.tagName).toBe('SUMMARY');
    expect(summary).toHaveTextContent('已映射 1');
    expect(summary).toHaveTextContent('未映射 1');

    fireEvent.click(summary);
    const disclosure = summary.closest('details');
    expect(disclosure).not.toBeNull();
    expect(within(disclosure as HTMLDetailsElement).getByRole('listitem', { name: 'theme_switchgear 映射到 switchgear' })).toBeInTheDocument();
    const unmappedNodes = within(disclosure as HTMLDetailsElement).getByRole('list', { name: '未映射主题节点' });
    expect(within(unmappedNodes).getByText('theme_backup_generator')).toBeInTheDocument();
  });

  it('states clearly when a linked theme has no unmapped nodes', async () => {
    apiMocks.fetchTechnologyIndustryChain.mockResolvedValueOnce({
      ...aiPowerDetail,
      theme_links: [{
        ...aiPowerDetail.theme_links[0],
        unmapped_theme_node_ids: []
      }]
    });
    render(<IndustryCatalogWorkspace pathname="/theme-research/catalog/ai_data_center_power" onNavigate={vi.fn()} />);

    await screen.findByRole('heading', { name: 'AI 数据中心供电' });
    const summary = screen.getByLabelText('查看 ai_power_value_capture_v1 节点映射详情');
    expect(summary).toHaveTextContent('未映射 0');
    fireEvent.click(summary);
    expect(within(summary.closest('details') as HTMLDetailsElement).getByText('无未映射节点')).toBeInTheDocument();
  });

  it('shows the explicit empty node message for an unexpanded chain', async () => {
    render(<IndustryCatalogWorkspace pathname="/theme-research/catalog/grid_storage" onNavigate={vi.fn()} />);
    expect(await screen.findByRole('heading', { name: '电网储能' })).toBeInTheDocument();
    expect(screen.getByText('该产业链尚未展开 L3/L4 节点')).toBeInTheDocument();
  });

  it('shows the unknown-chain state without retrying', async () => {
    render(<IndustryCatalogWorkspace pathname="/theme-research/catalog/missing" onNavigate={vi.fn()} />);
    expect(await screen.findByRole('heading', { name: '产业链不存在' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重试' })).not.toBeInTheDocument();
  });

  it('retries other catalog errors', async () => {
    apiMocks.fetchTechnologyIndustryCatalog
      .mockRejectedValueOnce(new Error('request_failed_500'))
      .mockResolvedValueOnce(catalogPayload);
    render(<IndustryCatalogWorkspace pathname="/theme-research/catalog" onNavigate={vi.fn()} />);

    fireEvent.click(await screen.findByRole('button', { name: '重试' }));

    await waitFor(() => expect(apiMocks.fetchTechnologyIndustryCatalog).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole('heading', { name: '科技产业目录' })).toBeInTheDocument();
  });

  it('retries a failed detail request and renders the chain after the next request succeeds', async () => {
    apiMocks.fetchTechnologyIndustryChain
      .mockRejectedValueOnce(new Error('request_failed_500'))
      .mockResolvedValueOnce(aiPowerDetail);
    render(<IndustryCatalogWorkspace pathname="/theme-research/catalog/ai_data_center_power" onNavigate={vi.fn()} />);

    fireEvent.click(await screen.findByRole('button', { name: '重试' }));

    await waitFor(() => expect(apiMocks.fetchTechnologyIndustryChain).toHaveBeenCalledTimes(2));
    expect(apiMocks.fetchTechnologyIndustryChain).toHaveBeenNthCalledWith(1, 'ai_data_center_power');
    expect(apiMocks.fetchTechnologyIndustryChain).toHaveBeenNthCalledWith(2, 'ai_data_center_power');
    expect(await screen.findByRole('heading', { name: 'AI 数据中心供电' })).toBeInTheDocument();
  });

  it('rejects encoded chain IDs that decode to multiple path segments', async () => {
    render(<IndustryCatalogWorkspace pathname="/theme-research/catalog/ai%20power%2Fprimary" onNavigate={vi.fn()} />);
    expect(await screen.findByRole('heading', { name: '产业链不存在' })).toBeInTheDocument();
    expect(apiMocks.fetchTechnologyIndustryChain).not.toHaveBeenCalled();
  });
});
