from __future__ import annotations

from typing import Any
from pathlib import Path
import json
import subprocess

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.core_data import sync_concept_memberships_from_akshare
from stock_research.loaders.baostock_ingestion import sync_industry_memberships
from stock_research.market_profile_backfill import no_proxy_env


METADATA_COLUMNS = [
    "asset_id",
    "stock_code",
    "stock_name",
    "industry",
    "industry_system",
    "industry_source",
    "concept_tags",
    "concept_source",
    "concept_mapping_status",
]

FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def stock_code_from_asset_id(asset_id: Any) -> str:
    text = str(asset_id or "").strip().upper()
    if text.startswith("CN:"):
        text = text.split(":")[-1]
    if "." in text:
        left, right = text.split(".", 1)
        if left in {"SH", "SZ", "BJ"}:
            return right.zfill(6)
        return left.zfill(6)
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(6) if digits else ""


def build_stock_metadata_read_model(
    *,
    assets: pd.DataFrame,
    industries: pd.DataFrame,
    concepts: pd.DataFrame,
) -> pd.DataFrame:
    base = assets.copy()
    if base.empty:
        return pd.DataFrame(columns=METADATA_COLUMNS)
    base["stock_code"] = base.get("stock_code", base["asset_id"].map(stock_code_from_asset_id)).map(stock_code_from_asset_id)
    base["stock_name"] = base.get("stock_name", base.get("name", ""))

    industry_map = _latest_industry_by_asset(industries)
    concept_map = _concepts_by_asset(concepts)
    rows: list[dict[str, Any]] = []
    for row in base.sort_values("stock_code").to_dict("records"):
        asset_id = str(row.get("asset_id") or "").strip()
        stock_code = stock_code_from_asset_id(row.get("stock_code") or asset_id)
        industry = industry_map.get(stock_code, {})
        concepts_for_asset = concept_map.get(stock_code, {})
        concept_tags = str(concepts_for_asset.get("concept_tags") or "").strip()
        rows.append(
            {
                "asset_id": asset_id,
                "stock_code": stock_code,
                "stock_name": str(row.get("stock_name") or row.get("name") or "").strip(),
                "industry": str(industry.get("industry_name") or "").strip(),
                "industry_system": str(industry.get("industry_system") or "").strip(),
                "industry_source": str(industry.get("source") or "").strip(),
                "concept_tags": concept_tags or "no_concept_mapping_found",
                "concept_source": str(concepts_for_asset.get("source") or "").strip(),
                "concept_mapping_status": "mapped" if concept_tags else "missing_concept_mapping",
            }
        )
    return pd.DataFrame(rows, columns=METADATA_COLUMNS)


def build_stock_metadata_coverage_audit(model: pd.DataFrame) -> dict[str, Any]:
    total = int(len(model))
    industry_mapped = int(model.get("industry", pd.Series(dtype="object")).astype(str).str.strip().ne("").sum())
    concept_series = model.get("concept_tags", pd.Series(dtype="object")).astype(str).str.strip()
    concept_mapped = int((concept_series.ne("") & concept_series.ne("no_concept_mapping_found")).sum())
    missing_industry = total - industry_mapped
    missing_concept = total - concept_mapped
    return {
        "total_stock_count": total,
        "industry_mapped_count": industry_mapped,
        "concept_mapped_count": concept_mapped,
        "missing_industry_count": missing_industry,
        "missing_concept_count": missing_concept,
        "all_industry_mapped": missing_industry == 0,
        "all_concept_status_accounted_for": bool(concept_series.ne("").all()),
    }


