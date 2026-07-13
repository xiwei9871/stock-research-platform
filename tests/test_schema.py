import pytest

from stock_research.schema import CREATE_RESEARCH_EXTENSION_SQL, CREATE_TABLES_SQL


def build_parser():
    from stock_research.cli import build_parser as _build_parser

    return _build_parser()


def format_progress_bar(value, total, width=20):
    from stock_research.cli import format_progress_bar as _format_progress_bar

    return _format_progress_bar(value, total, width=width)


def test_schema_contains_core_tables():
    sql = CREATE_TABLES_SQL
    assert "CREATE TABLE IF NOT EXISTS asset_master" in sql
    assert "CREATE TABLE IF NOT EXISTS market_daily_bar" in sql
    assert "CREATE TABLE IF NOT EXISTS feature_snapshot" in sql
    assert "CREATE TABLE IF NOT EXISTS label_snapshot" in sql
    assert "CREATE TABLE IF NOT EXISTS selection_result" in sql
    assert "CREATE TABLE IF NOT EXISTS data_quality_check" in sql


def test_schema_creates_stock_auction_tables():
    sql = CREATE_TABLES_SQL + CREATE_RESEARCH_EXTENSION_SQL

    assert "CREATE TABLE IF NOT EXISTS staging.tushare_stock_auction_bar" in sql
    assert "CREATE TABLE IF NOT EXISTS market.stock_auction_bar" in sql
    assert "CREATE TABLE IF NOT EXISTS staging.eastmoney_stock_auction_minute_bar" in sql
    assert "CREATE TABLE IF NOT EXISTS market.stock_auction_minute_bar" in sql
    assert "CREATE TABLE IF NOT EXISTS staging.eastmoney_stock_spot_snapshot" in sql
    assert "CREATE TABLE IF NOT EXISTS market.stock_open_auction_snapshot" in sql
    assert "CREATE TABLE IF NOT EXISTS staging.xtick_stock_auction_detail" in sql
    assert "CREATE TABLE IF NOT EXISTS market.stock_auction_detail" in sql
    assert "auction_phase text NOT NULL CHECK (auction_phase IN ('open_call', 'close_call'))" in sql
    assert "source text NOT NULL CHECK (source IN ('eastmoney_spot_snapshot'))" in sql
    assert "PRIMARY KEY (trade_date, asset_id, auction_phase, source)" in sql
    assert "PRIMARY KEY (trade_time, asset_id, auction_phase, freq, source)" in sql
    assert "PRIMARY KEY (trade_date, asset_id, target_time, source)" in sql
    assert "PRIMARY KEY (trade_time, asset_id, source)" in sql
    assert "idx_market_stock_auction_bar_date_phase" in sql
    assert "idx_market_stock_auction_minute_bar_date_phase" in sql
    assert "idx_market_stock_open_auction_snapshot_date_target" in sql
    assert "idx_market_stock_open_auction_snapshot_asset_time" in sql
    assert "idx_market_stock_auction_detail_date_time" in sql


def test_schema_uses_replay_keys():
    sql = CREATE_TABLES_SQL
    assert "run_id" in sql
    assert "feature_version" in sql
    assert "label_version" in sql
    assert "score_version" in sql
    assert "idx_market_daily_bar_adjust_asset_date_desc" in sql
    assert "idx_market_daily_bar_adjust_date_desc" in sql
    assert "idx_market_industry_daily_bar_system_date_desc" in CREATE_RESEARCH_EXTENSION_SQL


def test_schema_creates_backtest_tables():
    assert "CREATE TABLE IF NOT EXISTS backtest_run" in CREATE_TABLES_SQL
    assert "CREATE TABLE IF NOT EXISTS backtest_trade" in CREATE_TABLES_SQL
    assert "CREATE TABLE IF NOT EXISTS backtest_summary" in CREATE_TABLES_SQL
    assert "CREATE TABLE IF NOT EXISTS backtest_equity_curve" in CREATE_TABLES_SQL
    assert "idx_backtest_trade_run_holding" in CREATE_TABLES_SQL
    assert "idx_backtest_equity_curve_run_date" in CREATE_TABLES_SQL


def test_research_extension_creates_schemas_and_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE SCHEMA IF NOT EXISTS raw_akshare" in sql
    assert "CREATE SCHEMA IF NOT EXISTS raw_baostock" in sql
    assert "CREATE SCHEMA IF NOT EXISTS staging" in sql
    assert "CREATE SCHEMA IF NOT EXISTS core" in sql
    assert "CREATE SCHEMA IF NOT EXISTS finance" in sql
    assert "CREATE SCHEMA IF NOT EXISTS market" in sql
    assert "CREATE SCHEMA IF NOT EXISTS factor" in sql
    assert "CREATE SCHEMA IF NOT EXISTS backtest" in sql
    assert "CREATE SCHEMA IF NOT EXISTS ingest" in sql
    assert "CREATE TABLE IF NOT EXISTS core.asset_master" in sql
    assert "CREATE TABLE IF NOT EXISTS core.asset_status_daily" in sql
    assert "CREATE TABLE IF NOT EXISTS core.industry_membership" in sql
    assert "CREATE TABLE IF NOT EXISTS market.index_daily_bar" in sql
    assert "CREATE TABLE IF NOT EXISTS market.industry_daily_bar" in sql
    assert "CREATE TABLE IF NOT EXISTS finance.income_statement" in sql
    assert "CREATE TABLE IF NOT EXISTS finance.balance_sheet" in sql
    assert "CREATE TABLE IF NOT EXISTS finance.cash_flow" in sql
    assert "CREATE TABLE IF NOT EXISTS finance.indicator_quarter" in sql
    assert "CREATE TABLE IF NOT EXISTS finance.share_capital_event" in sql
    assert "CREATE TABLE IF NOT EXISTS raw_akshare.finance_payload" in sql
    assert "CREATE TABLE IF NOT EXISTS raw_baostock.finance_payload" in sql
    assert "CREATE TABLE IF NOT EXISTS ingest.batch_job" in sql
    assert "CREATE TABLE IF NOT EXISTS ingest.batch_event" in sql
    assert "CREATE TABLE IF NOT EXISTS factor.factor_daily" in sql


