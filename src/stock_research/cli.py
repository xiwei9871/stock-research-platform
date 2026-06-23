import argparse
import datetime as dt
import json
import math
import os
import sys
from pathlib import Path
from uuid import uuid4

import pandas as pd

from stock_research.assets import sync_asset_master
from stock_research.auction_data import (
    build_open_auction_spot_snapshot_cron_entries,
    build_lhb_auction_backfill_plan,
    build_lhb_auction_enhanced_rule_scan_report_v1,
    build_lhb_auction_observation_report_v1,
    build_lhb_auction_topn_rerank_comparison_report_v1,
    build_lhb_phase18d_close_auction_lifecycle_report_v1,
    build_lhb_phase18e_joint_exit_diagnostics_report_v1,
    build_tushare_auction_full_backfill_plan,
    collect_open_auction_spot_snapshot,
    collect_open_auction_minute_bars,
    collect_open_auction_minute_bars_until_covered,
    load_open_trading_dates,
    load_tushare_auction_full_coverage,
    load_existing_lhb_auction_coverage,
    load_lhb_auction_backfill_universe,
    load_open_auction_minute_universe,
    run_lhb_auction_backfill_plan,
    run_tushare_auction_full_backfill_plan,
    sync_tushare_stock_auction_bars,
    write_open_auction_spot_snapshot_report,
    write_open_auction_minute_collect_report,
    write_lhb_auction_backfill_plan_report,
    write_tushare_auction_full_backfill_report,
)
from stock_research.config import SETTINGS
from stock_research.backtest import run_top20_backtest
from stock_research.backfill_runs import (
    backfill_status_for_service,
    claim_backfill_tasks_for_service,
    create_backfill_run_for_service,
    mark_backfill_task_failed_for_service,
    mark_backfill_task_success_for_service,
    reset_stale_backfill_tasks_for_service,
)
from stock_research.corporate_actions import (
    build_adjustment_factors_for_service,
    build_corporate_actions_from_factors_for_service,
)
from stock_research.core_data import (
    build_asset_status_daily_for_service,
    build_industry_daily_bars_for_service,
    sync_chinese_stock_names_from_akshare_for_service,
    sync_core_asset_master_for_service,
)
from stock_research.data_audit import format_audit_line, run_data_audit
from stock_research.data_quality import (
    format_data_quality_check_line,
    format_data_quality_summary_line,
    run_data_quality,
)
from stock_research.dashboard.api import run_dashboard_api
from stock_research.dashboard.user_admin import (
    bootstrap_admin_account,
    enable_user_account_by_username,
)
from stock_research.db import connect, fetch_all
from stock_research.dimensions import (
    seed_trading_calendar_from_bars,
    sync_asset_lifecycle_from_master,
)
from stock_research.finance_audit import format_finance_audit_line, summarize_finance_coverage
from stock_research.industry_history import (
    benchmark_industry_day,
    run_industry_history_range,
)
from stock_research.industry_focus_score import run_industry_focus_backtest_report
from stock_research.industry_focus_v2 import (
    run_industry_focus_v2_backtest,
    run_industry_focus_v2_diagnostics,
)
from stock_research.industry_factor_audit import (
    run_fixed_industry_reconciliation,
    run_industry_error_audit,
)
from stock_research.industry_mainline_regime import (
    run_industry_mainline_regime_diagnostics,
)
from stock_research.industry_regime_gated_backtest import (
    run_industry_regime_gated_backtest,
)
from stock_research.industry_exposure_risk_control import (
    run_industry_exposure_risk_control,
)
from stock_research.intraday_risk_control_v2 import run_intraday_risk_control_v2_backtest
from stock_research.intraday_risk_filter_backtest import run_intraday_risk_filter_backtest
from stock_research.features import (
    compute_and_store_p0_features,
    compute_and_store_p0_features_range,
    derive_feature_backfill_window,
)
from stock_research.feishu_notify import send_openclaw_feishu_message
from stock_research.factor_backfill import (
    backfill_factor_daily_range,
    derive_factor_backfill_window,
)
from stock_research.free_enrichment_data import run_free_enrichment_backfill
from stock_research.approved_scoring_workflow import score_approved_factors_range
from stock_research.factor_pipeline import build_and_store_factor_daily
from stock_research.factor_eval_batch import run_factor_gate_batch
from stock_research.factor_eval.gate import decide_factor_gate
from stock_research.factor_eval.multi_horizon import generate_multi_horizon_report
from stock_research.factor_eval.report import generate_factor_eval_report
from stock_research.factor_eval.validation_review import (
    build_factor_validation_review,
    write_factor_validation_review,
)
from stock_research.factor_eval_store import (
    load_factor_eval_inputs,
    load_multi_horizon_factor_eval_inputs,
    store_factor_approval,
    store_factor_eval_run,
)
from stock_research.factor_store import load_top_scores, score_stored_factor_daily
from stock_research.factor_gate_watchdog import run_factor_gate_batch_watchdog
from stock_research.daily_pipeline import run_daily_factor_pipeline
from stock_research.daily_close_pipeline import (
    PipelineConfig as DailyClosePipelineConfig,
    parse_trade_date as parse_daily_close_trade_date,
    run_pipeline_stage as run_daily_close_pipeline_stage,
)
from stock_research.stock_cron_guard import sync_trading_calendar_range_from_tushare
from stock_research.intraday_pipeline import (
    IntradayConfig,
    parse_trade_date as parse_intraday_trade_date,
    run_intraday_stage,
)
from stock_research.daily_incremental import (
    build_default_step_runners,
    check_market_data_freshness,
    run_daily_incremental_pipeline,
)
from stock_research.daily_data_pipeline import run_stock_daily_data_pipeline
from stock_research.daily_job_run_store import (
    apply_daily_job_run_schema,
    record_daily_job_run,
)
from stock_research.daily_health import (
    format_operational_health_lines,
    summarize_operational_health,
)
from stock_research.dragon_strategy_research import run_dragon_research_v1
from stock_research.dragon_case_library import (
    apply_source_backfill,
    build_source_backfill_check_report,
    build_source_backfill_workpack,
    compare_source_backfill_curated,
    build_failure_event_rule_v21_curated_view,
    build_failure_event_rule_v21_transition_matrix,
    run_failure_event_rule_v2_diagnostics,
    run_dragon_case_expand_web_seeds,
    import_web_seeds,
    run_dragon_case_library_build,
    run_dragon_case_library_diagnose,
    run_dragon_case_web_verify,
)
from stock_research.ingest_jobs import (
    create_ingest_jobs_for_service,
    format_ingest_loop_report,
    ingest_status_for_service,
    reset_stale_ingest_jobs_for_service,
    run_ingest_loop_for_service,
    run_ingest_jobs_for_service,
)
from stock_research.labels import compute_and_store_labels, derive_label_backfill_window
from stock_research.lhb_data import (
    run_daily_lhb_shortline_watchlist_v1,
    run_dragon_case_lhb_alignment_audit,
    run_dragon_case_lhb_summary_report,
    run_lhb_diagnostics_after_failure_rule_v21,
    run_lhb_full_market_pool_backtest_v1,
    run_lhb_intraday_filtered_topn_comparison_v1,
    run_lhb_coverage_and_failure_rule_plan,
    run_lhb_exit_rule_audit_v1,
    run_lhb_follow_avoid_rule_audit_v1,
    run_lhb_follow_exit_replay_v1,
    run_lhb_shortline_daily_pipeline_v1,
    run_lhb_shortline_manual_review_v1,
    run_lhb_phase12a_multi_context_decision_v1,
    run_lhb_phase12a_rule_decision_v1,
    run_lhb_phase12a_real_entry_backtest_v1,
    run_lhb_phase12b_signal_exit_v1,
    run_lhb_phase13_two_stage_follow_pool_v1,
    run_lhb_phase13b_topn_filter_v1,
    run_lhb_phase14_lifecycle_exit_v1,
    run_lhb_phase14b_threshold_scan_v1,
    run_lhb_phase14c_lifecycle_portfolio_v1,
    run_lhb_phase14e_limit_lock_filter_v1,
    run_lhb_phase15_cash_account_backtest_v1,
    run_lhb_cutoff_audit_v1,
    run_lhb_phase16_quality_improvement_diagnostics_v1,
    run_lhb_phase16b_limit_break_failed_exit_replay_v1,
    run_lhb_phase16c_limit_break_failed_rule_scan_v1,
    run_lhb_phase16d_limit_break_failed_indicator_discovery_v1,
    run_lhb_phase16e_limit_break_failed_indicator_rule_scan_v1,
    run_lhb_phase18c_auction_enhanced_cash_account_backtest_v1,
    run_lhb_phase18f_tradable_joint_exit_replay_v1,
    run_lhb_risk_feature_diagnostics,
    run_lhb_case_difference_report,
    run_lhb_event_features_build,
    run_lhb_sample_import,
    run_lhb_shortline_event_replay_v1,
    run_lhb_shortline_intraday_confirmation_v1,
    run_lhb_shortline_rule_calibration_v1,
    run_lhb_shortline_shadow_backtest_v1,
    run_lhb_shortline_strategy_effectiveness_v1,
)
from stock_research.loaders.baostock_ingestion import (
    sync_index_daily_bars,
    sync_index_constituents,
    sync_industry_memberships,
)
from stock_research.loaders.baostock_finance_ingestion import sync_finance_for_period
from stock_research.market_data import (
    latest_complete_source_trade_date,
    load_market_daily_bars,
)
from stock_research.market_emotion_state_v1 import run_market_emotion_state_v1_backfill
from stock_research.migration_safety import run_backup_restore_check
from stock_research.minute_backfill import (
    benchmark_baostock_minute_backfill_workers,
    load_backfill_status,
    plan_baostock_minute_backfill,
    run_baostock_minute_backfill,
    run_baostock_minute_backfill_range,
    validate_minute_bars,
)
from stock_research.minute_backfill_watchdog import run_minute_backfill_watchdog
from stock_research.minute_data import sync_baostock_stock_minute_bars
from stock_research.news_source_backfill import (
    HISTORICAL_TOP10_NEWS_PROVIDERS,
    run_historical_top10_news_backfill,
    run_news_source_backfill,
    run_topn_news_source_backfill,
)
from stock_research.news_features import (
    run_news_feature_backfill,
    run_news_feature_diagnostics,
)
from stock_research.serenity_tight3b_c2_experiment import (
    run_serenity_tight3b_c2_experiment,
)
from stock_research.serenity_source_backed_evidence_fill import (
    run_serenity_source_backed_evidence_fill,
)
from stock_research.tech_bottleneck_evidence_workflow import (
    run_tech_bottleneck_evidence_workflow,
)
from stock_research.top10_historical_news_effectiveness_review import (
    run_top10_historical_news_effectiveness_review,
)
from stock_research.topn_news_enrichment import run_topn_news_enrichment
from stock_research.portfolio_backtest import run_portfolio_backtest
from stock_research.p2.artifact_rollup import (
    build_p2_artifact_rollup,
    write_p2_artifact_rollup,
)
from stock_research.p2.aggregate_review import (
    build_p2_aggregate_review,
    load_aggregate_artifact_payloads,
    write_p2_aggregate_review,
)
from stock_research.p2.review_read_model import import_p2_aggregate_review
from stock_research.p3.operator_export import export_operator_review
from stock_research.operator_decision.journal import (
    build_decision_journal,
    write_decision_journal,
)
from stock_research.operator_decision.outcome import (
    build_decision_outcome_review,
    write_decision_outcome_review,
)
from stock_research.operator_decision.outcome_analytics import (
    build_decision_outcome_analytics,
    write_decision_outcome_analytics,
)
from stock_research.operator_decision.shadow_outcome_analytics import (
    build_shadow_outcome_analytics,
    write_shadow_outcome_analytics,
)
from stock_research.operator_decision.shadow_analytics_review import (
    build_shadow_analytics_review,
    write_shadow_analytics_review,
)
from stock_research.open_auction_minute_cron import build_open_auction_minute_cron_entries
from stock_research.xtick_auction_data import (
    build_xtick_auction_backfill_plan,
    build_xtick_auction_close_check,
    collect_xtick_dayupdate_bid,
    load_existing_xtick_auction_coverage,
    load_xtick_backfill_trade_dates,
    run_xtick_auction_backfill_plan,
    write_xtick_auction_backfill_plan_report,
    write_xtick_auction_backfill_run_report,
    write_xtick_auction_close_check_report,
    write_xtick_auction_collect_report,
)
from stock_research.operator_decision.shadow_review_decisions import (
    build_shadow_review_decisions,
    write_shadow_review_decisions,
)
from stock_research.operator_decision.shadow_follow_up_queue import (
    build_shadow_follow_up_queue,
    write_shadow_follow_up_queue,
)
from stock_research.operator_decision.shadow_follow_up_resolution import (
    build_shadow_follow_up_resolution,
    write_shadow_follow_up_resolution,
)
from stock_research.operator_decision.shadow_outcome_analytics_read_model import (
    import_shadow_outcome_analytics,
)
from stock_research.operator_decision.shadow_analytics_review_read_model import (
    import_shadow_analytics_review,
)
from stock_research.operator_decision.shadow_review_decisions_read_model import (
    import_shadow_review_decisions,
)
from stock_research.operator_decision.shadow_follow_up_queue_read_model import (
    import_shadow_follow_up_queue,
)
from stock_research.operator_decision.shadow_follow_up_resolution_read_model import (
    import_shadow_follow_up_resolution,
)
from stock_research.operator_decision.experiment_proposals import (
    build_experiment_proposal_review,
    write_experiment_proposal_review,
)
from stock_research.operator_decision.experiment_proposals_read_model import import_experiment_proposal_review
from stock_research.operator_decision.experiment_replay import (
    build_experiment_replay_review,
    write_experiment_replay_review,
)
from stock_research.operator_decision.experiment_replay_read_model import import_experiment_replay_review
from stock_research.operator_decision.shadow_watchlist import (
    build_shadow_watchlist_review,
    write_shadow_watchlist_review,
)
from stock_research.operator_decision.shadow_outcomes import (
    build_shadow_outcome_review,
    write_shadow_outcome_review,
)
from stock_research.operator_decision.shadow_outcomes_read_model import (
    import_shadow_outcome_review,
    load_shadow_outcome_read_model_rows,
)
from stock_research.operator_decision.shadow_watchlist_read_model import (
    import_shadow_watchlist_review,
    load_shadow_watchlist_read_model_rows,
)
from stock_research.operator_decision.outcome_analytics_read_model import import_decision_outcome_analytics
from stock_research.operator_decision.outcome_read_model import import_decision_outcome_review
from stock_research.operator_decision.read_model import import_decision_journal
from stock_research.p4.scheduler import (
    check_read_model_freshness,
    format_daily_orchestration_lines,
    format_read_model_freshness_lines,
    run_daily_orchestration,
)
from stock_research.p4.scheduler_wrapper import build_p4_scheduler_cron_entry
from stock_research.simulation.portfolio import write_portfolio_simulation_review
from stock_research.simulation.virtual_portfolio import (
    build_virtual_portfolio_review,
    load_simulation_states,
    write_virtual_portfolio_review,
)
from stock_research.simulation.virtual_portfolio_read_model import (
    import_virtual_portfolio_review,
)
from stock_research.quality import run_daily_quality_checks
from stock_research.reporting import format_daily_report
from stock_research.report_delivery import deliver_local_reports
from stock_research.report_delivery_feishu import (
    FeishuDryRunAdapter,
    FeishuSendConfig,
    FeishuSender,
    FakeFeishuTransport,
    HttpFeishuTransport,
)
from stock_research.report_delivery_openclaw import OpenClawExportAdapter
from stock_research.report_delivery_openclaw_sender import (
    DryRunOpenClawTransport,
    HttpOpenClawTransport,
    OpenClawSendConfig,
    OpenClawSendInputError,
    OpenClawSender,
)
from stock_research.research_preflight import (
    check_factor_label_coverage,
    check_industry_membership_coverage,
    find_latest_common_label_date,
    default_research_factor_names,
)
from stock_research.research_windows import load_market_date_bounds
from stock_research.reports.daily_review_report_cli import (
    iter_daily_review_report_path_lines,
    run_daily_review_report,
)
from stock_research.reports.daily_research_report_cli import run_daily_research_report
from stock_research.reports.agent_research_report import build_agent_research_report
from stock_research.reports.watchlist_report import (
    _json_safe_value,
    write_watchlist_diagnostics_report,
    write_watchlist_report,
)
from stock_research.backtest_constraints import BacktestExecutionConstraints
from stock_research.retention_backtest import run_retention_backtest
from stock_research.research_snapshot_export import export_research_snapshot
from stock_research.schema import apply_schema
from stock_research.selection import generate_selection, store_selection
from stock_research.trend_candidate_backtest import run_trend_candidate_backtest_report
from stock_research.trend_candidate_enrichment import (
    run_entry_success_candidate_v2_report,
    run_entry_success_reverse_profile_report,
    run_candidate_enrichment_report,
    run_full_universe_candidate_enrichment_report,
)
from stock_research.trend_factor_profile import run_mid_trend_factor_profile_report
from stock_research.trend_lifecycle import run_trend_lifecycle_v1_report
from stock_research.trade_advice.advice import (
    TradeAdvicePolicy,
    generate_trade_advice,
    write_trade_advice,
)
from stock_research.technical_feature_store import (
    TECHNICAL_FEATURE_CALC_VERSION,
    build_and_store_stock_technical_features_daily,
)
from stock_research.technical_feature_benchmark import (
    run_technical_feature_compare_benchmark,
    run_technical_feature_store_compare_benchmark,
)
from stock_research.technical_feature_performance_review import (
    build_technical_feature_performance_review,
    write_technical_feature_performance_review,
)
from stock_research.technical_feature_promotion_audit import (
    run_technical_feature_promotion_audit,
)
from stock_research.technical_feature_regression import run_technical_feature_fast_regression
from stock_research.technical_feature_backfill import (
    backfill_technical_features_daily_range,
    derive_technical_feature_backfill_window,
    run_technical_feature_backfill_benchmark,
)
from stock_research.technical_feature_audit import (
    run_technical_feature_gap_check,
)
from stock_research.technical_feature_watchdog import (
    run_technical_feature_backfill_watchdog,
)
from stock_research.stock_report_backfill import (
    load_stock_report_asset_universe,
    run_stock_report_feature_backfill,
    run_stock_report_backfill_plan,
    run_stock_report_backfill_run,
)
from stock_research.stock_report_backfill_watchdog import run_stock_report_backfill_watchdog
from stock_research.stock_report_pdf_backfill import (
    run_stock_report_pdf_backfill_watchdog,
    run_stock_report_pdf_field_backfill,
)
from stock_research.stock_report_research import run_stock_report_workpack
from stock_research.stock_report_web_collection import (
    run_stock_report_feature_build,
    run_stock_report_search_plan,
    run_stock_report_web_source_collection,
)
from stock_research.yanbaoke_report_backfill import build_yanbaoke_inventory_plan
from stock_research.hibor_reports import (
    build_hibor_a_tier_backfill_plan,
    build_hibor_download_queue,
    download_hibor_report_pdfs,
    import_hibor_report_pdfs,
    run_hibor_a_tier_backfill,
    watch_hibor_downloads,
)
from stock_research.hibor_ui_download import run_hibor_ui_download_backfill
from stock_research.yanbaoke_reports import run_yanbaoke_report_backfill
from stock_research.intraday_features import (
    INTRADAY_FEATURE_CALC_VERSION,
    backfill_intraday_features_daily_range,
    build_and_store_intraday_features_daily,
    run_intraday_feature_gap_check,
)
from stock_research.intraday_factor_eval import run_intraday_factor_eval
from stock_research.alpha191_pilot_validation import (
    run_validate_alpha191_expanded,
    run_validate_alpha191_pilot,
)
from stock_research.technical_method_validation import run_validate_technical_methods
from stock_research.run_card import write_run_card
from stock_research.services.universe_service import (
    UniverseConfig,
    UniverseMember,
    UniverseService,
    get_universe_preset,
    load_watchlist_codes,
    write_universe_artifacts,
)
from stock_research.v31_cache import build_v31_cache
from stock_research.watchlist.workflow import (
    build_watchlist_diagnostics_snapshot,
    build_watchlist_snapshot,
    explain_watchlist_asset,
)
from stock_research.watchlist.diagnostics import DIAGNOSTICS_RULE_VERSION
from stock_research.watchlist.effectiveness import (
    run_watchlist_diagnostics_effectiveness_review,
)
from stock_research.watchlist.context_cross_review import run_watchlist_context_cross_review
from stock_research.watchlist.dual_strategy_review import run_dual_strategy_effectiveness_review
from stock_research.watchlist.trend_template_validation import (
    run_trend_discovery_template_validation,
)
from stock_research.watchlist.trend_discovery_v2_replay import run_trend_discovery_v2_replay
from stock_research.watchlist.trend_discovery_v2_purity import (
    run_trend_discovery_v2_purity_audit,
)
from stock_research.watchlist.trend_discovery_v2_2_replay import (
    run_trend_discovery_v2_2_replay,
)
from stock_research.watchlist.trend_discovery_v2_2_stability import (
    run_trend_discovery_v2_2_stability_review,
)
from stock_research.watchlist.risk_split import run_risk_watch_split_review
from stock_research.watchlist.fundamental_coverage import (
    run_watchlist_fundamental_coverage_audit,
)
from stock_research.watchlist.fundamental_pit_context import (
    run_watchlist_fundamental_pit_context_build,
)
from stock_research.strong_winner_miss_analysis import run_strong_winner_miss_analysis
from stock_research.strong_winner_capture_gap import run_strong_winner_capture_gap_analysis
from stock_research.strong_winner_taxonomy import run_strong_winner_taxonomy_v2
from stock_research.strong_winner_topn_attribution import run_strong_winner_topn_attribution
from stock_research.strong_winner_discovery_pool import run_strong_winner_discovery_pool
from stock_research.diagnostics_candidate_source_audit import (
    run_diagnostics_candidate_source_audit,
)
from stock_research.mid_trend_watch_funnel import run_mid_trend_watch_funnel
from stock_research.mid_trend_drawdown_control import run_mid_trend_drawdown_control_validation
from stock_research.mid_trend_pareto_scan import run_mid_trend_pareto_scan
from stock_research.mid_trend_shadow_stability import run_mid_trend_shadow_stability_review
from stock_research.mid_trend_shadow_top10 import run_mid_trend_shadow_top10
from stock_research.mid_trend_research_packet import run_mid_trend_research_packet
from stock_research.mid_trend_portfolio_review import run_mid_trend_portfolio_review
from stock_research.mid_trend_position_dossier import run_mid_trend_position_dossier
from stock_research.mid_trend_shadow_backtest import run_mid_trend_shadow_backtest
from stock_research.mid_trend_shadow_weekly_optimization import (
    run_mid_trend_shadow_weekly_optimization,
)
from stock_research.mid_trend_shadow_weekly_control import (
    run_mid_trend_shadow_weekly_control_review,
)
from stock_research.mid_trend_shadow_replacement_scan import (
    run_mid_trend_shadow_replacement_scan,
)
from stock_research.mid_trend_trend_protection_scan import run_mid_trend_trend_protection_scan
from stock_research.mid_trend_trend_protection_stability import (
    run_mid_trend_trend_protection_stability_review,
)
from stock_research.mid_trend_drawdown_throttle_scan import run_mid_trend_drawdown_throttle_scan
from stock_research.mid_trend_adaptive_candidate_review import (
    run_mid_trend_adaptive_candidate_review,
)
from stock_research.mid_trend_adaptive_issue_attribution import (
    run_mid_trend_adaptive_issue_attribution,
)
from stock_research.mid_trend_adaptive_bad_buy_attribution import (
    run_mid_trend_adaptive_bad_buy_attribution,
)
from stock_research.mid_trend_entry_timing_attribution import (
    run_mid_trend_entry_timing_attribution,
)
from stock_research.mid_trend_rebalance_attribution import run_mid_trend_rebalance_attribution
from stock_research.mid_trend_shadow_control_v2_scan import (
    run_mid_trend_shadow_control_v2_scan,
)
from stock_research.mid_trend_bad_rebalance_state_attribution import (
    run_bad_rebalance_state_attribution,
)
from stock_research.watchlist.store import load_watchlist_daily_signals, store_watchlist_daily_signals


def parse_int_list(value: str, option_name: str) -> list[int]:
    parts = [part.strip() for part in value.split(",")]
    if not parts or any(part == "" for part in parts):
        raise argparse.ArgumentTypeError(f"{option_name} must not contain empty values")
    try:
        values = [int(part) for part in parts]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"{option_name} must be a comma-separated list of integers"
        ) from exc

    if any(item <= 0 for item in values):
        raise argparse.ArgumentTypeError(f"{option_name} values must be positive")
    return values


def parse_float_list(value: str, option_name: str) -> list[float]:
    parts = [part.strip() for part in value.split(",")]
    if not parts or any(part == "" for part in parts):
        raise argparse.ArgumentTypeError(f"{option_name} must not contain empty values")
    try:
        values = [float(part) for part in parts]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"{option_name} must be a comma-separated list of numbers"
        ) from exc

    if any(item < 0 for item in values):
        raise argparse.ArgumentTypeError(f"{option_name} values must be non-negative")
    return values


def parse_holding_days(value: str) -> list[int]:
    return parse_int_list(value, "--holding-days")


def parse_top_ks(value: str) -> list[int]:
    return parse_int_list(value, "--top-ks")


def parse_worker_counts(value: str) -> list[int]:
    return parse_int_list(value, "--workers-list")


def parse_topn_thresholds(value: str) -> list[int]:
    return parse_int_list(value, "--topn-thresholds")


def parse_research_horizons(value: str) -> list[int]:
    return parse_int_list(value, "--horizons")


def parse_factor_names(value: str) -> list[str]:
    parts = [part.strip() for part in value.split(",")]
    if not parts or any(part == "" for part in parts):
        raise argparse.ArgumentTypeError("--factor-names must not contain empty values")
    return parts


def parse_str_list(value: str, option_name: str) -> list[str]:
    parts = [part.strip() for part in value.split(",")]
    if not parts or any(part == "" for part in parts):
        raise argparse.ArgumentTypeError(f"{option_name} must not contain empty values")
    return parts


def parse_exchanges(value: str) -> list[str]:
    return parse_str_list(value, "--exchanges")


def parse_index_ids(value: str) -> list[str]:
    return parse_str_list(value, "--index-ids")


def parse_adjust_types(value: str) -> list[str]:
    adjust_types = parse_str_list(value, "--adjust-types")
    allowed = {"raw", "qfq", "hfq"}
    invalid = [item for item in adjust_types if item not in allowed]
    if invalid:
        raise argparse.ArgumentTypeError(
            "--adjust-types values must be one of raw, qfq, hfq"
        )
    return adjust_types


def parse_auction_phases(value: str) -> list[str]:
    phases = parse_str_list(value, "--auction-phases")
    allowed = {"open_call", "close_call"}
    invalid = [item for item in phases if item not in allowed]
    if invalid:
        raise argparse.ArgumentTypeError(
            "--auction-phases values must be one of open_call, close_call"
        )
    return phases


def parse_ts_codes(value: str) -> list[str]:
    return parse_str_list(value, "--ts-codes")


def parse_candidate_paths(value: str) -> list[str]:
    return parse_str_list(value, "--candidate-paths")


def parse_trade_dates(value: str) -> list[str]:
    return parse_str_list(value, "--trade-dates")


def parse_thresholds(value: str) -> list[float]:
    return [float(item) for item in parse_str_list(value, "--thresholds")]


def parse_ingest_datasets(value: str) -> list[str]:
    return parse_str_list(value, "--ingest-datasets")


def parse_backfill_run_ids(value: str) -> list[str]:
    return parse_str_list(value, "--backfill-run-ids")


def parse_openclaw_timeout_seconds(value: object) -> float:
    try:
        timeout_seconds = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "report-delivery-openclaw-send: "
            "--timeout-seconds / OPENCLAW_TIMEOUT_SECONDS must be a finite number greater than 0, "
            f"got {value!r}"
        ) from exc
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError(
            "report-delivery-openclaw-send: "
            "--timeout-seconds / OPENCLAW_TIMEOUT_SECONDS must be a finite number greater than 0, "
            f"got {value!r}"
        )
    return timeout_seconds


def build_universe_config_from_args(
    args: argparse.Namespace,
    *,
    watchlist_codes: list[str] | None = None,
) -> UniverseConfig:
    overrides: dict[str, object] = {}
    if getattr(args, "min_listed_days", None) is not None:
        overrides["min_listed_days"] = int(args.min_listed_days)
    if getattr(args, "min_avg_turnover_amount", None) is not None:
        overrides["min_avg_turnover_amount"] = float(args.min_avg_turnover_amount)
    if getattr(args, "min_avg_volume", None) is not None:
        overrides["min_avg_volume"] = float(args.min_avg_volume)
    if getattr(args, "liquidity_lookback_days", None) is not None:
        overrides["liquidity_lookback_days"] = int(args.liquidity_lookback_days)
    if getattr(args, "max_suspended_days", None) is not None:
        overrides["max_suspended_days"] = int(args.max_suspended_days)
    return get_universe_preset(
        args.date,
        args.preset,
        watchlist_codes=watchlist_codes,
        **overrides,
    )


def build_universe_artifacts(
    *,
    result: object,
    output_dir: str,
) -> object:
    return write_universe_artifacts(result, output_dir)


def openclaw_export(
    *,
    trade_date: str,
    manifest_path: str,
    output_dir: str,
    include_all: bool,
    min_severity: str,
    dry_run: bool,
):
    adapter = OpenClawExportAdapter()
    manifest = adapter.load_local_manifest(manifest_path)
    source_trade_date = str(manifest.get("trade_date", ""))
    if source_trade_date != trade_date:
        raise ValueError(
            "report-delivery-openclaw-export: "
            f"trade-date {trade_date} does not match manifest trade_date {source_trade_date}"
        )
    return adapter.export(
        manifest_path,
        include_all=include_all,
        min_severity=min_severity,
        dry_run=dry_run,
        output_dir=output_dir,
    )


def feishu_preview(
    *,
    trade_date: str,
    manifest_path: str,
    output_dir: str,
    include_all: bool,
    min_severity: str,
):
    adapter = FeishuDryRunAdapter()
    manifest = adapter.load_local_manifest(manifest_path)
    source_trade_date = str(manifest.get("trade_date", ""))
    if source_trade_date != trade_date:
        raise ValueError(
            "report-delivery-feishu: "
            f"trade-date {trade_date} does not match manifest trade_date {source_trade_date}"
        )
    return adapter.render_preview(
        manifest_path,
        output_dir=output_dir,
        include_all=include_all,
        min_severity=min_severity,
    )


def feishu_send(
    *,
    trade_date: str,
    preview_path: str,
    output_dir: str,
    webhook_url: str | None,
    dry_run: bool,
    limit: int | None,
    allow_live_send: bool,
    severity_max: str | None,
    test_mode: bool,
):
    sender = FeishuSender(
        transport=FakeFeishuTransport() if dry_run else HttpFeishuTransport()
    )
    preview = sender.load_preview(preview_path)
    source_trade_date = str(preview.get("trade_date", ""))
    if source_trade_date != trade_date:
        raise ValueError(
            "report-delivery-feishu-send: "
            f"trade-date {trade_date} does not match preview trade_date {source_trade_date}"
        )
    return sender.send_preview(
        preview_path=preview_path,
        config=FeishuSendConfig(
            webhook_url=webhook_url,
            dry_run=dry_run,
            outbox_dir=output_dir,
            limit=limit,
            allow_live_send=allow_live_send,
            severity_max=severity_max,
            test_mode=test_mode,
        ),
    )


def universe_member_to_json(member: UniverseMember) -> str:
    return json.dumps(
        {
            "trade_date": member.trade_date,
            "asset_id": member.asset_id,
            "stock_code": member.stock_code,
            "stock_name": member.stock_name,
            "board": member.board,
            "listed_days": member.listed_days,
            "is_st": member.is_st,
            "is_suspended": member.is_suspended,
            "avg_turnover_amount": member.avg_turnover_amount,
            "avg_volume": member.avg_volume,
            "industry": member.industry,
            "included": member.included,
            "include_reasons": member.include_reasons,
            "exclude_reasons": member.exclude_reasons,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def format_progress_bar(index: int, total: int, width: int = 24) -> str:
    if total <= 0:
        return "[" + "-" * width + "]"
    filled = round(width * index / total)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def print_ingest_progress(event: dict) -> None:
    bar = format_progress_bar(int(event["index"]), int(event["total"]))
    prefix = (
        f"{bar} {event['index']}/{event['total']} "
        f"success={event['success']} failed={event['failed']}"
    )
    if event["event"] == "start":
        print(f"{prefix} running {event['job_id']}", flush=True)
    elif event["event"] == "success":
        print(
            f"{prefix} done {event['job_id']} "
            f"read={event['rows_read']} written={event['rows_written']}",
            flush=True,
        )
    elif event["event"] == "failed":
        print(f"{prefix} failed {event['job_id']} error={event['error']}", flush=True)


def _append_lhb_daily_watchlist_diagnostics_summary(
    *,
    summary_path: str | Path,
    report_paths: dict[str, str],
) -> None:
    path = Path(summary_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        payload = {"summary": {}, "paths": {}}
    payload.setdefault("paths", {})
    payload["paths"]["watchlist_diagnostics"] = report_paths["full_csv_path"]
    payload["paths"]["watchlist_diagnostics_must_watch"] = report_paths["must_watch_csv_path"]
    payload["paths"]["watchlist_diagnostics_markdown"] = report_paths["markdown_path"]
    payload.setdefault("summary", {})
    payload["summary"]["watchlist_diagnostics_built"] = True
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _store_watchlist_diagnostics_signals(diagnostics: pd.DataFrame) -> int:
    if diagnostics.empty:
        return 0

    rows: list[dict[str, object]] = []
    for record in diagnostics.to_dict("records"):
        watch_group = str(record.get("watch_group") or "candidate")
        risk_note = str(record.get("risk_note") or "").strip()
        rows.append(
            {
                "watchlist_id": "diagnostics",
                "trade_date": record.get("trade_date"),
                "asset_id": record.get("asset_id"),
                "stock_code": record.get("ts_code") or record.get("stock_code"),
                "stock_name": record.get("stock_name"),
                "priority": _diagnostics_priority(record),
                "signal_score": record.get("score_total") or 0.0,
                "primary_signal": watch_group,
                "signal_tags": [watch_group],
                "risk_tags": [risk_note] if risk_note else [],
                "must_watch": bool(watch_group in {"risk_watch", "opportunity_watch"} or record.get("opportunity_flag")),
                "reason_json": _json_safe_diagnostics_reason(record),
                "output_version": record.get("diagnostics_rule_version") or "watchlist_diagnostics",
            }
        )
    return store_watchlist_daily_signals(pd.DataFrame(rows))


def _diagnostics_priority(record: dict[str, object]) -> int:
    for key in ("watch_priority", "score_rank"):
        value = record.get(key)
        try:
            if pd.isna(value):
                continue
        except Exception:
            pass
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 999


def _json_safe_diagnostics_reason(record: dict[str, object]) -> dict[str, object]:
    keys = [
        "score_rank",
        "score_total",
        "watch_group",
        "watch_reason",
        "diagnostic_reason",
        "risk_note",
        "opportunity_note",
        "exit_signal",
        "exit_reason",
        "lhb_shortline_watch_group",
        "lhb_shortline_watch_reason",
        "event_structure",
        "failure_flag",
        "case_event_type",
        "industry_code",
        "industry_name",
        "market_regime",
        "market_risk_level",
        "entry_allowed",
        "diagnostics_rule_version",
    ]
    return {key: _json_safe_scalar(record.get(key)) for key in keys if not _is_json_missing(record.get(key))}


def _json_safe_scalar(value: object) -> object:
    if _is_json_missing(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe_scalar(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_scalar(item) for item in value]
    if isinstance(value, (int, float, bool, str)):
        return value
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(value)


def _is_json_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, tuple, dict)):
        return False
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def add_minute_backfill_watchdog_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument(
        "--freq",
        choices=["1min", "5min", "15min", "30min", "60min"],
        default="5min",
    )
    parser.add_argument(
        "--adjust-types",
        type=parse_adjust_types,
        default=["raw", "qfq"],
    )
    parser.add_argument("--max-jobs", type=int, default=1200)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--stale-after-minutes", type=int, default=20)
    parser.add_argument("--run-timeout-seconds", type=int, default=1800)
    parser.add_argument("--output-dir", default="outputs/research")
    parser.add_argument("--report-target", required=True)
    parser.add_argument("--report-account", default="jarvis")
    parser.add_argument("--openclaw-bin", default="openclaw")
    parser.add_argument("--report-dry-run", action="store_true")


def run_minute_backfill_watchdog_command(args: argparse.Namespace) -> None:
    result = run_minute_backfill_watchdog(
        start_date=args.start_date,
        end_date=args.end_date,
        freq=args.freq,
        adjust_types=args.adjust_types,
        max_jobs=args.max_jobs,
        workers=args.workers,
        stale_after_minutes=args.stale_after_minutes,
        run_timeout_seconds=args.run_timeout_seconds,
        report_target=args.report_target,
        report_account=args.report_account,
        openclaw_bin=args.openclaw_bin,
        report_dry_run=args.report_dry_run,
    )
    delta_success = (
        int(result["post_summary"]["success_jobs"])
        - int(result["pre_summary"]["success_jobs"])
    )
    print(f"minute_backfill_watchdog|action|{result['status']['watchdog_action']}")
    print(f"minute_backfill_watchdog|delta_success|{delta_success}")
    print(f"minute_backfill_watchdog|delta_rows|{result['run_result']['rows']}")
    if "work_remaining" in result["status"]:
        print(f"minute_backfill_watchdog|work_remaining|{result['status']['work_remaining']}")


def add_technical_feature_watchdog_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--lookback-bars", type=int, default=260)
    parser.add_argument(
        "--adjust-type",
        choices=["raw", "qfq", "hfq"],
        default="qfq",
    )
    parser.add_argument("--source-data-version")
    parser.add_argument("--sleep-between-runs-seconds", type=float, default=0.0)


def add_factor_gate_watchdog_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--factor-names", type=parse_factor_names)
    parser.add_argument("--validation-start-date")
    parser.add_argument("--horizons", default="5,10,20,60")
    parser.add_argument("--primary-horizon", type=int, default=5)
    parser.add_argument("--calc-version", default="v1")
    parser.add_argument("--score-version", default="manual_v1")
    parser.add_argument("--quantiles", type=int, default=5)
    parser.add_argument("--top-n", type=int, default=30)


def run_technical_feature_watchdog_command(args: argparse.Namespace) -> None:
    result = run_technical_feature_backfill_watchdog(
        start_date=args.start_date,
        end_date=args.end_date,
        adjust_type=args.adjust_type,
        lookback_bars=args.lookback_bars,
        source_data_version=args.source_data_version,
        max_jobs=args.max_jobs,
        workers=args.workers,
        stale_after_minutes=args.stale_after_minutes,
        run_timeout_seconds=args.run_timeout_seconds,
        sleep_between_runs_seconds=args.sleep_between_runs_seconds,
        report_target=args.report_target,
        report_account=args.report_account,
        openclaw_bin=args.openclaw_bin,
        report_dry_run=args.report_dry_run,
    )
    delta_success = result["post_summary"].success_tasks - result["pre_summary"].success_tasks
    delta_rows = result["post_summary"].total_rows_written - result["pre_summary"].total_rows_written
    run_result = result.get("run_result", {})
    print(f"technical_feature_watchdog|action|{result['status'].watchdog_action}")
    print(f"technical_feature_watchdog|delta_success|{delta_success}")
    print(f"technical_feature_watchdog|delta_rows|{max(0, delta_rows)}")
    print(f"technical_feature_watchdog|work_remaining|{result['status'].work_remaining}")
    for key in (
        "batch_start_date",
        "batch_end_date",
        "batch_size_days",
        "worker_count",
        "compute_seconds",
        "sleep_between_runs_seconds",
        "rows_written",
        "days_per_hour",
        "rows_per_hour",
        "timed_out",
    ):
        print(f"technical_feature_watchdog|{key}|{run_result.get(key, '')}")


def run_factor_gate_watchdog_command(args: argparse.Namespace) -> None:
    horizons = [int(value.strip()) for value in args.horizons.split(",") if value.strip()]
    result = run_factor_gate_batch_watchdog(
        start_date=args.start_date,
        end_date=args.end_date,
        validation_start_date=args.validation_start_date,
        horizons=horizons,
        primary_horizon=args.primary_horizon,
        calc_version=args.calc_version,
        score_version=args.score_version,
        quantiles=args.quantiles,
        top_n=args.top_n,
        factor_names=args.factor_names,
        max_jobs=args.max_jobs,
        workers=args.workers,
        stale_after_minutes=args.stale_after_minutes,
        run_timeout_seconds=args.run_timeout_seconds,
        report_target=args.report_target,
        report_account=args.report_account,
        openclaw_bin=args.openclaw_bin,
        report_dry_run=args.report_dry_run,
    )
    delta_success = result["post_summary"].success_tasks - result["pre_summary"].success_tasks
    delta_rows = result["post_summary"].total_rows_written - result["pre_summary"].total_rows_written
    print(f"factor_gate_watchdog|action|{result['status'].watchdog_action}")
    print(f"factor_gate_watchdog|delta_success|{delta_success}")
    print(f"factor_gate_watchdog|delta_rows|{max(0, delta_rows)}")
    print(f"factor_gate_watchdog|work_remaining|{result['status'].work_remaining}")


def print_factor_backfill_progress(event: dict) -> None:
    if event["event"] == "start":
        print(
            "factor_daily_backfill|start|"
            f"{event['trade_date']}|{event['index']}|{event['total']}",
            flush=True,
        )
    elif event["event"] == "done":
        print(
            "factor_daily_backfill|done|"
            f"{event['trade_date']}|{event['index']}|{event['total']}|{event['factor_rows']}",
            flush=True,
        )


def factor_backfill_progress_printer(interval: int):
    progress_interval = max(1, int(interval))

    def print_progress(event: dict) -> None:
        if event["event"] == "done" and progress_interval > 1:
            index = int(event["index"])
            total = int(event["total"])
            if index % progress_interval != 0 and index != total:
                return
        if event["event"] == "start" and progress_interval > 1:
            return
        print_factor_backfill_progress(event)

    return print_progress


def print_technical_feature_backfill_progress(event: dict) -> None:
    if event["event"] == "start":
        print(
            "technical_feature_daily_backfill|start|"
            f"{event['trade_date']}|{event['index']}|{event['total']}",
            flush=True,
        )
    elif event["event"] == "done":
        print(
            "technical_feature_daily_backfill|done|"
            f"{event['trade_date']}|{event['index']}|{event['total']}|{event['feature_rows']}",
            flush=True,
        )


def technical_feature_backfill_progress_printer(interval: int):
    progress_interval = max(1, int(interval))

    def print_progress(event: dict) -> None:
        if event["event"] == "done" and progress_interval > 1:
            index = int(event["index"])
            total = int(event["total"])
            if index % progress_interval != 0 and index != total:
                return
        if event["event"] == "start" and progress_interval > 1:
            return
        print_technical_feature_backfill_progress(event)

    return print_progress


def intraday_feature_backfill_progress_printer():
    def print_progress(event: dict) -> None:
        if event["event"] == "done":
            print(
                "intraday_feature_daily_backfill|done|"
                f"{event['trade_date']}|{event['index']}|{event['total']}|"
                f"stock_rows={event['stock_rows']}|industry_rows={event['industry_rows']}",
                flush=True,
            )

    return print_progress


def summarize_multi_horizon_report(report: dict) -> dict:
    summaries = {}
    for horizon, horizon_report in report.get("reports", {}).items():
        summaries[str(horizon)] = {
            "ic_summary": horizon_report.get("ic_summary", {}),
            "rank_ic_summary": horizon_report.get("rank_ic_summary", {}),
        }
    return {
        "factor_name": report.get("factor_name"),
        "horizons": report.get("horizons", []),
        "reports": summaries,
    }


def _load_p8_decision_outcome_inputs(
    *,
    start_date: str,
    end_date: str,
    review_session_id: str | None,
    decision_events_csv: str | None,
    bars_csv: str | None,
    service: str,
    adjust_type: str,
    max_horizon: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if decision_events_csv:
        decision_events = pd.read_csv(decision_events_csv)
    else:
        decision_events = _load_p8_decision_events_from_db(
            start_date=start_date,
            end_date=end_date,
            review_session_id=review_session_id,
            service=service,
        )

    if bars_csv:
        bars = pd.read_csv(bars_csv)
    else:
        bars = _load_p8_market_bars_from_db(
            start_date=start_date,
            end_date=end_date,
            service=service,
            adjust_type=adjust_type,
            max_horizon=max_horizon,
        )
    return decision_events, bars


def _load_p8_decision_events_from_db(
    *,
    start_date: str,
    end_date: str,
    review_session_id: str | None,
    service: str,
) -> pd.DataFrame:
    params: list[object] = [start_date, end_date]
    session_filter = ""
    if review_session_id:
        session_filter = "AND review_session_id = %s"
        params.append(review_session_id)
    sql = f"""
        SELECT
            event_id, review_session_id, review_date, asset_id, stock_code,
            stock_name, decision_label, evidence_artifact_id, evidence_path,
            source_context, requires_follow_up, follow_up_note, notes,
            manual_review_required, auto_trade_enabled, source_artifact_path
        FROM ops.operator_decision_event
        WHERE review_date BETWEEN %s AND %s
        {session_filter}
        ORDER BY review_date, review_session_id, event_id
    """
    with connect(service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, params))


def _load_p8_market_bars_from_db(
    *,
    start_date: str,
    end_date: str,
    service: str,
    adjust_type: str,
    max_horizon: int,
) -> pd.DataFrame:
    lookahead_days = max(1, int(max_horizon)) * 3
    extended_end_date = str((pd.Timestamp(end_date) + pd.Timedelta(days=lookahead_days)).date())
    sql = """
        SELECT asset_id, trade_date, close, high, low
        FROM market_daily_bar
        WHERE trade_date BETWEEN %s AND %s
          AND adjust_type = %s
        ORDER BY asset_id, trade_date
    """
    with connect(service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, [start_date, extended_end_date, adjust_type]))


def _load_p9_outcome_analytics_inputs(
    *,
    start_date: str,
    end_date: str,
    review_session_id: str | None,
    outcome_events_csv: str | None,
    service: str,
    limit: int,
) -> pd.DataFrame:
    if outcome_events_csv:
        events = pd.read_csv(outcome_events_csv)
        return _parse_p9_outcome_event_maps(events)
    return _load_p9_outcome_events_from_db(
        start_date=start_date,
        end_date=end_date,
        review_session_id=review_session_id,
        service=service,
        limit=limit,
    )


def _load_p9_outcome_events_from_db(
    *,
    start_date: str,
    end_date: str,
    review_session_id: str | None,
    service: str,
    limit: int,
) -> pd.DataFrame:
    params: list[object] = [start_date, end_date]
    session_filter = ""
    if review_session_id:
        session_filter = "AND review_session_id = %s"
        params.append(review_session_id)
    params.append(max(1, int(limit)))
    sql = f"""
        SELECT
            outcome_event_id, run_id, decision_event_id, review_session_id,
            review_date, asset_id, stock_code, stock_name, decision_label,
            source_context, outcome_status, available_future_bars,
            forward_returns, max_high_returns, max_low_drawdowns,
            manual_review_required, auto_trade_enabled, metadata
        FROM ops.operator_decision_outcome_event
        WHERE review_date BETWEEN %s AND %s
        {session_filter}
        ORDER BY review_date, review_session_id, outcome_event_id
        LIMIT %s
    """
    with connect(service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, params))


def _parse_p9_outcome_event_maps(events: pd.DataFrame) -> pd.DataFrame:
    parsed = events.copy()
    for column in ["forward_returns", "max_high_returns", "max_low_drawdowns", "metadata"]:
        if column in parsed.columns:
            parsed[column] = parsed[column].map(_parse_json_cell)
    return parsed


def _parse_json_cell(value):
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{":
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stock-research")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("apply-schema")
    subparsers.add_parser("apply-research-schema")
    subparsers.add_parser("sync-assets")
    subparsers.add_parser("sync-core-assets")
    subparsers.add_parser("sync-stock-chinese-names")

    dashboard_api = subparsers.add_parser("dashboard-api")
    dashboard_api.add_argument("--host", default="127.0.0.1")
    dashboard_api.add_argument("--port", type=int, default=8765)

    dashboard_bootstrap_admin = subparsers.add_parser("dashboard-bootstrap-admin")
    dashboard_bootstrap_admin.add_argument("--username", required=True)
    dashboard_bootstrap_admin.add_argument("--password", required=True)
    dashboard_bootstrap_admin.add_argument("--display-name", required=True)
    dashboard_bootstrap_admin.add_argument("--email", required=True)

    dashboard_enable_user = subparsers.add_parser("dashboard-enable-user")
    dashboard_enable_user.add_argument("--username", required=True)

    data_audit = subparsers.add_parser("data-audit")
    data_audit.add_argument("--expected-start-date", default="1990-12-01")

    daily_close_pipeline = subparsers.add_parser("daily-pipeline")
    daily_close_pipeline.add_argument("--date")
    daily_close_pipeline.add_argument(
        "--stage",
        choices=["all", "daily", "minute5", "deps", "health", "retry_failed", "status"],
        default="all",
    )
    daily_close_pipeline.add_argument("--force", action="store_true")

    intraday_pipeline = subparsers.add_parser("intraday-pipeline")
    intraday_pipeline.add_argument("--date")
    intraday_pipeline.add_argument("--previous-date")
    intraday_pipeline.add_argument(
        "--stage",
        choices=["all", "universe", "minute5", "sentiment", "status"],
        default="all",
    )
    intraday_pipeline.add_argument("--top-n", type=int)
    intraday_pipeline.add_argument("--score-version")
    intraday_pipeline.add_argument("--watchlist-id")
    intraday_pipeline.add_argument("--portfolio-id")

    subparsers.add_parser("finance-audit")

    news_source_backfill = subparsers.add_parser("news-source-backfill")
    news_source_backfill.add_argument("--start-date", required=True)
    news_source_backfill.add_argument("--end-date", required=True)
    news_source_backfill.add_argument("--provider", default="tushare")
    news_source_backfill.add_argument("--token")
    news_source_backfill.add_argument("--output-dir")

    topn_news_source_backfill = subparsers.add_parser("topn-news-source-backfill")
    topn_news_source_backfill.add_argument("--candidates-path", required=True)
    topn_news_source_backfill.add_argument(
        "--provider",
        choices=["akshare_stock_news_em"],
        required=True,
    )
    topn_news_source_backfill.add_argument("--trade-date", required=True)
    topn_news_source_backfill.add_argument("--output-dir")

    historical_top10_news_backfill = subparsers.add_parser("historical-top10-news-backfill")
    historical_top10_news_backfill.add_argument("--top10-path", required=True)
    historical_top10_news_backfill.add_argument("--start-date", required=True)
    historical_top10_news_backfill.add_argument("--end-date", required=True)
    historical_top10_news_backfill.add_argument(
        "--providers",
        nargs="+",
        choices=HISTORICAL_TOP10_NEWS_PROVIDERS,
        default=[
            "eastmoney_individual_notice",
            "eastmoney_research_report",
        ],
    )
    historical_top10_news_backfill.add_argument("--sample-trade-dates", type=int)
    historical_top10_news_backfill.add_argument("--output-dir")

    review_top10_historical_news_effectiveness = subparsers.add_parser(
        "review-top10-historical-news-effectiveness"
    )
    review_top10_historical_news_effectiveness.add_argument("--base-dir", required=True)
    review_top10_historical_news_effectiveness.add_argument("--adjust-type", default="qfq")
    review_top10_historical_news_effectiveness.add_argument("--output-dir", required=True)
    market_style_switch = subparsers.add_parser("market-style-switch-v1-backtest")
    market_style_switch.add_argument("--start-date", required=True)
    market_style_switch.add_argument("--end-date", required=True)
    market_style_switch.add_argument("--emotion-path", required=True)
    market_style_switch.add_argument("--funnel-detail-path", required=True)
    market_style_switch.add_argument("--output-dir", required=True)
    market_style_switch.add_argument("--top-n", type=int, default=5)
    market_style_switch.add_argument("--defensive-industry-keywords")
    market_style_switch.add_argument("--adjust-type", choices=["raw", "qfq", "hfq"], default="hfq")

    market_regime_confirmation = subparsers.add_parser("market-regime-confirmation-v1-backtest")
    market_regime_confirmation.add_argument("--start-date", required=True)
    market_regime_confirmation.add_argument("--end-date", required=True)
    market_regime_confirmation.add_argument("--emotion-path", required=True)
    market_regime_confirmation.add_argument("--funnel-detail-path", required=True)
    market_regime_confirmation.add_argument("--output-dir", required=True)
    market_regime_confirmation.add_argument("--policy-event-path")
    market_regime_confirmation.add_argument("--top-n", type=int, default=5)
    market_regime_confirmation.add_argument("--adjust-type", choices=["raw", "qfq", "hfq"], default="hfq")

    news_feature_backfill = subparsers.add_parser("news-feature-backfill")
    news_feature_backfill.add_argument("--events-path", required=True)
    news_feature_backfill.add_argument("--start-date", required=True)
    news_feature_backfill.add_argument("--end-date", required=True)
    news_feature_backfill.add_argument("--mode", choices=["replay", "live"], default="replay")
    news_feature_backfill.add_argument("--output-dir")

    news_feature_diagnostics = subparsers.add_parser("news-feature-diagnostics")
    news_feature_diagnostics.add_argument("--feature-path", required=True)
    news_feature_diagnostics.add_argument("--output-dir")

    topn_news_enrichment = subparsers.add_parser("topn-news-enrichment")
    topn_news_enrichment.add_argument("--candidates-path", required=True)
    topn_news_enrichment.add_argument("--news-features-path", required=True)
    topn_news_enrichment.add_argument("--output-dir")

    free_enrichment_backfill = subparsers.add_parser("free-enrichment-backfill")
    free_enrichment_backfill.add_argument(
        "--dataset",
        choices=["all", "lhb", "holder", "repurchase", "survey", "forecast", "express", "mainbiz"],
        default="all",
    )
    free_enrichment_backfill.add_argument("--start-date", required=True)
    free_enrichment_backfill.add_argument("--end-date", required=True)
    free_enrichment_backfill.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research/free_enrichment",
    )
    free_enrichment_backfill.add_argument("--batch-size", type=int, default=100)
    free_enrichment_backfill.add_argument("--sleep-seconds", type=float, default=1.0)
    free_enrichment_backfill.add_argument("--limit", type=int)
    free_enrichment_backfill.add_argument("--dry-run", action="store_true")
    free_enrichment_backfill.add_argument("--service", default=SETTINGS.research_service)

    data_quality = subparsers.add_parser("data-quality")
    data_quality.add_argument("--expected-start-date", default="1990-12-01")
    data_quality.add_argument("--start-date")
    data_quality.add_argument("--end-date")
    data_quality.add_argument(
        "--horizons",
        type=parse_research_horizons,
        default=[5, 10, 20, 60],
    )
    data_quality.add_argument("--factor-names", type=parse_factor_names)
    data_quality.add_argument("--calc-version", default="v1")
    data_quality.add_argument("--min-label-dates", type=int, default=20)
    data_quality.add_argument("--require-industry-membership", action="store_true")
    data_quality.add_argument("--json", action="store_true")

    seed_trading_calendar = subparsers.add_parser("seed-trading-calendar")
    seed_trading_calendar.add_argument("--start-date", required=True)
    seed_trading_calendar.add_argument("--end-date", required=True)
    seed_trading_calendar.add_argument("--exchanges", type=parse_exchanges, required=True)
    seed_trading_calendar.add_argument("--source-version", required=True)

    sync_tushare_trading_calendar = subparsers.add_parser("sync-tushare-trading-calendar")
    sync_tushare_trading_calendar.add_argument("--start-date", required=True)
    sync_tushare_trading_calendar.add_argument("--end-date", required=True)
    sync_tushare_trading_calendar.add_argument(
        "--exchanges",
        type=parse_exchanges,
        default=["SH", "SZ"],
    )
    sync_tushare_trading_calendar.add_argument(
        "--source-version",
        default="tushare_trade_cal_v1",
    )
    sync_tushare_trading_calendar.add_argument("--max-retries", type=int, default=3)
    sync_tushare_trading_calendar.add_argument("--retry-sleep-seconds", type=float, default=70.0)
    sync_tushare_trading_calendar.add_argument("--service", default=SETTINGS.research_service)

    sync_asset_lifecycle = subparsers.add_parser("sync-asset-lifecycle")
    sync_asset_lifecycle.add_argument("--source-version", required=True)

    create_backfill = subparsers.add_parser("create-backfill-run")
    create_backfill.add_argument("--run-id", required=True)
    create_backfill.add_argument("--dataset", required=True)
    create_backfill.add_argument("--source", required=True)
    create_backfill.add_argument("--source-version", required=True)
    create_backfill.add_argument("--start-date", required=True)
    create_backfill.add_argument("--end-date", required=True)
    create_backfill.add_argument("--months-per-partition", type=int, default=1)

    backfill_status = subparsers.add_parser("backfill-status")
    backfill_status.add_argument("--run-id", required=True)

    claim_backfill = subparsers.add_parser("claim-backfill-tasks")
    claim_backfill.add_argument("--run-id", required=True)
    claim_backfill.add_argument("--limit", type=int, default=10)

    mark_backfill_success = subparsers.add_parser("mark-backfill-task-success")
    mark_backfill_success.add_argument("--task-id", required=True)
    mark_backfill_success.add_argument("--rows-read", required=True, type=int)
    mark_backfill_success.add_argument("--rows-written", required=True, type=int)

    mark_backfill_failed = subparsers.add_parser("mark-backfill-task-failed")
    mark_backfill_failed.add_argument("--task-id", required=True)
    mark_backfill_failed.add_argument("--error-message", required=True)

    reset_stale_backfill = subparsers.add_parser("reset-stale-backfill-tasks")
    reset_stale_backfill.add_argument("--dataset", required=True)
    reset_stale_backfill.add_argument("--older-than-minutes", type=int, default=60)

    asset_status = subparsers.add_parser("build-asset-status")
    asset_status.add_argument("--start-date")
    asset_status.add_argument("--end-date")
    asset_status.add_argument("--adjust-type", default="hfq")

    adjustment_factors = subparsers.add_parser("build-adjustment-factors")
    adjustment_factors.add_argument("--start-date")
    adjustment_factors.add_argument("--end-date")
    adjustment_factors.add_argument("--source-version", default="derived_market_daily_bar_v1")

    corporate_actions = subparsers.add_parser("build-corporate-actions")
    corporate_actions.add_argument("--start-date")
    corporate_actions.add_argument("--end-date")
    corporate_actions.add_argument("--source-version", default="derived_adjustment_factor_v1")
    corporate_actions.add_argument(
        "--factor-source-version",
        default="derived_market_daily_bar_v1",
    )

    industry_bars = subparsers.add_parser("build-industry-bars")
    industry_bars.add_argument("--start-date")
    industry_bars.add_argument("--end-date")
    industry_bars.add_argument("--industry-system", default="csrc")
    industry_bars.add_argument("--adjust-type", default="hfq")

    industry_memberships = subparsers.add_parser("sync-industry-memberships")
    industry_memberships.add_argument("--trade-date", required=True)

    index_bars = subparsers.add_parser("sync-index-bars")
    index_bars.add_argument("--start-date", required=True)
    index_bars.add_argument("--end-date", required=True)

    index_constituents = subparsers.add_parser("sync-index-constituents")
    index_constituents.add_argument("--trade-date", required=True)
    index_constituents.add_argument("--index-ids", type=parse_index_ids)
    index_constituents.add_argument("--source-version", required=True)

    baostock_finance = subparsers.add_parser("sync-baostock-finance")
    baostock_finance.add_argument("--year", required=True, type=int)
    baostock_finance.add_argument("--quarter", required=True, type=int)
    baostock_finance.add_argument("--limit", type=int)
    baostock_finance.add_argument("--offset", type=int, default=0)

    baostock_minutes = subparsers.add_parser("sync-baostock-minute-bars")
    baostock_minutes.add_argument("--start-date", default="2024-01-01")
    baostock_minutes.add_argument("--end-date", required=True)
    baostock_minutes.add_argument(
        "--freq",
        choices=["1min", "5min", "15min", "30min", "60min"],
        default="5min",
    )
    baostock_minutes.add_argument("--adjust-types", type=parse_adjust_types, default=["raw", "qfq"])
    baostock_minutes.add_argument("--limit-assets", type=int)
    baostock_minutes.add_argument("--sleep-seconds", type=float, default=0.0)

    tushare_auction = subparsers.add_parser("sync-tushare-auction-bars")
    tushare_auction.add_argument("--start-date", required=True)
    tushare_auction.add_argument("--end-date", required=True)
    tushare_auction.add_argument(
        "--auction-phases",
        type=parse_auction_phases,
        default=["open_call", "close_call"],
    )
    tushare_auction.add_argument("--ts-codes", type=parse_ts_codes, required=True)
    tushare_auction.add_argument("--trade-dates", type=parse_trade_dates)
    tushare_auction.add_argument("--sleep-seconds", type=float, default=1.3)

    tushare_auction_full_backfill = subparsers.add_parser("tushare-auction-full-backfill-v1")
    tushare_auction_full_backfill.add_argument("--start-date", required=True)
    tushare_auction_full_backfill.add_argument("--end-date", required=True)
    tushare_auction_full_backfill.add_argument(
        "--auction-phases",
        type=parse_auction_phases,
        default=["open_call"],
    )
    tushare_auction_full_backfill.add_argument("--min-rows-per-date", type=int, default=1000)
    tushare_auction_full_backfill.add_argument("--max-calls", type=int, default=500)
    tushare_auction_full_backfill.add_argument("--sleep-seconds", type=float, default=1.3)
    tushare_auction_full_backfill.add_argument("--token")
    tushare_auction_full_backfill.add_argument("--dry-run", action="store_true")
    tushare_auction_full_backfill.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research/tushare_auction_full_backfill",
    )

    lhb_auction_backfill_plan = subparsers.add_parser("lhb-auction-backfill-plan-v1")
    lhb_auction_backfill_plan.add_argument("--candidate-paths", type=parse_candidate_paths, required=True)
    lhb_auction_backfill_plan.add_argument("--start-date", required=True)
    lhb_auction_backfill_plan.add_argument("--end-date", required=True)
    lhb_auction_backfill_plan.add_argument(
        "--auction-phases",
        type=parse_auction_phases,
        default=["open_call", "close_call"],
    )
    lhb_auction_backfill_plan.add_argument("--trade-dates", type=parse_trade_dates, required=True)
    lhb_auction_backfill_plan.add_argument("--min-coverage-ratio", type=float, default=0.95)
    lhb_auction_backfill_plan.add_argument("--output-dir", required=True)

    lhb_auction_backfill_run = subparsers.add_parser("lhb-auction-backfill-run-v1")
    lhb_auction_backfill_run.add_argument("--plan-path", required=True)
    lhb_auction_backfill_run.add_argument("--ts-codes-path", required=True)
    lhb_auction_backfill_run.add_argument("--max-calls", type=int, default=500)
    lhb_auction_backfill_run.add_argument("--sleep-seconds", type=float, default=1.3)
    lhb_auction_backfill_run.add_argument("--token")
    lhb_auction_backfill_run.add_argument("--output-dir", required=True)

    open_auction_minute_collect = subparsers.add_parser("collect-open-auction-minute-v1")
    open_auction_minute_collect.add_argument("--trade-date", default="auto")
    open_auction_minute_collect.add_argument("--universe-path", required=True)
    open_auction_minute_collect.add_argument("--start-time", default="09:15:00")
    open_auction_minute_collect.add_argument("--end-time", default="09:25:00")
    open_auction_minute_collect.add_argument("--sleep-seconds", type=float, default=0.2)
    open_auction_minute_collect.add_argument("--max-symbols", type=int)
    open_auction_minute_collect.add_argument("--retry-until-covered", action="store_true")
    open_auction_minute_collect.add_argument("--max-rounds", type=int, default=6)
    open_auction_minute_collect.add_argument("--round-sleep-seconds", type=float, default=300.0)
    open_auction_minute_collect.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research/open_auction_minute_collect",
    )

    open_auction_minute_cron = subparsers.add_parser("open-auction-minute-cron-entry")
    open_auction_minute_cron.add_argument("--project-dir", default="/Users/xiwei/stock_research")
    open_auction_minute_cron.add_argument("--universe-path", required=True)
    open_auction_minute_cron.add_argument(
        "--output-dir",
        default="outputs/research/open_auction_minute_collect",
    )
    open_auction_minute_cron.add_argument("--log-path", default="logs/open_auction_minute_collect.log")
    open_auction_minute_cron.add_argument("--primary-hour", type=int, default=9)
    open_auction_minute_cron.add_argument("--primary-minute", type=int, default=40)
    open_auction_minute_cron.add_argument("--retry-hour", type=int, default=15)
    open_auction_minute_cron.add_argument("--retry-minute", type=int, default=10)

    open_auction_spot_snapshot = subparsers.add_parser("collect-open-auction-spot-snapshot-v1")
    open_auction_spot_snapshot.add_argument("--trade-date", default="auto")
    open_auction_spot_snapshot.add_argument("--target-time", required=True)
    open_auction_spot_snapshot.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research/open_auction_spot_snapshot",
    )

    open_auction_spot_snapshot_cron = subparsers.add_parser("open-auction-spot-snapshot-cron-entry")
    open_auction_spot_snapshot_cron.add_argument("--project-dir", default="/Users/xiwei/stock_research")
    open_auction_spot_snapshot_cron.add_argument(
        "--output-dir",
        default="outputs/research/open_auction_spot_snapshot",
    )
    open_auction_spot_snapshot_cron.add_argument("--log-path", default="logs/open_auction_spot_snapshot.log")

    xtick_auction_detail = subparsers.add_parser("collect-xtick-auction-detail-v1")
    xtick_auction_detail.add_argument("--trade-date", required=True)
    xtick_auction_detail.add_argument(
        "--symbols",
        type=lambda value: parse_str_list(value, "--symbols"),
        default=["szm", "shm", "cyb", "kcb"],
    )
    xtick_auction_detail.add_argument("--token-env", default="XTICK_TOKEN")
    xtick_auction_detail.add_argument("--sleep-seconds", type=float, default=1.0)
    xtick_auction_detail.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research/xtick_auction_detail_collect",
    )

    xtick_auction_backfill_plan = subparsers.add_parser("xtick-auction-backfill-plan-v1")
    xtick_auction_backfill_plan.add_argument("--start-date", required=True)
    xtick_auction_backfill_plan.add_argument("--end-date", required=True)
    xtick_auction_backfill_plan.add_argument(
        "--symbols",
        type=lambda value: parse_str_list(value, "--symbols"),
        default=["szm", "shm", "cyb", "kcb"],
    )
    xtick_auction_backfill_plan.add_argument("--available-start-date", default="2026-05-10")
    xtick_auction_backfill_plan.add_argument("--min-existing-rows", type=int, default=1)
    xtick_auction_backfill_plan.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research/xtick_auction_detail_backfill",
    )

    xtick_auction_backfill_run = subparsers.add_parser("xtick-auction-backfill-run-v1")
    xtick_auction_backfill_run.add_argument("--plan-path", required=True)
    xtick_auction_backfill_run.add_argument("--max-tasks", type=int, default=1)
    xtick_auction_backfill_run.add_argument("--token-env", default="XTICK_TOKEN")
    xtick_auction_backfill_run.add_argument("--sleep-seconds", type=float, default=20.0)
    xtick_auction_backfill_run.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research/xtick_auction_detail_backfill",
    )

    xtick_auction_925_check = subparsers.add_parser("xtick-auction-925-check-v1")
    xtick_auction_925_check.add_argument("--start-date", required=True)
    xtick_auction_925_check.add_argument("--end-date", required=True)
    xtick_auction_925_check.add_argument("--source", default="xtick_dayupdate_bid")
    xtick_auction_925_check.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research/xtick_auction_detail_backfill",
    )

    lhb_auction_observation = subparsers.add_parser("lhb-auction-observation-v1")
    lhb_auction_observation.add_argument("--trades-path", required=True)
    lhb_auction_observation.add_argument("--start-date", required=True)
    lhb_auction_observation.add_argument("--end-date", required=True)
    lhb_auction_observation.add_argument("--ts-codes", type=parse_ts_codes, required=True)
    lhb_auction_observation.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_phase18_auction_scan = subparsers.add_parser("lhb-phase18-auction-rule-scan-v1")
    lhb_phase18_auction_scan.add_argument("--detail-path", required=True)
    lhb_phase18_auction_scan.add_argument("--rule-layer", default="follow_pool_core")
    lhb_phase18_auction_scan.add_argument(
        "--thresholds",
        type=parse_thresholds,
        default=[0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07],
    )
    lhb_phase18_auction_scan.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_phase18b_topn_rerank = subparsers.add_parser("lhb-phase18b-auction-topn-rerank-v1")
    lhb_phase18b_topn_rerank.add_argument("--detail-path", required=True)
    lhb_phase18b_topn_rerank.add_argument(
        "--top-n",
        type=lambda value: parse_int_list(value, "--top-n"),
        default=[5, 10],
    )
    lhb_phase18b_topn_rerank.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_phase18c_cash = subparsers.add_parser("lhb-phase18c-auction-cash-account-v1")
    lhb_phase18c_cash.add_argument("--lifecycle-trades-path", required=True)
    lhb_phase18c_cash.add_argument("--scored-candidates-path", required=True)
    lhb_phase18c_cash.add_argument(
        "--top-n",
        type=lambda value: parse_int_list(value, "--top-n"),
        default=[3, 5, 10],
    )
    lhb_phase18c_cash.add_argument("--max-positions", type=int, default=10)
    lhb_phase18c_cash.add_argument("--position-pct", type=float, default=0.10)
    lhb_phase18c_cash.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_phase18d_close_auction = subparsers.add_parser(
        "lhb-phase18d-close-auction-lifecycle-v1"
    )
    lhb_phase18d_close_auction.add_argument("--trades-path", required=True)
    lhb_phase18d_close_auction.add_argument("--strategy")
    lhb_phase18d_close_auction.add_argument("--top-n", type=int)
    lhb_phase18d_close_auction.add_argument("--start-date")
    lhb_phase18d_close_auction.add_argument("--end-date")
    lhb_phase18d_close_auction.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_phase18e_joint_exit = subparsers.add_parser(
        "lhb-phase18e-joint-exit-diagnostics-v1"
    )
    lhb_phase18e_joint_exit.add_argument("--account-trades-path", required=True)
    lhb_phase18e_joint_exit.add_argument("--auction-observation-path", required=True)
    lhb_phase18e_joint_exit.add_argument("--close-lifecycle-path", required=True)
    lhb_phase18e_joint_exit.add_argument("--intraday-indicator-path")
    lhb_phase18e_joint_exit.add_argument("--strategy")
    lhb_phase18e_joint_exit.add_argument("--top-n", type=int)
    lhb_phase18e_joint_exit.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_phase18f_tradable_exit = subparsers.add_parser(
        "lhb-phase18f-tradable-joint-exit-replay-v1"
    )
    lhb_phase18f_tradable_exit.add_argument("--account-trades-path", required=True)
    lhb_phase18f_tradable_exit.add_argument("--joint-state-detail-path", required=True)
    lhb_phase18f_tradable_exit.add_argument("--close-lifecycle-detail-path", required=True)
    lhb_phase18f_tradable_exit.add_argument("--minute-bars-path")
    lhb_phase18f_tradable_exit.add_argument("--selected-trades-path")
    lhb_phase18f_tradable_exit.add_argument("--strategy")
    lhb_phase18f_tradable_exit.add_argument("--top-n", type=int)
    lhb_phase18f_tradable_exit.add_argument("--freq", default="5min")
    lhb_phase18f_tradable_exit.add_argument("--adjust-type", default="raw")
    lhb_phase18f_tradable_exit.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    plan_minute_backfill = subparsers.add_parser("plan-baostock-minute-backfill")
    plan_minute_backfill.add_argument("--start-date", required=True)
    plan_minute_backfill.add_argument("--end-date", required=True)
    plan_minute_backfill.add_argument(
        "--freq",
        choices=["1min", "5min", "15min", "30min", "60min"],
        default="5min",
    )
    plan_minute_backfill.add_argument("--adjust-types", type=parse_adjust_types, default=["raw", "qfq"])
    plan_minute_backfill.add_argument("--batch-by", choices=["month"], default="month")
    plan_minute_backfill.add_argument("--output-dir", default="outputs/research")
    plan_minute_backfill.add_argument("--limit-assets", type=int)

    run_minute_backfill = subparsers.add_parser("run-baostock-minute-backfill")
    run_minute_backfill.add_argument("--start-date")
    run_minute_backfill.add_argument("--end-date")
    run_minute_backfill.add_argument(
        "--freq",
        choices=["1min", "5min", "15min", "30min", "60min"],
        default="5min",
    )
    run_minute_backfill.add_argument("--adjust-types", type=parse_adjust_types, default=["raw", "qfq"])
    run_minute_backfill.add_argument("--batch-by", choices=["month"], default="month")
    run_minute_backfill.add_argument("--max-jobs", type=int, default=50)
    run_minute_backfill.add_argument("--retry-failed", action="store_true")
    run_minute_backfill.add_argument("--sleep-seconds", type=float, default=0.5)
    run_minute_backfill.add_argument("--workers", type=int, default=1)

    benchmark_minute_backfill = subparsers.add_parser("benchmark-baostock-minute-backfill")
    benchmark_minute_backfill.add_argument("--start-date")
    benchmark_minute_backfill.add_argument("--end-date")
    benchmark_minute_backfill.add_argument(
        "--freq",
        choices=["1min", "5min", "15min", "30min", "60min"],
        default="5min",
    )
    benchmark_minute_backfill.add_argument("--adjust-types", type=parse_adjust_types, default=["raw"])
    benchmark_minute_backfill.add_argument("--batch-by", choices=["month"], default="month")
    benchmark_minute_backfill.add_argument("--max-jobs", type=int, default=300)
    benchmark_minute_backfill.add_argument("--retry-failed", action="store_true")
    benchmark_minute_backfill.add_argument("--sleep-seconds", type=float, default=0.1)
    benchmark_minute_backfill.add_argument(
        "--workers-list",
        dest="worker_counts",
        type=parse_worker_counts,
        default=[4, 8, 12, 16],
    )

    run_minute_backfill_range = subparsers.add_parser("run-baostock-minute-backfill-range")
    run_minute_backfill_range.add_argument("--start-date", required=True)
    run_minute_backfill_range.add_argument("--end-date", required=True)
    run_minute_backfill_range.add_argument(
        "--freq",
        choices=["1min", "5min", "15min", "30min", "60min"],
        default="5min",
    )
    run_minute_backfill_range.add_argument("--adjust-types", type=parse_adjust_types, default=["raw", "qfq"])
    run_minute_backfill_range.add_argument("--batch-by", choices=["month"], default="month")
    run_minute_backfill_range.add_argument("--max-jobs", type=int, default=500)
    run_minute_backfill_range.add_argument("--retry-failed", action="store_true")
    run_minute_backfill_range.add_argument("--sleep-seconds", type=float, default=0.1)
    run_minute_backfill_range.add_argument("--workers", type=int, default=1)
    run_minute_backfill_range.add_argument("--output-dir", default="outputs/research")
    run_minute_backfill_range.add_argument("--limit-assets", type=int)
    run_minute_backfill_range.add_argument("--report-target", required=True)
    run_minute_backfill_range.add_argument("--report-account", default="jarvis")
    run_minute_backfill_range.add_argument("--openclaw-bin", default="openclaw")
    run_minute_backfill_range.add_argument("--report-dry-run", action="store_true")

    minute_backfill_watchdog = subparsers.add_parser("minute-backfill-watchdog")
    add_minute_backfill_watchdog_arguments(minute_backfill_watchdog)

    backfill_watchdog = subparsers.add_parser("backfill-watchdog")
    backfill_watchdog.add_argument(
        "--adapter",
        choices=["minute", "technical-features", "factor-gate"],
        required=True,
    )
    add_minute_backfill_watchdog_arguments(backfill_watchdog)
    add_technical_feature_watchdog_arguments(backfill_watchdog)
    add_factor_gate_watchdog_arguments(backfill_watchdog)

    status_minute_backfill = subparsers.add_parser("baostock-minute-backfill-status")
    status_minute_backfill.add_argument("--output-dir", default="outputs/research")

    validate_minutes = subparsers.add_parser("validate-minute-bars")
    validate_minutes.add_argument("--start-date", required=True)
    validate_minutes.add_argument("--end-date", required=True)
    validate_minutes.add_argument(
        "--freq",
        choices=["1min", "5min", "15min", "30min", "60min"],
        default="5min",
    )
    validate_minutes.add_argument("--adjust-types", type=parse_adjust_types, default=["raw", "qfq"])
    validate_minutes.add_argument("--output-dir", default="outputs/research")
    validate_minutes.add_argument("--limit-rows", type=int)

    create_ingest = subparsers.add_parser("create-ingest-jobs")
    create_ingest.add_argument("--dataset", required=True)
    create_ingest.add_argument("--start-year", required=True, type=int)
    create_ingest.add_argument("--end-year", required=True, type=int)
    create_ingest.add_argument("--batch-size", required=True, type=int)

    run_ingest = subparsers.add_parser("run-ingest-jobs")
    run_ingest.add_argument("--dataset", required=True)
    run_ingest.add_argument("--limit-jobs", required=True, type=int)

    run_ingest_loop = subparsers.add_parser("run-ingest-loop")
    run_ingest_loop.add_argument("--dataset", required=True)
    run_ingest_loop.add_argument("--jobs-per-round", type=int, default=50)
    run_ingest_loop.add_argument("--sleep-seconds", type=int, default=10)
    run_ingest_loop.add_argument("--max-rounds", type=int)
    run_ingest_loop.add_argument("--workers", type=int, default=1)
    run_ingest_loop.add_argument("--report-target", required=True)
    run_ingest_loop.add_argument("--report-account", default="jarvis")
    run_ingest_loop.add_argument("--openclaw-bin", default="openclaw")
    run_ingest_loop.add_argument("--report-dry-run", action="store_true")

    ingest_status = subparsers.add_parser("ingest-status")
    ingest_status.add_argument("--dataset")

    reset_stale_ingest = subparsers.add_parser("reset-stale-ingest-jobs")
    reset_stale_ingest.add_argument("--dataset", required=True)
    reset_stale_ingest.add_argument("--older-than-minutes", type=int, default=60)

    load_bars = subparsers.add_parser("load-bars")
    load_bars.add_argument("--start-date")
    load_bars.add_argument("--end-date")
    load_bars.add_argument("--limit-tables", type=int)
    load_bars.add_argument("--archive-raw", action="store_true")

    quality = subparsers.add_parser("quality")
    quality.add_argument("--trade-date")

    features = subparsers.add_parser("features")
    features.add_argument("--trade-date", required=True)

    backfill_features = subparsers.add_parser("backfill-features")
    backfill_features.add_argument("--start-date")
    backfill_features.add_argument("--end-date")
    backfill_features.add_argument("--lookback-bars", type=int, default=120)
    backfill_features.add_argument("--adjust-type", default="hfq")
    backfill_features.add_argument("--workers", type=int, default=1)
    backfill_features.add_argument("--skip-complete", action="store_true")

    labels = subparsers.add_parser("labels")
    labels.add_argument("--end-date", required=True)

    backfill_labels = subparsers.add_parser("backfill-labels")
    backfill_labels.add_argument("--start-date")
    backfill_labels.add_argument("--end-date")
    backfill_labels.add_argument(
        "--horizons",
        type=parse_research_horizons,
        default=[5, 10, 20, 60],
    )
    backfill_labels.add_argument("--adjust-type", default="hfq")

    select = subparsers.add_parser("select")
    select.add_argument("--trade-date", required=True)
    select.add_argument("--top-n", type=int, default=20)

    report = subparsers.add_parser("report")
    report.add_argument("--trade-date", required=True)
    report.add_argument("--log-path", required=True)

    report_delivery_local = subparsers.add_parser("report-delivery-local")
    report_delivery_local.add_argument("--trade-date", required=True)
    report_delivery_local.add_argument("--input-dir", action="append", default=[])
    report_delivery_local.add_argument("--report-dir", action="append", default=[])
    report_delivery_local.add_argument("--run-card-dir", action="append", default=[])
    report_delivery_local.add_argument("--artifact-path", action="append", default=[])
    report_delivery_local.add_argument("--output-dir", required=True)
    report_delivery_local.add_argument("--dry-run", action="store_true", default=True)
    report_delivery_local.add_argument("--no-dry-run", dest="dry_run", action="store_false")

    report_delivery_openclaw_export = subparsers.add_parser("report-delivery-openclaw-export")
    report_delivery_openclaw_export.add_argument("--trade-date", required=True)
    report_delivery_openclaw_export.add_argument("--manifest", required=True)
    report_delivery_openclaw_export.add_argument("--output-dir", required=True)
    report_delivery_openclaw_export.add_argument("--dry-run", action="store_true", default=True)
    report_delivery_openclaw_export.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
    )
    report_delivery_openclaw_export.add_argument("--include-all", action="store_true")
    report_delivery_openclaw_export.add_argument(
        "--min-severity",
        choices=["info", "low", "medium", "high", "critical"],
        default="info",
    )

    report_delivery_feishu = subparsers.add_parser("report-delivery-feishu")
    report_delivery_feishu.add_argument("--trade-date", required=True)
    report_delivery_feishu.add_argument("--manifest", required=True)
    report_delivery_feishu.add_argument("--output-dir", required=True)
    report_delivery_feishu.add_argument("--include-all", action="store_true")
    report_delivery_feishu.add_argument(
        "--min-severity",
        choices=["info", "low", "medium", "high", "critical"],
        default="info",
    )

    report_delivery_feishu_send = subparsers.add_parser("report-delivery-feishu-send")
    report_delivery_feishu_send.add_argument("--trade-date", required=True)
    report_delivery_feishu_send.add_argument("--preview", required=True)
    report_delivery_feishu_send.add_argument("--output-dir", required=True)
    report_delivery_feishu_send.add_argument("--dry-run", action="store_true", default=True)
    report_delivery_feishu_send.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
    )
    report_delivery_feishu_send.add_argument("--webhook-url", default=os.environ.get("FEISHU_WEBHOOK_URL"))
    report_delivery_feishu_send.add_argument("--limit", type=int)
    report_delivery_feishu_send.add_argument("--allow-live-send", action="store_true")
    report_delivery_feishu_send.add_argument(
        "--severity-max",
        choices=["info", "low", "medium", "high", "critical"],
    )
    report_delivery_feishu_send.add_argument("--test-mode", action="store_true")

    agent_report = subparsers.add_parser("agent-report")
    agent_report.add_argument("--trade-date", required=True)
    agent_report.add_argument("--mode", choices=["topn", "watchlist"], required=True)
    agent_report.add_argument("--manifest", required=True)
    agent_report.add_argument("--output-dir", required=True)

    report_delivery_openclaw_send = subparsers.add_parser("report-delivery-openclaw-send")
    report_delivery_openclaw_send.add_argument("--trade-date", required=True)
    report_delivery_openclaw_send.add_argument("--manifest", required=True)
    report_delivery_openclaw_send.add_argument("--items", required=True)
    report_delivery_openclaw_send.add_argument("--output-dir", required=True)
    report_delivery_openclaw_send.add_argument("--dry-run", action="store_true", default=True)
    report_delivery_openclaw_send.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
    )
    report_delivery_openclaw_send.add_argument("--endpoint", default=os.environ.get("OPENCLAW_ENDPOINT"))
    report_delivery_openclaw_send.add_argument(
        "--timeout-seconds",
        default=os.environ.get("OPENCLAW_TIMEOUT_SECONDS", "10.0"),
    )
    report_delivery_openclaw_send.add_argument("--retry-count", type=int, default=0)
    report_delivery_openclaw_send.add_argument(
        "--retry-backoff-seconds",
        type=float,
        default=1.0,
    )
    report_delivery_openclaw_send.add_argument("--allow-live-send", action="store_true")
    report_delivery_openclaw_send.add_argument("--limit", type=int)
    report_delivery_openclaw_send.add_argument(
        "--route-allowlist",
        type=lambda value: parse_str_list(value, "--route-allowlist"),
        default=[],
    )
    report_delivery_openclaw_send.add_argument(
        "--severity-max",
        choices=["info", "low", "medium", "high", "critical"],
    )
    report_delivery_openclaw_send.add_argument("--test-mode", action="store_true")

    backtest_top20 = subparsers.add_parser("backtest-top20")
    backtest_top20.add_argument("--start-date", required=True)
    backtest_top20.add_argument("--end-date", required=True)
    backtest_top20.add_argument("--holding-days", required=True, type=parse_holding_days)
    backtest_top20.add_argument("--top-n", type=int, default=20)
    backtest_top20.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    portfolio_backtest = subparsers.add_parser("portfolio-backtest")
    portfolio_backtest.add_argument("--start-date", required=True)
    portfolio_backtest.add_argument("--end-date", required=True)
    portfolio_backtest.add_argument("--initial-cash", type=float, default=500000.0)
    portfolio_backtest.add_argument(
        "--top-ks",
        type=parse_top_ks,
        default="5,10",
    )
    portfolio_backtest.add_argument(
        "--holding-days",
        type=parse_holding_days,
        default="5,10,15,20,30",
    )
    portfolio_backtest.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    simulate_portfolio = subparsers.add_parser("simulate-portfolio")
    simulate_portfolio.add_argument("--start-date", required=True)
    simulate_portfolio.add_argument("--end-date", required=True)
    simulate_portfolio.add_argument("--initial-cash", type=float, default=500000.0)
    simulate_portfolio.add_argument(
        "--top-ks",
        type=parse_top_ks,
        default="5,10",
    )
    simulate_portfolio.add_argument(
        "--holding-days",
        type=parse_holding_days,
        default="5,10,15,20,30",
    )
    simulate_portfolio.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )
    simulate_portfolio.add_argument("--output-dir", required=True)

    generate_advice = subparsers.add_parser("generate-trade-advice")
    generate_advice.add_argument("--trade-date", required=True)
    generate_advice.add_argument("--simulation-state", required=True)
    generate_advice.add_argument("--candidates", required=True)
    generate_advice.add_argument("--output-dir", required=True)
    generate_advice.add_argument("--max-single-position-pct", type=float, default=0.10)
    generate_advice.add_argument("--max-industry-position-pct", type=float, default=0.30)
    generate_advice.add_argument("--target-total-exposure-pct", type=float, default=0.60)
    generate_advice.add_argument("--drawdown-defensive-threshold", type=float, default=-0.10)
    generate_advice.add_argument("--defensive-exposure-multiplier", type=float, default=0.50)

    retention_backtest = subparsers.add_parser("retention-backtest")
    retention_backtest.add_argument("--start-date", required=True)
    retention_backtest.add_argument("--end-date", required=True)
    retention_backtest.add_argument("--initial-cash", type=float, default=500000.0)
    retention_backtest.add_argument(
        "--top-ks",
        type=parse_top_ks,
        default="5,10",
    )
    retention_backtest.add_argument(
        "--variant",
        choices=["v1", "v2", "v3.1", "v31"],
        default="v1",
    )
    retention_backtest.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )
    retention_backtest.add_argument(
        "--cache-dir",
        default="/Users/xiwei/stock_research/cache/v3_1",
    )
    retention_backtest.add_argument("--commission-bps", type=float, default=0.0)
    retention_backtest.add_argument("--stamp-duty-bps", type=float, default=0.0)
    retention_backtest.add_argument("--slippage-bps", type=float, default=0.0)
    retention_backtest.add_argument("--min-amount", type=float)

    v31_cache = subparsers.add_parser("build-v31-cache")
    v31_cache.add_argument("--start-date", required=True)
    v31_cache.add_argument("--end-date", required=True)
    v31_cache.add_argument(
        "--cache-dir",
        default="/Users/xiwei/stock_research/cache/v3_1",
    )
    v31_cache.add_argument(
        "--format",
        choices=["auto", "parquet", "csv"],
        default="auto",
    )

    build_factor_daily = subparsers.add_parser("build-factor-daily")
    build_factor_daily.add_argument("--trade-date", required=True)
    build_factor_daily.add_argument("--lookback-bars", type=int, default=130)
    build_factor_daily.add_argument("--industry-system", default="csrc")

    research_preflight = subparsers.add_parser("research-preflight")
    research_preflight.add_argument("--start-date")
    research_preflight.add_argument("--end-date")
    research_preflight.add_argument(
        "--horizons",
        type=parse_research_horizons,
        default=[5, 10, 20, 60],
    )
    research_preflight.add_argument("--factor-names", type=parse_factor_names)
    research_preflight.add_argument("--calc-version", default="v1")
    research_preflight.add_argument("--min-label-dates", type=int, default=20)
    research_preflight.add_argument("--require-industry-membership", action="store_true")

    benchmark_industry_day = subparsers.add_parser("benchmark-industry-day")
    benchmark_industry_day.add_argument("--trade-date", required=True)
    benchmark_industry_day.add_argument("--industry-system", default="csrc")
    benchmark_industry_day.add_argument("--adjust-type", default="hfq")
    benchmark_industry_day.add_argument(
        "--no-cache",
        dest="use_cache",
        action="store_false",
        default=True,
    )

    backfill_industry_history = subparsers.add_parser("backfill-industry-history")
    backfill_industry_history.add_argument("--start-date", required=True)
    backfill_industry_history.add_argument("--end-date", required=True)
    backfill_industry_history.add_argument("--max-dates", required=True, type=int)
    backfill_industry_history.add_argument(
        "--frequency",
        choices=["daily", "monthly", "quarterly"],
        default="daily",
    )
    backfill_industry_history.add_argument("--industry-system", default="csrc")
    backfill_industry_history.add_argument("--adjust-type", default="hfq")
    backfill_industry_history.add_argument(
        "--no-cache",
        dest="use_cache",
        action="store_false",
        default=True,
    )

    backfill_factor_daily = subparsers.add_parser("backfill-factor-daily")
    backfill_factor_daily.add_argument("--start-date")
    backfill_factor_daily.add_argument("--end-date")
    backfill_factor_daily.add_argument("--lookback-bars", type=int, default=130)
    backfill_factor_daily.add_argument("--industry-system", default="csrc")
    backfill_factor_daily.add_argument("--workers", type=int, default=1)
    backfill_factor_daily.add_argument("--skip-complete", action="store_true")
    backfill_factor_daily.add_argument("--progress-interval", type=int, default=1)
    backfill_factor_daily.add_argument("--exact-window", action="store_true")

    backfill_approved_scores = subparsers.add_parser("backfill-approved-scores")
    backfill_approved_scores.add_argument("--start-date")
    backfill_approved_scores.add_argument("--end-date")
    backfill_approved_scores.add_argument("--score-version", default="manual_v1")
    backfill_approved_scores.add_argument("--calc-version", default="v1")
    backfill_approved_scores.add_argument("--adjust-type", default="hfq")

    score_factor_daily = subparsers.add_parser("score-factor-daily")
    score_factor_daily.add_argument("--trade-date", required=True)
    score_factor_daily.add_argument("--score-version", default="manual_v1")

    show_top_scores = subparsers.add_parser("show-top-scores")
    show_top_scores.add_argument("--trade-date", required=True)
    show_top_scores.add_argument("--score-version", default="manual_v1")
    show_top_scores.add_argument("--top-n", type=int, default=30)

    eval_factor = subparsers.add_parser("eval-factor")
    eval_factor.add_argument("--factor-name", required=True)
    eval_factor.add_argument("--start-date", required=True)
    eval_factor.add_argument("--end-date", required=True)
    eval_factor.add_argument("--horizon", type=int, default=5)
    eval_factor.add_argument("--quantiles", type=int, default=5)
    eval_factor.add_argument("--top-n", type=int, default=30)

    evaluate_factor_gate = subparsers.add_parser("evaluate-factor-gate")
    evaluate_factor_gate.add_argument("--factor-name", required=True)
    evaluate_factor_gate.add_argument("--start-date", required=True)
    evaluate_factor_gate.add_argument("--end-date", required=True)
    evaluate_factor_gate.add_argument("--horizons", default="5,10,20,60")
    evaluate_factor_gate.add_argument("--primary-horizon", type=int, default=5)
    evaluate_factor_gate.add_argument("--calc-version", default="v1")
    evaluate_factor_gate.add_argument("--score-version", default="manual_v1")
    evaluate_factor_gate.add_argument("--quantiles", type=int, default=5)
    evaluate_factor_gate.add_argument("--top-n", type=int, default=30)

    evaluate_factor_gate_batch = subparsers.add_parser("evaluate-factor-gate-batch")
    evaluate_factor_gate_batch.add_argument("--factor-names", type=parse_factor_names)
    evaluate_factor_gate_batch.add_argument("--start-date", required=True)
    evaluate_factor_gate_batch.add_argument("--end-date", required=True)
    evaluate_factor_gate_batch.add_argument("--validation-start-date")
    evaluate_factor_gate_batch.add_argument("--horizons", default="5,10,20,60")
    evaluate_factor_gate_batch.add_argument("--primary-horizon", type=int, default=5)
    evaluate_factor_gate_batch.add_argument("--calc-version", default="v1")
    evaluate_factor_gate_batch.add_argument("--score-version", default="manual_v1")
    evaluate_factor_gate_batch.add_argument("--quantiles", type=int, default=5)
    evaluate_factor_gate_batch.add_argument("--top-n", type=int, default=30)

    factor_validation_review = subparsers.add_parser("factor-validation-review")
    factor_validation_review.add_argument("--factor-name", required=True)
    factor_validation_review.add_argument("--factors", required=True)
    factor_validation_review.add_argument("--returns", required=True)
    factor_validation_review.add_argument("--segments")
    factor_validation_review.add_argument("--segment-col")
    factor_validation_review.add_argument("--split-date", required=True)
    factor_validation_review.add_argument(
        "--horizons",
        type=parse_research_horizons,
        default=[5, 10, 20, 60],
    )
    factor_validation_review.add_argument("--primary-horizon", type=int, default=5)
    factor_validation_review.add_argument("--factor-col", default="factor_value")
    factor_validation_review.add_argument("--min-abs-mean-ic", type=float, default=0.02)
    factor_validation_review.add_argument("--min-icir", type=float, default=0.3)
    factor_validation_review.add_argument("--min-ic-count", type=int, default=20)
    factor_validation_review.add_argument("--output-dir", required=True)

    intraday_factor_eval = subparsers.add_parser("intraday-factor-eval")
    intraday_factor_eval.add_argument("--start-date", required=True)
    intraday_factor_eval.add_argument("--end-date", required=True)
    intraday_factor_eval.add_argument(
        "--horizons",
        type=parse_research_horizons,
        default=[5, 10, 20, 60],
    )
    intraday_factor_eval.add_argument("--features", type=parse_factor_names)
    intraday_factor_eval.add_argument(
        "--freq",
        choices=["1min", "5min", "15min", "30min", "60min"],
        default="5min",
    )
    intraday_factor_eval.add_argument(
        "--adjust-type",
        choices=["raw", "qfq", "hfq"],
        default="raw",
    )
    intraday_factor_eval.add_argument("--industry-system", default="csrc")
    intraday_factor_eval.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research/intraday_factor_eval",
    )
    intraday_factor_eval.add_argument("--quantiles", type=int, default=5)
    intraday_factor_eval.add_argument("--top-n", type=int, default=30)

    intraday_risk_filter_backtest = subparsers.add_parser("intraday-risk-filter-backtest")
    intraday_risk_filter_backtest.add_argument("--start-date", required=True)
    intraday_risk_filter_backtest.add_argument("--end-date", required=True)
    intraday_risk_filter_backtest.add_argument("--score-version", default="manual_v1")
    intraday_risk_filter_backtest.add_argument(
        "--top-n-values",
        type=lambda value: parse_int_list(value, "--top-n-values"),
        default=[10, 20],
    )
    intraday_risk_filter_backtest.add_argument(
        "--rebalance-frequency",
        choices=["daily", "weekly"],
        default="daily",
    )
    intraday_risk_filter_backtest.add_argument("--transaction-cost-bps", type=float, default=20.0)
    intraday_risk_filter_backtest.add_argument(
        "--score-adjust-type",
        choices=["raw", "qfq", "hfq"],
        default="hfq",
    )
    intraday_risk_filter_backtest.add_argument(
        "--intraday-freq",
        choices=["1min", "5min", "15min", "30min", "60min"],
        default="5min",
    )
    intraday_risk_filter_backtest.add_argument(
        "--intraday-adjust-type",
        choices=["raw", "qfq", "hfq"],
        default="raw",
    )
    intraday_risk_filter_backtest.add_argument("--output-dir", required=True)

    intraday_risk_control_v2_backtest = subparsers.add_parser(
        "intraday-risk-control-v2-backtest"
    )
    intraday_risk_control_v2_backtest.add_argument("--start-date", required=True)
    intraday_risk_control_v2_backtest.add_argument("--end-date", required=True)
    intraday_risk_control_v2_backtest.add_argument("--score-version", default="manual_v1")
    intraday_risk_control_v2_backtest.add_argument(
        "--top-n-values",
        type=lambda value: parse_int_list(value, "--top-n-values"),
        default=[10, 20],
    )
    intraday_risk_control_v2_backtest.add_argument(
        "--rebalance-frequency",
        choices=["daily", "weekly"],
        default="daily",
    )
    intraday_risk_control_v2_backtest.add_argument("--transaction-cost-bps", type=float, default=20.0)
    intraday_risk_control_v2_backtest.add_argument(
        "--score-adjust-type",
        choices=["raw", "qfq", "hfq"],
        default="hfq",
    )
    intraday_risk_control_v2_backtest.add_argument(
        "--intraday-freq",
        choices=["1min", "5min", "15min", "30min", "60min"],
        default="5min",
    )
    intraday_risk_control_v2_backtest.add_argument(
        "--intraday-adjust-type",
        choices=["raw", "qfq", "hfq"],
        default="raw",
    )
    intraday_risk_control_v2_backtest.add_argument("--lookback", type=int, default=20)
    intraday_risk_control_v2_backtest.add_argument("--zscore-threshold", type=float, default=1.5)
    intraday_risk_control_v2_backtest.add_argument("--output-dir", required=True)

    market_emotion_state_v1 = subparsers.add_parser("market-emotion-state-v1-backfill")
    market_emotion_state_v1.add_argument("--start-date", required=True)
    market_emotion_state_v1.add_argument("--end-date", required=True)
    market_emotion_state_v1.add_argument(
        "--adjust-type",
        choices=["raw", "qfq", "hfq"],
        default="hfq",
    )
    market_emotion_state_v1.add_argument("--output-dir", required=True)
    market_emotion_state_v1.add_argument("--mid-trend-equity-path")

    daily_factor_pipeline = subparsers.add_parser("run-daily-factor-pipeline")
    daily_factor_pipeline.add_argument("--trade-date", required=True)
    daily_factor_pipeline.add_argument("--score-version", default="manual_v1")
    daily_factor_pipeline.add_argument("--top-n", type=int, default=30)
    daily_factor_pipeline.add_argument("--lookback-bars", type=int, default=130)
    daily_factor_pipeline.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    stock_daily_data_pipeline = subparsers.add_parser("run-stock-daily-data-pipeline")
    stock_daily_data_pipeline.add_argument("--trade-date", required=True)
    stock_daily_data_pipeline.add_argument("--output-dir", required=True)
    stock_daily_data_pipeline.add_argument("--feishu-target")
    stock_daily_data_pipeline.add_argument("--feishu-account", default="jarvis")
    stock_daily_data_pipeline.add_argument("--openclaw-bin", default="openclaw")
    stock_daily_data_pipeline.add_argument("--no-feishu", action="store_true")

    technical_features_daily = subparsers.add_parser("build-technical-features-daily")
    technical_features_daily.add_argument("--trade-date", required=True)
    technical_features_daily.add_argument("--lookback-bars", type=int, default=260)
    technical_features_daily.add_argument(
        "--adjust-type",
        choices=["raw", "qfq", "hfq"],
        default="qfq",
    )
    technical_features_daily.add_argument(
        "--build-strategy",
        choices=["legacy", "batch_frame", "latest_only"],
        default="latest_only",
    )

    backfill_technical_features_daily = subparsers.add_parser(
        "backfill-technical-features-daily"
    )
    backfill_technical_features_daily.add_argument("--start-date")
    backfill_technical_features_daily.add_argument("--end-date")
    backfill_technical_features_daily.add_argument("--lookback-bars", type=int, default=260)
    backfill_technical_features_daily.add_argument(
        "--adjust-type",
        choices=["raw", "qfq", "hfq"],
        default="qfq",
    )
    backfill_technical_features_daily.add_argument("--source-data-version")
    backfill_technical_features_daily.add_argument("--workers", type=int, default=1)
    backfill_technical_features_daily.add_argument("--skip-complete", action="store_true")
    backfill_technical_features_daily.add_argument("--progress-interval", type=int, default=1)
    backfill_technical_features_daily.add_argument(
        "--build-strategy",
        choices=["legacy", "batch_frame", "latest_only"],
        default="latest_only",
    )

    benchmark_technical_feature_backfill = subparsers.add_parser(
        "benchmark-technical-feature-backfill"
    )
    benchmark_technical_feature_backfill.add_argument("--start-date", required=True)
    benchmark_technical_feature_backfill.add_argument("--end-date", required=True)
    benchmark_technical_feature_backfill.add_argument("--lookback-bars", type=int, default=260)
    benchmark_technical_feature_backfill.add_argument(
        "--adjust-type",
        choices=["raw", "qfq", "hfq"],
        default="qfq",
    )
    benchmark_technical_feature_backfill.add_argument(
        "--strategy",
        choices=["current", "parallel_dates"],
        default="current",
    )
    benchmark_technical_feature_backfill.add_argument("--workers", type=int, default=1)
    benchmark_technical_feature_backfill.add_argument("--bench-tag", required=True)

    technical_feature_gap_check = subparsers.add_parser("technical-feature-gap-check")
    technical_feature_gap_check.add_argument("--start-date", required=True)
    technical_feature_gap_check.add_argument("--end-date", required=True)
    technical_feature_gap_check.add_argument(
        "--adjust-type",
        choices=["raw", "qfq", "hfq"],
        default="qfq",
    )
    technical_feature_gap_check.add_argument(
        "--calc-version",
        default=TECHNICAL_FEATURE_CALC_VERSION,
    )
    technical_feature_gap_check.add_argument("--source-data-version")

    intraday_features_daily = subparsers.add_parser("build-intraday-features-daily")
    intraday_features_daily.add_argument("--trade-date", required=True)
    intraday_features_daily.add_argument(
        "--freq",
        choices=["1min", "5min", "15min", "30min", "60min"],
        default="5min",
    )
    intraday_features_daily.add_argument(
        "--adjust-type",
        choices=["raw", "qfq", "hfq"],
        default="raw",
    )
    intraday_features_daily.add_argument("--industry-system", default="csrc")

    backfill_intraday_features = subparsers.add_parser("backfill-intraday-features-daily")
    backfill_intraday_features.add_argument("--start-date", required=True)
    backfill_intraday_features.add_argument("--end-date", required=True)
    backfill_intraday_features.add_argument(
        "--freq",
        choices=["1min", "5min", "15min", "30min", "60min"],
        default="5min",
    )
    backfill_intraday_features.add_argument(
        "--adjust-type",
        choices=["raw", "qfq", "hfq"],
        default="raw",
    )
    backfill_intraday_features.add_argument("--industry-system", default="csrc")
    backfill_intraday_features.add_argument("--workers", type=int, default=1)
    backfill_intraday_features.add_argument("--skip-complete", action="store_true")

    intraday_feature_gap_check = subparsers.add_parser("intraday-feature-gap-check")
    intraday_feature_gap_check.add_argument("--start-date", required=True)
    intraday_feature_gap_check.add_argument("--end-date", required=True)
    intraday_feature_gap_check.add_argument(
        "--freq",
        choices=["1min", "5min", "15min", "30min", "60min"],
        default="5min",
    )
    intraday_feature_gap_check.add_argument(
        "--adjust-type",
        choices=["raw", "qfq", "hfq"],
        default="raw",
    )
    intraday_feature_gap_check.add_argument(
        "--calc-version",
        default=INTRADAY_FEATURE_CALC_VERSION,
    )

    technical_feature_promotion_audit = subparsers.add_parser("technical-feature-promotion-audit")
    technical_feature_promotion_audit.add_argument("--start-date", required=True)
    technical_feature_promotion_audit.add_argument("--end-date", required=True)
    technical_feature_promotion_audit.add_argument(
        "--adjust-type",
        choices=["raw", "qfq", "hfq"],
        default="qfq",
    )
    technical_feature_promotion_audit.add_argument("--sample-size", type=int)
    technical_feature_promotion_audit.add_argument("--asset-id")
    technical_feature_promotion_audit.add_argument("--ts-code")
    technical_feature_promotion_audit.add_argument(
        "--feature-source",
        choices=["technical_table", "computed_on_fly"],
        default="technical_table",
    )
    technical_feature_promotion_audit.add_argument("--output-dir", required=True)

    technical_feature_performance_review = subparsers.add_parser(
        "technical-feature-performance-review"
    )
    technical_feature_performance_review.add_argument("--asset-count", type=int, default=16)
    technical_feature_performance_review.add_argument("--bar-count", type=int, default=260)
    technical_feature_performance_review.add_argument("--repeat", type=int, default=1)
    technical_feature_performance_review.add_argument("--min-speedup-ratio", type=float, default=1.0)
    technical_feature_performance_review.add_argument("--output-dir", required=True)

    p2_artifact_rollup = subparsers.add_parser("p2-artifact-rollup")
    p2_artifact_rollup.add_argument("--manifest", required=True)
    p2_artifact_rollup.add_argument("--output-dir", required=True)

    p2_simulation_review = subparsers.add_parser("p2-simulation-review")
    p2_simulation_review.add_argument("--trade-date", required=True)
    p2_simulation_review.add_argument("--portfolio-id", required=True)
    p2_simulation_review.add_argument(
        "--simulation-state",
        action="append",
        required=True,
    )
    p2_simulation_review.add_argument("--trade-advice")
    p2_simulation_review.add_argument("--output-dir", required=True)

    p2_aggregate_review = subparsers.add_parser("p2-aggregate-review")
    p2_aggregate_review.add_argument("--trade-date", required=True)
    p2_aggregate_review.add_argument("--rollup", required=True)
    p2_aggregate_review.add_argument("--output-dir", required=True)

    p3_import_p2_aggregate_review = subparsers.add_parser("p3-import-p2-aggregate-review")
    p3_import_p2_aggregate_review.add_argument("--path", required=True)
    p3_import_p2_aggregate_review.add_argument("--service", default="stock_research")

    p3_import_virtual_portfolio_review = subparsers.add_parser(
        "p3-import-virtual-portfolio-review"
    )
    p3_import_virtual_portfolio_review.add_argument("--path", required=True)
    p3_import_virtual_portfolio_review.add_argument("--service", default="stock_research")

    p3_export_operator_review = subparsers.add_parser("p3-export-operator-review")
    p3_export_operator_review.add_argument("--start-date", required=True)
    p3_export_operator_review.add_argument("--end-date", required=True)
    p3_export_operator_review.add_argument("--output-dir", required=True)
    p3_export_operator_review.add_argument("--status")
    p3_export_operator_review.add_argument("--section-group")
    p3_export_operator_review.add_argument("--portfolio-id")
    p3_export_operator_review.add_argument("--service", default="stock_research")

    p7_decision_journal = subparsers.add_parser("p7-decision-journal")
    p7_decision_journal.add_argument("--review-date", required=True)
    p7_decision_journal.add_argument("--review-session-id", required=True)
    p7_decision_journal.add_argument("--reviewer-id", required=True)
    p7_decision_journal.add_argument("--source-artifact-root", required=True)
    p7_decision_journal.add_argument("--input-csv", required=True)
    p7_decision_journal.add_argument("--output-dir", required=True)

    p7_import_decision_journal = subparsers.add_parser("p7-import-decision-journal")
    p7_import_decision_journal.add_argument("--path", required=True)
    p7_import_decision_journal.add_argument("--service", default="stock_research")

    p8_decision_outcome_review = subparsers.add_parser("p8-decision-outcome-review")
    p8_decision_outcome_review.add_argument("--start-date", required=True)
    p8_decision_outcome_review.add_argument("--end-date", required=True)
    p8_decision_outcome_review.add_argument("--review-session-id")
    p8_decision_outcome_review.add_argument("--decision-events-csv")
    p8_decision_outcome_review.add_argument("--bars-csv")
    p8_decision_outcome_review.add_argument("--output-dir", required=True)
    p8_decision_outcome_review.add_argument("--service", default="stock_research")
    p8_decision_outcome_review.add_argument("--adjust-type", default="qfq")
    p8_decision_outcome_review.add_argument("--horizon", dest="horizons", action="append", type=int)

    p8_import_decision_outcome_review = subparsers.add_parser("p8-import-decision-outcome-review")
    p8_import_decision_outcome_review.add_argument("--path", required=True)
    p8_import_decision_outcome_review.add_argument("--service", default="stock_research")

    p9_outcome_analytics = subparsers.add_parser("p9-outcome-analytics")
    p9_outcome_analytics.add_argument("--start-date", required=True)
    p9_outcome_analytics.add_argument("--end-date", required=True)
    p9_outcome_analytics.add_argument("--review-session-id")
    p9_outcome_analytics.add_argument("--outcome-events-csv")
    p9_outcome_analytics.add_argument("--output-dir", required=True)
    p9_outcome_analytics.add_argument("--service", default="stock_research")
    p9_outcome_analytics.add_argument("--limit", type=int, default=1000)
    p9_outcome_analytics.add_argument("--horizon", dest="horizons", action="append", type=int)

    p9_import_outcome_analytics = subparsers.add_parser("p9-import-outcome-analytics")
    p9_import_outcome_analytics.add_argument("--path", required=True)
    p9_import_outcome_analytics.add_argument("--service", default="stock_research")

    p10_experiment_proposals = subparsers.add_parser("p10-experiment-proposals")
    p10_experiment_proposals.add_argument("--input-csv", required=True)
    p10_experiment_proposals.add_argument("--review-date", required=True)
    p10_experiment_proposals.add_argument("--run-id")
    p10_experiment_proposals.add_argument("--output-dir", required=True)

    p10_import_experiment_proposals = subparsers.add_parser("p10-import-experiment-proposals")
    p10_import_experiment_proposals.add_argument("--path", required=True)
    p10_import_experiment_proposals.add_argument("--service", default="stock_research")

    p11_experiment_replay = subparsers.add_parser("p11-experiment-replay")
    p11_experiment_replay.add_argument("--proposals-json", required=True)
    p11_experiment_replay.add_argument("--metrics-csv", required=True)
    p11_experiment_replay.add_argument("--run-id")
    p11_experiment_replay.add_argument("--replay-start-date", required=True)
    p11_experiment_replay.add_argument("--replay-end-date", required=True)
    p11_experiment_replay.add_argument("--output-dir", required=True)

    p11_import_experiment_replay = subparsers.add_parser("p11-import-experiment-replay")
    p11_import_experiment_replay.add_argument("--path", required=True)
    p11_import_experiment_replay.add_argument("--service", default="stock_research")

    p12_shadow_watchlist = subparsers.add_parser("p12-shadow-watchlist")
    p12_shadow_watchlist.add_argument("--replay-json", required=True)
    p12_shadow_watchlist.add_argument("--candidates-csv", required=True)
    p12_shadow_watchlist.add_argument("--review-date", required=True)
    p12_shadow_watchlist.add_argument("--run-id")
    p12_shadow_watchlist.add_argument("--output-dir", required=True)

    p12_import_shadow_watchlist = subparsers.add_parser("p12-import-shadow-watchlist")
    p12_import_shadow_watchlist.add_argument("--path", required=True)
    p12_import_shadow_watchlist.add_argument("--service", default="stock_research")

    p13_shadow_outcome_review = subparsers.add_parser("p13-shadow-outcome-review")
    p13_shadow_outcome_review.add_argument("--shadow-json", required=True)
    p13_shadow_outcome_review.add_argument("--bars-csv", required=True)
    p13_shadow_outcome_review.add_argument("--review-date", required=True)
    p13_shadow_outcome_review.add_argument("--run-id")
    p13_shadow_outcome_review.add_argument("--output-dir", required=True)

    p13_import_shadow_outcomes = subparsers.add_parser("p13-import-shadow-outcomes")
    p13_import_shadow_outcomes.add_argument("--path", required=True)
    p13_import_shadow_outcomes.add_argument("--service", default="stock_research")

    p14_shadow_outcome_analytics = subparsers.add_parser("p14-shadow-outcome-analytics")
    p14_shadow_outcome_analytics.add_argument("--shadow-outcomes-json", required=True)
    p14_shadow_outcome_analytics.add_argument("--run-id", required=True)
    p14_shadow_outcome_analytics.add_argument("--review-start-date", required=True)
    p14_shadow_outcome_analytics.add_argument("--review-end-date", required=True)
    p14_shadow_outcome_analytics.add_argument("--output-dir", required=True)

    p15_shadow_analytics_review = subparsers.add_parser("p15-shadow-analytics-review")
    p15_shadow_analytics_review.add_argument("--p14-analytics-json", required=True)
    p15_shadow_analytics_review.add_argument("--run-id", required=True)
    p15_shadow_analytics_review.add_argument("--review-start-date", required=True)
    p15_shadow_analytics_review.add_argument("--review-end-date", required=True)
    p15_shadow_analytics_review.add_argument("--reviewer-id", required=True)
    p15_shadow_analytics_review.add_argument("--output-dir", required=True)

    p16_shadow_review_decisions = subparsers.add_parser("p16-shadow-review-decisions")
    p16_shadow_review_decisions.add_argument("--p15-review-json", required=True)
    p16_shadow_review_decisions.add_argument("--run-id", required=True)
    p16_shadow_review_decisions.add_argument("--decision-date", required=True)
    p16_shadow_review_decisions.add_argument("--operator-id", required=True)
    p16_shadow_review_decisions.add_argument("--output-dir", required=True)

    p17_shadow_follow_up_queue = subparsers.add_parser("p17-shadow-follow-up-queue")
    p17_shadow_follow_up_queue.add_argument("--p16-decisions-json", required=True)
    p17_shadow_follow_up_queue.add_argument("--run-id", required=True)
    p17_shadow_follow_up_queue.add_argument("--follow-up-date", required=True)
    p17_shadow_follow_up_queue.add_argument("--operator-id", required=True)
    p17_shadow_follow_up_queue.add_argument("--output-dir", required=True)

    p18_shadow_follow_up_resolution = subparsers.add_parser("p18-shadow-follow-up-resolution")
    p18_shadow_follow_up_resolution.add_argument("--p17-follow-up-json", required=True)
    p18_shadow_follow_up_resolution.add_argument("--run-id", required=True)
    p18_shadow_follow_up_resolution.add_argument("--resolution-date", required=True)
    p18_shadow_follow_up_resolution.add_argument("--operator-id", required=True)
    p18_shadow_follow_up_resolution.add_argument("--output-dir", required=True)

    p14_import_shadow_outcome_analytics = subparsers.add_parser("p14-import-shadow-outcome-analytics")
    p14_import_shadow_outcome_analytics.add_argument("--path", required=True)
    p14_import_shadow_outcome_analytics.add_argument("--service", default=SETTINGS.research_service)

    p15_import_shadow_analytics_review = subparsers.add_parser("p15-import-shadow-analytics-review")
    p15_import_shadow_analytics_review.add_argument("--path", required=True)
    p15_import_shadow_analytics_review.add_argument("--service", default=SETTINGS.research_service)

    p16_import_shadow_review_decisions = subparsers.add_parser("p16-import-shadow-review-decisions")
    p16_import_shadow_review_decisions.add_argument("--path", required=True)
    p16_import_shadow_review_decisions.add_argument("--service", default=SETTINGS.research_service)

    p17_import_shadow_follow_up_queue = subparsers.add_parser("p17-import-shadow-follow-up-queue")
    p17_import_shadow_follow_up_queue.add_argument("--path", required=True)
    p17_import_shadow_follow_up_queue.add_argument("--service", default=SETTINGS.research_service)

    p18_import_shadow_follow_up_resolution = subparsers.add_parser(
        "p18-import-shadow-follow-up-resolution"
    )
    p18_import_shadow_follow_up_resolution.add_argument("--path", required=True)
    p18_import_shadow_follow_up_resolution.add_argument("--service", default=SETTINGS.research_service)

    p4_daily_orchestration = subparsers.add_parser("p4-daily-orchestration")
    p4_daily_orchestration.add_argument("--trade-date", required=True)
    p4_daily_orchestration.add_argument("--aggregate-review", required=True)
    p4_daily_orchestration.add_argument("--virtual-portfolio", required=True)
    p4_daily_orchestration.add_argument("--output-dir", required=True)
    p4_daily_orchestration.add_argument("--portfolio-id")
    p4_daily_orchestration.add_argument("--apply-daily-run-schema", action="store_true")
    p4_daily_orchestration.add_argument("--record-run", action="store_true")
    p4_daily_orchestration.add_argument("--service", default="stock_research")

    p4_read_model_smoke = subparsers.add_parser("p4-read-model-smoke")
    p4_read_model_smoke.add_argument("--trade-date", required=True)
    p4_read_model_smoke.add_argument("--operator-manifest", required=True)
    p4_read_model_smoke.add_argument("--portfolio-id")
    p4_read_model_smoke.add_argument("--service", default="stock_research")

    p4_scheduler_cron_entry = subparsers.add_parser("p4-scheduler-cron-entry")
    p4_scheduler_cron_entry.add_argument(
        "--project-dir",
        default="/Users/xiwei/stock_research",
    )
    p4_scheduler_cron_entry.add_argument("--trade-date-expr", default="$(date +%F)")
    p4_scheduler_cron_entry.add_argument("--hour", type=int, default=19)
    p4_scheduler_cron_entry.add_argument("--minute", type=int, default=15)
    p4_scheduler_cron_entry.add_argument("--weekdays", default="1-5")
    p4_scheduler_cron_entry.add_argument("--portfolio-id", default="p2_smoke_demo")
    p4_scheduler_cron_entry.add_argument("--service", default="stock_research")
    p4_scheduler_cron_entry.add_argument(
        "--log-path",
        default="logs/p4_scheduler_daily.log",
    )

    daily_incremental = subparsers.add_parser("run-daily-incremental")
    daily_incremental.add_argument("--trade-date", required=True)
    daily_incremental.add_argument("--score-version", default="manual_v1")
    daily_incremental.add_argument("--top-n", type=int, default=30)
    daily_incremental.add_argument("--lookback-bars", type=int, default=130)
    daily_incremental.add_argument("--adjust-type", default="hfq")
    daily_incremental.add_argument("--source-service", default="stock_hfq")
    daily_incremental.add_argument("--industry-system", default="csrc")
    daily_incremental.add_argument("--label-start-date")
    daily_incremental_resume = daily_incremental.add_mutually_exclusive_group()
    daily_incremental_resume.add_argument("--start-at")
    daily_incremental_resume.add_argument("--only-step")
    daily_incremental.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )
    daily_incremental.add_argument("--dry-run", action="store_true")
    daily_incremental.add_argument("--apply-daily-run-schema", action="store_true")
    daily_incremental.add_argument("--record-run", action="store_true")

    mid_trend_watch_funnel = subparsers.add_parser("build-mid-trend-watch-funnel")
    mid_trend_watch_funnel.add_argument(
        "--discovery-pool-path",
        default="outputs/research/strong_winner_discovery_pool_detail.csv",
    )
    mid_trend_watch_funnel.add_argument("--trade-date")
    mid_trend_watch_funnel.add_argument("--top50-size", type=int, default=50)
    mid_trend_watch_funnel.add_argument("--top10-size", type=int, default=10)
    mid_trend_watch_funnel.add_argument(
        "--context-detail-path",
        default="outputs/research/trend_discovery_template_detail.csv",
    )
    mid_trend_watch_funnel.add_argument(
        "--market-regime-path",
        default="outputs/research/market_regime_diagnostics.csv",
    )
    mid_trend_watch_funnel.add_argument(
        "--industry-mainline-path",
        default="outputs/research/industry_mainline_regime_diagnostics.csv",
    )
    mid_trend_watch_funnel.add_argument("--output-dir", default="outputs/research")

    mid_trend_drawdown_control = subparsers.add_parser("validate-mid-trend-drawdown-control")
    mid_trend_drawdown_control.add_argument(
        "--funnel-detail-path",
        default="outputs/research/mid_trend_watch_funnel_detail.csv",
    )
    mid_trend_drawdown_control.add_argument(
        "--baseline-top10-path",
        default="outputs/research/mid_trend_watch_top10.csv",
    )
    mid_trend_drawdown_control.add_argument("--top-n", type=int, default=10)
    mid_trend_drawdown_control.add_argument("--output-dir", default="outputs/research")

    mid_trend_pareto_scan = subparsers.add_parser("scan-mid-trend-risk-return-pareto")
    mid_trend_pareto_scan.add_argument(
        "--funnel-detail-path",
        default="outputs/research/mid_trend_watch_funnel_detail.csv",
    )
    mid_trend_pareto_scan.add_argument("--top-n", type=int, default=10)
    mid_trend_pareto_scan.add_argument("--output-dir", default="outputs/research")

    mid_trend_shadow_stability = subparsers.add_parser("review-mid-trend-shadow-stability")
    mid_trend_shadow_stability.add_argument(
        "--funnel-detail-path",
        default="outputs/research/mid_trend_watch_funnel_detail.csv",
    )
    mid_trend_shadow_stability.add_argument(
        "--baseline-top10-path",
        default="outputs/research/mid_trend_watch_top10.csv",
    )
    mid_trend_shadow_stability.add_argument("--top-n", type=int, default=10)
    mid_trend_shadow_stability.add_argument("--output-dir", default="outputs/research")

    mid_trend_shadow_top10 = subparsers.add_parser("build-mid-trend-shadow-top10")
    mid_trend_shadow_top10.add_argument(
        "--funnel-detail-path",
        default="outputs/research/mid_trend_watch_funnel_detail.csv",
    )
    mid_trend_shadow_top10.add_argument("--trade-date")
    mid_trend_shadow_top10.add_argument("--top-n", type=int, default=10)
    mid_trend_shadow_top10.add_argument("--output-dir", default="outputs/research")

    mid_trend_research_packet = subparsers.add_parser("build-mid-trend-research-packet")
    mid_trend_research_packet.add_argument(
        "--funnel-detail-path",
        default="outputs/research/mid_trend_watch_funnel_detail.csv",
    )
    mid_trend_research_packet.add_argument(
        "--fundamental-path",
        default="outputs/research/watchlist_fundamental_pit_context.csv",
    )
    mid_trend_research_packet.add_argument("--stock-report-feature-path")
    mid_trend_research_packet.add_argument("--trade-date")
    mid_trend_research_packet.add_argument("--top-n", type=int, default=5)
    mid_trend_research_packet.add_argument("--score-floor", type=float, default=80.0)
    mid_trend_research_packet.add_argument("--output-dir", default="outputs/research")

    mid_trend_portfolio_review = subparsers.add_parser("build-mid-trend-portfolio-review")
    mid_trend_portfolio_review.add_argument("--trade-date", required=True)
    mid_trend_portfolio_review.add_argument("--strategy-variant", required=True)
    mid_trend_portfolio_review.add_argument("--top10-path", required=True)
    mid_trend_portfolio_review.add_argument("--holdings-path", required=True)
    mid_trend_portfolio_review.add_argument("--trades-path", required=True)
    mid_trend_portfolio_review.add_argument("--research-packet-path", required=True)
    mid_trend_portfolio_review.add_argument("--output-dir", default="outputs/research")
    mid_trend_portfolio_review.add_argument(
        "--write-research-infra",
        action="store_true",
        help="Write standardized research_infra sidecar artifacts for this review.",
    )

    mid_trend_position_dossier = subparsers.add_parser("build-mid-trend-position-dossier")
    mid_trend_position_dossier.add_argument("--trade-date", required=True)
    mid_trend_position_dossier.add_argument("--mode", choices=["replay", "live"], default="replay")
    mid_trend_position_dossier.add_argument("--portfolio-review-path", required=True)
    mid_trend_position_dossier.add_argument("--research-packet-path", required=True)
    mid_trend_position_dossier.add_argument("--news-enrichment-path")
    mid_trend_position_dossier.add_argument("--output-dir", default="outputs/research")

    mid_trend_shadow_backtest = subparsers.add_parser("backtest-mid-trend-shadow-top10")
    mid_trend_shadow_backtest.add_argument(
        "--shadow-top10-path",
        default="outputs/research/mid_trend_shadow_top10.csv",
    )
    mid_trend_shadow_backtest.add_argument("--start-date", required=True)
    mid_trend_shadow_backtest.add_argument("--end-date", required=True)
    mid_trend_shadow_backtest.add_argument("--top-n", type=int, default=10)
    mid_trend_shadow_backtest.add_argument("--rebalance-frequency", default="daily")
    mid_trend_shadow_backtest.add_argument("--transaction-cost-bps", type=float, default=20.0)
    mid_trend_shadow_backtest.add_argument("--adjust-type", default="hfq")
    mid_trend_shadow_backtest.add_argument("--output-dir", default="outputs/research")

    mid_trend_shadow_weekly_optimization = subparsers.add_parser(
        "optimize-mid-trend-shadow-weekly"
    )
    mid_trend_shadow_weekly_optimization.add_argument(
        "--funnel-detail-path",
        default="outputs/research/mid_trend_watch_funnel_detail.csv",
    )
    mid_trend_shadow_weekly_optimization.add_argument("--start-date", required=True)
    mid_trend_shadow_weekly_optimization.add_argument("--end-date", required=True)
    mid_trend_shadow_weekly_optimization.add_argument(
        "--top-n-values",
        type=lambda value: parse_int_list(value, "--top-n-values"),
        default="5,8,10,12,15",
    )
    mid_trend_shadow_weekly_optimization.add_argument(
        "--transaction-cost-bps-values",
        type=lambda value: parse_float_list(value, "--transaction-cost-bps-values"),
        default="10,20,30",
    )
    mid_trend_shadow_weekly_optimization.add_argument("--adjust-type", default="hfq")
    mid_trend_shadow_weekly_optimization.add_argument("--output-dir", default="outputs/research")

    serenity_tight3b_c2 = subparsers.add_parser("serenity-tight3b-c2-experiment")
    serenity_tight3b_c2.add_argument(
        "--candidates-path",
        default=(
            "outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/"
            "strict_153_performance_20250101_20260605/strict_153_performance_details.csv"
        ),
    )
    serenity_tight3b_c2.add_argument(
        "--market-exposure-path",
        default=(
            "outputs/research/market_regime_confirmation_v1_tight3b_bt100_20230103_20260605/"
            "market_regime_confirmation_daily.csv"
        ),
    )
    serenity_tight3b_c2.add_argument("--start-date", required=True)
    serenity_tight3b_c2.add_argument("--end-date", required=True)
    serenity_tight3b_c2.add_argument("--universe-name", default="strict_153")
    serenity_tight3b_c2.add_argument(
        "--top-n-values",
        type=lambda value: parse_int_list(value, "--top-n-values"),
        default="5,8,10",
    )
    serenity_tight3b_c2.add_argument(
        "--rebalance-frequencies",
        type=lambda value: [item.strip() for item in value.split(",") if item.strip()],
        default="monthly,biweekly,weekly",
    )
    serenity_tight3b_c2.add_argument("--transaction-cost-bps", type=float, default=20.0)
    serenity_tight3b_c2.add_argument("--adjust-type", default="hfq")
    serenity_tight3b_c2.add_argument("--output-dir", default="outputs/research")

    serenity_source_backed_evidence = subparsers.add_parser("serenity-source-backed-evidence-fill")
    serenity_source_backed_evidence.add_argument("--structured-detail-path", required=True)
    serenity_source_backed_evidence.add_argument("--evidence-seed-path")
    serenity_source_backed_evidence.add_argument("--output-dir", required=True)
    serenity_source_backed_evidence.add_argument("--run-id", default="serenity_source_backed_evidence_fill")

    tech_bottleneck_evidence = subparsers.add_parser("tech-bottleneck-evidence-workflow")
    tech_bottleneck_evidence.add_argument("--asset-queue-path", required=True)
    tech_bottleneck_evidence.add_argument("--evidence-detail-path", required=True)
    tech_bottleneck_evidence.add_argument("--candidate-path")
    tech_bottleneck_evidence.add_argument("--trade-date")
    tech_bottleneck_evidence.add_argument("--top-n", type=int, default=100)
    tech_bottleneck_evidence.add_argument(
        "--output-dir",
        default="outputs/research/tech_bottleneck_evidence_workflow",
    )

    mid_trend_shadow_weekly_control = subparsers.add_parser(
        "review-mid-trend-shadow-weekly-control"
    )
    mid_trend_shadow_weekly_control.add_argument(
        "--funnel-detail-path",
        default="outputs/research/mid_trend_watch_funnel_detail.csv",
    )
    mid_trend_shadow_weekly_control.add_argument("--start-date", required=True)
    mid_trend_shadow_weekly_control.add_argument("--end-date", required=True)
    mid_trend_shadow_weekly_control.add_argument("--top-n", type=int, default=5)
    mid_trend_shadow_weekly_control.add_argument("--buffer-rank", type=int, default=10)
    mid_trend_shadow_weekly_control.add_argument("--max-weekly-replacements", type=int, default=2)
    mid_trend_shadow_weekly_control.add_argument("--peak-drawdown-exit", type=float, default=0.12)
    mid_trend_shadow_weekly_control.add_argument("--transaction-cost-bps", type=float, default=20.0)
    mid_trend_shadow_weekly_control.add_argument("--adjust-type", default="hfq")
    mid_trend_shadow_weekly_control.add_argument("--output-dir", default="outputs/research")

    mid_trend_adaptive_candidate = subparsers.add_parser(
        "review-mid-trend-adaptive-candidate"
    )
    mid_trend_adaptive_candidate.add_argument(
        "--funnel-detail-path",
        default="outputs/research/mid_trend_watch_funnel_detail.csv",
    )
    mid_trend_adaptive_candidate.add_argument("--start-date", required=True)
    mid_trend_adaptive_candidate.add_argument("--end-date", required=True)
    mid_trend_adaptive_candidate.add_argument(
        "--cost-bps-values",
        type=lambda value: parse_float_list(value, "--cost-bps-values"),
        default="10,20,30,50",
    )
    mid_trend_adaptive_candidate.add_argument("--top-n", type=int, default=5)
    mid_trend_adaptive_candidate.add_argument("--buffer-rank", type=int, default=10)
    mid_trend_adaptive_candidate.add_argument("--max-weekly-replacements", type=int, default=2)
    mid_trend_adaptive_candidate.add_argument("--transaction-cost-bps", type=float, default=20.0)
    mid_trend_adaptive_candidate.add_argument("--adjust-type", default="hfq")
    mid_trend_adaptive_candidate.add_argument("--output-dir", default="outputs/research")

    mid_trend_adaptive_issue = subparsers.add_parser(
        "review-mid-trend-adaptive-issue-attribution"
    )
    mid_trend_adaptive_issue.add_argument(
        "--monthly-path",
        default=(
            "outputs/research/mid_trend_adaptive_candidate_review_v1/"
            "mid_trend_adaptive_candidate_monthly_stability.csv"
        ),
    )
    mid_trend_adaptive_issue.add_argument(
        "--attribution-detail-path",
        default=(
            "outputs/research/mid_trend_adaptive_candidate_review_v1/"
            "mid_trend_adaptive_candidate_rebalance_attribution_detail.csv"
        ),
    )
    mid_trend_adaptive_issue.add_argument(
        "--funnel-detail-path",
        default="outputs/research/mid_trend_watch_funnel_detail.csv",
    )
    mid_trend_adaptive_issue.add_argument("--output-dir", default="outputs/research")

    mid_trend_adaptive_bad_buy = subparsers.add_parser(
        "review-mid-trend-adaptive-bad-buy-attribution"
    )
    mid_trend_adaptive_bad_buy.add_argument(
        "--attribution-detail-path",
        default=(
            "outputs/research/mid_trend_adaptive_candidate_review_v1/"
            "mid_trend_adaptive_candidate_rebalance_attribution_detail.csv"
        ),
    )
    mid_trend_adaptive_bad_buy.add_argument(
        "--funnel-detail-path",
        default="outputs/research/mid_trend_watch_funnel_detail.csv",
    )
    mid_trend_adaptive_bad_buy.add_argument("--output-dir", default="outputs/research")

    mid_trend_entry_timing = subparsers.add_parser(
        "review-mid-trend-entry-timing-attribution"
    )
    mid_trend_entry_timing.add_argument(
        "--attribution-detail-path",
        default=(
            "outputs/research/mid_trend_adaptive_candidate_review_v1/"
            "mid_trend_adaptive_candidate_rebalance_attribution_detail.csv"
        ),
    )
    mid_trend_entry_timing.add_argument("--start-date", required=True)
    mid_trend_entry_timing.add_argument("--end-date", required=True)
    mid_trend_entry_timing.add_argument("--prices-path", default=None)
    mid_trend_entry_timing.add_argument("--valuation-path", default=None)
    mid_trend_entry_timing.add_argument("--adjust-type", default="hfq")
    mid_trend_entry_timing.add_argument("--output-dir", default="outputs/research")

    mid_trend_shadow_replacement_scan = subparsers.add_parser(
        "scan-mid-trend-shadow-replacements"
    )
    mid_trend_shadow_replacement_scan.add_argument(
        "--funnel-detail-path",
        default="outputs/research/mid_trend_watch_funnel_detail.csv",
    )
    mid_trend_shadow_replacement_scan.add_argument("--start-date", required=True)
    mid_trend_shadow_replacement_scan.add_argument("--end-date", required=True)
    mid_trend_shadow_replacement_scan.add_argument(
        "--top-n-values",
        type=lambda value: parse_int_list(value, "--top-n-values"),
        default="5,8",
    )
    mid_trend_shadow_replacement_scan.add_argument(
        "--max-weekly-replacements-values",
        type=lambda value: parse_int_list(value, "--max-weekly-replacements-values"),
        default="1,2,3",
    )
    mid_trend_shadow_replacement_scan.add_argument(
        "--transaction-cost-bps-values",
        type=lambda value: parse_float_list(value, "--transaction-cost-bps-values"),
        default="10,20,30",
    )
    mid_trend_shadow_replacement_scan.add_argument("--adjust-type", default="hfq")
    mid_trend_shadow_replacement_scan.add_argument("--output-dir", default="outputs/research")

    mid_trend_trend_protection_scan = subparsers.add_parser("scan-mid-trend-protection")
    mid_trend_trend_protection_scan.add_argument(
        "--funnel-detail-path",
        default="outputs/research/mid_trend_watch_funnel_detail.csv",
    )
    mid_trend_trend_protection_scan.add_argument("--start-date", required=True)
    mid_trend_trend_protection_scan.add_argument("--end-date", required=True)
    mid_trend_trend_protection_scan.add_argument(
        "--score-gap-values",
        type=lambda value: parse_float_list(value, "--score-gap-values"),
        default="6,8,10,12",
    )
    mid_trend_trend_protection_scan.add_argument(
        "--mainline-gap-values",
        type=lambda value: parse_float_list(value, "--mainline-gap-values"),
        default="0.05,0.10,0.15",
    )
    mid_trend_trend_protection_scan.add_argument(
        "--trend-r2-min-values",
        type=lambda value: parse_float_list(value, "--trend-r2-min-values"),
        default="75,80",
    )
    mid_trend_trend_protection_scan.add_argument(
        "--ret20-min-values",
        type=lambda value: parse_float_list(value, "--ret20-min-values"),
        default="65,70",
    )
    mid_trend_trend_protection_scan.add_argument(
        "--drawdown-min-values",
        type=lambda value: parse_float_list(value, "--drawdown-min-values"),
        default="50,55",
    )
    mid_trend_trend_protection_scan.add_argument("--top-n", type=int, default=5)
    mid_trend_trend_protection_scan.add_argument("--max-weekly-replacements", type=int, default=2)
    mid_trend_trend_protection_scan.add_argument("--transaction-cost-bps", type=float, default=20.0)
    mid_trend_trend_protection_scan.add_argument("--adjust-type", default="hfq")
    mid_trend_trend_protection_scan.add_argument("--output-dir", default="outputs/research")

    mid_trend_drawdown_throttle_scan = subparsers.add_parser(
        "scan-mid-trend-drawdown-throttle"
    )
    mid_trend_drawdown_throttle_scan.add_argument(
        "--funnel-detail-path",
        default="outputs/research/mid_trend_watch_funnel_detail.csv",
    )
    mid_trend_drawdown_throttle_scan.add_argument("--start-date", required=True)
    mid_trend_drawdown_throttle_scan.add_argument("--end-date", required=True)
    mid_trend_drawdown_throttle_scan.add_argument(
        "--threshold-values",
        type=lambda value: parse_float_list(value, "--threshold-values"),
        default="0.08,0.10,0.12",
    )
    mid_trend_drawdown_throttle_scan.add_argument(
        "--invested-weight-values",
        type=lambda value: parse_float_list(value, "--invested-weight-values"),
        default="0.8,0.9,1.0",
    )
    mid_trend_drawdown_throttle_scan.add_argument(
        "--max-replacement-values",
        type=lambda value: parse_int_list(value, "--max-replacement-values"),
        default="1,2",
    )
    mid_trend_drawdown_throttle_scan.add_argument("--top-n", type=int, default=5)
    mid_trend_drawdown_throttle_scan.add_argument("--buffer-rank", type=int, default=10)
    mid_trend_drawdown_throttle_scan.add_argument("--max-weekly-replacements", type=int, default=2)
    mid_trend_drawdown_throttle_scan.add_argument("--transaction-cost-bps", type=float, default=20.0)
    mid_trend_drawdown_throttle_scan.add_argument("--adjust-type", default="hfq")
    mid_trend_drawdown_throttle_scan.add_argument("--output-dir", default="outputs/research")

    mid_trend_trend_protection_stability = subparsers.add_parser(
        "review-mid-trend-protection-stability"
    )
    mid_trend_trend_protection_stability.add_argument(
        "--funnel-detail-path",
        default="outputs/research/mid_trend_watch_funnel_detail.csv",
    )
    mid_trend_trend_protection_stability.add_argument("--start-date", required=True)
    mid_trend_trend_protection_stability.add_argument("--end-date", required=True)
    mid_trend_trend_protection_stability.add_argument("--protection-score-gap", type=float, default=6.0)
    mid_trend_trend_protection_stability.add_argument("--protection-mainline-gap", type=float, default=0.05)
    mid_trend_trend_protection_stability.add_argument("--protection-trend-r2-min", type=float, default=75.0)
    mid_trend_trend_protection_stability.add_argument("--protection-ret20-min", type=float, default=65.0)
    mid_trend_trend_protection_stability.add_argument("--protection-drawdown-min", type=float, default=50.0)
    mid_trend_trend_protection_stability.add_argument("--top-n", type=int, default=5)
    mid_trend_trend_protection_stability.add_argument("--max-weekly-replacements", type=int, default=2)
    mid_trend_trend_protection_stability.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=20.0,
    )
    mid_trend_trend_protection_stability.add_argument("--adjust-type", default="hfq")
    mid_trend_trend_protection_stability.add_argument("--output-dir", default="outputs/research")

    mid_trend_rebalance_attribution = subparsers.add_parser(
        "review-mid-trend-rebalance-attribution"
    )
    mid_trend_rebalance_attribution.add_argument(
        "--trades-path",
        default=(
            "outputs/research/mid_trend_shadow_weekly_control_v1/"
            "mid_trend_shadow_weekly_control_trades.csv"
        ),
    )
    mid_trend_rebalance_attribution.add_argument(
        "--equity-path",
        default=(
            "outputs/research/mid_trend_shadow_weekly_control_v1/"
            "mid_trend_shadow_weekly_control_equity.csv"
        ),
    )
    mid_trend_rebalance_attribution.add_argument("--start-date", required=True)
    mid_trend_rebalance_attribution.add_argument("--end-date", required=True)
    mid_trend_rebalance_attribution.add_argument(
        "--variant-name",
        default="top5_weekly_max_2_replacements",
    )
    mid_trend_rebalance_attribution.add_argument("--adjust-type", default="hfq")
    mid_trend_rebalance_attribution.add_argument("--output-dir", default="outputs/research")

    mid_trend_shadow_control_v2 = subparsers.add_parser("scan-mid-trend-shadow-control-v2")
    mid_trend_shadow_control_v2.add_argument(
        "--funnel-detail-path",
        default="outputs/research/mid_trend_watch_funnel_detail.csv",
    )
    mid_trend_shadow_control_v2.add_argument("--start-date", required=True)
    mid_trend_shadow_control_v2.add_argument("--end-date", required=True)
    mid_trend_shadow_control_v2.add_argument("--top-n", type=int, default=5)
    mid_trend_shadow_control_v2.add_argument("--base-max-replacements", type=int, default=2)
    mid_trend_shadow_control_v2.add_argument("--drawdown-threshold", type=float, default=0.08)
    mid_trend_shadow_control_v2.add_argument("--drawdown-worsen-threshold", type=float, default=0.03)
    mid_trend_shadow_control_v2.add_argument("--transaction-cost-bps", type=float, default=20.0)
    mid_trend_shadow_control_v2.add_argument("--adjust-type", default="hfq")
    mid_trend_shadow_control_v2.add_argument("--output-dir", default="outputs/research")

    bad_rebalance_state_attribution = subparsers.add_parser(
        "review-bad-rebalance-state-attribution"
    )
    bad_rebalance_state_attribution.add_argument(
        "--attribution-detail-path",
        default=(
            "outputs/research/mid_trend_rebalance_attribution/"
            "mid_trend_rebalance_attribution_detail.csv"
        ),
    )
    bad_rebalance_state_attribution.add_argument(
        "--funnel-detail-path",
        default="outputs/research/mid_trend_watch_funnel_detail.csv",
    )
    bad_rebalance_state_attribution.add_argument("--output-dir", default="outputs/research")

    stock_report_workpack = subparsers.add_parser("build-stock-report-workpack")
    stock_report_workpack.add_argument(
        "--research-packet-path",
        default="outputs/research/mid_trend_research_packet_20260602/mid_trend_research_packet_candidates.csv",
    )
    stock_report_workpack.add_argument("--trade-date")
    stock_report_workpack.add_argument("--output-dir", default="outputs/research")

    stock_report_search_plan = subparsers.add_parser("build-stock-report-search-plan")
    stock_report_search_plan.add_argument(
        "--research-packet-path",
        default="outputs/research/mid_trend_research_packet_20260602/mid_trend_research_packet_candidates.csv",
    )
    stock_report_search_plan.add_argument("--trade-date")
    stock_report_search_plan.add_argument("--output-dir", default="outputs/research")

    stock_report_web_sources = subparsers.add_parser("collect-stock-report-web-sources")
    stock_report_web_sources.add_argument(
        "--search-plan-path",
        default="outputs/research/stock_report_web_collection_20260602/stock_report_search_plan.csv",
    )
    stock_report_web_sources.add_argument("--output-dir", default="outputs/research")
    stock_report_web_sources.add_argument("--dry-run", action="store_true")
    stock_report_web_sources.add_argument(
        "--adapter",
        choices=["mock", "web", "eastmoney_research"],
        default="mock",
    )
    stock_report_web_sources.add_argument("--max-fetches", type=int)
    stock_report_web_sources.add_argument("--write-db", action="store_true")
    stock_report_web_sources.add_argument("--service", default=SETTINGS.research_service)
    stock_report_web_sources.add_argument("--http-timeout-seconds", type=float, default=8.0)
    stock_report_web_sources.add_argument("--request-sleep-seconds", type=float, default=0.0)
    stock_report_web_sources.add_argument("--stop-after-consecutive-fetch-errors", type=int)
    stock_report_web_sources.add_argument("--start-date")
    stock_report_web_sources.add_argument("--end-date")

    stock_report_features = subparsers.add_parser("build-stock-report-features")
    stock_report_features.add_argument("--events-path", required=True)
    stock_report_features.add_argument("--trade-date", required=True)
    stock_report_features.add_argument("--output-dir", default="outputs/research")
    stock_report_features.add_argument("--write-db", action="store_true")

    stock_report_backfill_plan = subparsers.add_parser("stock-report-backfill-plan")
    stock_report_backfill_plan.add_argument("--start-date", required=True)
    stock_report_backfill_plan.add_argument("--end-date", required=True)
    stock_report_backfill_plan.add_argument("--sample-size", type=int)
    stock_report_backfill_plan.add_argument("--output-dir", default="outputs/research")

    stock_report_backfill_run = subparsers.add_parser("stock-report-backfill-run")
    stock_report_backfill_run.add_argument("--tasks-path", required=True)
    stock_report_backfill_run.add_argument("--start-date", required=True)
    stock_report_backfill_run.add_argument("--end-date", required=True)
    stock_report_backfill_run.add_argument("--batch-size", type=int, default=100)
    stock_report_backfill_run.add_argument("--sleep-seconds", type=float, default=0.5)
    stock_report_backfill_run.add_argument("--sample-size", type=int)
    stock_report_backfill_run.add_argument("--output-dir", default="outputs/research")
    stock_report_backfill_run.add_argument("--write-db", action="store_true")

    stock_report_backfill_watchdog = subparsers.add_parser("stock-report-backfill-watchdog")
    stock_report_backfill_watchdog.add_argument("--output-dir", default="outputs/research")
    stock_report_backfill_watchdog.add_argument("--stale-after-minutes", type=int, default=30)
    stock_report_backfill_watchdog.add_argument("--run-timeout-seconds", type=int, default=60)
    stock_report_backfill_watchdog.add_argument("--report-target", required=True)
    stock_report_backfill_watchdog.add_argument("--report-account", default="jarvis")
    stock_report_backfill_watchdog.add_argument("--openclaw-bin", default="openclaw")
    stock_report_backfill_watchdog.add_argument("--report-dry-run", action="store_true")

    stock_report_feature_backfill = subparsers.add_parser("stock-report-feature-backfill")
    stock_report_feature_backfill.add_argument("--start-date", required=True)
    stock_report_feature_backfill.add_argument("--end-date", required=True)
    stock_report_feature_backfill.add_argument("--events-path")
    stock_report_feature_backfill.add_argument("--output-dir", default="outputs/research")
    stock_report_feature_backfill.add_argument("--write-db", action="store_true")

    stock_report_pdf_field_backfill = subparsers.add_parser("stock-report-pdf-field-backfill")
    stock_report_pdf_field_backfill.add_argument("--source-path")
    stock_report_pdf_field_backfill.add_argument("--start-date")
    stock_report_pdf_field_backfill.add_argument("--end-date")
    stock_report_pdf_field_backfill.add_argument("--offset", type=int, default=0)
    stock_report_pdf_field_backfill.add_argument("--limit", type=int)
    stock_report_pdf_field_backfill.add_argument("--batch-size", type=int, default=100)
    stock_report_pdf_field_backfill.add_argument("--sleep-seconds", type=float, default=0.0)
    stock_report_pdf_field_backfill.add_argument("--output-dir", default="outputs/research")
    stock_report_pdf_field_backfill.add_argument("--resume", action="store_true", default=True)
    stock_report_pdf_field_backfill.add_argument("--no-resume", dest="resume", action="store_false")
    stock_report_pdf_field_backfill.add_argument("--write-db", action="store_true")

    stock_report_pdf_backfill_watchdog = subparsers.add_parser("stock-report-pdf-backfill-watchdog")
    stock_report_pdf_backfill_watchdog.add_argument("--output-dir", default="outputs/research")
    stock_report_pdf_backfill_watchdog.add_argument("--stale-after-minutes", type=int, default=30)
    stock_report_pdf_backfill_watchdog.add_argument("--run-timeout-seconds", type=int, default=60)
    stock_report_pdf_backfill_watchdog.add_argument("--report-target", required=True)
    stock_report_pdf_backfill_watchdog.add_argument("--report-account", default="jarvis")
    stock_report_pdf_backfill_watchdog.add_argument("--openclaw-bin", default="openclaw")
    stock_report_pdf_backfill_watchdog.add_argument("--report-dry-run", action="store_true")

    yanbaoke_report_backfill_plan = subparsers.add_parser("yanbaoke-report-backfill-plan")
    yanbaoke_report_backfill_plan.add_argument("--candidate-path", required=True)
    yanbaoke_report_backfill_plan.add_argument("--existing-coverage-path")
    yanbaoke_report_backfill_plan.add_argument("--start-date", default="2025-01-01")
    yanbaoke_report_backfill_plan.add_argument("--end-date", default="2026-06-12")
    yanbaoke_report_backfill_plan.add_argument("--output-dir", default="outputs/research/yanbaoke_backfill")

    hibor_download_queue = subparsers.add_parser("build-hibor-download-queue")
    hibor_download_queue.add_argument("--candidates-path", required=True)
    hibor_download_queue.add_argument("--start-date", required=True)
    hibor_download_queue.add_argument("--end-date", required=True)
    hibor_download_queue.add_argument("--output-dir", default="outputs/research/hibor_download_queue")
    hibor_download_queue.add_argument("--broker", action="append", dest="brokers")

    hibor_download = subparsers.add_parser("download-hibor-report-pdfs")
    hibor_download.add_argument("--candidates-path", required=True)
    hibor_download.add_argument("--start-date", required=True)
    hibor_download.add_argument("--end-date", required=True)
    hibor_download.add_argument("--download-dir", default="data/manual/hibor_reports/inbox")
    hibor_download.add_argument("--broker", action="append", dest="brokers")
    hibor_download.add_argument("--max-reports-per-candidate", type=int, default=1)

    hibor_import = subparsers.add_parser("import-hibor-report-pdfs")
    hibor_import.add_argument("--input-dir", required=True)
    hibor_import.add_argument("--output-dir", default="outputs/research/hibor_report_import")
    hibor_import.add_argument("--write-db", action="store_true")
    hibor_import.add_argument("--no-pdf-backfill", dest="run_pdf_backfill", action="store_false")
    hibor_import.add_argument("--feature-trade-date")
    hibor_import.set_defaults(run_pdf_backfill=True)

    hibor_watch = subparsers.add_parser("watch-hibor-downloads")
    hibor_watch.add_argument("--input-dir", required=True)
    hibor_watch.add_argument("--output-dir", default="outputs/research/hibor_report_import")
    hibor_watch.add_argument("--poll-seconds", type=float, default=5.0)
    hibor_watch.add_argument("--max-cycles", type=int)
    hibor_watch.add_argument("--write-db", action="store_true")

    hibor_a_tier_plan = subparsers.add_parser("build-hibor-a-tier-backfill-plan")
    hibor_a_tier_plan.add_argument("--start-date", default="2024-10-01")
    hibor_a_tier_plan.add_argument("--end-date", required=True)
    hibor_a_tier_plan.add_argument("--output-dir", default="outputs/research/hibor_a_tier_backfill")
    hibor_a_tier_plan.add_argument("--sample-size", type=int)
    hibor_a_tier_plan.add_argument("--service", default=SETTINGS.research_service)

    hibor_a_tier_run = subparsers.add_parser("run-hibor-a-tier-backfill")
    hibor_a_tier_run.add_argument("--tasks-path", required=True)
    hibor_a_tier_run.add_argument("--output-dir", default="outputs/research/hibor_a_tier_backfill")
    hibor_a_tier_run.add_argument("--config-path", default="config/hibor_institutions.csv")
    hibor_a_tier_run.add_argument("--download-dir")
    hibor_a_tier_run.add_argument("--review-threshold", type=int, default=50)
    hibor_a_tier_run.add_argument("--max-tasks", type=int)
    hibor_a_tier_run.add_argument("--max-detail-attempts", type=int)
    hibor_a_tier_run.add_argument("--fallback-tier", default="B")
    hibor_a_tier_run.add_argument("--retry-attempts", type=int, default=3)
    hibor_a_tier_run.add_argument("--retry-sleep-seconds", type=float, default=2.0)
    hibor_a_tier_run.add_argument("--write-db", action="store_true")
    hibor_a_tier_run.add_argument("--service", default=SETTINGS.research_service)
    hibor_a_tier_run.add_argument("--no-import", dest="import_pdfs", action="store_false")
    hibor_a_tier_run.add_argument("--no-pdf-backfill", dest="run_pdf_backfill", action="store_false")
    hibor_a_tier_run.add_argument("--feature-trade-date")
    hibor_a_tier_run.set_defaults(import_pdfs=True, run_pdf_backfill=True)

    hibor_ui_run = subparsers.add_parser("run-hibor-ui-download-backfill")
    hibor_ui_run.add_argument("--tasks-path", required=True)
    hibor_ui_run.add_argument("--output-dir", default="outputs/research/hibor_ui_download")
    hibor_ui_run.add_argument("--download-dir", default="data/manual/hibor_ui_reports")
    hibor_ui_run.add_argument("--staging-dir")
    hibor_ui_run.add_argument("--max-tasks", type=int)
    hibor_ui_run.add_argument("--wait-timeout-seconds", type=float, default=45.0)
    hibor_ui_run.add_argument("--poll-seconds", type=float, default=1.0)
    hibor_ui_run.add_argument("--skip-open-legacy-search", dest="open_legacy_search", action="store_false")
    hibor_ui_run.add_argument("--time-filter", choices=["all", "one_year"], default="all")
    hibor_ui_run.add_argument("--write-db", action="store_true")
    hibor_ui_run.add_argument("--service", default=SETTINGS.research_service)
    hibor_ui_run.add_argument("--no-import", dest="import_pdfs", action="store_false")
    hibor_ui_run.add_argument("--no-pdf-backfill", dest="run_pdf_backfill", action="store_false")
    hibor_ui_run.add_argument("--feature-trade-date")
    hibor_ui_run.set_defaults(open_legacy_search=True, import_pdfs=True, run_pdf_backfill=True)

    yanbaoke_run = subparsers.add_parser("run-yanbaoke-report-backfill")
    yanbaoke_run.add_argument("--tasks-path", required=True)
    yanbaoke_run.add_argument("--output-dir", default="outputs/research/yanbaoke_backfill")
    yanbaoke_run.add_argument("--download-dir")
    yanbaoke_run.add_argument("--api-key")
    yanbaoke_run.add_argument("--institutions-path", default="config/hibor_institutions.csv")
    yanbaoke_run.add_argument("--fallback-tier", default="B")
    yanbaoke_run.add_argument("--max-tasks", type=int)
    yanbaoke_run.add_argument("--max-downloads", type=int)
    yanbaoke_run.add_argument("--monthly-budget", type=int, default=1000)
    yanbaoke_run.add_argument("--base-budget", type=int, default=600)
    yanbaoke_run.add_argument("--top-budget", type=int, default=300)
    yanbaoke_run.add_argument("--reserve-budget", type=int, default=100)
    yanbaoke_run.add_argument("--top-ts-code", action="append", dest="top_ts_codes")
    yanbaoke_run.add_argument("--position-ts-code", action="append", dest="position_ts_codes")
    yanbaoke_run.add_argument("--max-broker-share", type=float, default=0.25)
    yanbaoke_run.add_argument("--write-db", action="store_true")
    yanbaoke_run.add_argument("--service", default=SETTINGS.research_service)
    yanbaoke_run.add_argument("--no-import", dest="import_pdfs", action="store_false")
    yanbaoke_run.add_argument("--no-pdf-backfill", dest="run_pdf_backfill", action="store_false")
    yanbaoke_run.add_argument("--feature-trade-date")
    yanbaoke_run.add_argument("--industry-structured-detail-path")
    yanbaoke_run.set_defaults(import_pdfs=True, run_pdf_backfill=True)

    daily_health = subparsers.add_parser("daily-health")
    daily_health.add_argument("--trade-date", required=True)
    daily_health.add_argument("--ingest-datasets", type=parse_ingest_datasets)
    daily_health.add_argument("--backfill-run-ids", type=parse_backfill_run_ids)
    daily_health.add_argument("--stale-minutes", type=int, default=60)
    daily_health.add_argument("--notify-target")
    daily_health.add_argument("--notify-account", default="jarvis")
    daily_health.add_argument("--openclaw-bin", default="openclaw")
    daily_health.add_argument("--notify-dry-run", action="store_true")

    export_snapshot = subparsers.add_parser("export-research-snapshot")
    export_snapshot.add_argument("--start-date", required=True)
    export_snapshot.add_argument("--end-date", required=True)
    export_snapshot.add_argument("--score-version", default="manual_v1")
    export_snapshot.add_argument("--output-dir", required=True)

    migration_safety = subparsers.add_parser("migration-safety-check")
    migration_safety.add_argument("--backup-path", required=True)
    migration_safety.add_argument("--source-service", default="stock_research")
    migration_safety.add_argument("--restore-service")
    migration_safety.add_argument("--dry-run", action="store_true")

    daily_research_report = subparsers.add_parser("run-daily-research-report")
    daily_research_report.add_argument("--trade-date", required=True)
    daily_research_report.add_argument("--score-version", default="manual_v1")
    daily_research_report.add_argument("--top-n", type=int, default=30)
    daily_research_report.add_argument("--index-id", default="CSI300")
    daily_research_report.add_argument("--market-lookback-days", type=int, default=90)
    daily_research_report.add_argument("--industry-system", default="csrc")
    daily_research_report.add_argument("--sector-lookback-days", type=int, default=60)
    daily_research_report.add_argument("--positions-csv")
    daily_research_report.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )
    daily_research_report.add_argument("--apply-report-run-schema", action="store_true")
    daily_research_report.add_argument("--record-run", action="store_true")

    daily_review_report = subparsers.add_parser("run-daily-review-v1")
    daily_review_report.add_argument("--trade-date", required=True)
    daily_review_report.add_argument(
        "--output-root",
        default="/Users/xiwei/stock_research/reports/daily_review",
    )
    daily_review_report.add_argument("--apply-report-run-schema", action="store_true")
    daily_review_report.add_argument("--record-run", action="store_true")

    trend_lifecycle_v1 = subparsers.add_parser("trend-lifecycle-v1")
    trend_lifecycle_v1.add_argument("--start-date", required=True)
    trend_lifecycle_v1.add_argument("--end-date", required=True)
    trend_lifecycle_v1.add_argument("--score-version", default="manual_v1")
    trend_lifecycle_v1.add_argument("--top-n", type=int, default=20)
    trend_lifecycle_v1.add_argument("--adjust-type", default="hfq")
    trend_lifecycle_v1.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    mid_trend_factor_profile = subparsers.add_parser("mid-trend-factor-profile")
    mid_trend_factor_profile.add_argument("--start-date", required=True)
    mid_trend_factor_profile.add_argument("--end-date", required=True)
    mid_trend_factor_profile.add_argument("--lifecycle-samples-path", required=True)
    mid_trend_factor_profile.add_argument("--factor-names", type=parse_factor_names)
    mid_trend_factor_profile.add_argument("--period", default="Q")
    mid_trend_factor_profile.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    mid_trend_candidate_enrichment = subparsers.add_parser("mid-trend-candidate-enrichment")
    mid_trend_candidate_enrichment.add_argument("--start-date", required=True)
    mid_trend_candidate_enrichment.add_argument("--end-date", required=True)
    mid_trend_candidate_enrichment.add_argument("--candidate-rank-path", required=True)
    mid_trend_candidate_enrichment.add_argument("--entry-success-labels-path", required=True)
    mid_trend_candidate_enrichment.add_argument("--max-factors", type=int)
    mid_trend_candidate_enrichment.add_argument("--min-candidate-score", type=float, default=0.0)
    mid_trend_candidate_enrichment.add_argument("--quantiles", type=int, default=5)
    mid_trend_candidate_enrichment.add_argument("--top-ns", type=parse_top_ks, default=(20, 50, 100))
    mid_trend_candidate_enrichment.add_argument("--period", default="Q")
    mid_trend_candidate_enrichment.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    mid_trend_full_universe_enrichment = subparsers.add_parser(
        "mid-trend-full-universe-enrichment"
    )
    mid_trend_full_universe_enrichment.add_argument("--start-date", required=True)
    mid_trend_full_universe_enrichment.add_argument("--end-date", required=True)
    mid_trend_full_universe_enrichment.add_argument("--candidate-scores-path", required=True)
    mid_trend_full_universe_enrichment.add_argument("--adjust-type", default="hfq")
    mid_trend_full_universe_enrichment.add_argument("--quantiles", type=int, default=5)
    mid_trend_full_universe_enrichment.add_argument("--top-ns", type=parse_top_ks, default=(20, 50, 100))
    mid_trend_full_universe_enrichment.add_argument("--period", default="Q")
    mid_trend_full_universe_enrichment.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    entry_success_reverse_profile = subparsers.add_parser("entry-success-reverse-profile")
    entry_success_reverse_profile.add_argument("--start-date", required=True)
    entry_success_reverse_profile.add_argument("--end-date", required=True)
    entry_success_reverse_profile.add_argument("--entry-success-labels-path", required=True)
    entry_success_reverse_profile.add_argument("--factor-names", type=parse_factor_names)
    entry_success_reverse_profile.add_argument("--horizons", type=parse_research_horizons, default=(20, 40, 60))
    entry_success_reverse_profile.add_argument("--period", default="Q")
    entry_success_reverse_profile.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    entry_success_candidate_v2 = subparsers.add_parser("entry-success-candidate-v2")
    entry_success_candidate_v2.add_argument("--start-date", required=True)
    entry_success_candidate_v2.add_argument("--end-date", required=True)
    entry_success_candidate_v2.add_argument("--factor-rank-path", required=True)
    entry_success_candidate_v2.add_argument("--horizon", type=int, default=40)
    entry_success_candidate_v2.add_argument("--max-factors", type=int)
    entry_success_candidate_v2.add_argument("--min-candidate-score", type=float, default=0.0)
    entry_success_candidate_v2.add_argument("--min-sign-match-rate", type=float, default=0.6)
    entry_success_candidate_v2.add_argument("--adjust-type", default="hfq")
    entry_success_candidate_v2.add_argument("--quantiles", type=int, default=5)
    entry_success_candidate_v2.add_argument("--top-ns", type=parse_top_ks, default=(20, 50, 100))
    entry_success_candidate_v2.add_argument("--period", default="Q")
    entry_success_candidate_v2.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    trend_candidate_backtest = subparsers.add_parser("trend-candidate-backtest")
    trend_candidate_backtest.add_argument("--start-date", required=True)
    trend_candidate_backtest.add_argument("--end-date", required=True)
    trend_candidate_backtest.add_argument("--candidate-scores-path", required=True)
    trend_candidate_backtest.add_argument("--top-ns", type=parse_top_ks, default=(20, 50))
    trend_candidate_backtest.add_argument("--holding-days", type=parse_holding_days, default=(5, 10, 20))
    trend_candidate_backtest.add_argument("--transaction-cost-bps", type=float, default=20.0)
    trend_candidate_backtest.add_argument("--adjust-type", default="hfq")
    trend_candidate_backtest.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    current_mid_trend_strategy_v1 = subparsers.add_parser(
        "current-mid-trend-strategy-v1-backtest"
    )
    current_mid_trend_strategy_v1.add_argument("--start-date", required=True)
    current_mid_trend_strategy_v1.add_argument("--end-date", required=True)
    current_mid_trend_strategy_v1.add_argument(
        "--regime-path",
        default="outputs/research/market_regime_confirmation_v1_tight3b_bt100_20230103_20260605/market_regime_confirmation_daily.csv",
    )
    current_mid_trend_strategy_v1.add_argument(
        "--funnel-detail-path",
        default="outputs/research/mid_trend_watch_funnel_20230103_20260605_aligned/mid_trend_watch_funnel_detail.csv",
    )
    current_mid_trend_strategy_v1.add_argument("--top-n", type=int, default=5)
    current_mid_trend_strategy_v1.add_argument("--adjust-type", default="hfq")
    current_mid_trend_strategy_v1.add_argument(
        "--output-dir",
        default="outputs/research/current_mid_trend_strategy_v1",
    )

    industry_focus_backtest = subparsers.add_parser("industry-focus-backtest")
    industry_focus_backtest.add_argument("--start-date", required=True)
    industry_focus_backtest.add_argument("--end-date", required=True)
    industry_focus_backtest.add_argument("--top-n", type=int, default=20)
    industry_focus_backtest.add_argument("--dynamic-top-k", type=int, default=4)
    industry_focus_backtest.add_argument("--min-industry-stocks", type=int, default=20)
    industry_focus_backtest.add_argument("--industry-system", default="csrc")
    industry_focus_backtest.add_argument("--industry-level", type=int, default=1)
    industry_focus_backtest.add_argument("--adjust-type", default="hfq")
    industry_focus_backtest.add_argument(
        "--reports-dir",
        default="/Users/xiwei/stock_research/reports",
    )

    industry_v1_attribution = subparsers.add_parser("industry-v1-attribution")
    industry_v1_attribution.add_argument("--start-date", required=True)
    industry_v1_attribution.add_argument("--end-date", required=True)
    industry_v1_attribution.add_argument("--min-industry-stocks", type=int, default=20)
    industry_v1_attribution.add_argument("--dynamic-top-k", type=int, default=4)
    industry_v1_attribution.add_argument("--industry-system", default="csrc")
    industry_v1_attribution.add_argument("--industry-level", type=int, default=1)
    industry_v1_attribution.add_argument("--adjust-type", default="hfq")
    industry_v1_attribution.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    industry_focus_v2_diagnostics = subparsers.add_parser("industry-focus-v2-diagnostics")
    industry_focus_v2_diagnostics.add_argument("--start-date", required=True)
    industry_focus_v2_diagnostics.add_argument("--end-date", required=True)
    industry_focus_v2_diagnostics.add_argument("--min-industry-stocks", type=int, default=20)
    industry_focus_v2_diagnostics.add_argument("--dynamic-top-k", type=int, default=4)
    industry_focus_v2_diagnostics.add_argument("--industry-system", default="csrc")
    industry_focus_v2_diagnostics.add_argument("--industry-level", type=int, default=1)
    industry_focus_v2_diagnostics.add_argument("--adjust-type", default="hfq")
    industry_focus_v2_diagnostics.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    industry_focus_v2_backtest = subparsers.add_parser("industry-focus-v2-backtest")
    industry_focus_v2_backtest.add_argument("--start-date", required=True)
    industry_focus_v2_backtest.add_argument("--end-date", required=True)
    industry_focus_v2_backtest.add_argument("--diagnostics-path", required=True)
    industry_focus_v2_backtest.add_argument("--top-n", type=int, default=20)
    industry_focus_v2_backtest.add_argument("--transaction-cost-bps", type=float, default=20.0)
    industry_focus_v2_backtest.add_argument("--industry-system", default="csrc")
    industry_focus_v2_backtest.add_argument("--industry-level", type=int, default=1)
    industry_focus_v2_backtest.add_argument("--adjust-type", default="hfq")
    industry_focus_v2_backtest.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    dragon_research_v1 = subparsers.add_parser("dragon-research-v1")
    dragon_research_v1.add_argument("--start-date", required=True)
    dragon_research_v1.add_argument("--end-date", required=True)
    dragon_research_v1.add_argument("--hot-industry-top-n", type=int, default=6)
    dragon_research_v1.add_argument("--adjust-type", default="hfq")
    dragon_research_v1.add_argument("--industry-system", default="csrc")
    dragon_research_v1.add_argument("--industry-level", type=int, default=1)
    dragon_research_v1.add_argument("--industry-diagnostics-path")
    dragon_research_v1.add_argument("--candidate-scores-path")
    dragon_research_v1.add_argument("--lifecycle-samples-path")
    dragon_research_v1.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    dragon_case_library_build = subparsers.add_parser("dragon-case-library-build")
    dragon_case_library_build.add_argument("--start-date", required=True)
    dragon_case_library_build.add_argument("--end-date", required=True)
    dragon_case_library_build.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )
    dragon_case_library_build.add_argument(
        "--seed-path",
        default="/Users/xiwei/stock_research/data/seed/dragon_case_seed.csv",
    )
    dragon_case_library_build.add_argument("--adjust-type", default="hfq")

    dragon_case_library_diagnose = subparsers.add_parser("dragon-case-library-diagnose")
    dragon_case_library_diagnose.add_argument("--case-path", required=True)
    dragon_case_library_diagnose.add_argument("--start-date", required=True)
    dragon_case_library_diagnose.add_argument("--end-date", required=True)
    dragon_case_library_diagnose.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )
    dragon_case_library_diagnose.add_argument("--adjust-type", default="hfq")

    dragon_case_import_web_seeds = subparsers.add_parser("dragon-case-import-web-seeds")
    dragon_case_import_web_seeds.add_argument("--input", required=True)
    dragon_case_import_web_seeds.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    dragon_case_expand_web_seeds = subparsers.add_parser("dragon-case-expand-web-seeds")
    dragon_case_expand_web_seeds.add_argument("--article-seed", required=True)
    dragon_case_expand_web_seeds.add_argument("--output", required=True)
    dragon_case_expand_web_seeds.add_argument("--start-date", required=True)
    dragon_case_expand_web_seeds.add_argument("--end-date", required=True)
    dragon_case_expand_web_seeds.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    dragon_case_web_verify = subparsers.add_parser("dragon-case-web-verify")
    dragon_case_web_verify.add_argument("--candidate-path", required=True)
    dragon_case_web_verify.add_argument("--start-date", required=True)
    dragon_case_web_verify.add_argument("--end-date", required=True)
    dragon_case_web_verify.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )
    dragon_case_web_verify.add_argument("--adjust-type", default="hfq")

    dragon_case_apply_source_backfill = subparsers.add_parser("dragon-case-apply-source-backfill")
    dragon_case_apply_source_backfill.add_argument("--tasks-path", required=True)
    dragon_case_apply_source_backfill.add_argument(
        "--article-seed",
        default="/Users/xiwei/stock_research/data/seed/dragon_case_web_article_seed_2024_2026.csv",
    )
    dragon_case_apply_source_backfill.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )
    dragon_case_apply_source_backfill.add_argument("--dry-run", action="store_true")

    dragon_case_source_backfill_compare = subparsers.add_parser("dragon-case-source-backfill-compare")
    dragon_case_source_backfill_compare.add_argument("--before-curated", required=True)
    dragon_case_source_backfill_compare.add_argument("--after-curated", required=True)
    dragon_case_source_backfill_compare.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    dragon_case_source_backfill_workpack = subparsers.add_parser("dragon-case-source-backfill-workpack")
    dragon_case_source_backfill_workpack.add_argument("--tasks-path", required=True)
    dragon_case_source_backfill_workpack.add_argument("--top-n", type=int, default=20)
    dragon_case_source_backfill_workpack.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    dragon_case_source_backfill_check = subparsers.add_parser("dragon-case-source-backfill-check")
    dragon_case_source_backfill_check.add_argument("--apply-summary", required=True)
    dragon_case_source_backfill_check.add_argument("--delta-summary", required=True)
    dragon_case_source_backfill_check.add_argument("--curated", required=True)
    dragon_case_source_backfill_check.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    dragon_case_failure_event_rules_v2 = subparsers.add_parser("dragon-case-failure-event-rules-v2")
    dragon_case_failure_event_rules_v2.add_argument(
        "--case-path",
        default="/Users/xiwei/stock_research/outputs/research/dragon_case_curated_library_2024_2026.csv",
    )
    dragon_case_failure_event_rules_v2.add_argument(
        "--snapshot-path",
        default="/Users/xiwei/stock_research/outputs/research/dragon_case_factor_snapshot_2024_2026.csv",
    )
    dragon_case_failure_event_rules_v2.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    validate_technical_methods = subparsers.add_parser("validate-technical-methods")
    validate_technical_methods.add_argument("--start-date", required=True)
    validate_technical_methods.add_argument("--end-date", required=True)
    validate_technical_methods.add_argument("--adjust-type", default="qfq")
    validate_technical_methods.add_argument("--sample-size", type=int)
    validate_technical_methods.add_argument("--asset-id")
    validate_technical_methods.add_argument("--ts-code")
    validate_technical_methods.add_argument("--feature-source", default="technical_table")
    validate_technical_methods.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    validate_alpha191_pilot = subparsers.add_parser("validate-alpha191-pilot")
    validate_alpha191_pilot.add_argument("--start-date", required=True)
    validate_alpha191_pilot.add_argument("--end-date", required=True)
    validate_alpha191_pilot.add_argument("--adjust-type", default="qfq")
    validate_alpha191_pilot.add_argument("--sample-size", type=int)
    validate_alpha191_pilot.add_argument("--asset-id")
    validate_alpha191_pilot.add_argument("--ts-code")
    validate_alpha191_pilot.add_argument("--strong-start-date", default="2025-01-01")
    validate_alpha191_pilot.add_argument("--strong-end-date", default="2025-05-01")
    validate_alpha191_pilot.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    validate_alpha191_expanded = subparsers.add_parser("validate-alpha191-expanded")
    validate_alpha191_expanded.add_argument("--start-date", required=True)
    validate_alpha191_expanded.add_argument("--end-date", required=True)
    validate_alpha191_expanded.add_argument("--adjust-type", default="qfq")
    validate_alpha191_expanded.add_argument("--sample-size", type=int)
    validate_alpha191_expanded.add_argument("--asset-id")
    validate_alpha191_expanded.add_argument("--ts-code")
    validate_alpha191_expanded.add_argument("--strong-start-date", default="2025-01-01")
    validate_alpha191_expanded.add_argument("--strong-end-date", default="2025-05-01")
    validate_alpha191_expanded.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_risk_diagnostics_after_failure_rule_v21 = subparsers.add_parser(
        "lhb-risk-diagnostics-after-failure-rule-v2-1"
    )
    lhb_risk_diagnostics_after_failure_rule_v21.add_argument(
        "--case-path",
        default="/Users/xiwei/stock_research/outputs/research/dragon_case_curated_library_2024_2026.csv",
    )
    lhb_risk_diagnostics_after_failure_rule_v21.add_argument(
        "--failure-audit-path",
        default="/Users/xiwei/stock_research/outputs/research/failure_event_rule_v2_audit.csv",
    )
    lhb_risk_diagnostics_after_failure_rule_v21.add_argument(
        "--snapshot-path",
        default="/Users/xiwei/stock_research/outputs/research/dragon_case_factor_snapshot_2024_2026.csv",
    )
    lhb_risk_diagnostics_after_failure_rule_v21.add_argument(
        "--lhb-features-path",
        default="/Users/xiwei/stock_research/outputs/research/lhb_event_features_daily_sample.csv",
    )
    lhb_risk_diagnostics_after_failure_rule_v21.add_argument(
        "--alignment-path",
        default="/Users/xiwei/stock_research/outputs/research/dragon_case_lhb_alignment_audit_2024_2026.csv",
    )
    lhb_risk_diagnostics_after_failure_rule_v21.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_sample_import = subparsers.add_parser("lhb-sample-import")
    lhb_sample_import.add_argument("--start-date", required=True)
    lhb_sample_import.add_argument("--end-date", required=True)
    lhb_sample_import.add_argument("--ts-codes")
    lhb_sample_import.add_argument("--provider", default="tushare")
    lhb_sample_import.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_event_features_build = subparsers.add_parser("lhb-build-event-features")
    lhb_event_features_build.add_argument("--start-date", required=True)
    lhb_event_features_build.add_argument("--end-date", required=True)
    lhb_event_features_build.add_argument("--ts-codes")
    lhb_event_features_build.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    dragon_case_lhb_alignment = subparsers.add_parser("dragon-case-lhb-alignment-audit")
    dragon_case_lhb_alignment.add_argument("--curated-path", required=True)
    dragon_case_lhb_alignment.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    dragon_case_lhb_summary = subparsers.add_parser("dragon-case-lhb-summary")
    dragon_case_lhb_summary.add_argument("--curated-path", required=True)
    dragon_case_lhb_summary.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_case_difference_report = subparsers.add_parser("lhb-case-difference-report")
    lhb_case_difference_report.add_argument("--case-path", required=True)
    lhb_case_difference_report.add_argument("--lhb-features-path", required=True)
    lhb_case_difference_report.add_argument("--alignment-path", required=True)
    lhb_case_difference_report.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_risk_feature_diagnostics = subparsers.add_parser("lhb-risk-feature-diagnostics")
    lhb_risk_feature_diagnostics.add_argument("--case-path", required=True)
    lhb_risk_feature_diagnostics.add_argument("--lhb-features-path", required=True)
    lhb_risk_feature_diagnostics.add_argument("--alignment-path", required=True)
    lhb_risk_feature_diagnostics.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_follow_exit_replay = subparsers.add_parser("lhb-follow-exit-replay-v1")
    lhb_follow_exit_replay.add_argument("--case-path", required=True)
    lhb_follow_exit_replay.add_argument("--lhb-features-path", required=True)
    lhb_follow_exit_replay.add_argument("--alignment-path", required=True)
    lhb_follow_exit_replay.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_shortline_event_replay = subparsers.add_parser("lhb-shortline-event-replay-v1")
    lhb_shortline_event_replay.add_argument("--case-path", required=True)
    lhb_shortline_event_replay.add_argument("--lhb-features-path", required=True)
    lhb_shortline_event_replay.add_argument("--alignment-path", required=True)
    lhb_shortline_event_replay.add_argument("--market-path")
    lhb_shortline_event_replay.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_follow_avoid_rule_audit = subparsers.add_parser("lhb-follow-avoid-rule-audit-v1")
    lhb_follow_avoid_rule_audit.add_argument(
        "--event-replay-path",
        default="/Users/xiwei/stock_research/outputs/research/lhb_shortline_event_replay_v1.csv",
    )
    lhb_follow_avoid_rule_audit.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_exit_rule_audit = subparsers.add_parser("lhb-exit-rule-audit-v1")
    lhb_exit_rule_audit.add_argument(
        "--event-replay-path",
        default="/Users/xiwei/stock_research/outputs/research/lhb_shortline_event_replay_v1.csv",
    )
    lhb_exit_rule_audit.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    daily_lhb_shortline_watchlist = subparsers.add_parser("daily-lhb-shortline-watchlist-v1")
    daily_lhb_shortline_watchlist.add_argument(
        "--event-replay-path",
        default="/Users/xiwei/stock_research/outputs/research/lhb_shortline_event_replay_v1.csv",
    )
    daily_lhb_shortline_watchlist.add_argument(
        "--rule-recommendations-path",
        default="/Users/xiwei/stock_research/outputs/research/lhb_follow_avoid_rule_recommendations_v1.csv",
    )
    daily_lhb_shortline_watchlist.add_argument("--rule-registry-path")
    daily_lhb_shortline_watchlist.add_argument("--trade-date", required=True)
    daily_lhb_shortline_watchlist.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_shortline_strategy_effectiveness = subparsers.add_parser("lhb-shortline-strategy-effectiveness-v1")
    lhb_shortline_strategy_effectiveness.add_argument(
        "--event-replay-path",
        default="/Users/xiwei/stock_research/outputs/research/lhb_shortline_event_replay_v1.csv",
    )
    lhb_shortline_strategy_effectiveness.add_argument("--daily-watchlist-path")
    lhb_shortline_strategy_effectiveness.add_argument("--min-sample-count", type=int, default=10)
    lhb_shortline_strategy_effectiveness.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_shortline_rule_calibration = subparsers.add_parser("lhb-shortline-rule-calibration-v1")
    lhb_shortline_rule_calibration.add_argument(
        "--follow-combo-path",
        default="/Users/xiwei/stock_research/outputs/research/lhb_shortline_follow_combo_effectiveness_v1.csv",
    )
    lhb_shortline_rule_calibration.add_argument(
        "--exit-combo-path",
        default="/Users/xiwei/stock_research/outputs/research/lhb_shortline_exit_combo_effectiveness_v1.csv",
    )
    lhb_shortline_rule_calibration.add_argument("--rule-version", default="lhb_shortline_rules_v1_1")
    lhb_shortline_rule_calibration.add_argument("--min-sample-count", type=int, default=10)
    lhb_shortline_rule_calibration.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_shortline_shadow_backtest = subparsers.add_parser("lhb-shortline-shadow-backtest-v1")
    lhb_shortline_shadow_backtest.add_argument(
        "--event-replay-path",
        default="/Users/xiwei/stock_research/outputs/research/lhb_shortline_event_replay_v1.csv",
    )
    lhb_shortline_shadow_backtest.add_argument("--start-date", required=True)
    lhb_shortline_shadow_backtest.add_argument("--end-date", required=True)
    lhb_shortline_shadow_backtest.add_argument("--top-n", default="5,10,20")
    lhb_shortline_shadow_backtest.add_argument("--pool-mode", default="strict_second_wave")
    lhb_shortline_shadow_backtest.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_shortline_intraday_confirmation = subparsers.add_parser("lhb-shortline-intraday-confirmation-v1")
    lhb_shortline_intraday_confirmation.add_argument(
        "--candidate-path",
        default="/Users/xiwei/stock_research/outputs/research/lhb_shortline_shadow_backtest_selected_trades_20250101_20260608_v1.csv",
    )
    lhb_shortline_intraday_confirmation.add_argument("--minute-bars-path", required=True)
    lhb_shortline_intraday_confirmation.add_argument("--freq", default="5min")
    lhb_shortline_intraday_confirmation.add_argument("--adjust-type", default="raw")
    lhb_shortline_intraday_confirmation.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_full_market_pool_backtest = subparsers.add_parser("lhb-full-market-pool-backtest-v1")
    lhb_full_market_pool_backtest.add_argument(
        "--lhb-features-path",
        default="/Users/xiwei/stock_research/outputs/research/lhb_feature_full_gap_fill_20260606/lhb_event_features_daily_sample.csv",
    )
    lhb_full_market_pool_backtest.add_argument("--daily-bars-path", required=True)
    lhb_full_market_pool_backtest.add_argument("--start-date", required=True)
    lhb_full_market_pool_backtest.add_argument("--end-date", required=True)
    lhb_full_market_pool_backtest.add_argument("--top-n", default="5,10,20")
    lhb_full_market_pool_backtest.add_argument("--pool-mode", default="raw_lhb_positive")
    lhb_full_market_pool_backtest.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_intraday_filtered_topn = subparsers.add_parser("lhb-intraday-filtered-topn-comparison-v1")
    lhb_intraday_filtered_topn.add_argument("--selected-trades-path", required=True)
    lhb_intraday_filtered_topn.add_argument("--intraday-detail-path", required=True)
    lhb_intraday_filtered_topn.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_phase12a_multi_context = subparsers.add_parser("lhb-phase12a-multi-context-decision-v1")
    lhb_phase12a_multi_context.add_argument("--selected-trades-path", required=True)
    lhb_phase12a_multi_context.add_argument("--minute-bars-path", required=True)
    lhb_phase12a_multi_context.add_argument("--intraday-detail-path", required=True)
    lhb_phase12a_multi_context.add_argument("--pre-context-days", type=int, default=2)
    lhb_phase12a_multi_context.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_phase12a_rule = subparsers.add_parser("lhb-phase12a-rule-decision-v1")
    lhb_phase12a_rule.add_argument("--phase12a-decision-path", required=True)
    lhb_phase12a_rule.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_phase12a_real_entry = subparsers.add_parser("lhb-phase12a-real-entry-backtest-v1")
    lhb_phase12a_real_entry.add_argument("--rule-decision-path", required=True)
    lhb_phase12a_real_entry.add_argument("--minute-bars-path", required=True)
    lhb_phase12a_real_entry.add_argument("--daily-bars-path", required=True)
    lhb_phase12a_real_entry.add_argument("--entry-start-time", default="10:30:00")
    lhb_phase12a_real_entry.add_argument("--slippage-bps", type=float, default=0.0)
    lhb_phase12a_real_entry.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_phase12b_signal_exit = subparsers.add_parser("lhb-phase12b-signal-exit-v1")
    lhb_phase12b_signal_exit.add_argument("--entry-trades-path", required=True)
    lhb_phase12b_signal_exit.add_argument("--minute-bars-path", required=True)
    lhb_phase12b_signal_exit.add_argument("--max-hold-days", type=int, default=5)
    lhb_phase12b_signal_exit.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_phase13_two_stage = subparsers.add_parser("lhb-phase13-two-stage-follow-pool-v1")
    lhb_phase13_two_stage.add_argument("--event-features-path", required=True)
    lhb_phase13_two_stage.add_argument("--t1-features-path", required=True)
    lhb_phase13_two_stage.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_phase13b_topn = subparsers.add_parser("lhb-phase13b-topn-filter-v1")
    lhb_phase13b_topn.add_argument("--phase13-decision-path", required=True)
    lhb_phase13b_topn.add_argument("--top-n", default="5,10,20")
    lhb_phase13b_topn.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_phase14_lifecycle_exit = subparsers.add_parser("lhb-phase14-lifecycle-exit-v1")
    lhb_phase14_lifecycle_exit.add_argument("--entry-trades-path", required=True)
    lhb_phase14_lifecycle_exit.add_argument("--minute-bars-path", required=True)
    lhb_phase14_lifecycle_exit.add_argument("--max-hold-days", type=int, default=5)
    lhb_phase14_lifecycle_exit.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_phase14b_threshold_scan = subparsers.add_parser("lhb-phase14b-threshold-scan-v1")
    lhb_phase14b_threshold_scan.add_argument("--entry-trades-path", required=True)
    lhb_phase14b_threshold_scan.add_argument("--minute-bars-path", required=True)
    lhb_phase14b_threshold_scan.add_argument("--max-hold-days", type=int, default=5)
    lhb_phase14b_threshold_scan.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_phase14c_lifecycle_portfolio = subparsers.add_parser("lhb-phase14c-lifecycle-portfolio-v1")
    lhb_phase14c_lifecycle_portfolio.add_argument("--entry-trades-path", required=True)
    lhb_phase14c_lifecycle_portfolio.add_argument("--minute-bars-path", required=True)
    lhb_phase14c_lifecycle_portfolio.add_argument("--max-hold-days", type=int, default=5)
    lhb_phase14c_lifecycle_portfolio.add_argument("--threshold-profile", default="sensitive_entry_buffer")
    lhb_phase14c_lifecycle_portfolio.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_phase14e_limit_lock_filter = subparsers.add_parser("lhb-phase14e-limit-lock-filter-v1")
    lhb_phase14e_limit_lock_filter.add_argument("--entry-trades-path", required=True)
    lhb_phase14e_limit_lock_filter.add_argument("--lifecycle-trades-path", required=True)
    lhb_phase14e_limit_lock_filter.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_phase15_cash_account = subparsers.add_parser("lhb-phase15-cash-account-backtest-v1")
    lhb_phase15_cash_account.add_argument("--lifecycle-trades-path", required=True)
    lhb_phase15_cash_account.add_argument("--max-positions", type=int, default=10)
    lhb_phase15_cash_account.add_argument("--position-pct", type=float, default=0.10)
    lhb_phase15_cash_account.add_argument("--cutoff-start-date")
    lhb_phase15_cash_account.add_argument("--cutoff-end-date")
    lhb_phase15_cash_account.add_argument("--strict-cutoff-audit", action="store_true")
    lhb_phase15_cash_account.add_argument("--allow-phase14e-best", action="store_true")
    lhb_phase15_cash_account.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_cutoff_audit = subparsers.add_parser("lhb-cutoff-audit-v1")
    lhb_cutoff_audit.add_argument("--path", action="append", required=True)
    lhb_cutoff_audit.add_argument("--start-date", required=True)
    lhb_cutoff_audit.add_argument("--end-date", required=True)
    lhb_cutoff_audit.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )
    lhb_cutoff_audit.add_argument("--no-strict", action="store_true")
    lhb_cutoff_audit.add_argument("--allow-phase14e-best", action="store_true")

    lhb_phase16_quality = subparsers.add_parser("lhb-phase16-quality-improvement-diagnostics-v1")
    lhb_phase16_quality.add_argument("--lifecycle-trades-path", required=True)
    lhb_phase16_quality.add_argument("--real-entry-trades-path", required=True)
    lhb_phase16_quality.add_argument("--selected-trades-path", required=True)
    lhb_phase16_quality.add_argument("--min-group-count", type=int, default=20)
    lhb_phase16_quality.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_phase16b_limit_break = subparsers.add_parser("lhb-phase16b-limit-break-failed-exit-replay-v1")
    lhb_phase16b_limit_break.add_argument("--lifecycle-trades-path", required=True)
    lhb_phase16b_limit_break.add_argument("--real-entry-trades-path", required=True)
    lhb_phase16b_limit_break.add_argument("--selected-trades-path", required=True)
    lhb_phase16b_limit_break.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_phase16c_limit_break = subparsers.add_parser("lhb-phase16c-limit-break-failed-rule-scan-v1")
    lhb_phase16c_limit_break.add_argument("--lifecycle-trades-path", required=True)
    lhb_phase16c_limit_break.add_argument("--real-entry-trades-path", required=True)
    lhb_phase16c_limit_break.add_argument("--selected-trades-path", required=True)
    lhb_phase16c_limit_break.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_phase16d_indicator = subparsers.add_parser("lhb-phase16d-limit-break-failed-indicator-discovery-v1")
    lhb_phase16d_indicator.add_argument("--lifecycle-trades-path", required=True)
    lhb_phase16d_indicator.add_argument("--real-entry-trades-path", required=True)
    lhb_phase16d_indicator.add_argument("--selected-trades-path", required=True)
    lhb_phase16d_indicator.add_argument("--minute-bars-path", required=True)
    lhb_phase16d_indicator.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_phase16e_indicator_rule = subparsers.add_parser("lhb-phase16e-limit-break-failed-indicator-rule-scan-v1")
    lhb_phase16e_indicator_rule.add_argument("--lifecycle-trades-path", required=True)
    lhb_phase16e_indicator_rule.add_argument("--real-entry-trades-path", required=True)
    lhb_phase16e_indicator_rule.add_argument("--selected-trades-path", required=True)
    lhb_phase16e_indicator_rule.add_argument("--minute-bars-path", required=True)
    lhb_phase16e_indicator_rule.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_shortline_daily = subparsers.add_parser("run-lhb-shortline-daily-v1")
    lhb_shortline_daily.add_argument("--case-path", required=True)
    lhb_shortline_daily.add_argument("--lhb-features-path", required=True)
    lhb_shortline_daily.add_argument("--alignment-path", required=True)
    lhb_shortline_daily.add_argument("--market-path")
    lhb_shortline_daily.add_argument("--trade-date", required=True)
    lhb_shortline_daily.add_argument("--rule-version", default="lhb_shortline_rules_v1_1")
    lhb_shortline_daily.add_argument("--min-sample-count", type=int, default=10)
    lhb_shortline_daily.add_argument("--build-watchlist-diagnostics", action="store_true")
    lhb_shortline_daily.add_argument("--score-version", default="manual_v1")
    lhb_shortline_daily.add_argument("--top-n", type=int, default=50)
    lhb_shortline_daily.add_argument("--risk-watch-n", type=int, default=10)
    lhb_shortline_daily.add_argument("--opportunity-watch-n", type=int, default=10)
    lhb_shortline_daily.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_shortline_manual_review = subparsers.add_parser("lhb-shortline-manual-review-v1")
    lhb_shortline_manual_review.add_argument("--daily-watchlist-path", required=True)
    lhb_shortline_manual_review.add_argument("--effectiveness-detail-path")
    lhb_shortline_manual_review.add_argument("--manual-review-path")
    lhb_shortline_manual_review.add_argument("--trade-date", required=True)
    lhb_shortline_manual_review.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    lhb_coverage_failure_plan = subparsers.add_parser("lhb-coverage-failure-plan")
    lhb_coverage_failure_plan.add_argument(
        "--coverage-gap-path",
        default="/Users/xiwei/stock_research/outputs/research/lhb_coverage_gap_recommendations.csv",
    )
    lhb_coverage_failure_plan.add_argument(
        "--case-path",
        default="/Users/xiwei/stock_research/outputs/research/dragon_case_curated_library_2024_2026.csv",
    )
    lhb_coverage_failure_plan.add_argument(
        "--snapshot-path",
        default="/Users/xiwei/stock_research/outputs/research/dragon_case_factor_snapshot_2024_2026.csv",
    )
    lhb_coverage_failure_plan.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    fixed_industry_reconciliation = subparsers.add_parser(
        "fixed-industry-reconciliation"
    )
    fixed_industry_reconciliation.add_argument("--start-date", required=True)
    fixed_industry_reconciliation.add_argument("--end-date", required=True)
    fixed_industry_reconciliation.add_argument("--top-n", type=int, default=20)
    fixed_industry_reconciliation.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=20.0,
    )
    fixed_industry_reconciliation.add_argument("--industry-system", default="csrc")
    fixed_industry_reconciliation.add_argument("--industry-level", type=int, default=1)
    fixed_industry_reconciliation.add_argument("--adjust-type", default="hfq")
    fixed_industry_reconciliation.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    industry_error_audit = subparsers.add_parser("industry-error-audit")
    industry_error_audit.add_argument("--diagnostics-path", required=True)
    industry_error_audit.add_argument("--start-date", required=True)
    industry_error_audit.add_argument("--end-date", required=True)
    industry_error_audit.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )
    industry_error_audit.add_argument(
        "--backtest-summary-path",
        default="/Users/xiwei/stock_research/outputs/research/industry_focus_score_v2_backtest_summary.csv",
    )
    industry_error_audit.add_argument(
        "--annual-metrics-path",
        default="/Users/xiwei/stock_research/outputs/research/industry_focus_score_v2_backtest_annual_metrics.csv",
    )

    industry_mainline_regime = subparsers.add_parser(
        "industry-mainline-regime-diagnostics"
    )
    industry_mainline_regime.add_argument("--diagnostics-path", required=True)
    industry_mainline_regime.add_argument("--start-date", required=True)
    industry_mainline_regime.add_argument("--end-date", required=True)
    industry_mainline_regime.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    industry_regime_gated_backtest = subparsers.add_parser(
        "industry-regime-gated-backtest"
    )
    industry_regime_gated_backtest.add_argument("--start-date", required=True)
    industry_regime_gated_backtest.add_argument("--end-date", required=True)
    industry_regime_gated_backtest.add_argument("--diagnostics-path", required=True)
    industry_regime_gated_backtest.add_argument("--regime-path", required=True)
    industry_regime_gated_backtest.add_argument("--mainline-path", required=True)
    industry_regime_gated_backtest.add_argument("--top-n", type=int, default=20)
    industry_regime_gated_backtest.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=20.0,
    )
    industry_regime_gated_backtest.add_argument("--industry-system", default="csrc")
    industry_regime_gated_backtest.add_argument("--industry-level", type=int, default=1)
    industry_regime_gated_backtest.add_argument("--adjust-type", default="hfq")
    industry_regime_gated_backtest.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    industry_exposure_risk_control = subparsers.add_parser(
        "industry-exposure-risk-control"
    )
    industry_exposure_risk_control.add_argument("--start-date", required=True)
    industry_exposure_risk_control.add_argument("--end-date", required=True)
    industry_exposure_risk_control.add_argument("--diagnostics-path", required=True)
    industry_exposure_risk_control.add_argument("--regime-path", required=True)
    industry_exposure_risk_control.add_argument("--mainline-path", required=True)
    industry_exposure_risk_control.add_argument("--top-n", type=int, default=20)
    industry_exposure_risk_control.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=20.0,
    )
    industry_exposure_risk_control.add_argument("--industry-system", default="csrc")
    industry_exposure_risk_control.add_argument("--industry-level", type=int, default=1)
    industry_exposure_risk_control.add_argument("--adjust-type", default="hfq")
    industry_exposure_risk_control.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research",
    )

    build_universe = subparsers.add_parser("build-universe")
    build_universe.add_argument("--date", required=True)
    build_universe.add_argument("--preset", default="research_default")
    build_universe.add_argument("--output", required=True)
    build_universe.add_argument("--min-listed-days", type=int)
    build_universe.add_argument("--min-avg-turnover-amount", type=float)
    build_universe.add_argument("--min-avg-volume", type=float)
    build_universe.add_argument("--liquidity-lookback-days", type=int)
    build_universe.add_argument("--max-suspended-days", type=int)

    explain_universe = subparsers.add_parser("explain-universe")
    explain_universe.add_argument("--date", required=True)
    explain_universe.add_argument("--code", required=True)
    explain_universe.add_argument("--preset", default="research_default")
    explain_universe.add_argument("--min-listed-days", type=int)
    explain_universe.add_argument("--min-avg-turnover-amount", type=float)
    explain_universe.add_argument("--min-avg-volume", type=float)
    explain_universe.add_argument("--liquidity-lookback-days", type=int)
    explain_universe.add_argument("--max-suspended-days", type=int)

    check_watchlist_universe = subparsers.add_parser("check-watchlist-universe")
    check_watchlist_universe.add_argument("--date", required=True)
    check_watchlist_universe.add_argument("--watchlist", required=True)
    check_watchlist_universe.add_argument("--preset", default="watchlist_check")
    check_watchlist_universe.add_argument("--output", required=True)
    check_watchlist_universe.add_argument("--min-listed-days", type=int)
    check_watchlist_universe.add_argument("--min-avg-turnover-amount", type=float)
    check_watchlist_universe.add_argument("--min-avg-volume", type=float)
    check_watchlist_universe.add_argument("--liquidity-lookback-days", type=int)
    check_watchlist_universe.add_argument("--max-suspended-days", type=int)

    watchlist_build = subparsers.add_parser("watchlist-build")
    watchlist_build.add_argument("--trade-date", required=True)
    watchlist_build.add_argument("--watchlist-id", required=True)
    watchlist_build.add_argument("--score-version", default="manual_v1")
    watchlist_build.add_argument("--top-n", type=int, default=30)
    watchlist_build.add_argument("--output-dir", required=True)

    build_watchlist_diagnostics = subparsers.add_parser("build-watchlist-diagnostics")
    build_watchlist_diagnostics.add_argument("--trade-date", required=True)
    build_watchlist_diagnostics.add_argument("--score-version", default="manual_v1")
    build_watchlist_diagnostics.add_argument("--top-n", type=int, default=50)
    build_watchlist_diagnostics.add_argument("--risk-watch-n", type=int, default=10)
    build_watchlist_diagnostics.add_argument("--opportunity-watch-n", type=int, default=10)
    build_watchlist_diagnostics.add_argument("--lhb-shortline-path")
    build_watchlist_diagnostics.add_argument("--output-dir", default="outputs/research")

    build_watchlist_diagnostics_range = subparsers.add_parser("build-watchlist-diagnostics-range")
    build_watchlist_diagnostics_range.add_argument("--start-date", required=True)
    build_watchlist_diagnostics_range.add_argument("--end-date", required=True)
    build_watchlist_diagnostics_range.add_argument("--score-version", default="manual_v1")
    build_watchlist_diagnostics_range.add_argument("--top-n", type=int, default=50)
    build_watchlist_diagnostics_range.add_argument("--risk-watch-n", type=int, default=10)
    build_watchlist_diagnostics_range.add_argument("--opportunity-watch-n", type=int, default=10)
    build_watchlist_diagnostics_range.add_argument("--lhb-shortline-path")
    build_watchlist_diagnostics_range.add_argument("--output-dir", default="outputs/research")
    build_watchlist_diagnostics_range.add_argument("--force", action="store_true")

    review_watchlist_diagnostics = subparsers.add_parser("review-watchlist-diagnostics")
    review_watchlist_diagnostics.add_argument("--diagnostics-dir", default="outputs/research")
    review_watchlist_diagnostics.add_argument("--start-date")
    review_watchlist_diagnostics.add_argument("--end-date")
    review_watchlist_diagnostics.add_argument("--output-dir", default="outputs/research")

    review_risk_watch_split = subparsers.add_parser("review-risk-watch-split")
    review_risk_watch_split.add_argument(
        "--detail-path",
        default="outputs/research/watchlist_diagnostics_effectiveness_detail.csv",
    )
    review_risk_watch_split.add_argument("--output-dir", default="outputs/research")

    review_watchlist_context_cross = subparsers.add_parser("review-watchlist-context-cross")
    review_watchlist_context_cross.add_argument(
        "--detail-path",
        default="outputs/research/watchlist_diagnostics_effectiveness_detail.csv",
    )
    review_watchlist_context_cross.add_argument("--fundamental-context-path")
    review_watchlist_context_cross.add_argument("--output-dir", default="outputs/research")

    review_dual_strategy_effectiveness = subparsers.add_parser(
        "review-dual-strategy-effectiveness"
    )
    review_dual_strategy_effectiveness.add_argument(
        "--detail-path",
        default="outputs/research/watchlist_context_cross_detail.csv",
    )
    review_dual_strategy_effectiveness.add_argument("--output-dir", default="outputs/research")

    validate_trend_discovery_templates = subparsers.add_parser(
        "validate-trend-discovery-templates"
    )
    validate_trend_discovery_templates.add_argument(
        "--detail-path",
        default="outputs/research/watchlist_context_cross_detail.csv",
    )
    validate_trend_discovery_templates.add_argument(
        "--strong-winner-path",
        default="outputs/research/strong_winner_miss_analysis_2025_to_now.csv",
    )
    validate_trend_discovery_templates.add_argument("--output-dir", default="outputs/research")

    replay_trend_discovery_v2 = subparsers.add_parser("replay-trend-discovery-v2")
    replay_trend_discovery_v2.add_argument(
        "--template-detail",
        default="outputs/research/trend_discovery_template_detail.csv",
    )
    replay_trend_discovery_v2.add_argument(
        "--strong-winner-path",
        default="outputs/research/strong_winner_miss_analysis_2025_to_now.csv",
    )
    replay_trend_discovery_v2.add_argument("--output-dir", default="outputs/research")

    audit_trend_discovery_v2_purity = subparsers.add_parser(
        "audit-trend-discovery-v2-purity"
    )
    audit_trend_discovery_v2_purity.add_argument(
        "--v2-detail",
        default="outputs/research/trend_discovery_v2_replay_detail.csv",
    )
    audit_trend_discovery_v2_purity.add_argument(
        "--strong-winner-path",
        default="outputs/research/strong_winner_miss_analysis_2025_to_now.csv",
    )
    audit_trend_discovery_v2_purity.add_argument("--output-dir", default="outputs/research")

    replay_trend_discovery_v2_2 = subparsers.add_parser("replay-trend-discovery-v2-2")
    replay_trend_discovery_v2_2.add_argument(
        "--v2-detail",
        default="outputs/research/trend_discovery_v2_purity_detail.csv",
    )
    replay_trend_discovery_v2_2.add_argument(
        "--strong-winner-path",
        default="outputs/research/strong_winner_miss_analysis_2025_to_now.csv",
    )
    replay_trend_discovery_v2_2.add_argument("--output-dir", default="outputs/research")

    review_trend_discovery_v2_2_stability = subparsers.add_parser(
        "review-trend-discovery-v2-2-stability"
    )
    review_trend_discovery_v2_2_stability.add_argument(
        "--detail-path",
        default="outputs/research/trend_discovery_v2_2_replay_detail.csv",
    )
    review_trend_discovery_v2_2_stability.add_argument(
        "--strong-winner-path",
        default="outputs/research/strong_winner_miss_analysis_2025_to_now.csv",
    )
    review_trend_discovery_v2_2_stability.add_argument(
        "--output-dir",
        default="outputs/research",
    )

    audit_watchlist_fundamental_coverage = subparsers.add_parser(
        "audit-watchlist-fundamental-coverage"
    )
    audit_watchlist_fundamental_coverage.add_argument(
        "--detail-path",
        default="outputs/research/watchlist_diagnostics_effectiveness_detail.csv",
    )
    audit_watchlist_fundamental_coverage.add_argument("--output-dir", default="outputs/research")

    build_watchlist_fundamental_pit_context = subparsers.add_parser(
        "build-watchlist-fundamental-pit-context"
    )
    build_watchlist_fundamental_pit_context.add_argument(
        "--detail-path",
        default="outputs/research/watchlist_diagnostics_effectiveness_detail.csv",
    )
    build_watchlist_fundamental_pit_context.add_argument(
        "--output-dir",
        default="outputs/research",
    )

    strong_winner_miss_analysis = subparsers.add_parser("analyze-strong-winner-misses")
    strong_winner_miss_analysis.add_argument("--start-date", required=True)
    strong_winner_miss_analysis.add_argument("--end-date", required=True)
    strong_winner_miss_analysis.add_argument("--adjust-type", default="qfq")
    strong_winner_miss_analysis.add_argument("--window-days", type=int, default=60)
    strong_winner_miss_analysis.add_argument("--threshold", type=float, default=1.0)
    strong_winner_miss_analysis.add_argument("--diagnostics-dir", default="outputs/research")
    strong_winner_miss_analysis.add_argument("--output-dir", default="outputs/research")

    strong_winner_taxonomy_v2 = subparsers.add_parser("analyze-strong-winner-taxonomy-v2")
    strong_winner_taxonomy_v2.add_argument("--start-date", required=True)
    strong_winner_taxonomy_v2.add_argument("--end-date", required=True)
    strong_winner_taxonomy_v2.add_argument("--adjust-type", default="qfq")
    strong_winner_taxonomy_v2.add_argument(
        "--v2-detail-path",
        default="outputs/research/trend_discovery_v2_2_replay_detail.csv",
    )
    strong_winner_taxonomy_v2.add_argument("--output-dir", default="outputs/research")

    strong_winner_capture_gap = subparsers.add_parser("analyze-strong-winner-capture-gap")
    strong_winner_capture_gap.add_argument(
        "--taxonomy-path",
        default="outputs/research/strong_winner_taxonomy_v2_2025_to_now.csv",
    )
    strong_winner_capture_gap.add_argument(
        "--v2-detail-path",
        default="outputs/research/trend_discovery_v2_2_replay_detail.csv",
    )
    strong_winner_capture_gap.add_argument("--output-dir", default="outputs/research")

    diagnostics_candidate_source_audit = subparsers.add_parser(
        "audit-diagnostics-candidate-source"
    )
    diagnostics_candidate_source_audit.add_argument(
        "--gap-detail-path",
        default="outputs/research/strong_winner_capture_gap_detail.csv",
    )
    diagnostics_candidate_source_audit.add_argument(
        "--v2-detail-path",
        default="outputs/research/trend_discovery_v2_2_replay_detail.csv",
    )
    diagnostics_candidate_source_audit.add_argument("--score-version", default="manual_v1")
    diagnostics_candidate_source_audit.add_argument("--diagnostics-top-n", type=int, default=50)
    diagnostics_candidate_source_audit.add_argument("--output-dir", default="outputs/research")

    strong_winner_topn_source = subparsers.add_parser("analyze-strong-winner-topn-source")
    strong_winner_topn_source.add_argument(
        "--miss-analysis-path",
        default="outputs/research/strong_winner_miss_analysis_2025_to_now.csv",
    )
    strong_winner_topn_source.add_argument("--score-version", default="manual_v1")
    strong_winner_topn_source.add_argument(
        "--topn-thresholds",
        type=parse_topn_thresholds,
        default=[50, 100, 200, 500],
    )
    strong_winner_topn_source.add_argument("--output-dir", default="outputs/research")

    strong_winner_discovery_pool = subparsers.add_parser("build-strong-winner-discovery-pool")
    strong_winner_discovery_pool.add_argument("--start-date", required=True)
    strong_winner_discovery_pool.add_argument("--end-date", required=True)
    strong_winner_discovery_pool.add_argument("--score-version", default="manual_v1")
    strong_winner_discovery_pool.add_argument("--adjust-type", default="qfq")
    strong_winner_discovery_pool.add_argument(
        "--topn-thresholds",
        type=parse_topn_thresholds,
        default=[50, 100, 200, 500],
    )
    strong_winner_discovery_pool.add_argument(
        "--strong-winner-path",
        default="outputs/research/strong_winner_taxonomy_v2_2025_to_now.csv",
    )
    strong_winner_discovery_pool.add_argument("--output-dir", default="outputs/research")

    watchlist_report = subparsers.add_parser("watchlist-report")
    watchlist_report.add_argument("--trade-date", required=True)
    watchlist_report.add_argument("--watchlist-id", required=True)
    watchlist_report.add_argument("--output-dir", required=True)

    watchlist_explain = subparsers.add_parser("watchlist-explain")
    watchlist_explain.add_argument("--trade-date", required=True)
    watchlist_explain.add_argument("--watchlist-id", required=True)
    watchlist_explain.add_argument("--asset-id", required=True)

    return parser


def _load_trade_dates_for_watchlist_diagnostics_range(start_date: str, end_date: str) -> list[str]:
    sql = """
        SELECT trade_date::text AS trade_date
        FROM market_daily_bar
        WHERE adjust_type = 'qfq'
          AND trade_date BETWEEN %s AND %s
        GROUP BY trade_date
        ORDER BY trade_date
    """
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql, [start_date, end_date])
    return [str(row["trade_date"]) for row in rows]


def _has_matching_watchlist_diagnostics_cache(*, output_dir: str | Path, trade_date: str) -> bool:
    path = Path(output_dir) / f"watchlist_diagnostics_{trade_date}_diagnostics_v1.csv"
    if not path.exists():
        return False
    try:
        frame = pd.read_csv(path, usecols=["diagnostics_rule_version"])
    except (ValueError, OSError, pd.errors.EmptyDataError):
        return False
    if frame.empty:
        return False
    versions = {str(value) for value in frame["diagnostics_rule_version"].dropna().unique()}
    return versions == {DIAGNOSTICS_RULE_VERSION}


def main_for_args(argv: list[str] | None = None) -> int | None:
    args = build_parser().parse_args(argv)

    if args.command == "apply-schema":
        apply_schema()
        print("schema_applied")
    elif args.command == "apply-research-schema":
        apply_schema()
        print("research_schema_applied")
    elif args.command == "sync-assets":
        print(f"asset_master_synced|{sync_asset_master()}")
    elif args.command == "sync-core-assets":
        sync_core_asset_master_for_service()
        print("core_asset_master_synced")
    elif args.command == "sync-stock-chinese-names":
        count = sync_chinese_stock_names_from_akshare_for_service()
        print(f"stock_chinese_names_synced|{count}")
    elif args.command == "dashboard-api":
        run_dashboard_api(host=args.host, port=args.port)
    elif args.command == "dashboard-bootstrap-admin":
        user_account = bootstrap_admin_account(
            username=args.username,
            password=args.password,
            display_name=args.display_name,
            email=args.email,
        )
        print(f"dashboard_admin_bootstrapped|{user_account['username']}")
    elif args.command == "dashboard-enable-user":
        enable_user_account_by_username(
            username=args.username,
            actor_user_id=None,
        )
        print(f"dashboard_user_enabled|{args.username}")
    elif args.command == "data-audit":
        for row in run_data_audit(expected_start_date=args.expected_start_date):
            print(format_audit_line(row))
    elif args.command == "daily-pipeline":
        config = DailyClosePipelineConfig.from_env()
        if args.force:
            config = DailyClosePipelineConfig(
                **{**config.__dict__, "force_non_trading_day": True}
            )
        trade_date = parse_daily_close_trade_date(args.date, config.timezone)
        result = run_daily_close_pipeline_stage(args.stage, trade_date, config)
        print(json.dumps(result, ensure_ascii=False, default=str, indent=2))
    elif args.command == "intraday-pipeline":
        config = IntradayConfig.from_env()
        config = IntradayConfig(
            **{
                **config.__dict__,
                **{
                    key: value
                    for key, value in {
                        "top_n": args.top_n,
                        "score_version": args.score_version,
                        "watchlist_id": args.watchlist_id,
                        "portfolio_id": args.portfolio_id,
                    }.items()
                    if value is not None
                },
            }
        )
        trade_date = parse_intraday_trade_date(args.date, config.timezone)
        previous_date = (
            parse_intraday_trade_date(args.previous_date, config.timezone)
            if args.previous_date
            else None
        )
        result = run_intraday_stage(
            args.stage,
            run_date=trade_date,
            previous_trade_date=previous_date,
            config=config,
        )
        print(json.dumps(result, ensure_ascii=False, default=str, indent=2))
    elif args.command == "finance-audit":
        for row in summarize_finance_coverage():
            print(format_finance_audit_line(row))
    elif args.command == "news-source-backfill":
        result = run_news_source_backfill(
            start_date=args.start_date,
            end_date=args.end_date,
            provider=args.provider,
            token=args.token,
            output_dir=args.output_dir,
        )
        print(f"news_source_backfill|events|{result['paths']['events']}")
        print(f"news_source_backfill|report|{result['paths']['report']}")
        print(f"news_source_backfill|source_status|{result['source_status']}")
    elif args.command == "topn-news-source-backfill":
        result = run_topn_news_source_backfill(
            candidates_path=args.candidates_path,
            provider=args.provider,
            trade_date=args.trade_date,
            output_dir=args.output_dir,
        )
        print(f"topn_news_source_backfill|events|{result['paths']['events']}")
        print(f"topn_news_source_backfill|report|{result['paths']['report']}")
        print(f"topn_news_source_backfill|rows|{len(result['events'])}")
    elif args.command == "historical-top10-news-backfill":
        result = run_historical_top10_news_backfill(
            top10_path=args.top10_path,
            start_date=args.start_date,
            end_date=args.end_date,
            providers=args.providers,
            output_dir=args.output_dir,
            sample_trade_dates=args.sample_trade_dates,
        )
        print(f"historical_top10_news_backfill|candidates|{result['paths']['candidates']}")
        print(f"historical_top10_news_backfill|source_events|{result['paths']['source_events']}")
        print(f"historical_top10_news_backfill|source_rows|{len(result['source_events'])}")
    elif args.command == "review-top10-historical-news-effectiveness":
        result = run_top10_historical_news_effectiveness_review(
            base_dir=args.base_dir,
            adjust_type=args.adjust_type,
            output_dir=args.output_dir,
        )
        print(f"review_top10_historical_news_effectiveness|base_dir|{result['paths']['base_dir']}")
        print(
            "review_top10_historical_news_effectiveness|candidates|"
            f"{result['paths']['candidates']}"
        )
        print(
            "review_top10_historical_news_effectiveness|features|"
            f"{result['paths']['features']}"
        )
        print(
            "review_top10_historical_news_effectiveness|enrichment|"
            f"{result['paths']['enrichment']}"
        )
        print(
            "review_top10_historical_news_effectiveness|output_dir|"
            f"{result['paths']['output_dir']}"
        )
        return 0
    elif args.command == "market-style-switch-v1-backtest":
        from stock_research.market_style_switch_v1 import (
            DEFAULT_DEFENSIVE_INDUSTRY_KEYWORDS,
            run_market_style_switch_v1_backtest,
        )

        keywords = (
            tuple(keyword.strip() for keyword in args.defensive_industry_keywords.split(",") if keyword.strip())
            if args.defensive_industry_keywords
            else DEFAULT_DEFENSIVE_INDUSTRY_KEYWORDS
        )
        result = run_market_style_switch_v1_backtest(
            start_date=args.start_date,
            end_date=args.end_date,
            emotion_path=args.emotion_path,
            funnel_detail_path=args.funnel_detail_path,
            output_dir=args.output_dir,
            top_n=args.top_n,
            defensive_industry_keywords=keywords,
            adjust_type=args.adjust_type,
        )
        print(f"market_style_switch|summary|{result['paths']['summary_path']}")
        print(f"market_style_switch|style_state_rows|{len(result['style_state'])}")
        print(f"market_style_switch|growth_rows|{len(result['growth_candidates'])}")
        print(f"market_style_switch|defensive_rows|{len(result['defensive_candidates'])}")
        print(f"market_style_switch|rotation_rows|{len(result['rotation_candidates'])}")
        print(f"market_style_switch|equity_rows|{len(result['equity'])}")
        print(f"market_style_switch|output_dir|{args.output_dir}")
        return 0
    elif args.command == "market-regime-confirmation-v1-backtest":
        from stock_research.market_regime_confirmation_v1 import (
            run_market_regime_confirmation_v1_backtest,
        )

        result = run_market_regime_confirmation_v1_backtest(
            start_date=args.start_date,
            end_date=args.end_date,
            emotion_path=args.emotion_path,
            funnel_detail_path=args.funnel_detail_path,
            output_dir=args.output_dir,
            policy_event_path=args.policy_event_path,
            top_n=args.top_n,
            adjust_type=args.adjust_type,
        )
        print(f"market_regime_confirmation|summary|{result['paths'].get('summary_path')}")
        print(f"market_regime_confirmation|regime_rows|{len(result['regime'])}")
        print(f"market_regime_confirmation|equity_rows|{len(result['equity'])}")
        print(f"market_regime_confirmation|output_dir|{args.output_dir}")
        return 0
    elif args.command == "current-mid-trend-strategy-v1-backtest":
        from stock_research.current_mid_trend_strategy_v1 import (
            run_current_mid_trend_strategy_v1_backtest,
        )

        result = run_current_mid_trend_strategy_v1_backtest(
            start_date=args.start_date,
            end_date=args.end_date,
            regime_path=args.regime_path,
            funnel_detail_path=args.funnel_detail_path,
            output_dir=args.output_dir,
            top_n=args.top_n,
            adjust_type=args.adjust_type,
        )
        print(f"current_mid_trend_strategy_v1|summary|{result['paths'].get('summary')}")
        print(f"current_mid_trend_strategy_v1|equity|{result['paths'].get('equity')}")
        print(f"current_mid_trend_strategy_v1|holdings|{result['paths'].get('holdings')}")
        print(f"current_mid_trend_strategy_v1|trades|{result['paths'].get('trades')}")
        print(f"current_mid_trend_strategy_v1|report|{result['paths'].get('report')}")
        print(f"current_mid_trend_strategy_v1|equity_rows|{len(result['equity'])}")
        print(f"current_mid_trend_strategy_v1|trade_rows|{len(result['trades'])}")
        print(f"current_mid_trend_strategy_v1|protection_events|{len(result['protection_events'])}")
        return 0
    elif args.command == "news-feature-backfill":
        result = run_news_feature_backfill(
            events_path=args.events_path,
            start_date=args.start_date,
            end_date=args.end_date,
            mode=args.mode,
            output_dir=args.output_dir,
        )
        print(f"news_feature_backfill|mentions|{result['paths']['mentions']}")
        print(f"news_feature_backfill|features|{result['paths']['features']}")
    elif args.command == "news-feature-diagnostics":
        result = run_news_feature_diagnostics(
            feature_path=args.feature_path,
            output_dir=args.output_dir,
        )
        print(f"news_feature_diagnostics|bucket_summary|{result['paths']['bucket_summary']}")
        print(f"news_feature_diagnostics|regime_summary|{result['paths']['regime_summary']}")
        print(f"news_feature_diagnostics|report|{result['paths']['report']}")
        print(f"news_feature_diagnostics|warnings|{len(result.get('warnings', []))}")
        for warning in result.get("warnings", []):
            print(f"news_feature_diagnostics|warning|{warning}")
    elif args.command == "topn-news-enrichment":
        result = run_topn_news_enrichment(
            candidates_path=args.candidates_path,
            news_features_path=args.news_features_path,
            output_dir=args.output_dir,
        )
        print(f"topn_news_enrichment|enrichment|{result['paths']['enrichment']}")
    elif args.command == "free-enrichment-backfill":
        result = run_free_enrichment_backfill(
            dataset=args.dataset,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
            batch_size=args.batch_size,
            sleep_seconds=args.sleep_seconds,
            limit=args.limit,
            dry_run=args.dry_run,
            service=args.service,
        )
        print(f"free_enrichment_backfill|summary|{result['summary_path']}")
        print(f"free_enrichment_backfill|coverage|{result['coverage_path']}")
        print(f"free_enrichment_backfill|failures|{result['failures_path']}")
        print(f"free_enrichment_backfill|datasets|{len(result['results'])}")
    elif args.command == "data-quality":
        start_date = args.start_date
        if start_date is None:
            bounds = load_market_date_bounds()
            start_date = bounds["start_date"]
        report = run_data_quality(
            expected_start_date=args.expected_start_date,
            start_date=start_date,
            end_date=args.end_date,
            horizons=args.horizons,
            factor_names=args.factor_names,
            calc_version=args.calc_version,
            min_label_dates=args.min_label_dates,
            require_industry_membership=args.require_industry_membership,
        )
        if args.json:
            print(json.dumps(report, ensure_ascii=False))
        else:
            print(format_data_quality_summary_line(report))
            for check in report["checks"]:
                print(format_data_quality_check_line(check))
        if report["overall_status"] == "blocked":
            raise SystemExit(1)
    elif args.command == "seed-trading-calendar":
        count = seed_trading_calendar_from_bars(
            start_date=args.start_date,
            end_date=args.end_date,
            exchanges=args.exchanges,
            source_version=args.source_version,
        )
        print(f"trading_calendar_seeded|rows|{count}")
    elif args.command == "sync-tushare-trading-calendar":
        count = sync_trading_calendar_range_from_tushare(
            service=args.service,
            start_date=dt.date.fromisoformat(args.start_date),
            end_date=dt.date.fromisoformat(args.end_date),
            exchanges=tuple(args.exchanges),
            source_version=args.source_version,
            max_retries=args.max_retries,
            retry_sleep_seconds=args.retry_sleep_seconds,
        )
        print(f"tushare_trading_calendar_synced|rows|{count}")
    elif args.command == "sync-asset-lifecycle":
        count = sync_asset_lifecycle_from_master(source_version=args.source_version)
        print(f"asset_lifecycle_synced|rows|{count}")
    elif args.command == "create-backfill-run":
        result = create_backfill_run_for_service(
            run_id=args.run_id,
            dataset=args.dataset,
            source=args.source,
            source_version=args.source_version,
            start_date=args.start_date,
            end_date=args.end_date,
            months_per_partition=args.months_per_partition,
        )
        print(
            "backfill_run_created|"
            f"{result['run_id']}|{result['dataset']}|tasks|{result['task_count']}"
        )
    elif args.command == "backfill-status":
        result = backfill_status_for_service(run_id=args.run_id)
        for status, count in sorted(result["counts"].items()):
            print(f"backfill_status|{result['run_id']}|{status}|{count}")
    elif args.command == "claim-backfill-tasks":
        rows = claim_backfill_tasks_for_service(run_id=args.run_id, limit=args.limit)
        for row in rows:
            print(
                "backfill_task_claimed|"
                f"{row['task_id']}|{row['partition_key']}|"
                f"{str(row['start_date'])[:10]}|{str(row['end_date'])[:10]}"
            )
    elif args.command == "mark-backfill-task-success":
        mark_backfill_task_success_for_service(
            task_id=args.task_id,
            rows_read=args.rows_read,
            rows_written=args.rows_written,
        )
        print(f"backfill_task_success|{args.task_id}|{args.rows_read}|{args.rows_written}")
    elif args.command == "mark-backfill-task-failed":
        mark_backfill_task_failed_for_service(
            task_id=args.task_id,
            error_message=args.error_message,
        )
        print(f"backfill_task_failed|{args.task_id}|{args.error_message}")
    elif args.command == "reset-stale-backfill-tasks":
        count = reset_stale_backfill_tasks_for_service(
            dataset=args.dataset,
            older_than_minutes=args.older_than_minutes,
        )
        print(f"backfill_task_stale_reset|{args.dataset}|{count}")
    elif args.command == "build-asset-status":
        build_asset_status_daily_for_service(
            args.start_date,
            args.end_date,
            args.adjust_type,
        )
        print("core_asset_status_daily_built")
    elif args.command == "build-adjustment-factors":
        build_adjustment_factors_for_service(
            start_date=args.start_date,
            end_date=args.end_date,
            source_version=args.source_version,
        )
        print("adjustment_factors_built")
    elif args.command == "build-corporate-actions":
        build_corporate_actions_from_factors_for_service(
            start_date=args.start_date,
            end_date=args.end_date,
            source_version=args.source_version,
            factor_source_version=args.factor_source_version,
        )
        print("corporate_actions_built")
    elif args.command == "build-industry-bars":
        build_industry_daily_bars_for_service(
            start_date=args.start_date,
            end_date=args.end_date,
            industry_system=args.industry_system,
            adjust_type=args.adjust_type,
        )
        print("market_industry_daily_bars_built")
    elif args.command == "build-factor-daily":
        count = build_and_store_factor_daily(
            trade_date=args.trade_date,
            lookback_bars=args.lookback_bars,
            industry_system=args.industry_system,
        )
        print(f"factor_daily_stored|{count}")
    elif args.command == "research-preflight":
        horizons = args.horizons
        start_date = args.start_date
        if start_date is None:
            bounds = load_market_date_bounds()
            start_date = bounds["start_date"]
        if start_date is None:
            print("research_preflight|latest_common_label_date||0")
            print("research_preflight|coverage|blocked|factor_dates|0|complete_factor_dates|0")
            print(
                "research_preflight|missing_horizons|"
                + ",".join(str(value) for value in horizons)
            )
            print("research_preflight|short_label_horizons|")
            return
        latest = find_latest_common_label_date(
            start_date=start_date,
            horizons=horizons,
        )
        end_date = args.end_date or latest["latest_common_date"]
        if end_date is None:
            print(f"research_preflight|latest_common_label_date||{latest['date_count']}")
            print("research_preflight|coverage|blocked|factor_dates|0|complete_factor_dates|0")
            print(
                "research_preflight|missing_horizons|"
                + ",".join(str(value) for value in horizons)
            )
            print("research_preflight|short_label_horizons|")
            return
        factors = args.factor_names if args.factor_names else default_research_factor_names()
        coverage = check_factor_label_coverage(
            factor_names=factors,
            start_date=start_date,
            end_date=end_date,
            horizons=horizons,
            calc_version=args.calc_version,
            min_label_dates=args.min_label_dates,
        )
        print(
            "research_preflight|latest_common_label_date|"
            f"{latest['latest_common_date']}|{latest['date_count']}"
        )
        print(
            "research_preflight|coverage|"
            f"{coverage['status']}|factor_dates|{coverage['factor_date_count']}|"
            f"complete_factor_dates|{coverage['factor_complete_date_count']}"
        )
        print(
            "research_preflight|missing_horizons|"
            + ",".join(str(value) for value in coverage["missing_horizons"])
        )
        print(
            "research_preflight|short_label_horizons|"
            + ",".join(str(value) for value in coverage["short_label_horizons"])
        )
        if args.require_industry_membership:
            if end_date is None:
                print("research_preflight|industry_membership|blocked|market_rows|0|covered_rows|0|missing_rows|0")
            else:
                industry = check_industry_membership_coverage(
                    start_date=start_date,
                    end_date=end_date,
                    industry_system="csrc",
                    adjust_type="hfq",
                )
                print(
                    "research_preflight|industry_membership|"
                    f"{industry['status']}|market_rows|{industry['market_rows']}|"
                    f"covered_rows|{industry['covered_rows']}|missing_rows|{industry['missing_rows']}"
                )
    elif args.command == "backfill-factor-daily":
        if args.exact_window:
            window = {
                "start_date": args.start_date,
                "end_date": args.end_date,
                "date_count": 0,
            }
        else:
            window = derive_factor_backfill_window(
                start_date=args.start_date,
                end_date=args.end_date,
                lookback_bars=args.lookback_bars,
                industry_system=args.industry_system,
            )
        if window["start_date"] is None or window["end_date"] is None:
            print("factor_daily_backfill|dates|0")
            print("factor_daily_backfill|rows|0")
            return
        result = backfill_factor_daily_range(
            start_date=str(window["start_date"]),
            end_date=str(window["end_date"]),
            lookback_bars=args.lookback_bars,
            industry_system=args.industry_system,
            workers=args.workers,
            skip_complete=args.skip_complete,
            progress=factor_backfill_progress_printer(args.progress_interval),
        )
        total = int(result["factor_rows"].sum()) if not result.empty else 0
        print(f"factor_daily_backfill|dates|{len(result)}")
        print(f"factor_daily_backfill|rows|{total}")
    elif args.command == "backfill-approved-scores":
        bounds = load_market_date_bounds(adjust_type=args.adjust_type)
        start_date = args.start_date or bounds["start_date"]
        end_date = args.end_date or bounds["end_date"]
        if start_date is None or end_date is None:
            print("approved_score_backfill|dates|0")
            print("approved_score_backfill|rows|0")
            return
        result = score_approved_factors_range(
            start_date=str(start_date),
            end_date=str(end_date),
            score_version=args.score_version,
            calc_version=args.calc_version,
            adjust_type=args.adjust_type,
        )
        total = int(result["score_rows"].sum()) if not result.empty else 0
        print(f"approved_score_backfill|start_date|{start_date}")
        print(f"approved_score_backfill|end_date|{end_date}")
        print(f"approved_score_backfill|dates|{len(result)}")
        print(f"approved_score_backfill|rows|{total}")
    elif args.command == "score-factor-daily":
        count = score_stored_factor_daily(
            trade_date=args.trade_date,
            score_version=args.score_version,
            approved_only=True,
        )
        print(f"stock_score_daily_stored|{count}")
    elif args.command == "show-top-scores":
        for row in load_top_scores(
            trade_date=args.trade_date,
            score_version=args.score_version,
            top_n=args.top_n,
        ):
            print(
                f"top_score|{row['trade_date']}|{row['rank']}|"
                f"{row['asset_id']}|{row['score_total']}|{row['score_version']}"
            )
    elif args.command == "eval-factor":
        factors, returns = load_factor_eval_inputs(
            factor_name=args.factor_name,
            start_date=args.start_date,
            end_date=args.end_date,
            horizon=args.horizon,
        )
        result = generate_factor_eval_report(
            factors,
            returns,
            factor_name=args.factor_name,
            return_col=f"forward_return_{args.horizon}d",
            quantiles=args.quantiles,
            top_n=args.top_n,
        )
        print(f"factor_eval|{args.factor_name}|mean_ic|{result['ic_summary']['mean_ic']}")
        print(f"factor_eval|{args.factor_name}|ic_count|{result['ic_summary']['ic_count']}")
        print(
            f"factor_eval|{args.factor_name}|mean_rank_ic|"
            f"{result['rank_ic_summary']['mean_ic']}"
        )
    elif args.command == "evaluate-factor-gate":
        horizons = [int(value.strip()) for value in args.horizons.split(",") if value.strip()]
        factors, returns = load_multi_horizon_factor_eval_inputs(
            factor_name=args.factor_name,
            start_date=args.start_date,
            end_date=args.end_date,
            horizons=horizons,
            calc_version=args.calc_version,
        )
        multi_horizon_report = generate_multi_horizon_report(
            factors=factors,
            returns=returns,
            factor_name=args.factor_name,
            horizons=horizons,
            quantiles=args.quantiles,
            top_n=args.top_n,
        )
        decision = decide_factor_gate(
            factor_name=args.factor_name,
            multi_horizon_report=multi_horizon_report,
            primary_horizon=args.primary_horizon,
        )
        run_id = f"factor-eval-{uuid4().hex}"
        store_factor_eval_run(
            run_id=run_id,
            factor_name=args.factor_name,
            calc_version=args.calc_version,
            start_date=args.start_date,
            end_date=args.end_date,
            horizons=horizons,
            primary_horizon=args.primary_horizon,
            status=decision["status"],
            reason=decision["reason"],
            metrics={
                "decision": decision,
                "multi_horizon": summarize_multi_horizon_report(multi_horizon_report),
            },
        )
        store_factor_approval(
            factor_name=args.factor_name,
            calc_version=args.calc_version,
            score_version=args.score_version,
            status=decision["status"],
            reason=decision["reason"],
            eval_run_id=run_id,
        )
        print(
            f"factor_gate|{args.factor_name}|{decision['status']}|"
            f"{decision['reason']}|{decision['primary_horizon']}"
        )
    elif args.command == "evaluate-factor-gate-batch":
        result = run_factor_gate_batch(
            factor_names=args.factor_names,
            start_date=args.start_date,
            end_date=args.end_date,
            horizons=[int(value.strip()) for value in args.horizons.split(",") if value.strip()],
            primary_horizon=args.primary_horizon,
            calc_version=args.calc_version,
            score_version=args.score_version,
            quantiles=args.quantiles,
            top_n=args.top_n,
            validation_start_date=args.validation_start_date,
        )
        for row in result.to_dict("records"):
            print(
                "factor_gate_batch|"
                f"{row['factor_name']}|{row['status']}|{row['reason']}|"
                f"{row['primary_horizon']}|{row['eval_run_id']}"
            )
    elif args.command == "factor-validation-review":

        factors = pd.read_csv(args.factors, low_memory=False)
        returns = pd.read_csv(args.returns, low_memory=False)
        segments = pd.read_csv(args.segments, low_memory=False) if args.segments else None
        review = build_factor_validation_review(
            factors=factors,
            returns=returns,
            factor_name=args.factor_name,
            horizons=args.horizons,
            split_date=args.split_date,
            primary_horizon=args.primary_horizon,
            segments=segments,
            segment_col=args.segment_col,
            factor_col=args.factor_col,
            min_abs_mean_ic=args.min_abs_mean_ic,
            min_icir=args.min_icir,
            min_ic_count=args.min_ic_count,
        )
        paths = write_factor_validation_review(review, output_dir=args.output_dir)
        print(f"factor_validation_review|status|{review['approval']['status']}")
        print(f"factor_validation_review|json|{paths['json_path']}")
        print(f"factor_validation_review|markdown|{paths['markdown_path']}")
        print(f"factor_validation_review|decay_csv|{paths['decay_csv_path']}")
        if "segment_csv_path" in paths:
            print(f"factor_validation_review|segment_csv|{paths['segment_csv_path']}")
    elif args.command == "intraday-factor-eval":
        result = run_intraday_factor_eval(
            start_date=args.start_date,
            end_date=args.end_date,
            horizons=args.horizons,
            output_dir=args.output_dir,
            feature_names=args.features,
            freq=args.freq,
            adjust_type=args.adjust_type,
            industry_system=args.industry_system,
            quantiles=args.quantiles,
            top_n=args.top_n,
        )
        summary = result["summary"]
        paths = result["paths"]
        print(f"intraday_factor_eval|summary|{paths['summary_csv_path']}")
        print(f"intraday_factor_eval|markdown|{paths['markdown_path']}")
        print(f"intraday_factor_eval|rows|{len(summary)}")
    elif args.command == "intraday-risk-filter-backtest":
        result = run_intraday_risk_filter_backtest(
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
            score_version=args.score_version,
            top_n_values=args.top_n_values,
            rebalance_frequency=args.rebalance_frequency,
            transaction_cost_bps=args.transaction_cost_bps,
            score_adjust_type=args.score_adjust_type,
            intraday_freq=args.intraday_freq,
            intraday_adjust_type=args.intraday_adjust_type,
        )
        summary = result["summary"]
        paths = result["paths"]
        print(f"intraday_risk_filter_backtest|summary|{paths['summary']}")
        print(f"intraday_risk_filter_backtest|report|{paths['report']}")
        print(f"intraday_risk_filter_backtest|rows|{len(summary)}")
    elif args.command == "intraday-risk-control-v2-backtest":
        result = run_intraday_risk_control_v2_backtest(
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
            score_version=args.score_version,
            top_n_values=args.top_n_values,
            rebalance_frequency=args.rebalance_frequency,
            transaction_cost_bps=args.transaction_cost_bps,
            score_adjust_type=args.score_adjust_type,
            intraday_freq=args.intraday_freq,
            intraday_adjust_type=args.intraday_adjust_type,
            lookback=args.lookback,
            zscore_threshold=args.zscore_threshold,
        )
        summary = result["summary"]
        paths = result["paths"]
        print(f"intraday_risk_control_v2_backtest|summary|{paths['summary']}")
        print(f"intraday_risk_control_v2_backtest|report|{paths['report']}")
        print(f"intraday_risk_control_v2_backtest|rows|{len(summary)}")
    elif args.command == "market-emotion-state-v1-backfill":
        result = run_market_emotion_state_v1_backfill(
            start_date=args.start_date,
            end_date=args.end_date,
            adjust_type=args.adjust_type,
            output_dir=args.output_dir,
            mid_trend_equity_path=args.mid_trend_equity_path,
        )
        print(f"market_emotion_state|rows|{len(result['daily'])}")
        for key, path in result["paths"].items():
            print(f"market_emotion_state|{key}|{path}")
    elif args.command == "run-daily-factor-pipeline":
        result = run_daily_factor_pipeline(
            trade_date=args.trade_date,
            score_version=args.score_version,
            top_n=args.top_n,
            lookback_bars=args.lookback_bars,
            reports_dir=args.reports_dir,
        )
        print(f"daily_factor_pipeline|factor_rows|{result['factor_rows']}")
        print(f"daily_factor_pipeline|score_rows|{result['score_rows']}")
        print(f"daily_factor_pipeline|top_scores|{len(result['top_scores'])}")
    elif args.command == "run-stock-daily-data-pipeline":
        trade_date = (
            latest_complete_source_trade_date()
            if args.trade_date == "auto"
            else args.trade_date
        )
        if not trade_date:
            raise SystemExit("could not resolve latest complete source trade date")
        sender = None
        if args.feishu_target:
            def sender(message: str) -> None:
                send_openclaw_feishu_message(
                    message=message,
                    target=args.feishu_target,
                    account=args.feishu_account,
                    openclaw_bin=args.openclaw_bin,
                    dry_run=False,
                )

        result = run_stock_daily_data_pipeline(
            trade_date=trade_date,
            output_dir=args.output_dir,
            feishu_sender=sender,
            send_feishu=not args.no_feishu,
        )
        print(f"stock_daily_data_pipeline|status|{result['status']}")
        print(f"stock_daily_data_pipeline|summary|{args.output_dir}/run_summary.json")
        if result["status"] != "success":
            raise SystemExit(1)
    elif args.command == "build-technical-features-daily":
        count = build_and_store_stock_technical_features_daily(
            trade_date=args.trade_date,
            lookback_bars=args.lookback_bars,
            adjust_type=args.adjust_type,
            build_strategy=args.build_strategy,
        )
        print(f"technical_features_daily_stored|{count}")
    elif args.command == "backfill-technical-features-daily":
        window = derive_technical_feature_backfill_window(
            start_date=args.start_date,
            end_date=args.end_date,
            lookback_bars=args.lookback_bars,
            adjust_type=args.adjust_type,
        )
        start_date = args.start_date or window["start_date"]
        end_date = args.end_date or window["end_date"]
        if start_date is None or end_date is None:
            print("technical_feature_daily_backfill|dates|0")
            print("technical_feature_daily_backfill|rows|0")
            return
        result = backfill_technical_features_daily_range(
            start_date=str(start_date),
            end_date=str(end_date),
            lookback_bars=args.lookback_bars,
            adjust_type=args.adjust_type,
            source_data_version=args.source_data_version,
            workers=args.workers,
            skip_complete=args.skip_complete,
            build_strategy=args.build_strategy,
            progress=technical_feature_backfill_progress_printer(args.progress_interval),
        )
        total = int(result["feature_rows"].sum()) if not result.empty else 0
        print(f"technical_feature_daily_backfill|dates|{len(result)}")
        print(f"technical_feature_daily_backfill|rows|{total}")
    elif args.command == "benchmark-technical-feature-backfill":
        result = run_technical_feature_backfill_benchmark(
            start_date=args.start_date,
            end_date=args.end_date,
            lookback_bars=args.lookback_bars,
            adjust_type=args.adjust_type,
            workers=args.workers,
            strategy=args.strategy,
            bench_tag=args.bench_tag,
        )
        print(f"technical_feature_benchmark|strategy|{result['strategy']}")
        print(f"technical_feature_benchmark|workers|{result['workers']}")
        print(f"technical_feature_benchmark|bench_tag|{result['bench_tag']}")
        print(
            "technical_feature_benchmark|source_data_version|"
            f"{result['source_data_version']}"
        )
        print(f"technical_feature_benchmark|dates|{result['dates']}")
        print(f"technical_feature_benchmark|rows|{result['rows']}")
        print(
            "technical_feature_benchmark|elapsed_seconds|"
            f"{result['elapsed_seconds']}"
        )
        print(
            "technical_feature_benchmark|rows_per_second|"
            f"{result['rows_per_second']}"
        )
        print(
            "technical_feature_benchmark|dates_per_second|"
            f"{result['dates_per_second']}"
        )
    elif args.command == "technical-feature-gap-check":
        result = run_technical_feature_gap_check(
            start_date=args.start_date,
            end_date=args.end_date,
            adjust_type=args.adjust_type,
            calc_version=args.calc_version,
            source_data_version=args.source_data_version,
        )
        for row in result.get("dates", []):
            if not row.get("has_gap"):
                continue
            print(
                "technical_feature_gap_check|date|"
                f"{row['trade_date']}|"
                f"market_assets={int(row['market_assets'])}|"
                f"feature_rows={int(row['feature_rows'])}|"
                f"missing={int(row['missing'])}|"
                f"stale={int(row['stale'])}"
            )
        summary = result.get("summary", {})
        print(
            "technical_feature_gap_check|summary|"
            f"dates={int(summary.get('dates') or 0)}|"
            f"dates_with_gaps={int(summary.get('dates_with_gaps') or 0)}"
        )
    elif args.command == "build-intraday-features-daily":
        result = build_and_store_intraday_features_daily(
            trade_date=args.trade_date,
            freq=args.freq,
            adjust_type=args.adjust_type,
            industry_system=args.industry_system,
        )
        print(f"intraday_features_daily|stock_rows|{int(result['stock_rows'])}")
        print(f"intraday_features_daily|industry_rows|{int(result['industry_rows'])}")
    elif args.command == "backfill-intraday-features-daily":
        result = backfill_intraday_features_daily_range(
            start_date=args.start_date,
            end_date=args.end_date,
            freq=args.freq,
            adjust_type=args.adjust_type,
            industry_system=args.industry_system,
            workers=args.workers,
            skip_complete=args.skip_complete,
            progress=intraday_feature_backfill_progress_printer(),
        )
        total = 0
        if not result.empty:
            total = int(result["stock_rows"].sum()) + int(result["industry_rows"].sum())
        print(f"intraday_feature_daily_backfill|dates|{len(result)}")
        print(f"intraday_feature_daily_backfill|rows|{total}")
    elif args.command == "intraday-feature-gap-check":
        result = run_intraday_feature_gap_check(
            start_date=args.start_date,
            end_date=args.end_date,
            freq=args.freq,
            adjust_type=args.adjust_type,
            calc_version=args.calc_version,
        )
        for row in result.get("dates", []):
            if not row.get("has_stock_gap") and not row.get("has_industry_gap"):
                continue
            print(
                "intraday_feature_gap_check|date|"
                f"{row['trade_date']}|"
                f"minute_assets={int(row['minute_assets'])}|"
                f"stock_feature_assets={int(row['stock_feature_assets'])}|"
                f"stock_missing={int(row['stock_missing'])}|"
                f"stock_stale={int(row['stock_stale'])}|"
                f"industry_feature_groups={int(row['industry_feature_groups'])}|"
                f"industry_gap={1 if row.get('has_industry_gap') else 0}"
            )
        summary = result.get("summary", {})
        print(
            "intraday_feature_gap_check|summary|"
            f"dates={int(summary.get('dates') or 0)}|"
            f"dates_with_stock_gaps={int(summary.get('dates_with_stock_gaps') or 0)}|"
            f"dates_with_industry_gaps={int(summary.get('dates_with_industry_gaps') or 0)}"
        )
    elif args.command == "technical-feature-performance-review":
        compare_benchmark = run_technical_feature_compare_benchmark(
            asset_count=args.asset_count,
            bar_count=args.bar_count,
            repeat=args.repeat,
        )
        store_benchmark = run_technical_feature_store_compare_benchmark(
            asset_count=args.asset_count,
            bar_count=args.bar_count,
        )
        regression = run_technical_feature_fast_regression(
            asset_count=args.asset_count,
            bar_count=args.bar_count,
        )
        review = build_technical_feature_performance_review(
            compare_benchmark=compare_benchmark,
            store_benchmark=store_benchmark,
            regression=regression,
            min_speedup_ratio=args.min_speedup_ratio,
        )
        paths = write_technical_feature_performance_review(
            review,
            output_dir=args.output_dir,
        )
        print(f"technical_feature_performance_review|status|{review['gate']['status']}")
        print(f"technical_feature_performance_review|json|{paths['json_path']}")
        print(f"technical_feature_performance_review|markdown|{paths['markdown_path']}")
        print(f"technical_feature_performance_review|metrics_csv|{paths['metrics_csv_path']}")
    elif args.command == "p2-artifact-rollup":
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        rollup = build_p2_artifact_rollup(manifest)
        paths = write_p2_artifact_rollup(rollup, output_dir=args.output_dir)
        print(f"p2_artifact_rollup|status|{rollup['status']}")
        print(f"p2_artifact_rollup|json|{paths['json_path']}")
        print(f"p2_artifact_rollup|markdown|{paths['markdown_path']}")
    elif args.command == "p2-simulation-review":

        states = load_simulation_states(args.simulation_state)
        advice = pd.read_csv(args.trade_advice) if args.trade_advice else None
        review = build_virtual_portfolio_review(
            trade_date=args.trade_date,
            portfolio_id=args.portfolio_id,
            states=states,
            advice=advice,
        )
        paths = write_virtual_portfolio_review(review, output_dir=args.output_dir)
        print(f"p2_simulation_review|status|{review['status']}")
        print(f"p2_simulation_review|json|{paths['json_path']}")
        print(f"p2_simulation_review|markdown|{paths['markdown_path']}")
        print(f"p2_simulation_review|history_csv|{paths['history_csv_path']}")
        print(f"p2_simulation_review|positions_csv|{paths['positions_csv_path']}")
    elif args.command == "p2-aggregate-review":
        rollup = json.loads(Path(args.rollup).read_text(encoding="utf-8"))
        payloads = load_aggregate_artifact_payloads(rollup)
        review = build_p2_aggregate_review(
            trade_date=args.trade_date,
            rollup=rollup,
            artifact_payloads=payloads,
        )
        paths = write_p2_aggregate_review(review, output_dir=args.output_dir)
        print(f"p2_aggregate_review|status|{review['status']}")
        print(f"p2_aggregate_review|json|{paths['json_path']}")
        print(f"p2_aggregate_review|markdown|{paths['markdown_path']}")
    elif args.command == "p3-import-p2-aggregate-review":
        result = import_p2_aggregate_review(Path(args.path), service=args.service)
        print(f"p3_p2_review_import|imported|{result['imported_count']}")
        for run_id in result["run_ids"]:
            print(f"p3_p2_review_import|run_id|{run_id}")
    elif args.command == "p3-import-virtual-portfolio-review":
        result = import_virtual_portfolio_review(Path(args.path), service=args.service)
        print(f"p3_virtual_portfolio_import|imported|{result['imported_count']}")
        print(f"p3_virtual_portfolio_import|states|{result['state_count']}")
        print(f"p3_virtual_portfolio_import|positions|{result['position_count']}")
        for portfolio_id in result["portfolio_ids"]:
            print(f"p3_virtual_portfolio_import|portfolio_id|{portfolio_id}")
    elif args.command == "p3-export-operator-review":
        result = export_operator_review(
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=Path(args.output_dir),
            status=args.status,
            section_group=args.section_group,
            portfolio_id=args.portfolio_id,
            service=args.service,
        )
        print(f"p3_operator_export|manifest|{result['manifest_path']}")
        for dataset_name, rows in result["row_counts"].items():
            print(
                "p3_operator_export_dataset|"
                f"{dataset_name}|rows|{rows}|{result['files'][dataset_name]}"
            )
    elif args.command == "p7-decision-journal":

        events = pd.read_csv(args.input_csv)
        try:
            journal = build_decision_journal(
                review_date=args.review_date,
                review_session_id=args.review_session_id,
                reviewer_id=args.reviewer_id,
                source_artifact_root=args.source_artifact_root,
                events=events,
            )
        except ValueError as exc:
            print(f"p7_decision_journal|error|{exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        paths = write_decision_journal(journal, output_dir=args.output_dir)
        print(f"p7_decision_journal|status|{journal['status']}")
        print(f"p7_decision_journal|json|{paths['json_path']}")
        print(f"p7_decision_journal|csv|{paths['csv_path']}")
        print(f"p7_decision_journal|markdown|{paths['markdown_path']}")
    elif args.command == "p7-import-decision-journal":
        result = import_decision_journal(Path(args.path), service=args.service)
        print(f"p7_decision_journal_import|imported|{result['imported_count']}")
        print(f"p7_decision_journal_import|events|{result['event_count']}")
        for session_id in result["session_ids"]:
            print(f"p7_decision_journal_import|session_id|{session_id}")
    elif args.command == "p8-decision-outcome-review":
        horizons = args.horizons or None
        max_horizon = max(horizons) if horizons else 60
        decision_events, bars = _load_p8_decision_outcome_inputs(
            start_date=args.start_date,
            end_date=args.end_date,
            review_session_id=args.review_session_id,
            decision_events_csv=args.decision_events_csv,
            bars_csv=args.bars_csv,
            service=args.service,
            adjust_type=args.adjust_type,
            max_horizon=max_horizon,
        )
        review = build_decision_outcome_review(
            start_date=args.start_date,
            end_date=args.end_date,
            decision_events=decision_events,
            bars=bars,
            horizons=horizons,
        )
        paths = write_decision_outcome_review(review, args.output_dir)
        print(f"p8_decision_outcome_review|status|{review['status']}")
        print(f"p8_decision_outcome_review|outcomes|{review['outcome_count']}")
        print(f"p8_decision_outcome_review|json|{paths['json_path']}")
        print(f"p8_decision_outcome_review|details_csv|{paths['details_csv_path']}")
        print(f"p8_decision_outcome_review|summary_csv|{paths['summary_csv_path']}")
        print(f"p8_decision_outcome_review|markdown|{paths['markdown_path']}")
    elif args.command == "p8-import-decision-outcome-review":
        result = import_decision_outcome_review(Path(args.path), service=args.service)
        print(f"p8_decision_outcome_review_import|imported|{result['imported_count']}")
        print(f"p8_decision_outcome_review_import|events|{result['event_count']}")
        for run_id in result["run_ids"]:
            print(f"p8_decision_outcome_review_import|run_id|{run_id}")
    elif args.command == "p9-outcome-analytics":
        outcome_events = _load_p9_outcome_analytics_inputs(
            start_date=args.start_date,
            end_date=args.end_date,
            review_session_id=args.review_session_id,
            outcome_events_csv=args.outcome_events_csv,
            service=args.service,
            limit=args.limit,
        )
        analytics = build_decision_outcome_analytics(
            start_date=args.start_date,
            end_date=args.end_date,
            outcome_events=outcome_events,
            horizons=args.horizons or None,
        )
        paths = write_decision_outcome_analytics(analytics, args.output_dir)
        print(f"p9_outcome_analytics|status|{analytics['status']}")
        print(f"p9_outcome_analytics|groups|{analytics['group_count']}")
        print(f"p9_outcome_analytics|json|{paths['json_path']}")
        print(f"p9_outcome_analytics|groups_csv|{paths['groups_csv_path']}")
        print(f"p9_outcome_analytics|diagnostics_csv|{paths['diagnostics_csv_path']}")
        print(f"p9_outcome_analytics|markdown|{paths['markdown_path']}")
    elif args.command == "p9-import-outcome-analytics":
        result = import_decision_outcome_analytics(Path(args.path), service=args.service)
        print(f"p9_outcome_analytics_import|imported|{result['imported_count']}")
        print(f"p9_outcome_analytics_import|groups|{result['group_count']}")
        for run_id in result["run_ids"]:
            print(f"p9_outcome_analytics_import|run_id|{run_id}")
    elif args.command == "p10-experiment-proposals":

        proposal_events = pd.read_csv(args.input_csv)
        review = build_experiment_proposal_review(
            proposal_events=proposal_events,
            run_id=args.run_id,
            review_date=args.review_date,
        )
        paths = write_experiment_proposal_review(review, args.output_dir)
        print(f"p10_experiment_proposals|status|{review['status']}")
        print(f"p10_experiment_proposals|proposals|{review['proposal_count']}")
        print(f"p10_experiment_proposals|json|{paths['json_path']}")
        print(f"p10_experiment_proposals|proposals_csv|{paths['proposals_csv_path']}")
        print(f"p10_experiment_proposals|markdown|{paths['markdown_path']}")
    elif args.command == "p10-import-experiment-proposals":
        result = import_experiment_proposal_review(Path(args.path), service=args.service)
        print(f"p10_experiment_proposals_import|imported|{result['imported_count']}")
        print(f"p10_experiment_proposals_import|proposals|{result['proposal_count']}")
        for run_id in result["run_ids"]:
            print(f"p10_experiment_proposals_import|run_id|{run_id}")
    elif args.command == "p11-experiment-replay":

        proposal_payload = json.loads(Path(args.proposals_json).read_text(encoding="utf-8"))
        proposals = pd.DataFrame(proposal_payload.get("proposals", []))
        replay_events = pd.read_csv(args.metrics_csv)
        review = build_experiment_replay_review(
            proposals=proposals,
            replay_events=replay_events,
            run_id=args.run_id,
            replay_start_date=args.replay_start_date,
            replay_end_date=args.replay_end_date,
        )
        paths = write_experiment_replay_review(review, args.output_dir)
        print(f"p11_experiment_replay|status|{review['status']}")
        print(f"p11_experiment_replay|results|{review['result_count']}")
        print(f"p11_experiment_replay|json|{paths['json_path']}")
        print(f"p11_experiment_replay|results_csv|{paths['results_csv_path']}")
        print(f"p11_experiment_replay|markdown|{paths['markdown_path']}")
    elif args.command == "p11-import-experiment-replay":
        result = import_experiment_replay_review(Path(args.path), service=args.service)
        print(f"p11_experiment_replay_import|imported|{result['imported_count']}")
        print(f"p11_experiment_replay_import|results|{result['result_count']}")
        for run_id in result["run_ids"]:
            print(f"p11_experiment_replay_import|run_id|{run_id}")
    elif args.command == "p12-shadow-watchlist":

        replay_payload = json.loads(Path(args.replay_json).read_text(encoding="utf-8"))
        replay_results = pd.DataFrame(replay_payload.get("results", []))
        candidate_events = pd.read_csv(args.candidates_csv)
        review = build_shadow_watchlist_review(
            replay_results=replay_results,
            candidate_events=candidate_events,
            run_id=args.run_id,
            review_date=args.review_date,
        )
        paths = write_shadow_watchlist_review(review, args.output_dir)
        print(f"p12_shadow_watchlist|status|{review['status']}")
        print(f"p12_shadow_watchlist|candidates|{review['candidate_count']}")
        print(f"p12_shadow_watchlist|json|{paths['json_path']}")
        print(f"p12_shadow_watchlist|candidates_csv|{paths['candidates_csv_path']}")
        print(f"p12_shadow_watchlist|markdown|{paths['markdown_path']}")
    elif args.command == "p12-import-shadow-watchlist":
        result = import_shadow_watchlist_review(Path(args.path), service=args.service)
        print(f"p12_shadow_watchlist_import|imported|{result['imported_count']}")
        print(f"p12_shadow_watchlist_import|candidates|{result['candidate_count']}")
        for run_id in result["run_ids"]:
            print(f"p12_shadow_watchlist_import|run_id|{run_id}")
    elif args.command == "p13-shadow-outcome-review":

        shadow_rows = load_shadow_watchlist_read_model_rows(args.shadow_json)
        shadow_candidates = pd.DataFrame(shadow_rows["candidates"])
        bars = pd.read_csv(args.bars_csv)
        review = build_shadow_outcome_review(
            review_date=args.review_date,
            shadow_candidates=shadow_candidates,
            bars=bars,
            run_id=args.run_id,
        )
        paths = write_shadow_outcome_review(review, args.output_dir)
        print(f"p13_shadow_outcome|status|{review['status']}")
        print(f"p13_shadow_outcome|outcomes|{review['outcome_count']}")
        print(f"p13_shadow_outcome|json|{paths['json_path']}")
        print(f"p13_shadow_outcome|details_csv|{paths['details_csv_path']}")
        print(f"p13_shadow_outcome|markdown|{paths['markdown_path']}")
    elif args.command == "p13-import-shadow-outcomes":
        result = import_shadow_outcome_review(Path(args.path), service=args.service)
        print(f"p13_shadow_outcome_import|imported|{result['imported_count']}")
        print(f"p13_shadow_outcome_import|candidates|{result['candidate_count']}")
        for run_id in result["run_ids"]:
            print(f"p13_shadow_outcome_import|run_id|{run_id}")
    elif args.command == "p14-shadow-outcome-analytics":

        rows = load_shadow_outcome_read_model_rows(args.shadow_outcomes_json)
        shadow_outcomes = pd.DataFrame(rows["candidates"])
        analytics = build_shadow_outcome_analytics(
            review_start_date=args.review_start_date,
            review_end_date=args.review_end_date,
            shadow_outcomes=shadow_outcomes,
            run_id=args.run_id,
        )
        paths = write_shadow_outcome_analytics(analytics, args.output_dir)
        print(f"p14_shadow_outcome_analytics|status|{analytics['status']}")
        print(f"p14_shadow_outcome_analytics|source_outcomes|{analytics['source_outcome_count']}")
        print(f"p14_shadow_outcome_analytics|groups|{analytics['group_count']}")
        print(f"p14_shadow_outcome_analytics|json|{paths['json_path']}")
        print(f"p14_shadow_outcome_analytics|groups_csv|{paths['groups_csv_path']}")
        print(f"p14_shadow_outcome_analytics|markdown|{paths['markdown_path']}")
    elif args.command == "p15-shadow-analytics-review":
        p14_payload = json.loads(Path(args.p14_analytics_json).read_text(encoding="utf-8"))
        review = build_shadow_analytics_review(
            p14_analytics=p14_payload,
            run_id=args.run_id,
            review_start_date=args.review_start_date,
            review_end_date=args.review_end_date,
            reviewer_id=args.reviewer_id,
        )
        paths = write_shadow_analytics_review(review, args.output_dir)
        print(f"p15_shadow_analytics_review|status|{review['status']}")
        print(f"p15_shadow_analytics_review|groups|{review['group_count']}")
        print(f"p15_shadow_analytics_review|json|{paths['json_path']}")
        print(f"p15_shadow_analytics_review|groups_csv|{paths['groups_csv_path']}")
        print(f"p15_shadow_analytics_review|markdown|{paths['markdown_path']}")
    elif args.command == "p16-shadow-review-decisions":
        p15_payload = json.loads(Path(args.p15_review_json).read_text(encoding="utf-8"))
        decisions = build_shadow_review_decisions(
            p15_review=p15_payload,
            run_id=args.run_id,
            decision_date=args.decision_date,
            operator_id=args.operator_id,
        )
        paths = write_shadow_review_decisions(decisions, args.output_dir)
        print(f"p16_shadow_review_decisions|status|{decisions['status']}")
        print(f"p16_shadow_review_decisions|groups|{decisions['group_count']}")
        print(f"p16_shadow_review_decisions|json|{paths['json_path']}")
        print(f"p16_shadow_review_decisions|groups_csv|{paths['groups_csv_path']}")
        print(f"p16_shadow_review_decisions|markdown|{paths['markdown_path']}")
    elif args.command == "p17-shadow-follow-up-queue":
        p16_payload = json.loads(Path(args.p16_decisions_json).read_text(encoding="utf-8"))
        queue = build_shadow_follow_up_queue(
            p16_decisions=p16_payload,
            run_id=args.run_id,
            follow_up_date=args.follow_up_date,
            operator_id=args.operator_id,
        )
        paths = write_shadow_follow_up_queue(queue, args.output_dir)
        print(f"p17_shadow_follow_up_queue|status|{queue['status']}")
        print(f"p17_shadow_follow_up_queue|items|{queue['item_count']}")
        print(f"p17_shadow_follow_up_queue|json|{paths['json_path']}")
        print(f"p17_shadow_follow_up_queue|items_csv|{paths['items_csv_path']}")
        print(f"p17_shadow_follow_up_queue|markdown|{paths['markdown_path']}")
    elif args.command == "p18-shadow-follow-up-resolution":
        p17_payload = json.loads(Path(args.p17_follow_up_json).read_text(encoding="utf-8"))
        resolution = build_shadow_follow_up_resolution(
            p17_follow_up=p17_payload,
            run_id=args.run_id,
            resolution_date=args.resolution_date,
            operator_id=args.operator_id,
        )
        paths = write_shadow_follow_up_resolution(resolution, args.output_dir)
        print(f"p18_shadow_follow_up_resolution|status|{resolution['status']}")
        print(f"p18_shadow_follow_up_resolution|items|{resolution['item_count']}")
        print(f"p18_shadow_follow_up_resolution|json|{paths['json_path']}")
        print(f"p18_shadow_follow_up_resolution|items_csv|{paths['items_csv_path']}")
        print(f"p18_shadow_follow_up_resolution|markdown|{paths['markdown_path']}")
    elif args.command == "p14-import-shadow-outcome-analytics":
        result = import_shadow_outcome_analytics(args.path, service=args.service)
        print(f"p14_import_shadow_outcome_analytics|imported|{result['imported_count']}")
        print(f"p14_import_shadow_outcome_analytics|groups|{result['group_count']}")
        print(f"p14_import_shadow_outcome_analytics|runs|{','.join(result['run_ids'])}")
    elif args.command == "p15-import-shadow-analytics-review":
        result = import_shadow_analytics_review(args.path, service=args.service)
        print(f"p15_import_shadow_analytics_review|imported|{result['imported_count']}")
        print(f"p15_import_shadow_analytics_review|groups|{result['group_count']}")
        print(f"p15_import_shadow_analytics_review|runs|{','.join(result['run_ids'])}")
    elif args.command == "p16-import-shadow-review-decisions":
        result = import_shadow_review_decisions(args.path, service=args.service)
        print(f"p16_import_shadow_review_decisions|imported|{result['imported_count']}")
        print(f"p16_import_shadow_review_decisions|groups|{result['group_count']}")
        print(f"p16_import_shadow_review_decisions|runs|{','.join(result['run_ids'])}")
    elif args.command == "p17-import-shadow-follow-up-queue":
        result = import_shadow_follow_up_queue(args.path, service=args.service)
        print(f"p17_import_shadow_follow_up_queue|imported|{result['imported_count']}")
        print(f"p17_import_shadow_follow_up_queue|items|{result['item_count']}")
        print(f"p17_import_shadow_follow_up_queue|runs|{','.join(result['run_ids'])}")
    elif args.command == "p18-import-shadow-follow-up-resolution":
        result = import_shadow_follow_up_resolution(args.path, service=args.service)
        print(f"p18_import_shadow_follow_up_resolution|imported|{result['imported_count']}")
        print(f"p18_import_shadow_follow_up_resolution|items|{result['item_count']}")
        print(f"p18_import_shadow_follow_up_resolution|runs|{','.join(result['run_ids'])}")
    elif args.command == "p4-daily-orchestration":
        result = run_daily_orchestration(
            trade_date=args.trade_date,
            aggregate_review_path=Path(args.aggregate_review),
            virtual_portfolio_path=Path(args.virtual_portfolio),
            output_dir=Path(args.output_dir),
            portfolio_id=args.portfolio_id,
            apply_daily_run_schema=args.apply_daily_run_schema,
            record_run=args.record_run,
            service=args.service,
        )
        for line in format_daily_orchestration_lines(result):
            print(line)
    elif args.command == "p4-read-model-smoke":
        result = check_read_model_freshness(
            trade_date=args.trade_date,
            operator_manifest_path=Path(args.operator_manifest),
            portfolio_id=args.portfolio_id,
            service=args.service,
        )
        for line in format_read_model_freshness_lines(result):
            print(line)
    elif args.command == "p4-scheduler-cron-entry":
        print(
            build_p4_scheduler_cron_entry(
                project_dir=args.project_dir,
                trade_date_expr=args.trade_date_expr,
                hour=args.hour,
                minute=args.minute,
                weekdays=args.weekdays,
                portfolio_id=args.portfolio_id,
                service=args.service,
                log_path=args.log_path,
            )
        )
    elif args.command == "run-daily-incremental":
        if args.apply_daily_run_schema:
            apply_daily_job_run_schema()
        recorder = None
        if args.record_run:
            recorder = lambda step: record_daily_job_run(
                trade_date=args.trade_date,
                step=step["step"],
                status=step["status"],
                metadata=step.get("result") or {},
                error_message=step.get("error"),
            )
        result = run_daily_incremental_pipeline(
            trade_date=args.trade_date,
            score_version=args.score_version,
            top_n=args.top_n,
            lookback_bars=args.lookback_bars,
            reports_dir=args.reports_dir,
            adjust_type=args.adjust_type,
            source_service=args.source_service,
            industry_system=args.industry_system,
            label_start_date=args.label_start_date,
            dry_run=args.dry_run,
            step_runners=None if args.dry_run else build_default_step_runners(),
            freshness_checker=None,
            recorder=recorder,
            start_at=args.start_at,
            only_step=args.only_step,
        )
        print(f"daily_incremental|status|{result['status']}")
        if "reason" in result:
            print(f"daily_incremental|reason|{result['reason']}")
        for step in result["steps"]:
            print(f"daily_incremental_step|{step['step']}|{step['status']}")
            if "error" in step:
                print(f"daily_incremental_step_error|{step['step']}|{step['error']}")
    elif args.command == "build-mid-trend-watch-funnel":
        result = run_mid_trend_watch_funnel(
            discovery_pool_path=args.discovery_pool_path,
            trade_date=args.trade_date,
            top50_size=args.top50_size,
            top10_size=args.top10_size,
            context_detail_path=args.context_detail_path,
            market_regime_path=args.market_regime_path,
            industry_mainline_path=args.industry_mainline_path,
            output_dir=args.output_dir,
        )
        print(f"mid_trend_watch_funnel|detail|{result['paths']['detail']}")
        print(f"mid_trend_watch_funnel|layer_effectiveness|{result['paths']['layer_effectiveness']}")
        print(f"mid_trend_watch_funnel|pool_effectiveness|{result['paths']['pool_effectiveness']}")
        print(f"mid_trend_watch_funnel|top50|{result['paths']['top50']}")
        print(f"mid_trend_watch_funnel|top10|{result['paths']['top10']}")
        print(f"mid_trend_watch_funnel|report|{result['paths']['report']}")
        print(f"mid_trend_watch_funnel|rows|{len(result['detail'])}")
    elif args.command == "validate-mid-trend-drawdown-control":
        result = run_mid_trend_drawdown_control_validation(
            funnel_detail_path=args.funnel_detail_path,
            baseline_top10_path=args.baseline_top10_path,
            top_n=args.top_n,
            output_dir=args.output_dir,
        )
        print(f"mid_trend_drawdown_control|variant_detail|{result['paths']['variant_detail']}")
        print(f"mid_trend_drawdown_control|effectiveness|{result['paths']['effectiveness']}")
        print(f"mid_trend_drawdown_control|recommendations|{result['paths']['recommendations']}")
        print(f"mid_trend_drawdown_control|report|{result['paths']['report']}")
        print(f"mid_trend_drawdown_control|rows|{len(result['variant_detail'])}")
    elif args.command == "scan-mid-trend-risk-return-pareto":
        result = run_mid_trend_pareto_scan(
            funnel_detail_path=args.funnel_detail_path,
            top_n=args.top_n,
            output_dir=args.output_dir,
        )
        print(f"mid_trend_pareto_scan|threshold_scan|{result['paths']['threshold_scan']}")
        print(f"mid_trend_pareto_scan|combo_scan|{result['paths']['combo_scan']}")
        print(
            "mid_trend_pareto_scan|high_elasticity_decomposition|"
            f"{result['paths']['high_elasticity_decomposition']}"
        )
        print(f"mid_trend_pareto_scan|pareto_recommendations|{result['paths']['pareto_recommendations']}")
        print(f"mid_trend_pareto_scan|report|{result['paths']['report']}")
        print(f"mid_trend_pareto_scan|rows|{len(result['threshold_scan'])}")
    elif args.command == "review-mid-trend-shadow-stability":
        result = run_mid_trend_shadow_stability_review(
            funnel_detail_path=args.funnel_detail_path,
            baseline_top10_path=args.baseline_top10_path,
            top_n=args.top_n,
            output_dir=args.output_dir,
        )
        print(f"mid_trend_shadow_stability|by_period|{result['paths']['by_period']}")
        print(f"mid_trend_shadow_stability|by_regime|{result['paths']['by_regime']}")
        print(f"mid_trend_shadow_stability|by_industry|{result['paths']['by_industry']}")
        print(f"mid_trend_shadow_stability|by_layer|{result['paths']['by_layer']}")
        print(f"mid_trend_shadow_stability|decision|{result['paths']['decision']}")
        print(f"mid_trend_shadow_stability|report|{result['paths']['report']}")
        print(f"mid_trend_shadow_stability|rows|{len(result['by_period'])}")
    elif args.command == "build-mid-trend-shadow-top10":
        result = run_mid_trend_shadow_top10(
            funnel_detail_path=args.funnel_detail_path,
            trade_date=args.trade_date,
            top_n=args.top_n,
            output_dir=args.output_dir,
        )
        print(f"mid_trend_shadow_top10|top10|{result['paths']['top10']}")
        print(f"mid_trend_shadow_top10|daily_summary|{result['paths']['daily_summary']}")
        print(f"mid_trend_shadow_top10|industry_summary|{result['paths']['industry_summary']}")
        print(f"mid_trend_shadow_top10|report|{result['paths']['report']}")
        print(f"mid_trend_shadow_top10|rows|{len(result['top10'])}")
    elif args.command == "build-mid-trend-research-packet":
        result = run_mid_trend_research_packet(
            funnel_detail_path=args.funnel_detail_path,
            fundamental_path=args.fundamental_path,
            stock_report_feature_path=args.stock_report_feature_path,
            trade_date=args.trade_date,
            top_n=args.top_n,
            score_floor=args.score_floor,
            output_dir=args.output_dir,
        )
        print(f"mid_trend_research_packet|candidates|{result['paths']['candidates']}")
        print(f"mid_trend_research_packet|manual_fields|{result['paths']['manual_fields']}")
        print(f"mid_trend_research_packet|report|{result['paths']['report']}")
        print(f"mid_trend_research_packet|rows|{len(result['candidates'])}")
    elif args.command == "build-mid-trend-portfolio-review":
        result = run_mid_trend_portfolio_review(
            trade_date=args.trade_date,
            strategy_variant=args.strategy_variant,
            top10_path=args.top10_path,
            holdings_path=args.holdings_path,
            trades_path=args.trades_path,
            research_packet_path=args.research_packet_path,
            output_dir=args.output_dir,
            write_research_infra=args.write_research_infra,
        )
        print(f"mid_trend_portfolio_review|csv|{result['paths']['csv']}")
        print(f"mid_trend_portfolio_review|report|{result['paths']['report']}")
        print(f"mid_trend_portfolio_review|rows|{len(result['review_rows'])}")
        research_infra = result.get("research_infra")
        if research_infra:
            print(
                "mid_trend_portfolio_review|research_infra|"
                f"{research_infra['research_infra_dir']}"
            )
            print(
                "mid_trend_portfolio_review|research_signals|"
                f"{research_infra['research_signals_json_path']}"
            )
            print(
                "mid_trend_portfolio_review|attribution_cards|"
                f"{research_infra['attribution_cards_json_path']}"
            )
            print(
                "mid_trend_portfolio_review|run_card|"
                f"{research_infra['run_card']['run_card_json_path']}"
            )
    elif args.command == "build-mid-trend-position-dossier":
        result = run_mid_trend_position_dossier(
            trade_date=args.trade_date,
            mode=args.mode,
            portfolio_review_path=args.portfolio_review_path,
            research_packet_path=args.research_packet_path,
            news_enrichment_path=args.news_enrichment_path,
            output_dir=args.output_dir,
        )
        print(f"mid_trend_position_dossier|csv|{result['paths']['csv']}")
        print(f"mid_trend_position_dossier|report|{result['paths']['report']}")
        print(f"mid_trend_position_dossier|rows|{len(result['summary_rows'])}")
        if args.news_enrichment_path is not None:
            status = result.get("news_enrichment_status", result.get("summary", {}))
            print(
                "mid_trend_position_dossier|news_enrichment_provided|"
                f"{status.get('news_enrichment_provided', 'yes')}"
            )
            print(
                "mid_trend_position_dossier|news_enrichment_used|"
                f"{status.get('news_enrichment_used', 'no')}"
            )
            print(
                "mid_trend_position_dossier|matched_news_rows|"
                f"{status.get('matched_news_rows', 0)}"
            )
    elif args.command == "backtest-mid-trend-shadow-top10":
        result = run_mid_trend_shadow_backtest(
            shadow_top10_path=args.shadow_top10_path,
            start_date=args.start_date,
            end_date=args.end_date,
            top_n=args.top_n,
            rebalance_frequency=args.rebalance_frequency,
            transaction_cost_bps=args.transaction_cost_bps,
            adjust_type=args.adjust_type,
            output_dir=args.output_dir,
        )
        print(f"mid_trend_shadow_backtest|equity_curve|{result['paths']['equity_curve']}")
        print(f"mid_trend_shadow_backtest|positions|{result['paths']['positions']}")
        print(f"mid_trend_shadow_backtest|trades|{result['paths']['trades']}")
        print(f"mid_trend_shadow_backtest|summary|{result['paths']['summary']}")
        print(f"mid_trend_shadow_backtest|report|{result['paths']['report']}")
        print(f"mid_trend_shadow_backtest|rows|{len(result.get('equity_curve', []))}")
    elif args.command == "optimize-mid-trend-shadow-weekly":
        top_n_values = (
            parse_int_list(args.top_n_values, "--top-n-values")
            if isinstance(args.top_n_values, str)
            else args.top_n_values
        )
        transaction_cost_bps_values = (
            parse_float_list(args.transaction_cost_bps_values, "--transaction-cost-bps-values")
            if isinstance(args.transaction_cost_bps_values, str)
            else args.transaction_cost_bps_values
        )
        result = run_mid_trend_shadow_weekly_optimization(
            funnel_detail_path=args.funnel_detail_path,
            start_date=args.start_date,
            end_date=args.end_date,
            top_n_values=top_n_values,
            transaction_cost_bps_values=transaction_cost_bps_values,
            adjust_type=args.adjust_type,
            output_dir=args.output_dir,
        )
        print(f"mid_trend_shadow_weekly_optimization|summary|{result['paths']['summary']}")
        print(f"mid_trend_shadow_weekly_optimization|best_equity_curve|{result['paths']['best_equity_curve']}")
        print(f"mid_trend_shadow_weekly_optimization|best_positions|{result['paths']['best_positions']}")
        print(f"mid_trend_shadow_weekly_optimization|best_trades|{result['paths']['best_trades']}")
        print(f"mid_trend_shadow_weekly_optimization|report|{result['paths']['report']}")
        print(f"mid_trend_shadow_weekly_optimization|rows|{len(result.get('summary', []))}")
    elif args.command == "serenity-tight3b-c2-experiment":
        top_n_values = (
            parse_int_list(args.top_n_values, "--top-n-values")
            if isinstance(args.top_n_values, str)
            else args.top_n_values
        )
        rebalance_frequencies = (
            [item.strip() for item in args.rebalance_frequencies.split(",") if item.strip()]
            if isinstance(args.rebalance_frequencies, str)
            else args.rebalance_frequencies
        )
        result = run_serenity_tight3b_c2_experiment(
            candidates_path=args.candidates_path,
            market_exposure_path=args.market_exposure_path,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
            universe_name=args.universe_name,
            top_n_values=top_n_values,
            rebalance_frequencies=rebalance_frequencies,
            transaction_cost_bps=args.transaction_cost_bps,
            adjust_type=args.adjust_type,
        )
        print(f"serenity_tight3b_c2|summary|{result['paths']['summary']}")
        print(f"serenity_tight3b_c2|equity|{result['paths']['equity']}")
        print(f"serenity_tight3b_c2|positions|{result['paths']['positions']}")
        print(f"serenity_tight3b_c2|trades|{result['paths']['trades']}")
        if "best_equity" in result["paths"]:
            print(f"serenity_tight3b_c2|best_equity|{result['paths']['best_equity']}")
            print(f"serenity_tight3b_c2|best_positions|{result['paths']['best_positions']}")
            print(f"serenity_tight3b_c2|best_trades|{result['paths']['best_trades']}")
        print(f"serenity_tight3b_c2|report|{result['paths']['report']}")
        print(f"serenity_tight3b_c2|rows|{len(result.get('summary', []))}")
    elif args.command == "serenity-source-backed-evidence-fill":
        result = run_serenity_source_backed_evidence_fill(
            structured_detail_path=args.structured_detail_path,
            evidence_seed_path=args.evidence_seed_path,
            output_dir=args.output_dir,
            run_id=args.run_id,
        )
        print(f"serenity_source_backed_evidence|detail|{result['paths']['detail']}")
        print(f"serenity_source_backed_evidence|long|{result['paths']['long']}")
        print(f"serenity_source_backed_evidence|summary|{result['paths']['summary']}")
        print(f"serenity_source_backed_evidence|manual_queue|{result['paths']['manual_queue']}")
        print(f"serenity_source_backed_evidence|report|{result['paths']['report']}")
        print(f"serenity_source_backed_evidence|summary_rows|{len(result.get('summary', []))}")
        print(f"serenity_source_backed_evidence|manual_queue_rows|{len(result.get('manual_queue', []))}")
    elif args.command == "tech-bottleneck-evidence-workflow":
        result = run_tech_bottleneck_evidence_workflow(
            asset_queue_path=args.asset_queue_path,
            evidence_detail_path=args.evidence_detail_path,
            candidate_path=args.candidate_path,
            trade_date=args.trade_date,
            top_n=args.top_n,
            output_dir=args.output_dir,
        )
        print(f"tech_bottleneck_evidence|topn_queue|{result['paths']['topn_backfill_queue']}")
        print(f"tech_bottleneck_evidence|weak_queue|{result['paths']['weak_evidence_queue']}")
        print(f"tech_bottleneck_evidence|adjusted_candidates|{result['paths']['adjusted_candidates']}")
        print(f"tech_bottleneck_evidence|yanbaoke_tasks|{result['paths']['yanbaoke_tasks']}")
        print(f"tech_bottleneck_evidence|report|{result['paths']['report']}")
        print(f"tech_bottleneck_evidence|topn_queue_rows|{len(result['topn_backfill_queue'])}")
        print(f"tech_bottleneck_evidence|weak_queue_rows|{len(result['weak_evidence_queue'])}")
    elif args.command == "review-mid-trend-shadow-weekly-control":
        result = run_mid_trend_shadow_weekly_control_review(
            funnel_detail_path=args.funnel_detail_path,
            start_date=args.start_date,
            end_date=args.end_date,
            top_n=args.top_n,
            buffer_rank=args.buffer_rank,
            max_weekly_replacements=args.max_weekly_replacements,
            peak_drawdown_exit=args.peak_drawdown_exit,
            transaction_cost_bps=args.transaction_cost_bps,
            adjust_type=args.adjust_type,
            output_dir=args.output_dir,
        )
        print(f"mid_trend_shadow_weekly_control|summary|{result['paths']['summary']}")
        print(f"mid_trend_shadow_weekly_control|equity_curve|{result['paths']['equity_curve']}")
        print(f"mid_trend_shadow_weekly_control|positions|{result['paths']['positions']}")
        print(f"mid_trend_shadow_weekly_control|trades|{result['paths']['trades']}")
        print(f"mid_trend_shadow_weekly_control|report|{result['paths']['report']}")
        print(f"mid_trend_shadow_weekly_control|rows|{len(result.get('summary', []))}")
    elif args.command == "review-mid-trend-adaptive-candidate":
        cost_bps_values = (
            parse_float_list(args.cost_bps_values, "--cost-bps-values")
            if isinstance(args.cost_bps_values, str)
            else args.cost_bps_values
        )
        result = run_mid_trend_adaptive_candidate_review(
            funnel_detail_path=args.funnel_detail_path,
            start_date=args.start_date,
            end_date=args.end_date,
            cost_bps_values=cost_bps_values,
            top_n=args.top_n,
            buffer_rank=args.buffer_rank,
            max_weekly_replacements=args.max_weekly_replacements,
            transaction_cost_bps=args.transaction_cost_bps,
            adjust_type=args.adjust_type,
            output_dir=args.output_dir,
        )
        print(f"mid_trend_adaptive_candidate|monthly|{result['paths']['monthly']}")
        print(f"mid_trend_adaptive_candidate|quarterly|{result['paths']['quarterly']}")
        print(f"mid_trend_adaptive_candidate|attribution_summary|{result['paths']['attribution_summary']}")
        print(f"mid_trend_adaptive_candidate|attribution_detail|{result['paths']['attribution_detail']}")
        print(f"mid_trend_adaptive_candidate|cost_scan|{result['paths']['cost_scan']}")
        print(f"mid_trend_adaptive_candidate|weak_periods|{result['paths']['weak_periods']}")
        print(f"mid_trend_adaptive_candidate|report|{result['paths']['report']}")
        print(f"mid_trend_adaptive_candidate|rows|{len(result.get('monthly', []))}")
    elif args.command == "review-mid-trend-adaptive-issue-attribution":
        result = run_mid_trend_adaptive_issue_attribution(
            monthly_path=args.monthly_path,
            attribution_detail_path=args.attribution_detail_path,
            funnel_detail_path=args.funnel_detail_path,
            output_dir=args.output_dir,
        )
        print(f"mid_trend_adaptive_issue_attribution|period_gap|{result['paths']['period_gap']}")
        print(f"mid_trend_adaptive_issue_attribution|sell_fly_detail|{result['paths']['sell_fly_detail']}")
        print(f"mid_trend_adaptive_issue_attribution|feature_summary|{result['paths']['feature_summary']}")
        print(f"mid_trend_adaptive_issue_attribution|report|{result['paths']['report']}")
        print(f"mid_trend_adaptive_issue_attribution|rows|{len(result.get('period_gap', []))}")
    elif args.command == "review-mid-trend-adaptive-bad-buy-attribution":
        result = run_mid_trend_adaptive_bad_buy_attribution(
            attribution_detail_path=args.attribution_detail_path,
            funnel_detail_path=args.funnel_detail_path,
            output_dir=args.output_dir,
        )
        print(f"mid_trend_adaptive_bad_buy_attribution|bad_buy_detail|{result['paths']['bad_buy_detail']}")
        print(f"mid_trend_adaptive_bad_buy_attribution|feature_contrast|{result['paths']['feature_contrast']}")
        print(f"mid_trend_adaptive_bad_buy_attribution|report|{result['paths']['report']}")
        print(f"mid_trend_adaptive_bad_buy_attribution|rows|{len(result.get('bad_buy_detail', []))}")
    elif args.command == "review-mid-trend-entry-timing-attribution":
        result = run_mid_trend_entry_timing_attribution(
            attribution_detail_path=args.attribution_detail_path,
            start_date=args.start_date,
            end_date=args.end_date,
            prices_path=args.prices_path,
            valuation_path=args.valuation_path,
            adjust_type=args.adjust_type,
            output_dir=args.output_dir,
        )
        print(f"mid_trend_entry_timing_attribution|detail|{result['paths']['entry_timing_detail']}")
        print(f"mid_trend_entry_timing_attribution|contrast|{result['paths']['entry_timing_contrast']}")
        print(f"mid_trend_entry_timing_attribution|report|{result['paths']['report']}")
        print(f"mid_trend_entry_timing_attribution|rows|{len(result.get('entry_timing_detail', []))}")
    elif args.command == "scan-mid-trend-shadow-replacements":
        top_n_values = (
            parse_int_list(args.top_n_values, "--top-n-values")
            if isinstance(args.top_n_values, str)
            else args.top_n_values
        )
        max_weekly_replacement_values = (
            parse_int_list(args.max_weekly_replacements_values, "--max-weekly-replacements-values")
            if isinstance(args.max_weekly_replacements_values, str)
            else args.max_weekly_replacements_values
        )
        transaction_cost_bps_values = (
            parse_float_list(args.transaction_cost_bps_values, "--transaction-cost-bps-values")
            if isinstance(args.transaction_cost_bps_values, str)
            else args.transaction_cost_bps_values
        )
        result = run_mid_trend_shadow_replacement_scan(
            funnel_detail_path=args.funnel_detail_path,
            start_date=args.start_date,
            end_date=args.end_date,
            top_n_values=top_n_values,
            max_weekly_replacement_values=max_weekly_replacement_values,
            transaction_cost_bps_values=transaction_cost_bps_values,
            adjust_type=args.adjust_type,
            output_dir=args.output_dir,
        )
        print(f"mid_trend_shadow_replacement_scan|summary|{result['paths']['summary']}")
        print(f"mid_trend_shadow_replacement_scan|report|{result['paths']['report']}")
        print(f"mid_trend_shadow_replacement_scan|rows|{len(result.get('summary', []))}")
    elif args.command == "scan-mid-trend-protection":
        score_gap_values = (
            parse_float_list(args.score_gap_values, "--score-gap-values")
            if isinstance(args.score_gap_values, str)
            else args.score_gap_values
        )
        mainline_gap_values = (
            parse_float_list(args.mainline_gap_values, "--mainline-gap-values")
            if isinstance(args.mainline_gap_values, str)
            else args.mainline_gap_values
        )
        trend_r2_min_values = (
            parse_float_list(args.trend_r2_min_values, "--trend-r2-min-values")
            if isinstance(args.trend_r2_min_values, str)
            else args.trend_r2_min_values
        )
        ret20_min_values = (
            parse_float_list(args.ret20_min_values, "--ret20-min-values")
            if isinstance(args.ret20_min_values, str)
            else args.ret20_min_values
        )
        drawdown_min_values = (
            parse_float_list(args.drawdown_min_values, "--drawdown-min-values")
            if isinstance(args.drawdown_min_values, str)
            else args.drawdown_min_values
        )
        result = run_mid_trend_trend_protection_scan(
            funnel_detail_path=args.funnel_detail_path,
            start_date=args.start_date,
            end_date=args.end_date,
            score_gap_values=score_gap_values,
            mainline_gap_values=mainline_gap_values,
            trend_r2_min_values=trend_r2_min_values,
            ret20_min_values=ret20_min_values,
            drawdown_min_values=drawdown_min_values,
            top_n=args.top_n,
            max_weekly_replacements=args.max_weekly_replacements,
            transaction_cost_bps=args.transaction_cost_bps,
            adjust_type=args.adjust_type,
            output_dir=args.output_dir,
        )
        print(f"mid_trend_trend_protection_scan|summary|{result['paths']['summary']}")
        print(f"mid_trend_trend_protection_scan|report|{result['paths']['report']}")
        print(f"mid_trend_trend_protection_scan|rows|{len(result.get('summary', []))}")
    elif args.command == "scan-mid-trend-drawdown-throttle":
        threshold_values = (
            parse_float_list(args.threshold_values, "--threshold-values")
            if isinstance(args.threshold_values, str)
            else args.threshold_values
        )
        invested_weight_values = (
            parse_float_list(args.invested_weight_values, "--invested-weight-values")
            if isinstance(args.invested_weight_values, str)
            else args.invested_weight_values
        )
        max_replacement_values = (
            parse_int_list(args.max_replacement_values, "--max-replacement-values")
            if isinstance(args.max_replacement_values, str)
            else args.max_replacement_values
        )
        result = run_mid_trend_drawdown_throttle_scan(
            funnel_detail_path=args.funnel_detail_path,
            start_date=args.start_date,
            end_date=args.end_date,
            threshold_values=threshold_values,
            invested_weight_values=invested_weight_values,
            max_replacement_values=max_replacement_values,
            top_n=args.top_n,
            buffer_rank=args.buffer_rank,
            max_weekly_replacements=args.max_weekly_replacements,
            transaction_cost_bps=args.transaction_cost_bps,
            adjust_type=args.adjust_type,
            output_dir=args.output_dir,
        )
        print(f"mid_trend_drawdown_throttle_scan|summary|{result['paths']['summary']}")
        print(f"mid_trend_drawdown_throttle_scan|report|{result['paths']['report']}")
        print(f"mid_trend_drawdown_throttle_scan|rows|{len(result.get('summary', []))}")
    elif args.command == "review-mid-trend-protection-stability":
        result = run_mid_trend_trend_protection_stability_review(
            funnel_detail_path=args.funnel_detail_path,
            start_date=args.start_date,
            end_date=args.end_date,
            protection_score_gap=args.protection_score_gap,
            protection_mainline_gap=args.protection_mainline_gap,
            protection_trend_r2_min=args.protection_trend_r2_min,
            protection_ret20_min=args.protection_ret20_min,
            protection_drawdown_min=args.protection_drawdown_min,
            top_n=args.top_n,
            max_weekly_replacements=args.max_weekly_replacements,
            transaction_cost_bps=args.transaction_cost_bps,
            adjust_type=args.adjust_type,
            output_dir=args.output_dir,
        )
        print(f"mid_trend_trend_protection_stability|monthly|{result['paths']['monthly']}")
        print(f"mid_trend_trend_protection_stability|quarterly|{result['paths']['quarterly']}")
        print(
            "mid_trend_trend_protection_stability|attribution_summary|"
            f"{result['paths']['attribution_summary']}"
        )
        print(
            "mid_trend_trend_protection_stability|attribution_detail|"
            f"{result['paths']['attribution_detail']}"
        )
        print(f"mid_trend_trend_protection_stability|report|{result['paths']['report']}")
        print(f"mid_trend_trend_protection_stability|rows|{len(result.get('monthly', []))}")
    elif args.command == "review-mid-trend-rebalance-attribution":
        result = run_mid_trend_rebalance_attribution(
            trades_path=args.trades_path,
            equity_path=args.equity_path,
            start_date=args.start_date,
            end_date=args.end_date,
            variant_name=args.variant_name,
            adjust_type=args.adjust_type,
            output_dir=args.output_dir,
        )
        print(f"mid_trend_rebalance_attribution|detail|{result['paths']['detail']}")
        print(f"mid_trend_rebalance_attribution|summary|{result['paths']['summary']}")
        print(f"mid_trend_rebalance_attribution|report|{result['paths']['report']}")
        print(f"mid_trend_rebalance_attribution|rows|{len(result.get('detail', []))}")
    elif args.command == "scan-mid-trend-shadow-control-v2":
        result = run_mid_trend_shadow_control_v2_scan(
            funnel_detail_path=args.funnel_detail_path,
            start_date=args.start_date,
            end_date=args.end_date,
            top_n=args.top_n,
            base_max_replacements=args.base_max_replacements,
            drawdown_threshold=args.drawdown_threshold,
            drawdown_worsen_threshold=args.drawdown_worsen_threshold,
            transaction_cost_bps=args.transaction_cost_bps,
            adjust_type=args.adjust_type,
            output_dir=args.output_dir,
        )
        print(f"mid_trend_shadow_control_v2|summary|{result['paths']['summary']}")
        print(f"mid_trend_shadow_control_v2|equity_curve|{result['paths']['equity_curve']}")
        print(f"mid_trend_shadow_control_v2|positions|{result['paths']['positions']}")
        print(f"mid_trend_shadow_control_v2|trades|{result['paths']['trades']}")
        print(f"mid_trend_shadow_control_v2|report|{result['paths']['report']}")
        print(f"mid_trend_shadow_control_v2|rows|{len(result.get('summary', []))}")
    elif args.command == "review-bad-rebalance-state-attribution":
        result = run_bad_rebalance_state_attribution(
            attribution_detail_path=args.attribution_detail_path,
            funnel_detail_path=args.funnel_detail_path,
            output_dir=args.output_dir,
        )
        print(f"bad_rebalance_state_attribution|detail|{result['paths']['detail']}")
        print(f"bad_rebalance_state_attribution|feature_summary|{result['paths']['feature_summary']}")
        print(f"bad_rebalance_state_attribution|report|{result['paths']['report']}")
        print(f"bad_rebalance_state_attribution|rows|{len(result.get('detail', []))}")
    elif args.command == "build-stock-report-workpack":
        result = run_stock_report_workpack(
            research_packet_path=args.research_packet_path,
            trade_date=args.trade_date,
            output_dir=args.output_dir,
        )
        print(f"stock_report_workpack|workpack|{result['paths']['workpack']}")
        print(f"stock_report_workpack|import_template|{result['paths']['import_template']}")
        print(f"stock_report_workpack|report|{result['paths']['report']}")
        print(f"stock_report_workpack|rows|{len(result['workpack'])}")
    elif args.command == "build-stock-report-search-plan":
        result = run_stock_report_search_plan(
            research_packet_path=args.research_packet_path,
            trade_date=args.trade_date,
            output_dir=args.output_dir,
        )
        print(f"stock_report_search_plan|search_plan|{result['paths']['search_plan']}")
        print(f"stock_report_search_plan|report|{result['paths']['report']}")
        print(f"stock_report_search_plan|rows|{len(result['search_plan'])}")
    elif args.command == "collect-stock-report-web-sources":
        result = run_stock_report_web_source_collection(
            search_plan_path=args.search_plan_path,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
            adapter=args.adapter,
            max_fetches=args.max_fetches,
            write_db=args.write_db,
            service=args.service,
            http_timeout_seconds=args.http_timeout_seconds,
            request_sleep_seconds=args.request_sleep_seconds,
            stop_after_consecutive_fetch_errors=args.stop_after_consecutive_fetch_errors,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        print(f"stock_report_web_sources|collection|{result['paths']['collection']}")
        print(f"stock_report_web_sources|sources|{result['paths']['sources']}")
        print(f"stock_report_web_sources|events|{result['paths']['events']}")
        print(f"stock_report_web_sources|report|{result['paths']['report']}")
        print(f"stock_report_web_sources|rows|{len(result['collection'])}")
    elif args.command == "build-stock-report-features":
        result = run_stock_report_feature_build(
            events_path=args.events_path,
            trade_date=args.trade_date,
            output_dir=args.output_dir,
            write_db=args.write_db,
        )
        print(f"stock_report_features|features|{result['paths']['features']}")
        print(f"stock_report_features|report|{result['paths']['report']}")
        print(f"stock_report_features|rows|{len(result['features'])}")
    elif args.command == "stock-report-backfill-plan":
        result = run_stock_report_backfill_plan(
            start_date=args.start_date,
            end_date=args.end_date,
            sample_size=args.sample_size,
            output_dir=args.output_dir,
        )
        print(f"stock_report_backfill_plan|tasks|{result['paths']['tasks']}")
        print(f"stock_report_backfill_plan|report|{result['paths']['report']}")
        print(f"stock_report_backfill_plan|rows|{len(result['tasks'])}")
    elif args.command == "stock-report-backfill-run":
        result = run_stock_report_backfill_run(
            tasks_path=args.tasks_path,
            start_date=args.start_date,
            end_date=args.end_date,
            batch_size=args.batch_size,
            sleep_seconds=args.sleep_seconds,
            sample_size=args.sample_size,
            output_dir=args.output_dir,
            write_db=args.write_db,
        )
        print(f"stock_report_backfill_run|tasks_csv|{result['paths']['tasks']}")
        print(f"stock_report_backfill_run|sources|{result['paths']['sources']}")
        print(f"stock_report_backfill_run|events|{result['paths']['events']}")
        print(f"stock_report_backfill_run|report|{result['paths']['report']}")
        print(f"stock_report_backfill_run|tasks|{len(result['status'])}")
        print(f"stock_report_backfill_run|events_rows|{len(result['events'])}")
    elif args.command == "stock-report-backfill-watchdog":
        result = run_stock_report_backfill_watchdog(
            output_dir=args.output_dir,
            stale_after_minutes=args.stale_after_minutes,
            run_timeout_seconds=args.run_timeout_seconds,
            report_target=args.report_target,
            report_account=args.report_account,
            openclaw_bin=args.openclaw_bin,
            report_dry_run=args.report_dry_run,
        )
        status = result["status"]
        summary = result["post_summary"]
        print(f"stock_report_backfill_watchdog|action|{status.watchdog_action}")
        print(f"stock_report_backfill_watchdog|work_remaining|{status.work_remaining}")
        print(f"stock_report_backfill_watchdog|done|{summary.success_tasks}")
        print(f"stock_report_backfill_watchdog|no_report|{summary.skipped_tasks}")
        print(f"stock_report_backfill_watchdog|fetch_error|{summary.failed_tasks}")
        print(f"stock_report_backfill_watchdog|pending|{summary.pending_tasks}")
        print(f"stock_report_backfill_watchdog|report_rows|{summary.total_rows_written}")
    elif args.command == "stock-report-feature-backfill":
        result = run_stock_report_feature_backfill(
            start_date=args.start_date,
            end_date=args.end_date,
            events_path=args.events_path,
            output_dir=args.output_dir,
            write_db=args.write_db,
        )
        print(f"stock_report_feature_backfill|features|{result['paths']['features']}")
        print(f"stock_report_feature_backfill|report|{result['paths']['report']}")
        print(f"stock_report_feature_backfill|rows|{len(result['features'])}")
    elif args.command == "stock-report-pdf-field-backfill":
        result = run_stock_report_pdf_field_backfill(
            source_path=args.source_path,
            start_date=args.start_date,
            end_date=args.end_date,
            offset=args.offset,
            limit=args.limit,
            batch_size=args.batch_size,
            sleep_seconds=args.sleep_seconds,
            output_dir=args.output_dir,
            resume=args.resume,
            write_db=args.write_db,
        )
        print(f"stock_report_pdf_field_backfill|fields|{result['paths']['fields']}")
        print(f"stock_report_pdf_field_backfill|summary|{result['paths']['summary']}")
        print(f"stock_report_pdf_field_backfill|report|{result['paths']['report']}")
        print(f"stock_report_pdf_field_backfill|rows|{len(result['fields'])}")
    elif args.command == "stock-report-pdf-backfill-watchdog":
        result = run_stock_report_pdf_backfill_watchdog(
            output_dir=args.output_dir,
            stale_after_minutes=args.stale_after_minutes,
            run_timeout_seconds=args.run_timeout_seconds,
            report_target=args.report_target,
            report_account=args.report_account,
            openclaw_bin=args.openclaw_bin,
            report_dry_run=args.report_dry_run,
        )
        status = result["status"]
        summary = result["post_summary"]
        print(f"stock_report_pdf_backfill_watchdog|action|{status.watchdog_action}")
        print(f"stock_report_pdf_backfill_watchdog|work_remaining|{status.work_remaining}")
        print(f"stock_report_pdf_backfill_watchdog|parsed_or_empty|{summary.success_tasks}")
        print(f"stock_report_pdf_backfill_watchdog|parse_error|{summary.failed_tasks}")
        print(f"stock_report_pdf_backfill_watchdog|pending|{summary.pending_tasks}")
        print(f"stock_report_pdf_backfill_watchdog|target_price_rows|{summary.total_rows_written}")
    elif args.command == "yanbaoke-report-backfill-plan":
        candidates = pd.read_csv(args.candidate_path, dtype="string", low_memory=False)
        existing_coverage = (
            pd.read_csv(args.existing_coverage_path, dtype="string", low_memory=False)
            if args.existing_coverage_path
            else pd.DataFrame()
        )
        result = build_yanbaoke_inventory_plan(
            candidates=candidates,
            existing_coverage=existing_coverage,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
        )
        print(f"yanbaoke_report_backfill_plan|candidate_reports|{result['paths']['candidate_reports']}")
        print(f"yanbaoke_report_backfill_plan|existing_report_coverage|{result['paths']['existing_report_coverage']}")
        print(f"yanbaoke_report_backfill_plan|gap_matrix|{result['paths']['gap_matrix']}")
        print(f"yanbaoke_report_backfill_plan|sector_gap_matrix|{result['paths']['sector_gap_matrix']}")
        print(f"yanbaoke_report_backfill_plan|asset_gap_matrix|{result['paths']['asset_gap_matrix']}")
        print(f"yanbaoke_report_backfill_plan|priority_queue|{result['paths']['priority_queue']}")
        print(f"yanbaoke_report_backfill_plan|pilot_queue|{result['paths']['pilot_queue']}")
        print(f"yanbaoke_report_backfill_plan|report|{result['paths']['report']}")
        print(f"yanbaoke_report_backfill_plan|candidate_rows|{len(result['candidates'])}")
        print(f"yanbaoke_report_backfill_plan|pilot_rows|{len(result['pilot_queue'])}")
    elif args.command == "build-hibor-download-queue":
        pandas_module = __import__("pandas")
        candidates = pandas_module.read_csv(args.candidates_path, low_memory=False)
        result = build_hibor_download_queue(
            candidates,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
            brokers=args.brokers,
        )
        print(f"hibor_download_queue|queue|{result['paths']['queue']}")
        print(f"hibor_download_queue|report|{result['paths']['report']}")
        print(f"hibor_download_queue|rows|{len(result['queue'])}")
    elif args.command == "download-hibor-report-pdfs":
        pandas_module = __import__("pandas")
        candidates = pandas_module.read_csv(args.candidates_path, low_memory=False)
        result = download_hibor_report_pdfs(
            candidates,
            start_date=args.start_date,
            end_date=args.end_date,
            download_dir=args.download_dir,
            brokers=args.brokers,
            max_reports_per_candidate=args.max_reports_per_candidate,
        )
        print(f"hibor_report_download|downloads|{result['paths']['downloads']}")
        print(f"hibor_report_download|download_dir|{result['paths']['download_dir']}")
        print(f"hibor_report_download|attempted|{result['summary']['attempted_count']}")
        print(f"hibor_report_download|downloaded|{result['summary']['downloaded_count']}")
    elif args.command == "import-hibor-report-pdfs":
        result = import_hibor_report_pdfs(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            write_db=args.write_db,
            run_pdf_backfill=args.run_pdf_backfill,
            feature_trade_date=args.feature_trade_date,
        )
        print(f"hibor_report_import|sources|{result['paths']['sources']}")
        print(f"hibor_report_import|events|{result['paths']['events']}")
        if "fields" in result["paths"]:
            print(f"hibor_report_import|fields|{result['paths']['fields']}")
        if "features" in result["paths"]:
            print(f"hibor_report_import|features|{result['paths']['features']}")
        print(f"hibor_report_import|report|{result['paths']['report']}")
        print(f"hibor_report_import|pdf_count|{result['summary']['pdf_count']}")
    elif args.command == "watch-hibor-downloads":
        result = watch_hibor_downloads(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            poll_seconds=args.poll_seconds,
            max_cycles=args.max_cycles,
            write_db=args.write_db,
        )
        print(f"hibor_download_watch|sources|{result['paths']['sources']}")
        print(f"hibor_download_watch|events|{result['paths']['events']}")
        if "fields" in result["paths"]:
            print(f"hibor_download_watch|fields|{result['paths']['fields']}")
        print(f"hibor_download_watch|report|{result['paths']['report']}")
        print(f"hibor_download_watch|pdf_count|{result['summary']['pdf_count']}")
        print(f"hibor_download_watch|cycles|{result['summary']['watch_cycles']}")
    elif args.command == "build-hibor-a-tier-backfill-plan":
        assets = load_stock_report_asset_universe(service=args.service)
        if args.sample_size is not None:
            assets = assets.head(args.sample_size).copy()
        result = build_hibor_a_tier_backfill_plan(
            assets,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
        )
        print(f"hibor_a_tier_backfill_plan|tasks|{result['paths']['tasks']}")
        print(f"hibor_a_tier_backfill_plan|report|{result['paths']['report']}")
        print(f"hibor_a_tier_backfill_plan|rows|{len(result['tasks'])}")
    elif args.command == "run-hibor-a-tier-backfill":
        result = run_hibor_a_tier_backfill(
            tasks_path=args.tasks_path,
            output_dir=args.output_dir,
            config_path=args.config_path,
            download_dir=args.download_dir,
            review_threshold=args.review_threshold,
            max_tasks=args.max_tasks,
            max_detail_attempts=args.max_detail_attempts,
            fallback_tier=args.fallback_tier,
            write_db=args.write_db,
            service=args.service,
            import_pdfs=args.import_pdfs,
            run_pdf_backfill=args.run_pdf_backfill,
            feature_trade_date=args.feature_trade_date,
            retry_attempts=args.retry_attempts,
            retry_sleep_seconds=args.retry_sleep_seconds,
        )
        print(f"hibor_a_tier_backfill|tasks|{result['paths']['tasks']}")
        print(f"hibor_a_tier_backfill|discovered|{result['paths']['discovered']}")
        print(f"hibor_a_tier_backfill|filtered|{result['paths']['filtered']}")
        print(f"hibor_a_tier_backfill|downloads|{result['paths']['downloads']}")
        print(f"hibor_a_tier_backfill|report|{result['paths']['report']}")
        if "import_report" in result["paths"]:
            print(f"hibor_a_tier_backfill|import_report|{result['paths']['import_report']}")
        print(f"hibor_a_tier_backfill|processed_tasks|{result['summary']['processed_tasks']}")
        print(f"hibor_a_tier_backfill|detail_attempts|{result['summary']['detail_attempts']}")
        print(f"hibor_a_tier_backfill|done_tasks|{result['summary']['done_tasks']}")
        print(f"hibor_a_tier_backfill|needs_review_tasks|{result['summary']['needs_review_tasks']}")
        print(f"hibor_a_tier_backfill|downloaded|{result['summary']['downloaded_count']}")
    elif args.command == "run-hibor-ui-download-backfill":
        result = run_hibor_ui_download_backfill(
            tasks_path=args.tasks_path,
            output_dir=args.output_dir,
            download_dir=args.download_dir,
            staging_dir=args.staging_dir,
            max_tasks=args.max_tasks,
            wait_timeout_seconds=args.wait_timeout_seconds,
            poll_seconds=args.poll_seconds,
            open_legacy_search=args.open_legacy_search,
            time_filter=args.time_filter,
            write_db=args.write_db,
            service=args.service,
            import_pdfs=args.import_pdfs,
            run_pdf_backfill=args.run_pdf_backfill,
            feature_trade_date=args.feature_trade_date,
        )
        print(f"hibor_ui_download|tasks|{result['paths']['tasks']}")
        print(f"hibor_ui_download|downloads|{result['paths']['downloads']}")
        print(f"hibor_ui_download|report|{result['paths']['report']}")
        if "import_report" in result["paths"]:
            print(f"hibor_ui_download|import_report|{result['paths']['import_report']}")
        print(f"hibor_ui_download|processed_tasks|{result['summary']['processed_tasks']}")
        print(f"hibor_ui_download|done_tasks|{result['summary']['done_tasks']}")
        print(f"hibor_ui_download|timeout_tasks|{result['summary']['timeout_tasks']}")
        print(f"hibor_ui_download|ui_error_tasks|{result['summary']['ui_error_tasks']}")
        print(f"hibor_ui_download|downloaded|{result['summary']['downloaded_count']}")
    elif args.command == "run-yanbaoke-report-backfill":
        result = run_yanbaoke_report_backfill(
            tasks_path=args.tasks_path,
            output_dir=args.output_dir,
            download_dir=args.download_dir,
            api_key=args.api_key,
            institutions_path=args.institutions_path,
            fallback_tier=args.fallback_tier,
            max_tasks=args.max_tasks,
            max_downloads=args.max_downloads,
            monthly_budget=args.monthly_budget,
            base_budget=args.base_budget,
            top_budget=args.top_budget,
            reserve_budget=args.reserve_budget,
            top_ts_codes=set(args.top_ts_codes or []),
            position_ts_codes=set(args.position_ts_codes or []),
            max_broker_share=args.max_broker_share,
            write_db=args.write_db,
            service=args.service,
            import_pdfs=args.import_pdfs,
            run_pdf_backfill=args.run_pdf_backfill,
            feature_trade_date=args.feature_trade_date,
            industry_structured_detail_path=args.industry_structured_detail_path,
        )
        print(f"yanbaoke_backfill|tasks|{result['paths']['tasks']}")
        print(f"yanbaoke_backfill|discovered|{result['paths']['discovered']}")
        print(f"yanbaoke_backfill|filtered|{result['paths']['filtered']}")
        print(f"yanbaoke_backfill|downloads|{result['paths']['downloads']}")
        print(f"yanbaoke_backfill|report|{result['paths']['report']}")
        if result.get("import") and result["import"].get("paths", {}).get("industry_evidence_seed"):
            print(f"yanbaoke_backfill|industry_evidence_seed|{result['import']['paths']['industry_evidence_seed']}")
        print(f"yanbaoke_backfill|processed_tasks|{result['summary']['processed_tasks']}")
        print(f"yanbaoke_backfill|done_tasks|{result['summary']['done_tasks']}")
        print(f"yanbaoke_backfill|downloaded|{result['summary']['downloaded_count']}")
    elif args.command == "daily-health":
        result = summarize_operational_health(
            trade_date=args.trade_date,
            ingest_datasets=args.ingest_datasets or [],
            backfill_run_ids=args.backfill_run_ids or [],
            stale_minutes=args.stale_minutes,
        )
        lines = format_operational_health_lines(result)
        for line in lines:
            print(line)
        if args.notify_target and result["status"] == "alert":
            send_openclaw_feishu_message(
                message="\n".join(lines),
                target=args.notify_target,
                account=args.notify_account,
                openclaw_bin=args.openclaw_bin,
                dry_run=args.notify_dry_run,
            )
    elif args.command == "export-research-snapshot":
        result = export_research_snapshot(
            start_date=args.start_date,
            end_date=args.end_date,
            score_version=args.score_version,
            output_dir=args.output_dir,
        )
        print(f"research_snapshot|manifest|{result['manifest_path']}")
        for dataset, rows in result["row_counts"].items():
            print(f"research_snapshot_dataset|{dataset}|rows|{rows}|{result['files'][dataset]}")
    elif args.command == "migration-safety-check":
        result = run_backup_restore_check(
            backup_path=args.backup_path,
            source_service=args.source_service,
            restore_service=args.restore_service,
            dry_run=args.dry_run,
        )
        print(f"migration_safety|status|{result['status']}")
        for command in result["commands"]:
            print(f"migration_safety_command|{command}")
        for check in result["checks"]:
            print(f"migration_safety_check|{check['check']}|{check['status']}|{check['detail']}")
    elif args.command == "run-daily-research-report":
        result = run_daily_research_report(
            trade_date=args.trade_date,
            score_version=args.score_version,
            top_n=args.top_n,
            index_id=args.index_id,
            market_lookback_days=args.market_lookback_days,
            industry_system=args.industry_system,
            sector_lookback_days=args.sector_lookback_days,
            positions_csv=args.positions_csv,
            reports_dir=args.reports_dir,
            apply_report_run_schema_first=args.apply_report_run_schema,
            record_run=args.record_run,
        )
        report_paths = result["report_paths"]
        for key in ("bundle", "topn", "market_state", "sector_strength", "risk_alerts", "position_review"):
            print(f"daily_research_report|{key}|{report_paths[key]['markdown_path']}")
    elif args.command == "run-daily-review-v1":
        result = run_daily_review_report(
            trade_date=args.trade_date,
            output_root=args.output_root,
            apply_report_run_schema_first=args.apply_report_run_schema,
            record_run=args.record_run,
        )
        for line in iter_daily_review_report_path_lines(result["report_paths"]):
            print(line)
    elif args.command == "trend-lifecycle-v1":
        result = run_trend_lifecycle_v1_report(
            start_date=args.start_date,
            end_date=args.end_date,
            score_version=args.score_version,
            top_n=args.top_n,
            adjust_type=args.adjust_type,
            reports_dir=args.reports_dir,
        )
        paths = result["paths"]
        print(f"trend_lifecycle_v1|report|{paths['markdown_report']}")
        print(f"trend_lifecycle_v1|trend_segments|{paths['trend_segments']}")
        print(f"trend_lifecycle_v1|lifecycle_samples|{paths['lifecycle_samples']}")
        print(f"trend_lifecycle_v1|entry_success_labels|{paths['entry_success_labels']}")
        print(f"trend_lifecycle_v1|top20_stage_hit_report|{paths['top20_stage_hit_report']}")
        print(f"trend_lifecycle_v1|segments|{len(result['segments'])}")
        print(f"trend_lifecycle_v1|lifecycle_samples_rows|{len(result['lifecycle_samples'])}")
        print(f"trend_lifecycle_v1|entry_success_rows|{len(result['entry_success'])}")
        print(f"trend_lifecycle_v1|top20_stage_hit_rows|{len(result['top20_stage_hits'])}")
        print(f"trend_lifecycle_v1|diagnostics|{len(result['diagnostics'])}")
    elif args.command == "mid-trend-factor-profile":
        result = run_mid_trend_factor_profile_report(
            start_date=args.start_date,
            end_date=args.end_date,
            lifecycle_samples_path=args.lifecycle_samples_path,
            factor_names=args.factor_names,
            period=args.period,
            reports_dir=args.reports_dir,
        )
        paths = result["paths"]
        print(f"mid_trend_factor_profile|report|{paths['markdown_report']}")
        print(f"mid_trend_factor_profile|factor_profile|{paths['factor_profile']}")
        print(f"mid_trend_factor_profile|stage_stability|{paths['stage_stability']}")
        print(f"mid_trend_factor_profile|candidate_rank|{paths['candidate_rank']}")
        print(f"mid_trend_factor_profile|stage_signatures|{paths['stage_signatures']}")
        print(f"mid_trend_factor_profile|profile_rows|{len(result['profile'])}")
        print(f"mid_trend_factor_profile|stability_rows|{len(result['stability'])}")
        print(f"mid_trend_factor_profile|candidate_rows|{len(result['candidate_rank'])}")
        print(f"mid_trend_factor_profile|stage_signature_rows|{len(result['stage_signatures'])}")
        print(f"mid_trend_factor_profile|diagnostics|{len(result['diagnostics'])}")
    elif args.command == "mid-trend-candidate-enrichment":
        result = run_candidate_enrichment_report(
            start_date=args.start_date,
            end_date=args.end_date,
            candidate_rank_path=args.candidate_rank_path,
            entry_success_labels_path=args.entry_success_labels_path,
            max_factors=args.max_factors,
            min_candidate_score=args.min_candidate_score,
            quantiles=args.quantiles,
            top_ns=tuple(args.top_ns),
            period=args.period,
            reports_dir=args.reports_dir,
        )
        paths = result["paths"]
        print(f"mid_trend_candidate_enrichment|report|{paths['markdown_report']}")
        print(f"mid_trend_candidate_enrichment|candidate_scores|{paths['candidate_scores']}")
        print(
            "mid_trend_candidate_enrichment|enrichment_by_quantile|"
            f"{paths['enrichment_by_quantile']}"
        )
        print(f"mid_trend_candidate_enrichment|enrichment_by_topn|{paths['enrichment_by_topn']}")
        print(f"mid_trend_candidate_enrichment|enrichment_by_period|{paths['enrichment_by_period']}")
        print(f"mid_trend_candidate_enrichment|candidate_score_rows|{len(result['candidate_scores'])}")
        print(f"mid_trend_candidate_enrichment|quantile_rows|{len(result['enrichment_by_quantile'])}")
        print(f"mid_trend_candidate_enrichment|topn_rows|{len(result['enrichment_by_topn'])}")
        print(f"mid_trend_candidate_enrichment|period_rows|{len(result['enrichment_by_period'])}")
        print(f"mid_trend_candidate_enrichment|diagnostics|{len(result['diagnostics'])}")
    elif args.command == "mid-trend-full-universe-enrichment":
        result = run_full_universe_candidate_enrichment_report(
            start_date=args.start_date,
            end_date=args.end_date,
            candidate_scores_path=args.candidate_scores_path,
            adjust_type=args.adjust_type,
            quantiles=args.quantiles,
            top_ns=tuple(args.top_ns),
            period=args.period,
            reports_dir=args.reports_dir,
        )
        paths = result["paths"]
        print(f"mid_trend_full_universe_enrichment|report|{paths['markdown_report']}")
        print(f"mid_trend_full_universe_enrichment|candidate_scores|{paths['candidate_scores']}")
        print(
            "mid_trend_full_universe_enrichment|candidate_entry_success_labels|"
            f"{paths['candidate_entry_success_labels']}"
        )
        print(
            "mid_trend_full_universe_enrichment|enrichment_by_quantile|"
            f"{paths['enrichment_by_quantile']}"
        )
        print(
            "mid_trend_full_universe_enrichment|enrichment_by_topn|"
            f"{paths['enrichment_by_topn']}"
        )
        print(
            "mid_trend_full_universe_enrichment|enrichment_by_period|"
            f"{paths['enrichment_by_period']}"
        )
        print(f"mid_trend_full_universe_enrichment|candidate_score_rows|{len(result['candidate_scores'])}")
        print(
            "mid_trend_full_universe_enrichment|entry_success_rows|"
            f"{len(result['candidate_entry_success_labels'])}"
        )
        print(f"mid_trend_full_universe_enrichment|quantile_rows|{len(result['enrichment_by_quantile'])}")
        print(f"mid_trend_full_universe_enrichment|topn_rows|{len(result['enrichment_by_topn'])}")
        print(f"mid_trend_full_universe_enrichment|period_rows|{len(result['enrichment_by_period'])}")
        print(f"mid_trend_full_universe_enrichment|diagnostics|{len(result['diagnostics'])}")
    elif args.command == "entry-success-reverse-profile":
        result = run_entry_success_reverse_profile_report(
            start_date=args.start_date,
            end_date=args.end_date,
            entry_success_labels_path=args.entry_success_labels_path,
            factor_names=args.factor_names,
            horizons=tuple(args.horizons),
            period=args.period,
            reports_dir=args.reports_dir,
        )
        paths = result["paths"]
        print(f"entry_success_reverse_profile|report|{paths['markdown_report']}")
        print(
            "entry_success_reverse_profile|factor_profile|"
            f"{paths['entry_success_factor_profile']}"
        )
        print(
            "entry_success_reverse_profile|factor_rank|"
            f"{paths['entry_success_factor_rank']}"
        )
        print(f"entry_success_reverse_profile|factor_profile_rows|{len(result['factor_profile'])}")
        print(f"entry_success_reverse_profile|factor_rank_rows|{len(result['factor_rank'])}")
        print(f"entry_success_reverse_profile|diagnostics|{len(result['diagnostics'])}")
    elif args.command == "entry-success-candidate-v2":
        result = run_entry_success_candidate_v2_report(
            start_date=args.start_date,
            end_date=args.end_date,
            factor_rank_path=args.factor_rank_path,
            horizon=args.horizon,
            max_factors=args.max_factors,
            min_candidate_score=args.min_candidate_score,
            min_sign_match_rate=args.min_sign_match_rate,
            adjust_type=args.adjust_type,
            quantiles=args.quantiles,
            top_ns=tuple(args.top_ns),
            period=args.period,
            reports_dir=args.reports_dir,
        )
        paths = result["paths"]
        print(f"entry_success_candidate_v2|report|{paths['markdown_report']}")
        print(f"entry_success_candidate_v2|candidate_rank|{paths['candidate_rank']}")
        print(f"entry_success_candidate_v2|candidate_scores|{paths['candidate_scores']}")
        print(
            "entry_success_candidate_v2|candidate_entry_success_labels|"
            f"{paths['candidate_entry_success_labels']}"
        )
        print(
            "entry_success_candidate_v2|enrichment_by_quantile|"
            f"{paths['enrichment_by_quantile']}"
        )
        print(f"entry_success_candidate_v2|enrichment_by_topn|{paths['enrichment_by_topn']}")
        print(f"entry_success_candidate_v2|enrichment_by_period|{paths['enrichment_by_period']}")
        print(f"entry_success_candidate_v2|candidate_rank_rows|{len(result['candidate_rank'])}")
        print(f"entry_success_candidate_v2|candidate_score_rows|{len(result['candidate_scores'])}")
        print(f"entry_success_candidate_v2|entry_success_rows|{len(result['candidate_entry_success_labels'])}")
        print(f"entry_success_candidate_v2|quantile_rows|{len(result['enrichment_by_quantile'])}")
        print(f"entry_success_candidate_v2|topn_rows|{len(result['enrichment_by_topn'])}")
        print(f"entry_success_candidate_v2|period_rows|{len(result['enrichment_by_period'])}")
        print(f"entry_success_candidate_v2|diagnostics|{len(result['diagnostics'])}")
    elif args.command == "trend-candidate-backtest":
        result = run_trend_candidate_backtest_report(
            start_date=args.start_date,
            end_date=args.end_date,
            candidate_scores_path=args.candidate_scores_path,
            top_ns=tuple(args.top_ns),
            holding_days=tuple(args.holding_days),
            transaction_cost_bps=args.transaction_cost_bps,
            adjust_type=args.adjust_type,
            reports_dir=args.reports_dir,
        )
        paths = result["paths"]
        print(f"trend_candidate_backtest|report|{paths['markdown_report']}")
        print(f"trend_candidate_backtest|summary|{paths['summary']}")
        print(f"trend_candidate_backtest|equity_curve|{paths['equity_curve']}")
        print(f"trend_candidate_backtest|positions|{paths['positions']}")
        print(f"trend_candidate_backtest|trades|{paths['trades']}")
        print(f"trend_candidate_backtest|summary_rows|{len(result['summary'])}")
        print(f"trend_candidate_backtest|equity_rows|{len(result['equity_curve'])}")
        print(f"trend_candidate_backtest|position_rows|{len(result['positions'])}")
        print(f"trend_candidate_backtest|trade_rows|{len(result['trades'])}")
        print(f"trend_candidate_backtest|diagnostics|{len(result['diagnostics'])}")
    elif args.command == "industry-focus-backtest":
        result = run_industry_focus_backtest_report(
            start_date=args.start_date,
            end_date=args.end_date,
            top_n=args.top_n,
            dynamic_top_k=args.dynamic_top_k,
            min_industry_stocks=args.min_industry_stocks,
            industry_system=args.industry_system,
            industry_level=args.industry_level,
            adjust_type=args.adjust_type,
            reports_dir=args.reports_dir,
        )
        paths = result["paths"]
        print(f"industry_focus_backtest|report|{paths['markdown_report']}")
        print(f"industry_focus_backtest|summary|{paths['summary']}")
        print(f"industry_focus_backtest|industry_scores|{paths['industry_scores']}")
        print(f"industry_focus_backtest|focus_industries_daily|{paths['focus_industries_daily']}")
        print(f"industry_focus_backtest|summary_rows|{len(result['summary'])}")
    elif args.command in {"industry-v1-attribution", "industry-focus-v2-diagnostics"}:
        result = run_industry_focus_v2_diagnostics(
            start_date=args.start_date,
            end_date=args.end_date,
            min_industry_stocks=args.min_industry_stocks,
            output_dir=args.output_dir,
            industry_system=args.industry_system,
            industry_level=args.industry_level,
            adjust_type=args.adjust_type,
            dynamic_top_k=args.dynamic_top_k,
        )
        paths = result["paths"]
        prefix = "industry_v1_attribution" if args.command == "industry-v1-attribution" else "industry_focus_v2_diagnostics"
        print(f"{prefix}|v1_failure_attribution|{paths['v1_failure_attribution']}")
        print(f"{prefix}|v2_diagnostics|{paths['v2_diagnostics']}")
        print(f"{prefix}|v1_rows|{len(result['v1_failure_attribution'])}")
        print(f"{prefix}|v2_rows|{len(result['v2_diagnostics'])}")
    elif args.command == "industry-focus-v2-backtest":
        result = run_industry_focus_v2_backtest(
            start_date=args.start_date,
            end_date=args.end_date,
            diagnostics_path=args.diagnostics_path,
            top_n=args.top_n,
            transaction_cost_bps=args.transaction_cost_bps,
            output_dir=args.output_dir,
            industry_system=args.industry_system,
            industry_level=args.industry_level,
            adjust_type=args.adjust_type,
        )
        paths = result["paths"]
        print(f"industry_focus_v2_backtest|summary|{paths['summary']}")
        print(f"industry_focus_v2_backtest|annual_metrics|{paths['annual_metrics']}")
        print(f"industry_focus_v2_backtest|monthly_metrics|{paths['monthly_metrics']}")
        print(f"industry_focus_v2_backtest|summary_rows|{len(result['summary'])}")
    elif args.command == "dragon-research-v1":
        result = run_dragon_research_v1(
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
            hot_industry_top_n=args.hot_industry_top_n,
            adjust_type=args.adjust_type,
            industry_system=args.industry_system,
            industry_level=args.industry_level,
            industry_diagnostics_path=args.industry_diagnostics_path,
            candidate_scores_path=args.candidate_scores_path,
            lifecycle_samples_path=args.lifecycle_samples_path,
        )
        paths = result["paths"]
        print(f"dragon_research_v1|diagnostics|{paths['diagnostics']}")
        print(f"dragon_research_v1|monthly_summary|{paths['monthly_summary']}")
        print(f"dragon_research_v1|role_effectiveness|{paths['role_effectiveness']}")
        print(f"dragon_research_v1|yearly_diagnosis|{paths['yearly_diagnosis']}")
        print(f"dragon_research_v1|report|{paths['markdown_report']}")
        print(f"dragon_research_v1|diagnostic_rows|{len(result['diagnostics'])}")
        print(f"dragon_research_v1|role_rows|{len(result['role_effectiveness'])}")
        print(f"dragon_research_v1|yearly_rows|{len(result['yearly_diagnosis'])}")
    elif args.command == "dragon-case-library-build":
        result = run_dragon_case_library_build(
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
            seed_path=args.seed_path,
            adjust_type=args.adjust_type,
        )
        print(f"dragon_case_library_build|case_library|{result['paths']['case_library']}")
        if "auto_candidates" in result.get("paths", {}):
            print(f"dragon_case_library_build|auto_candidates_csv|{result['paths']['auto_candidates']}")
        print(f"dragon_case_library_build|cases|{len(result['case_library'])}")
        print(f"dragon_case_library_build|auto_candidates|{len(result['auto_candidates'])}")
    elif args.command == "dragon-case-library-diagnose":
        result = run_dragon_case_library_diagnose(
            case_path=args.case_path,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
            adjust_type=args.adjust_type,
        )
        print(f"dragon_case_library_diagnose|event_diagnostics|{result['paths']['event_diagnostics']}")
        print(
            "dragon_case_library_diagnose|success_failure_comparison|"
            f"{result['paths']['success_failure_comparison']}"
        )
        print(f"dragon_case_library_diagnose|report|{result['paths']['markdown_report']}")
        print(f"dragon_case_library_diagnose|event_rows|{len(result['event_diagnostics'])}")
        print(f"dragon_case_library_diagnose|warnings|{len(result['warnings'])}")
    elif args.command == "dragon-case-import-web-seeds":
        result = import_web_seeds(args.input, args.output_dir)
        print(f"dragon_case_import_web_seeds|web_candidates|{result['paths']['web_candidates']}")
        print(f"dragon_case_import_web_seeds|rows|{len(result['web_candidates'])}")
    elif args.command == "dragon-case-expand-web-seeds":
        result = run_dragon_case_expand_web_seeds(
            article_seed_path=args.article_seed,
            output_path=args.output,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
        )
        print(f"dragon_case_expand_web_seeds|web_seed|{result['paths']['web_seed']}")
        print(f"dragon_case_expand_web_seeds|summary|{result['paths']['summary']}")
        print(f"dragon_case_expand_web_seeds|unmatched|{result['paths']['unmatched']}")
        print(f"dragon_case_expand_web_seeds|coverage|{result['paths']['coverage']}")
        print(f"dragon_case_expand_web_seeds|report|{result['paths']['report']}")
        print(f"dragon_case_expand_web_seeds|matched|{len(result['web_seed'])}")
        print(f"dragon_case_expand_web_seeds|unmatched_rows|{len(result['unmatched'])}")
    elif args.command == "dragon-case-web-verify":
        result = run_dragon_case_web_verify(
            candidate_path=args.candidate_path,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
            adjust_type=args.adjust_type,
        )
        print(f"dragon_case_web_verify|event_verification|{result['paths']['event_verification']}")
        print(f"dragon_case_web_verify|factor_review|{result['paths']['factor_review']}")
        print(f"dragon_case_web_verify|curated_library|{result['paths']['curated_library']}")
        print(f"dragon_case_web_verify|source_evidence|{result['paths']['source_evidence']}")
        print(f"dragon_case_web_verify|report|{result['paths']['markdown_report']}")
        print(f"dragon_case_web_verify|web_candidates|{len(result['web_candidates'])}")
        print(f"dragon_case_web_verify|verified|{len(result['verified'])}")
        print(f"dragon_case_web_verify|curated|{len(result['curated'])}")
    elif args.command == "dragon-case-apply-source-backfill":
        result = apply_source_backfill(
            tasks_path=args.tasks_path,
            article_seed_path=args.article_seed,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
        )
        print(f"dragon_case_apply_source_backfill|summary|{result['paths']['summary']}")
        print(f"dragon_case_apply_source_backfill|errors|{result['paths']['errors']}")
        print(f"dragon_case_apply_source_backfill|report|{result['paths']['report']}")
        print(f"dragon_case_apply_source_backfill|article_seed|{result['paths']['article_seed']}")
        print(f"dragon_case_apply_source_backfill|inserted|{int(result['summary'].iloc[0]['inserted_article_seed_rows'])}")
        print(f"dragon_case_apply_source_backfill|skipped_duplicate|{int(result['summary'].iloc[0]['skipped_duplicate_rows'])}")
        print(f"dragon_case_apply_source_backfill|dry_run|{args.dry_run}")
    elif args.command == "dragon-case-source-backfill-compare":
        result = compare_source_backfill_curated(
            before_curated_path=args.before_curated,
            after_curated_path=args.after_curated,
            output_dir=args.output_dir,
        )
        print(f"dragon_case_source_backfill_compare|delta|{result['paths']['delta']}")
        print(f"dragon_case_source_backfill_compare|warnings|{len(result['warnings'])}")
    elif args.command == "dragon-case-source-backfill-workpack":

        tasks = pd.read_csv(args.tasks_path, low_memory=False)
        result = build_source_backfill_workpack(tasks, top_n=args.top_n, output_dir=args.output_dir)
        print(f"dragon_case_source_backfill_workpack|csv|{result['paths']['csv']}")
        print(f"dragon_case_source_backfill_workpack|markdown|{result['paths']['markdown']}")
        print(f"dragon_case_source_backfill_workpack|next_commands|{result['paths']['next_commands']}")
        print(f"dragon_case_source_backfill_workpack|rows|{len(result['workpack'])}")
    elif args.command == "dragon-case-source-backfill-check":

        apply_summary = pd.read_csv(args.apply_summary, low_memory=False)
        delta_summary = pd.read_csv(args.delta_summary, low_memory=False)
        curated = pd.read_csv(args.curated, low_memory=False)
        report = build_source_backfill_check_report(apply_summary, delta_summary, curated)
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        report_path = out / "dragon_case_source_backfill_check_report.md"
        report_path.write_text(report, encoding="utf-8")
        print(f"dragon_case_source_backfill_check|report|{report_path}")
    elif args.command == "dragon-case-failure-event-rules-v2":
        result = run_failure_event_rule_v2_diagnostics(
            case_path=args.case_path,
            snapshot_path=args.snapshot_path,
            output_dir=args.output_dir,
        )
        print(f"failure_event_rule_v2|audit|{result['paths']['audit']}")
        print(f"failure_event_rule_v2|summary|{result['paths']['summary']}")
        print(f"failure_event_rule_v2|report|{result['paths']['report']}")
        print(f"failure_event_rule_v2|audit_rows|{len(result['audit'])}")
    elif args.command == "validate-technical-methods":
        result = run_validate_technical_methods(
            start_date=args.start_date,
            end_date=args.end_date,
            adjust_type=args.adjust_type,
            sample_size=args.sample_size,
            asset_id=args.asset_id,
            ts_code=args.ts_code,
            feature_source=args.feature_source,
            output_dir=args.output_dir,
        )
        print(f"technical_method_validation|feature_bucket_effectiveness|{result['paths']['feature_bucket_effectiveness']}")
        print(f"technical_method_validation|combo_effectiveness|{result['paths']['combo_effectiveness']}")
        print(f"technical_method_validation|regime_effectiveness|{result['paths']['regime_effectiveness']}")
        print(f"technical_method_validation|case_event_effectiveness|{result['paths']['case_event_effectiveness']}")
        print(f"technical_method_validation|lhb_cross_effectiveness|{result['paths']['lhb_cross_effectiveness']}")
        print(f"technical_method_validation|feature_correlation|{result['paths']['feature_correlation']}")
        print(f"technical_method_validation|redundancy_report|{result['paths']['redundancy_report']}")
        print(f"technical_method_validation|recommendation|{result['paths']['recommendation']}")
        print(f"technical_method_validation|report|{result['paths']['report']}")
        print(f"technical_method_validation|rows|{len(result['dataset'])}")
    elif args.command == "validate-alpha191-pilot":
        result = run_validate_alpha191_pilot(
            start_date=args.start_date,
            end_date=args.end_date,
            adjust_type=args.adjust_type,
            sample_size=args.sample_size,
            asset_id=args.asset_id,
            ts_code=args.ts_code,
            strong_start_date=args.strong_start_date,
            strong_end_date=args.strong_end_date,
            output_dir=args.output_dir,
        )
        print(f"alpha191_pilot_validation|factor_effectiveness|{result['paths']['factor_effectiveness']}")
        print(f"alpha191_pilot_validation|strong_winner_explanation|{result['paths']['strong_winner_explanation']}")
        print(f"alpha191_pilot_validation|trend_overlay|{result['paths']['trend_overlay']}")
        print(f"alpha191_pilot_validation|high_volatility_risk_split|{result['paths']['high_volatility_risk_split']}")
        print(f"alpha191_pilot_validation|recommendation|{result['paths']['recommendation']}")
        print(f"alpha191_pilot_validation|report|{result['paths']['report']}")
        print(f"alpha191_pilot_validation|rows|{len(result['dataset'])}")
    elif args.command == "validate-alpha191-expanded":
        result = run_validate_alpha191_expanded(
            start_date=args.start_date,
            end_date=args.end_date,
            adjust_type=args.adjust_type,
            sample_size=args.sample_size,
            asset_id=args.asset_id,
            ts_code=args.ts_code,
            strong_start_date=args.strong_start_date,
            strong_end_date=args.strong_end_date,
            output_dir=args.output_dir,
        )
        print(f"alpha191_expanded_validation|factor_effectiveness|{result['paths']['factor_effectiveness']}")
        print(f"alpha191_expanded_validation|factor_bucket_effectiveness|{result['paths']['factor_bucket_effectiveness']}")
        print(f"alpha191_expanded_validation|strong_winner_explanation|{result['paths']['strong_winner_explanation']}")
        print(f"alpha191_expanded_validation|drawdown_risk_effectiveness|{result['paths']['drawdown_risk_effectiveness']}")
        print(f"alpha191_expanded_validation|redundancy_report|{result['paths']['redundancy_report']}")
        print(f"alpha191_expanded_validation|candidate_factors|{result['paths']['candidate_factors']}")
        print(f"alpha191_expanded_validation|trend_overlay|{result['paths']['trend_overlay']}")
        print(f"alpha191_expanded_validation|high_volatility_risk_split|{result['paths']['high_volatility_risk_split']}")
        print(f"alpha191_expanded_validation|report|{result['paths']['report']}")
        print(f"alpha191_expanded_validation|rows|{len(result['dataset'])}")
    elif args.command == "technical-feature-promotion-audit":
        result = run_technical_feature_promotion_audit(
            start_date=args.start_date,
            end_date=args.end_date,
            adjust_type=args.adjust_type,
            sample_size=args.sample_size,
            asset_id=args.asset_id,
            ts_code=args.ts_code,
            feature_source=args.feature_source,
            output_dir=args.output_dir,
        )
        print(f"technical_feature_promotion_audit|audit|{result['paths']['promotion_audit']}")
        print(f"technical_feature_promotion_audit|watchlist|{result['paths']['watchlist_readiness']}")
        print(f"technical_feature_promotion_audit|report|{result['paths']['report']}")
        print(f"technical_feature_promotion_audit|rows|{len(result['promotion_audit'])}")
    elif args.command == "lhb-risk-diagnostics-after-failure-rule-v2-1":
        result = run_lhb_diagnostics_after_failure_rule_v21(
            case_path=args.case_path,
            failure_audit_path=args.failure_audit_path,
            snapshot_path=args.snapshot_path,
            lhb_features_path=args.lhb_features_path,
            alignment_path=args.alignment_path,
            output_dir=args.output_dir,
        )
        print(f"lhb_after_failure_rule_v2_1|curated_failure_v21|{result['paths']['curated_failure_v21']}")
        print(f"lhb_after_failure_rule_v2_1|transition_matrix|{result['paths']['transition_matrix']}")
        print(f"lhb_after_failure_rule_v2_1|case_type_difference_summary|{result['paths']['case_type_difference_summary']}")
        print(f"lhb_after_failure_rule_v2_1|risk_feature_case_detail|{result['paths']['risk_feature_case_detail']}")
        print(f"lhb_after_failure_rule_v2_1|comparison|{result['paths']['comparison']}")
        print(f"lhb_after_failure_rule_v2_1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-sample-import":
        ts_codes = parse_str_list(args.ts_codes, "--ts-codes") if args.ts_codes else None
        result = run_lhb_sample_import(
            start_date=args.start_date,
            end_date=args.end_date,
            ts_codes=ts_codes,
            output_dir=args.output_dir,
            provider=args.provider,
        )
        print(f"lhb_sample_import|top_list|{result['paths']['top_list']}")
        print(f"lhb_sample_import|top_inst|{result['paths']['top_inst']}")
        print(f"lhb_sample_import|top_list_rows|{len(result['top_list'])}")
        print(f"lhb_sample_import|top_inst_rows|{len(result['top_inst'])}")
    elif args.command == "lhb-build-event-features":
        ts_codes = parse_str_list(args.ts_codes, "--ts-codes") if args.ts_codes else None
        result = run_lhb_event_features_build(
            start_date=args.start_date,
            end_date=args.end_date,
            ts_codes=ts_codes,
            output_dir=args.output_dir,
        )
        print(f"lhb_event_features_build|lhb_event_features|{result['paths']['lhb_event_features']}")
        print(f"lhb_event_features_build|rows|{len(result['lhb_event_features'])}")
    elif args.command == "dragon-case-lhb-alignment-audit":
        result = run_dragon_case_lhb_alignment_audit(
            curated_path=args.curated_path,
            output_dir=args.output_dir,
        )
        print(f"dragon_case_lhb_alignment_audit|alignment_audit|{result['paths']['alignment_audit']}")
        print(f"dragon_case_lhb_alignment_audit|rows|{len(result['alignment_audit'])}")
        print(f"dragon_case_lhb_alignment_audit|warnings|{len(result['warnings'])}")
    elif args.command == "dragon-case-lhb-summary":
        result = run_dragon_case_lhb_summary_report(
            curated_path=args.curated_path,
            output_dir=args.output_dir,
        )
        print(f"dragon_case_lhb_summary|summary|{result['paths']['summary']}")
        print(f"dragon_case_lhb_summary|comparison|{result['paths']['comparison']}")
        print(f"dragon_case_lhb_summary|report|{result['paths']['markdown_report']}")
        print(f"dragon_case_lhb_summary|rows|{len(result['summary'])}")
    elif args.command == "lhb-case-difference-report":
        result = run_lhb_case_difference_report(
            case_path=args.case_path,
            lhb_features_path=args.lhb_features_path,
            alignment_path=args.alignment_path,
            output_dir=args.output_dir,
        )
        print(f"lhb_case_difference_report|case_type_difference_summary|{result['paths']['case_type_difference_summary']}")
        print(f"lhb_case_difference_report|event_window_difference|{result['paths']['event_window_difference']}")
        print(f"lhb_case_difference_report|risk_signal_effectiveness|{result['paths']['risk_signal_effectiveness']}")
        print(f"lhb_case_difference_report|positive_signal_effectiveness|{result['paths']['positive_signal_effectiveness']}")
        print(f"lhb_case_difference_report|case_event_detail|{result['paths']['case_event_detail']}")
        print(f"lhb_case_difference_report|coverage_summary|{result['paths']['coverage_summary']}")
        print(f"lhb_case_difference_report|report|{result['paths']['markdown_report']}")
        print(f"lhb_case_difference_report|warnings|{len(result['warnings'])}")
    elif args.command == "lhb-risk-feature-diagnostics":
        result = run_lhb_risk_feature_diagnostics(
            case_path=args.case_path,
            lhb_features_path=args.lhb_features_path,
            alignment_path=args.alignment_path,
            output_dir=args.output_dir,
        )
        print(f"lhb_risk_feature_diagnostics|risk_feature_case_detail|{result['paths']['risk_feature_case_detail']}")
        print(f"lhb_risk_feature_diagnostics|risk_score_bucket_effectiveness|{result['paths']['risk_score_bucket_effectiveness']}")
        print(f"lhb_risk_feature_diagnostics|risk_failure_type_cross|{result['paths']['risk_failure_type_cross']}")
        print(f"lhb_risk_feature_diagnostics|dragon_risk_cross_diagnostics|{result['paths']['dragon_risk_cross_diagnostics']}")
        print(f"lhb_risk_feature_diagnostics|coverage_gap_recommendations|{result['paths']['coverage_gap_recommendations']}")
        print(f"lhb_risk_feature_diagnostics|report|{result['paths']['markdown_report']}")
        print(f"lhb_risk_feature_diagnostics|warnings|{len(result['warnings'])}")
    elif args.command == "lhb-follow-exit-replay-v1":
        result = run_lhb_follow_exit_replay_v1(
            case_path=args.case_path,
            lhb_features_path=args.lhb_features_path,
            alignment_path=args.alignment_path,
            output_dir=args.output_dir,
        )
        print(f"lhb_follow_exit_replay_v1|replay_detail|{result['paths']['replay_detail']}")
        print(f"lhb_follow_exit_replay_v1|replay_effectiveness|{result['paths']['replay_effectiveness']}")
        print(f"lhb_follow_exit_replay_v1|report|{result['paths']['markdown_report']}")
        print(f"lhb_follow_exit_replay_v1|warnings|{len(result['warnings'])}")
    elif args.command == "lhb-shortline-event-replay-v1":
        result = run_lhb_shortline_event_replay_v1(
            case_path=args.case_path,
            lhb_features_path=args.lhb_features_path,
            alignment_path=args.alignment_path,
            output_dir=args.output_dir,
            market_path=args.market_path,
        )
        print(f"lhb_shortline_event_replay_v1|event_replay|{result['paths']['event_replay']}")
        print(f"lhb_shortline_event_replay_v1|report|{result['paths']['markdown_report']}")
        print(f"lhb_shortline_event_replay_v1|warnings|{len(result['warnings'])}")
    elif args.command == "lhb-follow-avoid-rule-audit-v1":
        result = run_lhb_follow_avoid_rule_audit_v1(
            event_replay_path=args.event_replay_path,
            output_dir=args.output_dir,
        )
        print(f"lhb_follow_avoid_rule_audit_v1|action_effectiveness|{result['paths']['action_effectiveness']}")
        print(f"lhb_follow_avoid_rule_audit_v1|rule_matrix|{result['paths']['rule_matrix']}")
        print(f"lhb_follow_avoid_rule_audit_v1|rule_recommendations|{result['paths']['rule_recommendations']}")
        print(f"lhb_follow_avoid_rule_audit_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-exit-rule-audit-v1":
        result = run_lhb_exit_rule_audit_v1(
            event_replay_path=args.event_replay_path,
            output_dir=args.output_dir,
        )
        print(f"lhb_exit_rule_audit_v1|exit_signal_effectiveness|{result['paths']['exit_signal_effectiveness']}")
        print(f"lhb_exit_rule_audit_v1|exit_reason_effectiveness|{result['paths']['exit_reason_effectiveness']}")
        print(f"lhb_exit_rule_audit_v1|false_positive_audit|{result['paths']['false_positive_audit']}")
        print(f"lhb_exit_rule_audit_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "daily-lhb-shortline-watchlist-v1":
        result = run_daily_lhb_shortline_watchlist_v1(
            event_replay_path=args.event_replay_path,
            rule_recommendations_path=args.rule_recommendations_path,
            rule_registry_path=args.rule_registry_path,
            trade_date=args.trade_date,
            output_dir=args.output_dir,
        )
        print(f"daily_lhb_shortline_watchlist_v1|watchlist|{result['paths']['watchlist']}")
        print(f"daily_lhb_shortline_watchlist_v1|report|{result['paths']['markdown_report']}")
        print(f"daily_lhb_shortline_watchlist_v1|rows|{len(result['watchlist'])}")
    elif args.command == "lhb-shortline-strategy-effectiveness-v1":
        result = run_lhb_shortline_strategy_effectiveness_v1(
            event_replay_path=args.event_replay_path,
            daily_watchlist_path=args.daily_watchlist_path,
            min_sample_count=args.min_sample_count,
            output_dir=args.output_dir,
        )
        print(f"lhb_shortline_strategy_effectiveness_v1|detail|{result['paths']['detail']}")
        print(f"lhb_shortline_strategy_effectiveness_v1|summary|{result['paths']['summary']}")
        print(
            "lhb_shortline_strategy_effectiveness_v1|follow_combo|"
            f"{result['paths']['follow_combo_effectiveness']}"
        )
        print(
            "lhb_shortline_strategy_effectiveness_v1|exit_combo|"
            f"{result['paths']['exit_combo_effectiveness']}"
        )
        print(f"lhb_shortline_strategy_effectiveness_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-shortline-rule-calibration-v1":
        result = run_lhb_shortline_rule_calibration_v1(
            follow_combo_path=args.follow_combo_path,
            exit_combo_path=args.exit_combo_path,
            rule_version=args.rule_version,
            min_sample_count=args.min_sample_count,
            output_dir=args.output_dir,
        )
        print(f"lhb_shortline_rule_calibration_v1|rule_registry|{result['paths']['rule_registry']}")
        print(f"lhb_shortline_rule_calibration_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-shortline-shadow-backtest-v1":
        top_n_values = [int(value.strip()) for value in str(args.top_n).split(",") if value.strip()]
        result = run_lhb_shortline_shadow_backtest_v1(
            event_replay_path=args.event_replay_path,
            start_date=args.start_date,
            end_date=args.end_date,
            top_n_values=top_n_values,
            pool_mode=args.pool_mode,
            output_dir=args.output_dir,
        )
        print(f"lhb_shortline_shadow_backtest_v1|summary|{result['paths']['summary']}")
        print(f"lhb_shortline_shadow_backtest_v1|selected_trades|{result['paths']['selected_trades']}")
        print(f"lhb_shortline_shadow_backtest_v1|daily_curve|{result['paths']['daily_curve']}")
        print(f"lhb_shortline_shadow_backtest_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-shortline-intraday-confirmation-v1":
        result = run_lhb_shortline_intraday_confirmation_v1(
            candidate_path=args.candidate_path,
            minute_bars_path=args.minute_bars_path,
            freq=args.freq,
            adjust_type=args.adjust_type,
            output_dir=args.output_dir,
        )
        print(f"lhb_shortline_intraday_confirmation_v1|detail|{result['paths']['detail']}")
        print(f"lhb_shortline_intraday_confirmation_v1|summary|{result['paths']['summary']}")
        print(f"lhb_shortline_intraday_confirmation_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-full-market-pool-backtest-v1":
        top_n_values = [int(value.strip()) for value in str(args.top_n).split(",") if value.strip()]
        result = run_lhb_full_market_pool_backtest_v1(
            lhb_features_path=args.lhb_features_path,
            daily_bars_path=args.daily_bars_path,
            start_date=args.start_date,
            end_date=args.end_date,
            top_n_values=top_n_values,
            pool_mode=args.pool_mode,
            output_dir=args.output_dir,
        )
        print(f"lhb_full_market_pool_backtest_v1|summary|{result['paths']['summary']}")
        print(f"lhb_full_market_pool_backtest_v1|selected_trades|{result['paths']['selected_trades']}")
        print(f"lhb_full_market_pool_backtest_v1|daily_curve|{result['paths']['daily_curve']}")
        print(f"lhb_full_market_pool_backtest_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-intraday-filtered-topn-comparison-v1":
        result = run_lhb_intraday_filtered_topn_comparison_v1(
            selected_trades_path=args.selected_trades_path,
            intraday_detail_path=args.intraday_detail_path,
            output_dir=args.output_dir,
        )
        print(f"lhb_intraday_filtered_topn_comparison_v1|comparison|{result['paths']['comparison']}")
        print(
            "lhb_intraday_filtered_topn_comparison_v1|action_effectiveness|"
            f"{result['paths']['action_effectiveness']}"
        )
        print(f"lhb_intraday_filtered_topn_comparison_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-phase12a-multi-context-decision-v1":
        result = run_lhb_phase12a_multi_context_decision_v1(
            selected_trades_path=args.selected_trades_path,
            minute_bars_path=args.minute_bars_path,
            intraday_detail_path=args.intraday_detail_path,
            pre_context_days=args.pre_context_days,
            output_dir=args.output_dir,
        )
        print(f"lhb_phase12a_multi_context_decision_v1|decision|{result['paths']['decision']}")
        print(f"lhb_phase12a_multi_context_decision_v1|summary|{result['paths']['summary']}")
        print(f"lhb_phase12a_multi_context_decision_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-phase12a-rule-decision-v1":
        result = run_lhb_phase12a_rule_decision_v1(
            phase12a_decision_path=args.phase12a_decision_path,
            output_dir=args.output_dir,
        )
        print(f"lhb_phase12a_rule_decision_v1|rule_decision|{result['paths']['rule_decision']}")
        print(f"lhb_phase12a_rule_decision_v1|summary|{result['paths']['summary']}")
        print(f"lhb_phase12a_rule_decision_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-phase12a-real-entry-backtest-v1":
        result = run_lhb_phase12a_real_entry_backtest_v1(
            rule_decision_path=args.rule_decision_path,
            minute_bars_path=args.minute_bars_path,
            daily_bars_path=args.daily_bars_path,
            entry_start_time=args.entry_start_time,
            slippage_bps=args.slippage_bps,
            output_dir=args.output_dir,
        )
        print(f"lhb_phase12a_real_entry_backtest_v1|trades|{result['paths']['trades']}")
        print(f"lhb_phase12a_real_entry_backtest_v1|summary|{result['paths']['summary']}")
        print(f"lhb_phase12a_real_entry_backtest_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-phase12b-signal-exit-v1":
        result = run_lhb_phase12b_signal_exit_v1(
            entry_trades_path=args.entry_trades_path,
            minute_bars_path=args.minute_bars_path,
            max_hold_days=args.max_hold_days,
            output_dir=args.output_dir,
        )
        print(f"lhb_phase12b_signal_exit_v1|exit_trades|{result['paths']['exit_trades']}")
        print(f"lhb_phase12b_signal_exit_v1|summary|{result['paths']['summary']}")
        print(f"lhb_phase12b_signal_exit_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-phase13-two-stage-follow-pool-v1":
        result = run_lhb_phase13_two_stage_follow_pool_v1(
            event_features_path=args.event_features_path,
            t1_features_path=args.t1_features_path,
            output_dir=args.output_dir,
        )
        print(f"lhb_phase13_two_stage_follow_pool_v1|observe_pool|{result['paths']['observe_pool']}")
        print(f"lhb_phase13_two_stage_follow_pool_v1|follow_pool|{result['paths']['follow_pool']}")
        print(f"lhb_phase13_two_stage_follow_pool_v1|reject_pool|{result['paths']['reject_pool']}")
        print(f"lhb_phase13_two_stage_follow_pool_v1|summary|{result['paths']['summary']}")
        print(f"lhb_phase13_two_stage_follow_pool_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-phase13b-topn-filter-v1":
        result = run_lhb_phase13b_topn_filter_v1(
            phase13_decision_path=args.phase13_decision_path,
            top_n=args.top_n,
            output_dir=args.output_dir,
        )
        print(f"lhb_phase13b_topn_filter_v1|scored|{result['paths']['scored']}")
        print(f"lhb_phase13b_topn_filter_v1|selected|{result['paths']['selected']}")
        print(f"lhb_phase13b_topn_filter_v1|summary|{result['paths']['summary']}")
        print(f"lhb_phase13b_topn_filter_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-phase14-lifecycle-exit-v1":
        result = run_lhb_phase14_lifecycle_exit_v1(
            entry_trades_path=args.entry_trades_path,
            minute_bars_path=args.minute_bars_path,
            max_hold_days=args.max_hold_days,
            output_dir=args.output_dir,
        )
        print(f"lhb_phase14_lifecycle_exit_v1|lifecycle_trades|{result['paths']['lifecycle_trades']}")
        print(f"lhb_phase14_lifecycle_exit_v1|summary|{result['paths']['summary']}")
        print(f"lhb_phase14_lifecycle_exit_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-phase14b-threshold-scan-v1":
        result = run_lhb_phase14b_threshold_scan_v1(
            entry_trades_path=args.entry_trades_path,
            minute_bars_path=args.minute_bars_path,
            max_hold_days=args.max_hold_days,
            output_dir=args.output_dir,
        )
        print(f"lhb_phase14b_threshold_scan_v1|profile_ranking|{result['paths']['profile_ranking']}")
        print(f"lhb_phase14b_threshold_scan_v1|threshold_summary|{result['paths']['threshold_summary']}")
        print(f"lhb_phase14b_threshold_scan_v1|best_lifecycle_trades|{result['paths']['best_lifecycle_trades']}")
        print(f"lhb_phase14b_threshold_scan_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-phase14c-lifecycle-portfolio-v1":
        result = run_lhb_phase14c_lifecycle_portfolio_v1(
            entry_trades_path=args.entry_trades_path,
            minute_bars_path=args.minute_bars_path,
            max_hold_days=args.max_hold_days,
            threshold_profile=args.threshold_profile,
            output_dir=args.output_dir,
        )
        print(f"lhb_phase14c_lifecycle_portfolio_v1|lifecycle_trades|{result['paths']['lifecycle_trades']}")
        print(f"lhb_phase14c_lifecycle_portfolio_v1|daily_curve|{result['paths']['daily_curve']}")
        print(f"lhb_phase14c_lifecycle_portfolio_v1|summary|{result['paths']['summary']}")
        print(f"lhb_phase14c_lifecycle_portfolio_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-phase14e-limit-lock-filter-v1":
        result = run_lhb_phase14e_limit_lock_filter_v1(
            entry_trades_path=args.entry_trades_path,
            lifecycle_trades_path=args.lifecycle_trades_path,
            output_dir=args.output_dir,
        )
        print(f"lhb_phase14e_limit_lock_filter_v1|risk_audit|{result['paths']['risk_audit']}")
        print(f"lhb_phase14e_limit_lock_filter_v1|filter_ranking|{result['paths']['filter_ranking']}")
        print(f"lhb_phase14e_limit_lock_filter_v1|best_trades|{result['paths']['best_trades']}")
        print(f"lhb_phase14e_limit_lock_filter_v1|best_curve|{result['paths']['best_curve']}")
        print(f"lhb_phase14e_limit_lock_filter_v1|best_summary|{result['paths']['best_summary']}")
        print(f"lhb_phase14e_limit_lock_filter_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-phase15-cash-account-backtest-v1":
        phase15_kwargs = {
            "lifecycle_trades_path": args.lifecycle_trades_path,
            "max_positions": args.max_positions,
            "position_pct": args.position_pct,
            "output_dir": args.output_dir,
        }
        if args.cutoff_start_date or args.cutoff_end_date or args.strict_cutoff_audit or args.allow_phase14e_best:
            phase15_kwargs.update(
                {
                    "cutoff_start_date": args.cutoff_start_date,
                    "cutoff_end_date": args.cutoff_end_date,
                    "strict_cutoff_audit": args.strict_cutoff_audit,
                    "allow_phase14e_best": args.allow_phase14e_best,
                }
            )
        result = run_lhb_phase15_cash_account_backtest_v1(**phase15_kwargs)
        print(f"lhb_phase15_cash_account_backtest_v1|account_trades|{result['paths']['account_trades']}")
        print(f"lhb_phase15_cash_account_backtest_v1|account_curve|{result['paths']['account_curve']}")
        print(f"lhb_phase15_cash_account_backtest_v1|summary|{result['paths']['summary']}")
        print(f"lhb_phase15_cash_account_backtest_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-cutoff-audit-v1":
        result = run_lhb_cutoff_audit_v1(
            paths=args.path,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
            strict=not args.no_strict,
            forbid_phase14e_best=not args.allow_phase14e_best,
        )
        print(f"lhb_cutoff_audit_v1|status|{result['status']}")
        print(f"lhb_cutoff_audit_v1|audit|{result['paths']['audit']}")
        print(f"lhb_cutoff_audit_v1|summary|{result['paths']['summary']}")
        print(f"lhb_cutoff_audit_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-phase16-quality-improvement-diagnostics-v1":
        result = run_lhb_phase16_quality_improvement_diagnostics_v1(
            lifecycle_trades_path=args.lifecycle_trades_path,
            real_entry_trades_path=args.real_entry_trades_path,
            selected_trades_path=args.selected_trades_path,
            min_group_count=args.min_group_count,
            output_dir=args.output_dir,
        )
        print(f"lhb_phase16_quality_improvement_diagnostics_v1|low_quality_buy_diagnostics|{result['paths']['low_quality_buy_diagnostics']}")
        print(f"lhb_phase16_quality_improvement_diagnostics_v1|exit_mistake_diagnostics|{result['paths']['exit_mistake_diagnostics']}")
        print(f"lhb_phase16_quality_improvement_diagnostics_v1|filter_scan|{result['paths']['filter_scan']}")
        print(f"lhb_phase16_quality_improvement_diagnostics_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-phase16b-limit-break-failed-exit-replay-v1":
        result = run_lhb_phase16b_limit_break_failed_exit_replay_v1(
            lifecycle_trades_path=args.lifecycle_trades_path,
            real_entry_trades_path=args.real_entry_trades_path,
            selected_trades_path=args.selected_trades_path,
            output_dir=args.output_dir,
        )
        print(f"lhb_phase16b_limit_break_failed_exit_replay_v1|opportunity_trades|{result['paths']['opportunity_trades']}")
        print(f"lhb_phase16b_limit_break_failed_exit_replay_v1|strategy_summary|{result['paths']['strategy_summary']}")
        print(f"lhb_phase16b_limit_break_failed_exit_replay_v1|candidate_summary|{result['paths']['candidate_summary']}")
        print(f"lhb_phase16b_limit_break_failed_exit_replay_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-phase16c-limit-break-failed-rule-scan-v1":
        result = run_lhb_phase16c_limit_break_failed_rule_scan_v1(
            lifecycle_trades_path=args.lifecycle_trades_path,
            real_entry_trades_path=args.real_entry_trades_path,
            selected_trades_path=args.selected_trades_path,
            output_dir=args.output_dir,
        )
        print(f"lhb_phase16c_limit_break_failed_rule_scan_v1|adjusted_trades|{result['paths']['adjusted_trades']}")
        print(f"lhb_phase16c_limit_break_failed_rule_scan_v1|rule_scan_summary|{result['paths']['rule_scan_summary']}")
        print(f"lhb_phase16c_limit_break_failed_rule_scan_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-phase16d-limit-break-failed-indicator-discovery-v1":
        result = run_lhb_phase16d_limit_break_failed_indicator_discovery_v1(
            lifecycle_trades_path=args.lifecycle_trades_path,
            real_entry_trades_path=args.real_entry_trades_path,
            selected_trades_path=args.selected_trades_path,
            minute_bars_path=args.minute_bars_path,
            output_dir=args.output_dir,
        )
        print(f"lhb_phase16d_limit_break_failed_indicator_discovery_v1|indicator_detail|{result['paths']['indicator_detail']}")
        print(f"lhb_phase16d_limit_break_failed_indicator_discovery_v1|indicator_summary|{result['paths']['indicator_summary']}")
        print(f"lhb_phase16d_limit_break_failed_indicator_discovery_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-phase16e-limit-break-failed-indicator-rule-scan-v1":
        result = run_lhb_phase16e_limit_break_failed_indicator_rule_scan_v1(
            lifecycle_trades_path=args.lifecycle_trades_path,
            real_entry_trades_path=args.real_entry_trades_path,
            selected_trades_path=args.selected_trades_path,
            minute_bars_path=args.minute_bars_path,
            output_dir=args.output_dir,
        )
        print(f"lhb_phase16e_limit_break_failed_indicator_rule_scan_v1|adjusted_trades|{result['paths']['adjusted_trades']}")
        print(f"lhb_phase16e_limit_break_failed_indicator_rule_scan_v1|rule_scan_summary|{result['paths']['rule_scan_summary']}")
        print(f"lhb_phase16e_limit_break_failed_indicator_rule_scan_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "run-lhb-shortline-daily-v1":
        result = run_lhb_shortline_daily_pipeline_v1(
            case_path=args.case_path,
            lhb_features_path=args.lhb_features_path,
            alignment_path=args.alignment_path,
            market_path=args.market_path,
            trade_date=args.trade_date,
            rule_version=args.rule_version,
            min_sample_count=args.min_sample_count,
            output_dir=args.output_dir,
        )
        print(f"lhb_shortline_daily_v1|event_replay|{result['paths']['event_replay']}")
        print(f"lhb_shortline_daily_v1|daily_watchlist|{result['paths']['daily_watchlist']}")
        print(f"lhb_shortline_daily_v1|rule_registry|{result['paths']['rule_registry']}")
        print(f"lhb_shortline_daily_v1|effectiveness_report|{result['paths']['effectiveness_report']}")
        print(f"lhb_shortline_daily_v1|run_summary|{result['paths']['run_summary']}")
        print(f"lhb_shortline_daily_v1|daily_watchlist_rows|{result['summary']['daily_watchlist_rows']}")
        if args.build_watchlist_diagnostics:
            diagnostics = build_watchlist_diagnostics_snapshot(
                trade_date=args.trade_date,
                score_version=args.score_version,
                top_n=args.top_n,
                risk_watch_n=args.risk_watch_n,
                opportunity_watch_n=args.opportunity_watch_n,
                lhb_shortline_path=result["paths"]["daily_watchlist"],
            )
            report_paths = write_watchlist_diagnostics_report(
                full_rows=diagnostics["full"],
                must_watch_rows=diagnostics["must_watch"],
                output_dir=args.output_dir,
                output_version="v1",
                trade_date=args.trade_date,
                watchlist_id="diagnostics",
            )
            stored = _store_watchlist_diagnostics_signals(diagnostics["full"])
            _append_lhb_daily_watchlist_diagnostics_summary(
                summary_path=result["paths"]["run_summary"],
                report_paths=report_paths,
            )
            print(f"lhb_shortline_daily_v1|watchlist_diagnostics|{report_paths['full_csv_path']}")
            print(f"lhb_shortline_daily_v1|watchlist_diagnostics_must_watch|{report_paths['must_watch_csv_path']}")
            print(f"lhb_shortline_daily_v1|watchlist_diagnostics_markdown|{report_paths['markdown_path']}")
            print(f"lhb_shortline_daily_v1|watchlist_diagnostics_stored|{stored}")
    elif args.command == "lhb-shortline-manual-review-v1":
        result = run_lhb_shortline_manual_review_v1(
            daily_watchlist_path=args.daily_watchlist_path,
            effectiveness_detail_path=args.effectiveness_detail_path,
            manual_review_path=args.manual_review_path,
            trade_date=args.trade_date,
            output_dir=args.output_dir,
        )
        print(f"lhb_shortline_manual_review_v1|manual_review|{result['paths']['manual_review']}")
        print(f"lhb_shortline_manual_review_v1|summary|{result['paths']['summary']}")
        print(f"lhb_shortline_manual_review_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-coverage-failure-plan":
        result = run_lhb_coverage_and_failure_rule_plan(
            coverage_gap_path=args.coverage_gap_path,
            case_path=args.case_path,
            snapshot_path=args.snapshot_path,
            output_dir=args.output_dir,
        )
        print(f"lhb_coverage_failure_plan|coverage_expansion_plan|{result['paths']['coverage_expansion_plan']}")
        print(f"lhb_coverage_failure_plan|coverage_expansion_summary|{result['paths']['coverage_expansion_summary']}")
        print(f"lhb_coverage_failure_plan|next_commands|{result['paths']['next_commands']}")
        print(f"lhb_coverage_failure_plan|failure_rule_audit|{result['paths']['failure_rule_audit']}")
        print(f"lhb_coverage_failure_plan|failure_rule_suggestions|{result['paths']['failure_rule_suggestions']}")
        print(f"lhb_coverage_failure_plan|report|{result['paths']['markdown_report']}")
        print(f"lhb_coverage_failure_plan|warnings|{len(result['warnings'])}")
    elif args.command == "fixed-industry-reconciliation":
        result = run_fixed_industry_reconciliation(
            start_date=args.start_date,
            end_date=args.end_date,
            top_n=args.top_n,
            transaction_cost_bps=args.transaction_cost_bps,
            output_dir=args.output_dir,
            industry_system=args.industry_system,
            industry_level=args.industry_level,
            adjust_type=args.adjust_type,
        )
        paths = result["paths"]
        print(f"fixed_industry_reconciliation|csv|{paths['reconciliation']}")
        print(f"fixed_industry_reconciliation|rows|{len(result['reconciliation'])}")
        print(f"fixed_industry_reconciliation|explanation|{result['explanation']}")
    elif args.command == "industry-error-audit":
        result = run_industry_error_audit(
            diagnostics_path=args.diagnostics_path,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
            backtest_summary_path=args.backtest_summary_path,
            annual_metrics_path=args.annual_metrics_path,
        )
        paths = result["paths"]
        print(f"industry_error_audit|monthly|{paths['monthly']}")
        print(f"industry_error_audit|summary|{paths['summary']}")
        print(f"industry_error_audit|tag_effectiveness|{paths['tag_effectiveness']}")
        print(f"industry_error_audit|component_effectiveness|{paths['component_effectiveness']}")
        print(f"industry_error_audit|yearly|{paths['yearly']}")
        print(f"industry_error_audit|markdown_report|{paths['markdown_report']}")
        print(f"industry_error_audit|monthly_rows|{len(result['monthly'])}")
        print(f"industry_error_audit|summary_rows|{len(result['summary'])}")
    elif args.command == "industry-mainline-regime-diagnostics":
        result = run_industry_mainline_regime_diagnostics(
            diagnostics_path=args.diagnostics_path,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
        )
        paths = result["paths"]
        print(f"industry_mainline_regime|diagnostics|{paths['diagnostics']}")
        print(f"industry_mainline_regime|market_regimes|{paths['market_regimes']}")
        print(
            "industry_mainline_regime|regime_effectiveness|"
            f"{paths['regime_effectiveness']}"
        )
        print(f"industry_mainline_regime|tag_effectiveness|{paths['tag_effectiveness']}")
        print(f"industry_mainline_regime|markdown_report|{paths['markdown_report']}")
        print(f"industry_mainline_regime|diagnostic_rows|{len(result['diagnostics'])}")
        print(f"industry_mainline_regime|regime_rows|{len(result['market_regimes'])}")
    elif args.command == "industry-regime-gated-backtest":
        result = run_industry_regime_gated_backtest(
            start_date=args.start_date,
            end_date=args.end_date,
            diagnostics_path=args.diagnostics_path,
            regime_path=args.regime_path,
            mainline_path=args.mainline_path,
            output_dir=args.output_dir,
            top_n=args.top_n,
            transaction_cost_bps=args.transaction_cost_bps,
            industry_system=args.industry_system,
            industry_level=args.industry_level,
            adjust_type=args.adjust_type,
        )
        paths = result["paths"]
        print(f"industry_regime_gated_backtest|summary|{paths['summary']}")
        print(f"industry_regime_gated_backtest|annual_metrics|{paths['annual_metrics']}")
        print(f"industry_regime_gated_backtest|monthly_metrics|{paths['monthly_metrics']}")
        print(f"industry_regime_gated_backtest|industry_exposure|{paths['industry_exposure']}")
        print(f"industry_regime_gated_backtest|turnover_detail|{paths['turnover_detail']}")
        print(f"industry_regime_gated_backtest|markdown_report|{paths['markdown_report']}")
        print(f"industry_regime_gated_backtest|summary_rows|{len(result['summary'])}")
    elif args.command == "industry-exposure-risk-control":
        result = run_industry_exposure_risk_control(
            start_date=args.start_date,
            end_date=args.end_date,
            diagnostics_path=args.diagnostics_path,
            regime_path=args.regime_path,
            mainline_path=args.mainline_path,
            output_dir=args.output_dir,
            top_n=args.top_n,
            transaction_cost_bps=args.transaction_cost_bps,
            industry_system=args.industry_system,
            industry_level=args.industry_level,
            adjust_type=args.adjust_type,
        )
        paths = result["paths"]
        print(f"industry_exposure_risk_control|summary|{paths['summary']}")
        print(f"industry_exposure_risk_control|annual_metrics|{paths['annual_metrics']}")
        print(f"industry_exposure_risk_control|monthly_metrics|{paths['monthly_metrics']}")
        print(f"industry_exposure_risk_control|industry_exposure|{paths['industry_exposure']}")
        print(f"industry_exposure_risk_control|turnover_detail|{paths['turnover_detail']}")
        print(f"industry_exposure_risk_control|markdown_report|{paths['markdown_report']}")
        print(f"industry_exposure_risk_control|summary_rows|{len(result['summary'])}")
    elif args.command == "sync-industry-memberships":
        count = sync_industry_memberships(args.trade_date)
        print(f"industry_memberships_synced|{count}")
    elif args.command == "sync-index-bars":
        count = sync_index_daily_bars(args.start_date, args.end_date)
        print(f"index_daily_bars_synced|{count}")
    elif args.command == "sync-index-constituents":
        count = sync_index_constituents(
            trade_date=args.trade_date,
            index_ids=args.index_ids,
            source_version=args.source_version,
        )
        print(f"index_constituents_synced|{count}")
    elif args.command == "benchmark-industry-day":
        result = benchmark_industry_day(
            trade_date=args.trade_date,
            industry_system=args.industry_system,
            adjust_type=args.adjust_type,
            use_cache=args.use_cache,
        )
        print(
            "industry_day_benchmark|sync_memberships|"
            f"{result['trade_date']}|rows|{result['membership_rows']}|seconds|{result['sync_seconds']}"
        )
        print(
            "industry_day_benchmark|build_bars|"
            f"{result['trade_date']}|seconds|{result['build_seconds']}"
        )
        print(
            "industry_day_benchmark|total|"
            f"{result['trade_date']}|seconds|{result['total_seconds']}"
        )
    elif args.command == "backfill-industry-history":
        result = run_industry_history_range(
            start_date=args.start_date,
            end_date=args.end_date,
            max_dates=args.max_dates,
            frequency=args.frequency,
            industry_system=args.industry_system,
            adjust_type=args.adjust_type,
            use_cache=args.use_cache,
            progress=lambda event: print(
                "industry_history_progress|"
                f"{event['trade_date']}|{event['index']}|{event['total']}|"
                f"membership_rows|{event['membership_rows']}|seconds|{event['seconds']}"
            ),
        )
        print(
            "industry_history_done|"
            f"dates|{result['dates']}|membership_rows|{result['membership_rows']}|"
            f"seconds|{result['seconds']}"
        )
    elif args.command == "sync-baostock-finance":
        counts = sync_finance_for_period(
            args.year,
            args.quarter,
            limit=args.limit,
            offset=args.offset,
        )
        print(f"baostock_finance_assets|{counts['queried_assets']}")
        print(f"finance_indicator_quarter_synced|{counts['indicator_quarter']}")
        print(f"finance_income_statement_synced|{counts['income_statement']}")
        print(f"finance_share_capital_event_synced|{counts['share_capital_event']}")
    elif args.command == "sync-baostock-minute-bars":
        counts = sync_baostock_stock_minute_bars(
            start_date=args.start_date,
            end_date=args.end_date,
            freq=args.freq,
            adjust_types=args.adjust_types,
            limit_assets=args.limit_assets,
            sleep_seconds=args.sleep_seconds,
        )
        for adjust_type, count in counts.items():
            print(f"stock_minute_bars_synced|{args.freq}|{adjust_type}|{count}")
    elif args.command == "sync-tushare-auction-bars":
        counts = sync_tushare_stock_auction_bars(
            start_date=args.start_date,
            end_date=args.end_date,
            auction_phases=args.auction_phases,
            ts_codes=args.ts_codes,
            trade_dates=args.trade_dates,
            sleep_seconds=args.sleep_seconds,
        )
        for phase, count in counts.items():
            print(f"stock_auction_bars_synced|{phase}|{count}")
    elif args.command == "tushare-auction-full-backfill-v1":
        trade_dates = load_open_trading_dates(
            start_date=args.start_date,
            end_date=args.end_date,
        )
        coverage = load_tushare_auction_full_coverage(
            start_date=args.start_date,
            end_date=args.end_date,
            auction_phases=args.auction_phases,
        )
        plan = build_tushare_auction_full_backfill_plan(
            trade_dates=trade_dates,
            auction_phases=args.auction_phases,
            existing_coverage=coverage,
            min_rows_per_date=args.min_rows_per_date,
        )
        executed = None
        run_summary = {"executed_calls": 0, "failed_calls": 0, "remaining_calls": len(plan), "upserted_rows": 0}
        if not args.dry_run and not plan.empty:
            result = run_tushare_auction_full_backfill_plan(
                plan=plan,
                max_calls=args.max_calls,
                token=args.token,
                sleep_seconds=args.sleep_seconds,
            )
            executed = result["executed"]
            run_summary = result["summary"]
        report = write_tushare_auction_full_backfill_report(
            plan=plan,
            executed=executed,
            output_dir=args.output_dir,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        print(f"tushare_auction_full_backfill_v1|plan|{report['paths']['plan']}")
        print(f"tushare_auction_full_backfill_v1|report|{report['paths']['markdown_report']}")
        if "executed" in report["paths"]:
            print(f"tushare_auction_full_backfill_v1|executed|{report['paths']['executed']}")
        print(f"tushare_auction_full_backfill_v1|planned_calls|{report['summary']['planned_calls']}")
        print(f"tushare_auction_full_backfill_v1|executed_calls|{run_summary['executed_calls']}")
        print(f"tushare_auction_full_backfill_v1|failed_calls|{run_summary['failed_calls']}")
        print(f"tushare_auction_full_backfill_v1|remaining_calls|{run_summary['remaining_calls']}")
        print(f"tushare_auction_full_backfill_v1|upserted_rows|{run_summary['upserted_rows']}")
        return 0
    elif args.command == "lhb-auction-backfill-plan-v1":
        ts_codes = load_lhb_auction_backfill_universe(
            candidate_paths=args.candidate_paths,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        coverage = load_existing_lhb_auction_coverage(
            start_date=args.start_date,
            end_date=args.end_date,
            ts_codes=ts_codes,
            auction_phases=args.auction_phases,
        )
        plan = build_lhb_auction_backfill_plan(
            trade_dates=args.trade_dates,
            ts_codes=ts_codes,
            auction_phases=args.auction_phases,
            existing_coverage=coverage,
            min_coverage_ratio=args.min_coverage_ratio,
        )
        result = write_lhb_auction_backfill_plan_report(
            plan=plan,
            output_dir=args.output_dir,
            start_date=args.start_date,
            end_date=args.end_date,
            ts_codes=ts_codes,
        )
        print(f"lhb_auction_backfill_plan_v1|plan|{result['paths']['plan']}")
        print(f"lhb_auction_backfill_plan_v1|universe|{result['paths']['universe']}")
        print(f"lhb_auction_backfill_plan_v1|report|{result['paths']['markdown_report']}")
        print(f"lhb_auction_backfill_plan_v1|planned_calls|{result['summary']['planned_calls']}")
        print(f"lhb_auction_backfill_plan_v1|ts_code_count|{result['summary']['ts_code_count']}")
        return 0
    elif args.command == "lhb-auction-backfill-run-v1":
        plan = pd.read_csv(args.plan_path, low_memory=False)
        universe = pd.read_csv(args.ts_codes_path, low_memory=False)
        ts_codes = sorted(universe["ts_code"].dropna().astype(str).str.strip().str.upper().unique())
        result = run_lhb_auction_backfill_plan(
            plan=plan,
            ts_codes=ts_codes,
            max_calls=args.max_calls,
            token=args.token,
            sleep_seconds=args.sleep_seconds,
        )
        output = Path(args.output_dir)
        output.mkdir(parents=True, exist_ok=True)
        executed_path = output / "lhb_auction_backfill_executed_latest.csv"
        result["executed"].to_csv(executed_path, index=False)
        print(f"lhb_auction_backfill_run_v1|executed|{executed_path}")
        print(f"lhb_auction_backfill_run_v1|executed_calls|{result['summary']['executed_calls']}")
        print(f"lhb_auction_backfill_run_v1|remaining_calls|{result['summary']['remaining_calls']}")
        print(f"lhb_auction_backfill_run_v1|upserted_rows|{result['summary']['upserted_rows']}")
        return 0
    elif args.command == "collect-open-auction-minute-v1":
        trade_date = dt.date.today().isoformat() if args.trade_date == "auto" else args.trade_date
        ts_codes = load_open_auction_minute_universe(args.universe_path)
        if args.retry_until_covered:
            result = collect_open_auction_minute_bars_until_covered(
                trade_date=trade_date,
                ts_codes=ts_codes,
                start_time=args.start_time,
                end_time=args.end_time,
                sleep_seconds=args.sleep_seconds,
                max_rounds=args.max_rounds,
                round_sleep_seconds=args.round_sleep_seconds,
                max_symbols=args.max_symbols,
            )
        else:
            result = collect_open_auction_minute_bars(
                trade_date=trade_date,
                ts_codes=ts_codes,
                start_time=args.start_time,
                end_time=args.end_time,
                sleep_seconds=args.sleep_seconds,
                max_symbols=args.max_symbols,
            )
        report = write_open_auction_minute_collect_report(
            result=result,
            output_dir=args.output_dir,
            trade_date=trade_date,
        )
        print(f"open_auction_minute_collect_v1|detail|{report['paths']['detail']}")
        print(f"open_auction_minute_collect_v1|latest|{report['paths']['latest']}")
        print(f"open_auction_minute_collect_v1|report|{report['paths']['markdown_report']}")
        for key in [
            "symbols_requested",
            "symbols_failed",
            "total_symbols",
            "covered_symbols",
            "remaining_symbols",
            "rounds_executed",
            "upserted_rows",
        ]:
            if key in report["summary"]:
                print(f"open_auction_minute_collect_v1|{key}|{report['summary'][key]}")
        return 0
    elif args.command == "open-auction-minute-cron-entry":
        for entry in build_open_auction_minute_cron_entries(
            project_dir=args.project_dir,
            universe_path=args.universe_path,
            output_dir=args.output_dir,
            log_path=args.log_path,
            primary_hour=args.primary_hour,
            primary_minute=args.primary_minute,
            retry_hour=args.retry_hour,
            retry_minute=args.retry_minute,
        ):
            print(entry)
        return 0
    elif args.command == "collect-open-auction-spot-snapshot-v1":
        trade_date = dt.date.today().isoformat() if args.trade_date == "auto" else args.trade_date
        result = collect_open_auction_spot_snapshot(
            trade_date=trade_date,
            target_time=args.target_time,
        )
        report = write_open_auction_spot_snapshot_report(
            result=result,
            output_dir=args.output_dir,
            trade_date=trade_date,
            target_time=args.target_time,
        )
        print(f"open_auction_spot_snapshot_v1|detail|{report['paths']['detail']}")
        print(f"open_auction_spot_snapshot_v1|latest|{report['paths']['latest']}")
        print(f"open_auction_spot_snapshot_v1|report|{report['paths']['markdown_report']}")
        print(f"open_auction_spot_snapshot_v1|queried_rows|{report['summary']['queried_rows']}")
        print(f"open_auction_spot_snapshot_v1|upserted_rows|{report['summary']['upserted_rows']}")
        print(f"open_auction_spot_snapshot_v1|skipped_rows|{report['summary']['skipped_rows']}")
        print(f"open_auction_spot_snapshot_v1|failed|{report['summary'].get('failed', False)}")
        return 1 if report["summary"].get("failed") else 0
    elif args.command == "open-auction-spot-snapshot-cron-entry":
        for entry in build_open_auction_spot_snapshot_cron_entries(
            project_dir=args.project_dir,
            output_dir=args.output_dir,
            log_path=args.log_path,
        ):
            print(entry)
        return 0
    elif args.command == "collect-xtick-auction-detail-v1":
        result = collect_xtick_dayupdate_bid(
            trade_date=args.trade_date,
            symbols=args.symbols,
            token_env=args.token_env,
            sleep_seconds=args.sleep_seconds,
        )
        report = write_xtick_auction_collect_report(
            result=result,
            output_dir=args.output_dir,
            trade_date=args.trade_date,
        )
        print(f"xtick_auction_detail_collect_v1|detail|{report['paths']['detail']}")
        print(f"xtick_auction_detail_collect_v1|latest|{report['paths']['latest']}")
        print(f"xtick_auction_detail_collect_v1|report|{report['paths']['markdown_report']}")
        print(f"xtick_auction_detail_collect_v1|symbols_requested|{report['summary']['symbols_requested']}")
        print(f"xtick_auction_detail_collect_v1|symbols_failed|{report['summary']['symbols_failed']}")
        print(f"xtick_auction_detail_collect_v1|upserted_rows|{report['summary']['upserted_rows']}")
        return 0
    elif args.command == "xtick-auction-backfill-plan-v1":
        coverage = load_existing_xtick_auction_coverage(
            start_date=args.start_date,
            end_date=args.end_date,
            source="xtick_dayupdate_bid",
        )
        trade_dates = load_xtick_backfill_trade_dates(
            start_date=args.start_date,
            end_date=args.end_date,
        )
        plan = build_xtick_auction_backfill_plan(
            start_date=args.start_date,
            end_date=args.end_date,
            trade_dates=trade_dates or None,
            symbols=args.symbols,
            existing_coverage=coverage,
            available_start_date=args.available_start_date,
            min_existing_rows=args.min_existing_rows,
        )
        report = write_xtick_auction_backfill_plan_report(
            plan=plan,
            output_dir=args.output_dir,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        print(f"xtick_auction_backfill_plan_v1|plan|{report['paths']['plan']}")
        print(f"xtick_auction_backfill_plan_v1|report|{report['paths']['markdown_report']}")
        print(f"xtick_auction_backfill_plan_v1|total_tasks|{report['summary']['total_tasks']}")
        print(f"xtick_auction_backfill_plan_v1|pending_tasks|{report['summary']['pending_tasks']}")
        print(f"xtick_auction_backfill_plan_v1|covered_tasks|{report['summary']['covered_tasks']}")
        print(f"xtick_auction_backfill_plan_v1|unavailable_tasks|{report['summary']['unavailable_tasks']}")
        return 0
    elif args.command == "xtick-auction-backfill-run-v1":
        plan = pd.read_csv(args.plan_path, low_memory=False)
        result = run_xtick_auction_backfill_plan(
            plan=plan,
            max_tasks=args.max_tasks,
            token_env=args.token_env,
            sleep_seconds=args.sleep_seconds,
        )
        report = write_xtick_auction_backfill_run_report(
            result=result,
            output_dir=args.output_dir,
        )
        print(f"xtick_auction_backfill_run_v1|executed|{report['paths']['executed']}")
        print(f"xtick_auction_backfill_run_v1|report|{report['paths']['markdown_report']}")
        print(f"xtick_auction_backfill_run_v1|executed_tasks|{report['summary']['executed_tasks']}")
        print(f"xtick_auction_backfill_run_v1|remaining_pending_tasks|{report['summary']['remaining_pending_tasks']}")
        print(f"xtick_auction_backfill_run_v1|upserted_rows|{report['summary']['upserted_rows']}")
        return 0
    elif args.command == "xtick-auction-925-check-v1":
        detail = build_xtick_auction_close_check(
            start_date=args.start_date,
            end_date=args.end_date,
            source=args.source,
        )
        report = write_xtick_auction_close_check_report(
            detail=detail,
            output_dir=args.output_dir,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        print(f"xtick_auction_925_check_v1|detail|{report['paths']['detail']}")
        print(f"xtick_auction_925_check_v1|report|{report['paths']['markdown_report']}")
        print(f"xtick_auction_925_check_v1|checked_rows|{report['summary']['checked_rows']}")
        print(f"xtick_auction_925_check_v1|match_rows|{report['summary']['match_rows']}")
        print(f"xtick_auction_925_check_v1|missing_result_bar_rows|{report['summary']['missing_result_bar_rows']}")
        print(f"xtick_auction_925_check_v1|price_mismatch_rows|{report['summary']['price_mismatch_rows']}")
        return 0
    elif args.command == "lhb-auction-observation-v1":
        result = build_lhb_auction_observation_report_v1(
            trades_path=args.trades_path,
            start_date=args.start_date,
            end_date=args.end_date,
            ts_codes=args.ts_codes,
            output_dir=args.output_dir,
        )
        print(f"lhb_auction_observation_v1|detail|{result['paths']['detail']}")
        print(f"lhb_auction_observation_v1|summary|{result['paths']['summary']}")
        print(f"lhb_auction_observation_v1|report|{result['paths']['markdown_report']}")
        print(f"lhb_auction_observation_v1|trades_observed|{result['summary']['trades_observed']}")
        print(f"lhb_auction_observation_v1|auction_rows_loaded|{result['summary']['auction_rows_loaded']}")
    elif args.command == "lhb-phase18-auction-rule-scan-v1":
        result = build_lhb_auction_enhanced_rule_scan_report_v1(
            detail_path=args.detail_path,
            output_dir=args.output_dir,
            rule_layer=args.rule_layer,
            thresholds=args.thresholds,
        )
        print(f"lhb_phase18_auction_rule_scan_v1|threshold_scan|{result['paths']['threshold_scan']}")
        print(f"lhb_phase18_auction_rule_scan_v1|strong_detail|{result['paths']['strong_detail']}")
        print(f"lhb_phase18_auction_rule_scan_v1|robustness|{result['paths']['robustness']}")
        print(f"lhb_phase18_auction_rule_scan_v1|quarterly|{result['paths']['quarterly']}")
        print(f"lhb_phase18_auction_rule_scan_v1|monthly|{result['paths']['monthly']}")
        print(f"lhb_phase18_auction_rule_scan_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-phase18b-auction-topn-rerank-v1":
        result = build_lhb_auction_topn_rerank_comparison_report_v1(
            detail_path=args.detail_path,
            output_dir=args.output_dir,
            top_ns=args.top_n,
        )
        print(f"lhb_phase18b_auction_topn_rerank_v1|summary|{result['paths']['summary']}")
        print(f"lhb_phase18b_auction_topn_rerank_v1|selected|{result['paths']['selected']}")
        print(f"lhb_phase18b_auction_topn_rerank_v1|scored|{result['paths']['scored']}")
        print(f"lhb_phase18b_auction_topn_rerank_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-phase18c-auction-cash-account-v1":
        result = run_lhb_phase18c_auction_enhanced_cash_account_backtest_v1(
            lifecycle_trades_path=args.lifecycle_trades_path,
            scored_candidates_path=args.scored_candidates_path,
            output_dir=args.output_dir,
            top_ns=args.top_n,
            max_positions=args.max_positions,
            position_pct=args.position_pct,
        )
        print(f"lhb_phase18c_auction_cash_account_v1|selected_trades|{result['paths']['selected_trades']}")
        print(f"lhb_phase18c_auction_cash_account_v1|account_trades|{result['paths']['account_trades']}")
        print(f"lhb_phase18c_auction_cash_account_v1|account_curve|{result['paths']['account_curve']}")
        print(f"lhb_phase18c_auction_cash_account_v1|summary|{result['paths']['summary']}")
        print(f"lhb_phase18c_auction_cash_account_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "lhb-phase18d-close-auction-lifecycle-v1":
        result = build_lhb_phase18d_close_auction_lifecycle_report_v1(
            trades_path=args.trades_path,
            output_dir=args.output_dir,
            strategy=args.strategy,
            top_n=args.top_n,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        print(f"lhb_phase18d_close_auction_lifecycle_v1|detail|{result['paths']['detail']}")
        print(
            "lhb_phase18d_close_auction_lifecycle_v1|trade_summary|"
            f"{result['paths']['trade_summary']}"
        )
        print(
            "lhb_phase18d_close_auction_lifecycle_v1|bucket_summary|"
            f"{result['paths']['bucket_summary']}"
        )
        print(f"lhb_phase18d_close_auction_lifecycle_v1|report|{result['paths']['markdown_report']}")
        print(
            "lhb_phase18d_close_auction_lifecycle_v1|trades_observed|"
            f"{result['summary']['trades_observed']}"
        )
        print(
            "lhb_phase18d_close_auction_lifecycle_v1|auction_rows_loaded|"
            f"{result['summary']['auction_rows_loaded']}"
        )
    elif args.command == "lhb-phase18e-joint-exit-diagnostics-v1":
        result = build_lhb_phase18e_joint_exit_diagnostics_report_v1(
            account_trades_path=args.account_trades_path,
            auction_observation_path=args.auction_observation_path,
            close_lifecycle_path=args.close_lifecycle_path,
            intraday_indicator_path=args.intraday_indicator_path,
            strategy=args.strategy,
            top_n=args.top_n,
            output_dir=args.output_dir,
        )
        print(f"lhb_phase18e_joint_exit_diagnostics_v1|state_detail|{result['paths']['state_detail']}")
        print(f"lhb_phase18e_joint_exit_diagnostics_v1|rule_scan|{result['paths']['rule_scan']}")
        print(f"lhb_phase18e_joint_exit_diagnostics_v1|report|{result['paths']['markdown_report']}")
        print(f"lhb_phase18e_joint_exit_diagnostics_v1|trades_observed|{result['summary']['trades_observed']}")
        print(
            "lhb_phase18e_joint_exit_diagnostics_v1|state_distribution|"
            f"{result['summary']['state_distribution']}"
        )
    elif args.command == "lhb-phase18f-tradable-joint-exit-replay-v1":
        result = run_lhb_phase18f_tradable_joint_exit_replay_v1(
            account_trades_path=args.account_trades_path,
            joint_state_detail_path=args.joint_state_detail_path,
            close_lifecycle_detail_path=args.close_lifecycle_detail_path,
            minute_bars_path=args.minute_bars_path,
            selected_trades_path=args.selected_trades_path,
            strategy=args.strategy,
            top_n=args.top_n,
            freq=args.freq,
            adjust_type=args.adjust_type,
            output_dir=args.output_dir,
        )
        print(f"lhb_phase18f_tradable_joint_exit_replay_v1|adjusted_trades|{result['paths']['adjusted_trades']}")
        print(f"lhb_phase18f_tradable_joint_exit_replay_v1|summary|{result['paths']['summary']}")
        print(f"lhb_phase18f_tradable_joint_exit_replay_v1|report|{result['paths']['markdown_report']}")
    elif args.command == "plan-baostock-minute-backfill":
        result = plan_baostock_minute_backfill(
            start_date=args.start_date,
            end_date=args.end_date,
            freq=args.freq,
            adjust_types=args.adjust_types,
            batch_by=args.batch_by,
            output_dir=args.output_dir,
            limit_assets=args.limit_assets,
        )
        for key, value in result["summary"].items():
            print(f"minute_backfill_plan|{key}|{value}")
    elif args.command == "run-baostock-minute-backfill":
        result = run_baostock_minute_backfill(
            start_date=args.start_date,
            end_date=args.end_date,
            freq=args.freq,
            adjust_types=args.adjust_types,
            batch_by=args.batch_by,
            max_jobs=args.max_jobs,
            retry_failed=args.retry_failed,
            sleep_seconds=args.sleep_seconds,
            workers=args.workers,
        )
        for key, value in result.items():
            print(f"minute_backfill_run|{key}|{value}")
    elif args.command == "benchmark-baostock-minute-backfill":
        result = benchmark_baostock_minute_backfill_workers(
            worker_counts=args.worker_counts,
            start_date=args.start_date,
            end_date=args.end_date,
            freq=args.freq,
            adjust_types=args.adjust_types,
            batch_by=args.batch_by,
            max_jobs=args.max_jobs,
            retry_failed=args.retry_failed,
            sleep_seconds=args.sleep_seconds,
        )
        for row in result["rows"]:
            print(
                "minute_backfill_benchmark|"
                f"workers|{row['workers']}|"
                f"attempted|{row['attempted']}|"
                f"success|{row['success']}|"
                f"failed|{row['failed']}|"
                f"rows|{row['rows']}|"
                f"elapsed_seconds|{row['elapsed_seconds']}|"
                f"jobs_per_second|{row['jobs_per_second']}|"
                f"rows_per_second|{row['rows_per_second']}|"
                f"failed_rate|{row['failed_rate']}"
            )
        print(
            "minute_backfill_benchmark_summary|"
            f"best_workers_by_rows_per_second|{result['summary']['best_workers_by_rows_per_second']}|"
            f"total_attempted|{result['summary']['total_attempted']}|"
            f"total_failed|{result['summary']['total_failed']}"
        )
    elif args.command == "run-baostock-minute-backfill-range":
        def report(summary: dict) -> None:
            month = summary["month"]
            job_summary = summary["job_summary"]
            validation_summary = summary["validation_summary"]
            message = (
                f"minute_backfill_month_done|{month}\n"
                f"jobs_total={job_summary['total_jobs']}\n"
                f"jobs_success={job_summary['success_jobs']}\n"
                f"jobs_failed={job_summary['failed_jobs']}\n"
                f"market_rows={job_summary['total_market_rows']}\n"
                f"staging_rows={job_summary['total_staging_rows']}\n"
                f"validation_errors={validation_summary['error_count']}"
            )
            print(message, flush=True)
            try:
                send_openclaw_feishu_message(
                    message=message,
                    target=args.report_target,
                    account=args.report_account,
                    openclaw_bin=args.openclaw_bin,
                    dry_run=args.report_dry_run,
                )
            except Exception as exc:
                print(
                    f"minute_backfill_report_failed|{exc.__class__.__name__}|{exc}",
                    file=sys.stderr,
                    flush=True,
                )

        result = run_baostock_minute_backfill_range(
            start_date=args.start_date,
            end_date=args.end_date,
            freq=args.freq,
            adjust_types=args.adjust_types,
            batch_by=args.batch_by,
            max_jobs=args.max_jobs,
            retry_failed=args.retry_failed,
            sleep_seconds=args.sleep_seconds,
            workers=args.workers,
            output_dir=args.output_dir,
            limit_assets=args.limit_assets,
            report=report,
        )
        for key, value in result.items():
            print(f"minute_backfill_range|{key}|{value}")
    elif args.command == "minute-backfill-watchdog":
        run_minute_backfill_watchdog_command(args)
    elif args.command == "backfill-watchdog":
        if args.adapter == "minute":
            run_minute_backfill_watchdog_command(args)
        elif args.adapter == "technical-features":
            run_technical_feature_watchdog_command(args)
        elif args.adapter == "factor-gate":
            run_factor_gate_watchdog_command(args)
    elif args.command == "baostock-minute-backfill-status":
        result = load_backfill_status(output_dir=args.output_dir)
        for key, value in result["summary"].items():
            print(f"minute_backfill_status|{key}|{value}")
        print(f"minute_backfill_status_by_period_rows|{len(result['by_period'])}")
    elif args.command == "validate-minute-bars":
        result = validate_minute_bars(
            start_date=args.start_date,
            end_date=args.end_date,
            freq=args.freq,
            adjust_types=args.adjust_types,
            output_dir=args.output_dir,
            limit_rows=args.limit_rows,
        )
        for key, value in result["summary"].items():
            print(f"minute_bar_validation|{key}|{value}")
    elif args.command == "create-ingest-jobs":
        count = create_ingest_jobs_for_service(
            args.dataset,
            start_year=args.start_year,
            end_year=args.end_year,
            batch_size=args.batch_size,
        )
        print(f"ingest_jobs_created|{args.dataset}|{count}")
    elif args.command == "run-ingest-jobs":
        result = run_ingest_jobs_for_service(
            args.dataset,
            limit_jobs=args.limit_jobs,
            progress=print_ingest_progress,
        )
        print(f"ingest_jobs_attempted|{result['attempted']}")
        print(f"ingest_jobs_success|{result['success']}")
        print(f"ingest_jobs_failed|{result['failed']}")
    elif args.command == "run-ingest-loop":
        def report(summary: dict) -> None:
            message = format_ingest_loop_report(summary)
            print(message, flush=True)
            try:
                send_openclaw_feishu_message(
                    message=message,
                    target=args.report_target,
                    account=args.report_account,
                    openclaw_bin=args.openclaw_bin,
                    dry_run=args.report_dry_run,
                )
            except Exception as exc:
                print(
                    f"ingest_loop_report_failed|{exc.__class__.__name__}|{exc}",
                    file=sys.stderr,
                    flush=True,
                )

        result = run_ingest_loop_for_service(
            args.dataset,
            jobs_per_round=args.jobs_per_round,
            report=report,
            progress=print_ingest_progress,
            sleep_seconds=args.sleep_seconds,
            max_rounds=args.max_rounds,
            workers=args.workers,
        )
        print(f"ingest_loop_rounds|{result['rounds']}")
        print(f"ingest_loop_attempted|{result['attempted']}")
        print(f"ingest_loop_success|{result['success']}")
        print(f"ingest_loop_failed|{result['failed']}")
        print(f"ingest_loop_done|{result['done']}")
    elif args.command == "reset-stale-ingest-jobs":
        count = reset_stale_ingest_jobs_for_service(
            dataset=args.dataset,
            older_than_minutes=args.older_than_minutes,
        )
        print(f"ingest_stale_reset|{args.dataset}|{count}")
    elif args.command == "ingest-status":
        for row in ingest_status_for_service(args.dataset):
            print(f"ingest_status|{row['dataset']}|{row['status']}|{row['count']}")
    elif args.command == "load-bars":
        hfq = load_market_daily_bars(
            "stock_hfq",
            "hfq",
            args.start_date,
            args.end_date,
            args.limit_tables,
            archive_raw=args.archive_raw,
        )
        qfq = load_market_daily_bars(
            "stock_qfq",
            "qfq",
            args.start_date,
            args.end_date,
            args.limit_tables,
            archive_raw=args.archive_raw,
        )
        print(f"market_rows_loaded|hfq|{hfq}")
        print(f"market_rows_loaded|qfq|{qfq}")
    elif args.command == "quality":
        for result in run_daily_quality_checks(args.trade_date):
            print(
                f"quality|{result['check_name']}|"
                f"{result['status']}|{result['metric_value']}"
            )
    elif args.command == "features":
        print(f"features_stored|{compute_and_store_p0_features(args.trade_date)}")
    elif args.command == "backfill-features":
        window = derive_feature_backfill_window(
            start_date=args.start_date,
            end_date=args.end_date,
            lookback_bars=args.lookback_bars,
            adjust_type=args.adjust_type,
        )
        if window["start_date"] is None or window["end_date"] is None:
            print("feature_backfill|dates|0")
            print("feature_backfill|rows|0")
            return
        result = compute_and_store_p0_features_range(
            start_date=str(window["start_date"]),
            end_date=str(window["end_date"]),
            lookback_bars=args.lookback_bars,
            adjust_type=args.adjust_type,
            workers=args.workers,
            skip_complete=args.skip_complete,
        )
        total = int(result["feature_rows"].sum()) if not result.empty else 0
        print(f"feature_backfill|dates|{len(result)}")
        print(f"feature_backfill|rows|{total}")
    elif args.command == "labels":
        print(f"labels_stored|{compute_and_store_labels(args.end_date)}")
    elif args.command == "backfill-labels":
        window = derive_label_backfill_window(
            start_date=args.start_date,
            end_date=args.end_date,
            horizons=args.horizons,
            adjust_type=args.adjust_type,
        )
        if window["start_date"] is None or window["end_date"] is None:
            print("labels_backfill|dates|0")
            print("labels_backfill|rows|0")
            return
        count = compute_and_store_labels(
            str(window["end_date"]),
            start_date=str(window["start_date"]),
            horizons=args.horizons,
        )
        print(f"labels_backfill|start_date|{window['start_date']}")
        print(f"labels_backfill|end_date|{window['end_date']}")
        print(f"labels_backfill|dates|{window['date_count']}")
        print(f"labels_backfill|rows|{count}")
    elif args.command == "select":
        selections = generate_selection(args.trade_date, args.top_n)
        print(f"selection_stored|{store_selection(selections)}")
    elif args.command == "report":
        quality_results = run_daily_quality_checks(args.trade_date)
        selections = generate_selection(args.trade_date, 20)
        print(
            format_daily_report(
                args.trade_date,
                quality_results,
                selections,
                args.log_path,
            )
        )
    elif args.command == "report-delivery-local":
        result = deliver_local_reports(
            trade_date=args.trade_date,
            input_dirs=args.input_dir,
            report_dirs=args.report_dir,
            run_card_dirs=args.run_card_dir,
            artifact_paths=args.artifact_path,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
        )
        print(f"report_delivery|status|{result.status}")
        print(f"report_delivery|artifacts|{result.artifact_count}")
        print(f"report_delivery|manifest|{result.manifest_path}")
        print(f"report_delivery|output_dir|{result.output_dir}")
        if result.delivery_log_path is not None:
            print(f"report_delivery|delivery_log|{result.delivery_log_path}")
    elif args.command == "report-delivery-openclaw-export":
        result = openclaw_export(
            trade_date=args.trade_date,
            manifest_path=args.manifest,
            output_dir=args.output_dir,
            include_all=args.include_all,
            min_severity=args.min_severity,
            dry_run=args.dry_run,
        )
        print(f"report_delivery_openclaw|status|{result.status}")
        print(f"report_delivery_openclaw|item_count|{result.item_count}")
        print(f"report_delivery_openclaw|manifest|{result.openclaw_manifest_path}")
        print(f"report_delivery_openclaw|items|{result.openclaw_items_path}")
        print(f"report_delivery_openclaw|output_dir|{result.output_dir}")
        print(f"report_delivery_openclaw|log|{result.openclaw_delivery_log_path}")
    elif args.command == "report-delivery-feishu":
        result = feishu_preview(
            trade_date=args.trade_date,
            manifest_path=args.manifest,
            output_dir=args.output_dir,
            include_all=args.include_all,
            min_severity=args.min_severity,
        )
        print(f"report_delivery_feishu|status|{result.status}")
        print(f"report_delivery_feishu|item_count|{result.item_count}")
        print(f"report_delivery_feishu|preview|{result.preview_path}")
        print(f"report_delivery_feishu|output_dir|{result.output_dir}")
        print(f"report_delivery_feishu|log|{result.delivery_log_path}")
    elif args.command == "report-delivery-feishu-send":
        result = feishu_send(
            trade_date=args.trade_date,
            preview_path=args.preview,
            output_dir=args.output_dir,
            webhook_url=args.webhook_url,
            dry_run=args.dry_run,
            limit=args.limit,
            allow_live_send=args.allow_live_send,
            severity_max=args.severity_max,
            test_mode=args.test_mode,
        )
        print(f"report_delivery_feishu_send|status|{result.status}")
        print(f"report_delivery_feishu_send|dry_run|{result.dry_run}")
        print(f"report_delivery_feishu_send|send_id|{result.send_id}")
        print(f"report_delivery_feishu_send|item_count|{result.item_count}")
        print(f"report_delivery_feishu_send|sent_count|{result.sent_count}")
        print(f"report_delivery_feishu_send|failed_count|{result.failed_count}")
        print(f"report_delivery_feishu_send|skipped_count|{result.skipped_count}")
        print(f"report_delivery_feishu_send|preview|{result.send_preview_path}")
        print(f"report_delivery_feishu_send|log|{result.send_log_path}")
        if not result.dry_run and result.status != "sent":
            raise RuntimeError(
                "report-delivery-feishu-send: "
                f"non-dry-run send failed with status {result.status}; "
                f"artifacts preserved at {result.send_log_path}"
            )
    elif args.command == "agent-report":
        result = build_agent_research_report(
            trade_date=args.trade_date,
            mode=args.mode,
            manifest_path=args.manifest,
            output_dir=args.output_dir,
        )
        print(f"agent_report|status|{result.status}")
        print(f"agent_report|review_status|{result.review_status}")
        print(f"agent_report|observations|{result.observation_count}")
        print(f"agent_report|blockers|{result.blocker_count}")
        print(f"agent_report|markdown|{result.markdown_path}")
        print(f"agent_report|json|{result.json_path}")
        print(f"agent_report|review|{result.review_path}")
    elif args.command == "report-delivery-openclaw-send":
        timeout_seconds = parse_openclaw_timeout_seconds(args.timeout_seconds)
        sender = OpenClawSender(
            transport=DryRunOpenClawTransport() if args.dry_run else HttpOpenClawTransport()
        )
        try:
            export_data = sender.load_export(args.manifest, args.items)
            manifest_trade_date = str(export_data["manifest"].get("trade_date", ""))
            if manifest_trade_date != args.trade_date:
                raise ValueError(
                    "report-delivery-openclaw-send: "
                    f"trade-date {args.trade_date} does not match loaded manifest trade_date {manifest_trade_date}"
                )
            result = sender.send_batch(
                manifest_path=args.manifest,
                items_path=args.items,
                config=OpenClawSendConfig(
                    endpoint=args.endpoint,
                    token=os.environ.get("OPENCLAW_TOKEN"),
                    timeout_seconds=timeout_seconds,
                    dry_run=args.dry_run,
                    retry_count=args.retry_count,
                    retry_backoff_seconds=args.retry_backoff_seconds,
                    outbox_dir=args.output_dir,
                    limit=args.limit,
                    allow_live_send=args.allow_live_send,
                    route_allowlist=args.route_allowlist,
                    severity_max=args.severity_max,
                    test_mode=args.test_mode,
                ),
            )
        except OpenClawSendInputError as exc:
            raise ValueError(f"report-delivery-openclaw-send: {exc}") from exc
        print(f"report_delivery_openclaw_send|status|{result.status}")
        print(f"report_delivery_openclaw_send|dry_run|{result.dry_run}")
        print(f"report_delivery_openclaw_send|send_id|{result.send_id}")
        print(f"report_delivery_openclaw_send|item_count|{result.item_count}")
        print(f"report_delivery_openclaw_send|sent_count|{result.sent_count}")
        print(f"report_delivery_openclaw_send|failed_count|{result.failed_count}")
        print(f"report_delivery_openclaw_send|skipped_count|{result.skipped_count}")
        print(f"report_delivery_openclaw_send|preview|{result.preview_path}")
        print(f"report_delivery_openclaw_send|log|{result.send_log_path}")
        if not result.dry_run and result.status != "sent":
            raise RuntimeError(
                "report-delivery-openclaw-send: "
                f"non-dry-run send failed with status {result.status}; "
                f"artifacts preserved at {result.send_log_path}"
            )
    elif args.command == "backtest-top20":
        result = run_top20_backtest(
            args.start_date,
            args.end_date,
            holding_days=args.holding_days,
            top_n=args.top_n,
            reports_dir=args.reports_dir,
        )
        print(f"backtest_run|{result['run'].run_id}")
        print(f"backtest_report|{result['report_path']}")
        print(f"backtest_trades|{len(result['trades'])}")
    elif args.command == "portfolio-backtest":
        result = run_portfolio_backtest(
            args.start_date,
            args.end_date,
            initial_cash=args.initial_cash,
            top_ks=args.top_ks,
            holding_days=args.holding_days,
            reports_dir=args.reports_dir,
        )
        print(f"portfolio_backtest_report|{result['report_path']}")
        print(
            f"portfolio_backtest_summary|{result['report_paths']['summary_path']}"
        )
        print(f"portfolio_backtest_configs|{len(result['summary'])}")
    elif args.command == "simulate-portfolio":
        result = run_portfolio_backtest(
            args.start_date,
            args.end_date,
            initial_cash=args.initial_cash,
            top_ks=args.top_ks,
            holding_days=args.holding_days,
            reports_dir=args.reports_dir,
        )
        review_paths = write_portfolio_simulation_review(
            result,
            output_dir=args.output_dir,
        )
        print(f"simulate_portfolio|json|{review_paths['json_path']}")
        print(f"simulate_portfolio|states_csv|{review_paths['states_csv_path']}")
        print(f"simulate_portfolio|markdown|{review_paths['markdown_path']}")
    elif args.command == "generate-trade-advice":

        simulation_state = json.loads(Path(args.simulation_state).read_text(encoding="utf-8"))
        candidates = pd.read_csv(args.candidates)
        advice = generate_trade_advice(
            trade_date=args.trade_date,
            simulation_state=simulation_state,
            candidates=candidates,
            policy=TradeAdvicePolicy(
                max_single_position_pct=args.max_single_position_pct,
                max_industry_position_pct=args.max_industry_position_pct,
                target_total_exposure_pct=args.target_total_exposure_pct,
                drawdown_defensive_threshold=args.drawdown_defensive_threshold,
                defensive_exposure_multiplier=args.defensive_exposure_multiplier,
            ),
        )
        advice_paths = write_trade_advice(
            trade_date=args.trade_date,
            advice=advice,
            output_dir=args.output_dir,
        )
        print(f"trade_advice|csv|{advice_paths['csv_path']}")
        print(f"trade_advice|json|{advice_paths['json_path']}")
        print(f"trade_advice|markdown|{advice_paths['markdown_path']}")
    elif args.command == "retention-backtest":
        execution_constraints = BacktestExecutionConstraints(
            commission_bps=args.commission_bps,
            stamp_duty_bps=args.stamp_duty_bps,
            slippage_bps=args.slippage_bps,
            min_amount=args.min_amount,
        )
        retention_kwargs = {
            "initial_cash": args.initial_cash,
            "top_ks": args.top_ks,
            "variant": args.variant,
            "reports_dir": args.reports_dir,
            "execution_constraints": execution_constraints,
        }
        if str(args.variant).strip().lower() in {"v3.1", "v31"}:
            retention_kwargs["cache_dir"] = args.cache_dir
        result = run_retention_backtest(
            args.start_date,
            args.end_date,
            **retention_kwargs,
        )
        print(f"retention_backtest_report|{result['report_path']}")
        print(
            f"retention_backtest_summary|{result['report_paths']['summary_path']}"
        )
        print(f"retention_backtest_configs|{len(result['summary'])}")
    elif args.command == "build-v31-cache":
        result = build_v31_cache(
            start_date=args.start_date,
            end_date=args.end_date,
            cache_dir=args.cache_dir,
            output_format=args.format,
        )
        print(f"v31_cache_manifest|{result['paths']['manifest']}")
        print(f"v31_cache_candidates|{result['counts']['retention_candidates']}")
    elif args.command == "build-universe":
        config = build_universe_config_from_args(args)
        result = UniverseService().build_universe(config)
        build_universe_artifacts(result=result, output_dir=args.output)
        print(f"universe_build|output|{args.output}")
        print(f"universe_build|included|{result.included_count}")
        print(f"universe_build|excluded|{result.excluded_count}")
    elif args.command == "explain-universe":
        config = build_universe_config_from_args(args)
        member = UniverseService().explain_stock(args.code, args.date, config)
        print(universe_member_to_json(member))
    elif args.command == "check-watchlist-universe":
        watchlist_codes = load_watchlist_codes(args.watchlist)
        config = build_universe_config_from_args(
            args,
            watchlist_codes=watchlist_codes,
        )
        result = UniverseService().build_universe(config)
        build_universe_artifacts(result=result, output_dir=args.output)
        print(f"watchlist_universe|output|{args.output}")
        print(f"watchlist_universe|members|{result.total_candidates}")
        print(f"watchlist_universe|included|{result.included_count}")
    elif args.command == "watchlist-build":
        rows = build_watchlist_snapshot(
            trade_date=args.trade_date,
            watchlist_id=args.watchlist_id,
            score_version=args.score_version,
            top_n=args.top_n,
        )
        report_paths = write_watchlist_report(rows, output_dir=args.output_dir)
        run_card = write_run_card(
            output_dir=Path(args.output_dir) / "run_card",
            run_type="watchlist_build",
            run_id=f"watchlist:{args.watchlist_id}:{args.trade_date}",
            title="Watchlist Build",
            config={
                "trade_date": args.trade_date,
                "watchlist_id": args.watchlist_id,
                "score_version": args.score_version,
                "top_n": args.top_n,
            },
            metrics={
                "rows": len(rows),
                "must_watch": int(rows["must_watch"].sum()) if not rows.empty else 0,
            },
            artifact_paths=report_paths,
        )
        print(f"watchlist_build|watchlist_id|{args.watchlist_id}")
        print(f"watchlist_build|members|{len(rows)}")
        print(f"watchlist_build|must_watch|{int(rows['must_watch'].sum()) if not rows.empty else 0}")
        print(f"watchlist_build|report|{report_paths['markdown_path']}")
        print(f"watchlist_build|run_card|{run_card['run_card_json_path']}")
    elif args.command == "build-watchlist-diagnostics":
        diagnostics = build_watchlist_diagnostics_snapshot(
            trade_date=args.trade_date,
            score_version=args.score_version,
            top_n=args.top_n,
            risk_watch_n=args.risk_watch_n,
            opportunity_watch_n=args.opportunity_watch_n,
            lhb_shortline_path=args.lhb_shortline_path,
        )
        report_paths = write_watchlist_diagnostics_report(
            full_rows=diagnostics["full"],
            must_watch_rows=diagnostics["must_watch"],
            output_dir=args.output_dir,
            output_version="v1",
            trade_date=args.trade_date,
            watchlist_id="diagnostics",
        )
        stored = _store_watchlist_diagnostics_signals(diagnostics["full"])
        print(f"watchlist_diagnostics|full_csv|{report_paths['full_csv_path']}")
        print(f"watchlist_diagnostics|must_watch_csv|{report_paths['must_watch_csv_path']}")
        print(f"watchlist_diagnostics|markdown|{report_paths['markdown_path']}")
        print(f"watchlist_diagnostics|stored|{stored}")
    elif args.command == "build-watchlist-diagnostics-range":
        dates = _load_trade_dates_for_watchlist_diagnostics_range(
            start_date=args.start_date,
            end_date=args.end_date,
        )
        built = 0
        skipped = 0
        for trade_date in dates:
            if not args.force and _has_matching_watchlist_diagnostics_cache(
                output_dir=args.output_dir,
                trade_date=trade_date,
            ):
                skipped += 1
                print(f"watchlist_diagnostics_range|skipped|{trade_date}")
                continue
            diagnostics = build_watchlist_diagnostics_snapshot(
                trade_date=trade_date,
                score_version=args.score_version,
                top_n=args.top_n,
                risk_watch_n=args.risk_watch_n,
                opportunity_watch_n=args.opportunity_watch_n,
                lhb_shortline_path=args.lhb_shortline_path,
            )
            write_watchlist_diagnostics_report(
                full_rows=diagnostics["full"],
                must_watch_rows=diagnostics["must_watch"],
                output_dir=args.output_dir,
                output_version="v1",
                trade_date=trade_date,
                watchlist_id="diagnostics",
            )
            built += 1
            print(f"watchlist_diagnostics_range|built|{trade_date}")
        print(
            "watchlist_diagnostics_range|summary|"
            f"dates|{len(dates)}|built|{built}|skipped|{skipped}|rule_version|{DIAGNOSTICS_RULE_VERSION}"
        )
    elif args.command == "review-watchlist-diagnostics":
        review_paths = run_watchlist_diagnostics_effectiveness_review(
            diagnostics_dir=args.diagnostics_dir,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
        )
        print(f"watchlist_effectiveness|detail_csv|{review_paths['detail_csv_path']}")
        print(f"watchlist_effectiveness|summary_csv|{review_paths['summary_csv_path']}")
        if "short_horizon_summary_csv_path" in review_paths:
            print(
                "watchlist_effectiveness|short_horizon_summary_csv|"
                f"{review_paths['short_horizon_summary_csv_path']}"
            )
        if "strong_winner_horizon_summary_csv_path" in review_paths:
            print(
                "watchlist_effectiveness|strong_winner_horizon_summary_csv|"
                f"{review_paths['strong_winner_horizon_summary_csv_path']}"
            )
        print(f"watchlist_effectiveness|markdown|{review_paths['markdown_path']}")
    elif args.command == "review-risk-watch-split":
        result = run_risk_watch_split_review(
            detail_path=args.detail_path,
            output_dir=args.output_dir,
        )
        print(f"risk_watch_split|detail|{result['paths']['detail']}")
        print(f"risk_watch_split|summary|{result['paths']['summary']}")
        print(f"risk_watch_split|reason_summary|{result['paths']['reason_summary']}")
        print(f"risk_watch_split|report|{result['paths']['report']}")
        print(f"risk_watch_split|rows|{len(result['detail'])}")
    elif args.command == "review-watchlist-context-cross":
        result = run_watchlist_context_cross_review(
            detail_path=args.detail_path,
            fundamental_context_path=args.fundamental_context_path,
            output_dir=args.output_dir,
        )
        print(f"watchlist_context_cross|detail|{result['paths']['detail']}")
        print(
            "watchlist_context_cross|short_horizon_summary|"
            f"{result['paths']['short_horizon_summary']}"
        )
        print(
            "watchlist_context_cross|strong_horizon_summary|"
            f"{result['paths']['strong_horizon_summary']}"
        )
        print(f"watchlist_context_cross|layer_summary|{result['paths']['layer_summary']}")
        print(f"watchlist_context_cross|industry_summary|{result['paths']['industry_summary']}")
        print(
            "watchlist_context_cross|fundamental_summary|"
            f"{result['paths']['fundamental_summary']}"
        )
        print(f"watchlist_context_cross|report|{result['paths']['report']}")
        for warning in result.get("warnings", []):
            print(f"watchlist_context_cross|warning|{warning}")
        print(f"watchlist_context_cross|rows|{len(result['detail'])}")
    elif args.command == "review-dual-strategy-effectiveness":
        result = run_dual_strategy_effectiveness_review(
            detail_path=args.detail_path,
            output_dir=args.output_dir,
        )
        print(f"dual_strategy_review|short_event_summary|{result['paths']['short_event_summary']}")
        print(
            "dual_strategy_review|trend_discovery_summary|"
            f"{result['paths']['trend_discovery_summary']}"
        )
        print(f"dual_strategy_review|comparison|{result['paths']['comparison']}")
        print(f"dual_strategy_review|report|{result['paths']['report']}")
        for warning in result.get("warnings", []):
            print(f"dual_strategy_review|warning|{warning}")
    elif args.command == "validate-trend-discovery-templates":
        result = run_trend_discovery_template_validation(
            detail_path=args.detail_path,
            strong_winner_path=args.strong_winner_path,
            output_dir=args.output_dir,
        )
        print(f"trend_template_validation|detail|{result['paths']['detail']}")
        print(f"trend_template_validation|summary|{result['paths']['summary']}")
        print(f"trend_template_validation|strong_winner_capture|{result['paths']['strong_winner_capture']}")
        print(f"trend_template_validation|recommendations|{result['paths']['recommendations']}")
        print(f"trend_template_validation|report|{result['paths']['report']}")
        for warning in result.get("warnings", []):
            print(f"trend_template_validation|warning|{warning}")
    elif args.command == "replay-trend-discovery-v2":
        result = run_trend_discovery_v2_replay(
            template_detail_path=args.template_detail,
            strong_winner_path=args.strong_winner_path,
            output_dir=args.output_dir,
        )
        print(f"trend_discovery_v2_replay|detail|{result['paths']['detail']}")
        print(f"trend_discovery_v2_replay|layer_effectiveness|{result['paths']['layer_effectiveness']}")
        print(f"trend_discovery_v2_replay|vs_existing|{result['paths']['vs_existing']}")
        print(f"trend_discovery_v2_replay|strong_winner_capture|{result['paths']['strong_winner_capture']}")
        print(f"trend_discovery_v2_replay|recommendations|{result['paths']['recommendations']}")
        print(f"trend_discovery_v2_replay|report|{result['paths']['report']}")
        for warning in result.get("warnings", []):
            print(f"trend_discovery_v2_replay|warning|{warning}")
    elif args.command == "audit-trend-discovery-v2-purity":
        result = run_trend_discovery_v2_purity_audit(
            v2_detail_path=args.v2_detail,
            strong_winner_path=args.strong_winner_path,
            output_dir=args.output_dir,
        )
        print(f"trend_discovery_v2_purity|purity_slice|{result['paths']['purity_slice']}")
        print(f"trend_discovery_v2_purity|bad_slice_audit|{result['paths']['bad_slice_audit']}")
        print(
            "trend_discovery_v2_purity|high_elasticity_slice|"
            f"{result['paths']['high_elasticity_slice']}"
        )
        print(
            "trend_discovery_v2_purity|v2_1_candidate_effectiveness|"
            f"{result['paths']['v2_1_candidate_effectiveness']}"
        )
        print(f"trend_discovery_v2_purity|missed_winner_audit|{result['paths']['missed_winner_audit']}")
        print(f"trend_discovery_v2_purity|recommendations|{result['paths']['recommendations']}")
        print(f"trend_discovery_v2_purity|report|{result['paths']['report']}")
        for warning in result.get("warnings", []):
            print(f"trend_discovery_v2_purity|warning|{warning}")
    elif args.command == "replay-trend-discovery-v2-2":
        result = run_trend_discovery_v2_2_replay(
            v2_detail_path=args.v2_detail,
            strong_winner_path=args.strong_winner_path,
            output_dir=args.output_dir,
        )
        print(f"trend_discovery_v2_2_replay|detail|{result['paths']['detail']}")
        print(f"trend_discovery_v2_2_replay|layer_effectiveness|{result['paths']['layer_effectiveness']}")
        print(f"trend_discovery_v2_2_replay|vs_existing|{result['paths']['vs_existing']}")
        print(f"trend_discovery_v2_2_replay|strong_winner_capture|{result['paths']['strong_winner_capture']}")
        print(f"trend_discovery_v2_2_replay|recommendations|{result['paths']['recommendations']}")
        print(f"trend_discovery_v2_2_replay|report|{result['paths']['report']}")
        for warning in result.get("warnings", []):
            print(f"trend_discovery_v2_2_replay|warning|{warning}")
    elif args.command == "review-trend-discovery-v2-2-stability":
        result = run_trend_discovery_v2_2_stability_review(
            detail_path=args.detail_path,
            strong_winner_path=args.strong_winner_path,
            output_dir=args.output_dir,
        )
        print(f"trend_discovery_v2_2_stability|by_period|{result['paths']['by_period']}")
        print(f"trend_discovery_v2_2_stability|by_regime|{result['paths']['by_regime']}")
        print(f"trend_discovery_v2_2_stability|by_industry|{result['paths']['by_industry']}")
        print(
            "trend_discovery_v2_2_stability|high_elasticity_short_horizon|"
            f"{result['paths']['high_elasticity_short_horizon']}"
        )
        print(
            "trend_discovery_v2_2_stability|strong_winner_capture|"
            f"{result['paths']['strong_winner_capture']}"
        )
        print(f"trend_discovery_v2_2_stability|decision|{result['paths']['decision']}")
        print(f"trend_discovery_v2_2_stability|report|{result['paths']['report']}")
        for warning in result.get("warnings", []):
            print(f"trend_discovery_v2_2_stability|warning|{warning}")
    elif args.command == "audit-watchlist-fundamental-coverage":
        result = run_watchlist_fundamental_coverage_audit(
            detail_path=args.detail_path,
            output_dir=args.output_dir,
        )
        print(f"watchlist_fundamental_coverage|summary|{result['paths']['summary']}")
        print(f"watchlist_fundamental_coverage|date_summary|{result['paths']['date_summary']}")
        print(f"watchlist_fundamental_coverage|report|{result['paths']['report']}")
    elif args.command == "build-watchlist-fundamental-pit-context":
        result = run_watchlist_fundamental_pit_context_build(
            detail_path=args.detail_path,
            output_dir=args.output_dir,
        )
        print(f"watchlist_fundamental_pit_context|context|{result['paths']['context']}")
        print(f"watchlist_fundamental_pit_context|summary|{result['paths']['summary']}")
        print(f"watchlist_fundamental_pit_context|report|{result['paths']['report']}")
        print(f"watchlist_fundamental_pit_context|rows|{len(result['context'])}")
    elif args.command == "analyze-strong-winner-misses":
        result = run_strong_winner_miss_analysis(
            start_date=args.start_date,
            end_date=args.end_date,
            adjust_type=args.adjust_type,
            window_days=args.window_days,
            threshold=args.threshold,
            diagnostics_dir=args.diagnostics_dir,
            output_dir=args.output_dir,
        )
        print(f"strong_winner_miss_analysis|strong_winners|{result['paths']['strong_winners']}")
        print(f"strong_winner_miss_analysis|miss_analysis|{result['paths']['miss_analysis']}")
        print(f"strong_winner_miss_analysis|summary|{result['paths']['summary']}")
        print(f"strong_winner_miss_analysis|report|{result['paths']['report']}")
        print(f"strong_winner_miss_analysis|rows|{len(result['miss_analysis'])}")
    elif args.command == "analyze-strong-winner-taxonomy-v2":
        result = run_strong_winner_taxonomy_v2(
            start_date=args.start_date,
            end_date=args.end_date,
            adjust_type=args.adjust_type,
            v2_detail_path=args.v2_detail_path,
            output_dir=args.output_dir,
        )
        print(f"strong_winner_taxonomy_v2|taxonomy|{result['paths']['taxonomy']}")
        print(f"strong_winner_taxonomy_v2|summary|{result['paths']['summary']}")
        print(f"strong_winner_taxonomy_v2|v2_2_capture|{result['paths']['v2_2_capture']}")
        print(f"strong_winner_taxonomy_v2|report|{result['paths']['report']}")
        print(f"strong_winner_taxonomy_v2|rows|{len(result.get('taxonomy', []))}")
        for warning in result.get("warnings", []):
            print(f"strong_winner_taxonomy_v2|warning|{warning}")
    elif args.command == "analyze-strong-winner-capture-gap":
        result = run_strong_winner_capture_gap_analysis(
            taxonomy_path=args.taxonomy_path,
            v2_detail_path=args.v2_detail_path,
            output_dir=args.output_dir,
        )
        print(f"strong_winner_capture_gap|detail|{result['paths']['detail']}")
        print(f"strong_winner_capture_gap|summary|{result['paths']['summary']}")
        print(f"strong_winner_capture_gap|by_type|{result['paths']['by_type']}")
        print(f"strong_winner_capture_gap|sample|{result['paths']['sample']}")
        print(f"strong_winner_capture_gap|report|{result['paths']['report']}")
        print(f"strong_winner_capture_gap|rows|{len(result.get('detail', []))}")
        for warning in result.get("warnings", []):
            print(f"strong_winner_capture_gap|warning|{warning}")
    elif args.command == "audit-diagnostics-candidate-source":
        result = run_diagnostics_candidate_source_audit(
            gap_detail_path=args.gap_detail_path,
            v2_detail_path=args.v2_detail_path,
            score_version=args.score_version,
            diagnostics_top_n=args.diagnostics_top_n,
            output_dir=args.output_dir,
        )
        print(f"diagnostics_candidate_source_audit|detail|{result['paths']['detail']}")
        print(f"diagnostics_candidate_source_audit|summary|{result['paths']['summary']}")
        print(f"diagnostics_candidate_source_audit|by_type|{result['paths']['by_type']}")
        print(f"diagnostics_candidate_source_audit|report|{result['paths']['report']}")
        print(f"diagnostics_candidate_source_audit|rows|{len(result.get('detail', []))}")
        for warning in result.get("warnings", []):
            print(f"diagnostics_candidate_source_audit|warning|{warning}")
    elif args.command == "analyze-strong-winner-topn-source":
        result = run_strong_winner_topn_attribution(
            miss_analysis_path=args.miss_analysis_path,
            score_version=args.score_version,
            topn_thresholds=args.topn_thresholds,
            output_dir=args.output_dir,
        )
        print(f"strong_winner_topn_source|attribution|{result['paths']['attribution']}")
        print(
            "strong_winner_topn_source|threshold_sensitivity|"
            f"{result['paths']['threshold_sensitivity']}"
        )
        print(f"strong_winner_topn_source|component_gap|{result['paths']['component_gap']}")
        print(f"strong_winner_topn_source|report|{result['paths']['report']}")
        print(f"strong_winner_topn_source|rows|{len(result['attribution'])}")
    elif args.command == "build-strong-winner-discovery-pool":
        result = run_strong_winner_discovery_pool(
            start_date=args.start_date,
            end_date=args.end_date,
            score_version=args.score_version,
            adjust_type=args.adjust_type,
            topn_thresholds=args.topn_thresholds,
            strong_winner_path=args.strong_winner_path,
            output_dir=args.output_dir,
        )
        print(f"strong_winner_discovery_pool|detail|{result['paths']['detail']}")
        print(
            "strong_winner_discovery_pool|pool_effectiveness|"
            f"{result['paths']['pool_effectiveness']}"
        )
        print(f"strong_winner_discovery_pool|capture_by_type|{result['paths']['capture_by_type']}")
        print(f"strong_winner_discovery_pool|report|{result['paths']['report']}")
        print(f"strong_winner_discovery_pool|rows|{len(result['detail'])}")
    elif args.command == "watchlist-report":
        rows = load_watchlist_daily_signals(args.watchlist_id, trade_date=args.trade_date)
        report_paths = write_watchlist_report(rows, output_dir=args.output_dir)
        print(f"watchlist_report|markdown|{report_paths['markdown_path']}")
    elif args.command == "watchlist-explain":
        print(
            json.dumps(
                _json_safe_value(
                    explain_watchlist_asset(
                    trade_date=args.trade_date,
                    watchlist_id=args.watchlist_id,
                    asset_id=args.asset_id,
                    )
                ),
                ensure_ascii=False,
                sort_keys=True,
            )
        )


def main(argv: list[str] | None = None) -> int | None:
    return main_for_args(argv)


if __name__ == "__main__":
    sys.exit(main())
