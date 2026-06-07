from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


TOP100_ARTIFACT_FILES = {
    "candidates_top100": "candidates_top100.csv",
    "top50_vs_top100_diff": "top50_vs_top100_diff.csv",
    "baseline_comparison": "baseline_comparison.md",
    "manifest": "manifest.json",
}

P1_DECISIONS = {"auto_approve"}
P2_DECISIONS = {"needs_more_evidence", "needs_product_family_mapping"}
JOIN_KEYS = ["asset_id", "stock_name", "trade_date"]


def build_weekly_topn_candidates(*, score_rows: pd.DataFrame, top_n: int = 100) -> pd.DataFrame:
    if "score" not in score_rows:
        raise ValueError("score_rows must include score")
    for column in ["asset_id", "trade_date"]:
        if column not in score_rows:
            raise ValueError(f"score_rows must include {column}")

    candidates = score_rows.copy()
    if "stock_name" not in candidates:
        candidates["stock_name"] = ""
    candidates["asset_id"] = candidates["asset_id"].fillna("").astype(str)
    candidates["stock_name"] = candidates["stock_name"].fillna("").astype(str)
    candidates["trade_date"] = candidates["trade_date"].map(_normalize_date)
    candidates["_score_sort"] = pd.to_numeric(candidates["score"], errors="coerce")
    candidates = candidates[
        candidates["asset_id"].str.strip().ne("")
        & candidates["trade_date"].map(_is_valid_normalized_date)
        & candidates["_score_sort"].notna()
    ].copy()

    candidates = candidates.sort_values(
        ["trade_date", "_score_sort", "asset_id"],
        ascending=[True, False, True],
        na_position="last",
        kind="mergesort",
    )
    candidates = candidates.groupby("trade_date", group_keys=False).head(top_n).copy()
    candidates["rank"] = candidates.groupby("trade_date").cumcount() + 1
    candidates["in_top50_baseline"] = candidates["rank"].le(50)
    return candidates.drop(columns=["_score_sort"]).reset_index(drop=True)


def build_baseline_comparison(
    *,
    top100_candidates: pd.DataFrame,
    quality_review: pd.DataFrame,
    baseline_promotions: pd.DataFrame,
) -> dict[str, Any]:
    candidates = _normalize_candidates(top100_candidates)
    review = _normalize_quality_review(quality_review)
    baseline = _normalize_baseline_promotions(baseline_promotions)

    comparison = candidates.merge(review, on=JOIN_KEYS, how="left")
    comparison["p3_decision"] = comparison["p3_decision"].fillna("")
    top50_asset_ids = set(candidates.loc[candidates["in_top50_baseline"], "asset_id"])
    baseline_ids = set(baseline["asset_id"]) if "asset_id" in baseline else set()
    existing_asset_ids = top50_asset_ids | baseline_ids
    comparison["top100_increment_status"] = comparison.apply(
        _increment_status,
        axis=1,
        existing_asset_ids=existing_asset_ids,
    )
    diff = comparison[~comparison["in_top50_baseline"]].copy().reset_index(drop=True)
    manifest = _manifest(comparison, diff, baseline)
    markdown = _render_markdown(manifest, diff)

    return {
        "candidates_top100": comparison.reset_index(drop=True),
        "top50_vs_top100_diff": diff,
        "baseline_comparison_md": markdown,
        "manifest": manifest,
    }


def run_core_tech_top100_from_files(
    *,
    scores_csv: Path,
    quality_review_csv: Path,
    baseline_promotions_csv: Path,
    output_dir: Path,
    top_n: int = 100,
) -> dict[str, Path]:
    score_rows = pd.read_csv(scores_csv)
    quality_review = pd.read_csv(quality_review_csv)
    baseline_promotions = pd.read_csv(baseline_promotions_csv)
    candidates = build_weekly_topn_candidates(score_rows=score_rows, top_n=top_n)
    comparison = build_baseline_comparison(
        top100_candidates=candidates,
        quality_review=quality_review,
        baseline_promotions=baseline_promotions,
    )
    inputs = {
        "scores_csv": str(scores_csv),
        "quality_review_csv": str(quality_review_csv),
        "baseline_promotions_csv": str(baseline_promotions_csv),
        "top_n": top_n,
    }
    return write_core_tech_top100_artifacts(
        candidates_top100=comparison["candidates_top100"],
        comparison=comparison,
        output_dir=output_dir,
        inputs=inputs,
    )