def test_schema_does_not_create_redundant_asset_status_lookup_index():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "PRIMARY KEY (trade_date, asset_id)" in sql
    assert "idx_core_asset_status_daily_lookup" not in sql
    assert "CREATE TABLE IF NOT EXISTS factor.stock_score_daily" in sql


def test_research_extension_contains_concept_sector_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL

    assert "CREATE TABLE IF NOT EXISTS core.concept_board" in sql
    assert "CREATE TABLE IF NOT EXISTS core.concept_membership" in sql
    assert "CREATE TABLE IF NOT EXISTS market.concept_daily_bar" in sql
    assert "idx_core_concept_membership_asset_date" in sql
    assert "idx_market_concept_daily_bar_system_date_desc" in sql


def test_research_extension_creates_watchlist_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL

    assert "CREATE SCHEMA IF NOT EXISTS watchlist;" in sql
    assert "CREATE TABLE IF NOT EXISTS watchlist.watchlist_item" in sql
    assert "CREATE TABLE IF NOT EXISTS watchlist.watchlist_daily_signal" in sql


def test_research_extension_creates_stock_report_research_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL

    assert "CREATE SCHEMA IF NOT EXISTS research;" in sql
    assert "CREATE TABLE IF NOT EXISTS research.stock_report_source" in sql
    assert "CREATE TABLE IF NOT EXISTS research.stock_report_event" in sql
    assert "CREATE TABLE IF NOT EXISTS research.stock_report_manual_review" in sql
    assert "CREATE TABLE IF NOT EXISTS research.stock_report_search_task" in sql
    assert "CREATE TABLE IF NOT EXISTS research.stock_report_feature_daily" in sql
    assert "report_id text PRIMARY KEY" in sql
    assert "source_url text NOT NULL" in sql
    assert "target_price numeric" in sql
    assert "moat_or_scarcity_note text" in sql
    assert "research_support_score numeric" in sql
    assert "auto_trade_enabled boolean NOT NULL DEFAULT false" in sql
    assert "idx_research_stock_report_event_asset_date" in sql
    assert "idx_research_stock_report_manual_review_status" in sql
    assert "idx_research_stock_report_search_task_status" in sql
    assert "idx_research_stock_report_feature_daily_score" in sql


def test_research_extension_includes_free_enrichment_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL

    assert "CREATE SCHEMA IF NOT EXISTS fundamental;" in sql
    assert "CREATE SCHEMA IF NOT EXISTS event;" in sql
    assert "CREATE TABLE IF NOT EXISTS raw_akshare.enrichment_payload" in sql
    assert "CREATE TABLE IF NOT EXISTS fundamental.shareholder_count" in sql
    assert "CREATE TABLE IF NOT EXISTS fundamental.top10_holder" in sql
    assert "CREATE TABLE IF NOT EXISTS fundamental.top10_float_holder" in sql
    assert "CREATE TABLE IF NOT EXISTS event.shareholder_trade" in sql
    assert "CREATE TABLE IF NOT EXISTS event.stock_repurchase" in sql
    assert "CREATE TABLE IF NOT EXISTS event.institution_survey" in sql
    assert "CREATE TABLE IF NOT EXISTS event.earnings_forecast" in sql
    assert "CREATE TABLE IF NOT EXISTS event.earnings_express" in sql
    assert "CREATE TABLE IF NOT EXISTS finance.main_business_composition" in sql
    assert "payload_hash text NOT NULL" in sql
    assert "UNIQUE (source_endpoint, payload_hash)" not in sql
    assert "idx_raw_akshare_enrichment_payload_endpoint" in sql
    assert "idx_event_shareholder_trade_asset_date" in sql
    assert "idx_event_stock_repurchase_asset_date" in sql
    assert "idx_finance_main_business_composition_asset_period" in sql


def test_research_extension_includes_unified_stock_minute_bar_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS market.stock_minute_bar" in sql
    assert "CREATE TABLE IF NOT EXISTS staging.baostock_stock_minute_bar" in sql
    assert "source text NOT NULL CHECK (source IN ('baostock', 'tushare', 'akshare', 'eastmoney'))" in sql
    assert "freq text NOT NULL" in sql
    assert "adjust_type text NOT NULL" in sql
    assert "CHECK (freq IN ('1min', '5min', '15min', '30min', '60min'))" in sql
    assert "CHECK (adjust_type IN ('raw', 'qfq', 'hfq'))" in sql
    assert "PRIMARY KEY (trade_date, asset_id, trade_time, freq, adjust_type, source)" in sql
    assert "PARTITION BY RANGE (trade_date)" in sql
    assert "idx_market_stock_minute_bar_asset_time" in sql
    assert "idx_market_stock_minute_bar_date_freq_adjust" in sql
    assert "idx_market_stock_minute_bar_time_freq" in sql
    assert "idx_staging_baostock_stock_minute_bar_date" in sql


def test_research_extension_reserves_intraday_feature_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS factor.stock_intraday_features_daily" in sql
    assert "CREATE TABLE IF NOT EXISTS factor.industry_intraday_features_daily" in sql
    assert "idx_factor_stock_intraday_features_daily_lookup" in sql
    assert "idx_factor_industry_intraday_features_daily_lookup" in sql


def test_research_extension_includes_stock_technical_features_daily_table():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS factor.stock_technical_features_daily" in sql
    assert "PRIMARY KEY (trade_date, asset_id, adjust_type, source_data_version, calc_version)" in sql
    assert "CHECK (adjust_type IN ('raw', 'qfq', 'hfq'))" in sql
    assert "ma5 numeric" in sql
    assert "macd_hist numeric" in sql
    assert "rsi6 numeric" in sql
    assert "boll_mid_20 numeric" in sql
    assert "atr14 numeric" in sql
    assert "ret_1d numeric" in sql
    assert "ret_20d numeric" in sql
    assert "close_position_in_day numeric" in sql
    assert "amount_vs_20d numeric" in sql
    assert "high_to_close_drawdown numeric" in sql
    assert "volatility_5d numeric" in sql
    assert "max_drawdown_20d numeric" in sql
    assert "atr_pct14 numeric" in sql
    assert "idx_factor_stock_technical_features_daily_lookup" in sql
    assert "idx_factor_stock_technical_features_daily_asset_history" in sql


