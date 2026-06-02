# Local Report Delivery Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade Local Delivery artifacts from basic file bundles into stable classified report objects with richer `report_type`, `severity`, `summary`, `metadata`, `tags`, channel hints, attention flags, and delivery priority.

**Architecture:** Keep `LocalDeliveryAdapter` collection and delivery flow intact, and add a lightweight rule-based classification stage inside `src/stock_research/report_delivery.py`. Classification remains local-only, JSON-safe, conservative, and backward compatible by preserving existing manifest structure while enriching each artifact entry.

**Tech Stack:** Python 3, dataclasses, pathlib, json, pytest, existing stock_research CLI

---

## File Map

- Modify: `src/stock_research/report_delivery.py`
  - Extend `ReportArtifact`
  - Add lightweight classification helpers
  - Run artifact classification after grouping and before manifest generation
  - Preserve existing adapter interface
- Modify: `tests/test_report_delivery.py`
  - Add classification tests, corrupt JSON tolerance tests, and manifest coverage
- Modify: `tests/test_factor_cli.py`
  - Only if CLI summary lines change
- Modify: `docs/quant_system/12_p1_report_delivery_adapter_plan.md`
  - Append a short `Artifact Classification` section

## Task 1: Lock the Classified Artifact Contract

**Files:**
- Modify: `src/stock_research/report_delivery.py`
- Test: `tests/test_report_delivery.py`

- [ ] **Step 1: Write the failing artifact contract tests**

```python
def test_classified_artifact_exposes_new_top_level_fields(tmp_path):
    source_dir = tmp_path / "reports"
    source_dir.mkdir()
    (source_dir / "daily_topn_2026-05-20_manual_v1.md").write_text(
        "# Daily TopN\n",
        encoding="utf-8",
    )

    adapter = report_delivery.LocalDeliveryAdapter()
    artifacts, warnings = adapter.collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[source_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
    )

    artifact = artifacts[0]
    assert warnings == []
    assert artifact.report_type == "daily_topn_report"
    assert artifact.severity == "info"
    assert artifact.summary == "Daily TopN"
    assert artifact.tags == ["daily", "topn"]
    assert artifact.recommended_channels == ["local", "openclaw"]
    assert artifact.requires_attention is False
    assert artifact.delivery_priority == 10


def test_manifest_retains_old_fields_and_adds_classification_fields(tmp_path):
    source_dir = tmp_path / "reports"
    source_dir.mkdir()
    (source_dir / "daily_topn_2026-05-20_manual_v1.md").write_text(
        "# Daily TopN\n",
        encoding="utf-8",
    )

    result = report_delivery.deliver_local_reports(
        trade_date="2026-05-20",
        input_dirs=[source_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
        output_dir=tmp_path / "delivery",
        dry_run=True,
    )

    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    artifact = manifest["artifacts"][0]
    assert "markdown_path" in artifact
    assert "json_path" in artifact
    assert artifact["report_type"] == "daily_topn_report"
    assert artifact["tags"] == ["daily", "topn"]
    assert artifact["recommended_channels"] == ["local", "openclaw"]
    assert artifact["requires_attention"] is False
    assert artifact["delivery_priority"] == 10
```

- [ ] **Step 2: Run the targeted tests to confirm failure**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery.py -q -k "classified_artifact_exposes_new_top_level_fields or manifest_retains_old_fields_and_adds_classification_fields"
```

Expected:

- FAIL because `ReportArtifact` does not yet expose `tags`, `recommended_channels`,
  `requires_attention`, or `delivery_priority`
- FAIL because current `report_type` values are still coarse (`run_card`, `watchlist`,
  etc.)

- [ ] **Step 3: Extend the artifact dataclass and add a classification hook**

Update `src/stock_research/report_delivery.py` so `ReportArtifact` includes:

```python
@dataclass(frozen=True)
class ReportArtifact:
    artifact_id: str
    report_type: str
    title: str
    trade_date: str
    generated_at: str
    markdown_path: str | None = None
    json_path: str | None = None
    csv_paths: list[str] = field(default_factory=list)
    run_card_path: str | None = None
    evidence_dir: str | None = None
    warnings: list[str] = field(default_factory=list)
    severity: str = "info"
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    recommended_channels: list[str] = field(default_factory=lambda: ["local"])
    requires_attention: bool = False
    delivery_priority: int = 10
```

Add a helper boundary so collection and classification stay separate:

```python
def _classify_collected_artifacts(
    self,
    artifacts: list[ReportArtifact],
    warnings: list[str],
) -> list[ReportArtifact]:
    return [classify_artifact(item, warnings=warnings) for item in artifacts]
