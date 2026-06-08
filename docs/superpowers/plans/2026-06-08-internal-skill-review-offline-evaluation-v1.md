# Internal Skill Review Offline Evaluation v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an offline-only internal skill review pipeline that turns existing daily report artifacts into review-only Agent reports and local artifacts so we can evaluate whether LLMQuant-inspired workflows improve human review.

**Architecture:** Keep this as a post-report, pre-delivery shadow layer. The pipeline reads local Markdown/JSON/CSV artifacts, builds deterministic `AgentReport` objects for risk review, watchlist memo, and position review, gates them through `ReviewAgent`, and writes JSON/Markdown review artifacts under `outputs/internal_skill_review/`. It does not call external LLMs, does not use LLMQuant Data/MCP, does not mutate scores/watchlists/dashboard state, and does not send OpenClaw/Feishu messages.

**Tech Stack:** Python dataclasses, pathlib, json, existing `stock_research.agents` contracts, existing report artifact conventions, pytest, existing `stock-research` argparse CLI.

---

## Scope Boundary

Included:

- Offline deterministic artifact builder for internal skill reviews.
- `ReviewAgent` gate on every generated `AgentReport`.
- Local JSON and Markdown artifacts.
- CLI command for synthetic/local runs.
- Runbook for a 5-day manual evaluation.

Excluded:

- External LLM calls.
- LLMQuant Data / MCP calls.
- Dashboard changes.
- Report delivery changes.
- Score, TopN, watchlist, P17/P18 label, or database mutation.
- Any broker, order, account, cash, position, fill, or execution state.

## File Structure

- Create: `src/stock_research/internal_skill_review.py`
  - Data types, artifact loading, deterministic observation builders, review gate, JSON/Markdown writers.
- Modify: `src/stock_research/cli.py`
  - Add `run-internal-skill-review` command and dispatch.
- Create: `tests/test_internal_skill_review.py`
  - Unit tests for artifact collection, AgentReport output, ReviewAgent rejection capture, and Markdown/JSON writing.
- Modify: `tests/test_factor_cli.py`
  - Parser coverage for the new CLI command.
- Create: `docs/internal-skill-review-offline-evaluation-runbook.md`
  - Manual 5-day evaluation process and metrics.

## Task 1: Build Offline Review Contract

**Files:**

- Create: `src/stock_research/internal_skill_review.py`
- Create: `tests/test_internal_skill_review.py`

- [ ] **Step 1: Write failing test for a valid offline review run**

Add this to `tests/test_internal_skill_review.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from stock_research.internal_skill_review import run_internal_skill_review


def _write_artifact(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_run_internal_skill_review_writes_review_artifacts(tmp_path):
    topn = _write_artifact(
        tmp_path / "reports" / "topn" / "daily_topn_2026-06-08.md",
        "# Daily TopN\n000001.SZ rank 1\n",
    )
    risk = _write_artifact(
        tmp_path / "reports" / "risk" / "risk_alerts_2026-06-08.md",
        "# Risk Alerts\n000001.SZ concentration risk high\n",
    )
    market = _write_artifact(
        tmp_path / "reports" / "market" / "market_state_2026-06-08.md",
        "# Market State\nCSI300 neutral\n",
    )
    position = _write_artifact(
        tmp_path / "reports" / "position" / "position_review_2026-06-08.md",
        "# Position Review\nNo live position mutation\n",
    )
    run_card = _write_artifact(
        tmp_path / "run_card" / "run_card.json",
        json.dumps({"run_id": "daily-2026-06-08", "status": "ok"}) + "\n",
    )

    result = run_internal_skill_review(
        trade_date="2026-06-08",
        artifact_paths=[topn, risk, market, position, run_card],
        output_dir=tmp_path / "outputs",
    )

    assert result.status == "passed"
    assert result.review_agent_status == "passed"
    assert result.observation_count == 3
    assert Path(result.agent_report_json_path).exists()
    assert Path(result.markdown_path).exists()
    assert Path(result.review_agent_result_path).exists()

    payload = json.loads(Path(result.agent_report_json_path).read_text(encoding="utf-8"))
    assert payload["trade_date"] == "2026-06-08"
    assert {item["agent_role"] for item in payload["observations"]} == {"risk", "watchlist", "review"}
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_internal_skill_review.py::test_run_internal_skill_review_writes_review_artifacts -q
```

Expected:

- FAIL with `ModuleNotFoundError: No module named 'stock_research.internal_skill_review'`.

- [ ] **Step 3: Implement minimal offline review module**

Create `src/stock_research/internal_skill_review.py`:

