from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


ALLOWED_AGENT_ROLES = {
    "data_quality",
    "factor_research",
    "backtest",
    "watchlist",
    "risk",
    "review",
}
ALLOWED_DECISION_LABELS = {"观察", "候选", "谨慎", "剔除"}
ALLOWED_MODES = {"topn", "watchlist"}


@dataclass(frozen=True)
class AgentRoleSpec:
    role: str
    display_name: str
    responsibilities: list[str]
    requires_evidence: bool = True
    allows_auto_trade: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceReference:
    artifact_id: str
    evidence_type: str
    path: str
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentObservation:
    agent_role: str
    subject: str
    decision_label: str
    data_facts: list[str] = field(default_factory=list)
    factor_results: list[str] = field(default_factory=list)
    backtest_findings: list[str] = field(default_factory=list)
    agent_reasoning: list[str] = field(default_factory=list)
    unverified_hypotheses: list[str] = field(default_factory=list)
    evidence: list[EvidenceReference] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence"] = [item.to_dict() for item in self.evidence]
        return payload


@dataclass(frozen=True)
class ReviewIssue:
    code: str
    severity: str
    message: str
    observation_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentReport:
    trade_date: str
    mode: str
    observations: list[AgentObservation]
    generated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "mode": self.mode,
            "generated_at": self.generated_at,
            "metadata": dict(self.metadata),
            "observations": [item.to_dict() for item in self.observations],
        }


def validate_agent_report(report: AgentReport) -> list[ReviewIssue]:
    issues: list[ReviewIssue] = []
    if report.mode not in ALLOWED_MODES:
        issues.append(
            ReviewIssue(
                code="invalid_mode",
                severity="blocker",
                message=f"Agent report mode must be one of {sorted(ALLOWED_MODES)}",
            )
        )
    if not report.observations:
        issues.append(
            ReviewIssue(
                code="empty_report",
                severity="blocker",
                message="Agent report must contain at least one observation",
            )
        )

    for index, observation in enumerate(report.observations):
        if observation.agent_role not in ALLOWED_AGENT_ROLES:
            issues.append(
                ReviewIssue(
                    code="invalid_agent_role",
                    severity="blocker",
                    message=f"Agent role {observation.agent_role!r} is not allowed",
                    observation_index=index,
                )
            )
        if observation.decision_label not in ALLOWED_DECISION_LABELS:
            issues.append(
                ReviewIssue(
                    code="invalid_decision_label",
                    severity="blocker",
                    message=f"Decision label {observation.decision_label!r} is not allowed",
                    observation_index=index,
                )
            )
        if not observation.evidence:
            issues.append(
                ReviewIssue(
                    code="missing_evidence",
                    severity="blocker",
                    message="Every agent observation must cite at least one evidence reference",
                    observation_index=index,
                )
            )
        if not observation.data_facts:
            issues.append(
                ReviewIssue(
                    code="missing_data_facts",
                    severity="blocker",
                    message="Every agent observation must include data facts separately from reasoning",
                    observation_index=index,
                )
            )
        if not observation.agent_reasoning:
            issues.append(
                ReviewIssue(
                    code="missing_agent_reasoning",
                    severity="warning",
                    message="Agent reasoning is empty",
                    observation_index=index,
                )
            )
    return issues


def list_agent_role_specs() -> dict[str, AgentRoleSpec]:
    return {
        "data_quality": AgentRoleSpec(
            role="data_quality",
            display_name="Data Quality Agent",
            responsibilities=[
                "check data completeness",
                "separate data gaps from investment views",
                "flag point-in-time risks",
            ],
        ),
        "factor_research": AgentRoleSpec(
            role="factor_research",
            display_name="Factor Research Agent",
            responsibilities=[
                "summarize factor signals",
                "cite factor artifacts",
                "avoid replacing validated alpha with unsupported claims",
            ],
        ),
        "backtest": AgentRoleSpec(
            role="backtest",
            display_name="Backtest Agent",
            responsibilities=[
                "summarize backtest artifacts",
                "flag missing sample-out validation",
                "cite run cards and evidence bundles",
            ],
        ),
        "watchlist": AgentRoleSpec(
            role="watchlist",
            display_name="Watchlist Agent",
            responsibilities=[
                "summarize watchlist observations",
                "separate candidates from trade instructions",
                "cite watchlist report artifacts",
            ],
        ),
        "risk": AgentRoleSpec(
            role="risk",
            display_name="Risk Agent",
            responsibilities=[
                "surface risk alerts",
                "label caution or exclusion candidates",
                "avoid bypassing human risk review",
            ],
        ),
        "review": AgentRoleSpec(
            role="review",
            display_name="Review Agent",
            responsibilities=[
                "block reports without evidence",
                "block automatic trading instructions",
                "check facts, reasoning, and unverified hypotheses are separated",
            ],
        ),
    }
