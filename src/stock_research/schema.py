from stock_research.config import SETTINGS
from stock_research.db import connect, execute


CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS asset_master (
    asset_id text PRIMARY KEY,
    market text NOT NULL,
    symbol text NOT NULL,
    exchange text NOT NULL,
    name text NOT NULL,
    currency text NOT NULL,
    industry text NOT NULL DEFAULT '',
    status text NOT NULL,
    list_date date,
    delist_date date,
    source text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS market_daily_bar (
    asset_id text NOT NULL REFERENCES asset_master(asset_id),
    trade_date date NOT NULL,
    open numeric,
    high numeric,
    low numeric,
    close numeric,
    preclose numeric,
    volume numeric,
    amount numeric,
    turnover_rate numeric,
    pct_chg numeric,
    trade_status text NOT NULL,
    is_st boolean NOT NULL,
    adjust_type text NOT NULL,
    source text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, trade_date, adjust_type)
);

CREATE TABLE IF NOT EXISTS data_quality_check (
    check_date date NOT NULL,
    check_name text NOT NULL,
    status text NOT NULL,
    metric_value numeric,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (check_date, check_name)
);

CREATE TABLE IF NOT EXISTS feature_snapshot (
    asset_id text NOT NULL REFERENCES asset_master(asset_id),
    trade_date date NOT NULL,
    feature_set text NOT NULL,
    feature_version text NOT NULL,
    feature_name text NOT NULL,
    feature_value numeric,
    source_data_version text NOT NULL,
    computed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, trade_date, feature_set, feature_version, feature_name)
);

CREATE TABLE IF NOT EXISTS label_snapshot (
    asset_id text NOT NULL REFERENCES asset_master(asset_id),
    trade_date date NOT NULL,
    label_set text NOT NULL,
    label_version text NOT NULL,
    horizon integer NOT NULL,
    label_name text NOT NULL,
    label_value numeric,
    computed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, trade_date, label_set, label_version, horizon, label_name)
);

CREATE TABLE IF NOT EXISTS selection_result (
    run_id text NOT NULL,
    trade_date date NOT NULL,
    asset_id text NOT NULL REFERENCES asset_master(asset_id),
    rank integer NOT NULL,
    score numeric NOT NULL,
    score_version text NOT NULL,
    reasons jsonb NOT NULL,
    risk_tags jsonb NOT NULL,
    feature_snapshot_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, asset_id)
);

CREATE TABLE IF NOT EXISTS backtest_run (
    run_id text PRIMARY KEY,
    score_version text NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    top_n integer NOT NULL,
    holding_days integer[] NOT NULL,
    buy_price_rule text NOT NULL,
    sell_price_rule text NOT NULL,
    execution_profile text NOT NULL,
    report_path text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS backtest_trade (
    run_id text NOT NULL REFERENCES backtest_run(run_id),
    selection_date date NOT NULL,
    asset_id text NOT NULL REFERENCES asset_master(asset_id),
    rank integer NOT NULL,
    score numeric NOT NULL,
    holding_days integer NOT NULL,
    buy_date date,
    buy_open numeric,
    sell_date date,
    sell_open numeric,
    return_value numeric,
    status text NOT NULL,
    skip_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, selection_date, asset_id, holding_days)
);

CREATE TABLE IF NOT EXISTS backtest_summary (
    run_id text NOT NULL REFERENCES backtest_run(run_id),
    holding_days integer NOT NULL,
    selection_days integer NOT NULL,
    theoretical_trades integer NOT NULL,
    closed_trades integer NOT NULL,
    skipped_trades integer NOT NULL,
    unclosed_trades integer NOT NULL,
    mean_return numeric,
    median_return numeric,
    win_rate numeric,
    best_return numeric,
    worst_return numeric,
    batch_mean_return numeric,
    batch_win_rate numeric,
    max_batch_drawdown numeric,
    max_drawdown_start_date date,
    max_drawdown_valley_date date,
    max_drawdown_recovery_date date,
    max_losing_streak integer NOT NULL,
    single_return_p10 numeric,
    single_return_p25 numeric,
    single_return_p75 numeric,
    single_return_p90 numeric,
    batch_return_p10 numeric,
    batch_return_p25 numeric,
    batch_return_p75 numeric,
    batch_return_p90 numeric,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, holding_days)
);