def load_stock_metadata_from_db(
    *,
    stock_codes: list[str] | tuple[str, ...],
    as_of_date: str,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    normalized_codes = sorted({stock_code_from_asset_id(code) for code in stock_codes if stock_code_from_asset_id(code)})
    if not normalized_codes:
        return pd.DataFrame(columns=METADATA_COLUMNS)
    with connect(service) as conn:
        assets = pd.DataFrame(_fetch_assets(conn, normalized_codes))
        industries = pd.DataFrame(_fetch_industries(conn, normalized_codes, as_of_date))
        concepts = pd.DataFrame(_fetch_concepts(conn, normalized_codes, as_of_date))
    return build_stock_metadata_read_model(assets=assets, industries=industries, concepts=concepts)


def load_all_active_stock_metadata_from_db(
    *,
    as_of_date: str,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    with connect(service) as conn:
        assets = pd.DataFrame(_fetch_all_active_assets(conn))
        stock_codes = [stock_code_from_asset_id(row.get("stock_code") or row.get("asset_id")) for row in assets.to_dict("records")]
        industries = pd.DataFrame(_fetch_industries(conn, stock_codes, as_of_date))
        concepts = pd.DataFrame(_fetch_concepts(conn, stock_codes, as_of_date))
    return build_stock_metadata_read_model(assets=assets, industries=industries, concepts=concepts)


def sync_concept_memberships_for_service(
    *,
    trade_date: str,
    service: str = SETTINGS.research_service,
    max_concepts: int | None = None,
) -> dict[str, object]:
    with no_proxy_env():
        with connect(service) as conn:
            return sync_concept_memberships_from_akshare(conn, trade_date=trade_date, max_concepts=max_concepts)


def run_stock_metadata_db_hydration(
    *,
    as_of_date: str,
    output_dir: Path,
    sync_industry: bool = False,
    sync_concept: bool = False,
    max_concepts: int | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    industry_sync_rows = sync_industry_memberships(as_of_date, service) if sync_industry else 0
    concept_sync_error = ""
    try:
        concept_sync_result = (
            sync_concept_memberships_for_service(trade_date=as_of_date, service=service, max_concepts=max_concepts)
            if sync_concept
            else {"boards": 0, "memberships": 0, "failed_concepts": []}
        )
    except Exception as exc:  # noqa: BLE001 - external metadata source failures should not block DB audit output.
        concept_sync_error = str(exc)
        concept_sync_result = {"boards": 0, "memberships": 0, "failed_concepts": [concept_sync_error]}
    model = load_all_active_stock_metadata_from_db(as_of_date=as_of_date, service=service)
    audit = build_stock_metadata_coverage_audit(model)
    strategy_clean = _strategy_diff_clean()
    summary = {
        "task_name": "stock_metadata_industry_concept_db_hydration_v1",
        "as_of_date": as_of_date,
        "active_stock_count": audit["total_stock_count"],
        "industry_mapped_count": audit["industry_mapped_count"],
        "concept_mapped_count": audit["concept_mapped_count"],
        "missing_industry_count": audit["missing_industry_count"],
        "missing_concept_count": audit["missing_concept_count"],
        "industry_sync_performed": bool(sync_industry),
        "industry_sync_rows": int(industry_sync_rows),
        "concept_sync_performed": bool(sync_concept),
        "concept_sync_boards": int(concept_sync_result.get("boards", 0)),
        "concept_sync_memberships": int(concept_sync_result.get("memberships", 0)),
        "concept_sync_failed_count": len(concept_sync_result.get("failed_concepts", [])),
        "concept_sync_error": concept_sync_error,
        "research_only": True,
        "auto_added_to_quality_pool_count": 0,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "acceptance_decision": _acceptance_decision(strategy_clean=strategy_clean, concept_sync_error=concept_sync_error),
    }
    guardrails = {
        **summary,
        "formal_strategy_files_modified": not strategy_clean,
        "signal_or_admission_integration_performed": False,
    }

    model.to_csv(output_dir / "stock_metadata_industry_concept_db_read_model.csv", index=False)
    _write_json(output_dir / "stock_metadata_industry_concept_db_hydration_summary.json", summary)
    _write_json(output_dir / "stock_metadata_industry_concept_db_hydration_guardrails.json", guardrails)
    missing = model[(model["industry"].astype(str).str.strip() == "") | (model["concept_tags"] == "no_concept_mapping_found")]
    missing.to_csv(output_dir / "stock_metadata_industry_concept_db_missing_mapping_audit.csv", index=False)
    (output_dir / "stock_metadata_industry_concept_db_hydration_v1_report.md").write_text(
        "\n".join(
            [
                "# Stock Metadata Industry Concept DB Hydration v1",
                "",
                f"- active stocks: {summary['active_stock_count']}",
                f"- industry mapped: {summary['industry_mapped_count']}",
                f"- concept mapped: {summary['concept_mapped_count']}",
                f"- missing industry: {summary['missing_industry_count']}",
                f"- missing concept: {summary['missing_concept_count']}",
                "- research only: true",
                "- used_for_signal: 0",
                "- used_for_admission: 0",
            ]
        ),
        encoding="utf-8",
    )
    return summary


def _latest_industry_by_asset(industries: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if industries.empty:
        return {}
    frame = industries.copy()
    if "start_date" not in frame.columns:
        frame["start_date"] = ""
    frame["start_date"] = frame["start_date"].astype(str)
    frame = frame.sort_values(["asset_id", "start_date"])
    frame["stock_code"] = frame["asset_id"].map(stock_code_from_asset_id)
    return frame.drop_duplicates("stock_code", keep="last").set_index("stock_code").to_dict("index")


def _concepts_by_asset(concepts: pd.DataFrame) -> dict[str, dict[str, str]]:
    if concepts.empty:
        return {}
    rows: dict[str, dict[str, str]] = {}
    frame = concepts.copy()
    frame["stock_code"] = frame["asset_id"].map(stock_code_from_asset_id)
    for stock_code, group in frame.sort_values(["stock_code", "concept_name"]).groupby("stock_code"):
        names = [str(value).strip() for value in group["concept_name"].tolist() if str(value).strip()]
        sources = [str(value).strip() for value in group.get("source", pd.Series(dtype="object")).tolist() if str(value).strip()]
        rows[str(stock_code)] = {
            "concept_tags": " / ".join(dict.fromkeys(names)),
            "source": " / ".join(dict.fromkeys(sources)),
        }
    return rows


def _fetch_assets(conn, stock_codes: list[str]) -> list[dict[str, Any]]:
    sql = """
    SELECT
        asset_id,
        symbol AS stock_code,
        name AS stock_name
    FROM core.asset_master
    WHERE symbol = ANY(%s)
      AND is_active = true
    ORDER BY symbol
    """
    return fetch_all(conn, sql, [stock_codes])


def _fetch_all_active_assets(conn) -> list[dict[str, Any]]:
    sql = """
    SELECT
        asset_id,
        symbol AS stock_code,
        name AS stock_name
    FROM core.asset_master
    WHERE is_active = true
      AND exchange IN ('SH', 'SZ', 'BJ')
    ORDER BY symbol
    """
    return fetch_all(conn, sql)


def _fetch_industries(conn, stock_codes: list[str], as_of_date: str) -> list[dict[str, Any]]:
    sql = """
    SELECT DISTINCT ON (a.asset_id)
        a.asset_id,
        m.industry_system,
        m.industry_name,
        m.start_date::text AS start_date,
        m.source
    FROM core.asset_master a
    JOIN core.industry_membership m
      ON m.asset_id = a.asset_id
    WHERE a.symbol = ANY(%s)
      AND m.start_date <= %s
      AND (m.end_date IS NULL OR %s < m.end_date)
    ORDER BY a.asset_id, m.level DESC, m.start_date DESC
    """
    return fetch_all(conn, sql, [stock_codes, as_of_date, as_of_date])


def _fetch_concepts(conn, stock_codes: list[str], as_of_date: str) -> list[dict[str, Any]]:
    sql = """
    SELECT
        a.asset_id,
        m.concept_system,
        m.concept_name,
        m.source
    FROM core.asset_master a
    JOIN core.concept_membership m
      ON m.asset_id = a.asset_id
    WHERE a.symbol = ANY(%s)
      AND m.start_date <= %s
      AND (m.end_date IS NULL OR %s < m.end_date)
    ORDER BY a.asset_id, m.concept_name
    """
    return fetch_all(conn, sql, [stock_codes, as_of_date, as_of_date])


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _acceptance_decision(*, strategy_clean: bool, concept_sync_error: str) -> str:
    if not strategy_clean:
        return "blocked_due_to_guardrail_violation"
    if concept_sync_error:
        return "conditionally_ready_with_concept_sync_gap"
    return "stock_metadata_industry_concept_db_hydration_ready"