def test_research_extension_includes_minute_backfill_job_table():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS market.minute_bar_backfill_job" in sql
    assert "status text NOT NULL" in sql
    assert "CHECK (status IN ('pending', 'running', 'success', 'failed', 'skipped'))" in sql
    assert "UNIQUE (ts_code, start_date, end_date, freq, adjust_type, source)" in sql
    assert "idx_market_minute_bar_backfill_job_status" in sql
    assert "idx_market_minute_bar_backfill_job_period" in sql


def test_research_extension_enforces_point_in_time_columns():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "report_period date NOT NULL" in sql
    assert "announcement_date date NOT NULL" in sql
    assert "idx_finance_indicator_quarter_pit" in sql
    assert "idx_finance_income_statement_pit" in sql
    assert "idx_core_industry_membership_window" in sql
    assert "idx_ingest_batch_job_status" in sql
    assert "idx_factor_daily_lookup" in sql
    assert "idx_stock_score_daily_rank" in sql


def test_schema_includes_phase11_full_history_indexes():
    sql = CREATE_TABLES_SQL + CREATE_RESEARCH_EXTENSION_SQL
    assert "idx_label_snapshot_eval_lookup" in sql
    assert "idx_label_snapshot_asset_history" in sql
    assert "idx_factor_daily_eval_lookup" in sql
    assert "idx_factor_daily_asset_history" in sql
    assert "idx_stock_score_daily_asset_history" in sql
    assert "idx_raw_baostock_daily_bar_payload_asset_date" in sql


def test_research_extension_includes_factor_eval_gate_tables():
    assert "CREATE TABLE IF NOT EXISTS factor.factor_eval_run" in CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS factor.factor_approval" in CREATE_RESEARCH_EXTENSION_SQL
    assert "idx_factor_eval_run_factor" in CREATE_RESEARCH_EXTENSION_SQL


def test_research_extension_includes_backfill_run_task_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS ingest.backfill_run" in sql
    assert "CREATE TABLE IF NOT EXISTS ingest.backfill_task" in sql
    assert "idx_ingest_backfill_task_status" in sql
    assert "idx_ingest_backfill_task_run_status" in sql


def test_research_extension_includes_calendar_and_lifecycle_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS market.trading_calendar" in sql
    assert "CREATE TABLE IF NOT EXISTS core.asset_lifecycle_event" in sql
    assert "idx_market_trading_calendar_open_date" in sql
    assert "idx_core_asset_lifecycle_event_asset_date" in sql


def test_research_extension_includes_raw_daily_bar_payload_table():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS raw_baostock.daily_bar_payload" in sql
    assert "payload_hash text NOT NULL" in sql
    assert "idx_raw_baostock_daily_bar_payload_lookup" in sql


def test_research_extension_includes_raw_industry_snapshot_payload_table():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS raw_baostock.industry_snapshot_payload" in sql
    assert "row_count integer NOT NULL" in sql
    assert "idx_raw_baostock_industry_snapshot_date" in sql


def test_research_extension_includes_phase4_action_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS market.adjustment_factor" in sql
    assert "CREATE TABLE IF NOT EXISTS market.corporate_action" in sql
    assert "idx_market_adjustment_factor_date" in sql
    assert "idx_market_corporate_action_asset_date" in sql


def test_research_extension_includes_index_constituent_table():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS market.index_constituent" in sql
    assert "source_version text NOT NULL" in sql
    assert "idx_market_index_constituent_lookup" in sql


def test_research_extension_includes_lhb_tables_and_event_features():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS market.lhb_top_list_daily" in sql
    assert "CREATE TABLE IF NOT EXISTS market.lhb_top_inst_daily" in sql
    assert "CREATE TABLE IF NOT EXISTS factor.lhb_event_features_daily" in sql
    assert "repeat_on_list_count_5d" in sql
    assert "institution_net_buy" in sql


def test_research_extension_includes_p2_review_read_model_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE SCHEMA IF NOT EXISTS ops" in sql
    assert "CREATE TABLE IF NOT EXISTS ops.p2_review_run" in sql
    assert "CREATE TABLE IF NOT EXISTS ops.p2_review_section" in sql
    assert "PRIMARY KEY (run_id, section_group, section_name)" in sql
    assert "idx_ops_p2_review_run_trade_date" in sql
    assert "idx_ops_p2_review_run_status_date" in sql
    assert "idx_ops_p2_review_section_group_status" in sql


def test_research_extension_includes_operator_decision_read_model_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE SCHEMA IF NOT EXISTS ops" in sql
    assert "CREATE TABLE IF NOT EXISTS ops.operator_review_session" in sql
    assert "CREATE TABLE IF NOT EXISTS ops.operator_decision_event" in sql
    assert "PRIMARY KEY (review_session_id)" in sql
    assert "PRIMARY KEY (event_id)" in sql
    assert "idx_ops_operator_review_session_date" in sql
    assert "idx_ops_operator_decision_event_asset_date" in sql
    assert "idx_ops_operator_decision_event_label_date" in sql


def test_research_extension_includes_operator_decision_outcome_read_model_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS ops.operator_decision_outcome_run" in sql
    assert "CREATE TABLE IF NOT EXISTS ops.operator_decision_outcome_event" in sql
    assert "PRIMARY KEY (run_id)" in sql
    assert "PRIMARY KEY (outcome_event_id)" in sql
    assert "decision_event_id text NOT NULL" in sql
    assert "forward_returns jsonb NOT NULL DEFAULT '{}'::jsonb" in sql
    assert "idx_ops_operator_decision_outcome_run_date" in sql
    assert "idx_ops_operator_decision_outcome_event_asset_date" in sql


