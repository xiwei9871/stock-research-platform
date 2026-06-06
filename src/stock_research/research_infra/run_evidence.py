from __future__ import annotations

from pathlib import Path
from typing import Any

from stock_research.run_card import write_run_card


class EvidenceBundleValidationError(ValueError):
    """Raised when an evidence bundle is missing required research context."""


def write_evidence_bundle(
    *,
    output_dir: str | Path,
    run_type: str,
    run_id: str,
    title: str,
    research_question: str,
    sample_window: dict[str, Any],
    universe: dict[str, Any],
    feature_set: list[str] | tuple[str, ...],
    label_definition: dict[str, Any],
    input_artifacts: dict[str, Any],
    output_artifacts: dict[str, Any],
    metrics: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    caveats: list[str] | None = None,
    reuse_status: str = "draft",
    data_coverage: dict[str, Any] | None = None,
) -> dict[str, str]:
    _validate_required_context(
        research_question=research_question,
        sample_window=sample_window,
        universe=universe,
        output_artifacts=output_artifacts,
    )
    config = {
        "sample_window": sample_window,
        "universe": universe,
        "feature_set": list(feature_set),
        "label_definition": label_definition,
        "input_artifacts": input_artifacts,
    }
    metadata = {
        "research_question": str(research_question),
        "reuse_status": str(reuse_status),
        "caveats": list(caveats or []),
    }
    return write_run_card(
        output_dir=output_dir,
        run_type=run_type,
        run_id=run_id,
        title=title,
        config=config,
        metrics=metrics or {},
        artifact_paths=output_artifacts,
        warnings=warnings or [],
        metadata=metadata,
        data_coverage=data_coverage or {},
    )


def _validate_required_context(
    *,
    research_question: str,
    sample_window: dict[str, Any],
    universe: dict[str, Any],
    output_artifacts: dict[str, Any],
) -> None:
    missing: list[str] = []
    if not str(research_question).strip():
        missing.append("research_question")
    if not sample_window:
        missing.append("sample_window")
    if not universe:
        missing.append("universe")
    if not output_artifacts:
        missing.append("output_artifacts")
    if missing:
        raise EvidenceBundleValidationError(
            "missing required evidence bundle context: " + ", ".join(missing)
        )
