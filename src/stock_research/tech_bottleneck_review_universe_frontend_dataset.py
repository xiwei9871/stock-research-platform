from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.stock_metadata_db_hydration import load_stock_metadata_from_db


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_review_universe_frontend_dataset_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME

V5_HYDRATED = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_v5_evidence_hydration_v1/tech_bottleneck_review_universe_v5_hydrated_frontend_ready.csv"
)
V5_HYDRATED_EVIDENCE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_v5_evidence_hydration_v1/tech_bottleneck_review_universe_v5_evidence_index.csv"
)
TARGETED = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_targeted_evidence_collection_v1/tech_bottleneck_review_universe_targeted_evidence_frontend_ready.csv"
)
TARGETED_EVIDENCE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_targeted_evidence_collection_v1/tech_bottleneck_review_universe_targeted_evidence_index.csv"
)
V7_PROPOSAL = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v7_proposal_v1/tech_bottleneck_quality_pool_layer_v7_proposal.csv"
)
V7_EVIDENCE = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v7_proposal_v1/tech_bottleneck_quality_pool_layer_v7_evidence_index.csv"
)
V6_EVIDENCE = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v6_proposal_v1/tech_bottleneck_quality_pool_layer_v6_evidence_index.csv"
)
V7_LEDGER = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v7_manual_approval_ingest_v1/v7_manual_approval_ledger.csv"
)
A_SHARE_UNIVERSE = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_a_share_candidate_universe_v1/a_share_candidate_universe.csv"
)
ENRICHED_REPORT_STATUS = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_reports_enriched_v1/hard_tech_review_pool_with_enriched_report_status.csv"
)

FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

DATASET_COLUMNS = [
    "stock_code",
    "stock_name",
    "review_universe_source",
    "current_layer_status",
    "manual_approval_status",
    "frontend_review_status",
    "evidence_count",
    "page_citation_count",
    "source_pdf_count",
    "primary_source_supported",
    "hard_tech_domain",
    "supply_chain_role_hint",
    "business_relevance_hint",
    "bottleneck_or_chokepoint_hint",
    "concept_pollution_risk",
    "route_around_or_substitution_risk",
    "value_capture_risk",
    "disconfirmation_trigger",
    "next_primary_source_to_check",
    "strongest_primary_source_claim",
    "weakest_or_riskiest_claim",
    "evidence_summary_for_review",
    "reviewer_decision",
    "reviewer_note",
    "used_for_signal",
    "used_for_admission",
    "auto_added_to_quality_pool",
    "industry",
    "concept_tags",
    "evidence_strength",
    "bottleneck_relevance",
    "source_group",
    "previous_tier",
    "bottleneck_confidence_score",
    "evidence_quality_score",
]

EVIDENCE_COLUMNS = [
    "stock_code",
    "stock_name",
    "review_universe_source",
    "source_file",
    "source_type",
    "source_title",
    "source_date",
    "page",
    "evidence_text",
    "evidence_claim_type",
    "citation_quality",
    "research_only",
    "used_for_signal",
    "used_for_admission",
]


