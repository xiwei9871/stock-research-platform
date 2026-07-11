import type { AssetThemeResearchContext } from '../../api/types';

type ThemeResearchContextSectionProps = {
  context?: AssetThemeResearchContext;
};

function statusText(status: string) {
  const labels: Record<string, string> = {
    reviewed_context_available: '已审核上下文',
    evidence_gap: '证据待补',
    not_mapped: '未映射',
    unavailable: '暂不可用',
    mixed_or_uncertain: '主题与公司因素混合或不确定'
  };
  return labels[status] ?? status.replaceAll('_', ' ');
}

export function ThemeResearchContextSection({ context }: ThemeResearchContextSectionProps) {
  const status = context?.status ?? 'unavailable';
  return (
    <section className="workspace-band stock-theme-research" role="region" aria-label="主题研究">
      <div className="section-heading">
        <div>
          <h2>主题研究</h2>
          <p className="muted">主题 → 产业节点 → 公司映射 → 证据</p>
        </div>
        <span className={`status-chip ${status === 'reviewed_context_available' ? 'success' : 'neutral'}`}>
          {statusText(status)}
        </span>
      </div>

      {!context || status === 'unavailable' ? (
        <p className="muted">主题研究上下文暂不可用。</p>
      ) : status === 'evidence_gap' ? (
        <p className="muted">存在候选映射，但证据或审核状态尚未达到工作流门槛。</p>
      ) : status === 'not_mapped' ? (
        <p className="muted">当前公司尚未建立审核通过的主题节点映射。</p>
      ) : (
        <div className="stock-theme-research-table-wrap">
          <table className="stock-theme-research-table">
            <thead>
              <tr>
                <th>主题</th>
                <th>节点</th>
                <th>核心评分</th>
                <th>业务关系</th>
                <th>证据</th>
              </tr>
            </thead>
            <tbody>
              {context.mappings.map((mapping) => {
                const theme = context.themes.find((item) => item.theme_id === mapping.theme_id);
                return (
                  <tr key={mapping.mapping_id}>
                    <td>
                      {theme ? <a href={theme.dashboard_path}>{theme.theme_name}</a> : mapping.theme_id}
                      <small>{statusText(context.driver_assessment)}</small>
                    </td>
                    <td>
                      <strong>{mapping.node.node_name}</strong>
                      <small>{statusText(mapping.mapping_type)}</small>
                    </td>
                    <td>
                      <span>价值量 {mapping.node.value_capture_score}/5</span>
                      <span>卡脖子 {mapping.node.bottleneck_score}/5</span>
                      <span>证据强度 {mapping.node.evidence_strength}/5</span>
                    </td>
                    <td>
                      <span>{mapping.product_or_service || '-'}</span>
                      <small>{mapping.relationship_summary}</small>
                    </td>
                    <td>
                      <span>
                        证据 {mapping.evidence_items.length} 条 · 已审核观点 {mapping.reviewed_claims.length} 条
                      </span>
                      <small>{statusText(mapping.business_materiality)}</small>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className="theme-research-guardrail">仅用于研究，不参与评分、信号或准入</p>
    </section>
  );
}

