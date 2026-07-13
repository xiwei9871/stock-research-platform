# Theme Research Database Productionization v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make PostgreSQL the authoritative Theme Research store with validated artifact bootstrap, versioned human review, DB-backed Dashboard reads, immutable snapshots, exports, and rollback-as-new-version.

**Architecture:** Add a dedicated normalized `research.theme_research_*` schema and focused schema, store, import, and Dashboard provider modules. Existing Phase 1-8 artifact loaders remain offline validators and bootstrap/export contracts; production writes use PostgreSQL transactions, optimistic versions, authenticated review APIs, revisions, and immutable snapshots.

**Tech Stack:** Python 3.11+, PostgreSQL/psycopg, FastAPI, existing dashboard authentication and CSRF service, JSON artifacts, pytest, existing `stock-research` argparse CLI.

---

## File Map

- `src/stock_research/theme_research_db_schema.py`: DDL, schema version, apply/status commands.
- `src/stock_research/theme_research_db_models.py`: enums, transition maps, typed validation helpers, stable domain errors.
- `src/stock_research/theme_research_import.py`: artifact normalization, semantic diff, dry-run, bootstrap/reconcile.
- `src/stock_research/theme_research_store.py`: authoritative reads/writes, revisions, snapshots, export, rollback.
- `src/stock_research/dashboard/theme_research_db.py`: Dashboard DB read model and compare provider.
- `src/stock_research/dashboard/theme_research.py`: provider selection while preserving existing GET contracts.
- `src/stock_research/dashboard/app.py`: authenticated controlled write/history/snapshot routes.
- `src/stock_research/cli.py`: `theme-research-db` delegated CLI.
- `tests/test_theme_research_db_schema.py`: DDL and schema command tests.
- `tests/test_theme_research_import.py`: normalization, diff, and import transaction tests.
- `tests/test_theme_research_store.py`: versioning, review, snapshot, export, rollback tests.
- `tests/test_dashboard_theme_research_db.py`: provider parity and API authorization tests.
- `tests/integration/test_theme_research_postgres.py`: configured PostgreSQL schema/import/concurrency drill.
- `docs/theme_research_database_v1.md`: operations, cutover, recovery, and rollback runbook.

### Task 1: Domain Errors, Enums, And State Transitions

**Files:**
- Create: `src/stock_research/theme_research_db_models.py`
- Create: `tests/test_theme_research_db_models.py`

- [ ] **Step 1: Write failing transition and validation tests**

```python
def test_s4_source_cannot_transition_to_accepted():
    with pytest.raises(ThemeResearchDomainError) as exc:
        validate_source_transition(
            reliability_level="S4",
            from_status="needs_full_text",
            to_status="accepted",
        )
    assert exc.value.code == "S4_SOURCE_CANNOT_BE_ACCEPTED"


def test_reviewed_claim_requires_accepted_non_s4_source():
    with pytest.raises(ThemeResearchDomainError) as exc:
        validate_claim_transition(
            from_status="draft",
            to_status="reviewed",
            evidence_sources=[{"review_status": "lead_only", "reliability_level": "S4"}],
        )
    assert exc.value.code == "REVIEWED_CLAIM_REQUIRES_ACCEPTED_SOURCE"


def test_node_review_requires_evidence_strength_three():
    with pytest.raises(ThemeResearchDomainError) as exc:
        validate_node_transition(from_status="needs_evidence", to_status="reviewed", evidence_strength=2)
    assert exc.value.code == "REVIEWED_NODE_REQUIRES_STRONG_EVIDENCE"
```

- [ ] **Step 2: Run tests and verify missing-module failure**

Run: `rtk .venv/bin/pytest tests/test_theme_research_db_models.py -q`

Expected: collection fails because `theme_research_db_models` does not exist.

- [ ] **Step 3: Implement stable errors and exact transition maps**

```python
SOURCE_TRANSITIONS = {
    "unknown": {"needs_full_text", "lead_only", "rejected"},
    "needs_full_text": {"accepted", "lead_only", "rejected"},
    "lead_only": {"needs_full_text", "rejected"},
    "accepted": {"needs_full_text", "rejected"},
    "rejected": {"needs_full_text"},
}

CLAIM_TRANSITIONS = {
    "research_lead": {"draft", "blocked"},
    "draft": {"research_lead", "reviewed", "blocked"},
    "reviewed": {"draft", "blocked"},
    "blocked": {"research_lead", "draft"},
}


class ThemeResearchDomainError(ValueError):
    def __init__(self, message: str, *, code: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}
```

