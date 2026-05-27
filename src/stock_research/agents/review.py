from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from stock_research.agents.contracts import AgentReport, ReviewIssue, validate_agent_report


BANNED_TRADING_INSTRUCTIONS = [
    "必须买入",
    "立即买入",
    "直接买入",
    "必须卖出",
    "立即卖出",
    "直接下单",
    "自动下单",
    "all in",
    "buy now",
    "must buy",
    "sell now",
]


@dataclass(frozen=True)
class ReviewResult:
    status: str
    issues: list[ReviewIssue]

    @property
    def blocker_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "blocker")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "blocker_count": self.blocker_count,
            "warning_count": self.warning_count,
            "issues": [issue.to_dict() for issue in self.issues],
        }


class ReviewAgent:
    def review(self, report: AgentReport) -> ReviewResult:
        issues = validate_agent_report(report)
        issues.extend(self._find_banned_trading_instructions(report))
        status = "rejected" if any(issue.severity == "blocker" for issue in issues) else "passed"
        return ReviewResult(status=status, issues=issues)

    def _find_banned_trading_instructions(self, report: AgentReport) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []
        for index, observation in enumerate(report.observations):
            text = "\n".join(
                [
                    observation.subject,
                    observation.decision_label,
                    *observation.data_facts,
                    *observation.factor_results,
                    *observation.backtest_findings,
                    *observation.agent_reasoning,
                    *observation.unverified_hypotheses,
                ]
            ).lower()
            matched = [phrase for phrase in BANNED_TRADING_INSTRUCTIONS if phrase.lower() in text]
            if matched:
                issues.append(
                    ReviewIssue(
                        code="banned_trading_instruction",
                        severity="blocker",
                        message=f"Agent output contains banned trading instruction: {matched[0]}",
                        observation_index=index,
                    )
                )
        return issues
