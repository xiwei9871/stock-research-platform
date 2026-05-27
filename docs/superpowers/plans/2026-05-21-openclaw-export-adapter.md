# OpenClaw Export Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local-only OpenClaw export layer that reads the Local Delivery manifest, selects OpenClaw-routable artifacts, and writes structured export files without calling OpenClaw.

**Architecture:** Keep Local Delivery unchanged and introduce a separate OpenClaw export module that consumes `manifest.json` as input. The adapter will transform already-classified artifacts into OpenClaw export items, then emit a manifest, jsonl items, and a log file in a dedicated output directory. Dry-run remains the default and is fully auditable.

**Tech Stack:** Python 3, dataclasses, pathlib, json, csv, pytest, existing stock_research CLI

---

## File Map

- Create: `src/stock_research/report_delivery_openclaw.py`
  - OpenClaw export types, adapter, selector, manifest/log writer
- Modify: `src/stock_research/cli.py`
  - Add `report-delivery-openclaw-export` command
- Modify: `tests/test_factor_cli.py`
  - Add focused CLI coverage if needed
- Create: `tests/test_report_delivery_openclaw.py`
  - New adapter and export tests
- Modify: `docs/quant_system/12_p1_report_delivery_adapter_plan.md`
  - Append the OpenClaw Export Adapter section

## Task 1: Define the OpenClaw Export Contract

**Files:**
- Create: `src/stock_research/report_delivery_openclaw.py`
- Test: `tests/test_report_delivery_openclaw.py`

- [ ] **Step 1: Write the failing contract tests**

```python
def test_openclaw_export_reads_local_manifest_and_filters_openclaw_items(tmp_path):
    local_manifest = {
        "generated_at": "2026-05-21T08:00:00Z",
        "trade_date": "2026-05-20",
        "channel": "local",
        "artifact_count": 2,
        "report_types": ["daily_topn_report", "watchlist_report"],
        "requires_attention_count": 0,
        "high_severity_count": 0,
        "artifacts": [
            {
                "artifact_id": "daily_topn_report:2026-05-20:abc",
                "report_type": "daily_topn_report",
                "title": "Daily TopN",
                "trade_date": "2026-05-20",
                "generated_at": "2026-05-21T08:00:00Z",
                "markdown_path": str(tmp_path / "reports" / "daily_topn.md"),
                "json_path": None,
                "csv_paths": [],
                "run_card_path": None,
                "evidence_dir": None,
                "warnings": [],
                "severity": "info",
                "summary": "Daily TopN",
                "tags": ["daily", "topn"],
                "recommended_channels": ["local", "openclaw"],
                "requires_attention": False,
                "delivery_priority": 10,
                "metadata": {"source_path": str(tmp_path / "reports" / "daily_topn.md")},
            },
            {
                "artifact_id": "watchlist_report:2026-05-20:def",
                "report_type": "watchlist_report",
                "title": "Watchlist Core",
                "trade_date": "2026-05-20",
                "generated_at": "2026-05-21T08:00:00Z",
                "markdown_path": str(tmp_path / "reports" / "watchlist.md"),
                "json_path": None,
                "csv_paths": [],
                "run_card_path": None,
                "evidence_dir": None,
                "warnings": [],
                "severity": "info",
                "summary": "Watchlist Core",
                "tags": ["watchlist"],
                "recommended_channels": ["local"],
                "requires_attention": False,
                "delivery_priority": 10,
                "metadata": {"source_path": str(tmp_path / "reports" / "watchlist.md")},
            },
        ],
        "warnings": [],
        "errors": [],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(local_manifest), encoding="utf-8")

    adapter = report_delivery_openclaw.OpenClawExportAdapter()
    result = adapter.export(
        trade_date="2026-05-20",
        manifest_path=manifest_path,
        output_dir=tmp_path / "openclaw",
        dry_run=True,
    )

    assert result.channel == "openclaw"
    assert result.status == "dry_run"
    assert result.item_count == 1
```

```python
def test_openclaw_export_item_routes_and_actions_are_stable():
    ...
```

