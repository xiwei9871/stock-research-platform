export type AssetSummary = {
  asset_id: string;
  symbol: string;
  name: string;
  exchange: string;
  board: string | null;
  is_active: boolean;
};

export type BarPoint = {
  time: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  amount: number | null;
};

export type ScoreRow = {
  trade_date: string;
  asset_id: string;
  rank: number;
  score_total: number;
  score_version: string;
  score_components: Record<string, unknown>;
};

export type WatchlistSignalRow = {
  watchlist_id: string;
  trade_date: string;
  asset_id: string;
  stock_code: string;
  stock_name: string;
  priority: number;
  signal_score: number | null;
  primary_signal: string;
  signal_tags: string[];
  risk_tags: string[];
  must_watch: boolean;
  reason_json: Record<string, unknown>;
};

export type ReportLink = {
  report_type: string;
  title: string;
  path: string;
  format: string;
  trade_date: string | null;
};

export type DecisionEventRow = {
  review_date: string;
  review_session_id: string;
  event_id: string;
  asset_id: string;
  stock_code: string;
  stock_name: string;
  decision_label: string;
  evidence_artifact_id: string;
  evidence_path: string;
  source_context: string;
  requires_follow_up: boolean;
  follow_up_note: string;
  notes: string;
  manual_review_required: boolean;
  auto_trade_enabled: boolean;
};

export type DecisionOutcomeRow = {
  outcome_event_id: string;
  run_id: string;
  decision_event_id: string;
  review_session_id: string;
  review_date: string;
  asset_id: string;
  stock_code: string;
  stock_name: string;
  decision_label: string;
  source_context: string;
  outcome_status: string;
  available_future_bars: number;
  base_trade_date: string;
  base_close: number | null;
  forward_returns: Record<string, number | null>;
  max_high_returns: Record<string, number | null>;
  max_low_drawdowns: Record<string, number | null>;
  manual_review_required: boolean;
  auto_trade_enabled: boolean;
  source_artifact_path: string;
  outcome_artifact_path: string;
};

export type OutcomeAnalyticsRow = {
  run_id: string;
  review_start_date: string;
  review_end_date: string;
  analytics_level: 'decision_label' | 'source_context' | string;
  group_value: string;
  sample_count: number;
  complete_count: number;
  insufficient_data_count: number;
  follow_up_required_rate: number | null;
  horizon_metrics: Record<
    string,
    {
      forward_return_mean?: number | null;
      forward_return_median?: number | null;
      forward_win_rate?: number | null;
      max_high_return_mean?: number | null;
      max_low_drawdown_mean?: number | null;
      max_low_drawdown_worst?: number | null;
    }
  >;
  analytics_artifact_path: string;
  manual_review_required: boolean;
  auto_trade_enabled: boolean;
};

export type PublicNewsItem = {
  news_id: string;
  source: string;
  source_channel: string;
  category: string;
  title: string;
  summary: string;
  url: string;
  published_at: string;
  collected_at: string;
  raw_id: string;
  raw_payload: Record<string, unknown>;
  status: string;
};

export type PublicNewsResponse = {
  items: PublicNewsItem[];
  warnings: string[];
};

export type PublicNewsRefreshResponse = {
  received?: number;
  stored: number;
  items_received: number;
  counts_by_category: Record<string, number>;
  warnings: string[];
};

export type ExperimentProposalRow = {
  proposal_id: string;
  run_id: string;
  review_date: string;
  proposal_title: string;
  hypothesis: string;
  source_p9_analytics_run_id: string;
  source_analytics_group_ids: string[];
  source_diagnostic_refs: string[];
  source_artifact_paths: string[];
  expected_validation_method: string;
  risk_notes: string;
  reviewer_id: string;
  status: string;
  proposal_artifact_path: string;
  manual_review_required: boolean;
  auto_trade_enabled: boolean;
  promotion_enabled: boolean;
};

export type ExperimentReplayRow = {
  replay_result_id: string;
  run_id: string;
  proposal_id: string;
  source_p10_proposal_run_id: string;
  source_p9_analytics_run_id: string;
  replay_start_date: string;
  replay_end_date: string;
  replay_input_artifact_paths: string[];
  validation_method: string;
  replay_status: string;
  sample_count: number;
  passed_count: number;
  failed_count: number;
  metric_summary: Record<string, number | string | boolean | null>;
  failure_reason: string;
  defer_reason: string;
  replay_artifact_path: string;
  manual_review_required: boolean;
  auto_trade_enabled: boolean;
  production_write_enabled: boolean;
};