Implement `validate_source_transition`, `validate_claim_transition`, and `validate_node_transition` using these maps and Phase 1.5 evidence gates.

- [ ] **Step 4: Run domain tests**

Run: `rtk .venv/bin/pytest tests/test_theme_research_db_models.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit domain model**

```bash
git add src/stock_research/theme_research_db_models.py tests/test_theme_research_db_models.py
git commit -m "feat: add theme research database domain model"
```

### Task 2: PostgreSQL Schema And Version Commands

**Files:**
- Create: `src/stock_research/theme_research_db_schema.py`
- Create: `tests/test_theme_research_db_schema.py`
- Modify: `src/stock_research/cli.py`

- [ ] **Step 1: Write failing DDL contract tests**

Assert that `THEME_RESEARCH_SCHEMA_SQL` contains all exact tables:

```python
REQUIRED_TABLES = {
    "theme_research_schema_migration",
    "theme_research_change_set",
    "theme_research_theme",
    "theme_research_node",
    "theme_research_source_item",
    "theme_research_theme_source",
    "theme_research_content_claim",
    "theme_research_claim_source",
    "theme_research_claim_node",
    "theme_research_value_assessment",
    "theme_research_assessment_evidence",
    "theme_research_company_mapping",
    "theme_research_company_mapping_evidence",
    "theme_research_review_event",
    "theme_research_object_revision",
    "theme_research_import_run",
    "theme_research_snapshot",
}

for table in REQUIRED_TABLES:
    assert f"CREATE TABLE IF NOT EXISTS research.{table}" in THEME_RESEARCH_SCHEMA_SQL
```

Also assert score/confidence checks, S4 rejection, unique idempotency key, relationship foreign keys, indexes, deferred reviewed-claim trigger, and append-only trigger functions.

- [ ] **Step 2: Run schema tests and verify failure**

Run: `rtk .venv/bin/pytest tests/test_theme_research_db_schema.py -q`

Expected: missing-module failure.

- [ ] **Step 3: Implement schema v1 DDL**

Define:

```python
THEME_RESEARCH_DB_SCHEMA_VERSION = "theme_research_db_v1"


def apply_theme_research_schema(service: str = SETTINGS.research_service) -> dict:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(THEME_RESEARCH_SCHEMA_SQL)
            cur.execute(
                """
                INSERT INTO research.theme_research_schema_migration (
                    schema_version, applied_by, ddl_sha256, metadata
                ) VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (schema_version) DO UPDATE
                SET ddl_sha256 = EXCLUDED.ddl_sha256,
                    metadata = EXCLUDED.metadata
                """,
                (THEME_RESEARCH_DB_SCHEMA_VERSION, "system", ddl_sha256(), "{}"),
            )
    return {"status": "ok", "schema_version": THEME_RESEARCH_DB_SCHEMA_VERSION, "ddl_sha256": ddl_sha256()}
```

Add `schema_status()` that reads applied version and compares the DDL hash.

- [ ] **Step 4: Add delegated CLI**

Register `theme-research-db` in `stock_research.cli`, delegating arguments to `theme_research_db_schema.cli()` initially. Commands:

```text
apply-schema
schema-status
```

- [ ] **Step 5: Run schema and CLI tests**

Run: `rtk .venv/bin/pytest tests/test_theme_research_db_schema.py tests/test_cli.py -q`

Expected: all relevant tests pass.

- [ ] **Step 6: Commit schema**

```bash
git add src/stock_research/theme_research_db_schema.py src/stock_research/cli.py tests/test_theme_research_db_schema.py
git commit -m "feat: add theme research PostgreSQL schema"
```

### Task 3: Artifact Normalization And Semantic Diff

**Files:**
- Create: `src/stock_research/theme_research_import.py`
- Create: `tests/test_theme_research_import.py`

- [ ] **Step 1: Write failing normalization tests**

```python
def test_normalize_current_artifacts_to_relational_rows():
    normalized = normalize_artifact_package()
    assert len(normalized["themes"]) == 2
    assert len(normalized["nodes"]) == 34
    assert all("theme_id" in row for row in normalized["theme_sources"])
    assert all("claim_id" in row and "node_id" in row for row in normalized["claim_nodes"])
    assert normalized["package_sha256"]


