import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { AssetSummary, CompanyOverview, CompanyProfile } from '../src/api/types';
import { CompanyBasicsSection } from '../src/components/stock-workspace/CompanyBasicsSection';

afterEach(() => {
  cleanup();
});

const asset: AssetSummary = {
  asset_id: '000049.SZ',
  symbol: '000049',
  name: '德赛电池',
  exchange: 'SZ',
  board: 'SZSE_MAIN',
  is_active: true
};

const profile: CompanyProfile = {
  asset_id: '000049.SZ',
  ts_code: '000049.SZ',
  symbol: '000049',
  name: '德赛电池',
  exchange: 'SZ',
  board: 'SZSE_MAIN',
  list_date: '1995-03-20',
  is_active: true,
  is_beijing: false,
  is_star: false,
  is_chinext: false,
  region: '-',
  source: 'core.asset_master'
};

function makeOverview(overrides: Partial<CompanyOverview> = {}): CompanyOverview {
  return {
    industry: '电气机械和器材制造业',
    concept_tags: ['储能'],
    business_summary:
      '深圳市德赛电池科技股份有限公司 2025 年半年度报告全文 9 产计划并组织生产。储能电芯产品为标准化产品，公司综合评估客户需求与产能利用情况，制定生产计划并组织生产。',
    profile_summary: '聚焦锂电池封装集成与储能电芯业务，核心客户稳定。',
    primary_products: ['智能手机类', '储能电芯'],
    data_status: 'available',
    missing_fields: [],
    ...overrides
  };
}

describe('CompanyBasicsSection', () => {
  it('hides raw report excerpts and prefers the concise company summary', () => {
    render(<CompanyBasicsSection asset={asset} companyProfile={profile} companyOverview={makeOverview()} />);

    const overviewCard = screen.getByRole('group', { name: '业务概览卡片' });
    expect(within(overviewCard).getByText('聚焦锂电池封装集成与储能电芯业务，核心客户稳定。')).toBeVisible();
    expect(
      within(overviewCard).queryByText(/深圳市德赛电池科技股份有限公司 2025 年半年度报告全文/)
    ).not.toBeInTheDocument();
  });
});
