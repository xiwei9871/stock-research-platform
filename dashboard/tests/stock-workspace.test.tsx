import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  StockWorkspace,
  reviewActionLabel,
  reviewConfidenceLabel,
  reviewConclusionText,
  type StockEntryContext
} from '../src/components/StockWorkspace';
import { reviewUniverseTechBottleneckEntryContext } from './stock-workspace-tech-bottleneck-fixtures';
import type {
  AssetNewsResponse,
  AssetProfile,
  AssetResearchReportResponse,
  DecisionOutcomeRow,
  EvidenceDigestResponse,
  StockMarketContextHeatmapPayload
} from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  createOperatorDecision: vi.fn(),
  fetchEvidenceDigest: vi.fn(),
  fetchAssetNews: vi.fn(),
  fetchAssetProfile: vi.fn(),
  fetchAssetResearchReports: vi.fn(),
  fetchDailyBars: vi.fn(),
  fetchStockMarketContextHeatmap: vi.fn(),
  searchAssets: vi.fn(),
  updateOperatorDecision: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

vi.mock('../src/charts/AssetChart', () => ({
  AssetChart: ({
    bars,
    timeAxisMode
  }: {
    bars: unknown[];
    timeAxisMode?: string;
  }) => (
    <div data-testid="asset-chart">
      {bars.length} bars / {timeAxisMode}
    </div>
  )
}));

function makeProfile(overrides: Partial<AssetProfile> = {}): AssetProfile {
  return {
    asset_id: '000001.SZ',
    canonical_asset_id: '000001.SZ',
    asset: { asset_id: '000001.SZ', symbol: '000001', name: '平安银行', exchange: 'SZ', board: null, is_active: true },
    bars: [
      { time: '2026-06-05', open: 10, high: 11, low: 9.8, close: 10.6, volume: 1000, amount: 10600 },
      { time: '2026-06-08', open: 10.6, high: 11.2, low: 10.4, close: 11, volume: 1300, amount: 14300 }
    ],
    score: {
      trade_date: '2026-06-08',
      asset_id: '000001.SZ',
      rank: 3,
      score_total: 82.4,
      score_version: 'manual_v1',
      score_components: { momentum: 31.2, quality: 18.4 }
    },
    signals: [
      {
        watchlist_id: 'default',
        trade_date: '2026-06-08',
        asset_id: '000001.SZ',
        stock_code: '000001',
        stock_name: '平安银行',
        priority: 8,
        signal_score: 82.4,
        primary_signal: 'candidate',
        signal_tags: ['momentum'],
        risk_tags: ['earnings'],
        must_watch: true,
        reason_json: { next_action: 'review close above 10d high' }
      }
    ],
    decisions: [
      {
        review_date: '2026-06-08',
        review_session_id: 'session-1',
        event_id: 'event-1',
        asset_id: '000001.SZ',
        stock_code: '000001',
        stock_name: '平安银行',
        decision_label: 'watch',
        evidence_artifact_id: 'artifact-1',
        evidence_path: 'reports/evidence/000001.md',
        source_context: 'strategy_lab',
        requires_follow_up: true,
        follow_up_note: 'check next close',
        notes: 'strong score',
        manual_review_required: true,
        auto_trade_enabled: false
      }
    ],
    outcomes: [],
    factor_values: [{ factor_name: 'momentum_20d', factor_group: 'momentum', factor_value: 0.21 }],
    coverage: { bars: { start: '2026-06-05', end: '2026-06-08' } },
    ...overrides
  };
}

function makeStockMarketContextHeatmapPayload(
  overrides: Partial<StockMarketContextHeatmapPayload> = {}
): StockMarketContextHeatmapPayload {
  return {
    asset_id: '000001.SZ',
    canonical_asset_id: '000001.SZ',
    trade_date: '2026-06-18',
    industry: { industry_id: 'bank', industry_name: '银行', industry_system: 'csrc' },
    selected: {
      asset_id: '000001.SZ',
      symbol: '000001',
      name: '平安银行',
      price: 12.5,
      change_pct: 0.02,
      amount: 3000000000,
      amount_rank: 1,
      change_rank: 1,
      amount_percentile: 1,
      change_percentile: 1
    },
    summary: {
      peer_count: 2,
      up_count: 1,
      flat_count: 0,
      down_count: 1,
      total_amount: 4000000000,
      selected_in_peer_set: true
    },
    peers: [
      {
        asset_id: '000001.SZ',
        symbol: '000001',
        name: '平安银行',
        price: 12.5,
        change_pct: 0.02,
        amount: 3000000000,
        value: 3000000000,
        is_selected: true
      },
      {
        asset_id: '600000.SH',
        symbol: '600000',
        name: '浦发银行',
        price: 9,
        change_pct: -0.01,
        amount: 1000000000,
        value: 1000000000,
        is_selected: false
      }
    ],
    data_status: 'completed',
    warnings: [],
    ...overrides
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

function makeResearchReports(overrides: Partial<AssetResearchReportResponse> = {}): AssetResearchReportResponse {
  return {
    asset_id: '000001.SZ',
    summary: {
      report_count_30d: 2,
      report_count_90d: 4,
      broker_coverage_count_90d: 3,
      latest_report_date: '2026-06-03',
      latest_rating: '买入',
      latest_target_price: 19.5
    },
    items: [
      {
        report_id: 'r1',
        event_key: 'r1:000001.SZ',
        asset_id: '000001.SZ',
        ts_code: '000001.SZ',
        stock_name: '平安银行',
        industry_name: '银行',
        report_title: '平安银行深度报告',
        publish_date: '2026-06-03',
        report_date: '2026-06-03',
        broker: '华泰证券',
        analyst: '',
        rating: '买入',
        rating_change: '',
        target_price: 19.5,
        target_upside: null,
        source_type: 'public_web_search_result',
        source_name: 'cfi_ybyl',
        source_confidence: 0.8,
        public_access: true,
        copyright_note: 'metadata only',
        source_url: 'https://example.com/r1',
        raw_summary: '',
        company_view: '',
        industry_view: '',
        risk_summary: '',
        metadata: {}
      }
    ],
    warnings: [],
    ...overrides
  };
}

function makeAssetNews(overrides: Partial<AssetNewsResponse> = {}): AssetNewsResponse {
  const assetId = overrides.asset_id ?? '000001.SZ';
  return {
    asset_id: assetId,
    items: [
      {
        news_id: 'news-1',
        source: 'sina_finance',
        source_channel: '公司',
        category: 'company',
        title: '平安银行相关新闻',
        summary: '',
        url: 'https://finance.sina.com.cn/doc/news.shtml',
        published_at: '2026-06-12T01:30:00+00:00',
        collected_at: '2026-06-12T01:31:00+00:00',
        raw_id: 'news-1',
        raw_payload: {},
        status: 'available',
        stocks: [{ asset_id: assetId, ts_code: '000001.SZ', stock_name: '平安银行' }]
      }
    ],
    summary: {
      news_count_1d: 1,
      news_count_3d: 1,
      news_count_7d: 1,
      latest_published_at: '2026-06-12T01:30:00+00:00',
      source_count: 1,
      category_counts: [{ name: 'company', rows: 1 }]
    },
    warnings: [],
    ...overrides
  };
}

const newsPayload = makeAssetNews();

function makeEvidenceDigest(overrides: Partial<EvidenceDigestResponse> = {}): EvidenceDigestResponse {
  return {
    asset_id: '000001.SZ',
    canonical_asset_id: '000001.SZ',
    trade_date: '2026-06-18',
    title: '平安银行 evidence digest',
    score: 62,
    bucket: 'mixed',
    facts: [
      { kind: 'news', key: 'news-1', label: 'Recent company news is available' },
      { kind: 'research', key: 'r1', label: 'Latest research keeps buy rating' }
    ],
    risk_flags: [{ key: 'turnover-risk', label: 'Turnover pressure elevated', severity: 'warning' }],
    source_refs: {
      workspace: 'stock',
      asset_id: '000001.SZ',
      news_id: 'news-1',
      report_id: 'r1',
      event_key: 'r1:000001.SZ',
      monitor_tab: 'limit_up'
    },
    next_actions: [
      {
        key: 'review_stock',
        label: 'Review stock',
        workspace: 'stock',
        asset_id: '000001.SZ',
        query: '平安银行'
      },
      {
        key: 'open_news',
        label: 'Open news evidence',
        workspace: 'news',
        asset_id: '000001.SZ',
        news_id: 'news-1',
        query: '平安银行 news'
      },
      {
        key: 'open_research',
        label: 'Open research evidence',
        workspace: 'researchReports',
        asset_id: '000001.SZ',
        report_id: 'r1',
        event_key: 'r1:000001.SZ',
        query: '平安银行 research'
      },
      {
        key: 'open_market',
        label: 'Open market evidence',
        workspace: 'market',
        asset_id: '000001.SZ',
        monitor_tab: 'limit_up',
        query: '平安银行 market'
      }
    ],
    warnings: ['Digest uses partial source coverage'],
    ...overrides
  };
}

function makeOutcome(overrides: Partial<DecisionOutcomeRow> = {}): DecisionOutcomeRow {
  return {
    outcome_event_id: 'outcome-1',
    run_id: 'run-1',
    decision_event_id: 'event-1',
    review_session_id: 'session-1',
    review_date: '2026-06-08',
    asset_id: '000001.SZ',
    stock_code: '000001',
    stock_name: '平安银行',
    decision_label: 'watch',
    source_context: 'strategy_lab',
    outcome_status: 'complete',
    available_future_bars: 5,
    base_trade_date: '2026-06-08',
    base_close: 11,
    forward_returns: { '1': 0.034, '5': 0.126 },
    max_high_returns: { '1': 0.041, '5': 0.18 },
    max_low_drawdowns: { '1': -0.01, '5': -0.025 },
    manual_review_required: true,
    auto_trade_enabled: false,
    source_artifact_path: 'reports/evidence/000001.md',
    outcome_artifact_path: 'reports/outcomes/000001-outcome.json',
    ...overrides
  };
}

function makeReviewBars() {
  return [
    { time: '2026-06-01', open: 9.8, high: 10.2, low: 9.6, close: 10, volume: 900, amount: 9000 },
    { time: '2026-06-02', open: 10, high: 10.5, low: 9.9, close: 10.2, volume: 1000, amount: 10200 },
    { time: '2026-06-03', open: 10.2, high: 10.8, low: 10.1, close: 10.6, volume: 1100, amount: 11660 },
    { time: '2026-06-04', open: 10.6, high: 11.2, low: 10.4, close: 10.8, volume: 1200, amount: 12960 },
    { time: '2026-06-05', open: 10.8, high: 11.5, low: 10.7, close: 11, volume: 1300, amount: 14300 }
  ];
}

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.fetchAssetProfile.mockResolvedValue(makeProfile());
  apiMocks.fetchAssetResearchReports.mockResolvedValue(makeResearchReports());
  apiMocks.fetchAssetNews.mockResolvedValue(newsPayload);
  apiMocks.fetchEvidenceDigest.mockResolvedValue(makeEvidenceDigest());
  apiMocks.fetchDailyBars.mockResolvedValue([]);
  apiMocks.fetchStockMarketContextHeatmap.mockResolvedValue(
    makeStockMarketContextHeatmapPayload({
      selected: null,
      peers: [],
      data_status: 'missing',
      summary: {
        peer_count: 0,
        up_count: 0,
        flat_count: 0,
        down_count: 0,
        total_amount: 0,
        selected_in_peer_set: false
      }
    })
  );
  apiMocks.searchAssets.mockResolvedValue([]);
  Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
    configurable: true,
    value: vi.fn((contextId: string) =>
      contextId === '2d'
        ? {
            clearRect: vi.fn(),
            fillRect: vi.fn(),
            strokeRect: vi.fn(),
            fillText: vi.fn(),
            measureText: vi.fn((text: string) => ({ width: text.length * 8 })),
            save: vi.fn(),
            restore: vi.fn(),
            scale: vi.fn()
          }
        : null
    ) as unknown as HTMLCanvasElement['getContext']
  });
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, value: 460 });
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, value: 240 });
  apiMocks.createOperatorDecision.mockResolvedValue({
    event_id: 'operator_decision:operator-decision-api-2026-06-08:0:abc',
    asset_id: '000001.SZ',
    stock_code: '000001.SZ',
    stock_name: '平安银行',
    decision_date: '2026-06-08',
    operator_action: 'watch',
    decision_status: 'open',
    decision_label: 'observe',
    run_id: 'eod-2026-06-08-local',
    digest_key: '2026-06-08:manual_v1:000001.SZ',
    review_item_snapshot_id: 'review_item_snapshot:abc',
    evidence_digest_snapshot_id: 'evidence_digest_snapshot:def',
    snapshot_linkage_status: 'linked',
    snapshot_linkage_warnings: [],
    warnings: []
  });
});