CREATE TABLE IF NOT EXISTS backtest_equity_curve (
    run_id text NOT NULL REFERENCES backtest_run(run_id),
    holding_days integer NOT NULL,
    selection_date date NOT NULL,
    batch_return numeric,
    equity_value numeric,
    drawdown numeric,
    closed_trades integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, holding_days, selection_date)
);

CREATE INDEX IF NOT EXISTS idx_market_daily_bar_trade_date
    ON market_daily_bar (trade_date, adjust_type);

CREATE INDEX IF NOT EXISTS idx_feature_snapshot_trade_date
    ON feature_snapshot (trade_date, feature_set, feature_version);

CREATE INDEX IF NOT EXISTS idx_label_snapshot_trade_date
    ON label_snapshot (trade_date, label_set, label_version);

CREATE INDEX IF NOT EXISTS idx_selection_result_trade_date
    ON selection_result (trade_date, score_version, rank);

CREATE INDEX IF NOT EXISTS idx_backtest_trade_run_holding
    ON backtest_trade (run_id, holding_days, selection_date);

CREATE INDEX IF NOT EXISTS idx_backtest_equity_curve_run_date
    ON backtest_equity_curve (run_id, selection_date, holding_days);
"""

CREATE_RESEARCH_EXTENSION_SQL = """
CREATE SCHEMA IF NOT EXISTS raw_akshare;
CREATE SCHEMA IF NOT EXISTS raw_baostock;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS finance;
CREATE SCHEMA IF NOT EXISTS market;
CREATE SCHEMA IF NOT EXISTS factor;
CREATE SCHEMA IF NOT EXISTS backtest;
CREATE SCHEMA IF NOT EXISTS ingest;

CREATE TABLE IF NOT EXISTS core.asset_master (
    asset_id text PRIMARY KEY,
    ts_code text,
    baostock_code text,
    akshare_code text,
    symbol text NOT NULL,
    name text NOT NULL,
    exchange text NOT NULL,
    board text,
    list_date date,
    delist_date date,
    is_active boolean NOT NULL,
    is_beijing boolean NOT NULL,
    is_star boolean NOT NULL,
    is_chinext boolean NOT NULL,
    region text,
    source text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.asset_status_daily (
    trade_date date NOT NULL,
    asset_id text NOT NULL,
    is_trade boolean NOT NULL,
    is_st boolean NOT NULL,
    is_suspended boolean NOT NULL,
    is_limit_up boolean,
    is_limit_down boolean,
    limit_up_price numeric,
    limit_down_price numeric,
    source text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, asset_id)
);

CREATE TABLE IF NOT EXISTS core.industry_membership (
    asset_id text NOT NULL,
    industry_system text NOT NULL,
    industry_code text NOT NULL,
    industry_name text NOT NULL,
    level integer NOT NULL,
    start_date date NOT NULL,
    end_date date,
    source text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, industry_system, industry_code, level, start_date)
);

CREATE TABLE IF NOT EXISTS market.index_daily_bar (
    index_id text NOT NULL,
    trade_date date NOT NULL,
    open numeric,
    high numeric,
    low numeric,
    close numeric,
    preclose numeric,
    volume numeric,
    amount numeric,
    source text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (index_id, trade_date)
);

CREATE TABLE IF NOT EXISTS market.industry_daily_bar (
    industry_system text NOT NULL,
    industry_code text NOT NULL,
    industry_name text NOT NULL,
    trade_date date NOT NULL,
    open numeric,
    high numeric,
    low numeric,
    close numeric,
    preclose numeric,
    volume numeric,
    amount numeric,
    source text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (industry_system, industry_code, trade_date)
);

