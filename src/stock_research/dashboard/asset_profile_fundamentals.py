from typing import Any, Callable

from stock_research.db import fetch_all
from stock_research.services import finance_ttm


FetchAll = Callable[[Any, str, list[Any] | None], list[dict[str, Any]]]


def load_asset_profile_fundamentals(
    conn: Any,
    asset_id: str,
    trade_date: str,
    *,
    fetch_all_fn: FetchAll = fetch_all,
) -> dict[str, Any]:
    income_rows = _load_income_ttm_rows(conn, asset_id, trade_date, fetch_all_fn=fetch_all_fn)
    latest_income = _latest_disclosed_row(income_rows)
    latest_indicator = _load_latest_indicator_row(conn, asset_id, trade_date, fetch_all_fn=fetch_all_fn)
    latest_cash_flow = _load_latest_cash_flow_row(conn, asset_id, trade_date, fetch_all_fn=fetch_all_fn)
    disclosed_report_periods = _disclosed_report_periods(latest_indicator, latest_income, latest_cash_flow)
    business_rows = _load_business_rows(
        conn,
        asset_id,
        report_period=_latest_business_composition_report_period(
            conn,
            asset_id,
            disclosed_report_periods,
            fetch_all_fn=fetch_all_fn,
        ),
        fetch_all_fn=fetch_all_fn,
    )
    company_overview = _build_company_overview(
        industry=_load_industry(conn, asset_id, trade_date, fetch_all_fn=fetch_all_fn),
        concept_tags=_load_concept_tags(conn, asset_id, trade_date, fetch_all_fn=fetch_all_fn),
        primary_products=_primary_products(business_rows),
        company_profile=_load_company_profile_context(conn, asset_id, fetch_all_fn=fetch_all_fn),
    )
    return {
        "company_overview": company_overview,
        "business_composition": _build_business_composition(business_rows),
        "financial_snapshot": _load_financial_snapshot(
            trade_date,
            income_rows=income_rows,
            latest_indicator=latest_indicator,
            latest_cash_flow=latest_cash_flow,
            fetch_all_fn=fetch_all_fn,
        ),
    }


def _load_industry(
    conn: Any,
    asset_id: str,
    trade_date: str,
    *,
    fetch_all_fn: FetchAll,
) -> str | None:
    sql = """
    SELECT industry_name
    FROM core.industry_membership
    WHERE asset_id = %s
      AND start_date <= %s
      AND (end_date IS NULL OR end_date >= %s)
    ORDER BY level DESC, start_date DESC
    LIMIT 1
    """
    rows = fetch_all_fn(conn, sql, [asset_id, trade_date, trade_date])
    if not rows:
        return None
    value = str(rows[0].get("industry_name") or "").strip()
    return value or None


def _load_concept_tags(
    conn: Any,
    asset_id: str,
    trade_date: str,
    *,
    fetch_all_fn: FetchAll,
) -> list[str]:
    sql = """
    SELECT concept_name
    FROM core.concept_membership
    WHERE asset_id = %s
      AND start_date <= %s
      AND (end_date IS NULL OR end_date >= %s)
    ORDER BY concept_name
    """
    rows = fetch_all_fn(conn, sql, [asset_id, trade_date, trade_date])
    concepts: list[str] = []
    for row in rows:
        value = str(row.get("concept_name") or "").strip()
        if value and value not in concepts:
            concepts.append(value)
    return concepts


def _load_business_rows(
    conn: Any,
    asset_id: str,
    report_period: str | None,
    *,
    fetch_all_fn: FetchAll,
) -> list[dict[str, Any]]:
    if not report_period:
        return []
    sql = """
    SELECT report_period::text AS report_period,
           classify_type,
           item_name,
           revenue,
           revenue_ratio,
           gross_margin
    FROM finance.main_business_composition
    WHERE asset_id = %s
      AND report_period = %s::date
    ORDER BY classify_type, revenue DESC NULLS LAST, item_name
    """
    return fetch_all_fn(conn, sql, [asset_id, report_period])


def _load_company_profile_context(
    conn: Any,
    asset_id: str,
    *,
    fetch_all_fn: FetchAll,
) -> dict[str, Any] | None:
    sql = """
    SELECT name, board, region
    FROM core.asset_master
    WHERE asset_id = %s
    LIMIT 1
    """
    rows = fetch_all_fn(conn, sql, [asset_id])
    return rows[0] if rows else None


def _primary_products(rows: list[dict[str, Any]]) -> list[str]:
    products: list[str] = []
    for row in rows:
        if str(row.get("classify_type") or "").strip() not in {"产品", "按产品", "按产品分类"}:
            continue
        value = str(row.get("item_name") or "").strip()
        if value and value not in products:
            products.append(value)
    return products


