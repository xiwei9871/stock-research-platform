import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { BusinessCompositionSnapshot, FinancialSnapshot } from '../src/api/types';
import { BusinessQualitySection } from '../src/components/stock-workspace/BusinessQualitySection';

afterEach(() => {
  cleanup();
});

function makeBusinessComposition(overrides: Partial<BusinessCompositionSnapshot> = {}): BusinessCompositionSnapshot {
  return {
    report_period: '2026Q1',
    data_status: 'available',
    missing_fields: [],
    groups: [
      {
        classify_type: '按产品',
        items: [
          { item_name: 'A产品', revenue: 1200000000, revenue_ratio: 0.35, gross_margin: 0.28 },
          { item_name: 'B产品', revenue: 980000000, revenue_ratio: 0.22, gross_margin: 0.24 },
          { item_name: 'C产品', revenue: 760000000, revenue_ratio: 0.16, gross_margin: 0.2 },
          { item_name: 'D产品', revenue: 580000000, revenue_ratio: 0.13, gross_margin: 0.18 },
          { item_name: 'E产品', revenue: 420000000, revenue_ratio: 0.09, gross_margin: 0.15 },
          { item_name: 'F产品', revenue: 180000000, revenue_ratio: 0.05, gross_margin: 0.11 }
        ]
      }
    ],
    ...overrides
  };
}

function makeFinancialSnapshot(overrides: Partial<FinancialSnapshot> = {}): FinancialSnapshot {
  return {
    report_period: '2026Q1',
    announcement_date: '2026-04-30',
    revenue_ttm: 31800000000,
    np_parent_ttm: 2200000000,
    operating_cash_flow: 2480000000,
    roe: 0.14,
    gross_margin: 0.21,
    debt_ratio: 0.38,
    ocf_to_np: 1.13,
    data_status: 'available',
    missing_fields: [],
    ...overrides
  };
}

