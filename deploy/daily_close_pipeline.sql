CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.daily_pipeline_job (
    id text PRIMARY KEY,
    trade_date date NOT NULL,
    job_name text NOT NULL,
    stage text NOT NULL,
    source text NOT NULL DEFAULT '',
    status text NOT NULL CHECK (status IN ('pending', 'running', 'success', 'partial_success', 'failed', 'skipped')),
    started_at timestamptz,
    finished_at timestamptz,
    duration_seconds numeric,
    attempt_count integer NOT NULL DEFAULT 0,
    rows_inserted integer NOT NULL DEFAULT 0,
    rows_updated integer NOT NULL DEFAULT 0,
    rows_failed integer NOT NULL DEFAULT 0,
    missing_symbols_count integer NOT NULL DEFAULT 0,
    error_summary text,
    error_detail_path text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (trade_date, job_name, stage, source)
);

CREATE TABLE IF NOT EXISTS ops.daily_pipeline_quality (
    trade_date date NOT NULL,
    dataset_name text NOT NULL,
    status text NOT NULL CHECK (status IN ('pass', 'warning', 'fail')),
    expected_count integer,
    actual_count integer,
    missing_symbols jsonb NOT NULL DEFAULT '[]'::jsonb,
    abnormal_symbols jsonb NOT NULL DEFAULT '[]'::jsonb,
    check_summary text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, dataset_name)
);

CREATE TABLE IF NOT EXISTS ops.daily_pipeline_failed_symbol (
    trade_date date NOT NULL,
    stage text NOT NULL,
    dataset_name text NOT NULL,
    ts_code text NOT NULL,
    source text NOT NULL,
    status text NOT NULL CHECK (status IN ('pending', 'running', 'success', 'failed')) DEFAULT 'pending',
    attempt_count integer NOT NULL DEFAULT 0,
    error_type text,
    error_summary text,
    last_error_at timestamptz,
    next_retry_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, stage, dataset_name, ts_code, source)
);

CREATE TABLE IF NOT EXISTS ops.daily_pipeline_status (
    trade_date date PRIMARY KEY,
    pipeline_status text NOT NULL CHECK (pipeline_status IN ('READY', 'DEGRADED_READY', 'NOT_READY')),
    daily_status text NOT NULL,
    minute5_status text NOT NULL,
    deps_status text NOT NULL,
    latest_ready_trade_date date,
    using_fallback_trade_date boolean NOT NULL DEFAULT false,
    warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
    failed_jobs jsonb NOT NULL DEFAULT '[]'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);
