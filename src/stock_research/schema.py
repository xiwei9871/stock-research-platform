import datetime as dt

from stock_research.config import SETTINGS
from stock_research.db import connect, execute


STOCK_MINUTE_BAR_PARTITIONED_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS market.stock_minute_bar (
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    trade_time timestamp without time zone NOT NULL,
    trade_date date NOT NULL,
    freq text NOT NULL CHECK (freq IN ('1min', '5min', '15min', '30min', '60min')),
    adjust_type text NOT NULL CHECK (adjust_type IN ('raw', 'qfq', 'hfq')),
    open numeric,
    high numeric,
    low numeric,
    close numeric,
    volume numeric,
    amount numeric,
    source text NOT NULL CHECK (source IN ('baostock', 'tushare', 'akshare')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, asset_id, trade_time, freq, adjust_type, source)
) PARTITION BY RANGE (trade_date);
"""


CREATE_RESEARCH_SCHEMAS_SQL = """
CREATE SCHEMA IF NOT EXISTS raw_akshare;
CREATE SCHEMA IF NOT EXISTS raw_baostock;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS finance;
CREATE SCHEMA IF NOT EXISTS fundamental;
CREATE SCHEMA IF NOT EXISTS event;
CREATE SCHEMA IF NOT EXISTS market;
CREATE SCHEMA IF NOT EXISTS factor;
CREATE SCHEMA IF NOT EXISTS backtest;
CREATE SCHEMA IF NOT EXISTS ingest;
CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS research;
CREATE SCHEMA IF NOT EXISTS simulation;
"""


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

CREATE INDEX IF NOT EXISTS idx_market_daily_bar_adjust_asset_date_desc
    ON market_daily_bar (adjust_type, asset_id, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_market_daily_bar_adjust_date_desc
    ON market_daily_bar (adjust_type, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_feature_snapshot_trade_date
    ON feature_snapshot (trade_date, feature_set, feature_version);

CREATE INDEX IF NOT EXISTS idx_label_snapshot_trade_date
    ON label_snapshot (trade_date, label_set, label_version);

CREATE INDEX IF NOT EXISTS idx_label_snapshot_eval_lookup
    ON label_snapshot (trade_date, horizon, label_name, label_set, label_version, asset_id);

CREATE INDEX IF NOT EXISTS idx_label_snapshot_asset_history
    ON label_snapshot (asset_id, label_set, label_version, horizon, trade_date DESC);

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
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS finance;
CREATE SCHEMA IF NOT EXISTS fundamental;
CREATE SCHEMA IF NOT EXISTS event;
CREATE SCHEMA IF NOT EXISTS market;
CREATE SCHEMA IF NOT EXISTS factor;
CREATE SCHEMA IF NOT EXISTS backtest;
CREATE SCHEMA IF NOT EXISTS ingest;
CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS research;
CREATE SCHEMA IF NOT EXISTS simulation;

CREATE TABLE IF NOT EXISTS backtest.strategy_backtest_run (
    run_id text PRIMARY KEY,
    strategy_id text NOT NULL,
    strategy_name text NOT NULL,
    combo_scheme text NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    summary_json jsonb NOT NULL,
    config_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_kind text NOT NULL DEFAULT 'validated_combo_replay',
    source_paths jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS backtest.strategy_backtest_equity (
    run_id text NOT NULL REFERENCES backtest.strategy_backtest_run(run_id) ON DELETE CASCADE,
    trade_date date NOT NULL,
    row_index integer NOT NULL,
    equity numeric,
    drawdown numeric,
    daily_return numeric,
    turnover numeric,
    invested_weight numeric,
    row_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, trade_date, row_index)
);

CREATE TABLE IF NOT EXISTS backtest.strategy_backtest_position (
    run_id text NOT NULL REFERENCES backtest.strategy_backtest_run(run_id) ON DELETE CASCADE,
    trade_date date NOT NULL,
    row_index integer NOT NULL,
    asset_id text,
    weight numeric,
    rank numeric,
    row_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, trade_date, row_index)
);

CREATE TABLE IF NOT EXISTS backtest.strategy_backtest_trade (
    run_id text NOT NULL REFERENCES backtest.strategy_backtest_run(run_id) ON DELETE CASCADE,
    trade_date date NOT NULL,
    row_index integer NOT NULL,
    asset_id text,
    side text,
    weight numeric,
    realized_return numeric,
    row_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, trade_date, row_index)
);

CREATE INDEX IF NOT EXISTS idx_strategy_backtest_run_lookup
    ON backtest.strategy_backtest_run (strategy_id, combo_scheme, start_date, end_date, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_strategy_backtest_equity_run_date
    ON backtest.strategy_backtest_equity (run_id, trade_date);

CREATE INDEX IF NOT EXISTS idx_strategy_backtest_position_run_date
    ON backtest.strategy_backtest_position (run_id, trade_date);

CREATE INDEX IF NOT EXISTS idx_strategy_backtest_trade_run_date
    ON backtest.strategy_backtest_trade (run_id, trade_date);

CREATE TABLE IF NOT EXISTS research.stock_report_source (
    report_id text PRIMARY KEY,
    source_type text NOT NULL,
    source_name text,
    broker text,
    analyst text,
    report_title text NOT NULL,
    publish_date date,
    source_url text NOT NULL,
    public_access boolean NOT NULL DEFAULT true,
    copyright_note text,
    source_confidence numeric,
    raw_summary text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS research.stock_report_event (
    report_id text NOT NULL REFERENCES research.stock_report_source(report_id) ON DELETE CASCADE,
    asset_id text,
    ts_code text NOT NULL,
    stock_name text,
    industry_name text,
    report_date date,
    rating text,
    rating_change text,
    target_price numeric,
    target_upside numeric,
    forecast_revenue text,
    forecast_profit text,
    industry_view text,
    company_view text,
    risk_summary text,
    effective_start_date date,
    effective_end_date date,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (report_id, ts_code)
);

CREATE TABLE IF NOT EXISTS research.stock_report_manual_review (
    review_id text PRIMARY KEY,
    report_id text REFERENCES research.stock_report_source(report_id) ON DELETE SET NULL,
    trade_date date,
    asset_id text,
    ts_code text NOT NULL,
    stock_name text,
    industry_name text,
    candidate_source text NOT NULL,
    candidate_rank integer,
    mid_trend_funnel_score numeric,
    fundamental_hard_risk text,
    research_view text,
    broker_report_count_90d integer,
    latest_rating text,
    target_price numeric,
    target_upside numeric,
    institution_names text,
    industry_position_note text,
    product_position_note text,
    moat_or_scarcity_note text,
    negative_research_note text,
    valuation_note text,
    evidence_summary text,
    confidence text,
    review_status text NOT NULL DEFAULT 'pending',
    human_reviewer text,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS research.stock_report_search_task (
    task_id text PRIMARY KEY,
    trade_date date NOT NULL,
    asset_id text,
    ts_code text NOT NULL,
    stock_name text,
    industry_name text,
    candidate_rank integer,
    query_type text NOT NULL,
    source_domain text NOT NULL,
    search_query text NOT NULL,
    search_url text NOT NULL,
    priority integer NOT NULL DEFAULT 100,
    status text NOT NULL DEFAULT 'pending',
    last_error text,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS research.stock_report_feature_daily (
    trade_date date NOT NULL,
    asset_id text,
    ts_code text NOT NULL,
    stock_name text,
    report_count_30d integer NOT NULL DEFAULT 0,
    report_count_90d integer NOT NULL DEFAULT 0,
    latest_report_days integer,
    positive_rating_count integer NOT NULL DEFAULT 0,
    rating_upgrade_count integer NOT NULL DEFAULT 0,
    target_price_median numeric,
    target_upside_median numeric,
    target_price_dispersion numeric,
    broker_coverage_count integer NOT NULL DEFAULT 0,
    top_broker_coverage_count integer NOT NULL DEFAULT 0,
    negative_report_flag boolean NOT NULL DEFAULT false,
    research_support_score numeric,
    source_count integer NOT NULL DEFAULT 0,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, ts_code)
);

CREATE TABLE IF NOT EXISTS research.news_event_source (
    source_event_id text PRIMARY KEY,
    source_name text NOT NULL,
    source_channel text,
    title text NOT NULL,
    content text,
    published_at timestamptz NOT NULL,
    collected_at timestamptz NOT NULL DEFAULT now(),
    language text NOT NULL DEFAULT 'zh',
    url text,
    hash_key text NOT NULL,
    source_status text NOT NULL CHECK (source_status IN ('available', 'permission_denied', 'disabled')),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS research.news_event_mention (
    mention_id bigserial PRIMARY KEY,
    source_event_id text NOT NULL REFERENCES research.news_event_source(source_event_id),
    asset_id text,
    ts_code text,
    stock_name text,
    mention_role text,
    mention_confidence double precision,
    theme_name text,
    theme_confidence double precision,
    mapping_method text NOT NULL,
    trade_date date
);

CREATE TABLE IF NOT EXISTS research.news_feature_daily (
    trade_date date NOT NULL,
    asset_id text NOT NULL,
    ts_code text,
    news_count_1d integer NOT NULL DEFAULT 0,
    news_count_3d integer NOT NULL DEFAULT 0,
    news_count_5d integer NOT NULL DEFAULT 0,
    major_news_count_3d integer NOT NULL DEFAULT 0,
    source_diversity_3d integer NOT NULL DEFAULT 0,
    overnight_news_count integer NOT NULL DEFAULT 0,
    preopen_news_count integer NOT NULL DEFAULT 0,
    headline_keyword_positive_count_3d integer NOT NULL DEFAULT 0,
    headline_keyword_risk_count_3d integer NOT NULL DEFAULT 0,
    theme_news_burst_flag boolean NOT NULL DEFAULT false,
    news_first_seen_gap integer,
    news_attention_level text NOT NULL DEFAULT 'low',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (trade_date, asset_id)
);

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

CREATE TABLE IF NOT EXISTS core.asset_lifecycle_event (
    asset_id text NOT NULL,
    event_date date NOT NULL,
    event_type text NOT NULL,
    event_value text,
    source text NOT NULL,
    source_version text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, event_date, event_type, source_version)
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

CREATE TABLE IF NOT EXISTS market.index_constituent (
    index_id text NOT NULL,
    asset_id text NOT NULL,
    start_date date NOT NULL,
    end_date date,
    weight numeric,
    source text NOT NULL,
    source_version text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (index_id, asset_id, start_date, source_version)
);

CREATE TABLE IF NOT EXISTS market.trading_calendar (
    exchange text NOT NULL,
    trade_date date NOT NULL,
    is_open boolean NOT NULL,
    source text NOT NULL,
    source_version text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (exchange, trade_date, source_version)
);

CREATE TABLE IF NOT EXISTS market.adjustment_factor (
    asset_id text NOT NULL,
    trade_date date NOT NULL,
    raw_close numeric,
    qfq_close numeric,
    hfq_close numeric,
    qfq_factor numeric,
    hfq_factor numeric,
    source text NOT NULL,
    source_version text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, trade_date, source_version)
);

CREATE TABLE IF NOT EXISTS market.corporate_action (
    asset_id text NOT NULL,
    event_date date NOT NULL,
    action_type text NOT NULL,
    factor_before numeric,
    factor_after numeric,
    source text NOT NULL,
    source_version text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, event_date, action_type, source_version)
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

CREATE TABLE IF NOT EXISTS staging.baostock_stock_minute_bar (
    source_endpoint text NOT NULL,
    request_params jsonb NOT NULL,
    baostock_code text NOT NULL,
    raw_date text NOT NULL,
    raw_time text NOT NULL,
    trade_time timestamp without time zone NOT NULL,
    trade_date date NOT NULL,
    freq text NOT NULL CHECK (freq IN ('1min', '5min', '15min', '30min', '60min')),
    adjust_type text NOT NULL CHECK (adjust_type IN ('raw', 'qfq', 'hfq')),
    open numeric,
    high numeric,
    low numeric,
    close numeric,
    volume numeric,
    amount numeric,
    payload jsonb NOT NULL,
    payload_hash text NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_endpoint, baostock_code, trade_time, freq, adjust_type)
);

CREATE TABLE IF NOT EXISTS market.stock_minute_bar (
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    trade_time timestamp without time zone NOT NULL,
    trade_date date NOT NULL,
    freq text NOT NULL CHECK (freq IN ('1min', '5min', '15min', '30min', '60min')),
    adjust_type text NOT NULL CHECK (adjust_type IN ('raw', 'qfq', 'hfq')),
    open numeric,
    high numeric,
    low numeric,
    close numeric,
    volume numeric,
    amount numeric,
    source text NOT NULL CHECK (source IN ('baostock', 'tushare', 'akshare')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, asset_id, trade_time, freq, adjust_type, source)
) PARTITION BY RANGE (trade_date);

CREATE TABLE IF NOT EXISTS market.minute_bar_backfill_job (
    job_id text PRIMARY KEY,
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    baostock_code text NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    freq text NOT NULL CHECK (freq IN ('1min', '5min', '15min', '30min', '60min')),
    adjust_type text NOT NULL CHECK (adjust_type IN ('raw', 'qfq', 'hfq')),
    source text NOT NULL CHECK (source IN ('baostock', 'tushare', 'akshare')),
    status text NOT NULL CHECK (status IN ('pending', 'running', 'success', 'failed', 'skipped')) DEFAULT 'pending',
    attempt_count integer NOT NULL DEFAULT 0,
    row_count_market integer NOT NULL DEFAULT 0,
    row_count_staging integer NOT NULL DEFAULT 0,
    started_at timestamptz,
    finished_at timestamptz,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (ts_code, start_date, end_date, freq, adjust_type, source)
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

CREATE TABLE IF NOT EXISTS raw_akshare.enrichment_payload (
    id bigserial PRIMARY KEY,
    source_endpoint text NOT NULL,
    request_params jsonb NOT NULL,
    asset_id text,
    ts_code text,
    payload jsonb NOT NULL,
    payload_hash text NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fundamental.shareholder_count (
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    report_date date NOT NULL,
    announcement_date date,
    shareholder_count numeric,
    shareholder_count_change numeric,
    shareholder_count_change_pct numeric,
    source text NOT NULL,
    source_endpoint text NOT NULL,
    payload_hash text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, report_date, source)
);

CREATE TABLE IF NOT EXISTS fundamental.top10_holder (
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    report_period date NOT NULL,
    holder_name text NOT NULL,
    holder_type text,
    hold_amount numeric,
    hold_ratio numeric,
    hold_change numeric,
    rank integer,
    source text NOT NULL,
    source_endpoint text NOT NULL,
    payload_hash text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, report_period, holder_name, source)
);

CREATE TABLE IF NOT EXISTS fundamental.top10_float_holder (
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    report_period date NOT NULL,
    holder_name text NOT NULL,
    holder_type text,
    hold_amount numeric,
    hold_ratio numeric,
    hold_change numeric,
    rank integer,
    source text NOT NULL,
    source_endpoint text NOT NULL,
    payload_hash text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, report_period, holder_name, source)
);

CREATE TABLE IF NOT EXISTS event.shareholder_trade (
    event_id text PRIMARY KEY,
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    trade_date date,
    announcement_date date,
    holder_name text,
    trade_type text,
    trade_amount numeric,
    trade_ratio numeric,
    trade_price numeric,
    source text NOT NULL,
    source_endpoint text NOT NULL,
    payload_hash text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS event.stock_repurchase (
    event_id text PRIMARY KEY,
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    announcement_date date,
    progress_date date,
    progress text,
    repurchase_amount numeric,
    repurchase_amount_min numeric,
    repurchase_amount_max numeric,
    repurchase_price_min numeric,
    repurchase_price_max numeric,
    source text NOT NULL,
    source_endpoint text NOT NULL,
    payload_hash text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS event.institution_survey (
    event_id text PRIMARY KEY,
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    survey_date date,
    announcement_date date,
    institution_count numeric,
    institution_names text,
    survey_type text,
    summary text,
    source text NOT NULL,
    source_endpoint text NOT NULL,
    payload_hash text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS event.earnings_forecast (
    event_id text PRIMARY KEY,
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    announcement_date date NOT NULL,
    report_period date,
    forecast_type text,
    forecast_np_min numeric,
    forecast_np_max numeric,
    forecast_np_change_min numeric,
    forecast_np_change_max numeric,
    summary text,
    source text NOT NULL,
    source_endpoint text NOT NULL,
    payload_hash text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS event.earnings_express (
    event_id text PRIMARY KEY,
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    announcement_date date NOT NULL,
    report_period date,
    revenue numeric,
    revenue_yoy numeric,
    np_parent numeric,
    np_parent_yoy numeric,
    eps_basic numeric,
    roe_weighted numeric,
    source text NOT NULL,
    source_endpoint text NOT NULL,
    payload_hash text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS finance.main_business_composition (
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    report_period date NOT NULL,
    classify_type text NOT NULL,
    item_name text NOT NULL,
    revenue numeric,
    revenue_ratio numeric,
    cost numeric,
    gross_profit numeric,
    gross_margin numeric,
    source text NOT NULL,
    source_endpoint text NOT NULL,
    payload_hash text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, report_period, classify_type, item_name, source)
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

CREATE TABLE IF NOT EXISTS raw_baostock.daily_bar_payload (
    source_service text NOT NULL,
    source_table text NOT NULL,
    adjust_type text NOT NULL,
    trade_date date NOT NULL,
    asset_id text NOT NULL,
    payload jsonb NOT NULL,
    payload_hash text NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_service, source_table, adjust_type, trade_date, asset_id)
);

CREATE INDEX IF NOT EXISTS idx_raw_baostock_daily_bar_payload_lookup
    ON raw_baostock.daily_bar_payload (adjust_type, trade_date, asset_id);

CREATE INDEX IF NOT EXISTS idx_raw_baostock_daily_bar_payload_asset_date
    ON raw_baostock.daily_bar_payload (asset_id, trade_date DESC, adjust_type);

CREATE TABLE IF NOT EXISTS raw_baostock.industry_snapshot_payload (
    snapshot_date date NOT NULL,
    source_endpoint text NOT NULL,
    request_params jsonb NOT NULL,
    payload jsonb NOT NULL,
    payload_hash text NOT NULL,
    row_count integer NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_date, source_endpoint)
);

CREATE INDEX IF NOT EXISTS idx_raw_baostock_industry_snapshot_date
    ON raw_baostock.industry_snapshot_payload (snapshot_date, source_endpoint);

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

CREATE TABLE IF NOT EXISTS ops.p2_review_run (
    run_id text PRIMARY KEY,
    trade_date date NOT NULL,
    status text NOT NULL,
    source_rollup_status text,
    artifact_count integer NOT NULL DEFAULT 0,
    blocker_count integer NOT NULL DEFAULT 0,
    warning_count integer NOT NULL DEFAULT 0,
    json_path text NOT NULL,
    markdown_path text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.p2_review_section (
    run_id text NOT NULL REFERENCES ops.p2_review_run(run_id),
    section_group text NOT NULL,
    section_name text NOT NULL,
    status text NOT NULL,
    required boolean NOT NULL,
    exists boolean NOT NULL,
    source_artifact_path text NOT NULL,
    summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, section_group, section_name)
);

CREATE TABLE IF NOT EXISTS ops.data_run_manifest (
    manifest_id text PRIMARY KEY,
    run_id text NOT NULL,
    run_date date NOT NULL,
    trade_date date,
    module text NOT NULL,
    source text NOT NULL,
    tier text NOT NULL CHECK (tier IN ('tier1', 'tier2', 'tier3')),
    status text NOT NULL CHECK (status IN ('success', 'partial', 'skipped', 'failed', 'unavailable')),
    started_at timestamptz,
    ended_at timestamptz,
    duration_seconds numeric,
    row_count bigint,
    asset_count bigint,
    coverage_ratio numeric,
    latest_trade_date date,
    freshness_lag integer,
    warning_count integer NOT NULL DEFAULT 0,
    warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
    error_message text,
    artifact_path text,
    code_version text,
    config_version text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.review_item_snapshot (
    snapshot_id text PRIMARY KEY,
    run_id text NOT NULL,
    trade_date date NOT NULL,
    latest_trade_date date,
    asset_id text NOT NULL,
    stock_code text,
    stock_name text,
    digest_key text NOT NULL,
    source_type text NOT NULL,
    source_name text NOT NULL,
    source_rank integer,
    topn_rank integer,
    score_version text NOT NULL,
    score numeric,
    evidence_status text NOT NULL,
    missing_evidence_count integer NOT NULL DEFAULT 0,
    partial_evidence_count integer NOT NULL DEFAULT 0,
    warnings_count integer NOT NULL DEFAULT 0,
    review_item_payload jsonb NOT NULL,
    payload_hash text NOT NULL,
    schema_version text NOT NULL DEFAULT 'v1',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, digest_key)
);

CREATE TABLE IF NOT EXISTS ops.evidence_digest_snapshot (
    snapshot_id text PRIMARY KEY,
    run_id text NOT NULL,
    trade_date date NOT NULL,
    latest_trade_date date,
    asset_id text NOT NULL,
    stock_code text,
    stock_name text,
    digest_key text NOT NULL,
    overall_status text NOT NULL,
    missing_evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
    partial_evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
    sections_status jsonb NOT NULL DEFAULT '{}'::jsonb,
    digest_payload jsonb NOT NULL,
    payload_hash text NOT NULL,
    schema_version text NOT NULL DEFAULT 'v1',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, digest_key)
);

CREATE TABLE IF NOT EXISTS ops.operator_review_session (
    review_session_id text NOT NULL,
    review_date date NOT NULL,
    reviewer_id text NOT NULL,
    status text NOT NULL,
    decision_count integer NOT NULL DEFAULT 0,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    source_artifact_root text NOT NULL,
    json_path text NOT NULL,
    csv_path text NOT NULL,
    markdown_path text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (review_session_id)
);

CREATE TABLE IF NOT EXISTS ops.operator_decision_event (
    event_id text NOT NULL,
    review_session_id text NOT NULL REFERENCES ops.operator_review_session(review_session_id),
    review_date date NOT NULL,
    event_index integer NOT NULL,
    asset_id text NOT NULL,
    stock_code text,
    stock_name text,
    decision_label text NOT NULL,
    evidence_artifact_id text NOT NULL,
    evidence_path text NOT NULL,
    source_context text,
    requires_follow_up boolean NOT NULL DEFAULT false,
    follow_up_note text,
    notes text,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    source_artifact_path text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id)
);

CREATE TABLE IF NOT EXISTS ops.operator_decision_outcome_run (
    run_id text NOT NULL,
    review_start_date date NOT NULL,
    review_end_date date NOT NULL,
    status text NOT NULL,
    outcome_count integer NOT NULL DEFAULT 0,
    summary_count integer NOT NULL DEFAULT 0,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    json_path text NOT NULL,
    details_csv_path text NOT NULL,
    summary_csv_path text NOT NULL,
    markdown_path text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id)
);

CREATE TABLE IF NOT EXISTS ops.operator_decision_outcome_event (
    outcome_event_id text NOT NULL,
    run_id text NOT NULL REFERENCES ops.operator_decision_outcome_run(run_id),
    decision_event_id text NOT NULL,
    review_session_id text NOT NULL,
    review_date date,
    asset_id text NOT NULL,
    stock_code text,
    stock_name text,
    decision_label text NOT NULL,
    source_context text,
    outcome_status text NOT NULL,
    available_future_bars integer NOT NULL DEFAULT 0,
    base_trade_date date,
    base_close numeric,
    forward_returns jsonb NOT NULL DEFAULT '{}'::jsonb,
    max_high_returns jsonb NOT NULL DEFAULT '{}'::jsonb,
    max_low_drawdowns jsonb NOT NULL DEFAULT '{}'::jsonb,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    source_artifact_path text NOT NULL,
    outcome_artifact_path text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (outcome_event_id)
);

CREATE TABLE IF NOT EXISTS ops.operator_decision_outcome_analytics_run (
    run_id text NOT NULL,
    review_start_date date NOT NULL,
    review_end_date date NOT NULL,
    status text NOT NULL,
    source_outcome_count integer NOT NULL DEFAULT 0,
    group_count integer NOT NULL DEFAULT 0,
    diagnostic_count integer NOT NULL DEFAULT 0,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    json_path text NOT NULL,
    groups_csv_path text NOT NULL,
    diagnostics_csv_path text NOT NULL,
    markdown_path text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id)
);

CREATE TABLE IF NOT EXISTS ops.operator_decision_outcome_analytics_group (
    analytics_group_id text NOT NULL,
    run_id text NOT NULL REFERENCES ops.operator_decision_outcome_analytics_run(run_id),
    review_start_date date NOT NULL,
    review_end_date date NOT NULL,
    analytics_level text NOT NULL,
    group_value text NOT NULL,
    decision_label text,
    source_context text,
    review_session_id text,
    asset_id text,
    sample_count integer NOT NULL DEFAULT 0,
    complete_count integer NOT NULL DEFAULT 0,
    insufficient_data_count integer NOT NULL DEFAULT 0,
    follow_up_required_rate numeric,
    horizon_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    analytics_artifact_path text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (analytics_group_id)
);

CREATE TABLE IF NOT EXISTS ops.operator_experiment_proposal_run (
    run_id text NOT NULL,
    review_date date NOT NULL,
    status text NOT NULL,
    proposal_count integer NOT NULL DEFAULT 0,
    status_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    promotion_enabled boolean NOT NULL DEFAULT false,
    json_path text NOT NULL,
    proposals_csv_path text NOT NULL,
    markdown_path text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id)
);

CREATE TABLE IF NOT EXISTS ops.operator_experiment_proposal (
    proposal_id text NOT NULL,
    run_id text NOT NULL REFERENCES ops.operator_experiment_proposal_run(run_id),
    review_date date NOT NULL,
    proposal_title text NOT NULL,
    hypothesis text NOT NULL,
    source_p9_analytics_run_id text NOT NULL,
    source_analytics_group_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_diagnostic_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_artifact_paths jsonb NOT NULL DEFAULT '[]'::jsonb,
    expected_validation_method text NOT NULL,
    risk_notes text NOT NULL,
    reviewer_id text NOT NULL,
    status text NOT NULL,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    promotion_enabled boolean NOT NULL DEFAULT false,
    proposal_artifact_path text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (proposal_id)
);

CREATE TABLE IF NOT EXISTS ops.operator_experiment_replay_run (
    run_id text NOT NULL,
    replay_start_date date NOT NULL,
    replay_end_date date NOT NULL,
    status text NOT NULL,
    result_count integer NOT NULL DEFAULT 0,
    status_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    production_write_enabled boolean NOT NULL DEFAULT false,
    json_path text NOT NULL,
    results_csv_path text NOT NULL,
    markdown_path text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id)
);

CREATE TABLE IF NOT EXISTS ops.operator_experiment_replay_result (
    replay_result_id text NOT NULL,
    run_id text NOT NULL REFERENCES ops.operator_experiment_replay_run(run_id),
    proposal_id text NOT NULL,
    source_p10_proposal_run_id text NOT NULL,
    source_p9_analytics_run_id text NOT NULL,
    replay_start_date date NOT NULL,
    replay_end_date date NOT NULL,
    replay_input_artifact_paths jsonb NOT NULL DEFAULT '[]'::jsonb,
    validation_method text NOT NULL,
    replay_status text NOT NULL,
    sample_count integer NOT NULL DEFAULT 0,
    passed_count integer NOT NULL DEFAULT 0,
    failed_count integer NOT NULL DEFAULT 0,
    metric_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    failure_reason text NOT NULL,
    defer_reason text NOT NULL,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    production_write_enabled boolean NOT NULL DEFAULT false,
    replay_artifact_path text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (replay_result_id)
);

CREATE TABLE IF NOT EXISTS ops.operator_shadow_watchlist_run (
    run_id text NOT NULL,
    review_date date NOT NULL,
    status text NOT NULL,
    candidate_count integer NOT NULL DEFAULT 0,
    status_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    production_watchlist_enabled boolean NOT NULL DEFAULT false,
    production_write_enabled boolean NOT NULL DEFAULT false,
    json_path text NOT NULL,
    candidates_csv_path text NOT NULL,
    markdown_path text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id)
);

CREATE TABLE IF NOT EXISTS ops.operator_shadow_watchlist_candidate (
    shadow_candidate_id text NOT NULL,
    run_id text NOT NULL REFERENCES ops.operator_shadow_watchlist_run(run_id),
    replay_result_id text NOT NULL,
    source_p11_replay_run_id text NOT NULL,
    source_p10_proposal_run_id text NOT NULL,
    source_p9_analytics_run_id text NOT NULL,
    candidate_date date NOT NULL,
    asset_id text NOT NULL,
    stock_code text NOT NULL,
    stock_name text NOT NULL,
    shadow_layer text NOT NULL,
    candidate_reason text NOT NULL,
    evidence_artifact_paths jsonb NOT NULL DEFAULT '[]'::jsonb,
    metric_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    reviewer_id text NOT NULL,
    status text NOT NULL,
    review_notes text NOT NULL,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    production_watchlist_enabled boolean NOT NULL DEFAULT false,
    production_write_enabled boolean NOT NULL DEFAULT false,
    shadow_artifact_path text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (shadow_candidate_id)
);

CREATE TABLE IF NOT EXISTS ops.operator_shadow_watchlist_outcome_run (
    run_id text NOT NULL,
    review_date date NOT NULL,
    status text NOT NULL,
    outcome_count integer NOT NULL DEFAULT 0,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    production_watchlist_enabled boolean NOT NULL DEFAULT false,
    production_write_enabled boolean NOT NULL DEFAULT false,
    json_path text NOT NULL,
    details_csv_path text NOT NULL,
    markdown_path text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id)
);

CREATE TABLE IF NOT EXISTS ops.operator_shadow_watchlist_outcome_candidate (
    shadow_outcome_id text NOT NULL,
    run_id text NOT NULL REFERENCES ops.operator_shadow_watchlist_outcome_run(run_id),
    shadow_candidate_id text NOT NULL,
    source_p12_shadow_run_id text NOT NULL,
    replay_result_id text NOT NULL,
    source_p11_replay_run_id text NOT NULL,
    source_p10_proposal_run_id text NOT NULL,
    source_p9_analytics_run_id text NOT NULL,
    candidate_date date NOT NULL,
    asset_id text NOT NULL,
    stock_code text NOT NULL,
    stock_name text NOT NULL,
    shadow_layer text NOT NULL,
    shadow_status text NOT NULL,
    candidate_reason text NOT NULL,
    outcome_status text NOT NULL,
    available_future_bars integer NOT NULL DEFAULT 0,
    base_trade_date date,
    base_close numeric,
    forward_returns jsonb NOT NULL DEFAULT '{}'::jsonb,
    max_high_returns jsonb NOT NULL DEFAULT '{}'::jsonb,
    max_low_drawdowns jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_shadow_artifact_path text NOT NULL,
    outcome_artifact_path text NOT NULL,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    production_watchlist_enabled boolean NOT NULL DEFAULT false,
    production_write_enabled boolean NOT NULL DEFAULT false,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (shadow_outcome_id)
);

CREATE TABLE IF NOT EXISTS ops.operator_shadow_watchlist_outcome_analytics_run (
    run_id text PRIMARY KEY,
    review_start_date date NOT NULL,
    review_end_date date NOT NULL,
    status text NOT NULL,
    group_by jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_outcome_count integer NOT NULL DEFAULT 0,
    group_count integer NOT NULL DEFAULT 0,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    production_watchlist_enabled boolean NOT NULL DEFAULT false,
    production_write_enabled boolean NOT NULL DEFAULT false,
    json_path text NOT NULL,
    groups_csv_path text NOT NULL,
    markdown_path text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.operator_shadow_watchlist_outcome_analytics_group (
    analytics_group_id text PRIMARY KEY,
    run_id text NOT NULL REFERENCES ops.operator_shadow_watchlist_outcome_analytics_run(run_id) ON DELETE CASCADE,
    review_start_date date NOT NULL,
    review_end_date date NOT NULL,
    group_key text NOT NULL,
    shadow_layer text NOT NULL,
    shadow_status text NOT NULL,
    sample_count integer NOT NULL DEFAULT 0,
    complete_count integer NOT NULL DEFAULT 0,
    insufficient_data_count integer NOT NULL DEFAULT 0,
    source_p12_shadow_run_count integer NOT NULL DEFAULT 0,
    source_p11_replay_run_count integer NOT NULL DEFAULT 0,
    source_p10_proposal_run_count integer NOT NULL DEFAULT 0,
    source_p9_analytics_run_count integer NOT NULL DEFAULT 0,
    horizon_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    analytics_artifact_path text NOT NULL,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    production_watchlist_enabled boolean NOT NULL DEFAULT false,
    production_write_enabled boolean NOT NULL DEFAULT false,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.operator_shadow_analytics_review_run (
    run_id text PRIMARY KEY,
    review_start_date date NOT NULL,
    review_end_date date NOT NULL,
    status text NOT NULL,
    reviewer_id text NOT NULL,
    source_p14_analytics_run_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    thresholds jsonb NOT NULL DEFAULT '{}'::jsonb,
    group_count integer NOT NULL DEFAULT 0,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    production_watchlist_enabled boolean NOT NULL DEFAULT false,
    production_write_enabled boolean NOT NULL DEFAULT false,
    json_path text NOT NULL,
    groups_csv_path text NOT NULL,
    markdown_path text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.operator_shadow_analytics_review_group (
    review_group_id text PRIMARY KEY,
    run_id text NOT NULL REFERENCES ops.operator_shadow_analytics_review_run(run_id) ON DELETE CASCADE,
    review_start_date date NOT NULL,
    review_end_date date NOT NULL,
    source_p14_analytics_group_id text NOT NULL,
    source_p14_analytics_run_id text NOT NULL,
    group_key text NOT NULL,
    shadow_layer text NOT NULL,
    shadow_status text NOT NULL,
    sample_count integer NOT NULL DEFAULT 0,
    complete_count integer NOT NULL DEFAULT 0,
    insufficient_data_count integer NOT NULL DEFAULT 0,
    horizon_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    review_status text NOT NULL,
    review_bucket text NOT NULL,
    evidence_summary text NOT NULL,
    risk_notes text NOT NULL,
    next_research_question text NOT NULL,
    review_artifact_path text NOT NULL,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    production_watchlist_enabled boolean NOT NULL DEFAULT false,
    production_write_enabled boolean NOT NULL DEFAULT false,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.operator_shadow_review_decision_run (
    run_id text PRIMARY KEY,
    decision_date date NOT NULL,
    status text NOT NULL,
    operator_id text NOT NULL,
    source_p15_review_run_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    group_count integer NOT NULL DEFAULT 0,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    production_watchlist_enabled boolean NOT NULL DEFAULT false,
    production_write_enabled boolean NOT NULL DEFAULT false,
    json_path text NOT NULL,
    groups_csv_path text NOT NULL,
    markdown_path text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.operator_shadow_review_decision_group (
    decision_group_id text PRIMARY KEY,
    run_id text NOT NULL REFERENCES ops.operator_shadow_review_decision_run(run_id) ON DELETE CASCADE,
    decision_date date NOT NULL,
    source_p15_review_group_id text NOT NULL,
    source_p15_review_run_id text NOT NULL,
    source_p14_analytics_group_id text NOT NULL,
    source_p14_analytics_run_id text NOT NULL,
    group_key text NOT NULL,
    shadow_layer text NOT NULL,
    shadow_status text NOT NULL,
    sample_count integer NOT NULL DEFAULT 0,
    complete_count integer NOT NULL DEFAULT 0,
    insufficient_data_count integer NOT NULL DEFAULT 0,
    review_status text NOT NULL,
    review_bucket text NOT NULL,
    decision_status text NOT NULL,
    decision_bucket text NOT NULL,
    decision_reason text NOT NULL,
    required_next_action text NOT NULL,
    evidence_summary text NOT NULL,
    risk_notes text NOT NULL,
    next_research_question text NOT NULL,
    decision_artifact_path text NOT NULL,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    production_watchlist_enabled boolean NOT NULL DEFAULT false,
    production_write_enabled boolean NOT NULL DEFAULT false,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.operator_shadow_follow_up_run (
    run_id text PRIMARY KEY,
    follow_up_date date NOT NULL,
    status text NOT NULL,
    operator_id text NOT NULL,
    source_p16_decision_run_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    item_count integer NOT NULL DEFAULT 0,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    production_watchlist_enabled boolean NOT NULL DEFAULT false,
    production_write_enabled boolean NOT NULL DEFAULT false,
    json_path text NOT NULL,
    items_csv_path text NOT NULL,
    markdown_path text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.operator_shadow_follow_up_item (
    follow_up_item_id text PRIMARY KEY,
    run_id text NOT NULL REFERENCES ops.operator_shadow_follow_up_run(run_id) ON DELETE CASCADE,
    follow_up_date date NOT NULL,
    source_p16_decision_group_id text NOT NULL,
    source_p16_decision_run_id text NOT NULL,
    source_p15_review_group_id text NOT NULL,
    source_p15_review_run_id text NOT NULL,
    source_p14_analytics_group_id text NOT NULL,
    source_p14_analytics_run_id text NOT NULL,
    group_key text NOT NULL,
    shadow_layer text NOT NULL,
    shadow_status text NOT NULL,
    sample_count integer NOT NULL DEFAULT 0,
    complete_count integer NOT NULL DEFAULT 0,
    insufficient_data_count integer NOT NULL DEFAULT 0,
    review_status text NOT NULL,
    review_bucket text NOT NULL,
    decision_status text NOT NULL,
    decision_bucket text NOT NULL,
    follow_up_status text NOT NULL,
    priority_bucket text NOT NULL,
    required_input text NOT NULL,
    follow_up_reason text NOT NULL,
    decision_reason text NOT NULL,
    required_next_action text NOT NULL,
    evidence_summary text NOT NULL,
    risk_notes text NOT NULL,
    next_research_question text NOT NULL,
    follow_up_artifact_path text NOT NULL,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    production_watchlist_enabled boolean NOT NULL DEFAULT false,
    production_write_enabled boolean NOT NULL DEFAULT false,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.operator_shadow_follow_up_resolution_run (
    run_id text PRIMARY KEY,
    resolution_date date NOT NULL,
    status text NOT NULL,
    operator_id text NOT NULL,
    source_p17_follow_up_run_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    item_count integer NOT NULL DEFAULT 0,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    production_watchlist_enabled boolean NOT NULL DEFAULT false,
    production_write_enabled boolean NOT NULL DEFAULT false,
    json_path text NOT NULL,
    items_csv_path text NOT NULL,
    markdown_path text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.operator_shadow_follow_up_resolution_item (
    resolution_item_id text PRIMARY KEY,
    run_id text NOT NULL REFERENCES ops.operator_shadow_follow_up_resolution_run(run_id) ON DELETE CASCADE,
    resolution_date date NOT NULL,
    source_p17_follow_up_item_id text NOT NULL,
    source_p17_follow_up_run_id text NOT NULL,
    source_p16_decision_group_id text NOT NULL,
    source_p16_decision_run_id text NOT NULL,
    source_p15_review_group_id text NOT NULL,
    source_p15_review_run_id text NOT NULL,
    source_p14_analytics_group_id text NOT NULL,
    source_p14_analytics_run_id text NOT NULL,
    group_key text NOT NULL,
    shadow_layer text NOT NULL,
    shadow_status text NOT NULL,
    sample_count integer NOT NULL DEFAULT 0,
    complete_count integer NOT NULL DEFAULT 0,
    insufficient_data_count integer NOT NULL DEFAULT 0,
    review_status text NOT NULL,
    review_bucket text NOT NULL,
    decision_status text NOT NULL,
    decision_bucket text NOT NULL,
    follow_up_status text NOT NULL,
    priority_bucket text NOT NULL,
    required_input text NOT NULL,
    resolution_status text NOT NULL,
    resolution_bucket text NOT NULL,
    recommended_resolution_action text NOT NULL,
    resolution_reason text NOT NULL,
    follow_up_reason text NOT NULL,
    decision_reason text NOT NULL,
    required_next_action text NOT NULL,
    evidence_summary text NOT NULL,
    risk_notes text NOT NULL,
    next_research_question text NOT NULL,
    resolution_artifact_path text NOT NULL,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    production_watchlist_enabled boolean NOT NULL DEFAULT false,
    production_write_enabled boolean NOT NULL DEFAULT false,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS simulation.virtual_portfolio_state_daily (
    portfolio_id text NOT NULL,
    trade_date date NOT NULL,
    strategy_id text NOT NULL,
    review_status text NOT NULL,
    cash numeric,
    market_value numeric,
    equity numeric,
    drawdown numeric,
    exposure_pct numeric,
    open_position_count integer NOT NULL DEFAULT 0,
    risk_level text,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    human_confirmation_required boolean NOT NULL DEFAULT true,
    source_artifact_path text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (portfolio_id, trade_date, strategy_id)
);

CREATE TABLE IF NOT EXISTS simulation.virtual_portfolio_position_daily (
    portfolio_id text NOT NULL,
    trade_date date NOT NULL,
    strategy_id text NOT NULL,
    asset_id text,
    stock_code text NOT NULL,
    stock_name text,
    quantity numeric,
    market_value numeric,
    weight numeric,
    cost_basis numeric,
    unrealized_pnl numeric,
    source_artifact_path text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (portfolio_id, trade_date, strategy_id, stock_code)
);

CREATE SCHEMA IF NOT EXISTS watchlist;

CREATE TABLE IF NOT EXISTS watchlist.watchlist_item (
    watchlist_id text NOT NULL,
    asset_id text NOT NULL,
    stock_code text NOT NULL,
    stock_name text NOT NULL,
    priority integer NOT NULL DEFAULT 100,
    active boolean NOT NULL DEFAULT true,
    note text,
    source text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (watchlist_id, asset_id)
);

CREATE TABLE IF NOT EXISTS watchlist.watchlist_daily_signal (
    watchlist_id text NOT NULL,
    trade_date date NOT NULL,
    asset_id text NOT NULL,
    stock_code text NOT NULL,
    stock_name text NOT NULL,
    priority integer NOT NULL DEFAULT 100,
    signal_score numeric,
    primary_signal text NOT NULL,
    signal_tags jsonb NOT NULL DEFAULT '[]'::jsonb,
    risk_tags jsonb NOT NULL DEFAULT '[]'::jsonb,
    must_watch boolean NOT NULL DEFAULT false,
    reason_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    output_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (watchlist_id, trade_date, asset_id)
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

CREATE TABLE IF NOT EXISTS factor.stock_technical_features_daily (
    trade_date date NOT NULL,
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    adjust_type text NOT NULL CHECK (adjust_type IN ('raw', 'qfq', 'hfq')),
    source text NOT NULL,
    source_data_version text NOT NULL,
    calc_version text NOT NULL,
    ma5 numeric,
    ma10 numeric,
    ma20 numeric,
    ma60 numeric,
    ma120 numeric,
    ema12 numeric,
    ema26 numeric,
    macd_dif numeric,
    macd_dea numeric,
    macd_hist numeric,
    rsi6 numeric,
    rsi12 numeric,
    rsi24 numeric,
    boll_upper_20 numeric,
    boll_mid_20 numeric,
    boll_lower_20 numeric,
    atr14 numeric,
    cci14 numeric,
    kdj_k numeric,
    kdj_d numeric,
    kdj_j numeric,
    adx14 numeric,
    obv numeric,
    ret_1d numeric,
    ret_20d numeric,
    close_position_in_day numeric,
    amount_vs_20d numeric,
    high_to_close_drawdown numeric,
    volatility_5d numeric,
    max_drawdown_20d numeric,
    atr_pct14 numeric,
    computed_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, asset_id, adjust_type, source_data_version, calc_version)
);

CREATE TABLE IF NOT EXISTS factor.stock_intraday_features_daily (
    trade_date date NOT NULL,
    asset_id text NOT NULL,
    freq text NOT NULL CHECK (freq IN ('1min', '5min', '15min', '30min', '60min')),
    adjust_type text NOT NULL CHECK (adjust_type IN ('raw', 'qfq', 'hfq')),
    feature_name text NOT NULL,
    feature_value numeric,
    calc_version text NOT NULL,
    source text NOT NULL,
    source_data_version text NOT NULL,
    computed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, asset_id, freq, adjust_type, feature_name, calc_version)
);

CREATE TABLE IF NOT EXISTS factor.industry_intraday_features_daily (
    trade_date date NOT NULL,
    industry_system text NOT NULL,
    industry_code text NOT NULL,
    industry_name text NOT NULL,
    freq text NOT NULL CHECK (freq IN ('1min', '5min', '15min', '30min', '60min')),
    adjust_type text NOT NULL CHECK (adjust_type IN ('raw', 'qfq', 'hfq')),
    feature_name text NOT NULL,
    feature_value numeric,
    calc_version text NOT NULL,
    source text NOT NULL,
    source_data_version text NOT NULL,
    computed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (
        trade_date,
        industry_system,
        industry_code,
        freq,
        adjust_type,
        feature_name,
        calc_version
    )
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

CREATE TABLE IF NOT EXISTS market.lhb_top_list_daily (
    trade_date date NOT NULL,
    ts_code text NOT NULL,
    name text,
    close numeric,
    pct_change numeric,
    turnover_rate numeric,
    amount numeric,
    l_sell numeric,
    l_buy numeric,
    l_amount numeric,
    net_amount numeric,
    net_rate numeric,
    amount_rate numeric,
    float_values numeric,
    reason text,
    source text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, ts_code, reason, source)
);

CREATE TABLE IF NOT EXISTS market.lhb_top_inst_daily (
    trade_date date NOT NULL,
    ts_code text NOT NULL,
    exalter text NOT NULL,
    buy numeric,
    buy_rate numeric,
    sell numeric,
    sell_rate numeric,
    net_buy numeric,
    reason text,
    source text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, ts_code, exalter, source)
);

CREATE TABLE IF NOT EXISTS factor.lhb_event_features_daily (
    trade_date date NOT NULL,
    ts_code text NOT NULL,
    on_lhb boolean NOT NULL DEFAULT false,
    lhb_reason text,
    lhb_net_buy_amount numeric,
    lhb_net_buy_ratio numeric,
    lhb_buy_amount numeric,
    lhb_sell_amount numeric,
    institution_net_buy numeric,
    top_seat_concentration numeric,
    repeat_on_list_count_3d integer,
    repeat_on_list_count_5d integer,
    lhb_after_limit_up boolean NOT NULL DEFAULT false,
    lhb_after_break_limit boolean NOT NULL DEFAULT false,
    lhb_after_reversal boolean NOT NULL DEFAULT false,
    lhb_one_day_pump_risk numeric,
    source text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, ts_code, source)
);

CREATE INDEX IF NOT EXISTS idx_finance_indicator_quarter_pit
    ON finance.indicator_quarter (asset_id, announcement_date DESC, report_period DESC);

CREATE INDEX IF NOT EXISTS idx_finance_income_statement_pit
    ON finance.income_statement (asset_id, announcement_date DESC, report_period DESC);

CREATE INDEX IF NOT EXISTS idx_finance_balance_sheet_pit
    ON finance.balance_sheet (asset_id, announcement_date DESC, report_period DESC);

CREATE INDEX IF NOT EXISTS idx_finance_cash_flow_pit
    ON finance.cash_flow (asset_id, announcement_date DESC, report_period DESC);

CREATE INDEX IF NOT EXISTS idx_raw_akshare_enrichment_payload_endpoint
    ON raw_akshare.enrichment_payload (source_endpoint, fetched_at DESC);

CREATE INDEX IF NOT EXISTS idx_fundamental_shareholder_count_asset_date
    ON fundamental.shareholder_count (asset_id, report_date DESC);

CREATE INDEX IF NOT EXISTS idx_event_shareholder_trade_asset_date
    ON event.shareholder_trade (asset_id, trade_date DESC, announcement_date DESC);

CREATE INDEX IF NOT EXISTS idx_event_stock_repurchase_asset_date
    ON event.stock_repurchase (asset_id, announcement_date DESC);

CREATE INDEX IF NOT EXISTS idx_event_institution_survey_asset_date
    ON event.institution_survey (asset_id, survey_date DESC);

CREATE INDEX IF NOT EXISTS idx_event_earnings_forecast_asset_date
    ON event.earnings_forecast (asset_id, announcement_date DESC);

CREATE INDEX IF NOT EXISTS idx_event_earnings_express_asset_date
    ON event.earnings_express (asset_id, announcement_date DESC);

CREATE INDEX IF NOT EXISTS idx_finance_main_business_composition_asset_period
    ON finance.main_business_composition (asset_id, report_period DESC);

CREATE INDEX IF NOT EXISTS idx_core_industry_membership_window
    ON core.industry_membership (asset_id, industry_system, start_date, end_date);

CREATE INDEX IF NOT EXISTS idx_core_asset_lifecycle_event_asset_date
    ON core.asset_lifecycle_event (asset_id, event_date, event_type);

CREATE INDEX IF NOT EXISTS idx_core_asset_status_daily_lookup
    ON core.asset_status_daily (trade_date, asset_id);

CREATE INDEX IF NOT EXISTS idx_market_index_daily_bar_date
    ON market.index_daily_bar (trade_date, index_id);

CREATE INDEX IF NOT EXISTS idx_market_index_constituent_lookup
    ON market.index_constituent (index_id, start_date, end_date, asset_id);

CREATE INDEX IF NOT EXISTS idx_market_trading_calendar_open_date
    ON market.trading_calendar (exchange, is_open, trade_date);

CREATE INDEX IF NOT EXISTS idx_market_adjustment_factor_date
    ON market.adjustment_factor (trade_date, asset_id);

CREATE INDEX IF NOT EXISTS idx_market_corporate_action_asset_date
    ON market.corporate_action (asset_id, event_date);

CREATE INDEX IF NOT EXISTS idx_market_industry_daily_bar_date
    ON market.industry_daily_bar (trade_date, industry_system, industry_code);

CREATE INDEX IF NOT EXISTS idx_market_industry_daily_bar_system_date_desc
    ON market.industry_daily_bar (industry_system, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_staging_baostock_stock_minute_bar_date
    ON staging.baostock_stock_minute_bar (trade_date, freq, adjust_type);

CREATE INDEX IF NOT EXISTS idx_market_stock_minute_bar_asset_time
    ON market.stock_minute_bar (asset_id, trade_time);

CREATE INDEX IF NOT EXISTS idx_market_stock_minute_bar_date_freq_adjust
    ON market.stock_minute_bar (trade_date, freq, adjust_type);

CREATE INDEX IF NOT EXISTS idx_market_stock_minute_bar_time_freq
    ON market.stock_minute_bar (trade_time, freq);

CREATE INDEX IF NOT EXISTS idx_market_minute_bar_backfill_job_status
    ON market.minute_bar_backfill_job (status, start_date, end_date);

CREATE INDEX IF NOT EXISTS idx_market_minute_bar_backfill_job_period
    ON market.minute_bar_backfill_job (start_date, end_date, freq, adjust_type, source);

CREATE INDEX IF NOT EXISTS idx_ingest_batch_job_status
    ON ingest.batch_job (dataset, status, year, quarter, offset_value);

CREATE INDEX IF NOT EXISTS idx_ingest_backfill_task_status
    ON ingest.backfill_task (dataset, status, start_date);

CREATE INDEX IF NOT EXISTS idx_ingest_backfill_task_run_status
    ON ingest.backfill_task (run_id, status, start_date);

CREATE INDEX IF NOT EXISTS idx_ops_p2_review_run_trade_date
    ON ops.p2_review_run (trade_date, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_ops_p2_review_run_status_date
    ON ops.p2_review_run (status, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_ops_p2_review_section_group_status
    ON ops.p2_review_section (section_group, status);

CREATE INDEX IF NOT EXISTS idx_data_run_manifest_run
    ON ops.data_run_manifest (run_id, tier, module);

CREATE INDEX IF NOT EXISTS idx_data_run_manifest_trade_date
    ON ops.data_run_manifest (trade_date DESC, tier, status);

CREATE INDEX IF NOT EXISTS idx_review_item_snapshot_run
    ON ops.review_item_snapshot (run_id, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_review_item_snapshot_digest
    ON ops.review_item_snapshot (digest_key);

CREATE INDEX IF NOT EXISTS idx_review_item_snapshot_asset
    ON ops.review_item_snapshot (asset_id, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_evidence_digest_snapshot_run
    ON ops.evidence_digest_snapshot (run_id, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_evidence_digest_snapshot_digest
    ON ops.evidence_digest_snapshot (digest_key);

CREATE INDEX IF NOT EXISTS idx_evidence_digest_snapshot_asset
    ON ops.evidence_digest_snapshot (asset_id, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_ops_operator_review_session_date
    ON ops.operator_review_session (review_date DESC, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_ops_operator_decision_event_asset_date
    ON ops.operator_decision_event (asset_id, review_date DESC);

CREATE INDEX IF NOT EXISTS idx_ops_operator_decision_event_label_date
    ON ops.operator_decision_event (decision_label, review_date DESC);

CREATE INDEX IF NOT EXISTS idx_ops_operator_decision_outcome_run_date
    ON ops.operator_decision_outcome_run (review_end_date DESC, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_ops_operator_decision_outcome_event_asset_date
    ON ops.operator_decision_outcome_event (asset_id, review_date DESC);

CREATE INDEX IF NOT EXISTS idx_ops_operator_decision_outcome_event_decision
    ON ops.operator_decision_outcome_event (decision_event_id);

CREATE INDEX IF NOT EXISTS idx_ops_operator_decision_outcome_analytics_run_date
    ON ops.operator_decision_outcome_analytics_run (review_end_date DESC, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_ops_operator_decision_outcome_analytics_group_level_date
    ON ops.operator_decision_outcome_analytics_group (analytics_level, review_end_date DESC);

CREATE INDEX IF NOT EXISTS idx_ops_operator_decision_outcome_analytics_group_run
    ON ops.operator_decision_outcome_analytics_group (run_id);

CREATE INDEX IF NOT EXISTS idx_ops_operator_experiment_proposal_run_date
    ON ops.operator_experiment_proposal_run (review_date DESC, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_ops_operator_experiment_proposal_status_date
    ON ops.operator_experiment_proposal (status, review_date DESC);

CREATE INDEX IF NOT EXISTS idx_ops_operator_experiment_proposal_source_run
    ON ops.operator_experiment_proposal (source_p9_analytics_run_id);

CREATE INDEX IF NOT EXISTS idx_ops_operator_experiment_replay_run_date
    ON ops.operator_experiment_replay_run (replay_end_date DESC, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_ops_operator_experiment_replay_status_date
    ON ops.operator_experiment_replay_result (replay_status, replay_end_date DESC);

CREATE INDEX IF NOT EXISTS idx_ops_operator_experiment_replay_source_proposal
    ON ops.operator_experiment_replay_result (proposal_id, source_p10_proposal_run_id);

CREATE INDEX IF NOT EXISTS idx_ops_operator_experiment_replay_source_p9
    ON ops.operator_experiment_replay_result (source_p9_analytics_run_id);

CREATE INDEX IF NOT EXISTS idx_ops_operator_shadow_watchlist_run_date
    ON ops.operator_shadow_watchlist_run (review_date DESC, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_ops_operator_shadow_watchlist_status_date
    ON ops.operator_shadow_watchlist_candidate (status, candidate_date DESC);

CREATE INDEX IF NOT EXISTS idx_ops_operator_shadow_watchlist_asset_date
    ON ops.operator_shadow_watchlist_candidate (asset_id, candidate_date DESC);

CREATE INDEX IF NOT EXISTS idx_ops_operator_shadow_watchlist_source_replay
    ON ops.operator_shadow_watchlist_candidate (replay_result_id, source_p11_replay_run_id);

CREATE INDEX IF NOT EXISTS idx_research_stock_report_source_publish
    ON research.stock_report_source (publish_date DESC, source_type);

CREATE INDEX IF NOT EXISTS idx_research_stock_report_event_asset_date
    ON research.stock_report_event (ts_code, report_date DESC);

CREATE INDEX IF NOT EXISTS idx_research_stock_report_manual_review_status
    ON research.stock_report_manual_review (review_status, trade_date DESC, candidate_rank);

CREATE INDEX IF NOT EXISTS idx_research_stock_report_manual_review_asset
    ON research.stock_report_manual_review (ts_code, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_research_stock_report_search_task_status
    ON research.stock_report_search_task (status, trade_date DESC, priority, source_domain);

CREATE INDEX IF NOT EXISTS idx_research_stock_report_search_task_asset
    ON research.stock_report_search_task (ts_code, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_research_stock_report_feature_daily_score
    ON research.stock_report_feature_daily (trade_date DESC, research_support_score DESC);

CREATE INDEX IF NOT EXISTS idx_research_stock_report_feature_daily_asset
    ON research.stock_report_feature_daily (ts_code, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_ops_operator_shadow_outcome_run_date
    ON ops.operator_shadow_watchlist_outcome_run (review_date DESC, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_ops_operator_shadow_outcome_status_date
    ON ops.operator_shadow_watchlist_outcome_candidate (outcome_status, candidate_date DESC);

CREATE INDEX IF NOT EXISTS idx_ops_operator_shadow_outcome_asset_date
    ON ops.operator_shadow_watchlist_outcome_candidate (asset_id, candidate_date DESC);

CREATE INDEX IF NOT EXISTS idx_ops_operator_shadow_outcome_source_candidate
    ON ops.operator_shadow_watchlist_outcome_candidate (shadow_candidate_id, source_p12_shadow_run_id);

CREATE INDEX IF NOT EXISTS idx_operator_shadow_watchlist_outcome_analytics_group_date
    ON ops.operator_shadow_watchlist_outcome_analytics_group (review_end_date DESC, sample_count DESC);

CREATE INDEX IF NOT EXISTS idx_operator_shadow_watchlist_outcome_analytics_group_key
    ON ops.operator_shadow_watchlist_outcome_analytics_group (group_key, review_end_date DESC);

CREATE INDEX IF NOT EXISTS idx_operator_shadow_analytics_review_group_date
    ON ops.operator_shadow_analytics_review_group (review_end_date DESC, review_status, sample_count DESC);

CREATE INDEX IF NOT EXISTS idx_operator_shadow_analytics_review_group_status
    ON ops.operator_shadow_analytics_review_group (review_status, review_end_date DESC);

CREATE INDEX IF NOT EXISTS idx_operator_shadow_review_decision_group_date
    ON ops.operator_shadow_review_decision_group (decision_date DESC, decision_status, sample_count DESC);

CREATE INDEX IF NOT EXISTS idx_operator_shadow_review_decision_group_status
    ON ops.operator_shadow_review_decision_group (decision_status, decision_date DESC);

CREATE INDEX IF NOT EXISTS idx_operator_shadow_follow_up_item_date
    ON ops.operator_shadow_follow_up_item (follow_up_date DESC, follow_up_status, priority_bucket);

CREATE INDEX IF NOT EXISTS idx_operator_shadow_follow_up_item_status
    ON ops.operator_shadow_follow_up_item (follow_up_status, priority_bucket, follow_up_date DESC);

CREATE INDEX IF NOT EXISTS idx_operator_shadow_follow_up_resolution_item_date
    ON ops.operator_shadow_follow_up_resolution_item (
        resolution_date DESC, resolution_status, resolution_bucket, priority_bucket
    );

CREATE INDEX IF NOT EXISTS idx_operator_shadow_follow_up_resolution_item_status
    ON ops.operator_shadow_follow_up_resolution_item (
        resolution_status, resolution_bucket, resolution_date DESC
    );

CREATE INDEX IF NOT EXISTS idx_simulation_virtual_portfolio_state_portfolio_date
    ON simulation.virtual_portfolio_state_daily (portfolio_id, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_simulation_virtual_portfolio_state_risk_date
    ON simulation.virtual_portfolio_state_daily (risk_level, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_simulation_virtual_portfolio_position_stock_date
    ON simulation.virtual_portfolio_position_daily (stock_code, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_simulation_virtual_portfolio_position_portfolio_date
    ON simulation.virtual_portfolio_position_daily (portfolio_id, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_factor_daily_lookup
    ON factor.factor_daily (trade_date, factor_name, calc_version);

CREATE INDEX IF NOT EXISTS idx_factor_daily_eval_lookup
    ON factor.factor_daily (factor_name, calc_version, trade_date, asset_id);

CREATE INDEX IF NOT EXISTS idx_factor_daily_asset_history
    ON factor.factor_daily (asset_id, factor_name, calc_version, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_stock_score_daily_rank
    ON factor.stock_score_daily (trade_date, score_version, rank);

CREATE INDEX IF NOT EXISTS idx_stock_score_daily_asset_history
    ON factor.stock_score_daily (asset_id, score_version, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_factor_stock_technical_features_daily_lookup
    ON factor.stock_technical_features_daily (trade_date, adjust_type, calc_version, asset_id);

CREATE INDEX IF NOT EXISTS idx_factor_stock_technical_features_daily_asset_history
    ON factor.stock_technical_features_daily (asset_id, adjust_type, calc_version, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_factor_stock_intraday_features_daily_lookup
    ON factor.stock_intraday_features_daily (trade_date, freq, adjust_type, feature_name);

CREATE INDEX IF NOT EXISTS idx_factor_industry_intraday_features_daily_lookup
    ON factor.industry_intraday_features_daily (trade_date, industry_system, freq, adjust_type, feature_name);

CREATE INDEX IF NOT EXISTS idx_factor_eval_run_factor
    ON factor.factor_eval_run (factor_name, calc_version, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_market_lhb_top_list_daily_lookup
    ON market.lhb_top_list_daily (ts_code, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_market_lhb_top_inst_daily_lookup
    ON market.lhb_top_inst_daily (ts_code, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_factor_lhb_event_features_daily_lookup
    ON factor.lhb_event_features_daily (ts_code, trade_date DESC);
"""