```python
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
    markdown_path.write_text(_render_markdown(report, review_result.to_dict(), warnings), encoding="utf-8")

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
        _build_observation("risk", "risk-review", "谨慎", artifacts, ["risk_alert_report", "market_state_report", "run_card"]),
        _build_observation("watchlist", "watchlist-memo", "观察", artifacts, ["daily_topn_report", "risk_alert_report", "run_card"]),
        _build_observation("review", "position-review", "观察", artifacts, ["position_review_report", "market_state_report", "risk_alert_report", "run_card"]),
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


def _render_markdown(report: AgentReport, review_result: dict[str, Any], warnings: list[str]) -> str:
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
    if warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run test to verify GREEN**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_internal_skill_review.py::test_run_internal_skill_review_writes_review_artifacts -q
```

Expected:

- PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/internal_skill_review.py tests/test_internal_skill_review.py
git commit -m "feat: add offline internal skill review"
```

## Task 2: Capture Rejected Review Outputs

**Files:**

- Modify: `tests/test_internal_skill_review.py`
- Modify: `src/stock_research/internal_skill_review.py`

- [ ] **Step 1: Write failing test for missing artifacts**

Add this test:

```python
def test_run_internal_skill_review_writes_rejected_artifact_when_evidence_missing(tmp_path):
    result = run_internal_skill_review(
        trade_date="2026-06-08",
        artifact_paths=[],
        output_dir=tmp_path / "outputs",
    )

    assert result.status == "rejected"
    assert result.review_agent_status == "rejected"
    assert result.observation_count == 3

    review_payload = json.loads(Path(result.review_agent_result_path).read_text(encoding="utf-8"))
    issue_codes = {issue["code"] for issue in review_payload["issues"]}
    assert "missing_evidence" in issue_codes
    assert "missing_data_facts" not in issue_codes
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_internal_skill_review.py::test_run_internal_skill_review_writes_rejected_artifact_when_evidence_missing -q
```

Expected:

- FAIL because current fallback evidence prevents missing-evidence rejection.

- [ ] **Step 3: Update missing-artifact behavior**

In `_build_observation`, replace the fallback selection with no evidence when no matching artifacts exist:

```python
selected = [artifact for artifact in artifacts if artifact.evidence_type in evidence_types]
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
    data_facts=data_facts or ["no matching local artifacts found"],
    factor_results=[],
    backtest_findings=[],
    agent_reasoning=["offline review artifact summarizes cited local evidence only"],
    unverified_hypotheses=[] if selected else ["attach local evidence before using this review"],
    evidence=evidence,
)
```

- [ ] **Step 4: Run tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_internal_skill_review.py -q
```

Expected:

- PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/internal_skill_review.py tests/test_internal_skill_review.py
git commit -m "test: capture rejected internal skill reviews"
```

## Task 3: Add CLI Command

**Files:**

- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`
- Test: `tests/test_factor_cli.py`

- [ ] **Step 1: Write parser test**

Add this test to `tests/test_factor_cli.py`:

```python
def test_cli_accepts_run_internal_skill_review_command():
    args = build_parser().parse_args(
        [
            "run-internal-skill-review",
            "--trade-date",
            "2026-06-08",
            "--artifact-path",
            "reports/daily_research/topn/daily_topn_2026-06-08.md",
            "--artifact-path",
            "reports/daily_research/risk_alerts/risk_alerts_2026-06-08.md",
            "--output-dir",
            "outputs/internal_skill_review/2026-06-08",
        ]
    )

    assert args.command == "run-internal-skill-review"
    assert args.trade_date == "2026-06-08"
    assert args.artifact_path == [
        "reports/daily_research/topn/daily_topn_2026-06-08.md",
        "reports/daily_research/risk_alerts/risk_alerts_2026-06-08.md",
    ]
    assert args.output_dir == "outputs/internal_skill_review/2026-06-08"
```

- [ ] **Step 2: Run parser test to verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_factor_cli.py::test_cli_accepts_run_internal_skill_review_command -q
```

Expected:

- FAIL because the parser does not know `run-internal-skill-review`.

- [ ] **Step 3: Add parser and dispatch**

In `src/stock_research/cli.py`, import:

```python
from stock_research.internal_skill_review import run_internal_skill_review
```

In `build_parser()`, add a subparser:

```python
    internal_skill_review_parser = subparsers.add_parser("run-internal-skill-review")
    internal_skill_review_parser.add_argument("--trade-date", required=True)
    internal_skill_review_parser.add_argument(
        "--artifact-path",
        action="append",
        default=[],
        help="Local Markdown/JSON/CSV artifact path to include in the offline review.",
    )
    internal_skill_review_parser.add_argument(
        "--output-dir",
        default="outputs/internal_skill_review",
    )
