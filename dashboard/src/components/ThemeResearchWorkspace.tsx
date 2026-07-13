import { ArrowLeft, ExternalLink, RefreshCw, Search } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import {
  fetchThemeResearchClaims,
  fetchThemeResearchCompanies,
  fetchThemeResearchNodes,
  fetchThemeResearchSources,
  fetchThemeResearchTheme,
  fetchThemeResearchThemes
} from '../api/themeResearch';
import type {
  ThemeResearchClaim,
  ThemeResearchCompany,
  ThemeResearchNode,
  ThemeResearchSource,
  ThemeResearchThemeCollection,
  ThemeResearchThemeDetail
} from '../types/themeResearch';

type ThemeResearchTab = 'overview' | 'nodes' | 'sources' | 'companies';

type Props = {
  pathname: string;
  onNavigate: (path: string) => void;
  onOpenStock: (path: string) => void;
};

type RouteState = {
  themeId: string;
  tab: ThemeResearchTab;
};

const TAB_LABELS: Record<ThemeResearchTab, string> = {
  overview: '主题概览',
  nodes: '产业链节点',
  sources: '来源证据',
  companies: '公司映射'
};

const NODE_LABELS: Record<string, string> = {
  power_generation: '发电',
  grid_connection: '电网接入',
  transformer: '变压器',
  switchgear: '开关设备',
  ups: 'UPS',
  hvdc_power: '高压直流供电',
  server_power_supply: '服务器电源',
  rack_power_distribution: '机架配电',
  liquid_cooling: '液冷',
  copper_interconnect: '铜互连',
  sic_gan_power_semiconductor: 'SiC/GaN 功率半导体',
  data_center_epc: '数据中心 EPC',
  ai_server_integration: 'AI 服务器集成',
  head_vision: '头部视觉',
  brain_ai_compute: '大脑与 AI 计算',
  torso_structure: '躯干结构',
  arm_actuator: '手臂执行器',
  hand_dexterous: '灵巧手',
  hip_joint: '髋关节',
  knee_joint: '膝关节',
  ankle_joint: '踝关节',
  frameless_motor: '无框力矩电机',
  harmonic_reducer: '谐波减速器',
  planetary_roller_screw: '行星滚柱丝杠',
  encoder: '编码器',
  torque_sensor: '扭矩传感器',
  six_axis_force_sensor: '六维力传感器',
  tactile_sensor: '触觉传感器',
  imu: 'IMU',
  battery_bms: '电池与 BMS',
  wiring_harness: '线束',
  controller: '控制器',
  bearing: '轴承',
  lightweight_materials: '轻量化材料'
};

const THEME_SUMMARIES: Record<string, string> = {
  ai_power_value_capture_v1: '从算力需求、数据中心供电瓶颈到电源、液冷和电网环节，追踪价值量、国产替代与证据缺口。',
  humanoid_robotics_head_to_toe_v1: '从人体功能系统拆到核心零部件、技术路线、价值量、卡脖子环节与国产替代。'
};

function themeSummary(themeId: string, fallback: string) {
  return THEME_SUMMARIES[themeId] ?? fallback;
}

function nodeLabel(nodeId: string, fallback = '') {
  return NODE_LABELS[nodeId] ?? (fallback || nodeId);
}

function parseRoute(pathname: string): RouteState | null {
  const match = pathname.match(/^\/theme-research\/([^/]+)(?:\/(nodes|sources|companies))?\/?$/);
  if (!match) return null;
  return {
    themeId: decodeURIComponent(match[1]),
    tab: (match[2] as ThemeResearchTab | undefined) ?? 'overview'
  };
}

function tabPath(themeId: string, tab: ThemeResearchTab) {
  return tab === 'overview' ? `/theme-research/${themeId}` : `/theme-research/${themeId}/${tab}`;
}

