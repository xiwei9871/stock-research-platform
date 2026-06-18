CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.intraday_universe_member (
    run_date date NOT NULL,
    previous_trade_date date,
    ts_code text NOT NULL,
    asset_id text NOT NULL,
    stock_name text NOT NULL DEFAULT '',
    source_types jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_detail text NOT NULL DEFAULT '',
    rank integer,
    score numeric,
    position_quantity numeric,
    position_weight numeric,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_date, ts_code)
);

CREATE TABLE IF NOT EXISTS ops.intraday_job (
    run_date date NOT NULL,
    stage text NOT NULL,
    status text NOT NULL,
    started_at timestamptz,
    finished_at timestamptz,
    rows_upserted integer NOT NULL DEFAULT 0,
    failed_symbols jsonb NOT NULL DEFAULT '[]'::jsonb,
    error_summary text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_date, stage)
);

CREATE TABLE IF NOT EXISTS ops.market_sentiment_snapshot (
    trade_date date NOT NULL,
    snapshot_time timestamptz NOT NULL,
    source text NOT NULL,
    up_count integer NOT NULL DEFAULT 0,
    down_count integer NOT NULL DEFAULT 0,
    flat_count integer NOT NULL DEFAULT 0,
    limit_up_count integer NOT NULL DEFAULT 0,
    limit_down_count integer NOT NULL DEFAULT 0,
    break_limit_count integer NOT NULL DEFAULT 0,
    total_count integer NOT NULL DEFAULT 0,
    sentiment_score numeric,
    sentiment_state text NOT NULL,
    raw_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, snapshot_time, source)
);
