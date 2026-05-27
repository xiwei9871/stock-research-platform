# Local Report Delivery Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-only report delivery adapter that scans or accepts report artifact paths, generates `manifest.json`, writes `delivery_log.jsonl`, and exposes a safe dry-run CLI without touching external services.

**Architecture:** Add a single new module `report_delivery.py` that owns the `ReportArtifact`, `DeliveryResult`, and `LocalDeliveryAdapter` abstractions. Keep the first implementation local-only: collect artifacts from mixed inputs, normalize them into a manifest, optionally materialize a local delivery snapshot under `outputs/report_delivery/YYYY-MM-DD/`, and expose it through a new CLI command in `cli.py`.

**Tech Stack:** Python 3, dataclasses, pathlib, json/jsonl, existing CLI parser patterns, pytest, tmp_path-based filesystem tests

---

## File Structure

- Create: `src/stock_research/report_delivery.py`
  - Own data structures, artifact collection, manifest generation, local delivery execution, and JSONL log writing.
- Modify: `src/stock_research/cli.py`
  - Add a `report-delivery-local` command and wire it to the new module.
- Create: `tests/test_report_delivery.py`
  - Cover filesystem scanning, artifact normalization, manifest generation, dry-run behavior, and delivery log writing.
- Modify: `tests/test_factor_cli.py`
  - Add parser/runtime coverage for the new CLI command.
- Modify: `docs/quant_system/12_p1_report_delivery_adapter_plan.md`
  - Append the minimal “implementation started” notes required by the user: output directory convention, manifest fields, delivery log fields, and CLI example.

This plan does not modify report generators such as `daily_pipeline.py`, `run_card.py`, `reports/watchlist_report.py`, or `reports/daily_research_report_cli.py`.

### Task 1: Build The Local Artifact Model And Collector

**Files:**
- Create: `src/stock_research/report_delivery.py`
- Create: `tests/test_report_delivery.py`

- [ ] **Step 1: Write the failing artifact collection tests**

Create `tests/test_report_delivery.py` with the first two tests:

```python
import json
from pathlib import Path

from stock_research import report_delivery


def test_collect_artifacts_scans_markdown_json_csv_and_run_card(tmp_path):
    input_dir = tmp_path / "reports"
    run_card_dir = input_dir / "run_card" / "daily"
    evidence_dir = run_card_dir / "evidence"
    evidence_dir.mkdir(parents=True)

    (input_dir / "daily_topn_2026-05-20_manual_v1.md").write_text("# topn\n", encoding="utf-8")
    (input_dir / "daily_topn_2026-05-20_manual_v1.csv").write_text("rank,asset_id\n1,A\n", encoding="utf-8")
    (input_dir / "watchlist_report_2026-05-20_core.json").write_text("[]\n", encoding="utf-8")
    (run_card_dir / "run_card.json").write_text("{}", encoding="utf-8")
    (evidence_dir / "manifest.json").write_text("{}", encoding="utf-8")

    adapter = report_delivery.LocalDeliveryAdapter()
    artifacts, warnings = adapter.collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[input_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
    )

    artifact_types = {item.report_type for item in artifacts}
    assert "topn" in artifact_types
    assert "watchlist" in artifact_types
    assert "run_card" in artifact_types
    assert warnings == []
```

```python
def test_collect_artifacts_returns_warning_for_empty_input_dir(tmp_path):
    input_dir = tmp_path / "empty"
    input_dir.mkdir()

    adapter = report_delivery.LocalDeliveryAdapter()
    artifacts, warnings = adapter.collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[input_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
    )

    assert artifacts == []
    assert warnings == [f"no_artifacts_found:{input_dir}"]
```

- [ ] **Step 2: Run the new delivery tests and verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery.py -q
```

Expected:

```text
ERROR tests/test_report_delivery.py
E   ImportError: cannot import name 'report_delivery'
```

- [ ] **Step 3: Implement the minimal local artifact collector**

Create `src/stock_research/report_delivery.py` with:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import hashlib
import json
import shutil


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
```

```python
@dataclass(frozen=True)
class DeliveryResult:
    delivery_id: str
    channel: str
    status: str
    artifact_count: int
    output_dir: str
    manifest_path: str | None
    delivery_log_path: str | None
    errors: list[str]
    generated_at: str
```

