# Research Infra Artifact Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a lightweight JSONL artifact index so generated `research_infra` evidence bundles can be discovered without walking output directories.

**Architecture:** Create a generic `artifact_index.py` contract under `stock_research.research_infra`, then integrate it into the existing mid-trend sidecar writer through an optional `artifact_index_path`. Keep default behavior unchanged: no index is written unless a caller explicitly passes an index path.

**Tech Stack:** Python 3.11+, dataclasses, JSONL files, pytest, existing `research_infra.mid_trend_integration`.

---

## File Structure

- Create `src/stock_research/research_infra/artifact_index.py`
  - Owns the record dataclass, JSON export/import, append, read, and deduplication.
- Create `tests/test_research_infra_artifact_index.py`
  - Tests append/read, missing file behavior, and duplicate skip.
- Modify `src/stock_research/research_infra/mid_trend_integration.py`
  - Accept optional `artifact_index_path`.
  - Append a mid-trend artifact index record when enabled.
  - Return `artifact_index_path` only when enabled.
- Modify `tests/test_research_infra_mid_trend_integration.py`
  - Tests optional index writing and repeated-run dedupe.
- Optional later main-worktree sync:
  - `src/stock_research/mid_trend_portfolio_review.py`
  - `src/stock_research/cli.py`
  - `tests/test_mid_trend_portfolio_review.py`

## Task 1: Generic Artifact Index Contract

**Files:**
- Create: `tests/test_research_infra_artifact_index.py`
- Create: `src/stock_research/research_infra/artifact_index.py`

- [ ] **Step 1: Write failing artifact index tests**

Create `tests/test_research_infra_artifact_index.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from stock_research.research_infra.artifact_index import (
    ResearchInfraArtifactIndexRecord,
    append_artifact_index_record,
    export_artifact_index_record,
    read_artifact_index,
)


def _record(run_id: str = "run-1") -> ResearchInfraArtifactIndexRecord:
    return ResearchInfraArtifactIndexRecord(
        run_id=run_id,
        run_type="mid_trend_portfolio_review",
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        created_at="2026-06-04T15:00:00",
        research_infra_dir="outputs/research/research_infra",
        run_card_json_path="outputs/research/research_infra/run_card/run_card.json",
        research_signals_json_path="outputs/research/research_infra/research_signals.json",
        attribution_cards_json_path="outputs/research/research_infra/attribution_cards.json",
        attribution_cards_md_path="outputs/research/research_infra/attribution_cards.md",
        experiment_registry_path="outputs/research/research_infra/experiment_registry.jsonl",
        metrics={"research_signal_count": 6, "attribution_card_count": 1},
        warnings=[],
        caveats=["review-only; no execution instruction"],
    )


def test_append_and_read_artifact_index_record(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "research_infra_index.jsonl"
    append_artifact_index_record(path, _record())

    rows = read_artifact_index(path)

    assert len(rows) == 1
    assert rows[0] == _record()
    raw_line = path.read_text(encoding="utf-8").strip()
    payload = json.loads(raw_line)
    assert payload["run_id"] == "run-1"
    assert payload["metrics"]["research_signal_count"] == 6


def test_append_artifact_index_record_skips_duplicate_run_dir_pair(tmp_path: Path) -> None:
    path = tmp_path / "research_infra_index.jsonl"
    append_artifact_index_record(path, _record())
    append_artifact_index_record(path, _record())

    rows = read_artifact_index(path)

    assert len(rows) == 1
    assert rows[0].run_id == "run-1"


def test_read_artifact_index_returns_empty_for_missing_file(tmp_path: Path) -> None:
    assert read_artifact_index(tmp_path / "missing.jsonl") == []


def test_export_artifact_index_record_uses_stable_keys() -> None:
    payload = export_artifact_index_record(_record())

    assert list(payload) == [
        "attribution_cards_json_path",
        "attribution_cards_md_path",
        "caveats",
        "created_at",
        "experiment_registry_path",
        "metrics",
        "research_infra_dir",
        "research_signals_json_path",
        "run_card_json_path",
        "run_id",
        "run_type",
        "strategy_variant",
        "trade_date",
        "warnings",
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_research_infra_artifact_index.py -q
```

Expected: fail with `ModuleNotFoundError` or import error for `stock_research.research_infra.artifact_index`.

- [ ] **Step 3: Implement the artifact index module**

Create `src/stock_research/research_infra/artifact_index.py`:

