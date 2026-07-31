# Theme Research 25-Theme Production Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the minimum backward-compatible v1.6 Theme Research contract, safely migrate the known production schema, and restore the exact 25-theme checkpoint at `eba5cdfc` without changing the existing two themes.

**Architecture:** Port only the v1.6 artifact, normalization, DB parity, and known-legacy schema-migration behaviors into the current canonical release. Deploy and migrate the schema before importing the isolated checkpoint through a tested 23-insert/zero-update/zero-deactivate gate.

**Tech Stack:** Python 3.12, PostgreSQL, psycopg, Pytest, Git archive, Docker Compose, SSH, FastAPI, React dashboard.

---

### Task 1: Preserve the Existing Read-Only Import Guard

**Files:**
- Existing: `scripts/theme_research_checkpoint_import_guard.py`
- Existing: `tests/test_theme_research_checkpoint_import_guard.py`

- [x] Write gate tests for exactly 25 desired themes, exactly two current themes, 23 theme inserts, and zero updates/deactivations.
- [x] Verify RED before the script existed.
- [x] Implement a read-only-by-default guard; permit `bootstrap_package()` only behind explicit authenticated `--execute` after the additive gate passes.
- [x] Verify all five gate tests pass.
- [x] Commit as `feat: guard 25-theme production restore`.

### Task 2: Accept and Validate the v1.6 Artifact Contract

**Files:**
- Modify: `src/stock_research/theme_decomposition.py`
- Modify: `tests/test_theme_decomposition.py`

- [x] **Step 1: Add failing v1.6 contract tests**

Add tests proving:

```python
assert "theme_decomposition_v1_6" in SUPPORTED_ARTIFACT_VERSIONS
assert "new_energy_storage" in THEME_TYPES
assert {"catalyst", "risk"} <= CLAIM_TYPES
```

Add a minimal v1.6 artifact with a complete `research_profile` and assert it validates. Add negative cases for a missing research-profile field and a catalyst/risk claim reference that does not exist.

- [x] **Step 2: Run focused tests and verify RED**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_theme_decomposition.py -k 'v1_6 or research_profile'
```

Expected: failure because the current validator rejects v1.6 and lacks research-profile validation.

- [x] **Step 3: Implement the minimal validator changes**

Keep `ARTIFACT_VERSION = "theme_decomposition_v1_5"` and add:

```python
SUPPORTED_ARTIFACT_VERSIONS = {
    ARTIFACT_VERSION,
    "theme_decomposition_v1_6",
}
```

Accept `new_energy_storage`, `catalyst`, and `risk`; expose `research_profiles` from `load_theme_package()`; validate nonempty profile strings, string-list fields, `research_kind == "industry_chain_deep_research"`, and catalyst/risk claim references.

- [x] **Step 4: Run focused and complete decomposition tests**

Require the focused tests and all of `tests/test_theme_decomposition.py` to pass.

- [x] **Step 5: Commit**

Commit with message `feat: support theme research artifact v1.6`.

### Task 3: Preserve v1.6 Metadata Through Database Parity

**Files:**
- Modify: `src/stock_research/theme_research_import.py`
- Modify: `src/stock_research/theme_research_store.py`
- Modify: `src/stock_research/dashboard/theme_research_db.py`
- Modify: `tests/test_theme_research_import.py`
- Modify: `tests/test_theme_research_store.py`
- Modify: `tests/test_dashboard_theme_research_db.py`

- [x] **Step 1: Add failing parity tests**

Assert normalization stores:

```python
theme["artifact_metadata"]["research_profile"] == artifact["research_profile"]
```

Assert store snapshot/export and DB dashboard reconstruction retain the same value. Add source-identity tests proving URLs differing only by case, fragment, or trailing slash are treated canonically and duplicate identities fail closed.

- [x] **Step 2: Run the three focused test files and verify RED**

Run the import, store, and dashboard DB test files. Expected failures must reference missing research-profile parity or source identity behavior.

- [x] **Step 3: Implement normalization and parity**

Add `research_profile` to theme `artifact_metadata`; compute source content hashes without provenance; compare duplicate source rows without notes/content hash; normalize source URLs before detecting duplicate identities; preserve `research_profile` in store artifact reconstruction and dashboard DB context.

- [x] **Step 4: Run focused tests and verify GREEN**

Require all import, store, and dashboard DB tests to pass.

- [x] **Step 5: Commit**

Commit with message `fix: preserve v1.6 theme research parity`.

### Task 4: Migrate the Known Legacy Theme Research Schema

**Files:**
- Modify: `src/stock_research/theme_research_db_schema.py`
- Modify: `tests/test_theme_research_db_schema.py`
- Modify: `tests/integration/test_theme_research_db_schema_postgres.py`

- [x] **Step 1: Add failing schema-contract tests**

Require named constraints containing:

```text
ck_theme_research_theme_type: new_energy_storage
ck_theme_research_claim_type: catalyst, risk
```

Test that the exact production legacy DDL/catalog contract is accepted as a migration predecessor, while partial or unknown drift is rejected. Test that migration acquires a dedicated advisory lock and updates the migration record only after post-inspection succeeds.

- [x] **Step 2: Run unit schema tests and verify RED**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_theme_research_db_schema.py
```

