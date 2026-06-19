import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GeneratedReportsWorkspace } from '../src/components/GeneratedReportsWorkspace';
import { getNewsAssetCandidate, NewsWorkspace } from '../src/components/NewsWorkspace';
import { ReportsWorkspace } from '../src/components/ReportsWorkspace';
import type { PublicNewsItem, PublicNewsResponse } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchOverview: vi.fn(),
  fetchPublicNews: vi.fn(),
  fetchPublicNewsStatus: vi.fn(),
  refreshPublicNews: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

function makeNewsItem(overrides: Partial<PublicNewsItem> = {}): PublicNewsItem {
  return {
    news_id: 'n1',
    source: 'sina_finance',
    source_channel: 'company',
    category: 'company',
    title: '600000 浦发银行公告',
    summary: '公司新闻',
    url: 'https://example.com/news/1',
    published_at: '2026-06-08T09:30:00',
    collected_at: '2026-06-08T09:31:00',
    raw_id: 'n1',
    raw_payload: {},
    status: 'active',
    ...overrides
  };
}

const newsPayload: PublicNewsResponse = {
  warnings: [],
  items: [
    makeNewsItem({
      stocks: [{ asset_id: 'CN:SH:600000', ts_code: '600000.SH', stock_name: '浦发银行' }]
    })
  ]
};

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.fetchPublicNews.mockResolvedValue(newsPayload);
  apiMocks.fetchPublicNewsStatus.mockResolvedValue({
    enabled: true,
    running: false,
    interval_seconds: 1800,
    next_run_at: '2026-06-12T02:00:00+00:00'
  });
  apiMocks.refreshPublicNews.mockResolvedValue({ stored: 1, items_received: 1, counts_by_category: {}, warnings: [] });
  apiMocks.fetchOverview.mockResolvedValue({
    reports: [
      {
        title: '茅台 validation report',
        report_type: 'validation',
        path: '/reports/validation-moutai.html',
        trade_date: '2026-06-08'
      },
      {
        title: '平安银行 risk report',
        report_type: 'risk',
        path: '/reports/risk-pingan.html',
        trade_date: '2026-06-07'
      }
    ]
  });
});

afterEach(() => {
  cleanup();
});

describe('getNewsAssetCandidate', () => {
  it('normalizes a bare six digit title candidate', () => {
    expect(getNewsAssetCandidate(makeNewsItem({ title: '600000 浦发银行公告' }))).toBe('600000.SH');
  });
});