afterEach(() => {
  cleanup();
});

describe('StockWorkspace', () => {
  it('prefers a wait-and-confirm action when the evidence digest is risk heavy', () => {
    const metrics = {
      dayReturn: 0.03,
      fiveDayReturn: 0.08,
      twentyDayReturn: 0.12,
      amountRatio: 1.4,
      highDrawdown: -0.02,
      state: '加速'
    };

    expect(reviewActionLabel(metrics, makeEvidenceDigest({ bucket: 'risk_heavy' }))).toBe('等待确认');
  });

  it('uses bottleneck confidence as the confidence baseline when digest score is absent', () => {
    const metrics = {
      dayReturn: null,
      fiveDayReturn: null,
      twentyDayReturn: null,
      amountRatio: null,
      highDrawdown: -0.03,
      state: '震荡'
    };
    const entryContext: StockEntryContext = {
      sourceWorkspace: 'techBottleneck',
      bottleneckConfidenceScore: 78
    };

    expect(reviewConfidenceLabel(metrics, entryContext, null)).toBe('较高');
  });

  it('surfaces the tech bottleneck evidence-gap conclusion when follow-up proof is still missing', () => {
    const metrics = {
      dayReturn: 0.01,
      fiveDayReturn: 0.02,
      twentyDayReturn: 0.04,
      amountRatio: 1.1,
      highDrawdown: -0.04,
      state: '启动'
    };
    const entryContext: StockEntryContext = {
      sourceWorkspace: 'techBottleneck',
      evidenceGapNote: 'primary source fields require follow-up'
    };

    expect(reviewConclusionText(metrics, entryContext, null)).toBe(
      '卡脖子主线仍可跟踪，但明日优先验证缺失证据。'
    );
  });

  it('does not infer a missing-proof conclusion from a raw report excerpt', () => {
    const metrics = {
      dayReturn: 0.01,
      fiveDayReturn: 0.02,
      twentyDayReturn: 0.04,
      amountRatio: 1.1,
      highDrawdown: -0.04,
      state: '启动'
    };
    const entryContext: StockEntryContext = {
      sourceWorkspace: 'techBottleneck',
      evidenceGapNote:
        '深圳市德赛电池科技股份有限公司 2025 年半年度报告全文 9 产计划并组织生产。储能电芯产品为标准化产品，公司综合评估客户需求与产能利用情况，制定生产计划并组织生产。'
    };

    expect(reviewConclusionText(metrics, entryContext, null)).toBe('暂无单边结论，明日结合价格行为与证据变化继续复盘。');
  });

  it('uses the concrete tech bottleneck next action in the operator conclusion when available', () => {
    const metrics = {
      dayReturn: 0.01,
      fiveDayReturn: 0.02,
      twentyDayReturn: 0.04,
      amountRatio: 1.1,
      highDrawdown: -0.04,
      state: '启动'
    };
    const entryContext: StockEntryContext = {
      sourceWorkspace: 'techBottleneck',
      nextAction: '核查客户认证和订单进入财报情况',
      evidenceGapNote: 'primary source fields require follow-up'
    };

    expect(reviewConclusionText(metrics, entryContext, null)).toBe(
      '明日先核查客户认证和订单进入财报情况，再决定是否继续跟踪。'
    );
  });

  it('normalizes english tech bottleneck next action in the operator conclusion', () => {
    const metrics = {
      dayReturn: 0.01,
      fiveDayReturn: 0.02,
      twentyDayReturn: 0.04,
      amountRatio: 1.1,
      highDrawdown: -0.04,
      state: '启动'
    };
    const entryContext: StockEntryContext = {
      sourceWorkspace: 'techBottleneck',
      nextAction: 'manual review of upgraded primary-source evidence before any future core-pool action',
      evidenceGapNote: 'primary source fields require follow-up'
    };

    expect(reviewConclusionText(metrics, entryContext, null)).toBe('明日先人工复核确认，再决定是否继续跟踪。');
  });

  it('renders a stock-page quote dossier without fabricating unavailable valuation fields', async () => {
    apiMocks.fetchAssetProfile.mockResolvedValueOnce(
      makeProfile({
        quote_snapshot: {
          trade_date: '2026-06-08',
          open: 10.6,
          high: 11.2,
          low: 10.4,
          close: 11,
          preclose: 10.6,
          volume: 1300,
          amount: 14300,
          turnover_rate: 2.35,
          pct_chg: 3.77,
          amount_ratio_20d: 1.23,
          data_status: 'available',
          missing_fields: []
        },
        company_profile: {
          asset_id: '000001.SZ',
          ts_code: '000001.SZ',
          symbol: '000001',
          name: '平安银行',
          exchange: 'SZ',
          board: '主板',
          list_date: '1991-04-03',
          is_active: true,
          is_beijing: false,
          is_star: false,
          is_chinext: false,
          region: '深圳',
          source: 'core.asset_master'
        },
        valuation_snapshot: {
          total_market_cap: 197940365620,
          float_market_cap: 197937126661,
          pe_ttm: 3.41,
          pb: 0.43,
          volume_ratio: 1.24,
          data_status: 'available',
          missing_fields: []
        }
      } as Partial<AssetProfile>)
    );

    const { container } = render(<StockWorkspace initialAssetId="000001.SZ" />);

    const quote = await screen.findByRole('region', { name: '今日价格行为' });
    const companyBasics = await screen.findByRole('region', { name: '公司基础信息' });
    const businessQuality = await screen.findByRole('region', { name: '主营构成与经营质量' });
    expect(screen.getByText('回放 / 切换设置')).toBeInTheDocument();
    expect(screen.getAllByText(/000001\.SZ · 复盘日/).length).toBeGreaterThan(0);
    expect(screen.queryByText('Load Stock')).not.toBeInTheDocument();
    expect(screen.queryByText('Trade Date')).not.toBeInTheDocument();
    expect(container.querySelector('.stock-quote-primary')).not.toBeInTheDocument();
    expect(within(quote).getByText('最新价')).toBeInTheDocument();
    expect(within(quote).getByText('11.00')).toBeInTheDocument();
    expect(within(quote).getByText('涨跌幅')).toBeInTheDocument();
    expect(within(quote).getAllByText('+3.77%').length).toBeGreaterThan(0);
    expect(within(quote).getByText('今开')).toBeInTheDocument();
    expect(within(quote).getAllByText('10.60').length).toBeGreaterThan(0);
    expect(within(quote).getByText('最高')).toBeInTheDocument();
    expect(within(quote).getByText('最低')).toBeInTheDocument();
    expect(within(quote).getByText('成交额')).toBeInTheDocument();
    expect(within(quote).getByText('1.43万')).toBeInTheDocument();
    expect(within(quote).getByText('换手率')).toBeInTheDocument();
    expect(within(quote).getByText('2.35%')).toBeInTheDocument();
    expect(within(quote).getByText('量能/20日均额')).toBeInTheDocument();
    expect(within(quote).getByText('1.23x')).toBeInTheDocument();
    expect(within(quote).getByText('总市值')).toBeInTheDocument();
    expect(within(quote).getByText('1979.40亿')).toBeInTheDocument();
    expect(within(quote).getByText('流通市值')).toBeInTheDocument();
    expect(within(quote).getByText('1979.37亿')).toBeInTheDocument();
    expect(within(quote).getByText('PE')).toBeInTheDocument();
    expect(within(quote).getByText('3.41')).toBeInTheDocument();
    expect(within(quote).getByText('PB')).toBeInTheDocument();
    expect(within(quote).getByText('0.43')).toBeInTheDocument();
    expect(within(companyBasics).queryByText('总市值')).not.toBeInTheDocument();
    expect(within(companyBasics).queryByText('流通市值')).not.toBeInTheDocument();
    expect(within(companyBasics).queryByText('PE')).not.toBeInTheDocument();
    expect(within(companyBasics).queryByText('PB')).not.toBeInTheDocument();
    expect(within(businessQuality).queryByText('总市值')).not.toBeInTheDocument();
    expect(within(businessQuality).queryByText('流通市值')).not.toBeInTheDocument();
    expect(within(businessQuality).queryByText('PE')).not.toBeInTheDocument();
    expect(within(businessQuality).queryByText('PB')).not.toBeInTheDocument();

    expect(within(companyBasics).getByText('公司档案')).toBeInTheDocument();
    expect(within(companyBasics).getByText('主板')).toBeInTheDocument();
    expect(within(companyBasics).getByText('1991-04-03')).toBeInTheDocument();
    expect(within(companyBasics).getByText('深圳')).toBeInTheDocument();
    expect(within(companyBasics).getByText('暂无概念标签')).toBeInTheDocument();
    expect(within(companyBasics).queryByText('asset detail')).not.toBeInTheDocument();

    expect(within(businessQuality).getByText('主营构成')).toBeInTheDocument();
    expect(within(businessQuality).getByText('暂无主营构成数据。')).toBeInTheDocument();
    expect(within(businessQuality).getByText('TTM营收')).toBeInTheDocument();
    expect(within(businessQuality).getAllByText('-').length).toBeGreaterThan(0);
    expect(within(businessQuality).queryByText('missing')).not.toBeInTheDocument();
  });

  it('keeps valuation fields in the quote block as dashes when valuation data is unavailable', async () => {
    apiMocks.fetchAssetProfile.mockResolvedValueOnce(
      makeProfile({
        quote_snapshot: {
          trade_date: '2026-06-08',
          open: 10.6,
          high: 11.2,
          low: 10.4,
          close: 11,
          preclose: 10.6,
          volume: 1300,
          amount: 14300,
          turnover_rate: 2.35,
          pct_chg: 3.77,
          amount_ratio_20d: 1.23,
          data_status: 'available',
          missing_fields: []
        },
        valuation_snapshot: {
          total_market_cap: null,
          float_market_cap: null,
          pe_ttm: null,
          pb: null,
          volume_ratio: null,
          data_status: 'unavailable',
          missing_fields: ['total_market_cap', 'float_market_cap', 'pe_ttm', 'pb']
        }
      } as Partial<AssetProfile>)
    );

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    const quote = await screen.findByRole('region', { name: '今日价格行为' });
    const quoteText = within(quote).getByText('总市值').closest('div');
    const floatMarketCapText = within(quote).getByText('流通市值').closest('div');
    const peText = within(quote).getByText('PE').closest('div');
    const pbText = within(quote).getByText('PB').closest('div');

    expect(quoteText).toHaveTextContent('总市值-');
    expect(floatMarketCapText).toHaveTextContent('流通市值-');
    expect(peText).toHaveTextContent('PE-');
    expect(pbText).toHaveTextContent('PB-');
  });

  it('uses a trailing 20-bar amount ratio when quote snapshot is unavailable', async () => {
    const bars = Array.from({ length: 25 }, (_, index) => {
      const isLastBar = index === 24;
      const amount = index < 5 ? 1000 : isLastBar ? 200 : 100;
      const close = 10 + index * 0.1;
      return {
        time: `2026-06-${String(index + 1).padStart(2, '0')}`,
        open: close - 0.1,
        high: close + 0.2,
        low: close - 0.2,
        close,
        volume: 1000 + index * 10,
        amount
      };
    });

    apiMocks.fetchAssetProfile.mockResolvedValueOnce(
      makeProfile({
        quote_snapshot: null,
        bars
      } as Partial<AssetProfile>)
    );

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    const quote = await screen.findByRole('region', { name: '今日价格行为' });
    const amountRatio = within(quote).getByText('量能/20日均额').closest('div');

    expect(amountRatio).toHaveTextContent('量能/20日均额1.90x');
    expect(within(quote).getByText('昨收')).toBeInTheDocument();
  });

  it('keeps zero-turnover fallback ratio on the trailing 20-bar path without falling back to valuation volume ratio', async () => {
    const bars = Array.from({ length: 20 }, (_, index) => {
      const close = 10 + index * 0.1;
      return {
        time: `2026-07-${String(index + 1).padStart(2, '0')}`,
        open: close - 0.1,
        high: close + 0.2,
        low: close - 0.2,
        close,
        volume: 1000 + index * 10,
        amount: index === 19 ? 0 : 100
      };
    });

    apiMocks.fetchAssetProfile.mockResolvedValueOnce(
      makeProfile({
        quote_snapshot: null,
        bars,
        valuation_snapshot: {
          total_market_cap: 1000000000,
          float_market_cap: 900000000,
          pe_ttm: 10,
          pb: 1.2,
          volume_ratio: 9.99,
          data_status: 'available',
          missing_fields: []
        }
      } as Partial<AssetProfile>)
    );

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    const quote = await screen.findByRole('region', { name: '今日价格行为' });
    const amountRatio = within(quote).getByText('量能/20日均额').closest('div');

    expect(amountRatio).toHaveTextContent('量能/20日均额0.00x');
    expect(amountRatio).not.toHaveTextContent('9.99x');
  });

  it('does not apply up-or-down styling to a flat quote change', async () => {
    apiMocks.fetchAssetProfile.mockResolvedValueOnce(
      makeProfile({
        quote_snapshot: {
          trade_date: '2026-06-08',
          open: 10.6,
          high: 11.2,
          low: 10.4,
          close: 11,
          preclose: 11,
          volume: 1300,
          amount: 14300,
          turnover_rate: 2.35,
          pct_chg: 0,
          amount_ratio_20d: 1.23,
          data_status: 'available',
          missing_fields: []
        }
      } as Partial<AssetProfile>)
    );

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    const quote = await screen.findByRole('region', { name: '今日价格行为' });
    const flatChange = within(quote).getByText('0.00%');

    expect(flatChange).not.toHaveClass('market-up');
    expect(flatChange).not.toHaveClass('market-down');
  });

  it('renders unknown company status and Chinese fallback copy when profile fields are missing', async () => {
    apiMocks.fetchAssetProfile.mockResolvedValueOnce(
      makeProfile({
        asset: null,
        company_profile: {
          asset_id: '000001.SZ',
          ts_code: '000001.SZ',
          symbol: '000001',
          name: '平安银行',
          exchange: 'SZ',
          board: null,
          list_date: null,
          is_active: null,
          is_beijing: false,
          is_star: false,
          is_chinext: false,
          region: null,
          source: null
        },
        company_overview: {
          industry: null,
          concept_tags: [],
          business_summary: null,
          profile_summary: null,
          primary_products: [],
          data_status: 'missing',
          missing_fields: ['industry']
        }
      } as Partial<AssetProfile>)
    );

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    const companyBasics = await screen.findByRole('region', { name: '公司基础信息' });

    expect(within(companyBasics).getAllByText('信息待补充').length).toBeGreaterThan(0);
    expect(within(companyBasics).getByText('待补充')).toBeVisible();
    expect(within(companyBasics).getByText('暂无公司业务摘要。')).toBeVisible();
    expect(within(companyBasics).queryByText('非活跃')).not.toBeInTheDocument();
    expect(within(companyBasics).queryByText('asset detail')).not.toBeInTheDocument();
    expect(within(companyBasics).queryByText('missing')).not.toBeInTheDocument();
  });

  it('reloads the profile when the parent default trade date advances', async () => {
    const { rerender } = render(<StockWorkspace initialAssetId="000001.SZ" defaultTradeDate="2026-06-30" />);

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
    await waitFor(() =>
      expect(apiMocks.fetchAssetProfile).toHaveBeenCalledWith(
        '000001.SZ',
        '2026-06-30',
        '2026-01-01',
        '2026-06-30',
        'manual_v1',
        'qfq'
      )
    );

    rerender(<StockWorkspace initialAssetId="000001.SZ" defaultTradeDate="2026-07-02" />);

    await waitFor(() =>
      expect(apiMocks.fetchAssetProfile).toHaveBeenLastCalledWith(
        '000001.SZ',
        '2026-07-02',
        '2026-01-03',
        '2026-07-02',
        'manual_v1',
        'qfq'
      )
    );
    expect((await screen.findAllByText(/复盘日 2026-07-02/)).length).toBeGreaterThan(0);
  });

  it('renders an action-first review summary before quote and evidence sections', async () => {
    render(<StockWorkspace initialAssetId="000001.SZ" />);

    const summary = await screen.findByRole('region', { name: '明日处理结论' });
    const quote = await screen.findByRole('region', { name: '今日价格行为' });
    const evidence = await screen.findByRole('region', { name: '支撑证据' });

    expect(summary).toBeInTheDocument();
    expect(summary).toHaveClass('stock-review-conclusion');
    expect(within(summary).getByText('明日处理建议')).toBeVisible();
    expect(within(summary).getByText('一句话结论')).toBeVisible();
    expect(within(summary).getByText('结论置信度')).toBeVisible();

    const summaryOrder = summary.compareDocumentPosition(quote);
    const quoteOrder = quote.compareDocumentPosition(evidence);
    expect(summaryOrder & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(quoteOrder & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('groups quote, evidence, and background sections by review flow', async () => {
    render(<StockWorkspace initialAssetId="000001.SZ" />);

    const behavior = await screen.findByRole('region', { name: '今日价格行为' });
    const evidence = await screen.findByRole('region', { name: '支撑证据' });
    const companyBasics = await screen.findByRole('region', { name: '公司基础信息' });
    const businessQuality = await screen.findByRole('region', { name: '主营构成与经营质量' });

    expect(within(behavior).getByText('今日价格行为')).toBeVisible();
    expect(behavior).toHaveClass('stock-price-behavior');
    expect(behavior.querySelector('.stock-quote-metrics')).toBeInTheDocument();
    expect(within(evidence).getByText('相关新闻')).toBeVisible();
    expect(within(evidence).getByText('策略证据摘要')).toBeVisible();
    expect(within(companyBasics).getByText('公司档案')).toBeVisible();
    expect(within(companyBasics).getByText('业务概览')).toBeVisible();
    expect(within(businessQuality).getByText('主营构成')).toBeVisible();
    expect(within(businessQuality).getByText('经营质量')).toBeVisible();
  });

  it('renders price behavior before company basics and business quality in the A layout', async () => {
    apiMocks.fetchAssetProfile.mockResolvedValueOnce(
      makeProfile({
        company_overview: {
          industry: '消费电子',
          concept_tags: ['AI 终端', '果链'],
          business_summary: '聚焦消费电子精密制造',
          profile_summary: '覆盖核心品牌客户',
          primary_products: ['结构件', '声学模组'],
          data_status: 'available',
          missing_fields: []
        },
        business_composition: {
          report_period: '2026Q1',
          data_status: 'available',
          missing_fields: [],
          groups: [
            {
              classify_type: '按产品',
              items: [
                { item_name: '精密结构件', revenue: 12500000000, revenue_ratio: 0.62, gross_margin: 0.24 },
                { item_name: '声学模组', revenue: 5100000000, revenue_ratio: 0.25, gross_margin: 0.18 }
              ]
            }
          ]
        },
        financial_snapshot: {
          report_period: '2026Q1',
          announcement_date: '2026-04-28',
          revenue_ttm: 32800000000,
          np_parent_ttm: 2960000000,
          operating_cash_flow: 3410000000,
          roe: 0.17,
          gross_margin: 0.235,
          debt_ratio: 0.44,
          ocf_to_np: 1.15,
          data_status: 'available',
          missing_fields: []
        }
      })
    );

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    const companyBasics = await screen.findByRole('region', { name: '公司基础信息' });
    const businessQuality = await screen.findByRole('region', { name: '主营构成与经营质量' });
    const behavior = await screen.findByRole('region', { name: '今日价格行为' });

    expect(behavior.compareDocumentPosition(companyBasics) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(behavior.compareDocumentPosition(businessQuality) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    expect(within(companyBasics).getByText('消费电子')).toBeVisible();
    expect(within(companyBasics).getByText('AI 终端')).toBeVisible();
    expect(within(companyBasics).getByText('果链')).toBeVisible();

    expect(within(businessQuality).getByText('精密结构件')).toBeVisible();
    expect(businessQuality.querySelector('.stock-composition-item')).toBeInTheDocument();
    expect(within(businessQuality).getByText('占比 62.00%')).toBeVisible();
    expect(within(businessQuality).getByText('328.00亿')).toBeVisible();
    expect(within(businessQuality).getByText('17.00%')).toBeVisible();
    expect(within(businessQuality).getByText('1.15x')).toBeVisible();
  });

  it('groups intraday chart periods under 分时 and loads weekly or monthly bars', async () => {
    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByRole('heading', { name: /平安银行|Stock Workspace/ })).toBeInTheDocument();
    await waitFor(() =>
      expect(apiMocks.fetchDailyBars).toHaveBeenCalledWith('000001.SZ', undefined, '2026-06-18', {
        resolution: '1D',
        adjustType: 'qfq'
      })
    );
    expect(screen.getByRole('button', { name: '日K' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '周K' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '月K' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '分时' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '30m' })).not.toBeInTheDocument();

    apiMocks.fetchDailyBars.mockResolvedValueOnce([
      { time: '2026-06-05', open: 10, high: 12, low: 9.8, close: 11.5, volume: 3000, amount: 33000 }
    ]);
    fireEvent.click(screen.getByRole('button', { name: '周K' }));

    await waitFor(() =>
      expect(apiMocks.fetchDailyBars).toHaveBeenLastCalledWith('000001.SZ', undefined, '2026-06-18', {
        resolution: '1W',
        adjustType: 'qfq'
      })
    );
    expect(screen.getByRole('button', { name: '周K' })).toHaveAttribute('aria-pressed', 'true');
    expect(await screen.findByTestId('asset-chart')).toHaveTextContent('daily');

    apiMocks.fetchDailyBars.mockResolvedValueOnce([
      { time: '2026-06-18 10:30:00', open: 10, high: 10.8, low: 9.9, close: 10.5, volume: 1800, amount: 19000 }
    ]);
    fireEvent.click(screen.getByRole('button', { name: '分时' }));
    expect(screen.getByRole('button', { name: '60m' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '30m' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '10m' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '5m' })).toBeInTheDocument();
    await waitFor(() =>
      expect(apiMocks.fetchDailyBars).toHaveBeenLastCalledWith('000001.SZ', '2025-12-20', '2026-06-18', {
        resolution: '60m',
        adjustType: 'raw'
      })
    );

    apiMocks.fetchDailyBars.mockResolvedValueOnce([
      { time: '2026-06-18 10:00:00', open: 10, high: 10.5, low: 9.9, close: 10.3, volume: 1000, amount: 10300 }
    ]);
    fireEvent.click(screen.getByRole('button', { name: '30m' }));

    await waitFor(() =>
      expect(apiMocks.fetchDailyBars).toHaveBeenLastCalledWith('000001.SZ', '2025-12-20', '2026-06-18', {
        resolution: '30m',
        adjustType: 'raw'
      })
    );
    expect(screen.getByRole('button', { name: '分时' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '30m' })).toHaveAttribute('aria-pressed', 'true');
    expect(await screen.findByTestId('asset-chart')).toHaveTextContent('intraday');
  });

  it('uses the latest platform date instead of an old source handoff date', async () => {
    render(
      <StockWorkspace
        initialAssetId="000001.SZ"
        defaultTradeDate="2026-07-21"
        entryContext={{ sourceWorkspace: 'reviewQueue', tradeDate: '2026-05-18' }}
      />
    );

    await waitFor(() =>
      expect(apiMocks.fetchAssetProfile).toHaveBeenCalledWith(
        '000001.SZ',
        '2026-07-21',
        '2026-01-22',
        '2026-07-21',
        'manual_v1',
        'qfq'
      )
    );
    await waitFor(() =>
      expect(apiMocks.fetchDailyBars).toHaveBeenCalledWith(
        '000001.SZ',
        undefined,
        '2026-07-21',
        { resolution: '1D', adjustType: 'qfq' }
      )
    );
    expect(screen.getByText(/结论更新 2026-07-21/)).toBeInTheDocument();
  });

  it('renders a decision-first layout with price state and collapsed secondary evidence', async () => {
    apiMocks.fetchAssetProfile.mockResolvedValueOnce(
      makeProfile({
        bars: makeReviewBars(),
        decisions: [makeProfile().decisions[0]],
        outcomes: [makeOutcome()]
      })
    );

    render(
      <StockWorkspace
        initialAssetId="000001.SZ"
        entryContext={{
          sourceWorkspace: 'reviewQueue',
          tradeDate: '2026-06-05',
          sourceName: 'LHB Shortline Combo',
          topnRank: 1
        }}
      />
    );

    const summary = await screen.findByRole('region', { name: '明日处理结论' });
    expect(summary).toHaveTextContent('平安银行');
    expect(within(summary).getByText('LHB Shortline Combo')).toBeInTheDocument();
    expect(within(summary).getByText('2026-06-18')).toBeInTheDocument();
    expect(within(summary).getByText('第 1 名')).toBeInTheDocument();
    expect(within(summary).getByText('当日涨跌幅')).toBeInTheDocument();
    expect(within(summary).getByText('+1.85%')).toBeInTheDocument();
    expect(within(summary).getByText('近5日表现')).toBeInTheDocument();
    expect(within(summary).getAllByText('+10.00%').length).toBeGreaterThan(0);
    expect(within(summary).getByText('量能/20日均额')).toBeInTheDocument();
    expect(within(summary).getByText('1.23x')).toBeInTheDocument();
    expect(within(summary).getByText('价格状态')).toBeInTheDocument();
    expect(within(summary).getAllByText('加速').length).toBeGreaterThan(0);

    expect(screen.getByRole('region', { name: '复盘决策栏' })).toBeInTheDocument();
    expect(screen.getByText('二级信息')).toBeInTheDocument();
    expect(screen.getByRole('group', { name: '二级信息' })).not.toHaveAttribute('open');
  });

  it('creates operator decisions from Evidence Digest lineage and refreshes history', async () => {
    apiMocks.fetchEvidenceDigest.mockResolvedValueOnce(
      makeEvidenceDigest({
        run_id: 'eod-2026-06-18-local',
        digest_key: '2026-06-18:manual_v1:000001.SZ',
        latest_trade_date: '2026-06-18',
        lineage: {
          source_type: 'score_topn',
          source_name: 'manual_v1_topn',
          review_item_snapshot_id: 'review_item_snapshot:abc',
          evidence_digest_snapshot_id: 'evidence_digest_snapshot:def'
        }
      })
    );
    apiMocks.fetchAssetProfile
      .mockResolvedValueOnce(makeProfile({ decisions: [] }))
      .mockResolvedValueOnce(
        makeProfile({
          decisions: [
            {
              ...makeProfile().decisions[0],
              event_id: 'operator_decision:operator-decision-api-2026-06-18:0:abc',
              decision_label: 'observe',
              notes: '观察回踩确认'
            }
          ]
        })
      );

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByText('平安银行 evidence digest')).toBeInTheDocument();
    const panel = await screen.findByRole('region', { name: 'Operator Decision Panel' });
    fireEvent.change(within(panel).getByLabelText('operator note'), {
      target: { value: '观察回踩确认' }
    });
    fireEvent.click(within(panel).getByRole('button', { name: 'Save decision' }));

    await waitFor(() => expect(apiMocks.createOperatorDecision).toHaveBeenCalledTimes(1));
    expect(apiMocks.createOperatorDecision).toHaveBeenCalledWith(
      expect.objectContaining({
        asset_id: '000001.SZ',
        stock_code: '000001.SZ',
        stock_name: '平安银行',
        decision_date: '2026-06-18',
        operator_action: 'watch',
        operator_note: '观察回踩确认',
        run_id: 'eod-2026-06-18-local',
        digest_key: '2026-06-18:manual_v1:000001.SZ',
        review_item_snapshot_id: 'review_item_snapshot:abc',
        evidence_digest_snapshot_id: 'evidence_digest_snapshot:def',
        source_type: 'score_topn',
        source_name: 'manual_v1_topn',
        source_context: expect.objectContaining({ entry: 'evidence_digest' })
      })
    );
    expect(await within(panel).findByText('证据快照已关联')).toBeInTheDocument();
    await waitFor(() => expect(apiMocks.fetchAssetProfile).toHaveBeenCalledTimes(2));
    const reviewOutcomes = screen.getByRole('region', { name: 'Review / Outcomes' });
    expect(within(reviewOutcomes).getByText('观察回踩确认')).toBeInTheDocument();
  });

  it('edits review log notes in place', async () => {
    const profile = makeProfile({
      decisions: [
        {
          ...makeProfile().decisions[0],
          event_id: 'operator_decision:1',
          decision_label: 'observe',
          notes: '原备注',
          follow_up_note: '',
          requires_follow_up: false
        }
      ]
    });
    apiMocks.fetchAssetProfile.mockResolvedValueOnce(profile);
    apiMocks.updateOperatorDecision.mockResolvedValueOnce({
      ...profile.decisions[0],
      notes: '更新后的复盘备注',
      follow_up_note: '明天看量能',
      requires_follow_up: true
    });

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    const reviewLog = await screen.findByRole('region', { name: '复盘日志' });
    fireEvent.click(within(reviewLog).getByRole('button', { name: '编辑复盘日志' }));
    fireEvent.change(within(reviewLog).getByLabelText('复盘日志备注'), {
      target: { value: '更新后的复盘备注' }
    });
    fireEvent.click(within(reviewLog).getByLabelText('需要跟进'));
    fireEvent.change(within(reviewLog).getByLabelText('跟进说明'), {
      target: { value: '明天看量能' }
    });
    fireEvent.click(within(reviewLog).getByRole('button', { name: '保存复盘日志' }));

    await waitFor(() => expect(apiMocks.updateOperatorDecision).toHaveBeenCalledTimes(1));
    expect(apiMocks.updateOperatorDecision).toHaveBeenCalledWith('operator_decision:1', {
      notes: '更新后的复盘备注',
      requires_follow_up: true,
      follow_up_note: '明天看量能'
    });
    expect(await within(reviewLog).findByText('更新后的复盘备注')).toBeInTheDocument();
    expect(within(reviewLog).getByText('明天看量能')).toBeInTheDocument();
  });

  it('renders the source workspace and match reason for stock handoffs', async () => {
    const entryContext: StockEntryContext = {
      sourceWorkspace: 'search',
      matchReason: 'Exact code match',
      newsId: 'news-1',
      eventKey: 'r1:000001.SZ',
      reportId: 'r1',
      monitorTab: 'limit_up'
    };

    render(
      <StockWorkspace
        initialAssetId="000001.SZ"
        entryContext={entryContext}
      />
    );

    expect(await screen.findByText('来源工作台：Search')).toBeInTheDocument();
    expect(screen.getByText('Exact code match')).toBeInTheDocument();
    expect(screen.getByText('newsId: news-1')).toBeInTheDocument();
    expect(screen.getByText('eventKey: r1:000001.SZ')).toBeInTheDocument();
    expect(screen.getByText('reportId: r1')).toBeInTheDocument();
    expect(screen.getByText('Monitor Tab limit_up')).toBeInTheDocument();
  });

  it('renders tech bottleneck thesis context inside the stock workspace', async () => {
    apiMocks.fetchAssetProfile.mockResolvedValueOnce(
      makeProfile({
        asset_id: 'CN:SZ:002885',
        canonical_asset_id: 'CN:SZ:002885',
        asset: { asset_id: '002885.SZ', symbol: '002885', name: '京泉华', exchange: 'SZ', board: null, is_active: true },
        score: {
          trade_date: '2026-06-08',
          asset_id: '002885.SZ',
          rank: 12,
          score_total: 74.2,
          score_version: 'manual_v1',
          score_components: { momentum: 21.2, quality: 17.4 }
        }
      })
    );
    const entryContext: StockEntryContext = {
      sourceWorkspace: 'techBottleneck',
      assetId: '002885.SZ',
      stockName: '京泉华',
      query: '京泉华',
      techBottleneckSource: 'tech_bottleneck_candidate_universe_workbench_patch_v1',
      sourceGroup: 'verified_rescue_extension_proposal',
      previousTier: 'Tier B',
      finalManualApprovalCategory: 'core_approval_candidate',
      evidenceStrength: 'moderate',
      bottleneckRelevance: 'core',
      evidenceCategory: 'key_component',
      businessRelevanceCategory: 'key_component',
      researchPriorityScore: 57.25,
      reviewStatus: 'not_reviewed',
      primarySourceUrl: 'https://example.com/announcement',
      evidenceExcerpt: '磁性元器件、电源产品用于电力电子关键环节。',
      rationale: 'verified rescue candidate integrated into manual review only stock workspace',
      nextAction: '核查客户认证和订单进入财报情况',
      reportStatus: 'partial_primary_source_missing',
      bottleneckConfidenceScore: 78,
      evidenceQualityScore: 58,
      reportReviewDecision: 'evidence_required',
      reportUpdatedAt: '2026-07-03T09:11:15+00:00',
      reportHtmlPath: 'outputs/research/tech_bottleneck_candidate_reports_enriched_v1/reports/002885_京泉华/report.html',
      reportPdfPath: 'outputs/research/tech_bottleneck_candidate_reports_enriched_v1/reports/002885_京泉华/report.pdf',
      evidenceMatrixPath: 'outputs/research/tech_bottleneck_candidate_reports_enriched_v1/evidence/002885/evidence_matrix.csv',
      reportSourcesPath: 'outputs/research/tech_bottleneck_candidate_reports_enriched_v1/evidence/002885/sources.jsonl',
      evidenceGapNote: 'primary source fields require follow-up',
      allowedForSignal: false,
      allowedForAdmission: false
    };

    render(<StockWorkspace initialAssetId="002885.SZ" entryContext={entryContext} />);

    const thesisPanel = await screen.findByRole('region', { name: '科技卡脖子复盘摘要' });
    expect(within(thesisPanel).queryByText('候选名称')).not.toBeInTheDocument();
    expect(within(thesisPanel).queryByText('来源')).not.toBeInTheDocument();
    expect(within(thesisPanel).queryByText('原 Tier')).not.toBeInTheDocument();
    expect(
      within(thesisPanel).queryByText('research-only · manual review only · no production signal/admission')
    ).not.toBeInTheDocument();
    expect(within(thesisPanel).queryByText('pending')).not.toBeInTheDocument();
    expect(within(thesisPanel).queryByText('not_reviewed')).not.toBeInTheDocument();
    expect(within(thesisPanel).getByRole('heading', { name: '科技卡脖子复盘摘要' })).toBeInTheDocument();
    expect(within(thesisPanel).getByText('核心判断')).toBeInTheDocument();
    expect(within(thesisPanel).getByText('瓶颈置信分')).toBeInTheDocument();
    expect(within(thesisPanel).getByText('证据质量分')).toBeInTheDocument();
    expect(within(thesisPanel).getByText('证据强度')).toBeInTheDocument();
    expect(within(thesisPanel).getAllByRole('article')).toHaveLength(7);
    expect(within(thesisPanel).getByText('中等')).toBeInTheDocument();
    expect(within(thesisPanel).getByText('核心瓶颈')).toBeInTheDocument();
    expect(within(thesisPanel).getByText('57.25')).toBeInTheDocument();
    expect(within(thesisPanel).getByText('当前缺口')).toBeInTheDocument();
    expect(within(thesisPanel).getByText('建议动作')).toBeInTheDocument();
    expect(within(thesisPanel).getByText('一手来源仍待补齐')).toBeInTheDocument();
    expect(within(thesisPanel).getByText('核查客户认证和订单进入财报情况')).toBeInTheDocument();
    expect(within(thesisPanel).getByText('研究优先级')).toBeInTheDocument();
    expect(within(thesisPanel).queryByText('人工审批分类')).not.toBeInTheDocument();
    expect(within(thesisPanel).queryByText('证据/业务类别')).not.toBeInTheDocument();
    expect(within(thesisPanel).queryByText('review_decision')).not.toBeInTheDocument();
    expect(within(thesisPanel).getByText('78')).toBeInTheDocument();
    expect(within(thesisPanel).getByText('58')).toBeInTheDocument();
    expect(within(thesisPanel).queryByText('primary source fields require follow-up')).not.toBeInTheDocument();
    expect(screen.getByText('来源工作台：科技卡脖子复盘')).toBeInTheDocument();
    expect(screen.getByText('科技卡脖子来源 tech_bottleneck_candidate_universe_workbench_patch_v1')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '技术瓶颈候选上下文' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '科技卡脖子报告面板' })).not.toBeInTheDocument();
  });

  it('renders a single tech bottleneck thesis section in enhanced mode', async () => {
    const entryContext: StockEntryContext = {
      sourceWorkspace: 'techBottleneck',
      stockName: '北方华创',
      reviewStatus: 'not_reviewed',
      sourceGroup: 'seed_tier_a',
      previousTier: 'Tier A',
      evidenceStrength: 'pending_primary_source',
      bottleneckRelevance: 'likely_core_pending',
      researchPriorityScore: 92,
      finalManualApprovalCategory: 'likely_hard_tech_pending_evidence',
      evidenceCategory: 'semiconductor_equipment_or_material',
      nextAction: 'manual review and evidence backfill',
      rationale: '核心设备链条相关，但一手来源待补齐。',
      reportStatus: 'partial_primary_source_missing',
      bottleneckConfidenceScore: 69,
      evidenceQualityScore: 33,
      reportReviewDecision: 'evidence_required',
      evidenceGapNote: 'primary source fields require follow-up'
    };

    render(<StockWorkspace initialAssetId="002371.SZ" entryContext={entryContext} />);

    const thesis = await screen.findByRole('region', { name: '科技卡脖子复盘摘要' });
    expect(within(thesis).queryByText('research-only · manual review only · no production signal/admission')).not.toBeInTheDocument();
    expect(within(thesis).queryByText('pending')).not.toBeInTheDocument();
    expect(within(thesis).queryByText('not_reviewed')).not.toBeInTheDocument();
    expect(within(thesis).getByRole('heading', { name: '科技卡脖子复盘摘要' })).toBeVisible();
    expect(within(thesis).getByText('核心判断')).toBeVisible();
    expect(within(thesis).getByText('瓶颈置信分')).toBeVisible();
    expect(within(thesis).getByText('证据质量分')).toBeVisible();
    expect(within(thesis).getByText('证据强度')).toBeVisible();
    expect(within(thesis).getAllByRole('article')).toHaveLength(7);
    expect(within(thesis).getByText('待一手来源')).toBeVisible();
    expect(within(thesis).getByText('可能核心待证据')).toBeVisible();
    expect(within(thesis).getByText('当前缺口')).toBeVisible();
    expect(within(thesis).getByText('建议动作')).toBeVisible();
    expect(within(thesis).getByText('研究优先级')).toBeVisible();
    expect(within(thesis).getByText('一手来源仍待补齐')).toBeVisible();
    expect(within(thesis).getByText('先补证，再做人工复核')).toBeVisible();
    expect(within(thesis).getByText('69')).toBeVisible();
    expect(within(thesis).getByText('33')).toBeVisible();
    expect(within(thesis).queryByText('manual review and evidence backfill')).not.toBeInTheDocument();
    expect(within(thesis).queryByText('primary source fields require follow-up')).not.toBeInTheDocument();
    expect(within(thesis).queryByText('候选名称')).not.toBeInTheDocument();
    expect(within(thesis).queryByText('来源')).not.toBeInTheDocument();
    expect(within(thesis).queryByText('原 Tier')).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '技术瓶颈候选上下文' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '科技卡脖子报告面板' })).not.toBeInTheDocument();
  });

  it('uses compact thesis fields for review-universe style entries', async () => {
    apiMocks.fetchAssetProfile.mockResolvedValueOnce(
      makeProfile({
        asset_id: '000049.SZ',
        canonical_asset_id: '000049.SZ',
        asset: {
          asset_id: '000049.SZ',
          symbol: '000049',
          name: '德赛电池',
          exchange: 'SZ',
          board: null,
          is_active: true
        },
        signals: [],
        decisions: [],
        outcomes: [],
        factor_values: []
      })
    );

    render(<StockWorkspace initialAssetId="000049.SZ" entryContext={reviewUniverseTechBottleneckEntryContext} />);

    const thesis = await screen.findByRole('region', { name: '科技卡脖子复盘摘要' });
    expect(within(thesis).queryByText('research-only · manual review only · no production signal/admission')).not.toBeInTheDocument();
    expect(within(thesis).queryByText('pending')).not.toBeInTheDocument();
    expect(within(thesis).queryByText('not_reviewed')).not.toBeInTheDocument();
    expect(within(thesis).getByRole('heading', { name: '科技卡脖子复盘摘要' })).toBeVisible();
    expect(within(thesis).getByText('核心判断')).toBeVisible();
    expect(within(thesis).getByText('瓶颈置信分')).toBeVisible();
    expect(within(thesis).getByText('证据质量分')).toBeVisible();
    expect(within(thesis).getByText('证据强度')).toBeVisible();
    expect(within(thesis).getByText('核心瓶颈')).toBeVisible();
    expect(within(thesis).getByText('充分')).toBeVisible();
    expect(within(thesis).getByText('88')).toBeVisible();
    expect(within(thesis).getByText('62')).toBeVisible();
    expect(within(thesis).getByText('研究优先级')).toBeVisible();
    expect(within(thesis).queryByText('客户验证证据待补齐')).not.toBeInTheDocument();
    expect(within(thesis).getAllByText('-').length).toBeGreaterThan(0);
    expect(within(thesis).getByText('人工复核确认')).toBeVisible();
    expect(
      within(thesis).queryByText('evidence=48; page_citations=18; sources=3; domain=strong; role=moderate; bottleneck=strong')
    ).not.toBeInTheDocument();
    expect(
      within(thesis).queryByText(/深圳市德赛电池科技股份有限公司 2025 年半年度报告全文/)
    ).not.toBeInTheDocument();
    expect(
      within(thesis).queryByText('manual review of upgraded primary-source evidence before any future core-pool action')
    ).not.toBeInTheDocument();
    expect(within(thesis).queryByText('候选名称')).not.toBeInTheDocument();
    expect(within(thesis).queryByText('来源')).not.toBeInTheDocument();
    expect(within(thesis).queryByText('原 Tier')).not.toBeInTheDocument();
    expect(screen.queryByText('来源工作台：科技卡脖子复盘')).not.toBeInTheDocument();
    expect(screen.queryByText('科技卡脖子来源 tech_bottleneck_review_universe_frontend_dataset_v1')).not.toBeInTheDocument();
  });

  it('separates tech-bottleneck evidence strength from generic digest coverage in review-universe mode', async () => {
    apiMocks.fetchAssetProfile.mockResolvedValueOnce(
      makeProfile({
        asset_id: '000049.SZ',
        canonical_asset_id: '000049.SZ',
        asset: {
          asset_id: '000049.SZ',
          symbol: '000049',
          name: '德赛电池',
          exchange: 'SZ',
          board: null,
          is_active: true
        },
        signals: [],
        decisions: [],
        outcomes: [],
        factor_values: []
      })
    );
    apiMocks.fetchEvidenceDigest.mockResolvedValueOnce(
      makeEvidenceDigest({
        asset_id: '000049.SZ',
        canonical_asset_id: '000049.SZ',
        trade_date: '2026-06-18',
        title: 'Thin evidence: 德赛电池',
        bucket: 'thin',
        facts: [{ kind: 'news', key: 'news-1', label: 'no matching public news items' }],
        risk_flags: [],
        source_refs: {
          workspace: 'stock',
          asset_id: '000049.SZ'
        },
        next_actions: []
      })
    );
    apiMocks.fetchStockMarketContextHeatmap.mockResolvedValueOnce(
      makeStockMarketContextHeatmapPayload({
        asset_id: '000049.SZ',
        canonical_asset_id: '000049.SZ',
        industry: { industry_id: 'battery', industry_name: '电池', industry_system: 'csrc' },
        selected: {
          asset_id: '000049.SZ',
          symbol: '000049',
          name: '德赛电池',
          price: 24.04,
          change_pct: 0.0029,
          amount: 167000000,
          amount_rank: 12,
          change_rank: 16,
          amount_percentile: 0.7,
          change_percentile: 0.6
        },
        peers: [
          {
            asset_id: '000049.SZ',
            symbol: '000049',
            name: '德赛电池',
            price: 24.04,
            change_pct: 0.0029,
            amount: 167000000,
            value: 167000000,
            is_selected: true
          },
          {
            asset_id: '600487.SH',
            symbol: '600487',
            name: '亨通光电',
            price: 18.88,
            change_pct: 0.0403,
            amount: 190000000,
            value: 190000000,
            is_selected: false
          }
        ],
        data_status: 'completed',
        summary: {
          peer_count: 2,
          up_count: 2,
          flat_count: 0,
          down_count: 0,
          total_amount: 357000000,
          selected_in_peer_set: true
        }
      })
    );

    render(<StockWorkspace initialAssetId="000049.SZ" entryContext={reviewUniverseTechBottleneckEntryContext} />);

    const digestPanel = await screen.findByRole('region', { name: '策略证据摘要' });
    expect(await within(digestPanel).findByText('新闻/研报覆盖偏弱')).toBeInTheDocument();
    expect(
      await within(digestPanel).findByText('这里只看新闻、研报与通用市场摘要，不等同于上方科技卡脖子复盘摘要口径。')
    ).toBeInTheDocument();
    expect(within(digestPanel).getByText('德赛电池 通用新闻/研报摘要')).toBeInTheDocument();
    expect(within(digestPanel).queryByText('证据较薄')).not.toBeInTheDocument();

    const marketPanel = await screen.findByRole('region', { name: 'Market Monitor State' });
    const marketEvidenceRow = within(marketPanel).getByText('市场证据').closest('div');
    expect(marketEvidenceRow).toHaveTextContent('市场证据已接入');
    expect(marketPanel).toHaveClass('stock-market-environment-panel');
    expect(screen.queryByRole('region', { name: 'Strategy Signal' })).not.toBeInTheDocument();
  });

  it('uses decision-first reading order and removes legacy rail shortcuts in tech bottleneck mode', async () => {
    const entryContext: StockEntryContext = {
      sourceWorkspace: 'techBottleneck',
      stockName: '北方华创',
      reviewStatus: 'not_reviewed',
      sourceGroup: 'seed_tier_a',
      previousTier: 'Tier A',
      evidenceStrength: 'pending_primary_source',
      bottleneckRelevance: 'likely_core_pending',
      researchPriorityScore: 92,
      finalManualApprovalCategory: 'likely_hard_tech_pending_evidence',
      evidenceCategory: 'semiconductor_equipment_or_material',
      nextAction: 'manual review and evidence backfill',
      rationale: '核心设备链条相关，但一手来源待补齐。',
      reportStatus: 'partial_primary_source_missing',
      bottleneckConfidenceScore: 69,
      evidenceQualityScore: 33,
      reportReviewDecision: 'evidence_required',
      evidenceGapNote: 'primary source fields require follow-up'
    };

    const { container } = render(<StockWorkspace initialAssetId="002371.SZ" entryContext={entryContext} />);

    const conclusion = await screen.findByRole('region', { name: '明日处理结论' });
    const thesis = await screen.findByRole('region', { name: '科技卡脖子复盘摘要' });
    const companyBasics = await screen.findByRole('region', { name: '公司基础信息' });
    const evidence = await screen.findByRole('region', { name: '支撑证据' });
    const decisionRail = await screen.findByRole('region', { name: '复盘决策栏' });

    const pageText = container.textContent ?? '';
    expect(pageText.indexOf('明日处理结论')).toBeLessThan(pageText.indexOf('科技卡脖子复盘摘要'));
    expect(pageText.indexOf('科技卡脖子复盘摘要')).toBeLessThan(pageText.indexOf('公司基础信息'));
    expect(conclusion.compareDocumentPosition(thesis) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(thesis.compareDocumentPosition(companyBasics) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(evidence.compareDocumentPosition(decisionRail) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByRole('region', { name: '复盘摘要' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '打开新闻' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '打开研报' })).not.toBeInTheDocument();
  });

  it('renders market monitor entry context with trade date and monitor tab', async () => {
    render(
      <StockWorkspace
        initialAssetId="000001.SZ"
        entryContext={{
          sourceWorkspace: 'market',
          assetId: '000001.SZ',
          tradeDate: '2026-06-12',
          monitorTab: 'limit_up',
          query: '平安银行'
        }}
      />
    );

    expect(await screen.findByText(/来源工作台：Market Monitor/)).toBeInTheDocument();
    expect(screen.getByText('Trade Date 2026-06-12')).toBeInTheDocument();
    expect(screen.getAllByText(/limit_up/).length).toBeGreaterThan(0);
    await waitFor(() =>
      expect(apiMocks.fetchAssetProfile).toHaveBeenCalledWith(
        '000001.SZ',
        '2026-06-18',
        '2025-12-20',
        '2026-06-18',
        'manual_v1',
        'qfq'
      )
    );
    await waitFor(() =>
      expect(apiMocks.fetchEvidenceDigest).toHaveBeenCalledWith('000001.SZ', {
        tradeDate: '2026-06-18',
        lookbackDays: 90
      })
    );
  });

  it('loads same-industry market context heatmap for the selected stock', async () => {
    apiMocks.fetchStockMarketContextHeatmap.mockResolvedValue(makeStockMarketContextHeatmapPayload());

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    await waitFor(() => expect(apiMocks.fetchStockMarketContextHeatmap).toHaveBeenCalledWith('000001.SZ', '2026-06-18'));
    expect(await screen.findByRole('region', { name: '同业市场定位' })).toBeInTheDocument();
    expect(screen.getByText('涨跌排名 #1')).toBeInTheDocument();
    expect(screen.getByText('成交额排名 #1')).toBeInTheDocument();
  });

  it('opens a peer stock from the same-industry heatmap context', async () => {
    const onOpenAsset = vi.fn();
    apiMocks.fetchStockMarketContextHeatmap.mockResolvedValue(makeStockMarketContextHeatmapPayload());

    render(<StockWorkspace initialAssetId="000001.SZ" onOpenAsset={onOpenAsset} />);

    fireEvent.click(await screen.findByRole('button', { name: /打开同业 浦发银行/ }));

    expect(onOpenAsset).toHaveBeenCalledWith('600000.SH', {
      sourceWorkspace: 'market',
      monitorTab: 'stock_peer_heatmap',
      tradeDate: '2026-06-18',
      matchReason: 'peer_heatmap'
    });
  });

  it('renders the simplified context rail and recent evidence timeline entries', async () => {
    apiMocks.fetchAssetProfile.mockResolvedValueOnce(
      makeProfile({
        outcomes: [makeOutcome({ outcome_artifact_path: 'reports/outcomes/000001-outcome.json' })]
      })
    );

    render(
      <StockWorkspace
        initialAssetId="000001.SZ"
        entryContext={{ sourceWorkspace: 'news', query: '平安银行', newsId: 'news-1' }}
      />
    );

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
    expect(await screen.findByText('平安银行相关新闻')).toBeInTheDocument();
    expect(await screen.findByText('平安银行深度报告')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '打开新闻' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '打开研报' })).not.toBeInTheDocument();

    const timeline = screen.getByRole('region', { name: 'Evidence Timeline' });
    expect(within(timeline).getByText('News: 平安银行相关新闻')).toBeInTheDocument();
    expect(within(timeline).getByText('Research: 平安银行深度报告')).toBeInTheDocument();
    expect(within(timeline).getByText('watch')).toBeInTheDocument();
    expect(within(timeline).getByText('complete')).toBeInTheDocument();
    expect(within(timeline).getByText('reports/outcomes/000001-outcome.json')).toBeInTheDocument();
  });

  it('clears stale source context when loading another stock', async () => {
    const secondProfile = makeProfile({
      asset_id: '600000.SH',
      canonical_asset_id: '600000.SH',
      asset: {
        asset_id: '600000.SH',
        symbol: '600000',
        name: '浦发银行',
        exchange: 'SH',
        board: null,
        is_active: true
      },
      signals: [],
      decisions: [],
      outcomes: [],
      factor_values: []
    });

    apiMocks.fetchAssetProfile.mockResolvedValueOnce(makeProfile()).mockResolvedValueOnce(secondProfile);

    render(
      <StockWorkspace
        initialAssetId="000001.SZ"
        entryContext={{ sourceWorkspace: 'news', assetId: '000001.SZ', query: 'old-query', newsId: 'news-old' }}
      />
    );

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('stock workspace asset'), { target: { value: '600000' } });
    fireEvent.click(screen.getByRole('button', { name: '加载回放' }));

    expect(await screen.findByRole('heading', { name: /浦发银行/ })).toBeInTheDocument();
    expect(screen.queryByText('来源工作台：News')).not.toBeInTheDocument();
    expect(screen.queryByText('newsId: news-old')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '打开新闻' })).not.toBeInTheDocument();
  });

  it('loads a stock dossier with factors, news, watchlist, and evidence', async () => {
    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
    const summary = screen.getByRole('region', { name: '明日处理结论' });
    expect(within(summary).getByText('策略分数')).toBeInTheDocument();
    expect(within(summary).getByText('82.4')).toBeInTheDocument();
    fireEvent.click(screen.getByText('二级信息'));
    expect(screen.getAllByText('momentum').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Score Component')).toHaveLength(2);
    expect(screen.getByText('quality')).toBeInTheDocument();
    expect(await screen.findByText('平安银行相关新闻')).toBeInTheDocument();
    expect(screen.getByText('candidate')).toBeInTheDocument();
    expect(screen.getByText('reports/evidence/000001.md')).toBeInTheDocument();
  });

  it('renders the stock detail evidence hub sections', async () => {
    const { container } = render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();

    [
      'stock-detail-shell',
      'stock-review-summary',
      'stock-detail-layout',
      'stock-detail-main',
      'stock-context-rail',
      'stock-review-metrics',
      'stock-evidence-grid',
      'stock-secondary-details',
      'stock-timeline'
    ].forEach((className) => {
      expect(container.querySelector(`.${className}`)).toBeInTheDocument();
    });
    expect(container.querySelectorAll('.stock-timeline-row').length).toBeGreaterThan(1);

    [
      '明日处理结论',
      '公司基础信息',
      '主营构成与经营质量',
      '今日价格行为',
      '支撑证据',
      '复盘决策栏',
      '策略证据摘要',
      'Market Monitor State',
      'Strategy Signal',
      'Research Coverage',
      'Related News',
      'Research Reports'
    ].forEach((regionName) => {
      expect(screen.getByRole('region', { name: regionName })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('二级信息'));
    [
      'Factor / Score Breakdown',
      'Review / Outcomes',
      'Evidence Timeline',
      'Search Matches'
    ].forEach((regionName) => {
      expect(screen.getByRole('region', { name: regionName })).toBeInTheDocument();
    });

    const summary = screen.getByRole('region', { name: '明日处理结论' });
    expect(within(summary).getByText('策略分数')).toBeInTheDocument();
    expect(within(summary).getByText('82.4')).toBeInTheDocument();
    expect(screen.getAllByText('momentum').length).toBeGreaterThan(0);
    expect(await screen.findByText('平安银行相关新闻')).toBeInTheDocument();
    expect(screen.getByText('candidate')).toBeInTheDocument();
    expect(screen.getByText('reports/evidence/000001.md')).toBeInTheDocument();
    expect(await screen.findByText('平安银行深度报告')).toBeInTheDocument();
    expect(await screen.findByText('90d reports 4')).toBeInTheDocument();
  });

  it('keeps the review action rail available after the redesign', async () => {
    render(<StockWorkspace initialAssetId="000001.SZ" />);

    const decisionRail = await screen.findByRole('region', { name: '复盘决策栏' });
    expect(within(decisionRail).getByText('复盘操作')).toBeVisible();
    expect(within(decisionRail).getByText('复盘日志')).toBeVisible();
    expect(within(decisionRail).queryByRole('button', { name: /打开新闻/ })).not.toBeInTheDocument();
    expect(within(decisionRail).queryByRole('button', { name: /打开研报/ })).not.toBeInTheDocument();
  });

  it('renders user-facing Chinese evidence copy instead of technical diagnostics', async () => {
    apiMocks.fetchEvidenceDigest.mockResolvedValueOnce(
      makeEvidenceDigest({
        bucket: 'thin',
        warnings: [
          'No review_item_snapshot lookup keys available',
          'No evidence_digest_snapshot lookup keys available'
        ]
      })
    );

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(
      await screen.findByText('个股复盘工作台：集中查看走势、策略证据、新闻研报和人工复盘记录。')
    ).toBeInTheDocument();
    expect(await screen.findByText('证据较薄')).toBeInTheDocument();
    const digestPanel = screen.getByRole('region', { name: '策略证据摘要' });
    expect(
      within(digestPanel).getByText('未找到复盘快照关联，本次决策仍会保存，但无法追溯到原始复盘队列快照。')
    ).toBeInTheDocument();
    expect(
      within(digestPanel).getByText('未找到证据摘要快照关联，本次决策仍会保存，但证据摘要无法做完整追溯。')
    ).toBeInTheDocument();
    expect(
      screen.queryByText('Single-stock evidence hub for price, factors, news, research reports, and strategy history.')
    ).not.toBeInTheDocument();
    expect(within(digestPanel).queryByText('thin')).not.toBeInTheDocument();
    expect(within(digestPanel).queryByText('No review_item_snapshot lookup keys available')).not.toBeInTheDocument();
  });

  it('renders 策略证据摘要 without source-backed next action buttons', async () => {
    const handleOpenNews = vi.fn();
    const handleOpenResearchReports = vi.fn();
    const handleOpenMarketMonitor = vi.fn();

    render(
      <StockWorkspace
        initialAssetId="000001.SZ"
        onOpenNews={handleOpenNews}
        onOpenResearchReports={handleOpenResearchReports}
        onOpenMarketMonitor={handleOpenMarketMonitor}
      />
    );

    const digestPanel = await screen.findByRole('region', { name: '策略证据摘要' });
    expect(within(digestPanel).getByRole('heading', { name: '策略证据摘要' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '证据摘要' })).not.toBeInTheDocument();
    expect(await within(digestPanel).findByText('平安银行 evidence digest')).toBeInTheDocument();
    expect(within(digestPanel).getByText('Score 62')).toBeInTheDocument();
    expect(within(digestPanel).getByText('Recent company news is available')).toBeInTheDocument();
    expect(within(digestPanel).getByText('Latest research keeps buy rating')).toBeInTheDocument();
    expect(within(digestPanel).getByText('Turnover pressure elevated')).toBeInTheDocument();

    expect(within(digestPanel).queryByRole('button', { name: 'Review stock' })).not.toBeInTheDocument();
    expect(within(digestPanel).queryByRole('button', { name: 'Open digest market evidence' })).not.toBeInTheDocument();
    expect(within(digestPanel).queryByRole('button', { name: '查看相关新闻' })).not.toBeInTheDocument();
    expect(within(digestPanel).queryByRole('button', { name: '查看相关研报' })).not.toBeInTheDocument();
    expect(handleOpenNews).not.toHaveBeenCalled();
    expect(handleOpenResearchReports).not.toHaveBeenCalled();
    expect(handleOpenMarketMonitor).not.toHaveBeenCalled();
  });

  it('keeps 策略证据摘要 in loading state before the digest request settles', async () => {
    const pendingDigest = deferred<EvidenceDigestResponse>();
    apiMocks.fetchEvidenceDigest.mockReturnValueOnce(pendingDigest.promise);

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    const digestPanel = await screen.findByRole('region', { name: '策略证据摘要' });
    expect(within(digestPanel).getByText('正在加载证据摘要...')).toBeInTheDocument();
    expect(within(digestPanel).queryByText('暂无证据摘要。')).not.toBeInTheDocument();
  });

  it('shows digest error locally without hiding stock profile', async () => {
    apiMocks.fetchEvidenceDigest.mockRejectedValueOnce(new Error('digest failed'));

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
    const digestPanel = await screen.findByRole('region', { name: '策略证据摘要' });
    expect(within(digestPanel).getByText('digest failed')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: '今日价格行为' })).toBeInTheDocument();
  });

  it('does not let a stale digest response overwrite the newer stock digest', async () => {
    const firstDigest = deferred<EvidenceDigestResponse>();
    const secondDigest = deferred<EvidenceDigestResponse>();
    const secondProfile = makeProfile({
      asset_id: '600000.SH',
      canonical_asset_id: '600000.SH',
      asset: {
        asset_id: '600000.SH',
        symbol: '600000',
        name: '浦发银行',
        exchange: 'SH',
        board: null,
        is_active: true
      },
      signals: [],
      decisions: [],
      outcomes: [],
      factor_values: []
    });

    apiMocks.fetchAssetProfile.mockResolvedValueOnce(makeProfile()).mockResolvedValueOnce(secondProfile);
    apiMocks.fetchEvidenceDigest.mockReturnValueOnce(firstDigest.promise).mockReturnValueOnce(secondDigest.promise);

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
    await waitFor(() =>
      expect(apiMocks.fetchEvidenceDigest).toHaveBeenCalledWith('000001.SZ', {
        tradeDate: '2026-06-18',
        lookbackDays: 90
      })
    );

    fireEvent.change(screen.getByLabelText('stock workspace asset'), { target: { value: '600000' } });
    fireEvent.click(screen.getByRole('button', { name: '加载回放' }));

    expect(await screen.findByRole('heading', { name: /浦发银行/ })).toBeInTheDocument();
    await waitFor(() =>
      expect(apiMocks.fetchEvidenceDigest).toHaveBeenLastCalledWith('600000.SH', {
        tradeDate: '2026-06-18',
        lookbackDays: 90
      })
    );

    await act(async () => {
      secondDigest.resolve(
        makeEvidenceDigest({
          asset_id: '600000.SH',
          canonical_asset_id: '600000.SH',
          title: '浦发银行 current digest',
          facts: [{ kind: 'market', key: 'second', label: 'Second stock market fact' }],
          risk_flags: []
        })
      );
      await secondDigest.promise;
    });

    expect(await screen.findByText('浦发银行 current digest')).toBeInTheDocument();

    await act(async () => {
      firstDigest.resolve(
        makeEvidenceDigest({
          title: 'stale first digest',
          facts: [{ kind: 'news', key: 'old', label: 'Old stale fact' }]
        })
      );
      await firstDigest.promise;
    });

    expect(screen.getByText('浦发银行 current digest')).toBeInTheDocument();
    expect(screen.queryByText('stale first digest')).not.toBeInTheDocument();
    expect(screen.queryByText('Old stale fact')).not.toBeInTheDocument();
  });

  it('renders outcome evidence in Review / Outcomes when no decisions are present', async () => {
    apiMocks.fetchAssetProfile.mockResolvedValueOnce(
      makeProfile({
        decisions: [],
        outcomes: [makeOutcome({ outcome_artifact_path: 'reports/outcomes/watch-outcome.json' })]
      })
    );

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    const reviewSection = await screen.findByRole('region', { name: 'Review / Outcomes' });
    expect(within(reviewSection).getByText('complete')).toBeInTheDocument();
    expect(within(reviewSection).getByText('reports/outcomes/watch-outcome.json')).toBeInTheDocument();
    expect(within(reviewSection).queryByText('No review decisions available.')).not.toBeInTheDocument();
    expect(within(reviewSection).queryByText('No outcomes recorded.')).not.toBeInTheDocument();
  });

  it('loads db-linked asset news for the selected stock', async () => {
    apiMocks.fetchAssetProfile.mockResolvedValueOnce(
      makeProfile({
        asset_id: 'CN:SH:600519',
        canonical_asset_id: 'CN:SH:600519',
        asset: {
          asset_id: 'CN:SH:600519',
          symbol: '600519',
          name: '贵州茅台',
          exchange: 'SH',
          board: null,
          is_active: true
        }
      })
    );
    apiMocks.fetchAssetNews.mockResolvedValueOnce(
      makeAssetNews({
        asset_id: 'CN:SH:600519',
        items: [
          {
            ...makeAssetNews().items[0],
            news_id: 'news-600519',
            title: '贵州茅台相关新闻',
            stocks: [{ asset_id: 'CN:SH:600519', ts_code: '600519.SH', stock_name: '贵州茅台' }]
          }
        ]
      })
    );

    render(<StockWorkspace initialAssetId="600519" />);

    expect(await screen.findByText('贵州茅台相关新闻')).toBeInTheDocument();
    expect(apiMocks.fetchAssetNews).toHaveBeenCalledWith('CN:SH:600519', { limit: 8, lookbackDays: 7 });
  });

  it('shows a loading state while selected stock news is loading', async () => {
    const pendingNews = deferred<AssetNewsResponse>();
    apiMocks.fetchAssetNews.mockReturnValueOnce(pendingNews.promise);

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
    const newsSection = screen.getByRole('region', { name: 'Related News' });
    expect(newsSection).not.toBeNull();
    expect(await within(newsSection as HTMLElement).findByText('Loading...')).toBeInTheDocument();

    await act(async () => {
      pendingNews.resolve(newsPayload);
      await pendingNews.promise;
    });
  });

  it('shows an error when selected stock news fails to load', async () => {
    apiMocks.fetchAssetNews.mockRejectedValueOnce(new Error('news failed'));

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
    expect(await screen.findByText('news failed')).toBeInTheDocument();
    expect(screen.queryByText('平安银行相关新闻')).not.toBeInTheDocument();
  });

  it('renders warnings returned with selected stock news', async () => {
    apiMocks.fetchAssetNews.mockResolvedValueOnce(makeAssetNews({ warnings: ['partial news store coverage'] }));

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByText('平安银行相关新闻')).toBeInTheDocument();
    expect(screen.getByText('partial news store coverage')).toBeInTheDocument();
  });

  it('does not render asset news responses for a different stock', async () => {
    apiMocks.fetchAssetNews.mockResolvedValueOnce(
      makeAssetNews({
        asset_id: '600000.SH',
        items: [
          {
            ...makeAssetNews().items[0],
            news_id: 'news-mismatch',
            title: '浦发银行不应显示的新闻',
            stocks: [{ asset_id: '600000.SH', ts_code: '600000.SH', stock_name: '浦发银行' }]
          }
        ]
      })
    );

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
    await waitFor(() => expect(apiMocks.fetchAssetNews).toHaveBeenCalledWith('000001.SZ', { limit: 8, lookbackDays: 7 }));
    await waitFor(() => expect(screen.getByText('No related news found.')).toBeInTheDocument());
    expect(screen.queryByText('浦发银行不应显示的新闻')).not.toBeInTheDocument();
  });

  it('hides the previous stock news as soon as a new stock profile is visible', async () => {
    const secondNews = deferred<AssetNewsResponse>();
    const secondProfile = makeProfile({
      asset_id: '600000.SH',
      canonical_asset_id: '600000.SH',
      asset: {
        asset_id: '600000.SH',
        symbol: '600000',
        name: '浦发银行',
        exchange: 'SH',
        board: null,
        is_active: true
      },
      signals: [],
      decisions: [],
      outcomes: [],
      factor_values: []
    });

    apiMocks.fetchAssetProfile.mockResolvedValueOnce(makeProfile()).mockResolvedValueOnce(secondProfile);
    apiMocks.fetchAssetNews.mockResolvedValueOnce(makeAssetNews()).mockReturnValueOnce(secondNews.promise);

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByText('平安银行相关新闻')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('stock workspace asset'), { target: { value: '600000' } });
    fireEvent.click(screen.getByRole('button', { name: '加载回放' }));

    expect(await screen.findByRole('heading', { name: /浦发银行/ })).toBeInTheDocument();
    expect(screen.queryByText('平安银行相关新闻')).not.toBeInTheDocument();
    await waitFor(() => expect(apiMocks.fetchAssetNews).toHaveBeenLastCalledWith('600000.SH', { limit: 8, lookbackDays: 7 }));
  });

  it('does not show stale news errors after a new stock profile is visible', async () => {
    const firstNews = deferred<AssetNewsResponse>();
    const secondNews = deferred<AssetNewsResponse>();
    const secondProfile = makeProfile({
      asset_id: '600000.SH',
      canonical_asset_id: '600000.SH',
      asset: {
        asset_id: '600000.SH',
        symbol: '600000',
        name: '浦发银行',
        exchange: 'SH',
        board: null,
        is_active: true
      },
      signals: [],
      decisions: [],
      outcomes: [],
      factor_values: []
    });

    apiMocks.fetchAssetProfile.mockResolvedValueOnce(makeProfile()).mockResolvedValueOnce(secondProfile);
    apiMocks.fetchAssetNews.mockReturnValueOnce(firstNews.promise).mockReturnValueOnce(secondNews.promise);

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
    await waitFor(() => expect(apiMocks.fetchAssetNews).toHaveBeenCalledWith('000001.SZ', { limit: 8, lookbackDays: 7 }));

    fireEvent.change(screen.getByLabelText('stock workspace asset'), { target: { value: '600000' } });
    fireEvent.click(screen.getByRole('button', { name: '加载回放' }));

    expect(await screen.findByRole('heading', { name: /浦发银行/ })).toBeInTheDocument();

    await act(async () => {
      firstNews.reject(new Error('old news failed'));
      await firstNews.promise.catch(() => undefined);
    });

    expect(screen.queryByText('old news failed')).not.toBeInTheDocument();

    await act(async () => {
      secondNews.resolve(makeAssetNews({ asset_id: '600000.SH', items: [] }));
      await secondNews.promise;
    });
  });

  it('normalizes six digit stock input before loading', async () => {
    render(<StockWorkspace initialAssetId="000001.SZ" />);

    await screen.findByRole('heading', { name: /平安银行/ });
    fireEvent.change(screen.getByLabelText('stock workspace asset'), { target: { value: '600000' } });
    fireEvent.click(screen.getByRole('button', { name: '加载回放' }));

    await waitFor(() => {
      expect(apiMocks.fetchAssetProfile).toHaveBeenLastCalledWith(
        '600000.SH',
        '2026-06-18',
        '2025-12-20',
        '2026-06-18',
        'manual_v1',
        'qfq'
      );
    });
  });

  it('searches asset matches only after loading a submitted stock', async () => {
    render(<StockWorkspace initialAssetId="000001.SZ" />);

    await screen.findByRole('heading', { name: /平安银行/ });
    await waitFor(() => {
      expect(apiMocks.searchAssets).toHaveBeenCalledWith('000001.SZ', 8);
    });
    const initialSearchCallCount = apiMocks.searchAssets.mock.calls.length;

    const assetInput = screen.getByLabelText('stock workspace asset');
    fireEvent.change(assetInput, { target: { value: '' } });
    fireEvent.change(assetInput, { target: { value: '6' } });
    fireEvent.change(assetInput, { target: { value: '60' } });
    fireEvent.change(assetInput, { target: { value: '600' } });
    fireEvent.change(assetInput, { target: { value: '6000' } });
    fireEvent.change(assetInput, { target: { value: '60000' } });
    fireEvent.change(assetInput, { target: { value: '600000' } });

    expect(apiMocks.searchAssets).toHaveBeenCalledTimes(initialSearchCallCount);

    fireEvent.click(screen.getByRole('button', { name: '加载回放' }));

    await waitFor(() => {
      expect(apiMocks.searchAssets).toHaveBeenCalledWith('600000.SH', 8);
    });
  });

  it('dedupes repeated search matches without duplicate key warnings', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    apiMocks.searchAssets.mockResolvedValueOnce([
      { asset_id: 'CN:SZ:000001', symbol: '000001', name: '平安银行', exchange: 'SZ' },
      { asset_id: 'CN:SZ:000001', symbol: '000001', name: '平安银行', exchange: 'SZ' },
      { asset_id: 'CN:SH:600000', symbol: '600000', name: '浦发银行', exchange: 'SH' }
    ]);

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    await screen.findByRole('heading', { name: /平安银行/ });
    fireEvent.click(screen.getByText('二级信息'));

    const searchMatches = await screen.findByRole('region', { name: 'Search Matches' });
    expect(within(searchMatches).getAllByRole('button')).toHaveLength(2);
    const messages = consoleError.mock.calls.map((call) => call.join(' ')).join('\n');
    expect(messages).not.toContain('Encountered two children with the same key');
    consoleError.mockRestore();
  });

  it('does not show stale news after a later profile load clears the profile', async () => {
    const firstNews = deferred<AssetNewsResponse>();
    const secondNews = deferred<AssetNewsResponse>();
    const secondProfile = makeProfile({
      asset_id: '600000.SH',
      canonical_asset_id: '600000.SH',
      asset: {
        asset_id: '600000.SH',
        symbol: '600000',
        name: '浦发银行',
        exchange: 'SH',
        board: null,
        is_active: true
      },
      signals: [],
      decisions: [],
      outcomes: [],
      factor_values: []
    });

    apiMocks.fetchAssetProfile
      .mockResolvedValueOnce(makeProfile())
      .mockRejectedValueOnce(new Error('profile failed'))
      .mockResolvedValueOnce(secondProfile);
    apiMocks.fetchAssetNews.mockReturnValueOnce(firstNews.promise).mockReturnValueOnce(secondNews.promise);

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
    await waitFor(() => expect(apiMocks.fetchAssetNews).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText('stock workspace asset'), { target: { value: '600000' } });
    fireEvent.click(screen.getByRole('button', { name: '加载回放' }));

    expect(await screen.findByText('profile failed')).toBeInTheDocument();

    await act(async () => {
      firstNews.resolve(newsPayload);
      await firstNews.promise;
    });

    expect(screen.queryByText('平安银行相关新闻')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '加载回放' }));

    expect(await screen.findByRole('heading', { name: /浦发银行/ })).toBeInTheDocument();
    await waitFor(() => expect(apiMocks.fetchAssetNews).toHaveBeenCalledTimes(2));
    expect(screen.queryByText('平安银行相关新闻')).not.toBeInTheDocument();
  });

  it('loads research reports for the selected stock', async () => {
    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByText('平安银行深度报告')).toBeInTheDocument();
    expect(screen.getByText('90d reports 4')).toBeInTheDocument();
    expect(apiMocks.fetchAssetResearchReports).toHaveBeenCalledWith('000001.SZ', { limit: 5, lookbackDays: 90 });
  });

  it('clears stale research reports while loading reports for a newly selected stock', async () => {
    const secondReports = deferred<AssetResearchReportResponse>();
    let staleReportVisibleWhenSecondFetchStarted: boolean | null = null;
    const secondProfile = makeProfile({
      asset_id: '600000.SH',
      canonical_asset_id: '600000.SH',
      asset: { asset_id: '600000.SH', symbol: '600000', name: '浦发银行', exchange: 'SH', board: null, is_active: true },
      signals: [],
      decisions: [],
      outcomes: [],
      factor_values: []
    });

    apiMocks.fetchAssetProfile.mockResolvedValueOnce(makeProfile()).mockResolvedValueOnce(secondProfile);
    apiMocks.fetchAssetResearchReports
      .mockResolvedValueOnce(makeResearchReports())
      .mockImplementationOnce(() => {
        staleReportVisibleWhenSecondFetchStarted =
          document.body.textContent?.includes('平安银行深度报告') ||
          document.body.textContent?.includes('90d reports 4') ||
          false;
        return secondReports.promise;
      });

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByText('平安银行深度报告')).toBeInTheDocument();
    expect(screen.getByText('90d reports 4')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('stock workspace asset'), { target: { value: '600000' } });
    fireEvent.click(screen.getByRole('button', { name: '加载回放' }));

    expect(await screen.findByRole('heading', { name: /浦发银行/ })).toBeInTheDocument();
    expect(Boolean(staleReportVisibleWhenSecondFetchStarted)).toBe(false);
    expect(screen.queryByText('平安银行深度报告')).not.toBeInTheDocument();
    expect(screen.queryByText('90d reports 4')).not.toBeInTheDocument();
    await waitFor(() =>
      expect(apiMocks.fetchAssetResearchReports).toHaveBeenLastCalledWith('600000.SH', {
        limit: 5,
        lookbackDays: 90
      })
    );

    await act(async () => {
      secondReports.resolve(
        makeResearchReports({
          asset_id: '600000.SH',
          summary: {
            report_count_30d: 1,
            report_count_90d: 2,
            broker_coverage_count_90d: 1,
            latest_report_date: '2026-06-04',
            latest_rating: '增持',
            latest_target_price: 12.3
          },
          items: [
            {
              ...makeResearchReports().items[0],
              report_id: 'r2',
              event_key: 'r2:600000.SH',
              asset_id: '600000.SH',
              ts_code: '600000.SH',
              stock_name: '浦发银行',
              report_title: '浦发银行跟踪报告',
              broker: '中信证券',
              source_url: 'https://example.com/r2'
            }
          ]
        })
      );
      await secondReports.promise;
    });

    expect(await screen.findByText('浦发银行跟踪报告')).toBeInTheDocument();
  });

  it('does not show stale research reports after a later profile load clears the profile', async () => {
    const firstReports = deferred<AssetResearchReportResponse>();
    apiMocks.fetchAssetResearchReports.mockReturnValueOnce(firstReports.promise);
    apiMocks.fetchAssetProfile.mockResolvedValueOnce(makeProfile()).mockRejectedValueOnce(new Error('not found'));

    render(<StockWorkspace initialAssetId="000001.SZ" />);
    await screen.findByRole('heading', { name: /平安银行/ });

    fireEvent.change(screen.getByLabelText('stock workspace asset'), { target: { value: '600000' } });
    fireEvent.click(screen.getByRole('button', { name: '加载回放' }));

    await screen.findByText('not found');

    await act(async () => {
      firstReports.resolve({
        asset_id: '000001.SZ',
        summary: {
          report_count_30d: 2,
          report_count_90d: 4,
          broker_coverage_count_90d: 3,
          latest_report_date: '2026-06-03',
          latest_rating: '买入',
          latest_target_price: 19.5
        },
        items: [],
        warnings: []
      });
    });

    expect(screen.queryByText('90d reports 4')).not.toBeInTheDocument();
  });
});
