# Internal Debate Review v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic TradingAgents-inspired debate layer to the existing offline `run-internal-skill-review` workflow.

**Architecture:** Keep the current CLI and artifact-first workflow. Extend `src/stock_research/internal_skill_review.py` with small dataclasses and a deterministic builder that writes `internal_debate_review.json` and renders debate sections in Markdown, while `ReviewAgent` remains the safety gate.

**Tech Stack:** Python dataclasses, pathlib/json, existing `ReviewAgent`, pytest, existing argparse CLI.

---

## File Structure

- Modify `src/stock_research/internal_skill_review.py`
  - Add `DebateCase` and `InternalDebateReview` dataclasses.
  - Add `debate_review_json_path` to `InternalSkillReviewResult`.
  - Build and write `internal_debate_review.json`.
  - Render debate sections in `internal_skill_review.md`.
- Modify `src/stock_research/cli.py`
  - Print `internal_skill_review|debate_review|...` after `review_agent_result`.
- Modify `tests/test_internal_skill_review.py`
  - Assert normal packets write structured debate output.
  - Assert missing evidence is reflected in debate JSON and Markdown.
  - Assert debate text avoids banned trading phrases.
- Modify `tests/test_factor_cli.py`
  - Add a dispatch test that monkeypatches `run_internal_skill_review` and verifies the new output line.
- Modify `docs/internal-skill-review-offline-evaluation-runbook.md`
  - Document `internal_debate_review.json` and the new review criteria.

---

### Task 1: Add Debate Output Contract Tests

**Files:**
- Modify: `tests/test_internal_skill_review.py`
- Test: `tests/test_internal_skill_review.py`

- [ ] **Step 1: Write the failing normal-packet debate test**

Add these imports near the top:

```python
from stock_research.agents.review import BANNED_TRADING_INSTRUCTIONS
```

Append this test:

```python
def test_run_internal_skill_review_writes_internal_debate_review(tmp_path):
    topn = _write_artifact(
        tmp_path / "reports" / "topn" / "daily_topn_2026-06-08.md",
        "# Daily TopN\n000001.SZ rank 1 with strong factor evidence\n",
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

    assert Path(result.debate_review_json_path).exists()
    debate = json.loads(Path(result.debate_review_json_path).read_text(encoding="utf-8"))
    assert debate["trade_date"] == "2026-06-08"
    assert debate["review_only"] is True
    assert debate["source"] == "internal_debate_review_v1"
    assert debate["bull_case"]["role"] == "bull_researcher"
    assert debate["bear_case"]["role"] == "bear_researcher"
    assert debate["risk_manager_review"]["role"] == "risk_manager"
    assert debate["portfolio_review_summary"]["role"] == "portfolio_reviewer"
    assert debate["bull_case"]["cited_evidence_ids"]
    assert debate["bear_case"]["cited_evidence_ids"]
    assert debate["risk_manager_review"]["cited_evidence_ids"]
    assert debate["portfolio_review_summary"]["cited_evidence_ids"]
    assert debate["missing_evidence"] == []
    assert isinstance(debate["operator_questions"], list)

    markdown = Path(result.markdown_path).read_text(encoding="utf-8")
    assert "## Internal Debate Review" in markdown
    assert "### Bull Case" in markdown
    assert "### Bear Case" in markdown
    assert "### Risk Manager Review" in markdown
    assert "### Portfolio Review Summary" in markdown

    debate_text = json.dumps(debate, ensure_ascii=False).lower()
    for phrase in BANNED_TRADING_INSTRUCTIONS:
        assert phrase.lower() not in debate_text
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_internal_skill_review.py::test_run_internal_skill_review_writes_internal_debate_review -q
```

Expected: FAIL because `InternalSkillReviewResult` has no `debate_review_json_path`.

- [ ] **Step 3: Write the failing missing-evidence debate test**

Append this test:

