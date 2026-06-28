export type AssetSummary = {
  asset_id: string;
  symbol: string;
  name: string;
  exchange: string;
  board: string | null;
  is_active: boolean;
};

export type AssetSearchResponse = {
  items: AssetSummary[];
};

export type GlobalSearchResultType = 'asset' | 'news' | 'research_report' | 'generated_report' | string;

export type GlobalSearchTarget = {
  workspace: 'stock' | 'news' | 'researchReports' | 'generatedReports' | string;
  asset_id?: string;
  news_id?: string;
  report_id?: string;
  event_key?: string;
  path?: string;
  q?: string;
  trade_date?: string;
};

export type GlobalSearchResult = {
  type: GlobalSearchResultType;
  id: string;
  title: string;
  subtitle: string;
  metadata: Record<string, unknown>;
  meta?: Record<string, unknown>;
  target: GlobalSearchTarget;
  score?: number;
  match_reason?: string;
  match_fields?: string[];
  asset_id?: string;
  source?: string;
  timestamp?: string;
  trade_date?: string;
  link?: string;
};

export type GlobalSearchGroup = {
  key: 'assets' | 'news' | 'research_reports' | 'generated_reports' | string;
  label: string;
  items: GlobalSearchResult[];
};

export type GlobalSearchResponse = {
  query: string;
  groups: GlobalSearchGroup[];
  warnings: string[];
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

export type WatchlistResponse = {
  watchlist_id: string;
  trade_date: string;
  items: WatchlistSignalRow[];
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
  run_id?: string;
  digest_key?: string;
  review_item_snapshot_id?: string;
  evidence_digest_snapshot_id?: string;
  review_item_payload_hash?: string;
  evidence_digest_payload_hash?: string;
  evidence_as_of?: string;
  review_item_as_of?: string;
  snapshot_linkage_status?: 'linked' | 'missing' | string;
  snapshot_linkage_warnings?: string[];
  requires_follow_up: boolean;
  follow_up_note: string;
  notes: string;
  manual_review_required: boolean;
  auto_trade_enabled: boolean;
};

export type CreateOperatorDecisionRequest = {
  asset_id?: string;
  stock_code?: string;
  stock_name?: string;
  decision_date?: string;
  operator_action: 'watch' | 'skip' | 'follow_up' | 'add_to_shadow' | 'remove_from_shadow' | 'note' | 'pause' | 'close' | string;
  decision_status?: string;
  operator_note?: string;
  run_id?: string;
  digest_key?: string;
  review_item_snapshot_id?: string;
  evidence_digest_snapshot_id?: string;
  source_type?: string;
  source_name?: string;
  follow_up_date?: string;
  tags?: string[];
  source_context?: Record<string, unknown> | string;
};

export type CreateOperatorDecisionResponse = {
  event_id: string;
  asset_id: string;
  stock_code: string;
  stock_name: string;
  decision_date: string;
  operator_action: string;
  decision_status: string;
  decision_label: string;
  run_id: string;
  digest_key: string;
  review_item_snapshot_id: string;
  evidence_digest_snapshot_id: string;
  review_item_payload_hash?: string;
  evidence_digest_payload_hash?: string;
  evidence_as_of?: string;
  review_item_as_of?: string;
  snapshot_linkage_status: 'linked' | 'missing' | string;
  snapshot_linkage_warnings: string[];
  warnings: string[];
  source_context?: string;
  workflow_effects?: Array<{
    type: string;
    status: string;
    watchlist_id?: string;
    asset_id?: string;
  }>;
};

export type UpdateOperatorDecisionRequest = {
  notes?: string;
  follow_up_note?: string;
  requires_follow_up?: boolean;
};

export type BacktestJobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | string;

export type BacktestJobResponse = {
  job_id: string;
  status: BacktestJobStatus;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
  payload?: Record<string, unknown>;
  result?: BacktestRunResult | null;
  error?: string;
};

export type ReviewItemSnapshot = {
  snapshot_id: string;
  run_id: string;
  trade_date: string;
  latest_trade_date?: string | null;
  asset_id: string;
  stock_code?: string | null;
  stock_name?: string | null;
  digest_key: string;
  source_type: string;
  source_name: string;
  source_rank?: number | null;
  topn_rank?: number | null;
  score_version: string;
  score?: number | null;
  evidence_status: string;
  missing_evidence_count: number;
  partial_evidence_count: number;
  warnings_count: number;
  review_item_payload?: Record<string, unknown>;
  payload_hash: string;
  schema_version: string;
  created_at?: string;
  updated_at?: string;
};

export type EvidenceDigestSnapshot = {
  snapshot_id: string;
  run_id: string;
  trade_date: string;
  latest_trade_date?: string | null;
  asset_id: string;
  stock_code?: string | null;
  stock_name?: string | null;
  digest_key: string;
  overall_status: string;
  missing_evidence: string[];
  partial_evidence: string[];
  sections_status: Record<string, string>;
  digest_payload?: Record<string, unknown>;
  payload_hash: string;
  schema_version: string;
  created_at?: string;
  updated_at?: string;
};

export type SnapshotListResponse<T> = {
  items: T[];
  warnings: string[];
  as_of: string;
  source: string;
};

export type EvidenceDigestSnapshotDetailResponse = {
  item: EvidenceDigestSnapshot;
  warnings: string[];
  source: string;
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

export type PlatformSummary = {
  latest_market_date: string;
  latest_score_date: string;
  latest_factor_date: string;
  market_asset_count: number;
  score_asset_count: number;
  factor_count: number;
  score_versions: string[];
  topn_preview: ScoreRow[];
};

export type MarketDataStatus = 'completed' | 'partial' | 'missing' | 'stale' | string;

export type SectorType = 'industry' | 'concept';

export type MarketOverviewIndex = {
  code: string;
  name: string;
  close: number | null;
  change_pct: number | null;
};

export type MarketOverview = {
  trade_date: string;
  updated_at: string | null;
  source: string;
  data_status: MarketDataStatus;
  warnings: string[];
  indices: MarketOverviewIndex[];
  total_amount: number | null;
  up_count: number | null;
  down_count: number | null;
  limit_up_count: number | null;
  limit_down_count: number | null;
};

export type SectorHeatmapItem = {
  sector_id: string;
  sector_name: string;
  sector_type: SectorType;
  change_pct: number | null;
  amount: number | null;
  up_count: number | null;
  down_count: number | null;
  main_net_inflow: number | null;
  stock_count: number | null;
};

export type SectorFundFlowItem = {
  rank: number;
  sector_id: string;
  sector_name: string;
  sector_type: SectorType;
  change_pct: number | null;
  amount: number | null;
  main_net_inflow: number | null;
  main_net_inflow_ratio: number | null;
  leading_stock_name: string | null;
};

export type SectorDetail = {
  trade_date: string;
  updated_at: string | null;
  source: string;
  data_status: MarketDataStatus;
  warnings: string[];
  sector_id: string;
  sector_name: string;
  sector_type: SectorType;
  change_pct: number | null;
  amount: number | null;
  up_count: number | null;
  down_count: number | null;
  main_net_inflow: number | null;
  main_net_inflow_ratio: number | null;
  leading_stocks: Array<{ asset_id: string; name: string; change_pct: number | null }> | [];
};

export type StrategyScoreAuditStrategySummary = {
  strategy_id: string;
  row_count?: number;
  selected_count?: number;
  anomaly_count: number;
};

export type StrategyScoreAuditSampleRow = {
  asset_id: string;
  anomaly_flags: string[];
  stock_name?: string | null;
  strategy_id?: string | null;
  published_score?: number | null;
};

export type StrategyScoreAuditSummary = {
  trade_date: string;
  status: string;
  overall_status: 'ok' | 'warning' | 'missing' | string;
  summary_path: string;
  detail_path: string;
  total_rows: number;
  selected_rows: number;
  anomaly_row_count: number;
  anomaly_counts_by_type: Record<string, number>;
  strategies: StrategyScoreAuditStrategySummary[];
  sample_rows: StrategyScoreAuditSampleRow[];
  warnings?: string[];
  generated_at?: string;
};

export type PlatformReadinessStatus = 'OK' | 'PARTIAL' | 'BLOCKED' | 'ready' | 'partial' | 'missing_data';

export type PlatformReadinessCheckStatus = PlatformReadinessStatus | 'unknown';

export type PlatformReadinessCheck = {
  key: string;
  label: string;
  status: PlatformReadinessCheckStatus;
  detail: string;
};

export type PlatformReadinessHealthItem = {
  key: string;
  label: string;
  status: PlatformReadinessCheckStatus;
  detail: string;
  row_count?: number | null;
  latest_trade_date?: string;
  module?: string;
};

export type PlatformReadinessHealthGroup = {
  key: string;
  label: string;
  status: PlatformReadinessCheckStatus;
  ready_count: number;
  total_count: number;
  items: PlatformReadinessHealthItem[];
};

export type PlatformReadiness = {
  mode: string;
  status: PlatformReadinessStatus;
  as_of: string;
  run_id?: string;
  latest_trade_date?: string;
  latest_market_date: string;
  display_trade_date?: string;
  candidate_trade_date?: string;
  display_gate?: PlatformDisplayDateGate;
  source?: string;
  summary_path?: string;
  tiers?: Array<{ tier: string; status: string }>;
  modules?: Array<Record<string, unknown>>;
  checks: PlatformReadinessCheck[];
  health_groups?: PlatformReadinessHealthGroup[];
  warnings: string[];
  errors?: string[];
  missing_data?: string[];
  partial_data?: string[];
  next_actions?: string[];
  dashboard_url?: string;
};

export type PlatformDisplayDateGate = {
  display_trade_date?: string;
  latest_market_date?: string;
  candidate_trade_date?: string;
  cutoff_time?: string;
  timezone?: string;
  display_status?: string;
  candidate_status?: string;
  strategy_ready?: string;
  contract_valid?: string;
  blocking_reasons?: string[];
};

export type PlatformDisplayDate = {
  display_trade_date: string;
  candidate_trade_date: string;
  latest_market_date: string;
  status: string;
  display_gate: PlatformDisplayDateGate;
  warnings: string[];
};

export type StrategyCatalogItem = {
  strategy_id: string;
  strategy_name: string;
  status: 'runnable' | 'replay_only' | 'planned' | string;
  description: string;
  factor_groups: string[];
  signal_inputs: string[];
  default_parameters: Record<string, unknown>;
  latest_evidence: string;
  latest_metrics?: {
    as_of_date: string | null;
    total_return_pct?: number | null;
    max_drawdown_pct?: number | null;
    latest_day_return_pct?: number | null;
    latest_day_drawdown_pct?: number | null;
    latest_period_return_pct?: number | null;
    latest_period_label?: string | null;
    signal_status: 'connected' | 'no_position_rows' | string;
    signal_count: number | null;
    signal_as_of_date?: string | null;
    error_message?: string | null;
  };
  primary_action: string;
};

export type FactorLibraryRow = {
  factor_name: string;
  factor_group: string;
  direction: 'higher' | 'lower' | string;
  description: string;
  source: string;
  calc_version: string;
  status: string;
  availability_start_date: string | null;
  availability_reason: string | null;
  latest_available_date: string | null;
  coverage_count: number;
  used_in_manual_v1: boolean;
  manual_v1_weight: number | null;
};

export type FactorSelection = {
  factor_name: string;
  direction: 'higher' | 'lower';
  weight: number;
};

export type FactorScorePreview = {
  trade_date: string;
  selected_factors: FactorSelection[];
  items: Array<{
    trade_date: string;
    asset_id: string;
    rank: number;
    score_total: number;
    score_components: Record<string, number | null>;
  }>;
};

export type AssetProfile = {
  asset_id: string;
  canonical_asset_id: string;
  asset: AssetSummary | null;
  bars: BarPoint[];
  score: ScoreRow | null;
  signals: WatchlistSignalRow[];
  decisions: DecisionEventRow[];
  outcomes: DecisionOutcomeRow[];
  factor_values: Array<Record<string, unknown>>;
  coverage: Record<string, unknown>;
};

export type BacktestRunRequest = {
  strategy_id: string;
  start_date: string;
  end_date: string;
  score_version: string;
  top_n: number;
  rebalance_frequency?: 'daily' | 'weekly';
  transaction_cost_bps: number;
  max_positions: number | null;
  max_position_weight?: number | null;
  risk_profile?: 'return_max' | 'balanced' | 'drawdown_control';
  adjust_type: string;
};

export type BacktestScalar = number | string | boolean | null;
export type BacktestValue = BacktestScalar | BacktestValue[] | { [key: string]: BacktestValue };

export type BacktestRunResult = {
  strategy_id: string;
  strategy_name: string;
  read_only: boolean;
  execution_mode?: 'fresh' | 'replay' | 'validated';
  result_source?: string;
  run_started_at?: string;
  run_finished_at?: string;
  elapsed_ms?: number;
  config: Record<string, unknown>;
  summary: Record<string, BacktestValue>;
  equity_curve: Array<Record<string, BacktestScalar>>;
  positions: Array<Record<string, BacktestScalar>>;
  trades: Array<Record<string, BacktestScalar>>;
};

export type StrategyValidationRun = {
  run_id: string;
  strategy_id: string;
  strategy_name: string;
  strategy_version: string;
  run_type: string;
  start_date: string;
  end_date: string;
  created_at: string;
  benchmark: string;
  universe: string;
  data_window: Record<string, unknown>;
  cost_config: Record<string, unknown>;
  slippage_config: Record<string, unknown>;
  risk_config: Record<string, unknown>;
  position_config: Record<string, unknown>;
  source_artifact_paths: string[];
  summary_metrics: Record<string, unknown>;
  warnings: string[];
};

export type StrategySignal = {
  run_id: string;
  strategy_id: string;
  asset_id: string;
  stock_code: string;
  stock_name: string;
  signal_time: string;
  trade_date: string;
  signal_type: string;
  signal_strength: number | null;
  signal_bucket: string;
  risk_bucket: string;
  rule_id: string;
  reason: string;
  tags: string[];
  source_artifact_path: string;
};

export type StrategyTrade = {
  run_id: string;
  strategy_id: string;
  asset_id: string;
  entry_time: string | null;
  entry_price: number | null;
  entry_reason: string;
  exit_time: string | null;
  exit_price: number | null;
  exit_reason: string;
  holding_days: number | null;
  return_pct: number | null;
  max_high_return_pct: number | null;
  max_drawdown_pct: number | null;
  outcome_status: string;
  source_artifact_path: string;
};

export type StrategyPositionSnapshot = {
  run_id: string;
  strategy_id: string;
  trade_date: string;
  asset_id: string;
  position_weight: number | null;
  target_weight: number | null;
  cash_weight: number | null;
  exposure: number | null;
  position_cap: number | null;
  risk_budget: number | null;
  suppression_reason: string;
  source_artifact_path: string;
};

export type StrategyMetricRow = {
  run_id: string;
  strategy_id: string;
  metric_level: string;
  group_key: string;
  sample_count: number;
  complete_count: number;
  win_rate: number | null;
  forward_return_mean: number | null;
  forward_return_median: number | null;
  max_high_return_mean: number | null;
  max_drawdown_mean: number | null;
  max_drawdown_worst: number | null;
  turnover: number | null;
  exposure_mean: number | null;
  source_artifact_path: string;
};

export type StrategyEvidenceArtifact = {
  run_id: string;
  artifact_type: string;
  title: string;
  path: string;
  format: string;
  trade_date: string | null;
  description: string;
};

export type StrategyReplayPayload = {
  run: StrategyValidationRun | null;
  asset_id: string;
  bars: BarPoint[];
  signals: StrategySignal[];
  trades: StrategyTrade[];
  positions: StrategyPositionSnapshot[];
  metrics: StrategyMetricRow[];
  artifacts: StrategyEvidenceArtifact[];
};

export type PublicNewsStockMention = {
  asset_id: string;
  ts_code: string;
  stock_name: string;
  mention_role?: string;
  mention_confidence?: number | null;
  mapping_method?: string;
  theme_name?: string;
  theme_confidence?: number | null;
  trade_date?: string;
};

export type CountRow = {
  name: string;
  rows: number;
};

export type PublicNewsSummary = {
  total_news?: number;
  latest_published_at?: string;
  latest_collected_at?: string;
  source_count?: number;
  source_counts?: CountRow[];
  category_counts?: CountRow[];
  collector_status?: PublicNewsCollectorStatus;
};

export type PublicNewsCollectorStatus = {
  enabled: boolean;
  running: boolean;
  interval_seconds: number;
  last_success_at?: string;
  last_error?: string;
  next_run_at?: string;
};

export type PublicNewsItem = {
  id?: string;
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
  quality_score?: number | null;
  quality_reasons?: string[];
  quality_run_id?: string;
  stocks?: PublicNewsStockMention[];
  metadata?: Record<string, unknown>;
};

export type PublicNewsResponse = {
  items: PublicNewsItem[];
  total?: number;
  limit?: number;
  offset?: number;
  summary?: PublicNewsSummary;
  warnings: string[];
};

export type AssetNewsSummary = {
  news_count_1d: number;
  news_count_3d: number;
  news_count_7d: number;
  latest_published_at?: string;
  source_count?: number;
  category_counts?: CountRow[];
};

export type AssetNewsResponse = {
  asset_id: string;
  items: PublicNewsItem[];
  summary: AssetNewsSummary;
  warnings: string[];
};

export type PublicNewsRefreshResponse = {
  received?: number;
  stored: number;
  items_received: number;
  accepted?: number;
  rejected?: number;
  rejection_counts?: Record<string, number>;
  quality_threshold?: number;
  max_accepted?: number;
  counts_by_category: Record<string, number>;
  warnings: string[];
};

export type MarketMonitorFreshness = {
  mode: 'eod' | string;
  label: string;
  is_realtime: boolean;
  latest_market_date?: string;
  latest_factor_date?: string;
  latest_score_date?: string;
};

export type MarketMonitorCoverage = {
  market_assets: number;
  score_assets: number;
  factor_count: number;
};

export type MarketBreadth = {
  advancers: number | null;
  decliners: number | null;
  limit_up: number | null;
  limit_down: number | null;
  advancing_ratio: number | null;
  turnover_change_pct: number | null;
  status: string;
};

export type MarketEmotionStatus = 'available' | 'pending_source' | string;

export type MarketEmotionSummary = {
  score: number | null;
  state: string;
  risk_state: string;
  style_signal_hint: string;
  position_budget_hint: string;
  status: MarketEmotionStatus;
};

export type MarketEmotionComponent = {
  key: string;
  label: string;
  score: number | null;
};

export type MarketEmotionPayload = {
  summary: MarketEmotionSummary;
  components: MarketEmotionComponent[];
  breadth: {
    traded_count?: number | null;
    up_count?: number | null;
    down_count?: number | null;
    strong_up_count?: number | null;
    strong_down_count?: number | null;
    status: MarketEmotionStatus;
  };
  liquidity: {
    total_amount?: number | null;
    amount_ratio_5_20?: number | null;
    status: MarketEmotionStatus;
  };
  limit_performance: {
    limit_up_count?: number | null;
    limit_down_count?: number | null;
    broken_limit_up_count?: number | null;
    broken_limit_up_rate?: number | null;
    first_board_count?: number | null;
    second_board_count?: number | null;
    third_board_plus_count?: number | null;
    high_board_height?: number | null;
    status: MarketEmotionStatus;
  };
  profit_effect: {
    limit_up_success_rate?: number | null;
    limit_up_profit_rate?: number | null;
    limit_up_limit_down_rate?: number | null;
    relay_profit_rate?: number | null;
    relay_success_rate?: number | null;
    relay_continue_rate?: number | null;
    broken_profit_rate?: number | null;
    broken_success_rate?: number | null;
    broken_limit_down_rate?: number | null;
    status: MarketEmotionStatus;
  };
  drawdown_pressure: {
    strong_down_count?: number | null;
    limit_down_count?: number | null;
    broken_limit_up_rate?: number | null;
    yesterday_limit_up_limit_down_rate?: number | null;
    status: MarketEmotionStatus;
  };
  weight_performance: {
    status: MarketEmotionStatus;
  };
};

export type EmotionStockListRow = {
  name: string;
  asset_id: string;
  symbol: string;
  amount: number | null;
  pct_chg: number | null;
  board: string | null;
  tab: string;
  limit_up_streak?: number | null;
};

export type EmotionStockLists = {
  auction_status: MarketEmotionStatus;
  auction: EmotionStockListRow[];
  limit_up: EmotionStockListRow[];
  broken_limit_up: EmotionStockListRow[];
  limit_down: EmotionStockListRow[];
};

export type MarketMonitorPayload = {
  trade_date: string;
  freshness: MarketMonitorFreshness;
  coverage: MarketMonitorCoverage;
  market_breadth: MarketBreadth;
  index_snapshot: Array<Record<string, unknown>>;
  sector_strength: {
    strongest: Array<Record<string, unknown>>;
    weakest: Array<Record<string, unknown>>;
    status: string;
  };
  unusual_moves: Array<Record<string, unknown>>;
  watchlist_alerts: Array<Record<string, unknown>>;
  strategy_signal_summary: {
    topn_preview_count: number;
    topn_preview: ScoreRow[];
    risk_filter_counts: Record<string, number>;
  };
  generated_reports: ReportLink[];
  market_emotion: MarketEmotionPayload;
  emotion_stock_lists: EmotionStockLists;
  warnings: string[];
};

export type ResearchReportCount = {
  rows: number;
  source_name?: string;
  rating?: string;
  broker?: string;
};

export type ResearchReportSummary = {
  total_reports: number;
  covered_stocks: number;
  latest_publish_date: string | null;
  latest_feature_date: string | null;
  source_count: number;
  source_counts: ResearchReportCount[];
  rating_counts: ResearchReportCount[];
  broker_counts: ResearchReportCount[];
};

export type ResearchReportItem = {
  event_key: string;
  report_id: string;
  asset_id: string;
  ts_code: string;
  stock_name: string;
  industry_name: string;
  report_title: string;
  publish_date: string | null;
  report_date: string | null;
  broker: string;
  analyst: string;
  rating: string;
  rating_change: string;
  target_price: number | null;
  target_upside: number | null;
  source_type: string;
  source_name: string;
  source_confidence: number | null;
  public_access: boolean;
  copyright_note: string;
  source_url: string;
  raw_summary: string;
  company_view: string;
  industry_view: string;
  risk_summary: string;
  metadata: Record<string, unknown>;
};

export type ResearchReportResponse = {
  items: ResearchReportItem[];
  total: number;
  limit: number;
  offset: number;
  warnings: string[];
};

export type AssetResearchReportSummary = {
  report_count_30d: number;
  report_count_90d: number;
  broker_coverage_count_90d: number;
  latest_report_date: string | null;
  latest_rating: string;
  latest_target_price: number | null;
};

export type AssetResearchReportResponse = {
  asset_id: string;
  summary: AssetResearchReportSummary;
  items: ResearchReportItem[];
  warnings: string[];
};

export type EvidenceDigestBucket = 'strong' | 'mixed' | 'thin' | 'risk_heavy';
export type EvidenceDigestSeverity = 'positive' | 'neutral' | 'warning' | 'negative' | 'severe' | string;
export type EvidenceDigestOverallStatus = 'OK' | 'PARTIAL' | 'BLOCKED' | string;
export type EvidenceSectionStatus = 'available' | 'partial' | 'missing' | 'unavailable' | 'skipped' | 'error' | string;

export type EvidenceDigestSourceRef = {
  workspace?: 'news' | 'researchReports' | 'market' | 'stock' | string;
  asset_id?: string;
  news_id?: string;
  report_id?: string;
  event_key?: string;
  monitor_tab?: string;
  strategy_asset_id?: string;
};

export type EvidenceDigestFact = {
  kind: 'news' | 'research' | 'market' | 'strategy' | string;
  key?: string;
  label: string;
  severity?: EvidenceDigestSeverity;
  value?: string | number | string[] | number[] | null;
  published_at?: string | null;
  rating?: string | null;
  target_price?: number | null;
  amount?: number | null;
  source_ref?: EvidenceDigestSourceRef;
};

export type EvidenceDigestRiskFlag = {
  key: string;
  label: string;
  severity: EvidenceDigestSeverity;
  value?: string | number | string[] | number[] | null;
};

export type EvidenceDigestAction = {
  key: 'open_news' | 'open_research' | 'open_market' | 'review_stock' | string;
  label: string;
  workspace: 'news' | 'researchReports' | 'market' | 'stock' | string;
  asset_id?: string;
  news_id?: string;
  report_id?: string;
  event_key?: string;
  monitor_tab?: string;
  query?: string;
};

export type EvidenceDigestSection = {
  status: EvidenceSectionStatus;
  as_of: string;
  source: string;
  item_count: number;
  warnings: string[];
  error_message: string;
  data: Record<string, unknown>;
  artifact_path: string;
};

export type EvidenceDigestResponse = {
  asset_id: string;
  canonical_asset_id: string;
  stock_code?: string;
  stock_name?: string;
  trade_date: string;
  latest_trade_date?: string;
  run_id?: string;
  digest_key?: string;
  generated_at?: string;
  overall_status?: EvidenceDigestOverallStatus;
  sections?: Record<string, EvidenceDigestSection>;
  missing_evidence?: string[];
  partial_evidence?: string[];
  lineage?: Record<string, unknown>;
  errors?: string[];
  title: string;
  score: number;
  bucket: EvidenceDigestBucket;
  facts: EvidenceDigestFact[];
  risk_flags: EvidenceDigestRiskFlag[];
  source_refs: EvidenceDigestSourceRef;
  next_actions: EvidenceDigestAction[];
  warnings: string[];
};

export type ReviewQueueItem = {
  queue_id: string;
  asset_id: string;
  canonical_asset_id: string;
  trade_date: string;
  latest_trade_date?: string;
  run_id?: string;
  generated_at?: string;
  score_version: string;
  display_name: string;
  rank: number | null;
  score: number | null;
  source_type?: string;
  source_name?: string;
  source_rank?: number | null;
  score_components?: Record<string, unknown>;
  topn_rank?: number | null;
  strategy_id?: string | null;
  strategy_name?: string | null;
  strategy_run_id?: string | null;
  review_tier?: 'top5_focus' | 'top10_watch' | string | null;
  weight?: number | null;
  factor_as_of?: string;
  factor_snapshot_id?: string | null;
  digest_key?: string;
  evidence_digest_id?: string;
  digest_url_path?: string;
  stock_workspace_url_path?: string;
  evidence_status?: EvidenceDigestOverallStatus;
  missing_evidence?: string[];
  partial_evidence?: string[];
  missing_evidence_count?: number;
  partial_evidence_count?: number;
  warnings_count?: number;
  warnings?: string[];
  manifest_modules?: Array<Record<string, unknown>>;
  digest_title: string;
  bucket: EvidenceDigestBucket;
  source_kinds: string[];
  risk_count: number;
  warning_count: number;
  next_action_count: number;
  digest: EvidenceDigestResponse;
};

export type ReviewQueueGroup = {
  bucket: string;
  label: string;
  count: number;
  items: ReviewQueueItem[];
};

export type ReviewQueueResponse = {
  trade_date: string;
  score_version: string;
  review_mode?: 'strategy_topn' | 'score_topn' | string;
  generated_at: string;
  groups: ReviewQueueGroup[];
  warnings: string[];
};

export type OpsStageRow = {
  stage: string;
  status: string;
  started_at: string | null;
  updated_at: string | null;
  error_summary: string | null;
};

export type OpsSnapshot = {
  run_window: {
    requested_trade_date: string;
    trade_date: string;
    status_trade_date: string | null;
    latest_available_trade_date: string | null;
    status_matches_requested_trade_date: boolean;
    current_trade_date: string | null;
    latest_ready_trade_date: string | null;
    last_updated_at: string | null;
    now: string;
    stage_count: number;
  };
  pipeline: {
    overall_status: string;
    pipeline_status: string;
    daily_status: string | null;
    minute5_status: string | null;
    deps_status: string | null;
    latest_ready_trade_date: string | null;
    last_updated_at: string | null;
    evaluated_at: string;
    stage_statuses: string[];
  };
  health: Record<string, unknown>;
  intervention: {
    severity: string;
    needs_intervention: boolean;
    reason_text: string;
    suggested_action?: string | null;
  };
  readiness: {
    ready_status: string;
    latest_ready_trade_date: string | null;
    ready_for_dashboard: boolean;
    ready_for_publication: boolean;
    blocking_issue_count: number;
  };
  snapshot_preview: {
    market_state: Record<string, unknown>;
    topn_preview: Array<Record<string, unknown>>;
    coverage_summary: Record<string, unknown>;
    factor_gate_summary: Record<string, unknown>;
    published_at: string | null;
  };
};

export type PublicSnapshot = {
  trade_date: string;
  published_at: string | null;
  latest_ready_trade_date: string | null;
  status: string;
  status_text: string;
  market_state: Record<string, unknown>;
  topn_preview: Array<Record<string, unknown>>;
  coverage_summary: Record<string, unknown>;
  factor_gate_summary: Record<string, unknown>;
  notes: string[];
};
