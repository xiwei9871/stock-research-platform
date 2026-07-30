# Theme Research 25-Theme Production Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore production Theme Research from 2 to the exact 25-theme checkpoint at `eba5cdfc` while proving that the existing two themes are unchanged.

**Architecture:** Extract only the historical artifact tree into an isolated staging directory, validate it with current production code, and use a tested guard script to enforce a 23-insert/zero-update/zero-deactivate semantic diff. Back up the production research schema, execute the existing authenticated transactional import CLI with generation locking, then verify the database, API, browser, and logs.

**Tech Stack:** Python 3.12, PostgreSQL, psycopg, Pytest, Git archive, Docker, SSH, FastAPI, React dashboard.

---

### Task 1: Add a Production Import Guard

**Files:**
- Create: `scripts/theme_research_checkpoint_import_guard.py`
- Create: `tests/test_theme_research_checkpoint_import_guard.py`

- [ ] **Step 1: Write failing unit tests for the semantic-diff gate**

Test a pure `evaluate_restore_gate()` function with:

- expected 25 theme IDs;
- current IDs containing only `ai_power_value_capture_v1` and `humanoid_robotics_head_to_toe_v1`;
- exactly 23 theme inserts;
- empty update and deactivate lists for every family.

Assert the safe case returns `allowed=True`. Add failing cases for a theme update, any deactivation, the wrong current theme set, and the wrong desired theme count.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_theme_research_checkpoint_import_guard.py
```

Expected: collection fails because the guard module does not exist.

- [ ] **Step 3: Implement the guard**

The script must:

- accept `--artifact-dir`, `--company-mapping-dir`, `--expected-theme-ids-file`, and `--runtime-service`;
- normalize and validate the historical package with current code;
- load the current database package read-only;
- call `dry_run_package()`;
- query the current store generation and package hash;
- record current theme versions and content hashes for the two existing themes;
- require exactly 25 expected IDs, exactly the two known current IDs, exactly 23 theme inserts, and no updates or deactivations in any family;
- emit one JSON document containing `allowed`, package counts, semantic-diff summaries, generation, package hashes, and original-theme fingerprints;
- exit nonzero when the gate is not allowed.

The script must never call `bootstrap_package()` and must not accept an execute flag.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the focused test command again and expect all tests to pass.

- [ ] **Step 5: Commit the guard**

Commit with message:

```text
feat: guard 25-theme production restore
```

### Task 2: Build and Validate the Immutable 25-Theme Package

**Files:**
- Create temporarily outside Git: an isolated staging directory from `mktemp -d`.
- Read: Git commit `eba5cdfc700a02d961e441cc1b92824ff9e35c7e`.

- [ ] **Step 1: Extract only the historical artifact tree**

Use `git archive` for `artifacts/theme_decomposition` at the pinned commit and extract it into the temporary staging root. Do not check out or merge the historical branch.

- [ ] **Step 2: Generate the immutable 25-ID manifest**

Derive the root theme IDs from the extracted JSON files, sort them, and write them to a temporary JSON array. Assert the count is exactly 25 and its SHA-256 is recorded in the migration evidence output.

- [ ] **Step 3: Run current artifact and package validators locally**

Use current code from this worktree to call `normalize_artifact_package()` and `validate_package_integrity()` against the extracted theme and company-mapping directories. Print object counts and package SHA-256.

Expected: 25 normalized themes with no integrity error.

- [ ] **Step 4: Run relevant regression tests**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q \
  tests/test_theme_research_checkpoint_import_guard.py \
  tests/test_theme_research_import.py \
  tests/test_theme_research_store.py \
  tests/test_dashboard_theme_research_db.py
```

Expected: all tests pass.

### Task 3: Stage Production Inputs and Create a Database Backup

**Files and remote state:**
- Remote release root: `/home/jqz/code/stock-research-platform-main`.
- Running API container: `stock_research_dashboard-api-1`.
- Remote backup directory: `/home/jqz/backups/theme-research-25-restore-20260730`.
- Container staging directory: `/tmp/theme-research-25-eba5cdfc`.

- [ ] **Step 1: Verify production prerequisites read-only**

Confirm the API container is healthy, the release ID is still the expected production release, both migration and runtime PostgreSQL services are reachable, and the production package still contains exactly the two known themes.

- [ ] **Step 2: Verify backup tooling before changing state**