def test_semantic_diff_is_order_independent():
    left = normalized_fixture()
    right = copy.deepcopy(left)
    right["nodes"].reverse()
    assert semantic_diff(left, right)["has_changes"] is False
```

Add tests for company mappings, assessment evidence, duplicate IDs, orphan relationships, and deterministic package hashing.

- [ ] **Step 2: Run normalization tests and verify failure**

Run: `rtk .venv/bin/pytest tests/test_theme_research_import.py -q`

Expected: missing-module failure.

- [ ] **Step 3: Implement immutable normalized package contract**

```python
@dataclass(frozen=True)
class NormalizedThemeResearchPackage:
    artifact_version: str
    package_sha256: str
    themes: tuple[dict, ...]
    nodes: tuple[dict, ...]
    sources: tuple[dict, ...]
    theme_sources: tuple[dict, ...]
    claims: tuple[dict, ...]
    claim_sources: tuple[dict, ...]
    claim_nodes: tuple[dict, ...]
    assessments: tuple[dict, ...]
    assessment_evidence: tuple[dict, ...]
    company_mappings: tuple[dict, ...]
    company_mapping_evidence: tuple[dict, ...]
```

`normalize_artifact_package()` must call existing Phase 1 and Phase 4 loaders and derive explicit relationship rows. `semantic_diff()` compares canonical JSON by stable keys and returns insert/update/deactivate/no-change sections for every object family.

- [ ] **Step 4: Run import normalization tests**

Run: `rtk .venv/bin/pytest tests/test_theme_research_import.py -q`

Expected: all normalization/diff tests pass without DB access.

- [ ] **Step 5: Commit normalization**

```bash
git add src/stock_research/theme_research_import.py tests/test_theme_research_import.py
git commit -m "feat: normalize theme research artifacts for import"
```

### Task 4: Transactional Store, Bootstrap, Revisions, And Snapshots

**Files:**
- Create: `src/stock_research/theme_research_store.py`
- Modify: `src/stock_research/theme_research_import.py`
- Create: `tests/test_theme_research_store.py`
- Modify: `tests/test_theme_research_import.py`

- [ ] **Step 1: Write failing transaction tests with recording connections**

Cover:

```python
def test_bootstrap_uses_serializable_transaction_and_package_lock():
    result = bootstrap_package(package, actor_user_id="admin-1", expected_generation=0, service="test")
    assert recorder.commands[0] == "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"
    assert any("pg_advisory_xact_lock" in sql for sql, _ in recorder.executions)
    assert result["resulting_generation"] == 1


def test_same_package_hash_is_idempotent():
    first = bootstrap_package(package, actor_user_id="admin-1", expected_generation=0)
    second = bootstrap_package(package, actor_user_id="admin-1", expected_generation=1)
    assert first["package_sha256"] == second["package_sha256"]
    assert second["status"] == "no_changes"


def test_failed_insert_rolls_back_canonical_and_history_rows():
    connection.fail_on("theme_research_content_claim")
    with pytest.raises(ThemeResearchDomainError):
        bootstrap_package(package, actor_user_id="admin-1", expected_generation=0)
    assert connection.rollback_count == 1
```

- [ ] **Step 2: Run store tests and verify failure**

Run: `rtk .venv/bin/pytest tests/test_theme_research_store.py tests/test_theme_research_import.py -q`

Expected: missing store functions.

- [ ] **Step 3: Implement store transaction primitives**

Implement these exact public interfaces:

- `load_database_package(*, service: str = SETTINGS.research_service) -> dict`
- `bootstrap_package(package: NormalizedThemeResearchPackage, *, actor_user_id: str, expected_generation: int, idempotency_key: str, replace_theme: bool = False, service: str = SETTINGS.research_service) -> dict`
- `create_snapshot(cur, *, theme_id: str, theme_version: int, snapshot_type: str, payload: dict, change_set_id: str, actor_user_id: str) -> str`

One transaction must insert a prepared change set, verify generation, write pre-change snapshots, apply objects and relationships, append revisions, write post-change snapshots/import run, and mark the change set committed.

- [ ] **Step 4: Implement dry-run and execute CLI commands**

Extend `theme-research-db`:

```text
import --dry-run
import --execute --expected-generation N --actor USER --idempotency-key KEY
import --execute --replace-theme ai_power_value_capture_v1 --expected-generation 0 --actor admin-1 --idempotency-key bootstrap-ai-power-v1
```

Dry run performs no canonical writes. Execute requires explicit actor, expected generation, and idempotency key.

- [ ] **Step 5: Run store/import tests**

Run: `rtk .venv/bin/pytest tests/test_theme_research_store.py tests/test_theme_research_import.py tests/test_theme_research_db_schema.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit transactional import**