```python
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ResearchInfraArtifactIndexRecord:
    run_id: str
    run_type: str
    trade_date: str
    strategy_variant: str
    created_at: str
    research_infra_dir: str
    run_card_json_path: str
    research_signals_json_path: str
    attribution_cards_json_path: str
    attribution_cards_md_path: str
    experiment_registry_path: str
    metrics: dict[str, Any]
    warnings: list[str]
    caveats: list[str]


def export_artifact_index_record(
    record: ResearchInfraArtifactIndexRecord,
) -> dict[str, Any]:
    return dict(sorted(asdict(record).items()))


def append_artifact_index_record(
    path: str | Path,
    record: ResearchInfraArtifactIndexRecord,
) -> None:
    index_path = Path(path)
    existing_records = read_artifact_index(index_path)
    record_key = (record.run_id, record.research_infra_dir)
    existing_keys = {
        (existing.run_id, existing.research_infra_dir)
        for existing in existing_records
    }
    if record_key in existing_keys:
        return

    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                export_artifact_index_record(record),
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )


def read_artifact_index(path: str | Path) -> list[ResearchInfraArtifactIndexRecord]:
    index_path = Path(path)
    if not index_path.exists():
        return []

    records: list[ResearchInfraArtifactIndexRecord] = []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        records.append(ResearchInfraArtifactIndexRecord(**payload))
    return records
```