```python
def test_run_internal_skill_review_debate_records_missing_evidence(tmp_path):
    result = run_internal_skill_review(
        trade_date="2026-06-08",
        artifact_paths=[],
        output_dir=tmp_path / "outputs",
    )

    debate = json.loads(Path(result.debate_review_json_path).read_text(encoding="utf-8"))
    assert result.status == "rejected"
    assert debate["review_agent_status"] == "rejected"
    assert "no_artifacts_provided" in debate["missing_evidence"]
    assert debate["bear_case"]["notes"]
    assert debate["risk_manager_review"]["notes"]

    markdown = Path(result.markdown_path).read_text(encoding="utf-8")
    assert "## Internal Debate Review" in markdown
    assert "no_artifacts_provided" in markdown
```

- [ ] **Step 4: Run missing-evidence test to verify it fails**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_internal_skill_review.py::test_run_internal_skill_review_debate_records_missing_evidence -q
```

Expected: FAIL because `InternalSkillReviewResult` has no `debate_review_json_path`.

- [ ] **Step 5: Commit failing tests**

Do not commit failing tests alone. Keep these changes unstaged until Task 2 implementation passes.

---

### Task 2: Implement Debate Builder and Artifacts

**Files:**
- Modify: `src/stock_research/internal_skill_review.py`
- Test: `tests/test_internal_skill_review.py`

- [ ] **Step 1: Add debate dataclasses**

In `src/stock_research/internal_skill_review.py`, add these dataclasses after `LocalReviewArtifact`:

```python
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
```

- [ ] **Step 2: Extend result dataclass**

Add this field to `InternalSkillReviewResult` after `review_agent_result_path`:

```python
    debate_review_json_path: str
```

- [ ] **Step 3: Build and write debate output**

In `run_internal_skill_review()`, after `review_result = ReviewAgent().review(report)`, add:

```python
    debate_review = _build_internal_debate_review(
        trade_date=trade_date,
        artifacts=artifacts,
        warnings=warnings,
        review_result=review_result.to_dict(),
    )
```

After `review_agent_result_path = output_path / "review_agent_result.json"`, add:

```python
    debate_review_json_path = output_path / "internal_debate_review.json"
