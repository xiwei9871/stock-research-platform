from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.research_infra.attribution_cards import (
    AttributionCard,
    export_attribution_cards,
    render_attribution_card_markdown,
)
from stock_research.research_infra.artifact_index import (
    ResearchInfraArtifactIndexRecord,
    append_artifact_index_record,
)
from stock_research.research_infra.experiment_registry import (
    ExperimentRecord,
    append_experiment_record,
    read_experiment_registry,
)
from stock_research.research_infra.research_signals import (
    ResearchSignalRecord,
    export_research_signal_records,
)
from stock_research.research_infra.run_evidence import write_evidence_bundle


def build_mid_trend_review_with_research_infra(
    *,
    trade_date: str,
    strategy_variant: str,
    review_builder: Callable[[], dict[str, Any]],
    output_dir: str | Path,
    write_research_infra: bool = False,
) -> dict[str, Any]:
    review_result = review_builder()
    if not isinstance(review_result, dict):
        raise TypeError("review_builder must return a dict review_result")

    if not write_research_infra:
        return review_result

    research_infra = write_mid_trend_research_infra_artifacts(
        trade_date=trade_date,
        strategy_variant=strategy_variant,
        review_result=review_result,
        output_dir=output_dir,
    )
    return {**review_result, "research_infra": research_infra}