- [ ] **Step 4: Run artifact index tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_research_infra_artifact_index.py -q
```

Expected:

```text
4 passed
```

- [ ] **Step 5: Commit generic artifact index**

Run:

```bash
git add src/stock_research/research_infra/artifact_index.py tests/test_research_infra_artifact_index.py
git commit -m "feat: add research infra artifact index"
```

## Task 2: Mid-Trend Sidecar Index Integration

**Files:**
- Modify: `tests/test_research_infra_mid_trend_integration.py`
- Modify: `src/stock_research/research_infra/mid_trend_integration.py`

- [ ] **Step 1: Write failing mid-trend index tests**

Update imports in `tests/test_research_infra_mid_trend_integration.py`:

```python
from stock_research.research_infra.artifact_index import read_artifact_index
from stock_research.research_infra.experiment_registry import read_experiment_registry
```

Append these tests after `test_mid_trend_integration_handles_empty_review_rows`:

```python
def test_mid_trend_integration_writes_artifact_index_when_enabled(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "research_infra_index.jsonl"

    result = write_mid_trend_research_infra_artifacts(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        review_result=_toy_review_result(tmp_path),
        output_dir=tmp_path,
        artifact_index_path=index_path,
    )

    assert result["artifact_index_path"] == str(index_path)
    records = read_artifact_index(index_path)
    assert len(records) == 1
    record = records[0]
    assert record.run_id == "mid-trend-review-2026-06-04-top5_weekly_max_2_replacements"
    assert record.run_type == "mid_trend_portfolio_review"
    assert record.trade_date == "2026-06-04"
    assert record.strategy_variant == "top5_weekly_max_2_replacements"
    assert record.research_infra_dir == result["research_infra_dir"]
    assert record.run_card_json_path == result["run_card"]["run_card_json_path"]
    assert record.research_signals_json_path == result["research_signals_json_path"]
    assert record.attribution_cards_json_path == result["attribution_cards_json_path"]
    assert record.attribution_cards_md_path == result["attribution_cards_md_path"]
    assert record.experiment_registry_path == result["experiment_registry_path"]
    assert record.metrics["research_signal_count"] == 6
    assert record.metrics["attribution_card_count"] == 1
    assert record.warnings == []
    assert record.caveats == ["review-only; no execution instruction"]


def test_mid_trend_integration_keeps_repeated_run_artifact_index_readable(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "research_infra_index.jsonl"
    kwargs = {
        "trade_date": "2026-06-04",
        "strategy_variant": "top5_weekly_max_2_replacements",
        "review_result": _toy_review_result(tmp_path),
        "output_dir": tmp_path,
        "artifact_index_path": index_path,
    }

    first = write_mid_trend_research_infra_artifacts(**kwargs)
    second = write_mid_trend_research_infra_artifacts(**kwargs)

    records = read_artifact_index(index_path)
    assert len(records) == 1
    assert records[0].run_id == "mid-trend-review-2026-06-04-top5_weekly_max_2_replacements"
    assert first["artifact_index_path"] == second["artifact_index_path"]
```

- [ ] **Step 2: Run mid-trend tests to verify they fail**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_research_infra_mid_trend_integration.py::test_mid_trend_integration_writes_artifact_index_when_enabled tests/test_research_infra_mid_trend_integration.py::test_mid_trend_integration_keeps_repeated_run_artifact_index_readable -q
```

Expected: fail with `TypeError` because `write_mid_trend_research_infra_artifacts(...)` does not accept `artifact_index_path`.

- [ ] **Step 3: Import artifact index helpers in the sidecar writer**

In `src/stock_research/research_infra/mid_trend_integration.py`, add:

```python
from stock_research.research_infra.artifact_index import (
    ResearchInfraArtifactIndexRecord,
    append_artifact_index_record,
)
```

- [ ] **Step 4: Add optional index parameter and write record**

Change the function signature:

```python
def write_mid_trend_research_infra_artifacts(
    *,
    trade_date: str,
    strategy_variant: str,
    review_result: dict[str, Any],
    output_dir: str | Path,
    artifact_index_path: str | Path | None = None,
) -> dict[str, Any]:
```

After the experiment registry append block, add:

```python
    if artifact_index_path is not None:
        append_artifact_index_record(
            artifact_index_path,
            ResearchInfraArtifactIndexRecord(
                run_id=f"mid-trend-review-{trade_date}-{strategy_variant}",
                run_type="mid_trend_portfolio_review",
                trade_date=trade_date,
                strategy_variant=strategy_variant,
                created_at=f"{trade_date}T15:00:00",
                research_infra_dir=str(sidecar_dir),
                run_card_json_path=run_card["run_card_json_path"],
                research_signals_json_path=str(signals_path),
                attribution_cards_json_path=str(attributions_json_path),
                attribution_cards_md_path=str(attributions_md_path),
                experiment_registry_path=str(experiment_registry_path),
                metrics={
                    "review_row_count": int(len(review_rows)),
                    "research_signal_count": len(signals),
                    "attribution_card_count": len(attributions),
                },
                warnings=[] if not review_rows.empty else ["empty_review_rows"],
                caveats=["review-only; no execution instruction"],
            ),
        )
```

Replace the return statement with a local payload so `artifact_index_path` is optional:

```python
    result = {
        "research_infra_dir": str(sidecar_dir),
        "research_signals_json_path": str(signals_path),
        "attribution_cards_json_path": str(attributions_json_path),
        "attribution_cards_md_path": str(attributions_md_path),
        "experiment_registry_path": str(experiment_registry_path),
        "run_card": run_card,
        "research_signal_count": len(signals),
        "attribution_card_count": len(attributions),
    }
    if artifact_index_path is not None:
        result["artifact_index_path"] = str(artifact_index_path)
    return result
```

- [ ] **Step 5: Run mid-trend index tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_research_infra_mid_trend_integration.py::test_mid_trend_integration_writes_artifact_index_when_enabled tests/test_research_infra_mid_trend_integration.py::test_mid_trend_integration_keeps_repeated_run_artifact_index_readable -q
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Run full sidecar tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_research_infra_mid_trend_integration.py -q
```

Expected:

```text
10 passed
```

- [ ] **Step 7: Commit mid-trend artifact index integration**

Run:

```bash
git add src/stock_research/research_infra/mid_trend_integration.py tests/test_research_infra_mid_trend_integration.py
git commit -m "feat: index mid-trend research infra artifacts"
```

## Task 3: Verification And Main-Worktree Sync Note

**Files:**
- No additional code changes in this branch.

- [ ] **Step 1: Run method-layer verification**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_run_card.py \
  tests/test_factor_eval.py \
  tests/test_research_infra_run_evidence.py \
  tests/test_research_infra_experiment_registry.py \
  tests/test_research_infra_feature_registry.py \
  tests/test_research_infra_research_signals.py \
  tests/test_research_infra_factor_cards.py \
  tests/test_research_infra_attribution_cards.py \
  tests/test_research_infra_artifact_index.py \
  tests/test_research_infra_mid_trend_integration.py \
  -q
```

Expected: all listed tests pass.

- [ ] **Step 2: Confirm clean branch**

Run:

```bash
git status --short --branch
```

Expected: clean `method-infra-first-slice` branch.

- [ ] **Step 3: Main-worktree sync note**

If applying this feature to the dirty main worktree where the real runner/CLI exists, make these follow-up edits after copying the updated `research_infra` package:

In `src/stock_research/research_infra/mid_trend_integration.py`, change the wrapper call to compute the default index path:

```python
    artifact_index_path = Path(output_dir) / "research_infra_index.jsonl"
    research_infra = write_mid_trend_research_infra_artifacts(
        trade_date=trade_date,
        strategy_variant=strategy_variant,
        review_result=review_result,
        output_dir=output_dir,
        artifact_index_path=artifact_index_path,
    )
```

In `src/stock_research/cli.py`, after printing `run_card`, print the index path when present:

```python
            artifact_index_path = research_infra.get("artifact_index_path")
            if artifact_index_path:
                print(
                    "mid_trend_portfolio_review|artifact_index|"
                    f"{artifact_index_path}"
                )
```

Add focused tests in `tests/test_mid_trend_portfolio_review.py` to assert:

```python
assert "artifact_index_path" in result["research_infra"]
assert "mid_trend_portfolio_review|artifact_index|" in out
```

Do not stage unrelated dirty main-worktree changes.

## Self-Review

- Spec coverage:
  - Generic JSONL index: Task 1.
  - Deduplication by `(run_id, research_infra_dir)`: Task 1.
  - Missing file read returns `[]`: Task 1.
  - Optional mid-trend index writing: Task 2.
  - Repeated mid-trend runs stay deduped: Task 2.
  - Runner/CLI print path: Task 3 sync note, because the real runner lives in the dirty main worktree, not this clean branch.
- Placeholder scan: no `TBD`, `TODO`, or unspecified code blocks remain.
- Type consistency: the plan consistently uses `ResearchInfraArtifactIndexRecord`, `artifact_index_path`, `research_infra_index.jsonl`, and the existing mid-trend artifact field names.