```

In `main()`, add dispatch:

```python
    if args.command == "run-internal-skill-review":
        result = run_internal_skill_review(
            trade_date=args.trade_date,
            artifact_paths=args.artifact_path,
            output_dir=args.output_dir,
        )
        print(f"internal_skill_review|status|{result.status}")
        print(f"internal_skill_review|review_agent_status|{result.review_agent_status}")
        print(f"internal_skill_review|observations|{result.observation_count}")
        print(f"internal_skill_review|json|{result.agent_report_json_path}")
        print(f"internal_skill_review|markdown|{result.markdown_path}")
        print(f"internal_skill_review|review_agent_result|{result.review_agent_result_path}")
        return 0 if result.status == "passed" else 2
```

- [ ] **Step 4: Run parser test**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_factor_cli.py::test_cli_accepts_run_internal_skill_review_command -q
```

Expected:

- PASS.

- [ ] **Step 5: Run focused tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_internal_skill_review.py tests/test_factor_cli.py::test_cli_accepts_run_internal_skill_review_command -q
```

Expected:

- PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/stock_research/cli.py tests/test_factor_cli.py
git commit -m "feat: add internal skill review cli"
```

## Task 4: Add Offline Evaluation Runbook

**Files:**

- Create: `docs/internal-skill-review-offline-evaluation-runbook.md`
- Modify: `docs/daily-factor-pipeline-runbook.md`

- [ ] **Step 1: Write the runbook**

Create `docs/internal-skill-review-offline-evaluation-runbook.md`:

```markdown
# Internal Skill Review Offline Evaluation Runbook

## Purpose

Evaluate whether internal skill review artifacts improve human review quality after daily report generation and before delivery.

## Boundary

This is offline-only:

- no external LLM calls
- no LLMQuant Data / MCP
- no OpenClaw or Feishu send
- no score, TopN, watchlist, dashboard, P17, P18, database, broker, order, account, cash, position, fill, or execution mutation

## Command

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research run-internal-skill-review \
  --trade-date YYYY-MM-DD \
  --artifact-path reports/daily_research/topn/daily_topn_YYYY-MM-DD.md \
  --artifact-path reports/daily_research/risk_alerts/risk_alerts_YYYY-MM-DD.md \
  --artifact-path reports/daily_research/market_state/market_state_YYYY-MM-DD.md \
  --artifact-path reports/daily_research/position_review/position_review_YYYY-MM-DD.md \
  --artifact-path reports/run_card/YYYY-MM-DD/run_card.json \
  --output-dir outputs/internal_skill_review/YYYY-MM-DD
```

## Five-Day Evaluation

Run the command for five recent report dates with existing artifacts.

Record:

- review status
- ReviewAgent rejection count
- missing evidence count
- artifacts cited per observation
- minutes spent reviewing the original bundle
- minutes spent reviewing the internal skill artifact
- operator usefulness label: `useful`, `mixed`, `not_useful`
- hallucination or uncited-claim notes

## Acceptance for Promotion

The offline review can move to the next design step only if:

- no accepted artifact contains direct trading instructions
- every accepted observation cites evidence
- rejected artifacts clearly explain why they failed
- at least three of five reviewed days are labelled `useful` or `mixed`
- no score, watchlist, dashboard, delivery, or database state is mutated
```

- [ ] **Step 2: Link it from daily pipeline runbook**

Add this sentence under `Internal Skill Review Insertion Point` in `docs/daily-factor-pipeline-runbook.md`:

```markdown
For the offline evaluation procedure and five-day scorecard, see `docs/internal-skill-review-offline-evaluation-runbook.md`.
```

- [ ] **Step 3: Documentation scan**

Run:

```bash
rg -n "run-internal-skill-review|offline-only|Five-Day Evaluation|no external LLM|no LLMQuant Data" docs/internal-skill-review-offline-evaluation-runbook.md docs/daily-factor-pipeline-runbook.md
```

Expected:

- The command, offline boundary, and evaluation criteria are present.

- [ ] **Step 4: Commit**

Run:

```bash
git add docs/internal-skill-review-offline-evaluation-runbook.md docs/daily-factor-pipeline-runbook.md
git commit -m "docs: add internal skill review evaluation runbook"
```

## Final Verification

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_internal_skill_review.py tests/test_llmquant_fusion_agent_contracts.py tests/test_research_infra_evidence_units.py tests/test_agent_contracts.py tests/test_factor_cli.py::test_cli_accepts_run_internal_skill_review_command -q
git diff --check
```

Expected:

- Tests pass.
- `git diff --check` reports no whitespace errors.

## Promotion Decision

After implementation, keep the branch isolated until the five-day offline evaluation produces evidence. Do not merge into the main worktree while unrelated local changes remain dirty unless the operator explicitly asks for a local merge.