describe('BusinessQualitySection', () => {
  it('shows only top two composition items by default and expands on demand', () => {
    render(
      <BusinessQualitySection
        businessComposition={makeBusinessComposition()}
        financialSnapshot={makeFinancialSnapshot()}
      />
    );

    const compositionCard = screen.getByRole('group', { name: '主营构成卡片' });
    expect(within(compositionCard).getByText('A产品')).toBeVisible();
    expect(within(compositionCard).getByText('B产品')).toBeVisible();
    expect(within(compositionCard).queryByText('C产品')).not.toBeInTheDocument();
    expect(within(compositionCard).queryByText('D产品')).not.toBeInTheDocument();
    expect(within(compositionCard).queryByText('E产品')).not.toBeInTheDocument();
    expect(within(compositionCard).queryByText('F产品')).not.toBeInTheDocument();
    expect(within(compositionCard).getByRole('button', { name: '展开更多' })).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(within(compositionCard).getByRole('button', { name: '展开更多' }));

    expect(within(compositionCard).getByText('C产品')).toBeVisible();
    expect(within(compositionCard).getByText('D产品')).toBeVisible();
    expect(within(compositionCard).getByText('E产品')).toBeVisible();
    expect(within(compositionCard).getByText('F产品')).toBeVisible();
    expect(within(compositionCard).getByRole('button', { name: '收起' })).toHaveAttribute('aria-expanded', 'true');
  });

  it('expands only the clicked composition group when multiple groups are present', () => {
    render(
      <BusinessQualitySection
        businessComposition={makeBusinessComposition({
          groups: [
            {
              classify_type: '按产品',
              items: [
                { item_name: 'A产品', revenue: 1200000000, revenue_ratio: 0.35, gross_margin: 0.28 },
                { item_name: 'B产品', revenue: 980000000, revenue_ratio: 0.22, gross_margin: 0.24 },
                { item_name: 'C产品', revenue: 760000000, revenue_ratio: 0.16, gross_margin: 0.2 },
                { item_name: 'D产品', revenue: 580000000, revenue_ratio: 0.13, gross_margin: 0.18 },
                { item_name: 'E产品', revenue: 420000000, revenue_ratio: 0.09, gross_margin: 0.15 },
                { item_name: 'F产品', revenue: 180000000, revenue_ratio: 0.05, gross_margin: 0.11 }
              ]
            },
            {
              classify_type: '按地区',
              items: [
                { item_name: '华东', revenue: 830000000, revenue_ratio: 0.3, gross_margin: 0.19 },
                { item_name: '华南', revenue: 690000000, revenue_ratio: 0.25, gross_margin: 0.18 },
                { item_name: '华北', revenue: 520000000, revenue_ratio: 0.19, gross_margin: 0.16 },
                { item_name: '西南', revenue: 360000000, revenue_ratio: 0.13, gross_margin: 0.14 },
                { item_name: '海外', revenue: 210000000, revenue_ratio: 0.08, gross_margin: 0.12 }
              ]
            }
          ]
        })}
        financialSnapshot={makeFinancialSnapshot()}
      />
    );

    const compositionCard = screen.getByRole('group', { name: '主营构成卡片' });
    const productGroup = screen.getByText('按产品').closest('.stock-composition-group');
    const regionGroup = screen.getByText('按地区').closest('.stock-composition-group');

    expect(productGroup).not.toBeNull();
    expect(regionGroup).not.toBeNull();
    expect(within(productGroup as HTMLElement).queryByText('C产品')).not.toBeInTheDocument();
    expect(within(productGroup as HTMLElement).queryByText('E产品')).not.toBeInTheDocument();
    expect(within(regionGroup as HTMLElement).queryByText('华北')).not.toBeInTheDocument();
    expect(within(regionGroup as HTMLElement).queryByText('海外')).not.toBeInTheDocument();
    expect(within(productGroup as HTMLElement).getByRole('button', { name: '展开更多' })).toHaveAttribute(
      'aria-expanded',
      'false'
    );
    expect(within(regionGroup as HTMLElement).getByRole('button', { name: '展开更多' })).toHaveAttribute(
      'aria-expanded',
      'false'
    );

    fireEvent.click(within(productGroup as HTMLElement).getByRole('button', { name: '展开更多' }));

    expect(within(productGroup as HTMLElement).getByText('C产品')).toBeVisible();
    expect(within(productGroup as HTMLElement).getByText('E产品')).toBeVisible();
    expect(within(productGroup as HTMLElement).getByText('F产品')).toBeVisible();
    expect(within(regionGroup as HTMLElement).queryByText('华北')).not.toBeInTheDocument();
    expect(within(regionGroup as HTMLElement).queryByText('海外')).not.toBeInTheDocument();
    expect(within(regionGroup as HTMLElement).getByRole('button', { name: '展开更多' })).toHaveAttribute(
      'aria-expanded',
      'false'
    );
    expect(within(compositionCard).getAllByRole('button', { name: '展开更多' })).toHaveLength(1);
    expect(within(productGroup as HTMLElement).getByRole('button', { name: '收起' })).toHaveAttribute(
      'aria-expanded',
      'true'
    );
  });

  it('collapses expanded composition groups after rerendering with a new business composition dataset', () => {
    const { rerender } = render(
      <BusinessQualitySection
        businessComposition={makeBusinessComposition({
          groups: [
            {
              classify_type: '按产品',
              items: [
                { item_name: 'A产品', revenue: 1200000000, revenue_ratio: 0.35, gross_margin: 0.28 },
                { item_name: 'B产品', revenue: 980000000, revenue_ratio: 0.22, gross_margin: 0.24 },
                { item_name: 'C产品', revenue: 760000000, revenue_ratio: 0.16, gross_margin: 0.2 },
                { item_name: 'D产品', revenue: 580000000, revenue_ratio: 0.13, gross_margin: 0.18 },
                { item_name: 'E产品', revenue: 420000000, revenue_ratio: 0.09, gross_margin: 0.15 },
                { item_name: 'F产品', revenue: 180000000, revenue_ratio: 0.05, gross_margin: 0.11 }
              ]
            }
          ]
        })}
        financialSnapshot={makeFinancialSnapshot()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '展开更多' }));
    expect(screen.getByRole('button', { name: '收起' })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('E产品')).toBeVisible();

    rerender(
      <BusinessQualitySection
        businessComposition={makeBusinessComposition({
          report_period: '2026Q2',
          groups: [
            {
              classify_type: '按产品',
              items: [
                { item_name: '新A产品', revenue: 1600000000, revenue_ratio: 0.36, gross_margin: 0.31 },
                { item_name: '新B产品', revenue: 1100000000, revenue_ratio: 0.24, gross_margin: 0.26 },
                { item_name: '新C产品', revenue: 820000000, revenue_ratio: 0.17, gross_margin: 0.22 },
                { item_name: '新D产品', revenue: 610000000, revenue_ratio: 0.12, gross_margin: 0.19 },
                { item_name: '新E产品', revenue: 380000000, revenue_ratio: 0.07, gross_margin: 0.16 }
              ]
            }
          ]
        })}
        financialSnapshot={makeFinancialSnapshot({ report_period: '2026Q2' })}
      />
    );

    expect(screen.getByText('新A产品')).toBeVisible();
    expect(screen.queryByText('新D产品')).not.toBeInTheDocument();
    expect(screen.queryByText('新E产品')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '展开更多' })).toHaveAttribute('aria-expanded', 'false');
  });
});
