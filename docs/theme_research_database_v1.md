# Theme Research Database Productionization v1

## Status

Phase 9 is productionized on 2026-07-11. PostgreSQL is authoritative for Theme Research canonical data. The Dashboard reads through `THEME_RESEARCH_READ_SOURCE=db`; artifact mode remains the emergency read fallback.

## Ownership Model

- `theme_research_owner`: NOLOGIN owner of `research.theme_research_*` tables and functions.
- migration service: `stock_research`; used only for role provisioning and schema migration.
- `theme_research_runtime`: NOLOGIN privilege group with constrained DML.
- `theme_research_app`: non-superuser LOGIN and member of runtime only.
- auth service: existing Dashboard identity store; CLI execute/export/rollback require an active admin account.

Runtime connections are rejected unless the login is a runtime member, is not an owner member, and has neither superuser nor CREATEROLE privileges.

PostgreSQL integration tests must use dedicated services whose database name ends in `_test`:

```text
THEME_RESEARCH_POSTGRES_TEST_SERVICE=theme_research_test_migration
THEME_RESEARCH_POSTGRES_TEST_RUNTIME_SERVICE=theme_research_test_runtime
```

The tests fail closed when pointed at the production database.

## Schema And Bootstrap

Local operator credentials are supplied through environment variables. They are not stored in the repository.

```bash
python -m stock_research.theme_research_db_schema schema-status
python -m stock_research.theme_research_db_schema import --dry-run
THEME_RESEARCH_DB_EXECUTE=1 scripts/run_theme_research_db_bootstrap.sh
python -m stock_research.theme_research_db_schema compare
```

Execute import additionally requires:

```text
THEME_RESEARCH_ADMIN_USERNAME
THEME_RESEARCH_ADMIN_PASSWORD
THEME_RESEARCH_EXPECTED_GENERATION
THEME_RESEARCH_IDEMPOTENCY_KEY
```

Ordinary bootstrap inserts or updates only. It never deactivates database-only objects. Explicit `--replace-theme THEME_ID` is required for theme-scoped deactivation. An already imported package that differs from DB returns `THEME_RESEARCH_RECONCILE_REQUIRED`.

## Read Modes

```text
THEME_RESEARCH_READ_SOURCE=artifact | compare | db
```

- `artifact`: emergency fallback and offline validation.
- `compare`: serves artifact payloads and attaches parity diagnostics.
- `db`: authoritative production reads.

Rollback to artifact reads requires changing the LaunchAgent environment to `artifact` and restarting the Dashboard API. This does not modify DB data.

## Review API

Authenticated users may review source, claim, and node status through the three POST routes. Requests require session authentication, matching CSRF cookie/header, a request ID, expected row version, non-empty comment, and idempotency key.

Each successful transition writes one transaction containing:

- optimistic row-version validation;
- evidence gate validation;
- pre/post immutable snapshots;
- object revision;
- review event;
- affected theme-version increment;
- committed change set.

Every canonical write, including review and rollback, advances the global store generation. This prevents a bootstrap request prepared before a human review from overwriting that review with a stale generation.

Version conflicts return HTTP 409 with the current row version.

## Export And Rollback

```bash
python -m stock_research.theme_research_db_schema export \
  --theme ai_power_value_capture_v1 \
  --output-dir outputs/theme_research_exports \
  --admin-username "$THEME_RESEARCH_ADMIN_USERNAME" \
  --idempotency-key export-ai-power-v1

python -m stock_research.theme_research_db_schema rollback \
  --theme ai_power_value_capture_v1 \
  --snapshot SNAPSHOT_ID \
  --expected-version VERSION \
  --admin-username "$THEME_RESEARCH_ADMIN_USERNAME" \
  --comment "Rollback reason" \
  --idempotency-key rollback-ai-power-v1
```

Exports are validated by the existing artifact loader before atomic rename. Rollback restores a complete normalized snapshot as a new theme version; prior snapshots, revisions, review events, and change sets remain immutable.

Idempotency keys are bound to a canonical request fingerprint. Reusing a key for a different object, target state, package, snapshot, expected version, or output path is rejected.

## Recovery

- Import failure: transaction rolls back; inspect the stable error code and rerun dry-run.
- Generation conflict: read current generation and submit a new reviewed request.
- Version conflict: reload the object and review the new version.
- DB outage: set read source to `artifact`; do not attempt artifact/DB dual writes.
- Parity mismatch: keep or return reads to `compare`/`artifact`, run `compare`, and resolve through explicit import or rollback.
- Unsafe DB role: correct `THEME_RESEARCH_RUNTIME_SERVICE`; never point runtime operations at the migration service.

## Production Verification

The 2026-07-11 cutover verified:

- schema catalog fingerprint current;
- runtime login cannot UPDATE/TRUNCATE history, CREATE in schema, or ALTER triggers;
- bootstrap counts: 2 themes, 34 nodes, 24 sources, 12 claims, 10 assessments, 4 company mappings;
- artifact and DB package SHA: `50560c59b2bc84304242a2858b1b948d74a0dd1b971a9524c975182c1000b067`;
- all six Dashboard GET contracts have artifact/DB parity;
- review and rollback drill restored canonical parity as theme version 3;
- exported AI power artifact validates with the existing loader;
- research-only guardrails remain unchanged: no signal or admission coupling.