def write_core_tech_top100_artifacts(
    *,
    candidates_top100: pd.DataFrame,
    comparison: dict[str, Any],
    output_dir: Path,
    inputs: dict[str, Any],
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {key: output_dir / filename for key, filename in TOP100_ARTIFACT_FILES.items()}

    candidates = candidates_top100.copy()
    diff = comparison["top50_vs_top100_diff"].copy()
    manifest = dict(comparison.get("manifest") or _manifest(candidates, diff, pd.DataFrame()))
    manifest["inputs"] = inputs
    manifest["files"] = {key: path.name for key, path in paths.items()}

    candidates.to_csv(paths["candidates_top100"], index=False)
    diff.to_csv(paths["top50_vs_top100_diff"], index=False)
    paths["baseline_comparison"].write_text(
        comparison.get("baseline_comparison_md") or _render_markdown(manifest, diff),
        encoding="utf-8",
    )
    paths["manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return paths


def _normalize_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    normalized = candidates.copy()
    for column in JOIN_KEYS:
        if column not in normalized:
            normalized[column] = ""
    if "rank" not in normalized:
        normalized["rank"] = 0
    if "in_top50_baseline" not in normalized:
        normalized["in_top50_baseline"] = pd.to_numeric(normalized["rank"], errors="coerce").fillna(0).le(50)

    normalized["asset_id"] = normalized["asset_id"].fillna("").astype(str)
    normalized["stock_name"] = normalized["stock_name"].fillna("").astype(str)
    normalized["trade_date"] = normalized["trade_date"].map(_normalize_date)
    normalized["rank"] = pd.to_numeric(normalized["rank"], errors="coerce").fillna(0).astype(int)
    normalized["in_top50_baseline"] = normalized["in_top50_baseline"].map(_as_bool)
    return normalized


def _normalize_quality_review(quality_review: pd.DataFrame) -> pd.DataFrame:
    normalized = quality_review.copy()
    for column in JOIN_KEYS:
        if column not in normalized:
            normalized[column] = ""
    if "p3_decision" not in normalized:
        normalized["p3_decision"] = ""

    normalized["asset_id"] = normalized["asset_id"].fillna("").astype(str)
    normalized["stock_name"] = normalized["stock_name"].fillna("").astype(str)
    normalized["trade_date"] = normalized["trade_date"].map(_normalize_date)
    normalized["p3_decision"] = normalized["p3_decision"].fillna("").astype(str)
    review_columns = JOIN_KEYS + [column for column in normalized.columns if column not in JOIN_KEYS]
    return normalized[review_columns].drop_duplicates(subset=JOIN_KEYS, keep="last")


def _normalize_baseline_promotions(baseline_promotions: pd.DataFrame) -> pd.DataFrame:
    normalized = baseline_promotions.copy()
    if "asset_id" not in normalized:
        normalized["asset_id"] = ""
    normalized["asset_id"] = normalized["asset_id"].fillna("").astype(str)
    return normalized


def _increment_status(row: pd.Series, *, existing_asset_ids: set[str] | None = None) -> str:
    if _as_bool(row.get("in_top50_baseline")):
        return "top50_baseline_row"
    if str(row.get("asset_id", "")) in (existing_asset_ids or set()):
        return "existing_top50_or_baseline_asset"
    decision = str(row.get("p3_decision", ""))
    if decision in P1_DECISIONS:
        return "new_p1_auto_promotion"
    if decision in P2_DECISIONS:
        return "new_p2_research_queue"
    return "new_p3_reject_or_noise"


def _manifest(comparison: pd.DataFrame, diff: pd.DataFrame, baseline_promotions: pd.DataFrame) -> dict[str, Any]:
    p1 = comparison["p3_decision"].isin(P1_DECISIONS)
    p2 = comparison["p3_decision"].isin(P2_DECISIONS)
    new_p1 = diff["top100_increment_status"].eq("new_p1_auto_promotion")
    new_p2 = diff["top100_increment_status"].eq("new_p2_research_queue")
    return {
        "top100_candidate_count": int(len(comparison)),
        "top100_asset_count": int(comparison["asset_id"].nunique()) if "asset_id" in comparison else 0,
        "baseline_p1_asset_count": int(baseline_promotions["asset_id"].nunique()) if "asset_id" in baseline_promotions else 0,
        "top100_p1_asset_count": int(comparison.loc[p1, "asset_id"].nunique()),
        "top100_p2_asset_count": int(comparison.loc[p2, "asset_id"].nunique()),
        "new_p1_from_rank_51_100": int(diff.loc[new_p1, "asset_id"].nunique()),
        "new_p2_from_rank_51_100": int(diff.loc[new_p2, "asset_id"].nunique()),
    }


def _render_markdown(manifest: dict[str, Any], diff: pd.DataFrame) -> str:
    p1_names = _names_for_status(diff, "new_p1_auto_promotion")
    p2_names = _names_for_status(diff, "new_p2_research_queue")
    lines = [
        "# Top50 vs Top100 Core-Tech Comparison",
        "",
        f"- Top50 baseline P1 count: {manifest['baseline_p1_asset_count']}",
        f"- Top100 core-tech P1 count: {manifest['top100_p1_asset_count']}",
        f"- Top100 core-tech P2 count: {manifest['top100_p2_asset_count']}",
        f"- New P1 from ranks 51-100: {manifest['new_p1_from_rank_51_100']} ({p1_names})",
        f"- New P2 from ranks 51-100: {manifest['new_p2_from_rank_51_100']} ({p2_names})",
    ]
    return "\n".join(lines) + "\n"


def _names_for_status(diff: pd.DataFrame, status: str) -> str:
    if diff.empty or "stock_name" not in diff:
        return "none"
    names = diff.loc[diff["top100_increment_status"].eq(status), "stock_name"].dropna().astype(str).tolist()
    return ", ".join(names) if names else "none"


def _normalize_date(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, int) and not isinstance(value, bool):
        parsed_compact = pd.to_datetime(str(value), format="%Y%m%d", errors="coerce")
        if not pd.isna(parsed_compact):
            return parsed_compact.strftime("%Y-%m-%d")
    if isinstance(value, str):
        compact_value = value.strip()
        if len(compact_value) == 8 and compact_value.isdigit():
            parsed_compact = pd.to_datetime(compact_value, format="%Y%m%d", errors="coerce")
            if not pd.isna(parsed_compact):
                return parsed_compact.strftime("%Y-%m-%d")
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return str(value)
    return parsed.strftime("%Y-%m-%d")


def _is_valid_normalized_date(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    return not pd.isna(pd.to_datetime(value, format="%Y-%m-%d", errors="coerce"))


def _as_bool(value: Any) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    return str(value).strip().casefold() in {"true", "1", "yes", "y"}
