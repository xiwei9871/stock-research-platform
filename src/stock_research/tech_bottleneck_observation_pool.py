from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


OBSERVATION_POOL_COLUMNS = [
    "asset_id",
    "stock_name",
    "observation_start_date",
    "source_group",
    "review_priority",
    "review_action",
    "product_family",
    "evidence_quality_score",
    "candidate_count_for_asset",
    "candidate_dates_for_asset",
    "observation_horizons",
    "observation_status",
    "source_manifest",
]

COMPARISON_GROUP_COLUMNS = [
    "comparison_group",
    "asset_id",
    "stock_name",
    "observation_start_date",
    "source_trade_date",
    "rank",
    "product_family",
    "evidence_quality_score",
]


def build_observation_pool(
    *,
    promotion_assets: pd.DataFrame,
    candidates: pd.DataFrame,
    pass_pool: pd.DataFrame | None,
    source_manifest_path: Path | None,
    horizons: list[int],
) -> dict[str, Any]:
    normalized_promotions = _normalize_promotion_assets(promotion_assets)
    horizon_text = "|".join(str(horizon) for horizon in horizons)
    source_manifest = str(source_manifest_path) if source_manifest_path else ""

    observation_pool = normalized_promotions.copy()
    observation_pool["observation_start_date"] = observation_pool["trade_date"]
    observation_pool["source_group"] = "quality_promotion_pool"
    observation_pool["observation_horizons"] = horizon_text
    observation_pool["observation_status"] = "active"
    observation_pool["source_manifest"] = source_manifest
    observation_pool = observation_pool.reindex(columns=OBSERVATION_POOL_COLUMNS)

    comparison_groups = pd.concat(
        [
            _comparison_group(_normalize_candidates(candidates), "original_topn_candidates"),
            _comparison_group(_normalize_candidates(pass_pool), "readiness_pass_pool"),
            _comparison_group(normalized_promotions, "quality_promotion_pool"),
        ],
        ignore_index=True,
    ).reindex(columns=COMPARISON_GROUP_COLUMNS)

    manifest = {
        "observation_asset_count": int(observation_pool["asset_id"].nunique()) if not observation_pool.empty else 0,
        "observation_row_count": int(len(observation_pool)),
        "comparison_group_counts": comparison_groups["comparison_group"].value_counts().to_dict()
        if not comparison_groups.empty
        else {},
        "horizons": horizons,
        "source_manifest_path": source_manifest,
    }
    return {
        "observation_pool": observation_pool,
        "comparison_groups": comparison_groups,
        "manifest": manifest,
    }


def run_observation_pool_from_files(
    *,
    promotion_assets_csv: Path,
    candidates_csv: Path,
    pass_pool_csv: Path | None,
    output_dir: Path,
    source_manifest_path: Path | None,
    horizons: list[int],
) -> dict[str, Path]:
    promotion_assets = pd.read_csv(promotion_assets_csv)
    candidates = pd.read_csv(candidates_csv)
    pass_pool = pd.read_csv(pass_pool_csv) if pass_pool_csv else pd.DataFrame()
    outputs = build_observation_pool(
        promotion_assets=promotion_assets,
        candidates=candidates,
        pass_pool=pass_pool,
        source_manifest_path=source_manifest_path,
        horizons=horizons,
    )
    source_manifest_payload = _load_json(source_manifest_path)
    inputs = {
        "promotion_assets_csv": str(promotion_assets_csv),
        "candidates_csv": str(candidates_csv),
        "pass_pool_csv": str(pass_pool_csv) if pass_pool_csv else "",
        "source_manifest_path": str(source_manifest_path) if source_manifest_path else "",
        "source_manifest": source_manifest_payload,
    }
    return write_observation_pool_artifacts(outputs=outputs, output_dir=output_dir, inputs=inputs)


