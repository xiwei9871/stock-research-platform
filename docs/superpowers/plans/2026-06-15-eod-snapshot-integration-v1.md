# EOD Snapshot Integration v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Review Queue and Evidence Digest snapshots a fixed Tier 2 artifact of the local EOD run.

**Architecture:** Add a small EOD snapshot orchestration function beside the Batch C snapshot service, call it from `daily_data_pipeline.py` as an optional post step, expose it through a minimal CLI command, and let existing manifest/readiness summarization classify it as Tier 2.

**Tech Stack:** Python, argparse, FastAPI dashboard read models, PostgreSQL helper functions, pytest.

---

### Task 1: Snapshot EOD Service

**Files:**
- Modify: `src/stock_research/review_evidence_snapshots.py`
- Test: `tests/test_review_evidence_snapshots.py`

- [ ] Write failing tests for `run_eod_review_evidence_snapshots` success, partial, skipped, and idempotent count behavior.
- [ ] Implement `run_eod_review_evidence_snapshots(run_id, trade_date, output_dir=None, score_version="manual_v1", limit=30, asset_id=None, dry_run=False)`.
- [ ] The service calls `build_review_queue`, filters by `asset_id` when provided, and persists snapshots through `snapshot_review_queue_payload`.
- [ ] The service writes `review_evidence_snapshots_summary.json` when `output_dir` is provided.
- [ ] The result includes `status`, `review_item_snapshot_count`, `evidence_digest_snapshot_count`, `skipped_count`, `failed_count`, `warning_count`, `warnings`, `errors`, `artifact_path`, and `asset_count`.

### Task 2: Pipeline Integration

**Files:**
- Modify: `src/stock_research/daily_data_pipeline.py`
- Test: `tests/test_daily_data_pipeline.py`

- [ ] Add `review_evidence_snapshots` to `STEP_MODULES` as `("review_evidence_snapshots", "review_queue/evidence_digest", "tier2")`.
- [ ] Add an optional `snapshot_runner` argument to `run_stock_daily_data_pipeline`.
- [ ] After command steps and before report delivery, run the snapshot step if Tier 1 is not already failed.
- [ ] Convert the snapshot result into a normal step result with rows, warnings, error, artifact path, and metadata.
- [ ] Add summary fields for snapshot counts/status/warnings/errors/path.
- [ ] Ensure `run_manifest.json.modules` contains the snapshot module.

### Task 3: data_run_manifest Persistence

**Files:**
- Modify: `src/stock_research/daily_data_pipeline.py`
- Test: `tests/test_daily_data_pipeline.py`

- [ ] Write a failing test that monkeypatches `upsert_data_run_manifest` and asserts the snapshot module entry is persisted.
- [ ] Import `upsert_data_run_manifest`.
- [ ] Upsert only the current snapshot module entry after the snapshot step completes.
- [ ] Do not fail the EOD run if DB manifest persistence raises; record a warning on the snapshot step instead.

### Task 4: CLI Command

**Files:**
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_daily_data_pipeline.py` or a focused CLI parser test

- [ ] Add parser command `snapshot-review-evidence`.
- [ ] Add arguments `--run-id`, `--trade-date`, `--output-dir`, `--limit`, `--asset-id`, `--dry-run`.
- [ ] Dispatch to `run_eod_review_evidence_snapshots`.
- [ ] Print stable lines for status, review snapshot count, evidence digest snapshot count, warnings, and summary path.

### Task 5: Readiness Compatibility

**Files:**
- Modify: `src/stock_research/dashboard/readiness.py`
- Test: `tests/test_dashboard_readiness.py`

- [ ] Add `review_evidence_snapshots` label and unavailable warning.
- [ ] Add a manifest check for the snapshot module.
- [ ] Verify snapshot Tier 2 failure yields `PARTIAL`, not `BLOCKED`.
- [ ] Verify snapshot success allows `OK` when other modules are healthy.

### Task 6: Runbook

**Files:**
- Modify: `docs/dashboard-local-runbook.md`

- [ ] Add snapshot post-step outputs to the EOD manifest smoke section.
- [ ] Add the standalone `snapshot-review-evidence` rerun command.

### Task 7: Verification

**Commands:**

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_review_evidence_snapshots.py \
  tests/test_daily_data_pipeline.py \
  tests/test_dashboard_readiness.py \
  tests/test_dashboard_app.py -q
```

```bash
/Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli snapshot-review-evidence --help
```

Expected: pytest passes; CLI help exits 0 and lists snapshot options.
