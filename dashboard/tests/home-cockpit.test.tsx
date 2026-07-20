import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AppShell } from '../src/components/AppShell';

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

vi.mock('../src/api/client', () => ({
  fetchPlatformReadiness: vi.fn(),
  fetchPlatformSummary: vi.fn(),
  fetchStrategyScoreAudit: vi.fn(),
  fetchStrategyCatalog: vi.fn(),
  fetchBacktestStrategies: vi.fn(),
  fetchOverview: vi.fn(),
  fetchDailyBars: vi.fn(),
  fetchAssetProfile: vi.fn(),
  fetchAssetScore: vi.fn(),
  fetchAssetSignals: vi.fn(),
  fetchAssetDecisions: vi.fn(),
  fetchAssetOutcomes: vi.fn(),
  fetchOutcomeAnalytics: vi.fn(),
  fetchExperimentProposals: vi.fn(),
  fetchExperimentReplay: vi.fn(),
  fetchShadowWatchlist: vi.fn(),
  fetchShadowOutcomes: vi.fn(),
  fetchShadowOutcomeAnalytics: vi.fn(),
  fetchShadowAnalyticsReview: vi.fn(),
  fetchShadowReviewDecisions: vi.fn(),
  fetchShadowFollowUpQueue: vi.fn(),
  fetchShadowFollowUpResolution: vi.fn(),
  fetchStrategyValidationRuns: vi.fn(),
  fetchStrategyValidationReplay: vi.fn(),
  fetchMarketMonitorEod: vi.fn(),
  fetchPublicNews: vi.fn(),
  fetchEvidenceDigest: vi.fn(),
  fetchResearchCases: vi.fn(),
  fetchResearchCaseDetail: vi.fn(),
  fetchResearchQueueHealth: vi.fn(),
  fetchResearchPublishGate: vi.fn(),
  fetchResearchPublicationPreview: vi.fn(),
  fetchResearchPublicationSnapshots: vi.fn(),
  fetchResearchExternalDeliveryPlan: vi.fn(),
  fetchResearchExternalDeliveryAttempts: vi.fn(),
  createResearchReviewAction: vi.fn(),
  fetchResearchEvidence: vi.fn(),
  fetchReviewQueue: vi.fn()
}));

import * as api from '../src/api/client';