```python
class LocalDeliveryAdapter:
    def collect_artifacts(
        self,
        *,
        trade_date: str,
        input_dirs: list[str | Path],
        report_dirs: list[str | Path],
        run_card_dirs: list[str | Path],
        artifact_paths: list[str | Path],
    ) -> tuple[list[ReportArtifact], list[str]]:
        ...
```

Implement these helpers:

- `_scan_dir(...)`
- `_artifact_from_path(...)`
- `_infer_report_type(path: Path) -> str`
- `_artifact_id_for(path: Path, report_type: str, trade_date: str) -> str`

Required collection behavior:

- recognize `run_card.json` as `report_type="run_card"`
- recognize `evidence/manifest.json` as `report_type="evidence_bundle"`
- infer `watchlist`, `topn`, `daily_research`, `risk_alerts`, `market_state`, `sector_strength`, `position_review`, else `unknown`
- if a directory exists but yields no supported files, emit `no_artifacts_found:<path>`
- for explicit artifact paths, missing files should become warnings, not crashes:
  - `missing_artifact_path:<path>`

- [ ] **Step 4: Re-run the delivery tests and make them pass**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit the artifact collector slice**

Run:

```bash
git add src/stock_research/report_delivery.py tests/test_report_delivery.py
git commit -m "feat: add local report artifact collector"
```

### Task 2: Add Manifest And Delivery Log Writing

**Files:**
- Modify: `src/stock_research/report_delivery.py`
- Modify: `tests/test_report_delivery.py`

- [ ] **Step 1: Write the failing manifest/log tests**

Extend `tests/test_report_delivery.py` with:

```python
def test_deliver_local_writes_manifest_and_delivery_log(tmp_path):
    source_dir = tmp_path / "reports"
    source_dir.mkdir()
    markdown = source_dir / "daily_topn_2026-05-20_manual_v1.md"
    markdown.write_text("# topn\n", encoding="utf-8")

    adapter = report_delivery.LocalDeliveryAdapter()
    result = adapter.deliver_local(
        trade_date="2026-05-20",
        input_dirs=[source_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
        output_dir=tmp_path / "delivery",
        dry_run=False,
    )

    manifest_path = Path(result.manifest_path)
    delivery_log_path = Path(result.delivery_log_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    log_lines = delivery_log_path.read_text(encoding="utf-8").splitlines()

    assert result.status == "completed"
    assert result.channel == "local"
    assert result.artifact_count == 1
    assert manifest["channel"] == "local"
    assert manifest["trade_date"] == "2026-05-20"
    assert manifest["artifact_count"] == 1
    assert len(log_lines) == 1
    assert json.loads(log_lines[0])["status"] == "completed"
```

```python
def test_deliver_local_dry_run_does_not_write_delivery_log(tmp_path):
    source_dir = tmp_path / "reports"
    source_dir.mkdir()
    (source_dir / "watchlist_report_2026-05-20_core.md").write_text("# watchlist\n", encoding="utf-8")

    adapter = report_delivery.LocalDeliveryAdapter()
    result = adapter.deliver_local(
        trade_date="2026-05-20",
        input_dirs=[source_dir],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
        output_dir=tmp_path / "delivery",
        dry_run=True,
    )

    assert result.status == "dry_run"
    assert result.delivery_log_path is None
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert manifest["artifact_count"] == 1
```