export type ShadowWatchlistRow = {
  shadow_candidate_id: string;
  run_id: string;
  replay_result_id: string;
  source_p11_replay_run_id: string;
  source_p10_proposal_run_id: string;
  source_p9_analytics_run_id: string;
  candidate_date: string;
  asset_id: string;
  stock_code: string;
  stock_name: string;
  shadow_layer: string;
  candidate_reason: string;
  evidence_artifact_paths: string[];
  metric_summary: Record<string, number | string | boolean | null>;
  reviewer_id: string;
  status: string;
  review_notes: string;
  shadow_artifact_path: string;
  manual_review_required: boolean;
  auto_trade_enabled: boolean;
  production_watchlist_enabled: boolean;
  production_write_enabled: boolean;
};

export type ShadowOutcomeRow = {
  shadow_outcome_id: string;
  run_id: string;
  shadow_candidate_id: string;
  source_p12_shadow_run_id: string;
  replay_result_id: string;
  source_p11_replay_run_id: string;
  source_p10_proposal_run_id: string;
  source_p9_analytics_run_id: string;
  candidate_date: string;
  asset_id: string;
  stock_code: string;
  stock_name: string;
  shadow_layer: string;
  shadow_status: string;
  outcome_status: string;
  available_future_bars: number;
  base_trade_date: string;
  base_close: number | null;
  forward_returns: Record<string, number | null>;
  max_high_returns: Record<string, number | null>;
  max_low_drawdowns: Record<string, number | null>;
  manual_review_required: boolean;
  auto_trade_enabled: boolean;
  production_watchlist_enabled: boolean;
  production_write_enabled: boolean;
};

export type ShadowOutcomeAnalyticsRow = {
  analytics_group_id: string;
  run_id: string;
  review_start_date: string;
  review_end_date: string;
  group_key: string;
  shadow_layer: string;
  shadow_status: string;
  sample_count: number;
  complete_count: number;
  insufficient_data_count: number;
  source_p12_shadow_run_count: number;
  source_p11_replay_run_count: number;
  source_p10_proposal_run_count: number;
  source_p9_analytics_run_count: number;
  horizon_metrics: Record<string, Record<string, number | null>>;
  analytics_artifact_path: string;
  manual_review_required: boolean;
  auto_trade_enabled: boolean;
  production_watchlist_enabled: boolean;
  production_write_enabled: boolean;
};

export type ShadowAnalyticsReviewRow = {
  review_group_id: string;
  run_id: string;
  review_start_date: string;
  review_end_date: string;
  group_key: string;
  shadow_layer: string;
  shadow_status: string;
  sample_count: number;
  complete_count: number;
  insufficient_data_count: number;
  horizon_metrics: Record<string, Record<string, number | null>>;
  review_status: string;
  review_bucket: string;
  evidence_summary: string;
  risk_notes: string;
  next_research_question: string;
  manual_review_required: boolean;
  auto_trade_enabled: boolean;
  production_watchlist_enabled: boolean;
  production_write_enabled: boolean;
};

export type ShadowReviewDecisionRow = {
  decision_group_id: string;
  run_id: string;
  decision_date: string;
  source_p15_review_group_id: string;
  source_p15_review_run_id: string;
  source_p14_analytics_group_id: string;
  source_p14_analytics_run_id: string;
  group_key: string;
  shadow_layer: string;
  shadow_status: string;
  sample_count: number;
  complete_count: number;
  insufficient_data_count: number;
  review_status: string;
  review_bucket: string;
  decision_status: string;
  decision_bucket: string;
  decision_reason: string;
  required_next_action: string;
  evidence_summary: string;
  risk_notes: string;
  next_research_question: string;
  manual_review_required: boolean;
  auto_trade_enabled: boolean;
  production_watchlist_enabled: boolean;
  production_write_enabled: boolean;
};

export type ShadowFollowUpRow = {
  follow_up_item_id: string;
  run_id: string;
  follow_up_date: string;
  source_p16_decision_group_id: string;
  source_p16_decision_run_id: string;
  source_p15_review_group_id: string;
  source_p15_review_run_id: string;
  source_p14_analytics_group_id: string;
  source_p14_analytics_run_id: string;
  group_key: string;
  shadow_layer: string;
  shadow_status: string;
  sample_count: number;
  complete_count: number;
  insufficient_data_count: number;
  review_status: string;
  review_bucket: string;
  decision_status: string;
  decision_bucket: string;
  follow_up_status: string;
  priority_bucket: string;
  required_input: string;
  follow_up_reason: string;
  decision_reason: string;
  required_next_action: string;
  evidence_summary: string;
  risk_notes: string;
  next_research_question: string;
  manual_review_required: boolean;
  auto_trade_enabled: boolean;
  production_watchlist_enabled: boolean;
  production_write_enabled: boolean;
};