```bash
git add src/stock_research/theme_research_store.py src/stock_research/theme_research_import.py tests/test_theme_research_store.py tests/test_theme_research_import.py
git commit -m "feat: add transactional theme research bootstrap"
```

### Task 5: DB Read Model, Compare Mode, And Existing GET Contract

**Files:**
- Create: `src/stock_research/dashboard/theme_research_db.py`
- Modify: `src/stock_research/dashboard/theme_research.py`
- Create: `tests/test_dashboard_theme_research_db.py`
- Modify: `tests/test_dashboard_theme_research.py`

- [ ] **Step 1: Write failing provider-parity tests**

```python
def test_db_provider_matches_artifact_provider_contract(monkeypatch):
    artifact = list_theme_research_themes(read_source="artifact")
    database = list_theme_research_themes(read_source="db")
    assert canonicalize(database) == canonicalize(artifact)


def test_compare_mode_surfaces_semantic_mismatch(monkeypatch):
    monkeypatch.setattr(db_provider, "list_themes", lambda: {"total": 1, "items": []})
    payload = list_theme_research_themes(read_source="compare")
    assert payload["comparison"]["status"] == "mismatch"
    assert payload["comparison"]["differences"]
```

Cover all six Phase 7 GET APIs and guardrails.

- [ ] **Step 2: Run provider tests and verify failure**

Run: `rtk .venv/bin/pytest tests/test_dashboard_theme_research_db.py tests/test_dashboard_theme_research.py -q`

Expected: missing DB provider/read-source support.

- [ ] **Step 3: Implement provider selection**

```python
READ_SOURCES = {"artifact", "compare", "db"}


def configured_theme_research_read_source() -> str:
    value = os.getenv("THEME_RESEARCH_READ_SOURCE", "artifact").strip().lower()
    if value not in READ_SOURCES:
        raise ThemeResearchDomainError(
            f"unsupported read source: {value}",
            code="THEME_RESEARCH_READ_SOURCE_INVALID",
        )
    return value
```

Move the existing artifact behavior behind an explicit provider and add DB queries that produce the same response contract. Compare mode returns artifact data plus an administrator-only comparison block; it never writes.

- [ ] **Step 4: Run Phase 7 and DB provider tests**

Run: `rtk .venv/bin/pytest tests/test_dashboard_theme_research.py tests/test_dashboard_theme_research_db.py -q`

Expected: all tests pass in artifact, compare, and DB modes.

- [ ] **Step 5: Commit DB read provider**

```bash
git add src/stock_research/dashboard/theme_research_db.py src/stock_research/dashboard/theme_research.py tests/test_dashboard_theme_research_db.py tests/test_dashboard_theme_research.py
git commit -m "feat: add database-backed theme research reads"
```

### Task 6: Authenticated Review Transitions And History APIs

**Files:**
- Modify: `src/stock_research/theme_research_store.py`
- Modify: `src/stock_research/dashboard/theme_research_db.py`
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `tests/test_theme_research_store.py`
- Modify: `tests/test_dashboard_theme_research_db.py`

- [ ] **Step 1: Write failing store transition tests**

