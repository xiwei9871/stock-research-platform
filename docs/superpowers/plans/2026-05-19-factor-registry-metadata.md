# Factor Registry / Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a code-side factor registry that centralizes metadata, preserves the current factor pipeline API, and adds validation hooks without changing database schema.

**Architecture:** Add one small registry module that owns factor metadata and derived maps. Keep `factor_config.py` as the compatibility layer that exposes the existing manual V1 config shape, but make it read from the registry. Wire the registry into factor pipeline validation and light-weight metadata access in store/eval code so downstream reporting can rely on one source of truth.

**Tech Stack:** Python, pytest, pandas, existing stock_research modules.

---

### Task 1: Add failing tests for registry metadata and config compatibility

**Files:**
- Create: `tests/test_factor_registry.py`
- Modify: `tests/test_factor_pipeline.py`
- Modify: `tests/test_factor_store.py`
- Modify: `tests/test_factor_eval_store.py`

- [ ] **Step 1: Write the failing test**

```python
from stock_research import factor_config
from stock_research import factor_registry


def test_factor_registry_returns_metadata_for_manual_factor():
    meta = factor_registry.get_factor_metadata("ret_20")
    assert meta.factor_name == "ret_20"
    assert meta.factor_group == "momentum"
    assert meta.direction == "higher"
    assert meta.status == "validated"


def test_manual_v1_config_is_derived_from_registry_maps():
    config = factor_config.manual_v1_config()
    assert config["factor_groups"]["ret_20"] == "momentum"
    assert config["factor_directions"]["volatility_20"] == "lower"
    assert "ret_20_score" in config["weights"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_factor_registry.py tests/test_factor_pipeline.py tests/test_factor_store.py tests/test_factor_eval_store.py -q`
Expected: FAIL because `factor_registry` does not exist yet and registry-backed compatibility is not implemented.

- [ ] **Step 3: Write minimal implementation**

No implementation in this task.

- [ ] **Step 4: Run test to verify it passes**

No implementation yet.

- [ ] **Step 5: Commit**

```bash
git add tests/test_factor_registry.py tests/test_factor_pipeline.py tests/test_factor_store.py tests/test_factor_eval_store.py
git commit -m "test: define factor registry metadata expectations"
```

### Task 2: Implement the code-side factor registry and compatibility maps

**Files:**
- Create: `src/stock_research/factor_registry.py`
- Modify: `src/stock_research/factor_config.py`

- [ ] **Step 1: Write the failing test**

Use the tests from Task 1 and add:

```python
def test_factor_registry_lists_all_known_factor_names():
    names = factor_registry.list_factor_names()
    assert "ret_20" in names
    assert "volatility_20" in names
    assert names == sorted(names)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_factor_registry.py -q`
Expected: FAIL because the registry module is missing.

- [ ] **Step 3: Write minimal implementation**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class FactorMetadata:
    factor_name: str
    factor_group: str
    direction: str
    description: str
    source: str
    calc_version: str
    status: str
    availability_start_date: str | None
    availability_reason: str | None


def list_factor_names() -> list[str]:
    return sorted(_REGISTRY)
```

Populate `_REGISTRY` with the current manual V1 factors already used by `manual_v1_config()`. Make `factor_config.manual_v1_config()` build `factor_groups`, `factor_directions`, and `weights` from the registry while keeping the returned dict shape unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_factor_registry.py tests/test_factor_pipeline.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/factor_registry.py src/stock_research/factor_config.py tests/test_factor_registry.py tests/test_factor_pipeline.py
git commit -m "feat: add code-side factor registry"
```

### Task 3: Add registry validation to factor pipeline and light metadata access in store/eval

**Files:**
- Modify: `src/stock_research/factor_pipeline.py`
- Modify: `src/stock_research/factor_store.py`
- Modify: `src/stock_research/factor_eval_store.py`
- Modify: `tests/test_factor_store.py`
- Modify: `tests/test_factor_eval_store.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_and_store_factor_daily_rejects_unknown_factor_group(monkeypatch):
    ...


def test_factor_store_can_read_factor_metadata_frame():
    ...
```

Add concrete assertions for:
- unknown configured factor names raise a `ValueError`
- factor metadata can be returned as a DataFrame or list of dicts for reports

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_factor_pipeline.py tests/test_factor_store.py tests/test_factor_eval_store.py -q`
Expected: FAIL because validation and metadata access are not wired yet.

- [ ] **Step 3: Write minimal implementation**

Add a small validator in `factor_pipeline.py` that checks configured factor names against the registry before scoring or storing. Add lightweight metadata helper functions in `factor_store.py` and `factor_eval_store.py` that return registry rows without touching PostgreSQL.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_factor_pipeline.py tests/test_factor_store.py tests/test_factor_eval_store.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/factor_pipeline.py src/stock_research/factor_store.py src/stock_research/factor_eval_store.py tests/test_factor_pipeline.py tests/test_factor_store.py tests/test_factor_eval_store.py
git commit -m "feat: wire factor registry validation into pipeline"
```

### Task 4: Update docs and run focused regression tests

**Files:**
- Modify: `docs/quant_system/05_mvp_implementation_plan.md` if the registry is now the next P0 landing point
- Create: `docs/quant_system/10_factor_registry_metadata.md` if a dedicated registry note is needed
- Modify: `tests/test_factor_registry.py`

- [ ] **Step 1: Write the failing test**

Add one test that asserts the registry metadata fields are stable and the config shape remains backward compatible.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_factor_registry.py -q`
Expected: PASS after the code is in place; if it fails, fix the registry data.

- [ ] **Step 3: Write minimal implementation**

Update docs only if the code path changed materially.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_factor_registry.py tests/test_factor_pipeline.py tests/test_factor_store.py tests/test_factor_eval_store.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/quant_system/05_mvp_implementation_plan.md docs/quant_system/10_factor_registry_metadata.md tests/test_factor_registry.py
git commit -m "docs: record factor registry metadata plan"
```

### Coverage Check

This plan covers:
- centralized factor metadata
- backward-compatible `manual_v1_config()`
- factor name validation in the pipeline
- lightweight metadata access from store/eval code
- focused tests for registry behavior and compatibility

It intentionally does not cover:
- new database tables
- new external dependencies
- factor formula rewrites
- run_card/evidence trail
- model training or factor evolution
