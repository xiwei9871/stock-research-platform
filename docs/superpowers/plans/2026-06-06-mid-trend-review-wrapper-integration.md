# Mid-Trend Review Wrapper Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in function wrapper that runs a caller-provided mid-trend review builder and optionally writes standardized `research_infra` sidecar artifacts.

**Architecture:** Keep the integration in `stock_research.research_infra.mid_trend_integration` so it remains a method-layer adapter rather than a dependency on uncommitted mid-trend modules. The wrapper calls the provided builder exactly once, preserves disabled-mode behavior by returning the original object, and adds a shallow `research_infra` metadata key only when artifact writing is enabled.

**Tech Stack:** Python 3.11+, pandas, pytest, existing `write_mid_trend_research_infra_artifacts()`.

---

## File Structure

- Modify `src/stock_research/research_infra/mid_trend_integration.py`
  - Add `Callable` import.
  - Add `build_mid_trend_review_with_research_infra(...)`.
  - Do not import `mid_trend_portfolio_review.py` or any main-worktree-only module.
- Modify `tests/test_research_infra_mid_trend_integration.py`
  - Import the new wrapper.
  - Add disabled-mode, enabled-mode, and non-dict result tests.

## Task 1: Wrapper Tests

**Files:**
- Modify: `tests/test_research_infra_mid_trend_integration.py`

- [ ] **Step 1: Write failing tests for wrapper behavior**

Update the import block:

```python
from stock_research.research_infra.mid_trend_integration import (
    build_mid_trend_review_with_research_infra,
    write_mid_trend_research_infra_artifacts,
)
```

Append these tests after `test_mid_trend_integration_handles_empty_review_rows`:

```python
def test_mid_trend_review_wrapper_disabled_returns_original_without_sidecars(
    tmp_path: Path,
) -> None:
    review_result = _toy_review_result(tmp_path)
    calls = {"count": 0}

    def build_review() -> dict:
        calls["count"] += 1
        return review_result

    result = build_mid_trend_review_with_research_infra(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        review_builder=build_review,
        output_dir=tmp_path,
        write_research_infra=False,
    )

    assert result is review_result
    assert calls["count"] == 1
    assert not (tmp_path / "research_infra").exists()


def test_mid_trend_review_wrapper_enabled_writes_research_infra(
    tmp_path: Path,
) -> None:
    review_result = _toy_review_result(tmp_path)
    calls = {"count": 0}

    def build_review() -> dict:
        calls["count"] += 1
        return review_result

    result = build_mid_trend_review_with_research_infra(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        review_builder=build_review,
        output_dir=tmp_path,
        write_research_infra=True,
    )

    assert result is not review_result
    assert result["portfolio_summary"] == review_result["portfolio_summary"]
    assert result["markdown"] == review_result["markdown"]
    assert result["paths"] == review_result["paths"]
    assert result["review_rows"].equals(review_result["review_rows"])
    assert calls["count"] == 1

    research_infra = result["research_infra"]
    assert Path(research_infra["research_signals_json_path"]).exists()
    assert Path(research_infra["attribution_cards_json_path"]).exists()
    assert Path(research_infra["attribution_cards_md_path"]).exists()
    assert Path(research_infra["experiment_registry_path"]).exists()
    assert Path(research_infra["run_card"]["run_card_json_path"]).exists()
    assert research_infra["research_signal_count"] == 6
    assert research_infra["attribution_card_count"] == 1


def test_mid_trend_review_wrapper_rejects_non_dict_result(tmp_path: Path) -> None:
    def build_review() -> list[str]:
        return ["not", "a", "review", "result"]

    with pytest.raises(TypeError, match="review_builder must return a dict"):
        build_mid_trend_review_with_research_infra(
            trade_date="2026-06-04",
            strategy_variant="top5_weekly_max_2_replacements",
            review_builder=build_review,
            output_dir=tmp_path,
            write_research_infra=True,
        )
```

- [ ] **Step 2: Add the pytest import**

At the top of `tests/test_research_infra_mid_trend_integration.py`, add:

```python
import pytest
```

The import section should be:

```python
import json
from pathlib import Path

import pandas as pd
import pytest
```

- [ ] **Step 3: Run tests to verify the new wrapper tests fail**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_research_infra_mid_trend_integration.py -q
```

Expected: fail during import with an error equivalent to:

```text
ImportError: cannot import name 'build_mid_trend_review_with_research_infra'
```

## Task 2: Wrapper Implementation

**Files:**
- Modify: `src/stock_research/research_infra/mid_trend_integration.py`

- [ ] **Step 1: Add the callable import**

Change the import section from:

```python
from pathlib import Path
from typing import Any
```

to:

```python
from collections.abc import Callable
from pathlib import Path
from typing import Any
```

- [ ] **Step 2: Add the wrapper function**

Insert this function above `write_mid_trend_research_infra_artifacts(...)`:

```python
def build_mid_trend_review_with_research_infra(
    *,
    trade_date: str,
    strategy_variant: str,
    review_builder: Callable[[], dict[str, Any]],
    output_dir: str | Path,
    write_research_infra: bool = False,
) -> dict[str, Any]:
    review_result = review_builder()
    if not isinstance(review_result, dict):
        raise TypeError("review_builder must return a dict review_result")

    if not write_research_infra:
        return review_result

    research_infra = write_mid_trend_research_infra_artifacts(
        trade_date=trade_date,
        strategy_variant=strategy_variant,
        review_result=review_result,
        output_dir=output_dir,
    )
    return {**review_result, "research_infra": research_infra}
```

- [ ] **Step 3: Run focused tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_research_infra_mid_trend_integration.py -q
```

Expected:

```text
8 passed
```

- [ ] **Step 4: Commit the wrapper implementation**

Run:

```bash
git add src/stock_research/research_infra/mid_trend_integration.py tests/test_research_infra_mid_trend_integration.py
git commit -m "feat: add mid-trend review research infra wrapper"
```

## Task 3: Verification

**Files:**
- No file changes expected.

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
  tests/test_research_infra_mid_trend_integration.py \
  -q
```

Expected:

```text
45 passed
```

- [ ] **Step 2: Confirm branch state**

Run:

```bash
git status --short --branch
```

Expected: branch `method-infra-first-slice` with no uncommitted changes after the implementation commit.

## Self-Review

- Spec coverage:
  - Disabled mode returns original object and creates no sidecar directory: Task 1 test.
  - Enabled mode writes sidecars and returns a shallow copy with `research_infra`: Task 1 test and Task 2 implementation.
  - Builder called exactly once: both wrapper behavior tests assert call count.
  - Non-dict builder output raises clear `TypeError`: Task 1 test and Task 2 implementation.
  - No import of uncommitted mid-trend modules: Task 2 only modifies `research_infra.mid_trend_integration`.
- Placeholder scan: no `TBD`, `TODO`, or unspecified implementation steps remain.
- Type consistency: the wrapper signature, import, tests, and expected return shape all use `dict[str, Any]`, `Callable[[], dict[str, Any]]`, `output_dir: str | Path`, and the key name `research_infra`.
