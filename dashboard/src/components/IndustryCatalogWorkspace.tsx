import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, ChevronRight, Link2, RefreshCw, Search } from 'lucide-react';
import {
  fetchTechnologyIndustryCatalog,
  fetchTechnologyIndustryChain
} from '../api/technologyIndustryCatalog';
import type {
  TechnologyIndustryCatalogIndex,
  TechnologyIndustryCatalogStatus,
  TechnologyIndustryChainDetail,
  TechnologyIndustryChainKind,
  TechnologyIndustryDecompositionMethod,
  TechnologyIndustryNode
} from '../types/technologyIndustryCatalog';

type IndustryCatalogWorkspaceProps = {
  pathname: string;
  onNavigate: (path: string) => void;
};

const STATUS_LABELS: Record<TechnologyIndustryCatalogStatus, string> = {
  skeleton: '骨架',
  draft: '草稿',
  reviewed: '已复核',
  published: '已发布'
};

const KIND_LABELS: Record<TechnologyIndustryChainKind, string> = {
  canonical_industry_chain: '标准产业链',
  application_theme_chain: '应用主题链',
  frontier_technology_chain: '前沿技术链'
};

const METHOD_LABELS: Record<TechnologyIndustryDecompositionMethod, string> = {
  manufacturing_process: '制造流程',
  system_architecture: '系统架构',
  infrastructure_flow: '基础设施流',
  technical_route: '技术路线'
};

function detailChainId(pathname: string) {
  const match = pathname.match(/^\/theme-research\/catalog\/([^/]+)$/);
  if (!match) return null;
  try {
    const decoded = decodeURIComponent(match[1]);
    return decoded.includes('/') ? null : decoded;
  } catch {
    return null;
  }
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="theme-research-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Status({ value }: { value: TechnologyIndustryCatalogStatus }) {
  return <span className="theme-research-status">{STATUS_LABELS[value]}</span>;
}

function ErrorState({ error, onRetry }: { error: string; onRetry: () => void }) {
  if (error === 'chain_not_found') {
    return (
      <section className="workspace-band theme-research-state" role="alert">
        <h1>产业链不存在</h1>
        <p>该产业链未出现在当前科技产业目录中。</p>
      </section>
    );
  }
  return (
    <section className="workspace-band theme-research-state" role="alert">
      <h1>科技产业目录加载失败</h1>
      <p>无法读取科技产业目录数据，请重试。</p>
      <button className="icon-text-button" type="button" onClick={onRetry}>
        <RefreshCw size={16} aria-hidden="true" /> 重试
      </button>
    </section>
  );
}

export function IndustryCatalogWorkspace({ pathname, onNavigate }: IndustryCatalogWorkspaceProps) {
  const isIndex = pathname === '/theme-research/catalog' || pathname === '/theme-research/catalog/';
  const chainId = isIndex ? null : detailChainId(pathname);
  const [catalog, setCatalog] = useState<TechnologyIndustryCatalogIndex | null>(null);
  const [detail, setDetail] = useState<TechnologyIndustryChainDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retryVersion, setRetryVersion] = useState(0);
  const [query, setQuery] = useState('');
  const [sectorId, setSectorId] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    setCatalog(null);
    setDetail(null);

    if (!isIndex && !chainId) {
      setError('chain_not_found');
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }

    const request = isIndex
      ? fetchTechnologyIndustryCatalog().then((payload) => {
          if (!cancelled) setCatalog(payload);
        })
      : fetchTechnologyIndustryChain(chainId as string).then((payload) => {
          if (!cancelled) setDetail(payload);
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
  }, [chainId, isIndex, retryVersion]);

  if (loading) {
    return (
      <section className="workspace-band theme-research-state" aria-busy="true">
        正在加载科技产业目录...
      </section>
    );
  }

  if (error) {
    return <ErrorState error={error} onRetry={() => setRetryVersion((value) => value + 1)} />;
  }

  if (isIndex && catalog) {
    return (
      <CatalogIndex
        catalog={catalog}
        query={query}
        sectorId={sectorId}
        onQueryChange={setQuery}
        onSectorChange={setSectorId}
        onNavigate={onNavigate}
      />
    );
  }

  if (detail) return <CatalogDetail detail={detail} onNavigate={onNavigate} />;
  return null;
}

type CatalogIndexProps = {
  catalog: TechnologyIndustryCatalogIndex;
  query: string;
  sectorId: string;
  onQueryChange: (value: string) => void;
  onSectorChange: (value: string) => void;
  onNavigate: (path: string) => void;
};