def test_research_extension_includes_operator_shadow_outcome_read_model_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS ops.operator_shadow_watchlist_outcome_run" in sql
    assert "CREATE TABLE IF NOT EXISTS ops.operator_shadow_watchlist_outcome_candidate" in sql
    assert "PRIMARY KEY (shadow_outcome_id)" in sql
    assert "source_p12_shadow_run_id text NOT NULL" in sql
    assert "production_watchlist_enabled boolean NOT NULL DEFAULT false" in sql
    assert "idx_ops_operator_shadow_outcome_run_date" in sql
    assert "idx_ops_operator_shadow_outcome_status_date" in sql
    assert "idx_ops_operator_shadow_outcome_asset_date" in sql
    assert "idx_ops_operator_shadow_outcome_source_candidate" in sql


def test_p14_shadow_outcome_analytics_tables_exist():
    ddl = CREATE_RESEARCH_EXTENSION_SQL

    assert "CREATE TABLE IF NOT EXISTS ops.operator_shadow_watchlist_outcome_analytics_run" in ddl
    assert "CREATE TABLE IF NOT EXISTS ops.operator_shadow_watchlist_outcome_analytics_group" in ddl
    assert "idx_operator_shadow_watchlist_outcome_analytics_group_date" in ddl
    assert "idx_operator_shadow_watchlist_outcome_analytics_group_key" in ddl


def test_p15_shadow_analytics_review_tables_exist():
    ddl = CREATE_RESEARCH_EXTENSION_SQL

    assert "CREATE TABLE IF NOT EXISTS ops.operator_shadow_analytics_review_run" in ddl
    assert "CREATE TABLE IF NOT EXISTS ops.operator_shadow_analytics_review_group" in ddl
    assert "idx_operator_shadow_analytics_review_group_date" in ddl
    assert "idx_operator_shadow_analytics_review_group_status" in ddl


def test_p16_shadow_review_decision_tables_exist():
    ddl = CREATE_RESEARCH_EXTENSION_SQL

    assert "CREATE TABLE IF NOT EXISTS ops.operator_shadow_review_decision_run" in ddl
    assert "CREATE TABLE IF NOT EXISTS ops.operator_shadow_review_decision_group" in ddl
    assert "idx_operator_shadow_review_decision_group_date" in ddl
    assert "idx_operator_shadow_review_decision_group_status" in ddl


def test_p17_shadow_follow_up_queue_tables_exist():
    ddl = CREATE_RESEARCH_EXTENSION_SQL

    assert "CREATE TABLE IF NOT EXISTS ops.operator_shadow_follow_up_run" in ddl
    assert "CREATE TABLE IF NOT EXISTS ops.operator_shadow_follow_up_item" in ddl
    assert "idx_operator_shadow_follow_up_item_date" in ddl
    assert "idx_operator_shadow_follow_up_item_status" in ddl


def test_p18_shadow_follow_up_resolution_tables_exist():
    ddl = CREATE_RESEARCH_EXTENSION_SQL

    assert "CREATE TABLE IF NOT EXISTS ops.operator_shadow_follow_up_resolution_run" in ddl
    assert "CREATE TABLE IF NOT EXISTS ops.operator_shadow_follow_up_resolution_item" in ddl
    assert "idx_operator_shadow_follow_up_resolution_item_date" in ddl
    assert "idx_operator_shadow_follow_up_resolution_item_status" in ddl


def test_research_extension_includes_operator_decision_outcome_analytics_read_model_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS ops.operator_decision_outcome_analytics_run" in sql
    assert "CREATE TABLE IF NOT EXISTS ops.operator_decision_outcome_analytics_group" in sql
    assert "PRIMARY KEY (analytics_group_id)" in sql
    assert "analytics_artifact_path text NOT NULL" in sql
    assert "horizon_metrics jsonb NOT NULL DEFAULT '{}'::jsonb" in sql
    assert "idx_ops_operator_decision_outcome_analytics_run_date" in sql
    assert "idx_ops_operator_decision_outcome_analytics_group_level_date" in sql


def test_research_extension_includes_operator_experiment_proposal_read_model_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS ops.operator_experiment_proposal_run" in sql
    assert "CREATE TABLE IF NOT EXISTS ops.operator_experiment_proposal" in sql
    assert "PRIMARY KEY (proposal_id)" in sql
    assert "source_p9_analytics_run_id text NOT NULL" in sql
    assert "source_analytics_group_ids jsonb NOT NULL DEFAULT '[]'::jsonb" in sql
    assert "promotion_enabled boolean NOT NULL DEFAULT false" in sql
    assert "idx_ops_operator_experiment_proposal_run_date" in sql
    assert "idx_ops_operator_experiment_proposal_status_date" in sql


def test_research_extension_includes_operator_experiment_replay_read_model_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS ops.operator_experiment_replay_run" in sql
    assert "CREATE TABLE IF NOT EXISTS ops.operator_experiment_replay_result" in sql
    assert "PRIMARY KEY (replay_result_id)" in sql
    assert "source_p10_proposal_run_id text NOT NULL" in sql
    assert "source_p9_analytics_run_id text NOT NULL" in sql
    assert "replay_input_artifact_paths jsonb NOT NULL DEFAULT '[]'::jsonb" in sql
    assert "metric_summary jsonb NOT NULL DEFAULT '{}'::jsonb" in sql
    assert "production_write_enabled boolean NOT NULL DEFAULT false" in sql
    assert "idx_ops_operator_experiment_replay_run_date" in sql
    assert "idx_ops_operator_experiment_replay_status_date" in sql


def test_research_extension_includes_operator_shadow_watchlist_read_model_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS ops.operator_shadow_watchlist_run" in sql
    assert "CREATE TABLE IF NOT EXISTS ops.operator_shadow_watchlist_candidate" in sql
    assert "PRIMARY KEY (shadow_candidate_id)" in sql
    assert "source_p11_replay_run_id text NOT NULL" in sql
    assert "production_watchlist_enabled boolean NOT NULL DEFAULT false" in sql
    assert "idx_ops_operator_shadow_watchlist_run_date" in sql
    assert "idx_ops_operator_shadow_watchlist_status_date" in sql


