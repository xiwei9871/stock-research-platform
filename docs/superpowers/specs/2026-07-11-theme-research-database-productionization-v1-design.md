# Theme Research Database Productionization v1 Design

## Purpose

Phase 9 moves Theme-driven Research Engine from artifact-first operation to a production PostgreSQL store without weakening the source, claim, node, review, and promotion gates established in Phases 1-8.

The target ownership model is:

```text
validated Phase 1-8 artifacts
  -> dry-run import and semantic diff
  -> administrator-confirmed bootstrap transaction
  -> PostgreSQL authoritative store
  -> authenticated review and state transitions
  -> immutable snapshots and JSON exports
```

After cutover, PostgreSQL is the only authoritative write store. JSON artifacts remain bootstrap inputs, immutable exports, rollback snapshots, and comparison fixtures. The platform does not maintain indefinite dual writes.

## Boundaries

Phase 9 includes:

- normalized PostgreSQL tables for the Phase 1-8 research model;
- schema versioning and repeatable migration commands;
- validated, idempotent artifact bootstrap/import;
- object and state-transition history;
- evidence provenance;
- authenticated human review decisions;
- immutable snapshots, JSON export, and rollback-as-new-version;
- DB-backed read models and controlled write APIs;
- artifact/DB comparison and staged read cutover;
- production and regression tests.

Phase 9 does not include:

- automatic recommendations or trading signals;
- autonomous AI review approval;
- Daily Review or Watchlist workflow integration, which remains Phase 10;
- remote crawling or scheduled source acquisition;
- automatic company admission;
- destructive history deletion;
- long-term artifact/DB dual writes.

The following guardrails remain invariant:

```text
research_only = true
used_for_signal = false
used_for_admission = false
```

## Architecture

Phase 9 introduces four focused modules:

1. `theme_research_db_schema.py`
   Owns PostgreSQL DDL, schema version, constraints, indexes, and the apply command.
2. `theme_research_store.py`
   Owns transactional reads, optimistic writes, revisions, review events, snapshots, exports, and rollback.
3. `theme_research_import.py`
   Owns validated artifact loading, semantic diff, idempotent bootstrap, and parity audits.
4. `dashboard/theme_research_db.py`
   Owns DB-backed dashboard read models and controlled review/administration operations.

The existing artifact loaders remain independent validators. They do not import the DB layer, which prevents circular ownership and preserves offline validation.

## Database Schema

All tables live in the existing `research` schema and use the prefix `theme_research_` to avoid ambiguity with the generic research-object subsystem.

### Schema and transaction metadata

`research.theme_research_schema_migration`

- `schema_version` text primary key;
- `applied_at` timestamptz;
- `applied_by` text;
- `ddl_sha256` text;
- `metadata` jsonb.

`research.theme_research_change_set`

- `change_set_id` text primary key;
- `change_type`: bootstrap_import / review_transition / admin_update / rollback / export;
- `theme_id` nullable;
- `actor_user_id`;
- `actor_role`;
- `request_id`;
- `idempotency_key`;
- `expected_theme_version` nullable;
- `resulting_theme_version` nullable;
- `status`: prepared / committed / failed;
- `created_at`, `committed_at`;
- `metadata` jsonb;
- unique `(actor_user_id, idempotency_key)` where the idempotency key is non-empty.

### Canonical research objects

`research.theme_research_theme`

- canonical Phase 1 theme fields;
- `theme_version` bigint, starting at 1;
- `row_version` bigint;
- `content_sha256`;
- `created_at`, `updated_at`, `created_by`, `updated_by`;
- check constraints for type, status, and origin.

`research.theme_research_node`

- canonical Phase 1 node fields;
- `key_metrics`, `overseas_leaders`, `domestic_players`, `related_stock_codes` as jsonb arrays;
- foreign keys to theme and parent node;
- score checks from 0 through 5;
- review-status checks;
- `row_version`, audit columns, and `is_active`.

`research.theme_research_source_item`

- canonical source fields;
- source/access/reliability/review checks;
- `content_sha256`, provenance jsonb, `row_version`, audit columns, and `is_active`;
- database check that S4 cannot be accepted.

`research.theme_research_theme_source`

- explicit many-to-many theme/source ownership;
- `link_reason`: primary_claim / supporting_claim / assessment / company_mapping / manual;
- primary key `(theme_id, source_id, link_reason)`.

`research.theme_research_content_claim`

- canonical claim fields excluding array relationships;
- foreign keys to theme and primary source;
- claim/evidence/platform-use checks;
- confidence check from 0 through 1;
- `row_version`, audit columns, and `is_active`.

`research.theme_research_claim_source`

- supporting-source relationship;
- primary key `(claim_id, source_id)`.

