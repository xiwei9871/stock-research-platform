import type { AssetSummary, CompanyOverview, CompanyProfile } from '../../api/types';

type CompanyBasicsSectionProps = {
  asset: AssetSummary | null | undefined;
  companyProfile: CompanyProfile | null | undefined;
  companyOverview: CompanyOverview | null | undefined;
};

function formatStatus(isActive: boolean | null | undefined) {
  if (isActive === true) return '正常';
  if (isActive === false) return '非活跃';
  return '待补充';
}

function formatProfileSource(source: string | null | undefined) {
  return source ? '基础档案' : '信息待补充';
}

function formatOverviewStatus(status: string | null | undefined) {
  if (!status || status === 'missing') return '信息待补充';
  if (status === 'available') return '信息完整';
  if (status === 'partial') return '信息待补全';
  return status;
}

function normalizeSummary(value: string | null | undefined) {
  return value?.replace(/\s+/g, ' ').trim() ?? '';
}

function isReadableCompanySummary(value: string) {
  if (!value) return false;
  if (value.length > 120) return false;
  if (/报告全文|年度报告|半年度报告|产计划并组织生产|公司主要围绕/.test(value)) return false;
  return true;
}

export function CompanyBasicsSection({
  asset,
  companyProfile,
  companyOverview
}: CompanyBasicsSectionProps) {
  const conceptTags = companyOverview?.concept_tags ?? [];
  const primaryProducts = companyOverview?.primary_products ?? [];
  const businessSummary = normalizeSummary(companyOverview?.business_summary);
  const profileSummary = normalizeSummary(companyOverview?.profile_summary);
  const overviewLines = [businessSummary, profileSummary]
    .filter((line, index, array) => Boolean(line) && array.indexOf(line) === index && isReadableCompanySummary(line));

  return (
    <section className="workspace-band stock-company-basics" role="region" aria-label="公司基础信息">
      <div className="section-heading">
        <div>
          <h2>公司基础信息</h2>
          <p className="muted">快速判断这家公司做什么、属于哪个赛道，以及是否值得继续投入研究。</p>
        </div>
      </div>
      <div className="stock-background-grid">
        <article className="stock-mini-panel" role="group" aria-label="公司档案卡片">
          <div className="section-heading compact-heading">
            <h3>公司档案</h3>
            <span className="muted">{formatProfileSource(companyProfile?.source)}</span>
          </div>
          <div className="stock-summary-strip compact">
            <div>
              <span>所属行业</span>
              <strong>{companyOverview?.industry ?? '-'}</strong>
            </div>
            <div>
              <span>交易所</span>
              <strong>{companyProfile?.exchange ?? asset?.exchange ?? '-'}</strong>
            </div>
            <div>
              <span>板块</span>
              <strong>{companyProfile?.board ?? asset?.board ?? '-'}</strong>
            </div>
            <div>
              <span>上市日期</span>
              <strong>{companyProfile?.list_date ?? '-'}</strong>
            </div>
            <div>
              <span>区域</span>
              <strong>{companyProfile?.region ?? '-'}</strong>
            </div>
            <div>
              <span>状态</span>
              <strong>{formatStatus(companyProfile?.is_active ?? asset?.is_active)}</strong>
            </div>
          </div>
        </article>
        <article className="stock-mini-panel stock-company-overview-panel" role="group" aria-label="业务概览卡片">
          <div className="section-heading compact-heading">
            <h3>业务概览</h3>
            <span className="muted">{formatOverviewStatus(companyOverview?.data_status)}</span>
          </div>
          <div className="stock-company-tag-list" aria-label="概念标签">
            {conceptTags.length > 0 ? conceptTags.map((tag) => <span key={tag}>{tag}</span>) : <span>暂无概念标签</span>}
          </div>
          <div className="stock-background-copy">
            {overviewLines.length > 0 ? overviewLines.map((line) => <p key={line}>{line}</p>) : <p>暂无公司业务摘要。</p>}
          </div>
          <div className="stock-company-product-list">
            <span>核心产品</span>
            <strong>{primaryProducts.length > 0 ? primaryProducts.join(' / ') : '-'}</strong>
          </div>
        </article>
      </div>
    </section>
  );
}
