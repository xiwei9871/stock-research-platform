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

export type DashboardOverview = {
  trade_date: string;
  score_version: string;
  watchlist_id: string;
  top_scores: ScoreRow[];
  watchlist_signals: WatchlistSignalRow[];
  reports: ReportLink[];
};
