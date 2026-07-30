# Theme Research 25-Theme Production Restore Design

## Objective

Restore the Theme Research production database from 2 visible themes to the exact 25-theme checkpoint recorded by Git commit `eba5cdfc700a02d961e441cc1b92824ff9e35c7e`, without merging the historical integration branch into the current application release and without overwriting the two themes already serving production.

Success means:

- PostgreSQL contains exactly the 25 theme IDs present at `eba5cdfc`.
- The 23 missing themes are inserted.
- The existing `ai_power_value_capture_v1` and `humanoid_robotics_head_to_toe_v1` themes have no object updates or deactivations.
- The external Theme Research list reports 25 themes and representative detail pages render nonzero node data.
- Production logs contain no new Theme Research HTTP 500 responses after verification begins.

## Source of Truth

The immutable data source is the `artifacts/theme_decomposition` tree at commit `eba5cdfc700a02d961e441cc1b92824ff9e35c7e`. That commit is the exact point where the historical research branch first reached 25 root theme artifacts.

Current application code, schema, validators, and database writers remain those from the canonical production release. Historical application code from the integration branch is not merged or deployed.

## Considered Approaches

### 1. Extract the 25-theme artifact tree and import it with current code — selected

Materialize the historical artifact directory into an isolated staging directory, validate it using current loaders and integrity checks, compare it with production using `dry_run_package()`, then write it through the existing transactional package import path.

This preserves a precise data boundary and avoids bringing unrelated historical code into production.

### 2. Merge the historical integration branch

Rejected because the branch contains tens of thousands of unrelated code and test changes. Merging it would turn a bounded data restoration into a broad application release.

### 3. Insert missing theme rows directly with SQL

Rejected because direct SQL would bypass package integrity validation, relationship ordering, snapshots, revisions, generation locking, and the existing audit trail.

## Staging and Validation Flow

1. Use `git archive` against the pinned commit to extract only `artifacts/theme_decomposition` into a temporary directory outside the release tree.
2. Normalize the extracted theme and company-mapping artifacts with the current `normalize_artifact_package()` implementation.
3. Run current artifact validation and package integrity validation.
4. Assert the normalized package has exactly 25 themes and the exact expected theme ID set.
5. Load the current production database package read-only and assert it contains exactly the two known theme IDs.
6. Run `dry_run_package()` against production.
7. Calculate insert, update, and deactivate totals for every object family.

The production write gate requires all of the following:

- theme inserts equal 23;
- theme updates equal 0;
- theme deactivations equal 0;
- every object-family deactivation count equals 0;
- the two existing themes have no insert or update entries in their scoped semantic diffs;
- package validation reports no errors.

If any gate fails, stop before writing and report the exact semantic difference.

## Production Write

Before the import, create a timestamped PostgreSQL backup of the Theme Research research schema on the production host and record the current store generation and package hash.

Call the existing transactional `bootstrap_package()` writer with:

- actor role `admin`;
- a migration-specific actor identifier;
- the freshly read production generation;
- a deterministic idempotency key containing the checkpoint and date;
- the fully validated 25-theme normalized package;
- no `replace_theme`, so absent production objects are not deactivated.

The writer provides a serializable transaction, advisory locking, generation conflict protection, change-set and import-run audit records, relationship replacement for changed themes, and snapshots for changed existing themes. The preflight gate is designed so only the 23 absent themes are changed.

## Verification

Immediately after the transaction:

1. Reload the production package and assert exactly 25 themes and the expected ID set.
2. Assert the original two theme payload hashes and versions are unchanged.
3. Confirm the import run is committed and records 25 themes.
4. Call the production Theme Research list and representative detail builders inside the API container.
5. Verify the authenticated external list renders 25 themes.
6. Open representative newly imported detail pages and verify node counts are nonzero.
7. Confirm no new `PRIORITY_POLICY_DIRECTORY_NOT_FOUND` or Theme Research HTTP 500 entries appear in production logs.

## Rollback

If the transaction itself fails, PostgreSQL rolls it back atomically.

If post-commit verification fails, stop external verification, preserve the import/change-set identifiers, and restore from the timestamped database backup. Do not attempt ad hoc row deletion. After restoration, recheck the two original themes and application health before reporting the rollback complete.

## Scope Boundaries

- This restores exactly 25 themes, not the later 40-theme research head.
- It does not deploy historical application code.
- It does not change frontend behavior or API contracts.
- It does not modify authentication, user accounts, strategy data, or unrelated research tables.
- The remaining 15 later themes require a separate review and production admission decision.