- [ ] **Step 2: Run the targeted tests to confirm failure**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery_openclaw.py -q
```

Expected:

- FAIL because the adapter does not yet exist

- [ ] **Step 3: Add the export dataclasses and adapter skeleton**

Create `src/stock_research/report_delivery_openclaw.py` with:

```python
@dataclass(frozen=True)
class OpenClawExportItem:
    item_id: str
    artifact_id: str
    report_type: str
    title: str
    summary: str
    severity: str
    requires_attention: bool
    delivery_priority: int
    tags: list[str]
    source_paths: list[str]
    evidence_paths: list[str]
    run_card_path: str | None
    recommended_action: str
    openclaw_route: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class OpenClawExportResult:
    export_id: str
    channel: str
    status: str
    trade_date: str
    item_count: int
    output_dir: str
    openclaw_manifest_path: str | None
    openclaw_items_path: str | None
    openclaw_delivery_log_path: str | None
    warnings: list[str]
    errors: list[str]
    generated_at: str


class OpenClawExportAdapter:
    def load_local_manifest(...): ...
    def select_openclaw_artifacts(...): ...
    def build_openclaw_item(...): ...
    def export(...): ...
    def write_openclaw_log(...): ...
```

Keep the implementation reference-based:

- read Local Delivery manifest
- do not copy artifact files
- do not call external services

- [ ] **Step 4: Run the targeted tests to confirm the skeleton compiles**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery_openclaw.py -q
```

Expected:

- still failing until the selector and writers are implemented

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/report_delivery_openclaw.py tests/test_report_delivery_openclaw.py
git commit -m "feat: add openclaw export adapter skeleton"
```

## Task 2: Implement Selection, Routing, and Payload Rendering

**Files:**
- Modify: `src/stock_research/report_delivery_openclaw.py`
- Test: `tests/test_report_delivery_openclaw.py`

- [ ] **Step 1: Write focused failing selector tests**

```python
def test_openclaw_export_defaults_to_openclaw_channel_only():
    ...

def test_openclaw_export_include_all_exports_all_artifacts():
    ...

def test_openclaw_export_min_severity_filters_by_threshold():
    ...

def test_openclaw_export_ignores_missing_source_paths_with_warning():
    ...
```

Cover these mapping rules:

- `run_card_bundle` -> `review_evidence`, `evidence_review`
- `daily_topn_report` -> `review_topn_candidates`, `daily_research`
- `watchlist_report` -> `review_watchlist`, `daily_research`
- `must_watch_report` -> `review_must_watch`, `daily_research`
- `risk_alert_report` -> `review_risk_alert`, `research_alert`
- `factor_eval_report` -> `review_factor_eval`, `research_validation`
- `backtest_report` -> `review_backtest`, `research_validation`
- `generic_report` -> `review_report`, `research_inbox`

- [ ] **Step 2: Run the targeted tests to confirm failure**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery_openclaw.py -q -k "defaults_to_openclaw_channel_only or include_all_exports_all_artifacts or min_severity_filters_by_threshold or ignores_missing_source_paths_with_warning"
```

Expected:

- FAIL before the selector is implemented

- [ ] **Step 3: Implement selection and rendering**

Add logic to:

```python
def select_openclaw_artifacts(manifest, *, include_all=False, min_severity="info"):
    ...

def build_openclaw_item(artifact):
    ...
```

Rules:

- only export artifacts with `recommended_channels` containing `openclaw` unless `include_all`
- preserve `run_card_bundle` even if `requires_attention` is false
- skip missing source paths with warnings
- do not promote severity
- use existing manifest values as authoritative

- [ ] **Step 4: Run the targeted tests to confirm pass**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery_openclaw.py -q -k "defaults_to_openclaw_channel_only or include_all_exports_all_artifacts or min_severity_filters_by_threshold or ignores_missing_source_paths_with_warning"
```

Expected:

- PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/report_delivery_openclaw.py tests/test_report_delivery_openclaw.py
git commit -m "feat: render openclaw export items"
```

## Task 3: Write Export Files and Dry-Run Log Behavior

**Files:**
- Modify: `src/stock_research/report_delivery_openclaw.py`
- Test: `tests/test_report_delivery_openclaw.py`

- [ ] **Step 1: Write failing output-file tests**

```python
def test_openclaw_export_writes_manifest_items_and_log(tmp_path):
    ...

def test_openclaw_export_dry_run_writes_dry_run_log_status(tmp_path):
    ...

def test_openclaw_export_empty_match_set_does_not_crash(tmp_path):
    ...
```