```

Then call it from `collect_artifacts(...)` just before returning:

```python
classified = self._classify_collected_artifacts(
    list(artifacts_by_key.values()),
    warnings,
)
return classified, warnings
```

- [ ] **Step 4: Run the same targeted tests to confirm the contract now passes**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery.py -q -k "classified_artifact_exposes_new_top_level_fields or manifest_retains_old_fields_and_adds_classification_fields"
```

Expected:

- PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/report_delivery.py tests/test_report_delivery.py
git commit -m "feat: add classified report artifact contract"
```

## Task 2: Implement Rule-Based Report Type, Severity, and Summary Detection

**Files:**
- Modify: `src/stock_research/report_delivery.py`
- Test: `tests/test_report_delivery.py`

- [ ] **Step 1: Write the failing classification rule tests**

```python
def test_daily_market_report_uses_specific_market_markers(tmp_path):
    source_dir = tmp_path / "reports"
    source_dir.mkdir()
    report_path = source_dir / "market_state_2026-05-20.md"
    report_path.write_text("# Market State\n", encoding="utf-8")

    artifacts, _ = report_delivery.LocalDeliveryAdapter().collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[source_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
    )

    assert artifacts[0].report_type == "daily_market_report"
    assert artifacts[0].severity == "info"
    assert artifacts[0].summary == "Market State"


def test_watchlist_report_and_must_watch_priority(tmp_path):
    source_dir = tmp_path / "reports"
    source_dir.mkdir()
    (source_dir / "watchlist_report_2026-05-20_core.md").write_text(
        "# Watchlist Core\n",
        encoding="utf-8",
    )
    (source_dir / "must_watch_2026-05-20_core.csv").write_text(
        "stock_code\n000001.SZ\n",
        encoding="utf-8",
    )

    artifacts, _ = report_delivery.LocalDeliveryAdapter().collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[source_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
    )

    assert artifacts[0].report_type == "must_watch_report"
    assert "urgent" in artifacts[0].tags


def test_run_card_bundle_classifies_with_openclaw_channel(tmp_path):
    output = run_card.write_run_card(
        output_dir=tmp_path / "run-cards",
        run_type="daily_research",
        run_id="2026-05-20-core",
        title="Daily Research",
        config={"universe": "core"},
        metrics={"rows": 2},
        artifact_paths={"report": "daily_research.md"},
        warnings=["coverage gap"],
        metadata={"owner": "test"},
        data_coverage={"expected_dates": ["2026-05-20"], "actual_dates": ["2026-05-20"]},
    )

    artifacts, _ = report_delivery.LocalDeliveryAdapter().collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[],
        report_dirs=[],
        run_card_dirs=[output["run_card_dir"]],
        artifact_paths=[],
    )

    artifact = artifacts[0]
    assert artifact.report_type == "run_card_bundle"
    assert "openclaw" in artifact.recommended_channels
    assert artifact.requires_attention is True
    assert artifact.delivery_priority == 10


def test_risk_alert_requires_explicit_risk_shape(tmp_path):
    source_dir = tmp_path / "reports"
    source_dir.mkdir()
    safe_json = source_dir / "watchlist_report_2026-05-20_core.json"
    safe_json.write_text(
        json.dumps({"risk_score": 9, "summary": "Watchlist snapshot"}, ensure_ascii=True),
        encoding="utf-8",
    )
    risk_md = source_dir / "risk_alert_2026-05-20.md"
    risk_md.write_text("# Risk Alert\n", encoding="utf-8")

    artifacts, _ = report_delivery.LocalDeliveryAdapter().collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[source_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
    )

    by_type = {artifact.report_type: artifact for artifact in artifacts}
    assert "risk_alert_report" in by_type
    assert by_type["risk_alert_report"].severity in {"high", "critical"}
    assert by_type["risk_alert_report"].requires_attention is True
    assert by_type["watchlist_report"].severity in {"info", "low", "medium"}


def test_unknown_file_falls_back_to_generic_report(tmp_path):
    source_dir = tmp_path / "reports"
    source_dir.mkdir()
    (source_dir / "misc_snapshot_2026-05-20.md").write_text(
        "# Misc Snapshot\n",
        encoding="utf-8",
    )

    artifacts, _ = report_delivery.LocalDeliveryAdapter().collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[source_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
    )

    assert artifacts[0].report_type == "generic_report"
    assert artifacts[0].severity == "info"
    assert artifacts[0].recommended_channels == ["local"]