function readableStatus(value: string) {
  const labels: Record<string, string> = {
    draft: '草稿',
    reviewed: '已审核',
    published: '已发布',
    needs_evidence: '待补证据',
    blocked: '阻塞',
    accepted: '已采纳',
    needs_full_text: '待获取全文',
    lead_only: '仅作线索',
    rejected: '已拒绝',
    unknown: '未知',
    verified: '已验证',
    partially_verified: '部分验证',
    unverified: '未验证',
    contradicted: '已否定',
    research_lead: '研究线索',
    evidence_collection_priority: '证据补齐优先',
    deep_research_priority: '深度研究优先',
    monitor: '观察',
    linked_existing_universe: '已连接复盘库',
    coverage_gap: '覆盖缺口',
    pending_review: '待复盘',
    not_in_existing_universe: '不在现有复盘库',
    collect_node_evidence: '补充节点证据',
    deep_node_research: '节点深度研究',
    deep_company_research: '公司深度研究',
    strengthen_node_evidence_for_company: '补强公司节点证据',
    review_crosswalk_coverage_gap: '复核覆盖缺口',
    ai_power: 'AI 供电',
    humanoid_robotics: '人形机器人',
    infrastructure: '基础设施',
    equipment: '设备',
    subsystem: '子系统',
    core_component: '核心零部件',
    upstream_material: '上游材料',
    software: '软件',
    service: '服务',
    downstream_application: '下游应用',
    direct_product: '直接产品',
    component_supplier: '零部件供应',
    equipment_supplier: '设备供应',
    material_supplier: '材料供应',
    system_integrator: '系统集成',
    downstream_customer: '下游客户',
    core_business: '核心业务',
    meaningful_segment: '重要业务板块',
    emerging_segment: '成长业务板块',
    reserve_only: '技术储备',
    concept_only: '概念关联',
    official_report: '官方报告',
    official_article: '官方文章',
    broker_report: '券商研报',
    media_article: '媒体文章',
    video_claim: '视频口播',
    social_post: '社交内容',
    company_filing: '公司公告',
    demand_shock: '需求冲击',
    bottleneck: '卡脖子',
    value_capture: '价值量',
    supply_constraint: '供给约束',
    localization: '国产替代',
    company_mapping: '公司映射',
    cost_structure: '成本结构',
    tech_route: '技术路线',
    valuation_signal: '估值线索',
    public: '公开',
    gated: '受限访问',
    private_claimed: '声称私有'
  };
  return labels[value] ?? (value || '未标记');
}

function statusClass(value: string) {
  if (['reviewed', 'accepted', 'verified', 'deep_research_priority', 'linked_existing_universe'].includes(value)) {
    return 'is-positive';
  }
  if (['blocked', 'rejected', 'contradicted', 'coverage_gap'].includes(value)) {
    return 'is-negative';
  }
  if (['needs_evidence', 'lead_only', 'unverified', 'evidence_collection_priority', 'needs_full_text'].includes(value)) {
    return 'is-warning';
  }
  return 'is-neutral';
}

function StatusBadge({ value }: { value: string }) {
  return <span className={`theme-research-status ${statusClass(value)}`}>{readableStatus(value)}</span>;
}

function Score({ value }: { value: number }) {
  return <span className="theme-research-score">{Number.isInteger(value) ? value : value.toFixed(1)}</span>;
}