- [ ] **Step 2: Run the targeted tests to confirm failure**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery_openclaw.py -q -k "writes_manifest_items_and_log or dry_run_writes_dry_run_log_status or empty_match_set_does_not_crash"
```

Expected:

- FAIL until manifest/log writing is implemented

- [ ] **Step 3: Implement writers**

Write:

```python
openclaw_manifest.json
openclaw_items.jsonl
openclaw_delivery_log.jsonl
```

Manifest fields:

- `generated_at`
- `trade_date`
- `channel`
- `dry_run`
- `source_manifest_path`
- `item_count`
- `items`
- `warnings`
- `errors`

Log fields:

- `export_id`
- `generated_at`
- `channel`
- `status`
- `trade_date`
- `item_count`
- `openclaw_manifest_path`
- `openclaw_items_path`
- `error_message`

Dry-run behavior:

- default `dry_run=True`
- still writes export package
- log status is `dry_run`

- [ ] **Step 4: Run the targeted tests to confirm pass**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery_openclaw.py -q -k "writes_manifest_items_and_log or dry_run_writes_dry_run_log_status or empty_match_set_does_not_crash"
```

Expected:

- PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/report_delivery_openclaw.py tests/test_report_delivery_openclaw.py
git commit -m "feat: add openclaw export file writers"
```

## Task 4: CLI Wiring and Plan Doc Update

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py` only if needed
- Modify: `docs/quant_system/12_p1_report_delivery_adapter_plan.md`
- Test: `tests/test_report_delivery_openclaw.py`
- Test: `tests/test_factor_cli.py` only if CLI output changes

- [ ] **Step 1: Add focused CLI tests**

```python
def test_report_delivery_openclaw_export_cli_parses_args():
    ...

def test_report_delivery_openclaw_export_cli_prints_summary(monkeypatch, capsys):
    ...
```

- [ ] **Step 2: Run the targeted tests to confirm failure**

Run:

```bash
.venv/bin/pytest tests/test_factor_cli.py -q -k "report_delivery"
```

Expected:

- FAIL for the new command until it is wired in

- [ ] **Step 3: Wire the CLI and update docs**

Add `report-delivery-openclaw-export` to `cli.py` with:

- `--trade-date`
- `--manifest`
- `--output-dir`
- `--dry-run`
- `--no-dry-run`
- `--include-all`
- `--min-severity`

Append a short `OpenClaw Export Adapter` section to:

- `docs/quant_system/12_p1_report_delivery_adapter_plan.md`

The section should cover:

- export-only phase
- local manifest input
- output files
- recommended_action rules
- openclaw_route rules
- CLI example
- dry-run semantics
- future live sender separation

- [ ] **Step 4: Run the focused verification**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery_openclaw.py -q
.venv/bin/pytest tests/test_factor_cli.py -q -k "report_delivery"
```

Expected:

- PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/cli.py tests/test_factor_cli.py docs/quant_system/12_p1_report_delivery_adapter_plan.md
git commit -m "feat: add openclaw export cli"
```

## Task 5: Final Verification

**Files:**
- Verify only

- [ ] **Step 1: Run the OpenClaw export test suite**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery.py -q
.venv/bin/pytest tests/test_report_delivery_openclaw.py -q
```

Expected:

- PASS

- [ ] **Step 2: Run CLI regression tests if the CLI changed**

Run:

```bash
.venv/bin/pytest tests/test_factor_cli.py -q -k "report_delivery"
```

Expected:

- PASS

- [ ] **Step 3: Inspect worktree state**

Run:

```bash
git status --short
```

Expected:

- only intended tracked OpenClaw export changes
- ignore unrelated untracked `docs/superpowers/*` notes

- [ ] **Step 4: Prepare handoff summary**

Summarize:

- files changed
- export filtering rules
- recommended_action / openclaw_route rules
- output files
- test results
- confirmation that no external services were accessed

No commit in this task. Use the summary for final user-facing closeout after implementation.

## Self-Review

- Spec coverage:
  - manifest input and selection rules: Task 1 and Task 2
  - export item shape and routing: Task 1 and Task 2
  - output files and dry-run semantics: Task 3
  - CLI and docs: Task 4
  - verification: Task 5
- Placeholder scan:
  - no TODO/TBD placeholders remain
- Type consistency:
  - OpenClaw item/result field names are used consistently across tasks
  - `dry_run` semantics are consistent across manifest/log writer and CLI