def _build_company_overview(
    *,
    industry: str | None,
    concept_tags: list[str],
    primary_products: list[str],
    company_profile: dict[str, Any] | None,
) -> dict[str, Any]:
    business_summary = _derive_business_summary(primary_products)
    profile_summary = _derive_profile_summary(industry, company_profile)
    overview = {
        "industry": industry,
        "concept_tags": concept_tags,
        "business_summary": business_summary,
        "profile_summary": profile_summary,
        "primary_products": primary_products,
    }
    required_fields = [
        "industry",
        "concept_tags",
        "business_summary",
        "primary_products",
        "profile_summary",
    ]
    missing_fields = [field_name for field_name in required_fields if _is_missing_overview_value(overview.get(field_name))]
    return {
        **overview,
        "data_status": "available" if not missing_fields else ("missing" if len(missing_fields) == len(required_fields) else "partial"),
        "missing_fields": missing_fields,
    }


def _derive_business_summary(primary_products: list[str]) -> str | None:
    products = [value for value in primary_products if value]
    if not products:
        return None
    return f"主营产品包括{'、'.join(products[:3])}。"


def _derive_profile_summary(industry: str | None, company_profile: dict[str, Any] | None) -> str | None:
    name = str((company_profile or {}).get("name") or "").strip()
    region = str((company_profile or {}).get("region") or "").strip()
    board = str((company_profile or {}).get("board") or "").strip()
    industry_text = str(industry or "").strip()
    if not any([name, region, board, industry_text]):
        return None
    summary_parts: list[str] = []
    prefix = name or "该公司"
    if region:
        prefix = f"{prefix}位于{region}"
    summary_parts.append(prefix)
    if industry_text:
        summary_parts.append(f"属于{industry_text}行业")
    if board:
        summary_parts.append(f"上市板为{board}")
    return "，".join(summary_parts) + "。"


def _build_business_composition(rows: list[dict[str, Any]]) -> dict[str, Any]:
    report_period = str(rows[0].get("report_period"))[:10] if rows else None
    groups: list[dict[str, Any]] = []
    by_type: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        classify_type = str(row.get("classify_type") or "").strip()
        if not classify_type:
            continue
        item = {
            "item_name": str(row.get("item_name") or "").strip(),
            "revenue": _to_float(row.get("revenue")),
            "revenue_ratio": _to_float(row.get("revenue_ratio")),
            "gross_margin": _to_float(row.get("gross_margin")),
        }
        by_type.setdefault(classify_type, []).append(item)
    for classify_type, items in by_type.items():
        groups.append({"classify_type": classify_type, "items": items})
    missing_fields: list[str] = []
    if report_period is None:
        missing_fields.append("report_period")
    if not groups:
        missing_fields.append("groups")
    return {
        "report_period": report_period,
        "groups": groups,
        "data_status": "available" if not missing_fields else ("missing" if len(missing_fields) == 2 else "partial"),
        "missing_fields": missing_fields,
    }


def _load_financial_snapshot(
    trade_date: str,
    *,
    income_rows: list[dict[str, Any]],
    latest_indicator: dict[str, Any] | None,
    latest_cash_flow: dict[str, Any] | None,
    fetch_all_fn: FetchAll,
) -> dict[str, Any]:
    income_ttm = {
        "revenue_ttm": finance_ttm.calc_ttm_from_cumulative_rows(
            income_rows,
            value_column="revenue",
            trade_date=trade_date,
        ),
        "np_parent_ttm": finance_ttm.calc_ttm_from_cumulative_rows(
            income_rows,
            value_column="np_parent",
            trade_date=trade_date,
        ),
    }
    latest_income = _latest_disclosed_row(income_rows)
    anchor_row = _coherent_financial_anchor(latest_indicator, latest_income, latest_cash_flow)
    return {
        "report_period": _to_date_text((anchor_row or {}).get("report_period")),
        "announcement_date": _to_date_text((anchor_row or {}).get("announcement_date")),
        "revenue_ttm": _to_float(income_ttm.get("revenue_ttm")),
        "np_parent_ttm": _to_float(income_ttm.get("np_parent_ttm")),
        "operating_cash_flow": _to_float((latest_cash_flow or {}).get("net_operate_cash_flow")),
        "roe": _to_float((latest_indicator or {}).get("roe")),
        "gross_margin": _to_float((latest_indicator or {}).get("gross_margin")),
        "debt_ratio": _to_float((latest_indicator or {}).get("debt_ratio")),
        "ocf_to_np": _to_float((latest_indicator or {}).get("ocf_to_np")),
        "data_status": "available",
        "missing_fields": [],
    } | _financial_snapshot_status(
        report_period=_to_date_text((anchor_row or {}).get("report_period")),
        announcement_date=_to_date_text((anchor_row or {}).get("announcement_date")),
        revenue_ttm=_to_float(income_ttm.get("revenue_ttm")),
        np_parent_ttm=_to_float(income_ttm.get("np_parent_ttm")),
        operating_cash_flow=_to_float((latest_cash_flow or {}).get("net_operate_cash_flow")),
        roe=_to_float((latest_indicator or {}).get("roe")),
        gross_margin=_to_float((latest_indicator or {}).get("gross_margin")),
        debt_ratio=_to_float((latest_indicator or {}).get("debt_ratio")),
        ocf_to_np=_to_float((latest_indicator or {}).get("ocf_to_np")),
    )