def apply_schema(service: str = SETTINGS.research_service) -> None:
    with connect(service) as conn:
        execute(conn, CREATE_TABLES_SQL)
        execute(conn, CREATE_RESEARCH_SCHEMAS_SQL)
        migrate_stock_minute_bar_to_partitioned(conn)
        execute(conn, CREATE_RESEARCH_EXTENSION_SQL)
        ensure_research_schema_compatibility(conn)
        ensure_stock_minute_bar_partitions(conn)


def ensure_research_schema_compatibility(conn) -> None:
    technical_feature_columns: tuple[tuple[str, str], ...] = (
        ("ma5", "numeric"),
        ("ma10", "numeric"),
        ("ma20", "numeric"),
        ("ma60", "numeric"),
        ("ma120", "numeric"),
        ("ema12", "numeric"),
        ("ema26", "numeric"),
        ("macd_dif", "numeric"),
        ("macd_dea", "numeric"),
        ("macd_hist", "numeric"),
        ("rsi6", "numeric"),
        ("rsi12", "numeric"),
        ("rsi24", "numeric"),
        ("boll_upper_20", "numeric"),
        ("boll_mid_20", "numeric"),
        ("boll_lower_20", "numeric"),
        ("atr14", "numeric"),
        ("cci14", "numeric"),
        ("kdj_k", "numeric"),
        ("kdj_d", "numeric"),
        ("kdj_j", "numeric"),
        ("adx14", "numeric"),
        ("obv", "numeric"),
        ("ret_1d", "numeric"),
        ("ret_20d", "numeric"),
        ("close_position_in_day", "numeric"),
        ("amount_vs_20d", "numeric"),
        ("high_to_close_drawdown", "numeric"),
        ("volatility_5d", "numeric"),
        ("max_drawdown_20d", "numeric"),
        ("atr_pct14", "numeric"),
    )
    for column_name, column_type in technical_feature_columns:
        conn.execute(
            f"""
            ALTER TABLE factor.stock_technical_features_daily
            ADD COLUMN IF NOT EXISTS {column_name} {column_type}
            """
        )