def test_research_extension_includes_virtual_portfolio_read_model_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE SCHEMA IF NOT EXISTS simulation" in sql
    assert "CREATE TABLE IF NOT EXISTS simulation.virtual_portfolio_state_daily" in sql
    assert "CREATE TABLE IF NOT EXISTS simulation.virtual_portfolio_position_daily" in sql
    assert "PRIMARY KEY (portfolio_id, trade_date, strategy_id)" in sql
    assert "PRIMARY KEY (portfolio_id, trade_date, strategy_id, stock_code)" in sql
    assert "idx_simulation_virtual_portfolio_state_portfolio_date" in sql
    assert "idx_simulation_virtual_portfolio_state_risk_date" in sql
    assert "idx_simulation_virtual_portfolio_position_stock_date" in sql


def test_cli_accepts_apply_research_schema_command():
    args = build_parser().parse_args(["apply-research-schema"])
    assert args.command == "apply-research-schema"


def test_cli_accepts_core_data_commands():
    sync_args = build_parser().parse_args(["sync-core-assets"])
    assert sync_args.command == "sync-core-assets"

    status_args = build_parser().parse_args(
        [
            "build-asset-status",
            "--start-date",
            "2026-05-06",
            "--end-date",
            "2026-05-08",
        ]
    )
    assert status_args.command == "build-asset-status"
    assert status_args.start_date == "2026-05-06"
    assert status_args.end_date == "2026-05-08"

    industry_bar_args = build_parser().parse_args(
        [
            "build-industry-bars",
            "--start-date",
            "2026-05-01",
            "--end-date",
            "2026-05-08",
            "--industry-system",
            "csrc",
        ]
    )
    assert industry_bar_args.command == "build-industry-bars"
    assert industry_bar_args.start_date == "2026-05-01"
    assert industry_bar_args.end_date == "2026-05-08"
    assert industry_bar_args.industry_system == "csrc"


