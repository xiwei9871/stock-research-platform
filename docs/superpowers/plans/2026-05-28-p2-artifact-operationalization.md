# P2 Artifact Operationalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build P2-1, a file-based daily rollup that turns P1 artifacts into one reviewable package.

**Architecture:** Add a focused `stock_research.p2.artifact_rollup` module that reads an explicit artifact manifest, validates identity fields, summarizes artifact groups, and writes JSON/Markdown rollup files. Add a CLI command that accepts the manifest path and output directory; do not add database tables or schedulers in P2-1.

**Tech Stack:** Python, pandas only where tabular summaries are needed, argparse CLI in `src/stock_research/cli.py`, pytest.

---

## File Structure

- Create `src/stock_research/p2/__init__.py` for the P2 package.
- Create `src/stock_research/p2/artifact_rollup.py` for manifest loading, validation, rollup building, and artifact writing.
- Modify `src/stock_research/cli.py` to add `p2-artifact-rollup`.
- Create `tests/test_p2_artifact_rollup.py` for module behavior.
- Modify `tests/test_factor_cli.py` for parser and CLI dispatch coverage.
- Update `docs/quant_system/14_p2_scope_and_execution_plan.md` only if the implementation changes the accepted P2-1 contract.

## Manifest Contract

The P2-1 input manifest is JSON:

```json
{
  "trade_date": "2026-05-28",
  "run_id": "p2-rollup-2026-05-28",
  "artifacts": [
    {
      "group": "delivery",
      "name": "feishu_preview",
      "path": "outputs/feishu/feishu_preview.json",
      "required": true
    },
    {
      "group": "agent",
      "name": "agent_report",
      "path": "outputs/agent/agent_research_report.json",
      "required": true
    },
    {
      "group": "simulation",
      "name": "portfolio_simulation",
      "path": "outputs/simulation/portfolio_simulation_review.json",
      "required": true
    },
    {
      "group": "factor_validation",
      "name": "factor_validation_review",
      "path": "outputs/factor_validation/factor_validation_review_demo.json",
      "required": false
    },
    {
      "group": "technical_performance",
      "name": "technical_feature_performance",
      "path": "outputs/technical/technical_feature_performance_review.json",
      "required": false
    },
    {
      "group": "watchlist",
      "name": "watchlist_diagnostics",
      "path": "outputs/research/watchlist_diagnostics_2026-05-28_diagnostics_v1.md",
      "required": false
    }
  ]
}
```

The output rollup JSON must contain:

- `trade_date`
- `run_id`
- `status`: `ready`, `warning`, or `blocked`
- `artifact_count`
- `missing_required_count`
- `warning_count`
- `groups`
- `artifacts`

## Task 1: Rollup Validation And Summary

**Files:**
- Create: `src/stock_research/p2/__init__.py`
- Create: `src/stock_research/p2/artifact_rollup.py`
- Test: `tests/test_p2_artifact_rollup.py`

- [ ] **Step 1: Write failing tests for ready and blocked rollups**

Create `tests/test_p2_artifact_rollup.py` with these tests:

```python
from pathlib import Path

from stock_research.p2.artifact_rollup import build_p2_artifact_rollup


def test_build_p2_artifact_rollup_marks_ready_when_required_artifacts_exist(tmp_path):
    artifact_path = tmp_path / "agent_report.json"
    artifact_path.write_text('{"status": "written"}', encoding="utf-8")

    rollup = build_p2_artifact_rollup(
        {
            "trade_date": "2026-05-28",
            "run_id": "p2-rollup-2026-05-28",
            "artifacts": [
                {
                    "group": "agent",
                    "name": "agent_report",
                    "path": str(artifact_path),
                    "required": True,
                }
            ],
        }
    )

    assert rollup["status"] == "ready"
    assert rollup["artifact_count"] == 1
    assert rollup["missing_required_count"] == 0
    assert rollup["artifacts"][0]["exists"] is True
    assert rollup["artifacts"][0]["path"] == str(artifact_path)


def test_build_p2_artifact_rollup_blocks_when_required_artifact_missing(tmp_path):
    missing_path = tmp_path / "missing.json"

    rollup = build_p2_artifact_rollup(
        {
            "trade_date": "2026-05-28",
            "run_id": "p2-rollup-2026-05-28",
            "artifacts": [
                {
                    "group": "simulation",
                    "name": "portfolio_simulation",
                    "path": str(missing_path),
                    "required": True,
                }
            ],
        }
    )

    assert rollup["status"] == "blocked"
    assert rollup["missing_required_count"] == 1
    assert rollup["artifacts"][0]["group"] == "simulation"
    assert rollup["artifacts"][0]["name"] == "portfolio_simulation"
    assert rollup["artifacts"][0]["required"] is True
    assert rollup["artifacts"][0]["exists"] is False
```