def write_mid_trend_research_infra_artifacts(
    *,
    trade_date: str,
    strategy_variant: str,
    review_result: dict[str, Any],
    output_dir: str | Path,
    artifact_index_path: str | Path | None = None,
) -> dict[str, Any]:
    sidecar_dir = Path(output_dir) / "research_infra"
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    review_rows = _review_rows(review_result)

    signals = _build_signals(review_rows, trade_date)
    attributions = _build_attributions(review_rows, trade_date, strategy_variant)

    signals_path = sidecar_dir / "research_signals.json"
    attributions_json_path = sidecar_dir / "attribution_cards.json"
    attributions_md_path = sidecar_dir / "attribution_cards.md"
    experiment_registry_path = sidecar_dir / "experiment_registry.jsonl"

    signals_path.write_text(
        json.dumps(
            export_research_signal_records(signals),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    attributions_json_path.write_text(
        json.dumps(
            export_attribution_cards(attributions),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    attributions_md_path.write_text(
        "\n\n".join(render_attribution_card_markdown(card) for card in attributions)
        + ("\n" if attributions else ""),
        encoding="utf-8",
    )

    run_card = write_evidence_bundle(
        output_dir=sidecar_dir / "run_card",
        run_type="mid_trend_portfolio_review",
        run_id=f"mid-trend-review-{trade_date}-{strategy_variant}",
        title=f"Mid-Trend Portfolio Review {trade_date}",
        research_question=(
            "Should current mid-trend candidates be held, deprioritized, or discussed?"
        ),
        sample_window={"start_date": trade_date, "end_date": trade_date},
        universe={
            "strategy_variant": strategy_variant,
            "review_row_count": int(len(review_rows)),
        },
        feature_set=[
            "research_support_score",
            "coverage_freshness_score",
            "risk_disclosure_score",
            "market_regime",
            "mainline_status",
            "final_label",
        ],
        label_definition={
            "name": "mid_trend_review_final_label",
            "source": "review_rows.final_label",
        },
        input_artifacts={},
        output_artifacts={
            **{
                str(key): str(value)
                for key, value in (review_result.get("paths") or {}).items()
            },
            "research_signals": str(signals_path),
            "attribution_cards_json": str(attributions_json_path),
            "attribution_cards_markdown": str(attributions_md_path),
        },
        metrics={
            "review_row_count": int(len(review_rows)),
            "research_signal_count": len(signals),
            "attribution_card_count": len(attributions),
        },
        warnings=[] if not review_rows.empty else ["empty_review_rows"],
        caveats=["review-only; no execution instruction"],
        reuse_status="monitor_only",
    )

    experiment_record = ExperimentRecord(
        experiment_id=f"mid-trend-review-infra-{trade_date}-{strategy_variant}",
        created_at=f"{trade_date}T15:00:00",
        objective="Standardize evidence for mid-trend review.",
        hypothesis=(
            "Standardized evidence improves review reproducibility and "
            "coverage-gap diagnosis."
        ),
        sample_window={"start_date": trade_date, "end_date": trade_date},
        universe={
            "strategy_variant": strategy_variant,
            "review_row_count": int(len(review_rows)),
        },
        feature_set_id="feature-set:mid-trend-review-infra-v1",
        label_id="label:mid-trend-review-final-label",
        model_or_rule_version="mid_trend_research_infra_integration_v1",
        constraints={"review_only": True},
        artifact_paths={
            "run_card": run_card["run_card_json_path"],
            "research_signals": str(signals_path),
            "attribution_cards_json": str(attributions_json_path),
        },
        conclusion="Monitor-only integration artifact.",
        reuse_status="monitor_only",
    )
    existing_experiment_ids = {
        record.experiment_id
        for record in read_experiment_registry(experiment_registry_path)
    }
    if experiment_record.experiment_id not in existing_experiment_ids:
        append_experiment_record(experiment_registry_path, experiment_record)

    if artifact_index_path is not None:
        append_artifact_index_record(
            artifact_index_path,
            ResearchInfraArtifactIndexRecord(
                run_id=f"mid-trend-review-{trade_date}-{strategy_variant}",
                run_type="mid_trend_portfolio_review",
                trade_date=trade_date,
                strategy_variant=strategy_variant,
                created_at=f"{trade_date}T15:00:00",
                research_infra_dir=str(sidecar_dir),
                run_card_json_path=run_card["run_card_json_path"],
                research_signals_json_path=str(signals_path),
                attribution_cards_json_path=str(attributions_json_path),
                attribution_cards_md_path=str(attributions_md_path),
                experiment_registry_path=str(experiment_registry_path),
                metrics={
                    "review_row_count": int(len(review_rows)),
                    "research_signal_count": len(signals),
                    "attribution_card_count": len(attributions),
                },
                warnings=[] if not review_rows.empty else ["empty_review_rows"],
                caveats=["review-only; no execution instruction"],
            ),
        )

    result = {
        "research_infra_dir": str(sidecar_dir),
        "research_signals_json_path": str(signals_path),
        "attribution_cards_json_path": str(attributions_json_path),
        "attribution_cards_md_path": str(attributions_md_path),
        "experiment_registry_path": str(experiment_registry_path),
        "run_card": run_card,
        "research_signal_count": len(signals),
        "attribution_card_count": len(attributions),
    }
    if artifact_index_path is not None:
        result["artifact_index_path"] = str(artifact_index_path)
    return result


def _review_rows(review_result: dict[str, Any]) -> pd.DataFrame:
    rows = review_result.get("review_rows")
    if isinstance(rows, pd.DataFrame):
        return rows.copy()
    return pd.DataFrame()


def _build_signals(
    review_rows: pd.DataFrame,
    trade_date: str,
) -> list[ResearchSignalRecord]:
    signals: list[ResearchSignalRecord] = []
    available_at = f"{trade_date}T15:00:00"
    for _, row in review_rows.iterrows():
        asset_id = str(row.get("asset_id", ""))
        ts_code = str(row.get("ts_code", ""))
        report_count = _int_or_zero(row.get("broker_report_count_90d"))
        risk_count = _int_or_zero(row.get("pdf_risk_section_count_90d"))
        support = _float_or_none(row.get("research_support_score_pit"))
        has_fresh_report = report_count > 0
        signal_specs = [
            (
                "research_support_score",
                support if has_fresh_report else None,
                "" if has_fresh_report else "no_fresh_report",
            ),
            (
                "coverage_freshness_score",
                float(report_count) if has_fresh_report else None,
                "" if has_fresh_report else "no_fresh_report",
            ),
            (
                "risk_disclosure_score",
                float(risk_count) if risk_count > 0 else None,
                _risk_disclosure_missingness(
                    has_fresh_report=has_fresh_report,
                    risk_count=risk_count,
                ),
            ),
        ]
        for signal_name, value, missingness_reason in signal_specs:
            signals.append(
                ResearchSignalRecord(
                    asset_id=asset_id,
                    ts_code=ts_code,
                    trade_date=trade_date,
                    signal_name=signal_name,
                    signal_value=value,
                    signal_type="numeric",
                    source_type="manual_review",
                    source_id=f"mid_trend_review:{trade_date}:{asset_id}",
                    availability_timestamp=available_at,
                    confidence="medium" if has_fresh_report else "thin",
                    missingness_reason=missingness_reason if value is None else "",
                )
            )
    return signals


def _build_attributions(
    review_rows: pd.DataFrame,
    trade_date: str,
    strategy_variant: str,
) -> list[AttributionCard]:
    cards: list[AttributionCard] = []
    for _, row in review_rows.iterrows():
        report_count = _int_or_zero(row.get("broker_report_count_90d"))
        final_label = str(row.get("final_label", ""))
        if report_count > 0 or "低优先级" not in final_label:
            continue
        asset_id = str(row.get("asset_id", ""))
        cards.append(
            AttributionCard(
                case_id=f"case:mid-trend:{asset_id}:{trade_date}:coverage-gap",
                asset_id=asset_id,
                ts_code=str(row.get("ts_code", "")),
                trade_date=trade_date,
                strategy_context=strategy_variant,
                failure_or_success_type="mixed",
                primary_cause="research_coverage_gap",
                secondary_causes=[],
                evidence={
                    "final_label": final_label,
                    "broker_report_count_90d": report_count,
                    "research_support_score_pit": _float_or_none(
                        row.get("research_support_score_pit")
                    ),
                },
                counterfactual=(
                    "Require fresh research coverage before high-priority hold review."
                ),
                preventability="partly_preventable",
                recommended_rule_change=(
                    "Flag low-priority holds with no fresh report coverage."
                ),
                confidence="medium",
            )
        )
    return cards


def _int_or_zero(value: Any) -> int:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return 0
    return int(parsed)


def _float_or_none(value: Any) -> float | None:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return float(parsed)


def _risk_disclosure_missingness(
    *,
    has_fresh_report: bool,
    risk_count: int,
) -> str:
    if risk_count > 0:
        return ""
    if has_fresh_report:
        return "no_risk_disclosure"
    return "no_fresh_report"