def test_cli_accepts_baostock_ingestion_commands():
    industry_args = build_parser().parse_args(
        ["sync-industry-memberships", "--trade-date", "2026-05-08"]
    )
    assert industry_args.command == "sync-industry-memberships"
    assert industry_args.trade_date == "2026-05-08"

    index_args = build_parser().parse_args(
        [
            "sync-index-bars",
            "--start-date",
            "2026-05-01",
            "--end-date",
            "2026-05-08",
        ]
    )
    assert index_args.command == "sync-index-bars"
    assert index_args.start_date == "2026-05-01"
    assert index_args.end_date == "2026-05-08"

    finance_args = build_parser().parse_args(
        [
            "sync-baostock-finance",
            "--year",
            "2025",
            "--quarter",
            "4",
            "--limit",
            "20",
            "--offset",
            "40",
        ]
    )
    assert finance_args.command == "sync-baostock-finance"
    assert finance_args.year == 2025
    assert finance_args.quarter == 4
    assert finance_args.limit == 20
    assert finance_args.offset == 40

    minute_args = build_parser().parse_args(
        [
            "sync-baostock-minute-bars",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2026-05-13",
            "--freq",
            "5min",
            "--adjust-types",
            "raw,qfq",
            "--limit-assets",
            "10",
        ]
    )
    assert minute_args.command == "sync-baostock-minute-bars"
    assert minute_args.start_date == "2024-01-01"
    assert minute_args.end_date == "2026-05-13"
    assert minute_args.freq == "5min"
    assert minute_args.adjust_types == ["raw", "qfq"]
    assert minute_args.limit_assets == 10

    auction_args = build_parser().parse_args(
        [
            "sync-tushare-auction-bars",
            "--ts-codes",
            "600023.SH,000001.SZ",
            "--start-date",
            "2026-03-05",
            "--end-date",
            "2026-03-06",
            "--auction-phases",
            "open_call,close_call",
        ]
    )
    assert auction_args.command == "sync-tushare-auction-bars"
    assert auction_args.ts_codes == ["600023.SH", "000001.SZ"]
    assert auction_args.start_date == "2026-03-05"
    assert auction_args.end_date == "2026-03-06"
    assert auction_args.auction_phases == ["open_call", "close_call"]

    parser = build_parser()
    args = parser.parse_args(
        [
            "collect-open-auction-spot-snapshot-v1",
            "--trade-date",
            "2026-06-11",
            "--target-time",
            "09:17",
        ]
    )
    assert args.command == "collect-open-auction-spot-snapshot-v1"
    assert args.target_time == "09:17"

    cron_args = parser.parse_args(["open-auction-spot-snapshot-cron-entry"])
    assert cron_args.command == "open-auction-spot-snapshot-cron-entry"

    auction_observation_args = build_parser().parse_args(
        [
            "lhb-auction-observation-v1",
            "--trades-path",
            "phase15.csv",
            "--start-date",
            "2025-01-02",
            "--end-date",
            "2025-01-06",
            "--ts-codes",
            "300615.SZ,605080.SH",
            "--output-dir",
            "outputs/research/lhb_auction_observation_smoke",
        ]
    )
    assert auction_observation_args.command == "lhb-auction-observation-v1"
    assert auction_observation_args.trades_path == "phase15.csv"
    assert auction_observation_args.ts_codes == ["300615.SZ", "605080.SH"]
    assert auction_observation_args.output_dir == "outputs/research/lhb_auction_observation_smoke"

    phase18_args = build_parser().parse_args(
        [
            "lhb-phase18-auction-rule-scan-v1",
            "--detail-path",
            "lhb_auction_observation_detail_v1.csv",
            "--rule-layer",
            "follow_pool_core",
            "--thresholds",
            "0.02,0.04,0.06",
            "--output-dir",
            "outputs/research/lhb_phase18",
        ]
    )
    assert phase18_args.command == "lhb-phase18-auction-rule-scan-v1"
    assert phase18_args.detail_path == "lhb_auction_observation_detail_v1.csv"
    assert phase18_args.rule_layer == "follow_pool_core"
    assert phase18_args.thresholds == [0.02, 0.04, 0.06]
    assert phase18_args.output_dir == "outputs/research/lhb_phase18"

    phase18b_args = build_parser().parse_args(
        [
            "lhb-phase18b-auction-topn-rerank-v1",
            "--detail-path",
            "phase14c_detail.csv",
            "--top-n",
            "5,10",
            "--output-dir",
            "outputs/research/lhb_phase18b",
        ]
    )
    assert phase18b_args.command == "lhb-phase18b-auction-topn-rerank-v1"
    assert phase18b_args.detail_path == "phase14c_detail.csv"
    assert phase18b_args.top_n == [5, 10]
    assert phase18b_args.output_dir == "outputs/research/lhb_phase18b"

    phase18c_args = build_parser().parse_args(
        [
            "lhb-phase18c-auction-cash-account-v1",
            "--lifecycle-trades-path",
            "lifecycle.csv",
            "--scored-candidates-path",
            "scored.csv",
            "--top-n",
            "3,5,10",
            "--max-positions",
            "10",
            "--position-pct",
            "0.1",
            "--output-dir",
            "outputs/research/lhb_phase18c",
        ]
    )
    assert phase18c_args.command == "lhb-phase18c-auction-cash-account-v1"
    assert phase18c_args.lifecycle_trades_path == "lifecycle.csv"
    assert phase18c_args.scored_candidates_path == "scored.csv"
    assert phase18c_args.top_n == [3, 5, 10]
    assert phase18c_args.max_positions == 10
    assert phase18c_args.position_pct == 0.1

    phase18d_args = build_parser().parse_args(
        [
            "lhb-phase18d-close-auction-lifecycle-v1",
            "--trades-path",
            "account_trades.csv",
            "--strategy",
            "auction_enhanced_rerank",
            "--top-n",
            "5",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2026-06-05",
            "--output-dir",
            "outputs/research/lhb_phase18d",
        ]
    )
    assert phase18d_args.command == "lhb-phase18d-close-auction-lifecycle-v1"
    assert phase18d_args.trades_path == "account_trades.csv"
    assert phase18d_args.strategy == "auction_enhanced_rerank"
    assert phase18d_args.top_n == 5
    assert phase18d_args.start_date == "2025-01-01"
    assert phase18d_args.end_date == "2026-06-05"
    assert phase18d_args.output_dir == "outputs/research/lhb_phase18d"

    phase18e_args = build_parser().parse_args(
        [
            "lhb-phase18e-joint-exit-diagnostics-v1",
            "--account-trades-path",
            "account_trades.csv",
            "--auction-observation-path",
            "auction_observation.csv",
            "--close-lifecycle-path",
            "close_lifecycle.csv",
            "--intraday-indicator-path",
            "phase16d.csv",
            "--strategy",
            "auction_enhanced_rerank",
            "--top-n",
            "5",
            "--output-dir",
            "outputs/research/lhb_phase18e",
        ]
    )
    assert phase18e_args.command == "lhb-phase18e-joint-exit-diagnostics-v1"
    assert phase18e_args.account_trades_path == "account_trades.csv"
    assert phase18e_args.auction_observation_path == "auction_observation.csv"
    assert phase18e_args.close_lifecycle_path == "close_lifecycle.csv"
    assert phase18e_args.intraday_indicator_path == "phase16d.csv"
    assert phase18e_args.strategy == "auction_enhanced_rerank"
    assert phase18e_args.top_n == 5
    assert phase18e_args.output_dir == "outputs/research/lhb_phase18e"

    phase18f_args = build_parser().parse_args(
        [
            "lhb-phase18f-tradable-joint-exit-replay-v1",
            "--account-trades-path",
            "account_trades.csv",
            "--joint-state-detail-path",
            "joint_state.csv",
            "--close-lifecycle-detail-path",
            "close_lifecycle_detail.csv",
            "--selected-trades-path",
            "selected.csv",
            "--minute-bars-path",
            "minute.csv",
            "--strategy",
            "auction_enhanced_rerank",
            "--top-n",
            "5",
            "--freq",
            "5min",
            "--adjust-type",
            "raw",
            "--output-dir",
            "outputs/research/lhb_phase18f",
        ]
    )
    assert phase18f_args.command == "lhb-phase18f-tradable-joint-exit-replay-v1"
    assert phase18f_args.account_trades_path == "account_trades.csv"
    assert phase18f_args.joint_state_detail_path == "joint_state.csv"
    assert phase18f_args.close_lifecycle_detail_path == "close_lifecycle_detail.csv"
    assert phase18f_args.selected_trades_path == "selected.csv"
    assert phase18f_args.minute_bars_path == "minute.csv"
    assert phase18f_args.strategy == "auction_enhanced_rerank"
    assert phase18f_args.top_n == 5
    assert phase18f_args.freq == "5min"
    assert phase18f_args.adjust_type == "raw"
    assert phase18f_args.output_dir == "outputs/research/lhb_phase18f"

    auction_backfill_plan_args = build_parser().parse_args(
        [
            "lhb-auction-backfill-plan-v1",
            "--candidate-paths",
            "selected.csv,phase18.csv",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2026-06-09",
            "--auction-phases",
            "open_call,close_call",
            "--trade-dates",
            "2025-01-02,2025-01-03",
            "--min-coverage-ratio",
            "0.95",
            "--output-dir",
            "outputs/research/lhb_auction_backfill_20250101",
        ]
    )
    assert auction_backfill_plan_args.command == "lhb-auction-backfill-plan-v1"
    assert auction_backfill_plan_args.candidate_paths == ["selected.csv", "phase18.csv"]
    assert auction_backfill_plan_args.auction_phases == ["open_call", "close_call"]
    assert auction_backfill_plan_args.trade_dates == ["2025-01-02", "2025-01-03"]
    assert auction_backfill_plan_args.min_coverage_ratio == 0.95

    auction_backfill_run_args = build_parser().parse_args(
        [
            "lhb-auction-backfill-run-v1",
            "--plan-path",
            "plan.csv",
            "--ts-codes-path",
            "universe.csv",
            "--max-calls",
            "500",
            "--sleep-seconds",
            "1.3",
            "--output-dir",
            "outputs/research/lhb_auction_backfill_20250101",
        ]
    )
    assert auction_backfill_run_args.command == "lhb-auction-backfill-run-v1"
    assert auction_backfill_run_args.max_calls == 500
    assert auction_backfill_run_args.sleep_seconds == 1.3

    plan_args = build_parser().parse_args(
        [
            "plan-baostock-minute-backfill",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2026-05-13",
            "--freq",
            "5min",
            "--adjust-types",
            "raw,qfq",
            "--batch-by",
            "month",
            "--output-dir",
            "outputs/research",
        ]
    )
    assert plan_args.command == "plan-baostock-minute-backfill"
    assert plan_args.batch_by == "month"

    run_args = build_parser().parse_args(
        [
            "run-baostock-minute-backfill",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2026-05-13",
            "--freq",
            "5min",
            "--adjust-types",
            "raw,qfq",
            "--batch-by",
            "month",
            "--max-jobs",
            "50",
            "--retry-failed",
            "--sleep-seconds",
            "0.5",
            "--workers",
            "1",
        ]
    )
    assert run_args.command == "run-baostock-minute-backfill"
    assert run_args.max_jobs == 50
    assert run_args.retry_failed is True
    assert run_args.workers == 1

    range_args = build_parser().parse_args(
        [
            "run-baostock-minute-backfill-range",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-03-31",
            "--freq",
            "5min",
            "--adjust-types",
            "raw,qfq",
            "--max-jobs",
            "200",
            "--workers",
            "1",
            "--report-target",
            "chat:oc_82dd978138a0cde5864868c5b5b8e754",
            "--report-account",
            "jarvis",
        ]
    )
    assert range_args.command == "run-baostock-minute-backfill-range"
    assert range_args.workers == 1
    assert range_args.report_account == "jarvis"

    benchmark_args = build_parser().parse_args(
        [
            "benchmark-baostock-minute-backfill",
            "--start-date",
            "2026-06-10",
            "--end-date",
            "2026-06-10",
            "--freq",
            "5min",
            "--adjust-types",
            "raw",
            "--max-jobs",
            "300",
            "--workers-list",
            "1",
            "--retry-failed",
            "--sleep-seconds",
            "0.05",
        ]
    )
    assert benchmark_args.command == "benchmark-baostock-minute-backfill"
    assert benchmark_args.worker_counts == [1]
    assert benchmark_args.max_jobs == 300
    assert benchmark_args.freq == "5min"
    assert benchmark_args.adjust_types == ["raw"]

    with pytest.raises(SystemExit):
        build_parser().parse_args(["run-baostock-minute-backfill", "--workers", "4"])
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [
                "run-baostock-minute-backfill-range",
                "--start-date",
                "2024-01-01",
                "--end-date",
                "2024-01-31",
                "--workers",
                "4",
                "--report-target",
                "chat:test",
            ]
        )
    with pytest.raises(SystemExit):
        build_parser().parse_args(["benchmark-baostock-minute-backfill", "--workers-list", "4,8"])

    watchdog_args = build_parser().parse_args(
        [
            "baostock-minute-backfill-watchdog",
            "--start-date",
            "2021-07-02",
            "--end-date",
            "2026-07-02",
            "--freq",
            "5min",
            "--adjust-types",
            "raw,qfq",
            "--baostock-daily-request-limit",
            "50000",
            "--baostock-safety-multiplier",
            "1.1",
            "--request-ledger-path",
            "logs/baostock_minute_request_quota.json",
            "--report-target",
            "chat:oc_82dd978138a0cde5864868c5b5b8e754",
        ]
    )
    assert watchdog_args.command == "baostock-minute-backfill-watchdog"
    assert watchdog_args.baostock_safety_multiplier == 1.1
    assert watchdog_args.request_ledger_path == "logs/baostock_minute_request_quota.json"

    probe_args = build_parser().parse_args(
        [
            "probe-baostock-minute-backfill-coverage",
            "--start-date",
            "2021-07-02",
            "--end-date",
            "2026-07-02",
            "--freq",
            "5min",
            "--adjust-types",
            "raw,qfq",
        ]
    )
    assert probe_args.command == "probe-baostock-minute-backfill-coverage"
    assert probe_args.adjust_types == ["raw", "qfq"]

    availability_args = build_parser().parse_args(
        [
            "probe-baostock-minute-availability",
            "--codes",
            "sh.600000,sz.000001",
            "--dates",
            "2019-12-31,2020-01-02,2021-07-01",
            "--freq",
            "5min",
            "--adjust-types",
            "raw,qfq",
            "--timeout-seconds",
            "15",
        ]
    )
    assert availability_args.command == "probe-baostock-minute-availability"
    assert availability_args.codes == ["sh.600000", "sz.000001"]
    assert availability_args.dates == ["2019-12-31", "2020-01-02", "2021-07-01"]
    assert availability_args.timeout_seconds == 15

    status_args = build_parser().parse_args(["baostock-minute-backfill-status"])
    assert status_args.command == "baostock-minute-backfill-status"

    validate_args = build_parser().parse_args(
        [
            "validate-minute-bars",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2026-05-13",
            "--freq",
            "5min",
            "--adjust-types",
            "raw,qfq",
        ]
    )
    assert validate_args.command == "validate-minute-bars"
    assert validate_args.adjust_types == ["raw", "qfq"]


