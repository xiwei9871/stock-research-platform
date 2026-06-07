# Hibor A-Tier Report Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a resumable Hibor A-tier research report backfill for active A-shares from `2024-10-01` through run date.

**Architecture:** Extend the existing Hibor downloader into a batch backfill layer. Keep broker quality rules in a data config, write durable CSV artifacts for task/discovery/download status, then reuse the existing Hibor PDF import, PDF field extraction, and stock report feature generation.

**Tech Stack:** Python, pandas, requests, pypdf, existing `stock_research` CLI, existing PostgreSQL stock report schemas.

---

## File Structure

- Create `config/hibor_a_tier_institutions.csv`
  Stores A1/A2 institution aliases and region metadata.

- Modify `src/stock_research/hibor_reports.py`
  Add whitelist loading, broker normalization, all-market task building, batch discovery/download orchestration, resume handling, coverage reporting, and CLI-callable runner functions.

- Modify `src/stock_research/cli.py`
  Add `build-hibor-a-tier-backfill-plan` and `run-hibor-a-tier-backfill`.

- Modify `tests/test_hibor_reports.py`
  Add focused unit tests for whitelist matching, task generation, result filtering, resume behavior, and report summary.

## Task 1: A-Tier Institution Config

**Files:**
- Create: `config/hibor_a_tier_institutions.csv`
- Modify: `src/stock_research/hibor_reports.py`
- Test: `tests/test_hibor_reports.py`

- [ ] **Step 1: Write failing tests**

Add tests that assert:

```python
def test_load_hibor_a_tier_institutions_normalizes_domestic_and_foreign_aliases():
    rules = load_hibor_a_tier_institutions("config/hibor_a_tier_institutions.csv")

    assert normalize_hibor_broker("东吴证券", rules)["institution_name"] == "东吴证券"
    assert normalize_hibor_broker("Morgan Stanley", rules)["institution_name"] == "摩根士丹利"
    assert normalize_hibor_broker("大摩", rules)["region"] == "foreign"
    assert normalize_hibor_broker("未知证券", rules) is None
```

Run:

```bash
.venv/bin/pytest tests/test_hibor_reports.py::test_load_hibor_a_tier_institutions_normalizes_domestic_and_foreign_aliases -q
```

Expected: import/name failure.

- [ ] **Step 2: Create config and loader**

Create `config/hibor_a_tier_institutions.csv` with columns:

```csv
institution_name,alias,tier,group,region
东吴证券,东吴证券,A,A1_domestic,domestic
摩根士丹利,摩根士丹利,A,A2_foreign_hk_international,foreign
摩根士丹利,Morgan Stanley,A,A2_foreign_hk_international,foreign
摩根士丹利,大摩,A,A2_foreign_hk_international,foreign
```

Then include the full A1/A2 list from the design spec.

Implement:

```python
def load_hibor_a_tier_institutions(path: str | Path = DEFAULT_HIBOR_A_TIER_CONFIG) -> list[dict[str, str]]:
    return pd.read_csv(path, dtype=str).fillna("").to_dict("records")

def normalize_hibor_broker(value: str, rules: list[dict[str, str]]) -> dict[str, str] | None:
    text = str(value or "").lower()
    for rule in rules:
        alias = str(rule["alias"]).lower()
        if alias and alias in text:
            return dict(rule)
    return None
```

- [ ] **Step 3: Verify**

Run:

```bash
.venv/bin/pytest tests/test_hibor_reports.py::test_load_hibor_a_tier_institutions_normalizes_domestic_and_foreign_aliases -q
```

Expected: pass.

## Task 2: Full-Universe Task Plan

**Files:**
- Modify: `src/stock_research/hibor_reports.py`
- Test: `tests/test_hibor_reports.py`

- [ ] **Step 1: Write failing tests**

Add tests for pure task building:

```python
def test_build_hibor_a_tier_backfill_plan_outputs_active_asset_tasks(tmp_path):
    assets = pd.DataFrame([
        {"asset_id": "CN:SH:603530", "ts_code": "603530.SH", "stock_name": "神马电力", "symbol": "603530"},
        {"asset_id": "CN:SZ:002484", "ts_code": "002484.SZ", "stock_name": "江海股份", "symbol": "002484"},
    ])

    result = build_hibor_a_tier_backfill_plan(
        assets,
        start_date="2024-10-01",
        end_date="2026-06-04",
        output_dir=tmp_path,
    )

    assert list(result["tasks"]["status"]) == ["pending", "pending"]
    assert Path(result["paths"]["tasks"]).exists()
```

- [ ] **Step 2: Implement task builder**

Implement:

```python
def build_hibor_a_tier_backfill_plan(
    assets: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    frame = assets.copy()
    frame["status"] = "pending"
    write task/report artifacts when output_dir is provided and return {"tasks": frame, "paths": paths}.
```

Include columns:

`task_id, asset_id, ts_code, symbol, stock_name, start_date, end_date, status, discovered_count, downloaded_count, error_type, error_message, started_at, finished_at`

- [ ] **Step 3: Verify**

Run:

```bash
.venv/bin/pytest tests/test_hibor_reports.py::test_build_hibor_a_tier_backfill_plan_outputs_active_asset_tasks -q
```

Expected: pass.

## Task 3: Discovery Filtering

**Files:**
- Modify: `src/stock_research/hibor_reports.py`
- Test: `tests/test_hibor_reports.py`

- [ ] **Step 1: Write failing tests**