CREATE TABLE IF NOT EXISTS finance.income_statement (
    asset_id text NOT NULL,
    report_period date NOT NULL,
    report_type text NOT NULL,
    announcement_date date NOT NULL,
    revenue numeric,
    operating_profit numeric,
    total_profit numeric,
    net_profit numeric,
    np_parent numeric,
    np_parent_deducted numeric,
    eps_basic numeric,
    source text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, report_period, report_type, announcement_date, source)
);

CREATE TABLE IF NOT EXISTS finance.balance_sheet (
    asset_id text NOT NULL,
    report_period date NOT NULL,
    report_type text NOT NULL,
    announcement_date date NOT NULL,
    total_assets numeric,
    total_liabilities numeric,
    total_equity numeric,
    monetary_funds numeric,
    accounts_receivable numeric,
    inventory numeric,
    goodwill numeric,
    source text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, report_period, report_type, announcement_date, source)
);

CREATE TABLE IF NOT EXISTS finance.cash_flow (
    asset_id text NOT NULL,
    report_period date NOT NULL,
    report_type text NOT NULL,
    announcement_date date NOT NULL,
    net_operate_cash_flow numeric,
    net_invest_cash_flow numeric,
    net_finance_cash_flow numeric,
    capex numeric,
    free_cash_flow numeric,
    source text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, report_period, report_type, announcement_date, source)
);

CREATE TABLE IF NOT EXISTS finance.indicator_quarter (
    asset_id text NOT NULL,
    report_period date NOT NULL,
    announcement_date date NOT NULL,
    roe numeric,
    roa numeric,
    gross_margin numeric,
    net_margin numeric,
    debt_ratio numeric,
    revenue_yoy numeric,
    np_yoy numeric,
    deduct_np_yoy numeric,
    ocf_to_np numeric,
    asset_turnover numeric,
    current_ratio numeric,
    quick_ratio numeric,
    source text NOT NULL,
    calc_version text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, report_period, announcement_date, source, calc_version)
);

CREATE TABLE IF NOT EXISTS finance.share_capital_event (
    asset_id text NOT NULL,
    event_date date NOT NULL,
    announcement_date date,
    total_share numeric,
    float_share numeric,
    free_float_share numeric,
    reason text,
    source text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, event_date, source)
);