Check for `pg_dump` on the production host. If it is unavailable, use a pinned PostgreSQL client container on `stock-research-dashboard-release` with the existing read-only-mounted pg service file. Do not proceed until `pg_dump --version` succeeds.

- [ ] **Step 3: Create and verify the backup**

Create a timestamped custom-format dump covering the `research` schema through the migration service. Run `pg_restore --list` against the dump and require entries for `theme_research_theme`, `theme_research_node`, `theme_research_import_run`, and `theme_research_store_state`.

- [ ] **Step 4: Copy the staged package and guard into the API container**

Transfer only the extracted `artifacts/theme_decomposition` tree, the 25-ID manifest, and the guard script to the container staging directory. Confirm the container sees exactly 25 root theme JSON files.

### Task 4: Run the Production Dry-Run Gate

**Files:**
- Write remote evidence: `/home/jqz/backups/theme-research-25-restore-20260730/preflight.json`.

- [ ] **Step 1: Execute the guard inside the API container**

Run the guard with the container's current application code, runtime service, extracted artifact directory, company-mapping directory, and expected-ID manifest. Save its JSON output outside the container.

- [ ] **Step 2: Verify every write gate**

Require:

```text
allowed = true
desired theme count = 25
current theme count = 2
theme inserts = 23
all family updates = 0
all family deactivations = 0
```

Also record the generation and original two theme fingerprints. Stop before production write if any value differs.

- [ ] **Step 3: Re-read production generation immediately before execution**

Require it to equal the generation recorded in `preflight.json`. A mismatch means another writer changed the store; rerun the complete dry-run gate.

### Task 5: Execute the Transactional Import

**Files and state:**
- Use the existing `theme-research-db import --execute` CLI.
- Use idempotency key `theme-research-25-eba5cdfc-20260730`.

- [ ] **Step 1: Confirm the admin credential environment is available without printing it**

Inside the API container, require the configured admin password environment variable to be nonempty. Do not display its value.

- [ ] **Step 2: Execute the authenticated import**

Run the current CLI with:

- `--runtime-service` set to the migration-capable Theme Research service;
- `--artifact-dir` and `--company-mapping-dir` pointing to the staged checkpoint;
- `--expected-generation` from the preflight evidence;
- `--admin-username admin`;
- the deterministic idempotency key;
- `--execute` and no `--replace-theme`.

Save the JSON result to the remote evidence directory. Require `status=committed`, `resulting_generation=previous+1`, and object counts containing 25 themes.

- [ ] **Step 3: Preserve import audit identifiers**

Record the returned change-set ID, import-run ID, package SHA-256, prior generation, resulting generation, and backup path in a migration summary JSON file.

### Task 6: Verify Database and External Behavior

**Files:**
- Write remote evidence: `/home/jqz/backups/theme-research-25-restore-20260730/postflight.json`.

- [ ] **Step 1: Verify the database package**

Reload the database package and assert exactly the expected 25 theme IDs. Compare the original two theme versions and content hashes with `preflight.json` and require exact equality.

- [ ] **Step 2: Verify server-side read models**

Inside the production API container, call the Theme Research list builder and representative new-theme detail builders. Require list total 25 and nonzero node counts for at least three newly imported themes.

- [ ] **Step 3: Verify the authenticated external browser**

Reload `/theme-research`, require the visible total to be 25, open at least one newly imported theme, and confirm its overview and priority-node content render without a loading-failure panel or console errors.

- [ ] **Step 4: Verify production logs**

From the verification start timestamp onward, require Theme Research list and detail requests to return HTTP 200 and no HTTP 500 or `PRIORITY_POLICY_DIRECTORY_NOT_FOUND` entries.

- [ ] **Step 5: Run final repository checks**

Run `rtk git diff --check`, confirm the worktree is clean, and confirm the production application release ID was not changed by this data-only migration.

### Task 7: Commit Operational Evidence Documentation

**Files:**
- Create: `docs/ops/theme-research-25-production-restore-20260730.md`

- [ ] **Step 1: Record non-secret migration evidence**

Document the pinned checkpoint, 25-ID manifest digest, package digest, backup path, dry-run counts, import/change-set identifiers, generations, final theme count, representative detail checks, and log verification. Do not include passwords, connection strings, cookies, or tokens.

- [ ] **Step 2: Commit the evidence**

Commit with message:

```text
docs: record 25-theme production restore
```

- [ ] **Step 3: Review completion requirement by requirement**

Re-read the design and this plan, map each requirement to fresh evidence, and only then report the migration complete.
