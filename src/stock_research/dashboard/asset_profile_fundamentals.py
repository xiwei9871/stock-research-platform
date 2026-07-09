from typing import Any, Callable

from stock_research.db import fetch_all
from stock_research.services import finance_ttm, point_in_time_finance


FetchAll = Callable[[Any, str, list[Any] | None], list[dict[str, Any]]]


def load_asset_profile_fundamentals(
    conn: Any,
    asset_id: str,
    trade_date: str,
    *,
    fetch_all_fn: FetchAll = fetch_all,
) -> dict[str, Any]:
    business_rows = _load_business_rows(conn, asset_id, trade_date, fetch_all_fn=fetch_all_fn)
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
            conn,
            asset_id,
            trade_date,
            fetch_all_fn=fetch_all_fn,
        ),
    }


def _run_with_fetch_all(module: Any, fetch_all_fn: FetchAll, operation: Callable[[], Any]) -> Any:
    original = getattr(module, "fetch_all")
    if original is fetch_all_fn:
        return operation()
    setattr(module, "fetch_all", fetch_all_fn)
    try:
        return operation()
    finally:
        setattr(module, "fetch_all", original)


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
    trade_date: str,
    *,
    fetch_all_fn: FetchAll,
) -> list[dict[str, Any]]:
    sql = """
    SELECT report_period::text AS report_period,
           classify_type,
           item_name,
           revenue,
           revenue_ratio,
           cost,
           gross_profit,
           gross_margin
    FROM finance.main_business_composition
    WHERE asset_id = %s
      AND report_period <= %s
      AND report_period = (
          SELECT max(report_period)
          FROM finance.main_business_composition
          WHERE asset_id = %s
            AND report_period <= %s
      )
    ORDER BY classify_type, revenue DESC NULLS LAST, item_name
    """
    rows = fetch_all_fn(conn, sql, [asset_id, trade_date, asset_id, trade_date])
    return [
        row
        for row in rows
        if (str(row.get("report_period") or "")[:10] or "9999-12-31") <= trade_date
    ]


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
        if str(row.get("classify_type") or "").strip() not in {"产品", "按产品"}:
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
    missing_fields = [
        field_name
        for field_name, value in overview.items()
        if value is None and field_name in {"business_summary", "profile_summary"}
    ]
    return {
        **overview,
        "data_status": "available" if not missing_fields else "partial",
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
            "gross_profit": _to_float(row.get("gross_profit")),
            "gross_margin": _to_float(row.get("gross_margin")),
        }
        cost = _to_float(row.get("cost"))
        if cost is not None:
            item["cost"] = cost
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
    conn: Any,
    asset_id: str,
    trade_date: str,
    *,
    fetch_all_fn: FetchAll,
) -> dict[str, Any]:
    income_ttm = _run_with_fetch_all(
        finance_ttm,
        fetch_all_fn,
        lambda: finance_ttm.load_income_ttm_rows(
            conn,
            [asset_id],
            trade_date,
            value_columns=["revenue", "np_parent"],
        ),
    ).get(asset_id, {})
    latest_indicator = _run_with_fetch_all(
        point_in_time_finance,
        fetch_all_fn,
        lambda: point_in_time_finance.get_latest_indicator(conn, asset_id, trade_date),
    )
    latest_cash_flow = _run_with_fetch_all(
        point_in_time_finance,
        fetch_all_fn,
        lambda: point_in_time_finance.get_latest_cash_flow(conn, asset_id, trade_date),
    )
    latest_income = _run_with_fetch_all(
        point_in_time_finance,
        fetch_all_fn,
        lambda: point_in_time_finance.get_latest_income_statement(conn, asset_id, trade_date),
    )
    return {
        "report_period": _to_date_text((latest_income or {}).get("report_period")),
        "announcement_date": _to_date_text((latest_income or {}).get("announcement_date")),
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
        report_period=_to_date_text((latest_income or {}).get("report_period")),
        announcement_date=_to_date_text((latest_income or {}).get("announcement_date")),
        revenue_ttm=_to_float(income_ttm.get("revenue_ttm")),
        np_parent_ttm=_to_float(income_ttm.get("np_parent_ttm")),
        operating_cash_flow=_to_float((latest_cash_flow or {}).get("net_operate_cash_flow")),
        roe=_to_float((latest_indicator or {}).get("roe")),
        gross_margin=_to_float((latest_indicator or {}).get("gross_margin")),
        debt_ratio=_to_float((latest_indicator or {}).get("debt_ratio")),
        ocf_to_np=_to_float((latest_indicator or {}).get("ocf_to_np")),
    )


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


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_date_text(value: Any) -> str | None:
    return str(value)[:10] if value else None