def test_cli_accepts_ingest_batch_commands():
    create_args = build_parser().parse_args(
        [
            "create-ingest-jobs",
            "--dataset",
            "baostock-finance",
            "--start-year",
            "1990",
            "--end-year",
            "2025",
            "--batch-size",
            "50",
        ]
    )
    assert create_args.command == "create-ingest-jobs"
    assert create_args.dataset == "baostock-finance"
    assert create_args.start_year == 1990
    assert create_args.end_year == 2025
    assert create_args.batch_size == 50

    run_args = build_parser().parse_args(
        ["run-ingest-jobs", "--dataset", "baostock-finance", "--limit-jobs", "3"]
    )
    assert run_args.command == "run-ingest-jobs"
    assert run_args.limit_jobs == 3

    akshare_create_args = build_parser().parse_args(
        [
            "create-ingest-jobs",
            "--dataset",
            "akshare-finance-statements",
            "--start-year",
            "1990",
            "--end-year",
            "2025",
            "--batch-size",
            "20",
        ]
    )
    assert akshare_create_args.command == "create-ingest-jobs"
    assert akshare_create_args.dataset == "akshare-finance-statements"
    assert akshare_create_args.batch_size == 20

    akshare_run_args = build_parser().parse_args(
        ["run-ingest-jobs", "--dataset", "akshare-finance-statements", "--limit-jobs", "3"]
    )
    assert akshare_run_args.command == "run-ingest-jobs"
    assert akshare_run_args.dataset == "akshare-finance-statements"

    finance_audit_args = build_parser().parse_args(["finance-audit"])
    assert finance_audit_args.command == "finance-audit"

    status_args = build_parser().parse_args(
        ["ingest-status", "--dataset", "baostock-finance"]
    )
    assert status_args.command == "ingest-status"
    assert status_args.dataset == "baostock-finance"

    loop_args = build_parser().parse_args(
        [
            "run-ingest-loop",
            "--dataset",
            "baostock-finance",
            "--jobs-per-round",
            "50",
            "--report-target",
            "oc_group",
            "--report-account",
            "jarvis",
            "--sleep-seconds",
            "0",
            "--max-rounds",
            "1",
            "--workers",
            "2",
            "--report-dry-run",
        ]
    )
    assert loop_args.command == "run-ingest-loop"
    assert loop_args.dataset == "baostock-finance"
    assert loop_args.jobs_per_round == 50
    assert loop_args.report_target == "oc_group"
    assert loop_args.report_account == "jarvis"
    assert loop_args.sleep_seconds == 0
    assert loop_args.max_rounds == 1
    assert loop_args.workers == 2
    assert loop_args.report_dry_run is True

    label_args = build_parser().parse_args(
        [
            "backfill-labels",
            "--horizons",
            "5,20,60",
            "--start-date",
            "1990-12-19",
            "--end-date",
            "2026-05-08",
        ]
    )
    assert label_args.command == "backfill-labels"
    assert label_args.horizons == [5, 20, 60]
    assert label_args.start_date == "1990-12-19"
    assert label_args.end_date == "2026-05-08"


