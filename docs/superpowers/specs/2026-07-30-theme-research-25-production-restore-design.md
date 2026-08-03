# Theme Research 25-Theme Production Restore Design

## Objective

Restore Theme Research production from 2 visible themes to the exact 25-theme checkpoint recorded by Git commit `eba5cdfc700a02d961e441cc1b92824ff9e35c7e`.

The checkpoint uses the `theme_decomposition_v1_6` data contract while the current canonical release supports only `v1_5`. The restore therefore includes a minimal backward-compatible application and schema upgrade before the data import. It does not merge the historical integration branch.

Success means:

- the canonical application accepts both v1.5 and v1.6 artifacts;
- the production schema accepts the v1.6 `new_energy_storage` theme type and `catalyst` and `risk` claim types;
- PostgreSQL contains exactly the 25 expected theme IDs;
- the 23 missing themes are inserted;
- the existing `ai_power_value_capture_v1` and `humanoid_robotics_head_to_toe_v1` themes have no semantic updates or deactivations;
- the external Theme Research list reports 25 themes and representative detail pages render nonzero node data;
- production logs contain no new Theme Research HTTP 500 responses after verification begins.

## Evidence Behind the Expanded Scope

The immutable checkpoint contains:

- 25 themes;
- 270 nodes;
- 282 sources;
- 320 claims;
- 248 company mappings;
- 1 `new_energy_storage` theme;
- 24 `catalyst` claims;
- 59 `risk` claims.

Current production has the legacy Theme Research schema digest `1acce2a856b94b6479c7e08623779e230124fc54fb78fba3358e9cfe4cc882ce`, two themes, and constraints that reject the new enum values. Current code rejects the checkpoint at artifact validation with `UNSUPPORTED_ARTIFACT_VERSION`.

The later research-platform code validates the same isolated checkpoint successfully as a 25-theme normalized package. This proves the historical data itself is valid and locates the incompatibility at the current application/schema contract boundary.

## Source of Truth

The data source is only the `artifacts/theme_decomposition` tree at `eba5cdfc`. The historical branch's application code, frontend, unrelated tests, and later 15 themes are excluded.

The compatibility implementation is ported as a minimal patch into the current canonical release. Historical commits are references for behavior, not merge targets:

- `821b00f0`: v1.6 artifact contract and validation;
- `9ad63600`: preserve deep-research metadata through normalized DB parity;
- `a9ef12af` and `3dc6289d`: fail-closed schema drift handling and migration from the known immediate predecessor;
- `61d34878` and `c530777a`: canonical source identity validation required by the finalized checkpoint contract.

Every compatibility behavior is covered by tests ported or rewritten against the current release. No commit is cherry-picked blindly.

## Considered Approaches

### 1. Minimal v1.6 compatibility upgrade, schema migration, then import — selected

Extend the current release to support both artifact versions, preserve the v1.6 research profile in the existing theme metadata JSON, safely widen two PostgreSQL constraints, and import the checkpoint through the existing transactional writer.

This retains all catalyst, risk, and deep-research data without broadening the application release.

### 2. Convert the checkpoint to v1.5

Rejected because it would discard or flatten catalyst claims, risk claims, the new theme type, and the deep-research profile. That would not restore the completed research faithfully.

### 3. Merge the historical integration branch

Rejected because the branch contains tens of thousands of unrelated application, data, and test changes. It would turn a bounded restoration into a high-risk platform release.

## Compatibility Upgrade

### Artifact validation

`theme_decomposition.py` will:

- retain `theme_decomposition_v1_5` as the canonical default;
- accept `theme_decomposition_v1_6` as a supported version;
- accept `new_energy_storage`, `catalyst`, and `risk` values;
- validate the v1.6 `research_profile` fields and references;
- continue validating v1.5 artifacts unchanged.

### Database normalization and read parity

`theme_research_import.py` will store `research_profile` in the existing `artifact_metadata` JSON rather than add a new table. It will calculate stable source hashes and reject duplicate source identities within a theme.

`theme_research_store.py` and `dashboard/theme_research_db.py` will preserve and return this metadata so artifact-to-database comparisons remain lossless.