Use temporary files for required artifacts. Assert that:

- ready rollup has `status == "ready"`
- blocked rollup has `status == "blocked"`
- blocked rollup has `missing_required_count == 1`
- every artifact row preserves `path`, `group`, `name`, `required`, and `exists`

- [ ] **Step 2: Run red test**

Run:

```bash
.venv/bin/pytest tests/test_p2_artifact_rollup.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'stock_research.p2'`.

- [ ] **Step 3: Implement minimal rollup builder**

Create:

```python
from pathlib import Path
from typing import Any


def build_p2_artifact_rollup(manifest: dict[str, Any]) -> dict[str, Any]:
    trade_date = str(manifest.get("trade_date") or "")
    run_id = str(manifest.get("run_id") or "")
    artifacts = manifest.get("artifacts")
    if not trade_date:
        raise ValueError("p2 artifact rollup requires trade_date")
    if not run_id:
        raise ValueError("p2 artifact rollup requires run_id")
    if not isinstance(artifacts, list):
        raise ValueError("p2 artifact rollup requires artifacts list")

    rows = []
    for item in artifacts:
        path = str(item["path"])
        required = bool(item.get("required"))
        exists = Path(path).exists()
        rows.append(
            {
                "group": str(item["group"]),
                "name": str(item["name"]),
                "path": path,
                "required": required,
                "exists": exists,
            }
        )

    missing_required_count = sum(1 for row in rows if row["required"] and not row["exists"])
    warning_count = sum(1 for row in rows if not row["required"] and not row["exists"])
    status = "blocked" if missing_required_count else "warning" if warning_count else "ready"
    return {
        "trade_date": trade_date,
        "run_id": run_id,
        "status": status,
        "artifact_count": len(rows),
        "missing_required_count": missing_required_count,
        "warning_count": warning_count,
        "groups": sorted({row["group"] for row in rows}),
        "artifacts": rows,
    }
```

Rules:

- `trade_date` and `run_id` are required strings.
- `artifacts` must be a list.
- missing required files make status `blocked`.
- missing optional files make status `warning` unless already blocked.
- all paths are kept as strings exactly as provided.

- [ ] **Step 4: Run green test**

Run:

```bash
.venv/bin/pytest tests/test_p2_artifact_rollup.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/p2 tests/test_p2_artifact_rollup.py
git commit -m "feat: add p2 artifact rollup summary"
```

## Task 2: Rollup Artifact Writer

**Files:**
- Modify: `src/stock_research/p2/artifact_rollup.py`
- Test: `tests/test_p2_artifact_rollup.py`

- [ ] **Step 1: Write failing writer test**

Add:

```python
import json


def test_write_p2_artifact_rollup_outputs_json_and_markdown(tmp_path):
    artifact_path = tmp_path / "simulation.json"
    artifact_path.write_text('{"status": "written"}', encoding="utf-8")
    rollup = build_p2_artifact_rollup(
        {
            "trade_date": "2026-05-28",
            "run_id": "p2-rollup-2026-05-28",
            "artifacts": [
                {
                    "group": "delivery",
                    "name": "feishu_preview",
                    "path": str(artifact_path),
                    "required": True,
                },
                {
                    "group": "simulation",
                    "name": "portfolio_simulation",
                    "path": str(artifact_path),
                    "required": True,
                },
            ],
        }
    )

    paths = write_p2_artifact_rollup(rollup, output_dir=tmp_path / "out")

    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert payload["status"] == "ready"
    assert "P2 Artifact Rollup" in markdown
    assert "delivery" in markdown
    assert "simulation" in markdown
    assert "ready" in markdown
```

Assert that `write_p2_artifact_rollup(rollup, output_dir=tmp_path)` returns:

- `json_path`
- `markdown_path`

Assert JSON includes `status`, and Markdown includes:

- `P2 Artifact Rollup`
- `delivery`
- `simulation`
- `blocked` or `ready`

