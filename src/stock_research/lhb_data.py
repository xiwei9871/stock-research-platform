from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, execute_many, fetch_all
from stock_research.dragon_case_library import (
    build_failure_event_rule_v21_curated_view,
    build_failure_event_rule_v21_transition_matrix,
)


TOP_LIST_COLUMNS = [
    "trade_date",
    "ts_code",
    "name",
    "close",
    "pct_change",
    "turnover_rate",
    "amount",
    "l_sell",
    "l_buy",
    "l_amount",
    "net_amount",
    "net_rate",
    "amount_rate",
    "float_values",
    "reason",
    "source",
]

TOP_INST_COLUMNS = [
    "trade_date",
    "ts_code",
    "exalter",
    "buy",
    "buy_rate",
    "sell",
    "sell_rate",
    "net_buy",
    "reason",
    "source",
]

LHB_ALIGNMENT_COLUMNS = [
    "case_id",
    "ts_code",
    "stock_name",
    "case_type",
    "event_type",
    "event_date",
    "lhb_on_event_date",
    "lhb_before_event_3d",
    "lhb_after_event_3d",
    "lhb_reason",
    "lhb_net_buy_amount",
    "institution_net_buy",
    "top_seat_concentration",
    "repeat_on_list_count_3d",
    "repeat_on_list_count_5d",
    "lhb_one_day_pump_risk",
    "lhb_alignment_status",
]

LHB_EVENT_FEATURE_COLUMNS = [
    "trade_date",
    "ts_code",
    "on_lhb",
    "lhb_reason",
    "lhb_net_buy_amount",
    "lhb_net_buy_ratio",
    "lhb_buy_amount",
    "lhb_sell_amount",
    "institution_net_buy",
    "top_seat_concentration",
    "repeat_on_list_count_3d",
    "repeat_on_list_count_5d",
    "lhb_after_limit_up",
    "lhb_after_break_limit",
    "lhb_after_reversal",
    "lhb_one_day_pump_risk",
    "source",
]

FUTURE_DIAGNOSTIC_COLUMNS = [
    "future_1d_return",
    "future_3d_return",
    "future_5d_return",
    "future_10d_return",
    "future_5d_max_drawdown",
    "future_10d_max_drawdown",
]

LHB_FOLLOW_EXIT_REPLAY_COLUMNS = [
    "case_id",
    "ts_code",
    "stock_name",
    "event_date",
    "event_type",
    "verified_case_type",
    "success_or_failure",
    "lhb_replay_action",
    "lhb_replay_reason",
    "lhb_risk_score",
    "lhb_risk_level",
    "lhb_negative_net_buy",
    "lhb_institution_selling",
    "lhb_high_pump_risk",
    "lhb_after_event_attention",
    "lhb_net_buy_amount_event",
    "institution_net_buy_event",
    "future_3d_return",
    "future_5d_return",
    "future_10d_return",
    "future_5d_max_drawdown",
    "future_10d_max_drawdown",
]

LHB_SHORTLINE_EVENT_REPLAY_COLUMNS = [
    "trade_date",
    "ts_code",
    "stock_name",
    "short_market_state",
    "short_allowed",
    "market_risk_level",
    "industry_name",
    "mainline_flag",
    "industry_rank",
    "industry_focus_score_v2",
    "dragon_role",
    "dragon_entry_score",
    "dragon_risk_score",
    "entry_window_v2",
    "event_structure",
    "event_date",
    "lhb_event_date",
    "lhb_behavior_type",
    "lhb_replay_action",
    "lhb_replay_reason",
    "lhb_risk_score",
    "lhb_risk_level",
    "lhb_negative_net_buy",
    "lhb_institution_selling",
    "lhb_high_pump_risk",
    "lhb_after_event_attention",
    "exit_signal",
    "exit_reason",
    "future_1d_return",
    "future_3d_return",
    "future_5d_return",
    "future_10d_return",
    "future_5d_max_drawdown",
    "future_10d_max_drawdown",
    "case_id",
    "event_type",
    "verified_case_type",
    "success_or_failure",
]

LHB_FOLLOW_AVOID_EFFECTIVENESS_COLUMNS = [
    "sample_count",
    "avg_future_3d_return",
    "avg_future_5d_return",
    "avg_future_10d_return",
    "win_rate_3d",
    "win_rate_5d",
    "win_rate_10d",
    "avg_future_5d_max_drawdown",
    "avg_future_10d_max_drawdown",
    "success_count",
    "failure_count",
]

DAILY_LHB_SHORTLINE_WATCHLIST_COLUMNS = [
    "trade_date",
    "ts_code",
    "stock_name",
    "watch_group",
    "watch_reason",
    "exit_signal",
    "exit_reason",
    "short_market_state",
    "short_allowed",
    "market_risk_level",
    "mainline_flag",
    "dragon_role",
    "entry_window_v2",
    "event_structure",
    "lhb_behavior_type",
    "lhb_replay_action",
    "lhb_replay_reason",
    "lhb_risk_score",
    "lhb_risk_level",
    "lhb_shortline_rule_version",
    "lhb_shortline_follow_rule_id",
    "lhb_shortline_exit_rule_id",
    "lhb_shortline_rule_confidence",
    "lhb_shortline_rule_sample_count",
    "rule_calibration_action",
]

LHB_SHORTLINE_STRATEGY_EFFECTIVENESS_DETAIL_COLUMNS = [
    "trade_date",
    "ts_code",
    "stock_name",
    "watch_group",
    "lhb_behavior_type",
    "lhb_replay_action",
    "event_structure",
    "entry_window_v2",
    "mainline_flag",
    "short_market_state",
    "market_risk_level",
    "exit_signal",
    "exit_reason",
    "future_1d_return",
    "future_3d_return",
    "future_5d_return",
    "future_10d_return",
    "future_5d_max_drawdown",
    "future_10d_max_drawdown",
    "limit_up_within_5d",
    "a_kill_within_5d",
    "second_wave_success",
    "exit_hit",
]

LHB_SHORTLINE_STRATEGY_EFFECTIVENESS_METRIC_COLUMNS = [
    "sample_count",
    "avg_future_1d_return",
    "avg_future_3d_return",
    "avg_future_5d_return",
    "avg_future_10d_return",
    "win_rate_1d",
    "win_rate_3d",
    "win_rate_5d",
    "win_rate_10d",
    "avg_future_5d_max_drawdown",
    "avg_future_10d_max_drawdown",
    "limit_up_rate_5d",
    "a_kill_rate_5d",
    "second_wave_success_rate",
    "exit_hit_rate",
    "low_sample_flag",
]

LHB_SHORTLINE_SHADOW_BACKTEST_SELECTED_COLUMNS = [
    "pool_mode",
    "top_n",
    "trade_date",
    "ts_code",
    "stock_name",
    "selection_rank",
    "selection_score",
    "lhb_behavior_type",
    "lhb_replay_action",
    "event_structure",
    "lhb_risk_score",
    "dragon_entry_score",
    "industry_focus_score_v2",
    "future_1d_return",
    "future_3d_return",
    "future_5d_return",
    "future_10d_return",
    "future_5d_max_drawdown",
    "exit_signal",
    "exit_reason",
]

LHB_SHORTLINE_SHADOW_BACKTEST_DAILY_CURVE_COLUMNS = [
    "pool_mode",
    "top_n",
    "trade_date",
    "selected_count",
    "daily_1d_return",
    "daily_3d_return",
    "daily_5d_return",
    "daily_10d_return",
    "daily_5d_max_drawdown",
    "equity_5d_proxy",
    "drawdown_5d_proxy",
]

LHB_SHORTLINE_SHADOW_BACKTEST_SUMMARY_COLUMNS = [
    "pool_mode",
    "top_n",
    "start_date",
    "end_date",
    "signal_day_count",
    "selected_trade_count",
    "avg_trade_1d_return",
    "avg_trade_3d_return",
    "avg_trade_5d_return",
    "avg_trade_10d_return",
    "win_rate_5d",
    "avg_trade_5d_max_drawdown",
    "avg_daily_5d_return",
    "final_equity_5d_proxy",
    "max_drawdown_5d_proxy",
]

LHB_SHORTLINE_INTRADAY_CONFIRMATION_DETAIL_COLUMNS = [
    "trade_date",
    "ts_code",
    "stock_name",
    "top_n",
    "confirmation_trade_date",
    "intraday_confirmation_action",
    "intraday_confirmation_reason",
    "minute_bar_count",
    "entry_time_proxy",
    "entry_price_proxy",
    "first_60m_return",
    "intraday_return",
    "high_to_close_drawdown",
    "close_to_vwap",
    "tail_return",
    "lhb_replay_action",
    "lhb_behavior_type",
    "event_structure",
]

LHB_SHORTLINE_INTRADAY_CONFIRMATION_SUMMARY_COLUMNS = [
    "intraday_confirmation_action",
    "candidate_count",
    "avg_first_60m_return",
    "avg_intraday_return",
    "avg_high_to_close_drawdown",
    "avg_close_to_vwap",
    "avg_tail_return",
]

LHB_FULL_MARKET_POOL_SELECTED_COLUMNS = [
    "pool_mode",
    "top_n",
    "trade_date",
    "ts_code",
    "selection_rank",
    "selection_score",
    "lhb_net_buy_amount",
    "lhb_net_buy_ratio",
    "institution_net_buy",
    "top_seat_concentration",
    "repeat_on_list_count_3d",
    "repeat_on_list_count_5d",
    "lhb_after_limit_up",
    "lhb_after_break_limit",
    "lhb_after_reversal",
    "lhb_one_day_pump_risk",
    "future_1d_return",
    "future_3d_return",
    "future_5d_return",
    "future_10d_return",
    "future_5d_max_drawdown",
    "future_10d_max_drawdown",
]

LHB_INTRADAY_FILTERED_TOPN_COMPARISON_COLUMNS = [
    "pool_mode",
    "top_n",
    "candidate_set",
    "selected_trade_count",
    "signal_day_count",
    "avg_future_1d_return",
    "avg_future_3d_return",
    "avg_future_5d_return",
    "avg_future_10d_return",
    "win_rate_5d",
    "avg_future_5d_max_drawdown",
]

LHB_INTRADAY_ACTION_EFFECTIVENESS_COLUMNS = [
    "intraday_confirmation_action",
    "candidate_count",
    "avg_future_1d_return",
    "avg_future_3d_return",
    "avg_future_5d_return",
    "avg_future_10d_return",
    "win_rate_5d",
    "avg_future_5d_max_drawdown",
]

LHB_PHASE12A_DECISION_COLUMNS = [
    "pool_mode",
    "top_n",
    "trade_date",
    "ts_code",
    "stock_name",
    "selection_rank",
    "selection_score",
    "pre_event_context_type",
    "pre_event_day_count",
    "pre_event_return",
    "event_day_context_type",
    "event_day_return",
    "event_day_high_to_close_drawdown",
    "event_day_close_to_vwap",
    "event_day_tail_return",
    "intraday_confirmation_action",
    "intraday_confirmation_reason",
    "lhb_phase12a_decision",
    "decision_priority",
    "can_follow",
    "should_retreat",
    "position_note",
    "future_1d_return",
    "future_3d_return",
    "future_5d_return",
    "future_10d_return",
    "future_5d_max_drawdown",
    "future_10d_max_drawdown",
]

LHB_PHASE12A_SUMMARY_COLUMNS = [
    "lhb_phase12a_decision",
    "candidate_count",
    "signal_day_count",
    "avg_future_1d_return",
    "avg_future_3d_return",
    "avg_future_5d_return",
    "avg_future_10d_return",
    "win_rate_5d",
    "avg_future_5d_max_drawdown",
]

LHB_PHASE12A_RULE_DECISION_EXTRA_COLUMNS = [
    "phase12a_rule_layer",
    "phase12a_rule_action",
    "phase12a_rule_priority",
    "phase12a_rule_reason",
]

LHB_PHASE12A_RULE_SUMMARY_COLUMNS = [
    "phase12a_rule_layer",
    "candidate_count",
    "signal_day_count",
    "avg_future_1d_return",
    "avg_future_3d_return",
    "avg_future_5d_return",
    "avg_future_10d_return",
    "win_rate_5d",
    "avg_future_5d_max_drawdown",
]

LHB_PHASE12A_REAL_ENTRY_TRADE_COLUMNS = [
    "trade_date",
    "ts_code",
    "top_n",
    "phase12a_rule_layer",
    "phase12a_rule_action",
    "fill_status",
    "confirmation_trade_date",
    "entry_signal_time",
    "entry_time",
    "entry_price",
    "entry_start_time",
    "slippage_bps",
    "blocked_entry_bar_count",
    "blocked_entry_reason",
    "exit_0d_close",
    "exit_0d_return",
    "exit_1d_close",
    "exit_1d_return",
    "exit_2d_close",
    "exit_2d_return",
    "exit_3d_close",
    "exit_3d_return",
    "exit_5d_close",
    "exit_5d_return",
    "max_drawdown_to_5d",
]

LHB_PHASE12A_REAL_ENTRY_SUMMARY_COLUMNS = [
    "phase12a_rule_layer",
    "candidate_count",
    "filled_count",
    "fill_rate",
    "avg_entry_price",
    "avg_exit_0d_return",
    "win_rate_0d",
    "avg_exit_1d_return",
    "win_rate_1d",
    "avg_exit_2d_return",
    "win_rate_2d",
    "avg_exit_3d_return",
    "win_rate_3d",
    "avg_exit_5d_return",
    "win_rate_5d",
    "avg_max_drawdown_to_5d",
]

LHB_PHASE12B_SIGNAL_EXIT_TRADE_COLUMNS = [
    "trade_date",
    "ts_code",
    "top_n",
    "phase12a_rule_layer",
    "fill_status",
    "entry_trade_date",
    "entry_time",
    "entry_price",
    "exit_status",
    "exit_signal",
    "exit_signal_trade_date",
    "exit_signal_time",
    "exit_trade_date",
    "exit_time",
    "exit_price",
    "realized_return",
    "holding_trade_days",
    "max_hold_days",
]

LHB_PHASE12B_SIGNAL_EXIT_SUMMARY_COLUMNS = [
    "phase12a_rule_layer",
    "entry_count",
    "filled_count",
    "signal_exit_count",
    "fallback_exit_count",
    "avg_realized_return",
    "win_rate",
    "avg_holding_trade_days",
]

LHB_PHASE14_LIFECYCLE_EXIT_TRADE_COLUMNS = [
    "trade_date",
    "ts_code",
    "top_n",
    "phase12a_rule_layer",
    "fill_status",
    "entry_trade_date",
    "entry_time",
    "entry_price",
    "exit_status",
    "exit_signal",
    "exit_reason",
    "exit_signal_trade_date",
    "exit_signal_time",
    "exit_trade_date",
    "exit_time",
    "exit_price",
    "realized_return",
    "holding_trade_days",
    "max_hold_days",
    "blocked_exit_bar_count",
    "blocked_exit_reason",
]

LHB_PHASE14_LIFECYCLE_EXIT_SUMMARY_COLUMNS = [
    "phase12a_rule_layer",
    "entry_count",
    "filled_count",
    "signal_exit_count",
    "fallback_exit_count",
    "avg_realized_return",
    "win_rate",
    "avg_holding_trade_days",
]

LHB_PHASE14B_THRESHOLD_SUMMARY_COLUMNS = [
    "threshold_profile",
    "phase12a_rule_layer",
    "entry_count",
    "filled_count",
    "signal_exit_count",
    "fallback_exit_count",
    "avg_realized_return",
    "win_rate",
    "avg_holding_trade_days",
    "signal_exit_rate",
]

LHB_PHASE14B_PROFILE_RANKING_COLUMNS = [
    "threshold_profile",
    "filled_count",
    "signal_exit_count",
    "fallback_exit_count",
    "avg_realized_return",
    "win_rate",
    "avg_holding_trade_days",
    "signal_exit_rate",
    "rank_score",
]

LHB_PHASE14C_DAILY_CURVE_COLUMNS = [
    "top_n",
    "exit_trade_date",
    "closed_trade_count",
    "daily_realized_return",
    "equity",
    "drawdown",
]

LHB_PHASE14C_PORTFOLIO_SUMMARY_COLUMNS = [
    "top_n",
    "threshold_profile",
    "entry_count",
    "filled_count",
    "closed_trade_count",
    "signal_exit_count",
    "fallback_exit_count",
    "avg_realized_return",
    "win_rate",
    "avg_holding_trade_days",
    "final_equity",
    "max_drawdown",
]

LHB_PHASE14E_RISK_AUDIT_COLUMNS = [
    "risk_type",
    "event_count",
    "affected_trade_count",
    "avg_realized_return",
    "avg_blocked_bar_count",
    "max_blocked_bar_count",
]

LHB_PHASE14E_FILTER_RANKING_COLUMNS = [
    "filter_profile",
    "top_n",
    "entry_count",
    "filled_count",
    "closed_trade_count",
    "avg_realized_return",
    "win_rate",
    "final_equity",
    "max_drawdown",
    "blocked_exit_count",
    "rank_score",
]

LHB_PHASE15_ACCOUNT_TRADE_COLUMNS = [
    "account_trade_status",
    "trade_date",
    "ts_code",
    "top_n",
    "phase12a_rule_layer",
    "entry_trade_date",
    "entry_time",
    "entry_price",
    "exit_status",
    "exit_signal",
    "exit_reason",
    "exit_trade_date",
    "exit_time",
    "exit_price",
    "realized_return",
    "position_notional",
    "pnl",
    "skip_reason",
]

LHB_PHASE15_ACCOUNT_CURVE_COLUMNS = [
    "trade_date",
    "cash",
    "invested_notional",
    "equity",
    "drawdown",
    "open_position_count",
    "opened_count",
    "closed_count",
    "daily_realized_pnl",
]

LHB_PHASE15_ACCOUNT_SUMMARY_COLUMNS = [
    "initial_equity",
    "final_equity",
    "total_return",
    "max_drawdown",
    "filled_trade_count",
    "closed_trade_count",
    "skipped_duplicate_count",
    "skipped_cash_count",
    "win_rate",
    "avg_trade_return",
    "avg_position_notional",
]

LHB_CUTOFF_AUDIT_COLUMNS = [
    "path",
    "file_role",
    "row_count",
    "date_columns",
    "actual_min_date",
    "actual_max_date",
    "requested_start_date",
    "requested_end_date",
    "issue_code",
    "severity",
    "message",
]

LHB_CUTOFF_AUDIT_SUMMARY_COLUMNS = [
    "status",
    "strict",
    "requested_start_date",
    "requested_end_date",
    "input_file_count",
    "issue_count",
    "error_count",
    "warning_count",
]

LHB_PHASE16_LOW_QUALITY_COLUMNS = [
    "diagnostic_group",
    "diagnostic_type",
    "closed_trade_count",
    "win_rate",
    "loss_rate",
    "avg_realized_return",
    "avg_exit_5d_return",
    "avg_missed_return_vs_5d",
    "avg_max_drawdown_to_5d",
    "bad_trade_count",
]

LHB_PHASE16_EXIT_MISTAKE_COLUMNS = [
    "trade_date",
    "ts_code",
    "top_n",
    "phase12a_rule_layer",
    "exit_signal",
    "exit_reason",
    "exit_trade_date",
    "realized_return",
    "exit_5d_return",
    "missed_return_vs_5d",
    "max_drawdown_to_5d",
    "exit_mistake_type",
]

LHB_PHASE16_FILTER_SCAN_COLUMNS = [
    "filter_profile",
    "description",
    "entry_count",
    "closed_trade_count",
    "win_rate",
    "avg_realized_return",
    "final_equity",
    "max_drawdown",
    "account_final_equity",
    "account_max_drawdown",
]

LHB_PHASE16B_OPPORTUNITY_COLUMNS = [
    "trade_date",
    "ts_code",
    "top_n",
    "phase12a_rule_layer",
    "entry_trade_date",
    "exit_trade_date",
    "realized_return",
    "exit_1d_return",
    "exit_2d_return",
    "exit_3d_return",
    "exit_5d_return",
    "missed_return_to_1d",
    "missed_return_to_2d",
    "missed_return_to_3d",
    "missed_return_to_5d",
    "max_drawdown_to_5d",
    "selection_score",
    "lhb_net_buy_ratio",
    "candidate_profile",
]

LHB_PHASE16B_STRATEGY_SUMMARY_COLUMNS = [
    "strategy",
    "trade_count",
    "win_rate",
    "avg_return",
    "median_return",
    "worst_return",
    "best_return",
    "avg_missed_vs_current",
    "final_equity",
    "max_drawdown",
]

LHB_PHASE16B_CANDIDATE_SUMMARY_COLUMNS = [
    "candidate_profile",
    "trade_count",
    "win_rate",
    "avg_realized_return",
    "avg_exit_2d_return",
    "avg_exit_5d_return",
    "avg_missed_return_to_2d",
    "avg_missed_return_to_5d",
]

LHB_PHASE16C_ADJUSTED_TRADE_COLUMNS = [
    "rule_profile",
    "trade_date",
    "ts_code",
    "top_n",
    "phase12a_rule_layer",
    "fill_status",
    "exit_signal",
    "original_realized_return",
    "realized_return",
    "phase16c_adjust_reason",
    "selection_score",
    "lhb_net_buy_ratio",
]

LHB_PHASE16C_RULE_SCAN_SUMMARY_COLUMNS = [
    "rule_profile",
    "description",
    "entry_count",
    "closed_trade_count",
    "adjusted_trade_count",
    "win_rate",
    "avg_realized_return",
    "median_realized_return",
    "worst_realized_return",
    "best_realized_return",
    "final_equity",
    "max_drawdown",
    "account_final_equity",
    "account_max_drawdown",
]

LHB_PHASE16D_INDICATOR_DETAIL_COLUMNS = [
    "trade_date",
    "ts_code",
    "top_n",
    "phase12a_rule_layer",
    "entry_trade_date",
    "exit_trade_date",
    "realized_return",
    "exit_3d_return",
    "exit_5d_return",
    "missed_return_to_3d",
    "hold_label",
    "exit_day_close_vs_vwap",
    "exit_day_close_position",
    "exit_day_high_to_close_drawdown",
    "exit_day_close_vs_entry",
    "next_morning_return",
    "next_morning_close_vs_vwap",
    "selection_score",
    "lhb_net_buy_ratio",
]

LHB_PHASE16D_INDICATOR_SUMMARY_COLUMNS = [
    "indicator_rule",
    "matched_count",
    "good_hold_count",
    "should_exit_count",
    "good_hold_rate",
    "avg_missed_return_to_3d",
    "avg_realized_return",
]

LHB_PHASE16E_ADJUSTED_TRADE_COLUMNS = [
    "rule_profile",
    "trade_date",
    "ts_code",
    "top_n",
    "phase12a_rule_layer",
    "fill_status",
    "exit_signal",
    "original_realized_return",
    "realized_return",
    "phase16e_adjust_reason",
    "exit_day_close_vs_vwap",
    "next_morning_close_vs_vwap",
    "selection_score",
    "lhb_net_buy_ratio",
]

LHB_PHASE16E_RULE_SCAN_SUMMARY_COLUMNS = [
    "rule_profile",
    "description",
    "entry_count",
    "closed_trade_count",
    "adjusted_trade_count",
    "win_rate",
    "avg_realized_return",
    "median_realized_return",
    "worst_realized_return",
    "best_realized_return",
    "final_equity",
    "max_drawdown",
    "account_final_equity",
    "account_max_drawdown",
]

LHB_PHASE13_SIGNAL_COLUMNS = [
    "trade_date",
    "t1_trade_date",
    "ts_code",
    "stock_name",
    "event_family",
    "prev_limit_up_streak",
    "event_close_position",
    "event_high_to_close_drawdown",
    "amount_vs_20d",
    "lhb_net_amount",
    "phase13_observe_signal",
    "phase13_observe_reason",
    "phase13_follow_signal",
    "phase13_follow_reason",
    "phase13_reject_signal",
    "phase13_reject_reason",
    "t1_midday_return",
    "t1_close_vs_vwap",
    "t1_final_close_position",
    "t1_weak_close_like",
    "t1_retreat_proxy",
    "post_5d_return",
    "post_5d_max_drawdown",
]

LHB_PHASE13B_SCORED_COLUMNS = LHB_PHASE13_SIGNAL_COLUMNS + [
    "phase13b_pool",
    "phase13b_score",
    "phase13b_rank",
]

LHB_PHASE13B_SUMMARY_COLUMNS = [
    "pool_mode",
    "top_n",
    "selected_count",
    "signal_day_count",
    "avg_daily_selected_count",
    "avg_post_5d_return",
    "win_rate_5d",
    "avg_post_5d_max_drawdown",
]

LHB_SHORTLINE_RULE_REGISTRY_COLUMNS = [
    "rule_id",
    "rule_scope",
    "lhb_shortline_rule_version",
    "rule_recommendation",
    "lhb_shortline_rule_confidence",
    "lhb_shortline_rule_sample_count",
    "calibration_reason",
    "watch_group",
    "lhb_behavior_type",
    "event_structure",
    "entry_window_v2",
    "mainline_flag",
    "short_market_state",
    "exit_signal",
    "exit_reason",
    "avg_future_5d_return",
    "win_rate_5d",
    "avg_future_5d_max_drawdown",
    "a_kill_rate_5d",
    "exit_hit_rate",
]

LHB_SHORTLINE_MANUAL_REVIEW_COLUMNS = [
    "trade_date",
    "ts_code",
    "stock_name",
    "watch_group",
    "watch_reason",
    "exit_signal",
    "exit_reason",
    "lhb_shortline_follow_rule_id",
    "lhb_shortline_exit_rule_id",
    "manual_follow_decision",
    "manual_exit_decision",
    "manual_decision_reason",
    "next_day_confirmation_review",
    "post_review_label",
    "operator_notes",
    "future_1d_return",
    "future_3d_return",
    "future_5d_return",
    "a_kill_within_5d",
    "second_wave_success",
]


def normalize_top_list_rows(frame: pd.DataFrame, *, source: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=TOP_LIST_COLUMNS)
    data = frame.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    data["ts_code"] = data["ts_code"].fillna("").astype(str).str.upper()
    data["source"] = source
    return data.reindex(columns=TOP_LIST_COLUMNS)


def normalize_top_inst_rows(frame: pd.DataFrame, *, source: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=TOP_INST_COLUMNS)
    data = frame.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    data["ts_code"] = data["ts_code"].fillna("").astype(str).str.upper()
    data["source"] = source
    return data.reindex(columns=TOP_INST_COLUMNS)


def normalize_top_list_rows_akshare(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=TOP_LIST_COLUMNS)
    data = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(frame["上榜日"], errors="coerce").dt.strftime("%Y-%m-%d"),
            "ts_code": frame["代码"].map(_code_to_ts_code),
            "name": frame.get("名称"),
            "close": frame.get("收盘价"),
            "pct_change": frame.get("涨跌幅"),
            "turnover_rate": frame.get("换手率"),
            "amount": frame.get("市场总成交额"),
            "l_sell": frame.get("龙虎榜卖出额"),
            "l_buy": frame.get("龙虎榜买入额"),
            "l_amount": frame.get("龙虎榜成交额"),
            "net_amount": frame.get("龙虎榜净买额"),
            "net_rate": frame.get("净买额占总成交比"),
            "amount_rate": frame.get("成交额占总成交比"),
            "float_values": frame.get("流通市值"),
            "reason": frame.get("上榜原因"),
            "source": "akshare",
        }
    )
    return data.reindex(columns=TOP_LIST_COLUMNS)


def normalize_top_inst_rows_akshare(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=TOP_INST_COLUMNS)
    data = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(frame["上榜日期"], errors="coerce").dt.strftime("%Y-%m-%d"),
            "ts_code": frame["代码"].map(_code_to_ts_code),
            "exalter": "机构汇总",
            "buy": frame.get("机构买入总额"),
            "buy_rate": None,
            "sell": frame.get("机构卖出总额"),
            "sell_rate": None,
            "net_buy": frame.get("机构买入净额"),
            "reason": frame.get("上榜原因"),
            "source": "akshare",
        }
    )
    return data.reindex(columns=TOP_INST_COLUMNS)


def build_tushare_client(token: str | None = None):
    actual_token = token or os.getenv("TUSHARE_TOKEN", "").strip()
    if not actual_token:
        raise RuntimeError("TUSHARE_TOKEN is required for LHB sample import")
    try:
        import tushare as ts
    except ImportError as exc:
        raise RuntimeError("tushare package is required for LHB sample import") from exc
    return ts.pro_api(actual_token)


def build_akshare_client():
    try:
        import akshare as ak
    except ImportError as exc:
        raise RuntimeError("akshare package is required for LHB sample import") from exc
    return ak


def fetch_lhb_sample(
    *,
    start_date: str,
    end_date: str,
    ts_codes: list[str] | None = None,
    client: Any = None,
    provider: str = "tushare",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    provider_name = str(provider or "tushare").strip().lower()
    if provider_name == "akshare":
        ak = client or build_akshare_client()
        top_list = normalize_top_list_rows_akshare(ak.stock_lhb_detail_em(start_date=_compact_date(start_date), end_date=_compact_date(end_date)))
        top_inst = normalize_top_inst_rows_akshare(ak.stock_lhb_jgmmtj_em(start_date=_compact_date(start_date), end_date=_compact_date(end_date)))
        if ts_codes:
            codes = {code.strip().upper() for code in ts_codes if code.strip()}
            top_list = top_list[top_list["ts_code"].isin(codes)].reset_index(drop=True)
            top_inst = top_inst[top_inst["ts_code"].isin(codes)].reset_index(drop=True)
        return top_list, top_inst

    pro = client or build_tushare_client()
    top_list_frames: list[pd.DataFrame] = []
    top_inst_frames: list[pd.DataFrame] = []
    codes = [code.strip().upper() for code in (ts_codes or []) if code.strip()]
    if codes:
        for code in codes:
            top_list_frames.append(pd.DataFrame(pro.top_list(ts_code=code, start_date=_compact_date(start_date), end_date=_compact_date(end_date))))
            top_inst_frames.append(pd.DataFrame(pro.top_inst(ts_code=code, start_date=_compact_date(start_date), end_date=_compact_date(end_date))))
    else:
        top_list_frames.append(pd.DataFrame(pro.top_list(start_date=_compact_date(start_date), end_date=_compact_date(end_date))))
        top_inst_frames.append(pd.DataFrame(pro.top_inst(start_date=_compact_date(start_date), end_date=_compact_date(end_date))))
    top_list = pd.concat(top_list_frames, ignore_index=True) if top_list_frames else pd.DataFrame()
    top_inst = pd.concat(top_inst_frames, ignore_index=True) if top_inst_frames else pd.DataFrame()
    return normalize_top_list_rows(top_list, source="tushare"), normalize_top_inst_rows(top_inst, source="tushare")


def upsert_lhb_sample(
    *,
    top_list: pd.DataFrame,
    top_inst: pd.DataFrame,
    service: str = SETTINGS.research_service,
) -> None:
    top_list_sql = """
        INSERT INTO market.lhb_top_list_daily (
            trade_date, ts_code, name, close, pct_change, turnover_rate, amount,
            l_sell, l_buy, l_amount, net_amount, net_rate, amount_rate, float_values,
            reason, source
        ) VALUES (
            %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (trade_date, ts_code, reason, source) DO UPDATE SET
            name = EXCLUDED.name,
            close = EXCLUDED.close,
            pct_change = EXCLUDED.pct_change,
            turnover_rate = EXCLUDED.turnover_rate,
            amount = EXCLUDED.amount,
            l_sell = EXCLUDED.l_sell,
            l_buy = EXCLUDED.l_buy,
            l_amount = EXCLUDED.l_amount,
            net_amount = EXCLUDED.net_amount,
            net_rate = EXCLUDED.net_rate,
            amount_rate = EXCLUDED.amount_rate,
            float_values = EXCLUDED.float_values,
            updated_at = now()
    """
    top_inst_sql = """
        INSERT INTO market.lhb_top_inst_daily (
            trade_date, ts_code, exalter, buy, buy_rate, sell, sell_rate, net_buy, reason, source
        ) VALUES (
            %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (trade_date, ts_code, exalter, source) DO UPDATE SET
            buy = EXCLUDED.buy,
            buy_rate = EXCLUDED.buy_rate,
            sell = EXCLUDED.sell,
            sell_rate = EXCLUDED.sell_rate,
            net_buy = EXCLUDED.net_buy,
            reason = EXCLUDED.reason,
            updated_at = now()
    """
    with connect(service) as conn:
        if not top_list.empty:
            execute_many(conn, top_list_sql, _top_list_rows(top_list))
        if not top_inst.empty:
            execute_many(conn, top_inst_sql, _top_inst_rows(top_inst))


def run_lhb_sample_import(
    *,
    start_date: str,
    end_date: str,
    ts_codes: list[str] | None,
    output_dir: str | Path,
    client: Any = None,
    provider: str = "tushare",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    top_list, top_inst = fetch_lhb_sample(
        start_date=start_date,
        end_date=end_date,
        ts_codes=ts_codes,
        client=client,
        provider=provider,
    )
    upsert_lhb_sample(top_list=top_list, top_inst=top_inst, service=service)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    top_list_path = out / "lhb_top_list_sample.csv"
    top_inst_path = out / "lhb_top_inst_sample.csv"
    top_list.to_csv(top_list_path, index=False)
    top_inst.to_csv(top_inst_path, index=False)
    return {
        "top_list": top_list,
        "top_inst": top_inst,
        "paths": {"top_list": str(top_list_path), "top_inst": str(top_inst_path)},
    }


def load_lhb_from_db(
    *,
    ts_codes: list[str] | None,
    start_date: str,
    end_date: str,
    service: str = SETTINGS.research_service,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    code_filter = ""
    params = [start_date, end_date]
    if ts_codes:
        placeholders = ",".join(["%s"] * len(ts_codes))
        code_filter = f"AND ts_code IN ({placeholders})"
        params.extend(ts_codes)
    top_list_sql = f"""
        SELECT trade_date::text, ts_code, name, close, pct_change, turnover_rate, amount,
               l_sell, l_buy, l_amount, net_amount, net_rate, amount_rate, float_values, reason, source
        FROM market.lhb_top_list_daily
        WHERE trade_date BETWEEN %s::date AND %s::date
          {code_filter}
        ORDER BY trade_date, ts_code
    """
    top_inst_sql = f"""
        SELECT trade_date::text, ts_code, exalter, buy, buy_rate, sell, sell_rate, net_buy, reason, source
        FROM market.lhb_top_inst_daily
        WHERE trade_date BETWEEN %s::date AND %s::date
          {code_filter}
        ORDER BY trade_date, ts_code
    """
    with connect(service) as conn:
        top_list = pd.DataFrame(fetch_all(conn, top_list_sql, params))
        top_inst = pd.DataFrame(fetch_all(conn, top_inst_sql, params))
    return top_list.reindex(columns=TOP_LIST_COLUMNS), top_inst.reindex(columns=TOP_INST_COLUMNS)


def build_lhb_event_features_daily(
    *,
    top_list: pd.DataFrame,
    top_inst: pd.DataFrame,
) -> pd.DataFrame:
    list_frame = top_list.copy().reindex(columns=TOP_LIST_COLUMNS)
    inst_frame = top_inst.copy().reindex(columns=TOP_INST_COLUMNS)
    list_frame = _normalize_date_code_frame(list_frame, "trade_date", "ts_code")
    inst_frame = _normalize_date_code_frame(inst_frame, "trade_date", "ts_code")

    key_columns = ["trade_date", "ts_code", "source"]
    keys: list[tuple[str, str, str]] = []
    if not list_frame.empty:
        keys.extend(list_frame[key_columns].drop_duplicates().itertuples(index=False, name=None))
    if not inst_frame.empty:
        keys.extend(inst_frame[key_columns].drop_duplicates().itertuples(index=False, name=None))
    unique_keys = sorted(set(keys))
    if not unique_keys:
        return pd.DataFrame(columns=LHB_EVENT_FEATURE_COLUMNS)

    rows: list[dict[str, Any]] = []
    for trade_date, ts_code, source in unique_keys:
        day_list = list_frame[
            (list_frame["trade_date"] == trade_date)
            & (list_frame["ts_code"] == ts_code)
            & (list_frame["source"] == source)
        ]
        day_inst = inst_frame[
            (inst_frame["trade_date"] == trade_date)
            & (inst_frame["ts_code"] == ts_code)
            & (inst_frame["source"] == source)
        ]
        amount = _numeric_scalar(day_list["amount"], aggregator="max")
        l_amount = _numeric_scalar(day_list["l_amount"], aggregator="max")
        lhb_net_buy_amount = _numeric_scalar(day_list["net_amount"], aggregator="max")
        lhb_buy_amount = _numeric_scalar(day_list["l_buy"], aggregator="max")
        lhb_sell_amount = _numeric_scalar(day_list["l_sell"], aggregator="max")
        pct_change = _numeric_scalar(day_list["pct_change"], aggregator="max")
        turnover_rate = _numeric_scalar(day_list["turnover_rate"], aggregator="max")
        net_rate = _numeric_scalar(day_list["net_rate"], aggregator="max")
        amount_rate = _numeric_scalar(day_list["amount_rate"], aggregator="max")
        institution_net_buy = _numeric_scalar(day_inst["net_buy"], aggregator="sum")
        repeat_3d = _repeat_on_list_count(list_frame, ts_code=ts_code, source=source, trade_date=trade_date, lookback_days=3)
        repeat_5d = _repeat_on_list_count(list_frame, ts_code=ts_code, source=source, trade_date=trade_date, lookback_days=5)
        lhb_net_buy_ratio = _coerce_ratio(net_rate)
        if lhb_net_buy_ratio is None:
            lhb_net_buy_ratio = _coerce_ratio((lhb_net_buy_amount / amount) if amount not in (None, 0) and lhb_net_buy_amount is not None else None, clamp=False)
        top_seat_concentration = _coerce_ratio(amount_rate)
        if top_seat_concentration is None:
            top_seat_concentration = _coerce_ratio((l_amount / amount) if amount not in (None, 0) and l_amount is not None else None)
        lhb_after_limit_up = bool(pct_change is not None and pct_change >= 9.5)
        lhb_after_break_limit = bool(
            not lhb_after_limit_up
            and repeat_3d >= 1
            and pct_change is not None
            and pct_change >= -3.0
        )
        lhb_after_reversal = bool(
            not lhb_after_limit_up
            and repeat_5d >= 1
            and pct_change is not None
            and pct_change >= 5.0
        )
        risk_score = 0.0
        if pct_change is not None and pct_change >= 9.5:
            risk_score += 0.30
        if amount_rate is not None and amount_rate >= 0.20:
            risk_score += 0.20
        if turnover_rate is not None and turnover_rate >= 20.0:
            risk_score += 0.20
        if lhb_net_buy_amount is not None and lhb_net_buy_amount < 0:
            risk_score += 0.20
        if repeat_3d <= 1:
            risk_score += 0.10
        rows.append(
            {
                "trade_date": trade_date,
                "ts_code": ts_code,
                "on_lhb": True,
                "lhb_reason": _join_unique(day_list["reason"]) or _join_unique(day_inst["reason"]),
                "lhb_net_buy_amount": lhb_net_buy_amount,
                "lhb_net_buy_ratio": lhb_net_buy_ratio,
                "lhb_buy_amount": lhb_buy_amount,
                "lhb_sell_amount": lhb_sell_amount,
                "institution_net_buy": institution_net_buy,
                "top_seat_concentration": top_seat_concentration,
                "repeat_on_list_count_3d": repeat_3d,
                "repeat_on_list_count_5d": repeat_5d,
                "lhb_after_limit_up": lhb_after_limit_up,
                "lhb_after_break_limit": lhb_after_break_limit,
                "lhb_after_reversal": lhb_after_reversal,
                "lhb_one_day_pump_risk": min(risk_score, 1.0),
                "source": source,
            }
        )
    features = pd.DataFrame(rows).reindex(columns=LHB_EVENT_FEATURE_COLUMNS)
    return features.sort_values(["trade_date", "ts_code", "source"]).reset_index(drop=True)


def upsert_lhb_event_features_daily(
    *,
    features: pd.DataFrame,
    service: str = SETTINGS.research_service,
) -> None:
    if features.empty:
        return
    sql = """
        INSERT INTO factor.lhb_event_features_daily (
            trade_date, ts_code, on_lhb, lhb_reason, lhb_net_buy_amount, lhb_net_buy_ratio,
            lhb_buy_amount, lhb_sell_amount, institution_net_buy, top_seat_concentration,
            repeat_on_list_count_3d, repeat_on_list_count_5d, lhb_after_limit_up,
            lhb_after_break_limit, lhb_after_reversal, lhb_one_day_pump_risk, source
        ) VALUES (
            %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (trade_date, ts_code, source) DO UPDATE SET
            on_lhb = EXCLUDED.on_lhb,
            lhb_reason = EXCLUDED.lhb_reason,
            lhb_net_buy_amount = EXCLUDED.lhb_net_buy_amount,
            lhb_net_buy_ratio = EXCLUDED.lhb_net_buy_ratio,
            lhb_buy_amount = EXCLUDED.lhb_buy_amount,
            lhb_sell_amount = EXCLUDED.lhb_sell_amount,
            institution_net_buy = EXCLUDED.institution_net_buy,
            top_seat_concentration = EXCLUDED.top_seat_concentration,
            repeat_on_list_count_3d = EXCLUDED.repeat_on_list_count_3d,
            repeat_on_list_count_5d = EXCLUDED.repeat_on_list_count_5d,
            lhb_after_limit_up = EXCLUDED.lhb_after_limit_up,
            lhb_after_break_limit = EXCLUDED.lhb_after_break_limit,
            lhb_after_reversal = EXCLUDED.lhb_after_reversal,
            lhb_one_day_pump_risk = EXCLUDED.lhb_one_day_pump_risk,
            updated_at = now()
    """
    with connect(service) as conn:
        execute_many(conn, sql, _event_feature_rows(features))


def run_lhb_event_features_build(
    *,
    start_date: str,
    end_date: str,
    ts_codes: list[str] | None,
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    top_list, top_inst = load_lhb_from_db(
        ts_codes=ts_codes or [],
        start_date=start_date,
        end_date=end_date,
        service=service,
    )
    features = build_lhb_event_features_daily(top_list=top_list, top_inst=top_inst)
    upsert_lhb_event_features_daily(features=features, service=service)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "lhb_event_features_daily_sample.csv"
    features.to_csv(path, index=False)
    return {"lhb_event_features": features, "paths": {"lhb_event_features": str(path)}}


def build_dragon_case_lhb_alignment_audit(
    curated: pd.DataFrame,
    top_list: pd.DataFrame,
    top_inst: pd.DataFrame,
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    features = build_lhb_event_features_daily(top_list=top_list, top_inst=top_inst)
    features = _normalize_date_code_frame(features, "trade_date", "ts_code")
    for record in curated.fillna("").to_dict("records"):
        ts_code = str(record.get("ts_code") or "").upper()
        case_type = str(record.get("case_type") or record.get("verified_case_type") or "")
        for event_type, field in [
            ("first_limit_up", "first_limit_up_date"),
            ("break_limit", "break_limit_date"),
            ("reversal", "reversal_date"),
            ("second_wave_start", "second_wave_start_date"),
            ("peak", "peak_date"),
            ("a_kill_start", "a_kill_start_date"),
        ]:
            event_date = str(record.get(field) or "").strip()
            if not event_date:
                continue
            rows_for_code = features[features["ts_code"] == ts_code] if not features.empty else pd.DataFrame(columns=LHB_EVENT_FEATURE_COLUMNS)
            on_date = rows_for_code[rows_for_code["trade_date"] == event_date]
            before = rows_for_code[(rows_for_code["trade_date"] < event_date) & (rows_for_code["trade_date"] >= _shift_date(event_date, -3))]
            after = rows_for_code[(rows_for_code["trade_date"] > event_date) & (rows_for_code["trade_date"] <= _shift_date(event_date, 3))]
            rows.append(
                {
                    "case_id": record.get("case_id"),
                    "ts_code": ts_code,
                    "stock_name": record.get("stock_name"),
                    "case_type": case_type,
                    "event_type": event_type,
                    "event_date": event_date,
                    "lhb_on_event_date": not on_date.empty,
                    "lhb_before_event_3d": not before.empty,
                    "lhb_after_event_3d": not after.empty,
                    "lhb_reason": str(on_date.iloc[0]["lhb_reason"]) if not on_date.empty else "",
                    "lhb_net_buy_amount": _float_or_none(on_date.iloc[0]["lhb_net_buy_amount"]) if not on_date.empty else None,
                    "institution_net_buy": _float_or_none(on_date.iloc[0]["institution_net_buy"]) if not on_date.empty else None,
                    "top_seat_concentration": _float_or_none(on_date.iloc[0]["top_seat_concentration"]) if not on_date.empty else None,
                    "repeat_on_list_count_3d": int(on_date.iloc[0]["repeat_on_list_count_3d"]) if not on_date.empty and pd.notna(on_date.iloc[0]["repeat_on_list_count_3d"]) else 0,
                    "repeat_on_list_count_5d": int(on_date.iloc[0]["repeat_on_list_count_5d"]) if not on_date.empty and pd.notna(on_date.iloc[0]["repeat_on_list_count_5d"]) else 0,
                    "lhb_one_day_pump_risk": _float_or_none(on_date.iloc[0]["lhb_one_day_pump_risk"]) if not on_date.empty else None,
                    "lhb_alignment_status": "matched" if (not on_date.empty or not before.empty or not after.empty) else "missing",
                }
            )
    audit = pd.DataFrame(rows).reindex(columns=LHB_ALIGNMENT_COLUMNS)
    result = {"alignment_audit": audit}
    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "dragon_case_lhb_alignment_audit_2024_2026.csv"
        audit.to_csv(path, index=False)
        result["paths"] = {"alignment_audit": str(path)}
    return result


def run_dragon_case_lhb_alignment_audit(
    *,
    curated_path: str | Path,
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    curated = pd.read_csv(curated_path, low_memory=False)
    ts_codes = sorted({str(value).upper() for value in curated.get("ts_code", pd.Series(dtype="object")).dropna().astype(str) if value})
    dates = []
    for field in ["first_limit_up_date", "break_limit_date", "reversal_date", "second_wave_start_date", "peak_date", "a_kill_start_date"]:
        if field in curated.columns:
            dates.extend([str(value) for value in curated[field].dropna().astype(str) if str(value).strip()])
    start_date = min(dates) if dates else "2024-01-01"
    end_date = max(dates) if dates else "2026-05-13"
    warnings: list[str] = []
    try:
        top_list, top_inst = load_lhb_from_db(ts_codes=ts_codes, start_date=start_date, end_date=end_date, service=service)
    except Exception as exc:
        if "lhb_top_list_daily" in str(exc) or "lhb_top_inst_daily" in str(exc):
            warnings.append(str(exc))
            top_list = pd.DataFrame(columns=TOP_LIST_COLUMNS)
            top_inst = pd.DataFrame(columns=TOP_INST_COLUMNS)
        else:
            raise
    result = build_dragon_case_lhb_alignment_audit(curated, top_list, top_inst, output_dir=output_dir)
    result["warnings"] = warnings
    return result


def build_dragon_case_lhb_summary_report(
    *,
    curated: pd.DataFrame,
    alignment_audit: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Any]:
    summary = _build_lhb_case_summary(alignment_audit)
    comparison = _build_lhb_case_comparison(curated, alignment_audit)
    report = _lhb_case_summary_report(summary=summary, comparison=comparison)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "dragon_case_lhb_summary_2024_2026.csv"
    comparison_path = out / "dragon_case_lhb_comparison_2024_2026.csv"
    report_path = out / "dragon_case_lhb_report_2024_2026.md"
    summary.to_csv(summary_path, index=False)
    comparison.to_csv(comparison_path, index=False)
    report_path.write_text(report, encoding="utf-8")
    return {
        "summary": summary,
        "comparison": comparison,
        "paths": {
            "summary": str(summary_path),
            "comparison": str(comparison_path),
            "markdown_report": str(report_path),
        },
    }


def run_dragon_case_lhb_summary_report(
    *,
    curated_path: str | Path,
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    curated = pd.read_csv(curated_path, low_memory=False)
    audit_result = run_dragon_case_lhb_alignment_audit(
        curated_path=curated_path,
        output_dir=output_dir,
        service=service,
    )
    result = build_dragon_case_lhb_summary_report(
        curated=curated,
        alignment_audit=audit_result["alignment_audit"],
        output_dir=output_dir,
    )
    result["alignment_audit"] = audit_result["alignment_audit"]
    result["warnings"] = audit_result.get("warnings", [])
    result["paths"]["alignment_audit"] = audit_result["paths"]["alignment_audit"]
    return result


def build_lhb_case_difference_report(
    *,
    curated: pd.DataFrame,
    lhb_features: pd.DataFrame,
    alignment_audit: pd.DataFrame,
    output_dir: str | Path,
    factor_review: pd.DataFrame | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    if curated.empty:
        warnings.append("curated case library is empty")
    if alignment_audit.empty:
        warnings.append("LHB alignment audit is empty")
    if lhb_features.empty:
        warnings.append("LHB event features are empty")
    factor_review = factor_review if factor_review is not None else pd.DataFrame()

    detail = _build_lhb_case_event_detail(curated, alignment_audit, factor_review, lhb_features=lhb_features)
    case_type_summary = _build_lhb_case_type_difference_summary(detail)
    event_window = _build_lhb_event_window_difference(curated, alignment_audit, lhb_features, factor_review)
    risk = _build_lhb_signal_effectiveness(detail, signal_kind="risk")
    positive = _build_lhb_signal_effectiveness(detail, signal_kind="positive")
    coverage = _build_lhb_case_coverage_summary(curated, alignment_audit)
    report = _lhb_case_difference_markdown(
        case_type_summary=case_type_summary,
        event_window=event_window,
        risk=risk,
        positive=positive,
        coverage=coverage,
        warnings=warnings,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "case_type_difference_summary": str(out / "lhb_case_type_difference_summary.csv"),
        "event_window_difference": str(out / "lhb_event_window_difference.csv"),
        "risk_signal_effectiveness": str(out / "lhb_risk_signal_effectiveness.csv"),
        "positive_signal_effectiveness": str(out / "lhb_positive_signal_effectiveness.csv"),
        "case_event_detail": str(out / "lhb_case_event_detail.csv"),
        "coverage_summary": str(out / "lhb_case_coverage_summary.csv"),
        "markdown_report": str(out / "lhb_case_difference_report.md"),
    }
    case_type_summary.to_csv(paths["case_type_difference_summary"], index=False)
    event_window.to_csv(paths["event_window_difference"], index=False)
    risk.to_csv(paths["risk_signal_effectiveness"], index=False)
    positive.to_csv(paths["positive_signal_effectiveness"], index=False)
    detail.to_csv(paths["case_event_detail"], index=False)
    coverage.to_csv(paths["coverage_summary"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "case_type_difference_summary": case_type_summary,
        "event_window_difference": event_window,
        "risk_signal_effectiveness": risk,
        "positive_signal_effectiveness": positive,
        "case_event_detail": detail,
        "coverage_summary": coverage,
        "warnings": warnings,
        "paths": paths,
    }


def run_lhb_case_difference_report(
    *,
    case_path: str | Path,
    lhb_features_path: str | Path,
    alignment_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    curated = pd.read_csv(case_path, low_memory=False)
    lhb_features = pd.read_csv(lhb_features_path, low_memory=False)
    alignment = pd.read_csv(alignment_path, low_memory=False)
    factor_path = Path(output_dir) / "dragon_case_factor_review_2024_2026.csv"
    factor_review = pd.read_csv(factor_path, low_memory=False) if factor_path.exists() else pd.DataFrame()
    return build_lhb_case_difference_report(
        curated=curated,
        lhb_features=lhb_features,
        alignment_audit=alignment,
        output_dir=output_dir,
        factor_review=factor_review,
    )


def build_lhb_risk_feature_diagnostics(
    *,
    curated: pd.DataFrame,
    lhb_features: pd.DataFrame,
    alignment_audit: pd.DataFrame,
    output_dir: str | Path,
    factor_review: pd.DataFrame | None = None,
    optional_diagnostics: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    factor_review = factor_review if factor_review is not None else pd.DataFrame()
    optional_diagnostics = optional_diagnostics or {}
    if curated.empty:
        warnings.append("curated case library is empty")
    if alignment_audit.empty:
        warnings.append("LHB alignment audit is empty")
    if not optional_diagnostics:
        warnings.append("Dragon diagnostics were not available; dragon risk cross table is empty")

    base_detail = _build_lhb_case_event_detail(
        curated,
        alignment_audit,
        factor_review,
        lhb_features=lhb_features,
    )
    risk_detail = _standardize_lhb_risk_features(base_detail)
    bucket = _build_lhb_risk_score_bucket_effectiveness(risk_detail)
    cross = _build_lhb_risk_failure_type_cross(risk_detail)
    dragon_cross = _build_lhb_dragon_risk_cross(risk_detail, optional_diagnostics)
    gaps = _build_lhb_coverage_gap_recommendations(risk_detail)
    report = _lhb_risk_feature_markdown(
        risk_detail=risk_detail,
        bucket=bucket,
        cross=cross,
        dragon_cross=dragon_cross,
        gaps=gaps,
        warnings=warnings,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "risk_feature_case_detail": str(out / "lhb_risk_feature_case_detail.csv"),
        "risk_score_bucket_effectiveness": str(out / "lhb_risk_score_bucket_effectiveness.csv"),
        "risk_failure_type_cross": str(out / "lhb_risk_failure_type_cross.csv"),
        "dragon_risk_cross_diagnostics": str(out / "lhb_dragon_risk_cross_diagnostics.csv"),
        "coverage_gap_recommendations": str(out / "lhb_coverage_gap_recommendations.csv"),
        "markdown_report": str(out / "lhb_risk_feature_diagnostics_report.md"),
    }
    risk_detail.to_csv(paths["risk_feature_case_detail"], index=False)
    bucket.to_csv(paths["risk_score_bucket_effectiveness"], index=False)
    cross.to_csv(paths["risk_failure_type_cross"], index=False)
    dragon_cross.to_csv(paths["dragon_risk_cross_diagnostics"], index=False)
    gaps.to_csv(paths["coverage_gap_recommendations"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "risk_feature_case_detail": risk_detail,
        "risk_score_bucket_effectiveness": bucket,
        "risk_failure_type_cross": cross,
        "dragon_risk_cross_diagnostics": dragon_cross,
        "coverage_gap_recommendations": gaps,
        "warnings": warnings,
        "paths": paths,
    }


def run_lhb_risk_feature_diagnostics(
    *,
    case_path: str | Path,
    lhb_features_path: str | Path,
    alignment_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    out = Path(output_dir)
    curated = pd.read_csv(case_path, low_memory=False)
    lhb_features = pd.read_csv(lhb_features_path, low_memory=False)
    alignment = pd.read_csv(alignment_path, low_memory=False)
    factor_path = out / "dragon_case_factor_review_2024_2026.csv"
    factor_review = pd.read_csv(factor_path, low_memory=False) if factor_path.exists() else pd.DataFrame()
    optional_paths = {
        "dragon_v1_3": out / "dragon_strategy_v1_3_diagnostics.csv",
        "dragon_v1_2": out / "dragon_strategy_v1_2_diagnostics.csv",
        "case_factor_snapshot": out / "dragon_case_factor_snapshot_2024_2026.csv",
    }
    optional_diagnostics = {
        name: pd.read_csv(path, low_memory=False)
        for name, path in optional_paths.items()
        if path.exists()
    }
    return build_lhb_risk_feature_diagnostics(
        curated=curated,
        lhb_features=lhb_features,
        alignment_audit=alignment,
        output_dir=output_dir,
        factor_review=factor_review,
        optional_diagnostics=optional_diagnostics,
    )


def build_lhb_follow_exit_replay_v1(
    *,
    curated: pd.DataFrame,
    lhb_features: pd.DataFrame,
    alignment_audit: pd.DataFrame,
    output_dir: str | Path,
    factor_review: pd.DataFrame | None = None,
    optional_diagnostics: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any]:
    risk_result = build_lhb_risk_feature_diagnostics(
        curated=curated,
        lhb_features=lhb_features,
        alignment_audit=alignment_audit,
        output_dir=output_dir,
        factor_review=factor_review,
        optional_diagnostics=optional_diagnostics,
    )
    replay_detail = _build_lhb_follow_exit_replay_detail(risk_result["risk_feature_case_detail"])
    effectiveness = _build_lhb_follow_exit_effectiveness(replay_detail)
    report = _lhb_follow_exit_markdown(
        replay_detail=replay_detail,
        effectiveness=effectiveness,
        warnings=risk_result.get("warnings", []),
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "replay_detail": str(out / "lhb_follow_exit_replay_v1_detail.csv"),
        "replay_effectiveness": str(out / "lhb_follow_exit_replay_v1_effectiveness.csv"),
        "markdown_report": str(out / "lhb_follow_exit_replay_v1_report.md"),
    }
    replay_detail.to_csv(paths["replay_detail"], index=False)
    effectiveness.to_csv(paths["replay_effectiveness"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "replay_detail": replay_detail,
        "replay_effectiveness": effectiveness,
        "warnings": risk_result.get("warnings", []),
        "paths": paths,
    }


def run_lhb_follow_exit_replay_v1(
    *,
    case_path: str | Path,
    lhb_features_path: str | Path,
    alignment_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    out = Path(output_dir)
    curated = pd.read_csv(case_path, low_memory=False)
    lhb_features = pd.read_csv(lhb_features_path, low_memory=False)
    alignment = pd.read_csv(alignment_path, low_memory=False)
    factor_path = out / "dragon_case_factor_review_2024_2026.csv"
    factor_review = pd.read_csv(factor_path, low_memory=False) if factor_path.exists() else pd.DataFrame()
    optional_paths = {
        "dragon_v1_3": out / "dragon_strategy_v1_3_diagnostics.csv",
        "dragon_v1_2": out / "dragon_strategy_v1_2_diagnostics.csv",
        "case_factor_snapshot": out / "dragon_case_factor_snapshot_2024_2026.csv",
    }
    optional_diagnostics = {
        name: pd.read_csv(path, low_memory=False)
        for name, path in optional_paths.items()
        if path.exists()
    }
    return build_lhb_follow_exit_replay_v1(
        curated=curated,
        lhb_features=lhb_features,
        alignment_audit=alignment,
        output_dir=output_dir,
        factor_review=factor_review,
        optional_diagnostics=optional_diagnostics,
    )


def build_lhb_shortline_event_replay_v1(
    *,
    curated: pd.DataFrame,
    lhb_features: pd.DataFrame,
    alignment_audit: pd.DataFrame,
    output_dir: str | Path,
    factor_review: pd.DataFrame | None = None,
    optional_diagnostics: dict[str, pd.DataFrame] | None = None,
    market_frame: pd.DataFrame | None = None,
) -> dict[str, Any]:
    risk_result = build_lhb_risk_feature_diagnostics(
        curated=curated,
        lhb_features=lhb_features,
        alignment_audit=alignment_audit,
        output_dir=output_dir,
        factor_review=factor_review,
        optional_diagnostics=optional_diagnostics,
    )
    event_replay = _build_lhb_shortline_event_replay_detail(
        risk_result["risk_feature_case_detail"],
        optional_diagnostics=optional_diagnostics or {},
        market_frame=market_frame if market_frame is not None else pd.DataFrame(),
    )
    report = _lhb_shortline_event_replay_markdown(
        event_replay=event_replay,
        warnings=risk_result.get("warnings", []),
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "event_replay": str(out / "lhb_shortline_event_replay_v1.csv"),
        "markdown_report": str(out / "lhb_shortline_event_replay_v1_report.md"),
    }
    event_replay.to_csv(paths["event_replay"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "event_replay": event_replay,
        "warnings": risk_result.get("warnings", []),
        "paths": paths,
    }


def run_lhb_shortline_event_replay_v1(
    *,
    case_path: str | Path,
    lhb_features_path: str | Path,
    alignment_path: str | Path,
    output_dir: str | Path,
    market_path: str | Path | None = None,
) -> dict[str, Any]:
    out = Path(output_dir)
    curated = pd.read_csv(case_path, low_memory=False)
    lhb_features = pd.read_csv(lhb_features_path, low_memory=False)
    alignment = pd.read_csv(alignment_path, low_memory=False)
    factor_path = out / "dragon_case_factor_review_2024_2026.csv"
    factor_review = pd.read_csv(factor_path, low_memory=False) if factor_path.exists() else pd.DataFrame()
    optional_paths = {
        "dragon_v1_3": out / "dragon_strategy_v1_3_diagnostics.csv",
        "dragon_v1_2": out / "dragon_strategy_v1_2_diagnostics.csv",
        "case_factor_snapshot": out / "dragon_case_factor_snapshot_2024_2026.csv",
    }
    optional_diagnostics = {
        name: pd.read_csv(path, low_memory=False)
        for name, path in optional_paths.items()
        if path.exists()
    }
    market_frame = pd.read_csv(market_path, low_memory=False) if market_path else pd.DataFrame()
    return build_lhb_shortline_event_replay_v1(
        curated=curated,
        lhb_features=lhb_features,
        alignment_audit=alignment,
        output_dir=output_dir,
        factor_review=factor_review,
        optional_diagnostics=optional_diagnostics,
        market_frame=market_frame,
    )


def build_lhb_follow_avoid_rule_audit_v1(
    *,
    event_replay: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Any]:
    replay = event_replay.copy()
    action_effectiveness = _build_lhb_follow_avoid_action_effectiveness(replay)
    rule_matrix = _build_lhb_follow_avoid_rule_matrix(replay)
    recommendations = _build_lhb_follow_avoid_rule_recommendations(rule_matrix)
    report = _lhb_follow_avoid_rule_audit_markdown(
        action_effectiveness=action_effectiveness,
        rule_matrix=rule_matrix,
        recommendations=recommendations,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "action_effectiveness": str(out / "lhb_follow_avoid_action_effectiveness_v1.csv"),
        "rule_matrix": str(out / "lhb_follow_avoid_rule_matrix_v1.csv"),
        "rule_recommendations": str(out / "lhb_follow_avoid_rule_recommendations_v1.csv"),
        "markdown_report": str(out / "lhb_follow_avoid_rule_audit_v1.md"),
    }
    action_effectiveness.to_csv(paths["action_effectiveness"], index=False)
    rule_matrix.to_csv(paths["rule_matrix"], index=False)
    recommendations.to_csv(paths["rule_recommendations"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "action_effectiveness": action_effectiveness,
        "rule_matrix": rule_matrix,
        "rule_recommendations": recommendations,
        "paths": paths,
    }


def run_lhb_follow_avoid_rule_audit_v1(
    *,
    event_replay_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    event_replay = pd.read_csv(event_replay_path, low_memory=False)
    return build_lhb_follow_avoid_rule_audit_v1(event_replay=event_replay, output_dir=output_dir)


def build_lhb_exit_rule_audit_v1(
    *,
    event_replay: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Any]:
    replay = event_replay.copy()
    exit_signal_effectiveness = _build_lhb_exit_signal_effectiveness(replay)
    exit_reason_effectiveness = _build_lhb_exit_reason_effectiveness(replay)
    false_positive_audit = _build_lhb_exit_false_positive_audit(replay)
    report = _lhb_exit_rule_audit_markdown(
        exit_signal_effectiveness=exit_signal_effectiveness,
        exit_reason_effectiveness=exit_reason_effectiveness,
        false_positive_audit=false_positive_audit,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "exit_signal_effectiveness": str(out / "lhb_exit_signal_effectiveness_v1.csv"),
        "exit_reason_effectiveness": str(out / "lhb_exit_reason_effectiveness_v1.csv"),
        "false_positive_audit": str(out / "lhb_exit_false_positive_audit_v1.csv"),
        "markdown_report": str(out / "lhb_exit_rule_audit_v1.md"),
    }
    exit_signal_effectiveness.to_csv(paths["exit_signal_effectiveness"], index=False)
    exit_reason_effectiveness.to_csv(paths["exit_reason_effectiveness"], index=False)
    false_positive_audit.to_csv(paths["false_positive_audit"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "exit_signal_effectiveness": exit_signal_effectiveness,
        "exit_reason_effectiveness": exit_reason_effectiveness,
        "false_positive_audit": false_positive_audit,
        "paths": paths,
    }


def run_lhb_exit_rule_audit_v1(
    *,
    event_replay_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    event_replay = pd.read_csv(event_replay_path, low_memory=False)
    return build_lhb_exit_rule_audit_v1(event_replay=event_replay, output_dir=output_dir)


def build_daily_lhb_shortline_watchlist_v1(
    *,
    event_replay: pd.DataFrame,
    rule_recommendations: pd.DataFrame,
    rule_registry: pd.DataFrame | None = None,
    trade_date: str,
    output_dir: str | Path,
) -> dict[str, Any]:
    watchlist = _build_daily_lhb_shortline_watchlist_frame(
        event_replay=event_replay,
        rule_recommendations=rule_recommendations,
        rule_registry=rule_registry if rule_registry is not None else pd.DataFrame(),
        trade_date=trade_date,
    )
    report = _daily_lhb_shortline_watchlist_markdown(watchlist=watchlist, trade_date=trade_date)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe_date = str(trade_date).replace("-", "")
    paths = {
        "watchlist": str(out / f"daily_lhb_shortline_watchlist_{safe_date}.csv"),
        "markdown_report": str(out / f"daily_lhb_shortline_watchlist_{safe_date}.md"),
    }
    watchlist.to_csv(paths["watchlist"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {"watchlist": watchlist, "paths": paths}


def run_daily_lhb_shortline_watchlist_v1(
    *,
    event_replay_path: str | Path,
    rule_recommendations_path: str | Path,
    trade_date: str,
    output_dir: str | Path,
    rule_registry_path: str | Path | None = None,
) -> dict[str, Any]:
    event_replay = pd.read_csv(event_replay_path, low_memory=False)
    rule_recommendations = pd.read_csv(rule_recommendations_path, low_memory=False)
    rule_registry = pd.read_csv(rule_registry_path, low_memory=False) if rule_registry_path else pd.DataFrame()
    return build_daily_lhb_shortline_watchlist_v1(
        event_replay=event_replay,
        rule_recommendations=rule_recommendations,
        rule_registry=rule_registry,
        trade_date=trade_date,
        output_dir=output_dir,
    )


def build_lhb_shortline_strategy_effectiveness_v1(
    *,
    event_replay: pd.DataFrame,
    output_dir: str | Path,
    daily_watchlist: pd.DataFrame | None = None,
    min_sample_count: int = 10,
) -> dict[str, Any]:
    detail = _build_lhb_shortline_strategy_effectiveness_detail(
        event_replay=event_replay,
        daily_watchlist=daily_watchlist if daily_watchlist is not None else pd.DataFrame(),
    )
    summary = _build_lhb_shortline_strategy_effectiveness_summary(
        detail,
        group_cols=["watch_group"],
        min_sample_count=min_sample_count,
    )
    follow_combo = _build_lhb_shortline_strategy_effectiveness_summary(
        detail[detail["watch_group"].isin(["follow_watch", "high_elasticity_watch"])],
        group_cols=[
            "watch_group",
            "lhb_behavior_type",
            "event_structure",
            "entry_window_v2",
            "mainline_flag",
            "short_market_state",
        ],
        min_sample_count=min_sample_count,
    )
    exit_combo = _build_lhb_shortline_exit_combo_effectiveness(
        detail,
        min_sample_count=min_sample_count,
    )
    report = _lhb_shortline_strategy_effectiveness_markdown(
        summary=summary,
        follow_combo=follow_combo,
        exit_combo=exit_combo,
        min_sample_count=min_sample_count,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "detail": str(out / "lhb_shortline_strategy_effectiveness_detail_v1.csv"),
        "summary": str(out / "lhb_shortline_strategy_effectiveness_summary_v1.csv"),
        "follow_combo_effectiveness": str(out / "lhb_shortline_follow_combo_effectiveness_v1.csv"),
        "exit_combo_effectiveness": str(out / "lhb_shortline_exit_combo_effectiveness_v1.csv"),
        "markdown_report": str(out / "lhb_shortline_strategy_effectiveness_v1.md"),
    }
    detail.to_csv(paths["detail"], index=False)
    summary.to_csv(paths["summary"], index=False)
    follow_combo.to_csv(paths["follow_combo_effectiveness"], index=False)
    exit_combo.to_csv(paths["exit_combo_effectiveness"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "detail": detail,
        "summary": summary,
        "follow_combo_effectiveness": follow_combo,
        "exit_combo_effectiveness": exit_combo,
        "paths": paths,
    }


def run_lhb_shortline_strategy_effectiveness_v1(
    *,
    event_replay_path: str | Path,
    output_dir: str | Path,
    daily_watchlist_path: str | Path | None = None,
    min_sample_count: int = 10,
) -> dict[str, Any]:
    event_replay = pd.read_csv(event_replay_path, low_memory=False)
    daily_watchlist = pd.read_csv(daily_watchlist_path, low_memory=False) if daily_watchlist_path else pd.DataFrame()
    return build_lhb_shortline_strategy_effectiveness_v1(
        event_replay=event_replay,
        daily_watchlist=daily_watchlist,
        output_dir=output_dir,
        min_sample_count=min_sample_count,
    )


def build_lhb_shortline_shadow_backtest_v1(
    *,
    event_replay: pd.DataFrame,
    start_date: str,
    end_date: str,
    top_n_values: list[int],
    output_dir: str | Path,
    pool_mode: str = "strict_second_wave",
) -> dict[str, Any]:
    candidates = _build_lhb_shortline_shadow_backtest_candidates(
        event_replay=event_replay,
        start_date=start_date,
        end_date=end_date,
        pool_mode=pool_mode,
    )
    selected = _build_lhb_shortline_shadow_backtest_selected(candidates, top_n_values=top_n_values)
    daily_curve = _build_lhb_shortline_shadow_backtest_daily_curve(selected)
    summary = _build_lhb_shortline_shadow_backtest_summary(
        selected=selected,
        daily_curve=daily_curve,
        start_date=start_date,
        end_date=end_date,
        top_n_values=top_n_values,
        pool_mode=pool_mode,
    )
    report = _lhb_shortline_shadow_backtest_markdown(
        summary=summary,
        selected=selected,
        daily_curve=daily_curve,
        start_date=start_date,
        end_date=end_date,
        top_n_values=top_n_values,
        pool_mode=pool_mode,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe_start = str(start_date).replace("-", "")
    safe_end = str(end_date).replace("-", "")
    paths = {
        "summary": str(out / f"lhb_shortline_shadow_backtest_summary_{safe_start}_{safe_end}_v1.csv"),
        "selected_trades": str(out / f"lhb_shortline_shadow_backtest_selected_trades_{safe_start}_{safe_end}_v1.csv"),
        "daily_curve": str(out / f"lhb_shortline_shadow_backtest_daily_curve_{safe_start}_{safe_end}_v1.csv"),
        "markdown_report": str(out / f"lhb_shortline_shadow_backtest_{safe_start}_{safe_end}_v1.md"),
    }
    summary.to_csv(paths["summary"], index=False)
    selected.to_csv(paths["selected_trades"], index=False)
    daily_curve.to_csv(paths["daily_curve"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "summary": summary,
        "selected_trades": selected,
        "daily_curve": daily_curve,
        "paths": paths,
    }


def run_lhb_shortline_shadow_backtest_v1(
    *,
    event_replay_path: str | Path,
    start_date: str,
    end_date: str,
    top_n_values: list[int],
    output_dir: str | Path,
    pool_mode: str = "strict_second_wave",
) -> dict[str, Any]:
    event_replay = pd.read_csv(event_replay_path, low_memory=False)
    return build_lhb_shortline_shadow_backtest_v1(
        event_replay=event_replay,
        start_date=start_date,
        end_date=end_date,
        top_n_values=top_n_values,
        output_dir=output_dir,
        pool_mode=pool_mode,
    )


def build_lhb_shortline_intraday_confirmation_v1(
    *,
    candidates: pd.DataFrame,
    minute_bars: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Any]:
    detail = _build_lhb_shortline_intraday_confirmation_detail(
        candidates=candidates,
        minute_bars=minute_bars,
    )
    summary = _build_lhb_shortline_intraday_confirmation_summary(detail)
    report = _lhb_shortline_intraday_confirmation_markdown(detail=detail, summary=summary)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "detail": str(out / "lhb_shortline_intraday_confirmation_detail_v1.csv"),
        "summary": str(out / "lhb_shortline_intraday_confirmation_summary_v1.csv"),
        "markdown_report": str(out / "lhb_shortline_intraday_confirmation_v1.md"),
    }
    detail.to_csv(paths["detail"], index=False)
    summary.to_csv(paths["summary"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {"detail": detail, "summary": summary, "paths": paths}


def run_lhb_shortline_intraday_confirmation_v1(
    *,
    candidate_path: str | Path,
    minute_bars_path: str | Path,
    output_dir: str | Path,
    freq: str = "5min",
    adjust_type: str = "raw",
) -> dict[str, Any]:
    _ = (freq, adjust_type)
    candidates = pd.read_csv(candidate_path, low_memory=False)
    minute_bars = pd.read_csv(minute_bars_path, low_memory=False)
    return build_lhb_shortline_intraday_confirmation_v1(
        candidates=candidates,
        minute_bars=minute_bars,
        output_dir=output_dir,
    )


def build_lhb_full_market_pool_backtest_v1(
    *,
    lhb_features: pd.DataFrame,
    daily_bars: pd.DataFrame,
    start_date: str,
    end_date: str,
    top_n_values: list[int],
    output_dir: str | Path,
    pool_mode: str = "raw_lhb_positive",
) -> dict[str, Any]:
    candidates = _build_lhb_full_market_pool_candidates(
        lhb_features=lhb_features,
        daily_bars=daily_bars,
        start_date=start_date,
        end_date=end_date,
        pool_mode=pool_mode,
    )
    selected = _build_lhb_full_market_pool_selected(candidates, top_n_values=top_n_values)
    daily_curve = _build_lhb_shortline_shadow_backtest_daily_curve(selected)
    summary = _build_lhb_shortline_shadow_backtest_summary(
        selected=selected,
        daily_curve=daily_curve,
        start_date=start_date,
        end_date=end_date,
        top_n_values=top_n_values,
        pool_mode=pool_mode,
    )
    report = _lhb_full_market_pool_backtest_markdown(
        summary=summary,
        selected=selected,
        daily_curve=daily_curve,
        start_date=start_date,
        end_date=end_date,
        top_n_values=top_n_values,
        pool_mode=pool_mode,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe_start = str(start_date).replace("-", "")
    safe_end = str(end_date).replace("-", "")
    paths = {
        "summary": str(out / f"lhb_full_market_pool_summary_{safe_start}_{safe_end}_v1.csv"),
        "selected_trades": str(out / f"lhb_full_market_pool_selected_trades_{safe_start}_{safe_end}_v1.csv"),
        "daily_curve": str(out / f"lhb_full_market_pool_daily_curve_{safe_start}_{safe_end}_v1.csv"),
        "markdown_report": str(out / f"lhb_full_market_pool_backtest_{safe_start}_{safe_end}_v1.md"),
    }
    summary.to_csv(paths["summary"], index=False)
    selected.to_csv(paths["selected_trades"], index=False)
    daily_curve.to_csv(paths["daily_curve"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "summary": summary,
        "selected_trades": selected,
        "daily_curve": daily_curve,
        "paths": paths,
    }


def run_lhb_full_market_pool_backtest_v1(
    *,
    lhb_features_path: str | Path,
    daily_bars_path: str | Path,
    start_date: str,
    end_date: str,
    top_n_values: list[int],
    output_dir: str | Path,
    pool_mode: str = "raw_lhb_positive",
) -> dict[str, Any]:
    lhb_features = pd.read_csv(lhb_features_path, low_memory=False)
    daily_bars = pd.read_csv(daily_bars_path, low_memory=False)
    return build_lhb_full_market_pool_backtest_v1(
        lhb_features=lhb_features,
        daily_bars=daily_bars,
        start_date=start_date,
        end_date=end_date,
        top_n_values=top_n_values,
        pool_mode=pool_mode,
        output_dir=output_dir,
    )


def build_lhb_intraday_filtered_topn_comparison_v1(
    *,
    selected_trades: pd.DataFrame,
    intraday_detail: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Any]:
    joined = _join_lhb_intraday_actions(selected_trades, intraday_detail)
    comparison = _build_lhb_intraday_filtered_topn_comparison(joined)
    action_effectiveness = _build_lhb_intraday_action_effectiveness(joined)
    report = _lhb_intraday_filtered_topn_comparison_markdown(
        comparison=comparison,
        action_effectiveness=action_effectiveness,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "comparison": str(out / "lhb_intraday_filtered_topn_comparison_v1.csv"),
        "action_effectiveness": str(out / "lhb_intraday_action_effectiveness_v1.csv"),
        "markdown_report": str(out / "lhb_intraday_filtered_topn_comparison_v1.md"),
    }
    comparison.to_csv(paths["comparison"], index=False)
    action_effectiveness.to_csv(paths["action_effectiveness"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "comparison": comparison,
        "action_effectiveness": action_effectiveness,
        "joined": joined,
        "paths": paths,
    }


def run_lhb_intraday_filtered_topn_comparison_v1(
    *,
    selected_trades_path: str | Path,
    intraday_detail_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    selected_trades = pd.read_csv(selected_trades_path, low_memory=False)
    intraday_detail = pd.read_csv(intraday_detail_path, low_memory=False)
    return build_lhb_intraday_filtered_topn_comparison_v1(
        selected_trades=selected_trades,
        intraday_detail=intraday_detail,
        output_dir=output_dir,
    )


def build_lhb_phase12a_multi_context_decision_v1(
    *,
    selected_trades: pd.DataFrame,
    minute_bars: pd.DataFrame,
    intraday_detail: pd.DataFrame,
    output_dir: str | Path,
    pre_context_days: int = 2,
) -> dict[str, Any]:
    decision = _build_lhb_phase12a_decision_frame(
        selected_trades=selected_trades,
        minute_bars=minute_bars,
        intraday_detail=intraday_detail,
        pre_context_days=pre_context_days,
    )
    summary = _build_lhb_phase12a_decision_summary(decision)
    report = _lhb_phase12a_multi_context_decision_markdown(decision=decision, summary=summary)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "decision": str(out / "lhb_phase12a_multi_context_decision_v1.csv"),
        "summary": str(out / "lhb_phase12a_decision_summary_v1.csv"),
        "markdown_report": str(out / "lhb_phase12a_multi_context_decision_v1.md"),
    }
    decision.to_csv(paths["decision"], index=False)
    summary.to_csv(paths["summary"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {"decision": decision, "summary": summary, "paths": paths}


def run_lhb_phase12a_multi_context_decision_v1(
    *,
    selected_trades_path: str | Path,
    minute_bars_path: str | Path,
    intraday_detail_path: str | Path,
    output_dir: str | Path,
    pre_context_days: int = 2,
) -> dict[str, Any]:
    selected_trades = pd.read_csv(selected_trades_path, low_memory=False)
    minute_bars = pd.read_csv(minute_bars_path, low_memory=False)
    intraday_detail = pd.read_csv(intraday_detail_path, low_memory=False)
    return build_lhb_phase12a_multi_context_decision_v1(
        selected_trades=selected_trades,
        minute_bars=minute_bars,
        intraday_detail=intraday_detail,
        output_dir=output_dir,
        pre_context_days=pre_context_days,
    )


def build_lhb_phase12a_rule_decision_v1(
    *,
    phase12a_decision: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Any]:
    rule_decision = _build_lhb_phase12a_rule_decision_frame(phase12a_decision)
    summary = _build_lhb_phase12a_rule_summary(rule_decision)
    report = _lhb_phase12a_rule_markdown(rule_decision=rule_decision, summary=summary)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "rule_decision": str(out / "lhb_phase12a_rule_decision_v1.csv"),
        "summary": str(out / "lhb_phase12a_rule_summary_v1.csv"),
        "markdown_report": str(out / "lhb_phase12a_rule_v1.md"),
    }
    rule_decision.to_csv(paths["rule_decision"], index=False)
    summary.to_csv(paths["summary"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {"rule_decision": rule_decision, "summary": summary, "paths": paths}


def run_lhb_phase12a_rule_decision_v1(
    *,
    phase12a_decision_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    phase12a_decision = pd.read_csv(phase12a_decision_path, low_memory=False)
    return build_lhb_phase12a_rule_decision_v1(
        phase12a_decision=phase12a_decision,
        output_dir=output_dir,
    )


def build_lhb_phase12a_real_entry_backtest_v1(
    *,
    rule_decision: pd.DataFrame,
    minute_bars: pd.DataFrame,
    daily_bars: pd.DataFrame,
    output_dir: str | Path,
    entry_start_time: str = "10:30:00",
    slippage_bps: float = 0.0,
) -> dict[str, Any]:
    trades = _build_lhb_phase12a_real_entry_trades(
        rule_decision=rule_decision,
        minute_bars=minute_bars,
        daily_bars=daily_bars,
        entry_start_time=entry_start_time,
        slippage_bps=slippage_bps,
    )
    summary = _build_lhb_phase12a_real_entry_summary(trades)
    report = _lhb_phase12a_real_entry_backtest_markdown(trades=trades, summary=summary)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "trades": str(out / "lhb_phase12a_real_entry_trades_v1.csv"),
        "summary": str(out / "lhb_phase12a_real_entry_summary_v1.csv"),
        "markdown_report": str(out / "lhb_phase12a_real_entry_backtest_v1.md"),
    }
    trades.to_csv(paths["trades"], index=False)
    summary.to_csv(paths["summary"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {"trades": trades, "summary": summary, "paths": paths}


def run_lhb_phase12a_real_entry_backtest_v1(
    *,
    rule_decision_path: str | Path,
    minute_bars_path: str | Path,
    daily_bars_path: str | Path,
    output_dir: str | Path,
    entry_start_time: str = "10:30:00",
    slippage_bps: float = 0.0,
) -> dict[str, Any]:
    rule_decision = pd.read_csv(rule_decision_path, low_memory=False)
    minute_bars = pd.read_csv(minute_bars_path, low_memory=False)
    daily_bars = pd.read_csv(daily_bars_path, low_memory=False)
    return build_lhb_phase12a_real_entry_backtest_v1(
        rule_decision=rule_decision,
        minute_bars=minute_bars,
        daily_bars=daily_bars,
        output_dir=output_dir,
        entry_start_time=entry_start_time,
        slippage_bps=slippage_bps,
    )


def build_lhb_phase12b_signal_exit_v1(
    *,
    entry_trades: pd.DataFrame,
    minute_bars: pd.DataFrame,
    output_dir: str | Path,
    max_hold_days: int = 5,
) -> dict[str, Any]:
    exit_trades = _build_lhb_phase12b_signal_exit_trades(
        entry_trades=entry_trades,
        minute_bars=minute_bars,
        max_hold_days=max_hold_days,
    )
    summary = _build_lhb_phase12b_signal_exit_summary(exit_trades)
    report = _lhb_phase12b_signal_exit_markdown(exit_trades=exit_trades, summary=summary)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "exit_trades": str(out / "lhb_phase12b_signal_exit_trades_v1.csv"),
        "summary": str(out / "lhb_phase12b_signal_exit_summary_v1.csv"),
        "markdown_report": str(out / "lhb_phase12b_signal_exit_v1.md"),
    }
    exit_trades.to_csv(paths["exit_trades"], index=False)
    summary.to_csv(paths["summary"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {"exit_trades": exit_trades, "summary": summary, "paths": paths}


def run_lhb_phase12b_signal_exit_v1(
    *,
    entry_trades_path: str | Path,
    minute_bars_path: str | Path,
    output_dir: str | Path,
    max_hold_days: int = 5,
) -> dict[str, Any]:
    entry_trades = pd.read_csv(entry_trades_path, low_memory=False)
    minute_bars = pd.read_csv(minute_bars_path, low_memory=False)
    return build_lhb_phase12b_signal_exit_v1(
        entry_trades=entry_trades,
        minute_bars=minute_bars,
        output_dir=output_dir,
        max_hold_days=max_hold_days,
    )


def build_lhb_phase14_lifecycle_exit_v1(
    *,
    entry_trades: pd.DataFrame,
    minute_bars: pd.DataFrame,
    output_dir: str | Path,
    max_hold_days: int = 5,
) -> dict[str, Any]:
    lifecycle_trades = _build_lhb_phase14_lifecycle_exit_trades(
        entry_trades=entry_trades,
        minute_bars=minute_bars,
        max_hold_days=max_hold_days,
    )
    summary = _build_lhb_phase14_lifecycle_exit_summary(lifecycle_trades)
    report = _lhb_phase14_lifecycle_exit_markdown(lifecycle_trades=lifecycle_trades, summary=summary)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "lifecycle_trades": str(out / "lhb_phase14_lifecycle_exit_trades_v1.csv"),
        "summary": str(out / "lhb_phase14_lifecycle_exit_summary_v1.csv"),
        "markdown_report": str(out / "lhb_phase14_lifecycle_exit_v1.md"),
    }
    lifecycle_trades.to_csv(paths["lifecycle_trades"], index=False)
    summary.to_csv(paths["summary"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {"lifecycle_trades": lifecycle_trades, "summary": summary, "paths": paths}


def run_lhb_phase14_lifecycle_exit_v1(
    *,
    entry_trades_path: str | Path,
    minute_bars_path: str | Path,
    output_dir: str | Path,
    max_hold_days: int = 5,
) -> dict[str, Any]:
    entry_trades = pd.read_csv(entry_trades_path, low_memory=False)
    minute_bars = pd.read_csv(minute_bars_path, low_memory=False)
    return build_lhb_phase14_lifecycle_exit_v1(
        entry_trades=entry_trades,
        minute_bars=minute_bars,
        output_dir=output_dir,
        max_hold_days=max_hold_days,
    )


def build_lhb_phase14b_threshold_scan_v1(
    *,
    entry_trades: pd.DataFrame,
    minute_bars: pd.DataFrame,
    output_dir: str | Path,
    max_hold_days: int = 5,
) -> dict[str, Any]:
    scanned = _build_lhb_phase14b_threshold_scan_trades(
        entry_trades=entry_trades,
        minute_bars=minute_bars,
        max_hold_days=max_hold_days,
    )
    threshold_summary = _build_lhb_phase14b_threshold_summary(scanned)
    profile_ranking = _build_lhb_phase14b_profile_ranking(scanned)
    best_profile = str(profile_ranking.iloc[0]["threshold_profile"]) if not profile_ranking.empty else ""
    best_lifecycle_trades = scanned[scanned["threshold_profile"].eq(best_profile)].copy() if best_profile else scanned.head(0).copy()
    report = _lhb_phase14b_threshold_scan_markdown(
        profile_ranking=profile_ranking,
        threshold_summary=threshold_summary,
        best_lifecycle_trades=best_lifecycle_trades,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "profile_ranking": str(out / "lhb_phase14b_threshold_profile_ranking_v1.csv"),
        "threshold_summary": str(out / "lhb_phase14b_threshold_summary_v1.csv"),
        "best_lifecycle_trades": str(out / "lhb_phase14b_best_lifecycle_trades_v1.csv"),
        "markdown_report": str(out / "lhb_phase14b_threshold_scan_v1.md"),
    }
    profile_ranking.to_csv(paths["profile_ranking"], index=False)
    threshold_summary.to_csv(paths["threshold_summary"], index=False)
    best_lifecycle_trades.to_csv(paths["best_lifecycle_trades"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "profile_ranking": profile_ranking,
        "threshold_summary": threshold_summary,
        "best_lifecycle_trades": best_lifecycle_trades,
        "paths": paths,
    }


def run_lhb_phase14b_threshold_scan_v1(
    *,
    entry_trades_path: str | Path,
    minute_bars_path: str | Path,
    output_dir: str | Path,
    max_hold_days: int = 5,
) -> dict[str, Any]:
    entry_trades = pd.read_csv(entry_trades_path, low_memory=False)
    minute_bars = pd.read_csv(minute_bars_path, low_memory=False)
    return build_lhb_phase14b_threshold_scan_v1(
        entry_trades=entry_trades,
        minute_bars=minute_bars,
        output_dir=output_dir,
        max_hold_days=max_hold_days,
    )


def build_lhb_phase14c_lifecycle_portfolio_v1(
    *,
    entry_trades: pd.DataFrame,
    minute_bars: pd.DataFrame,
    output_dir: str | Path,
    max_hold_days: int = 5,
    threshold_profile: str = "sensitive_entry_buffer",
) -> dict[str, Any]:
    profile = _lhb_phase14b_profile_by_name(threshold_profile)
    thresholds = {key: value for key, value in profile.items() if key != "threshold_profile"}
    lifecycle_trades = _build_lhb_phase14_lifecycle_exit_trades(
        entry_trades=entry_trades,
        minute_bars=minute_bars,
        max_hold_days=max_hold_days,
        thresholds=thresholds,
    )
    lifecycle_trades.insert(0, "threshold_profile", str(profile["threshold_profile"]))
    daily_curve = _build_lhb_phase14c_daily_curve(lifecycle_trades)
    summary = _build_lhb_phase14c_portfolio_summary(
        lifecycle_trades=lifecycle_trades,
        daily_curve=daily_curve,
        threshold_profile=str(profile["threshold_profile"]),
    )
    report = _lhb_phase14c_lifecycle_portfolio_markdown(
        summary=summary,
        daily_curve=daily_curve,
        lifecycle_trades=lifecycle_trades,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "lifecycle_trades": str(out / "lhb_phase14c_lifecycle_trades_v1.csv"),
        "daily_curve": str(out / "lhb_phase14c_lifecycle_daily_curve_v1.csv"),
        "summary": str(out / "lhb_phase14c_lifecycle_portfolio_summary_v1.csv"),
        "markdown_report": str(out / "lhb_phase14c_lifecycle_portfolio_v1.md"),
    }
    lifecycle_trades.to_csv(paths["lifecycle_trades"], index=False)
    daily_curve.to_csv(paths["daily_curve"], index=False)
    summary.to_csv(paths["summary"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "lifecycle_trades": lifecycle_trades,
        "daily_curve": daily_curve,
        "summary": summary,
        "paths": paths,
    }


def run_lhb_phase14c_lifecycle_portfolio_v1(
    *,
    entry_trades_path: str | Path,
    minute_bars_path: str | Path,
    output_dir: str | Path,
    max_hold_days: int = 5,
    threshold_profile: str = "sensitive_entry_buffer",
) -> dict[str, Any]:
    entry_trades = pd.read_csv(entry_trades_path, low_memory=False)
    minute_bars = pd.read_csv(minute_bars_path, low_memory=False)
    return build_lhb_phase14c_lifecycle_portfolio_v1(
        entry_trades=entry_trades,
        minute_bars=minute_bars,
        output_dir=output_dir,
        max_hold_days=max_hold_days,
        threshold_profile=threshold_profile,
    )


def build_lhb_phase14e_limit_lock_filter_v1(
    *,
    entry_trades: pd.DataFrame,
    lifecycle_trades: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Any]:
    risk_audit = _build_lhb_phase14e_risk_audit(
        entry_trades=entry_trades,
        lifecycle_trades=lifecycle_trades,
    )
    scanned = _build_lhb_phase14e_filter_scan(lifecycle_trades)
    filter_ranking = _build_lhb_phase14e_filter_ranking(scanned)
    best_profile = str(filter_ranking.iloc[0]["filter_profile"]) if not filter_ranking.empty else ""
    best_trades = scanned[scanned["filter_profile"].eq(best_profile)].copy() if best_profile else scanned.head(0).copy()
    best_curve = _build_lhb_phase14c_daily_curve(best_trades)
    threshold_profile = _clean_lhb_reason(best_trades.get("threshold_profile", pd.Series([""])).dropna().iloc[0]) if not best_trades.empty and "threshold_profile" in best_trades.columns and best_trades["threshold_profile"].notna().any() else ""
    best_summary = _build_lhb_phase14c_portfolio_summary(
        lifecycle_trades=best_trades,
        daily_curve=best_curve,
        threshold_profile=threshold_profile,
    )
    report = _lhb_phase14e_limit_lock_filter_markdown(
        risk_audit=risk_audit,
        filter_ranking=filter_ranking,
        best_summary=best_summary,
        best_trades=best_trades,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "risk_audit": str(out / "lhb_phase14e_limit_lock_risk_audit_v1.csv"),
        "filter_ranking": str(out / "lhb_phase14e_filter_ranking_v1.csv"),
        "best_trades": str(out / "lhb_phase14e_best_trades_v1.csv"),
        "best_curve": str(out / "lhb_phase14e_best_daily_curve_v1.csv"),
        "best_summary": str(out / "lhb_phase14e_best_summary_v1.csv"),
        "markdown_report": str(out / "lhb_phase14e_limit_lock_filter_v1.md"),
    }
    risk_audit.to_csv(paths["risk_audit"], index=False)
    filter_ranking.to_csv(paths["filter_ranking"], index=False)
    best_trades.to_csv(paths["best_trades"], index=False)
    best_curve.to_csv(paths["best_curve"], index=False)
    best_summary.to_csv(paths["best_summary"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "risk_audit": risk_audit,
        "filter_ranking": filter_ranking,
        "best_trades": best_trades,
        "best_curve": best_curve,
        "best_summary": best_summary,
        "paths": paths,
    }


def run_lhb_phase14e_limit_lock_filter_v1(
    *,
    entry_trades_path: str | Path,
    lifecycle_trades_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    entry_trades = pd.read_csv(entry_trades_path, low_memory=False)
    lifecycle_trades = pd.read_csv(lifecycle_trades_path, low_memory=False)
    return build_lhb_phase14e_limit_lock_filter_v1(
        entry_trades=entry_trades,
        lifecycle_trades=lifecycle_trades,
        output_dir=output_dir,
    )


def build_lhb_phase15_cash_account_backtest_v1(
    *,
    lifecycle_trades: pd.DataFrame,
    output_dir: str | Path,
    max_positions: int = 10,
    position_pct: float = 0.10,
) -> dict[str, Any]:
    account_trades, account_curve = _build_lhb_phase15_cash_account_frames(
        lifecycle_trades=lifecycle_trades,
        max_positions=max_positions,
        position_pct=position_pct,
    )
    summary = _build_lhb_phase15_cash_account_summary(account_trades=account_trades, account_curve=account_curve)
    report = _lhb_phase15_cash_account_markdown(
        summary=summary,
        account_curve=account_curve,
        account_trades=account_trades,
        max_positions=max_positions,
        position_pct=position_pct,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "account_trades": str(out / "lhb_phase15_account_trades_v1.csv"),
        "account_curve": str(out / "lhb_phase15_account_curve_v1.csv"),
        "summary": str(out / "lhb_phase15_account_summary_v1.csv"),
        "markdown_report": str(out / "lhb_phase15_cash_account_backtest_v1.md"),
    }
    account_trades.to_csv(paths["account_trades"], index=False)
    account_curve.to_csv(paths["account_curve"], index=False)
    summary.to_csv(paths["summary"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "account_trades": account_trades,
        "account_curve": account_curve,
        "summary": summary,
        "paths": paths,
    }


def run_lhb_phase15_cash_account_backtest_v1(
    *,
    lifecycle_trades_path: str | Path,
    output_dir: str | Path,
    max_positions: int = 10,
    position_pct: float = 0.10,
    cutoff_start_date: str | None = None,
    cutoff_end_date: str | None = None,
    strict_cutoff_audit: bool = False,
    allow_phase14e_best: bool = False,
) -> dict[str, Any]:
    if cutoff_start_date or cutoff_end_date or strict_cutoff_audit:
        if not cutoff_start_date or not cutoff_end_date:
            raise ValueError("cutoff_start_date and cutoff_end_date are required when cutoff audit is enabled")
        audit = build_lhb_cutoff_audit_v1(
            paths=[lifecycle_trades_path],
            start_date=cutoff_start_date,
            end_date=cutoff_end_date,
            output_dir=Path(output_dir) / "cutoff_audit",
            strict=strict_cutoff_audit,
            forbid_phase14e_best=not allow_phase14e_best,
        )
        if strict_cutoff_audit and audit["status"] != "pass":
            raise ValueError(f"lhb_phase15_cutoff_audit_failed: {audit['paths']['audit']}")
    lifecycle_trades = pd.read_csv(lifecycle_trades_path, low_memory=False)
    return build_lhb_phase15_cash_account_backtest_v1(
        lifecycle_trades=lifecycle_trades,
        output_dir=output_dir,
        max_positions=max_positions,
        position_pct=position_pct,
    )


def build_lhb_cutoff_audit_v1(
    *,
    paths: list[str | Path],
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    strict: bool = True,
    forbid_phase14e_best: bool = True,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    requested_start = _date_string(start_date)
    requested_end = _date_string(end_date)
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            rows.append(
                _lhb_cutoff_audit_row(
                    path=path,
                    file_role=_lhb_cutoff_file_role(path),
                    row_count=0,
                    date_columns=[],
                    actual_min_date="",
                    actual_max_date="",
                    requested_start_date=requested_start,
                    requested_end_date=requested_end,
                    issue_code="file_missing",
                    severity="error",
                    message="Input file does not exist.",
                )
            )
            continue
        frame = pd.read_csv(path, low_memory=False)
        date_columns = _lhb_cutoff_date_columns(frame)
        min_date, max_date = _lhb_cutoff_date_range(frame, date_columns)
        role = _lhb_cutoff_file_role(path)
        if not date_columns:
            rows.append(
                _lhb_cutoff_audit_row(
                    path=path,
                    file_role=role,
                    row_count=len(frame),
                    date_columns=[],
                    actual_min_date="",
                    actual_max_date="",
                    requested_start_date=requested_start,
                    requested_end_date=requested_end,
                    issue_code="date_columns_missing",
                    severity="error",
                    message="No recognized date columns found.",
                )
            )
        else:
            if min_date and min_date < requested_start:
                rows.append(
                    _lhb_cutoff_audit_row(
                        path=path,
                        file_role=role,
                        row_count=len(frame),
                        date_columns=date_columns,
                        actual_min_date=min_date,
                        actual_max_date=max_date,
                        requested_start_date=requested_start,
                        requested_end_date=requested_end,
                        issue_code="date_before_requested_start",
                        severity="error",
                        message="At least one date value is before requested start_date.",
                    )
                )
            if max_date and max_date > requested_end:
                rows.append(
                    _lhb_cutoff_audit_row(
                        path=path,
                        file_role=role,
                        row_count=len(frame),
                        date_columns=date_columns,
                        actual_min_date=min_date,
                        actual_max_date=max_date,
                        requested_start_date=requested_start,
                        requested_end_date=requested_end,
                        issue_code="date_after_requested_end",
                        severity="error",
                        message="At least one date value is after requested end_date.",
                    )
                )
            if max_date and max_date < requested_end:
                rows.append(
                    _lhb_cutoff_audit_row(
                        path=path,
                        file_role=role,
                        row_count=len(frame),
                        date_columns=date_columns,
                        actual_min_date=min_date,
                        actual_max_date=max_date,
                        requested_start_date=requested_start,
                        requested_end_date=requested_end,
                        issue_code="date_coverage_shortfall",
                        severity="error",
                        message="Input max date is earlier than requested end_date.",
                    )
                )
        if forbid_phase14e_best and _lhb_cutoff_is_phase14e_best(path, frame):
            rows.append(
                _lhb_cutoff_audit_row(
                    path=path,
                    file_role=role,
                    row_count=len(frame),
                    date_columns=date_columns,
                    actual_min_date=min_date,
                    actual_max_date=max_date,
                    requested_start_date=requested_start,
                    requested_end_date=requested_end,
                    issue_code="phase14e_best_profile_in_sample_selection",
                    severity="error",
                    message="Phase14E best-trades output is selected by full-sample ranking and is not allowed for strict official backtests.",
                )
            )
    audit = pd.DataFrame(rows).reindex(columns=LHB_CUTOFF_AUDIT_COLUMNS)
    summary = _lhb_cutoff_audit_summary(
        audit,
        strict=strict,
        start_date=requested_start,
        end_date=requested_end,
        input_file_count=len(paths),
    )
    report = _lhb_cutoff_audit_markdown(audit=audit, summary=summary)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths_out = {
        "audit": str(out / "lhb_cutoff_audit_v1.csv"),
        "summary": str(out / "lhb_cutoff_audit_summary_v1.csv"),
        "markdown_report": str(out / "lhb_cutoff_audit_v1.md"),
    }
    audit.to_csv(paths_out["audit"], index=False)
    summary.to_csv(paths_out["summary"], index=False)
    Path(paths_out["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "status": str(summary.iloc[0]["status"]) if not summary.empty else "pass",
        "audit": audit,
        "summary": summary,
        "paths": paths_out,
    }


def run_lhb_cutoff_audit_v1(
    *,
    paths: list[str | Path],
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    strict: bool = True,
    forbid_phase14e_best: bool = True,
) -> dict[str, Any]:
    return build_lhb_cutoff_audit_v1(
        paths=paths,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
        strict=strict,
        forbid_phase14e_best=forbid_phase14e_best,
    )


def _lhb_cutoff_date_columns(frame: pd.DataFrame) -> list[str]:
    candidates = [
        "trade_date",
        "entry_trade_date",
        "exit_trade_date",
        "exit_signal_trade_date",
        "confirmation_trade_date",
        "signal_trade_date",
    ]
    return [column for column in candidates if column in frame.columns]


def _date_string(value: str) -> str:
    parsed = pd.to_datetime(value, errors="raise")
    return parsed.strftime("%Y-%m-%d")


def _lhb_cutoff_date_range(frame: pd.DataFrame, date_columns: list[str]) -> tuple[str, str]:
    values: list[pd.Series] = []
    for column in date_columns:
        values.append(pd.to_datetime(frame[column], errors="coerce", format="mixed"))
    if not values:
        return "", ""
    dates = pd.concat(values, ignore_index=True).dropna()
    if dates.empty:
        return "", ""
    return dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d")


def _lhb_cutoff_file_role(path: Path) -> str:
    name = path.name
    if "phase14e_best_trades" in name:
        return "phase14e_best_trades"
    if "phase15_account_trades" in name:
        return "phase15_account_trades"
    if "phase15_account_curve" in name:
        return "phase15_account_curve"
    if "phase14c_lifecycle_trades" in name:
        return "phase14c_lifecycle_trades"
    if "phase12a_real_entry_trades" in name:
        return "phase12a_real_entry_trades"
    return "lhb_input"


def _lhb_cutoff_is_phase14e_best(path: Path, frame: pd.DataFrame) -> bool:
    if "lhb_phase14e_best_trades" in path.name:
        return True
    if "filter_profile" not in frame.columns:
        return False
    profiles = {str(value) for value in frame["filter_profile"].dropna().unique()}
    return any(profile and profile != "baseline" for profile in profiles)


def _lhb_cutoff_audit_row(
    *,
    path: Path,
    file_role: str,
    row_count: int,
    date_columns: list[str],
    actual_min_date: str,
    actual_max_date: str,
    requested_start_date: str,
    requested_end_date: str,
    issue_code: str,
    severity: str,
    message: str,
) -> dict[str, Any]:
    return {
        "path": str(path),
        "file_role": file_role,
        "row_count": int(row_count),
        "date_columns": ",".join(date_columns),
        "actual_min_date": actual_min_date,
        "actual_max_date": actual_max_date,
        "requested_start_date": requested_start_date,
        "requested_end_date": requested_end_date,
        "issue_code": issue_code,
        "severity": severity,
        "message": message,
    }


def _lhb_cutoff_audit_summary(
    audit: pd.DataFrame,
    *,
    strict: bool,
    start_date: str,
    end_date: str,
    input_file_count: int,
) -> pd.DataFrame:
    severity = audit["severity"] if "severity" in audit.columns else pd.Series(dtype="object")
    error_count = int(severity.eq("error").sum())
    warning_count = int(severity.eq("warning").sum())
    status = "fail" if strict and error_count else "pass"
    return pd.DataFrame(
        [
            {
                "status": status,
                "strict": bool(strict),
                "requested_start_date": start_date,
                "requested_end_date": end_date,
                "input_file_count": int(input_file_count),
                "issue_count": int(len(audit)),
                "error_count": error_count,
                "warning_count": warning_count,
            }
        ],
        columns=LHB_CUTOFF_AUDIT_SUMMARY_COLUMNS,
    )


def _lhb_cutoff_audit_markdown(*, audit: pd.DataFrame, summary: pd.DataFrame) -> str:
    return "\n".join(
        [
            "# LHB Cutoff Audit V1",
            "",
            "## Summary",
            summary.to_markdown(index=False) if not summary.empty else "No summary.",
            "",
            "## Issues",
            audit.to_markdown(index=False) if not audit.empty else "No issues.",
            "",
        ]
    )


def _lhb_phase18c_select_topn(
    *,
    lifecycle_trades: pd.DataFrame,
    scored_candidates: pd.DataFrame,
    top_n: int,
    strategy: str,
) -> pd.DataFrame:
    trades = lifecycle_trades.copy().reset_index(names="original_order")
    trades["trade_date"] = pd.to_datetime(trades["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    trades["ts_code"] = trades["ts_code"].astype(str)
    if strategy == "auction_enhanced_rerank":
        scored = scored_candidates[["trade_date", "ts_code", "auction_enhanced_score"]].copy()
        scored["trade_date"] = pd.to_datetime(scored["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        scored["ts_code"] = scored["ts_code"].astype(str)
        trades = trades.merge(scored, on=["trade_date", "ts_code"], how="left")
        trades["auction_enhanced_score"] = pd.to_numeric(
            trades["auction_enhanced_score"], errors="coerce"
        ).fillna(-9999.0)
        ordered = trades.sort_values(
            ["trade_date", "auction_enhanced_score", "original_order"],
            ascending=[True, False, True],
            kind="stable",
        )
    elif strategy == "baseline_original_order":
        ordered = trades.sort_values(["trade_date", "original_order"], kind="stable")
    else:
        raise ValueError(f"Unsupported Phase18C strategy: {strategy}")
    selected = ordered.groupby("trade_date", group_keys=False).head(int(top_n)).copy()
    selected["phase18c_strategy"] = strategy
    selected["phase18c_top_n"] = int(top_n)
    selected["top_n"] = int(top_n)
    return selected


def build_lhb_phase18c_auction_enhanced_cash_account_backtest_v1(
    *,
    lifecycle_trades: pd.DataFrame,
    scored_candidates: pd.DataFrame,
    output_dir: str | Path,
    top_ns: list[int] | None = None,
    max_positions: int = 10,
    position_pct: float = 0.10,
    write_outputs: bool = True,
) -> dict[str, Any]:
    selected_top_ns = top_ns or [3, 5, 10]
    summary_frames: list[pd.DataFrame] = []
    account_trade_frames: list[pd.DataFrame] = []
    account_curve_frames: list[pd.DataFrame] = []
    selected_frames: list[pd.DataFrame] = []

    for top_n in selected_top_ns:
        for strategy in ["baseline_original_order", "auction_enhanced_rerank"]:
            selected = _lhb_phase18c_select_topn(
                lifecycle_trades=lifecycle_trades,
                scored_candidates=scored_candidates,
                top_n=top_n,
                strategy=strategy,
            )
            account_trades, account_curve = _build_lhb_phase15_cash_account_frames(
                lifecycle_trades=selected,
                max_positions=max_positions,
                position_pct=position_pct,
            )
            summary = _build_lhb_phase15_cash_account_summary(
                account_trades=account_trades,
                account_curve=account_curve,
            )
            for frame in [selected, account_trades, account_curve, summary]:
                frame["strategy"] = strategy
                frame["top_n"] = int(top_n)
            selected_frames.append(selected)
            account_trade_frames.append(account_trades)
            account_curve_frames.append(account_curve)
            summary_frames.append(summary)

    selected_trades = pd.concat(selected_frames, ignore_index=True) if selected_frames else pd.DataFrame()
    account_trades_all = pd.concat(account_trade_frames, ignore_index=True) if account_trade_frames else pd.DataFrame()
    account_curve_all = pd.concat(account_curve_frames, ignore_index=True) if account_curve_frames else pd.DataFrame()
    summary_all = pd.concat(summary_frames, ignore_index=True) if summary_frames else pd.DataFrame()
    summary_all = summary_all[
        ["strategy", "top_n"]
        + [column for column in summary_all.columns if column not in {"strategy", "top_n"}]
    ]

    out = Path(output_dir)
    paths = {
        "selected_trades": str(out / "lhb_phase18c_selected_trades_v1.csv"),
        "account_trades": str(out / "lhb_phase18c_account_trades_v1.csv"),
        "account_curve": str(out / "lhb_phase18c_account_curve_v1.csv"),
        "summary": str(out / "lhb_phase18c_summary_v1.csv"),
        "markdown_report": str(out / "lhb_phase18c_auction_enhanced_cash_account_v1.md"),
    }
    if write_outputs:
        out.mkdir(parents=True, exist_ok=True)
        selected_trades.to_csv(paths["selected_trades"], index=False)
        account_trades_all.to_csv(paths["account_trades"], index=False)
        account_curve_all.to_csv(paths["account_curve"], index=False)
        summary_all.to_csv(paths["summary"], index=False)
        report = "\n".join(
            [
                "# LHB Phase18C Auction Enhanced Cash Account V1",
                "",
                "## Summary",
                "",
                summary_all.to_markdown(index=False),
                "",
                "## Notes",
                "",
                "- Baseline uses the original daily candidate order.",
                "- Enhanced rerank uses Phase18B auction enhanced score.",
                "- Account simulation reuses Phase15 cash account constraints.",
            ]
        )
        Path(paths["markdown_report"]).write_text(report + "\n", encoding="utf-8")

    return {
        "selected_trades": selected_trades,
        "account_trades": account_trades_all,
        "account_curve": account_curve_all,
        "summary": summary_all,
        "paths": paths,
    }


def run_lhb_phase18c_auction_enhanced_cash_account_backtest_v1(
    *,
    lifecycle_trades_path: str | Path,
    scored_candidates_path: str | Path,
    output_dir: str | Path,
    top_ns: list[int] | None = None,
    max_positions: int = 10,
    position_pct: float = 0.10,
) -> dict[str, Any]:
    lifecycle_trades = pd.read_csv(lifecycle_trades_path, low_memory=False)
    scored_candidates = pd.read_csv(scored_candidates_path, low_memory=False)
    return build_lhb_phase18c_auction_enhanced_cash_account_backtest_v1(
        lifecycle_trades=lifecycle_trades,
        scored_candidates=scored_candidates,
        output_dir=output_dir,
        top_ns=top_ns,
        max_positions=max_positions,
        position_pct=position_pct,
    )


def build_lhb_phase18f_tradable_joint_exit_replay_v1(
    *,
    account_trades: pd.DataFrame,
    joint_state_detail: pd.DataFrame,
    close_lifecycle_detail: pd.DataFrame,
    minute_bars: pd.DataFrame,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    filled = account_trades.copy()
    if "account_trade_status" in filled.columns:
        filled = filled[filled["account_trade_status"].eq("filled")].copy()
    for column in ["trade_date", "entry_trade_date", "exit_trade_date"]:
        if column in filled.columns:
            filled[column] = pd.to_datetime(filled[column], errors="coerce").dt.strftime("%Y-%m-%d")
    filled["ts_code"] = filled.get("ts_code", pd.Series(dtype="object")).astype(str)
    filled["top_n"] = pd.to_numeric(filled.get("top_n", pd.Series(dtype="float64")), errors="coerce")
    filled["entry_price"] = pd.to_numeric(filled.get("entry_price", pd.Series(dtype="float64")), errors="coerce")
    filled["realized_return"] = pd.to_numeric(filled.get("realized_return", pd.Series(dtype="float64")), errors="coerce")
    if "strategy" not in filled.columns:
        filled["strategy"] = ""

    state = joint_state_detail.copy()
    if state.empty:
        state = pd.DataFrame(columns=["trade_date", "ts_code", "top_n", "strategy", "weak_open_confirm"])
    for column in ["trade_date"]:
        if column in state.columns:
            state[column] = pd.to_datetime(state[column], errors="coerce").dt.strftime("%Y-%m-%d")
    state["ts_code"] = state.get("ts_code", pd.Series(dtype="object")).astype(str)
    state["top_n"] = pd.to_numeric(state.get("top_n", pd.Series(dtype="float64")), errors="coerce")
    if "strategy" not in state.columns:
        state["strategy"] = ""
    if "weak_open_confirm" not in state.columns:
        state["weak_open_confirm"] = False
    state = state[["trade_date", "ts_code", "top_n", "strategy", "weak_open_confirm"]].drop_duplicates(
        ["trade_date", "ts_code", "top_n", "strategy"]
    )

    trades = filled.merge(
        state,
        on=["trade_date", "ts_code", "top_n", "strategy"],
        how="left",
    )
    trades["weak_open_confirm"] = trades["weak_open_confirm"].fillna(False).astype(bool)

    triggers = _build_lhb_phase18f_negative_close_triggers(close_lifecycle_detail)
    trades = trades.merge(
        triggers,
        on=["trade_date", "ts_code", "top_n", "strategy"],
        how="left",
    )

    bars = _normalize_lhb_phase18f_minute_bars(minute_bars)
    profiles = ["baseline_original_exit", "priority_exit_next_open_5min", "priority_exit_next_30m_vwap"]
    frames = []
    for profile in profiles:
        adjusted = trades.copy()
        adjusted["phase18f_exit_profile"] = profile
        adjusted["original_exit_trade_date"] = adjusted["exit_trade_date"]
        adjusted["original_exit_time"] = adjusted.get("exit_time", pd.Series("", index=adjusted.index))
        adjusted["original_exit_price"] = adjusted.get("exit_price", pd.Series(index=adjusted.index))
        adjusted["original_realized_return"] = adjusted["realized_return"]
        adjusted["phase18f_adjust_reason"] = ""
        adjusted["exit_time"] = ""
        if profile != "baseline_original_exit":
            adjusted = _apply_lhb_phase18f_priority_exit(
                trades=adjusted,
                minute_bars=bars,
                profile=profile,
            )
        adjusted["return_delta_vs_original"] = (
            pd.to_numeric(adjusted["realized_return"], errors="coerce")
            - pd.to_numeric(adjusted["original_realized_return"], errors="coerce")
        )
        frames.append(adjusted)

    adjusted_trades = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    summary = _build_lhb_phase18f_summary(adjusted_trades)
    report = _lhb_phase18f_markdown(summary=summary, adjusted_trades=adjusted_trades)

    paths: dict[str, str] = {}
    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        paths = {
            "adjusted_trades": str(out / "lhb_phase18f_tradable_joint_exit_adjusted_trades_v1.csv"),
            "summary": str(out / "lhb_phase18f_tradable_joint_exit_summary_v1.csv"),
            "markdown_report": str(out / "lhb_phase18f_tradable_joint_exit_replay_v1.md"),
        }
        adjusted_trades.to_csv(paths["adjusted_trades"], index=False)
        summary.to_csv(paths["summary"], index=False)
        Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "adjusted_trades": adjusted_trades,
        "summary": summary,
        "markdown_report": report,
        "paths": paths,
    }


def _build_lhb_phase18f_negative_close_triggers(close_lifecycle_detail: pd.DataFrame) -> pd.DataFrame:
    if close_lifecycle_detail.empty:
        return pd.DataFrame(
            columns=["trade_date", "ts_code", "top_n", "strategy", "phase18f_trigger_trade_date"]
        )
    frame = close_lifecycle_detail.copy()
    for column in ["trade_date", "entry_trade_date", "auction_trade_date"]:
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["ts_code"] = frame.get("ts_code", pd.Series(dtype="object")).astype(str)
    frame["top_n"] = pd.to_numeric(frame.get("top_n", pd.Series(dtype="float64")), errors="coerce")
    if "strategy" not in frame.columns:
        frame["strategy"] = ""
    frame["close_auction_return"] = pd.to_numeric(
        frame.get("close_auction_return", pd.Series(dtype="float64")),
        errors="coerce",
    )
    if "entry_trade_date" in frame.columns:
        frame = frame[frame["auction_trade_date"].ge(frame["entry_trade_date"])].copy()
    weak = frame[frame["close_auction_return"].lt(0)].copy()
    if weak.empty:
        return pd.DataFrame(
            columns=["trade_date", "ts_code", "top_n", "strategy", "phase18f_trigger_trade_date"]
        )
    trigger = (
        weak.sort_values(["trade_date", "ts_code", "top_n", "strategy", "auction_trade_date"], kind="stable")
        .groupby(["trade_date", "ts_code", "top_n", "strategy"], dropna=False)
        .first()
        .reset_index()
    )
    return trigger[
        ["trade_date", "ts_code", "top_n", "strategy", "auction_trade_date"]
    ].rename(columns={"auction_trade_date": "phase18f_trigger_trade_date"})


def _normalize_lhb_phase18f_minute_bars(minute_bars: pd.DataFrame) -> pd.DataFrame:
    bars = minute_bars.copy()
    if bars.empty:
        return pd.DataFrame(columns=["trade_date", "trade_time", "ts_code", "close", "volume", "amount"])
    for column in ["trade_date", "trade_time", "ts_code", "close", "volume", "amount"]:
        if column not in bars.columns:
            bars[column] = pd.NA
    bars["trade_date"] = pd.to_datetime(bars["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    bars["trade_time"] = pd.to_datetime(bars["trade_time"], errors="coerce")
    bars["ts_code"] = bars["ts_code"].astype(str)
    for column in ["close", "volume", "amount"]:
        bars[column] = pd.to_numeric(bars[column], errors="coerce")
    return bars.sort_values(["ts_code", "trade_date", "trade_time"], kind="stable").reset_index(drop=True)


def _apply_lhb_phase18f_priority_exit(
    *,
    trades: pd.DataFrame,
    minute_bars: pd.DataFrame,
    profile: str,
) -> pd.DataFrame:
    adjusted = trades.copy()
    for idx, row in adjusted.iterrows():
        if not bool(row.get("weak_open_confirm")):
            continue
        trigger_date = row.get("phase18f_trigger_trade_date")
        entry_date = row.get("entry_trade_date")
        original_exit_date = row.get("exit_trade_date")
        if pd.isna(trigger_date) or pd.isna(entry_date) or pd.isna(original_exit_date):
            continue
        ts_code = str(row.get("ts_code") or "")
        bars = minute_bars[minute_bars["ts_code"].eq(ts_code)]
        eligible_dates = sorted(
            date
            for date in bars["trade_date"].dropna().astype(str).unique().tolist()
            if date > str(entry_date) and date > str(trigger_date) and date <= str(original_exit_date)
        )
        if not eligible_dates:
            continue
        exit_date = eligible_dates[0]
        day_bars = bars[bars["trade_date"].eq(exit_date)].sort_values("trade_time", kind="stable")
        if day_bars.empty:
            continue
        if profile == "priority_exit_next_open_5min":
            exit_row = day_bars.iloc[0]
            exit_price = _coerce_numeric(exit_row.get("close"), 0.0)
            exit_time = pd.to_datetime(exit_row.get("trade_time")).strftime("%H:%M:%S")
        elif profile == "priority_exit_next_30m_vwap":
            first_bars = day_bars.head(6)
            amount = pd.to_numeric(first_bars.get("amount", pd.Series(dtype="float64")), errors="coerce").sum()
            volume = pd.to_numeric(first_bars.get("volume", pd.Series(dtype="float64")), errors="coerce").sum()
            exit_price = amount / volume if volume else pd.to_numeric(first_bars["close"], errors="coerce").mean()
            exit_time = pd.to_datetime(first_bars.iloc[-1].get("trade_time")).strftime("%H:%M:%S")
        else:
            continue
        if exit_date == str(original_exit_date):
            original_exit_time = str(row.get("original_exit_time") or "").strip()
            if not original_exit_time or original_exit_time.lower() == "nan" or exit_time >= original_exit_time:
                continue
        entry_price = _coerce_numeric(row.get("entry_price"), 0.0)
        if not entry_price or not exit_price:
            continue
        adjusted.loc[idx, "exit_trade_date"] = exit_date
        adjusted.loc[idx, "exit_time"] = exit_time
        adjusted.loc[idx, "exit_price"] = exit_price
        adjusted.loc[idx, "realized_return"] = exit_price / entry_price - 1.0
        adjusted.loc[idx, "phase18f_adjust_reason"] = "weak_open_plus_negative_close_auction"
    return adjusted


def _build_lhb_phase18f_summary(adjusted_trades: pd.DataFrame) -> pd.DataFrame:
    if adjusted_trades.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for profile, group in adjusted_trades.groupby("phase18f_exit_profile", sort=False):
        returns = pd.to_numeric(group.get("realized_return", pd.Series(dtype="float64")), errors="coerce").dropna()
        delta = pd.to_numeric(group.get("return_delta_vs_original", pd.Series(dtype="float64")), errors="coerce").dropna()
        adjusted_count = int(group.get("phase18f_adjust_reason", pd.Series(dtype="object")).astype(str).ne("").sum())
        rows.append(
            {
                "phase18f_exit_profile": profile,
                "trade_count": int(len(group)),
                "adjusted_trade_count": adjusted_count,
                "win_rate": float(returns.gt(0).mean()) if len(returns) else pd.NA,
                "avg_realized_return": float(returns.mean()) if len(returns) else pd.NA,
                "median_realized_return": float(returns.median()) if len(returns) else pd.NA,
                "worst_realized_return": float(returns.min()) if len(returns) else pd.NA,
                "best_realized_return": float(returns.max()) if len(returns) else pd.NA,
                "avg_return_delta_vs_original": float(delta.mean()) if len(delta) else pd.NA,
                "adjusted_avg_return_delta_vs_original": float(
                    pd.to_numeric(
                        group.loc[group.get("phase18f_adjust_reason", pd.Series(dtype="object")).astype(str).ne(""), "return_delta_vs_original"],
                        errors="coerce",
                    ).mean()
                )
                if adjusted_count
                else pd.NA,
            }
        )
    return pd.DataFrame(rows)


def _lhb_phase18f_markdown(*, summary: pd.DataFrame, adjusted_trades: pd.DataFrame) -> str:
    return "\n".join(
        [
            "# LHB Phase18F Tradable Joint Exit Replay v1",
            "",
            "This replay converts Phase18E joint weak signals into T+1-compliant 5min priority exits.",
            "",
            "## Summary",
            "",
            _table_preview(summary, rows=20),
            "",
            "## Adjusted Trades Preview",
            "",
            _table_preview(
                adjusted_trades[
                    adjusted_trades.get("phase18f_adjust_reason", pd.Series(dtype="object")).astype(str).ne("")
                ],
                rows=40,
            ),
            "",
        ]
    )


def load_lhb_phase18f_minute_bars(
    *,
    ts_codes: list[str],
    start_date: str,
    end_date: str,
    freq: str = "5min",
    adjust_type: str = "raw",
    research_service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    if not ts_codes:
        return pd.DataFrame()
    sql = """
    SELECT trade_date::text AS trade_date, trade_time, ts_code, open, high, low, close, volume, amount
    FROM market.stock_minute_bar
    WHERE ts_code = ANY(%s)
      AND trade_date BETWEEN %s AND %s
      AND freq = %s
      AND adjust_type = %s
    ORDER BY ts_code, trade_date, trade_time
    """
    with connect(research_service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, [sorted(set(ts_codes)), start_date, end_date, freq, adjust_type]))


def run_lhb_phase18f_tradable_joint_exit_replay_v1(
    *,
    account_trades_path: str | Path,
    joint_state_detail_path: str | Path,
    close_lifecycle_detail_path: str | Path,
    output_dir: str | Path,
    minute_bars_path: str | Path | None = None,
    selected_trades_path: str | Path | None = None,
    strategy: str | None = None,
    top_n: int | None = None,
    freq: str = "5min",
    adjust_type: str = "raw",
) -> dict[str, Any]:
    account_trades = pd.read_csv(account_trades_path, low_memory=False)
    if strategy and "strategy" in account_trades.columns:
        account_trades = account_trades[account_trades["strategy"].eq(strategy)].copy()
    if top_n is not None and "top_n" in account_trades.columns:
        account_trades = account_trades[pd.to_numeric(account_trades["top_n"], errors="coerce").eq(top_n)].copy()

    if selected_trades_path:
        selected = pd.read_csv(selected_trades_path, low_memory=False)
        if strategy and "strategy" in selected.columns:
            selected = selected[selected["strategy"].eq(strategy)].copy()
        if top_n is not None and "top_n" in selected.columns:
            selected = selected[pd.to_numeric(selected["top_n"], errors="coerce").eq(top_n)].copy()
        selected_cols = [
            column
            for column in ["trade_date", "ts_code", "top_n", "strategy", "exit_time", "exit_signal", "exit_reason"]
            if column in selected.columns
        ]
        selected = selected[selected_cols].copy()
        if not selected.empty:
            selected["trade_date"] = pd.to_datetime(selected["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
            selected["ts_code"] = selected["ts_code"].astype(str)
            selected["top_n"] = pd.to_numeric(selected["top_n"], errors="coerce")
            if "strategy" not in selected.columns:
                selected["strategy"] = ""
            account_trades["trade_date"] = pd.to_datetime(account_trades["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
            account_trades["ts_code"] = account_trades["ts_code"].astype(str)
            account_trades["top_n"] = pd.to_numeric(account_trades["top_n"], errors="coerce")
            if "strategy" not in account_trades.columns:
                account_trades["strategy"] = ""
            account_trades = account_trades.merge(
                selected.drop_duplicates(["trade_date", "ts_code", "top_n", "strategy"]),
                on=["trade_date", "ts_code", "top_n", "strategy"],
                how="left",
                suffixes=("", "_selected"),
            )

    joint_state = pd.read_csv(joint_state_detail_path, low_memory=False)
    if strategy and "strategy" in joint_state.columns:
        joint_state = joint_state[joint_state["strategy"].eq(strategy)].copy()
    if top_n is not None and "top_n" in joint_state.columns:
        joint_state = joint_state[pd.to_numeric(joint_state["top_n"], errors="coerce").eq(top_n)].copy()

    close_lifecycle = pd.read_csv(close_lifecycle_detail_path, low_memory=False)
    if strategy and "strategy" in close_lifecycle.columns:
        close_lifecycle = close_lifecycle[close_lifecycle["strategy"].eq(strategy)].copy()
    if top_n is not None and "top_n" in close_lifecycle.columns:
        close_lifecycle = close_lifecycle[
            pd.to_numeric(close_lifecycle["top_n"], errors="coerce").eq(top_n)
        ].copy()

    if minute_bars_path:
        minute_bars = pd.read_csv(minute_bars_path, low_memory=False)
    else:
        filled = account_trades[account_trades.get("account_trade_status", pd.Series(dtype="object")).eq("filled")].copy()
        ts_codes = filled.get("ts_code", pd.Series(dtype="object")).dropna().astype(str).unique().tolist()
        start = pd.to_datetime(filled.get("entry_trade_date", pd.Series(dtype="object")), errors="coerce").min()
        end = pd.to_datetime(filled.get("exit_trade_date", pd.Series(dtype="object")), errors="coerce").max()
        minute_bars = load_lhb_phase18f_minute_bars(
            ts_codes=ts_codes,
            start_date=start.strftime("%Y-%m-%d") if pd.notna(start) else "",
            end_date=end.strftime("%Y-%m-%d") if pd.notna(end) else "",
            freq=freq,
            adjust_type=adjust_type,
        )

    return build_lhb_phase18f_tradable_joint_exit_replay_v1(
        account_trades=account_trades,
        joint_state_detail=joint_state,
        close_lifecycle_detail=close_lifecycle,
        minute_bars=minute_bars,
        output_dir=output_dir,
    )


def build_lhb_phase16_quality_improvement_diagnostics_v1(
    *,
    lifecycle_trades: pd.DataFrame,
    real_entry_trades: pd.DataFrame,
    selected_trades: pd.DataFrame,
    output_dir: str | Path,
    min_group_count: int = 20,
) -> dict[str, Any]:
    merged = _build_lhb_phase16_merged_trade_frame(
        lifecycle_trades=lifecycle_trades,
        real_entry_trades=real_entry_trades,
        selected_trades=selected_trades,
    )
    low_quality = _build_lhb_phase16_low_quality_buy_diagnostics(merged, min_group_count=min_group_count)
    exit_mistakes = _build_lhb_phase16_exit_mistake_diagnostics(merged)
    filter_scan = _build_lhb_phase16_filter_scan(merged)
    report = _lhb_phase16_quality_improvement_markdown(
        low_quality=low_quality,
        exit_mistakes=exit_mistakes,
        filter_scan=filter_scan,
        min_group_count=min_group_count,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "low_quality_buy_diagnostics": str(out / "lhb_phase16_low_quality_buy_diagnostics_v1.csv"),
        "exit_mistake_diagnostics": str(out / "lhb_phase16_exit_mistake_diagnostics_v1.csv"),
        "filter_scan": str(out / "lhb_phase16_filter_scan_v1.csv"),
        "markdown_report": str(out / "lhb_phase16_quality_improvement_diagnostics_v1.md"),
    }
    low_quality.to_csv(paths["low_quality_buy_diagnostics"], index=False)
    exit_mistakes.to_csv(paths["exit_mistake_diagnostics"], index=False)
    filter_scan.to_csv(paths["filter_scan"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "low_quality_buy_diagnostics": low_quality,
        "exit_mistake_diagnostics": exit_mistakes,
        "filter_scan": filter_scan,
        "paths": paths,
    }


def run_lhb_phase16_quality_improvement_diagnostics_v1(
    *,
    lifecycle_trades_path: str | Path,
    real_entry_trades_path: str | Path,
    selected_trades_path: str | Path,
    output_dir: str | Path,
    min_group_count: int = 20,
) -> dict[str, Any]:
    lifecycle_trades = pd.read_csv(lifecycle_trades_path, low_memory=False)
    real_entry_trades = pd.read_csv(real_entry_trades_path, low_memory=False)
    selected_trades = pd.read_csv(selected_trades_path, low_memory=False)
    return build_lhb_phase16_quality_improvement_diagnostics_v1(
        lifecycle_trades=lifecycle_trades,
        real_entry_trades=real_entry_trades,
        selected_trades=selected_trades,
        output_dir=output_dir,
        min_group_count=min_group_count,
    )


def build_lhb_phase16b_limit_break_failed_exit_replay_v1(
    *,
    lifecycle_trades: pd.DataFrame,
    real_entry_trades: pd.DataFrame,
    selected_trades: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Any]:
    merged = _build_lhb_phase16_merged_trade_frame(
        lifecycle_trades=lifecycle_trades,
        real_entry_trades=real_entry_trades,
        selected_trades=selected_trades,
    )
    opportunity_trades = _build_lhb_phase16b_limit_break_failed_opportunities(merged)
    strategy_summary = _build_lhb_phase16b_limit_break_failed_strategy_summary(opportunity_trades)
    candidate_summary = _build_lhb_phase16b_limit_break_failed_candidate_summary(opportunity_trades)
    report = _lhb_phase16b_limit_break_failed_markdown(
        opportunity_trades=opportunity_trades,
        strategy_summary=strategy_summary,
        candidate_summary=candidate_summary,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "opportunity_trades": str(out / "lhb_phase16b_limit_break_failed_opportunity_trades_v1.csv"),
        "strategy_summary": str(out / "lhb_phase16b_limit_break_failed_strategy_summary_v1.csv"),
        "candidate_summary": str(out / "lhb_phase16b_limit_break_failed_candidate_summary_v1.csv"),
        "markdown_report": str(out / "lhb_phase16b_limit_break_failed_exit_replay_v1.md"),
    }
    opportunity_trades.to_csv(paths["opportunity_trades"], index=False)
    strategy_summary.to_csv(paths["strategy_summary"], index=False)
    candidate_summary.to_csv(paths["candidate_summary"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "opportunity_trades": opportunity_trades,
        "strategy_summary": strategy_summary,
        "candidate_summary": candidate_summary,
        "paths": paths,
    }


def run_lhb_phase16b_limit_break_failed_exit_replay_v1(
    *,
    lifecycle_trades_path: str | Path,
    real_entry_trades_path: str | Path,
    selected_trades_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    lifecycle_trades = pd.read_csv(lifecycle_trades_path, low_memory=False)
    real_entry_trades = pd.read_csv(real_entry_trades_path, low_memory=False)
    selected_trades = pd.read_csv(selected_trades_path, low_memory=False)
    return build_lhb_phase16b_limit_break_failed_exit_replay_v1(
        lifecycle_trades=lifecycle_trades,
        real_entry_trades=real_entry_trades,
        selected_trades=selected_trades,
        output_dir=output_dir,
    )


def build_lhb_phase16c_limit_break_failed_rule_scan_v1(
    *,
    lifecycle_trades: pd.DataFrame,
    real_entry_trades: pd.DataFrame,
    selected_trades: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Any]:
    merged = _build_lhb_phase16_merged_trade_frame(
        lifecycle_trades=lifecycle_trades,
        real_entry_trades=real_entry_trades,
        selected_trades=selected_trades,
    )
    adjusted_trades, summary = _build_lhb_phase16c_limit_break_failed_rule_scan_frames(merged)
    report = _lhb_phase16c_limit_break_failed_rule_scan_markdown(
        adjusted_trades=adjusted_trades,
        summary=summary,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "adjusted_trades": str(out / "lhb_phase16c_limit_break_failed_adjusted_trades_v1.csv"),
        "rule_scan_summary": str(out / "lhb_phase16c_limit_break_failed_rule_scan_summary_v1.csv"),
        "markdown_report": str(out / "lhb_phase16c_limit_break_failed_rule_scan_v1.md"),
    }
    adjusted_trades.to_csv(paths["adjusted_trades"], index=False)
    summary.to_csv(paths["rule_scan_summary"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "adjusted_trades": adjusted_trades,
        "rule_scan_summary": summary,
        "paths": paths,
    }


def run_lhb_phase16c_limit_break_failed_rule_scan_v1(
    *,
    lifecycle_trades_path: str | Path,
    real_entry_trades_path: str | Path,
    selected_trades_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    lifecycle_trades = pd.read_csv(lifecycle_trades_path, low_memory=False)
    real_entry_trades = pd.read_csv(real_entry_trades_path, low_memory=False)
    selected_trades = pd.read_csv(selected_trades_path, low_memory=False)
    return build_lhb_phase16c_limit_break_failed_rule_scan_v1(
        lifecycle_trades=lifecycle_trades,
        real_entry_trades=real_entry_trades,
        selected_trades=selected_trades,
        output_dir=output_dir,
    )


def build_lhb_phase16d_limit_break_failed_indicator_discovery_v1(
    *,
    lifecycle_trades: pd.DataFrame,
    real_entry_trades: pd.DataFrame,
    selected_trades: pd.DataFrame,
    minute_bars: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Any]:
    merged = _build_lhb_phase16_merged_trade_frame(
        lifecycle_trades=lifecycle_trades,
        real_entry_trades=real_entry_trades,
        selected_trades=selected_trades,
    )
    detail = _build_lhb_phase16d_indicator_detail(merged=merged, minute_bars=minute_bars)
    summary = _build_lhb_phase16d_indicator_summary(detail)
    report = _lhb_phase16d_indicator_discovery_markdown(detail=detail, summary=summary)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "indicator_detail": str(out / "lhb_phase16d_limit_break_failed_indicator_detail_v1.csv"),
        "indicator_summary": str(out / "lhb_phase16d_limit_break_failed_indicator_summary_v1.csv"),
        "markdown_report": str(out / "lhb_phase16d_limit_break_failed_indicator_discovery_v1.md"),
    }
    detail.to_csv(paths["indicator_detail"], index=False)
    summary.to_csv(paths["indicator_summary"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "indicator_detail": detail,
        "indicator_summary": summary,
        "paths": paths,
    }


def run_lhb_phase16d_limit_break_failed_indicator_discovery_v1(
    *,
    lifecycle_trades_path: str | Path,
    real_entry_trades_path: str | Path,
    selected_trades_path: str | Path,
    minute_bars_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    lifecycle_trades = pd.read_csv(lifecycle_trades_path, low_memory=False)
    real_entry_trades = pd.read_csv(real_entry_trades_path, low_memory=False)
    selected_trades = pd.read_csv(selected_trades_path, low_memory=False)
    minute_bars = pd.read_csv(minute_bars_path, low_memory=False)
    return build_lhb_phase16d_limit_break_failed_indicator_discovery_v1(
        lifecycle_trades=lifecycle_trades,
        real_entry_trades=real_entry_trades,
        selected_trades=selected_trades,
        minute_bars=minute_bars,
        output_dir=output_dir,
    )


def build_lhb_phase16e_limit_break_failed_indicator_rule_scan_v1(
    *,
    lifecycle_trades: pd.DataFrame,
    real_entry_trades: pd.DataFrame,
    selected_trades: pd.DataFrame,
    minute_bars: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Any]:
    merged = _build_lhb_phase16_merged_trade_frame(
        lifecycle_trades=lifecycle_trades,
        real_entry_trades=real_entry_trades,
        selected_trades=selected_trades,
    )
    indicator_detail = _build_lhb_phase16d_indicator_detail(merged=merged, minute_bars=minute_bars)
    adjusted_trades, summary = _build_lhb_phase16e_indicator_rule_scan_frames(
        merged=merged,
        indicator_detail=indicator_detail,
    )
    report = _lhb_phase16e_indicator_rule_scan_markdown(adjusted_trades=adjusted_trades, summary=summary)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "adjusted_trades": str(out / "lhb_phase16e_limit_break_failed_indicator_adjusted_trades_v1.csv"),
        "rule_scan_summary": str(out / "lhb_phase16e_limit_break_failed_indicator_rule_scan_summary_v1.csv"),
        "markdown_report": str(out / "lhb_phase16e_limit_break_failed_indicator_rule_scan_v1.md"),
    }
    adjusted_trades.to_csv(paths["adjusted_trades"], index=False)
    summary.to_csv(paths["rule_scan_summary"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "adjusted_trades": adjusted_trades,
        "rule_scan_summary": summary,
        "paths": paths,
    }


def run_lhb_phase16e_limit_break_failed_indicator_rule_scan_v1(
    *,
    lifecycle_trades_path: str | Path,
    real_entry_trades_path: str | Path,
    selected_trades_path: str | Path,
    minute_bars_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    lifecycle_trades = pd.read_csv(lifecycle_trades_path, low_memory=False)
    real_entry_trades = pd.read_csv(real_entry_trades_path, low_memory=False)
    selected_trades = pd.read_csv(selected_trades_path, low_memory=False)
    minute_bars = pd.read_csv(minute_bars_path, low_memory=False)
    return build_lhb_phase16e_limit_break_failed_indicator_rule_scan_v1(
        lifecycle_trades=lifecycle_trades,
        real_entry_trades=real_entry_trades,
        selected_trades=selected_trades,
        minute_bars=minute_bars,
        output_dir=output_dir,
    )


def build_lhb_phase13_two_stage_follow_pool_v1(
    *,
    event_features: pd.DataFrame,
    t1_features: pd.DataFrame | None,
    output_dir: str | Path,
) -> dict[str, Any]:
    decision = _build_lhb_phase13_two_stage_decision_frame(
        event_features=event_features,
        t1_features=t1_features,
    )
    observe_pool = decision[decision["phase13_observe_signal"].eq("observe_pool")].copy()
    follow_pool = decision[decision["phase13_follow_signal"].ne("")].copy()
    reject_pool = decision[decision["phase13_reject_signal"].ne("")].copy()
    summary = _build_lhb_phase13_two_stage_summary(
        decision=decision,
        observe_pool=observe_pool,
        follow_pool=follow_pool,
        reject_pool=reject_pool,
    )
    report = _lhb_phase13_two_stage_follow_pool_markdown(
        observe_pool=observe_pool,
        follow_pool=follow_pool,
        reject_pool=reject_pool,
        summary=summary,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "decision": str(out / "lhb_phase13_two_stage_decision_v1.csv"),
        "observe_pool": str(out / "lhb_phase13_observe_pool_v1.csv"),
        "follow_pool": str(out / "lhb_phase13_follow_pool_v1.csv"),
        "reject_pool": str(out / "lhb_phase13_reject_pool_v1.csv"),
        "summary": str(out / "lhb_phase13_two_stage_summary_v1.csv"),
        "markdown_report": str(out / "lhb_phase13_two_stage_follow_pool_v1.md"),
    }
    decision.to_csv(paths["decision"], index=False)
    observe_pool.to_csv(paths["observe_pool"], index=False)
    follow_pool.to_csv(paths["follow_pool"], index=False)
    reject_pool.to_csv(paths["reject_pool"], index=False)
    summary.to_csv(paths["summary"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "decision": decision,
        "observe_pool": observe_pool,
        "follow_pool": follow_pool,
        "reject_pool": reject_pool,
        "summary": summary,
        "paths": paths,
    }


def run_lhb_phase13_two_stage_follow_pool_v1(
    *,
    event_features_path: str | Path,
    t1_features_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    event_features = pd.read_csv(event_features_path, low_memory=False)
    t1_features = pd.read_csv(t1_features_path, low_memory=False)
    return build_lhb_phase13_two_stage_follow_pool_v1(
        event_features=event_features,
        t1_features=t1_features,
        output_dir=output_dir,
    )


def build_lhb_phase13b_topn_filter_v1(
    *,
    phase13_decision: pd.DataFrame,
    output_dir: str | Path,
    top_n_values: list[int] | tuple[int, ...] = (5, 10, 20),
) -> dict[str, Any]:
    scored = _build_lhb_phase13b_scored_frame(phase13_decision)
    selected = _build_lhb_phase13b_selected_topn(scored=scored, top_n_values=top_n_values)
    summary = _build_lhb_phase13b_summary(selected)
    report = _lhb_phase13b_topn_filter_markdown(scored=scored, selected=selected, summary=summary)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "scored": str(out / "lhb_phase13b_scored_v1.csv"),
        "selected": str(out / "lhb_phase13b_topn_selected_v1.csv"),
        "summary": str(out / "lhb_phase13b_topn_summary_v1.csv"),
        "markdown_report": str(out / "lhb_phase13b_topn_filter_v1.md"),
    }
    scored.to_csv(paths["scored"], index=False)
    selected.to_csv(paths["selected"], index=False)
    summary.to_csv(paths["summary"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {"scored": scored, "selected": selected, "summary": summary, "paths": paths}


def run_lhb_phase13b_topn_filter_v1(
    *,
    phase13_decision_path: str | Path,
    top_n: str = "5,10,20",
    output_dir: str | Path,
) -> dict[str, Any]:
    decision = pd.read_csv(phase13_decision_path, low_memory=False)
    top_n_values = [int(item.strip()) for item in str(top_n).split(",") if item.strip()]
    return build_lhb_phase13b_topn_filter_v1(
        phase13_decision=decision,
        top_n_values=top_n_values,
        output_dir=output_dir,
    )


def build_lhb_shortline_rule_calibration_v1(
    *,
    follow_combo: pd.DataFrame,
    exit_combo: pd.DataFrame,
    output_dir: str | Path,
    rule_version: str = "lhb_shortline_rules_v1_1",
    min_sample_count: int = 10,
) -> dict[str, Any]:
    rule_registry = _build_lhb_shortline_rule_registry(
        follow_combo=follow_combo,
        exit_combo=exit_combo,
        rule_version=rule_version,
        min_sample_count=min_sample_count,
    )
    report = _lhb_shortline_rule_calibration_markdown(
        rule_registry=rule_registry,
        rule_version=rule_version,
        min_sample_count=min_sample_count,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "rule_registry": str(out / "lhb_shortline_rule_registry_v1.csv"),
        "markdown_report": str(out / "lhb_shortline_rule_calibration_v1.md"),
    }
    rule_registry.to_csv(paths["rule_registry"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {"rule_registry": rule_registry, "paths": paths}


def run_lhb_shortline_rule_calibration_v1(
    *,
    follow_combo_path: str | Path,
    exit_combo_path: str | Path,
    output_dir: str | Path,
    rule_version: str = "lhb_shortline_rules_v1_1",
    min_sample_count: int = 10,
) -> dict[str, Any]:
    follow_combo = pd.read_csv(follow_combo_path, low_memory=False)
    exit_combo = pd.read_csv(exit_combo_path, low_memory=False)
    return build_lhb_shortline_rule_calibration_v1(
        follow_combo=follow_combo,
        exit_combo=exit_combo,
        output_dir=output_dir,
        rule_version=rule_version,
        min_sample_count=min_sample_count,
    )


def run_lhb_shortline_daily_pipeline_v1(
    *,
    case_path: str | Path,
    lhb_features_path: str | Path,
    alignment_path: str | Path,
    trade_date: str,
    output_dir: str | Path,
    market_path: str | Path | None = None,
    min_sample_count: int = 10,
    rule_version: str = "lhb_shortline_rules_v1_1",
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    event_replay_result = run_lhb_shortline_event_replay_v1(
        case_path=case_path,
        lhb_features_path=lhb_features_path,
        alignment_path=alignment_path,
        output_dir=out,
        market_path=market_path,
    )
    follow_audit = run_lhb_follow_avoid_rule_audit_v1(
        event_replay_path=event_replay_result["paths"]["event_replay"],
        output_dir=out,
    )
    exit_audit = run_lhb_exit_rule_audit_v1(
        event_replay_path=event_replay_result["paths"]["event_replay"],
        output_dir=out,
    )
    initial_daily = run_daily_lhb_shortline_watchlist_v1(
        event_replay_path=event_replay_result["paths"]["event_replay"],
        rule_recommendations_path=follow_audit["paths"]["rule_recommendations"],
        trade_date=trade_date,
        output_dir=out,
    )
    effectiveness = run_lhb_shortline_strategy_effectiveness_v1(
        event_replay_path=event_replay_result["paths"]["event_replay"],
        daily_watchlist_path=initial_daily["paths"]["watchlist"],
        min_sample_count=min_sample_count,
        output_dir=out,
    )
    calibration = run_lhb_shortline_rule_calibration_v1(
        follow_combo_path=effectiveness["paths"]["follow_combo_effectiveness"],
        exit_combo_path=effectiveness["paths"]["exit_combo_effectiveness"],
        rule_version=rule_version,
        min_sample_count=min_sample_count,
        output_dir=out,
    )
    calibrated_daily = run_daily_lhb_shortline_watchlist_v1(
        event_replay_path=event_replay_result["paths"]["event_replay"],
        rule_recommendations_path=follow_audit["paths"]["rule_recommendations"],
        rule_registry_path=calibration["paths"]["rule_registry"],
        trade_date=trade_date,
        output_dir=out,
    )
    safe_date = str(trade_date).replace("-", "")
    summary_path = out / f"lhb_shortline_daily_run_summary_{safe_date}.json"
    summary = {
        "trade_date": trade_date,
        "event_replay_rows": int(len(event_replay_result["event_replay"])),
        "follow_rule_recommendation_rows": int(len(follow_audit["rule_recommendations"])),
        "exit_signal_rows": int(len(exit_audit["exit_signal_effectiveness"])),
        "daily_watchlist_rows": int(len(calibrated_daily["watchlist"])),
        "rule_registry_rows": int(len(calibration["rule_registry"])),
        "warnings": event_replay_result.get("warnings", []),
    }
    paths = {
        "event_replay": event_replay_result["paths"]["event_replay"],
        "daily_watchlist": calibrated_daily["paths"]["watchlist"],
        "rule_registry": calibration["paths"]["rule_registry"],
        "effectiveness_report": effectiveness["paths"]["markdown_report"],
        "run_summary": str(summary_path),
    }
    summary_path.write_text(json.dumps({"summary": summary, "paths": paths}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"summary": summary, "paths": paths}


def build_lhb_shortline_manual_review_v1(
    *,
    daily_watchlist: pd.DataFrame,
    trade_date: str,
    output_dir: str | Path,
    effectiveness_detail: pd.DataFrame | None = None,
    manual_review: pd.DataFrame | None = None,
) -> dict[str, Any]:
    review = _build_lhb_shortline_manual_review_frame(
        daily_watchlist=daily_watchlist,
        effectiveness_detail=effectiveness_detail if effectiveness_detail is not None else pd.DataFrame(),
        manual_review=manual_review if manual_review is not None else pd.DataFrame(),
        trade_date=trade_date,
    )
    summary = _build_lhb_shortline_manual_review_summary(review)
    report = _lhb_shortline_manual_review_markdown(review=review, summary=summary, trade_date=trade_date)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe_date = str(trade_date).replace("-", "")
    paths = {
        "manual_review": str(out / f"lhb_shortline_manual_review_{safe_date}.csv"),
        "summary": str(out / "lhb_shortline_manual_review_summary_v1.csv"),
        "markdown_report": str(out / "lhb_shortline_manual_review_v1.md"),
    }
    review.to_csv(paths["manual_review"], index=False)
    summary.to_csv(paths["summary"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {"manual_review": review, "summary": summary, "paths": paths}


def run_lhb_shortline_manual_review_v1(
    *,
    daily_watchlist_path: str | Path,
    trade_date: str,
    output_dir: str | Path,
    effectiveness_detail_path: str | Path | None = None,
    manual_review_path: str | Path | None = None,
) -> dict[str, Any]:
    daily_watchlist = pd.read_csv(daily_watchlist_path, low_memory=False)
    effectiveness_detail = pd.read_csv(effectiveness_detail_path, low_memory=False) if effectiveness_detail_path else pd.DataFrame()
    manual_review = pd.read_csv(manual_review_path, low_memory=False) if manual_review_path else pd.DataFrame()
    return build_lhb_shortline_manual_review_v1(
        daily_watchlist=daily_watchlist,
        effectiveness_detail=effectiveness_detail,
        manual_review=manual_review,
        trade_date=trade_date,
        output_dir=output_dir,
    )


def build_lhb_diagnostics_after_failure_rule_v21(
    *,
    curated: pd.DataFrame,
    failure_v21_view: pd.DataFrame,
    lhb_features: pd.DataFrame,
    alignment_audit: pd.DataFrame,
    factor_review: pd.DataFrame,
    optional_diagnostics: dict[str, pd.DataFrame] | None,
    output_dir: str | Path,
) -> dict[str, Any]:
    warnings: list[str] = []
    optional_diagnostics = optional_diagnostics or {}
    curated_failure_v21 = _merge_failure_v21_view(curated, failure_v21_view)
    alignment_v21 = _apply_failure_v21_labels_to_alignment(alignment_audit, curated_failure_v21)
    detail = _build_lhb_case_event_detail(curated_failure_v21, alignment_v21, factor_review, lhb_features=lhb_features)
    case_type_summary = _build_lhb_case_type_difference_summary(detail)
    event_window = _build_lhb_event_window_difference(curated_failure_v21, alignment_v21, lhb_features, factor_review)
    coverage = _build_lhb_case_coverage_summary(curated_failure_v21, alignment_v21)
    risk_detail = _standardize_lhb_risk_features(detail)
    risk_bucket = _build_lhb_risk_score_bucket_effectiveness(risk_detail)
    risk_cross = _build_lhb_risk_failure_type_cross(risk_detail)
    dragon_cross = _build_lhb_dragon_risk_cross(risk_detail, optional_diagnostics)
    coverage_gaps = _build_lhb_coverage_gap_recommendations(risk_detail)
    transition_matrix = build_failure_event_rule_v21_transition_matrix(failure_v21_view)
    comparison = _build_lhb_v2_vs_v21_comparison(
        output_dir=output_dir,
        new_detail=detail,
        curated=curated,
        failure_v21_view=failure_v21_view,
    )
    report = _lhb_after_failure_rule_v21_markdown(
        transition_matrix=transition_matrix,
        case_type_summary=case_type_summary,
        risk_cross=risk_cross,
        comparison=comparison,
        warnings=warnings,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "curated_failure_v21": str(out / "dragon_case_curated_library_failure_v2_1.csv"),
        "transition_matrix": str(out / "failure_event_rule_v2_1_transition_matrix.csv"),
        "case_type_difference_summary": str(out / "lhb_case_type_difference_summary_v2_1.csv"),
        "event_window_difference": str(out / "lhb_event_window_difference_v2_1.csv"),
        "case_event_detail": str(out / "lhb_case_event_detail_v2_1.csv"),
        "coverage_summary": str(out / "lhb_case_coverage_summary_v2_1.csv"),
        "risk_feature_case_detail": str(out / "lhb_risk_feature_case_detail_v2_1.csv"),
        "risk_score_bucket_effectiveness": str(out / "lhb_risk_score_bucket_effectiveness_v2_1.csv"),
        "risk_failure_type_cross": str(out / "lhb_risk_failure_type_cross_v2_1.csv"),
        "dragon_risk_cross_diagnostics": str(out / "lhb_dragon_risk_cross_diagnostics_v2_1.csv"),
        "coverage_gap_recommendations": str(out / "lhb_coverage_gap_recommendations_v2_1.csv"),
        "comparison": str(out / "lhb_risk_diagnostics_v2_vs_v2_1_comparison.csv"),
        "markdown_report": str(out / "lhb_risk_diagnostics_after_failure_rule_v2_1_report.md"),
    }
    curated_failure_v21.to_csv(paths["curated_failure_v21"], index=False)
    transition_matrix.to_csv(paths["transition_matrix"], index=False)
    case_type_summary.to_csv(paths["case_type_difference_summary"], index=False)
    event_window.to_csv(paths["event_window_difference"], index=False)
    detail.to_csv(paths["case_event_detail"], index=False)
    coverage.to_csv(paths["coverage_summary"], index=False)
    risk_detail.to_csv(paths["risk_feature_case_detail"], index=False)
    risk_bucket.to_csv(paths["risk_score_bucket_effectiveness"], index=False)
    risk_cross.to_csv(paths["risk_failure_type_cross"], index=False)
    dragon_cross.to_csv(paths["dragon_risk_cross_diagnostics"], index=False)
    coverage_gaps.to_csv(paths["coverage_gap_recommendations"], index=False)
    comparison.to_csv(paths["comparison"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "curated_failure_v21": curated_failure_v21,
        "transition_matrix": transition_matrix,
        "case_type_difference_summary": case_type_summary,
        "event_window_difference": event_window,
        "case_event_detail": detail,
        "coverage_summary": coverage,
        "risk_feature_case_detail": risk_detail,
        "risk_score_bucket_effectiveness": risk_bucket,
        "risk_failure_type_cross": risk_cross,
        "dragon_risk_cross_diagnostics": dragon_cross,
        "coverage_gap_recommendations": coverage_gaps,
        "comparison": comparison,
        "warnings": warnings,
        "paths": paths,
    }


def run_lhb_diagnostics_after_failure_rule_v21(
    *,
    case_path: str | Path,
    failure_audit_path: str | Path,
    snapshot_path: str | Path,
    lhb_features_path: str | Path,
    alignment_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    out = Path(output_dir)
    curated = pd.read_csv(case_path, low_memory=False)
    failure_audit = pd.read_csv(failure_audit_path, low_memory=False)
    snapshot = pd.read_csv(snapshot_path, low_memory=False)
    lhb_features = pd.read_csv(lhb_features_path, low_memory=False)
    alignment = pd.read_csv(alignment_path, low_memory=False)
    factor_path = out / "dragon_case_factor_review_2024_2026.csv"
    factor_review = pd.read_csv(factor_path, low_memory=False) if factor_path.exists() else pd.DataFrame()
    optional_paths = {
        "dragon_v1_3": out / "dragon_strategy_v1_3_diagnostics.csv",
        "dragon_v1_2": out / "dragon_strategy_v1_2_diagnostics.csv",
        "case_factor_snapshot": out / "dragon_case_factor_snapshot_2024_2026.csv",
    }
    optional_diagnostics = {name: pd.read_csv(path, low_memory=False) for name, path in optional_paths.items() if path.exists()}
    failure_v21_view = build_failure_event_rule_v21_curated_view(
        curated=curated,
        case_factor_snapshot=snapshot,
        failure_rule_audit=failure_audit,
    )
    return build_lhb_diagnostics_after_failure_rule_v21(
        curated=curated,
        failure_v21_view=failure_v21_view,
        lhb_features=lhb_features,
        alignment_audit=alignment,
        factor_review=factor_review,
        optional_diagnostics=optional_diagnostics,
        output_dir=output_dir,
    )


def build_lhb_coverage_and_failure_rule_plan(
    *,
    coverage_gaps: pd.DataFrame,
    curated: pd.DataFrame,
    case_factor_snapshot: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Any]:
    warnings: list[str] = []
    if coverage_gaps.empty:
        warnings.append("LHB coverage gap recommendations are empty")
    if curated.empty:
        warnings.append("curated case library is empty")
    if case_factor_snapshot.empty:
        warnings.append("case factor snapshot is empty")

    plan = _build_lhb_coverage_expansion_plan(coverage_gaps)
    summary = _build_lhb_coverage_expansion_summary(coverage_gaps, plan)
    commands = _lhb_coverage_expansion_commands(plan)
    audit = _build_failure_event_rule_refinement_audit(curated, case_factor_snapshot)
    suggestions = _build_failure_event_rule_refinement_suggestions(curated, audit)
    report = _lhb_coverage_failure_plan_markdown(
        plan=plan,
        summary=summary,
        audit=audit,
        suggestions=suggestions,
        warnings=warnings,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "coverage_expansion_plan": str(out / "lhb_coverage_expansion_plan_2024_2026.csv"),
        "coverage_expansion_summary": str(out / "lhb_coverage_expansion_summary.csv"),
        "next_commands": str(out / "lhb_coverage_expansion_next_commands.sh"),
        "failure_rule_audit": str(out / "failure_event_rule_refinement_audit.csv"),
        "failure_rule_suggestions": str(out / "failure_event_rule_refinement_suggestions.csv"),
        "markdown_report": str(out / "lhb_coverage_and_failure_rule_plan_report.md"),
    }
    plan.to_csv(paths["coverage_expansion_plan"], index=False)
    summary.to_csv(paths["coverage_expansion_summary"], index=False)
    Path(paths["next_commands"]).write_text(commands, encoding="utf-8")
    audit.to_csv(paths["failure_rule_audit"], index=False)
    suggestions.to_csv(paths["failure_rule_suggestions"], index=False)
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return {
        "coverage_expansion_plan": plan,
        "coverage_expansion_summary": summary,
        "failure_rule_audit": audit,
        "failure_rule_suggestions": suggestions,
        "warnings": warnings,
        "paths": paths,
    }


def run_lhb_coverage_and_failure_rule_plan(
    *,
    coverage_gap_path: str | Path,
    case_path: str | Path,
    snapshot_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    coverage_gaps = pd.read_csv(coverage_gap_path, low_memory=False)
    curated = pd.read_csv(case_path, low_memory=False)
    snapshot = pd.read_csv(snapshot_path, low_memory=False)
    return build_lhb_coverage_and_failure_rule_plan(
        coverage_gaps=coverage_gaps,
        curated=curated,
        case_factor_snapshot=snapshot,
        output_dir=output_dir,
    )


def _build_lhb_coverage_expansion_plan(coverage_gaps: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "plan_id",
        "case_id",
        "ts_code",
        "stock_name",
        "case_year",
        "verified_case_type",
        "success_or_failure",
        "event_date",
        "priority_for_lhb_backfill",
        "suggested_lhb_query_start_date",
        "suggested_lhb_query_end_date",
        "query_window_days_before",
        "query_window_days_after",
        "reason",
        "expected_value",
        "status",
        "notes",
    ]
    if coverage_gaps.empty:
        return pd.DataFrame(columns=columns)

    priority_map = {
        "a_kill_failure": 1,
        "failed_second_wave": 2,
        "failed_reversal": 3,
        "high_open_low_close_failure": 4,
        "one_day_pump": 5,
        "second_wave": 6,
    }
    value_map = {
        "a_kill_failure": "补齐 A杀 龙头榜风险证据，验证负净买和机构卖出是否领先恶化",
        "failed_second_wave": "补齐失败二波分歧延续证据，验证事后关注和资金撤退",
        "failed_reversal": "校准反包失败规则，确认放量后走弱是否伴随龙虎榜抛压",
        "high_open_low_close_failure": "校准高开低走失败规则，确认日内回落和席位卖压",
        "one_day_pump": "校准一日脉冲规则，识别无持续性的短线扰动",
        "second_wave": "保留成功二波代表样本，作为低风险对照组",
    }
    rows = []
    for idx, record in enumerate(coverage_gaps.fillna("").to_dict("records"), start=1):
        case_type = str(record.get("verified_case_type") or record.get("case_type") or "")
        event_date = str(record.get("event_date") or "")
        if not event_date:
            continue
        days_after = 10 if case_type in {"a_kill_failure", "failed_second_wave"} else 5
        priority = priority_map.get(case_type, int(record.get("priority_for_lhb_backfill") or 9))
        rows.append(
            {
                "plan_id": f"lhb_expand_{idx:04d}",
                "case_id": record.get("case_id"),
                "ts_code": record.get("ts_code"),
                "stock_name": record.get("stock_name"),
                "case_year": record.get("case_year"),
                "verified_case_type": case_type,
                "success_or_failure": record.get("success_or_failure"),
                "event_date": event_date,
                "priority_for_lhb_backfill": priority,
                "suggested_lhb_query_start_date": _shift_date(event_date, -5),
                "suggested_lhb_query_end_date": _shift_date(event_date, days_after),
                "query_window_days_before": 5,
                "query_window_days_after": days_after,
                "reason": record.get("missing_reason") or "coverage_gap",
                "expected_value": value_map.get(case_type, "补齐 LHB 覆盖，支持后续风险诊断复跑"),
                "status": "pending",
                "notes": record.get("notes") or "",
            }
        )
    return (
        pd.DataFrame(rows)
        .reindex(columns=columns)
        .sort_values(["priority_for_lhb_backfill", "case_year", "event_date", "case_id"])
        .reset_index(drop=True)
    )


def _build_lhb_coverage_expansion_summary(coverage_gaps: pd.DataFrame, plan: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "verified_case_type",
        "success_or_failure",
        "case_year",
        "priority_for_lhb_backfill",
        "case_count",
        "event_count",
        "avg_query_window_days",
        "expected_lhb_rows",
        "current_lhb_matched_count",
        "missing_lhb_count",
    ]
    if plan.empty:
        return pd.DataFrame(columns=columns)

    gaps = coverage_gaps.copy()
    if "has_lhb" not in gaps.columns:
        gaps["has_lhb"] = False
    gaps["has_lhb"] = gaps["has_lhb"].astype(bool)
    merged = plan.merge(
        gaps[["case_id", "event_date", "has_lhb"]].drop_duplicates(),
        on=["case_id", "event_date"],
        how="left",
    )
    merged["has_lhb"] = merged["has_lhb"].fillna(False).astype(bool)
    merged["query_window_days"] = merged["query_window_days_before"] + 1 + merged["query_window_days_after"]
    rows = []
    group_cols = ["verified_case_type", "success_or_failure", "case_year", "priority_for_lhb_backfill"]
    for keys, group in merged.groupby(group_cols, dropna=False):
        case_type, success, year, priority = keys
        avg_window = pd.to_numeric(group["query_window_days"], errors="coerce").mean()
        rows.append(
            {
                "verified_case_type": case_type,
                "success_or_failure": success,
                "case_year": year,
                "priority_for_lhb_backfill": priority,
                "case_count": int(group["case_id"].nunique()),
                "event_count": int(len(group)),
                "avg_query_window_days": avg_window,
                "expected_lhb_rows": int(round(len(group) * avg_window)) if pd.notna(avg_window) else 0,
                "current_lhb_matched_count": int(group["has_lhb"].sum()),
                "missing_lhb_count": int((~group["has_lhb"]).sum()),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(group_cols).reset_index(drop=True)


def _lhb_coverage_expansion_commands(plan: pd.DataFrame) -> str:
    if plan.empty:
        return "#!/usr/bin/env bash\nset -euo pipefail\n\n# No LHB coverage expansion cases available.\n"

    top5 = ",".join(plan.head(5)["ts_code"].dropna().astype(str).tolist())
    mid = plan[plan["verified_case_type"].isin(["a_kill_failure", "failed_second_wave"])]
    mid_codes = ",".join(mid["ts_code"].dropna().astype(str).unique().tolist())
    high = plan[plan["priority_for_lhb_backfill"] <= 4]
    high_codes = ",".join(high["ts_code"].dropna().astype(str).unique().tolist())
    start = str(plan["suggested_lhb_query_start_date"].min())
    top_end = str(plan.head(5)["suggested_lhb_query_end_date"].max())
    mid_end = str(mid["suggested_lhb_query_end_date"].max()) if not mid.empty else top_end
    high_end = str(high["suggested_lhb_query_end_date"].max()) if not high.empty else top_end
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "",
            "# AkShare LHB 小批量补数命令计划，只生成建议，不自动执行全量。",
            "# TODO: do not run full-market LHB backfill before reviewing sample results.",
            "# TODO: if stock-research lhb-sample-import cannot cover date range backfill, implement AkShare LHB range backfill CLI.",
            "",
            "# 1. 小样本: Top 5 priority cases, 事件日前后 ±5 日",
            f"# stock-research lhb-sample-import --start-date {start} --end-date {top_end} --ts-codes {top5} --provider akshare --output-dir outputs/research/lhb_top5_sample",
            "",
            "# 2. 中样本: 所有 a_kill_failure / failed_second_wave, 事件日前后 ±5 到 ±10 日",
            f"# stock-research lhb-sample-import --start-date {start} --end-date {mid_end} --ts-codes {mid_codes} --provider akshare --output-dir outputs/research/lhb_failure_mid_sample",
            "",
            "# 3. 扩展样本: 全部 high priority gap cases",
            f"# stock-research lhb-sample-import --start-date {start} --end-date {high_end} --ts-codes {high_codes} --provider akshare --output-dir outputs/research/lhb_high_priority_sample",
            "",
        ]
    )


def _build_failure_event_rule_refinement_audit(curated: pd.DataFrame, case_factor_snapshot: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "case_id",
        "ts_code",
        "stock_name",
        "current_verified_case_type",
        "event_date",
        "pre_3d_return",
        "pre_5d_return",
        "post_1d_return",
        "post_3d_return",
        "post_5d_return",
        "post_10d_return",
        "post_5d_max_drawdown",
        "post_10d_max_drawdown",
        "amount_vs_20d",
        "high_to_close_drawdown",
        "close_position_in_day",
        "is_limit_up_day",
        "is_break_limit_event",
        "is_reversal_event",
        "is_second_wave_event",
        "is_a_kill_event",
        "suggested_refined_case_type",
        "refinement_reason",
        "confidence",
    ]
    if curated.empty or case_factor_snapshot.empty:
        return pd.DataFrame(columns=columns)
    targets = {
        "failed_reversal",
        "high_open_low_close_failure",
        "one_day_pump",
        "failed_second_wave",
        "a_kill_failure",
    }
    cases = curated.copy()
    cases["current_verified_case_type"] = cases.get("verified_case_type", cases.get("case_type", "")).fillna("")
    cases = cases[cases["current_verified_case_type"].isin(targets)]
    snapshot = case_factor_snapshot.copy()
    if "relative_day" in snapshot.columns:
        snapshot = snapshot[pd.to_numeric(snapshot["relative_day"], errors="coerce").fillna(0).eq(0)]
    merged = cases.merge(snapshot, on="case_id", how="left", suffixes=("", "_snapshot"))
    rows = []
    for record in merged.fillna("").to_dict("records"):
        suggested, reason, confidence = _suggest_failure_case_type(record)
        rows.append(
            {
                "case_id": record.get("case_id"),
                "ts_code": record.get("ts_code") or record.get("ts_code_snapshot"),
                "stock_name": record.get("stock_name") or record.get("stock_name_snapshot"),
                "current_verified_case_type": record.get("current_verified_case_type"),
                "event_date": record.get("event_date") or record.get("event_date_snapshot"),
                "pre_3d_return": record.get("pre_3d_return"),
                "pre_5d_return": record.get("pre_5d_return"),
                "post_1d_return": record.get("future_1d_return"),
                "post_3d_return": record.get("future_3d_return"),
                "post_5d_return": record.get("future_5d_return"),
                "post_10d_return": record.get("future_10d_return"),
                "post_5d_max_drawdown": record.get("future_5d_max_drawdown"),
                "post_10d_max_drawdown": record.get("future_10d_max_drawdown"),
                "amount_vs_20d": record.get("amount_vs_20d"),
                "high_to_close_drawdown": record.get("high_to_close_drawdown"),
                "close_position_in_day": record.get("close_position_in_day"),
                "is_limit_up_day": bool(record.get("is_limit_up_day")),
                "is_break_limit_event": bool(record.get("is_break_limit_event")),
                "is_reversal_event": bool(record.get("is_reversal_event")),
                "is_second_wave_event": bool(record.get("is_second_wave_event")),
                "is_a_kill_event": bool(record.get("is_a_kill_event")),
                "suggested_refined_case_type": suggested,
                "refinement_reason": reason,
                "confidence": confidence,
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns)


def _suggest_failure_case_type(record: dict[str, Any]) -> tuple[str, str, str]:
    current = str(record.get("current_verified_case_type") or "")
    post_10d = pd.to_numeric(pd.Series([record.get("future_10d_return")]), errors="coerce").iloc[0]
    drawdown = pd.to_numeric(pd.Series([record.get("future_10d_max_drawdown")]), errors="coerce").iloc[0]
    high_to_close = pd.to_numeric(pd.Series([record.get("high_to_close_drawdown")]), errors="coerce").iloc[0]
    amount = pd.to_numeric(pd.Series([record.get("amount_vs_20d")]), errors="coerce").iloc[0]
    pre_5d = pd.to_numeric(pd.Series([record.get("pre_5d_return")]), errors="coerce").iloc[0]
    if bool(record.get("is_a_kill_event")) or (pd.notna(post_10d) and post_10d <= -0.20):
        return "a_kill_failure", "10日后续跌幅/回撤明显，优先归入 A杀失败边界", "high"
    if bool(record.get("is_second_wave_event")) and pd.notna(post_10d) and post_10d < 0:
        return "failed_second_wave", "二波形态成立但后续收益转弱，保留失败二波标签", "high"
    if bool(record.get("is_reversal_event")) and pd.notna(pre_5d) and pre_5d > 0.10:
        return "failed_reversal", "前期已有涨幅且反包后走弱，适合反包失败规则", "medium"
    if bool(record.get("is_break_limit_event")) and pd.notna(high_to_close) and high_to_close >= 0.08:
        return "high_open_low_close_failure", "日内高点回落较深且破板/回落，适合高开低走失败", "medium"
    if bool(record.get("is_limit_up_day")) and pd.notna(amount) and amount >= 3:
        return "one_day_pump", "放量脉冲但持续性不足，适合一日脉冲规则", "medium"
    return current, "当前字段不足以稳定改判，保持原标签并补充人工复核", "low"


def _build_failure_event_rule_refinement_suggestions(curated: pd.DataFrame, audit: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "case_type",
        "current_sample_count",
        "suggested_rule",
        "required_fields",
        "expected_improvement",
        "risk_of_false_positive",
        "notes",
    ]
    case_types = curated.get("verified_case_type", pd.Series(dtype=str)).fillna("").astype(str)
    counts = case_types.value_counts().to_dict()
    rows = [
        {
            "case_type": "failed_reversal",
            "current_sample_count": int(counts.get("failed_reversal", 0)),
            "suggested_rule": "前5日涨幅较高，事件日反包/涨停尝试失败，后3-5日收益转负或回撤加深。",
            "required_fields": "pre_5d_return,is_reversal_event,is_limit_up_day,post_3d_return,post_5d_max_drawdown",
            "expected_improvement": "降低把普通震荡误标为反包失败的概率。",
            "risk_of_false_positive": "强趋势中的短暂换手可能被误判为失败。",
            "notes": "需要和 high_open_low_close_failure 按日内回落幅度区分。",
        },
        {
            "case_type": "high_open_low_close_failure",
            "current_sample_count": int(counts.get("high_open_low_close_failure", 0)),
            "suggested_rule": "事件日高开或冲高后收盘靠近低位，high_to_close_drawdown 明显，且破板/后续3-5日走弱。",
            "required_fields": "high_to_close_drawdown,close_position_in_day,is_break_limit_event,post_3d_return",
            "expected_improvement": "更准确识别高位分歧后的日内失败。",
            "risk_of_false_positive": "低位洗盘也可能出现高开低走。",
            "notes": "和 one_day_pump 的边界应以是否已有前置涨幅和是否破板为核心。",
        },
        {
            "case_type": "one_day_pump",
            "current_sample_count": int(counts.get("one_day_pump", 0)),
            "suggested_rule": "低前置涨幅、事件日放量脉冲或涨停，后1-5日没有持续收益。",
            "required_fields": "pre_3d_return,pre_5d_return,amount_vs_20d,is_limit_up_day,post_1d_return,post_5d_return",
            "expected_improvement": "避免把无持续性的单日脉冲混入二波或反包失败。",
            "risk_of_false_positive": "首板启动初期可能被误伤。",
            "notes": "若前5日涨幅和日内回落都高，应优先考虑 high_open_low_close_failure。",
        },
        {
            "case_type": "failed_second_wave",
            "current_sample_count": int(counts.get("failed_second_wave", 0)),
            "suggested_rule": "二波事件形态成立，但后5-10日收益转弱，且非单日 A杀式连续下挫。",
            "required_fields": "is_second_wave_event,pre_5d_return,post_5d_return,post_10d_return,post_10d_max_drawdown",
            "expected_improvement": "把失败二波从一日脉冲和 A杀中拆清。",
            "risk_of_false_positive": "样本窗口太短会把正常二波回踩误判为失败。",
            "notes": "与 a_kill_failure 的边界看跌幅速度和回撤深度。",
        },
        {
            "case_type": "a_kill_failure",
            "current_sample_count": int(counts.get("a_kill_failure", 0)),
            "suggested_rule": "高位或二波后快速转弱，后5-10日负收益和最大回撤显著。",
            "required_fields": "is_a_kill_event,pre_5d_return,post_5d_return,post_10d_return,post_10d_max_drawdown",
            "expected_improvement": "优先识别最需要 LHB 风险证据补充的失败类型。",
            "risk_of_false_positive": "系统性下跌日可能放大个股 A杀标签。",
            "notes": "应高于 failed_second_wave 的风险优先级。",
        },
    ]
    return pd.DataFrame(rows).reindex(columns=columns)


def _lhb_coverage_failure_plan_markdown(
    *,
    plan: pd.DataFrame,
    summary: pd.DataFrame,
    audit: pd.DataFrame,
    suggestions: pd.DataFrame,
    warnings: list[str],
) -> str:
    high_priority = plan[plan["priority_for_lhb_backfill"] <= 3] if not plan.empty else plan
    return "\n".join(
        [
            "# LHB Coverage Expansion & Failure Rule Refinement Plan v1",
            "",
            "## 1. 背景",
            "LHB 风险诊断已经能解释 A杀、失败二波和高位分歧的部分风险，但覆盖缺口和失败事件标签仍是短板。",
            "",
            "## 2. LHB 覆盖缺口",
            f"当前覆盖扩展计划 {len(plan)} 行，高优先级案例 {len(high_priority)} 行。优先补 a_kill_failure、failed_second_wave、failed_reversal。",
            _table_preview(summary, rows=20),
            "",
            "## 3. 覆盖扩展计划",
            "默认事件日前 5 日到事件后 5 日；a_kill_failure 和 failed_second_wave 扩到事件后 10 日。",
            _table_preview(plan.head(20), rows=20),
            "",
            "## 4. AkShare 小批量补数建议",
            "先小样本 Top 5，再跑 a_kill_failure / failed_second_wave 中样本，最后扩展到全部高优先级 gap cases。",
            "",
            "## 5. 失败事件规则问题",
            "failed_reversal、high_open_low_close_failure、one_day_pump 当前边界容易混淆，需要引入前置涨幅、日内回落、放量和后续收益/回撤共同约束。",
            _table_preview(audit.head(20), rows=20),
            "",
            "## 6. 规则修正建议",
            _table_preview(suggestions, rows=20),
            "",
            "## 7. 下一步",
            "- 先补 LHB 高优先级窗口；",
            "- 再实现失败事件规则 v2；",
            "- 再重新跑 LHB risk diagnostics；",
            "- 最后再考虑 entry_score v3。",
            "",
            "### Warnings",
            *(warnings or ["无"]),
        ]
    )


def _compact_date(value: str) -> str:
    return pd.to_datetime(value, errors="coerce").strftime("%Y%m%d")


def _code_to_ts_code(value: Any) -> str:
    text = str(value or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) != 6:
        return text.upper()
    if digits.startswith(("8", "4")):
        exchange = "BJ"
    elif digits.startswith(("5", "6", "9")):
        exchange = "SH"
    else:
        exchange = "SZ"
    return f"{digits}.{exchange}"


def _top_list_rows(frame: pd.DataFrame) -> list[tuple[Any, ...]]:
    return [
        (
            row.trade_date,
            row.ts_code,
            row.name,
            row.close,
            row.pct_change,
            row.turnover_rate,
            row.amount,
            row.l_sell,
            row.l_buy,
            row.l_amount,
            row.net_amount,
            row.net_rate,
            row.amount_rate,
            row.float_values,
            row.reason,
            row.source,
        )
        for row in frame.itertuples(index=False)
    ]


def _top_inst_rows(frame: pd.DataFrame) -> list[tuple[Any, ...]]:
    return [
        (
            row.trade_date,
            row.ts_code,
            row.exalter,
            row.buy,
            row.buy_rate,
            row.sell,
            row.sell_rate,
            row.net_buy,
            row.reason,
            row.source,
        )
        for row in frame.itertuples(index=False)
    ]


def _event_feature_rows(frame: pd.DataFrame) -> list[tuple[Any, ...]]:
    return [
        (
            row.trade_date,
            row.ts_code,
            row.on_lhb,
            row.lhb_reason,
            row.lhb_net_buy_amount,
            row.lhb_net_buy_ratio,
            row.lhb_buy_amount,
            row.lhb_sell_amount,
            row.institution_net_buy,
            row.top_seat_concentration,
            row.repeat_on_list_count_3d,
            row.repeat_on_list_count_5d,
            row.lhb_after_limit_up,
            row.lhb_after_break_limit,
            row.lhb_after_reversal,
            row.lhb_one_day_pump_risk,
            row.source,
        )
        for row in frame.itertuples(index=False)
    ]


def _normalize_date_code_frame(frame: pd.DataFrame, date_col: str, code_col: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    data = frame.copy()
    data[date_col] = pd.to_datetime(data[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
    data[code_col] = data[code_col].fillna("").astype(str).str.upper()
    return data


def _numeric_scalar(series: pd.Series, *, aggregator: str) -> float | None:
    if series.empty:
        return None
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return None
    if aggregator == "sum":
        return float(numeric.sum())
    return float(numeric.max())


def _join_unique(series: pd.Series) -> str:
    values: list[str] = []
    seen: set[str] = set()
    for value in series.fillna("").astype(str):
        text = value.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        values.append(text)
    return " | ".join(values)


def _repeat_on_list_count(
    frame: pd.DataFrame,
    *,
    ts_code: str,
    source: str,
    trade_date: str,
    lookback_days: int,
) -> int:
    if frame.empty:
        return 0
    start_date = _shift_date(trade_date, -lookback_days)
    mask = (
        (frame["ts_code"] == ts_code)
        & (frame["source"] == source)
        & (frame["trade_date"] >= start_date)
        & (frame["trade_date"] <= trade_date)
    )
    return int(frame.loc[mask, "trade_date"].nunique())


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "" or pd.isna(value):
        return None
    return float(value)


def _coerce_ratio(value: Any, *, clamp: bool = True) -> float | None:
    if value is None or pd.isna(value):
        return None
    ratio = float(value)
    if abs(ratio) > 1.0:
        ratio = ratio / 100.0
    if clamp:
        ratio = max(min(ratio, 1.0), -1.0)
    return ratio


def _build_lhb_case_summary(alignment_audit: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "case_type",
        "event_type",
        "sample_count",
        "matched_count",
        "matched_rate",
        "on_event_date_count",
        "on_event_date_rate",
        "before_event_3d_count",
        "before_event_3d_rate",
        "after_event_3d_count",
        "after_event_3d_rate",
        "avg_lhb_net_buy_amount",
        "avg_institution_net_buy",
        "avg_top_seat_concentration",
        "avg_repeat_on_list_count_5d",
        "avg_lhb_one_day_pump_risk",
    ]
    if alignment_audit.empty:
        return pd.DataFrame(columns=columns)
    frame = alignment_audit.copy()
    rows: list[dict[str, Any]] = []
    for (case_type, event_type), group in frame.groupby(["case_type", "event_type"], dropna=False):
        sample_count = int(len(group))
        matched_count = int((group["lhb_alignment_status"] == "matched").sum())
        on_count = int(pd.to_numeric(group["lhb_on_event_date"], errors="coerce").fillna(False).astype(bool).sum())
        before_count = int(pd.to_numeric(group["lhb_before_event_3d"], errors="coerce").fillna(False).astype(bool).sum())
        after_count = int(pd.to_numeric(group["lhb_after_event_3d"], errors="coerce").fillna(False).astype(bool).sum())
        rows.append(
            {
                "case_type": case_type,
                "event_type": event_type,
                "sample_count": sample_count,
                "matched_count": matched_count,
                "matched_rate": matched_count / sample_count if sample_count else None,
                "on_event_date_count": on_count,
                "on_event_date_rate": on_count / sample_count if sample_count else None,
                "before_event_3d_count": before_count,
                "before_event_3d_rate": before_count / sample_count if sample_count else None,
                "after_event_3d_count": after_count,
                "after_event_3d_rate": after_count / sample_count if sample_count else None,
                "avg_lhb_net_buy_amount": pd.to_numeric(group["lhb_net_buy_amount"], errors="coerce").mean(),
                "avg_institution_net_buy": pd.to_numeric(group["institution_net_buy"], errors="coerce").mean(),
                "avg_top_seat_concentration": pd.to_numeric(group["top_seat_concentration"], errors="coerce").mean(),
                "avg_repeat_on_list_count_5d": pd.to_numeric(group["repeat_on_list_count_5d"], errors="coerce").mean(),
                "avg_lhb_one_day_pump_risk": pd.to_numeric(group["lhb_one_day_pump_risk"], errors="coerce").mean(),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(["case_type", "event_type"]).reset_index(drop=True)


def _build_lhb_case_comparison(curated: pd.DataFrame, alignment_audit: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "case_group",
        "success_or_failure",
        "case_type",
        "sample_count",
        "matched_count",
        "on_event_date_rate",
        "before_event_3d_rate",
        "after_event_3d_rate",
        "avg_lhb_net_buy_amount",
        "avg_institution_net_buy",
        "avg_top_seat_concentration",
        "avg_repeat_on_list_count_5d",
        "avg_lhb_one_day_pump_risk",
    ]
    if curated.empty or alignment_audit.empty:
        return pd.DataFrame(columns=columns)
    meta = curated.copy()
    meta["case_type_key"] = meta.get("verified_case_type", pd.Series(dtype="object")).fillna("").astype(str)
    empty_mask = meta["case_type_key"] == ""
    if "case_type" in meta.columns:
        meta.loc[empty_mask, "case_type_key"] = meta.loc[empty_mask, "case_type"].fillna("").astype(str)
    merged = alignment_audit.merge(
        meta[["case_id", "success_or_failure", "case_type_key"]],
        on="case_id",
        how="left",
    )
    merged["case_type_final"] = merged["case_type"].fillna("").astype(str)
    empty_mask = merged["case_type_final"] == ""
    merged.loc[empty_mask, "case_type_final"] = merged.loc[empty_mask, "case_type_key"].fillna("").astype(str)
    merged["case_group"] = merged["success_or_failure"].fillna("unknown").astype(str) + ":" + merged["case_type_final"].fillna("unknown").astype(str)
    rows: list[dict[str, Any]] = []
    for case_group, group in merged.groupby("case_group", dropna=False):
        sample_count = int(len(group))
        matched_count = int((group["lhb_alignment_status"] == "matched").sum())
        rows.append(
            {
                "case_group": case_group,
                "success_or_failure": str(group["success_or_failure"].iloc[0] or ""),
                "case_type": str(group["case_type_final"].iloc[0] or ""),
                "sample_count": sample_count,
                "matched_count": matched_count,
                "on_event_date_rate": pd.to_numeric(group["lhb_on_event_date"], errors="coerce").fillna(False).astype(bool).mean(),
                "before_event_3d_rate": pd.to_numeric(group["lhb_before_event_3d"], errors="coerce").fillna(False).astype(bool).mean(),
                "after_event_3d_rate": pd.to_numeric(group["lhb_after_event_3d"], errors="coerce").fillna(False).astype(bool).mean(),
                "avg_lhb_net_buy_amount": pd.to_numeric(group["lhb_net_buy_amount"], errors="coerce").mean(),
                "avg_institution_net_buy": pd.to_numeric(group["institution_net_buy"], errors="coerce").mean(),
                "avg_top_seat_concentration": pd.to_numeric(group["top_seat_concentration"], errors="coerce").mean(),
                "avg_repeat_on_list_count_5d": pd.to_numeric(group["repeat_on_list_count_5d"], errors="coerce").mean(),
                "avg_lhb_one_day_pump_risk": pd.to_numeric(group["lhb_one_day_pump_risk"], errors="coerce").mean(),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(["success_or_failure", "case_type"]).reset_index(drop=True)


def _lhb_case_summary_report(*, summary: pd.DataFrame, comparison: pd.DataFrame) -> str:
    focus = comparison[comparison["case_type"].isin(["second_wave", "failed_second_wave", "a_kill_failure", "failed_reversal"])].copy() if not comparison.empty else comparison
    return "\n".join(
        [
            "# LHB Case Summary 2024-2026",
            "",
            "## 1. Scope",
            "本报告只做案例层龙虎榜事件诊断，不接策略打分，不做回测。",
            "",
            "## 2. Event Summary",
            _table_preview(summary, rows=20),
            "",
            "## 3. Success vs Failure",
            _table_preview(comparison, rows=20),
            "",
            "## 4. Focus Groups",
            _table_preview(focus, rows=12),
            "",
            "## 5. Notes",
            "- on_event_date / before_event_3d / after_event_3d 用于看上榜时点分布。",
            "- institution_net_buy / repeat_on_list_count_5d / one_day_pump_risk 目前是诊断特征，不进入策略。",
        ]
    )


def _table_preview(frame: pd.DataFrame, *, rows: int = 12) -> str:
    if frame.empty:
        return "无数据。"
    return frame.head(rows).to_markdown(index=False)


def _build_lhb_case_event_detail(
    curated: pd.DataFrame,
    alignment_audit: pd.DataFrame,
    factor_review: pd.DataFrame,
    *,
    lhb_features: pd.DataFrame | None = None,
) -> pd.DataFrame:
    columns = [
        "case_id",
        "ts_code",
        "stock_name",
        "case_year",
        "case_type",
        "verified_case_type",
        "success_or_failure",
        "role",
        "event_type",
        "event_date",
        "lhb_on_event_date",
        "lhb_before_3d",
        "lhb_after_3d",
        "lhb_after_5d",
        "lhb_net_buy_amount_event",
        "lhb_net_buy_ratio_event",
        "institution_net_buy_event",
        "top_seat_concentration_event",
        "repeat_on_list_count_3d",
        "repeat_on_list_count_5d",
        "lhb_one_day_pump_risk",
        "future_1d_return",
        "future_3d_return",
        "future_5d_return",
        "future_10d_return",
        "future_5d_max_drawdown",
        "future_10d_max_drawdown",
        "diagnostic_note",
    ]
    if curated.empty or alignment_audit.empty:
        return pd.DataFrame(columns=columns)
    features = _normalize_date_code_frame((lhb_features if lhb_features is not None else pd.DataFrame()).copy().reindex(columns=LHB_EVENT_FEATURE_COLUMNS), "trade_date", "ts_code")
    meta = curated.copy()
    meta["case_id"] = meta["case_id"].fillna("").astype(str)
    lookup = meta.set_index("case_id", drop=False)
    future_lookup = pd.DataFrame()
    if not factor_review.empty:
        future_lookup = factor_review.copy()
        future_lookup["case_id"] = future_lookup.get("case_id", pd.Series(dtype="object")).fillna("").astype(str)
        if "case_id" not in future_lookup.columns or not future_lookup["case_id"].astype(str).str.strip().any():
            future_lookup["case_id"] = future_lookup.get("web_candidate_id", pd.Series(dtype="object")).fillna("").astype(str).map(
                lambda value: f"curated_{value.split('_')[-1]}" if value else ""
            )
    rows: list[dict[str, Any]] = []
    for record in alignment_audit.fillna("").to_dict("records"):
        case_id = str(record.get("case_id") or "")
        meta_row = lookup.loc[case_id] if case_id in lookup.index else pd.Series(dtype="object")
        if isinstance(meta_row, pd.DataFrame):
            meta_row = meta_row.iloc[0]
        future_row = pd.Series(dtype="object")
        if not future_lookup.empty and case_id:
            matched_future = future_lookup[(future_lookup["case_id"] == case_id)]
            if matched_future.empty and "ts_code" in future_lookup.columns:
                matched_future = future_lookup[(future_lookup["ts_code"].fillna("").astype(str).str.upper() == str(record.get("ts_code") or "").upper())]
            if not matched_future.empty and "event_type" in matched_future.columns:
                event_matched = matched_future[matched_future["event_type"].fillna("").astype(str) == str(record.get("event_type") or "")]
                if not event_matched.empty:
                    matched_future = event_matched
            if not matched_future.empty and "event_date" in matched_future.columns:
                date_matched = matched_future[matched_future["event_date"].fillna("").astype(str) == str(record.get("event_date") or "")]
                if not date_matched.empty:
                    matched_future = date_matched
            if not matched_future.empty:
                if "relative_day" in matched_future.columns:
                    rel0 = matched_future[pd.to_numeric(matched_future["relative_day"], errors="coerce").fillna(999).astype(int) == 0]
                    future_row = rel0.iloc[0] if not rel0.empty else matched_future.iloc[0]
                else:
                    future_row = matched_future.iloc[0]
        event_feature = pd.Series(dtype="object")
        if not features.empty:
            feature_rows = features[
                (features["ts_code"] == str(record.get("ts_code") or "").upper())
                & (features["trade_date"] == str(record.get("event_date") or ""))
            ]
            if not feature_rows.empty:
                event_feature = feature_rows.iloc[0]
        after_5d = bool(record.get("lhb_after_event_3d"))
        if not features.empty:
            event_date = str(record.get("event_date") or "")
            if event_date:
                after_5d = not features[
                    (features["ts_code"] == str(record.get("ts_code") or "").upper())
                    & (features["trade_date"] > event_date)
                    & (features["trade_date"] <= _shift_date(event_date, 5))
                ].empty
        diagnostic_note = _diagnostic_note_from_case_and_lhb(meta_row, record)
        rows.append(
            {
                "case_id": case_id,
                "ts_code": record.get("ts_code"),
                "stock_name": record.get("stock_name"),
                "case_year": meta_row.get("case_year") if not meta_row.empty else None,
                "case_type": record.get("case_type") or meta_row.get("case_type"),
                "verified_case_type": meta_row.get("verified_case_type") if not meta_row.empty else None,
                "success_or_failure": meta_row.get("success_or_failure") if not meta_row.empty else None,
                "role": meta_row.get("role") if not meta_row.empty else None,
                "event_type": record.get("event_type"),
                "event_date": record.get("event_date"),
                "lhb_on_event_date": bool(record.get("lhb_on_event_date")),
                "lhb_before_3d": bool(record.get("lhb_before_event_3d")),
                "lhb_after_3d": bool(record.get("lhb_after_event_3d")),
                "lhb_after_5d": after_5d,
                "lhb_net_buy_amount_event": _float_or_none(record.get("lhb_net_buy_amount")),
                "lhb_net_buy_ratio_event": _float_or_none(event_feature.get("lhb_net_buy_ratio")) if not event_feature.empty else None,
                "institution_net_buy_event": _float_or_none(record.get("institution_net_buy")),
                "top_seat_concentration_event": _float_or_none(record.get("top_seat_concentration")),
                "repeat_on_list_count_3d": int(record.get("repeat_on_list_count_3d") or 0),
                "repeat_on_list_count_5d": int(record.get("repeat_on_list_count_5d") or 0),
                "lhb_one_day_pump_risk": _float_or_none(record.get("lhb_one_day_pump_risk")),
                "future_1d_return": _float_or_none(future_row.get("future_1d_return")) if not future_row.empty else None,
                "future_3d_return": _float_or_none(future_row.get("future_3d_return")) if not future_row.empty else None,
                "future_5d_return": _float_or_none(future_row.get("future_5d_return")) if not future_row.empty else None,
                "future_10d_return": _float_or_none(future_row.get("future_10d_return")) if not future_row.empty else None,
                "future_5d_max_drawdown": _float_or_none(future_row.get("future_5d_max_drawdown")) if not future_row.empty else None,
                "future_10d_max_drawdown": _float_or_none(future_row.get("future_10d_max_drawdown")) if not future_row.empty else None,
                "diagnostic_note": diagnostic_note,
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns)


def _diagnostic_note_from_case_and_lhb(meta_row: pd.Series, record: dict[str, Any]) -> str:
    case_type = str(record.get("case_type") or meta_row.get("case_type") or "")
    success = str(meta_row.get("success_or_failure") or "")
    net_buy = _float_or_none(record.get("lhb_net_buy_amount"))
    risk = _float_or_none(record.get("lhb_one_day_pump_risk"))
    if net_buy is None and not bool(record.get("lhb_on_event_date")):
        return "lhb_missing"
    if case_type == "second_wave" and success == "success" and (net_buy or 0) > 0:
        return "success_second_wave_with_positive_lhb"
    if case_type == "failed_second_wave" and bool(record.get("lhb_after_3d")):
        return "failed_second_wave_after_event_lhb_attention"
    if case_type == "a_kill_failure" and (net_buy or 0) < 0:
        return "a_kill_with_negative_lhb"
    if risk is not None and risk >= 0.7:
        return "high_pump_risk_after_event"
    if net_buy is not None and net_buy > 0:
        return "lhb_no_clear_signal"
    return "lhb_no_clear_signal"


def _build_lhb_case_type_difference_summary(detail: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "success_or_failure",
        "verified_case_type",
        "case_type",
        "role",
        "sample_count",
        "lhb_on_event_date_rate",
        "lhb_before_3d_rate",
        "lhb_after_3d_rate",
        "avg_lhb_net_buy_amount_on_event",
        "median_lhb_net_buy_amount_on_event",
        "avg_lhb_net_buy_ratio_on_event",
        "avg_institution_net_buy_on_event",
        "avg_top_seat_concentration_on_event",
        "avg_repeat_on_list_count_3d",
        "avg_repeat_on_list_count_5d",
        "avg_lhb_one_day_pump_risk",
        "avg_future_3d_return",
        "avg_future_5d_return",
        "avg_future_10d_return",
        "avg_future_5d_max_drawdown",
        "avg_future_10d_max_drawdown",
    ]
    if detail.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for (success_or_failure, verified_case_type, case_type, role), group in detail.groupby(
        ["success_or_failure", "verified_case_type", "case_type", "role"], dropna=False
    ):
        rows.append(
            {
                "success_or_failure": success_or_failure,
                "verified_case_type": verified_case_type,
                "case_type": case_type,
                "role": role,
                "sample_count": int(len(group)),
                "lhb_on_event_date_rate": pd.to_numeric(group["lhb_on_event_date"], errors="coerce").fillna(False).astype(bool).mean(),
                "lhb_before_3d_rate": pd.to_numeric(group["lhb_before_3d"], errors="coerce").fillna(False).astype(bool).mean(),
                "lhb_after_3d_rate": pd.to_numeric(group["lhb_after_3d"], errors="coerce").fillna(False).astype(bool).mean(),
                "avg_lhb_net_buy_amount_on_event": pd.to_numeric(group["lhb_net_buy_amount_event"], errors="coerce").mean(),
                "median_lhb_net_buy_amount_on_event": pd.to_numeric(group["lhb_net_buy_amount_event"], errors="coerce").median(),
                "avg_lhb_net_buy_ratio_on_event": pd.to_numeric(group["lhb_net_buy_ratio_event"], errors="coerce").mean(),
                "avg_institution_net_buy_on_event": pd.to_numeric(group["institution_net_buy_event"], errors="coerce").mean(),
                "avg_top_seat_concentration_on_event": pd.to_numeric(group["top_seat_concentration_event"], errors="coerce").mean(),
                "avg_repeat_on_list_count_3d": pd.to_numeric(group["repeat_on_list_count_3d"], errors="coerce").mean(),
                "avg_repeat_on_list_count_5d": pd.to_numeric(group["repeat_on_list_count_5d"], errors="coerce").mean(),
                "avg_lhb_one_day_pump_risk": pd.to_numeric(group["lhb_one_day_pump_risk"], errors="coerce").mean(),
                "avg_future_3d_return": pd.to_numeric(group["future_3d_return"], errors="coerce").mean(),
                "avg_future_5d_return": pd.to_numeric(group["future_5d_return"], errors="coerce").mean(),
                "avg_future_10d_return": pd.to_numeric(group["future_10d_return"], errors="coerce").mean(),
                "avg_future_5d_max_drawdown": pd.to_numeric(group["future_5d_max_drawdown"], errors="coerce").mean(),
                "avg_future_10d_max_drawdown": pd.to_numeric(group["future_10d_max_drawdown"], errors="coerce").mean(),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(["success_or_failure", "verified_case_type", "case_type", "role"]).reset_index(drop=True)


def _window_rows(detail: pd.DataFrame, lhb_features: pd.DataFrame) -> pd.DataFrame:
    if detail.empty or lhb_features.empty:
        return pd.DataFrame()
    features = _normalize_date_code_frame(lhb_features, "trade_date", "ts_code")
    rows: list[dict[str, Any]] = []
    for record in detail.fillna("").to_dict("records"):
        event_date = str(record.get("event_date") or "")
        ts_code = str(record.get("ts_code") or "").upper()
        event_features = features[features["ts_code"] == ts_code]
        if event_features.empty:
            continue
        windows = {
            "before_3d": event_features[(event_features["trade_date"] < event_date) & (event_features["trade_date"] >= _shift_date(event_date, -3))],
            "event_day": event_features[event_features["trade_date"] == event_date],
            "after_3d": event_features[(event_features["trade_date"] > event_date) & (event_features["trade_date"] <= _shift_date(event_date, 3))],
            "after_5d": event_features[(event_features["trade_date"] > event_date) & (event_features["trade_date"] <= _shift_date(event_date, 5))],
        }
        for window, frame in windows.items():
            if frame.empty:
                rows.append(
                    {
                        **record,
                        "event_window": window,
                        "lhb_hit_rate": 0.0,
                        "avg_lhb_net_buy_amount": None,
                        "median_lhb_net_buy_amount": None,
                        "avg_lhb_net_buy_ratio": None,
                        "avg_institution_net_buy": None,
                        "avg_top_seat_concentration": None,
                        "avg_repeat_on_list_count_3d": None,
                        "avg_repeat_on_list_count_5d": None,
                        "avg_lhb_one_day_pump_risk": None,
                    }
                )
                continue
            rows.append(
                {
                    **record,
                    "event_window": window,
                    "lhb_hit_rate": 1.0,
                    "avg_lhb_net_buy_amount": pd.to_numeric(frame["lhb_net_buy_amount"], errors="coerce").mean(),
                    "median_lhb_net_buy_amount": pd.to_numeric(frame["lhb_net_buy_amount"], errors="coerce").median(),
                    "avg_lhb_net_buy_ratio": pd.to_numeric(frame["lhb_net_buy_ratio"], errors="coerce").mean(),
                    "avg_institution_net_buy": pd.to_numeric(frame["institution_net_buy"], errors="coerce").mean(),
                    "avg_top_seat_concentration": pd.to_numeric(frame["top_seat_concentration"], errors="coerce").mean(),
                    "avg_repeat_on_list_count_3d": pd.to_numeric(frame["repeat_on_list_count_3d"], errors="coerce").mean(),
                    "avg_repeat_on_list_count_5d": pd.to_numeric(frame["repeat_on_list_count_5d"], errors="coerce").mean(),
                    "avg_lhb_one_day_pump_risk": pd.to_numeric(frame["lhb_one_day_pump_risk"], errors="coerce").mean(),
                }
            )
    return pd.DataFrame(rows)


def _build_lhb_event_window_difference(
    curated: pd.DataFrame,
    alignment_audit: pd.DataFrame,
    lhb_features: pd.DataFrame,
    factor_review: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "success_or_failure",
        "verified_case_type",
        "event_window",
        "sample_count",
        "lhb_hit_rate",
        "avg_lhb_net_buy_amount",
        "median_lhb_net_buy_amount",
        "avg_lhb_net_buy_ratio",
        "avg_institution_net_buy",
        "avg_top_seat_concentration",
        "avg_repeat_on_list_count_3d",
        "avg_repeat_on_list_count_5d",
        "avg_lhb_one_day_pump_risk",
        "avg_future_3d_return",
        "avg_future_5d_return",
        "avg_future_10d_return",
        "avg_future_5d_max_drawdown",
        "avg_future_10d_max_drawdown",
    ]
    detail = _build_lhb_case_event_detail(curated, alignment_audit, factor_review, lhb_features=lhb_features)
    window_frame = _window_rows(detail, lhb_features)
    if window_frame.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for (success_or_failure, verified_case_type, event_window), group in window_frame.groupby(
        ["success_or_failure", "verified_case_type", "event_window"], dropna=False
    ):
        rows.append(
            {
                "success_or_failure": success_or_failure,
                "verified_case_type": verified_case_type,
                "event_window": event_window,
                "sample_count": int(len(group)),
                "lhb_hit_rate": pd.to_numeric(group["lhb_hit_rate"], errors="coerce").mean(),
                "avg_lhb_net_buy_amount": pd.to_numeric(group["avg_lhb_net_buy_amount"], errors="coerce").mean(),
                "median_lhb_net_buy_amount": pd.to_numeric(group["median_lhb_net_buy_amount"], errors="coerce").median(),
                "avg_lhb_net_buy_ratio": pd.to_numeric(group["avg_lhb_net_buy_ratio"], errors="coerce").mean(),
                "avg_institution_net_buy": pd.to_numeric(group["avg_institution_net_buy"], errors="coerce").mean(),
                "avg_top_seat_concentration": pd.to_numeric(group["avg_top_seat_concentration"], errors="coerce").mean(),
                "avg_repeat_on_list_count_3d": pd.to_numeric(group["avg_repeat_on_list_count_3d"], errors="coerce").mean(),
                "avg_repeat_on_list_count_5d": pd.to_numeric(group["avg_repeat_on_list_count_5d"], errors="coerce").mean(),
                "avg_lhb_one_day_pump_risk": pd.to_numeric(group["avg_lhb_one_day_pump_risk"], errors="coerce").mean(),
                "avg_future_3d_return": pd.to_numeric(group["future_3d_return"], errors="coerce").mean(),
                "avg_future_5d_return": pd.to_numeric(group["future_5d_return"], errors="coerce").mean(),
                "avg_future_10d_return": pd.to_numeric(group["future_10d_return"], errors="coerce").mean(),
                "avg_future_5d_max_drawdown": pd.to_numeric(group["future_5d_max_drawdown"], errors="coerce").mean(),
                "avg_future_10d_max_drawdown": pd.to_numeric(group["future_10d_max_drawdown"], errors="coerce").mean(),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(["success_or_failure", "verified_case_type", "event_window"]).reset_index(drop=True)


def _build_lhb_signal_effectiveness(detail: pd.DataFrame, *, signal_kind: str) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame()
    frame = detail.copy()
    if signal_kind == "risk":
        label_frames = {
            "lhb_negative_net_buy": frame[pd.to_numeric(frame["lhb_net_buy_amount_event"], errors="coerce") < 0],
            "lhb_strong_negative_net_buy": frame[pd.to_numeric(frame["lhb_net_buy_amount_event"], errors="coerce") <= frame["lhb_net_buy_amount_event"].quantile(0.25)],
            "lhb_high_pump_risk": frame[pd.to_numeric(frame["lhb_one_day_pump_risk"], errors="coerce") >= frame["lhb_one_day_pump_risk"].quantile(0.75)],
            "lhb_high_concentration": frame[pd.to_numeric(frame["top_seat_concentration_event"], errors="coerce") >= frame["top_seat_concentration_event"].quantile(0.75)],
            "lhb_repeat_attention": frame[(pd.to_numeric(frame["repeat_on_list_count_3d"], errors="coerce") >= 2) | (pd.to_numeric(frame["repeat_on_list_count_5d"], errors="coerce") >= 3)],
            "lhb_institution_selling": frame[pd.to_numeric(frame["institution_net_buy_event"], errors="coerce") < 0],
        }
        label_col = "risk_signal"
    else:
        label_frames = {
            "lhb_positive_net_buy": frame[pd.to_numeric(frame["lhb_net_buy_amount_event"], errors="coerce") > 0],
            "lhb_institution_positive": frame[pd.to_numeric(frame["institution_net_buy_event"], errors="coerce") > 0],
            "lhb_repeat_with_positive_net_buy": frame[(pd.to_numeric(frame["repeat_on_list_count_3d"], errors="coerce") >= 2) & (pd.to_numeric(frame["lhb_net_buy_amount_event"], errors="coerce") > 0)],
            "lhb_after_break_with_positive_net_buy": frame[(frame["lhb_after_3d"].astype(bool)) & (pd.to_numeric(frame["lhb_net_buy_amount_event"], errors="coerce") > 0)],
            "lhb_after_reversal_with_positive_net_buy": frame[(frame["diagnostic_note"].astype(str).str.contains("reversal", case=False, na=False)) & (pd.to_numeric(frame["lhb_net_buy_amount_event"], errors="coerce") > 0)],
        }
        label_col = "positive_signal"
    rows: list[dict[str, Any]] = []
    for label, group in label_frames.items():
        rows.append(
            {
                label_col: label,
                "sample_count": int(len(group)),
                "avg_future_3d_return": pd.to_numeric(group["future_3d_return"], errors="coerce").mean(),
                "avg_future_5d_return": pd.to_numeric(group["future_5d_return"], errors="coerce").mean(),
                "avg_future_10d_return": pd.to_numeric(group["future_10d_return"], errors="coerce").mean(),
                "win_rate_3d": (pd.to_numeric(group["future_3d_return"], errors="coerce") > 0).mean() if not group.empty else None,
                "win_rate_5d": (pd.to_numeric(group["future_5d_return"], errors="coerce") > 0).mean() if not group.empty else None,
                "win_rate_10d": (pd.to_numeric(group["future_10d_return"], errors="coerce") > 0).mean() if not group.empty else None,
                "avg_future_5d_max_drawdown": pd.to_numeric(group["future_5d_max_drawdown"], errors="coerce").mean(),
                "avg_future_10d_max_drawdown": pd.to_numeric(group["future_10d_max_drawdown"], errors="coerce").mean(),
                "case_type_distribution": str(group["case_type"].value_counts().to_dict()) if "case_type" in group.columns else "{}",
                "success_failure_distribution": str(group["success_or_failure"].value_counts().to_dict()) if "success_or_failure" in group.columns else "{}",
            }
        )
    columns = [
        label_col,
        "sample_count",
        "avg_future_3d_return",
        "avg_future_5d_return",
        "avg_future_10d_return",
        "win_rate_3d",
        "win_rate_5d",
        "win_rate_10d",
        "avg_future_5d_max_drawdown",
        "avg_future_10d_max_drawdown",
        "case_type_distribution",
        "success_failure_distribution",
    ]
    return pd.DataFrame(rows).reindex(columns=columns)


def _build_lhb_case_coverage_summary(curated: pd.DataFrame, alignment_audit: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "total_cases",
        "cases_with_any_lhb",
        "cases_without_lhb",
        "total_case_events",
        "matched_case_events",
        "missing_case_events",
        "matched_rate",
        "by_case_type_matched_rate",
        "by_year_matched_rate",
    ]
    if curated.empty or alignment_audit.empty:
        return pd.DataFrame([
            {
                "total_cases": int(len(curated)),
                "cases_with_any_lhb": 0,
                "cases_without_lhb": int(len(curated)),
                "total_case_events": 0,
                "matched_case_events": 0,
                "missing_case_events": 0,
                "matched_rate": 0.0,
                "by_case_type_matched_rate": "{}",
                "by_year_matched_rate": "{}",
            }
        ], columns=columns)
    matched_cases = alignment_audit[alignment_audit["lhb_alignment_status"] == "matched"]
    cases_with_lhb = int(matched_cases["case_id"].nunique())
    total_case_events = int(len(alignment_audit))
    matched_case_events = int((alignment_audit["lhb_alignment_status"] == "matched").sum())
    by_case_type = {
        key: float((group["lhb_alignment_status"] == "matched").mean())
        for key, group in alignment_audit.groupby("case_type", dropna=False)
    }
    case_year_map = curated.set_index("case_id")["case_year"].to_dict() if "case_id" in curated.columns else {}
    year_series = alignment_audit["case_id"].map(case_year_map)
    by_year = {
        str(key): float((group["lhb_alignment_status"] == "matched").mean())
        for key, group in alignment_audit.assign(case_year=year_series).groupby("case_year", dropna=False)
    }
    return pd.DataFrame([
        {
            "total_cases": int(len(curated)),
            "cases_with_any_lhb": cases_with_lhb,
            "cases_without_lhb": int(len(curated)) - cases_with_lhb,
            "total_case_events": total_case_events,
            "matched_case_events": matched_case_events,
            "missing_case_events": total_case_events - matched_case_events,
            "matched_rate": matched_case_events / total_case_events if total_case_events else 0.0,
            "by_case_type_matched_rate": str(by_case_type),
            "by_year_matched_rate": str(by_year),
        }
    ], columns=columns)


def _merge_failure_v21_view(curated: pd.DataFrame, failure_v21_view: pd.DataFrame) -> pd.DataFrame:
    if curated.empty:
        return curated.copy()
    if failure_v21_view.empty:
        data = curated.copy()
        data["old_verified_case_type"] = data.get("verified_case_type", "")
        data["verified_case_type_v2_1"] = data.get("verified_case_type", "")
        return data
    merged = curated.merge(
        failure_v21_view[
            [
                "case_id",
                "old_verified_case_type",
                "verified_case_type_v2_1",
                "event_date",
                "event_type",
                "label_change_reason",
                "confidence",
                "source_origin",
                "web_source_available",
                "local_event_verified",
            ]
        ].drop_duplicates(subset=["case_id"]),
        on="case_id",
        how="left",
    )
    merged["old_verified_case_type"] = merged["old_verified_case_type"].fillna(merged.get("verified_case_type", ""))
    merged["verified_case_type"] = merged["verified_case_type_v2_1"].fillna(merged.get("verified_case_type", ""))
    merged["case_type"] = merged["verified_case_type"]
    return merged


def _apply_failure_v21_labels_to_alignment(alignment_audit: pd.DataFrame, curated_failure_v21: pd.DataFrame) -> pd.DataFrame:
    if alignment_audit.empty:
        return alignment_audit.copy()
    label_map = curated_failure_v21.set_index("case_id")["verified_case_type_v2_1"].to_dict() if "verified_case_type_v2_1" in curated_failure_v21.columns else {}
    data = alignment_audit.copy()
    data["case_type"] = data["case_id"].map(label_map).fillna(data.get("case_type", ""))
    return data


def _build_lhb_v2_vs_v21_comparison(
    *,
    output_dir: str | Path,
    new_detail: pd.DataFrame,
    curated: pd.DataFrame,
    failure_v21_view: pd.DataFrame,
) -> pd.DataFrame:
    columns = ["metric", "old_value", "v2_1_value", "delta", "interpretation"]
    out = Path(output_dir)
    old_detail_path = out / "lhb_case_event_detail.csv"
    old_detail = pd.read_csv(old_detail_path, low_memory=False) if old_detail_path.exists() else pd.DataFrame()

    old_curated = curated.copy()
    old_curated["old_verified_case_type"] = old_curated.get("verified_case_type", "")

    def _metric(frame: pd.DataFrame, label: str, field: str) -> float | int | None:
        if frame.empty:
            return None
        subset = frame[frame.get("verified_case_type", pd.Series(dtype=str)).fillna("").astype(str) == label]
        if field == "count":
            return int(len(subset))
        if subset.empty:
            return None
        if field == "lhb_after_3d_rate":
            return float(pd.to_numeric(subset["lhb_after_3d"], errors="coerce").fillna(False).astype(bool).mean())
        values = pd.to_numeric(subset[field], errors="coerce")
        return float(values.mean()) if values.notna().any() else None

    def _case_count(frame: pd.DataFrame, label_col: str, label: str) -> int:
        if frame.empty or label_col not in frame.columns:
            return 0
        subset = frame[frame[label_col].fillna("").astype(str) == label]
        return int(subset["case_id"].nunique()) if "case_id" in subset.columns else int(len(subset))

    metric_defs = [
        ("a_kill_failure_count", "a_kill_failure", "count", "A杀样本数变化"),
        ("failed_second_wave_count", "failed_second_wave", "count", "失败二波样本数变化"),
        ("high_open_low_close_failure_count", "high_open_low_close_failure", "count", "高开低走失败样本数变化"),
        ("a_kill_avg_lhb_net_buy", "a_kill_failure", "lhb_net_buy_amount_event", "A杀事件日净买额是否更负"),
        ("a_kill_avg_pump_risk", "a_kill_failure", "lhb_one_day_pump_risk", "A杀 pump risk 是否更高"),
        ("a_kill_avg_future_5d_return", "a_kill_failure", "future_5d_return", "A杀 5 日收益是否更差"),
        ("a_kill_avg_future_10d_return", "a_kill_failure", "future_10d_return", "A杀 10 日收益是否更差"),
        ("a_kill_avg_future_10d_max_drawdown", "a_kill_failure", "future_10d_max_drawdown", "A杀 10 日回撤是否更深"),
        ("failed_second_wave_avg_lhb_net_buy", "failed_second_wave", "lhb_net_buy_amount_event", "失败二波净买额"),
        ("failed_second_wave_after_3d_lhb_rate", "failed_second_wave", "lhb_after_3d_rate", "失败二波事件后 LHB 关注率"),
        ("failed_second_wave_avg_future_10d_return", "failed_second_wave", "future_10d_return", "失败二波 10 日收益"),
    ]
    rows = []
    for metric, label, field, interpretation in metric_defs:
        if field == "count":
            old_value = _case_count(old_curated, "old_verified_case_type", label)
            new_value = _case_count(failure_v21_view, "verified_case_type_v2_1", label)
        else:
            old_value = _metric(old_detail, label, field)
            new_value = _metric(new_detail, label, field)
        delta = (new_value - old_value) if old_value is not None and new_value is not None else None
        rows.append(
            {
                "metric": metric,
                "old_value": old_value,
                "v2_1_value": new_value,
                "delta": delta,
                "interpretation": interpretation,
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns)


def _lhb_case_difference_markdown(
    *,
    case_type_summary: pd.DataFrame,
    event_window: pd.DataFrame,
    risk: pd.DataFrame,
    positive: pd.DataFrame,
    coverage: pd.DataFrame,
    warnings: list[str],
) -> str:
    return "\n".join(
        [
            "# LHB Case/Event Difference Report v1",
            "",
            "## 1. 研究目标",
            "本轮只做案例级资金行为诊断，不接策略、不做回测。",
            "",
            "## 2. 数据来源与样本覆盖",
            _table_preview(coverage, rows=4),
            "",
            "## 3. 成功二波 vs 失败二波",
            _table_preview(case_type_summary[case_type_summary["verified_case_type"].isin(["second_wave", "failed_second_wave"])], rows=16),
            "",
            "## 4. A杀失败样本",
            _table_preview(case_type_summary[case_type_summary["verified_case_type"] == "a_kill_failure"], rows=12),
            "",
            "## 5. 其他失败类型",
            _table_preview(case_type_summary[case_type_summary["verified_case_type"].isin(["failed_reversal", "high_open_low_close_failure", "one_day_pump"])], rows=12),
            "",
            "## 6. LHB 风险信号",
            _table_preview(risk, rows=12),
            "",
            "## 7. LHB 正向确认信号",
            _table_preview(positive, rows=12),
            "",
            "## 8. 对 Dragon Strategy 的启发",
            "LHB 当前更适合作为风险过滤和案例解释，不适合直接进入策略打分。",
            "",
            "## 9. 下一步建议",
            "继续补 failed_reversal / high_open_low_close_failure / one_day_pump 样本。",
            "",
            "### Event Window",
            _table_preview(event_window, rows=20),
            "",
            "### Warnings",
            *(warnings or ["无"]),
        ]
    )


def _lhb_after_failure_rule_v21_markdown(
    *,
    transition_matrix: pd.DataFrame,
    case_type_summary: pd.DataFrame,
    risk_cross: pd.DataFrame,
    comparison: pd.DataFrame,
    warnings: list[str],
) -> str:
    a_kill = case_type_summary[case_type_summary["verified_case_type"] == "a_kill_failure"] if not case_type_summary.empty else case_type_summary
    failed_wave = case_type_summary[case_type_summary["verified_case_type"] == "failed_second_wave"] if not case_type_summary.empty else case_type_summary
    hocl = case_type_summary[case_type_summary["verified_case_type"] == "high_open_low_close_failure"] if not case_type_summary.empty else case_type_summary
    sample_note = []
    if hocl.empty or int(pd.to_numeric(hocl["sample_count"], errors="coerce").fillna(0).sum()) < 3:
        sample_note.append("high_open_low_close_failure 样本仍偏少。")
    if case_type_summary[case_type_summary["verified_case_type"] == "failed_reversal"].empty:
        sample_note.append("failed_reversal 样本偏少。")
    if case_type_summary[case_type_summary["verified_case_type"] == "one_day_pump"].empty:
        sample_note.append("one_day_pump 样本偏少。")
    return "\n".join(
        [
            "# LHB Risk Diagnostics after Failure Rule v2.1",
            "",
            "## 1. 背景",
            "v2.1 收紧了 A杀定义，要求绑定破位上下文，避免深跌但无破位事件的样本被直接归入 A杀。",
            "",
            "## 2. 标签迁移结果",
            _table_preview(transition_matrix, rows=20),
            "",
            "## 3. A杀样本 LHB 特征",
            _table_preview(a_kill, rows=12),
            "",
            "## 4. 失败二波样本 LHB 特征",
            _table_preview(failed_wave, rows=16),
            "",
            "## 5. high_open_low_close_failure",
            _table_preview(hocl, rows=12),
            *(sample_note or [""]),
            "",
            "## 6. 成功二波对照",
            _table_preview(case_type_summary[case_type_summary["verified_case_type"] == "second_wave"], rows=12),
            "",
            "## 7. v2 vs v2.1 结论变化",
            _table_preview(comparison, rows=20),
            "",
            "## 8. 下一步建议",
            "保留 v2.1 的 A杀定义；继续补 failed_reversal / one_day_pump 样本，暂时仍不接策略打分。",
            "",
            "### Risk Cross",
            _table_preview(risk_cross, rows=20),
            "",
            "### Warnings",
            *(warnings or ["无"]),
        ]
    )


def _standardize_lhb_risk_features(detail: pd.DataFrame) -> pd.DataFrame:
    columns = [
        *detail.columns.tolist(),
        "lhb_negative_net_buy",
        "lhb_strong_negative_net_buy",
        "lhb_institution_selling",
        "lhb_high_pump_risk",
        "lhb_high_concentration",
        "lhb_repeat_attention",
        "lhb_after_event_attention",
        "lhb_after_break_attention",
        "lhb_after_reversal_attention",
        "lhb_risk_score",
        "lhb_risk_level",
    ]
    if detail.empty:
        return pd.DataFrame(columns=columns)
    frame = detail.copy()
    net_buy = pd.to_numeric(frame["lhb_net_buy_amount_event"], errors="coerce")
    inst = pd.to_numeric(frame["institution_net_buy_event"], errors="coerce")
    pump = pd.to_numeric(frame["lhb_one_day_pump_risk"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    concentration = pd.to_numeric(frame["top_seat_concentration_event"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    repeat_3d = pd.to_numeric(frame["repeat_on_list_count_3d"], errors="coerce").fillna(0.0)
    repeat_5d = pd.to_numeric(frame["repeat_on_list_count_5d"], errors="coerce").fillna(0.0)
    strong_negative_cutoff = net_buy.dropna().quantile(0.25) if net_buy.notna().any() else 0.0
    high_pump_cutoff = max(0.7, pump.quantile(0.75)) if not pump.empty else 0.7
    high_concentration_cutoff = max(0.5, concentration.quantile(0.75)) if not concentration.empty else 0.5

    frame["lhb_negative_net_buy"] = net_buy < 0
    frame["lhb_strong_negative_net_buy"] = net_buy <= strong_negative_cutoff
    frame["lhb_institution_selling"] = inst < 0
    frame["lhb_high_pump_risk"] = pump >= high_pump_cutoff
    frame["lhb_high_concentration"] = concentration >= high_concentration_cutoff
    frame["lhb_repeat_attention"] = (repeat_3d >= 2) | (repeat_5d >= 3)
    frame["lhb_after_event_attention"] = frame["lhb_after_3d"].fillna(False).astype(bool)
    frame["lhb_after_break_attention"] = frame["event_type"].fillna("").astype(str).eq("break_limit") & frame["lhb_after_event_attention"]
    frame["lhb_after_reversal_attention"] = frame["event_type"].fillna("").astype(str).eq("reversal") & frame["lhb_after_event_attention"]

    negative_net_buy_score = frame["lhb_negative_net_buy"].astype(float)
    institution_selling_score = frame["lhb_institution_selling"].astype(float)
    pump_risk_score = pump
    repeat_attention_score = frame["lhb_repeat_attention"].astype(float)
    concentration_score = concentration
    after_event_attention_score = frame["lhb_after_event_attention"].astype(float)
    frame["lhb_risk_score"] = (
        0.25 * negative_net_buy_score
        + 0.20 * institution_selling_score
        + 0.20 * pump_risk_score
        + 0.15 * repeat_attention_score
        + 0.10 * concentration_score
        + 0.10 * after_event_attention_score
    ).clip(0.0, 1.0)
    frame["lhb_risk_level"] = frame["lhb_risk_score"].map(_risk_level)
    return frame.reindex(columns=columns)


def _build_lhb_follow_exit_replay_detail(risk_detail: pd.DataFrame) -> pd.DataFrame:
    if risk_detail.empty:
        return pd.DataFrame(columns=LHB_FOLLOW_EXIT_REPLAY_COLUMNS)
    frame = risk_detail.copy()
    classifications = frame.apply(_classify_lhb_follow_exit_row, axis=1, result_type="expand")
    frame = pd.concat([frame.reset_index(drop=True), classifications.reset_index(drop=True)], axis=1)
    return frame.reindex(columns=LHB_FOLLOW_EXIT_REPLAY_COLUMNS)


def _classify_lhb_follow_exit_row(row: pd.Series) -> dict[str, str]:
    reasons: list[str] = []
    case_type = str(row.get("verified_case_type") or row.get("case_type") or "").strip()
    event_type = str(row.get("event_type") or "").strip()
    success = str(row.get("success_or_failure") or "").strip().lower()
    net_buy = _num(row.get("lhb_net_buy_amount_event")) or 0.0
    inst_buy = _num(row.get("institution_net_buy_event")) or 0.0
    risk_score = _num(row.get("lhb_risk_score")) or 0.0
    future_5d = _num(row.get("future_5d_return"))
    negative_lhb = bool(row.get("lhb_negative_net_buy")) or bool(row.get("lhb_institution_selling"))
    high_pump = bool(row.get("lhb_high_pump_risk"))
    after_event = bool(row.get("lhb_after_event_attention"))
    failure_structure = case_type in {
        "a_kill_failure",
        "failed_second_wave",
        "failed_reversal",
        "one_day_pump",
        "high_open_low_close_failure",
    } or success == "failure"
    constructive_structure = case_type in {
        "second_wave",
        "dragon_pullback",
        "break_then_reversal",
        "weak_to_strong",
        "continuous_limit_up",
    } or event_type in {"second_wave_start", "reversal", "first_limit_up"}

    if negative_lhb:
        reasons.append("withdrawal_lhb")
    if failure_structure:
        reasons.append("failure_structure")
    if after_event:
        reasons.append("after_event_attention")
    if high_pump:
        reasons.append("high_elasticity_pump")
    if net_buy > 0:
        reasons.append("positive_net_buy")
    if inst_buy > 0:
        reasons.append("institution_support")

    if negative_lhb and (failure_structure or risk_score >= 0.55):
        action = "avoid_withdrawal"
    elif failure_structure and (after_event or negative_lhb or (future_5d is not None and future_5d < 0)):
        action = "exit_confirmation"
    elif constructive_structure and net_buy > 0 and inst_buy >= 0 and risk_score < 0.70:
        action = "follow_candidate"
        reasons.append("positive_lhb_confirmed_structure")
    elif constructive_structure and high_pump and not negative_lhb and risk_score < 0.70:
        action = "high_elasticity_follow"
    else:
        action = "no_follow"

    return {
        "lhb_replay_action": action,
        "lhb_replay_reason": ",".join(dict.fromkeys(reasons)) if reasons else "insufficient_confirmation",
    }


def _build_lhb_follow_exit_effectiveness(detail: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "lhb_replay_action",
        "sample_count",
        "avg_future_3d_return",
        "avg_future_5d_return",
        "avg_future_10d_return",
        "win_rate_3d",
        "win_rate_5d",
        "win_rate_10d",
        "avg_future_5d_max_drawdown",
        "avg_future_10d_max_drawdown",
        "failure_count",
        "success_count",
    ]
    if detail.empty:
        return pd.DataFrame(columns=columns)
    frame = detail.copy()
    for column in FUTURE_DIAGNOSTIC_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    rows: list[dict[str, Any]] = []
    for action, group in frame.groupby("lhb_replay_action", dropna=False):
        future_3d = pd.to_numeric(group["future_3d_return"], errors="coerce")
        future_5d = pd.to_numeric(group["future_5d_return"], errors="coerce")
        future_10d = pd.to_numeric(group["future_10d_return"], errors="coerce")
        rows.append(
            {
                "lhb_replay_action": action,
                "sample_count": len(group),
                "avg_future_3d_return": future_3d.mean(),
                "avg_future_5d_return": future_5d.mean(),
                "avg_future_10d_return": future_10d.mean(),
                "win_rate_3d": (future_3d > 0).mean(),
                "win_rate_5d": (future_5d > 0).mean(),
                "win_rate_10d": (future_10d > 0).mean(),
                "avg_future_5d_max_drawdown": pd.to_numeric(group["future_5d_max_drawdown"], errors="coerce").mean(),
                "avg_future_10d_max_drawdown": pd.to_numeric(group["future_10d_max_drawdown"], errors="coerce").mean(),
                "failure_count": int(group["success_or_failure"].fillna("").astype(str).str.lower().eq("failure").sum()),
                "success_count": int(group["success_or_failure"].fillna("").astype(str).str.lower().eq("success").sum()),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values("lhb_replay_action").reset_index(drop=True)


def _lhb_follow_exit_markdown(
    *,
    replay_detail: pd.DataFrame,
    effectiveness: pd.DataFrame,
    warnings: list[str],
) -> str:
    return "\n".join(
        [
            "# LHB Follow / Exit Replay v1",
            "",
            "## 1. 研究目标",
            "本报告评估龙虎榜短线事件中什么可以跟、什么应该避开、什么构成跑点确认；不生成实盘交易指令。",
            "",
            "## 2. Replay Action 定义",
            "- follow_candidate: 正向 LHB 承接叠加可跟事件结构。",
            "- high_elasticity_follow: 高 pump 或高波动但没有撤退信号的弹性观察。",
            "- avoid_withdrawal: 负净买、机构卖出与失败/高风险共振。",
            "- exit_confirmation: 失败结构后出现 LHB 关注或后续收益确认走弱。",
            "- no_follow: 信息不足或没有清晰确认。",
            "",
            "## 3. 动作有效性",
            _table_preview(effectiveness, rows=20),
            "",
            "## 4. 样本明细预览",
            _table_preview(replay_detail, rows=20),
            "",
            "## 5. Warnings",
            *(warnings or ["无"]),
            "",
        ]
    )


def _build_lhb_shortline_event_replay_detail(
    risk_detail: pd.DataFrame,
    *,
    optional_diagnostics: dict[str, pd.DataFrame],
    market_frame: pd.DataFrame,
) -> pd.DataFrame:
    if risk_detail.empty:
        return pd.DataFrame(columns=LHB_SHORTLINE_EVENT_REPLAY_COLUMNS)
    replay = risk_detail.copy()
    action = replay.apply(_classify_lhb_follow_exit_row, axis=1, result_type="expand")
    replay = pd.concat([replay.reset_index(drop=True), action.reset_index(drop=True)], axis=1)
    replay["lhb_behavior_type"] = replay.apply(_classify_lhb_behavior_type, axis=1)
    replay["event_structure"] = replay["verified_case_type"].fillna("").astype(str)
    replay["trade_date"] = pd.to_datetime(replay["event_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    replay["lhb_event_date"] = replay["event_date"]
    replay["exit_signal"] = replay.apply(_classify_lhb_exit_signal, axis=1)
    replay["exit_reason"] = replay.apply(_classify_lhb_exit_reason, axis=1)
    replay = _attach_lhb_shortline_dragon_fields(replay, optional_diagnostics)
    replay = _attach_lhb_shortline_market_fields(replay, market_frame)
    return replay.reindex(columns=LHB_SHORTLINE_EVENT_REPLAY_COLUMNS)


def _classify_lhb_behavior_type(row: pd.Series) -> str:
    negative = _coerce_bool(row.get("lhb_negative_net_buy")) or _coerce_bool(row.get("lhb_institution_selling"))
    high_pump = _coerce_bool(row.get("lhb_high_pump_risk"))
    net_buy = _num(row.get("lhb_net_buy_amount_event")) or 0.0
    inst_buy = _num(row.get("institution_net_buy_event")) or 0.0
    if negative:
        return "withdrawal"
    if net_buy > 0 and inst_buy >= 0:
        return "support"
    if high_pump:
        return "high_elasticity"
    if _coerce_bool(row.get("lhb_on_event_date")) or _coerce_bool(row.get("lhb_before_3d")) or _coerce_bool(row.get("lhb_after_3d")):
        return "attention"
    return "no_lhb"


def _classify_lhb_exit_signal(row: pd.Series) -> str:
    action = str(row.get("lhb_replay_action") or "")
    if action == "avoid_withdrawal":
        return "hard_exit"
    if action == "exit_confirmation":
        return "reduce_watch"
    return ""


def _classify_lhb_exit_reason(row: pd.Series) -> str:
    signal = _classify_lhb_exit_signal(row)
    if not signal:
        return ""
    reasons = []
    if _coerce_bool(row.get("lhb_negative_net_buy")) or _coerce_bool(row.get("lhb_institution_selling")):
        reasons.append("withdrawal_lhb")
    if str(row.get("success_or_failure") or "").lower() == "failure":
        reasons.append("failure_structure")
    if _coerce_bool(row.get("lhb_after_event_attention")):
        reasons.append("after_event_attention")
    return ",".join(dict.fromkeys(reasons)) or str(row.get("lhb_replay_reason") or "")


def _attach_lhb_shortline_dragon_fields(
    replay: pd.DataFrame,
    optional_diagnostics: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    result = replay.copy()
    dragon_cols = [
        "industry_name",
        "mainline_flag",
        "industry_rank",
        "industry_focus_score_v2",
        "dragon_role",
        "dragon_entry_score",
        "dragon_risk_score",
        "entry_window_v2",
    ]
    for column in dragon_cols:
        if column not in result.columns:
            result[column] = pd.NA
    for diagnostics in optional_diagnostics.values():
        if diagnostics.empty:
            continue
        diag = diagnostics.copy()
        date_col = "trade_date" if "trade_date" in diag.columns else ("event_date" if "event_date" in diag.columns else None)
        code_col = "ts_code" if "ts_code" in diag.columns else None
        if not date_col or not code_col:
            continue
        diag[date_col] = pd.to_datetime(diag[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
        diag[code_col] = diag[code_col].fillna("").astype(str).str.upper()
        use_cols = [code_col, date_col] + [column for column in dragon_cols if column in diag.columns]
        merged = result.merge(
            diag[use_cols].drop_duplicates(subset=[code_col, date_col]),
            left_on=["ts_code", "trade_date"],
            right_on=[code_col, date_col],
            how="left",
            suffixes=("", "_diag"),
        )
        for column in dragon_cols:
            diag_col = f"{column}_diag"
            source_col = diag_col if diag_col in merged.columns else column
            if source_col not in merged.columns:
                continue
            mask = result[column].isna() & merged[source_col].notna()
            result.loc[mask, column] = merged.loc[mask, source_col]
    return result


def _attach_lhb_shortline_market_fields(replay: pd.DataFrame, market_frame: pd.DataFrame) -> pd.DataFrame:
    result = replay.copy()
    market_cols = ["short_market_state", "short_allowed", "market_risk_level"]
    for column in market_cols:
        if column not in result.columns:
            result[column] = pd.NA
    if market_frame.empty:
        return result
    market = market_frame.copy()
    date_col = "trade_date" if "trade_date" in market.columns else ("event_date" if "event_date" in market.columns else None)
    if not date_col:
        return result
    market[date_col] = pd.to_datetime(market[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
    use_cols = [date_col] + [column for column in market_cols if column in market.columns]
    merged = result.merge(
        market[use_cols].drop_duplicates(subset=[date_col]),
        left_on="trade_date",
        right_on=date_col,
        how="left",
        suffixes=("", "_market"),
    )
    for column in market_cols:
        market_col = f"{column}_market"
        source_col = market_col if market_col in merged.columns else column
        if source_col not in merged.columns:
            continue
        mask = result[column].isna() & merged[source_col].notna()
        result.loc[mask, column] = merged.loc[mask, source_col]
    return result


def _lhb_shortline_event_replay_markdown(
    *,
    event_replay: pd.DataFrame,
    warnings: list[str],
) -> str:
    if event_replay.empty:
        action_summary = pd.DataFrame()
        behavior_summary = pd.DataFrame()
    else:
        action_summary = (
            event_replay.groupby(["lhb_replay_action"], dropna=False)
            .agg(
                sample_count=("case_id", "size"),
                avg_future_5d_return=("future_5d_return", "mean"),
                avg_future_10d_max_drawdown=("future_10d_max_drawdown", "mean"),
            )
            .reset_index()
        )
        behavior_summary = (
            event_replay.groupby(["lhb_behavior_type"], dropna=False)
            .agg(
                sample_count=("case_id", "size"),
                avg_future_5d_return=("future_5d_return", "mean"),
                avg_future_10d_max_drawdown=("future_10d_max_drawdown", "mean"),
            )
            .reset_index()
        )
    return "\n".join(
        [
            "# LHB Shortline Event Replay v1",
            "",
            "## 1. 目标",
            "统一龙虎榜、Dragon、市场环境和未来诊断字段，作为后续选股入池和撤退信号校准的基础表。",
            "",
            "## 2. Replay Action Summary",
            _table_preview(action_summary, rows=20),
            "",
            "## 3. LHB Behavior Summary",
            _table_preview(behavior_summary, rows=20),
            "",
            "## 4. Detail Preview",
            _table_preview(event_replay, rows=20),
            "",
            "## 5. Warnings",
            *(warnings or ["无"]),
            "",
        ]
    )


def _build_lhb_follow_avoid_action_effectiveness(event_replay: pd.DataFrame) -> pd.DataFrame:
    columns = ["lhb_replay_action", *LHB_FOLLOW_AVOID_EFFECTIVENESS_COLUMNS]
    if event_replay.empty:
        return pd.DataFrame(columns=columns)
    return _effectiveness_by_group(event_replay, ["lhb_replay_action"], columns)


def _build_lhb_follow_avoid_rule_matrix(event_replay: pd.DataFrame) -> pd.DataFrame:
    group_cols = [
        "lhb_replay_action",
        "lhb_behavior_type",
        "event_structure",
        "dragon_role",
        "entry_window_v2",
        "short_market_state",
        "mainline_flag",
    ]
    columns = [*group_cols, *LHB_FOLLOW_AVOID_EFFECTIVENESS_COLUMNS]
    if event_replay.empty:
        return pd.DataFrame(columns=columns)
    frame = event_replay.copy()
    for column in group_cols:
        if column not in frame.columns:
            frame[column] = ""
    return _effectiveness_by_group(frame, group_cols, columns)


def _build_lhb_follow_avoid_rule_recommendations(rule_matrix: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "rule_recommendation",
        "lhb_replay_action",
        "lhb_behavior_type",
        "event_structure",
        "dragon_role",
        "entry_window_v2",
        "short_market_state",
        "mainline_flag",
        "sample_count",
        "avg_future_5d_return",
        "win_rate_5d",
        "avg_future_5d_max_drawdown",
        "reason",
    ]
    if rule_matrix.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for record in rule_matrix.to_dict("records"):
        action = str(record.get("lhb_replay_action") or "")
        behavior = str(record.get("lhb_behavior_type") or "")
        mainline = _coerce_bool(record.get("mainline_flag"))
        avg_5d = _num(record.get("avg_future_5d_return")) or 0.0
        win_5d = _num(record.get("win_rate_5d")) or 0.0
        dd_5d = _num(record.get("avg_future_5d_max_drawdown")) or 0.0
        if action == "avoid_withdrawal" or behavior == "withdrawal":
            recommendation = "avoid_watch"
            reason = "withdrawal_or_failure_risk"
        elif action == "follow_candidate" and mainline and avg_5d > 0 and win_5d >= 0.5:
            recommendation = "follow_watch"
            reason = "positive_follow_effectiveness"
        elif action == "high_elasticity_follow" and avg_5d > 0 and dd_5d > -0.15:
            recommendation = "high_elasticity_watch"
            reason = "positive_elasticity_with_controlled_drawdown"
        else:
            recommendation = "watch_only"
            reason = "insufficient_follow_evidence"
        rows.append(
            {
                "rule_recommendation": recommendation,
                "lhb_replay_action": action,
                "lhb_behavior_type": behavior,
                "event_structure": record.get("event_structure"),
                "dragon_role": record.get("dragon_role"),
                "entry_window_v2": record.get("entry_window_v2"),
                "short_market_state": record.get("short_market_state"),
                "mainline_flag": record.get("mainline_flag"),
                "sample_count": record.get("sample_count"),
                "avg_future_5d_return": record.get("avg_future_5d_return"),
                "win_rate_5d": record.get("win_rate_5d"),
                "avg_future_5d_max_drawdown": record.get("avg_future_5d_max_drawdown"),
                "reason": reason,
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(["rule_recommendation", "lhb_replay_action"]).reset_index(drop=True)


def _effectiveness_by_group(frame: pd.DataFrame, group_cols: list[str], columns: list[str]) -> pd.DataFrame:
    data = frame.copy()
    for column in [
        "future_3d_return",
        "future_5d_return",
        "future_10d_return",
        "future_5d_max_drawdown",
        "future_10d_max_drawdown",
    ]:
        if column not in data.columns:
            data[column] = pd.NA
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if "success_or_failure" not in data.columns:
        data["success_or_failure"] = ""
    rows: list[dict[str, Any]] = []
    for keys, group in data.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        future_3d = pd.to_numeric(group["future_3d_return"], errors="coerce")
        future_5d = pd.to_numeric(group["future_5d_return"], errors="coerce")
        future_10d = pd.to_numeric(group["future_10d_return"], errors="coerce")
        row = dict(zip(group_cols, keys, strict=False))
        row.update(
            {
                "sample_count": len(group),
                "avg_future_3d_return": future_3d.mean(),
                "avg_future_5d_return": future_5d.mean(),
                "avg_future_10d_return": future_10d.mean(),
                "win_rate_3d": (future_3d > 0).mean(),
                "win_rate_5d": (future_5d > 0).mean(),
                "win_rate_10d": (future_10d > 0).mean(),
                "avg_future_5d_max_drawdown": pd.to_numeric(group["future_5d_max_drawdown"], errors="coerce").mean(),
                "avg_future_10d_max_drawdown": pd.to_numeric(group["future_10d_max_drawdown"], errors="coerce").mean(),
                "success_count": int(group["success_or_failure"].fillna("").astype(str).str.lower().eq("success").sum()),
                "failure_count": int(group["success_or_failure"].fillna("").astype(str).str.lower().eq("failure").sum()),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(group_cols).reset_index(drop=True)


def _lhb_follow_avoid_rule_audit_markdown(
    *,
    action_effectiveness: pd.DataFrame,
    rule_matrix: pd.DataFrame,
    recommendations: pd.DataFrame,
) -> str:
    return "\n".join(
        [
            "# LHB Follow / Avoid Rule Audit v1",
            "",
            "## 1. 目标",
            "基于统一事件回放表校准选股入池与回避规则；本报告不输出交易指令。",
            "",
            "## 2. Action Effectiveness",
            _table_preview(action_effectiveness, rows=20),
            "",
            "## 3. Rule Recommendations",
            _table_preview(recommendations, rows=30),
            "",
            "## 4. Rule Matrix",
            _table_preview(rule_matrix, rows=30),
            "",
        ]
    )


def _build_lhb_exit_signal_effectiveness(event_replay: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "exit_signal",
        *LHB_FOLLOW_AVOID_EFFECTIVENESS_COLUMNS,
    ]
    if event_replay.empty:
        return pd.DataFrame(columns=columns)
    frame = event_replay.copy()
    frame["exit_signal"] = frame.get("exit_signal", pd.Series(dtype="object")).fillna("").astype(str)
    frame = frame[frame["exit_signal"].ne("")]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    return _effectiveness_by_group(frame, ["exit_signal"], columns)


def _build_lhb_exit_reason_effectiveness(event_replay: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "exit_reason",
        *LHB_FOLLOW_AVOID_EFFECTIVENESS_COLUMNS,
    ]
    if event_replay.empty or "exit_reason" not in event_replay.columns:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    frame = event_replay.copy()
    frame["exit_reason"] = frame["exit_reason"].fillna("").astype(str)
    for reason in sorted({part.strip() for value in frame["exit_reason"] for part in value.split(",") if part.strip()}):
        group = frame[frame["exit_reason"].str.split(",").apply(lambda parts: reason in {part.strip() for part in parts})]
        grouped = _effectiveness_by_group(group.assign(exit_reason=reason), ["exit_reason"], columns)
        if not grouped.empty:
            rows.extend(grouped.to_dict("records"))
    return pd.DataFrame(rows).reindex(columns=columns).sort_values("exit_reason").reset_index(drop=True)


def _build_lhb_exit_false_positive_audit(event_replay: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "sample_count",
        "strong_follow_count",
        "exit_flagged_strong_follow_count",
        "false_positive_rate",
        "avg_strong_follow_future_5d_return",
        "avg_exit_flagged_future_5d_return",
    ]
    if event_replay.empty:
        return pd.DataFrame([{column: 0 for column in columns}]).reindex(columns=columns)
    frame = event_replay.copy()
    frame["exit_signal"] = frame.get("exit_signal", pd.Series(dtype="object")).fillna("").astype(str)
    future_5d = pd.to_numeric(frame.get("future_5d_return", pd.Series(dtype=float)), errors="coerce")
    strong_follow = (
        frame.get("lhb_replay_action", pd.Series(dtype="object")).fillna("").astype(str).isin(["follow_candidate", "high_elasticity_follow"])
        & future_5d.gt(0)
    )
    exit_flagged_strong = strong_follow & frame["exit_signal"].ne("")
    strong_count = int(strong_follow.sum())
    exit_flagged_count = int(exit_flagged_strong.sum())
    row = {
        "sample_count": strong_count,
        "strong_follow_count": strong_count,
        "exit_flagged_strong_follow_count": exit_flagged_count,
        "false_positive_rate": exit_flagged_count / strong_count if strong_count else 0.0,
        "avg_strong_follow_future_5d_return": future_5d[strong_follow].mean(),
        "avg_exit_flagged_future_5d_return": future_5d[exit_flagged_strong].mean(),
    }
    return pd.DataFrame([row]).reindex(columns=columns)


def _lhb_exit_rule_audit_markdown(
    *,
    exit_signal_effectiveness: pd.DataFrame,
    exit_reason_effectiveness: pd.DataFrame,
    false_positive_audit: pd.DataFrame,
) -> str:
    return "\n".join(
        [
            "# LHB Exit Rule Audit v1",
            "",
            "## 1. 目标",
            "基于统一事件回放表校准撤退信号，重点验证是否减少 A 杀/失败二波暴露，并观察是否误杀强跟踪样本。",
            "",
            "## 2. Exit Signal Effectiveness",
            _table_preview(exit_signal_effectiveness, rows=20),
            "",
            "## 3. Exit Reason Effectiveness",
            _table_preview(exit_reason_effectiveness, rows=30),
            "",
            "## 4. False Positive Audit",
            _table_preview(false_positive_audit, rows=10),
            "",
        ]
    )


def _build_daily_lhb_shortline_watchlist_frame(
    *,
    event_replay: pd.DataFrame,
    rule_recommendations: pd.DataFrame,
    rule_registry: pd.DataFrame,
    trade_date: str,
) -> pd.DataFrame:
    if event_replay.empty:
        return pd.DataFrame(columns=DAILY_LHB_SHORTLINE_WATCHLIST_COLUMNS)
    frame = event_replay.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame = frame[frame["trade_date"].eq(str(trade_date))].copy()
    if frame.empty:
        return pd.DataFrame(columns=DAILY_LHB_SHORTLINE_WATCHLIST_COLUMNS)
    frame = _attach_daily_lhb_rule_recommendations(frame, rule_recommendations)
    classifications = frame.apply(_classify_daily_lhb_watch_row, axis=1, result_type="expand")
    frame = pd.concat([frame.reset_index(drop=True), classifications.reset_index(drop=True)], axis=1)
    frame = _attach_lhb_shortline_rule_registry(frame, rule_registry)
    frame = _apply_lhb_shortline_rule_calibration(frame)
    frame["_priority"] = frame["watch_group"].map(
        {
            "exit_watch": 0,
            "avoid_watch": 1,
            "follow_watch": 2,
            "high_elasticity_watch": 3,
            "watch_only": 4,
        }
    ).fillna(9)
    frame = frame.sort_values(["_priority", "ts_code"], kind="stable").drop(columns=["_priority"])
    return frame.reindex(columns=DAILY_LHB_SHORTLINE_WATCHLIST_COLUMNS).reset_index(drop=True)


def _attach_daily_lhb_rule_recommendations(frame: pd.DataFrame, rule_recommendations: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["rule_recommendation"] = ""
    result["rule_recommendation_reason"] = ""
    if rule_recommendations.empty:
        return result
    keys = [
        "lhb_replay_action",
        "lhb_behavior_type",
        "event_structure",
        "dragon_role",
        "entry_window_v2",
        "short_market_state",
        "mainline_flag",
    ]
    recs = rule_recommendations.copy()
    for column in keys:
        if column not in recs.columns:
            recs[column] = ""
        if column not in result.columns:
            result[column] = ""
    use_cols = keys + [column for column in ["rule_recommendation", "reason"] if column in recs.columns]
    merged = result.merge(
        recs[use_cols].drop_duplicates(subset=keys),
        on=keys,
        how="left",
        suffixes=("", "_rec"),
    )
    if "rule_recommendation_rec" in merged.columns:
        result["rule_recommendation"] = merged["rule_recommendation_rec"].fillna("")
    elif "rule_recommendation" in merged.columns:
        result["rule_recommendation"] = merged["rule_recommendation"].fillna("")
    if "reason" in merged.columns:
        result["rule_recommendation_reason"] = merged["reason"].fillna("")
    return result


def _attach_lhb_shortline_rule_registry(frame: pd.DataFrame, rule_registry: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    defaults = {
        "lhb_shortline_rule_version": "",
        "lhb_shortline_follow_rule_id": "",
        "lhb_shortline_exit_rule_id": "",
        "lhb_shortline_rule_confidence": "",
        "lhb_shortline_rule_sample_count": "",
        "rule_calibration_action": "",
    }
    for column, value in defaults.items():
        result[column] = pd.Series([value] * len(result), index=result.index, dtype="object")
    if rule_registry.empty:
        return result

    registry = rule_registry.copy()
    for column in LHB_SHORTLINE_RULE_REGISTRY_COLUMNS:
        if column not in registry.columns:
            registry[column] = ""
    exit_rules = registry[registry["rule_scope"].fillna("").astype(str).eq("exit")]
    follow_rules = registry[registry["rule_scope"].fillna("").astype(str).eq("follow")]
    result = result.apply(lambda row: _apply_lhb_shortline_rule_row(row, exit_rules=exit_rules, follow_rules=follow_rules), axis=1)
    return result


def _apply_lhb_shortline_rule_row(
    row: pd.Series,
    *,
    exit_rules: pd.DataFrame,
    follow_rules: pd.DataFrame,
) -> pd.Series:
    result = row.copy()
    exit_match = _match_lhb_shortline_exit_rule(result, exit_rules)
    if exit_match is not None:
        _write_lhb_shortline_rule_fields(result, exit_match, rule_id_field="lhb_shortline_exit_rule_id")
        return result
    follow_match = _match_lhb_shortline_follow_rule(result, follow_rules)
    if follow_match is not None:
        _write_lhb_shortline_rule_fields(result, follow_match, rule_id_field="lhb_shortline_follow_rule_id")
    return result


def _write_lhb_shortline_rule_fields(row: pd.Series, rule: pd.Series, *, rule_id_field: str) -> None:
    row["lhb_shortline_rule_version"] = _clean_lhb_reason(rule.get("lhb_shortline_rule_version"))
    row[rule_id_field] = _clean_lhb_reason(rule.get("rule_id"))
    row["lhb_shortline_rule_confidence"] = _clean_lhb_reason(rule.get("lhb_shortline_rule_confidence"))
    row["lhb_shortline_rule_sample_count"] = rule.get("lhb_shortline_rule_sample_count", "")
    row["rule_calibration_action"] = _clean_lhb_reason(rule.get("rule_recommendation"))


def _match_lhb_shortline_exit_rule(row: pd.Series, exit_rules: pd.DataFrame) -> pd.Series | None:
    if exit_rules.empty:
        return None
    row_signal = _clean_lhb_reason(row.get("exit_signal"))
    row_reasons = _split_lhb_reason_set(row.get("exit_reason"))
    for _, rule in exit_rules.iterrows():
        rule_signal = _clean_lhb_reason(rule.get("exit_signal"))
        rule_reason = _clean_lhb_reason(rule.get("exit_reason"))
        if rule_signal and rule_signal != row_signal:
            continue
        if rule_reason and rule_reason not in row_reasons:
            continue
        return rule
    return None


def _match_lhb_shortline_follow_rule(row: pd.Series, follow_rules: pd.DataFrame) -> pd.Series | None:
    if follow_rules.empty:
        return None
    for _, rule in follow_rules.iterrows():
        if _clean_lhb_reason(rule.get("watch_group")) and _clean_lhb_reason(rule.get("watch_group")) != _clean_lhb_reason(row.get("watch_group")):
            continue
        if _clean_lhb_reason(rule.get("lhb_behavior_type")) and _clean_lhb_reason(rule.get("lhb_behavior_type")) != _clean_lhb_reason(row.get("lhb_behavior_type")):
            continue
        if _clean_lhb_reason(rule.get("event_structure")) and _clean_lhb_reason(rule.get("event_structure")) != _clean_lhb_reason(row.get("event_structure")):
            continue
        return rule
    return None


def _apply_lhb_shortline_rule_calibration(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    action = result["rule_calibration_action"].fillna("").astype(str)
    downgrade_exit = action.eq("downgrade_to_reduce_watch")
    if downgrade_exit.any():
        result.loc[downgrade_exit, "exit_signal"] = "reduce_watch"
        result.loc[downgrade_exit, "watch_group"] = "exit_watch"
        result.loc[downgrade_exit, "watch_reason"] = result.loc[downgrade_exit].apply(
            lambda row: ",".join(
                dict.fromkeys(
                    reason
                    for reason in [
                        _clean_lhb_reason(row.get("watch_reason")),
                        _clean_lhb_reason(row.get("rule_calibration_action")),
                    ]
                    if reason
                )
            ),
            axis=1,
        )
    return result


def _split_lhb_reason_set(value: Any) -> set[str]:
    text = _clean_lhb_reason(value)
    if not text:
        return set()
    return {part.strip() for part in text.split(",") if part.strip()}


def _classify_daily_lhb_watch_row(row: pd.Series) -> dict[str, str]:
    exit_signal = str(row.get("exit_signal") or "").strip()
    action = str(row.get("lhb_replay_action") or "").strip()
    behavior = str(row.get("lhb_behavior_type") or "").strip()
    recommendation = str(row.get("rule_recommendation") or "").strip()
    reasons = [
        str(row.get("rule_recommendation_reason") or "").strip(),
        str(row.get("lhb_replay_reason") or "").strip(),
    ]
    if exit_signal:
        group = "avoid_watch" if exit_signal == "hard_exit" else "exit_watch"
        reasons.append(str(row.get("exit_reason") or "").strip())
    elif action == "avoid_withdrawal" or behavior == "withdrawal" or recommendation == "avoid_watch":
        group = "avoid_watch"
    elif recommendation in {"follow_watch", "high_elasticity_watch"}:
        group = recommendation
    elif action == "follow_candidate":
        group = "follow_watch"
    elif action == "high_elasticity_follow":
        group = "high_elasticity_watch"
    else:
        group = "watch_only"
    return {
        "watch_group": group,
        "watch_reason": ",".join(dict.fromkeys(reason for reason in (_clean_lhb_reason(reason) for reason in reasons) if reason)),
    }


def _clean_lhb_reason(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null", "<na>"} else text


def _daily_lhb_shortline_watchlist_markdown(*, watchlist: pd.DataFrame, trade_date: str) -> str:
    lines = [
        f"# Daily LHB Shortline Watchlist {trade_date}",
        "",
        "## 1. 说明",
        "本报告只输出短线观察池和撤退提示，不生成自动交易指令。",
        "",
    ]
    if watchlist.empty:
        lines.append("- 无观察样本。")
        return "\n".join(lines) + "\n"
    for group in ["follow_watch", "high_elasticity_watch", "avoid_watch", "exit_watch", "watch_only"]:
        subset = watchlist[watchlist["watch_group"].eq(group)]
        lines.extend([f"## {group}", _table_preview(subset, rows=30), ""])
    return "\n".join(lines) + "\n"


def _build_lhb_shortline_strategy_effectiveness_detail(
    *,
    event_replay: pd.DataFrame,
    daily_watchlist: pd.DataFrame,
) -> pd.DataFrame:
    if event_replay.empty:
        return pd.DataFrame(columns=LHB_SHORTLINE_STRATEGY_EFFECTIVENESS_DETAIL_COLUMNS)
    frame = event_replay.copy()
    for column in LHB_SHORTLINE_STRATEGY_EFFECTIVENESS_DETAIL_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["ts_code"] = frame["ts_code"].fillna("").astype(str).str.strip().str.upper()
    frame["watch_group"] = _infer_lhb_shortline_watch_group_series(frame)

    watchlist = _normalize_lhb_shortline_daily_watchlist_for_effectiveness(daily_watchlist)
    if not watchlist.empty:
        frame = frame.merge(
            watchlist,
            on=["trade_date", "ts_code"],
            how="left",
            suffixes=("", "_daily"),
        )
        daily_group = frame.get("watch_group_daily", pd.Series(dtype="object")).fillna("").astype(str).str.strip()
        frame["watch_group"] = frame["watch_group"].where(daily_group.eq(""), daily_group)
        frame = frame.drop(columns=[column for column in ["watch_group_daily"] if column in frame.columns])

    for column in [
        "future_1d_return",
        "future_3d_return",
        "future_5d_return",
        "future_10d_return",
        "future_5d_max_drawdown",
        "future_10d_max_drawdown",
    ]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in ["limit_up_within_5d", "a_kill_within_5d", "second_wave_success"]:
        frame[column] = frame[column].map(_coerce_lhb_bool)
    frame["exit_signal"] = frame["exit_signal"].fillna("").astype(str).str.strip()
    frame["exit_reason"] = frame["exit_reason"].fillna("").astype(str).str.strip()
    frame["exit_hit"] = (frame["exit_signal"].ne("") & (frame["future_5d_return"].lt(0) | frame["a_kill_within_5d"])).astype(object)
    return frame.reindex(columns=LHB_SHORTLINE_STRATEGY_EFFECTIVENESS_DETAIL_COLUMNS).reset_index(drop=True)


def _normalize_lhb_shortline_daily_watchlist_for_effectiveness(daily_watchlist: pd.DataFrame) -> pd.DataFrame:
    columns = ["trade_date", "ts_code", "watch_group"]
    if daily_watchlist.empty:
        return pd.DataFrame(columns=[*columns[:2], "watch_group_daily"])
    frame = daily_watchlist.copy()
    for column in columns:
        if column not in frame.columns:
            frame[column] = ""
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["ts_code"] = frame["ts_code"].fillna("").astype(str).str.strip().str.upper()
    frame["watch_group_daily"] = frame["watch_group"].fillna("").astype(str).str.strip()
    return frame.loc[:, ["trade_date", "ts_code", "watch_group_daily"]].drop_duplicates(
        subset=["trade_date", "ts_code"],
        keep="last",
    )


def _infer_lhb_shortline_watch_group_series(frame: pd.DataFrame) -> pd.Series:
    action = frame.get("lhb_replay_action", pd.Series(dtype="object")).fillna("").astype(str).str.strip()
    behavior = frame.get("lhb_behavior_type", pd.Series(dtype="object")).fillna("").astype(str).str.strip()
    exit_signal = frame.get("exit_signal", pd.Series(dtype="object")).fillna("").astype(str).str.strip()
    result = pd.Series("watch_only", index=frame.index, dtype="object")
    result = result.mask(action.eq("follow_candidate"), "follow_watch")
    result = result.mask(action.eq("high_elasticity_follow"), "high_elasticity_watch")
    result = result.mask(action.eq("avoid_withdrawal") | behavior.eq("withdrawal"), "avoid_watch")
    result = result.mask(exit_signal.ne("") & ~exit_signal.eq("hard_exit"), "exit_watch")
    result = result.mask(exit_signal.eq("hard_exit"), "avoid_watch")
    return result


def _build_lhb_shortline_strategy_effectiveness_summary(
    detail: pd.DataFrame,
    *,
    group_cols: list[str],
    min_sample_count: int,
) -> pd.DataFrame:
    columns = [*group_cols, *LHB_SHORTLINE_STRATEGY_EFFECTIVENESS_METRIC_COLUMNS]
    if detail.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    frame = detail.copy()
    for column in group_cols:
        if column not in frame.columns:
            frame[column] = ""
        frame[column] = frame[column].fillna("").astype(str)
    for keys, group in frame.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = dict(zip(group_cols, keys, strict=False))
        row.update(_lhb_shortline_effectiveness_metrics(group, min_sample_count=min_sample_count))
        rows.append(row)
    result = pd.DataFrame(rows).reindex(columns=columns)
    if "low_sample_flag" in result.columns:
        result["low_sample_flag"] = result["low_sample_flag"].astype(object)
    return result.sort_values(
        ["low_sample_flag", "sample_count", *group_cols],
        ascending=[True, False, *([True] * len(group_cols))],
        kind="stable",
    ).reset_index(drop=True)


def _build_lhb_shortline_exit_combo_effectiveness(
    detail: pd.DataFrame,
    *,
    min_sample_count: int,
) -> pd.DataFrame:
    group_cols = ["exit_signal", "exit_reason"]
    columns = [*group_cols, *LHB_SHORTLINE_STRATEGY_EFFECTIVENESS_METRIC_COLUMNS]
    if detail.empty:
        return pd.DataFrame(columns=columns)
    frame = detail.copy()
    frame["exit_signal"] = frame["exit_signal"].fillna("").astype(str).str.strip()
    frame["exit_reason"] = frame["exit_reason"].fillna("").astype(str)
    frame = frame[frame["exit_signal"].ne("") | frame["exit_reason"].str.strip().ne("")]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for reason in sorted({part.strip() for value in frame["exit_reason"] for part in value.split(",") if part.strip()}):
        subset = frame[frame["exit_reason"].str.split(",").apply(lambda parts: reason in {part.strip() for part in parts})]
        for exit_signal, group in subset.groupby("exit_signal", dropna=False):
            row = {"exit_signal": exit_signal, "exit_reason": reason}
            row.update(_lhb_shortline_effectiveness_metrics(group, min_sample_count=min_sample_count))
            rows.append(row)
    if not rows:
        for exit_signal, group in frame.groupby("exit_signal", dropna=False):
            row = {"exit_signal": exit_signal, "exit_reason": ""}
            row.update(_lhb_shortline_effectiveness_metrics(group, min_sample_count=min_sample_count))
            rows.append(row)
    result = pd.DataFrame(rows).reindex(columns=columns)
    if "low_sample_flag" in result.columns:
        result["low_sample_flag"] = result["low_sample_flag"].astype(object)
    return result.sort_values(
        ["low_sample_flag", "sample_count", "exit_signal", "exit_reason"],
        ascending=[True, False, True, True],
        kind="stable",
    ).reset_index(drop=True)


def _lhb_shortline_effectiveness_metrics(group: pd.DataFrame, *, min_sample_count: int) -> dict[str, Any]:
    future_1d = pd.to_numeric(group["future_1d_return"], errors="coerce")
    future_3d = pd.to_numeric(group["future_3d_return"], errors="coerce")
    future_5d = pd.to_numeric(group["future_5d_return"], errors="coerce")
    future_10d = pd.to_numeric(group["future_10d_return"], errors="coerce")
    sample_count = int(len(group))
    return {
        "sample_count": sample_count,
        "avg_future_1d_return": future_1d.mean(),
        "avg_future_3d_return": future_3d.mean(),
        "avg_future_5d_return": future_5d.mean(),
        "avg_future_10d_return": future_10d.mean(),
        "win_rate_1d": (future_1d > 0).mean() if future_1d.notna().any() else None,
        "win_rate_3d": (future_3d > 0).mean() if future_3d.notna().any() else None,
        "win_rate_5d": (future_5d > 0).mean() if future_5d.notna().any() else None,
        "win_rate_10d": (future_10d > 0).mean() if future_10d.notna().any() else None,
        "avg_future_5d_max_drawdown": pd.to_numeric(group["future_5d_max_drawdown"], errors="coerce").mean(),
        "avg_future_10d_max_drawdown": pd.to_numeric(group["future_10d_max_drawdown"], errors="coerce").mean(),
        "limit_up_rate_5d": group["limit_up_within_5d"].map(_coerce_lhb_bool).mean(),
        "a_kill_rate_5d": group["a_kill_within_5d"].map(_coerce_lhb_bool).mean(),
        "second_wave_success_rate": group["second_wave_success"].map(_coerce_lhb_bool).mean(),
        "exit_hit_rate": group["exit_hit"].map(_coerce_lhb_bool).mean(),
        "low_sample_flag": bool(sample_count < min_sample_count),
    }


def _coerce_lhb_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or pd.isna(value):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "t"}


def _lhb_shortline_strategy_effectiveness_markdown(
    *,
    summary: pd.DataFrame,
    follow_combo: pd.DataFrame,
    exit_combo: pd.DataFrame,
    min_sample_count: int,
) -> str:
    return "\n".join(
        [
            "# LHB Shortline Strategy Effectiveness v1",
            "",
            "## 1. 目标",
            "复盘 Phase 1-5 形成的龙虎榜短线分组，判断什么可以跟、什么时候该跑。本报告不改变当日入池规则。",
            "",
            f"- Low sample threshold: {min_sample_count}",
            "",
            "## 2. Watch Group Summary",
            _table_preview(summary, rows=20),
            "",
            "## 3. Top Follow / Elasticity Combos",
            _table_preview(follow_combo, rows=30),
            "",
            "## 4. Exit Combos",
            _table_preview(exit_combo, rows=30),
            "",
        ]
    )


def _build_lhb_shortline_shadow_backtest_candidates(
    *,
    event_replay: pd.DataFrame,
    start_date: str,
    end_date: str,
    pool_mode: str,
) -> pd.DataFrame:
    if event_replay.empty:
        return pd.DataFrame(columns=LHB_SHORTLINE_SHADOW_BACKTEST_SELECTED_COLUMNS)
    frame = event_replay.copy()
    for column in LHB_SHORTLINE_SHADOW_BACKTEST_SELECTED_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    start = pd.to_datetime(start_date, errors="coerce")
    end = pd.to_datetime(end_date, errors="coerce")
    frame = frame[frame["trade_date"].notna()]
    if not pd.isna(start):
        frame = frame[frame["trade_date"].ge(start)]
    if not pd.isna(end):
        frame = frame[frame["trade_date"].le(end)]

    frame["ts_code"] = frame["ts_code"].fillna("").astype(str).str.strip().str.upper()
    frame = frame[frame["ts_code"].map(_is_lhb_full_market_stock_code)].copy()
    frame["lhb_behavior_type"] = frame["lhb_behavior_type"].fillna("").astype(str).str.strip()
    frame["lhb_replay_action"] = frame["lhb_replay_action"].fillna("").astype(str).str.strip()
    frame["event_structure"] = frame["event_structure"].fillna("").astype(str).str.strip()
    frame = _filter_lhb_shadow_pool(frame, pool_mode=pool_mode)
    if frame.empty:
        return pd.DataFrame(columns=LHB_SHORTLINE_SHADOW_BACKTEST_SELECTED_COLUMNS)

    for column in [
        "lhb_risk_score",
        "dragon_entry_score",
        "industry_focus_score_v2",
        "future_1d_return",
        "future_3d_return",
        "future_5d_return",
        "future_10d_return",
        "future_5d_max_drawdown",
    ]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["selection_score"] = (
        frame["dragon_entry_score"].fillna(0.0)
        + frame["industry_focus_score_v2"].fillna(0.0)
        - frame["lhb_risk_score"].fillna(0.0) * 10.0
    )
    frame["pool_mode"] = pool_mode
    frame = frame.sort_values(
        ["trade_date", "ts_code", "lhb_risk_score", "selection_score", "dragon_entry_score", "industry_focus_score_v2"],
        ascending=[True, True, True, False, False, False],
        kind="stable",
    ).drop_duplicates(subset=["trade_date", "ts_code"], keep="first")
    frame["trade_date"] = frame["trade_date"].dt.strftime("%Y-%m-%d")
    return frame.reset_index(drop=True)


def _filter_lhb_shadow_pool(frame: pd.DataFrame, *, pool_mode: str) -> pd.DataFrame:
    mode = str(pool_mode or "strict_second_wave").strip()
    action = frame["lhb_replay_action"].fillna("").astype(str).str.strip()
    behavior = frame["lhb_behavior_type"].fillna("").astype(str).str.strip()
    structure = frame["event_structure"].fillna("").astype(str).str.strip()
    exit_signal = frame.get("exit_signal", pd.Series("", index=frame.index)).fillna("").astype(str).str.strip()
    risk_score = pd.to_numeric(frame.get("lhb_risk_score", pd.Series(0.0, index=frame.index)), errors="coerce").fillna(0.0)
    net_buy = pd.to_numeric(
        frame.get("lhb_net_buy_amount_event", frame.get("lhb_net_buy_amount", pd.Series(0.0, index=frame.index))),
        errors="coerce",
    ).fillna(0.0)
    inst_buy = pd.to_numeric(
        frame.get("institution_net_buy_event", frame.get("institution_net_buy", pd.Series(0.0, index=frame.index))),
        errors="coerce",
    ).fillna(0.0)
    not_hard_exit = ~exit_signal.eq("hard_exit")
    not_withdrawal = ~behavior.eq("withdrawal") & ~action.eq("avoid_withdrawal")

    if mode == "strict_second_wave":
        mask = behavior.eq("support") & action.eq("follow_candidate") & structure.eq("second_wave")
    elif mode == "broad_follow":
        mask = action.eq("follow_candidate")
    elif mode == "support_attention":
        mask = behavior.isin(["support", "attention"]) & not_withdrawal & not_hard_exit
    elif mode == "raw_lhb_positive":
        mask = net_buy.gt(0) & inst_buy.ge(0) & risk_score.lt(0.70) & not_withdrawal & not_hard_exit
    else:
        raise ValueError(
            "pool_mode must be one of: strict_second_wave, broad_follow, support_attention, raw_lhb_positive"
        )
    return frame[mask].copy()


def _build_lhb_shortline_shadow_backtest_selected(
    candidates: pd.DataFrame,
    *,
    top_n_values: list[int],
) -> pd.DataFrame:
    columns = LHB_SHORTLINE_SHADOW_BACKTEST_SELECTED_COLUMNS
    clean_top_n = _normalize_lhb_shadow_top_n_values(top_n_values)
    if candidates.empty or not clean_top_n:
        return pd.DataFrame(columns=columns)
    frame = candidates.copy()
    rows: list[pd.DataFrame] = []
    for top_n in clean_top_n:
        selected_days: list[pd.DataFrame] = []
        for _, group in frame.groupby("trade_date", dropna=False):
            ranked = group.sort_values(
                ["lhb_risk_score", "selection_score", "dragon_entry_score", "industry_focus_score_v2", "ts_code"],
                ascending=[True, False, False, False, True],
                kind="stable",
            ).head(top_n).copy()
            ranked["selection_rank"] = range(1, len(ranked) + 1)
            ranked["top_n"] = top_n
            selected_days.append(ranked)
        if selected_days:
            rows.append(pd.concat(selected_days, ignore_index=True))
    if not rows:
        return pd.DataFrame(columns=columns)
    result = pd.concat(rows, ignore_index=True)
    return result.reindex(columns=columns).reset_index(drop=True)


def _build_lhb_shortline_shadow_backtest_daily_curve(selected: pd.DataFrame) -> pd.DataFrame:
    columns = LHB_SHORTLINE_SHADOW_BACKTEST_DAILY_CURVE_COLUMNS
    if selected.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for (pool_mode, top_n, trade_date), group in selected.groupby(["pool_mode", "top_n", "trade_date"], dropna=False):
        rows.append(
            {
                "pool_mode": pool_mode,
                "top_n": top_n,
                "trade_date": trade_date,
                "selected_count": int(len(group)),
                "daily_1d_return": pd.to_numeric(group["future_1d_return"], errors="coerce").mean(),
                "daily_3d_return": pd.to_numeric(group["future_3d_return"], errors="coerce").mean(),
                "daily_5d_return": pd.to_numeric(group["future_5d_return"], errors="coerce").mean(),
                "daily_10d_return": pd.to_numeric(group["future_10d_return"], errors="coerce").mean(),
                "daily_5d_max_drawdown": pd.to_numeric(group["future_5d_max_drawdown"], errors="coerce").mean(),
            }
        )
    curve = pd.DataFrame(rows).sort_values(["top_n", "trade_date"], kind="stable").reset_index(drop=True)
    equity_parts: list[pd.DataFrame] = []
    for _, group in curve.groupby("top_n", dropna=False):
        part = group.copy()
        daily_5d = pd.to_numeric(part["daily_5d_return"], errors="coerce").fillna(0.0)
        part["equity_5d_proxy"] = (1.0 + daily_5d).cumprod()
        running_max = part["equity_5d_proxy"].cummax()
        part["drawdown_5d_proxy"] = part["equity_5d_proxy"] / running_max - 1.0
        equity_parts.append(part)
    return pd.concat(equity_parts, ignore_index=True).reindex(columns=columns)


def _build_lhb_shortline_shadow_backtest_summary(
    *,
    selected: pd.DataFrame,
    daily_curve: pd.DataFrame,
    start_date: str,
    end_date: str,
    top_n_values: list[int],
    pool_mode: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for top_n in _normalize_lhb_shadow_top_n_values(top_n_values):
        trades = selected[selected["top_n"].eq(top_n)] if not selected.empty else pd.DataFrame()
        curve = daily_curve[daily_curve["top_n"].eq(top_n)] if not daily_curve.empty else pd.DataFrame()
        future_5d = pd.to_numeric(trades.get("future_5d_return", pd.Series(dtype="float64")), errors="coerce")
        valid_future_5d = future_5d.dropna()
        row = {
            "pool_mode": pool_mode,
            "top_n": top_n,
            "start_date": start_date,
            "end_date": end_date,
            "signal_day_count": int(curve["trade_date"].nunique()) if not curve.empty else 0,
            "selected_trade_count": int(len(trades)),
            "avg_trade_1d_return": pd.to_numeric(trades.get("future_1d_return", pd.Series(dtype="float64")), errors="coerce").mean(),
            "avg_trade_3d_return": pd.to_numeric(trades.get("future_3d_return", pd.Series(dtype="float64")), errors="coerce").mean(),
            "avg_trade_5d_return": future_5d.mean(),
            "avg_trade_10d_return": pd.to_numeric(trades.get("future_10d_return", pd.Series(dtype="float64")), errors="coerce").mean(),
            "win_rate_5d": (valid_future_5d > 0).mean() if not valid_future_5d.empty else None,
            "avg_trade_5d_max_drawdown": pd.to_numeric(
                trades.get("future_5d_max_drawdown", pd.Series(dtype="float64")),
                errors="coerce",
            ).mean(),
            "avg_daily_5d_return": pd.to_numeric(
                curve.get("daily_5d_return", pd.Series(dtype="float64")),
                errors="coerce",
            ).mean(),
            "final_equity_5d_proxy": pd.to_numeric(
                curve.get("equity_5d_proxy", pd.Series(dtype="float64")),
                errors="coerce",
            ).iloc[-1]
            if not curve.empty
            else None,
            "max_drawdown_5d_proxy": pd.to_numeric(
                curve.get("drawdown_5d_proxy", pd.Series(dtype="float64")),
                errors="coerce",
            ).min()
            if not curve.empty
            else None,
        }
        rows.append(row)
    return pd.DataFrame(rows).reindex(columns=LHB_SHORTLINE_SHADOW_BACKTEST_SUMMARY_COLUMNS)


def _is_lhb_full_market_stock_code(ts_code: Any) -> bool:
    text = str(ts_code or "").strip().upper()
    if "." not in text:
        return False
    symbol, exchange = text.split(".", 1)
    if exchange not in {"SH", "SZ"} or len(symbol) != 6 or not symbol.isdigit():
        return False
    return symbol.startswith(("000", "001", "002", "003", "300", "301", "600", "601", "603", "605", "688"))


def _normalize_lhb_shadow_top_n_values(top_n_values: list[int]) -> list[int]:
    result: list[int] = []
    for value in top_n_values:
        number = int(value)
        if number > 0 and number not in result:
            result.append(number)
    return result


def _lhb_shortline_shadow_backtest_markdown(
    *,
    summary: pd.DataFrame,
    selected: pd.DataFrame,
    daily_curve: pd.DataFrame,
    start_date: str,
    end_date: str,
    top_n_values: list[int],
    pool_mode: str,
) -> str:
    return "\n".join(
        [
            "# LHB Shortline Shadow Backtest v1",
            "",
            "## 1. Scope",
            f"- Date range: {start_date} to {end_date}",
            f"- Top-N values: {', '.join(str(value) for value in _normalize_lhb_shadow_top_n_values(top_n_values))}",
            f"- Pool mode: {pool_mode}",
            "- De-duplication: trade_date + ts_code, keeping the strongest ranked row",
            "- This is an event-level shadow replay, not an executable fill/slippage portfolio simulation.",
            "",
            "## 2. Top-N Summary",
            _table_preview(summary, rows=20),
            "",
            "## 3. Daily 5D Proxy Curve",
            _table_preview(daily_curve, rows=30),
            "",
            "## 4. Selected Trade Preview",
            _table_preview(selected, rows=30),
            "",
        ]
    )


def _build_lhb_shortline_intraday_confirmation_detail(
    *,
    candidates: pd.DataFrame,
    minute_bars: pd.DataFrame,
) -> pd.DataFrame:
    columns = LHB_SHORTLINE_INTRADAY_CONFIRMATION_DETAIL_COLUMNS
    if candidates.empty:
        return pd.DataFrame(columns=columns)

    candidate_frame = candidates.copy()
    for column in columns:
        if column not in candidate_frame.columns:
            candidate_frame[column] = pd.NA
    candidate_frame["trade_date"] = pd.to_datetime(candidate_frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    candidate_frame["ts_code"] = candidate_frame["ts_code"].fillna("").astype(str).str.strip().str.upper()
    if "top_n" in candidate_frame.columns:
        candidate_frame["_top_n_sort"] = pd.to_numeric(candidate_frame["top_n"], errors="coerce")
        candidate_frame = candidate_frame.sort_values(["trade_date", "ts_code", "_top_n_sort"], kind="stable")
    candidate_frame = candidate_frame.drop_duplicates(subset=["trade_date", "ts_code"], keep="first")

    bars = _normalize_lhb_intraday_minute_bars(minute_bars)
    bars_by_code = {
        str(ts_code): group.reset_index(drop=True)
        for ts_code, group in bars.groupby("ts_code", sort=False)
    } if not bars.empty else {}
    rows: list[dict[str, Any]] = []
    for record in candidate_frame.to_dict("records"):
        trade_date = str(record.get("trade_date") or "")
        ts_code = str(record.get("ts_code") or "")
        asset_bars = bars_by_code.get(ts_code, pd.DataFrame())
        next_bars = _next_lhb_confirmation_bars(asset_bars, trade_date)
        metrics = _lhb_intraday_confirmation_metrics(next_bars)
        action, reason = _classify_lhb_intraday_confirmation(metrics)
        rows.append(
            {
                "trade_date": trade_date,
                "ts_code": ts_code,
                "stock_name": _clean_lhb_reason(record.get("stock_name")),
                "top_n": record.get("top_n", ""),
                "confirmation_trade_date": metrics.get("confirmation_trade_date", ""),
                "intraday_confirmation_action": action,
                "intraday_confirmation_reason": reason,
                "minute_bar_count": metrics.get("minute_bar_count", 0),
                "entry_time_proxy": metrics.get("entry_time_proxy", ""),
                "entry_price_proxy": metrics.get("entry_price_proxy"),
                "first_60m_return": metrics.get("first_60m_return"),
                "intraday_return": metrics.get("intraday_return"),
                "high_to_close_drawdown": metrics.get("high_to_close_drawdown"),
                "close_to_vwap": metrics.get("close_to_vwap"),
                "tail_return": metrics.get("tail_return"),
                "lhb_replay_action": _clean_lhb_reason(record.get("lhb_replay_action")),
                "lhb_behavior_type": _clean_lhb_reason(record.get("lhb_behavior_type")),
                "event_structure": _clean_lhb_reason(record.get("event_structure")),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns)


def _normalize_lhb_intraday_minute_bars(minute_bars: pd.DataFrame) -> pd.DataFrame:
    columns = ["trade_date", "ts_code", "trade_time", "open", "high", "low", "close", "volume", "amount"]
    if minute_bars.empty:
        return pd.DataFrame(columns=columns)
    frame = minute_bars.copy()
    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["ts_code"] = frame["ts_code"].fillna("").astype(str).str.strip().str.upper()
    frame["trade_time"] = pd.to_datetime(frame["trade_time"], errors="coerce")
    for column in ["open", "high", "low", "close", "volume", "amount"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["trade_date", "ts_code", "trade_time"]).sort_values(
        ["ts_code", "trade_date", "trade_time"],
        kind="stable",
    ).reset_index(drop=True)


def _next_lhb_confirmation_bars(asset_bars: pd.DataFrame, trade_date: str) -> pd.DataFrame:
    if asset_bars.empty:
        return asset_bars
    signal_date = pd.to_datetime(trade_date, errors="coerce")
    frame = asset_bars.copy()
    frame["_trade_date_dt"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    frame = frame[frame["_trade_date_dt"].gt(signal_date)]
    if frame.empty:
        return frame.drop(columns=["_trade_date_dt"], errors="ignore")
    next_date = frame["_trade_date_dt"].min()
    return frame[frame["_trade_date_dt"].eq(next_date)].drop(columns=["_trade_date_dt"], errors="ignore")


def _lhb_intraday_confirmation_metrics(bars: pd.DataFrame) -> dict[str, Any]:
    if bars.empty:
        return {
            "confirmation_trade_date": "",
            "minute_bar_count": 0,
            "entry_time_proxy": "",
            "entry_price_proxy": None,
            "first_60m_return": None,
            "intraday_return": None,
            "high_to_close_drawdown": None,
            "close_to_vwap": None,
            "tail_return": None,
        }
    frame = bars.sort_values("trade_time", kind="stable").reset_index(drop=True)
    first = frame.iloc[0]
    last = frame.iloc[-1]
    entry_price = _coerce_numeric(first.get("open"), 0.0)
    close = _coerce_numeric(last.get("close"), 0.0)
    first_time = pd.to_datetime(first.get("trade_time"), errors="coerce")
    first_60m = frame[frame["trade_time"].le(first_time + pd.Timedelta(minutes=60))] if not pd.isna(first_time) else frame.head(1)
    first_60m_close = _coerce_numeric(first_60m.iloc[-1].get("close"), entry_price) if not first_60m.empty else entry_price
    high = pd.to_numeric(frame["high"], errors="coerce").max()
    amount_sum = pd.to_numeric(frame["amount"], errors="coerce").sum()
    volume_sum = pd.to_numeric(frame["volume"], errors="coerce").sum()
    vwap = amount_sum / volume_sum if volume_sum else None
    tail_count = min(6, len(frame))
    tail_start = _coerce_numeric(frame.iloc[-tail_count].get("close"), close) if tail_count else close
    return {
        "confirmation_trade_date": str(first.get("trade_date") or ""),
        "minute_bar_count": int(len(frame)),
        "entry_time_proxy": first_time.strftime("%H:%M:%S") if not pd.isna(first_time) else "",
        "entry_price_proxy": entry_price,
        "first_60m_return": _safe_return(first_60m_close, entry_price),
        "intraday_return": _safe_return(close, entry_price),
        "high_to_close_drawdown": _safe_return(close, high),
        "close_to_vwap": _safe_return(close, vwap),
        "tail_return": _safe_return(close, tail_start),
    }


def _safe_return(end_value: Any, start_value: Any) -> float | None:
    end = _coerce_numeric(end_value, 0.0)
    start = _coerce_numeric(start_value, 0.0)
    if start == 0.0:
        return None
    return end / start - 1.0


def _classify_lhb_intraday_confirmation(metrics: dict[str, Any]) -> tuple[str, str]:
    if int(metrics.get("minute_bar_count") or 0) == 0:
        return "no_minute_data", "missing_next_day_5min_bars"
    first_60m = _coerce_numeric(metrics.get("first_60m_return"), 0.0)
    intraday = _coerce_numeric(metrics.get("intraday_return"), 0.0)
    fade = _coerce_numeric(metrics.get("high_to_close_drawdown"), 0.0)
    close_to_vwap = _coerce_numeric(metrics.get("close_to_vwap"), 0.0)
    tail = _coerce_numeric(metrics.get("tail_return"), 0.0)
    reasons: list[str] = []
    if first_60m < -0.02:
        reasons.append("weak_first_60m")
    if fade < -0.045:
        reasons.append("morning_fade")
    if close_to_vwap < -0.015:
        reasons.append("below_vwap")
    if tail < -0.02:
        reasons.append("tail_selloff")
    if intraday < -0.03:
        reasons.append("negative_intraday")
    if first_60m > 0.0 and intraday >= 0.0 and ("morning_fade" in reasons or "below_vwap" in reasons):
        control_reasons = [
            "morning_fade_chase_control" if reason == "morning_fade" else reason
            for reason in reasons
            if reason in {"morning_fade", "below_vwap"}
        ]
        return "confirm_but_chase_control", ",".join(control_reasons)
    if first_60m < 0.0 and intraday > 0.0 and close_to_vwap > 0.0:
        return "watch_pullback_confirm", "weak_first_60m_recovered"
    if reasons:
        return "reject_follow", ",".join(reasons)
    if first_60m >= 0.0 and close_to_vwap >= 0.0 and intraday >= 0.0:
        return "confirm_follow", "first_60m_and_vwap_confirmed"
    return "watch_only", "mixed_intraday_confirmation"


def _build_lhb_shortline_intraday_confirmation_summary(detail: pd.DataFrame) -> pd.DataFrame:
    columns = LHB_SHORTLINE_INTRADAY_CONFIRMATION_SUMMARY_COLUMNS
    if detail.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for action, group in detail.groupby("intraday_confirmation_action", dropna=False):
        rows.append(
            {
                "intraday_confirmation_action": action,
                "candidate_count": int(len(group)),
                "avg_first_60m_return": pd.to_numeric(group["first_60m_return"], errors="coerce").mean(),
                "avg_intraday_return": pd.to_numeric(group["intraday_return"], errors="coerce").mean(),
                "avg_high_to_close_drawdown": pd.to_numeric(group["high_to_close_drawdown"], errors="coerce").mean(),
                "avg_close_to_vwap": pd.to_numeric(group["close_to_vwap"], errors="coerce").mean(),
                "avg_tail_return": pd.to_numeric(group["tail_return"], errors="coerce").mean(),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(
        ["candidate_count", "intraday_confirmation_action"],
        ascending=[False, True],
        kind="stable",
    ).reset_index(drop=True)


def _lhb_shortline_intraday_confirmation_markdown(*, detail: pd.DataFrame, summary: pd.DataFrame) -> str:
    return "\n".join(
        [
            "# LHB Shortline Intraday Confirmation v1",
            "",
            "## 1. Scope",
            "LHB T-day signal is treated as a post-close candidate. The next available 5min trading day is used only for confirmation/rejection diagnostics.",
            "",
            "## 2. Summary",
            _table_preview(summary, rows=20),
            "",
            "## 3. Detail Preview",
            _table_preview(detail, rows=30),
            "",
        ]
    )


def _build_lhb_full_market_pool_candidates(
    *,
    lhb_features: pd.DataFrame,
    daily_bars: pd.DataFrame,
    start_date: str,
    end_date: str,
    pool_mode: str,
) -> pd.DataFrame:
    columns = LHB_FULL_MARKET_POOL_SELECTED_COLUMNS
    if lhb_features.empty:
        return pd.DataFrame(columns=columns)
    frame = lhb_features.copy()
    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    start = pd.to_datetime(start_date, errors="coerce")
    end = pd.to_datetime(end_date, errors="coerce")
    frame = frame[frame["trade_date"].notna()]
    if not pd.isna(start):
        frame = frame[frame["trade_date"].ge(start)]
    if not pd.isna(end):
        frame = frame[frame["trade_date"].le(end)]
    frame["ts_code"] = frame["ts_code"].fillna("").astype(str).str.strip().str.upper()
    frame = frame[frame["ts_code"].map(_is_lhb_full_market_stock_code)].copy()
    for column in [
        "lhb_net_buy_amount",
        "lhb_net_buy_ratio",
        "institution_net_buy",
        "top_seat_concentration",
        "repeat_on_list_count_3d",
        "repeat_on_list_count_5d",
        "lhb_one_day_pump_risk",
    ]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in ["lhb_after_limit_up", "lhb_after_break_limit", "lhb_after_reversal"]:
        frame[column] = frame[column].map(_coerce_lhb_bool)
    frame = _filter_lhb_full_market_pool(frame, pool_mode=pool_mode)
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame["selection_score"] = _score_lhb_full_market_pool(frame)
    frame = _attach_lhb_full_market_future_returns(frame, daily_bars)
    frame["pool_mode"] = pool_mode
    frame["trade_date"] = frame["trade_date"].dt.strftime("%Y-%m-%d")
    return frame.reindex(columns=columns).sort_values(
        ["trade_date", "selection_score", "ts_code"],
        ascending=[True, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _filter_lhb_full_market_pool(frame: pd.DataFrame, *, pool_mode: str) -> pd.DataFrame:
    mode = str(pool_mode or "raw_lhb_positive").strip()
    net_buy = pd.to_numeric(frame["lhb_net_buy_amount"], errors="coerce").fillna(0.0)
    net_ratio = pd.to_numeric(frame["lhb_net_buy_ratio"], errors="coerce").fillna(0.0)
    inst_buy = pd.to_numeric(frame["institution_net_buy"], errors="coerce").fillna(0.0)
    pump = pd.to_numeric(frame["lhb_one_day_pump_risk"], errors="coerce").fillna(0.0)
    after_limit = frame["lhb_after_limit_up"].map(_coerce_lhb_bool)
    after_break = frame["lhb_after_break_limit"].map(_coerce_lhb_bool)
    after_reversal = frame["lhb_after_reversal"].map(_coerce_lhb_bool)
    if mode == "raw_lhb_positive":
        mask = net_buy.gt(0) & net_ratio.gt(0) & inst_buy.ge(0) & pump.lt(0.90)
    elif mode == "positive_no_pump":
        mask = net_buy.gt(0) & net_ratio.gt(0) & inst_buy.ge(0) & pump.lt(0.70)
    elif mode == "limit_support":
        mask = net_buy.gt(0) & net_ratio.gt(0) & inst_buy.ge(0) & after_limit & ~after_break & ~after_reversal
    else:
        raise ValueError("pool_mode must be one of: raw_lhb_positive, positive_no_pump, limit_support")
    return frame[mask].copy()


def _score_lhb_full_market_pool(frame: pd.DataFrame) -> pd.Series:
    net_ratio = pd.to_numeric(frame["lhb_net_buy_ratio"], errors="coerce").fillna(0.0)
    net_amount = pd.to_numeric(frame["lhb_net_buy_amount"], errors="coerce").fillna(0.0)
    inst_buy = pd.to_numeric(frame["institution_net_buy"], errors="coerce").fillna(0.0)
    repeat = pd.to_numeric(frame["repeat_on_list_count_3d"], errors="coerce").fillna(0.0)
    concentration = pd.to_numeric(frame["top_seat_concentration"], errors="coerce").fillna(0.0)
    pump = pd.to_numeric(frame["lhb_one_day_pump_risk"], errors="coerce").fillna(0.0)
    after_limit = frame["lhb_after_limit_up"].map(_coerce_lhb_bool).astype(float)
    after_break = frame["lhb_after_break_limit"].map(_coerce_lhb_bool).astype(float)
    amount_score = (net_amount.clip(lower=0.0).rank(pct=True, method="average") * 100.0).fillna(0.0)
    return (
        net_ratio * 1000.0
        + amount_score
        + (inst_buy.gt(0).astype(float) * 15.0)
        + after_limit * 12.0
        + repeat.clip(upper=3.0) * 3.0
        - concentration * 20.0
        - pump * 20.0
        - after_break * 18.0
    )


def _attach_lhb_full_market_future_returns(candidates: pd.DataFrame, daily_bars: pd.DataFrame) -> pd.DataFrame:
    result = candidates.copy()
    for column in [
        "future_1d_return",
        "future_3d_return",
        "future_5d_return",
        "future_10d_return",
        "future_5d_max_drawdown",
        "future_10d_max_drawdown",
    ]:
        result[column] = pd.NA
    bars = _normalize_lhb_full_market_daily_bars(daily_bars)
    if bars.empty:
        return result
    grouped = {ts_code: group.reset_index(drop=True) for ts_code, group in bars.groupby("ts_code", sort=False)}
    rows: list[dict[str, Any]] = []
    for record in result.to_dict("records"):
        group = grouped.get(str(record.get("ts_code") or ""))
        if group is None or group.empty:
            rows.append(record)
            continue
        trade_date = pd.to_datetime(record.get("trade_date"), errors="coerce")
        exact = group[group["trade_date"].eq(trade_date)]
        if exact.empty:
            rows.append(record)
            continue
        idx = int(exact.index[0])
        base_close = _coerce_numeric(group.loc[idx, "close"], 0.0)
        for horizon in [1, 3, 5, 10]:
            target_idx = idx + horizon
            if base_close and target_idx < len(group):
                record[f"future_{horizon}d_return"] = _safe_return(group.loc[target_idx, "close"], base_close)
                low = pd.to_numeric(group.loc[idx + 1 : target_idx, "low"], errors="coerce").min()
                record[f"future_{horizon}d_max_drawdown"] = _safe_return(low, base_close)
        rows.append(record)
    return pd.DataFrame(rows)


def _normalize_lhb_full_market_daily_bars(daily_bars: pd.DataFrame) -> pd.DataFrame:
    columns = ["trade_date", "ts_code", "close", "low"]
    if daily_bars.empty:
        return pd.DataFrame(columns=columns)
    frame = daily_bars.copy()
    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    frame["ts_code"] = frame["ts_code"].fillna("").astype(str).str.strip().str.upper()
    for column in ["close", "low"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["trade_date", "ts_code", "close"]).sort_values(
        ["ts_code", "trade_date"],
        kind="stable",
    ).reset_index(drop=True)


def _build_lhb_full_market_pool_selected(candidates: pd.DataFrame, *, top_n_values: list[int]) -> pd.DataFrame:
    columns = LHB_FULL_MARKET_POOL_SELECTED_COLUMNS
    clean_top_n = _normalize_lhb_shadow_top_n_values(top_n_values)
    if candidates.empty or not clean_top_n:
        return pd.DataFrame(columns=columns)
    rows: list[pd.DataFrame] = []
    for top_n in clean_top_n:
        selected_days: list[pd.DataFrame] = []
        for _, group in candidates.groupby("trade_date", dropna=False):
            ranked = group.sort_values(["selection_score", "ts_code"], ascending=[False, True], kind="stable").head(top_n).copy()
            ranked["selection_rank"] = range(1, len(ranked) + 1)
            ranked["top_n"] = top_n
            selected_days.append(ranked)
        if selected_days:
            rows.append(pd.concat(selected_days, ignore_index=True))
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.concat(rows, ignore_index=True).reindex(columns=columns).reset_index(drop=True)


def _lhb_full_market_pool_backtest_markdown(
    *,
    summary: pd.DataFrame,
    selected: pd.DataFrame,
    daily_curve: pd.DataFrame,
    start_date: str,
    end_date: str,
    top_n_values: list[int],
    pool_mode: str,
) -> str:
    return "\n".join(
        [
            "# LHB Full Market Pool Backtest v1",
            "",
            f"- Date range: {start_date} to {end_date}",
            f"- Pool mode: {pool_mode}",
            f"- Top-N values: {', '.join(str(value) for value in _normalize_lhb_shadow_top_n_values(top_n_values))}",
            "- Signal source: full-market LHB daily features, not curated dragon case replay.",
            "- Future returns use daily bars and remain a shadow diagnostic, not a fill/slippage simulation.",
            "",
            "## Top-N Summary",
            _table_preview(summary, rows=20),
            "",
            "## Daily Curve",
            _table_preview(daily_curve, rows=30),
            "",
            "## Selected Preview",
            _table_preview(selected, rows=30),
            "",
        ]
    )


def _join_lhb_intraday_actions(selected_trades: pd.DataFrame, intraday_detail: pd.DataFrame) -> pd.DataFrame:
    if selected_trades.empty:
        return pd.DataFrame()
    selected = selected_trades.copy()
    selected["trade_date"] = pd.to_datetime(selected["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    selected["ts_code"] = selected["ts_code"].fillna("").astype(str).str.strip().str.upper()
    if "pool_mode" not in selected.columns:
        selected["pool_mode"] = ""
    if "top_n" not in selected.columns:
        selected["top_n"] = pd.NA
    detail = intraday_detail.copy()
    if detail.empty:
        selected["intraday_confirmation_action"] = "no_intraday_detail"
        return selected
    for column in ["trade_date", "ts_code", "intraday_confirmation_action"]:
        if column not in detail.columns:
            detail[column] = ""
    detail["trade_date"] = pd.to_datetime(detail["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    detail["ts_code"] = detail["ts_code"].fillna("").astype(str).str.strip().str.upper()
    detail["intraday_confirmation_action"] = detail["intraday_confirmation_action"].fillna("").astype(str).str.strip()
    detail = detail.loc[:, ["trade_date", "ts_code", "intraday_confirmation_action"]].drop_duplicates(
        subset=["trade_date", "ts_code"],
        keep="first",
    )
    joined = selected.merge(detail, on=["trade_date", "ts_code"], how="left")
    joined["intraday_confirmation_action"] = joined["intraday_confirmation_action"].fillna("no_intraday_detail").astype(str)
    return joined


def _build_lhb_intraday_filtered_topn_comparison(joined: pd.DataFrame) -> pd.DataFrame:
    columns = LHB_INTRADAY_FILTERED_TOPN_COMPARISON_COLUMNS
    if joined.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for (pool_mode, top_n), group in joined.groupby(["pool_mode", "top_n"], dropna=False):
        candidate_sets = {
            "raw_topn": group,
            "intraday_confirm_follow": group[group["intraday_confirmation_action"].eq("confirm_follow")],
            "intraday_follow_or_watch": group[
                group["intraday_confirmation_action"].isin(
                    ["confirm_follow", "watch_only", "watch_pullback_confirm", "confirm_but_chase_control"]
                )
            ],
            "intraday_watch_only": group[group["intraday_confirmation_action"].isin(["watch_only", "watch_pullback_confirm"])],
            "intraday_chase_control": group[group["intraday_confirmation_action"].eq("confirm_but_chase_control")],
            "intraday_reject_follow": group[group["intraday_confirmation_action"].eq("reject_follow")],
        }
        for candidate_set, subset in candidate_sets.items():
            row = {"pool_mode": pool_mode, "top_n": top_n, "candidate_set": candidate_set}
            row.update(_lhb_intraday_filtered_metrics(subset))
            rows.append(row)
    return pd.DataFrame(rows).reindex(columns=columns)


def _build_lhb_intraday_action_effectiveness(joined: pd.DataFrame) -> pd.DataFrame:
    columns = LHB_INTRADAY_ACTION_EFFECTIVENESS_COLUMNS
    if joined.empty:
        return pd.DataFrame(columns=columns)
    joined = joined.drop_duplicates(subset=["trade_date", "ts_code"], keep="first")
    rows: list[dict[str, Any]] = []
    for action, group in joined.groupby("intraday_confirmation_action", dropna=False):
        row = {"intraday_confirmation_action": action}
        row.update(_lhb_intraday_filtered_metrics(group, count_column="candidate_count"))
        rows.append(row)
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(
        ["candidate_count", "intraday_confirmation_action"],
        ascending=[False, True],
        kind="stable",
    ).reset_index(drop=True)


def _lhb_intraday_filtered_metrics(group: pd.DataFrame, *, count_column: str = "selected_trade_count") -> dict[str, Any]:
    future_1d = pd.to_numeric(group.get("future_1d_return", pd.Series(dtype="float64")), errors="coerce")
    future_3d = pd.to_numeric(group.get("future_3d_return", pd.Series(dtype="float64")), errors="coerce")
    future_5d = pd.to_numeric(group.get("future_5d_return", pd.Series(dtype="float64")), errors="coerce")
    future_10d = pd.to_numeric(group.get("future_10d_return", pd.Series(dtype="float64")), errors="coerce")
    valid_5d = future_5d.dropna()
    result = {
        count_column: int(len(group)),
        "avg_future_1d_return": future_1d.mean(),
        "avg_future_3d_return": future_3d.mean(),
        "avg_future_5d_return": future_5d.mean(),
        "avg_future_10d_return": future_10d.mean(),
        "win_rate_5d": (valid_5d > 0).mean() if not valid_5d.empty else None,
        "avg_future_5d_max_drawdown": pd.to_numeric(
            group.get("future_5d_max_drawdown", pd.Series(dtype="float64")),
            errors="coerce",
        ).mean(),
    }
    if count_column == "selected_trade_count":
        result["signal_day_count"] = int(group["trade_date"].nunique()) if not group.empty and "trade_date" in group.columns else 0
    return result


def _lhb_intraday_filtered_topn_comparison_markdown(
    *,
    comparison: pd.DataFrame,
    action_effectiveness: pd.DataFrame,
) -> str:
    return "\n".join(
        [
            "# LHB Intraday Filtered TopN Comparison v1",
            "",
            "## 1. TopN Candidate Set Comparison",
            _table_preview(comparison, rows=40),
            "",
            "## 2. Intraday Action Effectiveness",
            _table_preview(action_effectiveness, rows=20),
            "",
        ]
    )


def _build_lhb_phase12a_decision_frame(
    *,
    selected_trades: pd.DataFrame,
    minute_bars: pd.DataFrame,
    intraday_detail: pd.DataFrame,
    pre_context_days: int,
) -> pd.DataFrame:
    columns = LHB_PHASE12A_DECISION_COLUMNS
    if selected_trades.empty:
        return pd.DataFrame(columns=columns)
    selected = selected_trades.copy()
    for column in columns:
        if column not in selected.columns:
            selected[column] = pd.NA
    selected["trade_date"] = pd.to_datetime(selected["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    selected["ts_code"] = selected["ts_code"].fillna("").astype(str).str.strip().str.upper()

    bars = _normalize_lhb_intraday_minute_bars(minute_bars)
    bars_by_code = {
        str(ts_code): group.reset_index(drop=True)
        for ts_code, group in bars.groupby("ts_code", sort=False)
    } if not bars.empty else {}
    detail_by_key = _lhb_intraday_detail_by_key(intraday_detail)

    rows: list[dict[str, Any]] = []
    for record in selected.to_dict("records"):
        trade_date = str(record.get("trade_date") or "")
        ts_code = str(record.get("ts_code") or "")
        asset_bars = bars_by_code.get(ts_code, pd.DataFrame())
        pre_metrics = _lhb_phase12a_pre_event_metrics(
            asset_bars=asset_bars,
            trade_date=trade_date,
            pre_context_days=pre_context_days,
        )
        event_metrics = _lhb_phase12a_event_day_metrics(asset_bars=asset_bars, trade_date=trade_date)
        pre_type = _classify_lhb_phase12a_pre_event_context(pre_metrics)
        event_type = _classify_lhb_phase12a_event_day_context(event_metrics)
        detail = detail_by_key.get((trade_date, ts_code), {})
        confirmation_action = _clean_lhb_reason(detail.get("intraday_confirmation_action")) or "no_intraday_detail"
        confirmation_reason = _clean_lhb_reason(detail.get("intraday_confirmation_reason"))
        decision, priority, can_follow, should_retreat, note = _map_lhb_phase12a_decision(
            pre_event_context_type=pre_type,
            event_day_context_type=event_type,
            intraday_confirmation_action=confirmation_action,
        )
        row = {column: record.get(column, pd.NA) for column in columns}
        row.update(
            {
                "trade_date": trade_date,
                "ts_code": ts_code,
                "stock_name": _clean_lhb_reason(record.get("stock_name")),
                "pre_event_context_type": pre_type,
                "pre_event_day_count": pre_metrics["pre_event_day_count"],
                "pre_event_return": pre_metrics["pre_event_return"],
                "event_day_context_type": event_type,
                "event_day_return": event_metrics["intraday_return"],
                "event_day_high_to_close_drawdown": event_metrics["high_to_close_drawdown"],
                "event_day_close_to_vwap": event_metrics["close_to_vwap"],
                "event_day_tail_return": event_metrics["tail_return"],
                "intraday_confirmation_action": confirmation_action,
                "intraday_confirmation_reason": confirmation_reason,
                "lhb_phase12a_decision": decision,
                "decision_priority": priority,
                "can_follow": bool(can_follow),
                "should_retreat": bool(should_retreat),
                "position_note": note,
            }
        )
        rows.append(row)
    frame = pd.DataFrame(rows).reindex(columns=columns)
    frame["can_follow"] = frame["can_follow"].astype(object)
    frame["should_retreat"] = frame["should_retreat"].astype(object)
    return frame


def _lhb_intraday_detail_by_key(intraday_detail: pd.DataFrame) -> dict[tuple[str, str], dict[str, Any]]:
    if intraday_detail.empty:
        return {}
    detail = intraday_detail.copy()
    for column in ["trade_date", "ts_code", "intraday_confirmation_action", "intraday_confirmation_reason"]:
        if column not in detail.columns:
            detail[column] = ""
    detail["trade_date"] = pd.to_datetime(detail["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    detail["ts_code"] = detail["ts_code"].fillna("").astype(str).str.strip().str.upper()
    detail = detail.drop_duplicates(subset=["trade_date", "ts_code"], keep="first")
    return {
        (str(row["trade_date"]), str(row["ts_code"])): row
        for row in detail.to_dict("records")
    }


def _lhb_phase12a_pre_event_metrics(
    *,
    asset_bars: pd.DataFrame,
    trade_date: str,
    pre_context_days: int,
) -> dict[str, Any]:
    empty = {"pre_event_day_count": 0, "pre_event_return": None}
    if asset_bars.empty:
        return empty
    signal_date = pd.to_datetime(trade_date, errors="coerce")
    frame = asset_bars.copy()
    frame["_trade_date_dt"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    frame = frame[frame["_trade_date_dt"].lt(signal_date)]
    if frame.empty:
        return empty
    dates = sorted(frame["_trade_date_dt"].dropna().unique())[-max(int(pre_context_days), 0):]
    if not dates:
        return empty
    window = frame[frame["_trade_date_dt"].isin(dates)].sort_values("trade_time", kind="stable")
    if window.empty:
        return empty
    first_open = _coerce_numeric(window.iloc[0].get("open"), 0.0)
    last_close = _coerce_numeric(window.iloc[-1].get("close"), 0.0)
    return {
        "pre_event_day_count": int(window["trade_date"].nunique()),
        "pre_event_return": _safe_return(last_close, first_open),
    }


def _lhb_phase12a_event_day_metrics(*, asset_bars: pd.DataFrame, trade_date: str) -> dict[str, Any]:
    if asset_bars.empty:
        return _lhb_intraday_confirmation_metrics(pd.DataFrame())
    frame = asset_bars[asset_bars["trade_date"].eq(trade_date)]
    return _lhb_intraday_confirmation_metrics(frame)


def _classify_lhb_phase12a_pre_event_context(metrics: dict[str, Any]) -> str:
    if int(metrics.get("pre_event_day_count") or 0) == 0:
        return "no_pre_event_context"
    pre_return = _coerce_numeric(metrics.get("pre_event_return"), 0.0)
    if pre_return >= 0.03:
        return "preheated"
    if pre_return <= -0.03:
        return "pre_event_weak"
    return "quiet_pre_event"


def _classify_lhb_phase12a_event_day_context(metrics: dict[str, Any]) -> str:
    if int(metrics.get("minute_bar_count") or 0) == 0:
        return "no_event_day_context"
    intraday = _coerce_numeric(metrics.get("intraday_return"), 0.0)
    fade = _coerce_numeric(metrics.get("high_to_close_drawdown"), 0.0)
    close_to_vwap = _coerce_numeric(metrics.get("close_to_vwap"), 0.0)
    tail = _coerce_numeric(metrics.get("tail_return"), 0.0)
    if intraday <= -0.03 or fade <= -0.045 or close_to_vwap <= -0.015 or tail <= -0.02:
        return "event_day_failed"
    if intraday >= 0.03 and close_to_vwap >= 0.0 and fade > -0.035:
        return "event_day_strong"
    return "event_day_neutral"


def _map_lhb_phase12a_decision(
    *,
    pre_event_context_type: str,
    event_day_context_type: str,
    intraday_confirmation_action: str,
) -> tuple[str, int, bool, bool, str]:
    _ = pre_event_context_type
    action = str(intraday_confirmation_action or "")
    if action == "reject_follow":
        return "retreat_signal", 90, False, True, "retreat_next_day_reject"
    if event_day_context_type == "event_day_failed" and action != "confirm_follow":
        return "retreat_signal", 85, False, True, "retreat_event_day_failed"
    if action == "confirm_follow":
        if event_day_context_type == "event_day_failed":
            return "watch_pool", 45, False, False, "watch_confirm_after_failed_event_day"
        return "follow_pool", 10, True, False, "can_follow_intraday_confirmed"
    if action == "confirm_but_chase_control":
        return "chase_control_pool", 30, False, False, "no_chase_wait_pullback"
    if action in {"watch_only", "watch_pullback_confirm"}:
        return "watch_pool", 50, False, False, "watch_wait_second_confirmation"
    return "pending_intraday", 70, False, False, "pending_next_day_intraday_detail"


def _build_lhb_phase12a_decision_summary(decision: pd.DataFrame) -> pd.DataFrame:
    columns = LHB_PHASE12A_SUMMARY_COLUMNS
    if decision.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for decision_name, group in decision.groupby("lhb_phase12a_decision", dropna=False):
        metrics = _lhb_intraday_filtered_metrics(group)
        rows.append(
            {
                "lhb_phase12a_decision": decision_name,
                "candidate_count": metrics["selected_trade_count"],
                "signal_day_count": metrics["signal_day_count"],
                "avg_future_1d_return": metrics["avg_future_1d_return"],
                "avg_future_3d_return": metrics["avg_future_3d_return"],
                "avg_future_5d_return": metrics["avg_future_5d_return"],
                "avg_future_10d_return": metrics["avg_future_10d_return"],
                "win_rate_5d": metrics["win_rate_5d"],
                "avg_future_5d_max_drawdown": metrics["avg_future_5d_max_drawdown"],
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(
        ["candidate_count", "lhb_phase12a_decision"],
        ascending=[False, True],
        kind="stable",
    ).reset_index(drop=True)


def _lhb_phase12a_multi_context_decision_markdown(*, decision: pd.DataFrame, summary: pd.DataFrame) -> str:
    return "\n".join(
        [
            "# LHB Phase 12A Multi-Context Decision v1",
            "",
            "## 1. Decision Summary",
            _table_preview(summary, rows=20),
            "",
            "## 2. Decision Preview",
            _table_preview(decision, rows=40),
            "",
        ]
    )


def _build_lhb_phase12a_rule_decision_frame(phase12a_decision: pd.DataFrame) -> pd.DataFrame:
    columns = list(phase12a_decision.columns) + [
        column for column in LHB_PHASE12A_RULE_DECISION_EXTRA_COLUMNS if column not in phase12a_decision.columns
    ]
    if phase12a_decision.empty:
        return pd.DataFrame(columns=columns)
    frame = phase12a_decision.copy()
    for column in [
        "lhb_phase12a_decision",
        "pre_event_context_type",
        "event_day_context_type",
        "intraday_confirmation_action",
    ]:
        if column not in frame.columns:
            frame[column] = ""
        frame[column] = frame[column].fillna("").astype(str).str.strip()
    layers = frame.apply(_map_lhb_phase12a_rule_layer, axis=1, result_type="expand")
    layers.columns = LHB_PHASE12A_RULE_DECISION_EXTRA_COLUMNS
    return pd.concat([frame, layers], axis=1).reindex(columns=columns)


def _map_lhb_phase12a_rule_layer(row: pd.Series) -> tuple[str, str, int, str]:
    decision = str(row.get("lhb_phase12a_decision") or "")
    pre_context = str(row.get("pre_event_context_type") or "")
    event_context = str(row.get("event_day_context_type") or "")
    action = str(row.get("intraday_confirmation_action") or "")
    if decision == "follow_pool" and pre_context == "preheated" and event_context == "event_day_strong" and action == "confirm_follow":
        return (
            "follow_pool_high_confidence",
            "follow_allowed",
            10,
            "preheated_event_strong_next_day_confirm",
        )
    if decision == "follow_pool" and event_context == "event_day_neutral" and action == "confirm_follow":
        return (
            "follow_pool_low_drawdown",
            "follow_allowed",
            20,
            "event_neutral_next_day_confirm_low_drawdown_slice",
        )
    if decision == "follow_pool":
        return ("follow_pool_core", "follow_allowed", 30, "next_day_confirm_follow")
    if decision == "retreat_signal" or action == "reject_follow":
        return ("retreat_hard", "retreat", 90, "reject_or_retreat_signal")
    if decision == "chase_control_pool" or action == "confirm_but_chase_control":
        return ("chase_control", "no_chase_watch_pullback", 60, "confirm_but_chase_control")
    if decision == "watch_pool" or action in {"watch_only", "watch_pullback_confirm"}:
        return ("watch_pool", "watch_only", 50, "wait_for_second_confirmation")
    return ("pending_intraday", "pending", 70, "missing_or_pending_intraday_confirmation")


def _build_lhb_phase12a_rule_summary(rule_decision: pd.DataFrame) -> pd.DataFrame:
    columns = LHB_PHASE12A_RULE_SUMMARY_COLUMNS
    if rule_decision.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for layer, group in rule_decision.groupby("phase12a_rule_layer", dropna=False):
        metrics = _lhb_intraday_filtered_metrics(group)
        rows.append(
            {
                "phase12a_rule_layer": layer,
                "candidate_count": metrics["selected_trade_count"],
                "signal_day_count": metrics["signal_day_count"],
                "avg_future_1d_return": metrics["avg_future_1d_return"],
                "avg_future_3d_return": metrics["avg_future_3d_return"],
                "avg_future_5d_return": metrics["avg_future_5d_return"],
                "avg_future_10d_return": metrics["avg_future_10d_return"],
                "win_rate_5d": metrics["win_rate_5d"],
                "avg_future_5d_max_drawdown": metrics["avg_future_5d_max_drawdown"],
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(
        ["candidate_count", "phase12a_rule_layer"],
        ascending=[False, True],
        kind="stable",
    ).reset_index(drop=True)


def _lhb_phase12a_rule_markdown(*, rule_decision: pd.DataFrame, summary: pd.DataFrame) -> str:
    return "\n".join(
        [
            "# LHB Phase 12A Rule v1",
            "",
            "## 1. Rule Layer Summary",
            _table_preview(summary, rows=20),
            "",
            "## 2. Rule Decision Preview",
            _table_preview(rule_decision, rows=40),
            "",
        ]
    )


def _build_lhb_phase12a_real_entry_trades(
    *,
    rule_decision: pd.DataFrame,
    minute_bars: pd.DataFrame,
    daily_bars: pd.DataFrame,
    entry_start_time: str,
    slippage_bps: float,
) -> pd.DataFrame:
    columns = LHB_PHASE12A_REAL_ENTRY_TRADE_COLUMNS
    if rule_decision.empty:
        return pd.DataFrame(columns=columns)
    decisions = rule_decision.copy()
    for column in ["trade_date", "ts_code", "phase12a_rule_layer", "phase12a_rule_action"]:
        if column not in decisions.columns:
            decisions[column] = ""
    decisions["trade_date"] = pd.to_datetime(decisions["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    decisions["ts_code"] = decisions["ts_code"].fillna("").astype(str).str.strip().str.upper()
    if "top_n" in decisions.columns:
        decisions["_top_n_sort"] = pd.to_numeric(decisions["top_n"], errors="coerce")
        decisions = decisions.sort_values(["trade_date", "ts_code", "_top_n_sort"], kind="stable")
    decisions = decisions.drop_duplicates(["trade_date", "ts_code"], keep="first")

    bars = _normalize_lhb_intraday_minute_bars(minute_bars)
    bars_by_code = {
        str(ts_code): group.reset_index(drop=True)
        for ts_code, group in bars.groupby("ts_code", sort=False)
    } if not bars.empty else {}
    daily = _normalize_lhb_phase12a_daily_bars(daily_bars)
    daily_by_code = {
        str(ts_code): group.reset_index(drop=True)
        for ts_code, group in daily.groupby("ts_code", sort=False)
    } if not daily.empty else {}

    rows: list[dict[str, Any]] = []
    for record in decisions.to_dict("records"):
        trade_date = str(record.get("trade_date") or "")
        ts_code = str(record.get("ts_code") or "")
        base = {
            "trade_date": trade_date,
            "ts_code": ts_code,
            "top_n": record.get("top_n", ""),
            "phase12a_rule_layer": record.get("phase12a_rule_layer", ""),
            "phase12a_rule_action": record.get("phase12a_rule_action", ""),
            "entry_start_time": entry_start_time,
            "slippage_bps": slippage_bps,
        }
        if str(record.get("phase12a_rule_action") or "") != "follow_allowed":
            rows.append({**base, "fill_status": "not_follow_allowed"})
            continue
        entry = _find_lhb_phase12a_real_entry(
            asset_bars=bars_by_code.get(ts_code, pd.DataFrame()),
            trade_date=trade_date,
            entry_start_time=entry_start_time,
            slippage_bps=slippage_bps,
        )
        row = {**base, **entry}
        if entry["fill_status"] == "filled":
            row.update(
                _lhb_phase12a_real_entry_exits(
                    daily_bars=daily_by_code.get(ts_code, pd.DataFrame()),
                    entry_trade_date=str(entry.get("confirmation_trade_date") or ""),
                    entry_price=entry.get("entry_price"),
                )
            )
        rows.append(row)
    return pd.DataFrame(rows).reindex(columns=columns)


def _normalize_lhb_phase12a_daily_bars(daily_bars: pd.DataFrame) -> pd.DataFrame:
    columns = ["trade_date", "ts_code", "close"]
    if daily_bars.empty:
        return pd.DataFrame(columns=columns)
    frame = daily_bars.copy()
    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["ts_code"] = frame["ts_code"].fillna("").astype(str).str.strip().str.upper()
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    return frame.dropna(subset=["trade_date", "ts_code", "close"]).sort_values(
        ["ts_code", "trade_date"],
        kind="stable",
    ).reset_index(drop=True)


def _find_lhb_phase12a_real_entry(
    *,
    asset_bars: pd.DataFrame,
    trade_date: str,
    entry_start_time: str,
    slippage_bps: float,
) -> dict[str, Any]:
    if asset_bars.empty:
        return {"fill_status": "no_minute_data"}
    next_bars = _next_lhb_confirmation_bars(asset_bars, trade_date)
    if next_bars.empty:
        return {"fill_status": "no_next_day_bars"}
    frame = next_bars.sort_values("trade_time", kind="stable").reset_index(drop=True).copy()
    day_open = _coerce_numeric(frame.iloc[0].get("open"), 0.0)
    start_time = pd.to_datetime(f"{frame.iloc[0]['trade_date']} {entry_start_time}", errors="coerce")
    amount_cumsum = pd.to_numeric(frame["amount"], errors="coerce").fillna(0.0).cumsum()
    volume_cumsum = pd.to_numeric(frame["volume"], errors="coerce").fillna(0.0).cumsum()
    frame["_vwap_so_far"] = amount_cumsum / volume_cumsum.replace(0.0, pd.NA)
    for idx, bar in frame.iterrows():
        trade_time = pd.to_datetime(bar.get("trade_time"), errors="coerce")
        if pd.isna(trade_time) or trade_time < start_time:
            continue
        close = _coerce_numeric(bar.get("close"), 0.0)
        vwap = _coerce_numeric(bar.get("_vwap_so_far"), 0.0)
        if close <= day_open or close < vwap:
            continue
        next_idx = int(idx) + 1
        if next_idx >= len(frame):
            return {
                "fill_status": "entry_signal_without_next_bar",
                "confirmation_trade_date": str(bar.get("trade_date") or ""),
                "entry_signal_time": trade_time.strftime("%H:%M:%S"),
            }
        execution_idx, blocked_count = _find_lhb_next_tradable_entry_execution_idx(
            frame=frame,
            start_idx=next_idx,
            reference_price=close,
        )
        if execution_idx is None:
            return {
                "fill_status": "entry_signal_locked_limit_up",
                "confirmation_trade_date": str(bar.get("trade_date") or ""),
                "entry_signal_time": trade_time.strftime("%H:%M:%S"),
                "blocked_entry_bar_count": blocked_count,
                "blocked_entry_reason": "locked_limit_up",
            }
        execution = frame.iloc[execution_idx]
        execution_time = pd.to_datetime(execution.get("trade_time"), errors="coerce")
        raw_entry_price = _coerce_numeric(execution.get("open"), 0.0)
        return {
            "fill_status": "filled",
            "confirmation_trade_date": str(execution.get("trade_date") or ""),
            "entry_signal_time": trade_time.strftime("%H:%M:%S"),
            "entry_time": execution_time.strftime("%H:%M:%S") if not pd.isna(execution_time) else "",
            "entry_price": raw_entry_price * (1.0 + float(slippage_bps) / 10000.0),
            "blocked_entry_bar_count": blocked_count,
            "blocked_entry_reason": "locked_limit_up" if blocked_count else "",
        }
    return {"fill_status": "no_entry_signal"}


def _find_lhb_next_tradable_entry_execution_idx(
    *,
    frame: pd.DataFrame,
    start_idx: int,
    reference_price: float,
) -> tuple[int | None, int]:
    _ = reference_price
    idx = int(start_idx)
    if idx < len(frame):
        return idx, 0
    return None, 0


def _lhb_phase12a_real_entry_exits(
    *,
    daily_bars: pd.DataFrame,
    entry_trade_date: str,
    entry_price: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    entry = _coerce_numeric(entry_price, 0.0)
    if daily_bars.empty or entry == 0.0:
        return result
    frame = daily_bars[daily_bars["trade_date"].ge(entry_trade_date)].sort_values("trade_date", kind="stable").reset_index(drop=True)
    for horizon in [0, 1, 2, 3, 5]:
        if horizon < len(frame):
            close = _coerce_numeric(frame.iloc[horizon].get("close"), 0.0)
            result[f"exit_{horizon}d_close"] = close
            result[f"exit_{horizon}d_return"] = _safe_return(close, entry)
    max_horizon = min(5, len(frame) - 1)
    if max_horizon >= 0:
        lows = pd.to_numeric(frame.iloc[: max_horizon + 1]["close"], errors="coerce")
        if not lows.empty:
            result["max_drawdown_to_5d"] = _safe_return(lows.min(), entry)
    return result


def _build_lhb_phase12a_real_entry_summary(trades: pd.DataFrame) -> pd.DataFrame:
    columns = LHB_PHASE12A_REAL_ENTRY_SUMMARY_COLUMNS
    if trades.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for layer, group in trades.groupby("phase12a_rule_layer", dropna=False):
        filled = group[group["fill_status"].eq("filled")]
        row: dict[str, Any] = {
            "phase12a_rule_layer": layer,
            "candidate_count": int(len(group)),
            "filled_count": int(len(filled)),
            "fill_rate": len(filled) / len(group) if len(group) else None,
            "avg_entry_price": pd.to_numeric(filled.get("entry_price", pd.Series(dtype="float64")), errors="coerce").mean(),
            "avg_max_drawdown_to_5d": pd.to_numeric(
                filled.get("max_drawdown_to_5d", pd.Series(dtype="float64")),
                errors="coerce",
            ).mean(),
        }
        for horizon in [0, 1, 2, 3, 5]:
            returns = pd.to_numeric(filled.get(f"exit_{horizon}d_return", pd.Series(dtype="float64")), errors="coerce")
            valid = returns.dropna()
            row[f"avg_exit_{horizon}d_return"] = returns.mean()
            row[f"win_rate_{horizon}d"] = (valid > 0).mean() if not valid.empty else None
        rows.append(row)
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(
        ["filled_count", "phase12a_rule_layer"],
        ascending=[False, True],
        kind="stable",
    ).reset_index(drop=True)


def _lhb_phase12a_real_entry_backtest_markdown(*, trades: pd.DataFrame, summary: pd.DataFrame) -> str:
    return "\n".join(
        [
            "# LHB Phase 12A Real Entry Backtest v1",
            "",
            "## 1. Summary",
            _table_preview(summary, rows=20),
            "",
            "## 2. Trade Preview",
            _table_preview(trades, rows=40),
            "",
        ]
    )


def _build_lhb_phase12b_signal_exit_trades(
    *,
    entry_trades: pd.DataFrame,
    minute_bars: pd.DataFrame,
    max_hold_days: int,
) -> pd.DataFrame:
    columns = LHB_PHASE12B_SIGNAL_EXIT_TRADE_COLUMNS
    if entry_trades.empty:
        return pd.DataFrame(columns=columns)
    entries = entry_trades.copy()
    for column in ["trade_date", "ts_code", "phase12a_rule_layer", "fill_status", "confirmation_trade_date"]:
        if column not in entries.columns:
            entries[column] = ""
    entries["trade_date"] = pd.to_datetime(entries["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    entries["confirmation_trade_date"] = pd.to_datetime(entries["confirmation_trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    entries["ts_code"] = entries["ts_code"].fillna("").astype(str).str.strip().str.upper()
    entries["entry_price"] = pd.to_numeric(entries.get("entry_price", pd.Series(dtype="float64")), errors="coerce")

    bars = _normalize_lhb_intraday_minute_bars(minute_bars)
    bars_by_code = {
        str(ts_code): group.reset_index(drop=True)
        for ts_code, group in bars.groupby("ts_code", sort=False)
    } if not bars.empty else {}

    rows: list[dict[str, Any]] = []
    for record in entries.to_dict("records"):
        base = {
            "trade_date": record.get("trade_date", ""),
            "ts_code": record.get("ts_code", ""),
            "top_n": record.get("top_n", ""),
            "phase12a_rule_layer": record.get("phase12a_rule_layer", ""),
            "fill_status": record.get("fill_status", ""),
            "entry_trade_date": record.get("confirmation_trade_date", ""),
            "entry_time": record.get("entry_time", ""),
            "entry_price": record.get("entry_price"),
            "max_hold_days": max_hold_days,
        }
        if record.get("fill_status") != "filled":
            rows.append({**base, "exit_status": "not_filled"})
            continue
        exit_row = _find_lhb_phase12b_signal_exit(
            asset_bars=bars_by_code.get(str(record.get("ts_code", "")), pd.DataFrame()),
            entry_trade_date=str(record.get("confirmation_trade_date") or ""),
            entry_price=record.get("entry_price"),
            max_hold_days=max_hold_days,
        )
        rows.append({**base, **exit_row})
    return pd.DataFrame(rows).reindex(columns=columns)


def _find_lhb_phase12b_signal_exit(
    *,
    asset_bars: pd.DataFrame,
    entry_trade_date: str,
    entry_price: Any,
    max_hold_days: int,
) -> dict[str, Any]:
    entry = _coerce_numeric(entry_price, 0.0)
    if asset_bars.empty or entry == 0.0:
        return {"exit_status": "no_exit_data"}
    frame = asset_bars.copy()
    frame["_trade_date_dt"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    entry_date = pd.to_datetime(entry_trade_date, errors="coerce")
    frame = frame[frame["_trade_date_dt"].gt(entry_date)]
    if frame.empty:
        return {"exit_status": "no_post_entry_bars"}
    dates = sorted(frame["_trade_date_dt"].dropna().unique())[: max(int(max_hold_days), 1)]
    window = frame[frame["_trade_date_dt"].isin(dates)].sort_values(["trade_date", "trade_time"], kind="stable").reset_index(drop=True)
    if window.empty:
        return {"exit_status": "no_post_entry_bars"}
    for idx, bar in window.iterrows():
        close = _coerce_numeric(bar.get("close"), 0.0)
        if close >= entry:
            continue
        signal_time = pd.to_datetime(bar.get("trade_time"), errors="coerce")
        next_idx = int(idx) + 1
        if next_idx < len(window):
            execution = window.iloc[next_idx]
            execution_time = pd.to_datetime(execution.get("trade_time"), errors="coerce")
            exit_price = _coerce_numeric(execution.get("open"), 0.0)
            exit_trade_date = str(execution.get("trade_date") or "")
            exit_time = execution_time.strftime("%H:%M:%S") if not pd.isna(execution_time) else ""
        else:
            exit_price = close
            exit_trade_date = str(bar.get("trade_date") or "")
            exit_time = signal_time.strftime("%H:%M:%S") if not pd.isna(signal_time) else ""
        return {
            "exit_status": "signal_exit",
            "exit_signal": "break_entry_price",
            "exit_signal_trade_date": str(bar.get("trade_date") or ""),
            "exit_signal_time": signal_time.strftime("%H:%M:%S") if not pd.isna(signal_time) else "",
            "exit_trade_date": exit_trade_date,
            "exit_time": exit_time,
            "exit_price": exit_price,
            "realized_return": _safe_return(exit_price, entry),
            "holding_trade_days": _lhb_phase12b_holding_trade_days(
                dates=dates,
                exit_trade_date=exit_trade_date,
            ),
        }
    fallback = window.iloc[-1]
    fallback_time = pd.to_datetime(fallback.get("trade_time"), errors="coerce")
    fallback_price = _coerce_numeric(fallback.get("close"), 0.0)
    fallback_date = str(fallback.get("trade_date") or "")
    return {
        "exit_status": "max_hold_exit",
        "exit_signal": "max_hold_days",
        "exit_signal_trade_date": fallback_date,
        "exit_signal_time": fallback_time.strftime("%H:%M:%S") if not pd.isna(fallback_time) else "",
        "exit_trade_date": fallback_date,
        "exit_time": fallback_time.strftime("%H:%M:%S") if not pd.isna(fallback_time) else "",
        "exit_price": fallback_price,
        "realized_return": _safe_return(fallback_price, entry),
        "holding_trade_days": len(dates),
    }


def _lhb_phase12b_holding_trade_days(*, dates: list[Any], exit_trade_date: str) -> int | None:
    exit_date = pd.to_datetime(exit_trade_date, errors="coerce")
    if pd.isna(exit_date):
        return None
    for idx, date in enumerate(dates, start=1):
        if pd.to_datetime(date, errors="coerce") == exit_date:
            return idx
    return None


def _build_lhb_phase12b_signal_exit_summary(exit_trades: pd.DataFrame) -> pd.DataFrame:
    columns = LHB_PHASE12B_SIGNAL_EXIT_SUMMARY_COLUMNS
    if exit_trades.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for layer, group in exit_trades.groupby("phase12a_rule_layer", dropna=False):
        filled = group[group["fill_status"].eq("filled")]
        returns = pd.to_numeric(filled.get("realized_return", pd.Series(dtype="float64")), errors="coerce")
        valid = returns.dropna()
        rows.append(
            {
                "phase12a_rule_layer": layer,
                "entry_count": int(len(group)),
                "filled_count": int(len(filled)),
                "signal_exit_count": int(filled["exit_status"].eq("signal_exit").sum()) if not filled.empty else 0,
                "fallback_exit_count": int(filled["exit_status"].eq("max_hold_exit").sum()) if not filled.empty else 0,
                "avg_realized_return": returns.mean(),
                "win_rate": (valid > 0).mean() if not valid.empty else None,
                "avg_holding_trade_days": pd.to_numeric(
                    filled.get("holding_trade_days", pd.Series(dtype="float64")),
                    errors="coerce",
                ).mean(),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(
        ["filled_count", "phase12a_rule_layer"],
        ascending=[False, True],
        kind="stable",
    ).reset_index(drop=True)


def _lhb_phase12b_signal_exit_markdown(*, exit_trades: pd.DataFrame, summary: pd.DataFrame) -> str:
    return "\n".join(
        [
            "# LHB Phase 12B Signal Exit v1",
            "",
            "## 1. Summary",
            _table_preview(summary, rows=20),
            "",
            "## 2. Exit Trades Preview",
            _table_preview(exit_trades, rows=40),
            "",
        ]
    )


def _build_lhb_phase14_lifecycle_exit_trades(
    *,
    entry_trades: pd.DataFrame,
    minute_bars: pd.DataFrame,
    max_hold_days: int,
    thresholds: dict[str, Any] | None = None,
) -> pd.DataFrame:
    columns = LHB_PHASE14_LIFECYCLE_EXIT_TRADE_COLUMNS
    if entry_trades.empty:
        return pd.DataFrame(columns=columns)
    entries = entry_trades.copy()
    for column in ["trade_date", "ts_code", "phase12a_rule_layer", "fill_status", "confirmation_trade_date"]:
        if column not in entries.columns:
            entries[column] = ""
    entries["trade_date"] = pd.to_datetime(entries["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    entries["confirmation_trade_date"] = pd.to_datetime(entries["confirmation_trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    entries["ts_code"] = entries["ts_code"].fillna("").astype(str).str.strip().str.upper()
    entries["entry_price"] = pd.to_numeric(entries.get("entry_price", pd.Series(dtype="float64")), errors="coerce")

    bars = _normalize_lhb_intraday_minute_bars(minute_bars)
    bars_by_code = {
        str(ts_code): group.reset_index(drop=True)
        for ts_code, group in bars.groupby("ts_code", sort=False)
    } if not bars.empty else {}

    rows: list[dict[str, Any]] = []
    for record in entries.to_dict("records"):
        base = {
            "trade_date": record.get("trade_date", ""),
            "ts_code": record.get("ts_code", ""),
            "top_n": record.get("top_n", ""),
            "phase12a_rule_layer": record.get("phase12a_rule_layer", ""),
            "fill_status": record.get("fill_status", ""),
            "entry_trade_date": record.get("confirmation_trade_date", ""),
            "entry_time": record.get("entry_time", ""),
            "entry_price": record.get("entry_price"),
            "max_hold_days": max_hold_days,
        }
        if record.get("fill_status") != "filled":
            rows.append({**base, "exit_status": "not_filled"})
            continue
        exit_row = _find_lhb_phase14_lifecycle_exit(
            asset_bars=bars_by_code.get(str(record.get("ts_code", "")), pd.DataFrame()),
            entry_trade_date=str(record.get("confirmation_trade_date") or ""),
            entry_price=record.get("entry_price"),
            max_hold_days=max_hold_days,
            thresholds=thresholds,
        )
        rows.append({**base, **exit_row})
    return pd.DataFrame(rows).reindex(columns=columns)


def _find_lhb_phase14_lifecycle_exit(
    *,
    asset_bars: pd.DataFrame,
    entry_trade_date: str,
    entry_price: Any,
    max_hold_days: int,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry = _coerce_numeric(entry_price, 0.0)
    if asset_bars.empty or entry == 0.0:
        return {"exit_status": "no_exit_data"}
    frame = asset_bars.copy()
    frame["_trade_date_dt"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    entry_date = pd.to_datetime(entry_trade_date, errors="coerce")
    frame = frame[frame["_trade_date_dt"].gt(entry_date)]
    if frame.empty:
        return {"exit_status": "no_post_entry_bars"}
    dates = sorted(frame["_trade_date_dt"].dropna().unique())[: max(int(max_hold_days), 1)]
    window = frame[frame["_trade_date_dt"].isin(dates)].sort_values(["trade_date", "trade_time"], kind="stable").reset_index(drop=True)
    if window.empty:
        return {"exit_status": "no_post_entry_bars"}

    signal = _scan_lhb_phase14_exit_signal(window=window, entry_price=entry, thresholds=thresholds)
    if signal is not None:
        idx, exit_signal, exit_reason = signal
        bar = window.iloc[idx]
        signal_time = pd.to_datetime(bar.get("trade_time"), errors="coerce")
        execution_idx, blocked_count = _find_lhb_next_tradable_exit_execution_idx(
            window=window,
            signal_idx=idx,
            entry_price=entry,
        )
        if execution_idx is not None:
            execution = window.iloc[execution_idx]
            execution_time = pd.to_datetime(execution.get("trade_time"), errors="coerce")
            exit_price = _coerce_numeric(execution.get("open"), 0.0)
            exit_trade_date = str(execution.get("trade_date") or "")
            exit_time = execution_time.strftime("%H:%M:%S") if not pd.isna(execution_time) else ""
        else:
            fallback = window.iloc[-1]
            fallback_time = pd.to_datetime(fallback.get("trade_time"), errors="coerce")
            exit_price = _coerce_numeric(fallback.get("close"), 0.0)
            exit_trade_date = str(fallback.get("trade_date") or "")
            exit_time = fallback_time.strftime("%H:%M:%S") if not pd.isna(fallback_time) else ""
        return {
            "exit_status": "signal_exit",
            "exit_signal": exit_signal,
            "exit_reason": exit_reason,
            "exit_signal_trade_date": str(bar.get("trade_date") or ""),
            "exit_signal_time": signal_time.strftime("%H:%M:%S") if not pd.isna(signal_time) else "",
            "exit_trade_date": exit_trade_date,
            "exit_time": exit_time,
            "exit_price": exit_price,
            "realized_return": _safe_return(exit_price, entry),
            "holding_trade_days": _lhb_phase12b_holding_trade_days(dates=dates, exit_trade_date=exit_trade_date),
            "blocked_exit_bar_count": blocked_count,
            "blocked_exit_reason": "locked_limit_down" if blocked_count else "",
        }

    fallback = window.iloc[-1]
    fallback_time = pd.to_datetime(fallback.get("trade_time"), errors="coerce")
    fallback_price = _coerce_numeric(fallback.get("close"), 0.0)
    fallback_date = str(fallback.get("trade_date") or "")
    return {
        "exit_status": "max_hold_exit",
        "exit_signal": "max_hold_days",
        "exit_reason": "no_lifecycle_exit_signal_before_max_hold",
        "exit_signal_trade_date": fallback_date,
        "exit_signal_time": fallback_time.strftime("%H:%M:%S") if not pd.isna(fallback_time) else "",
        "exit_trade_date": fallback_date,
        "exit_time": fallback_time.strftime("%H:%M:%S") if not pd.isna(fallback_time) else "",
        "exit_price": fallback_price,
        "realized_return": _safe_return(fallback_price, entry),
        "holding_trade_days": len(dates),
        "blocked_exit_bar_count": 0,
        "blocked_exit_reason": "",
    }


def _find_lhb_next_tradable_exit_execution_idx(
    *,
    window: pd.DataFrame,
    signal_idx: int,
    entry_price: float,
) -> tuple[int | None, int]:
    blocked_count = 0
    start_idx = int(signal_idx)
    if start_idx < len(window) and _is_lhb_locked_limit_down_bar(window.iloc[start_idx], reference_price=entry_price):
        blocked_count += 1
        start_idx += 1
        while start_idx < len(window) and _is_lhb_locked_limit_down_bar(window.iloc[start_idx], reference_price=entry_price):
            blocked_count += 1
            start_idx += 1
        execution_idx = start_idx + 1
        return (execution_idx if execution_idx < len(window) else None), blocked_count

    execution_idx = int(signal_idx) + 1
    while execution_idx < len(window) and _is_lhb_locked_limit_down_bar(window.iloc[execution_idx], reference_price=entry_price):
        blocked_count += 1
        execution_idx += 1
    return (execution_idx if execution_idx < len(window) else None), blocked_count


def _scan_lhb_phase14_exit_signal(
    *,
    window: pd.DataFrame,
    entry_price: float,
    thresholds: dict[str, Any] | None = None,
) -> tuple[int, str, str] | None:
    config = _lhb_phase14_threshold_config(thresholds)
    for _, day in window.groupby("trade_date", sort=False):
        frame = day.sort_values("trade_time", kind="stable").reset_index()
        day_open = _coerce_numeric(frame.iloc[0].get("open"), 0.0)
        amount_cumsum = pd.to_numeric(frame["amount"], errors="coerce").fillna(0.0).cumsum()
        volume_cumsum = pd.to_numeric(frame["volume"], errors="coerce").fillna(0.0).cumsum()
        vwap_so_far = amount_cumsum / volume_cumsum.replace(0.0, pd.NA)
        high_so_far = pd.to_numeric(frame["high"], errors="coerce").cummax()
        for pos, bar in frame.iterrows():
            close = _coerce_numeric(bar.get("close"), 0.0)
            vwap = _coerce_numeric(vwap_so_far.iloc[pos], 0.0)
            high_mark = _coerce_numeric(high_so_far.iloc[pos], 0.0)
            close_vs_vwap = _coerce_numeric(_safe_return(close, vwap), 0.0)
            high_to_close = _coerce_numeric(_safe_return(close, high_mark), 0.0)
            high_vs_open = _coerce_numeric(_safe_return(high_mark, day_open), 0.0)
            if (
                high_vs_open >= config["limit_high_vs_open"]
                and high_to_close <= config["limit_high_to_close"]
                and close_vs_vwap <= config["limit_close_vs_vwap"]
            ):
                return int(bar["index"]), "limit_break_failed", "intraday_high_near_limit_but_failed_close_below_vwap"
            if close_vs_vwap <= config["vwap_break"] and high_to_close <= config["vwap_high_to_close"]:
                return int(bar["index"]), "vwap_break_with_distribution", "close_below_vwap_after_intraday_fade"
            if close <= entry_price * (1.0 + config["entry_break_buffer"]):
                return int(bar["index"]), "break_entry_price", "close_below_entry_price_after_t1"
    return None


def _lhb_phase14_threshold_config(thresholds: dict[str, Any] | None = None) -> dict[str, float]:
    config = {
        "limit_high_vs_open": 0.095,
        "limit_high_to_close": -0.025,
        "limit_close_vs_vwap": 0.0,
        "vwap_break": -0.015,
        "vwap_high_to_close": -0.025,
        "entry_break_buffer": 0.0,
    }
    if thresholds:
        for key, value in thresholds.items():
            if key in config:
                config[key] = float(value)
    return config


def _is_lhb_one_price_bar(row: pd.Series) -> bool:
    prices = [_coerce_numeric(row.get(column), 0.0) for column in ["open", "high", "low", "close"]]
    if any(price <= 0.0 for price in prices):
        return False
    return max(prices) - min(prices) <= 1e-8


def _is_lhb_locked_limit_up_bar(row: pd.Series, *, reference_price: float) -> bool:
    if not _is_lhb_one_price_bar(row):
        return False
    price = _coerce_numeric(row.get("open"), 0.0)
    return price >= _coerce_numeric(reference_price, 0.0)


def _is_lhb_locked_limit_down_bar(row: pd.Series, *, reference_price: float) -> bool:
    if not _is_lhb_one_price_bar(row):
        return False
    price = _coerce_numeric(row.get("open"), 0.0)
    return price <= _coerce_numeric(reference_price, 0.0)


def _lhb_phase14b_threshold_profiles() -> list[dict[str, Any]]:
    return [
        {
            "threshold_profile": "sensitive_vwap",
            "vwap_break": -0.005,
            "vwap_high_to_close": -0.015,
            "limit_high_vs_open": 0.085,
            "limit_high_to_close": -0.015,
            "limit_close_vs_vwap": 0.0,
            "entry_break_buffer": 0.0,
        },
        {
            "threshold_profile": "sensitive_entry_buffer",
            "vwap_break": -0.005,
            "vwap_high_to_close": -0.020,
            "limit_high_vs_open": 0.090,
            "limit_high_to_close": -0.020,
            "limit_close_vs_vwap": 0.0,
            "entry_break_buffer": 0.005,
        },
        {
            "threshold_profile": "balanced_fast",
            "vwap_break": -0.010,
            "vwap_high_to_close": -0.020,
            "limit_high_vs_open": 0.090,
            "limit_high_to_close": -0.020,
            "limit_close_vs_vwap": 0.0,
            "entry_break_buffer": 0.0,
        },
        {
            "threshold_profile": "base_v1",
            "vwap_break": -0.015,
            "vwap_high_to_close": -0.025,
            "limit_high_vs_open": 0.095,
            "limit_high_to_close": -0.025,
            "limit_close_vs_vwap": 0.0,
            "entry_break_buffer": 0.0,
        },
        {
            "threshold_profile": "loose_vwap",
            "vwap_break": -0.020,
            "vwap_high_to_close": -0.030,
            "limit_high_vs_open": 0.095,
            "limit_high_to_close": -0.030,
            "limit_close_vs_vwap": -0.005,
            "entry_break_buffer": -0.005,
        },
        {
            "threshold_profile": "structure_first",
            "vwap_break": -0.015,
            "vwap_high_to_close": -0.035,
            "limit_high_vs_open": 0.085,
            "limit_high_to_close": -0.020,
            "limit_close_vs_vwap": 0.0,
            "entry_break_buffer": -0.005,
        },
        {
            "threshold_profile": "entry_guard_only_loose",
            "vwap_break": -0.030,
            "vwap_high_to_close": -0.040,
            "limit_high_vs_open": 0.105,
            "limit_high_to_close": -0.035,
            "limit_close_vs_vwap": -0.010,
            "entry_break_buffer": 0.0,
        },
    ]


def _lhb_phase14b_profile_by_name(threshold_profile: str) -> dict[str, Any]:
    wanted = str(threshold_profile or "").strip()
    for profile in _lhb_phase14b_threshold_profiles():
        if str(profile["threshold_profile"]) == wanted:
            return dict(profile)
    known = ", ".join(str(profile["threshold_profile"]) for profile in _lhb_phase14b_threshold_profiles())
    raise ValueError(f"unknown LHB phase14 threshold_profile={threshold_profile!r}; known={known}")


def _build_lhb_phase14b_threshold_scan_trades(
    *,
    entry_trades: pd.DataFrame,
    minute_bars: pd.DataFrame,
    max_hold_days: int,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for profile in _lhb_phase14b_threshold_profiles():
        profile_name = str(profile["threshold_profile"])
        thresholds = {key: value for key, value in profile.items() if key != "threshold_profile"}
        trades = _build_lhb_phase14_lifecycle_exit_trades(
            entry_trades=entry_trades,
            minute_bars=minute_bars,
            max_hold_days=max_hold_days,
            thresholds=thresholds,
        )
        trades.insert(0, "threshold_profile", profile_name)
        for key, value in thresholds.items():
            trades[key] = value
        rows.append(trades)
    if not rows:
        return pd.DataFrame(columns=["threshold_profile", *LHB_PHASE14_LIFECYCLE_EXIT_TRADE_COLUMNS])
    return pd.concat(rows, ignore_index=True)


def _build_lhb_phase14b_threshold_summary(scanned: pd.DataFrame) -> pd.DataFrame:
    columns = LHB_PHASE14B_THRESHOLD_SUMMARY_COLUMNS
    if scanned.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for (profile, layer), group in scanned.groupby(["threshold_profile", "phase12a_rule_layer"], dropna=False):
        row = _lhb_phase14b_metric_row(group)
        row.update({"threshold_profile": profile, "phase12a_rule_layer": layer})
        rows.append(row)
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(
        ["threshold_profile", "filled_count", "phase12a_rule_layer"],
        ascending=[True, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_lhb_phase14b_profile_ranking(scanned: pd.DataFrame) -> pd.DataFrame:
    columns = LHB_PHASE14B_PROFILE_RANKING_COLUMNS
    if scanned.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    follow = scanned[scanned["phase12a_rule_layer"].fillna("").astype(str).str.startswith("follow_pool")].copy()
    base = follow if not follow.empty else scanned
    for profile, group in base.groupby("threshold_profile", dropna=False):
        row = _lhb_phase14b_metric_row(group)
        row["threshold_profile"] = profile
        avg_return = _coerce_numeric(row["avg_realized_return"], 0.0)
        win_rate = _coerce_numeric(row["win_rate"], 0.0)
        hold_days = _coerce_numeric(row["avg_holding_trade_days"], 0.0)
        signal_rate = _coerce_numeric(row["signal_exit_rate"], 0.0)
        row["rank_score"] = avg_return * 100.0 + win_rate * 10.0 + signal_rate - hold_days * 0.10
        rows.append(row)
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(
        ["rank_score", "avg_realized_return", "win_rate", "avg_holding_trade_days"],
        ascending=[False, False, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _lhb_phase14b_metric_row(group: pd.DataFrame) -> dict[str, Any]:
    filled = group[group["fill_status"].eq("filled")]
    returns = pd.to_numeric(filled.get("realized_return", pd.Series(dtype="float64")), errors="coerce")
    valid = returns.dropna()
    signal_exit_count = int(filled["exit_status"].eq("signal_exit").sum()) if not filled.empty else 0
    fallback_exit_count = int(filled["exit_status"].eq("max_hold_exit").sum()) if not filled.empty else 0
    return {
        "entry_count": int(len(group)),
        "filled_count": int(len(filled)),
        "signal_exit_count": signal_exit_count,
        "fallback_exit_count": fallback_exit_count,
        "avg_realized_return": returns.mean(),
        "win_rate": (valid > 0).mean() if not valid.empty else None,
        "avg_holding_trade_days": pd.to_numeric(
            filled.get("holding_trade_days", pd.Series(dtype="float64")),
            errors="coerce",
        ).mean(),
        "signal_exit_rate": signal_exit_count / len(filled) if len(filled) else None,
    }


def _lhb_phase14b_threshold_scan_markdown(
    *,
    profile_ranking: pd.DataFrame,
    threshold_summary: pd.DataFrame,
    best_lifecycle_trades: pd.DataFrame,
) -> str:
    return "\n".join(
        [
            "# LHB Phase 14B Threshold Scan v1",
            "",
            "Profiles are ranked on follow_pool trades by realized return, win rate, signal exit rate, and shorter holding days.",
            "",
            "## 1. Profile Ranking",
            _table_preview(profile_ranking, rows=20),
            "",
            "## 2. Threshold Summary",
            _table_preview(threshold_summary, rows=40),
            "",
            "## 3. Best Profile Trades Preview",
            _table_preview(best_lifecycle_trades, rows=40),
            "",
        ]
    )


def _build_lhb_phase14c_daily_curve(lifecycle_trades: pd.DataFrame) -> pd.DataFrame:
    columns = LHB_PHASE14C_DAILY_CURVE_COLUMNS
    if lifecycle_trades.empty:
        return pd.DataFrame(columns=columns)
    frame = lifecycle_trades.copy()
    for column in ["top_n", "fill_status", "exit_trade_date", "realized_return"]:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame = frame[frame["fill_status"].eq("filled")].copy()
    frame["exit_trade_date"] = pd.to_datetime(frame["exit_trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["realized_return"] = pd.to_numeric(frame["realized_return"], errors="coerce")
    frame["top_n"] = pd.to_numeric(frame["top_n"], errors="coerce")
    frame = frame.dropna(subset=["top_n", "exit_trade_date", "realized_return"])
    if frame.empty:
        return pd.DataFrame(columns=columns)
    daily = (
        frame.groupby(["top_n", "exit_trade_date"], dropna=False)
        .agg(
            closed_trade_count=("ts_code", "size"),
            daily_realized_return=("realized_return", "mean"),
        )
        .reset_index()
        .sort_values(["top_n", "exit_trade_date"], kind="stable")
    )
    parts: list[pd.DataFrame] = []
    for top_n, group in daily.groupby("top_n", sort=False):
        part = group.copy().reset_index(drop=True)
        part["equity"] = (1.0 + pd.to_numeric(part["daily_realized_return"], errors="coerce").fillna(0.0)).cumprod()
        running_max = part["equity"].cummax()
        part["drawdown"] = part["equity"] / running_max - 1.0
        part["top_n"] = int(top_n)
        parts.append(part)
    return pd.concat(parts, ignore_index=True).reindex(columns=columns)


def _build_lhb_phase14c_portfolio_summary(
    *,
    lifecycle_trades: pd.DataFrame,
    daily_curve: pd.DataFrame,
    threshold_profile: str,
) -> pd.DataFrame:
    columns = LHB_PHASE14C_PORTFOLIO_SUMMARY_COLUMNS
    if lifecycle_trades.empty:
        return pd.DataFrame(columns=columns)
    frame = lifecycle_trades.copy()
    frame["top_n"] = pd.to_numeric(frame.get("top_n", pd.Series(dtype="float64")), errors="coerce")
    rows: list[dict[str, Any]] = []
    for top_n, group in frame.dropna(subset=["top_n"]).groupby("top_n", dropna=False):
        filled = group[group["fill_status"].eq("filled")]
        closed = filled[filled["realized_return"].notna()] if "realized_return" in filled.columns else filled.head(0)
        returns = pd.to_numeric(closed.get("realized_return", pd.Series(dtype="float64")), errors="coerce")
        valid = returns.dropna()
        curve = daily_curve[daily_curve["top_n"].eq(int(top_n))]
        rows.append(
            {
                "top_n": int(top_n),
                "threshold_profile": threshold_profile,
                "entry_count": int(len(group)),
                "filled_count": int(len(filled)),
                "closed_trade_count": int(len(closed)),
                "signal_exit_count": int(filled["exit_status"].eq("signal_exit").sum()) if not filled.empty else 0,
                "fallback_exit_count": int(filled["exit_status"].eq("max_hold_exit").sum()) if not filled.empty else 0,
                "avg_realized_return": returns.mean(),
                "win_rate": (valid > 0).mean() if not valid.empty else None,
                "avg_holding_trade_days": pd.to_numeric(
                    filled.get("holding_trade_days", pd.Series(dtype="float64")),
                    errors="coerce",
                ).mean(),
                "final_equity": pd.to_numeric(curve.get("equity", pd.Series(dtype="float64")), errors="coerce").iloc[-1]
                if not curve.empty
                else None,
                "max_drawdown": pd.to_numeric(curve.get("drawdown", pd.Series(dtype="float64")), errors="coerce").min()
                if not curve.empty
                else None,
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values("top_n", kind="stable").reset_index(drop=True)


def _lhb_phase14c_lifecycle_portfolio_markdown(
    *,
    summary: pd.DataFrame,
    daily_curve: pd.DataFrame,
    lifecycle_trades: pd.DataFrame,
) -> str:
    return "\n".join(
        [
            "# LHB Phase 14C Lifecycle Portfolio v1",
            "",
            "Default exit profile is sensitive_entry_buffer. Curve compounds equal-weight realized returns by exit date.",
            "",
            "## 1. Portfolio Summary",
            _table_preview(summary, rows=20),
            "",
            "## 2. Daily Curve",
            _table_preview(daily_curve, rows=40),
            "",
            "## 3. Lifecycle Trades Preview",
            _table_preview(lifecycle_trades, rows=40),
            "",
        ]
    )


def _build_lhb_phase14e_risk_audit(
    *,
    entry_trades: pd.DataFrame,
    lifecycle_trades: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    entry = entry_trades.copy() if not entry_trades.empty else pd.DataFrame()
    if not entry.empty:
        for column in ["fill_status", "blocked_entry_bar_count"]:
            if column not in entry.columns:
                entry[column] = 0 if column.endswith("_count") else ""
        blocked_entry = entry[entry["fill_status"].fillna("").astype(str).eq("entry_signal_locked_limit_up")].copy()
        rows.append(_lhb_phase14e_audit_row("blocked_entry_locked_limit_up", blocked_entry, "blocked_entry_bar_count"))

    trades = lifecycle_trades.copy() if not lifecycle_trades.empty else pd.DataFrame()
    if not trades.empty:
        for column in ["blocked_exit_bar_count", "blocked_exit_reason"]:
            if column not in trades.columns:
                trades[column] = 0 if column.endswith("_count") else ""
        blocked_exit_count = pd.to_numeric(trades["blocked_exit_bar_count"], errors="coerce").fillna(0.0)
        blocked_exit = trades[blocked_exit_count.gt(0)].copy()
        rows.append(_lhb_phase14e_audit_row("blocked_exit_locked_limit_down", blocked_exit, "blocked_exit_bar_count"))
    return pd.DataFrame(rows).reindex(columns=LHB_PHASE14E_RISK_AUDIT_COLUMNS)


def _lhb_phase14e_audit_row(risk_type: str, frame: pd.DataFrame, blocked_column: str) -> dict[str, Any]:
    blocked = pd.to_numeric(frame.get(blocked_column, pd.Series(dtype="float64")), errors="coerce")
    returns = pd.to_numeric(frame.get("realized_return", pd.Series(dtype="float64")), errors="coerce")
    return {
        "risk_type": risk_type,
        "event_count": int(len(frame)),
        "affected_trade_count": int(frame["ts_code"].nunique()) if "ts_code" in frame.columns and not frame.empty else int(len(frame)),
        "avg_realized_return": returns.mean(),
        "avg_blocked_bar_count": blocked.mean(),
        "max_blocked_bar_count": blocked.max(),
    }


def _build_lhb_phase14e_filter_scan(lifecycle_trades: pd.DataFrame) -> pd.DataFrame:
    if lifecycle_trades.empty:
        return pd.DataFrame(columns=["filter_profile", *list(lifecycle_trades.columns)])
    frame = lifecycle_trades.copy()
    for column in ["blocked_exit_bar_count", "phase12a_rule_layer", "trade_date", "ts_code"]:
        if column not in frame.columns:
            frame[column] = 0 if column.endswith("_count") else ""
    blocked_exit = pd.to_numeric(frame["blocked_exit_bar_count"], errors="coerce").fillna(0.0)
    blocked_layers = set(frame.loc[blocked_exit.gt(0), "phase12a_rule_layer"].fillna("").astype(str))
    blocked_codes = set(frame.loc[blocked_exit.gt(0), "ts_code"].fillna("").astype(str))

    profiles: list[tuple[str, pd.Series]] = [
        ("baseline", pd.Series(True, index=frame.index)),
        ("exclude_blocked_exit_history", ~blocked_exit.gt(0)),
        ("exclude_blocked_exit_layers", ~frame["phase12a_rule_layer"].fillna("").astype(str).isin(blocked_layers)),
        ("exclude_blocked_exit_codes", ~frame["ts_code"].fillna("").astype(str).isin(blocked_codes)),
    ]
    rows: list[pd.DataFrame] = []
    for profile, mask in profiles:
        subset = frame[mask].copy()
        subset.insert(0, "filter_profile", profile)
        rows.append(subset)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["filter_profile", *list(frame.columns)])


def _build_lhb_phase14e_filter_ranking(scanned: pd.DataFrame) -> pd.DataFrame:
    columns = LHB_PHASE14E_FILTER_RANKING_COLUMNS
    if scanned.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for (profile, top_n), group in scanned.groupby(["filter_profile", "top_n"], dropna=False):
        curve = _build_lhb_phase14c_daily_curve(group)
        summary = _build_lhb_phase14c_portfolio_summary(
            lifecycle_trades=group,
            daily_curve=curve,
            threshold_profile=_clean_lhb_reason(group.get("threshold_profile", pd.Series([""])).dropna().iloc[0]) if "threshold_profile" in group.columns and group["threshold_profile"].notna().any() else "",
        )
        if summary.empty:
            continue
        row = summary.iloc[0].to_dict()
        blocked_exit_count = int(pd.to_numeric(group.get("blocked_exit_bar_count", pd.Series(dtype="float64")), errors="coerce").fillna(0.0).gt(0).sum())
        final_equity = _coerce_numeric(row.get("final_equity"), 0.0)
        max_drawdown = _coerce_numeric(row.get("max_drawdown"), 0.0)
        win_rate = _coerce_numeric(row.get("win_rate"), 0.0)
        avg_return = _coerce_numeric(row.get("avg_realized_return"), 0.0)
        rank_score = final_equity + win_rate * 5.0 + avg_return * 100.0 - abs(max_drawdown) * 10.0 - blocked_exit_count * 0.25
        rows.append(
            {
                "filter_profile": profile,
                "top_n": int(top_n),
                "entry_count": row.get("entry_count"),
                "filled_count": row.get("filled_count"),
                "closed_trade_count": row.get("closed_trade_count"),
                "avg_realized_return": row.get("avg_realized_return"),
                "win_rate": row.get("win_rate"),
                "final_equity": row.get("final_equity"),
                "max_drawdown": row.get("max_drawdown"),
                "blocked_exit_count": blocked_exit_count,
                "rank_score": rank_score,
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(
        ["rank_score", "final_equity", "max_drawdown"],
        ascending=[False, False, False],
        kind="stable",
    ).reset_index(drop=True)


def _lhb_phase14e_limit_lock_filter_markdown(
    *,
    risk_audit: pd.DataFrame,
    filter_ranking: pd.DataFrame,
    best_summary: pd.DataFrame,
    best_trades: pd.DataFrame,
) -> str:
    return "\n".join(
        [
            "# LHB Phase 14E Limit-Lock Filter v1",
            "",
            "This report audits locked limit-up entries and locked limit-down exits, then compares simple risk filters against the Phase14C lifecycle baseline.",
            "",
            "## 1. Risk Audit",
            _table_preview(risk_audit, rows=20),
            "",
            "## 2. Filter Ranking",
            _table_preview(filter_ranking, rows=20),
            "",
            "## 3. Best Summary",
            _table_preview(best_summary, rows=20),
            "",
            "## 4. Best Trades Preview",
            _table_preview(best_trades, rows=40),
            "",
        ]
    )


def _build_lhb_phase15_cash_account_frames(
    *,
    lifecycle_trades: pd.DataFrame,
    max_positions: int,
    position_pct: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if lifecycle_trades.empty:
        return (
            pd.DataFrame(columns=LHB_PHASE15_ACCOUNT_TRADE_COLUMNS),
            pd.DataFrame(columns=LHB_PHASE15_ACCOUNT_CURVE_COLUMNS),
        )
    trades = lifecycle_trades.copy()
    for column in ["fill_status", "entry_trade_date", "exit_trade_date", "ts_code", "realized_return", "top_n", "phase12a_rule_layer", "trade_date"]:
        if column not in trades.columns:
            trades[column] = pd.NA
    trades["entry_trade_date"] = pd.to_datetime(trades["entry_trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    trades["exit_trade_date"] = pd.to_datetime(trades["exit_trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    trades["trade_date"] = pd.to_datetime(trades["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    trades["realized_return"] = pd.to_numeric(trades["realized_return"], errors="coerce")
    candidates = trades[
        trades["fill_status"].eq("filled")
        & trades["entry_trade_date"].notna()
        & trades["exit_trade_date"].notna()
        & trades["realized_return"].notna()
    ].copy()
    candidates = candidates.sort_values(["entry_trade_date", "trade_date", "top_n", "ts_code"], kind="stable").reset_index(drop=True)

    dates = sorted(set(candidates["entry_trade_date"].dropna()) | set(candidates["exit_trade_date"].dropna()))
    cash = 1.0
    running_max = 1.0
    open_positions: dict[str, dict[str, Any]] = {}
    account_rows: list[dict[str, Any]] = []
    curve_rows: list[dict[str, Any]] = []
    trade_records: dict[int, dict[str, Any]] = {}
    by_entry = {date: group for date, group in candidates.groupby("entry_trade_date", sort=False)}

    for date in dates:
        opened_count = 0
        closed_count = 0
        daily_pnl = 0.0

        for ts_code, position in list(open_positions.items()):
            if str(position["exit_trade_date"]) != str(date):
                continue
            pnl = float(position["position_notional"]) * float(position["realized_return"])
            proceeds = float(position["position_notional"]) + pnl
            cash += proceeds
            daily_pnl += pnl
            closed_count += 1
            record = trade_records[int(position["trade_idx"])]
            record["pnl"] = pnl
            open_positions.pop(ts_code, None)

        entries = by_entry.get(date)
        if entries is not None:
            for idx, row in entries.iterrows():
                ts_code = str(row.get("ts_code") or "")
                base_record = _lhb_phase15_trade_record(row)
                if ts_code in open_positions:
                    account_rows.append({**base_record, "account_trade_status": "duplicate_position_skipped", "skip_reason": "duplicate_open_position"})
                    continue
                if len(open_positions) >= int(max_positions):
                    account_rows.append({**base_record, "account_trade_status": "max_positions_skipped", "skip_reason": "max_positions_reached"})
                    continue
                equity_before_entry = cash + sum(float(pos["position_notional"]) for pos in open_positions.values())
                notional = min(equity_before_entry * float(position_pct), cash)
                if notional <= 0.0:
                    account_rows.append({**base_record, "account_trade_status": "cash_skipped", "skip_reason": "insufficient_cash"})
                    continue
                cash -= notional
                trade_idx = len(account_rows)
                record = {
                    **base_record,
                    "account_trade_status": "filled",
                    "position_notional": notional,
                    "pnl": pd.NA,
                    "skip_reason": "",
                }
                account_rows.append(record)
                trade_records[trade_idx] = record
                open_positions[ts_code] = {
                    "trade_idx": trade_idx,
                    "exit_trade_date": row.get("exit_trade_date"),
                    "realized_return": _coerce_numeric(row.get("realized_return"), 0.0),
                    "position_notional": notional,
                }
                opened_count += 1

        invested = sum(float(pos["position_notional"]) for pos in open_positions.values())
        equity = cash + invested
        running_max = max(running_max, equity)
        curve_row = {
            "trade_date": date,
            "cash": cash,
            "invested_notional": invested,
            "equity": equity,
            "drawdown": equity / running_max - 1.0 if running_max else 0.0,
            "open_position_count": len(open_positions),
            "opened_count": opened_count,
            "closed_count": closed_count,
            "daily_realized_pnl": daily_pnl,
        }
        curve_rows.append(curve_row)

    account_trades = pd.DataFrame(account_rows).reindex(columns=LHB_PHASE15_ACCOUNT_TRADE_COLUMNS)
    account_curve = pd.DataFrame(curve_rows).reindex(columns=LHB_PHASE15_ACCOUNT_CURVE_COLUMNS)
    return account_trades, account_curve


def _lhb_phase15_trade_record(row: pd.Series) -> dict[str, Any]:
    return {
        "account_trade_status": "",
        "trade_date": row.get("trade_date", ""),
        "ts_code": row.get("ts_code", ""),
        "top_n": row.get("top_n", ""),
        "phase12a_rule_layer": row.get("phase12a_rule_layer", ""),
        "entry_trade_date": row.get("entry_trade_date", ""),
        "entry_time": row.get("entry_time", ""),
        "entry_price": row.get("entry_price", ""),
        "exit_status": row.get("exit_status", ""),
        "exit_signal": row.get("exit_signal", ""),
        "exit_reason": row.get("exit_reason", ""),
        "exit_trade_date": row.get("exit_trade_date", ""),
        "exit_time": row.get("exit_time", ""),
        "exit_price": row.get("exit_price", ""),
        "realized_return": row.get("realized_return", ""),
        "position_notional": pd.NA,
        "pnl": pd.NA,
        "skip_reason": "",
    }


def _build_lhb_phase15_cash_account_summary(*, account_trades: pd.DataFrame, account_curve: pd.DataFrame) -> pd.DataFrame:
    if account_curve.empty:
        return pd.DataFrame(columns=LHB_PHASE15_ACCOUNT_SUMMARY_COLUMNS)
    filled = account_trades[account_trades["account_trade_status"].eq("filled")] if not account_trades.empty else pd.DataFrame()
    closed = filled[pd.to_numeric(filled.get("pnl", pd.Series(dtype="float64")), errors="coerce").notna()] if not filled.empty else filled
    returns = pd.to_numeric(closed.get("realized_return", pd.Series(dtype="float64")), errors="coerce")
    final_equity = _coerce_numeric(account_curve.iloc[-1].get("equity"), 1.0)
    max_drawdown = pd.to_numeric(account_curve.get("drawdown", pd.Series(dtype="float64")), errors="coerce").min()
    row = {
        "initial_equity": 1.0,
        "final_equity": final_equity,
        "total_return": final_equity - 1.0,
        "max_drawdown": max_drawdown,
        "filled_trade_count": int(len(filled)),
        "closed_trade_count": int(len(closed)),
        "skipped_duplicate_count": int(account_trades["account_trade_status"].eq("duplicate_position_skipped").sum()) if not account_trades.empty else 0,
        "skipped_cash_count": int(account_trades["account_trade_status"].eq("cash_skipped").sum()) if not account_trades.empty else 0,
        "win_rate": (returns > 0).mean() if returns.notna().any() else None,
        "avg_trade_return": returns.mean(),
        "avg_position_notional": pd.to_numeric(closed.get("position_notional", pd.Series(dtype="float64")), errors="coerce").mean(),
    }
    return pd.DataFrame([row]).reindex(columns=LHB_PHASE15_ACCOUNT_SUMMARY_COLUMNS)


def _lhb_phase15_cash_account_markdown(
    *,
    summary: pd.DataFrame,
    account_curve: pd.DataFrame,
    account_trades: pd.DataFrame,
    max_positions: int,
    position_pct: float,
) -> str:
    return "\n".join(
        [
            "# LHB Phase 15 Cash Account Backtest v1",
            "",
            f"- max_positions: {max_positions}",
            f"- position_pct: {position_pct}",
            "",
            "## 1. Summary",
            _table_preview(summary, rows=10),
            "",
            "## 2. Account Curve",
            _table_preview(account_curve, rows=40),
            "",
            "## 3. Account Trades",
            _table_preview(account_trades, rows=40),
            "",
        ]
    )


def _build_lhb_phase16_merged_trade_frame(
    *,
    lifecycle_trades: pd.DataFrame,
    real_entry_trades: pd.DataFrame,
    selected_trades: pd.DataFrame,
) -> pd.DataFrame:
    trades = lifecycle_trades.copy()
    for column in ["trade_date", "ts_code", "top_n", "realized_return", "fill_status"]:
        if column not in trades.columns:
            trades[column] = pd.NA
    trades["trade_date"] = pd.to_datetime(trades["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    trades["ts_code"] = trades["ts_code"].astype(str)
    trades["top_n"] = pd.to_numeric(trades["top_n"], errors="coerce")
    trades["realized_return"] = pd.to_numeric(trades["realized_return"], errors="coerce")

    selected = selected_trades.copy()
    for column in [
        "trade_date",
        "ts_code",
        "top_n",
        "selection_score",
        "lhb_net_buy_ratio",
        "lhb_one_day_pump_risk",
        "lhb_after_break_limit",
        "lhb_after_reversal",
    ]:
        if column not in selected.columns:
            selected[column] = pd.NA
    selected["trade_date"] = pd.to_datetime(selected["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    selected["ts_code"] = selected["ts_code"].astype(str)
    selected["top_n"] = pd.to_numeric(selected["top_n"], errors="coerce")
    if selected["top_n"].isna().all():
        selected = selected.drop(columns=["top_n"])
        selected_merge_keys = ["trade_date", "ts_code"]
    else:
        selected = selected.drop_duplicates(["trade_date", "ts_code", "top_n"])
        selected_merge_keys = ["trade_date", "ts_code", "top_n"]

    real_entry = real_entry_trades.copy()
    for column in ["trade_date", "ts_code", "top_n", "exit_1d_return", "exit_2d_return", "exit_3d_return", "exit_5d_return", "max_drawdown_to_5d"]:
        if column not in real_entry.columns:
            real_entry[column] = pd.NA
    real_entry["trade_date"] = pd.to_datetime(real_entry["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    real_entry["ts_code"] = real_entry["ts_code"].astype(str)
    real_entry["top_n"] = pd.to_numeric(real_entry["top_n"], errors="coerce")
    if real_entry["top_n"].isna().all():
        real_entry = real_entry.drop(columns=["top_n"])
        merge_keys = ["trade_date", "ts_code"]
    else:
        real_entry = real_entry.drop_duplicates(["trade_date", "ts_code", "top_n"])
        merge_keys = ["trade_date", "ts_code", "top_n"]

    selected_cols = [
        column
        for column in [
            "trade_date",
            "ts_code",
            "top_n",
            "selection_score",
            "lhb_net_buy_ratio",
            "lhb_one_day_pump_risk",
            "lhb_after_break_limit",
            "lhb_after_reversal",
        ]
        if column in selected.columns
    ]
    merged = trades.merge(selected[selected_cols], on=selected_merge_keys, how="left")
    real_cols = [
        column
        for column in [
            "trade_date",
            "ts_code",
            "top_n",
            "exit_1d_return",
            "exit_2d_return",
            "exit_3d_return",
            "exit_5d_return",
            "max_drawdown_to_5d",
        ]
        if column in real_entry.columns
    ]
    merged = merged.merge(real_entry[real_cols], on=merge_keys, how="left")
    for column in ["selection_score", "lhb_net_buy_ratio", "lhb_one_day_pump_risk", "exit_5d_return", "max_drawdown_to_5d", "blocked_exit_bar_count"]:
        if column not in merged.columns:
            merged[column] = pd.NA
        merged[column] = pd.to_numeric(merged[column], errors="coerce")
    for column in ["lhb_after_break_limit", "lhb_after_reversal"]:
        if column not in merged.columns:
            merged[column] = False
        merged[column] = merged[column].fillna(False).astype(bool)
    return merged


def _build_lhb_phase16_low_quality_buy_diagnostics(merged: pd.DataFrame, *, min_group_count: int) -> pd.DataFrame:
    filled = _lhb_phase16_filled_trades(merged)
    groups: list[tuple[str, str, pd.Series]] = [
        ("all_filled", "baseline", pd.Series(True, index=filled.index)),
        ("lhb_one_day_pump_risk_high", "pre_trade_feature", filled["lhb_one_day_pump_risk"].ge(0.5)),
        ("lhb_after_break_limit", "pre_trade_feature", filled["lhb_after_break_limit"].astype(bool)),
        ("lhb_after_reversal", "pre_trade_feature", filled["lhb_after_reversal"].astype(bool)),
        ("low_lhb_net_buy_ratio", "pre_trade_feature", filled["lhb_net_buy_ratio"].lt(0.2)),
        ("blocked_exit_history", "execution_risk", filled["blocked_exit_bar_count"].fillna(0).gt(0)),
    ]
    score = pd.to_numeric(filled.get("selection_score", pd.Series(dtype="float64")), errors="coerce")
    if score.notna().any():
        groups.append(("low_selection_score_bottom_quartile", "pre_trade_feature", score.le(score.quantile(0.25))))
    for layer, _ in filled.groupby("phase12a_rule_layer", dropna=False):
        groups.append((f"layer:{layer}", "rule_layer", filled["phase12a_rule_layer"].eq(layer)))
    for signal, _ in filled.groupby("exit_signal", dropna=False):
        groups.append((f"exit_signal:{signal}", "exit_signal", filled["exit_signal"].eq(signal)))

    rows = []
    for name, group_type, mask in groups:
        subset = filled[mask.fillna(False)]
        if len(subset) < int(min_group_count):
            continue
        rows.append(_lhb_phase16_group_summary(name, group_type, subset))
    return (
        pd.DataFrame(rows)
        .reindex(columns=LHB_PHASE16_LOW_QUALITY_COLUMNS)
        .sort_values(["win_rate", "avg_realized_return", "closed_trade_count"], ascending=[True, True, False], na_position="last")
        .reset_index(drop=True)
    )


def _build_lhb_phase16_exit_mistake_diagnostics(merged: pd.DataFrame) -> pd.DataFrame:
    filled = _lhb_phase16_filled_trades(merged)
    filled["missed_return_vs_5d"] = pd.to_numeric(filled["exit_5d_return"], errors="coerce") - pd.to_numeric(filled["realized_return"], errors="coerce")
    mask = (
        filled["exit_status"].eq("signal_exit")
        & filled["exit_5d_return"].gt(0)
        & filled["missed_return_vs_5d"].ge(0.05)
    )
    result = filled.loc[mask].copy()
    result["exit_mistake_type"] = "early_exit_positive_5d"
    return (
        result.reindex(columns=LHB_PHASE16_EXIT_MISTAKE_COLUMNS)
        .sort_values(["missed_return_vs_5d", "exit_5d_return"], ascending=[False, False], na_position="last")
        .reset_index(drop=True)
    )


def _build_lhb_phase16_filter_scan(merged: pd.DataFrame) -> pd.DataFrame:
    profiles: list[tuple[str, str, pd.Series]] = [
        ("baseline", "No extra quality filter", pd.Series(True, index=merged.index)),
        ("exclude_high_pump_risk", "Drop lhb_one_day_pump_risk >= 0.5", merged["lhb_one_day_pump_risk"].lt(0.5) | merged["lhb_one_day_pump_risk"].isna()),
        ("exclude_after_break_limit", "Drop LHB after break-limit events", ~merged["lhb_after_break_limit"].astype(bool)),
        ("exclude_after_reversal", "Drop LHB after reversal events", ~merged["lhb_after_reversal"].astype(bool)),
        ("exclude_low_lhb_net_buy_ratio", "Keep lhb_net_buy_ratio >= 0.2 or missing", merged["lhb_net_buy_ratio"].ge(0.2) | merged["lhb_net_buy_ratio"].isna()),
        (
            "exclude_high_pump_or_break_limit",
            "Drop high one-day-pump risk and break-limit events",
            (merged["lhb_one_day_pump_risk"].lt(0.5) | merged["lhb_one_day_pump_risk"].isna()) & ~merged["lhb_after_break_limit"].astype(bool),
        ),
        (
            "quality_combo_conservative",
            "Keep low pump risk, no break/reversal, and lhb_net_buy_ratio >= 0.2",
            (merged["lhb_one_day_pump_risk"].lt(0.5) | merged["lhb_one_day_pump_risk"].isna())
            & ~merged["lhb_after_break_limit"].astype(bool)
            & ~merged["lhb_after_reversal"].astype(bool)
            & (merged["lhb_net_buy_ratio"].ge(0.2) | merged["lhb_net_buy_ratio"].isna()),
        ),
    ]
    score = pd.to_numeric(merged.get("selection_score", pd.Series(dtype="float64")), errors="coerce")
    if score.notna().any():
        profiles.append(("exclude_low_selection_score", "Drop bottom quartile selection_score", score.ge(score.quantile(0.25)) | score.isna()))

    rows = []
    for profile, description, mask in profiles:
        subset = merged[mask.fillna(False)].copy()
        filled = _lhb_phase16_filled_trades(subset)
        returns = pd.to_numeric(filled.get("realized_return", pd.Series(dtype="float64")), errors="coerce").dropna()
        curve = _build_lhb_phase14c_daily_curve(subset) if not subset.empty else pd.DataFrame(columns=LHB_PHASE14C_DAILY_CURVE_COLUMNS)
        account_trades, account_curve = _build_lhb_phase15_cash_account_frames(
            lifecycle_trades=subset,
            max_positions=10,
            position_pct=0.10,
        )
        final_equity = pd.to_numeric(curve.get("equity", pd.Series(dtype="float64")), errors="coerce").iloc[-1] if not curve.empty else pd.NA
        account_final_equity = (
            pd.to_numeric(account_curve.get("equity", pd.Series(dtype="float64")), errors="coerce").iloc[-1]
            if not account_curve.empty
            else pd.NA
        )
        rows.append(
            {
                "filter_profile": profile,
                "description": description,
                "entry_count": int(len(subset)),
                "closed_trade_count": int(len(returns)),
                "win_rate": float((returns > 0).mean()) if len(returns) else pd.NA,
                "avg_realized_return": float(returns.mean()) if len(returns) else pd.NA,
                "final_equity": final_equity,
                "max_drawdown": pd.to_numeric(curve.get("drawdown", pd.Series(dtype="float64")), errors="coerce").min() if not curve.empty else pd.NA,
                "account_final_equity": account_final_equity,
                "account_max_drawdown": pd.to_numeric(account_curve.get("drawdown", pd.Series(dtype="float64")), errors="coerce").min() if not account_curve.empty else pd.NA,
            }
        )
        _ = account_trades
    return (
        pd.DataFrame(rows)
        .reindex(columns=LHB_PHASE16_FILTER_SCAN_COLUMNS)
        .sort_values(["account_final_equity", "win_rate", "closed_trade_count"], ascending=[False, False, False], na_position="last")
        .reset_index(drop=True)
    )


def _lhb_phase16_filled_trades(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    filled = frame[frame["fill_status"].eq("filled")].copy()
    filled["realized_return"] = pd.to_numeric(filled.get("realized_return", pd.Series(dtype="float64")), errors="coerce")
    return filled[filled["realized_return"].notna()].copy()


def _lhb_phase16_group_summary(name: str, group_type: str, subset: pd.DataFrame) -> dict[str, Any]:
    returns = pd.to_numeric(subset.get("realized_return", pd.Series(dtype="float64")), errors="coerce").dropna()
    exit_5d = pd.to_numeric(subset.get("exit_5d_return", pd.Series(dtype="float64")), errors="coerce")
    missed = exit_5d - pd.to_numeric(subset.get("realized_return", pd.Series(dtype="float64")), errors="coerce")
    drawdown = pd.to_numeric(subset.get("max_drawdown_to_5d", pd.Series(dtype="float64")), errors="coerce")
    return {
        "diagnostic_group": name,
        "diagnostic_type": group_type,
        "closed_trade_count": int(len(returns)),
        "win_rate": float((returns > 0).mean()) if len(returns) else pd.NA,
        "loss_rate": float((returns <= 0).mean()) if len(returns) else pd.NA,
        "avg_realized_return": float(returns.mean()) if len(returns) else pd.NA,
        "avg_exit_5d_return": float(exit_5d.mean()) if exit_5d.notna().any() else pd.NA,
        "avg_missed_return_vs_5d": float(missed.mean()) if missed.notna().any() else pd.NA,
        "avg_max_drawdown_to_5d": float(drawdown.mean()) if drawdown.notna().any() else pd.NA,
        "bad_trade_count": int((returns <= 0).sum()),
    }


def _lhb_phase16_quality_improvement_markdown(
    *,
    low_quality: pd.DataFrame,
    exit_mistakes: pd.DataFrame,
    filter_scan: pd.DataFrame,
    min_group_count: int,
) -> str:
    return "\n".join(
        [
            "# LHB Phase 16 Quality Improvement Diagnostics v1",
            "",
            f"- min_group_count: {min_group_count}",
            "",
            "## 1. Low Quality Buy Diagnostics",
            _table_preview(low_quality, rows=30),
            "",
            "## 2. Exit Mistake Diagnostics",
            _table_preview(exit_mistakes, rows=40),
            "",
            "## 3. Tradable Filter Scan",
            _table_preview(filter_scan, rows=30),
            "",
        ]
    )


def _build_lhb_phase16b_limit_break_failed_opportunities(merged: pd.DataFrame) -> pd.DataFrame:
    filled = _lhb_phase16_filled_trades(merged)
    subset = filled[
        filled["exit_signal"].eq("limit_break_failed")
        & filled["exit_status"].eq("signal_exit")
        & filled["realized_return"].notna()
    ].copy()
    for column in ["exit_1d_return", "exit_2d_return", "exit_3d_return", "exit_5d_return"]:
        if column not in subset.columns:
            subset[column] = pd.NA
        subset[column] = pd.to_numeric(subset[column], errors="coerce")
        horizon = column.replace("exit_", "").replace("_return", "")
        subset[f"missed_return_to_{horizon}"] = subset[column] - subset["realized_return"]
    subset["candidate_profile"] = subset.apply(_lhb_phase16b_candidate_profile, axis=1)
    return (
        subset.reindex(columns=LHB_PHASE16B_OPPORTUNITY_COLUMNS)
        .sort_values(["missed_return_to_2d", "missed_return_to_5d"], ascending=[False, False], na_position="last")
        .reset_index(drop=True)
    )


def _build_lhb_phase16b_limit_break_failed_strategy_summary(opportunity_trades: pd.DataFrame) -> pd.DataFrame:
    strategies = [
        ("current_exit", "realized_return"),
        ("hold_to_1d", "exit_1d_return"),
        ("hold_to_2d", "exit_2d_return"),
        ("hold_to_3d", "exit_3d_return"),
        ("hold_to_5d", "exit_5d_return"),
    ]
    current = pd.to_numeric(opportunity_trades.get("realized_return", pd.Series(dtype="float64")), errors="coerce")
    rows = []
    for strategy, column in strategies:
        returns = pd.to_numeric(opportunity_trades.get(column, pd.Series(dtype="float64")), errors="coerce").dropna()
        curve = _lhb_phase16b_return_curve(returns)
        rows.append(
            {
                "strategy": strategy,
                "trade_count": int(len(returns)),
                "win_rate": float((returns > 0).mean()) if len(returns) else pd.NA,
                "avg_return": float(returns.mean()) if len(returns) else pd.NA,
                "median_return": float(returns.median()) if len(returns) else pd.NA,
                "worst_return": float(returns.min()) if len(returns) else pd.NA,
                "best_return": float(returns.max()) if len(returns) else pd.NA,
                "avg_missed_vs_current": float((returns.reset_index(drop=True) - current.dropna().reset_index(drop=True)).mean())
                if len(returns) and len(returns) == len(current.dropna())
                else pd.NA,
                "final_equity": curve[-1] if curve else pd.NA,
                "max_drawdown": _lhb_phase16b_max_drawdown(curve) if curve else pd.NA,
            }
        )
    return pd.DataFrame(rows).reindex(columns=LHB_PHASE16B_STRATEGY_SUMMARY_COLUMNS)


def _build_lhb_phase16b_limit_break_failed_candidate_summary(opportunity_trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for profile, group in opportunity_trades.groupby("candidate_profile", dropna=False):
        returns = pd.to_numeric(group.get("realized_return", pd.Series(dtype="float64")), errors="coerce").dropna()
        exit_2d = pd.to_numeric(group.get("exit_2d_return", pd.Series(dtype="float64")), errors="coerce")
        exit_5d = pd.to_numeric(group.get("exit_5d_return", pd.Series(dtype="float64")), errors="coerce")
        rows.append(
            {
                "candidate_profile": profile,
                "trade_count": int(len(group)),
                "win_rate": float((returns > 0).mean()) if len(returns) else pd.NA,
                "avg_realized_return": float(returns.mean()) if len(returns) else pd.NA,
                "avg_exit_2d_return": float(exit_2d.mean()) if exit_2d.notna().any() else pd.NA,
                "avg_exit_5d_return": float(exit_5d.mean()) if exit_5d.notna().any() else pd.NA,
                "avg_missed_return_to_2d": float(pd.to_numeric(group.get("missed_return_to_2d", pd.Series(dtype="float64")), errors="coerce").mean()),
                "avg_missed_return_to_5d": float(pd.to_numeric(group.get("missed_return_to_5d", pd.Series(dtype="float64")), errors="coerce").mean()),
            }
        )
    return (
        pd.DataFrame(rows)
        .reindex(columns=LHB_PHASE16B_CANDIDATE_SUMMARY_COLUMNS)
        .sort_values(["avg_missed_return_to_2d", "trade_count"], ascending=[False, False], na_position="last")
        .reset_index(drop=True)
    )


def _lhb_phase16b_candidate_profile(row: pd.Series) -> str:
    score = _coerce_numeric(row.get("selection_score"), 0.0)
    ratio = _coerce_numeric(row.get("lhb_net_buy_ratio"), 0.0)
    if score >= 300.0 and ratio >= 0.2:
        return "strong_lhb_quality"
    if score < 150.0 or ratio < 0.2:
        return "weak_lhb_quality"
    return "middle_lhb_quality"


def _lhb_phase16b_return_curve(returns: pd.Series) -> list[float]:
    equity = 1.0
    curve = []
    for value in returns:
        if pd.isna(value):
            continue
        equity *= 1.0 + float(value)
        curve.append(equity)
    return curve


def _lhb_phase16b_max_drawdown(curve: list[float]) -> float:
    running_max = 1.0
    max_drawdown = 0.0
    for equity in curve:
        running_max = max(running_max, equity)
        max_drawdown = min(max_drawdown, equity / running_max - 1.0)
    return max_drawdown


def _lhb_phase16b_limit_break_failed_markdown(
    *,
    opportunity_trades: pd.DataFrame,
    strategy_summary: pd.DataFrame,
    candidate_summary: pd.DataFrame,
) -> str:
    return "\n".join(
        [
            "# LHB Phase 16B Limit Break Failed Exit Replay v1",
            "",
            "## 1. Strategy Summary",
            _table_preview(strategy_summary, rows=10),
            "",
            "## 2. Candidate Summary",
            _table_preview(candidate_summary, rows=20),
            "",
            "## 3. Opportunity Trades",
            _table_preview(opportunity_trades, rows=40),
            "",
        ]
    )


def _build_lhb_phase16c_limit_break_failed_rule_scan_frames(merged: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    profiles: list[tuple[str, str, str | None, str]] = [
        ("baseline_current_exit", "Current lifecycle exits", None, ""),
        ("delay_all_limit_break_failed_to_2d", "Replace every limit_break_failed realized return with exit_2d_return", "exit_2d_return", "limit_break_failed_delay_to_2d"),
        ("delay_all_limit_break_failed_to_3d", "Replace every limit_break_failed realized return with exit_3d_return", "exit_3d_return", "limit_break_failed_delay_to_3d"),
        ("delay_all_limit_break_failed_to_5d", "Replace every limit_break_failed realized return with exit_5d_return", "exit_5d_return", "limit_break_failed_delay_to_5d"),
        (
            "delay_strong_quality_limit_break_failed_to_3d",
            "Replace strong-quality limit_break_failed trades with exit_3d_return",
            "exit_3d_return",
            "strong_quality_limit_break_failed_delay_to_3d",
        ),
    ]
    adjusted_frames = []
    summary_rows = []
    for profile, description, replacement_column, reason in profiles:
        adjusted = merged.copy()
        adjusted["rule_profile"] = profile
        adjusted["original_realized_return"] = pd.to_numeric(adjusted.get("realized_return", pd.Series(dtype="float64")), errors="coerce")
        adjusted["phase16c_adjust_reason"] = ""
        mask = adjusted["exit_signal"].eq("limit_break_failed") & adjusted["fill_status"].eq("filled")
        if profile == "delay_strong_quality_limit_break_failed_to_3d":
            mask = mask & adjusted.apply(_lhb_phase16c_is_strong_quality_limit_break, axis=1)
        if replacement_column is not None:
            replacement = pd.to_numeric(adjusted.get(replacement_column, pd.Series(dtype="float64")), errors="coerce")
            replace_mask = mask & replacement.notna()
            adjusted.loc[replace_mask, "realized_return"] = replacement.loc[replace_mask]
            adjusted.loc[replace_mask, "phase16c_adjust_reason"] = reason

        adjusted_frames.append(adjusted.reindex(columns=LHB_PHASE16C_ADJUSTED_TRADE_COLUMNS))
        summary_rows.append(_lhb_phase16c_rule_scan_summary_row(profile, description, adjusted))
    adjusted_trades = pd.concat(adjusted_frames, ignore_index=True).reindex(columns=LHB_PHASE16C_ADJUSTED_TRADE_COLUMNS)
    summary = (
        pd.DataFrame(summary_rows)
        .reindex(columns=LHB_PHASE16C_RULE_SCAN_SUMMARY_COLUMNS)
        .sort_values(["account_final_equity", "avg_realized_return"], ascending=[False, False], na_position="last")
        .reset_index(drop=True)
    )
    return adjusted_trades, summary


def _lhb_phase16c_is_strong_quality_limit_break(row: pd.Series) -> bool:
    return _coerce_numeric(row.get("selection_score"), 0.0) >= 300.0 and _coerce_numeric(row.get("lhb_net_buy_ratio"), 0.0) >= 0.2


def _lhb_phase16c_rule_scan_summary_row(profile: str, description: str, adjusted: pd.DataFrame) -> dict[str, Any]:
    filled = _lhb_phase16_filled_trades(adjusted)
    returns = pd.to_numeric(filled.get("realized_return", pd.Series(dtype="float64")), errors="coerce").dropna()
    curve = _build_lhb_phase14c_daily_curve(adjusted)
    _, account_curve = _build_lhb_phase15_cash_account_frames(
        lifecycle_trades=adjusted,
        max_positions=10,
        position_pct=0.10,
    )
    return {
        "rule_profile": profile,
        "description": description,
        "entry_count": int(len(adjusted)),
        "closed_trade_count": int(len(returns)),
        "adjusted_trade_count": int(adjusted.get("phase16c_adjust_reason", pd.Series(dtype="object")).astype(str).ne("").sum()),
        "win_rate": float((returns > 0).mean()) if len(returns) else pd.NA,
        "avg_realized_return": float(returns.mean()) if len(returns) else pd.NA,
        "median_realized_return": float(returns.median()) if len(returns) else pd.NA,
        "worst_realized_return": float(returns.min()) if len(returns) else pd.NA,
        "best_realized_return": float(returns.max()) if len(returns) else pd.NA,
        "final_equity": pd.to_numeric(curve.get("equity", pd.Series(dtype="float64")), errors="coerce").iloc[-1] if not curve.empty else pd.NA,
        "max_drawdown": pd.to_numeric(curve.get("drawdown", pd.Series(dtype="float64")), errors="coerce").min() if not curve.empty else pd.NA,
        "account_final_equity": pd.to_numeric(account_curve.get("equity", pd.Series(dtype="float64")), errors="coerce").iloc[-1] if not account_curve.empty else pd.NA,
        "account_max_drawdown": pd.to_numeric(account_curve.get("drawdown", pd.Series(dtype="float64")), errors="coerce").min() if not account_curve.empty else pd.NA,
    }


def _lhb_phase16c_limit_break_failed_rule_scan_markdown(
    *,
    adjusted_trades: pd.DataFrame,
    summary: pd.DataFrame,
) -> str:
    return "\n".join(
        [
            "# LHB Phase 16C Limit Break Failed Rule Scan v1",
            "",
            "This is a return-substitution diagnostic. It does not yet change 5min exit timestamps or capital holding time.",
            "",
            "## 1. Rule Scan Summary",
            _table_preview(summary, rows=20),
            "",
            "## 2. Adjusted Trades Preview",
            _table_preview(adjusted_trades[adjusted_trades["phase16c_adjust_reason"].astype(str).ne("")], rows=40),
            "",
        ]
    )


def _build_lhb_phase16d_indicator_detail(*, merged: pd.DataFrame, minute_bars: pd.DataFrame) -> pd.DataFrame:
    trades = _lhb_phase16_filled_trades(merged)
    trades = trades[
        trades["exit_signal"].eq("limit_break_failed")
        & trades["exit_status"].eq("signal_exit")
        & trades["exit_trade_date"].notna()
    ].copy()
    trades["missed_return_to_3d"] = pd.to_numeric(trades.get("exit_3d_return", pd.Series(dtype="float64")), errors="coerce") - trades["realized_return"]
    trades["hold_label"] = trades["missed_return_to_3d"].apply(
        lambda value: "good_hold" if pd.notna(value) and value >= 0.03 else "should_exit"
    )

    bars = minute_bars.copy()
    for column in ["trade_date", "ts_code", "trade_time", "open", "high", "low", "close", "volume", "amount"]:
        if column not in bars.columns:
            bars[column] = pd.NA
    bars["trade_date"] = pd.to_datetime(bars["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    bars["trade_time"] = pd.to_datetime(bars["trade_time"], errors="coerce")
    bars["ts_code"] = bars["ts_code"].astype(str)
    for column in ["open", "high", "low", "close", "volume", "amount"]:
        bars[column] = pd.to_numeric(bars[column], errors="coerce")
    bars = bars.sort_values(["ts_code", "trade_date", "trade_time"], kind="stable")
    date_map = _lhb_phase16d_next_date_map(bars)

    rows = []
    for _, row in trades.iterrows():
        ts_code = str(row.get("ts_code") or "")
        exit_date = str(row.get("exit_trade_date") or "")
        exit_bars = bars[bars["ts_code"].eq(ts_code) & bars["trade_date"].eq(exit_date)]
        next_date = date_map.get((ts_code, exit_date), "")
        next_bars = bars[bars["ts_code"].eq(ts_code) & bars["trade_date"].eq(next_date)].head(6) if next_date else pd.DataFrame()
        exit_metrics = _lhb_phase16d_day_metrics(exit_bars)
        next_metrics = _lhb_phase16d_next_morning_metrics(next_bars)
        record = row.to_dict()
        record.update(exit_metrics)
        record.update(next_metrics)
        rows.append(record)
    return pd.DataFrame(rows).reindex(columns=LHB_PHASE16D_INDICATOR_DETAIL_COLUMNS).reset_index(drop=True)


def _build_lhb_phase16d_indicator_summary(detail: pd.DataFrame) -> pd.DataFrame:
    rules: list[tuple[str, pd.Series]] = [
        ("exit_day_close_position_ge_0_70", pd.to_numeric(detail.get("exit_day_close_position", pd.Series(dtype="float64")), errors="coerce").ge(0.70)),
        ("exit_day_close_vs_vwap_ge_0", pd.to_numeric(detail.get("exit_day_close_vs_vwap", pd.Series(dtype="float64")), errors="coerce").ge(0.0)),
        ("exit_day_high_to_close_drawdown_ge_neg_0_03", pd.to_numeric(detail.get("exit_day_high_to_close_drawdown", pd.Series(dtype="float64")), errors="coerce").ge(-0.03)),
        ("exit_day_close_vs_entry_ge_0_05", pd.to_numeric(detail.get("exit_day_close_vs_entry", pd.Series(dtype="float64")), errors="coerce").ge(0.05)),
        ("next_morning_return_ge_0", pd.to_numeric(detail.get("next_morning_return", pd.Series(dtype="float64")), errors="coerce").ge(0.0)),
        ("next_morning_close_vs_vwap_ge_0", pd.to_numeric(detail.get("next_morning_close_vs_vwap", pd.Series(dtype="float64")), errors="coerce").ge(0.0)),
        ("selection_score_ge_300", pd.to_numeric(detail.get("selection_score", pd.Series(dtype="float64")), errors="coerce").ge(300.0)),
        ("lhb_net_buy_ratio_ge_0_20", pd.to_numeric(detail.get("lhb_net_buy_ratio", pd.Series(dtype="float64")), errors="coerce").ge(0.20)),
    ]
    rows = []
    for name, mask in rules:
        subset = detail[mask.fillna(False)]
        rows.append(_lhb_phase16d_indicator_summary_row(name, subset))
    return (
        pd.DataFrame(rows)
        .reindex(columns=LHB_PHASE16D_INDICATOR_SUMMARY_COLUMNS)
        .sort_values(["good_hold_rate", "matched_count"], ascending=[False, False], na_position="last")
        .reset_index(drop=True)
    )


def _lhb_phase16d_indicator_summary_row(name: str, subset: pd.DataFrame) -> dict[str, Any]:
    good = subset["hold_label"].eq("good_hold") if "hold_label" in subset.columns else pd.Series(dtype="bool")
    should_exit = subset["hold_label"].eq("should_exit") if "hold_label" in subset.columns else pd.Series(dtype="bool")
    return {
        "indicator_rule": name,
        "matched_count": int(len(subset)),
        "good_hold_count": int(good.sum()),
        "should_exit_count": int(should_exit.sum()),
        "good_hold_rate": float(good.mean()) if len(subset) else pd.NA,
        "avg_missed_return_to_3d": pd.to_numeric(subset.get("missed_return_to_3d", pd.Series(dtype="float64")), errors="coerce").mean(),
        "avg_realized_return": pd.to_numeric(subset.get("realized_return", pd.Series(dtype="float64")), errors="coerce").mean(),
    }


def _lhb_phase16d_day_metrics(day_bars: pd.DataFrame) -> dict[str, float]:
    if day_bars.empty:
        return {
            "exit_day_close_vs_vwap": pd.NA,
            "exit_day_close_position": pd.NA,
            "exit_day_high_to_close_drawdown": pd.NA,
            "exit_day_close_vs_entry": pd.NA,
        }
    high = pd.to_numeric(day_bars["high"], errors="coerce").max()
    low = pd.to_numeric(day_bars["low"], errors="coerce").min()
    close = _coerce_numeric(day_bars.iloc[-1].get("close"), 0.0)
    amount = pd.to_numeric(day_bars.get("amount", pd.Series(dtype="float64")), errors="coerce").sum()
    volume = pd.to_numeric(day_bars.get("volume", pd.Series(dtype="float64")), errors="coerce").sum()
    vwap = amount / volume if volume else pd.NA
    first_open = _coerce_numeric(day_bars.iloc[0].get("open"), 0.0)
    return {
        "exit_day_close_vs_vwap": _safe_return(close, vwap) if pd.notna(vwap) else pd.NA,
        "exit_day_close_position": (close - low) / (high - low) if high and low and high > low else pd.NA,
        "exit_day_high_to_close_drawdown": _safe_return(close, high),
        "exit_day_close_vs_entry": _safe_return(close, first_open),
    }


def _lhb_phase16d_next_morning_metrics(next_bars: pd.DataFrame) -> dict[str, float]:
    if next_bars.empty:
        return {"next_morning_return": pd.NA, "next_morning_close_vs_vwap": pd.NA}
    first_open = _coerce_numeric(next_bars.iloc[0].get("open"), 0.0)
    close = _coerce_numeric(next_bars.iloc[-1].get("close"), 0.0)
    amount = pd.to_numeric(next_bars.get("amount", pd.Series(dtype="float64")), errors="coerce").sum()
    volume = pd.to_numeric(next_bars.get("volume", pd.Series(dtype="float64")), errors="coerce").sum()
    vwap = amount / volume if volume else pd.NA
    return {
        "next_morning_return": _safe_return(close, first_open),
        "next_morning_close_vs_vwap": _safe_return(close, vwap) if pd.notna(vwap) else pd.NA,
    }


def _lhb_phase16d_next_date_map(bars: pd.DataFrame) -> dict[tuple[str, str], str]:
    mapping: dict[tuple[str, str], str] = {}
    for ts_code, group in bars.groupby("ts_code", sort=False):
        dates = sorted(group["trade_date"].dropna().astype(str).unique().tolist())
        for idx, date in enumerate(dates[:-1]):
            mapping[(str(ts_code), date)] = dates[idx + 1]
    return mapping


def _lhb_phase16d_indicator_discovery_markdown(*, detail: pd.DataFrame, summary: pd.DataFrame) -> str:
    return "\n".join(
        [
            "# LHB Phase 16D Limit Break Failed Indicator Discovery v1",
            "",
            "Hold label: good_hold when exit_3d_return - current realized_return >= 3%.",
            "",
            "## 1. Indicator Summary",
            _table_preview(summary, rows=30),
            "",
            "## 2. Indicator Detail",
            _table_preview(detail, rows=40),
            "",
        ]
    )


def _build_lhb_phase16e_indicator_rule_scan_frames(
    *,
    merged: pd.DataFrame,
    indicator_detail: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    indicator_cols = [
        "trade_date",
        "ts_code",
        "top_n",
        "exit_day_close_vs_vwap",
        "next_morning_close_vs_vwap",
    ]
    indicators = indicator_detail[[column for column in indicator_cols if column in indicator_detail.columns]].copy()
    indicators["trade_date"] = pd.to_datetime(indicators["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    indicators["ts_code"] = indicators["ts_code"].astype(str)
    if "top_n" in indicators.columns:
        indicators["top_n"] = pd.to_numeric(indicators["top_n"], errors="coerce")

    base = merged.copy()
    base["trade_date"] = pd.to_datetime(base["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    base["ts_code"] = base["ts_code"].astype(str)
    base["top_n"] = pd.to_numeric(base["top_n"], errors="coerce")
    base = base.merge(indicators, on=["trade_date", "ts_code", "top_n"], how="left")

    profiles: list[tuple[str, str, str, Any]] = [
        ("baseline_current_exit", "Current lifecycle exits", "", lambda frame: pd.Series(False, index=frame.index)),
        (
            "delay_if_exit_day_close_vs_vwap_ge_0_to_3d",
            "Delay limit_break_failed to 3d when exit day close is above VWAP",
            "exit_day_close_vs_vwap_ge_0_delay_to_3d",
            lambda frame: pd.to_numeric(frame["exit_day_close_vs_vwap"], errors="coerce").ge(0.0),
        ),
        (
            "delay_if_exit_day_close_vs_vwap_ge_0_and_lhb_ratio_ge_0_2_to_3d",
            "Delay when exit day close is above VWAP and lhb_net_buy_ratio >= 0.2",
            "exit_day_vwap_and_lhb_ratio_delay_to_3d",
            lambda frame: pd.to_numeric(frame["exit_day_close_vs_vwap"], errors="coerce").ge(0.0)
            & pd.to_numeric(frame["lhb_net_buy_ratio"], errors="coerce").ge(0.2),
        ),
        (
            "delay_if_exit_and_next_morning_vwap_ge_0_to_3d",
            "Delay when exit day and next morning closes are above VWAP",
            "exit_day_and_next_morning_vwap_delay_to_3d",
            lambda frame: pd.to_numeric(frame["exit_day_close_vs_vwap"], errors="coerce").ge(0.0)
            & pd.to_numeric(frame["next_morning_close_vs_vwap"], errors="coerce").ge(0.0),
        ),
    ]

    adjusted_frames = []
    summary_rows = []
    for profile, description, reason, mask_fn in profiles:
        adjusted = base.copy()
        adjusted["rule_profile"] = profile
        adjusted["original_realized_return"] = pd.to_numeric(adjusted["realized_return"], errors="coerce")
        adjusted["phase16e_adjust_reason"] = ""
        mask = (
            adjusted["fill_status"].eq("filled")
            & adjusted["exit_signal"].eq("limit_break_failed")
            & mask_fn(adjusted).fillna(False)
            & pd.to_numeric(adjusted.get("exit_3d_return", pd.Series(dtype="float64")), errors="coerce").notna()
        )
        if reason:
            adjusted.loc[mask, "realized_return"] = pd.to_numeric(adjusted.loc[mask, "exit_3d_return"], errors="coerce")
            adjusted.loc[mask, "phase16e_adjust_reason"] = reason
        adjusted_frames.append(adjusted.reindex(columns=LHB_PHASE16E_ADJUSTED_TRADE_COLUMNS))
        summary_rows.append(_lhb_phase16e_rule_scan_summary_row(profile, description, adjusted))
    adjusted_trades = pd.concat(adjusted_frames, ignore_index=True).reindex(columns=LHB_PHASE16E_ADJUSTED_TRADE_COLUMNS)
    summary = (
        pd.DataFrame(summary_rows)
        .reindex(columns=LHB_PHASE16E_RULE_SCAN_SUMMARY_COLUMNS)
        .sort_values(["account_final_equity", "avg_realized_return"], ascending=[False, False], na_position="last")
        .reset_index(drop=True)
    )
    return adjusted_trades, summary


def _lhb_phase16e_rule_scan_summary_row(profile: str, description: str, adjusted: pd.DataFrame) -> dict[str, Any]:
    filled = _lhb_phase16_filled_trades(adjusted)
    returns = pd.to_numeric(filled.get("realized_return", pd.Series(dtype="float64")), errors="coerce").dropna()
    curve = _build_lhb_phase14c_daily_curve(adjusted)
    _, account_curve = _build_lhb_phase15_cash_account_frames(lifecycle_trades=adjusted, max_positions=10, position_pct=0.10)
    return {
        "rule_profile": profile,
        "description": description,
        "entry_count": int(len(adjusted)),
        "closed_trade_count": int(len(returns)),
        "adjusted_trade_count": int(adjusted.get("phase16e_adjust_reason", pd.Series(dtype="object")).astype(str).ne("").sum()),
        "win_rate": float((returns > 0).mean()) if len(returns) else pd.NA,
        "avg_realized_return": round(float(returns.mean()), 6) if len(returns) else pd.NA,
        "median_realized_return": float(returns.median()) if len(returns) else pd.NA,
        "worst_realized_return": float(returns.min()) if len(returns) else pd.NA,
        "best_realized_return": float(returns.max()) if len(returns) else pd.NA,
        "final_equity": pd.to_numeric(curve.get("equity", pd.Series(dtype="float64")), errors="coerce").iloc[-1] if not curve.empty else pd.NA,
        "max_drawdown": pd.to_numeric(curve.get("drawdown", pd.Series(dtype="float64")), errors="coerce").min() if not curve.empty else pd.NA,
        "account_final_equity": pd.to_numeric(account_curve.get("equity", pd.Series(dtype="float64")), errors="coerce").iloc[-1] if not account_curve.empty else pd.NA,
        "account_max_drawdown": pd.to_numeric(account_curve.get("drawdown", pd.Series(dtype="float64")), errors="coerce").min() if not account_curve.empty else pd.NA,
    }


def _lhb_phase16e_indicator_rule_scan_markdown(*, adjusted_trades: pd.DataFrame, summary: pd.DataFrame) -> str:
    adjusted = adjusted_trades[adjusted_trades["phase16e_adjust_reason"].astype(str).ne("")]
    return "\n".join(
        [
            "# LHB Phase 16E Limit Break Failed Indicator Rule Scan v1",
            "",
            "This is an indicator-gated return-substitution scan for limit_break_failed exits.",
            "",
            "## 1. Rule Scan Summary",
            _table_preview(summary, rows=20),
            "",
            "## 2. Adjusted Trades Preview",
            _table_preview(adjusted, rows=40),
            "",
        ]
    )


def _build_lhb_phase14_lifecycle_exit_summary(lifecycle_trades: pd.DataFrame) -> pd.DataFrame:
    columns = LHB_PHASE14_LIFECYCLE_EXIT_SUMMARY_COLUMNS
    if lifecycle_trades.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for layer, group in lifecycle_trades.groupby("phase12a_rule_layer", dropna=False):
        filled = group[group["fill_status"].eq("filled")]
        returns = pd.to_numeric(filled.get("realized_return", pd.Series(dtype="float64")), errors="coerce")
        valid = returns.dropna()
        rows.append(
            {
                "phase12a_rule_layer": layer,
                "entry_count": int(len(group)),
                "filled_count": int(len(filled)),
                "signal_exit_count": int(filled["exit_status"].eq("signal_exit").sum()) if not filled.empty else 0,
                "fallback_exit_count": int(filled["exit_status"].eq("max_hold_exit").sum()) if not filled.empty else 0,
                "avg_realized_return": returns.mean(),
                "win_rate": (valid > 0).mean() if not valid.empty else None,
                "avg_holding_trade_days": pd.to_numeric(
                    filled.get("holding_trade_days", pd.Series(dtype="float64")),
                    errors="coerce",
                ).mean(),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(
        ["filled_count", "phase12a_rule_layer"],
        ascending=[False, True],
        kind="stable",
    ).reset_index(drop=True)


def _lhb_phase14_lifecycle_exit_markdown(*, lifecycle_trades: pd.DataFrame, summary: pd.DataFrame) -> str:
    return "\n".join(
        [
            "# LHB Phase 14 Lifecycle Exit v1",
            "",
            "T+0 sell is disabled. Exit scanning starts from the first trading day after the confirmed entry day.",
            "",
            "## 1. Summary",
            _table_preview(summary, rows=20),
            "",
            "## 2. Lifecycle Trades Preview",
            _table_preview(lifecycle_trades, rows=40),
            "",
        ]
    )


def _build_lhb_phase13_two_stage_decision_frame(
    *,
    event_features: pd.DataFrame,
    t1_features: pd.DataFrame | None,
) -> pd.DataFrame:
    columns = LHB_PHASE13_SIGNAL_COLUMNS
    if event_features.empty:
        return pd.DataFrame(columns=columns)
    events = event_features.copy()
    for column in [
        "trade_date",
        "t1_trade_date",
        "ts_code",
        "stock_name",
        "event_family",
        "prev_limit_up_streak",
        "event_close_position",
        "event_high_to_close_drawdown",
        "amount_vs_20d",
        "lhb_net_amount",
        "post_5d_return",
        "post_5d_max_drawdown",
    ]:
        if column not in events.columns:
            events[column] = ""
    events["trade_date"] = pd.to_datetime(events["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    events["t1_trade_date"] = pd.to_datetime(events["t1_trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    events["ts_code"] = events["ts_code"].fillna("").astype(str).str.strip().str.upper()

    if t1_features is not None and not t1_features.empty:
        t1 = t1_features.copy()
        for column in [
            "trade_date",
            "t1_trade_date",
            "ts_code",
            "t1_midday_return",
            "t1_close_vs_vwap",
            "t1_final_close_position",
            "t1_weak_close_like",
            "t1_retreat_proxy",
        ]:
            if column not in t1.columns:
                t1[column] = ""
        t1["trade_date"] = pd.to_datetime(t1["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        t1["t1_trade_date"] = pd.to_datetime(t1["t1_trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        t1["ts_code"] = t1["ts_code"].fillna("").astype(str).str.strip().str.upper()
        t1 = t1[
            [
                "trade_date",
                "t1_trade_date",
                "ts_code",
                "t1_midday_return",
                "t1_close_vs_vwap",
                "t1_final_close_position",
                "t1_weak_close_like",
                "t1_retreat_proxy",
            ]
        ].drop_duplicates(subset=["trade_date", "t1_trade_date", "ts_code"], keep="first")
        frame = events.merge(t1, on=["trade_date", "t1_trade_date", "ts_code"], how="left")
    else:
        frame = events.copy()
        for column in [
            "t1_midday_return",
            "t1_close_vs_vwap",
            "t1_final_close_position",
            "t1_weak_close_like",
            "t1_retreat_proxy",
        ]:
            frame[column] = ""

    signal_parts = frame.apply(_map_lhb_phase13_two_stage_signals, axis=1, result_type="expand")
    signal_parts.columns = [
        "phase13_observe_signal",
        "phase13_observe_reason",
        "phase13_follow_signal",
        "phase13_follow_reason",
        "phase13_reject_signal",
        "phase13_reject_reason",
    ]
    frame = pd.concat([frame, signal_parts], axis=1)
    return frame.reindex(columns=columns).sort_values(
        ["trade_date", "phase13_follow_signal", "phase13_observe_signal", "ts_code"],
        ascending=[True, False, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _map_lhb_phase13_two_stage_signals(row: pd.Series) -> tuple[str, str, str, str, str, str]:
    event_family = str(row.get("event_family") or "")
    prev_streak = _coerce_numeric(row.get("prev_limit_up_streak"), 0.0)
    close_position = _coerce_numeric(row.get("event_close_position"), 0.0)
    high_to_close = _coerce_numeric(row.get("event_high_to_close_drawdown"), -1.0)
    observe = event_family == "limit_relay" and prev_streak >= 1 and close_position >= 0.80 and high_to_close >= -0.03
    observe_signal = "observe_pool" if observe else ""
    observe_reason = "limit_relay_core,strong_close,no_large_high_to_close_drawdown" if observe else ""
    if not observe:
        return "", "", "", "", "", ""

    midday = _coerce_numeric(row.get("t1_midday_return"), -9.0)
    close_vs_vwap = _coerce_numeric(row.get("t1_close_vs_vwap"), -9.0)
    t1_close_position = _coerce_numeric(row.get("t1_final_close_position"), 0.0)
    weak_close = _coerce_bool(row.get("t1_weak_close_like"))
    retreat_proxy = _coerce_bool(row.get("t1_retreat_proxy"))

    reject = retreat_proxy or t1_close_position <= 0.25 or close_vs_vwap <= -0.015
    if reject:
        reasons = []
        if retreat_proxy:
            reasons.append("t1_retreat_proxy")
        if t1_close_position <= 0.25:
            reasons.append("t1_weak_close_position")
        if close_vs_vwap <= -0.015:
            reasons.append("t1_below_vwap")
        return observe_signal, observe_reason, "", "", "t1_retreat_reject", ",".join(reasons)

    follow = midday >= 0 and close_vs_vwap >= 0 and t1_close_position >= 0.75 and not weak_close
    if follow:
        return (
            observe_signal,
            observe_reason,
            "t1_strong_confirm",
            "t1_strong_confirmation,midday_nonnegative,close_above_vwap,strong_close_position",
            "",
            "",
        )
    return observe_signal, observe_reason, "", "", "", ""


def _build_lhb_phase13_two_stage_summary(
    *,
    decision: pd.DataFrame,
    observe_pool: pd.DataFrame,
    follow_pool: pd.DataFrame,
    reject_pool: pd.DataFrame,
) -> pd.DataFrame:
    rows = [
        {"metric": "event_rows", "value": int(len(decision))},
        {"metric": "observe_pool_rows", "value": int(len(observe_pool))},
        {"metric": "follow_pool_rows", "value": int(len(follow_pool))},
        {"metric": "reject_pool_rows", "value": int(len(reject_pool))},
        {"metric": "follow_pool_avg_post_5d_return", "value": pd.to_numeric(follow_pool.get("post_5d_return", pd.Series(dtype="float64")), errors="coerce").mean()},
        {"metric": "follow_pool_avg_post_5d_max_drawdown", "value": pd.to_numeric(follow_pool.get("post_5d_max_drawdown", pd.Series(dtype="float64")), errors="coerce").mean()},
        {"metric": "reject_pool_avg_post_5d_return", "value": pd.to_numeric(reject_pool.get("post_5d_return", pd.Series(dtype="float64")), errors="coerce").mean()},
        {"metric": "reject_pool_avg_post_5d_max_drawdown", "value": pd.to_numeric(reject_pool.get("post_5d_max_drawdown", pd.Series(dtype="float64")), errors="coerce").mean()},
    ]
    return pd.DataFrame(rows, columns=["metric", "value"])


def _lhb_phase13_two_stage_follow_pool_markdown(
    *,
    observe_pool: pd.DataFrame,
    follow_pool: pd.DataFrame,
    reject_pool: pd.DataFrame,
    summary: pd.DataFrame,
) -> str:
    return "\n".join(
        [
            "# LHB Phase 13 Two-Stage Follow Pool v1",
            "",
            "## 1. Rule Intent",
            "Phase 13 separates T-day observation from T+1 follow confirmation. It only outputs pools for human review; it does not automate trading.",
            "",
            "## 2. Summary",
            _table_preview(summary, rows=20),
            "",
            "## 3. Follow Pool",
            _table_preview(follow_pool, rows=40),
            "",
            "## 4. Reject Pool",
            _table_preview(reject_pool, rows=40),
            "",
            "## 5. Observe Pool",
            _table_preview(observe_pool, rows=40),
            "",
        ]
    )


def _build_lhb_phase13b_scored_frame(phase13_decision: pd.DataFrame) -> pd.DataFrame:
    columns = LHB_PHASE13B_SCORED_COLUMNS
    if phase13_decision.empty:
        return pd.DataFrame(columns=columns)
    frame = phase13_decision.copy()
    for column in LHB_PHASE13_SIGNAL_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["ts_code"] = frame["ts_code"].fillna("").astype(str).str.strip().str.upper()
    frame["phase13b_pool"] = frame.apply(_map_lhb_phase13b_pool, axis=1)
    frame["phase13b_score"] = frame.apply(_score_lhb_phase13b_row, axis=1)
    frame = frame[frame["phase13b_pool"].ne("")].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame["phase13b_rank"] = (
        frame.sort_values(["trade_date", "phase13b_pool", "phase13b_score", "ts_code"], ascending=[True, True, False, True], kind="stable")
        .groupby(["trade_date", "phase13b_pool"], sort=False)
        .cumcount()
        + 1
    )
    return frame.reindex(columns=columns).sort_values(
        ["trade_date", "phase13b_pool", "phase13b_rank", "ts_code"],
        kind="stable",
    ).reset_index(drop=True)


def _map_lhb_phase13b_pool(row: pd.Series) -> str:
    if _nonempty_lhb_text(row.get("phase13_reject_signal")):
        return "reject_pool"
    if _nonempty_lhb_text(row.get("phase13_follow_signal")):
        return "follow_pool"
    if _nonempty_lhb_text(row.get("phase13_observe_signal")):
        return "observe_pool"
    return ""


def _score_lhb_phase13b_row(row: pd.Series) -> float:
    score = 0.0
    score += min(max(_coerce_numeric(row.get("prev_limit_up_streak"), 0.0), 0.0), 10.0) * 10.0
    score += min(max(_coerce_numeric(row.get("event_close_position"), 0.0), 0.0), 1.0) * 25.0
    score += min(max(_coerce_numeric(row.get("amount_vs_20d"), 0.0), 0.0), 8.0) * 4.0
    score += min(max(_coerce_numeric(row.get("lhb_net_amount"), 0.0) / 100000000.0, -5.0), 10.0) * 2.0
    score += min(max(_coerce_numeric(row.get("t1_midday_return"), 0.0), -0.10), 0.20) * 100.0
    score += min(max(_coerce_numeric(row.get("t1_close_vs_vwap"), 0.0), -0.05), 0.10) * 120.0
    score += min(max(_coerce_numeric(row.get("t1_final_close_position"), 0.0), 0.0), 1.0) * 25.0
    if _nonempty_lhb_text(row.get("phase13_follow_signal")):
        score += 30.0
    if _nonempty_lhb_text(row.get("phase13_reject_signal")):
        score -= 80.0
    return float(score)


def _nonempty_lhb_text(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    text = str(value).strip()
    return bool(text) and text.lower() != "nan"


def _build_lhb_phase13b_selected_topn(
    *,
    scored: pd.DataFrame,
    top_n_values: list[int] | tuple[int, ...],
) -> pd.DataFrame:
    if scored.empty:
        return pd.DataFrame(columns=["pool_mode", "top_n", *LHB_PHASE13B_SCORED_COLUMNS])
    rows: list[pd.DataFrame] = []
    for pool_mode in ["observe_pool", "follow_pool", "reject_pool"]:
        pool = scored[scored["phase13b_pool"].eq(pool_mode)].copy()
        if pool.empty:
            continue
        for top_n in top_n_values:
            selected = pool[pool["phase13b_rank"].le(int(top_n))].copy()
            selected.insert(0, "top_n", int(top_n))
            selected.insert(0, "pool_mode", pool_mode)
            rows.append(selected)
    if not rows:
        return pd.DataFrame(columns=["pool_mode", "top_n", *LHB_PHASE13B_SCORED_COLUMNS])
    return pd.concat(rows, ignore_index=True)


def _build_lhb_phase13b_summary(selected: pd.DataFrame) -> pd.DataFrame:
    columns = LHB_PHASE13B_SUMMARY_COLUMNS
    if selected.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for (pool_mode, top_n), group in selected.groupby(["pool_mode", "top_n"], sort=True):
        post_5d = pd.to_numeric(group.get("post_5d_return", pd.Series(dtype="float64")), errors="coerce")
        post_dd = pd.to_numeric(group.get("post_5d_max_drawdown", pd.Series(dtype="float64")), errors="coerce")
        daily_counts = group.groupby("trade_date")["ts_code"].count()
        rows.append(
            {
                "pool_mode": pool_mode,
                "top_n": int(top_n),
                "selected_count": int(len(group)),
                "signal_day_count": int(group["trade_date"].nunique()),
                "avg_daily_selected_count": daily_counts.mean(),
                "avg_post_5d_return": post_5d.mean(),
                "win_rate_5d": (post_5d.dropna() > 0).mean() if post_5d.notna().any() else None,
                "avg_post_5d_max_drawdown": post_dd.mean(),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns)


def _lhb_phase13b_topn_filter_markdown(
    *,
    scored: pd.DataFrame,
    selected: pd.DataFrame,
    summary: pd.DataFrame,
) -> str:
    return "\n".join(
        [
            "# LHB Phase 13B TopN Filter v1",
            "",
            "## 1. Rule Intent",
            "Phase 13B compares daily TopN filters on Phase 13 observe/follow/reject pools. Scores use visible T-day and T+1 confirmation features; future returns are only reported for evaluation.",
            "",
            "## 2. Summary",
            _table_preview(summary, rows=30),
            "",
            "## 3. Selected Preview",
            _table_preview(selected, rows=40),
            "",
            "## 4. Scored Preview",
            _table_preview(scored, rows=40),
            "",
        ]
    )


def _build_lhb_shortline_rule_registry(
    *,
    follow_combo: pd.DataFrame,
    exit_combo: pd.DataFrame,
    rule_version: str,
    min_sample_count: int,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for idx, record in enumerate(follow_combo.fillna("").to_dict("records"), start=1):
        recommendation, confidence, reason = _calibrate_lhb_follow_rule(record, min_sample_count=min_sample_count)
        rows.append(
            {
                "rule_id": f"LHB-FOLLOW-{idx:03d}",
                "rule_scope": "follow",
                "lhb_shortline_rule_version": rule_version,
                "rule_recommendation": recommendation,
                "lhb_shortline_rule_confidence": confidence,
                "lhb_shortline_rule_sample_count": int(_coerce_numeric(record.get("sample_count"), 0)),
                "calibration_reason": reason,
                "watch_group": record.get("watch_group", ""),
                "lhb_behavior_type": record.get("lhb_behavior_type", ""),
                "event_structure": record.get("event_structure", ""),
                "entry_window_v2": record.get("entry_window_v2", ""),
                "mainline_flag": record.get("mainline_flag", ""),
                "short_market_state": record.get("short_market_state", ""),
                "exit_signal": "",
                "exit_reason": "",
                "avg_future_5d_return": _coerce_numeric(record.get("avg_future_5d_return")),
                "win_rate_5d": _coerce_numeric(record.get("win_rate_5d")),
                "avg_future_5d_max_drawdown": _coerce_numeric(record.get("avg_future_5d_max_drawdown")),
                "a_kill_rate_5d": _coerce_numeric(record.get("a_kill_rate_5d")),
                "exit_hit_rate": "",
            }
        )
    for idx, record in enumerate(exit_combo.fillna("").to_dict("records"), start=1):
        recommendation, confidence, reason = _calibrate_lhb_exit_rule(record, min_sample_count=min_sample_count)
        rows.append(
            {
                "rule_id": f"LHB-EXIT-{idx:03d}",
                "rule_scope": "exit",
                "lhb_shortline_rule_version": rule_version,
                "rule_recommendation": recommendation,
                "lhb_shortline_rule_confidence": confidence,
                "lhb_shortline_rule_sample_count": int(_coerce_numeric(record.get("sample_count"), 0)),
                "calibration_reason": reason,
                "watch_group": "",
                "lhb_behavior_type": "",
                "event_structure": "",
                "entry_window_v2": "",
                "mainline_flag": "",
                "short_market_state": "",
                "exit_signal": record.get("exit_signal", ""),
                "exit_reason": record.get("exit_reason", ""),
                "avg_future_5d_return": _coerce_numeric(record.get("avg_future_5d_return")),
                "win_rate_5d": _coerce_numeric(record.get("win_rate_5d")),
                "avg_future_5d_max_drawdown": _coerce_numeric(record.get("avg_future_5d_max_drawdown")),
                "a_kill_rate_5d": "",
                "exit_hit_rate": _coerce_numeric(record.get("exit_hit_rate")),
            }
        )
    return pd.DataFrame(rows).reindex(columns=LHB_SHORTLINE_RULE_REGISTRY_COLUMNS)


def _calibrate_lhb_follow_rule(record: dict[str, Any], *, min_sample_count: int) -> tuple[str, str, str]:
    sample_count = int(_coerce_numeric(record.get("sample_count"), 0))
    avg_5d = _coerce_numeric(record.get("avg_future_5d_return"), 0.0)
    win_5d = _coerce_numeric(record.get("win_rate_5d"), 0.0)
    drawdown = _coerce_numeric(record.get("avg_future_5d_max_drawdown"), 0.0)
    a_kill_rate = _coerce_numeric(record.get("a_kill_rate_5d"), 0.0)
    watch_group = str(record.get("watch_group") or "")
    if sample_count < min_sample_count:
        return "review_sparse", "low", "sample_below_threshold"
    if avg_5d >= 0.08 and win_5d >= 0.55 and drawdown >= -0.10 and a_kill_rate <= 0.10:
        recommendation = "keep_high_elasticity_watch" if watch_group == "high_elasticity_watch" else "keep_follow_watch"
        confidence = "high" if avg_5d >= 0.15 and win_5d >= 0.70 else "medium"
        return recommendation, confidence, "positive_follow_effectiveness"
    if avg_5d < 0 or win_5d < 0.45 or drawdown < -0.15 or a_kill_rate > 0.20:
        return "downgrade_to_watch_only", "medium", "weak_follow_effectiveness"
    return "review_watch_only", "medium", "mixed_follow_effectiveness"


def _calibrate_lhb_exit_rule(record: dict[str, Any], *, min_sample_count: int) -> tuple[str, str, str]:
    sample_count = int(_coerce_numeric(record.get("sample_count"), 0))
    avg_5d = _coerce_numeric(record.get("avg_future_5d_return"), 0.0)
    win_5d = _coerce_numeric(record.get("win_rate_5d"), 0.0)
    exit_hit_rate = _coerce_numeric(record.get("exit_hit_rate"), 0.0)
    exit_signal = str(record.get("exit_signal") or "")
    if sample_count < min_sample_count:
        return "review_sparse", "low", "sample_below_threshold"
    if avg_5d > 0.03 or win_5d >= 0.45:
        recommendation = "downgrade_to_reduce_watch" if exit_signal == "hard_exit" else "review_exit_rule"
        return recommendation, "medium", "positive_after_exit"
    if exit_hit_rate >= 0.70 and avg_5d < 0:
        recommendation = "keep_hard_exit" if exit_signal == "hard_exit" else "keep_reduce_watch"
        confidence = "high" if exit_hit_rate >= 0.85 and win_5d <= 0.20 else "medium"
        return recommendation, confidence, "negative_after_exit_confirmed"
    if exit_hit_rate < 0.55:
        return "downgrade_to_observe", "medium", "weak_exit_hit_rate"
    return "review_exit_rule", "medium", "mixed_exit_effectiveness"


def _coerce_numeric(value: Any, default: float | None = None) -> float:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return 0.0 if default is None else float(default)
    return float(number)


def _lhb_shortline_rule_calibration_markdown(
    *,
    rule_registry: pd.DataFrame,
    rule_version: str,
    min_sample_count: int,
) -> str:
    follow = rule_registry[rule_registry["rule_scope"].eq("follow")]
    exit_rules = rule_registry[rule_registry["rule_scope"].eq("exit")]
    return "\n".join(
        [
            "# LHB Shortline Rule Calibration v1",
            "",
            f"- Rule version: {rule_version}",
            f"- Min sample count: {min_sample_count}",
            "",
            "## 1. 说明",
            "本报告基于 Phase 6 复盘证据生成规则建议；future 字段只用于校准，不进入当日入池判断。",
            "",
            "## 2. Follow / Elasticity Rules",
            _table_preview(follow, rows=30),
            "",
            "## 3. Exit Rules",
            _table_preview(exit_rules, rows=30),
            "",
        ]
    )


def _build_lhb_shortline_manual_review_frame(
    *,
    daily_watchlist: pd.DataFrame,
    effectiveness_detail: pd.DataFrame,
    manual_review: pd.DataFrame,
    trade_date: str,
) -> pd.DataFrame:
    if daily_watchlist.empty:
        return pd.DataFrame(columns=LHB_SHORTLINE_MANUAL_REVIEW_COLUMNS)
    frame = daily_watchlist.copy()
    frame = _normalize_lhb_review_key_columns(frame)
    frame = frame[frame["trade_date"].eq(str(trade_date))].copy()
    if frame.empty:
        return pd.DataFrame(columns=LHB_SHORTLINE_MANUAL_REVIEW_COLUMNS)

    outcome = _normalize_lhb_manual_outcome_frame(effectiveness_detail)
    if not outcome.empty:
        frame = frame.merge(outcome, on=["trade_date", "ts_code"], how="left", suffixes=("", "_outcome"))

    manual = _normalize_lhb_manual_review_input(manual_review)
    if not manual.empty:
        frame = frame.merge(manual, on=["trade_date", "ts_code"], how="left", suffixes=("", "_manual"))
    else:
        for column in [
            "manual_follow_decision",
            "manual_exit_decision",
            "manual_decision_reason",
            "next_day_confirmation_review",
            "post_review_label",
            "operator_notes",
        ]:
            frame[column] = ""

    for column in LHB_SHORTLINE_MANUAL_REVIEW_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    for column in ["a_kill_within_5d", "second_wave_success"]:
        frame[column] = frame[column].map(_coerce_lhb_bool).astype(object)
    return frame.reindex(columns=LHB_SHORTLINE_MANUAL_REVIEW_COLUMNS).fillna("").reset_index(drop=True)


def _normalize_lhb_review_key_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in ["trade_date", "ts_code"]:
        if column not in result.columns:
            result[column] = ""
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    result["ts_code"] = result["ts_code"].fillna("").astype(str).str.strip().str.upper()
    return result


def _normalize_lhb_manual_outcome_frame(effectiveness_detail: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "trade_date",
        "ts_code",
        "future_1d_return",
        "future_3d_return",
        "future_5d_return",
        "a_kill_within_5d",
        "second_wave_success",
    ]
    if effectiveness_detail.empty:
        return pd.DataFrame(columns=columns)
    frame = _normalize_lhb_review_key_columns(effectiveness_detail)
    for column in columns:
        if column not in frame.columns:
            frame[column] = ""
    for column in ["future_1d_return", "future_3d_return", "future_5d_return"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.loc[:, columns].drop_duplicates(subset=["trade_date", "ts_code"], keep="last")


def _normalize_lhb_manual_review_input(manual_review: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "trade_date",
        "ts_code",
        "manual_follow_decision",
        "manual_exit_decision",
        "manual_decision_reason",
        "next_day_confirmation_review",
        "post_review_label",
        "operator_notes",
    ]
    if manual_review.empty:
        return pd.DataFrame(columns=columns)
    frame = _normalize_lhb_review_key_columns(manual_review)
    for column in columns:
        if column not in frame.columns:
            frame[column] = ""
    return frame.loc[:, columns].drop_duplicates(subset=["trade_date", "ts_code"], keep="last")


def _build_lhb_shortline_manual_review_summary(review: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {"metric": "total_rows", "value": int(len(review))},
        {"metric": "manual_follow_focus_count", "value": _count_lhb_review_value(review, "manual_follow_decision", "focus")},
        {"metric": "manual_follow_skip_count", "value": _count_lhb_review_value(review, "manual_follow_decision", "skip")},
        {"metric": "manual_exit_accept_count", "value": _count_lhb_review_value(review, "manual_exit_decision", "accept_exit")},
        {"metric": "manual_exit_reject_count", "value": _count_lhb_review_value(review, "manual_exit_decision", "reject_exit")},
        {"metric": "exit_hit_label_count", "value": _count_lhb_review_value(review, "post_review_label", "exit_hit")},
        {"metric": "system_hit_label_count", "value": _count_lhb_review_value(review, "post_review_label", "system_hit")},
        {"metric": "system_miss_label_count", "value": _count_lhb_review_value(review, "post_review_label", "system_miss")},
    ]
    return pd.DataFrame(rows)


def _count_lhb_review_value(frame: pd.DataFrame, column: str, value: str) -> int:
    if frame.empty or column not in frame.columns:
        return 0
    return int(frame[column].fillna("").astype(str).str.strip().eq(value).sum())


def _lhb_shortline_manual_review_markdown(
    *,
    review: pd.DataFrame,
    summary: pd.DataFrame,
    trade_date: str,
) -> str:
    return "\n".join(
        [
            "# LHB Shortline Manual Review v1",
            "",
            f"- Trade date: {trade_date}",
            "- Scope: 人工纸面交易复盘，不自动下单。",
            "",
            "## 1. Summary",
            _table_preview(summary, rows=30),
            "",
            "## 2. Review Rows",
            _table_preview(review, rows=50),
            "",
        ]
    )


def _build_lhb_risk_score_bucket_effectiveness(detail: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "bucket",
        "sample_count",
        "avg_future_3d_return",
        "avg_future_5d_return",
        "avg_future_10d_return",
        "win_rate_3d",
        "win_rate_5d",
        "win_rate_10d",
        "avg_future_5d_max_drawdown",
        "avg_future_10d_max_drawdown",
        "a_kill_failure_count",
        "failed_second_wave_count",
        "second_wave_success_count",
    ]
    if detail.empty:
        return pd.DataFrame(columns=columns)
    frame = detail.copy()
    scores = pd.to_numeric(frame["lhb_risk_score"], errors="coerce").fillna(0.0)
    if scores.nunique() <= 1:
        frame["bucket"] = 1
    else:
        frame["bucket"] = pd.qcut(scores.rank(method="first"), q=min(10, len(frame)), labels=False, duplicates="drop") + 1
    rows = []
    for bucket, group in frame.groupby("bucket", dropna=False):
        rows.append(
            {
                "bucket": int(bucket),
                "sample_count": int(len(group)),
                **_future_stats(group),
                "a_kill_failure_count": int((group["verified_case_type"] == "a_kill_failure").sum()),
                "failed_second_wave_count": int((group["verified_case_type"] == "failed_second_wave").sum()),
                "second_wave_success_count": int(((group["verified_case_type"] == "second_wave") & (group["success_or_failure"] == "success")).sum()),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values("bucket").reset_index(drop=True)


def _build_lhb_risk_failure_type_cross(detail: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "verified_case_type",
        "success_or_failure",
        "lhb_risk_level",
        "sample_count",
        "avg_lhb_risk_score",
        "avg_lhb_net_buy_amount",
        "avg_institution_net_buy",
        "avg_lhb_one_day_pump_risk",
        "avg_future_5d_return",
        "avg_future_10d_return",
        "avg_future_10d_max_drawdown",
    ]
    if detail.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for (case_type, success, level), group in detail.groupby(["verified_case_type", "success_or_failure", "lhb_risk_level"], dropna=False):
        rows.append(
            {
                "verified_case_type": case_type,
                "success_or_failure": success,
                "lhb_risk_level": level,
                "sample_count": int(len(group)),
                "avg_lhb_risk_score": pd.to_numeric(group["lhb_risk_score"], errors="coerce").mean(),
                "avg_lhb_net_buy_amount": pd.to_numeric(group["lhb_net_buy_amount_event"], errors="coerce").mean(),
                "avg_institution_net_buy": pd.to_numeric(group["institution_net_buy_event"], errors="coerce").mean(),
                "avg_lhb_one_day_pump_risk": pd.to_numeric(group["lhb_one_day_pump_risk"], errors="coerce").mean(),
                "avg_future_5d_return": pd.to_numeric(group["future_5d_return"], errors="coerce").mean(),
                "avg_future_10d_return": pd.to_numeric(group["future_10d_return"], errors="coerce").mean(),
                "avg_future_10d_max_drawdown": pd.to_numeric(group["future_10d_max_drawdown"], errors="coerce").mean(),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(["verified_case_type", "success_or_failure", "lhb_risk_level"]).reset_index(drop=True)


def _build_lhb_dragon_risk_cross(detail: pd.DataFrame, optional_diagnostics: dict[str, pd.DataFrame]) -> pd.DataFrame:
    columns = [
        "lhb_risk_level",
        "dragon_risk_level",
        "entry_window",
        "entry_window_v2",
        "verified_case_type",
        "success_or_failure",
        "sample_count",
        "avg_future_5d_return",
        "avg_future_10d_return",
        "avg_future_10d_max_drawdown",
    ]
    if detail.empty or not optional_diagnostics:
        return pd.DataFrame(columns=columns)
    enriched = detail.copy()
    enriched["dragon_risk_level"] = ""
    enriched["entry_window"] = ""
    enriched["entry_window_v2"] = ""
    for _, diagnostics in optional_diagnostics.items():
        if diagnostics.empty:
            continue
        diag = diagnostics.copy()
        date_col = "trade_date" if "trade_date" in diag.columns else ("event_date" if "event_date" in diag.columns else None)
        code_col = "ts_code" if "ts_code" in diag.columns else ("asset_id" if "asset_id" in diag.columns else None)
        if not date_col or not code_col:
            continue
        diag[date_col] = pd.to_datetime(diag[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
        diag[code_col] = diag[code_col].fillna("").astype(str).str.upper()
        merge_cols = [code_col, date_col]
        use_cols = merge_cols + [col for col in ["dragon_risk_score", "entry_window", "entry_window_v2"] if col in diag.columns]
        merged = enriched.merge(
            diag[use_cols].drop_duplicates(subset=merge_cols),
            left_on=["ts_code", "event_date"],
            right_on=merge_cols,
            how="left",
            suffixes=("", "_diag"),
        )
        if "dragon_risk_score" in merged.columns:
            mask = enriched["dragon_risk_level"].eq("") & merged["dragon_risk_score"].notna()
            enriched.loc[mask, "dragon_risk_level"] = merged.loc[mask, "dragon_risk_score"].map(_risk_level)
        for col in ["entry_window", "entry_window_v2"]:
            diag_col = f"{col}_diag" if f"{col}_diag" in merged.columns else col
            if diag_col in merged.columns:
                mask = enriched[col].eq("") & merged[diag_col].notna()
                enriched.loc[mask, col] = merged.loc[mask, diag_col].astype(str)
    enriched = enriched[enriched["dragon_risk_level"].astype(str) != ""]
    if enriched.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for keys, group in enriched.groupby(["lhb_risk_level", "dragon_risk_level", "entry_window", "entry_window_v2", "verified_case_type", "success_or_failure"], dropna=False):
        lhb_level, dragon_level, entry_window, entry_window_v2, case_type, success = keys
        rows.append(
            {
                "lhb_risk_level": lhb_level,
                "dragon_risk_level": dragon_level,
                "entry_window": entry_window,
                "entry_window_v2": entry_window_v2,
                "verified_case_type": case_type,
                "success_or_failure": success,
                "sample_count": int(len(group)),
                "avg_future_5d_return": pd.to_numeric(group["future_5d_return"], errors="coerce").mean(),
                "avg_future_10d_return": pd.to_numeric(group["future_10d_return"], errors="coerce").mean(),
                "avg_future_10d_max_drawdown": pd.to_numeric(group["future_10d_max_drawdown"], errors="coerce").mean(),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns)


def _build_lhb_coverage_gap_recommendations(detail: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "case_id",
        "ts_code",
        "stock_name",
        "case_year",
        "verified_case_type",
        "success_or_failure",
        "event_date",
        "has_lhb",
        "missing_reason",
        "priority_for_lhb_backfill",
        "suggested_lhb_query_start_date",
        "suggested_lhb_query_end_date",
        "notes",
    ]
    if detail.empty:
        return pd.DataFrame(columns=columns)
    priority_map = {
        "a_kill_failure": 1,
        "failed_second_wave": 2,
        "failed_reversal": 3,
        "high_open_low_close_failure": 4,
        "one_day_pump": 5,
        "second_wave": 6,
    }
    rows = []
    for record in detail.fillna("").to_dict("records"):
        has_lhb = bool(record.get("lhb_on_event_date") or record.get("lhb_before_3d") or record.get("lhb_after_3d"))
        case_type = str(record.get("verified_case_type") or record.get("case_type") or "")
        event_date = str(record.get("event_date") or "")
        if not event_date:
            continue
        rows.append(
            {
                "case_id": record.get("case_id"),
                "ts_code": record.get("ts_code"),
                "stock_name": record.get("stock_name"),
                "case_year": record.get("case_year"),
                "verified_case_type": case_type,
                "success_or_failure": record.get("success_or_failure"),
                "event_date": event_date,
                "has_lhb": has_lhb,
                "missing_reason": "" if has_lhb else "no_lhb_within_event_window",
                "priority_for_lhb_backfill": priority_map.get(case_type, 9),
                "suggested_lhb_query_start_date": _shift_date(event_date, -5),
                "suggested_lhb_query_end_date": _shift_date(event_date, 5),
                "notes": "already_covered" if has_lhb else "expand AkShare/Tushare LHB range around this event",
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(["has_lhb", "priority_for_lhb_backfill", "case_year"]).reset_index(drop=True)


def _build_lhb_coverage_expansion_plan(coverage_gaps: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "plan_id",
        "case_id",
        "ts_code",
        "stock_name",
        "case_year",
        "verified_case_type",
        "success_or_failure",
        "event_date",
        "priority_for_lhb_backfill",
        "suggested_lhb_query_start_date",
        "suggested_lhb_query_end_date",
        "query_window_days_before",
        "query_window_days_after",
        "reason",
        "expected_value",
        "status",
        "notes",
    ]
    if coverage_gaps.empty:
        return pd.DataFrame(columns=columns)
    priority_map = {
        "a_kill_failure": 1,
        "failed_second_wave": 2,
        "failed_reversal": 3,
        "high_open_low_close_failure": 4,
        "one_day_pump": 5,
        "second_wave": 6,
    }
    frame = coverage_gaps.copy()
    if "has_lhb" in frame.columns:
        has_lhb = frame["has_lhb"].map(_coerce_bool)
        frame = frame[~has_lhb].copy()
    rows = []
    for record in frame.fillna("").to_dict("records"):
        case_type = str(record.get("verified_case_type") or "")
        success = str(record.get("success_or_failure") or "")
        if case_type == "second_wave" and success != "success":
            priority = 8
        else:
            priority = priority_map.get(case_type, 9)
        event_date = _format_date(record.get("event_date"))
        if not event_date:
            continue
        after_days = 10 if case_type in {"a_kill_failure", "failed_second_wave"} else 5
        before_days = 5
        rows.append(
            {
                "case_id": record.get("case_id"),
                "ts_code": str(record.get("ts_code") or "").upper(),
                "stock_name": record.get("stock_name"),
                "case_year": record.get("case_year"),
                "verified_case_type": case_type,
                "success_or_failure": success,
                "event_date": event_date,
                "priority_for_lhb_backfill": priority,
                "suggested_lhb_query_start_date": _shift_date(event_date, -before_days),
                "suggested_lhb_query_end_date": _shift_date(event_date, after_days),
                "query_window_days_before": before_days,
                "query_window_days_after": after_days,
                "reason": _lhb_expansion_reason(case_type, success),
                "expected_value": _lhb_expansion_expected_value(case_type, success),
                "status": "pending",
                "notes": record.get("notes") or "LHB coverage gap; planned for small-batch AkShare/Tushare backfill",
            }
        )
    if not rows:
        return pd.DataFrame(columns=columns)
    return (
        pd.DataFrame(rows)
        .reindex(columns=columns)
        .sort_values(["priority_for_lhb_backfill", "case_year", "event_date", "ts_code"])
        .reset_index(drop=True)
        .assign(plan_id=lambda df: [f"lhb_plan_{idx:04d}" for idx in range(1, len(df) + 1)])
        .reindex(columns=columns)
    )


def _build_lhb_coverage_expansion_summary(coverage_gaps: pd.DataFrame, plan: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "verified_case_type",
        "success_or_failure",
        "case_year",
        "priority_for_lhb_backfill",
        "case_count",
        "event_count",
        "avg_query_window_days",
        "expected_lhb_rows",
        "current_lhb_matched_count",
        "missing_lhb_count",
    ]
    if plan.empty:
        return pd.DataFrame(columns=columns)
    frame = plan.copy()
    frame["query_window_days"] = pd.to_numeric(frame["query_window_days_before"], errors="coerce").fillna(0) + pd.to_numeric(frame["query_window_days_after"], errors="coerce").fillna(0) + 1
    matched_lookup = pd.DataFrame()
    if not coverage_gaps.empty and {"verified_case_type", "success_or_failure", "case_year", "priority_for_lhb_backfill", "has_lhb"}.issubset(coverage_gaps.columns):
        matched_lookup = coverage_gaps.copy()
        matched_lookup["has_lhb"] = matched_lookup["has_lhb"].map(_coerce_bool)
        matched_lookup["priority_for_lhb_backfill"] = matched_lookup.apply(
            lambda row: _lhb_case_priority(row.get("verified_case_type"), row.get("success_or_failure")),
            axis=1,
        )
    rows = []
    keys = ["verified_case_type", "success_or_failure", "case_year", "priority_for_lhb_backfill"]
    for key_values, group in frame.groupby(keys, dropna=False):
        key_dict = dict(zip(keys, key_values))
        current_matched = 0
        if not matched_lookup.empty:
            mask = pd.Series(True, index=matched_lookup.index)
            for col, value in key_dict.items():
                mask &= matched_lookup[col].astype(str).eq(str(value))
            current_matched = int(matched_lookup.loc[mask, "has_lhb"].sum())
        rows.append(
            {
                **key_dict,
                "case_count": int(group["case_id"].nunique()),
                "event_count": int(len(group)),
                "avg_query_window_days": float(group["query_window_days"].mean()),
                "expected_lhb_rows": int(group["query_window_days"].sum()),
                "current_lhb_matched_count": current_matched,
                "missing_lhb_count": int(len(group)),
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(["priority_for_lhb_backfill", "case_year"]).reset_index(drop=True)


def _lhb_coverage_expansion_commands(plan: pd.DataFrame) -> str:
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        "# LHB coverage expansion command suggestions.",
        "# Commands are intentionally commented out: review the windows before running.",
        "# TODO: do not run full-market LHB backfill from this script.",
        "",
        "# 1. Small sample: Top 5 priority cases, event window around +/-5 trading days.",
    ]
    lines.extend(_commented_lhb_import_commands(plan.head(5)))
    high = plan[plan["verified_case_type"].isin(["a_kill_failure", "failed_second_wave"])] if not plan.empty else plan
    lines.extend(["", "# 2. Medium sample: all a_kill_failure / failed_second_wave cases, event window +5 to +10 days."])
    lines.extend(_commented_lhb_import_commands(high))
    high_priority = plan[pd.to_numeric(plan["priority_for_lhb_backfill"], errors="coerce").fillna(99) <= 5] if not plan.empty else plan
    lines.extend(["", "# 3. Extended sample: all high-priority gap cases."])
    lines.extend(_commented_lhb_import_commands(high_priority))
    lines.append("")
    return "\n".join(lines)


def _commented_lhb_import_commands(plan: pd.DataFrame) -> list[str]:
    if plan.empty:
        return ["# No matching cases in this layer."]
    start = pd.to_datetime(plan["suggested_lhb_query_start_date"], errors="coerce").min()
    end = pd.to_datetime(plan["suggested_lhb_query_end_date"], errors="coerce").max()
    codes = ",".join(sorted({str(code).upper() for code in plan["ts_code"].dropna() if str(code).strip()}))
    if pd.isna(start) or pd.isna(end) or not codes:
        return ["# Missing date/code fields; inspect lhb_coverage_expansion_plan_2024_2026.csv first."]
    return [
        "# stock-research lhb-sample-import \\",
        f"#   --provider akshare --start-date {start.strftime('%Y-%m-%d')} --end-date {end.strftime('%Y-%m-%d')} \\",
        f"#   --ts-codes {codes} \\",
        "#   --output-dir outputs/research",
    ]


def _build_failure_event_rule_refinement_audit(curated: pd.DataFrame, snapshot: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "case_id",
        "ts_code",
        "stock_name",
        "current_verified_case_type",
        "event_date",
        "pre_3d_return",
        "pre_5d_return",
        "post_1d_return",
        "post_3d_return",
        "post_5d_return",
        "post_10d_return",
        "post_5d_max_drawdown",
        "post_10d_max_drawdown",
        "amount_vs_20d",
        "high_to_close_drawdown",
        "close_position_in_day",
        "is_limit_up_day",
        "is_break_limit_event",
        "is_reversal_event",
        "is_second_wave_event",
        "is_a_kill_event",
        "suggested_refined_case_type",
        "refinement_reason",
        "confidence",
    ]
    if curated.empty or snapshot.empty:
        return pd.DataFrame(columns=columns)
    focus_types = {"failed_reversal", "high_open_low_close_failure", "one_day_pump", "failed_second_wave", "a_kill_failure"}
    cases = curated.copy()
    cases["case_id"] = cases["case_id"].astype(str)
    current_type_col = "verified_case_type" if "verified_case_type" in cases.columns else "case_type"
    events = snapshot.copy()
    events["case_id"] = events["case_id"].astype(str)
    if "relative_day" in events.columns:
        day0 = events[pd.to_numeric(events["relative_day"], errors="coerce").fillna(999).eq(0)].copy()
        if not day0.empty:
            events = day0
    merged = events.merge(
        cases[["case_id", current_type_col]].rename(columns={current_type_col: "current_verified_case_type"}),
        on="case_id",
        how="left",
    )
    merged["current_verified_case_type"] = merged["current_verified_case_type"].fillna("")
    merged = merged[merged["current_verified_case_type"].isin(focus_types) | merged["is_a_kill_event"].map(_coerce_bool) | merged["is_reversal_event"].map(_coerce_bool) | merged["is_second_wave_event"].map(_coerce_bool)]
    rows = []
    for record in merged.fillna("").to_dict("records"):
        suggested, reason, confidence = _suggest_failure_case_type(record)
        rows.append(
            {
                "case_id": record.get("case_id"),
                "ts_code": str(record.get("ts_code") or "").upper(),
                "stock_name": record.get("stock_name"),
                "current_verified_case_type": record.get("current_verified_case_type"),
                "event_date": _format_date(record.get("event_date")) or _format_date(record.get("trade_date")),
                "pre_3d_return": _num(record.get("pre_3d_return")),
                "pre_5d_return": _num(record.get("pre_5d_return")),
                "post_1d_return": _num(record.get("future_1d_return")),
                "post_3d_return": _num(record.get("future_3d_return")),
                "post_5d_return": _num(record.get("future_5d_return")),
                "post_10d_return": _num(record.get("future_10d_return")),
                "post_5d_max_drawdown": _num(record.get("future_5d_max_drawdown")),
                "post_10d_max_drawdown": _num(record.get("future_10d_max_drawdown")),
                "amount_vs_20d": _num(record.get("amount_vs_20d")),
                "high_to_close_drawdown": _num(record.get("high_to_close_drawdown")),
                "close_position_in_day": _num(record.get("close_position_in_day")),
                "is_limit_up_day": _coerce_bool(record.get("is_limit_up_day")),
                "is_break_limit_event": _coerce_bool(record.get("is_break_limit_event")),
                "is_reversal_event": _coerce_bool(record.get("is_reversal_event")),
                "is_second_wave_event": _coerce_bool(record.get("is_second_wave_event")),
                "is_a_kill_event": _coerce_bool(record.get("is_a_kill_event")),
                "suggested_refined_case_type": suggested,
                "refinement_reason": reason,
                "confidence": confidence,
            }
        )
    return pd.DataFrame(rows).reindex(columns=columns)


def _build_failure_event_rule_refinement_suggestions(curated: pd.DataFrame, audit: pd.DataFrame) -> pd.DataFrame:
    columns = ["case_type", "current_sample_count", "suggested_rule", "required_fields", "expected_improvement", "risk_of_false_positive", "notes"]
    current = curated["verified_case_type"].value_counts().to_dict() if "verified_case_type" in curated.columns else {}
    suggestions = [
        {
            "case_type": "failed_reversal",
            "suggested_rule": "断板后 1-5 日出现反包/强修复，但 1-3 日内无法延续，跌破反包日低点或 post_3d/post_5d 转负。",
            "required_fields": "is_reversal_event, post_3d_return, post_5d_return, high_to_close_drawdown, close_position_in_day",
            "expected_improvement": "把成功反包与假反包拆开，补足 failed_reversal 样本。",
            "risk_of_false_positive": "强趋势里的正常分歧可能被误判为失败反包。",
            "notes": "需要结合后续是否再创新高做二次校验。",
        },
        {
            "case_type": "high_open_low_close_failure",
            "suggested_rule": "事件日冲高回落明显，close_position_in_day 偏低且 high_to_close_drawdown 较高，后续 3/5 日继续走弱。",
            "required_fields": "high_to_close_drawdown, close_position_in_day, post_3d_return, post_5d_return, amount_vs_20d",
            "expected_improvement": "识别高位爆量分歧、准天地板和大面样本。",
            "risk_of_false_positive": "低位洗盘或指数拖累的长上影可能被误判。",
            "notes": "与 one_day_pump 的边界在于前期是否已有高度/人气确认。",
        },
        {
            "case_type": "one_day_pump",
            "suggested_rule": "单日大涨或涨停伴随 amount_vs_20d 放大，但无连板/反包/二波，次日或 3 日内明显回落。",
            "required_fields": "is_limit_up_day, limit_up_count_before_event, amount_vs_20d, post_1d_return, post_3d_return",
            "expected_improvement": "把低持续性脉冲从弱转强/跟风里拆出来。",
            "risk_of_false_positive": "首板试错后再次走强的样本可能被提前归为一日游。",
            "notes": "需要排除后续二波或连续趋势延续。",
        },
        {
            "case_type": "failed_second_wave_vs_a_kill_failure",
            "suggested_rule": "failed_second_wave 需要先有二波尝试/突破失败；a_kill_failure 更强调高人气确认后破位且无有效反包。",
            "required_fields": "is_second_wave_event, is_a_kill_event, post_5d_return, post_10d_return, post_10d_max_drawdown",
            "expected_improvement": "减少二波失败与纯 A 杀互相污染。",
            "risk_of_false_positive": "先失败后二次修复的 mixed 案例需要人工备注。",
            "notes": "若后续再突破前高，应改为 mixed 或 failed_then_recovered。",
        },
        {
            "case_type": "high_open_low_close_failure_vs_one_day_pump",
            "suggested_rule": "HOCL 侧重已有高度后的高位冲高回落；one_day_pump 侧重低持续性的单日脉冲。",
            "required_fields": "pre_5d_return, limit_up_count_before_event, high_to_close_drawdown, post_3d_return",
            "expected_improvement": "让失败类型更贴近市场语言。",
            "risk_of_false_positive": "缺少分钟线时无法确认早盘高开/冲高路径。",
            "notes": "后续 5min 承接特征可显著提高边界质量。",
        },
    ]
    for item in suggestions:
        item["current_sample_count"] = int(current.get(item["case_type"], 0))
    return pd.DataFrame(suggestions).reindex(columns=columns)


def _suggest_failure_case_type(record: dict[str, Any]) -> tuple[str, str, float]:
    current = str(record.get("current_verified_case_type") or "")
    post_3d = _num(record.get("future_3d_return")) or 0.0
    post_5d = _num(record.get("future_5d_return")) or 0.0
    post_10d = _num(record.get("future_10d_return")) or 0.0
    dd_10d = _num(record.get("future_10d_max_drawdown")) or 0.0
    high_to_close = _num(record.get("high_to_close_drawdown")) or 0.0
    close_pos = _num(record.get("close_position_in_day"))
    limit_count = _num(record.get("limit_up_count_before_event")) or 0.0
    if _coerce_bool(record.get("is_a_kill_event")) or post_10d <= -0.15 or dd_10d <= -0.18:
        return "a_kill_failure", "破位后 10 日收益/回撤显示 A 杀风险，且无有效修复确认。", 0.85
    if _coerce_bool(record.get("is_reversal_event")) and (post_3d < 0 or post_5d <= -0.05):
        return "failed_reversal", "反包尝试后 3-5 日无法延续，符合失败反包。", 0.80
    if _coerce_bool(record.get("is_second_wave_event")) and (post_5d <= -0.08 or dd_10d <= -0.12):
        return "failed_second_wave", "二波尝试后收益转弱且回撤扩大。", 0.78
    if high_to_close >= 0.08 and (close_pos is None or close_pos <= 0.35) and post_3d < 0:
        return "high_open_low_close_failure", "事件日冲高回落且收盘位置偏低，后续走弱。", 0.76
    if _coerce_bool(record.get("is_limit_up_day")) and limit_count <= 1 and post_3d <= -0.06:
        return "one_day_pump", "单日涨停/大涨后 3 日回落且缺少连板延续。", 0.72
    return current or "unknown", "现有日线字段不足以重分类，保留原标签。", 0.50


def _lhb_coverage_failure_plan_markdown(
    *,
    plan: pd.DataFrame,
    summary: pd.DataFrame,
    audit: pd.DataFrame,
    suggestions: pd.DataFrame,
    warnings: list[str],
) -> str:
    high_priority = int((pd.to_numeric(plan.get("priority_for_lhb_backfill", pd.Series(dtype=float)), errors="coerce") <= 3).sum()) if not plan.empty else 0
    return "\n".join(
        [
            "# LHB Coverage Expansion & Failure Rule Refinement Plan v1",
            "",
            "## 1. 背景",
            "LHB 风险诊断已能解释部分 A杀、失败二波和高位分歧，但覆盖和失败事件标签仍是短板。本轮只生成补数计划和规则审计，不接策略打分、不做组合回测、不接实盘。",
            "",
            "## 2. LHB 覆盖缺口",
            f"覆盖扩展计划共 {len(plan)} 条，其中高优先级（priority <= 3）{high_priority} 条。",
            _table_preview(summary, rows=20),
            "",
            "## 3. 覆盖扩展计划",
            "优先级为 a_kill_failure、failed_second_wave、failed_reversal、high_open_low_close_failure、one_day_pump、success second_wave 代表案例。a_kill_failure / failed_second_wave 的事件后窗口扩到 10 日。",
            _table_preview(plan, rows=20),
            "",
            "## 4. AkShare 小批量补数建议",
            "先跑 Top 5 小样本，再跑 a_kill_failure / failed_second_wave 中样本，最后扩展到全部高优先级缺口。脚本只输出注释命令，不自动执行全量补数。",
            "",
            "## 5. 失败事件规则问题",
            "failed_reversal、high_open_low_close_failure、one_day_pump 样本仍偏少，且仅靠日线会混淆假反包、高位冲高回落和单日脉冲。",
            _table_preview(audit, rows=20),
            "",
            "## 6. 规则修正建议",
            _table_preview(suggestions, rows=10),
            "",
            "## 7. 下一步",
            "建议先做 AkShare LHB 高优先级窗口小批量补数，再实现失败事件规则 v2，随后重跑 LHB risk diagnostics；最后再考虑 entry_score v3。",
            "",
            "### Warnings",
            *(warnings or ["无"]),
        ]
    )


def _lhb_case_priority(case_type: Any, success: Any) -> int:
    text = str(case_type or "")
    if text == "a_kill_failure":
        return 1
    if text == "failed_second_wave":
        return 2
    if text == "failed_reversal":
        return 3
    if text == "high_open_low_close_failure":
        return 4
    if text == "one_day_pump":
        return 5
    if text == "second_wave" and str(success or "") == "success":
        return 6
    return 9


def _lhb_expansion_reason(case_type: str, success: str) -> str:
    if case_type == "a_kill_failure":
        return "A杀风险样本需要验证负净买、重复上榜和 pump risk。"
    if case_type == "failed_second_wave":
        return "失败二波需要观察事件后分歧关注和资金撤退。"
    if case_type == "failed_reversal":
        return "失败反包样本稀缺，优先补 LHB 证据。"
    if case_type == "high_open_low_close_failure":
        return "高开低走/冲高回落需要资金分歧证据。"
    if case_type == "one_day_pump":
        return "一日游需要验证事件后资金承接缺失。"
    if case_type == "second_wave" and success == "success":
        return "成功二波作为对照组补充覆盖。"
    return "低覆盖案例补充 LHB 对齐。"


def _lhb_expansion_expected_value(case_type: str, success: str) -> str:
    if case_type in {"a_kill_failure", "failed_second_wave", "failed_reversal"}:
        return "high: improve failure-risk diagnostics"
    if case_type in {"high_open_low_close_failure", "one_day_pump"}:
        return "medium_high: refine sparse failure labels"
    if case_type == "second_wave" and success == "success":
        return "medium: success contrast sample"
    return "low: coverage completeness"


def _future_stats(group: pd.DataFrame) -> dict[str, Any]:
    future_3d = pd.to_numeric(group["future_3d_return"], errors="coerce")
    future_5d = pd.to_numeric(group["future_5d_return"], errors="coerce")
    future_10d = pd.to_numeric(group["future_10d_return"], errors="coerce")
    return {
        "avg_future_3d_return": future_3d.mean(),
        "avg_future_5d_return": future_5d.mean(),
        "avg_future_10d_return": future_10d.mean(),
        "win_rate_3d": (future_3d > 0).mean() if future_3d.notna().any() else None,
        "win_rate_5d": (future_5d > 0).mean() if future_5d.notna().any() else None,
        "win_rate_10d": (future_10d > 0).mean() if future_10d.notna().any() else None,
        "avg_future_5d_max_drawdown": pd.to_numeric(group["future_5d_max_drawdown"], errors="coerce").mean(),
        "avg_future_10d_max_drawdown": pd.to_numeric(group["future_10d_max_drawdown"], errors="coerce").mean(),
    }


def _risk_level(value: Any) -> str:
    score = float(value) if value is not None and not pd.isna(value) else 0.0
    if score >= 0.66:
        return "high"
    if score >= 0.33:
        return "mid"
    return "low"


def _lhb_risk_feature_markdown(
    *,
    risk_detail: pd.DataFrame,
    bucket: pd.DataFrame,
    cross: pd.DataFrame,
    dragon_cross: pd.DataFrame,
    gaps: pd.DataFrame,
    warnings: list[str],
) -> str:
    return "\n".join(
        [
            "# LHB Risk Feature Diagnostics v1",
            "",
            "## 1. 研究目标",
            "本轮只做 LHB 风险特征标准化和案例诊断，不接策略打分。",
            "",
            "## 2. LHB 风险特征定义",
            "lhb_risk_score = 25% negative_net_buy + 20% institution_selling + 20% pump_risk + 15% repeat_attention + 10% concentration + 10% after_event_attention。future return 不参与分数。",
            "",
            "## 3. risk_score 分桶结果",
            _table_preview(bucket, rows=12),
            "",
            "## 4. 失败类型交叉分析",
            _table_preview(cross, rows=20),
            "",
            "## 5. 与 Dragon 风险标签交叉",
            _table_preview(dragon_cross, rows=20),
            "",
            "## 6. 覆盖缺口",
            _table_preview(gaps, rows=20),
            "",
            "## 7. 当前结论",
            f"标准化明细 {len(risk_detail)} 行。LHB 当前更适合作为风险因子候选，不适合作为买点确认。",
            "",
            "## 8. 下一步建议",
            "继续扩大 LHB 覆盖，修 failed_reversal / high_open_low_close_failure / one_day_pump 事件识别规则，后续再设计 entry_score v3。",
            "",
            "### Warnings",
            *(warnings or ["无"]),
        ]
    )


def _shift_date(value: str, days: int) -> str:
    return (pd.Timestamp(value) + pd.Timedelta(days=days)).strftime("%Y-%m-%d")


def _format_date(value: Any) -> str:
    date = pd.to_datetime(value, errors="coerce")
    if pd.isna(date):
        return ""
    return date.strftime("%Y-%m-%d")


def _num(value: Any) -> float | None:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return None
    return float(number)


def _coerce_bool(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "true", "t", "yes", "y"}