function CatalogIndex({
  catalog,
  query,
  sectorId,
  onQueryChange,
  onSectorChange,
  onNavigate
}: CatalogIndexProps) {
  const sectors = useMemo(() => [...catalog.sectors].sort((left, right) => left.order - right.order), [catalog.sectors]);
  const groupedChains = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return sectors
      .filter((sector) => !sectorId || sector.sector_id === sectorId)
      .map((sector) => ({
        sector,
        chains: catalog.chains
          .filter((chain) => chain.sector_id === sector.sector_id)
          .filter((chain) => {
            if (!normalized) return true;
            return [sector.sector_name, sector.description, chain.chain_name, chain.description, ...chain.aliases]
              .join(' ')
              .toLowerCase()
              .includes(normalized);
          })
          .sort((left, right) => left.order - right.order)
      }))
      .filter((group) => group.chains.length > 0);
  }, [catalog.chains, query, sectorId, sectors]);

  const unexpanded = useMemo(() => new Set(catalog.summary.unexpanded_chain_ids), [catalog.summary.unexpanded_chain_ids]);

  return (
    <section className="theme-research-workspace industry-catalog-workspace industry-catalog-index" aria-label="科技产业目录">
      <header className="theme-research-header">
        <div>
          <h1>科技产业目录</h1>
          <p>按科技板块与产业链层级组织的只读研究目录</p>
        </div>
        <span className="theme-research-count">{catalog.summary.chain_count} 条产业链</span>
      </header>
      <div className="theme-research-metrics" aria-label="产业目录概况">
        <Metric label="板块" value={catalog.summary.sector_count} />
        <Metric label="产业链" value={catalog.summary.chain_count} />
        <Metric label="已详细展开" value={catalog.summary.detailed_chain_count} />
        <Metric label="骨架链" value={catalog.summary.skeleton_chain_count} />
        <Metric label="结构完整度" value={`${catalog.summary.structural_completeness_percent}%`} />
      </div>
      <div className="theme-research-toolbar">
        <label className="theme-research-search">
          <Search size={16} aria-hidden="true" />
          <span className="sr-only">搜索产业目录</span>
          <input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="搜索板块、产业链、别名或描述"
          />
        </label>
        <label>
          <span className="sr-only">产业板块筛选</span>
          <select value={sectorId} onChange={(event) => onSectorChange(event.target.value)}>
            <option value="">全部板块</option>
            {sectors.map((sector) => (
              <option key={sector.sector_id} value={sector.sector_id}>{sector.sector_name}</option>
            ))}
          </select>
        </label>
      </div>
      {groupedChains.length ? groupedChains.map(({ sector, chains }) => (
        <section key={sector.sector_id} className="theme-research-section industry-catalog-sector" role="region" aria-label={`${sector.sector_name}产业链`}>
          <div className="theme-research-view-header">
            <h2>{sector.sector_name}</h2>
            <span>{chains.length} 条</span>
          </div>
          <div className="theme-research-table-wrap industry-catalog-table-wrap">
            <table className="theme-research-table industry-catalog-table">
              <thead>
                <tr><th>产业链</th><th>类型</th><th>拆解方法</th><th>状态</th><th>节点展开</th></tr>
              </thead>
              <tbody>
                {chains.map((chain) => {
                  const expanded = !unexpanded.has(chain.chain_id);
                  return (
                    <tr key={chain.chain_id}>
                      <td>
                        <button
                          className="theme-research-primary-link"
                          type="button"
                          aria-label={`打开${chain.chain_name}产业链`}
                          onClick={() => onNavigate(`/theme-research/catalog/${encodeURIComponent(chain.chain_id)}`)}
                        >
                          <strong>{chain.chain_name}</strong>
                          <small>{chain.description}</small>
                          <small>{STATUS_LABELS[chain.status]} · {expanded ? '已展开' : '未展开'}</small>
                          <ChevronRight size={16} aria-hidden="true" />
                        </button>
                      </td>
                      <td>{KIND_LABELS[chain.chain_kind]}</td>
                      <td>{METHOD_LABELS[chain.decomposition_method]}</td>
                      <td><Status value={chain.status} /></td>
                      <td>{expanded ? '已展开' : '未展开'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )) : <div className="theme-research-empty">当前筛选条件下没有产业链。</div>}
    </section>
  );
}

function CatalogDetail({ detail, onNavigate }: { detail: TechnologyIndustryChainDetail; onNavigate: (path: string) => void }) {
  const l3Nodes = detail.nodes.filter((node) => node.level === 'L3');
  const l4ByParent = detail.nodes
    .filter((node) => node.level === 'L4')
    .reduce<Map<string, TechnologyIndustryNode[]>>((groups, node) => {
      if (!node.parent_node_id) return groups;
      const children = groups.get(node.parent_node_id) ?? [];
      children.push(node);
      groups.set(node.parent_node_id, children);
      return groups;
    }, new Map());

  return (
    <section className="theme-research-workspace industry-catalog-workspace industry-catalog-detail-grid" aria-label="科技产业链详情">
      <header className="theme-research-header theme-research-detail-header">
        <button className="icon-button" type="button" onClick={() => onNavigate('/theme-research/catalog')} aria-label="返回产业目录">
          <ArrowLeft size={18} aria-hidden="true" />
        </button>
        <div>
          <div className="theme-research-title-line"><h1>{detail.chain.chain_name}</h1><Status value={detail.chain.status} /></div>
          <p>{detail.chain.description}</p>
        </div>
      </header>
      <section className="theme-research-section industry-catalog-definition" aria-label="产业链定义">
        <h2>链条定义</h2>
        <div className="theme-research-table-wrap industry-catalog-table-wrap">
          <table className="theme-research-table industry-catalog-table">
            <tbody>
              <tr><th>范围</th><td>{detail.chain.scope || '未标注'}</td></tr>
              <tr><th>排除项</th><td>{detail.chain.exclusions.join('、') || '无'}</td></tr>
              <tr><th>别名</th><td>{detail.chain.aliases.join('、') || '无'}</td></tr>
              <tr><th>链条类型</th><td>{KIND_LABELS[detail.chain.chain_kind]}</td></tr>
              <tr><th>拆解方法</th><td>{METHOD_LABELS[detail.chain.decomposition_method]}</td></tr>
              <tr><th>状态</th><td><Status value={detail.chain.status} /></td></tr>
            </tbody>
          </table>
        </div>
      </section>
      <section className="theme-research-section industry-catalog-node-groups" aria-label="L3和L4节点">
        <h2>L3/L4 节点</h2>
        {l3Nodes.length ? l3Nodes.map((node) => (
          <section key={node.node_id} className="theme-research-section industry-catalog-node-group" role="region" aria-label={`${node.node_name}节点组`}>
            <div className="theme-research-view-header">
              <h2>{node.node_name}</h2>
              <Status value={node.status} />
            </div>
            <p>{node.description}</p>
            {(l4ByParent.get(node.node_id) ?? []).length ? (
              <div className="theme-research-table-wrap industry-catalog-table-wrap">
                <table className="theme-research-table industry-catalog-table">
                  <thead><tr><th>L4 节点</th><th>类型</th><th>描述</th><th>状态</th></tr></thead>
                  <tbody>{(l4ByParent.get(node.node_id) ?? []).map((child) => (
                    <tr key={child.node_id}>
                      <td><strong>{child.node_name}</strong><small>{child.node_id}</small></td>
                      <td>{child.node_type}</td><td>{child.description}</td><td><Status value={child.status} /></td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            ) : <div className="theme-research-empty">该 L3 节点暂无 L4 节点。</div>}
          </section>
        )) : <div className="theme-research-empty">该产业链尚未展开 L3/L4 节点</div>}
      </section>
      {detail.edges.length ? (
        <section className="theme-research-section industry-catalog-edges" aria-label="产业链边关系">
          <h2>节点关系</h2>
          <div className="theme-research-table-wrap industry-catalog-table-wrap">
            <table className="theme-research-table industry-catalog-table">
              <thead><tr><th>来源节点</th><th>关系</th><th>目标节点</th><th>说明</th></tr></thead>
              <tbody>{detail.edges.map((edge) => (
                <tr key={edge.edge_id}><td>{edge.source_node_id}</td><td>{edge.relationship_type}</td><td>{edge.target_node_id}</td><td>{edge.notes || '未标注'}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </section>
      ) : null}
      {detail.theme_links.length ? (
        <section className="theme-research-section industry-catalog-theme-links" aria-label="关联主题">
          <h2>关联主题</h2>
          <div className="theme-research-table-wrap industry-catalog-table-wrap">
            <table className="theme-research-table industry-catalog-table">
              <thead><tr><th>主题 ID</th><th>节点映射</th><th>操作</th></tr></thead>
              <tbody>{detail.theme_links.map((link) => (
                <tr key={link.theme_id}>
                  <td><strong>{link.theme_id}</strong></td>
                  <td>
                    <span>已映射 {link.node_links.length}</span>{' '}
                    <span>未映射 {link.unmapped_theme_node_ids.length}</span>
                  </td>
                  <td>
                    <button className="icon-text-button" type="button" aria-label={`打开关联主题 ${link.theme_id}`} onClick={() => onNavigate(`/theme-research/${encodeURIComponent(link.theme_id)}`)}>
                      <Link2 size={16} aria-hidden="true" /> 打开主题
                    </button>
                  </td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </section>
      ) : null}
    </section>
  );
}
