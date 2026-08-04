# Historical Concept Membership Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Obtain and validate a point-in-time concept membership snapshot for the 302 target THS concepts at 2026-07-31 without assigning current provider membership to a historical date.

**Architecture:** Keep the strategy database-only. Historical membership acquisition remains an explicit backfill boundary, but every candidate source must declare its effective date or fail closed. Existing non-PIT THS current-top50 rows are not reused for historical replay.

**Tech Stack:** PostgreSQL via `psycopg`, Python, pandas, pytest, existing `core.concept_membership` SCD2 schema, THS/AkShare only for source validation.

> Operational policy update (2026-08-04): this strict historical-PIT plan is
> no longer a blocker for sector-first P2 acceptance. The production workflow
> uses the 2026-07-09 snapshot as the 2026-07-31 replay proxy and the
> 2026-08-04 snapshot as the latest snapshot; the strict source path remains
> optional for stock-level historical attribution.

---

### Task 1: Inventory locally available historical membership evidence

**Files:**
- Read: `core.concept_membership`
- Read: `artifacts/rolling_sector_oversold/`
- Read: `/tmp/rolling_sector_target_membership_20260731_preview/`
- Create: `/tmp/historical_membership_inventory_20260731.json`

- [x] **Step 1: Query all target membership intervals and source timestamps.**

Run a read-only query for the 302 target codes, grouping by concept, start/end date, source, and `updated_at`; record whether any rows are known to be captured on or before 2026-07-31.

- [x] **Step 2: Search existing reports and artifacts for serialized membership rows.**

Search only existing files; do not modify user-owned artifacts. Accept a candidate only when the file contains concept code, asset code, and an explicit capture/effective date no later than 2026-07-31.

- [x] **Step 3: Write an inventory JSON with evidence classification.**

Classify each candidate as `pit_verified`, `current_unknown_asof`, or `not_membership`. No database writes are allowed in this task.

- [x] **Step 4: Verify the inventory is reproducible.**

Re-run the query/search commands and confirm identical counts and hashes.

### Task 2: Validate whether the provider exposes a historical membership endpoint

**Files:**
- Modify: `src/stock_research/rolling_oversold/target_membership_backfill.py`
- Test: `tests/test_rolling_oversold_target_membership_backfill.py`

- [x] **Step 1: Add a failing test for date-aware source metadata.**

```python
def test_current_ths_source_is_not_accepted_as_historical_snapshot():
    result = validate_membership_source_asof(
        source_asof=None,
        requested_date=date(2026, 7, 31),
    )
    assert result == (False, "source_asof_unknown")
```

- [x] **Step 2: Run the focused test and confirm it fails for the missing helper.**

Run:

```text
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_rolling_oversold_target_membership_backfill.py -k source_asof
```

Expected: failure because the date-aware validation helper does not yet exist.

- [x] **Step 3: Probe THS/AkShare response metadata and URL parameters.**

Verify whether the response carries an effective date or accepts a historical date parameter. A live response that only exposes current fields such as `涨跌幅(%)` must be classified `current_unknown_asof`.

- [x] **Step 4: Implement the minimal date validation helper and fail-closed source contract.**

The helper must accept only an explicit `source_asof <= requested_date`; unknown or later source dates return `False` and a stable reason. The default current THS adapter must report `source_asof=None` rather than pretending it is the requested historical date.

- [x] **Step 5: Run the focused test and source adapter regression tests.**

Run:

```text
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_rolling_oversold_target_membership_backfill.py
```

Expected: all existing tests plus the date-aware fail-closed tests pass.

### Task 3: Select a PIT-verified source or produce a blocked report

**Files:**
- Modify: `src/stock_research/rolling_oversold/target_membership_backfill.py`
- Modify: `src/stock_research/cli.py`
- Modify: `docs/daily-close-pipeline-runbook.md`
- Test: `tests/test_rolling_oversold_target_membership_backfill.py`

- [x] **Step 1: Add a failing test that unknown source-as-of blocks all writes.**

```python
def test_unknown_membership_source_asof_blocks_execute_writes(monkeypatch, tmp_path):
    result = run_target_membership_backfill(
        trade_date=date(2026, 7, 31),
        target_codes=["300238"],
        source_asof=None,
        dry_run=False,
        output_dir=tmp_path,
    )
    assert result["write_blocked"] is True
    assert result["write_blocked_reason"] == "source_asof_unknown"
    assert result["database_writes"] == 0
```

- [x] **Step 2: Run the test and confirm it fails.**

Run the single test; it must fail because execution currently has no source-as-of gate.

- [x] **Step 3: Implement the source-as-of gate and CLI/report fields.**

Expose `source_asof`, `source_effective_date`, and `source_pit_status` in JSON/CSV summaries. An unknown or later source date must set global `write_blocked=True` and skip board, membership, and close SQL. A verified source date may proceed only after the existing 302-code, BSE, 900xxx, master, and pagination checks pass.

- [x] **Step 4: Run focused and full rolling tests.**

Run:

```text
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_rolling_oversold_target_membership_backfill.py tests/test_rolling_oversold_cli.py
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_rolling_oversold_*.py
```

### Task 3A: Add an explicit dated-snapshot import boundary

- [x] **Step 1: Define a dated snapshot file contract.**

Accepted inputs are CSV, JSON, and Parquet with `concept_code`,
`concept_name`, `asset_id`, and one uniform `source_asof` (or
`source_effective_date`). The loader rejects unknown/later dates, duplicate
concept/member pairs, target-scope violations, invalid IDs, and missing target
concepts.

- [x] **Step 2: Route verified files through the existing transactional writer.**

`--membership-snapshot-file` bypasses the live THS adapters, records the source
hash/lineage, and reuses the existing master/PIT/exchange checks and SCD2
upsert/close transaction. A failed snapshot import cannot fall back to a live
current source.

- [x] **Step 3: Add regression coverage and runbook instructions.**

Focused loader, runner, CLI, compile, and rolling test coverage is required
before accepting a real source export.

### Task 4: Execute only if a PIT-verified snapshot exists

**Files:**
- Create: `/tmp/historical_membership_backfill_20260731/`

- [ ] **Step 1: Run a dry-run with the verified source.**

Require `target_code_count=302`, `source_pit_status=verified`, no failed concepts, no missing target codes, and zero unexpected exclusions before execution.

- [ ] **Step 2: Execute one transactional backfill.**

Write board/membership rows and close old SCD2 rows only after the source gate passes. Use the existing conflict key `(asset_id, concept_system, concept_code, start_date)`.

- [ ] **Step 3: Verify database invariants.**

Require 302 active target codes, no active BSE/900xxx, zero active missing-master rows, no duplicate conflict groups, and every active target membership row to have `start_date <= 2026-07-31`.

- [ ] **Step 4: Run the target replay and record evidence.**

Only after the database invariants pass, replay 2026-07-31 and verify all 302 target concept rows have nonzero valid membership.

### Task 5: Close the task with an explicit status

- [x] **Step 1: If no PIT source exists, publish a blocked report.**

State that operational current membership is not a substitute for the 2026-07-31 historical snapshot; leave the database unchanged.

- [ ] **Step 2: If a PIT source exists, publish the source lineage and acceptance report.**

Include source endpoint, source-as-of date, payload hash, target count, valid member count, exclusions, database writes, and replay evidence.

- [x] **Step 3: Run final verification.**

Run compileall, focused tests, full rolling tests, and `git diff --check`; do not modify or commit user-owned artifacts.