export type ShadowFollowUpResolutionRow = {
  resolution_item_id: string;
  run_id: string;
  resolution_date: string;
  source_p17_follow_up_item_id: string;
  source_p17_follow_up_run_id: string;
  source_p16_decision_group_id: string;
  source_p16_decision_run_id: string;
  source_p15_review_group_id: string;
  source_p15_review_run_id: string;
  source_p14_analytics_group_id: string;
  source_p14_analytics_run_id: string;
  group_key: string;
  shadow_layer: string;
  shadow_status: string;
  sample_count: number;
  complete_count: number;
  insufficient_data_count: number;
  review_status: string;
  review_bucket: string;
  decision_status: string;
  decision_bucket: string;
  follow_up_status: string;
  priority_bucket: string;
  required_input: string;
  resolution_status: string;
  resolution_bucket: string;
  recommended_resolution_action: string;
  resolution_reason: string;
  follow_up_reason: string;
  decision_reason: string;
  required_next_action: string;
  evidence_summary: string;
  risk_notes: string;
  next_research_question: string;
  manual_review_required: boolean;
  auto_trade_enabled: boolean;
  production_watchlist_enabled: boolean;
  production_write_enabled: boolean;
};

export type DashboardOverview = {
  trade_date: string;
  score_version: string;
  watchlist_id: string;
  top_scores: ScoreRow[];
  watchlist_signals: WatchlistSignalRow[];
  reports: ReportLink[];
};

export type DailyReviewLiteState = 'ready' | 'partial' | 'failed' | 'empty';

export type DailyReviewLiteRunStatus = 'success' | 'partial' | 'failed';

export type DailyReviewLiteArtifactHealth = 'healthy' | 'missing' | 'invalid';

export type DailyReviewLiteSectionStatus = 'success' | 'partial' | 'empty';

export type DailyReviewLiteSelectedRun = {
  run_id: string;
  report_type: string;
  status: DailyReviewLiteRunStatus;
  updated_at: string | null;
  source: string;
  artifact_health: DailyReviewLiteArtifactHealth;
  artifact_health_detail: Record<string, DailyReviewLiteArtifactHealth>;
};

export type DailyReviewLiteSummary = {
  market_status: string | null;
  overall_position_bias: string | null;
  lhb_conclusion: string | null;
  mid_trend_conclusion: string | null;
  technical_bottleneck_conclusion: string | null;
  must_review_asset_ids: string[];
  warning_count: number;
};

export type DailyReviewLiteMissingSource = {
  source_key: string | null;
  summary: string | null;
  affected_sections: string[];
  confidence_impact: string | null;
};

export type DailyReviewLiteArtifactDescriptor = {
  key: string;
  label: string;
  kind: string;
  required: boolean;
  available: boolean;
  filename: string | null;
  content_type: string;
  url: string;
};

export type DailyReviewLiteReason = {
  strategy_id: string | null;
  summary: string | null;
  detail?: string | null;
};

export type DailyReviewLiteStrategyItem = {
  asset_id: string | null;
  ts_code: string | null;
  stock_name: string | null;
  item_type: string | null;
  state: string | null;
  action: string | null;
  review_priority: string | null;
  reason?: {
    summary?: string | null;
    detail?: string | null;
  };
};

export type DailyReviewLiteStrategySection = {
  strategy_id: string;
  status: DailyReviewLiteSectionStatus;
  warnings: string[];
  summary: Record<string, unknown>;
  top_items: DailyReviewLiteStrategyItem[];
};

export type DailyReviewLiteChecklistItem = {
  asset_id: string | null;
  ts_code: string | null;
  stock_name: string | null;
  strategy_ids: string[];
  reasons: DailyReviewLiteReason[];
  actions: string[];
  review_priority: string | null;
};

export type DailyReviewLiteSections = {
  data_readiness: {
    status: DailyReviewLiteSectionStatus;
    warnings: string[];
    sources: Record<string, unknown>;
  };
  market_review: {
    status: DailyReviewLiteSectionStatus;
    warnings: string[];
    payload: Record<string, unknown>;
  };
  strategy_summaries: {
    lhb: DailyReviewLiteStrategySection;
    mid_trend: DailyReviewLiteStrategySection;
    technical_bottleneck: DailyReviewLiteStrategySection;
  };
  holding_review: {
    status: DailyReviewLiteSectionStatus;
    warnings: string[];
    items: Record<string, unknown>[];
  };
  operator_plan: {
    status: DailyReviewLiteSectionStatus;
    warnings: string[];
    payload: Record<string, unknown>;
  };
  next_day_checklist: {
    status: DailyReviewLiteSectionStatus;
    warnings: string[];
    must_review_items: DailyReviewLiteChecklistItem[];
    forbidden_actions: string[];
    data_warnings: string[];
  };
};

export type DailyReviewLiteResponse = {
  trade_date: string;
  state: DailyReviewLiteState;
  selected_run: DailyReviewLiteSelectedRun | null;
  summary: DailyReviewLiteSummary | null;
  warnings: string[];
  missing_sources: DailyReviewLiteMissingSource[];
  sections: DailyReviewLiteSections;
  artifacts: DailyReviewLiteArtifactDescriptor[];
};
