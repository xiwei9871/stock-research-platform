from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from stock_research.agents.contracts import AgentObservation, AgentReport, EvidenceReference
from stock_research.agents.review import ReviewAgent


@dataclass(frozen=True)
class AgentResearchReportResult:
    status: str
    review_status: str
    observation_count: int
    blocker_count: int
    markdown_path: str
    json_path: str
    review_path: str


def build_agent_research_report(
    *,
    trade_date: str,
    mode: str,
    manifest_path: str | Path,
    output_dir: str | Path,
) -> AgentResearchReportResult:
    manifest = _load_manifest(manifest_path)
    source_trade_date = str(manifest.get("trade_date", ""))
    if source_trade_date != trade_date:
        raise ValueError(
            "agent-report: "
            f"trade-date {trade_date} does not match manifest trade_date {source_trade_date}"
        )

    generated_at = _utc_now_iso()
    report = AgentReport(
        trade_date=trade_date,
        mode=mode,
        generated_at=generated_at,
        metadata={
            "source_manifest_path": str(manifest_path),
            "source_channel": manifest.get("channel", ""),
        },
        observations=_observations_from_manifest(manifest, mode=mode),
    )
    review = ReviewAgent().review(report)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    stem = f"agent_research_report_{trade_date}_{mode}"
    json_path = output_path / f"{stem}.json"
    markdown_path = output_path / f"{stem}.md"
    review_path = output_path / f"agent_research_review_{trade_date}_{mode}.json"

    payload = report.to_dict()
    payload["review"] = review.to_dict()
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    review_path.write_text(json.dumps(review.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_render_markdown(report, review.to_dict()), encoding="utf-8")

    return AgentResearchReportResult(
        status="written",
        review_status=review.status,
        observation_count=len(report.observations),
        blocker_count=review.blocker_count,
        markdown_path=str(markdown_path),
        json_path=str(json_path),
        review_path=str(review_path),
    )


def _load_manifest(manifest_path: str | Path) -> dict[str, Any]:
    path = Path(manifest_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"agent-report: manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"agent-report: manifest is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("agent-report: manifest must be a JSON object")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("agent-report: manifest artifacts must be a list")
    return payload


def _observations_from_manifest(manifest: dict[str, Any], *, mode: str) -> list[AgentObservation]:
    observations: list[AgentObservation] = []
    for artifact in manifest.get("artifacts", []):
        if not isinstance(artifact, dict):
            continue
        observation = _observation_from_artifact(artifact, mode=mode)
        if observation is not None:
            observations.append(observation)
    return observations


def _observation_from_artifact(artifact: dict[str, Any], *, mode: str) -> AgentObservation | None:
    report_type = str(artifact.get("report_type", "unknown"))
    if mode == "topn" and "watchlist" in report_type and "topn" not in report_type:
        return None
    if mode == "watchlist" and "topn" in report_type and "watchlist" not in report_type:
        return None

    severity = str(artifact.get("severity", "info"))
    title = str(artifact.get("title") or report_type)
    summary = str(artifact.get("summary") or title)
    evidence = _evidence_from_artifact(artifact)
    return AgentObservation(
        agent_role=_agent_role_for_report_type(report_type),
        subject=title,
        decision_label=_decision_label_for(report_type=report_type, severity=severity),
        data_facts=[
            f"report_type={report_type}",
            f"severity={severity}",
            f"summary={summary}",
        ],
        factor_results=_factor_results_for(report_type, summary),
        backtest_findings=_backtest_findings_for(artifact),
        agent_reasoning=[
            "This is a research-assistant observation derived from cited artifacts; final action remains human-controlled."
        ],
        unverified_hypotheses=[
            "Intraday liquidity, latest disclosures, and execution constraints require separate confirmation."
        ],
        evidence=evidence,
    )


def _evidence_from_artifact(artifact: dict[str, Any]) -> list[EvidenceReference]:
    artifact_id = str(artifact.get("artifact_id", ""))
    summary = str(artifact.get("summary") or artifact.get("title") or artifact_id)
    references: list[EvidenceReference] = []
    for key in ["run_card_path", "json_path", "markdown_path", "evidence_dir"]:
        value = artifact.get(key)
        if isinstance(value, str) and value:
            references.append(
                EvidenceReference(
                    artifact_id=artifact_id,
                    evidence_type=_evidence_type_for_key(key),
                    path=value,
                    summary=summary,
                )
            )
    csv_paths = artifact.get("csv_paths")
    if isinstance(csv_paths, list):
        for value in csv_paths:
            if isinstance(value, str) and value:
                references.append(
                    EvidenceReference(
                        artifact_id=artifact_id,
                        evidence_type="csv_artifact",
                        path=value,
                        summary=summary,
                    )
                )
    path_value = artifact.get("metadata", {}).get("path") if isinstance(artifact.get("metadata"), dict) else None
    if not references and isinstance(path_value, str) and path_value:
        references.append(
            EvidenceReference(
                artifact_id=artifact_id,
                evidence_type="report_artifact",
                path=path_value,
                summary=summary,
            )
        )
    return references


def _evidence_type_for_key(key: str) -> str:
    return {
        "run_card_path": "run_card",
        "json_path": "json_artifact",
        "markdown_path": "markdown_artifact",
        "evidence_dir": "evidence_bundle",
    }[key]


def _agent_role_for_report_type(report_type: str) -> str:
    normalized = report_type.lower()
    if "risk" in normalized:
        return "risk"
    if "watchlist" in normalized or "must_watch" in normalized:
        return "watchlist"
    if "backtest" in normalized or "run_card" in normalized or "retention" in normalized:
        return "backtest"
    if "topn" in normalized or "factor" in normalized:
        return "factor_research"
    return "data_quality"


def _decision_label_for(*, report_type: str, severity: str) -> str:
    normalized_type = report_type.lower()
    normalized_severity = severity.lower()
    if "risk" in normalized_type and normalized_severity in {"high", "critical"}:
        return "剔除"
    if normalized_severity in {"high", "critical"}:
        return "谨慎"
    if "topn" in normalized_type or "must_watch" in normalized_type:
        return "候选"
    if normalized_severity == "medium":
        return "谨慎"
    return "观察"


def _factor_results_for(report_type: str, summary: str) -> list[str]:
    normalized = report_type.lower()
    if "topn" in normalized or "factor" in normalized or "watchlist" in normalized:
        return [summary]
    return []


def _backtest_findings_for(artifact: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    if artifact.get("run_card_path"):
        findings.append("run_card_path is available")
    if artifact.get("evidence_dir"):
        findings.append("evidence bundle is available")
    if "backtest" in str(artifact.get("report_type", "")).lower():
        findings.append(str(artifact.get("summary") or "backtest artifact included"))
    return findings


def _render_markdown(report: AgentReport, review_payload: dict[str, Any]) -> str:
    lines = [
        f"# Agent Research Report {report.trade_date}",
        "",
        f"- mode: {report.mode}",
        f"- review_status: {review_payload['status']}",
        f"- blocker_count: {review_payload['blocker_count']}",
        "",
    ]
    for index, observation in enumerate(report.observations, start=1):
        lines.extend(
            [
                f"## Observation {index}: {observation.subject}",
                "",
                f"- agent_role: {observation.agent_role}",
                f"- decision_label: {observation.decision_label}",
                "",
                "## 数据事实",
                *_bullet_lines(observation.data_facts),
                "",
                "## 因子结果",
                *_bullet_lines(observation.factor_results),
                "",
                "## 回测结论",
                *_bullet_lines(observation.backtest_findings),
                "",
                "## AI 推理",
                *_bullet_lines(observation.agent_reasoning),
                "",
                "## 未验证假设",
                *_bullet_lines(observation.unverified_hypotheses),
                "",
                "## 证据引用",
                *_bullet_lines(
                    [
                        f"{item.artifact_id} | {item.evidence_type} | {item.path} | {item.summary}"
                        for item in observation.evidence
                    ]
                ),
                "",
            ]
        )
    if review_payload["issues"]:
        lines.extend(["## Review Issues", ""])
        lines.extend(_bullet_lines([f"{item['severity']}:{item['code']}:{item['message']}" for item in review_payload["issues"]]))
    return "\n".join(lines).rstrip() + "\n"


def _bullet_lines(values: list[str]) -> list[str]:
    if not values:
        return ["- none"]
    return [f"- {value}" for value in values]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
