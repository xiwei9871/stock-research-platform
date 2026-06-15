# Review Evidence Snapshot v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist Review Queue item and Evidence Digest snapshots, expose snapshot query APIs, and surface operator decision snapshot linkage.

**Architecture:** Add two `ops` tables and a focused `review_evidence_snapshots.py` service. Dashboard APIs remain read-only. Operator decision linkage is parsed from existing `source_context` JSON where present, avoiding a decision ingestion rewrite.

**Tech Stack:** Python 3.14, psycopg/PostgreSQL SQL strings, FastAPI, pytest, TypeScript API types, Vitest, Vite build.

---

### Task 1: Snapshot Schema And Hash Helpers

**Files:**
- Modify: `src/stock_research/schema.py`
- Create: `src/stock_research/review_evidence_snapshots.py`
- Create: `tests/test_review_evidence_snapshots.py`
- Modify: `tests/test_schema.py`

- [ ] **Step 1: Write failing tests**

Add tests asserting schema DDL contains `ops.review_item_snapshot`, `ops.evidence_digest_snapshot`, unique indexes, and that `canonical_payload_hash({"b": 2, "a": 1})` equals the hash for `{"a": 1, "b": 2}`.

- [ ] **Step 2: Run red tests**

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_review_evidence_snapshots.py tests/test_schema.py -k "snapshot" -q
```

Expected: fail because module/tables do not exist.

- [ ] **Step 3: Implement schema and helpers**

Add `CREATE_REVIEW_EVIDENCE_SNAPSHOT_SQL`, `apply_review_evidence_snapshot_schema`, `canonical_payload_hash`, `build_review_item_snapshot`, and `build_evidence_digest_snapshot`.

- [ ] **Step 4: Run green tests**

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_review_evidence_snapshots.py tests/test_schema.py -k "snapshot" -q
```

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/schema.py src/stock_research/review_evidence_snapshots.py tests/test_review_evidence_snapshots.py tests/test_schema.py
git commit -m "feat: add review evidence snapshot schema"
```

### Task 2: Snapshot Insert And Query Service

**Files:**
- Modify: `src/stock_research/review_evidence_snapshots.py`
- Modify: `tests/test_review_evidence_snapshots.py`

- [ ] **Step 1: Write failing tests**

Add tests for `upsert_review_item_snapshot`, `upsert_evidence_digest_snapshot`, `snapshot_review_queue_payload`, `list_review_item_snapshots`, `list_evidence_digest_snapshots`, and `load_evidence_digest_snapshot`.

- [ ] **Step 2: Run red tests**

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_review_evidence_snapshots.py -q
```

- [ ] **Step 3: Implement service SQL**

Use JSONB payload columns, upsert on `(run_id, digest_key)`, and filter queries by optional `run_id`, `trade_date`, `asset_id`, and `digest_key`.

- [ ] **Step 4: Run green tests**

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_review_evidence_snapshots.py -q
```

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/review_evidence_snapshots.py tests/test_review_evidence_snapshots.py
git commit -m "feat: persist review evidence snapshots"
```

### Task 3: Snapshot APIs And Decision Linkage

**Files:**
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `src/stock_research/dashboard/decisions.py`
- Modify: `tests/test_dashboard_app.py`
- Modify: `tests/test_dashboard_decisions.py`

- [ ] **Step 1: Write failing tests**

Add tests for `/api/review-queue/snapshots`, `/api/evidence-digest/snapshots`, `/api/evidence-digest/snapshots/{snapshot_id}`, parsed decision linkage, and missing linkage warnings.

- [ ] **Step 2: Run red tests**

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_app.py tests/test_dashboard_decisions.py -q
```

- [ ] **Step 3: Implement APIs and linkage parser**

Import snapshot list/detail helpers into `dashboard/app.py`. In `decisions.py`, parse JSON `source_context` into linkage fields without failing plain text contexts.

- [ ] **Step 4: Run green tests**

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_app.py tests/test_dashboard_decisions.py -q
```

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/app.py src/stock_research/dashboard/decisions.py tests/test_dashboard_app.py tests/test_dashboard_decisions.py
git commit -m "feat: expose snapshot APIs and decision linkage"
```

### Task 4: Frontend Type Compatibility

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/tests/client.test.ts`

- [ ] **Step 1: Write failing client tests**

Add client tests for fetching review snapshots and evidence digest snapshots.

- [ ] **Step 2: Run red tests/build**

```bash
cd dashboard && pnpm exec vitest run --exclude "**/*.spec.ts" tests/client.test.ts
cd dashboard && pnpm build
```

- [ ] **Step 3: Implement client/types**

Add snapshot response types and fetch helpers only. Do not alter components.

- [ ] **Step 4: Run green tests/build**

```bash
cd dashboard && pnpm exec vitest run --exclude "**/*.spec.ts" tests/client.test.ts
cd dashboard && pnpm build
```

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/tests/client.test.ts
git commit -m "feat: add snapshot api client types"
```

### Task 5: Final Verification

**Files:**
- No production edits unless focused verification finds a Batch C regression.

- [ ] **Step 1: Backend focused verification**

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_review_evidence_snapshots.py \
  tests/test_dashboard_review_queue.py \
  tests/test_dashboard_evidence_digest.py \
  tests/test_dashboard_decisions.py \
  tests/test_dashboard_app.py \
  tests/test_dashboard_readiness.py -q
```

- [ ] **Step 2: Frontend focused verification**

```bash
cd dashboard && pnpm exec vitest run --exclude "**/*.spec.ts" tests/client.test.ts
cd dashboard && pnpm build
```

- [ ] **Step 3: Optional platform smoke**

```bash
cd dashboard && pnpm exec playwright test tests/platform-full-flow.spec.ts
```