def _stock_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path, dtype={"stock_code": str}).fillna("")
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _non_empty(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return default if not text or text.lower() == "nan" else text


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _summary_text(row: dict[str, Any]) -> str:
    parts = [
        f"evidence={row['evidence_count']}",
        f"page_citations={row['page_citation_count']}",
        f"sources={row['source_pdf_count']}",
        f"domain={row['hard_tech_domain']}",
        f"role={row['supply_chain_role_hint']}",
        f"bottleneck={row['bottleneck_or_chokepoint_hint']}",
    ]
    return "; ".join(parts)


def _int_value(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _score_value(value: Any) -> int | None:
    try:
        if str(value).strip() == "":
            return None
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _clamp_score(value: float, low: int, high: int) -> int:
    return int(max(low, min(high, round(value))))


def _metadata_maps(universe: pd.DataFrame, report_status: pd.DataFrame) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    universe_map = universe.set_index("stock_code").to_dict("index") if not universe.empty else {}
    report_map = report_status.set_index("stock_code").to_dict("index") if not report_status.empty else {}
    return universe_map, report_map


def _load_database_stock_metadata(stock_codes: list[str]) -> pd.DataFrame:
    try:
        return load_stock_metadata_from_db(stock_codes=stock_codes, as_of_date="2026-07-08")
    except Exception:  # noqa: BLE001 - research CSV remains the safe fallback when DB is unavailable.
        return pd.DataFrame()


def _database_metadata_map(metadata: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if metadata.empty or "stock_code" not in metadata.columns:
        return {}
    frame = metadata.copy()
    frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame.set_index("stock_code").to_dict("index")


def _concept_tags(meta: dict[str, Any], row: pd.Series | dict[str, Any]) -> str:
    tags = [
        _non_empty(meta.get("tech_bottleneck_domain")),
        _non_empty(meta.get("tech_bottleneck_sub_domain")),
        _non_empty(meta.get("supply_chain_role")),
        _non_empty(row.get("current_layer_status") if isinstance(row, dict) else row.get("current_layer_status")),
    ]
    unique = []
    for tag in tags:
        if tag and tag not in unique:
            unique.append(tag)
    return " / ".join(unique) if unique else "待人工补行业主题"


def _display_industry(meta: dict[str, Any], db_meta: dict[str, Any]) -> str:
    db_industry = _non_empty(db_meta.get("industry"))
    if db_industry:
        return db_industry
    return _non_empty(meta.get("industry"), _non_empty(meta.get("tech_bottleneck_domain"), "待人工补行业"))


def _display_concept_tags(meta: dict[str, Any], row: pd.Series | dict[str, Any], db_meta: dict[str, Any]) -> str:
    db_concepts = _non_empty(db_meta.get("concept_tags"))
    if db_concepts and db_concepts != "no_concept_mapping_found":
        return db_concepts
    return _concept_tags(meta, row)


def _row_get(row: pd.Series | dict[str, Any], key: str, default: Any = "") -> Any:
    return row.get(key, default)


def _evidence_strength(row: dict[str, Any], meta: dict[str, Any], report: dict[str, Any]) -> str:
    evidence_count = _int_value(row.get("evidence_count"))
    page_count = _int_value(row.get("page_citation_count"))
    source_count = _int_value(row.get("source_pdf_count"))
    if page_count >= 20 and source_count >= 3:
        return "strong"
    if page_count >= 10 and source_count >= 2:
        return "sufficient"
    if page_count > 0 and evidence_count > 0:
        return "moderate"
    report_value = _non_empty(report.get("evidence_strength_y") or report.get("evidence_strength"))
    if report_value and report_value not in {"missing", "pending_primary_source"}:
        return report_value
    meta_value = _non_empty(meta.get("evidence_strength"))
    return meta_value or "insufficient"


def _bottleneck_relevance(row: dict[str, Any], meta: dict[str, Any], report: dict[str, Any]) -> str:
    bottleneck_hint = str(row.get("bottleneck_or_chokepoint_hint", "")).lower()
    role = str(meta.get("supply_chain_role", "")).lower()
    if "strong" in bottleneck_hint or "chokepoint" in role or "bottleneck" in role:
        return "core"
    if "moderate" in bottleneck_hint or "supported" in bottleneck_hint:
        return "core_pending"
    if "weak" in bottleneck_hint or "beneficiary" in role or "concept" in role:
        return "adjacent"
    report_value = _non_empty(report.get("bottleneck_relevance_y") or report.get("bottleneck_relevance"))
    if report_value and report_value not in {"missing", "unclear"}:
        return report_value
    return "unclear"


def _display_scores(row: dict[str, Any], meta: dict[str, Any], report: dict[str, Any]) -> tuple[int, int]:
    report_bottleneck = _score_value(report.get("bottleneck_confidence_score"))
    report_evidence = _score_value(report.get("evidence_quality_score"))
    if report_bottleneck is not None and report_evidence is not None:
        return report_bottleneck, report_evidence

    evidence_count = _int_value(row.get("evidence_count"))
    page_count = _int_value(row.get("page_citation_count"))
    source_count = _int_value(row.get("source_pdf_count"))
    primary_supported = bool(row.get("primary_source_supported"))

    evidence_score = 22
    evidence_score += min(evidence_count, 80) * 0.22
    evidence_score += min(page_count, 45) * 0.72
    evidence_score += min(source_count, 5) * 3.2
    if primary_supported:
        evidence_score += 7
    if "missing" in str(row.get("next_primary_source_to_check", "")).lower():
        evidence_score -= 4

    bottleneck_score = 48
    hard_tech = str(row.get("hard_tech_domain", "")).lower()
    role_hint = str(row.get("supply_chain_role_hint", "")).lower()
    business = str(row.get("business_relevance_hint", "")).lower()
    bottleneck = str(row.get("bottleneck_or_chokepoint_hint", "")).lower()
    concept_risk = str(row.get("concept_pollution_risk", "")).lower()
    route_risk = str(row.get("route_around_or_substitution_risk", "")).lower()
    value_risk = str(row.get("value_capture_risk", "")).lower()
    meta_role = str(meta.get("supply_chain_role", "")).lower()
    if "strong" in hard_tech or "supported" in hard_tech:
        bottleneck_score += 8
    if "strong" in bottleneck:
        bottleneck_score += 12
    elif "moderate" in bottleneck or "supported" in bottleneck:
        bottleneck_score += 7
    if "chokepoint" in meta_role or "bottleneck" in meta_role:
        bottleneck_score += 7
    elif "component" in meta_role or "equipment" in meta_role or "material" in meta_role:
        bottleneck_score += 4
    if "moderate" in role_hint or "supported" in role_hint:
        bottleneck_score += 4
    if "core" in business or "supported" in business:
        bottleneck_score += 6
    if primary_supported:
        bottleneck_score += 4
    bottleneck_score += min(page_count // 6, 6)
    if "high" in concept_risk:
        bottleneck_score -= 10
    if "weak" in route_risk or "high" in route_risk:
        bottleneck_score -= 5
    elif "moderate" in route_risk:
        bottleneck_score -= 2
    if "weak" in value_risk or "unclear" in value_risk:
        bottleneck_score -= 3
    if bool(row.get("disconfirmation_trigger")):
        bottleneck_score -= 2

    return _clamp_score(bottleneck_score, 45, 95), _clamp_score(evidence_score, 20, 90)


def _apply_display_enrichment(
    data: dict[str, Any],
    source_row: pd.Series | dict[str, Any],
    meta: dict[str, Any],
    report: dict[str, Any],
    db_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    db_meta = db_meta or {}
    bottleneck_score, evidence_score = _display_scores(data, meta, report)
    source_group = _non_empty(data.get("source_group") or _row_get(source_row, "source_group"))
    previous_tier = _non_empty(report.get("previous_tier") or meta.get("candidate_tier") or data.get("previous_tier") or _row_get(source_row, "proposal_source"))
    data.update(
        {
            "industry": _display_industry(meta, db_meta),
            "concept_tags": _display_concept_tags(meta, source_row, db_meta),
            "evidence_strength": _evidence_strength(data, meta, report),
            "bottleneck_relevance": _bottleneck_relevance(data, meta, report),
            "source_group": source_group or data.get("review_universe_source", ""),
            "previous_tier": previous_tier or _non_empty(meta.get("candidate_tier"), data.get("current_layer_status", "")),
            "bottleneck_confidence_score": bottleneck_score,
            "evidence_quality_score": evidence_score,
        }
    )
    return data


def _row_from_v5(
    row: pd.Series,
    source: str,
    universe_map: dict[str, dict[str, Any]],
    report_map: dict[str, dict[str, Any]],
    db_metadata_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    data = {
        "stock_code": row["stock_code"],
        "stock_name": row.get("stock_name", ""),
        "review_universe_source": source,
        "current_layer_status": row.get("current_layer_status", ""),
        "manual_approval_status": "pending_manual_approval",
        "frontend_review_status": "pending_review",
        "evidence_count": int(float(row.get("evidence_count") or 0)),
        "page_citation_count": int(float(row.get("page_citation_count") or 0)),
        "source_pdf_count": int(float(row.get("source_pdf_count") or 0)),
        "primary_source_supported": _truthy(row.get("primary_source_supported")),
        "hard_tech_domain": _non_empty(row.get("hard_tech_domain"), "supported"),
        "supply_chain_role_hint": _non_empty(row.get("supply_chain_role_hint"), "supported"),
        "business_relevance_hint": _non_empty(row.get("business_relevance_hint"), "supported"),
        "bottleneck_or_chokepoint_hint": _non_empty(row.get("bottleneck_or_chokepoint_hint"), "supported"),
        "concept_pollution_risk": _non_empty(row.get("concept_pollution_risk"), "not_detected_in_existing_artifacts"),
        "route_around_or_substitution_risk": _non_empty(row.get("route_around_or_substitution_risk"), "needs_manual_review"),
        "value_capture_risk": _non_empty(row.get("value_capture_risk"), "needs_manual_review"),
        "disconfirmation_trigger": _truthy(row.get("disconfirmation_trigger")),
        "next_primary_source_to_check": _non_empty(row.get("next_primary_source_to_check"), "manual review"),
        "strongest_primary_source_claim": _non_empty(row.get("strongest_primary_source_claim")),
        "weakest_or_riskiest_claim": _non_empty(row.get("weakest_or_riskiest_claim")),
        "reviewer_decision": "",
        "reviewer_note": "",
        "used_for_signal": False,
        "used_for_admission": False,
        "auto_added_to_quality_pool": False,
    }
    data["evidence_summary_for_review"] = _summary_text(data)
    return _apply_display_enrichment(
        data,
        row,
        universe_map.get(data["stock_code"], {}),
        report_map.get(data["stock_code"], {}),
        db_metadata_map.get(data["stock_code"], {}),
    )


def _v7_rows(
    v7: pd.DataFrame,
    ledger: pd.DataFrame,
    universe_map: dict[str, dict[str, Any]],
    report_map: dict[str, dict[str, Any]],
    db_metadata_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    ledger_codes = set(ledger["stock_code"].tolist())
    v7_new = v7[v7["stock_code"].isin(ledger_codes)].copy()
    ledger_by_code = ledger.set_index("stock_code").to_dict("index")
    rows: list[dict[str, Any]] = []
    for _, row in v7_new.sort_values("stock_code").iterrows():
        ledger_row = ledger_by_code.get(row["stock_code"], {})
        candidate_source = ledger_row.get("candidate_source", "")
        manual_status = "hold_for_review" if candidate_source == "v6_hold_for_review_unresolved" else "pending"
        data = {
            "stock_code": row["stock_code"],
            "stock_name": row.get("stock_name", ""),
            "review_universe_source": "v7_proposal_new",
            "current_layer_status": row.get("source_layer", row.get("quality_layer", "")),
            "manual_approval_status": manual_status,
            "frontend_review_status": "pending_review",
            "evidence_count": int(float(row.get("evidence_count") or ledger_row.get("evidence_row_count") or 0)),
            "page_citation_count": int(float(row.get("page_citation_count") or ledger_row.get("page_citation_count") or 0)),
            "source_pdf_count": int(float(row.get("source_pdf_count") or 0)),
            "primary_source_supported": _truthy(row.get("primary_source_supported") or ledger_row.get("primary_source_supported")),
            "hard_tech_domain": _non_empty(row.get("hard_tech_domain"), "supported"),
            "supply_chain_role_hint": _non_empty(row.get("supply_chain_role_hint"), "supported"),
            "business_relevance_hint": _non_empty(row.get("business_relevance_hint"), "supported"),
            "bottleneck_or_chokepoint_hint": _non_empty(row.get("bottleneck_or_chokepoint_hint"), "supported"),
            "concept_pollution_risk": _non_empty(row.get("concept_pollution_risk"), "not_detected_in_chunk"),
            "route_around_or_substitution_risk": _non_empty(row.get("remaining_evidence_gap_flags"), "needs_manual_review"),
            "value_capture_risk": "needs_manual_review",
            "disconfirmation_trigger": "risk" in str(row.get("concept_pollution_risk", "")).lower(),
            "next_primary_source_to_check": _non_empty(row.get("next_action_hint"), "manual review"),
            "strongest_primary_source_claim": "",
            "weakest_or_riskiest_claim": "",
            "reviewer_decision": "",
            "reviewer_note": "",
            "used_for_signal": False,
            "used_for_admission": False,
            "auto_added_to_quality_pool": False,
        }
        data["evidence_summary_for_review"] = _summary_text(data)
        rows.append(
            _apply_display_enrichment(
                data,
                row,
                universe_map.get(data["stock_code"], {}),
                report_map.get(data["stock_code"], {}),
                db_metadata_map.get(data["stock_code"], {}),
            )
        )
    return rows


def _build_dataset(
    v5_hydrated: pd.DataFrame,
    targeted: pd.DataFrame,
    v7: pd.DataFrame,
    ledger: pd.DataFrame,
    universe: pd.DataFrame,
    report_status: pd.DataFrame,
) -> pd.DataFrame:
    universe_map, report_map = _metadata_maps(universe, report_status)
    source_codes = sorted(
        {
            _stock_code(value)
            for frame in (v5_hydrated, targeted, v7, ledger)
            if "stock_code" in frame.columns
            for value in frame["stock_code"].tolist()
        }
    )
    db_metadata_map = _database_metadata_map(_load_database_stock_metadata(source_codes))
    rows: list[dict[str, Any]] = []
    rows.extend(
        _row_from_v5(row, "v5_hydrated", universe_map, report_map, db_metadata_map)
        for _, row in v5_hydrated.sort_values("stock_code").iterrows()
    )
    rows.extend(
        _row_from_v5(row, "v5_targeted_hydrated", universe_map, report_map, db_metadata_map)
        for _, row in targeted.sort_values("stock_code").iterrows()
    )
    rows.extend(_v7_rows(v7, ledger, universe_map, report_map, db_metadata_map))
    return pd.DataFrame(rows, columns=DATASET_COLUMNS).sort_values(["review_universe_source", "stock_code"]).reset_index(drop=True)


def _normalize_v5_evidence(frame: pd.DataFrame, source: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=EVIDENCE_COLUMNS)
    rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row.get("stock_name", ""),
                "review_universe_source": source,
                "source_file": row.get("source_path_or_url", ""),
                "source_type": row.get("source_type", ""),
                "source_title": row.get("source_title", ""),
                "source_date": "",
                "page": row.get("page", ""),
                "evidence_text": row.get("claim", ""),
                "evidence_claim_type": row.get("supports_field", ""),
                "citation_quality": row.get("citation_quality", row.get("provenance_status", "")),
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return pd.DataFrame(rows, columns=EVIDENCE_COLUMNS)


def _normalize_v7_evidence(v6_evidence: pd.DataFrame, v7_evidence: pd.DataFrame, ledger: pd.DataFrame) -> pd.DataFrame:
    ledger_codes = set(ledger["stock_code"].tolist())
    frames = []
    for frame in [v6_evidence, v7_evidence]:
        if frame.empty:
            continue
        subset = frame[frame["stock_code"].isin(ledger_codes)].copy()
        if subset.empty:
            continue
        rows: list[dict[str, Any]] = []
        for _, row in subset.iterrows():
            rows.append(
                {
                    "stock_code": row["stock_code"],
                    "stock_name": row.get("stock_name", ""),
                    "review_universe_source": "v7_proposal_new",
                    "source_file": row.get("source_file", ""),
                    "source_type": row.get("source_type", ""),
                    "source_title": row.get("source_title", ""),
                    "source_date": row.get("source_date", ""),
                    "page": row.get("page", ""),
                    "evidence_text": row.get("evidence_text", ""),
                    "evidence_claim_type": row.get("evidence_claim_type", ""),
                    "citation_quality": row.get("citation_quality", ""),
                    "research_only": True,
                    "used_for_signal": False,
                    "used_for_admission": False,
                }
            )
        frames.append(pd.DataFrame(rows, columns=EVIDENCE_COLUMNS))
    if not frames:
        return pd.DataFrame(columns=EVIDENCE_COLUMNS)
    return pd.concat(frames, ignore_index=True).drop_duplicates().sort_values(["stock_code", "source_file", "page"])


def _source_index(evidence: pd.DataFrame) -> pd.DataFrame:
    sources = evidence[
        ["stock_code", "stock_name", "review_universe_source", "source_file", "source_type", "source_title"]
    ].drop_duplicates()
    sources = sources[sources["source_file"].astype(str).str.len() > 0].copy()
    sources["research_only"] = True
    sources["used_for_signal"] = False
    sources["used_for_admission"] = False
    return sources.sort_values(["stock_code", "source_file"]).reset_index(drop=True)


def _filter_options(dataset: pd.DataFrame) -> dict[str, list[Any]]:
    fields = [
        "review_universe_source",
        "current_layer_status",
        "manual_approval_status",
        "hard_tech_domain",
        "supply_chain_role_hint",
        "concept_pollution_risk",
        "route_around_or_substitution_risk",
        "value_capture_risk",
        "industry",
        "concept_tags",
        "evidence_strength",
        "bottleneck_relevance",
        "source_group",
        "previous_tier",
        "primary_source_supported",
        "frontend_review_status",
        "reviewer_decision",
    ]
    return {field: sorted(dataset[field].drop_duplicates().tolist(), key=lambda value: str(value)) for field in fields}


def _summary(dataset: pd.DataFrame, evidence: pd.DataFrame, sources: pd.DataFrame) -> dict[str, Any]:
    source_counts = dataset["review_universe_source"].value_counts().to_dict()
    strategy_clean = _strategy_diff_clean()
    duplicate_count = int(dataset["stock_code"].duplicated().sum())
    used_for_signal_count = int(dataset["used_for_signal"].astype(bool).sum())
    used_for_admission_count = int(dataset["used_for_admission"].astype(bool).sum())
    auto_added_count = int(dataset["auto_added_to_quality_pool"].astype(bool).sum())
    remaining_gap = int(
        (
            (dataset["evidence_count"].astype(int) <= 0)
            | (dataset["page_citation_count"].astype(int) <= 0)
            | (dataset["source_pdf_count"].astype(int) <= 0)
        ).sum()
    )
    violation = (
        source_counts.get("v5_hydrated", 0) != 271
        or source_counts.get("v7_proposal_new", 0) != 78
        or source_counts.get("v5_targeted_hydrated", 0) != 29
        or len(dataset) != 378
        or duplicate_count != 0
        or remaining_gap != 0
        or used_for_signal_count != 0
        or used_for_admission_count != 0
        or auto_added_count != 0
        or not strategy_clean
    )
    if violation:
        decision = "blocked_due_to_guardrail_violation"
    elif any(str(value).strip() == "" for value in dataset["hard_tech_domain"].tolist()):
        decision = "conditionally_ready_with_field_gaps"
    else:
        decision = "tech_bottleneck_review_universe_frontend_dataset_ready"
    return {
        "task_name": TASK_NAME,
        "review_universe_total_count": 378,
        "v5_hydrated_count": int(source_counts.get("v5_hydrated", 0)),
        "v7_proposal_new_count": int(source_counts.get("v7_proposal_new", 0)),
        "v5_targeted_hydrated_count": int(source_counts.get("v5_targeted_hydrated", 0)),
        "frontend_dataset_count": int(len(dataset)),
        "duplicate_stock_count": duplicate_count,
        "remaining_evidence_gap_count": remaining_gap,
        "evidence_index_row_count": int(len(evidence)),
        "source_index_row_count": int(len(sources)),
        "primary_source_collection_performed": False,
        "new_pdf_download_count": 0,
        "evidence_backfill_performed": False,
        "core_equivalence_performed": False,
        "frontend_write_performed": False,
        "dashboard_code_modified": False,
        "frozen_quality_pool_generated": False,
        "auto_added_to_quality_pool_count": auto_added_count,
        "used_for_signal_count": used_for_signal_count,
        "used_for_admission_count": used_for_admission_count,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "strategy_file_diff_clean": strategy_clean,
        "acceptance_decision": decision,
    }


def _write_report(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Tech Bottleneck Review Universe Frontend Dataset v1",
        "",
        "## 1. Scope",
        "This research-only step generates data files for a future review panel. It does not develop a page, write dashboard code, run collection/backfill/equivalence, freeze a pool, or connect to signal/admission/scoring/strategy.",
        "",
        "## 2. Dataset Composition",
        f"- v5_hydrated: {summary['v5_hydrated_count']}",
        f"- v7_proposal_new: {summary['v7_proposal_new_count']}",
        f"- v5_targeted_hydrated: {summary['v5_targeted_hydrated_count']}",
        f"- total: {summary['frontend_dataset_count']}",
        "",
        "## 3. Evidence Index",
        f"- evidence_index_row_count: {summary['evidence_index_row_count']}",
        f"- source_index_row_count: {summary['source_index_row_count']}",
        f"- remaining_evidence_gap_count: {summary['remaining_evidence_gap_count']}",
        "",
        "## 4. Guardrails",
        f"- frontend_write_performed: {str(summary['frontend_write_performed']).lower()}",
        f"- dashboard_code_modified: {str(summary['dashboard_code_modified']).lower()}",
        f"- frozen_quality_pool_generated: {str(summary['frozen_quality_pool_generated']).lower()}",
        f"- used_for_signal_count: {summary['used_for_signal_count']}",
        f"- used_for_admission_count: {summary['used_for_admission_count']}",
        f"- strategy_file_diff_clean: {str(summary['strategy_file_diff_clean']).lower()}",
        "",
        "## 5. Acceptance Decision",
        summary["acceptance_decision"],
        "",
        "## 6. Recommended Next Steps",
        "1. tech_bottleneck_stock_workspace_review_panel_v1",
        "2. tech_bottleneck_review_universe_manual_review_export_v1",
        "3. tech_bottleneck_review_universe_review_decision_ingest_v1",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    v5_hydrated = _read_csv(V5_HYDRATED)
    targeted = _read_csv(TARGETED)
    v7 = _read_csv(V7_PROPOSAL)
    ledger = _read_csv(V7_LEDGER)
    v5_evidence = _read_csv(V5_HYDRATED_EVIDENCE)
    targeted_evidence = _read_csv(TARGETED_EVIDENCE)
    v6_evidence = _read_csv(V6_EVIDENCE)
    v7_evidence = _read_csv(V7_EVIDENCE)
    universe = _read_csv(A_SHARE_UNIVERSE)
    report_status = _read_csv(ENRICHED_REPORT_STATUS)

    dataset = _build_dataset(v5_hydrated, targeted, v7, ledger, universe, report_status)
    evidence = pd.concat(
        [
            _normalize_v5_evidence(v5_evidence[v5_evidence["stock_code"].isin(set(v5_hydrated["stock_code"]))], "v5_hydrated"),
            _normalize_v5_evidence(targeted_evidence, "v5_targeted_hydrated"),
            _normalize_v7_evidence(v6_evidence, v7_evidence, ledger),
        ],
        ignore_index=True,
    ).drop_duplicates()
    evidence = evidence[evidence["stock_code"].isin(set(dataset["stock_code"]))].sort_values(
        ["review_universe_source", "stock_code", "source_file", "page"]
    )
    sources = _source_index(evidence)
    filters = _filter_options(dataset)
    summary = _summary(dataset, evidence, sources)
    guardrails = {
        key: summary[key]
        for key in [
            "task_name",
            "review_universe_total_count",
            "v5_hydrated_count",
            "v7_proposal_new_count",
            "v5_targeted_hydrated_count",
            "frontend_dataset_count",
            "duplicate_stock_count",
            "remaining_evidence_gap_count",
            "primary_source_collection_performed",
            "new_pdf_download_count",
            "evidence_backfill_performed",
            "core_equivalence_performed",
            "frontend_write_performed",
            "dashboard_code_modified",
            "frozen_quality_pool_generated",
            "auto_added_to_quality_pool_count",
            "used_for_signal_count",
            "used_for_admission_count",
            "price_move_used_for_signal",
            "low_position_used_for_signal",
            "strategy_file_diff_clean",
            "acceptance_decision",
        ]
    }
    dataset.to_csv(output_dir / "tech_bottleneck_review_universe_frontend_dataset.csv", index=False)
    evidence.to_csv(output_dir / "tech_bottleneck_review_universe_frontend_evidence_index.csv", index=False)
    sources.to_csv(output_dir / "tech_bottleneck_review_universe_frontend_source_index.csv", index=False)
    _write_json(output_dir / "tech_bottleneck_review_universe_frontend_filter_options.json", filters)
    _write_json(output_dir / "tech_bottleneck_review_universe_frontend_dataset_summary.json", summary)
    _write_json(output_dir / "tech_bottleneck_review_universe_frontend_guardrails.json", guardrails)
    _write_report(output_dir / "tech_bottleneck_review_universe_frontend_dataset_v1_report.md", summary)
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, sort_keys=True))