def write_observation_pool_artifacts(
    *,
    outputs: dict[str, Any],
    output_dir: Path,
    inputs: dict[str, Any],
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    observation_pool_path = output_dir / "tech_bottleneck_observation_pool.csv"
    comparison_groups_path = output_dir / "tech_bottleneck_comparison_groups.csv"
    summary_path = output_dir / "summary.md"
    manifest_path = output_dir / "manifest.json"

    observation_pool = outputs["observation_pool"]
    comparison_groups = outputs["comparison_groups"]
    observation_pool.to_csv(observation_pool_path, index=False)
    comparison_groups.to_csv(comparison_groups_path, index=False)

    manifest = {
        **outputs["manifest"],
        "inputs": inputs,
        "files": {
            "observation_pool": observation_pool_path.name,
            "comparison_groups": comparison_groups_path.name,
            "summary": summary_path.name,
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(_render_summary(manifest), encoding="utf-8")
    return {
        "observation_pool": observation_pool_path,
        "comparison_groups": comparison_groups_path,
        "summary": summary_path,
        "manifest": manifest_path,
    }


def _normalize_promotion_assets(frame: pd.DataFrame | None) -> pd.DataFrame:
    normalized = _normalize_candidates(frame)
    for column in [
        "review_priority",
        "review_action",
        "product_family",
        "candidate_dates_for_asset",
    ]:
        if column not in normalized.columns:
            normalized[column] = ""
        normalized[column] = normalized[column].astype("string").fillna("")
    for column in ["evidence_quality_score", "candidate_count_for_asset"]:
        if column not in normalized.columns:
            normalized[column] = 0
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce").fillna(0).astype(int)
    if "candidate_dates_for_asset" in normalized:
        normalized["candidate_dates_for_asset"] = normalized["candidate_dates_for_asset"].where(
            normalized["candidate_dates_for_asset"].ne(""),
            normalized["trade_date"],
        )
    return normalized.sort_values(["trade_date", "asset_id"]).drop_duplicates("asset_id", keep="first").copy()


def _normalize_candidates(frame: pd.DataFrame | None) -> pd.DataFrame:
    normalized = frame.copy() if frame is not None else pd.DataFrame()
    if "trade_date" not in normalized.columns and "candidate_trade_date" in normalized.columns:
        normalized = normalized.rename(columns={"candidate_trade_date": "trade_date"})
    for column in ["asset_id", "stock_name", "trade_date", "rank", "product_family", "evidence_quality_score"]:
        if column not in normalized.columns:
            normalized[column] = 0 if column in {"rank", "evidence_quality_score"} else ""
    normalized["asset_id"] = normalized["asset_id"].astype("string").fillna("")
    normalized["stock_name"] = normalized["stock_name"].astype("string").fillna("")
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    normalized["product_family"] = normalized["product_family"].astype("string").fillna("")
    normalized["rank"] = pd.to_numeric(normalized["rank"], errors="coerce").fillna(0).astype(int)
    normalized["evidence_quality_score"] = pd.to_numeric(normalized["evidence_quality_score"], errors="coerce").fillna(0).astype(int)
    return normalized[normalized["asset_id"].ne("") & normalized["trade_date"].ne("")].copy()


def _comparison_group(frame: pd.DataFrame, group_name: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=COMPARISON_GROUP_COLUMNS)
    grouped = frame.sort_values(["trade_date", "asset_id"]).drop_duplicates("asset_id", keep="first").copy()
    grouped["comparison_group"] = group_name
    grouped["observation_start_date"] = grouped["trade_date"]
    grouped["source_trade_date"] = grouped["trade_date"]
    return grouped.reindex(columns=COMPARISON_GROUP_COLUMNS)


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _render_summary(manifest: dict[str, Any]) -> str:
    counts = manifest.get("comparison_group_counts", {})
    lines = [
        "# tech-bottleneck observation pool",
        "",
        "This file defines observation inputs only. It is not a return test.",
        "",
        f"- observation_asset_count: {manifest.get('observation_asset_count', 0)}",
        f"- horizons: {'|'.join(str(item) for item in manifest.get('horizons', []))}",
        f"- source_manifest_path: {manifest.get('source_manifest_path', '')}",
        "",
        "## Comparison Groups",
    ]
    for group_name, count in counts.items():
        lines.append(f"- {group_name}: {count}")
    return "\n".join(lines) + "\n"