describe('NewsWorkspace', () => {
  it('loads accepted Sina news from today by default', async () => {
    render(<NewsWorkspace />);

    expect(await screen.findByText('600000 浦发银行公告')).toBeInTheDocument();
    expect(apiMocks.fetchPublicNews).toHaveBeenCalledWith(expect.objectContaining({
      source: 'sina_finance',
      limit: 100,
      minQualityScore: 65,
      startTime: expect.stringContaining('T00:00:00')
    }));
    expect(screen.getByText('今日通过 1 条')).toBeInTheDocument();
    expect(screen.getByText(/next run 2026-06-12T02:00:00\+00:00/)).toBeInTheDocument();
  });

  it('marks the initial news result when it is loaded', async () => {
    apiMocks.fetchPublicNews.mockResolvedValueOnce({
      source: 'sina_finance',
      items: [
        {
          news_id: 'sina_finance:n1',
          source: 'sina_finance',
          category: '公司',
          title: '贵州茅台公告',
          summary: '经营更新',
          published_at: '2026-06-12T09:30:00+08:00',
          url: 'https://example.com/n1',
          stocks: []
        }
      ],
      categories: ['公司'],
      refreshed_at: '2026-06-12T09:31:00+08:00',
      count: 1,
      stored: true,
      warnings: []
    });

    render(<NewsWorkspace initialQuery="600519" initialNewsId="sina_finance:n1" />);

    const title = await screen.findByText('贵州茅台公告');
    const row = title.closest('article');

    expect(title).toBeInTheDocument();
    expect(row).toHaveClass('news-feed-row--selected');
    expect(row).toHaveTextContent('Matched search result');
    expect(row).not.toHaveAttribute('aria-label', 'Selected news result');
    expect(row).not.toHaveAttribute('aria-current');
  });

  it('does not mark a row when the initial news id does not match', async () => {
    render(<NewsWorkspace initialNewsId="sina_finance:missing" />);

    expect(await screen.findByText('600000 浦发银行公告')).toBeInTheDocument();
    expect(document.querySelector('.news-feed-row--selected')).toBeNull();
  });

  it('uses the initial query as the news search input value', () => {
    const { rerender } = render(<NewsWorkspace initialQuery="茅台" />);

    expect(screen.getByDisplayValue('茅台')).toBeInTheDocument();
    rerender(<NewsWorkspace initialQuery="平安" />);
    expect(screen.getByDisplayValue('平安')).toBeInTheDocument();
  });

  it('sends category and query filters to the server', async () => {
    render(<NewsWorkspace />);
    expect(await screen.findByText('600000 浦发银行公告')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('news search'), { target: { value: ' 茅台 ' } });
    fireEvent.click(screen.getByRole('button', { name: '公司' }));

    expect(screen.getByLabelText('news search')).toHaveValue(' 茅台 ');
    await waitFor(() =>
      expect(apiMocks.fetchPublicNews).toHaveBeenLastCalledWith({
        source: 'sina_finance',
        limit: 100,
        minQualityScore: 65,
        startTime: expect.stringContaining('T00:00:00'),
        category: 'company',
        q: '茅台'
      })
    );
  });

  it('opens a stock when a news item has an API stock mention', async () => {
    const onOpenAsset = vi.fn();
    render(<NewsWorkspace onOpenAsset={onOpenAsset} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Open 浦发银行 in Stock Workspace' }));

    expect(onOpenAsset).toHaveBeenCalledWith('CN:SH:600000', {
      sourceWorkspace: 'news',
      assetId: 'CN:SH:600000',
      newsId: 'n1',
      query: '600000 浦发银行公告'
    });
  });

  it('renders db freshness and stock mention chips', async () => {
    const openAsset = vi.fn();
    apiMocks.fetchPublicNews.mockResolvedValueOnce({
      items: [
        makeNewsItem({
          title: '贵州茅台经营快讯',
          category: 'company',
          stocks: [{ asset_id: 'CN:SH:600519', ts_code: '600519.SH', stock_name: '贵州茅台' }]
        })
      ],
      total: 1,
      limit: 100,
      offset: 0,
      summary: {
        total_news: 1,
        latest_collected_at: '2026-06-12T01:30:00+00:00',
        source_count: 1,
        source_counts: [{ name: 'sina_finance', rows: 1 }],
        category_counts: [{ name: 'company', rows: 1 }]
      },
      warnings: []
    });

    render(<NewsWorkspace onOpenAsset={openAsset} />);

    expect(await screen.findByText('贵州茅台经营快讯')).toBeInTheDocument();
    expect(screen.getByText(/DB collected/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Open 贵州茅台 in Stock Workspace' }));
    expect(openAsset).toHaveBeenCalledWith('CN:SH:600519', {
      sourceWorkspace: 'news',
      assetId: 'CN:SH:600519',
      newsId: 'n1',
      query: '贵州茅台经营快讯'
    });
  });

  it('shows fallback warnings without clearing rows', async () => {
    apiMocks.fetchPublicNews.mockResolvedValueOnce({
      items: [makeNewsItem({ title: '缓存新闻' })],
      summary: { total_news: 1, latest_collected_at: '2026-06-12T01:30:00+00:00' },
      warnings: ['fallback json cache used: db offline']
    });

    render(<NewsWorkspace />);

    expect(await screen.findByText('缓存新闻')).toBeInTheDocument();
    expect(screen.getByText('fallback json cache used: db offline')).toBeInTheDocument();
  });

  it('renders quality score and reason chips', async () => {
    apiMocks.fetchPublicNews.mockResolvedValueOnce({
      items: [
        makeNewsItem({
          title: '高质量新闻',
          quality_score: 86,
          quality_reasons: ['权威来源', '信息完整']
        })
      ],
      warnings: []
    });

    render(<NewsWorkspace />);

    expect(await screen.findByText('高质量新闻')).toBeInTheDocument();
    expect(screen.getByText('quality 86')).toBeInTheDocument();
    expect(screen.getByText('权威来源')).toBeInTheDocument();
    expect(screen.getByText('信息完整')).toBeInTheDocument();
  });

  it('shows the exact daily accepted-news empty state', async () => {
    apiMocks.fetchPublicNews.mockResolvedValueOnce({ items: [], warnings: [] });

    render(<NewsWorkspace />);

    expect(await screen.findByText('今日暂无高质量新闻')).toBeInTheDocument();
  });

  it('handles malformed public news payload arrays defensively', async () => {
    apiMocks.fetchPublicNews.mockResolvedValueOnce({ summary: {} } as PublicNewsResponse);

    render(<NewsWorkspace />);

    expect(await screen.findByText('今日暂无高质量新闻')).toBeInTheDocument();
    expect(screen.getByText('今日通过 0 条')).toBeInTheDocument();
  });

  it('falls back to collector status from the news summary', async () => {
    apiMocks.fetchPublicNewsStatus.mockRejectedValueOnce(new Error('status offline'));
    apiMocks.fetchPublicNews.mockResolvedValueOnce({
      items: [],
      summary: {
        collector_status: {
          enabled: false,
          running: false,
          interval_seconds: 1800
        }
      },
      warnings: []
    });

    render(<NewsWorkspace />);

    expect(await screen.findByText('collector off')).toBeInTheDocument();
  });

  it('renders accepted news without waiting for slow collector status', async () => {
    apiMocks.fetchPublicNewsStatus.mockReturnValueOnce(new Promise(() => {}));
    apiMocks.fetchPublicNews.mockResolvedValueOnce({
      items: [makeNewsItem({ title: '状态接口慢但新闻先显示' })],
      warnings: []
    });

    render(<NewsWorkspace />);

    expect(await screen.findByText('状态接口慢但新闻先显示')).toBeInTheDocument();
    expect(screen.getByText('今日通过 1 条')).toBeInTheDocument();
  });

  it('clears previous rows when a foreground filter load fails', async () => {
    render(<NewsWorkspace />);

    expect(await screen.findByText('600000 浦发银行公告')).toBeInTheDocument();
    apiMocks.fetchPublicNews.mockRejectedValueOnce(new Error('news filter failed'));

    fireEvent.change(screen.getByLabelText('news search'), { target: { value: '茅台' } });

    expect(await screen.findByText('news filter failed')).toBeInTheDocument();
    expect(screen.queryByText('600000 浦发银行公告')).not.toBeInTheDocument();
    expect(screen.getByText('今日暂无高质量新闻')).toBeInTheDocument();
  });
});

describe('ReportsWorkspace', () => {
  it('uses the supplied latest trade date for generated reports', async () => {
    render(<ReportsWorkspace initialTradeDate="2026-06-18" />);

    expect(screen.getByLabelText('report trade date')).toHaveValue('2026-06-18');
    await waitFor(() =>
      expect(apiMocks.fetchOverview).toHaveBeenCalledWith({
        tradeDate: '2026-06-18',
        scoreVersion: 'manual_v1',
        watchlistId: 'default',
        topN: 5
      })
    );
  });

  it('filters generated reports by the initial query', async () => {
    const { rerender } = render(<ReportsWorkspace initialQuery="茅台" />);

    expect(screen.getByLabelText('generated reports search')).toHaveDisplayValue('茅台');
    expect(await screen.findByText('茅台 validation report')).toBeInTheDocument();
    expect(screen.queryByText('平安银行 risk report')).not.toBeInTheDocument();

    rerender(<ReportsWorkspace initialQuery="平安" />);
    expect(screen.getByLabelText('generated reports search')).toHaveDisplayValue('平安');
    expect(await screen.findByText('平安银行 risk report')).toBeInTheDocument();
    expect(screen.queryByText('茅台 validation report')).not.toBeInTheDocument();
  });

  it('marks the initial generated report path after reports load', async () => {
    apiMocks.fetchOverview.mockResolvedValueOnce({
      trade_date: '2026-06-10',
      generated_at: '2026-06-10T18:00:00+08:00',
      summary: {},
      reports: [
        {
          title: 'TopN strategy validation',
          path: 'reports/topn-validation.md',
          report_type: 'validation',
          format: 'markdown',
          size_bytes: 1024,
          modified_at: '2026-06-10T18:00:00+08:00'
        },
        {
          title: 'TopN strategy risk review',
          path: 'reports/topn-risk.md',
          report_type: 'risk',
          format: 'markdown',
          size_bytes: 2048,
          modified_at: '2026-06-10T18:05:00+08:00'
        }
      ]
    });

    render(
      <ReportsWorkspace
        initialQuery=""
        initialTradeDate="2026-06-10"
        initialPath="reports/topn-validation.md"
      />
    );

    const selectedReport = await screen.findByRole('link', { name: /TopN strategy validation/i });
    const unselectedReport = screen.getByRole('link', { name: /TopN strategy risk review/i });

    expect(selectedReport).toHaveClass('report-card--selected');
    expect(selectedReport).not.toHaveAttribute('aria-label');
    expect(selectedReport).not.toHaveAttribute('aria-current');
    expect(unselectedReport).not.toHaveClass('report-card--selected');
  });
});

describe('GeneratedReportsWorkspace', () => {
  it('passes the initial query to the reports workspace', async () => {
    render(<GeneratedReportsWorkspace initialQuery="validation" />);

    expect(screen.getByLabelText('generated reports search')).toHaveDisplayValue('validation');
    expect(await screen.findByText('茅台 validation report')).toBeInTheDocument();
    expect(screen.queryByText('平安银行 risk report')).not.toBeInTheDocument();
  });
});