```

After writing `review_agent_result_path`, add:

```python
    debate_review_json_path.write_text(
        json.dumps(debate_review.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
```

Change the Markdown call to:

```python
        _render_markdown(report, review_result.to_dict(), warnings, debate_review),
```

Add `debate_review_json_path=str(debate_review_json_path),` to the returned `InternalSkillReviewResult`.

- [ ] **Step 4: Add deterministic builder helpers**

Add these functions before `_render_markdown()`:

```python
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
        bear_notes = ["No explicit opposing artifact was provided; reviewer should check whether the case is one-sided."]

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
        conflicts.append("candidate support and risk alert artifacts are both present; operator should compare strength and risk.")
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
```

- [ ] **Step 5: Render debate sections in Markdown**

Change `_render_markdown()` signature to:

```python
def _render_markdown(
    report: AgentReport,
    review_result: dict[str, Any],
    warnings: list[str],
    debate_review: InternalDebateReview,
) -> str:
```

Before the existing `if warnings:` block, add:

```python
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
```

Add this helper after `_render_markdown()`:

```python
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
```

- [ ] **Step 6: Run tests to verify green**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_internal_skill_review.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit implementation**

Run:

```bash
git add src/stock_research/internal_skill_review.py tests/test_internal_skill_review.py
git commit -m "feat: add internal debate review artifacts"
```

---

### Task 3: Expose Debate Artifact in CLI Output

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`
- Test: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing CLI dispatch test**

Append this test near `test_cli_accepts_run_internal_skill_review_command()`:

```python
def test_cli_run_internal_skill_review_prints_debate_artifact(monkeypatch, capsys):
    def fake_run_internal_skill_review(*, trade_date, artifact_paths, output_dir):
        assert trade_date == "2026-06-08"
        assert artifact_paths == ["reports/topn.md"]
        assert output_dir == "outputs/internal_skill_review/2026-06-08"
        return SimpleNamespace(
            status="passed",
            review_agent_status="passed",
            observation_count=3,
            agent_report_json_path="outputs/internal_skill_review/2026-06-08/agent_report.json",
            markdown_path="outputs/internal_skill_review/2026-06-08/internal_skill_review.md",
            review_agent_result_path="outputs/internal_skill_review/2026-06-08/review_agent_result.json",
            debate_review_json_path="outputs/internal_skill_review/2026-06-08/internal_debate_review.json",
        )

    monkeypatch.setattr(cli, "run_internal_skill_review", fake_run_internal_skill_review)
    args = build_parser().parse_args(
        [
            "run-internal-skill-review",
            "--trade-date",
            "2026-06-08",
            "--artifact-path",
            "reports/topn.md",
            "--output-dir",
            "outputs/internal_skill_review/2026-06-08",
        ]
    )

    exit_code = cli.main(args)

    assert exit_code == 0
    output = capsys.readouterr().out
    assert (
        "internal_skill_review|debate_review|"
        "outputs/internal_skill_review/2026-06-08/internal_debate_review.json"
    ) in output
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_factor_cli.py::test_cli_run_internal_skill_review_prints_debate_artifact -q
```

Expected: FAIL because CLI does not print `internal_skill_review|debate_review|...`.

- [ ] **Step 3: Add CLI print line**

In `src/stock_research/cli.py`, inside the `run-internal-skill-review` branch, add after the `review_agent_result` print:

```python
        print(f"internal_skill_review|debate_review|{result.debate_review_json_path}")
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_factor_cli.py::test_cli_accepts_run_internal_skill_review_command tests/test_factor_cli.py::test_cli_run_internal_skill_review_prints_debate_artifact -q
```

Expected: PASS.

- [ ] **Step 5: Commit CLI output**

Run:

```bash
git add src/stock_research/cli.py tests/test_factor_cli.py
git commit -m "feat: expose internal debate review cli artifact"
```

---

### Task 4: Update Runbook and Run Full Verification

**Files:**
- Modify: `docs/internal-skill-review-offline-evaluation-runbook.md`
- Test: targeted pytest suite

- [ ] **Step 1: Update runbook output section**

In `docs/internal-skill-review-offline-evaluation-runbook.md`, add after the command block:

```markdown
## Outputs

- `agent_report.json`: existing agent contract payload passed to `ReviewAgent`.
- `review_agent_result.json`: safety and evidence validation result.
- `internal_debate_review.json`: deterministic bull, bear, risk-manager, and portfolio-review synthesis.
- `internal_skill_review.md`: human-readable review packet with observations, review issues, debate sections, missing evidence, and operator questions.
```

Add to “Five-Day Evaluation”:

```markdown
- bull case evidence count
- bear case evidence count
- risk-manager notes count
- portfolio-review summary usefulness: `useful`, `mixed`, `not_useful`
```

- [ ] **Step 2: Run targeted verification**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_internal_skill_review.py tests/test_llmquant_fusion_agent_contracts.py tests/test_research_infra_evidence_units.py tests/test_agent_contracts.py tests/test_factor_cli.py::test_cli_accepts_run_internal_skill_review_command tests/test_factor_cli.py::test_cli_run_internal_skill_review_prints_debate_artifact -q
```

Expected: PASS.

- [ ] **Step 3: Check worktree status**

Run:

```bash
git status --short
```

Expected: only the runbook is modified.

- [ ] **Step 4: Commit docs**

Run:

```bash
git add docs/internal-skill-review-offline-evaluation-runbook.md
git commit -m "docs: document internal debate review output"
```

- [ ] **Step 5: Final branch status**

Run:

```bash
git status --short --branch
```

Expected: clean worktree on `llmquant-method-fusion`, ahead of `origin/llmquant-method-fusion`.

---

## Self-Review

- Spec coverage: The plan implements the confirmed v1 fields, JSON artifact, Markdown rendering, CLI visibility, missing evidence handling, and review-only documentation.
- Placeholder scan: The plan contains no `TBD`, `TODO`, `implement later`, or vague “add tests” steps.
- Type consistency: The plan uses `InternalDebateReview`, `DebateCase`, and `debate_review_json_path` consistently across implementation, tests, and CLI output.