### Schema migration

`theme_research_db_schema.py` will widen only:

- `research.theme_research_theme.theme_type` to include `new_energy_storage`;
- `research.theme_research_content_claim.claim_type` to include `catalyst` and `risk`.

The migration will:

- acquire a dedicated advisory transaction lock;
- recognize the exact legacy production DDL and catalog digests;
- reject partial or unknown schema drift;
- replace the known legacy unnamed constraints with stable named constraints;
- update the existing schema migration record only after post-migration inspection succeeds.

No table, column, row, or unrelated constraint is removed.

## Release and Migration Sequence

1. Implement the compatibility patch with red-green tests in the isolated worktree.
2. Run Theme Research backend, schema, import, store, and dashboard regression suites.
3. Fast-forward the clean canonical release root and deploy the compatibility application release.
4. Confirm existing two-theme reads still return HTTP 200 before changing the schema.
5. Create and verify a timestamped PostgreSQL backup of the `research` schema.
6. Run schema status with the new code and require it to identify the known legacy contract.
7. Apply the schema migration using the authenticated admin and migration service.
8. Recheck schema status and existing two-theme reads.
9. Extract and stage only the 25-theme checkpoint artifacts.
10. Run the production dry-run gate. If the checkpoint contains newer revisions of the two production themes, construct an additive desired package from the current database package plus only the 23 missing checkpoint themes.
11. Import the guarded additive package through the existing authenticated transactional writer with generation locking and a deterministic idempotency key.
12. Verify database, API, browser, and logs.

## Data Import Gate

The isolated artifact tree is normalized with current upgraded code. The desired write package preserves the current database objects for the two existing themes and adds only theme-scoped objects for the 23 missing checkpoint themes. The gate requires:

- expected theme count equals 25;
- current production theme IDs equal the two known IDs;
- theme inserts equal 23;
- updates equal 0 in every normalized object family;
- deactivations equal 0 in every normalized object family;
- the two original theme versions and content hashes are recorded before execution.

If any gate fails, stop before importing and report the exact semantic difference.

## Production Write

Call the existing `bootstrap_package()` path through the authenticated restore guard with:

- actor role `admin`;
- the freshly read production generation;
- idempotency key `theme-research-25-eba5cdfc-additive-20260731`;
- the validated additive 25-theme package built from the current two-theme package plus the 23 missing checkpoint themes;
- no `replace_theme`.

The writer provides a serializable transaction, advisory locking, generation conflict protection, and change-set/import-run audit records. Identity collisions between existing objects and missing-theme objects are rejected before execution. Checkpoint, database, desired-package, and generation values are bound to the approved preflight. After acquiring the transaction lock and reloading the authoritative database package, the writer requires exactly 23 theme inserts and rejects every update or deactivation before any write.

## Verification

Immediately after the transaction:

1. Reload the production package and assert exactly the expected 25 theme IDs.
2. Assert the original two theme versions and content hashes are unchanged.
3. Confirm the committed import run records 25 themes.
4. Confirm the server-side list returns 25 and at least three newly imported details have nonzero nodes.
5. Verify the authenticated external list displays 25 themes.
6. Open at least one newly imported detail and verify overview and priority content render.
7. Confirm no new Theme Research HTTP 500 or priority-policy-directory errors appear in production logs.

## Rollback

If the schema migration fails, its PostgreSQL transaction rolls back atomically and the data import does not run.

If the data transaction fails, it also rolls back atomically.

If post-commit verification fails, preserve the release ID, schema migration evidence, import/change-set identifiers, and database backup. Restore the database from the verified backup and redeploy the previous application release. Do not perform ad hoc row deletion or constraint editing.

## Scope Boundaries

- Restore exactly 25 themes, not the later 40-theme head.
- Do not merge the historical integration branch.
- Do not change frontend behavior or API contracts.
- Do not modify authentication, user accounts, strategy data, or unrelated research tables.
- Do not package the 25 canonical theme artifacts into the runtime image; stage them only for the controlled import.
- Review the remaining 15 themes separately.