- [x] **Step 3: Implement the schema migration**

Widen only the two enum checks. Introduce a `LegacyThemeResearchSchemaContract` for the production digest `1acce2a856b94b6479c7e08623779e230124fc54fb78fba3358e9cfe4cc882ce` and its catalog digest. Acquire `THEME_RESEARCH_SCHEMA_MIGRATION_LOCK_KEY`, reject unknown drift, apply DDL transactionally, re-inspect, then update the migration row.

- [x] **Step 4: Run unit and configured PostgreSQL integration tests**

Run the schema unit suite. If the configured integration database is available, run the dedicated PostgreSQL schema migration file and require pass; otherwise record the explicit skip reason and rely on the production dry-run/status gate before apply.

- [x] **Step 5: Commit**

Commit with message `fix: migrate theme research schema for v1.6`.

### Task 5: Validate the 25-Theme Release Candidate

**Files:**
- Read: checkpoint `eba5cdfc700a02d961e441cc1b92824ff9e35c7e`.
- Use temporary staging directory `/tmp/theme-research-25-eba5cdfc.*`.

- [x] Extract only `artifacts/theme_decomposition` with `git archive`.
- [x] Generate and hash the exact 25-theme ID manifest.
- [x] Normalize and validate the isolated checkpoint with the upgraded current code.
- [x] Require counts of 25 themes, 270 nodes, 282 sources, 320 claims, and 248 company mappings.
- [x] Run all Theme Research backend tests, the complete dashboard frontend suite, and production frontend build.
- [x] Run `rtk git diff --check` and review the compatibility diff against the design.

### Task 6: Publish the Compatibility Release

**Files and state:**
- Canonical release root: `/Users/xiwei/stock_research_release_20260727`.
- Production URL: `https://stock.manqiaotechnology.com`.

- [x] Fast-forward the clean canonical release root to the verified compatibility commit.
- [x] Publish through `deploy/sync_dashboard_release.sh` with expected trade date `2026-07-29`.
- [x] Confirm external `release.json` matches the new commit.
- [x] Before schema changes, require the existing two-theme list and one detail to return HTTP 200.

### Task 7: Back Up and Migrate the Production Schema

**Remote state:**
- Backup directory: `/home/jqz/backups/theme-research-25-restore-20260731`.
- API container: `stock_research_dashboard-api-1`.

- [x] Verify `pg_dump` and `pg_restore` tooling without printing credentials.
- [x] Create a timestamped custom-format backup of the production `research` schema through the migration service.
- [x] Require `pg_restore --list` entries for Theme Research theme, node, import-run, and store-state tables.
- [x] Run the new schema status and require recognition of the known legacy contract.
- [x] Apply the schema through the authenticated admin CLI.
- [x] Require current schema status and verify the existing two-theme reads remain HTTP 200.

### Task 8: Run the Production Import Gate and Transaction

**Remote staging:**
- Container directory: `/tmp/theme-research-25-eba5cdfc`.
- Evidence directory: `/home/jqz/backups/theme-research-25-restore-20260731`.
- Idempotency key: `theme-research-25-eba5cdfc-additive-20260731`.

- [x] Copy only the checkpoint artifact tree, 25-ID manifest, and read-only guard into container staging.
- [x] Run the guard and save preflight evidence outside the container.
- [x] When the raw checkpoint updates the existing two themes, build the additive desired package from current production plus only the 23 missing themes.
- [x] Require 25 desired themes, two current themes, 23 theme inserts, zero updates, and zero deactivations in every family.
- [x] Re-read and match the generation immediately before execution.
- [x] Confirm the admin credential is available without displaying it.
- [x] Execute the authenticated transactional import with the recorded generation and deterministic idempotency key.
- [x] Bind checkpoint/database/desired hashes to preflight and enforce the zero-update/zero-deactivate gate again on the authoritative diff inside the locked transaction.
- [x] Save import/change-set IDs, package SHA, generations, counts, and backup path in migration evidence.

### Task 9: Verify Production and Record Evidence

**Files:**
- Create: `docs/ops/theme-research-25-production-restore-20260731.md`

- [x] Reload the DB package and require the exact 25-theme ID set.
- [x] Require the original two theme versions and content hashes to match preflight evidence.
- [x] Require server-side list total 25 and nonzero nodes on at least three new details.
- [x] Reload the authenticated external list, verify visible total 25, and open a newly imported detail without console errors.
- [x] Require Theme Research list/detail HTTP 200 and no new HTTP 500 or priority-policy-directory errors in production logs.
- [x] Confirm the release root and feature worktree are clean and `git diff --check` passes.
- [x] Record non-secret backup, release, schema, dry-run, import, count, browser, and log evidence in the operations document.
- [x] Commit with message `docs: record 25-theme production restore`.
- [x] Re-read the design and plan requirement by requirement before reporting completion.