export function ThemeResearchWorkspace({ pathname, onNavigate, onOpenStock }: Props) {
  const route = parseRoute(pathname);
  const [themes, setThemes] = useState<ThemeResearchThemeCollection | null>(null);
  const [detail, setDetail] = useState<ThemeResearchThemeDetail | null>(null);
  const [nodes, setNodes] = useState<ThemeResearchNode[]>([]);
  const [sources, setSources] = useState<ThemeResearchSource[]>([]);
  const [claims, setClaims] = useState<ThemeResearchClaim[]>([]);
  const [companies, setCompanies] = useState<ThemeResearchCompany[]>([]);
  const [query, setQuery] = useState('');
  const [nodeState, setNodeState] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retryVersion, setRetryVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    setThemes(null);
    setDetail(null);
    setNodes([]);
    setSources([]);
    setClaims([]);
    setCompanies([]);
    const request = !route
      ? fetchThemeResearchThemes().then((nextThemes) => {
          if (!cancelled) setThemes(nextThemes);
        })
      : Promise.all([
          fetchThemeResearchTheme(route.themeId),
          route.tab === 'nodes' ? fetchThemeResearchNodes(route.themeId) : Promise.resolve(null),
          route.tab === 'sources' ? fetchThemeResearchSources(route.themeId) : Promise.resolve(null),
          route.tab === 'sources' ? fetchThemeResearchClaims(route.themeId) : Promise.resolve(null),
          route.tab === 'companies' ? fetchThemeResearchCompanies(route.themeId) : Promise.resolve(null)
        ]).then(([nextDetail, nextNodes, nextSources, nextClaims, nextCompanies]) => {
          if (cancelled) return;
          setDetail(nextDetail);
          setNodes(nextNodes?.items ?? []);
          setSources(nextSources?.items ?? []);
          setClaims(nextClaims?.items ?? []);
          setCompanies(nextCompanies?.items ?? []);
        });
    request
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : 'unknown_error');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [pathname, retryVersion]);

  const filteredThemes = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!themes || !normalized) return themes?.items ?? [];
    return themes.items.filter((theme) =>
      `${theme.theme_name} ${theme.theme_type} ${theme.summary}`.toLowerCase().includes(normalized)
    );
  }, [query, themes]);

  const filteredNodes = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return nodes.filter((node) => {
      const matchesQuery = !normalized || `${node.node_name} ${node.node_id} ${node.description}`.toLowerCase().includes(normalized);
      return matchesQuery && (!nodeState || node.priority_class === nodeState || node.node_review_status === nodeState);
    });
  }, [nodeState, nodes, query]);

  if (loading) {
    return <section className="workspace-band theme-research-state" aria-busy="true">正在加载主题研究数据...</section>;
  }

  if (error) {
    const notFound = error === 'theme_not_found';
    return (
      <section className="workspace-band theme-research-state" role="alert">
        <h1>{notFound ? '主题不存在' : '主题研究加载失败'}</h1>
        <p>{notFound ? '该主题未出现在当前已验证研究 artifact 中。' : '无法读取主题研究数据，请重试。'}</p>
        <button className="icon-text-button" type="button" onClick={() => setRetryVersion((value) => value + 1)}>
          <RefreshCw size={16} aria-hidden="true" /> 重试
        </button>
      </section>
    );
  }

  if (!route) {
    return (
      <section className="theme-research-workspace" aria-label="主题研究工作台">
        <header className="theme-research-header">
          <div>
            <h1>主题研究</h1>
            <p>产业链节点、证据来源与公司映射的只读研究视图</p>
          </div>
          <span className="theme-research-count">{themes?.total ?? 0} 个主题</span>
        </header>
        <div className="theme-research-toolbar">
          <label className="theme-research-search">
            <Search size={16} aria-hidden="true" />
            <span className="sr-only">搜索主题</span>
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索主题、类型或摘要" />
          </label>
        </div>
        {filteredThemes.length ? (
          <div className="theme-research-table-wrap">
            <table className="theme-research-table theme-research-theme-table">
              <thead>
                <tr>
                  <th>主题</th><th>状态</th><th>节点</th><th>来源</th><th>观点</th><th>公司</th><th>证据缺口</th><th>深度研究</th><th>更新</th>
                </tr>
              </thead>
              <tbody>
                {filteredThemes.map((theme) => (
                  <tr key={theme.theme_id}>
                    <td>
                      <button className="theme-research-primary-link" type="button" onClick={() => onNavigate(`/theme-research/${theme.theme_id}`)} aria-label={`打开${theme.theme_name}`}>
                        <strong>{theme.theme_name}</strong><small>{readableStatus(theme.theme_type)}</small>
                      </button>
                    </td>
                    <td><StatusBadge value={theme.status} /></td>
                    <td><Score value={theme.node_count} /></td>
                    <td><Score value={theme.source_count} /></td>
                    <td><Score value={theme.claim_count} /></td>
                    <td><Score value={theme.company_count} /></td>
                    <td><Score value={theme.evidence_gap_count} /></td>
                    <td><Score value={theme.deep_research_node_count} /></td>
                    <td>{theme.last_updated}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="theme-research-empty">当前筛选条件下没有主题。</div>
        )}
      </section>
    );
  }

  if (!detail) return null;
  return (
    <section className="theme-research-workspace" aria-label="主题研究详情">
      <header className="theme-research-header theme-research-detail-header">
        <button className="icon-button" type="button" onClick={() => onNavigate('/theme-research')} aria-label="返回主题列表">
          <ArrowLeft size={18} aria-hidden="true" />
        </button>
        <div>
          <div className="theme-research-title-line"><h1>{detail.theme.theme_name}</h1><StatusBadge value={detail.theme.status} /></div>
          <p>{themeSummary(detail.theme.theme_id, detail.theme.summary)}</p>
        </div>
        <time dateTime={detail.theme.last_updated}>更新 {detail.theme.last_updated}</time>
      </header>
      <div className="theme-research-metrics" aria-label="主题研究概况">
        <Metric label="产业链节点" value={detail.node_summary.total} />
        <Metric label="证据缺口" value={detail.evidence_gap_summary.total} tone="warning" />
        <Metric label="来源" value={detail.source_summary.total} />
        <Metric label="观点" value={detail.claim_summary.total} />
        <Metric label="公司映射" value={detail.company_summary.total} />
      </div>
      <nav className="theme-research-tabs" role="tablist" aria-label="主题研究视图">
        {(Object.keys(TAB_LABELS) as ThemeResearchTab[]).map((tab) => (
          <button key={tab} type="button" role="tab" aria-selected={route.tab === tab} onClick={() => onNavigate(tabPath(route.themeId, tab))}>
            {TAB_LABELS[tab]}
          </button>
        ))}
      </nav>
      {route.tab === 'overview' ? <Overview detail={detail} /> : null}
      {route.tab === 'nodes' ? (
        <NodesView nodes={filteredNodes} query={query} setQuery={setQuery} nodeState={nodeState} setNodeState={setNodeState} />
      ) : null}
      {route.tab === 'sources' ? <SourcesView sources={sources} claims={claims} /> : null}
      {route.tab === 'companies' ? <CompaniesView companies={companies} onOpenStock={onOpenStock} /> : null}
    </section>
  );
}

function Metric({ label, value, tone = '' }: { label: string; value: number; tone?: string }) {
  return <div className={`theme-research-metric ${tone}`}><span>{label}</span><strong>{value}</strong></div>;
}

function Overview({ detail }: { detail: ThemeResearchThemeDetail }) {
  return (
    <div className="theme-research-view">
      <section className="theme-research-section">
        <h2>优先节点</h2>
        <NodeTable nodes={detail.top_node_priorities} compact />
      </section>
      <section className="theme-research-section">
        <h2>待补证据缺口</h2>
        <NodeTable nodes={detail.evidence_gaps} compact />
      </section>
      <section className="theme-research-section">
        <h2>重点公司</h2>
        <PriorityCompanyTable companies={detail.top_company_priorities} />
      </section>
      <section className="theme-research-section">
        <h2>证据状态</h2>
        <div className="theme-research-distribution">
          {Object.entries(detail.claim_evidence_status_distribution).map(([status, count]) => (
            <div key={status}><StatusBadge value={status} /><strong>{count}</strong></div>
          ))}
        </div>
      </section>
    </div>
  );
}

function PriorityCompanyTable({ companies }: { companies: ThemeResearchCompany[] }) {
  if (!companies.length) return <div className="theme-research-empty">当前主题还没有重点公司映射。</div>;
  return (
    <div className="theme-research-table-wrap">
      <table className="theme-research-table theme-research-overview-company-table">
        <thead><tr><th>公司</th><th>节点</th><th>研究优先级</th><th>复盘库</th><th>动作</th></tr></thead>
        <tbody>{companies.map((company) => <tr key={company.mapping_id}><td><strong>{company.company_name}</strong><small>{company.company_code}</small></td><td>{nodeLabel(company.mapped_node.node_id, company.mapped_node.node_name)}</td><td><Score value={company.company_research_priority_score} /></td><td><StatusBadge value={company.integration_status} /></td><td>{readableStatus(company.recommended_action)}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

function NodesView({ nodes, query, setQuery, nodeState, setNodeState }: {
  nodes: ThemeResearchNode[];
  query: string;
  setQuery: (value: string) => void;
  nodeState: string;
  setNodeState: (value: string) => void;
}) {
  return (
    <div className="theme-research-view">
      <div className="theme-research-toolbar">
        <label className="theme-research-search"><Search size={16} aria-hidden="true" /><span className="sr-only">搜索节点</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索节点" /></label>
        <select aria-label="筛选节点状态" value={nodeState} onChange={(event) => setNodeState(event.target.value)}>
          <option value="">全部状态</option><option value="deep_research_priority">深度研究优先</option><option value="evidence_collection_priority">证据补齐优先</option><option value="needs_evidence">待补证据</option><option value="reviewed">已审核</option>
        </select>
      </div>
      <NodeTable nodes={nodes} />
    </div>
  );
}

function NodeTable({ nodes, compact = false }: { nodes: ThemeResearchNode[]; compact?: boolean }) {
  if (!nodes.length) return <div className="theme-research-empty">没有符合条件的产业链节点。</div>;
  return (
    <div className="theme-research-table-wrap">
      <table className={`theme-research-table theme-research-node-table ${compact ? 'is-compact' : ''}`}>
        <thead><tr><th>节点</th><th>类型</th><th>价值量</th><th>卡脖子</th><th>国产差距</th><th>供给</th><th>证据</th><th>优先级</th><th>审核</th><th>动作</th></tr></thead>
        <tbody>{nodes.map((node) => <tr key={node.node_id}><td><strong>{nodeLabel(node.node_id, node.node_name)}</strong><small>{node.node_id}</small></td><td>{readableStatus(node.node_type)}</td><td><Score value={node.value_capture_score} /></td><td><Score value={node.bottleneck_score} /></td><td><Score value={node.localization_gap_score} /></td><td><Score value={node.supply_tightness_score} /></td><td><Score value={node.evidence_strength} /></td><td><StatusBadge value={node.priority_class} /><Score value={node.priority_score} /></td><td><StatusBadge value={node.node_review_status} /></td><td>{readableStatus(node.recommended_action)}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

function SourcesView({ sources, claims }: { sources: ThemeResearchSource[]; claims: ThemeResearchClaim[] }) {
  return (
    <div className="theme-research-view">
      <header className="theme-research-view-header"><h2>来源证据</h2><span>{sources.length} 个来源 · {claims.length} 条观点</span></header>
      <section className="theme-research-section"><h2>来源清单</h2>{sources.length ? <div className="theme-research-table-wrap"><table className="theme-research-table"><thead><tr><th>来源</th><th>发布方</th><th>类型</th><th>访问</th><th>可靠性</th><th>审核</th><th>日期</th><th>关联观点</th></tr></thead><tbody>{sources.map((source) => <tr key={source.source_id}><td><strong>{source.title}</strong><small>{source.source_id}</small></td><td>{source.publisher}</td><td>{readableStatus(source.source_type)}</td><td>{readableStatus(source.access_level)}</td><td><span className="theme-research-reliability">{source.reliability_level}</span></td><td><StatusBadge value={source.review_status} /></td><td>{source.publish_date || '未标注'}</td><td><Score value={source.claim_count} /></td></tr>)}</tbody></table></div> : <div className="theme-research-empty">当前主题还没有关联来源。</div>}</section>
      <section className="theme-research-section"><h2>观点与证据状态</h2>{claims.length ? <div className="theme-research-table-wrap"><table className="theme-research-table"><thead><tr><th>观点</th><th>类型</th><th>主来源</th><th>支持来源</th><th>证据状态</th><th>平台用途</th><th>影响节点</th></tr></thead><tbody>{claims.map((claim) => <tr key={claim.claim_id}><td>{claim.claim_text}</td><td>{readableStatus(claim.claim_type)}</td><td><span className="theme-research-reliability">{claim.source_reliability_level}</span> {claim.source_title}</td><td>{claim.supporting_sources.length ? claim.supporting_sources.map((source) => source.title).join('；') : '无'}</td><td><StatusBadge value={claim.evidence_status} /></td><td><StatusBadge value={claim.platform_use_status} /></td><td>{claim.affected_theme_nodes.map((nodeId) => nodeLabel(nodeId)).join('、') || '未映射'}</td></tr>)}</tbody></table></div> : <div className="theme-research-empty">当前主题还没有结构化观点。</div>}</section>
    </div>
  );
}

function CompaniesView({ companies, onOpenStock }: { companies: ThemeResearchCompany[]; onOpenStock: (path: string) => void }) {
  return (
    <div className="theme-research-view">
      <header className="theme-research-view-header"><h2>公司映射</h2><span>{companies.length} 家公司</span></header>
      {companies.length ? <div className="theme-research-table-wrap"><table className="theme-research-table theme-research-company-table"><thead><tr><th>公司</th><th>节点</th><th>映射</th><th>相关度</th><th>业务重要性</th><th>证据</th><th>研究优先级</th><th>复盘库</th><th>操作</th></tr></thead><tbody>{companies.map((company) => <tr key={company.mapping_id}><td><strong>{company.company_name}</strong><small>{company.company_code}</small></td><td>{nodeLabel(company.mapped_node.node_id, company.mapped_node.node_name)}</td><td>{readableStatus(company.mapping_type)}</td><td><Score value={company.company_relevance_score} /></td><td>{readableStatus(company.business_materiality)}</td><td><Score value={company.mapped_node.evidence_strength} /></td><td><Score value={company.company_research_priority_score} /><small>{readableStatus(company.recommended_action)}</small></td><td><StatusBadge value={company.integration_status} /><small>{readableStatus(company.existing_review_context.status)}</small></td><td><button className="icon-button" type="button" onClick={() => onOpenStock(company.tech_bottleneck_stock_path)} aria-label={`打开${company.company_name}个股工作台`} title="打开个股工作台"><ExternalLink size={16} aria-hidden="true" /></button></td></tr>)}</tbody></table></div> : <div className="theme-research-empty">当前主题还没有公司映射。</div>}
    </div>
  );
}
