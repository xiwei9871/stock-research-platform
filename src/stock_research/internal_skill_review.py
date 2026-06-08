from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from stock_research.agents.contracts import AgentObservation, AgentReport, EvidenceReference
from stock_research.agents.review import ReviewAgent


@dataclass(frozen=True)
class InternalSkillReviewResult:
    trade_date: str
    status: str
    review_agent_status: str
    observation_count: int
    output_dir: str
    agent_report_json_path: str
    markdown_path: str
    review_agent_result_path: str
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LocalReviewArtifact:
    path: str
    artifact_id: str
    evidence_type: str
    title: str
    summary: str


def run_internal_skill_review(
    *,
    trade_date: str,
    artifact_paths: list[str | Path],
    output_dir: str | Path,
) -> InternalSkillReviewResult:
    artifacts, warnings = _load_artifacts(artifact_paths)
    report = _build_agent_report(trade_date=trade_date, artifacts=artifacts)
    review_result = ReviewAgent().review(report)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    agent_report_json_path = output_path / "agent_report.json"
    markdown_path = output_path / "internal_skill_review.md"
    review_agent_result_path = output_path / "review_agent_result.json"

    agent_report_json_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    review_agent_result_path.write_text(
        json.dumps(review_result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        _render_markdown(report, review_result.to_dict(), warnings),
        encoding="utf-8",
    )

    status = "passed" if review_result.status == "passed" else "rejected"
    return InternalSkillReviewResult(
        trade_date=trade_date,
        status=status,
        review_agent_status=review_result.status,
        observation_count=len(report.observations),
        output_dir=str(output_path),
        agent_report_json_path=str(agent_report_json_path),
        markdown_path=str(markdown_path),
        review_agent_result_path=str(review_agent_result_path),
        warnings=warnings,
    )


def _load_artifacts(paths: list[str | Path]) -> tuple[list[LocalReviewArtifact], list[str]]:
    artifacts: list[LocalReviewArtifact] = []
    warnings: list[str] = []
    for item in paths:
        path = Path(item)
        if not path.exists():
            warnings.append(f"missing_artifact:{path}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        evidence_type = _infer_evidence_type(path)
        artifacts.append(
            LocalReviewArtifact(
                path=str(path),
                artifact_id=f"{evidence_type}:{path.stem}",
                evidence_type=evidence_type,
                title=path.stem.replace("_", " "),
                summary=_summarize_text(text),
            )
        )
    return artifacts, warnings


def _build_agent_report(*, trade_date: str, artifacts: list[LocalReviewArtifact]) -> AgentReport:
    generated_at = datetime.now(timezone.utc).isoformat()
    observations = [
        _build_observation(
            "risk",
            "risk-review",
            "谨慎",
            artifacts,
            ["risk_alert_report", "market_state_report", "run_card"],
        ),
        _build_observation(
            "watchlist",
            "watchlist-memo",
            "观察",
            artifacts,
            ["daily_topn_report", "risk_alert_report", "run_card"],
        ),
        _build_observation(
            "review",
            "position-review",
            "观察",
            artifacts,
            ["position_review_report", "market_state_report", "risk_alert_report", "run_card"],
        ),
    ]
    return AgentReport(
        trade_date=trade_date,
        mode="watchlist",
        generated_at=generated_at,
        metadata={"source": "internal_skill_review_offline_v1"},
        observations=observations,
    )


def _build_observation(
    agent_role: str,
    subject: str,
    decision_label: str,
    artifacts: list[LocalReviewArtifact],
    evidence_types: list[str],
) -> AgentObservation:
    selected = [artifact for artifact in artifacts if artifact.evidence_type in evidence_types]
    if not selected:
        selected = artifacts[:1]
    evidence = [
        EvidenceReference(
            artifact_id=artifact.artifact_id,
            evidence_type=artifact.evidence_type,
            path=artifact.path,
            summary=artifact.summary,
        )
        for artifact in selected
    ]
    data_facts = [f"{artifact.evidence_type}: {artifact.summary}" for artifact in selected]
    return AgentObservation(
        agent_role=agent_role,
        subject=subject,
        decision_label=decision_label,
        data_facts=data_facts or ["no local artifact summary available"],
        factor_results=[],
        backtest_findings=[],
        agent_reasoning=["offline review artifact summarizes cited local evidence only"],
        unverified_hypotheses=[] if selected else ["no matching local artifacts found"],
        evidence=evidence,
    )


def _infer_evidence_type(path: Path) -> str:
    lowered = str(path).lower()
    if "risk" in lowered:
        return "risk_alert_report"
    if "market" in lowered:
        return "market_state_report"
    if "position" in lowered:
        return "position_review_report"
    if "topn" in lowered:
        return "daily_topn_report"
    if "run_card" in lowered:
        return "run_card"
    return "generic_report"


def _summarize_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " ".join(lines[:2])[:240] or "empty artifact"


def _render_markdown(
    report: AgentReport,
    review_result: dict[str, Any],
    warnings: list[str],
) -> str:
    lines = [
        "# Internal Skill Review",
        "",
        f"- Trade date: {report.trade_date}",
        f"- Review status: {review_result['status']}",
        f"- Observations: {len(report.observations)}",
        "",
        "## Observations",
    ]
    for observation in report.observations:
        lines.extend(
            [
                "",
                f"### {observation.subject}",
                "",
                f"- Role: {observation.agent_role}",
                f"- Label: {observation.decision_label}",
                f"- Evidence count: {len(observation.evidence)}",
            ]
        )
        for fact in observation.data_facts:
            lines.append(f"- Fact: {fact}")
    issues = review_result.get("issues", [])
    if issues:
        lines.extend(["", "## Review Issues"])
        for issue in issues:
            lines.append(
                "- "
                f"{issue.get('severity', 'unknown')}: "
                f"{issue.get('code', 'unknown_issue')} "
                f"{issue.get('message', '')}"
            )
    if warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines) + "\n"