describe('AppShell and HomeCockpit', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/');
    vi.mocked(api.fetchPlatformReadiness).mockResolvedValue({
      mode: 'eod_local',
      status: 'PARTIAL',
      as_of: '2026-06-15T08:30:00+08:00',
      latest_market_date: '2026-06-12',
      latest_trade_date: '2026-06-12',
      display_trade_date: '2026-06-08',
      candidate_trade_date: '2026-06-12',
      checks: [
        {
          key: 'market_data',
          label: 'Market data',
          status: 'ready',
          detail: 'Latest EOD data loaded'
        },
        {
          key: 'news_flow',
          label: 'News flow',
          status: 'partial',
          detail: 'Collector is lagging'
        }
      ],
      health_groups: [
        {
          key: 'base_data',
          label: '基础数据',
          status: 'partial',
          ready_count: 1,
          total_count: 2,
          items: [
            {
              key: 'market_data',
              label: 'Market data',
              status: 'ready',
              detail: 'Latest EOD data loaded'
            },
            {
              key: 'news_flow',
              label: 'News flow',
              status: 'partial',
              detail: 'Collector is lagging'
            }
          ]
        }
      ],
      warnings: ['Generated Reports unavailable']
    });
    vi.mocked(api.fetchPlatformSummary).mockResolvedValue({
      latest_market_date: '2026-06-08',
      latest_score_date: '2026-06-08',
      latest_factor_date: '2026-06-07',
      market_asset_count: 5207,
      score_asset_count: 5207,
      factor_count: 43,
      score_versions: ['manual_v1'],
      topn_preview: [
        {
          trade_date: '2026-06-08',
          asset_id: 'CN:SZ:300951',
          rank: 1,
          score_total: 89.9,
          score_version: 'manual_v1',
          score_components: {}
        }
      ]
    });
    vi.mocked(api.fetchStrategyScoreAudit).mockResolvedValue({
      trade_date: '2026-06-08',
      status: 'success',
      overall_status: 'ok',
      summary_path: '/tmp/strategy_score_audit_summary.json',
      detail_path: '/tmp/strategy_score_audit_detail.csv',
      total_rows: 12,
      selected_rows: 12,
      anomaly_row_count: 0,
      anomaly_counts_by_type: {},
      strategies: [],
      sample_rows: []
    });
    vi.mocked(api.fetchStrategyCatalog).mockResolvedValue([
      {
        strategy_id: 'manual_v1_topn_rotation',
        strategy_name: 'Manual V1 TopN Rotation',
        status: 'runnable',
        description: 'TopN rotation',
        factor_groups: ['momentum'],
        signal_inputs: ['factor.stock_score_daily'],
        default_parameters: { top_n: 20 },
        latest_evidence: '',
        primary_action: 'Run backtest'
      }
    ]);
    vi.mocked(api.fetchBacktestStrategies).mockResolvedValue([
      {
        strategy_id: 'lhb_shortline',
        strategy_name: 'LHB Shortline Combo',
        status: 'runnable',
        description: 'LHB combo',
        factor_groups: ['资金行为'],
        signal_inputs: ['龙虎榜'],
        default_parameters: { top_n: 20 },
        latest_evidence: 'Top5/20%/10bps 净值约 2.6069，最大回撤约 -5.32%。',
        latest_metrics: {
          as_of_date: '2026-06-08',
          total_return_pct: 160.7,
          max_drawdown_pct: -5.3,
          latest_day_return_pct: 1.2,
          latest_day_drawdown_pct: -0.4,
          strategy_version: 'lhb_v1_stable_safe_top5',
          selection_policy: 'original_topn_then_eligibility_no_refill',
          cash_slot_count: 9,
          contract_status: 'success',
          contract_id: 'lhb_shortline:balanced:auction_enhanced_rerank:balanced',
          publish_id: 'lhb-shortline-20260608',
          identity_schema_version: 'strategy_publication_identity_v1',
          config_fingerprint: 'lhb-fingerprint',
          publication_policy: {
            strategy_version: 'lhb_v1_stable_safe_top5',
            selection_policy: 'phase18c_top5_then_eligibility_no_refill',
            market_regime_policy: 'disabled_for_stable_strategy'
          },
          artifact_version: 'strategy_artifact_v1',
          publication_manifest_path:
            '/srv/outputs/research/strategy_daily_eod/2026-06-08/strategy_runs/lhb_shortline/publish-1/publication_manifest.json',
          performance_as_of_date: '2026-06-08',
          signal_status: 'no_position_rows',
          signal_count: null
        },
        primary_action: 'Run backtest'
      },
      {
        strategy_id: 'mid_trend',
        strategy_name: 'Mid Trend Combo',
        status: 'runnable',
        description: 'Mid trend combo',
        factor_groups: ['趋势强度'],
        signal_inputs: ['趋势'],
        default_parameters: { top_n: 5 },
        latest_evidence: '2026区间净值 1.5599，最大回撤 -17.52%。',
        latest_metrics: {
          as_of_date: '2026-06-02',
          total_return_pct: 56.0,
          max_drawdown_pct: -17.5,
          latest_day_return_pct: -2.1,
          latest_day_drawdown_pct: -2.7,
          contract_status: 'success',
          contract_id: 'mid_trend:balanced:top5_weekly_max2_selective_trend_holding_protection_v1',
          publish_id: 'mid-trend-20260602',
          identity_schema_version: 'strategy_publication_identity_v1',
          config_fingerprint: 'mid-fingerprint',
          publication_policy: {
            benchmark_variant: 'top5_weekly_max2_selective_trend_holding_protection_v1'
          },
          artifact_version: 'strategy_artifact_v1',
          publication_manifest_path:
            '/srv/outputs/research/strategy_daily_eod/2026-06-02/strategy_runs/mid_trend/publish-1/publication_manifest.json',
          performance_as_of_date: '2026-06-02',
          signal_status: 'connected',
          signal_count: 5
        },
        primary_action: 'Run backtest'
      },
      {
        strategy_id: 'tech_bottleneck',
        strategy_name: 'Tech Bottleneck Combo',
        status: 'runnable',
        description: 'Tech bottleneck combo',
        factor_groups: ['技术形态'],
        signal_inputs: ['技术'],
        default_parameters: { top_n: 5 },
        latest_evidence: '2026-01-01 至 2026-06-08 净值约 1.6007，最大回撤约 -8.30%。',
        latest_metrics: {
          as_of_date: '2026-06-08',
          total_return_pct: 60.1,
          max_drawdown_pct: -8.3,
          latest_day_return_pct: 0.8,
          latest_day_drawdown_pct: -0.5,
          contract_status: 'success',
          contract_id: 'tech_bottleneck:balanced:strict_153_st_only_financial_state:biweekly:rank_exit_top10_1d',
          publish_id: 'tech-bottleneck-20260608',
          identity_schema_version: 'strategy_publication_identity_v1',
          config_fingerprint: 'tech-fingerprint',
          publication_policy: {
            universe: 'strict_153_st_only_financial_state',
            frequency: 'biweekly',
            protection_name: 'rank_exit_top10_1d'
          },
          artifact_version: 'strategy_artifact_v1',
          publication_manifest_path:
            '/srv/outputs/research/strategy_daily_eod/2026-06-08/strategy_runs/tech_bottleneck/publish-1/publication_manifest.json',
          performance_as_of_date: '2026-06-08',
          signal_status: 'connected',
          signal_count: 5
        },
        primary_action: 'Run backtest'
      }
    ]);
    vi.mocked(api.fetchOverview).mockResolvedValue({
      trade_date: '2026-06-08',
      score_version: 'manual_v1',
      watchlist_id: 'default',
      top_scores: [],
      watchlist_signals: [],
      reports: [
        {
          report_type: 'daily',
          title: 'Daily Market Review',
          path: '/reports/daily-market-review.md',
          format: 'markdown',
          trade_date: '2026-06-08'
        }
      ]
    });
    vi.mocked(api.fetchAssetProfile).mockResolvedValue({
      asset_id: '000001.SZ',
      canonical_asset_id: 'CN:SZ:000001',
      asset: {
        asset_id: '000001.SZ',
        symbol: '000001',
        name: '平安银行',
        exchange: 'SZ',
        board: 'main',
        is_active: true
      },
      bars: [],
      score: null,
      signals: [],
      decisions: [],
      outcomes: [],
      factor_values: [],
      coverage: {}
    });
    vi.mocked(api.fetchMarketMonitorEod).mockResolvedValue({
      trade_date: '2026-06-10',
      freshness: { mode: 'eod', label: 'Last Completed Trading Day', is_realtime: false },
      coverage: { market_assets: 5300, score_assets: 3100, factor_count: 42 },
      market_breadth: {
        advancers: null,
        decliners: null,
        limit_up: null,
        limit_down: null,
        advancing_ratio: null,
        turnover_change_pct: null,
        status: 'pending_source'
      },
      index_snapshot: [],
      sector_strength: { strongest: [], weakest: [], status: 'pending_source' },
      unusual_moves: [],
      watchlist_alerts: [],
      strategy_signal_summary: { topn_preview_count: 0, topn_preview: [], risk_filter_counts: {} },
      generated_reports: [],
      market_emotion: {
        summary: {
          score: 73.6,
          state: 'hot',
          risk_state: 'medium',
          style_signal_hint: 'growth_favorable',
          position_budget_hint: 'reduced',
          status: 'available'
        },
        components: [
          { key: 'breadth', label: '涨跌家数', score: 68.2 },
          { key: 'limit', label: '涨停表现', score: 75.4 },
          { key: 'relay', label: '连板接力', score: 71.1 },
          { key: 'feedback', label: '赚钱效应', score: 66.8 },
          { key: 'liquidity', label: '市场量能', score: 82.0 }
        ],
        breadth: {
          traded_count: 5207,
          up_count: 3610,
          down_count: 1492,
          strong_up_count: 269,
          strong_down_count: 55,
          status: 'available'
        },
        liquidity: { total_amount: 1280000000000, amount_ratio_5_20: 1.18, status: 'available' },
        limit_performance: {
          limit_up_count: 90,
          limit_down_count: 10,
          broken_limit_up_count: 55,
          broken_limit_up_rate: 0.3793,
          first_board_count: 58,
          second_board_count: 21,
          third_board_plus_count: 11,
          high_board_height: 6,
          status: 'available'
        },
        profit_effect: {
          limit_up_success_rate: 0.7361,
          limit_up_profit_rate: 0.026,
          limit_up_limit_down_rate: 0.026,
          relay_profit_rate: 0.018,
          relay_success_rate: 0.615,
          relay_continue_rate: 0.312,
          broken_profit_rate: 0.007,
          broken_success_rate: 0.564,
          broken_limit_down_rate: 0.073,
          status: 'available'
        },
        drawdown_pressure: {
          strong_down_count: 55,
          limit_down_count: 10,
          broken_limit_up_rate: 0.3793,
          yesterday_limit_up_limit_down_rate: 0.026,
          status: 'available'
        },
        weight_performance: { status: 'pending_source' }
      },
      emotion_stock_lists: {
        auction_status: 'pending_source',
        auction: [],
        limit_up: [
          {
            name: '金钼股份',
            asset_id: 'CN:SH:601958',
            symbol: '601958',
            amount: 3038000000,
            pct_chg: 10,
            board: '金属钼',
            tab: 'limit_up',
            limit_up_streak: 1
          }
        ],
        broken_limit_up: [],
        limit_down: []
      },
      warnings: []
    });
    vi.mocked(api.fetchPublicNews).mockResolvedValue({
      items: [
        {
          news_id: 'news-home',
          source: 'sina_finance',
          source_channel: '7x24',
          category: 'live',
          title: '首页快讯',
          summary: '',
          url: '',
          published_at: '2026-06-11 10:00:00',
          collected_at: '2026-06-11T02:00:00Z',
          raw_id: '',
          raw_payload: {},
          status: 'available'
        }
      ],
      warnings: []
    });
    vi.mocked(api.fetchEvidenceDigest).mockResolvedValue({
      asset_id: 'CN:SZ:300951',
      canonical_asset_id: 'CN:SZ:300951',
      trade_date: '2026-06-08',
      title: 'Strong evidence',
      score: 81,
      bucket: 'strong',
      facts: [],
      risk_flags: [],
      source_refs: {},
      next_actions: [],
      warnings: []
    });
    vi.mocked(api.fetchResearchCases).mockResolvedValue({
      items: [
        {
          case_id: 'research_case:alpha',
          trade_date: '2026-06-12',
          asset_id: 'CN:SZ:000001',
          theme: 'bank_reversal',
          title: 'Bank reversal candidate',
          status: 'open',
          priority: 20,
          source_type: 'review_item_snapshot',
          source_id: 'review_item_snapshot:alpha',
          evidence_status: 'partial',
          missing_evidence_count: 1,
          partial_evidence_count: 0,
          evidence_count: 0,
          claim_count: 2
        },
        {
          case_id: 'research_case:beta',
          trade_date: '2026-06-12',
          asset_id: 'CN:SH:600001',
          theme: 'industry_rotation',
          title: 'Industry rotation follow-up',
          status: 'open',
          priority: 35,
          source_type: 'review_item_snapshot',
          source_id: 'review_item_snapshot:beta',
          evidence_status: 'complete',
          missing_evidence_count: 0,
          partial_evidence_count: 0,
          evidence_count: 3,
          claim_count: 1
        }
      ]
    });
    vi.mocked(api.fetchResearchEvidence).mockResolvedValue({
      items: [
        {
          evidence_id: 'evidence_artifact:evidence_digest_snapshot:abc',
          source_type: 'evidence_digest_snapshot',
          source_id: 'evidence_digest_snapshot:abc',
          asset_id: 'CN:SH:600001',
          trade_date: '2026-06-12',
          title: 'Evidence snapshot',
          uri: '',
          content_hash: 'hash123',
          allowed_metadata: { digest_key: 'digest:1' }
        }
      ]
    });
    vi.mocked(api.fetchResearchCaseDetail).mockResolvedValue({
      case: {
        case_id: 'research_case:alpha',
        trade_date: '2026-06-12',
        asset_id: 'CN:SZ:000001',
        theme: 'bank_reversal',
        title: 'Bank reversal candidate',
        status: 'open',
        priority: 20,
        source_type: 'review_item_snapshot',
        source_id: 'review_item_snapshot:alpha'
      },
      claims: [
        {
          claim_id: 'research_claim:1',
          claim_type: 'risk',
          claim_text: 'evidence_status=partial, missing=1, partial=0',
          confidence: null,
          status: 'draft',
          source_type: 'review_item_snapshot',
          source_id: 'review_item_snapshot:alpha'
        }
      ],
      evidence: [
        {
          evidence_id: 'evidence_artifact:1',
          source_type: 'review_item_snapshot',
          source_id: 'review_item_snapshot:alpha',
          asset_id: 'CN:SZ:000001',
          trade_date: '2026-06-12',
          title: 'Review snapshot evidence',
          uri: '',
          content_hash: 'hash123',
          relation: 'supports',
          target_type: 'research_case',
          target_id: 'research_case:alpha',
          allowed_metadata: { digest_key: 'digest:1', seed_version: 'research_case_seed_v1' }
        }
      ],
      summary: {
        claim_count: 1,
        evidence_count: 1,
        missing_or_partial_evidence_count: 1,
        evidence_status: 'partial',
        missing_evidence_count: 1,
        partial_evidence_count: 0
      },
      gap_reasons: ['missing_evidence', 'incomplete_evidence_status'],
      gap_summary: 'missing evidence signal found; evidence status is partial',
      review_status: 'pending',
      latest_review_action: null,
      review_actions: []
    });
    vi.mocked(api.createResearchReviewAction).mockResolvedValue({
      review_action_id: 'review_action:new',
      status: 'recorded'
    });
    vi.mocked(api.fetchResearchQueueHealth).mockResolvedValue({
      trade_date: '2026-06-12',
      status: 'partial',
      can_review: true,
      can_publish_research_queue: false,
      publish_gate_status: 'blocked',
      research_ready_for_publication: false,
      actual_publish_enabled: false,
      internal_snapshot_enabled: false,
      external_delivery_enabled: false,
      summary: {
        case_count: 2,
        open_case_count: 2,
        claim_count: 3,
        evidence_artifact_count: 4,
        evidence_link_count: 5,
        evidence_gap_count: 1,
        unmatched_digest_count: 0,
        error_count: 0,
        no_evidence_count: 0,
        missing_evidence_count: 1,
        partial_evidence_count: 0,
        incomplete_evidence_status_count: 1,
        unknown_gap_count: 0
      },
      top_gap_cases: [
        {
          case_id: 'research_case:alpha',
          trade_date: '2026-06-12',
          asset_id: 'CN:SZ:000001',
          theme: 'bank_reversal',
          title: 'Bank reversal candidate',
          status: 'open',
          priority: 20,
          evidence_count: 0,
          claim_count: 2,
          gap_reasons: ['missing_evidence', 'incomplete_evidence_status'],
          gap_summary: 'missing evidence signal found; evidence status is partial',
          review_status: 'pending',
          latest_review_action: null,
          source_type: 'review_item_snapshot',
          source_id: 'review_item_snapshot:alpha'
        }
      ],
      last_refresh: {
        run_id: 'research_queue_refresh:1',
        finished_at: '2026-06-12T02:00:00.257014+00:00',
        manifest_path: 'outputs/research/research_queue_refresh_v1/2026-06-12/research_queue_refresh_manifest.json'
      },
      warnings: ['evidence_gap_count=1']
    });
    vi.mocked(api.fetchResearchPublishGate).mockResolvedValue({
      trade_date: '2026-06-12',
      status: 'blocked',
      research_ready_for_publication: false,
      actual_publish_enabled: false,
      internal_snapshot_enabled: false,
      external_delivery_enabled: false,
      publication_entrypoint_status: 'scaffolded',
      summary: {
        case_count: 2,
        open_case_count: 2,
        claim_count: 3,
        evidence_artifact_count: 4,
        evidence_link_count: 5,
        evidence_gap_count: 1,
        pending_gap_count: 1,
        reviewed_gap_count: 0,
        request_more_evidence_count: 0,
        deferred_gap_count: 0,
        unmatched_digest_count: 0,
        error_count: 0
      },
      blockers: [
        { code: 'pending_gap', message: '1 gap case has not been reviewed', count: 1 },
        {
          code: 'external_delivery_not_connected',
          message: 'External research delivery is not connected',
          count: 1
        }
      ],
      warnings: [],
      top_blocked_cases: [
        {
          case_id: 'research_case:alpha',
          trade_date: '2026-06-12',
          asset_id: 'CN:SZ:000001',
          theme: 'bank_reversal',
          title: 'Bank reversal candidate',
          review_status: 'pending',
          gap_reasons: ['missing_evidence', 'incomplete_evidence_status'],
          gap_summary: 'missing evidence signal found; evidence status is partial'
        }
      ]
    });
    vi.mocked(api.fetchResearchPublicationPreview).mockResolvedValue({
      trade_date: '2026-06-12',
      package_id: 'research_publication_package:alpha',
      publishable: false,
      actual_publish_enabled: false,
      internal_snapshot_enabled: false,
      external_delivery_enabled: false,
      gate: {
        status: 'blocked',
        research_ready_for_publication: false,
        actual_publish_enabled: false,
        internal_snapshot_enabled: false,
        external_delivery_enabled: false
      },
      summary: {
        case_count: 2,
        claim_count: 3,
        evidence_count: 4,
        evidence_link_count: 5,
        gap_count: 1,
        reviewed_gap_count: 0,
        pending_gap_count: 1,
        request_more_evidence_count: 0,
        deferred_gap_count: 0,
        unmatched_digest_count: 0,
        error_count: 0
      },
      sections: [
        {
          section_type: 'blocked_cases',
          title: '发布阻塞项',
          items: [
            {
              case_id: 'research_case:alpha',
              trade_date: '2026-06-12',
              asset_id: 'CN:SZ:000001',
              theme: 'bank_reversal',
              title: 'Bank reversal candidate',
              review_status: 'pending',
              gap_reasons: ['missing_evidence'],
              gap_summary: 'missing evidence signal found'
            }
          ]
        }
      ],
      warnings: [],
      blockers: [{ code: 'pending_gap', message: '1 gap case has not been reviewed', count: 1 }]
    });
    vi.mocked(api.fetchResearchPublicationSnapshots).mockResolvedValue({ items: [] });
    vi.mocked(api.fetchResearchExternalDeliveryPlan).mockResolvedValue({
      delivery_plan_id: 'research_external_delivery_plan:abc',
      publication_snapshot_id: 'publication_snapshot:research_queue_internal:abc',
      trade_date: '2026-06-12',
      channel: 'feishu_preview',
      dry_run: true,
      external_send_enabled: false,
      status: 'preview_ready',
      message: {
        title: 'Research Queue Snapshot 2026-06-12',
        summary: 'Cases 2, claims 3, evidence 4, gaps 0. Gate research_ready.',
        sections: [{ section_type: 'research_queue_summary', title: '研究队列摘要', items: [] }]
      },
      source: {
        package_id: 'research_publication_package:abc',
        gate_status: 'research_ready',
        snapshot_channel: 'research_queue_internal'
      },
      blockers: [],
      warnings: ['External delivery is not connected in this version.']
    });
    vi.mocked(api.fetchResearchExternalDeliveryAttempts).mockResolvedValue({ items: [] });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('renders a strategy-centered command center', async () => {
    render(<AppShell />);

    expect(await screen.findByText('策略指挥中心')).toBeVisible();
    expect(screen.getByText('启用策略表现')).toBeVisible();
    expect(screen.getByText('今日研究队列')).toBeVisible();
    expect(screen.getByText('策略持仓状态')).toBeVisible();
    expect(screen.getByText('市场环境')).toBeVisible();
    expect(screen.getByText('高质量新闻')).toBeVisible();
    expect(within(screen.getByRole('region', { name: '首页状态' })).getByText('部分可用')).toBeVisible();
    expect(screen.getByText('生成报告不可用')).toBeVisible();
    expect(screen.queryByText('Strategy Health')).not.toBeInTheDocument();
    expect(screen.queryByText('Market Pulse')).not.toBeInTheDocument();
    expect(screen.queryByText('Today Focus')).not.toBeInTheDocument();
    expect(screen.queryByText('Today Actions')).not.toBeInTheDocument();
    expect(screen.queryByText('CN:SZ:300951')).not.toBeInTheDocument();

    const healthCheckRegion = screen.getByRole('region', { name: '平台健康检查' });
    expect(healthCheckRegion).toHaveClass('collapsible-panel');
    const healthCheck = within(healthCheckRegion);
    expect(healthCheck.getByRole('button', { name: '展开' })).toHaveAttribute('aria-expanded', 'false');
    expect(healthCheck.queryByText('Market data')).not.toBeInTheDocument();
    fireEvent.click(healthCheck.getByRole('button', { name: '展开' }));
    expect(healthCheck.getByRole('button', { name: '收起' })).toHaveAttribute('aria-expanded', 'true');
    expect(healthCheck.getByText('Market data')).toBeVisible();
    fireEvent.click(healthCheck.getByRole('button', { name: '收起' }));
    expect(healthCheck.getByRole('button', { name: '展开' })).toHaveAttribute('aria-expanded', 'false');

    const strategyPerformance = within(screen.getByRole('region', { name: '启用策略表现' }));
    expect(strategyPerformance.getByText('LHB Shortline Combo')).toBeVisible();
    expect(strategyPerformance.getByText('LHB V1 Stable Safe Top5')).toBeVisible();
    expect(strategyPerformance.getByText('+160.70%')).toBeVisible();
    expect(strategyPerformance.getByText('-5.3%')).toBeVisible();
    expect(strategyPerformance.getByText('+1.2%')).toBeVisible();
    expect(strategyPerformance.getAllByText('正常')).toHaveLength(2);
    expect(strategyPerformance.getByText('Mid Trend Combo')).toBeVisible();
    expect(strategyPerformance.getByText('+56.00%')).toBeVisible();
    expect(strategyPerformance.getByText('-17.5%')).toBeVisible();
    expect(strategyPerformance.getByText('-2.1%')).toBeVisible();
    expect(strategyPerformance.getByText('复盘')).toBeVisible();
    expect(strategyPerformance.getByText('Tech Bottleneck Combo')).toBeVisible();
    expect(strategyPerformance.getByText('+60.10%')).toBeVisible();
    expect(strategyPerformance.getByText('-8.3%')).toBeVisible();
    expect(strategyPerformance.getByText('+0.8%')).toBeVisible();
    expect(strategyPerformance.getByText('持仓明细暂无')).toBeVisible();
    expect(strategyPerformance.getAllByText('最新持仓 5')).toHaveLength(2);
    expect(strategyPerformance.getAllByTestId('strategy-performance-date').filter((node) => node.textContent === '2026-06-08')).toHaveLength(2);
    expect(
      within(strategyPerformance.getByText('LHB Shortline Combo').closest('article')!).getByTestId('strategy-publish-id')
    ).toHaveTextContent('lhb-shortline-20260608');

    await screen.findByText('策略指挥中心');
    const researchQueueRegion = screen.getByRole('region', { name: '今日研究队列' });
    expect(researchQueueRegion).toHaveClass('collapsible-panel');
    const researchQueue = within(researchQueueRegion);
    expect(researchQueue.getByRole('button', { name: '展开' })).toHaveAttribute('aria-expanded', 'false');
    expect(researchQueue.getByText('今日有 2 个待审案例，1 个证据缺口，2 个发布阻塞。')).toBeVisible();
    expect(researchQueue.getByText('先处理证据缺口，再处理发布保护。')).toBeVisible();
    expect(researchQueue.getByText('最近刷新 2026-06-12 10:00')).toBeVisible();
    expect(researchQueue.queryByText('Open Cases')).not.toBeInTheDocument();
    expect(researchQueue.queryByText('Evidence Gaps')).not.toBeInTheDocument();
    expect(researchQueue.queryByText('Publication Blocks')).not.toBeInTheDocument();
    expect(researchQueue.queryByText('Last Refresh')).not.toBeInTheDocument();
    expect(researchQueue.queryByText('2026-06-12T02:00:00.257014+00:00')).not.toBeInTheDocument();
    expect(researchQueue.queryByText('Bank reversal candidate')).not.toBeInTheDocument();

    fireEvent.click(researchQueue.getByRole('button', { name: '展开' }));

    expect(researchQueue.getByRole('button', { name: '收起' })).toHaveAttribute('aria-expanded', 'true');
    expect(researchQueue.getByText('Open Cases')).toBeVisible();
    expect(researchQueue.getByText('Evidence Gaps')).toBeVisible();
    expect(researchQueue.getByText('Publication Blocks')).toBeVisible();
    expect(researchQueue.getByText('partial')).toBeVisible();
    expect(researchQueue.getByText('Last Refresh')).toBeVisible();
    expect(researchQueue.getByText('2026-06-12 10:00')).toBeVisible();
    expect(researchQueue.queryByText('2026-06-12T02:00:00.257014+00:00')).not.toBeInTheDocument();
    expect(researchQueue.getByText('Claims')).toBeVisible();
    expect(researchQueue.getByText('3')).toBeVisible();
    expect(researchQueue.getByText('Links')).toBeVisible();
    expect(researchQueue.getByText('5')).toBeVisible();
    expect(researchQueue.getByText('外部发送未接入')).toBeVisible();
    expect(researchQueue.getByText('研究发布检查')).toBeVisible();
    expect(researchQueue.getByText('研究发布检查未通过')).toBeVisible();
    expect(researchQueue.getByText('外部发送入口未接入')).toBeVisible();
    expect(researchQueue.getByText('内部发布快照')).toBeVisible();
    expect(researchQueue.getByText('暂无内部发布快照')).toBeVisible();
    expect(researchQueue.getByText('1 gap case has not been reviewed')).toBeVisible();
    expect(researchQueue.getByText('待处理证据缺口')).toBeVisible();
    expect(researchQueue.getAllByText('缺少 evidence / evidence 未完成')[0]).toBeVisible();
    expect(researchQueue.getAllByText('Bank reversal candidate')[0]).toBeVisible();
    expect(researchQueue.getAllByText('CN:SZ:000001')[0]).toBeVisible();
    expect(researchQueue.getAllByText('bank_reversal')[0]).toBeVisible();
    expect(researchQueue.getAllByText('0 evidence / 2 claims')[0]).toBeVisible();
    expect(researchQueue.getByText('Industry rotation follow-up')).toBeVisible();
    expect(researchQueue.getByText('3 evidence / 1 claims')).toBeVisible();
    expect(api.fetchResearchCases).toHaveBeenCalledWith(
      expect.objectContaining({ tradeDate: '2026-06-12', status: 'open', limit: 100 })
    );
    expect(api.fetchResearchEvidence).toHaveBeenCalledWith(
      expect.objectContaining({ limit: 100 })
    );
    expect(api.fetchResearchQueueHealth).toHaveBeenCalledWith(
      expect.objectContaining({ tradeDate: '2026-06-12' })
    );
    expect(api.fetchResearchPublishGate).toHaveBeenCalledWith(
      expect.objectContaining({ tradeDate: '2026-06-12' })
    );
    expect(api.fetchResearchPublicationSnapshots).toHaveBeenCalledWith(
      expect.objectContaining({ tradeDate: '2026-06-12', limit: 5 })
    );

    const marketRegime = within(screen.getByRole('region', { name: '市场环境' }));
    expect(marketRegime.getByText('73.6')).toBeVisible();
    expect(marketRegime.getByText('偏热')).toBeVisible();
    expect(marketRegime.getByText('涨跌家数')).toBeVisible();
    expect(marketRegime.getByText('3,610 / 1,492')).toBeVisible();
    expect(marketRegime.getByText(/强涨 269，强跌 55/)).toBeVisible();
    expect(marketRegime.getByText('涨停 / 跌停')).toBeVisible();
    expect(marketRegime.getByText('90 / 10')).toBeVisible();
    expect(marketRegime.getAllByText(/炸板 55，炸板率 37.9%/).length).toBeGreaterThan(0);
    expect(marketRegime.getByText('首板 / 二板')).toBeVisible();
    expect(marketRegime.getByText('58 / 21')).toBeVisible();
    expect(marketRegime.getByText('三板以上 / 高度')).toBeVisible();
    expect(marketRegime.getByText('11 / 6')).toBeVisible();
    expect(marketRegime.getByText('连板数量')).toBeVisible();
    expect(marketRegime.getByText('二板数量')).toBeVisible();
    expect(marketRegime.getByText('三板以上')).toBeVisible();
    expect(marketRegime.getByText('金钼股份')).toBeVisible();
    expect(marketRegime.getAllByText('股票列表未接入')).toHaveLength(1);
    expect(marketRegime.getByText('涨跌广度评分')).toBeVisible();
    expect(marketRegime.getByText('权重 25%：上涨/下跌比例 + 强涨/强跌比例')).toBeVisible();
    expect(marketRegime.getByText('涨停表现评分')).toBeVisible();
    expect(marketRegime.getByText('连板接力评分')).toBeVisible();
    expect(marketRegime.getByText('权重 25%：涨停数量加分，跌停和炸板率扣分')).toBeVisible();
    expect(marketRegime.getByText('权重 20%：最高连板高度 + 二板以上占涨停比例')).toBeVisible();
    expect(marketRegime.getByText('赚钱效应评分')).toBeVisible();
    expect(marketRegime.getByText('66.8 分')).toBeVisible();
    expect(marketRegime.getByText(/情绪偏强但需要看炸板压力/)).toBeVisible();

    const strategySignals = within(screen.getByRole('region', { name: '策略持仓状态' }));
    expect(strategySignals.getByText('LHB Shortline Combo')).toBeVisible();
    expect(strategySignals.getByText('Mid Trend Combo')).toBeVisible();
    expect(strategySignals.getByText('Tech Bottleneck Combo')).toBeVisible();
    expect(strategySignals.getByText('持仓明细暂无')).toBeVisible();
    expect(strategySignals.getAllByText('最新持仓 5')).toHaveLength(2);
    expect(strategySignals.getByText('非买卖建议')).toBeVisible();
    expect(strategySignals.getByText(/最新回测持仓数量/)).toBeVisible();

    const qualityNews = within(screen.getByRole('region', { name: '高质量新闻' }));
    expect(qualityNews.getByText('首页快讯')).toBeVisible();
    expect(qualityNews.getByText('1')).toBeVisible();
    expect(screen.queryByText('Manual V1 TopN Rotation')).not.toBeInTheDocument();
    expect(api.fetchEvidenceDigest).not.toHaveBeenCalled();
    expect(api.fetchPublicNews).toHaveBeenCalledWith(
      expect.objectContaining({ limit: 5, minQualityScore: 65 })
    );
    expect(screen.queryByRole('navigation', { name: 'Quick actions' })).not.toBeInTheDocument();
  });

  it('opens a research case detail panel from the research queue', async () => {
    render(<AppShell />);

    await screen.findByText('策略指挥中心');
    const researchQueue = within(await screen.findByRole('region', { name: '今日研究队列' }));
    fireEvent.click(researchQueue.getByRole('button', { name: '展开' }));
    fireEvent.click(researchQueue.getAllByRole('button', { name: /审阅/ })[0]);

    const detail = within(await screen.findByRole('region', { name: '研究案例详情' }));
    expect(detail.getByText('Bank reversal candidate')).toBeVisible();
    expect(detail.getByText('review_item_snapshot')).toBeVisible();
    expect(detail.getByText('review_item_snapshot:alpha')).toBeVisible();
    expect(detail.getByText('缺少 evidence / evidence 未完成')).toBeVisible();
    expect(detail.getByText('evidence_status=partial, missing=1, partial=0')).toBeVisible();
    expect(detail.getByText('Review snapshot evidence')).toBeVisible();
    expect(detail.getByText('supports · research_case')).toBeVisible();
    expect(detail.getByText('人工审阅动作')).toBeVisible();
    expect(detail.getByText('当前状态')).toBeVisible();
    expect(detail.getAllByText('待处理')[0]).toBeVisible();
    expect(detail.getByRole('button', { name: '需要补充证据' })).toBeVisible();
    expect(api.fetchResearchCaseDetail).toHaveBeenCalledWith('research_case:alpha');
  });

  it('records a research review action and refreshes detail and health', async () => {
    render(<AppShell />);

    await screen.findByText('策略指挥中心');
    const researchQueue = within(await screen.findByRole('region', { name: '今日研究队列' }));
    fireEvent.click(researchQueue.getByRole('button', { name: '展开' }));
    fireEvent.click(researchQueue.getAllByRole('button', { name: /审阅/ })[0]);

    const detail = within(await screen.findByRole('region', { name: '研究案例详情' }));
    fireEvent.change(detail.getByLabelText('审阅备注'), { target: { value: '需要补充公告证据' } });
    fireEvent.click(detail.getByRole('button', { name: '需要补充证据' }));

    await waitFor(() => {
      expect(api.createResearchReviewAction).toHaveBeenCalledWith(
        expect.objectContaining({
          case_id: 'research_case:alpha',
          trade_date: '2026-06-12',
          asset_id: 'CN:SZ:000001',
          action_type: 'request_more_evidence',
          gap_reasons: ['missing_evidence', 'incomplete_evidence_status'],
          reviewer: 'operator',
          comment: '需要补充公告证据',
          source_context: expect.objectContaining({ from: 'home_cockpit_gap_detail' })
        })
      );
    });
    await waitFor(() => {
      expect(api.fetchResearchCaseDetail).toHaveBeenCalledTimes(2);
      expect(api.fetchResearchQueueHealth).toHaveBeenCalledTimes(2);
      expect(api.fetchResearchPublishGate).toHaveBeenCalledTimes(2);
    });
    expect(researchQueue.getByText('外部发送未接入')).toBeVisible();
  });

  it('shows a dry-run research publication preview without publish actions', async () => {
    render(<AppShell />);

    await screen.findByText('策略指挥中心');
    const researchQueue = within(await screen.findByRole('region', { name: '今日研究队列' }));
    fireEvent.click(researchQueue.getByRole('button', { name: '展开' }));
    fireEvent.click(await researchQueue.findByRole('button', { name: '查看发布预览' }));

    const preview = within(await researchQueue.findByLabelText('发布预览'));
    expect(preview.getByText('发布预览')).toBeVisible();
    expect(preview.getByText('预览，不是发布')).toBeVisible();
    expect(preview.getByText('publishable=false')).toBeVisible();
    expect(preview.getByText('research_publication_package:alpha')).toBeVisible();
    expect(preview.getByText('Gate 未通过，不能记录')).toBeVisible();
    expect(preview.getByText('外部发送入口未接入')).toBeVisible();
    expect(preview.getByText('1 gap case has not been reviewed')).toBeVisible();
    expect(api.fetchResearchPublicationPreview).toHaveBeenCalledWith(
      expect.objectContaining({ tradeDate: '2026-06-12' })
    );
    expect(researchQueue.queryByRole('button', { name: '立即发布' })).not.toBeInTheDocument();
    expect(researchQueue.queryByRole('button', { name: '发送飞书' })).not.toBeInTheDocument();
    expect(researchQueue.queryByRole('button', { name: '写入 publication snapshot' })).not.toBeInTheDocument();
  });

  it('shows latest internal publication snapshot summary without external publish wording', async () => {
    vi.mocked(api.fetchResearchPublicationSnapshots).mockResolvedValueOnce({
      items: [
        {
          publication_snapshot_id: 'publication_snapshot:research_queue_internal:abc',
          trade_date: '2026-06-12',
          channel: 'research_queue_internal',
          title: 'Research Queue Internal Snapshot 2026-06-12',
          created_by: 'research_queue_publish',
          created_at: '2026-06-12T03:00:00.000000+00:00',
          package_id: 'research_publication_package:abc',
          gate_status: 'research_ready',
          research_ready_for_publication: true,
          actual_external_delivery_enabled: false,
          case_count: 2,
          claim_count: 3,
          evidence_count: 4,
          gap_count: 0,
          blocker_count: 0
        }
      ]
    });

    render(<AppShell />);

    await screen.findByText('策略指挥中心');
    const researchQueue = within(await screen.findByRole('region', { name: '今日研究队列' }));
    fireEvent.click(researchQueue.getByRole('button', { name: '展开' }));

    expect(await researchQueue.findByText('内部发布快照')).toBeVisible();
    expect(researchQueue.getByText('publication_snapshot:research_queue_internal:abc')).toBeVisible();
    expect(researchQueue.getByText('research_queue_internal')).toBeVisible();
    expect(researchQueue.getByText('research_ready')).toBeVisible();
    expect(researchQueue.getByText('外部发送状态：未接入')).toBeVisible();
    expect(researchQueue.queryByText('外部已发布')).not.toBeInTheDocument();
    expect(researchQueue.queryByRole('button', { name: '立即发布' })).not.toBeInTheDocument();
    expect(researchQueue.queryByRole('button', { name: '发送飞书' })).not.toBeInTheDocument();
  });

  it('shows external delivery dry-run plan when an internal snapshot exists', async () => {
    vi.mocked(api.fetchResearchPublicationSnapshots).mockResolvedValueOnce({
      items: [
        {
          publication_snapshot_id: 'publication_snapshot:research_queue_internal:abc',
          trade_date: '2026-06-12',
          channel: 'research_queue_internal',
          title: 'Research Queue Internal Snapshot 2026-06-12',
          created_by: 'research_queue_publish',
          created_at: '2026-06-12T03:00:00.000000+00:00',
          package_id: 'research_publication_package:abc',
          gate_status: 'research_ready',
          research_ready_for_publication: true,
          actual_external_delivery_enabled: false,
          case_count: 2,
          claim_count: 3,
          evidence_count: 4,
          gap_count: 0,
          blocker_count: 0
        }
      ]
    });

    render(<AppShell />);

    await screen.findByText('策略指挥中心');
    const researchQueue = within(await screen.findByRole('region', { name: '今日研究队列' }));
    fireEvent.click(researchQueue.getByRole('button', { name: '展开' }));

    expect(await researchQueue.findByText('外部发送预案')).toBeVisible();
    expect(researchQueue.getByText('外部发送预案，仅 dry-run')).toBeVisible();
    expect(researchQueue.getByText('feishu_preview')).toBeVisible();
    expect(researchQueue.getByText('Research Queue Snapshot 2026-06-12')).toBeVisible();
    expect(researchQueue.getByText('Cases 2, claims 3, evidence 4, gaps 0. Gate research_ready.')).toBeVisible();
    expect(researchQueue.getByText('External delivery is not connected in this version.')).toBeVisible();
    expect(api.fetchResearchExternalDeliveryPlan).toHaveBeenCalledWith({
      publicationSnapshotId: 'publication_snapshot:research_queue_internal:abc',
      channel: 'feishu_preview'
    });
    expect(researchQueue.getByText('发送尝试账本')).toBeVisible();
    expect(researchQueue.getByText('暂无外部发送尝试记录')).toBeVisible();
    expect(researchQueue.queryByRole('button', { name: '立即推送' })).not.toBeInTheDocument();
    expect(researchQueue.queryByRole('button', { name: '真实发送' })).not.toBeInTheDocument();
    expect(researchQueue.queryByText('已发布到飞书')).not.toBeInTheDocument();
  });

  it('shows latest external delivery dry-run attempt ledger', async () => {
    vi.mocked(api.fetchResearchPublicationSnapshots).mockResolvedValueOnce({
      items: [
        {
          publication_snapshot_id: 'publication_snapshot:research_queue_internal:abc',
          trade_date: '2026-06-12',
          channel: 'research_queue_internal',
          title: 'Research Queue Internal Snapshot 2026-06-12',
          created_by: 'research_queue_publish',
          created_at: '2026-06-12T03:00:00.000000+00:00',
          package_id: 'research_publication_package:abc',
          gate_status: 'research_ready',
          research_ready_for_publication: true,
          actual_external_delivery_enabled: false,
          case_count: 2,
          claim_count: 3,
          evidence_count: 4,
          gap_count: 0,
          blocker_count: 0
        }
      ]
    });
    vi.mocked(api.fetchResearchExternalDeliveryAttempts).mockResolvedValueOnce({
      items: [
        {
          delivery_attempt_id: 'external_delivery_attempt:abc',
          publication_snapshot_id: 'publication_snapshot:research_queue_internal:abc',
          trade_date: '2026-06-12',
          channel: 'feishu_preview',
          mode: 'dry_run',
          status: 'preview_recorded',
          dry_run: true,
          external_send_enabled: false,
          delivery_plan_id: 'research_external_delivery_plan:abc',
          message_title: 'Research Queue Snapshot 2026-06-12',
          created_by: 'operator',
          created_at: '2026-06-12T03:05:00.000000+00:00',
          error_code: '',
          error_message: ''
        }
      ]
    });

    render(<AppShell />);

    await screen.findByText('策略指挥中心');
    const researchQueue = within(await screen.findByRole('region', { name: '今日研究队列' }));
    fireEvent.click(researchQueue.getByRole('button', { name: '展开' }));

    const ledger = within(await researchQueue.findByLabelText('发送尝试账本'));
    expect(ledger.getByText('external_delivery_attempt:abc')).toBeVisible();
    expect(ledger.getByText('preview_recorded')).toBeVisible();
    expect(ledger.getByText('feishu_preview')).toBeVisible();
    expect(ledger.getByText('disabled')).toBeVisible();
    expect(researchQueue.queryByText('delivery success')).not.toBeInTheDocument();
    expect(researchQueue.queryByText('已发送到飞书')).not.toBeInTheDocument();
  });

  it('shows an error when recording a research review action fails', async () => {
    vi.mocked(api.createResearchReviewAction).mockRejectedValueOnce(new Error('write token missing'));

    render(<AppShell />);

    await screen.findByText('策略指挥中心');
    const researchQueue = within(await screen.findByRole('region', { name: '今日研究队列' }));
    fireEvent.click(researchQueue.getByRole('button', { name: '展开' }));
    fireEvent.click(researchQueue.getAllByRole('button', { name: /审阅/ })[0]);

    const detail = within(await screen.findByRole('region', { name: '研究案例详情' }));
    fireEvent.click(detail.getByRole('button', { name: '已知晓缺口' }));

    expect(await screen.findByText(/审阅动作写入失败：write token missing/)).toBeVisible();
  });

  it('does not show gap cases when research queue is healthy', async () => {
    vi.mocked(api.fetchResearchQueueHealth).mockResolvedValueOnce({
      trade_date: '2026-06-12',
      status: 'healthy',
      can_review: true,
      can_publish_research_queue: false,
      publish_gate_status: 'research_ready',
      research_ready_for_publication: true,
      actual_publish_enabled: false,
      internal_snapshot_enabled: true,
      external_delivery_enabled: false,
      summary: {
        case_count: 2,
        open_case_count: 2,
        claim_count: 3,
        evidence_artifact_count: 4,
        evidence_link_count: 5,
        evidence_gap_count: 0,
        unmatched_digest_count: 0,
        error_count: 0,
        no_evidence_count: 0,
        missing_evidence_count: 0,
        partial_evidence_count: 0,
        incomplete_evidence_status_count: 0,
        unknown_gap_count: 0
      },
      top_gap_cases: [],
      last_refresh: null,
      warnings: []
    });
    vi.mocked(api.fetchResearchPublishGate).mockResolvedValueOnce({
      trade_date: '2026-06-12',
      status: 'research_ready',
      research_ready_for_publication: true,
      actual_publish_enabled: false,
      internal_snapshot_enabled: true,
      external_delivery_enabled: false,
      publication_entrypoint_status: 'scaffolded',
      summary: {
        case_count: 2,
        open_case_count: 2,
        claim_count: 3,
        evidence_artifact_count: 4,
        evidence_link_count: 5,
        evidence_gap_count: 0,
        pending_gap_count: 0,
        reviewed_gap_count: 0,
        request_more_evidence_count: 0,
        deferred_gap_count: 0,
        unmatched_digest_count: 0,
        error_count: 0
      },
      blockers: [],
      warnings: [
        {
          code: 'external_delivery_not_connected',
          message: 'External research delivery is not connected',
          count: 1
        }
      ],
      top_blocked_cases: []
    });

    render(<AppShell />);

    await screen.findByText('策略指挥中心');
    const researchQueue = within(screen.getByRole('region', { name: '今日研究队列' }));
    fireEvent.click(researchQueue.getByRole('button', { name: '展开' }));
    expect(await researchQueue.findByText('研究审阅已通过，可记录内部快照；外部发送未接入')).toBeVisible();
    expect(researchQueue.queryByText('待处理证据缺口')).not.toBeInTheDocument();
    expect(researchQueue.queryByText('真实可发布')).not.toBeInTheDocument();
  });

  it('shows empty research publish gate without reporting blockers', async () => {
    vi.mocked(api.fetchResearchCases).mockResolvedValueOnce({ items: [] });
    vi.mocked(api.fetchResearchQueueHealth).mockResolvedValueOnce({
      trade_date: '2026-06-12',
      status: 'empty',
      can_review: false,
      can_publish_research_queue: false,
      publish_gate_status: 'empty',
      research_ready_for_publication: false,
      actual_publish_enabled: false,
      internal_snapshot_enabled: false,
      external_delivery_enabled: false,
      summary: {
        case_count: 0,
        open_case_count: 0,
        claim_count: 0,
        evidence_artifact_count: 0,
        evidence_link_count: 0,
        evidence_gap_count: 0,
        unmatched_digest_count: 0,
        error_count: 0
      },
      top_gap_cases: [],
      last_refresh: null,
      warnings: []
    });
    vi.mocked(api.fetchResearchPublishGate).mockResolvedValueOnce({
      trade_date: '2026-06-12',
      status: 'empty',
      research_ready_for_publication: false,
      actual_publish_enabled: false,
      internal_snapshot_enabled: false,
      external_delivery_enabled: false,
      publication_entrypoint_status: 'scaffolded',
      summary: {
        case_count: 0,
        open_case_count: 0,
        claim_count: 0,
        evidence_artifact_count: 0,
        evidence_link_count: 0,
        evidence_gap_count: 0,
        pending_gap_count: 0,
        reviewed_gap_count: 0,
        request_more_evidence_count: 0,
        deferred_gap_count: 0,
        unmatched_digest_count: 0,
        error_count: 0
      },
      blockers: [],
      warnings: [],
      top_blocked_cases: []
    });

    render(<AppShell />);

    await screen.findByText('策略指挥中心');
    const researchQueue = within(screen.getByRole('region', { name: '今日研究队列' }));
    fireEvent.click(researchQueue.getByRole('button', { name: '展开' }));

    expect(await researchQueue.findByText('无研究队列，无法执行研究发布检查')).toBeVisible();
    expect(researchQueue.queryByText('待处理证据缺口')).not.toBeInTheDocument();
  });

  it('keeps core cockpit content when platform readiness fails', async () => {
    vi.mocked(api.fetchPlatformReadiness).mockRejectedValueOnce(new Error('readiness unavailable'));

    render(<AppShell />);

    expect(await screen.findByRole('heading', { name: '策略指挥中心' })).toBeVisible();
    expect(screen.getByText('平台就绪状态不可用：readiness unavailable')).toBeVisible();
    expect(screen.getByText('策略持仓状态')).toBeVisible();
    expect(screen.getByText('市场环境')).toBeVisible();
  });

  it('surfaces degraded readiness as dashboard-available and publication-ready with warnings', async () => {
    vi.mocked(api.fetchPlatformReadiness).mockResolvedValueOnce({
      mode: 'eod_local',
      status: 'PARTIAL',
      as_of: '2026-06-30T21:30:00+08:00',
      latest_market_date: '2026-06-30',
      latest_trade_date: '2026-06-30',
      display_trade_date: '2026-06-30',
      candidate_trade_date: '2026-06-30',
      checks: [],
      health_groups: [],
      warnings: ['pipeline_status=DEGRADED_READY'],
      policy: {
        status: 'degraded_ready',
        ready_for_dashboard: true,
        ready_for_publication: true,
        blocking_reasons: [],
        warnings: [
          'pipeline_status=DEGRADED_READY',
          'partial_data=daily_status=partial_success',
          'partial_data=minute5_status=partial_success'
        ]
      }
    });

    render(<AppShell />);

    expect(await screen.findByRole('heading', { name: '策略指挥中心' })).toBeVisible();
    const homeStatus = within(screen.getByRole('region', { name: '首页状态' }));
    expect(homeStatus.getByText('可查看')).toBeVisible();
    expect(homeStatus.getByText('可发布')).toBeVisible();
    const policyPanel = within(screen.getByRole('region', { name: '平台发布保护' }));
    expect(policyPanel.getByText('可发布')).toBeVisible();
    expect(policyPanel.getByText(/daily_status=partial_success/)).toBeVisible();
    expect(policyPanel.getByText(/minute5_status=partial_success/)).toBeVisible();
  });

  it('keeps core cockpit content when optional home widgets fail', async () => {
    vi.mocked(api.fetchMarketMonitorEod).mockRejectedValueOnce(new Error('market monitor unavailable'));
    vi.mocked(api.fetchPublicNews).mockRejectedValueOnce(new Error('news unavailable'));

    render(<AppShell />);

    expect(await screen.findByRole('heading', { name: '策略指挥中心' })).toBeVisible();
    expect(screen.getByText('平台日期')).toBeVisible();
    expect(screen.getByText('2026-06-12')).toBeVisible();
    expect(screen.getByText('策略持仓状态')).toBeVisible();
    expect(screen.getByText('启用策略表现')).toBeVisible();
    expect(screen.getAllByText('LHB Shortline Combo')[0]).toBeVisible();
    expect(screen.getByText('市场环境不可用：market monitor unavailable')).toBeVisible();
    expect(screen.getByText('新闻流不可用：news unavailable')).toBeVisible();
  });

  it('shows research queue errors without breaking the cockpit', async () => {
    vi.mocked(api.fetchResearchCases).mockRejectedValueOnce(new Error('research cases unavailable'));
    vi.mocked(api.fetchResearchEvidence).mockRejectedValueOnce(new Error('research evidence unavailable'));

    render(<AppShell />);

    expect(await screen.findByRole('heading', { name: '策略指挥中心' })).toBeVisible();
    expect(screen.getByText('今日研究队列')).toBeVisible();
    const researchQueue = within(screen.getByRole('region', { name: '今日研究队列' }));
    expect(await researchQueue.findByText('研究队列暂不可用。')).toBeVisible();
    expect(researchQueue.getByText('不可用')).toBeVisible();
    expect(researchQueue.queryByText('无待处理')).not.toBeInTheDocument();
    expect(screen.queryByText(/研究队列不可用：research cases unavailable/)).not.toBeInTheDocument();
    fireEvent.click(researchQueue.getByRole('button', { name: '展开' }));
    expect(await researchQueue.findByText(/研究队列不可用：research cases unavailable/)).toBeVisible();
  });

  it('does not load manual v1 evidence digest rows on the home page', async () => {
    render(<AppShell />);

    expect(await screen.findByText('策略指挥中心')).toBeVisible();
    expect(screen.queryByText('Strong evidence')).not.toBeInTheDocument();
    expect(screen.queryByText('CN:SZ:300951')).not.toBeInTheDocument();
    expect(api.fetchEvidenceDigest).not.toHaveBeenCalled();
  });

  it('ignores manual v1 topn rows even when platform summary has them', async () => {
    const focusRows = Array.from({ length: 6 }, (_, index) => ({
      trade_date: '2026-06-08',
      asset_id: `CN:SZ:00000${index + 1}`,
      rank: index + 1,
      score_total: 90 - index,
      score_version: 'manual_v1',
      score_components: {}
    }));
    vi.mocked(api.fetchPlatformSummary).mockResolvedValueOnce({
      latest_market_date: '2026-06-08',
      latest_score_date: '2026-06-08',
      latest_factor_date: '2026-06-07',
      market_asset_count: 5207,
      score_asset_count: 5207,
      factor_count: 43,
      score_versions: ['manual_v1'],
      topn_preview: focusRows
    });

    render(<AppShell />);

    expect(await screen.findByRole('heading', { name: '策略指挥中心' })).toBeVisible();
    expect(screen.queryByText('CN:SZ:000001')).not.toBeInTheDocument();
    expect(screen.queryByText('CN:SZ:000006')).not.toBeInTheDocument();
    expect(api.fetchEvidenceDigest).not.toHaveBeenCalled();
  });

  it('does not request evidence digests when platform summary fails', async () => {
    vi.mocked(api.fetchPlatformSummary).mockRejectedValueOnce(new Error('summary unavailable'));

    render(<AppShell />);

    expect(await screen.findByText('平台摘要不可用：summary unavailable')).toBeVisible();
    expect(api.fetchEvidenceDigest).not.toHaveBeenCalled();
  });

  it('renders core cockpit content while optional home widgets are still pending', async () => {
    vi.mocked(api.fetchMarketMonitorEod).mockReturnValueOnce(new Promise(() => undefined));
    vi.mocked(api.fetchPublicNews).mockReturnValueOnce(new Promise(() => undefined));

    render(<AppShell />);

    expect(await screen.findByRole('heading', { name: '策略指挥中心' })).toBeVisible();
    expect(screen.getByText('平台日期')).toBeVisible();
    expect(screen.getByText('2026-06-12')).toBeVisible();
    expect(screen.getByText('启用策略表现')).toBeVisible();
    expect(screen.getAllByText('LHB Shortline Combo')[0]).toBeVisible();
    expect(screen.getByRole('button', { name: '打开策略实验室' })).toBeVisible();
    const marketRegime = within(screen.getByRole('region', { name: '市场环境' }));
    expect(marketRegime.getByText('市场环境加载中')).toBeVisible();
    expect(marketRegime.queryByText('市场情绪数据暂未接入。')).not.toBeInTheDocument();
  });

  it('marks failed strategy EOD outputs as not ready instead of showing stale performance', async () => {
    vi.mocked(api.fetchBacktestStrategies).mockResolvedValueOnce([
      {
        strategy_id: 'tech_bottleneck',
        strategy_name: 'Tech Bottleneck Combo',
        status: 'runnable',
        description: 'Tech bottleneck combo',
        factor_groups: ['技术形态'],
        signal_inputs: ['技术'],
        default_parameters: { top_n: 5 },
        latest_evidence: 'Tech Bottleneck Combo 正式策略产物失败：base candidate source freshness metadata missing',
        latest_metrics: {
          as_of_date: '2026-06-18',
          signal_status: 'strategy_failed',
          signal_count: 0,
          error_message: 'base candidate source freshness metadata missing'
        },
        primary_action: 'Run backtest'
      }
    ]);

    render(<AppShell />);

    expect(await screen.findByRole('heading', { name: '策略指挥中心' })).toBeVisible();
    const strategyPerformance = within(screen.getByRole('region', { name: '启用策略表现' }));
    expect(strategyPerformance.getByText('Tech Bottleneck Combo')).toBeVisible();
    expect(strategyPerformance.getByText('未就绪')).toBeVisible();
    expect(strategyPerformance.getByText('正式产物失败')).toBeVisible();
    expect(strategyPerformance.getByText(/base candidate source freshness metadata missing/)).toBeVisible();
    expect(strategyPerformance.queryByText('+60.10%')).not.toBeInTheDocument();
  });

  it('renders generic publication contracts and suppresses mismatched strategy performance', async () => {
    vi.mocked(api.fetchBacktestStrategies).mockResolvedValueOnce([
      {
        strategy_id: 'lhb_shortline',
        strategy_name: 'LHB Shortline Combo',
        status: 'runnable',
        description: 'LHB combo',
        factor_groups: ['资金行为'],
        signal_inputs: ['龙虎榜'],
        default_parameters: { top_n: 5 },
        latest_evidence: '正式策略产物。',
        latest_metrics: {
          as_of_date: '2026-07-18',
          performance_as_of_date: '2026-07-18',
          total_return_pct: 34.5,
          max_drawdown_pct: -4.2,
          signal_status: 'candidate_rows',
          signal_count: 5,
          contract_status: 'success',
          contract_id: 'lhb_shortline:balanced:auction_enhanced_rerank:balanced',
          publish_id: 'lhb-shortline-20260718',
          identity_schema_version: 'strategy_publication_identity_v1',
          config_fingerprint: 'lhb-fingerprint',
          publication_policy: {
            strategy_version: 'lhb_v1_stable_safe_top5',
            selection_policy: 'phase18c_top5_then_eligibility_no_refill',
            market_regime_policy: 'disabled_for_stable_strategy'
          },
          artifact_version: 'strategy_artifact_v1',
          publication_manifest_path:
            '/srv/outputs/research/strategy_daily_eod/2026-07-18/strategy_runs/lhb_shortline/publish-1/publication_manifest.json'
        },
        primary_action: 'Run backtest'
      },
      {
        strategy_id: 'mid_trend',
        strategy_name: 'Mid Trend Combo',
        status: 'runnable',
        description: 'Mid trend combo',
        factor_groups: ['趋势'],
        signal_inputs: ['趋势'],
        default_parameters: { top_n: 5 },
        latest_evidence: '身份合同不匹配。',
        latest_metrics: {
          as_of_date: '2026-07-18',
          performance_as_of_date: '2026-07-18',
          total_return_pct: 88.8,
          max_drawdown_pct: -12.3,
          signal_status: 'contract_mismatch',
          signal_count: 5,
          contract_status: 'contract_mismatch',
          contract_id: 'mid_trend:balanced:wrong',
          artifact_version: 'strategy_artifact_v1'
        },
        primary_action: 'Run backtest'
      }
    ]);

    render(<AppShell />);

    const strategyPerformance = within(await screen.findByRole('region', { name: '启用策略表现' }));
    const lhbCard = strategyPerformance.getByText('LHB Shortline Combo').closest('article');
    const midCard = strategyPerformance.getByText('Mid Trend Combo').closest('article');
    expect(lhbCard).not.toBeNull();
    expect(midCard).not.toBeNull();
    expect(within(lhbCard!).getByText('正式合同')).toBeVisible();
    expect(within(lhbCard!).getByText('发布编号')).toBeVisible();
    expect(within(lhbCard!).getByText('产物版本')).toBeVisible();
    expect(within(lhbCard!).getByText('校验状态')).toBeVisible();
    expect(within(lhbCard!).getByText('lhb_shortline:balanced:auction_enhanced_rerank:balanced')).toBeVisible();
    expect(within(lhbCard!).getByTestId('strategy-publish-id')).toHaveTextContent('lhb-shortline-20260718');
    expect(within(lhbCard!).getByText('strategy_artifact_v1')).toBeVisible();
    expect(within(lhbCard!).getByText('通过')).toBeVisible();
    expect(within(lhbCard!).getByText('Top5 先选后校验，不补位')).toBeVisible();
    expect(within(midCard!).getByText('正式合同')).toBeVisible();
    expect(within(midCard!).getByText('校验状态')).toBeVisible();
    expect(within(midCard!).getByText('合同不匹配')).toBeVisible();
    expect(within(midCard!).getByText('正式合同不匹配')).toBeVisible();
    expect(within(midCard!).queryByText('+88.8%')).not.toBeInTheDocument();
    expect(within(midCard!).queryByText('-12.3%')).not.toBeInTheDocument();
    expect(within(midCard!).queryByText('Top5 先选后校验，不补位')).not.toBeInTheDocument();
  });

  it('opens an official strategy deep link and selects it without running a backtest', async () => {
    render(<AppShell />);

    const strategyPerformance = within(await screen.findByRole('region', { name: '启用策略表现' }));
    fireEvent.click(strategyPerformance.getByRole('button', { name: '打开策略 Mid Trend Combo' }));

    expect(window.location.pathname).toBe('/strategy-lab');
    expect(window.location.search).toBe('?strategy_id=mid_trend');
    await waitFor(() => expect(screen.getByLabelText('strategy')).toHaveValue('mid_trend'));
  });

  it('does not expose Data Explorer in primary navigation', async () => {
    render(<AppShell />);
    await screen.findByRole('heading', { name: '策略指挥中心' });

    const sideNav = screen.getByRole('navigation', { name: 'Workspace navigation' });

    expect(within(sideNav).queryByRole('button', { name: 'Open Data Explorer workspace' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Data Explorer' })).not.toBeInTheDocument();
  });

  it('exposes side navigation with unique accessible names and current state', async () => {
    render(<AppShell />);
    await screen.findByRole('heading', { name: '策略指挥中心' });

    const sideNav = screen.getByRole('navigation', { name: 'Workspace navigation' });

    expect(within(sideNav).getByRole('button', { name: 'Open Home workspace' })).toHaveAttribute(
      'aria-current',
      'page'
    );
    expect(screen.getByRole('button', { name: 'Open Strategy Lab workspace' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Open Generated Reports workspace' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Open Strategy Validation workspace' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Open Reports workspace' })).not.toBeInTheDocument();
  });

  it('navigates to Generated Reports workspace and loads reports for the default trade date', async () => {
    render(<AppShell />);
    await screen.findByRole('heading', { name: '策略指挥中心' });

    const sideNav = screen.getByRole('navigation', { name: 'Workspace navigation' });
    fireEvent.click(within(sideNav).getByRole('button', { name: 'Open Generated Reports workspace' }));

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Generated Reports', level: 1 })).toBeVisible());
    expect(screen.getByText('Local generated artifacts from TopN, risk, factor, backtest, and validation jobs.')).toBeVisible();
    expect(api.fetchOverview).toHaveBeenCalledWith({
      tradeDate: '2026-06-12',
      scoreVersion: 'manual_v1',
      watchlistId: 'default',
      topN: 5
    });
    expect(await screen.findByText('Daily Market Review')).toBeVisible();
  });

  it('loads reports for the selected report date', async () => {
    render(<AppShell />);
    await screen.findByRole('heading', { name: '策略指挥中心' });

    const sideNav = screen.getByRole('navigation', { name: 'Workspace navigation' });
    fireEvent.click(within(sideNav).getByRole('button', { name: 'Open Generated Reports workspace' }));
    await screen.findByRole('heading', { name: 'Generated Reports', level: 1 });

    fireEvent.change(screen.getByLabelText('report trade date'), { target: { value: '2026-06-05' } });
    fireEvent.click(screen.getByRole('button', { name: 'Load Reports' }));

    await waitFor(() =>
      expect(api.fetchOverview).toHaveBeenLastCalledWith({
        tradeDate: '2026-06-05',
        scoreVersion: 'manual_v1',
        watchlistId: 'default',
        topN: 5
      })
    );
  });
});
