# Operator Decision Snapshot Linkage v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically attach Review Queue and Evidence Digest snapshot IDs and hashes to imported operator decision events.

**Architecture:** Add a focused resolver module under `operator_decision`, call it from the existing decision journal import row builder, and extend dashboard decision parsing to expose hashes and warnings from `source_context`.

**Tech Stack:** Python, PostgreSQL helper functions, JSON source_context, pytest.

---

### Task 1: Linkage Resolver

**Files:**
- Create: `src/stock_research/operator_decision/snapshot_linkage.py`
- Test: `tests/test_operator_decision_snapshot_linkage.py`

- [ ] Write failing tests for explicit snapshot IDs, `run_id + digest_key`, `run_id + asset_id`, missing snapshots, and source_context merge preservation.
- [ ] Implement `resolve_decision_snapshot_linkage(context, service=...)`.
- [ ] Use `list_review_item_snapshots`, `list_evidence_digest_snapshots`, and `load_evidence_digest_snapshot` where possible.
- [ ] Add a small helper to load review snapshot by ID because Batch C currently has a detail loader only for evidence digest snapshots.
- [ ] Return a JSON-serializable dict with status, warnings, IDs, hashes, digest key, run ID, and as-of timestamps.

### Task 2: Decision Import Integration

**Files:**
- Modify: `src/stock_research/operator_decision/read_model.py`
- Test: `tests/test_operator_decision_read_model.py`

- [ ] Write a failing import test where source_context has `run_id + digest_key` and the persisted event source_context is enriched.
- [ ] Write a failing test where snapshots are missing and import still succeeds with missing warnings.
- [ ] Call the resolver in `_event_row`.
- [ ] Merge linkage JSON into `source_context`.
- [ ] Preserve plain string source_context as `source_context_label`.

### Task 3: Dashboard Read Model

**Files:**
- Modify: `src/stock_research/dashboard/decisions.py`
- Test: `tests/test_dashboard_decisions.py`

- [ ] Extend `_snapshot_linkage` to expose `review_item_payload_hash` and `evidence_digest_payload_hash`.
- [ ] Prefer `snapshot_linkage_status` and `snapshot_linkage_warnings` from JSON when present.
- [ ] Keep plain-text source_context compatible and missing.

### Task 4: API Shape

**Files:**
- Test: `tests/test_dashboard_app.py`
- Modify: `dashboard/src/api/types.ts` only if frontend type gaps appear.

- [ ] Add or update dashboard app test to assert decision payload includes linkage hashes.
- [ ] Avoid frontend edits unless TypeScript tests fail.

### Task 5: Runbook

**Files:**
- Modify: `docs/dashboard-local-runbook.md`

- [ ] Add a short decision linkage smoke section.

### Task 6: Verification

**Commands:**

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_operator_decision_snapshot_linkage.py \
  tests/test_operator_decision_read_model.py \
  tests/test_dashboard_decisions.py \
  tests/test_dashboard_app.py \
  tests/test_review_evidence_snapshots.py \
  tests/test_daily_data_pipeline.py \
  tests/test_dashboard_readiness.py -q
```

Expected: all tests pass. Frontend build is not required unless frontend files are touched.