- [ ] **Step 2: Run the focused manifest/log tests and verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery.py -q -k "manifest or dry_run"
```

Expected:

```text
FAILED ... AttributeError: 'LocalDeliveryAdapter' object has no attribute 'deliver_local'
```

- [ ] **Step 3: Implement manifest and delivery log writing**

In `src/stock_research/report_delivery.py`, add:

- `build_manifest(...)`
- `write_delivery_log(...)`
- `deliver_local(...)`

Manifest structure must include:

```python
{
    "generated_at": generated_at,
    "trade_date": trade_date,
    "channel": "local",
    "artifact_count": len(artifacts),
    "artifacts": [asdict(artifact) for artifact in artifacts],
    "warnings": warnings,
    "errors": errors,
}
```

Delivery log JSONL line must include:

```python
{
    "delivery_id": delivery_id,
    "generated_at": generated_at,
    "channel": "local",
    "status": status,
    "trade_date": trade_date,
    "artifact_count": len(artifacts),
    "manifest_path": str(manifest_path),
    "error_message": "; ".join(errors) if errors else "",
}
```

Non dry-run behavior:

- create `output_dir`
- create `output_dir/artifacts`
- copy collected files into `artifacts/`
- write `manifest.json`
- append one line to `delivery_log.jsonl`

Dry-run behavior:

- still write a preview `manifest.json`
- do not write `delivery_log.jsonl`
- do not copy artifacts
- return `status="dry_run"`

- [ ] **Step 4: Re-run the focused manifest/log tests and make them pass**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery.py -q -k "manifest or dry_run"
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit the local delivery execution slice**

Run:

```bash
git add src/stock_research/report_delivery.py tests/test_report_delivery.py
git commit -m "feat: add local report delivery manifest and log"
```

### Task 3: Add CLI Wiring For `report-delivery-local`

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write the failing CLI parser/runtime tests**

Add these tests to `tests/test_factor_cli.py`:

```python
def test_cli_accepts_report_delivery_local_command():
    args = build_parser().parse_args(
        [
            "report-delivery-local",
            "--trade-date",
            "2026-05-20",
            "--input-dir",
            "outputs/reports",
            "--output-dir",
            "outputs/report_delivery/2026-05-20",
            "--dry-run",
        ]
    )

    assert args.command == "report-delivery-local"
    assert args.trade_date == "2026-05-20"
    assert args.input_dir == ["outputs/reports"]
    assert args.output_dir == "outputs/report_delivery/2026-05-20"
    assert args.dry_run is True
```

```python
def test_report_delivery_local_cli_prints_manifest_summary(monkeypatch, capsys):
    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "deliver_local_reports",
        lambda **kwargs: {
            "status": "dry_run",
            "artifact_count": 2,
            "manifest_path": "/tmp/manifest.json",
            "delivery_log_path": None,
            "output_dir": "/tmp/delivery",
            "errors": [],
        },
    )

    cli.main_for_args(
        [
            "report-delivery-local",
            "--trade-date",
            "2026-05-20",
            "--input-dir",
            "outputs/reports",
            "--output-dir",
            "/tmp/delivery",
            "--dry-run",
        ]
    )

    assert capsys.readouterr().out.splitlines() == [
        "report_delivery|status|dry_run",
        "report_delivery|artifacts|2",
        "report_delivery|manifest|/tmp/manifest.json",
        "report_delivery|output_dir|/tmp/delivery",
    ]
```

- [ ] **Step 2: Run the targeted CLI tests and verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_factor_cli.py -q -k "report_delivery_local"
```

Expected:

```text
FAILED ... SystemExit
FAILED ... AttributeError
```

- [ ] **Step 3: Wire the new command into `cli.py`**

In `src/stock_research/cli.py`:

1. Import the helper from `report_delivery.py`, for example:

```python
from stock_research.report_delivery import deliver_local_reports
```

2. Add a parser:

```python
report_delivery_local = subparsers.add_parser("report-delivery-local")
report_delivery_local.add_argument("--trade-date", required=True)
report_delivery_local.add_argument("--input-dir", action="append", default=[])
report_delivery_local.add_argument("--report-dir", action="append", default=[])
report_delivery_local.add_argument("--run-card-dir", action="append", default=[])
report_delivery_local.add_argument("--artifact-path", action="append", default=[])
report_delivery_local.add_argument("--output-dir", required=True)
report_delivery_local.add_argument("--dry-run", action="store_true", default=True)
```

3. Add a runtime branch that calls the adapter and prints a short summary:

```python
elif args.command == "report-delivery-local":
    result = deliver_local_reports(
        trade_date=args.trade_date,
        input_dirs=args.input_dir,
        report_dirs=args.report_dir,
        run_card_dirs=args.run_card_dir,
        artifact_paths=args.artifact_path,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
    )
    print(f"report_delivery|status|{result['status']}")
    print(f"report_delivery|artifacts|{result['artifact_count']}")
    print(f"report_delivery|manifest|{result['manifest_path']}")
    print(f"report_delivery|output_dir|{result['output_dir']}")
```