```python
def test_review_transition_locks_row_and_increments_versions():
    result = review_source(
        source_id="source-1",
        to_status="accepted",
        expected_row_version=3,
        actor_user_id="user-1",
        actor_role="user",
        comment="Full text verified.",
        request_id="req-1",
        idempotency_key="review-1",
    )
    assert result["row_version"] == 4
    assert result["theme_version"] == 8
    assert recorder.contains("FOR UPDATE")
    assert recorder.inserted("theme_research_review_event")
    assert recorder.inserted("theme_research_object_revision")


def test_version_conflict_returns_current_version():
    with pytest.raises(ThemeResearchDomainError) as exc:
        review_claim(
            claim_id="claim-1",
            to_status="reviewed",
            expected_row_version=2,
            actor_user_id="user-1",
            actor_role="user",
            comment="Evidence reviewed.",
            request_id="req-conflict",
            idempotency_key="review-conflict",
        )
    assert exc.value.code == "THEME_RESEARCH_VERSION_CONFLICT"
    assert exc.value.details["current_row_version"] == 3
```

Add tests for duplicate idempotency replay, comment required, S4 gate, reviewed-claim gate, node evidence gate, and atomic snapshot creation.

- [ ] **Step 2: Write failing API authorization tests**

Cover:

- unauthenticated request returns 401;
- missing/mismatched CSRF returns 403;
- active `user` can review source/claim/node;
- ordinary user cannot rollback/import;
- stable version conflict response is 409;
- idempotent replay returns the original 200 response.

- [ ] **Step 3: Implement review store methods**

Implement these exact public interfaces:

- `review_source(*, source_id: str, to_status: str, expected_row_version: int, actor_user_id: str, actor_role: str, comment: str, request_id: str, idempotency_key: str, service: str = SETTINGS.research_service) -> dict`
- `review_claim(*, claim_id: str, to_status: str, expected_row_version: int, actor_user_id: str, actor_role: str, comment: str, request_id: str, idempotency_key: str, service: str = SETTINGS.research_service) -> dict`
- `review_node(*, node_id: str, to_status: str, expected_row_version: int, actor_user_id: str, actor_role: str, comment: str, request_id: str, idempotency_key: str, service: str = SETTINGS.research_service) -> dict`

- [ ] **Step 4: Implement FastAPI request models and routes**

Use the existing session loader, `validate_csrf`, and request-ID middleware. Request body:

```python
class ThemeResearchReviewRequest(BaseModel):
    to_status: str
    expected_row_version: int
    comment: str
    idempotency_key: str
```

Add the three POST review routes plus GET history and GET snapshot-list routes from the design. Map domain errors to 400/403/404/409 with `{status, error_code, message, details}`.

- [ ] **Step 5: Run store and API tests**

Run: `rtk .venv/bin/pytest tests/test_theme_research_store.py tests/test_dashboard_theme_research_db.py tests/test_dashboard_auth_service.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit controlled review writes**

```bash
git add src/stock_research/theme_research_store.py src/stock_research/dashboard/theme_research_db.py src/stock_research/dashboard/app.py tests/test_theme_research_store.py tests/test_dashboard_theme_research_db.py
git commit -m "feat: add controlled theme research reviews"
```

### Task 7: Snapshot Export And Artifact Validation

**Files:**
- Modify: `src/stock_research/theme_research_store.py`
- Modify: `src/stock_research/theme_research_db_schema.py`
- Modify: `tests/test_theme_research_store.py`

- [ ] **Step 1: Write failing snapshot/export tests**

```python
def test_exported_theme_validates_with_existing_loader(tmp_path):
    exported = export_theme("ai_power_value_capture_v1", output_dir=tmp_path)
    package = load_theme_package(tmp_path)
    assert package["themes"][0]["theme_id"] == "ai_power_value_capture_v1"
    assert file_sha256(exported["path"]) == exported["payload_sha256"]


def test_snapshot_rows_are_immutable():
    assert "RAISE EXCEPTION 'theme_research_snapshot is append-only'" in THEME_RESEARCH_SCHEMA_SQL
```

- [ ] **Step 2: Implement canonical package reconstruction**

Implement `build_theme_artifact(theme_id)` by joining canonical tables and restoring exact Phase 1 array fields and relationship ordering. Preserve `artifact_version=theme_decomposition_v1_5` and guardrail metadata.

- [ ] **Step 3: Implement export command**

```text
theme-research-db export --theme THEME --output-dir PATH --actor ADMIN --idempotency-key KEY
```

Export writes through a temporary file, validates with `load_theme_package`, atomically renames, and records an immutable export snapshot/change set.

- [ ] **Step 4: Run export tests**

Run: `rtk .venv/bin/pytest tests/test_theme_research_store.py tests/test_theme_decomposition.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit snapshot/export**