`research.theme_research_claim_node`

- affected-node relationship;
- primary key `(claim_id, node_id)`.

`research.theme_research_value_assessment`

- assessment ID, node ID, value basis, text, rank, uncertainty;
- `row_version`, audit columns, and `is_active`.

`research.theme_research_assessment_evidence`

- assessment ID;
- evidence type: source / claim;
- evidence ID;
- primary key `(assessment_id, evidence_type, evidence_id)`.

`research.theme_research_company_mapping`

- the complete Phase 4 mapping contract;
- company identity, node relationship, mapping type, confidence, materiality, review status, and notes;
- jsonb fields only for established flexible dimensions;
- foreign keys to theme and node;
- `row_version`, audit columns, and `is_active`.

`research.theme_research_company_mapping_evidence`

- mapping ID and evidence ID;
- evidence type: source / claim / mapping_evidence_item;
- primary key `(mapping_id, evidence_type, evidence_id)`.

### Review and history

`research.theme_research_review_event`

- `review_event_id` primary key;
- `change_set_id` foreign key;
- `theme_id`, `object_type`, `object_id`;
- `from_status`, `to_status`, `decision`;
- `reviewer_user_id`, `reviewer_role`, `comment`;
- `request_id`, `idempotency_key`;
- `created_at`;
- immutable payload jsonb;
- no update/delete application path.

`research.theme_research_object_revision`

- `revision_id` primary key;
- `change_set_id` foreign key;
- `theme_id`, `object_type`, `object_id`;
- `object_version`;
- `operation`: insert / update / deactivate / restore;
- `before_payload`, `after_payload` jsonb;
- `actor_user_id`, `created_at`;
- unique `(object_type, object_id, object_version)`.

### Imports, snapshots, and exports

`research.theme_research_import_run`

- import-run ID, artifact/schema versions, package SHA-256;
- mode: dry_run / bootstrap / reconcile;
- status and object counts;
- semantic diff jsonb;
- actor, timestamps, and error fields;
- unique successful package SHA-256 per import mode.

`research.theme_research_snapshot`

- snapshot ID primary key;
- theme ID, theme version, snapshot type: import / pre_change / post_change / export / rollback;
- canonical `theme_decomposition_v1_5` compatible payload jsonb;
- payload SHA-256;
- source change-set ID;
- actor and timestamp;
- immutable after insert.

## Database Constraints And Triggers

Application validation remains the first line of defense, but the DB independently enforces critical invariants:

- enum-like check constraints for all canonical statuses and types;
- numeric score and confidence bounds;
- S4 source cannot be accepted;
- reviewed claim must reference at least one accepted non-S4 source, enforced through a deferred constraint trigger;
- reviewed node requires `evidence_strength >= 3`;
- claim-node links must stay within the same theme;
- company mapping node must belong to the mapping theme;
- active child rows cannot reference inactive parents;
- canonical tables reject direct version decreases;
- review events, revisions, snapshots, and committed change sets are append-only through privilege and application boundaries.

## Artifact Bootstrap And Import

The importer loads and validates:

- canonical theme artifacts through `load_theme_package()`;
- Phase 4 company mappings through the existing mapping loader;
- the Phase 5 crosswalk and Phase 6 priority packages only for parity metadata, not canonical writes;
- artifact and file SHA-256 values.

Import has two explicit stages.

### Dry run

```text
load and validate artifacts
-> normalize relational rows
-> read current DB state
-> calculate insert/update/deactivate/no-change diff
-> validate future state in memory
-> persist import_run dry-run report only when requested
```

### Execute

```text
administrator confirmation
-> SERIALIZABLE transaction
-> PostgreSQL advisory package lock
-> expected DB generation check
-> pre-change snapshots
-> canonical upserts and relationship replacement
-> revision rows
-> post-change snapshots
-> import-run and change-set commit
```

Bootstrap is idempotent by package SHA-256 and semantic row identity. Re-importing the same package produces no canonical changes. Missing rows are never deleted implicitly. An explicit `--replace-theme` mode marks absent rows inactive and records revisions.

## Authority And Read Cutover

Read source is controlled by one setting:

```text
THEME_RESEARCH_READ_SOURCE=artifact | compare | db
```

- `artifact`: current Phase 7 behavior; used before bootstrap.
- `compare`: serves artifact output but builds the DB output and records/returns parity diagnostics to administrators.
- `db`: serves the DB read model and treats artifact mismatches as audit findings.

Cutover requires:

- successful bootstrap;
- zero semantic differences for themes, nodes, sources, claims, assessments, and company mappings;
- successful API contract tests against artifact and DB providers;
- one explicit administrator command to change the deployed setting.