Add a test that feeds parsed Hibor rows and expects only A-tier rows:

```python
def test_filter_hibor_discovered_reports_keeps_a_tier_window_only():
    rows = pd.DataFrame([
        {"ts_code": "603530.SH", "title": "东吴证券-神马电力-603530-深度报告-260604", "detail_url": "u1"},
        {"ts_code": "603530.SH", "title": "Morgan Stanley-神马电力-603530-Update-250101", "detail_url": "u2"},
        {"ts_code": "603530.SH", "title": "未知证券-神马电力-603530-点评-260101", "detail_url": "u3"},
        {"ts_code": "603530.SH", "title": "东吴证券-神马电力-603530-旧报告-240901", "detail_url": "u4"},
    ])
    rules = load_hibor_a_tier_institutions("config/hibor_a_tier_institutions.csv")

    filtered = filter_hibor_a_tier_reports(rows, rules, start_date="2024-10-01", end_date="2026-06-04")

    assert filtered["detail_url"].tolist() == ["u1", "u2"]
    assert filtered.loc[filtered["detail_url"].eq("u2"), "broker_region"].iloc[0] == "foreign"
```

- [ ] **Step 2: Implement filter**

Implement:

```python
def filter_hibor_a_tier_reports(
    discovered: pd.DataFrame,
    rules: list[dict[str, str]],
    *,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    Return discovered rows with normalized broker columns and in-window report_date, excluding non-A-tier rows.
```

Parse dates from `YYMMDD` title suffix and normalize to `YYYY-MM-DD`.

- [ ] **Step 3: Verify**

Run the focused test. Expected: pass.

## Task 4: Resumable Batch Runner

**Files:**
- Modify: `src/stock_research/hibor_reports.py`
- Test: `tests/test_hibor_reports.py`

- [ ] **Step 1: Write failing tests**

Add tests that:

- Skip tasks with `status=done`.
- Mark stocks with more than 50 retained reports as `needs_review`.
- Write discovery and download CSVs.

- [ ] **Step 2: Implement runner**

Implement:

```python
def run_hibor_a_tier_backfill(
    *,
    tasks_path: str | Path,
    output_dir: str | Path,
    batch_size: int = 50,
    request_sleep_seconds: float = 1.5,
    download_sleep_seconds: float = 2.0,
    max_reports_per_stock_review_threshold: int = 50,
    write_db: bool = False,
    feature_trade_date: str | None = None,
) -> dict[str, Any]:
    Load pending tasks, discover/filter/download one batch, update status CSVs, import downloaded PDFs, and return summary/path artifacts.
```

The runner should call existing Hibor search/download helpers, then call `import_hibor_report_pdfs()` on the batch download directory.

- [ ] **Step 3: Verify**

Run all Hibor tests:

```bash
.venv/bin/pytest tests/test_hibor_reports.py -q
```

Expected: pass.

## Task 5: CLI Wiring

**Files:**
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_hibor_reports.py`

- [ ] **Step 1: Write failing CLI dispatch tests**

Add tests for:

- `build-hibor-a-tier-backfill-plan`
- `run-hibor-a-tier-backfill`

- [ ] **Step 2: Implement CLI**

Add arguments:

```text
build-hibor-a-tier-backfill-plan
  --start-date
  --end-date
  --sample-size
  --output-dir

run-hibor-a-tier-backfill
  --tasks-path
  --output-dir
  --batch-size
  --request-sleep-seconds
  --download-sleep-seconds
  --write-db
  --feature-trade-date
```

- [ ] **Step 3: Verify**

Run:

```bash
.venv/bin/pytest tests/test_hibor_reports.py -q
.venv/bin/stock-research build-hibor-a-tier-backfill-plan --help
.venv/bin/stock-research run-hibor-a-tier-backfill --help
```

Expected: tests pass and both help commands exit 0.

## Task 6: Pilot Verification

**Files:**
- No new files unless run outputs are intentionally kept under `outputs/research/`.

- [ ] **Step 1: Build a 50-stock pilot plan**

Run:

```bash
.venv/bin/stock-research build-hibor-a-tier-backfill-plan \
  --start-date 2024-10-01 \
  --end-date 2026-06-04 \
  --sample-size 50 \
  --output-dir outputs/research/hibor_a_tier_pilot_20260604
```

- [ ] **Step 2: Run pilot without DB writes**

Run:

```bash
.venv/bin/stock-research run-hibor-a-tier-backfill \
  --tasks-path outputs/research/hibor_a_tier_pilot_20260604/hibor_a_tier_backfill_tasks.csv \
  --output-dir outputs/research/hibor_a_tier_pilot_20260604 \
  --batch-size 50 \
  --request-sleep-seconds 1.5 \
  --download-sleep-seconds 2.0 \
  --feature-trade-date 2026-06-04
```

- [ ] **Step 3: Review pilot report**

Confirm the Markdown report includes:

- searched stock count
- A1 coverage
- A2 coverage
- downloaded PDF count
- skipped non-A-tier count
- failure reason counts
- parse hit rates

Only after the pilot report is acceptable should `--write-db` be used.

## Self-Review

Spec coverage:

- A1/A2 config covered in Task 1.
- Full universe task generation covered in Task 2.
- A-tier filtering and time window covered in Task 3.
- Batch/resume/safety threshold covered in Task 4.
- CLI and pilot runbook covered in Tasks 5-6.

Placeholder scan: no unresolved implementation markers remain in the plan text.

Type consistency: public function names are consistent across tasks.