- [ ] **Step 4: Re-run the targeted CLI tests and make them pass**

Run:

```bash
.venv/bin/pytest tests/test_factor_cli.py -q -k "report_delivery_local"
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit the CLI slice**

Run:

```bash
git add src/stock_research/cli.py tests/test_factor_cli.py
git commit -m "feat: add local report delivery CLI"
```

### Task 4: Update The P1 Design Doc And Run Final Regression

**Files:**
- Modify: `docs/quant_system/12_p1_report_delivery_adapter_plan.md`
- Modify: `tests/test_report_delivery.py`
- Modify: `tests/test_factor_cli.py` if final polish is needed

- [ ] **Step 1: Add the required doc updates**

Append a short implementation-started note to `docs/quant_system/12_p1_report_delivery_adapter_plan.md` covering:

- Local Delivery Adapter implementation has started
- output directory convention
- `manifest.json` fields
- `delivery_log.jsonl` fields
- CLI example

Use short prose, not a rewrite. Suggested section heading:

```markdown
## Local Delivery Baseline
```

- [ ] **Step 2: Add the remaining negative-path tests**

Extend `tests/test_report_delivery.py` with:

```python
def test_collect_artifacts_warns_for_missing_explicit_path(tmp_path):
    adapter = report_delivery.LocalDeliveryAdapter()
    artifacts, warnings = adapter.collect_artifacts(
        trade_date="2026-05-20",
        input_dirs=[],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[tmp_path / "missing.md"],
    )

    assert artifacts == []
    assert warnings == [f"missing_artifact_path:{tmp_path / 'missing.md'}"]
```

```python
def test_deliver_local_reports_returns_clear_error_for_missing_input_dir(tmp_path):
    result = report_delivery.deliver_local_reports(
        trade_date="2026-05-20",
        input_dirs=[tmp_path / "missing"],
        report_dirs=[],
        run_card_dirs=[],
        artifact_paths=[],
        output_dir=tmp_path / "delivery",
        dry_run=True,
    )

    assert result["status"] == "warning"
    assert "missing_input_dir" in result["errors"][0]
```

- [ ] **Step 3: Run the final local-delivery regression set**

Run:

```bash
.venv/bin/pytest tests/test_report_delivery.py -q
```

If CLI coverage was added in `tests/test_factor_cli.py`, also run:

```bash
.venv/bin/pytest tests/test_factor_cli.py -q -k "report_delivery_local"
```

Expected:

```text
all selected tests passed
```

- [ ] **Step 4: Review the final diff**

Run:

```bash
git diff -- src/stock_research/report_delivery.py src/stock_research/cli.py tests/test_report_delivery.py tests/test_factor_cli.py docs/quant_system/12_p1_report_delivery_adapter_plan.md
```

Verify:

- no external-service calls
- no Feishu/OpenClaw logic
- no changes to existing report generators
- dry-run remains safe

- [ ] **Step 5: Commit the local-delivery baseline**

Run:

```bash
git add src/stock_research/report_delivery.py src/stock_research/cli.py tests/test_report_delivery.py tests/test_factor_cli.py docs/quant_system/12_p1_report_delivery_adapter_plan.md
git commit -m "feat: add local report delivery adapter baseline"
```

## Self-Review

### Spec coverage

- Local-only adapter and no external services: Tasks 1-4
- Mixed input model: Tasks 1 and 3
- `ReportArtifact` / `DeliveryResult` / `LocalDeliveryAdapter`: Tasks 1 and 2
- `manifest.json` and `delivery_log.jsonl`: Task 2
- CLI with safe dry-run: Task 3
- Plan doc update: Task 4

### Placeholder scan

- No `TBD`, `TODO`, or deferred placeholders remain
- Every task includes concrete file paths, code snippets, commands, and expected results
- Later tasks only reference functions introduced earlier in the plan

### Type consistency

- Module: `src/stock_research/report_delivery.py`
- Main entrypoint: `deliver_local_reports(...)`
- Core classes: `ReportArtifact`, `DeliveryResult`, `LocalDeliveryAdapter`
- Output files: `manifest.json`, `delivery_log.jsonl`
