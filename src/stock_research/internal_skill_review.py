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
    debate_review_json_path: str
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


@dataclass(frozen=True)
class DebateCase:
    role: str
    conclusion: str
    cited_evidence_ids: list[str]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InternalDebateReview:
    trade_date: str
    source: str
    review_only: bool
    review_agent_status: str
    bull_case: DebateCase
    bear_case: DebateCase
    risk_manager_review: DebateCase
    portfolio_review_summary: DebateCase
    evidence_conflicts: list[str]
    missing_evidence: list[str]
    operator_questions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "source": self.source,
            "review_only": self.review_only,
            "review_agent_status": self.review_agent_status,
            "bull_case": self.bull_case.to_dict(),
            "bear_case": self.bear_case.to_dict(),
            "risk_manager_review": self.risk_manager_review.to_dict(),
            "portfolio_review_summary": self.portfolio_review_summary.to_dict(),
            "evidence_conflicts": self.evidence_conflicts,
            "missing_evidence": self.missing_evidence,
            "operator_questions": self.operator_questions,
        }


def run_internal_skill_review(
    *,
    trade_date: str,
    artifact_paths: list[str | Path],
    output_dir: str | Path,
) -> InternalSkillReviewResult:
    artifacts, warnings = _load_artifacts(artifact_paths)
    report = _build_agent_report(trade_date=trade_date, artifacts=artifacts)
    review_result = ReviewAgent().review(report)
    debate_review = _build_internal_debate_review(
        trade_date=trade_date,
        artifacts=artifacts,
        warnings=warnings,
        review_result=review_result.to_dict(),
    )

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    agent_report_json_path = output_path / "agent_report.json"
    markdown_path = output_path / "internal_skill_review.md"
    review_agent_result_path = output_path / "review_agent_result.json"
    debate_review_json_path = output_path / "internal_debate_review.json"

    agent_report_json_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    review_agent_result_path.write_text(
        json.dumps(review_result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    debate_review_json_path.write_text(
        json.dumps(debate_review.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        _render_markdown(report, review_result.to_dict(), warnings, debate_review),
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
        debate_review_json_path=str(debate_review_json_path),
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


def _build_internal_debate_review(
    *,
    trade_date: str,
    artifacts: list[LocalReviewArtifact],
    warnings: list[str],
    review_result: dict[str, Any],
) -> InternalDebateReview:
    by_type = _artifacts_by_type(artifacts)
    missing_evidence = _derive_missing_evidence(artifacts, warnings)
    review_issues = [
        f"{issue.get('code', 'unknown_issue')}: {issue.get('message', '')}".strip()
        for issue in review_result.get("issues", [])
    ]
    evidence_conflicts = _derive_evidence_conflicts(by_type, review_issues)
    all_ids = [artifact.artifact_id for artifact in artifacts]

    bull_artifacts = _select_artifacts(
        by_type,
        ["daily_topn_report", "position_review_report", "market_state_report", "run_card"],
    )
    bear_artifacts = _select_artifacts(
        by_type,
        ["risk_alert_report", "market_state_report", "generic_report"],
    )
    risk_artifacts = _select_artifacts(
        by_type,
        ["risk_alert_report", "market_state_report", "run_card"],
    )

    bull_notes = _artifact_notes(bull_artifacts)
    if not bull_notes:
        bull_notes = ["No positive-case local artifact was provided; keep this packet in manual review."]

    bear_notes = _artifact_notes(bear_artifacts) + review_issues + missing_evidence
    if not bear_notes:
        bear_notes = [
            "No explicit opposing artifact was provided; reviewer should check whether the case is one-sided."
        ]

    risk_notes = _artifact_notes(risk_artifacts) + review_issues + missing_evidence
    if not risk_notes:
        risk_notes = ["No standalone risk artifact was provided; do not treat this as risk clearance."]

    portfolio_notes = [
        "Review-only synthesis for human operator; no score, watchlist, dashboard, or trading state is mutated.",
        f"ReviewAgent status: {review_result.get('status', 'unknown')}.",
    ]
    if evidence_conflicts:
        portfolio_notes.extend(evidence_conflicts)
    if missing_evidence:
        portfolio_notes.extend(missing_evidence)

    operator_questions = _derive_operator_questions(missing_evidence, evidence_conflicts, review_result)

    return InternalDebateReview(
        trade_date=trade_date,
        source="internal_debate_review_v1",
        review_only=True,
        review_agent_status=str(review_result.get("status", "unknown")),
        bull_case=DebateCase(
            role="bull_researcher",
            conclusion="Support case is limited to cited local artifacts and requires human review.",
            cited_evidence_ids=[artifact.artifact_id for artifact in bull_artifacts] or all_ids,
            notes=bull_notes,
        ),
        bear_case=DebateCase(
            role="bear_researcher",
            conclusion="Opposing case highlights risk, missing evidence, and review issues before delivery.",
            cited_evidence_ids=[artifact.artifact_id for artifact in bear_artifacts] or all_ids,
            notes=bear_notes,
        ),
        risk_manager_review=DebateCase(
            role="risk_manager",
            conclusion="Risk review is not a clearance; it records constraints for operator inspection.",
            cited_evidence_ids=[artifact.artifact_id for artifact in risk_artifacts] or all_ids,
            notes=risk_notes,
        ),
        portfolio_review_summary=DebateCase(
            role="portfolio_reviewer",
            conclusion="Final packet remains review-only and should be compared with existing platform outputs.",
            cited_evidence_ids=all_ids,
            notes=portfolio_notes,
        ),
        evidence_conflicts=evidence_conflicts,
        missing_evidence=missing_evidence,
        operator_questions=operator_questions,
    )


def _artifacts_by_type(artifacts: list[LocalReviewArtifact]) -> dict[str, list[LocalReviewArtifact]]:
    by_type: dict[str, list[LocalReviewArtifact]] = {}
    for artifact in artifacts:
        by_type.setdefault(artifact.evidence_type, []).append(artifact)
    return by_type


def _select_artifacts(
    by_type: dict[str, list[LocalReviewArtifact]],
    evidence_types: list[str],
) -> list[LocalReviewArtifact]:
    selected: list[LocalReviewArtifact] = []
    for evidence_type in evidence_types:
        selected.extend(by_type.get(evidence_type, []))
    return selected


def _artifact_notes(artifacts: list[LocalReviewArtifact]) -> list[str]:
    return [f"{artifact.evidence_type}: {artifact.summary}" for artifact in artifacts]


def _derive_missing_evidence(artifacts: list[LocalReviewArtifact], warnings: list[str]) -> list[str]:
    missing = list(warnings)
    if not artifacts:
        missing.append("no_artifacts_provided")
    available_types = {artifact.evidence_type for artifact in artifacts}
    expected_types = {
        "daily_topn_report",
        "risk_alert_report",
        "market_state_report",
        "position_review_report",
        "run_card",
    }
    for evidence_type in sorted(expected_types - available_types):
        missing.append(f"missing_expected_artifact:{evidence_type}")
    return missing


def _derive_evidence_conflicts(
    by_type: dict[str, list[LocalReviewArtifact]],
    review_issues: list[str],
) -> list[str]:
    conflicts: list[str] = []
    if by_type.get("daily_topn_report") and by_type.get("risk_alert_report"):
        conflicts.append(
            "candidate support and risk alert artifacts are both present; operator should compare strength and risk."
        )
    conflicts.extend(review_issues)
    return conflicts


def _derive_operator_questions(
    missing_evidence: list[str],
    evidence_conflicts: list[str],
    review_result: dict[str, Any],
) -> list[str]:
    questions: list[str] = []
    if missing_evidence:
        questions.append("Which missing evidence must be restored before this packet is useful?")
    if evidence_conflicts:
        questions.append("Do risk alerts weaken the support case enough to keep the item in observation only?")
    if review_result.get("status") != "passed":
        questions.append("What blocker must be resolved before delivery or downstream review?")
    if not questions:
        questions.append("Is the bear case strong enough to change the human review label?")
    return questions


def _render_markdown(
    report: AgentReport,
    review_result: dict[str, Any],
    warnings: list[str],
    debate_review: InternalDebateReview,
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
    lines.extend(["", "## Internal Debate Review"])
    _append_debate_case(lines, "Bull Case", debate_review.bull_case)
    _append_debate_case(lines, "Bear Case", debate_review.bear_case)
    _append_debate_case(lines, "Risk Manager Review", debate_review.risk_manager_review)
    _append_debate_case(lines, "Portfolio Review Summary", debate_review.portfolio_review_summary)
    if debate_review.evidence_conflicts:
        lines.extend(["", "### Evidence Conflicts"])
        lines.extend(f"- {item}" for item in debate_review.evidence_conflicts)
    if debate_review.missing_evidence:
        lines.extend(["", "### Missing Evidence"])
        lines.extend(f"- {item}" for item in debate_review.missing_evidence)
    if debate_review.operator_questions:
        lines.extend(["", "### Operator Questions"])
        lines.extend(f"- {item}" for item in debate_review.operator_questions)
    if warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines) + "\n"


def _append_debate_case(lines: list[str], title: str, debate_case: DebateCase) -> None:
    lines.extend(
        [
            "",
            f"### {title}",
            "",
            f"- Role: {debate_case.role}",
            f"- Conclusion: {debate_case.conclusion}",
            f"- Evidence ids: {', '.join(debate_case.cited_evidence_ids) if debate_case.cited_evidence_ids else 'none'}",
        ]
    )
    for note in debate_case.notes:
        lines.append(f"- Note: {note}")