```bash
git add src/stock_research/theme_research_store.py src/stock_research/theme_research_db_schema.py tests/test_theme_research_store.py
git commit -m "feat: export versioned theme research snapshots"
```

### Task 8: Rollback As A New Version

**Files:**
- Modify: `src/stock_research/theme_research_store.py`
- Modify: `src/stock_research/dashboard/theme_research_db.py`
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `tests/test_theme_research_store.py`
- Modify: `tests/test_dashboard_theme_research_db.py`

- [ ] **Step 1: Write failing rollback tests**

```python
def test_rollback_restores_snapshot_as_new_version():
    before = load_theme("theme-1")
    result = rollback_theme(
        theme_id="theme-1",
        snapshot_id="snapshot-1",
        expected_theme_version=before["theme_version"],
        actor_user_id="admin-1",
        actor_role="admin",
        comment="Rollback drill.",
        idempotency_key="rollback-1",
    )
    assert result["theme_version"] == before["theme_version"] + 1
    assert result["restored_from_snapshot_id"] == "snapshot-1"
    assert recorder.inserted_revision_operations == {"restore"}


def test_non_admin_cannot_rollback():
    with pytest.raises(ThemeResearchDomainError) as exc:
        rollback_theme(
            theme_id="theme-1",
            snapshot_id="snapshot-1",
            expected_theme_version=4,
            actor_user_id="user-1",
            actor_role="user",
            comment="Unauthorized rollback.",
            idempotency_key="rollback-denied",
        )
    assert exc.value.code == "THEME_RESEARCH_ADMIN_REQUIRED"
```

Also prove that rollback does not delete prior revisions, review events, snapshots, or change sets.

- [ ] **Step 2: Implement rollback transaction**

`rollback_theme()` must validate the snapshot through the existing artifact loader, use SERIALIZABLE isolation and advisory lock, verify expected version, create pre/post snapshots, restore rows/relationships, append `restore` revisions, increment theme version, and commit a rollback change set.

- [ ] **Step 3: Add admin rollback API and CLI**

```text
POST /api/research/theme-decomposition/themes/:theme_id/rollback
theme-research-db rollback --theme ai_power_value_capture_v1 --snapshot snapshot-1 --expected-version 4 --actor admin-1 --idempotency-key rollback-ai-power-1
```

Both paths require admin role and non-empty comment.

- [ ] **Step 4: Run rollback tests**

Run: `rtk .venv/bin/pytest tests/test_theme_research_store.py tests/test_dashboard_theme_research_db.py -q`

Expected: all rollback, role, and history-preservation tests pass.

- [ ] **Step 5: Commit rollback**

```bash
git add src/stock_research/theme_research_store.py src/stock_research/dashboard/theme_research_db.py src/stock_research/dashboard/app.py tests/test_theme_research_store.py tests/test_dashboard_theme_research_db.py
git commit -m "feat: add versioned theme research rollback"
```

### Task 9: PostgreSQL Integration Tests And Current Artifact Bootstrap

**Files:**
- Create: `tests/integration/test_theme_research_postgres.py`
- Create: `scripts/run_theme_research_db_bootstrap.sh`
- Modify: `docs/theme_research_database_v1.md`

- [ ] **Step 1: Add integration-test environment gate**

```python
pytestmark = pytest.mark.skipif(
    os.getenv("THEME_RESEARCH_POSTGRES_TEST") != "1",
    reason="set THEME_RESEARCH_POSTGRES_TEST=1 for configured PostgreSQL integration tests",
)
```

Tests must use the configured research service and unique test IDs, then clean only those IDs.

- [ ] **Step 2: Implement integration scenarios**

Cover:

- applying schema twice;
- dry-run current artifacts;
- bootstrap current artifacts;
- second bootstrap returns no changes;
- exact canonical object counts and zero semantic diff;
- DB GET read-model parity;
- concurrent source review where one writer receives version conflict;
- reviewed-claim deferred constraint;
- export loader validation;
- rollback drill as a new version;
- append-only table update/delete rejection.

- [ ] **Step 3: Add guarded bootstrap script**

`scripts/run_theme_research_db_bootstrap.sh` must:

