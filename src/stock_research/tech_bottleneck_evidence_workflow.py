from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


FIELD_COLUMNS = [
    "revenue_exposure_bucket",
    "customer_certification_stage",
    "supplier_concentration_type",
]

STATUS_MULTIPLIER = {
    "strong": 1.0,
    "partial": 0.9,
    "weak_pending_backfill": 0.75,
    "missing_blocking": 0.6,
}


def run_tech_bottleneck_evidence_workflow(
    *,
    asset_queue_path: str | Path,
    evidence_detail_path: str | Path,
    candidate_path: str | Path | None = None,
    trade_date: str | None = None,
    top_n: int = 100,
    output_dir: str | Path = "outputs/research/tech_bottleneck_evidence_workflow",
) -> dict[str, Any]:
    asset_queue = pd.read_csv(asset_queue_path, low_memory=False)
    evidence_detail = pd.read_csv(evidence_detail_path, low_memory=False)
    candidates = pd.read_csv(candidate_path, low_memory=False) if candidate_path else None
    return build_tech_bottleneck_evidence_workflow(
        asset_queue=asset_queue,
        evidence_detail=evidence_detail,
        candidates=candidates,
        trade_date=trade_date,
        top_n=top_n,
        output_dir=output_dir,
    )


def build_tech_bottleneck_evidence_workflow(
    *,
    asset_queue: pd.DataFrame,
    evidence_detail: pd.DataFrame,
    candidates: pd.DataFrame | None = None,
    trade_date: str | None = None,
    top_n: int = 100,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    top_assets = _prepare_asset_queue(asset_queue).head(int(top_n)).copy()
    evidence = _prepare_evidence_detail(evidence_detail)
    topn_backfill_queue = _build_topn_backfill_queue(top_assets, evidence)
    yanbaoke_tasks = _build_yanbaoke_tasks(topn_backfill_queue, trade_date=trade_date)

    adjusted_candidates = pd.DataFrame()
    weak_evidence_queue = pd.DataFrame()
    if candidates is not None:
        adjusted_candidates = _build_adjusted_candidates(candidates, evidence, trade_date=trade_date)
        weak_evidence_queue = _build_weak_evidence_queue(adjusted_candidates)

    report = _render_report(
        topn_backfill_queue=topn_backfill_queue,
        weak_evidence_queue=weak_evidence_queue,
        adjusted_candidates=adjusted_candidates,
        top_n=top_n,
        trade_date=trade_date,
    )
    paths: dict[str, str] = {}
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        files = {
            "topn_backfill_queue": output / "tech_bottleneck_topn_evidence_backfill_queue.csv",
            "weak_evidence_queue": output / "tech_bottleneck_weak_evidence_queue.csv",
            "adjusted_candidates": output / "tech_bottleneck_evidence_adjusted_candidates.csv",
            "yanbaoke_tasks": output / "tech_bottleneck_yanbaoke_backfill_tasks.csv",
            "report": output / "tech_bottleneck_evidence_workflow_report.md",
        }
        topn_backfill_queue.to_csv(files["topn_backfill_queue"], index=False)
        weak_evidence_queue.to_csv(files["weak_evidence_queue"], index=False)
        adjusted_candidates.to_csv(files["adjusted_candidates"], index=False)
        yanbaoke_tasks.to_csv(files["yanbaoke_tasks"], index=False)
        files["report"].write_text(report, encoding="utf-8")
        paths = {key: str(value) for key, value in files.items()}

    return {
        "topn_backfill_queue": topn_backfill_queue,
        "weak_evidence_queue": weak_evidence_queue,
        "adjusted_candidates": adjusted_candidates,
        "yanbaoke_tasks": yanbaoke_tasks,
        "report": report,
        "paths": paths,
    }


def _prepare_asset_queue(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in ["asset_id", "stock_name", "ts_code", "primary_chain_id", "source_collection_priority"]:
        if column not in result.columns:
            result[column] = ""
    result["source_collection_priority"] = pd.to_numeric(result["source_collection_priority"], errors="coerce").fillna(0)
    return result.sort_values(["source_collection_priority", "asset_id"], ascending=[False, True]).reset_index(drop=True)


def _prepare_evidence_detail(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "asset_id" not in result.columns:
        result["asset_id"] = ""
    for column in ["source_backed_field_count", "artifact_only_or_missing_field_count"]:
        if column not in result.columns:
            result[column] = 0
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0).astype(int)
    for field in FIELD_COLUMNS:
        grade_col = f"{field}_evidence_grade"
        if grade_col not in result.columns:
            result[grade_col] = ""
    result["evidence_status"] = result.apply(_evidence_status, axis=1)
    result["missing_fields"] = result.apply(_missing_fields, axis=1)
    result["evidence_confidence_multiplier"] = result["evidence_status"].map(STATUS_MULTIPLIER).fillna(0.6)
    return result.drop_duplicates(subset=["asset_id"], keep="last")


def _evidence_status(row: pd.Series) -> str:
    source_backed = int(row.get("source_backed_field_count", 0) or 0)
    missing_count = int(row.get("artifact_only_or_missing_field_count", 0) or 0)
    if source_backed >= 3 and missing_count <= 0:
        return "strong"
    if source_backed >= 2:
        return "partial"
    if source_backed >= 1:
        return "weak_pending_backfill"
    return "missing_blocking"


def _missing_fields(row: pd.Series) -> str:
    missing = []
    for field in FIELD_COLUMNS:
        grade = _text(row.get(f"{field}_evidence_grade"))
        if grade in {"", "missing", "artifact_only"}:
            missing.append(field)
    return "|".join(missing)


def _build_topn_backfill_queue(top_assets: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    merged = top_assets.merge(
        evidence[
            [
                "asset_id",
                "source_backed_field_count",
                "artifact_only_or_missing_field_count",
                "evidence_status",
                "missing_fields",
                "evidence_confidence_multiplier",
            ]
        ],
        on="asset_id",
        how="left",
        suffixes=("", "_evidence"),
    )
    _prefer_evidence_columns(
        merged,
        [
            "source_backed_field_count",
            "artifact_only_or_missing_field_count",
            "evidence_status",
            "missing_fields",
            "evidence_confidence_multiplier",
        ],
    )
    merged["source_backed_field_count"] = pd.to_numeric(merged["source_backed_field_count"], errors="coerce").fillna(0).astype(int)
    merged["artifact_only_or_missing_field_count"] = (
        pd.to_numeric(merged["artifact_only_or_missing_field_count"], errors="coerce").fillna(3).astype(int)
    )
    merged["evidence_status"] = merged["evidence_status"].fillna("missing_blocking")
    merged["missing_fields"] = merged["missing_fields"].fillna("|".join(FIELD_COLUMNS))
    merged["source_backed_field_count"] = pd.to_numeric(
        merged["source_backed_field_count"], errors="coerce"
    ).fillna(0).astype(int)
    merged["artifact_only_or_missing_field_count"] = pd.to_numeric(
        merged["artifact_only_or_missing_field_count"], errors="coerce"
    ).fillna(len(FIELD_COLUMNS)).astype(int)
    merged["evidence_confidence_multiplier"] = pd.to_numeric(
        merged["evidence_confidence_multiplier"], errors="coerce"
    ).fillna(0.6)
    result = merged[merged["evidence_status"].ne("strong")].copy()
    result["backfill_reason"] = result["evidence_status"].map(
        {
            "partial": "partial evidence; fill remaining fields",
            "weak_pending_backfill": "weak source-backed evidence; prioritize backfill",
            "missing_blocking": "missing source-backed evidence; block high-confidence promotion",
        }
    )
    columns = [
        "asset_id",
        "ts_code",
        "stock_name",
        "primary_chain_id",
        "source_collection_priority",
        "evidence_status",
        "source_backed_field_count",
        "artifact_only_or_missing_field_count",
        "missing_fields",
        "backfill_reason",
    ]
    return result[[column for column in columns if column in result.columns]].reset_index(drop=True)


def _build_adjusted_candidates(candidates: pd.DataFrame, evidence: pd.DataFrame, *, trade_date: str | None) -> pd.DataFrame:
    frame = candidates.copy()
    if trade_date and "trade_date" in frame.columns:
        frame = frame[frame["trade_date"].astype(str).eq(str(trade_date))].copy()
    for column in ["asset_id", "stock_name", "primary_chain_id"]:
        if column not in frame.columns:
            frame[column] = ""
    score_col = _score_column(frame)
    frame[score_col] = pd.to_numeric(frame[score_col], errors="coerce").fillna(0.0)
    merged = frame.merge(
        evidence[
            [
                "asset_id",
                "source_backed_field_count",
                "artifact_only_or_missing_field_count",
                "evidence_status",
                "missing_fields",
                "evidence_confidence_multiplier",
            ]
        ],
        on="asset_id",
        how="left",
        suffixes=("", "_evidence"),
    )
    _prefer_evidence_columns(
        merged,
        [
            "source_backed_field_count",
            "artifact_only_or_missing_field_count",
            "evidence_status",
            "missing_fields",
            "evidence_confidence_multiplier",
        ],
    )
    merged["evidence_status"] = merged["evidence_status"].fillna("missing_blocking")
    merged["missing_fields"] = merged["missing_fields"].fillna("|".join(FIELD_COLUMNS))
    merged["evidence_confidence_multiplier"] = pd.to_numeric(
        merged["evidence_confidence_multiplier"], errors="coerce"
    ).fillna(0.6)
    merged["raw_candidate_score"] = merged[score_col]
    merged["evidence_adjusted_score"] = merged["raw_candidate_score"] * merged["evidence_confidence_multiplier"]
    merged = merged.sort_values(["evidence_adjusted_score", "raw_candidate_score", "asset_id"], ascending=[False, False, True])
    merged["evidence_adjusted_rank"] = range(1, len(merged) + 1)
    return merged.reset_index(drop=True)


def _build_weak_evidence_queue(adjusted_candidates: pd.DataFrame) -> pd.DataFrame:
    if adjusted_candidates.empty:
        return pd.DataFrame()
    weak = adjusted_candidates[adjusted_candidates["evidence_status"].isin(["weak_pending_backfill", "missing_blocking", "partial"])].copy()
    if "bottleneck_rank" in weak.columns:
        weak["bottleneck_rank"] = pd.to_numeric(weak["bottleneck_rank"], errors="coerce")
        weak = weak.sort_values(["bottleneck_rank", "asset_id"], ascending=[True, True])
    columns = [
        "trade_date",
        "asset_id",
        "stock_name",
        "primary_chain_id",
        "bottleneck_rank",
        "raw_candidate_score",
        "evidence_adjusted_score",
        "evidence_adjusted_rank",
        "evidence_status",
        "missing_fields",
        "source_backed_field_count",
        "artifact_only_or_missing_field_count",
    ]
    return weak[[column for column in columns if column in weak.columns]].reset_index(drop=True)


def _build_yanbaoke_tasks(queue: pd.DataFrame, *, trade_date: str | None) -> pd.DataFrame:
    rows = []
    for row in queue.to_dict("records"):
        rows.append(
            {
                "asset_id": row.get("asset_id", ""),
                "ts_code": row.get("ts_code", ""),
                "stock_name": row.get("stock_name", ""),
                "start_date": "2024-01-01",
                "end_date": str(trade_date or pd.Timestamp.today().strftime("%Y-%m-%d")),
                "status": "pending",
                "source_collection_priority": row.get("source_collection_priority", ""),
                "evidence_status": row.get("evidence_status", ""),
                "missing_fields": row.get("missing_fields", ""),
            }
        )
    return pd.DataFrame(rows)


def _score_column(frame: pd.DataFrame) -> str:
    for column in ["bottleneck_score", "score_total", "score", "hit_count"]:
        if column in frame.columns:
            return column
    frame["score"] = 0.0
    return "score"


def _prefer_evidence_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        evidence_column = f"{column}_evidence"
        if evidence_column in frame.columns:
            frame[column] = frame[evidence_column]


def _render_report(
    *,
    topn_backfill_queue: pd.DataFrame,
    weak_evidence_queue: pd.DataFrame,
    adjusted_candidates: pd.DataFrame,
    top_n: int,
    trade_date: str | None,
) -> str:
    lines = [
        "# Tech Bottleneck Evidence Workflow",
        "",
        f"- trade_date: {trade_date or ''}",
        f"- top_n: {top_n}",
        f"- topn_backfill_assets: {len(topn_backfill_queue)}",
        f"- weak_daily_candidates: {len(weak_evidence_queue)}",
        "",
        "## Evidence Status",
        "",
    ]
    if not adjusted_candidates.empty:
        lines.append(adjusted_candidates["evidence_status"].value_counts().rename_axis("evidence_status").reset_index(name="count").to_markdown(index=False))
    else:
        lines.append("No candidate input.")
    lines.extend(["", "## Top Backfill Queue", "", topn_backfill_queue.head(30).to_markdown(index=False) if not topn_backfill_queue.empty else "No rows."])
    return "\n".join(lines) + "\n"


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()