def migrate_stock_minute_bar_to_partitioned(conn) -> None:
    existing = conn.execute(
        """
        SELECT c.relkind, p.partrelid IS NOT NULL AS is_partitioned
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_partitioned_table p ON p.partrelid = c.oid
        WHERE n.nspname = 'market'
          AND c.relname = 'stock_minute_bar'
        """
    ).fetchone()
    if existing is None or existing["is_partitioned"]:
        return

    conn.execute("ALTER TABLE market.stock_minute_bar RENAME TO stock_minute_bar_unpartitioned_backup")
    conn.execute(
        "ALTER INDEX IF EXISTS market.stock_minute_bar_pkey "
        "RENAME TO stock_minute_bar_unpartitioned_backup_pkey"
    )
    for index_name in [
        "idx_market_stock_minute_bar_asset_time",
        "idx_market_stock_minute_bar_date_freq_adjust",
        "idx_market_stock_minute_bar_time_freq",
    ]:
        conn.execute(
            f"ALTER INDEX IF EXISTS market.{index_name} RENAME TO {index_name}_backup"
        )
    conn.execute(STOCK_MINUTE_BAR_PARTITIONED_TABLE_SQL)
    ensure_stock_minute_bar_partitions(conn)
    conn.execute(
        """
        INSERT INTO market.stock_minute_bar (
            trade_date,
            asset_id,
            ts_code,
            trade_time,
            freq,
            adjust_type,
            open,
            high,
            low,
            close,
            volume,
            amount,
            source,
            created_at,
            updated_at
        )
        SELECT
            trade_date,
            asset_id,
            ts_code,
            trade_time,
            freq,
            adjust_type,
            open,
            high,
            low,
            close,
            volume,
            amount,
            source,
            created_at,
            updated_at
        FROM market.stock_minute_bar_unpartitioned_backup
        ON CONFLICT (trade_date, asset_id, trade_time, freq, adjust_type, source)
        DO NOTHING
        """
    )


def ensure_stock_minute_bar_partitions(
    conn,
    start_month: dt.date = dt.date(2024, 1, 1),
    end_month: dt.date = dt.date(2027, 1, 1),
) -> None:
    conn.execute(STOCK_MINUTE_BAR_PARTITIONED_TABLE_SQL)
    current = start_month
    while current < end_month:
        next_month = _add_month(current)
        suffix = current.strftime("%Y_%m")
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS market.stock_minute_bar_{suffix}
            PARTITION OF market.stock_minute_bar
            FOR VALUES FROM ('{current.isoformat()}') TO ('{next_month.isoformat()}')
            """
        )
        current = next_month
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market.stock_minute_bar_default
        PARTITION OF market.stock_minute_bar DEFAULT
        """
    )


def _add_month(value: dt.date) -> dt.date:
    if value.month == 12:
        return dt.date(value.year + 1, 1, 1)
    return dt.date(value.year, value.month + 1, 1)