There is no normal dual-write path. DB changes produce snapshots and exports; they do not mutate checked-in source artifacts.

## Controlled Writes And State Transitions

Phase 9 exposes controlled writes for human review only. General object editing remains an administrator operation through CLI/service methods in v1.

Allowed source transitions:

```text
unknown -> needs_full_text | lead_only | rejected
needs_full_text -> accepted | lead_only | rejected
lead_only -> needs_full_text | rejected
accepted -> needs_full_text | rejected
rejected -> needs_full_text
```

S4 can never transition to accepted.

Allowed claim transitions:

```text
research_lead -> draft | blocked
draft -> research_lead | reviewed | blocked
reviewed -> draft | blocked
blocked -> research_lead | draft
```

Transition to reviewed requires an accepted non-S4 source. Node transitions follow the existing evidence-strength gate.

Every write requires:

- authenticated active dashboard user;
- CSRF validation for browser requests;
- non-empty comment;
- idempotency key;
- expected theme/object row version;
- request ID;
- a single committed change set containing the canonical update, review event, revision, and snapshots.

Ordinary `user` accounts may submit source, claim, and node review transitions. Only `admin` may apply schema, import, reconcile, deactivate, rollback, or export authoritative packages.

## APIs And CLI

Existing GET routes keep their contract and switch providers through `THEME_RESEARCH_READ_SOURCE`.

Controlled APIs:

```text
POST /api/research/theme-decomposition/sources/:source_id/review
POST /api/research/theme-decomposition/claims/:claim_id/review
POST /api/research/theme-decomposition/nodes/:node_id/review
GET  /api/research/theme-decomposition/themes/:theme_id/history
GET  /api/research/theme-decomposition/themes/:theme_id/snapshots
POST /api/research/theme-decomposition/themes/:theme_id/rollback   # admin
```

CLI:

```text
stock-research theme-research-db apply-schema
stock-research theme-research-db schema-status
stock-research theme-research-db import --dry-run
stock-research theme-research-db import --execute --expected-generation ...
stock-research theme-research-db compare
stock-research theme-research-db export --theme ...
stock-research theme-research-db rollback --theme ... --snapshot ...
stock-research theme-research-db audit
```

All commands emit structured JSON and stable error codes.

## Snapshot And Rollback Semantics

Rollback never rewrites or deletes history. It is a new administrator change set:

1. load and validate the selected immutable snapshot;
2. verify expected current theme version;
3. calculate a semantic reverse diff;
4. create a pre-rollback snapshot;
5. restore canonical rows and relationships in one transaction;
6. write object revisions with operation `restore`;
7. increment the theme version;
8. create a post-rollback snapshot and rollback review event.

The resulting state is exportable as a valid artifact package and remains traceable to both the original and rollback change sets.

## Error Handling And Concurrency

- all writes use explicit transactions;
- bootstrap, reconcile, and rollback use SERIALIZABLE isolation plus a package advisory lock;
- object review uses `SELECT ... FOR UPDATE` and expected row versions;
- duplicate idempotency keys return the original committed result;
- version mismatch returns `THEME_RESEARCH_VERSION_CONFLICT` with current version metadata;
- failed writes mark their change set failed when possible and leave canonical state unchanged;
- constraint failures return stable domain error codes;
- compare-mode mismatches never silently fall back to DB writes;
- DB unavailability in `db` mode is an error, not an automatic artifact fallback;
- artifact mode remains an explicit operational rollback switch.

## Testing And Acceptance

Unit tests cover:

- DDL tables, constraints, indexes, and append-only objects;
- artifact-to-row normalization;
- semantic diff and idempotency;
- state-transition gates;
- optimistic version conflicts;
- idempotency-key replay;
- snapshot and reverse diff generation;
- JSON export validation.

PostgreSQL integration tests cover:

- schema application twice;
- bootstrap transaction and exact object counts;
- foreign keys and deferred review constraints;
- concurrent review conflict;
- failed import rollback;
- snapshot rollback as a new version;
- revision and review-event immutability;
- DB/artifact semantic parity.

Dashboard tests cover:

- existing GET contract parity;
- authentication, CSRF, role enforcement, and stable errors;
- ordinary-user review transitions;
- admin-only import/rollback boundaries;
- history and snapshot reads.

Completion requires:

- schema applied to the configured research PostgreSQL database;
- current Phase 1-8 artifacts imported idempotently;
- artifact/DB compare reports zero canonical differences;
- DB-backed Dashboard GET APIs pass the existing Phase 7 contract tests;
- controlled write APIs pass authentication and state-transition tests;
- snapshot export validates through existing artifact loaders;
- rollback drill restores a prior state as a new version;
- no signal, admission, recommendation, or Phase 10 write path is introduced.

