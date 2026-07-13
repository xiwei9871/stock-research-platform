import { useEffect, useState } from 'react';
import type { BusinessCompositionSnapshot, FinancialSnapshot } from '../../api/types';

type BusinessQualitySectionProps = {
  businessComposition: BusinessCompositionSnapshot | null | undefined;
  financialSnapshot: FinancialSnapshot | null | undefined;
};

const DEFAULT_VISIBLE_COMPOSITION_ITEMS = 2;

function formatSnapshotStatus(status: string | null | undefined) {
  if (!status || status === 'missing') return '信息待补充';
  if (status === 'available') return '信息完整';
  if (status === 'partial') return '信息待补全';
  return status;
}

function formatPercent(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '-';
  return `${(value * 100).toFixed(2)}%`;
}

function formatRatio(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '-';
  return `${value.toFixed(2)}x`;
}

function formatChineseAmount(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '-';
  const abs = Math.abs(value);
  if (abs >= 100000000) return `${(value / 100000000).toFixed(2)}亿`;
  if (abs >= 10000) return `${(value / 10000).toFixed(2)}万`;
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

function sortCompositionItems<T extends { revenue_ratio: number | null; revenue: number | null }>(items: T[]) {
  return [...items].sort((left, right) => {
    const ratioDiff = (right.revenue_ratio ?? 0) - (left.revenue_ratio ?? 0);
    if (ratioDiff !== 0) return ratioDiff;
    return (right.revenue ?? 0) - (left.revenue ?? 0);
  });
}

export function BusinessQualitySection({
  businessComposition,
  financialSnapshot
}: BusinessQualitySectionProps) {
  const [expandedCompositionGroups, setExpandedCompositionGroups] = useState<Record<string, boolean>>({});
  const groups = businessComposition?.groups ?? [];

  useEffect(() => {
    setExpandedCompositionGroups({});
  }, [businessComposition]);

  return (
    <section className="workspace-band stock-business-quality" role="region" aria-label="主营构成与经营质量">
      <div className="section-heading">
        <div>
          <h2>主营构成与经营质量</h2>
          <p className="muted">把收入构成和核心质量指标并排查看，快速判断主营集中度与盈利质量。</p>
        </div>
      </div>
      <div className="stock-business-quality-grid">
        <article className="stock-mini-panel" role="group" aria-label="主营构成卡片">
          <div className="section-heading compact-heading">
            <h3>主营构成</h3>
            <span className="muted">
              {businessComposition?.report_period ?? formatSnapshotStatus(businessComposition?.data_status)}
            </span>
          </div>
          <div className="stock-composition-groups">
            {groups.length > 0 ? (
              groups.map((group) => {
                const isExpanded = expandedCompositionGroups[group.classify_type] ?? false;
                const hasMoreCompositionItems = group.items.length > DEFAULT_VISIBLE_COMPOSITION_ITEMS;

                return (
                  <div key={group.classify_type} className="stock-composition-group">
                  <div className="stock-composition-group-label">
                    <span>{group.classify_type}</span>
                    <small>{group.items.length} 项</small>
                  </div>
                  <div className="stock-composition-items">
                    {sortCompositionItems(group.items)
                      .slice(0, isExpanded ? group.items.length : DEFAULT_VISIBLE_COMPOSITION_ITEMS)
                      .map((item) => (
                      <article key={`${group.classify_type}:${item.item_name}`} className="stock-composition-item">
                        <strong>{item.item_name}</strong>
                        <span>营收 {formatChineseAmount(item.revenue)}</span>
                        <span>占比 {formatPercent(item.revenue_ratio)}</span>
                        <span>毛利率 {formatPercent(item.gross_margin)}</span>
                      </article>
                    ))}
                  </div>
                  {hasMoreCompositionItems ? (
                    <button
                      type="button"
                      className="inline-button stock-composition-toggle"
                      aria-expanded={isExpanded}
                      onClick={() =>
                        setExpandedCompositionGroups((current) => ({
                          ...current,
                          [group.classify_type]: !isExpanded
                        }))
                      }
                    >
                      {isExpanded ? '收起' : '展开更多'}
                    </button>
                  ) : null}
                  </div>
                );
              })
            ) : (
              <p className="muted">暂无主营构成数据。</p>
            )}
          </div>
        </article>
        <article className="stock-mini-panel" role="group" aria-label="经营质量卡片">
          <div className="section-heading compact-heading">
            <h3>经营质量</h3>
            <span className="muted">
              {financialSnapshot?.report_period ?? formatSnapshotStatus(financialSnapshot?.data_status)}
            </span>
          </div>
          <div className="stock-summary-strip compact stock-business-quality-metrics">
            <div>
              <span>TTM营收</span>
              <strong>{formatChineseAmount(financialSnapshot?.revenue_ttm)}</strong>
            </div>
            <div>
              <span>TTM归母净利</span>
              <strong>{formatChineseAmount(financialSnapshot?.np_parent_ttm)}</strong>
            </div>
            <div>
              <span>经营现金流</span>
              <strong>{formatChineseAmount(financialSnapshot?.operating_cash_flow)}</strong>
            </div>
            <div>
              <span>ROE</span>
              <strong>{formatPercent(financialSnapshot?.roe)}</strong>
            </div>
            <div>
              <span>毛利率</span>
              <strong>{formatPercent(financialSnapshot?.gross_margin)}</strong>
            </div>
            <div>
              <span>资产负债率</span>
              <strong>{formatPercent(financialSnapshot?.debt_ratio)}</strong>
            </div>
            <div>
              <span>经营现金流/净利</span>
              <strong>{formatRatio(financialSnapshot?.ocf_to_np)}</strong>
            </div>
          </div>
        </article>
      </div>
    </section>
  );
}