```

- [ ] **Step 2: Run the targeted tests to confirm failure**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery.py -q -k "daily_market_report_uses_specific_market_markers or watchlist_report_and_must_watch_priority or run_card_bundle_classifies_with_openclaw_channel or risk_alert_requires_explicit_risk_shape or unknown_file_falls_back_to_generic_report"
```

Expected:

- FAIL because current matching logic only returns coarse types and does not compute the
  new routing fields

- [ ] **Step 3: Implement the rule-based classifiers**

Add lightweight helpers in `src/stock_research/report_delivery.py`:

```python
REPORT_TYPE_PRIORITY = (
    "run_card_bundle",
    "risk_alert_report",
    "must_watch_report",
    "watchlist_signal_report",
    "watchlist_report",
    "factor_eval_report",
    "daily_topn_report",
    "daily_market_report",
    "backtest_report",
    "generic_report",
)


def detect_report_type(artifact: ReportArtifact) -> tuple[str, list[str]]:
    ...


def detect_severity(artifact: ReportArtifact, report_type: str) -> str:
    ...


def extract_summary(artifact: ReportArtifact, warnings: list[str]) -> str:
    ...


def classify_artifact(artifact: ReportArtifact, *, warnings: list[str]) -> ReportArtifact:
    report_type, detected_by = detect_report_type(artifact)
    severity = detect_severity(artifact, report_type)
    summary = extract_summary(artifact, warnings)
    metadata = build_artifact_metadata(
        artifact,
        detected_by=detected_by,
        warning_count=len(artifact.warnings),
    )
    tags = build_tags(report_type=report_type, requires_attention=requires_attention)
    channels = build_recommended_channels(report_type=report_type, severity=severity)
    requires_attention = should_require_attention(
        report_type=report_type,
        severity=severity,
        warning_count=metadata["warning_count"] or 0,
    )
    priority = priority_for_severity(severity)
    return replace(
        artifact,
        report_type=report_type,
        severity=severity,
        summary=summary,
        metadata=metadata,
        tags=tags,
        recommended_channels=channels,
        requires_attention=requires_attention,
        delivery_priority=priority,
    )
```

Use these matching rules:

- `run_card_bundle` when `run_card_path` or `evidence_dir` exists
- `risk_alert_report` only on explicit risk markers from file/dir/title/type, not just a
  `risk_score` field
- `must_watch_report` before `watchlist_signal_report`
- `daily_market_report` only on specific markers:
  - `daily_market`
  - `market_state`
  - `market_regime`
  - `market_summary`
  - `market_report`
- ambiguous severity falls back to `info`
- summary comes only from existing JSON summary, run-card title/metrics/warnings, Markdown
  H1, or cleaned filename

Do not read large files. For Markdown, inspect only the first lines. For JSON, parse
small files only and catch `json.JSONDecodeError` by appending a warning.

- [ ] **Step 4: Run the targeted tests to confirm the classification passes**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery.py -q -k "daily_market_report_uses_specific_market_markers or watchlist_report_and_must_watch_priority or run_card_bundle_classifies_with_openclaw_channel or risk_alert_requires_explicit_risk_shape or unknown_file_falls_back_to_generic_report"
```

Expected:

- PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/report_delivery.py tests/test_report_delivery.py
git commit -m "feat: classify local report artifacts"
```

## Task 3: Enrich Metadata and Harden Corrupt Artifact Handling

**Files:**
- Modify: `src/stock_research/report_delivery.py`
- Test: `tests/test_report_delivery.py`

- [ ] **Step 1: Write the failing metadata and corrupt artifact tests**

```python
def test_metadata_flags_track_available_file_types(tmp_path):
    source_dir = tmp_path / "reports"
    source_dir.mkdir()
    (source_dir / "daily_topn_2026-05-20_manual_v1.md").write_text(
        "# Daily TopN\n",
        encoding="utf-8",
    )
    (source_dir / "daily_topn_2026-05-20_manual_v1.json").write_text(
        json.dumps({"summary": "TopN summary"}, ensure_ascii=True),
        encoding="utf-8",
    )
    (source_dir / "daily_topn_2026-05-20_manual_v1.csv").write_text(
        "stock_code\n000001.SZ\n",
        encoding="utf-8",
    )

    artifacts, _ = report_delivery.LocalDeliveryAdapter().collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[source_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
    )

    metadata = artifacts[0].metadata
    assert metadata["source_kind"] == "file"
    assert metadata["has_markdown"] is True
    assert metadata["has_json"] is True
    assert metadata["has_csv"] is True
    assert metadata["has_run_card"] is False
    assert metadata["has_evidence_bundle"] is False
    assert metadata["warning_count"] == 0


def test_summary_prefers_json_summary_when_present(tmp_path):
    source_dir = tmp_path / "reports"
    source_dir.mkdir()
    (source_dir / "factor_eval_2026-05-20.json").write_text(
        json.dumps({"summary": "Factor gate passed on medium horizon"}, ensure_ascii=True),
        encoding="utf-8",
    )
    (source_dir / "factor_eval_2026-05-20.md").write_text(
        "# Factor Eval Markdown Title\n",
        encoding="utf-8",
    )

    artifacts, _ = report_delivery.LocalDeliveryAdapter().collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[source_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
    )

    assert artifacts[0].summary == "Factor gate passed on medium horizon"


def test_corrupt_json_adds_warning_without_crashing(tmp_path):
    source_dir = tmp_path / "reports"
    source_dir.mkdir()
    bad_json = source_dir / "risk_alert_2026-05-20.json"
    bad_json.write_text("{bad json", encoding="utf-8")

    artifacts, warnings = report_delivery.LocalDeliveryAdapter().collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[source_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
    )

    assert len(artifacts) == 1
    assert artifacts[0].report_type == "risk_alert_report"
    assert any("invalid_json:" in warning for warning in warnings)
```