CREATE TABLE IF NOT EXISTS raw_akshare.finance_payload (
    id bigserial PRIMARY KEY,
    source_endpoint text NOT NULL,
    request_params jsonb NOT NULL,
    asset_id text,
    payload jsonb NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now(),
    payload_hash text NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_baostock.finance_payload (
    id bigserial PRIMARY KEY,
    source_endpoint text NOT NULL,
    request_params jsonb NOT NULL,
    asset_id text,
    payload jsonb NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now(),
    payload_hash text NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest.batch_job (
    job_id text PRIMARY KEY,
    dataset text NOT NULL,
    source text NOT NULL,
    year integer,
    quarter integer,
    period_start date,
    period_end date,
    offset_value integer NOT NULL DEFAULT 0,
    limit_value integer NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    rows_read integer NOT NULL DEFAULT 0,
    rows_written integer NOT NULL DEFAULT 0,
    error_message text,
    params jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ingest.batch_event (
    event_id bigserial PRIMARY KEY,
    job_id text NOT NULL REFERENCES ingest.batch_job(job_id),
    status text NOT NULL,
    message text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ingest.backfill_run (
    run_id text PRIMARY KEY,
    dataset text NOT NULL,
    source text NOT NULL,
    source_version text NOT NULL,
    start_date date,
    end_date date,
    status text NOT NULL DEFAULT 'pending',
    params jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ingest.backfill_task (
    task_id text PRIMARY KEY,
    run_id text NOT NULL REFERENCES ingest.backfill_run(run_id),
    dataset text NOT NULL,
    partition_key text NOT NULL,
    start_date date,
    end_date date,
    status text NOT NULL DEFAULT 'pending',
    rows_read integer NOT NULL DEFAULT 0,
    rows_written integer NOT NULL DEFAULT 0,
    attempts integer NOT NULL DEFAULT 0,
    error_message text,
    params jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, partition_key)
);

CREATE TABLE IF NOT EXISTS factor.factor_daily (
    trade_date date NOT NULL,
    asset_id text NOT NULL,
    factor_name text NOT NULL,
    factor_group text NOT NULL,
    factor_value numeric,
    calc_version text NOT NULL,
    source text NOT NULL,
    source_data_version text NOT NULL,
    computed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, asset_id, factor_name, calc_version)
);

CREATE TABLE IF NOT EXISTS factor.stock_score_daily (
    trade_date date NOT NULL,
    asset_id text NOT NULL,
    rank integer NOT NULL,
    score_total numeric NOT NULL,
    score_version text NOT NULL,
    score_components jsonb NOT NULL DEFAULT '{}'::jsonb,
    calc_version text NOT NULL,
    source_data_version text NOT NULL,
    computed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, asset_id, score_version)
);

CREATE TABLE IF NOT EXISTS factor.factor_eval_run (
    run_id text PRIMARY KEY,
    factor_name text NOT NULL,
    calc_version text NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    horizons integer[] NOT NULL,
    primary_horizon integer NOT NULL,
    status text NOT NULL,
    reason text NOT NULL,
    metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS factor.factor_approval (
    factor_name text NOT NULL,
    calc_version text NOT NULL,
    score_version text NOT NULL,
    status text NOT NULL,
    reason text NOT NULL,
    eval_run_id text NOT NULL REFERENCES factor.factor_eval_run(run_id),
    approved_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (factor_name, calc_version, score_version)
);

CREATE INDEX IF NOT EXISTS idx_finance_indicator_quarter_pit
    ON finance.indicator_quarter (asset_id, announcement_date DESC, report_period DESC);

CREATE INDEX IF NOT EXISTS idx_finance_income_statement_pit
    ON finance.income_statement (asset_id, announcement_date DESC, report_period DESC);

CREATE INDEX IF NOT EXISTS idx_finance_balance_sheet_pit
    ON finance.balance_sheet (asset_id, announcement_date DESC, report_period DESC);

CREATE INDEX IF NOT EXISTS idx_finance_cash_flow_pit
    ON finance.cash_flow (asset_id, announcement_date DESC, report_period DESC);

CREATE INDEX IF NOT EXISTS idx_core_industry_membership_window
    ON core.industry_membership (asset_id, industry_system, start_date, end_date);

CREATE INDEX IF NOT EXISTS idx_core_asset_status_daily_lookup
    ON core.asset_status_daily (trade_date, asset_id);

CREATE INDEX IF NOT EXISTS idx_market_index_daily_bar_date
    ON market.index_daily_bar (trade_date, index_id);

CREATE INDEX IF NOT EXISTS idx_market_industry_daily_bar_date
    ON market.industry_daily_bar (trade_date, industry_system, industry_code);

CREATE INDEX IF NOT EXISTS idx_ingest_batch_job_status
    ON ingest.batch_job (dataset, status, year, quarter, offset_value);

CREATE INDEX IF NOT EXISTS idx_ingest_backfill_task_status
    ON ingest.backfill_task (dataset, status, start_date);

CREATE INDEX IF NOT EXISTS idx_ingest_backfill_task_run_status
    ON ingest.backfill_task (run_id, status, start_date);

CREATE INDEX IF NOT EXISTS idx_factor_daily_lookup
    ON factor.factor_daily (trade_date, factor_name, calc_version);

CREATE INDEX IF NOT EXISTS idx_stock_score_daily_rank
    ON factor.stock_score_daily (trade_date, score_version, rank);

CREATE INDEX IF NOT EXISTS idx_factor_eval_run_factor
    ON factor.factor_eval_run (factor_name, calc_version, created_at DESC);
"""


def apply_schema(service: str = SETTINGS.research_service) -> None:
    with connect(service) as conn:
        execute(conn, CREATE_TABLES_SQL)
        execute(conn, CREATE_RESEARCH_EXTENSION_SQL)