```text
set -euo pipefail
apply-schema
schema-status
import --dry-run
require THEME_RESEARCH_DB_EXECUTE=1 before execute
execute with explicit expected generation, actor, and idempotency key
compare and require zero differences
```

The script must not hardcode `rtk` or credentials.

- [ ] **Step 4: Run configured integration tests**

Run:

```bash
rtk env THEME_RESEARCH_POSTGRES_TEST=1 .venv/bin/pytest tests/integration/test_theme_research_postgres.py -q
```

Expected: all PostgreSQL integration tests pass.

- [ ] **Step 5: Apply schema and bootstrap current artifacts**

Run the guarded script first without execute and inspect the dry-run counts. Then run with:

```bash
rtk env THEME_RESEARCH_DB_EXECUTE=1 scripts/run_theme_research_db_bootstrap.sh
```

Expected: schema current, import committed once, second import no changes, compare reports zero differences.

- [ ] **Step 6: Commit integration/bootstrap assets**

```bash
git add tests/integration/test_theme_research_postgres.py scripts/run_theme_research_db_bootstrap.sh docs/theme_research_database_v1.md
git commit -m "test: verify theme research PostgreSQL productionization"
```

### Task 10: Cutover Runbook, Regression, And Independent Review

**Files:**
- Create: `docs/theme_research_database_v1.md`
- Modify: `docs/theme_driven_research_engine_roadmap.md`
- Modify: `docs/theme_decomposition_research_baseline_v1.md`
- Modify: `docs/theme_research_dashboard_v1.md`

- [ ] **Step 1: Document operations**

The runbook must include:

- ownership model and table map;
- schema apply/status commands;
- dry-run and execute import;
- generation and idempotency behavior;
- artifact/compare/db read modes;
- review API authorization and CSRF;
- snapshot/export and rollback drill;
- recovery from import failure, version conflict, DB outage, and parity mismatch;
- explicit rollback to `THEME_RESEARCH_READ_SOURCE=artifact`;
- no-signal/no-admission guardrails.

- [ ] **Step 2: Mark Phase 9 complete only after production evidence exists**

Update the roadmap status and implementation result only after schema application, import, zero-diff compare, API tests, export validation, and rollback drill all succeed.

- [ ] **Step 3: Run focused and Theme Research regression suites**

```bash
rtk .venv/bin/pytest \
  tests/test_theme_research_db_models.py \
  tests/test_theme_research_db_schema.py \
  tests/test_theme_research_import.py \
  tests/test_theme_research_store.py \
  tests/test_dashboard_theme_research_db.py \
  tests/test_theme_research_ingestion.py \
  tests/test_theme_decomposition.py \
  tests/test_ai_power_source_pack.py \
  tests/test_decomposition_templates.py \
  tests/test_theme_company_mapping.py \
  tests/test_theme_tech_bottleneck_crosswalk.py \
  tests/test_theme_research_priority.py \
  tests/test_dashboard_theme_research.py -q
```

Expected: all tests pass; only already-known third-party deprecation warnings may remain.

- [ ] **Step 4: Run CLI smoke tests**

Run `apply-schema`, `schema-status`, import dry-run, compare, export, history, snapshot list, and rollback drill commands against the configured database. Record structured JSON outputs in the verification notes.

- [ ] **Step 5: Request independent code review**

Review must focus on SQL constraints, transaction boundaries, privilege checks, idempotency, lost updates, rollback, artifact parity, and accidental signal/admission coupling. Resolve every high and medium finding.

- [ ] **Step 6: Run final verification**

```bash
rtk git diff --check
rtk .venv/bin/python -m compileall -q \
  src/stock_research/theme_research_db_models.py \
  src/stock_research/theme_research_db_schema.py \
  src/stock_research/theme_research_import.py \
  src/stock_research/theme_research_store.py \
  src/stock_research/dashboard/theme_research_db.py
```

Verify the Dashboard GET contract in `THEME_RESEARCH_READ_SOURCE=db` and confirm controlled writes still return `research_only=true`, `used_for_signal=false`, and `used_for_admission=false`.

- [ ] **Step 7: Commit final documentation**

```bash
git add docs/theme_research_database_v1.md docs/theme_driven_research_engine_roadmap.md docs/theme_decomposition_research_baseline_v1.md docs/theme_research_dashboard_v1.md
git commit -m "docs: complete theme research database productionization"
```