- [ ] **Step 2: Run the targeted tests to confirm failure**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery.py -q -k "metadata_flags_track_available_file_types or summary_prefers_json_summary_when_present or corrupt_json_adds_warning_without_crashing"
```

Expected:

- FAIL because metadata keys are incomplete and corrupt JSON is not yet surfaced as a
  warning

- [ ] **Step 3: Implement metadata enrichment and safe parsing**

Add helpers in `src/stock_research/report_delivery.py`:

```python
def _load_json_preview(path: Path, warnings: list[str]) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        warnings.append(f"invalid_json:{path}")
        return None


def _load_markdown_title(path: Path) -> str | None:
    with path.open("r", encoding="utf-8") as handle:
        for _ in range(8):
            line = handle.readline()
            if not line:
                break
            if line.startswith("# "):
                return line[2:].strip()
    return None


def build_artifact_metadata(
    artifact: ReportArtifact,
    *,
    detected_by: list[str],
    warning_count: int,
) -> dict[str, Any]:
    return {
        "source_path": primary_source_path(artifact),
        "source_kind": source_kind_for(artifact),
        "detected_by": detected_by,
        "file_count": file_count_for(artifact),
        "has_markdown": artifact.markdown_path is not None,
        "has_json": artifact.json_path is not None,
        "has_csv": bool(artifact.csv_paths),
        "has_run_card": artifact.run_card_path is not None,
        "has_evidence_bundle": artifact.evidence_dir is not None,
        "run_id": extract_run_id(artifact),
        "config_hash": extract_config_hash(artifact, warnings=warnings),
        "workflow_type": extract_workflow_type(artifact),
        "date_range": None,
        "asset_count": extract_asset_count(artifact, warnings=warnings),
        "warning_count": warning_count,
    }
```

Requirements:

- metadata values must remain JSON-safe
- summary should prefer JSON `summary` over Markdown H1
- corrupt JSON should never abort collection
- warnings from damaged files should be surfaced through the adapter warning list

- [ ] **Step 4: Run the targeted tests to confirm pass**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery.py -q -k "metadata_flags_track_available_file_types or summary_prefers_json_summary_when_present or corrupt_json_adds_warning_without_crashing"
```

Expected:

- PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/report_delivery.py tests/test_report_delivery.py
git commit -m "fix: harden local report classification metadata"
```

## Task 4: Update Manifest Reporting and Document the Classification Layer

**Files:**
- Modify: `src/stock_research/report_delivery.py`
- Modify: `tests/test_factor_cli.py`
- Modify: `docs/quant_system/12_p1_report_delivery_adapter_plan.md`
- Test: `tests/test_report_delivery.py`

- [ ] **Step 1: Write the failing CLI and manifest summary tests**

```python
def test_manifest_counts_attention_and_severity(tmp_path):
    source_dir = tmp_path / "reports"
    source_dir.mkdir()
    (source_dir / "risk_alert_2026-05-20.md").write_text("# Risk Alert\n", encoding="utf-8")
    (source_dir / "daily_topn_2026-05-20_manual_v1.md").write_text(
        "# Daily TopN\n",
        encoding="utf-8",
    )

    result = report_delivery.deliver_local_reports(
        trade_date="2026-05-20",
        input_dirs=[source_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
        output_dir=tmp_path / "delivery",
        dry_run=True,
    )

    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert manifest["artifact_count"] == 2
    assert manifest["requires_attention_count"] == 1
    assert manifest["high_severity_count"] == 1
    assert manifest["report_types"] == ["daily_topn_report", "risk_alert_report"]
```

If CLI output is extended, add:

```python
def test_report_delivery_local_prints_classification_summary(tmp_path, capsys):
    source_dir = tmp_path / "reports"
    source_dir.mkdir()
    (source_dir / "risk_alert_2026-05-20.md").write_text("# Risk Alert\n", encoding="utf-8")

    exit_code = cli.main(
        [
            "report-delivery-local",
            "--trade-date",
            "2026-05-20",
            "--input-dir",
            str(source_dir),
            "--output-dir",
            str(tmp_path / "delivery"),
            "--dry-run",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "report_delivery|high_severity|1" in captured.out
    assert "report_delivery|requires_attention|1" in captured.out
```

- [ ] **Step 2: Run the targeted tests to confirm failure**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery.py -q -k "manifest_counts_attention_and_severity"
```

If CLI output changed, also run:

```bash
.venv/bin/pytest tests/test_factor_cli.py -q -k "report_delivery_local"
```

Expected:

- FAIL because manifest summary counters do not yet exist
- optional CLI FAIL if the extra summary lines are added in the test

- [ ] **Step 3: Implement manifest counters and append the doc section**

Update `build_manifest(...)` in `src/stock_research/report_delivery.py`:

```python
def build_manifest(...):
    report_types = sorted({artifact.report_type for artifact in artifacts})
    requires_attention_count = sum(1 for artifact in artifacts if artifact.requires_attention)
    high_severity_count = sum(
        1 for artifact in artifacts if artifact.severity in {"high", "critical"}
    )
    return {
        "generated_at": generated_at,
        "trade_date": trade_date,
        "channel": "local",
        "artifact_count": len(artifacts),
        "artifacts": [asdict(artifact) for artifact in artifacts],
        "warnings": warnings,
        "errors": errors,
        "report_types": report_types,
        "requires_attention_count": requires_attention_count,
        "high_severity_count": high_severity_count,
    }
```

If CLI output is extended, print additive lines only:

```python
print(f"report_delivery|high_severity|{manifest['high_severity_count']}")
print(f"report_delivery|requires_attention|{manifest['requires_attention_count']}")
print(
    "report_delivery|report_types|"
    + ",".join(manifest["report_types"])
)
```

Append a short `Artifact Classification` section to
`docs/quant_system/12_p1_report_delivery_adapter_plan.md` covering:

- supported `report_type` list
- severity rules
- summary extraction rules
- `recommended_channels` rules
- `requires_attention` rules
- `delivery_priority` mapping
- how this layer feeds future OpenClaw and Feishu adapters

- [ ] **Step 4: Run the focused verification**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery.py -q
```

If CLI output changed, also run:

```bash
.venv/bin/pytest tests/test_factor_cli.py -q -k "report_delivery_local"
```

Expected:

- PASS for `tests/test_report_delivery.py`
- PASS for the local delivery CLI subset if modified

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/report_delivery.py tests/test_report_delivery.py tests/test_factor_cli.py docs/quant_system/12_p1_report_delivery_adapter_plan.md
git commit -m "feat: enrich local report delivery classification"
```

## Task 5: Final Verification

**Files:**
- Verify only

- [ ] **Step 1: Run the required report delivery test suite**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery.py -q
```

Expected:

- PASS

- [ ] **Step 2: Run CLI tests if the CLI output changed**

Run:

```bash
.venv/bin/pytest tests/test_factor_cli.py -q -k "report_delivery_local"
```

Expected:

- PASS

- [ ] **Step 3: Inspect worktree state**

Run:

```bash
git status --short
```

Expected:

- Only the intended tracked file changes for classification enhancement
- Ignore unrelated untracked `docs/superpowers/*` notes

- [ ] **Step 4: Prepare handoff summary**

Summarize:

- files changed
- supported report types
- severity, attention, and priority rules
- new manifest fields
- test results
- confirmation that no external services were accessed

No commit in this task. Use this summary for the final user-facing closeout after
implementation.

## Self-Review

- Spec coverage:
  - classification fields: covered in Task 1
  - report type detection and fixed priority: covered in Task 2
  - severity and summary rules: covered in Task 2
  - metadata enrichment and corrupt JSON tolerance: covered in Task 3
  - manifest enrichment and doc update: covered in Task 4
  - verification and no external service scope: covered in Task 5
- Placeholder scan:
  - no `TODO`, `TBD`, or implicit “add tests later” steps remain
- Type consistency:
  - top-level artifact fields are consistent across Tasks 1-4
  - helper names used later are introduced in Task 2 or Task 3
