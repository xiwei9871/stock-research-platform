from stock_research.config import SETTINGS
from stock_research.db import connect, execute


def build_adjustment_factors_for_service(
    start_date: str | None = None,
    end_date: str | None = None,
    source_version: str = "derived_market_daily_bar_v1",
    service: str = SETTINGS.research_service,
) -> None:
    with connect(service) as conn:
        build_adjustment_factors(
            conn,
            start_date=start_date,
            end_date=end_date,
            source_version=source_version,
        )


def build_adjustment_factors(
    conn,
    start_date: str | None = None,
    end_date: str | None = None,
    source_version: str = "derived_market_daily_bar_v1",
) -> None:
    filters = ["qfq.adjust_type = 'qfq'"]
    params = [source_version]
    if start_date:
        filters.append("qfq.trade_date >= %s")
        params.append(start_date)
    if end_date:
        filters.append("qfq.trade_date <= %s")
        params.append(end_date)

    where_sql = " AND ".join(filters)
    sql = f"""
    INSERT INTO market.adjustment_factor (
        asset_id,
        trade_date,
        raw_close,
        qfq_close,
        hfq_close,
        qfq_factor,
        hfq_factor,
        source,
        source_version
    )
    SELECT
        qfq.asset_id,
        qfq.trade_date,
        raw.close AS raw_close,
        qfq.close AS qfq_close,
        hfq.close AS hfq_close,
        COALESCE(qfq.close / NULLIF(raw.close, 0), 1.0) AS qfq_factor,
        COALESCE(hfq.close / NULLIF(raw.close, 0), hfq.close / NULLIF(qfq.close, 0)) AS hfq_factor,
        'derived:market_daily_bar' AS source,
        %s AS source_version
    FROM market_daily_bar qfq
    JOIN market_daily_bar hfq
      ON hfq.asset_id = qfq.asset_id
     AND hfq.trade_date = qfq.trade_date
     AND hfq.adjust_type = 'hfq'
    LEFT JOIN market_daily_bar raw
      ON raw.asset_id = qfq.asset_id
     AND raw.trade_date = qfq.trade_date
     AND raw.adjust_type = 'raw'
    WHERE {where_sql}
    ON CONFLICT (asset_id, trade_date, source_version) DO UPDATE SET
        raw_close = EXCLUDED.raw_close,
        qfq_close = EXCLUDED.qfq_close,
        hfq_close = EXCLUDED.hfq_close,
        qfq_factor = EXCLUDED.qfq_factor,
        hfq_factor = EXCLUDED.hfq_factor,
        source = EXCLUDED.source,
        updated_at = now()
    """
    execute(conn, sql, params)


def build_corporate_actions_from_factors_for_service(
    start_date: str | None = None,
    end_date: str | None = None,
    source_version: str = "derived_adjustment_factor_v1",
    service: str = SETTINGS.research_service,
) -> None:
    with connect(service) as conn:
        build_corporate_actions_from_factors(
            conn,
            start_date=start_date,
            end_date=end_date,
            source_version=source_version,
        )


def build_corporate_actions_from_factors(
    conn,
    start_date: str | None = None,
    end_date: str | None = None,
    source_version: str = "derived_adjustment_factor_v1",
) -> None:
    params = [source_version, source_version]
    filters = ["factor_before IS NOT NULL"]
    if start_date:
        filters.append("event_date >= %s")
        params.append(start_date)
    if end_date:
        filters.append("event_date <= %s")
        params.append(end_date)

    where_sql = " AND ".join(filters)
    sql = f"""
    INSERT INTO market.corporate_action (
        asset_id,
        event_date,
        action_type,
        factor_before,
        factor_after,
        source,
        source_version
    )
    SELECT
        asset_id,
        event_date,
        'adjustment_factor_change' AS action_type,
        factor_before,
        factor_after,
        'derived:market.adjustment_factor' AS source,
        %s AS source_version
    FROM (
        SELECT
            asset_id,
            trade_date AS event_date,
            lag(hfq_factor) OVER (
                PARTITION BY asset_id
                ORDER BY trade_date
            ) AS factor_before,
            hfq_factor AS factor_after
        FROM market.adjustment_factor
        WHERE hfq_factor IS NOT NULL
          AND source_version = %s
    ) changes
    WHERE {where_sql}
      AND factor_after IS DISTINCT FROM factor_before
    ON CONFLICT (asset_id, event_date, action_type, source_version) DO UPDATE SET
        factor_before = EXCLUDED.factor_before,
        factor_after = EXCLUDED.factor_after,
        source = EXCLUDED.source,
        updated_at = now()
    """
    execute(conn, sql, params)