- [ ] **Step 2: Run red test**

Run:

```bash
.venv/bin/pytest tests/test_p2_artifact_rollup.py -q
```

Expected: fail because `write_p2_artifact_rollup` is missing.

- [ ] **Step 3: Implement writer**

Add:

```python
import json
from pathlib import Path


def write_p2_artifact_rollup(rollup: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    stem = f"p2_artifact_rollup_{rollup['trade_date']}_{rollup['run_id']}"
    json_path = output_path / f"{stem}.json"
    markdown_path = output_path / f"{stem}.md"
    json_path.write_text(json.dumps(rollup, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_render_rollup_markdown(rollup), encoding="utf-8")
    return {"json_path": str(json_path), "markdown_path": str(markdown_path)}
```

Output names:

- `p2_artifact_rollup_<trade_date>_<run_id>.json`
- `p2_artifact_rollup_<trade_date>_<run_id>.md`

- [ ] **Step 4: Run green test**

Run:

```bash
.venv/bin/pytest tests/test_p2_artifact_rollup.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/p2/artifact_rollup.py tests/test_p2_artifact_rollup.py
git commit -m "feat: write p2 artifact rollup artifacts"
```

## Task 3: CLI Command

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write parser test**

Add:

```python
def test_cli_accepts_p2_artifact_rollup_command():
    args = build_parser().parse_args([
        "p2-artifact-rollup",
        "--manifest",
        "outputs/p2/input_manifest.json",
        "--output-dir",
        "outputs/p2",
    ])
    assert args.command == "p2-artifact-rollup"
    assert args.manifest == "outputs/p2/input_manifest.json"
    assert args.output_dir == "outputs/p2"
```

- [ ] **Step 2: Run red parser test**

Run:

```bash
.venv/bin/pytest tests/test_factor_cli.py -q -k p2_artifact_rollup
```

Expected: fail because the command is not registered.

- [ ] **Step 3: Add parser and dispatch test**

Add:

```python
def test_p2_artifact_rollup_cli_prints_paths(capsys, tmp_path):
    artifact_path = tmp_path / "agent_report.json"
    artifact_path.write_text('{"status": "written"}', encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "trade_date": "2026-05-28",
                "run_id": "p2-rollup-2026-05-28",
                "artifacts": [
                    {
                        "group": "agent",
                        "name": "agent_report",
                        "path": str(artifact_path),
                        "required": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cli.main_for_args(
        [
            "p2-artifact-rollup",
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(tmp_path / "rollup"),
        ]
    )

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "p2_artifact_rollup|status|ready"
    assert lines[1].startswith("p2_artifact_rollup|json|")
    assert lines[2].startswith("p2_artifact_rollup|markdown|")
```

Use a temp manifest and real temp artifact files. Assert CLI prints:

- `p2_artifact_rollup|status|ready`
- `p2_artifact_rollup|json|`
- `p2_artifact_rollup|markdown|`

- [ ] **Step 4: Implement CLI**

In `src/stock_research/cli.py`:

- import `build_p2_artifact_rollup` and `write_p2_artifact_rollup`
- add parser `p2-artifact-rollup`
- read manifest JSON
- build rollup
- write artifacts
- print status and paths

- [ ] **Step 5: Run green CLI tests**

Run:

```bash
.venv/bin/pytest tests/test_factor_cli.py -q -k p2_artifact_rollup
```

Expected: pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/stock_research/cli.py tests/test_factor_cli.py
git commit -m "feat: add p2 artifact rollup cli"
```

## Task 4: Final Verification

**Files:**
- Modify only if tests reveal a defect.

- [ ] **Step 1: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/test_p2_artifact_rollup.py tests/test_factor_cli.py -q -k "p2_artifact_rollup"
```

Expected: pass.

- [ ] **Step 2: Run full regression**

Run:

```bash
.venv/bin/pytest -q
```

Expected: pass with no project test failures.

- [ ] **Step 3: Commit any final fixes**

If a fix was needed:

```bash
git add <changed-files>
git commit -m "fix: stabilize p2 artifact rollup"
```

- [ ] **Step 4: Update P2 scope status**

Update `docs/quant_system/14_p2_scope_and_execution_plan.md` to record P2-1 status and verification command result.

Commit:

```bash
git add docs/quant_system/14_p2_scope_and_execution_plan.md
git commit -m "docs: record p2 artifact rollup status"
```