def test_format_progress_bar():
    assert format_progress_bar(0, 10, width=10) == "[----------]"
    assert format_progress_bar(5, 10, width=10) == "[#####-----]"
    assert format_progress_bar(10, 10, width=10) == "[##########]"


def test_cli_main_runs_ingest_loop_and_prints_outputs(monkeypatch, capsys):
    from stock_research import cli

    calls = []
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "run-ingest-loop",
            "--dataset",
            "baostock-finance",
            "--jobs-per-round",
            "2",
            "--report-target",
            "oc_group",
            "--sleep-seconds",
            "0",
            "--max-rounds",
            "1",
            "--workers",
            "2",
            "--report-dry-run",
        ],
    )

    def fake_run_loop(dataset, **kwargs):
        kwargs["report"](
            {
                "dataset": "baostock-finance",
                "round": 1,
                "attempted": 2,
                "success": 2,
                "failed": 0,
                "rows_read": 100,
                "rows_written": 0,
                "status_counts": {"success": 2, "pending": 0},
                "recent_jobs": [],
                "done": True,
            }
        )
        calls.append(("run_loop", dataset, kwargs))
        return {
            "rounds": 1,
            "attempted": 2,
            "success": 2,
            "failed": 0,
            "done": True,
        }

    monkeypatch.setattr(cli, "run_ingest_loop_for_service", fake_run_loop)
    monkeypatch.setattr(
        cli,
        "send_openclaw_feishu_message",
        lambda **kwargs: calls.append(("send", kwargs)),
    )

    cli.main()

    captured = capsys.readouterr()
    assert "A股财务数据补齐进度" in captured.out
    assert "ingest_loop_rounds|1" in captured.out
    assert "ingest_loop_done|True" in captured.out
    assert calls[0][0] == "send"
    assert calls[0][1]["target"] == "oc_group"
    assert calls[0][1]["account"] == "jarvis"
    assert calls[0][1]["dry_run"] is True
    assert calls[1][0] == "run_loop"
    assert calls[1][1] == "baostock-finance"
    assert calls[1][2]["jobs_per_round"] == 2
    assert calls[1][2]["workers"] == 2


def test_run_ingest_loop_notification_failure_does_not_abort(monkeypatch, capsys):
    import stock_research.cli as cli

    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "run-ingest-loop",
            "--dataset",
            "baostock-finance",
            "--jobs-per-round",
            "2",
            "--sleep-seconds",
            "0",
            "--max-rounds",
            "1",
            "--report-target",
            "oc_group",
        ],
    )

    monkeypatch.setattr(
        cli,
        "run_ingest_loop_for_service",
        lambda dataset, **kwargs: (
            kwargs["report"](
                {
                    "dataset": "baostock-finance",
                    "round": 1,
                    "attempted": 2,
                    "success": 2,
                    "failed": 0,
                    "rows_read": 100,
                    "rows_written": 0,
                    "status_counts": {"success": 2, "pending": 0},
                    "recent_jobs": [],
                    "done": True,
                }
            )
            or {
                "rounds": 1,
                "attempted": 2,
                "success": 2,
                "failed": 0,
                "done": True,
            }
        ),
    )

    def boom(**kwargs):
        raise RuntimeError("feishu down")

    monkeypatch.setattr(cli, "send_openclaw_feishu_message", boom)

    cli.main()

    captured = capsys.readouterr()
    assert "ingest_loop_rounds|1" in captured.out
    assert "ingest_loop_done|True" in captured.out
    assert "ingest_loop_report_failed|RuntimeError|feishu down" in captured.err