def _load_income_ttm_rows(
    conn: Any,
    asset_id: str,
    trade_date: str,
    *,
    fetch_all_fn: FetchAll,
) -> list[dict[str, Any]]:
    sql = """
    SELECT report_period::text AS report_period,
           announcement_date::text AS announcement_date,
           revenue,
           np_parent
    FROM finance.income_statement
    WHERE asset_id = %s
      AND announcement_date <= %s
      AND (revenue IS NOT NULL OR np_parent IS NOT NULL)
    ORDER BY report_period DESC, announcement_date DESC
    """
    rows = fetch_all_fn(conn, sql, [asset_id, trade_date])
    return _filter_disclosed_rows(rows, trade_date)


def _load_latest_indicator_row(
    conn: Any,
    asset_id: str,
    trade_date: str,
    *,
    fetch_all_fn: FetchAll,
) -> dict[str, Any] | None:
    sql = """
    SELECT report_period::text AS report_period,
           announcement_date::text AS announcement_date,
           roe,
           gross_margin,
           debt_ratio,
           ocf_to_np
    FROM finance.indicator_quarter
    WHERE asset_id = %s
      AND announcement_date <= %s
    ORDER BY announcement_date DESC, report_period DESC
    LIMIT 1
    """
    rows = fetch_all_fn(conn, sql, [asset_id, trade_date])
    filtered = _filter_disclosed_rows(rows, trade_date)
    return filtered[0] if filtered else None


def _load_latest_cash_flow_row(
    conn: Any,
    asset_id: str,
    trade_date: str,
    *,
    fetch_all_fn: FetchAll,
) -> dict[str, Any] | None:
    sql = """
    SELECT report_period::text AS report_period,
           announcement_date::text AS announcement_date,
           net_operate_cash_flow
    FROM finance.cash_flow
    WHERE asset_id = %s
      AND announcement_date <= %s
    ORDER BY announcement_date DESC, report_period DESC
    LIMIT 1
    """
    rows = fetch_all_fn(conn, sql, [asset_id, trade_date])
    filtered = _filter_disclosed_rows(rows, trade_date)
    return filtered[0] if filtered else None


def _latest_disclosed_report_period(*rows: dict[str, Any] | None) -> str | None:
    report_periods = [
        _to_date_text((row or {}).get("report_period"))
        for row in rows
        if _to_date_text((row or {}).get("report_period")) is not None
    ]
    return max(report_periods) if report_periods else None


def _latest_disclosed_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    disclosed = sorted(
        rows,
        key=lambda row: (
            _to_date_text(row.get("announcement_date")) or "",
            _to_date_text(row.get("report_period")) or "",
        ),
        reverse=True,
    )
    return disclosed[0] if disclosed else None


def _disclosed_report_periods(*rows: dict[str, Any] | None) -> list[str]:
    periods = [
        _to_date_text((row or {}).get("report_period"))
        for row in rows
        if _to_date_text((row or {}).get("report_period")) is not None
    ]
    return sorted(set(periods), reverse=True)


def _latest_business_composition_report_period(
    conn: Any,
    asset_id: str,
    disclosed_report_periods: list[str],
    *,
    fetch_all_fn: FetchAll,
) -> str | None:
    if not disclosed_report_periods:
        return None
    sql = """
    SELECT DISTINCT report_period::text AS report_period
    FROM finance.main_business_composition
    WHERE asset_id = %s
    ORDER BY report_period DESC
    """
    rows = fetch_all_fn(conn, sql, [asset_id])
    available_periods = {
        _to_date_text(row.get("report_period"))
        for row in rows
        if _to_date_text(row.get("report_period")) is not None
    }
    for report_period in disclosed_report_periods:
        if report_period in available_periods:
            return report_period
    return None


def _coherent_financial_anchor(*rows: dict[str, Any] | None) -> dict[str, Any] | None:
    disclosed_rows = [row for row in rows if row]
    if not disclosed_rows:
        return None
    report_periods = {
        _to_date_text(row.get("report_period"))
        for row in disclosed_rows
        if _to_date_text(row.get("report_period")) is not None
    }
    if len(report_periods) != 1:
        return None
    announcement_dates = {
        _to_date_text(row.get("announcement_date"))
        for row in disclosed_rows
        if _to_date_text(row.get("announcement_date")) is not None
    }
    if len(announcement_dates) == 1:
        return disclosed_rows[0]
    return {
        "report_period": next(iter(report_periods)),
        "announcement_date": None,
    }


def _filter_disclosed_rows(rows: list[dict[str, Any]], trade_date: str) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if (_to_date_text(row.get("announcement_date")) or "9999-12-31") <= trade_date
    ]


def _financial_snapshot_status(**snapshot: Any) -> dict[str, Any]:
    missing_fields = [field_name for field_name, value in snapshot.items() if value is None]
    if not missing_fields:
        status = "available"
    elif len(missing_fields) == len(snapshot):
        status = "missing"
    else:
        status = "partial"
    return {
        "data_status": status,
        "missing_fields": missing_fields,
    }


def _is_missing_overview_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return len(value) == 0
    return False


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_date_text(value: Any) -> str | None:
    return str(value)[:10] if value else None
