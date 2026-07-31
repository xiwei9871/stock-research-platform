# Theme Research Analysis Report Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Index backend-generated Theme Research Markdown/PDF artifacts, require admin review before publication, and let authenticated users read or download approved versions without exposing generation or upload controls.

**Architecture:** Report files remain immutable under a configured filesystem root and a required manifest is the generator-to-application contract. Focused Python modules validate and index artifacts into PostgreSQL, enforce review transitions and safe reads, and expose authenticated FastAPI endpoints; React adds an approved-report reader and an admin-only review queue. A startup/periodic scheduler performs idempotent discovery while PostgreSQL remains authoritative for review and publication state.

**Tech Stack:** Python 3.11, FastAPI, psycopg/PostgreSQL, `markdown-it-py`, `nh3`, React 19, TypeScript, Vitest, Playwright, pytest.

---

## File Structure

### Backend files to create

- `src/stock_research/theme_research_report_schema.py` — owns report DDL and schema application.
- `src/stock_research/theme_research_report_manifest.py` — parses and validates `manifest.json`, artifact paths, sizes, and checksums.
- `src/stock_research/theme_research_report_store.py` — owns indexing persistence, review transitions, audit events, and approved/admin read models.
- `src/stock_research/theme_research_report_index.py` — scans the fixed report root, indexes finalized versions, reports diagnostics, and provides an operator CLI.
- `src/stock_research/dashboard/theme_research_reports.py` — reads approved/admin reports, renders sanitized Markdown, and resolves safe PDF downloads.
- `src/stock_research/dashboard/theme_research_report_scheduler.py` — runs startup and periodic scans without blocking request handlers.

### Backend files to modify

- `pyproject.toml` — adds Markdown rendering and HTML sanitization dependencies.
- `src/stock_research/config.py` — adds report-root, scan interval, and artifact-size settings.
- `src/stock_research/dashboard/app.py` — wires scheduler lifecycle, request models, read endpoints, admin endpoints, and PDF responses.
- `src/stock_research/dashboard/theme_research_db.py` — adds published-report summary fields to theme list/detail reads without leaking pending state.

### Frontend files to create

- `dashboard/src/components/ThemeResearchReportReader.tsx` — renders approved report metadata, sanitized HTML, version picker, and PDF action.
- `dashboard/src/components/ThemeResearchReportReviewWorkspace.tsx` — admin pending queue, preview, publish, and reject UI.

### Frontend files to modify

- `dashboard/src/api/types.ts` — report metadata, document, queue, and review mutation types.
- `dashboard/src/api/client.ts` — approved-report and admin-review API functions.
- `dashboard/src/components/ThemeResearchWorkspace.tsx` — report status, empty state, reader route, and approved history integration.
- `dashboard/src/components/AppShell.tsx` — admin-only `报告审核` navigation and route.
- `dashboard/src/styles.css` — reader and review queue styles.

### Tests to create or modify

- `tests/test_theme_research_report_manifest.py`
- `tests/integration/test_theme_research_report_store_postgres.py`
- `tests/test_theme_research_report_index.py`
- `tests/test_dashboard_theme_research_reports.py`
- `dashboard/tests/theme-research-report-reader.test.tsx`
- `dashboard/tests/theme-research-report-review.test.tsx`
- `dashboard/tests/theme-research-full-flow.spec.ts`
- `dashboard/tests/app-shell.test.tsx`
- `dashboard/tests/theme-research-workspace.test.tsx`

## Task 1: Add configuration, dependencies, and the report schema

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/stock_research/config.py`
- Create: `src/stock_research/theme_research_report_schema.py`
- Test: `tests/integration/test_theme_research_report_store_postgres.py`

- [ ] **Step 1: Write the failing schema/config tests**

Add tests that instantiate `Settings` under explicit environment variables and assert the resolved values, then apply the schema to the dedicated test PostgreSQL service and inspect both tables and constraints:

```python
def test_report_settings_are_explicit(monkeypatch, tmp_path):
    monkeypatch.setenv("THEME_RESEARCH_REPORT_ROOT", str(tmp_path / "theme-reports"))
    monkeypatch.setenv("THEME_RESEARCH_REPORT_SCAN_INTERVAL_SECONDS", "45")
    monkeypatch.setenv("THEME_RESEARCH_REPORT_MAX_MANIFEST_BYTES", "65536")
    monkeypatch.setenv("THEME_RESEARCH_REPORT_MAX_MARKDOWN_BYTES", "10485760")
    monkeypatch.setenv("THEME_RESEARCH_REPORT_MAX_PDF_BYTES", "52428800")
    settings = Settings()
    assert settings.theme_research_report_root == tmp_path / "theme-reports"
    assert settings.theme_research_report_scan_interval_seconds == 45
    assert settings.theme_research_report_max_manifest_bytes == 65536


def test_apply_report_schema_creates_version_and_event_tables(test_service):
    apply_theme_research_report_schema(service=test_service)
    with connect(test_service) as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('research.theme_research_report_version') AS name")
        assert cur.fetchone()["name"] == "research.theme_research_report_version"
        cur.execute("SELECT to_regclass('research.theme_research_report_review_event') AS name")
        assert cur.fetchone()["name"] == "research.theme_research_report_review_event"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/integration/test_theme_research_report_store_postgres.py -v
```

Expected: FAIL because the new settings and `theme_research_report_schema` module do not exist.

- [ ] **Step 3: Add dependencies and configuration**

Add these project dependencies:

```toml
"markdown-it-py",
"nh3",
```

Add these `Settings` fields using existing `_path_from_env` and `_env_int` helpers:

```python
theme_research_report_root: Path = field(
    default_factory=lambda: Path(
        os.environ.get(
            "THEME_RESEARCH_REPORT_ROOT",
            str(_path_from_env("STOCK_RESEARCH_REPORTS_ROOT", "reports") / "theme-research"),
        )
    )
)
theme_research_report_scan_interval_seconds: int = field(
    default_factory=lambda: _env_int("THEME_RESEARCH_REPORT_SCAN_INTERVAL_SECONDS", 60)
)
theme_research_report_max_manifest_bytes: int = field(
    default_factory=lambda: _env_int("THEME_RESEARCH_REPORT_MAX_MANIFEST_BYTES", 64 * 1024)
)
theme_research_report_max_markdown_bytes: int = field(
    default_factory=lambda: _env_int("THEME_RESEARCH_REPORT_MAX_MARKDOWN_BYTES", 10 * 1024 * 1024)
)
theme_research_report_max_pdf_bytes: int = field(
    default_factory=lambda: _env_int("THEME_RESEARCH_REPORT_MAX_PDF_BYTES", 50 * 1024 * 1024)
)
```

- [ ] **Step 4: Implement focused schema application**

Create DDL with:

```sql
CREATE TABLE IF NOT EXISTS research.theme_research_report_version (
    report_version_id text PRIMARY KEY,
    theme_id text NOT NULL REFERENCES research.theme_research_theme(theme_id),
    version text NOT NULL,
    title text NOT NULL,
    summary text NOT NULL DEFAULT '',
    status text NOT NULL CHECK (status IN ('pending_review', 'published', 'rejected', 'archived')),
    markdown_relative_path text NOT NULL,
    markdown_sha256 text NOT NULL,
    pdf_relative_path text,
    pdf_sha256 text,
    manifest_relative_path text NOT NULL,
    manifest_sha256 text NOT NULL,
    generator_name text NOT NULL,
    generator_version text NOT NULL,
    generated_at timestamptz NOT NULL,
    indexed_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    published_by_user_id text REFERENCES identity.user_account(user_id),
    rejected_at timestamptz,
    rejected_by_user_id text REFERENCES identity.user_account(user_id),
    rejection_reason text NOT NULL DEFAULT '',
    row_version bigint NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (theme_id, version),
    CHECK ((pdf_relative_path IS NULL) = (pdf_sha256 IS NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_theme_research_report_current
    ON research.theme_research_report_version(theme_id)
    WHERE status = 'published';

CREATE TABLE IF NOT EXISTS research.theme_research_report_review_event (
    event_id text PRIMARY KEY,
    report_version_id text NOT NULL REFERENCES research.theme_research_report_version(report_version_id),
    from_status text,
    to_status text NOT NULL,
    actor_user_id text NOT NULL,
    comment text NOT NULL DEFAULT '',
    request_id text NOT NULL DEFAULT '',
    idempotency_key text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_theme_research_report_review_idempotency
    ON research.theme_research_report_review_event(actor_user_id, idempotency_key)
    WHERE idempotency_key <> '';
```

Expose `apply_theme_research_report_schema(service=SETTINGS.theme_research_migration_service)` and keep schema creation separate from the existing large Theme Research DDL. Add a module CLI with `--apply` and `--service`; `python -m stock_research.theme_research_report_schema --apply` must apply the DDL and print a JSON object containing `status`, `service`, and `schema_version`.

- [ ] **Step 5: Run the schema/config tests**

Run:

```bash
pytest tests/integration/test_theme_research_report_store_postgres.py -v
```

Expected: PASS for configuration and schema creation tests.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/stock_research/config.py src/stock_research/theme_research_report_schema.py tests/integration/test_theme_research_report_store_postgres.py
git commit -m "feat: add theme research report schema"
```

## Task 2: Validate manifests and artifact boundaries

**Files:**
- Create: `src/stock_research/theme_research_report_manifest.py`
- Create: `tests/test_theme_research_report_manifest.py`

- [ ] **Step 1: Write failing manifest tests**

Cover a valid Markdown-only manifest, optional PDF, unsupported schema, absolute/traversing paths, symlinks, oversized files, malformed timestamps, and checksum mismatches. Use a fixture helper that writes bytes and real SHA-256 values:

```python
def write_manifest_version(root: Path, *, theme_id="ai_power_value_capture_v1", version="2026-07-31.1", pdf=False):
    version_dir = root / theme_id / version
    version_dir.mkdir(parents=True)
    markdown = b"# AI Power\n\nApproved research draft.\n"
    (version_dir / "report.md").write_bytes(markdown)
    artifacts = {
        "markdown": {"path": "report.md", "sha256": hashlib.sha256(markdown).hexdigest()}
    }
    if pdf:
        pdf_bytes = b"%PDF-1.4\nfixture"
        (version_dir / "report.pdf").write_bytes(pdf_bytes)
        artifacts["pdf"] = {"path": "report.pdf", "sha256": hashlib.sha256(pdf_bytes).hexdigest()}
    manifest = {
        "schema_version": "theme_research_report_manifest_v1",
        "theme_id": theme_id,
        "version": version,
        "title": "AI 电力主题分析报告",
        "summary": "报告摘要",
        "generated_at": "2026-07-31T10:00:00+08:00",
        "generator": {"name": "theme-research-report-pipeline", "version": "1.0.0"},
        "artifacts": artifacts,
        "metadata": {},
    }
    (version_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return version_dir


def test_load_manifest_rejects_parent_traversal(tmp_path):
    version_dir = write_manifest_version(tmp_path)
    payload = json.loads((version_dir / "manifest.json").read_text())
    payload["artifacts"]["markdown"]["path"] = "../secret.md"
    (version_dir / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ReportManifestError, match="artifact_path_invalid"):
        load_report_manifest(version_dir / "manifest.json", limits=TEST_LIMITS)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_theme_research_report_manifest.py -v
```

Expected: FAIL because the manifest module does not exist.

- [ ] **Step 3: Implement immutable manifest models and validation**

Define:

```python
@dataclass(frozen=True)
class ReportArtifact:
    relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ThemeResearchReportManifest:
    theme_id: str
    version: str
    title: str
    summary: str
    generated_at: datetime
    generator_name: str
    generator_version: str
    markdown: ReportArtifact
    pdf: ReportArtifact | None
    manifest_relative_path: str
    manifest_sha256: str
    metadata: dict[str, Any]


class ReportManifestError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
```

`load_report_manifest()` must read the manifest with a byte limit, require UTF-8 JSON and the exact v1 schema, validate non-empty identity/title/generator fields, require a timezone-aware ISO timestamp, reject paths that are absolute or contain `..`, call `resolve(strict=True)`, require `resolved.parent == version_dir` for v1 artifact filenames, reject symlinks/non-regular files, enforce byte limits, and verify SHA-256 with `hmac.compare_digest`.

- [ ] **Step 4: Run all manifest tests**

Run:

```bash
pytest tests/test_theme_research_report_manifest.py -v
```

Expected: PASS for valid Markdown/PDF and every fail-closed validation case.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/theme_research_report_manifest.py tests/test_theme_research_report_manifest.py
git commit -m "feat: validate theme report manifests"
```

## Task 3: Persist indexed versions idempotently

**Files:**
- Create: `src/stock_research/theme_research_report_store.py`
- Modify: `tests/integration/test_theme_research_report_store_postgres.py`

- [ ] **Step 1: Write failing store tests**

Seed a Theme Research theme, index a manifest, repeat the same index, and attempt the same `(theme_id, version)` with changed checksums:

```python
def test_register_manifest_is_idempotent_and_conflicts_on_changed_bytes(test_service, valid_manifest):
    first = register_report_manifest(valid_manifest, service=test_service)
    second = register_report_manifest(valid_manifest, service=test_service)
    assert first["result"] == "indexed"
    assert second["result"] == "unchanged"
    assert second["report_version_id"] == first["report_version_id"]

    changed = replace(valid_manifest, markdown=replace(valid_manifest.markdown, sha256="f" * 64))
    with pytest.raises(ThemeResearchReportError) as exc:
        register_report_manifest(changed, service=test_service)
    assert exc.value.code == "THEME_REPORT_VERSION_CONTENT_CONFLICT"
```

Also assert the inserted row is `pending_review`, the initial `generated -> pending_review` event uses actor `system`, and an unknown theme fails without inserting a row.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/integration/test_theme_research_report_store_postgres.py -k register -v
```

Expected: FAIL because the store functions do not exist.

- [ ] **Step 3: Implement the store boundary**

Create `ThemeResearchReportError(code, message, details={})`, stable identity:

```python
def report_version_id(theme_id: str, version: str) -> str:
    digest = hashlib.sha256(f"{theme_id}\0{version}".encode("utf-8")).hexdigest()[:20]
    return f"theme_report:{digest}"
```

Implement `register_report_manifest()` in one transaction. Lock/select an existing `(theme_id, version)` row. When absent, verify the theme exists and insert the full index plus an initial system audit event. When present, compare manifest, Markdown, and PDF checksums; return `unchanged` only when all indexed identity fields match, otherwise raise `THEME_REPORT_VERSION_CONTENT_CONFLICT`. Never modify status during a rescan.

- [ ] **Step 4: Run store tests**

Run:

```bash
pytest tests/integration/test_theme_research_report_store_postgres.py -k register -v
```

Expected: PASS for insert, idempotency, conflict, and unknown-theme cases.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/theme_research_report_store.py tests/integration/test_theme_research_report_store_postgres.py
git commit -m "feat: index immutable theme report versions"
```

## Task 4: Build the filesystem indexer and operator command

**Files:**
- Create: `src/stock_research/theme_research_report_index.py`
- Create: `tests/test_theme_research_report_index.py`

- [ ] **Step 1: Write failing scan tests**

Use temporary roots and monkeypatch `register_report_manifest` so unit tests do not need PostgreSQL:

```python
def test_scan_indexes_valid_versions_and_isolates_invalid_ones(tmp_path, monkeypatch):
    write_manifest_version(tmp_path, theme_id="theme-a", version="v1")
    broken = write_manifest_version(tmp_path, theme_id="theme-b", version="v1")
    (broken / "report.md").write_text("changed", encoding="utf-8")
    registered = []
    monkeypatch.setattr(index_module, "register_report_manifest", lambda manifest, service: registered.append(manifest) or {"result": "indexed"})

    result = scan_theme_research_report_root(tmp_path, limits=TEST_LIMITS, service="test")
    assert result.discovered == 2
    assert result.indexed == 1
    assert result.invalid == 1
    assert registered[0].theme_id == "theme-a"
    assert result.errors[0]["code"] == "artifact_checksum_mismatch"
```

Add tests for missing root, deterministic manifest ordering, unchanged counts, content conflicts, and bounded error output.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_theme_research_report_index.py -v
```

Expected: FAIL because the indexer module does not exist.

- [ ] **Step 3: Implement scanning and diagnostics**

Define immutable `ReportScanResult` with `discovered`, `indexed`, `unchanged`, `invalid`, `errors`, `started_at`, and `completed_at`. Discover only `*/*/manifest.json`, sort by POSIX relative path, call manifest validation and the store boundary per manifest, catch errors per version, and cap returned errors at 100 while logging all failures.

Add an operator entry point:

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme-research-report-index")
    parser.add_argument("--root", type=Path, default=SETTINGS.theme_research_report_root)
    parser.add_argument("--service", default=SETTINGS.research_service)
    args = parser.parse_args(argv)
    result = scan_theme_research_report_root(args.root, limits=limits_from_settings(SETTINGS), service=args.service)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.invalid == 0 else 2
```

- [ ] **Step 4: Run indexer tests**

Run:

```bash
pytest tests/test_theme_research_report_index.py -v
```

Expected: PASS with invalid artifacts isolated from valid versions.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/theme_research_report_index.py tests/test_theme_research_report_index.py
git commit -m "feat: scan generated theme reports"
```

## Task 5: Implement admin review transitions and approved read models

**Files:**
- Modify: `src/stock_research/theme_research_report_store.py`
- Modify: `tests/integration/test_theme_research_report_store_postgres.py`

- [ ] **Step 1: Write failing publication tests**

Test admin enforcement, required rejection reason, row-version conflicts, idempotency, and transactional replacement of the current version:

```python
def test_publish_new_version_archives_previous_in_one_transaction(test_service, two_pending_versions, admin_user):
    first = publish_report_version(
        two_pending_versions[0], expected_row_version=1, actor_user_id=admin_user.user_id,
        actor_role="admin", comment="initial", request_id="req-1", idempotency_key="publish-v1",
        service=test_service,
    )
    second = publish_report_version(
        two_pending_versions[1], expected_row_version=1, actor_user_id=admin_user.user_id,
        actor_role="admin", comment="updated research", request_id="req-2", idempotency_key="publish-v2",
        service=test_service,
    )
    assert first["status"] == "published"
    assert second["status"] == "published"
    history = list_approved_report_versions(second["theme_id"], service=test_service)
    assert [row["status"] for row in history] == ["published", "archived"]
```

Assert a non-admin gets `THEME_REPORT_ADMIN_REQUIRED`, stale versions get `THEME_REPORT_VERSION_CONFLICT`, invalid transitions get `THEME_REPORT_STATE_CONFLICT`, and repeated idempotency keys return the original result.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/integration/test_theme_research_report_store_postgres.py -k 'publish or reject or approved' -v
```

Expected: FAIL because review transitions/read models do not exist.

- [ ] **Step 3: Implement review and read functions**

Add these exact public interfaces:

- `publish_report_version(report_version_id, *, expected_row_version, actor_user_id, actor_role, comment, request_id, idempotency_key, service=SETTINGS.research_service) -> dict[str, Any]` returns the safe updated admin row.
- `reject_report_version(report_version_id, *, expected_row_version, actor_user_id, actor_role, reason, request_id, idempotency_key, service=SETTINGS.research_service) -> dict[str, Any]` returns the safe updated admin row.
- `list_admin_report_versions(*, status="pending_review", service=SETTINGS.research_service) -> dict[str, Any]` returns `{"total": int, "items": list[dict]}` and permits only `pending_review` or `rejected` filters.
- `get_admin_report_version(report_version_id, *, service=SETTINGS.research_service) -> dict[str, Any]` returns admin metadata including indexed relative paths and checksums for the dashboard service, but the API adapter must remove those internal fields.
- `list_approved_report_versions(theme_id, *, service=SETTINGS.research_service) -> dict[str, Any]` returns current `published` first, then `archived` versions ordered by publication time descending.
- `get_approved_report_version(theme_id, report_version_id, *, service=SETTINGS.research_service) -> dict[str, Any]` returns one `published` or `archived` row or raises `THEME_REPORT_NOT_FOUND`.

Both mutations must call a shared admin validator, lock the target row `FOR UPDATE`, validate `pending_review` and `row_version`, and write an audit event. Publication must first archive any current version for the same theme, then publish the target in the same transaction. Normal read models select only `status IN ('published', 'archived')` and omit paths, checksums, rejection details, and generator diagnostics.

- [ ] **Step 4: Run publication tests**

Run:

```bash
pytest tests/integration/test_theme_research_report_store_postgres.py -v
```

Expected: PASS for schema, indexing, audit, authorization, rejection, publication, history, concurrency, and idempotency.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/theme_research_report_store.py tests/integration/test_theme_research_report_store_postgres.py
git commit -m "feat: review and publish theme reports"
```

## Task 6: Render reports safely and resolve protected PDF files

**Files:**
- Create: `src/stock_research/dashboard/theme_research_reports.py`
- Create: `tests/test_dashboard_theme_research_reports.py`

- [ ] **Step 1: Write failing rendering and file-boundary tests**

Mock store rows and create indexed fixtures:

```python
def test_render_report_removes_raw_script_and_unsafe_links(tmp_path, monkeypatch):
    markdown = "# Report\n\n<script>alert(1)</script>\n\n[x](javascript:alert(2))"
    row = indexed_row(tmp_path, markdown=markdown, status="published")
    monkeypatch.setattr(service, "get_approved_report_version", lambda *args, **kwargs: row)
    payload = load_published_report_document("theme-a", row["report_version_id"], report_root=tmp_path)
    assert "<h1>Report</h1>" in payload["html"]
    assert "<script" not in payload["html"]
    assert "javascript:" not in payload["html"]
    assert "markdown_relative_path" not in payload
```

Add tests for missing files, changed checksums, escaping indexed paths, absent PDF, valid PDF download metadata, and admin preview of `pending_review`.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_dashboard_theme_research_reports.py -v
```

Expected: FAIL because the dashboard report service does not exist.

- [ ] **Step 3: Implement sanitized Markdown rendering and protected artifact resolution**

Use `MarkdownIt("commonmark", {"html": False, "linkify": True, "typographer": False})`, then sanitize with `nh3.clean()` and an explicit allowlist for headings, paragraphs, lists, tables, blockquotes, code, pre, links, emphasis, and horizontal rules. Add `rel="noopener noreferrer"` to external links.

The service must re-resolve the stored relative path below the configured root, reject symlinks/special files, enforce size limits, and compare the current SHA-256 with the indexed checksum before rendering or streaming. Define stable exceptions mapped later to 404, 409, or 503.

Expose `load_published_report_document(theme_id, report_version_id, *, report_root, service)`, `load_admin_report_document(report_version_id, *, report_root, service)`, `resolve_published_report_pdf(theme_id, report_version_id, *, report_root, service)`, and `resolve_admin_report_pdf(report_version_id, *, report_root, service)`. Document loaders return safe metadata plus `html`; PDF resolvers return `ResolvedPdf(path, filename, media_type="application/pdf")` only after the same boundary and checksum checks.

- [ ] **Step 4: Run rendering tests**

Run:

```bash
pytest tests/test_dashboard_theme_research_reports.py -v
```

Expected: PASS, including sanitization and post-index file-integrity failures.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/theme_research_reports.py tests/test_dashboard_theme_research_reports.py
git commit -m "feat: serve sanitized theme reports"
```

## Task 7: Add the index scheduler and FastAPI endpoints

**Files:**
- Create: `src/stock_research/dashboard/theme_research_report_scheduler.py`
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `tests/test_dashboard_theme_research_reports.py`

- [ ] **Step 1: Write failing API and scheduler tests**

Test these behaviors with dependency functions monkeypatched at the module boundary:

- all report reads require a valid session;
- normal reads return only approved versions;
- pending admin preview requires `admin`;
- publish/reject require admin and CSRF;
- rejection requires a reason;
- PDF returns `Content-Disposition: attachment`;
- report-index diagnostics require admin and expose the latest bounded scan result;
- startup scan executes once and periodic scan stops cleanly.

Example:

```python
def test_admin_publish_requires_admin_and_csrf(client_with_user, pending_report):
    response = client_with_user.post(
        f"/api/admin/theme-research/reports/{pending_report['report_version_id']}/publish",
        json={"expected_row_version": 1, "idempotency_key": "publish-1", "comment": "ok"},
    )
    assert response.status_code == 403


def test_pdf_is_streamed_as_attachment(admin_client, monkeypatch, tmp_path):
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 fixture")
    monkeypatch.setattr(dashboard_app, "resolve_published_report_pdf", lambda *args, **kwargs: ResolvedPdf(pdf, "report.pdf", "application/pdf"))
    response = admin_client.get("/api/research/theme-decomposition/themes/theme-a/reports/report-1/pdf")
    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment;")
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_dashboard_theme_research_reports.py -v
```

Expected: FAIL because routes and scheduler do not exist.

- [ ] **Step 3: Implement the scheduler**

Create a scheduler with `start()`, async `stop()`, `run_once()`, `last_result`, and an async loop using `asyncio.wait_for(stop_event.wait(), timeout=interval)`. `start()` performs one scan through `asyncio.to_thread`, then schedules future scans. Failures are logged and captured in diagnostics; they do not abort FastAPI startup.

- [ ] **Step 4: Wire scheduler and API routes**

In `create_app()`, assign `app.state.theme_research_report_scheduler`. Start and stop it in the existing lifespan beside `public_news_scheduler`.

Add Pydantic request models:

```python
class ThemeResearchReportPublishRequest(BaseModel):
    expected_row_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=200)
    comment: str = Field(default="", max_length=2000)


class ThemeResearchReportRejectRequest(BaseModel):
    expected_row_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=4000)
```

Implement the seven report/read-review endpoints from the design plus `GET /api/admin/theme-research/report-index/status`, which returns the scheduler's latest safe counters, timestamps, and bounded errors. Explicitly call `_current_user_or_401` on normal report endpoints even when global dashboard auth is disabled, `_admin_user_or_403` on admin routes, and `_require_csrf` on both mutations. Map unknown/private versions to 404, stale/invalid transitions to 409, malformed requests to 400/422, and missing/corrupted indexed files to 503.

- [ ] **Step 5: Run API and scheduler tests**

Run:

```bash
pytest tests/test_dashboard_theme_research_reports.py -v
```

Expected: PASS for auth, admin isolation, CSRF, review mutations, PDF streaming, and scheduler lifecycle.

- [ ] **Step 6: Run related backend regressions**

Run:

```bash
pytest tests/test_dashboard_auth_service.py tests/test_dashboard_theme_research.py tests/test_theme_research_report_manifest.py tests/test_theme_research_report_index.py tests/test_dashboard_theme_research_reports.py -v
```

Expected: PASS with no regressions to login or existing Theme Research reads.

- [ ] **Step 7: Commit**

```bash
git add src/stock_research/dashboard/theme_research_report_scheduler.py src/stock_research/dashboard/app.py tests/test_dashboard_theme_research_reports.py
git commit -m "feat: expose reviewed theme report APIs"
```

## Task 8: Enrich theme reads with approved-report status only

**Files:**
- Modify: `src/stock_research/dashboard/theme_research_db.py`
- Modify: `tests/test_dashboard_theme_research.py`

- [ ] **Step 1: Write failing read-model tests**

Seed one published, one pending-only, and one no-report theme. Assert normal theme reads expose only safe summary state:

```python
def test_theme_list_exposes_only_approved_report_summary(monkeypatch):
    payload = list_theme_research_themes()
    published = next(row for row in payload["items"] if row["theme_id"] == "published-theme")
    pending = next(row for row in payload["items"] if row["theme_id"] == "pending-theme")
    assert published["analysis_report"] == {
        "status": "published",
        "report_version_id": "theme_report:published",
        "version": "v1",
        "published_at": "2026-07-31T12:00:00+08:00",
        "has_pdf": True,
    }
    assert pending["analysis_report"] == {"status": "researching"}
    assert "pending_review" not in json.dumps(payload)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_dashboard_theme_research.py -k analysis_report -v
```

Expected: FAIL because the theme payload has no report summary.

- [ ] **Step 3: Add approved-only report joins**

Use a lateral join or one batched query against `research.theme_research_report_version` where `status='published'`. Return `analysis_report.status='published'` with safe identifiers and timestamps when present; otherwise return exactly `{"status": "researching"}`. Do not query or count pending/rejected versions in normal Theme Research payloads.

- [ ] **Step 4: Run read-model tests**

Run:

```bash
pytest tests/test_dashboard_theme_research.py -v
```

Expected: PASS with existing theme/node/source/company payload assertions preserved.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/theme_research_db.py tests/test_dashboard_theme_research.py
git commit -m "feat: expose approved theme report status"
```

## Task 9: Add frontend API types and clients

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/tests/client.test.ts`

- [ ] **Step 1: Write failing client tests**

Assert URL encoding, query construction, CSRF-backed POSTs, and response typing:

```typescript
it('publishes a theme report through the admin endpoint', async () => {
  fetchMock.mockResolvedValueOnce(jsonResponse({ report: { report_version_id: 'r1', status: 'published' } }));
  await publishThemeResearchReport('r1', {
    expected_row_version: 1,
    idempotency_key: 'publish-r1',
    comment: 'approved'
  });
  expect(fetchMock).toHaveBeenCalledWith(
    '/api/admin/theme-research/reports/r1/publish',
    expect.objectContaining({ method: 'POST' })
  );
});
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd dashboard && pnpm test -- tests/client.test.ts
```

Expected: FAIL because report API functions/types do not exist.

- [ ] **Step 3: Add exact TypeScript contracts**

Define `ThemeResearchReportSummary`, `ThemeResearchReportVersion`, `ThemeResearchReportDocument`, `ThemeResearchReportListResponse`, `AdminThemeResearchReport`, `AdminThemeResearchReportListResponse`, `ThemeResearchReportPublishRequest`, and `ThemeResearchReportRejectRequest`. Normal-user types must not contain relative paths, checksums, rejection reasons, or internal diagnostics.

Add:

```typescript
export function fetchThemeResearchReports(themeId: string): Promise<ThemeResearchReportListResponse>;
export function fetchThemeResearchReportDocument(themeId: string, reportVersionId: string): Promise<ThemeResearchReportDocument>;
export function themeResearchReportPdfUrl(themeId: string, reportVersionId: string): string;
export function fetchAdminThemeResearchReports(status?: 'pending_review' | 'rejected'): Promise<AdminThemeResearchReportListResponse>;
export function fetchAdminThemeResearchReport(reportVersionId: string): Promise<ThemeResearchReportDocument>;
export function publishThemeResearchReport(reportVersionId: string, payload: ThemeResearchReportPublishRequest): Promise<{ report: AdminThemeResearchReport }>;
export function rejectThemeResearchReport(reportVersionId: string, payload: ThemeResearchReportRejectRequest): Promise<{ report: AdminThemeResearchReport }>;
```

Reuse the existing CSRF-aware JSON POST helper rather than calling `fetch` directly.

- [ ] **Step 4: Run client tests and typecheck**

Run:

```bash
cd dashboard && pnpm test -- tests/client.test.ts && pnpm exec tsc --noEmit
```

Expected: PASS with no TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/tests/client.test.ts
git commit -m "feat: add theme report dashboard client"
```

## Task 10: Add the approved report reader to Theme Research

**Files:**
- Create: `dashboard/src/components/ThemeResearchReportReader.tsx`
- Modify: `dashboard/src/components/ThemeResearchWorkspace.tsx`
- Modify: `dashboard/src/styles.css`
- Create: `dashboard/tests/theme-research-report-reader.test.tsx`
- Modify: `dashboard/tests/theme-research-workspace.test.tsx`

- [ ] **Step 1: Write failing reader/workspace tests**

Cover:

- `研究中` when there is no approved report;
- `已发布`, online-read, and PDF actions for an approved report;
- history selector contains approved versions only;
- sanitized HTML is rendered;
- reader loading, 404, and 503 states;
- no `生成报告` or `上传报告` controls.

Example:

```tsx
it('shows published report actions without generation or upload controls', async () => {
  render(<ThemeResearchWorkspace pathname="/theme-research/theme-a" onNavigate={navigate} onOpenStock={vi.fn()} />);
  expect(await screen.findByText('分析报告')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '在线阅读' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: '下载 PDF' })).toHaveAttribute('href', expect.stringContaining('/pdf'));
  expect(screen.queryByText('生成报告')).not.toBeInTheDocument();
  expect(screen.queryByText('上传报告')).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd dashboard && pnpm test -- tests/theme-research-report-reader.test.tsx tests/theme-research-workspace.test.tsx
```

Expected: FAIL because report components and report route support do not exist.

- [ ] **Step 3: Implement the reader and route**

Extend Theme Research routing to accept:

```text
/theme-research/{themeId}/report/{reportVersionId}
```

The overview report card navigates there. `ThemeResearchReportReader` fetches the approved list and selected document, renders server-sanitized `html` inside a dedicated article element, offers an approved-history selector, and uses the protected PDF endpoint. It must not construct or display filesystem paths.

Use `dangerouslySetInnerHTML` only for the backend-sanitized `html` field and document that trust boundary in one concise code comment.

- [ ] **Step 4: Add responsive reader styles**

Add `.theme-report-card`, `.theme-report-reader`, `.theme-report-article`, `.theme-report-version-select`, and table/code overflow rules consistent with the existing Theme Research visual system. Ensure headings and long tables remain readable at narrow widths.

- [ ] **Step 5: Run component tests and build**

Run:

```bash
cd dashboard && pnpm test -- tests/theme-research-report-reader.test.tsx tests/theme-research-workspace.test.tsx && pnpm build
```

Expected: PASS; production TypeScript/Vite build succeeds.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/components/ThemeResearchReportReader.tsx dashboard/src/components/ThemeResearchWorkspace.tsx dashboard/src/styles.css dashboard/tests/theme-research-report-reader.test.tsx dashboard/tests/theme-research-workspace.test.tsx
git commit -m "feat: add theme report reader"
```

## Task 11: Add the admin-only report review workspace

**Files:**
- Create: `dashboard/src/components/ThemeResearchReportReviewWorkspace.tsx`
- Modify: `dashboard/src/components/AppShell.tsx`
- Modify: `dashboard/src/styles.css`
- Create: `dashboard/tests/theme-research-report-review.test.tsx`
- Modify: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Write failing admin UI tests**

Assert admin-only navigation, queue loading, preview, publish, mandatory rejection reason, successful refresh, 409 conflict feedback, and no generate/upload controls:

```tsx
it('shows report review only to admins', () => {
  const { rerender } = render(<AppShell currentUser={userAccount} {...shellProps} />);
  expect(screen.queryByText('报告审核')).not.toBeInTheDocument();
  rerender(<AppShell currentUser={adminAccount} {...shellProps} />);
  expect(screen.getByText('报告审核')).toBeInTheDocument();
});


it('requires a reason before rejecting', async () => {
  render(<ThemeResearchReportReviewWorkspace />);
  await screen.findByText('AI 电力主题分析报告');
  fireEvent.click(screen.getByRole('button', { name: '驳回' }));
  expect(await screen.findByText('请填写驳回原因')).toBeInTheDocument();
  expect(api.rejectThemeResearchReport).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd dashboard && pnpm test -- tests/theme-research-report-review.test.tsx tests/app-shell.test.tsx
```

Expected: FAIL because the workspace and route do not exist.

- [ ] **Step 3: Implement admin routing and review workspace**

Add `themeReportReview` to `WorkspaceMode`, `/admin/theme-research/report-review` path handling, and this admin item:

```typescript
{ mode: 'themeReportReview', label: '报告审核', ariaLabel: 'Open Theme Research report review workspace' }
```

The review workspace loads `pending_review`, selects a report, loads the sanitized preview, displays safe generator/version metadata, offers PDF download, and posts publish/reject mutations with `crypto.randomUUID()` idempotency keys and the current `row_version`. After success, refresh the queue. On 409, show `报告状态已被其他管理员更新，请刷新后重试` and reload the selected row.

Do not include generation, upload, filesystem, or editing controls.

- [ ] **Step 4: Add review queue styles**

Add a responsive two-column queue/preview layout, collapse to one column below the existing dashboard mobile breakpoint, and reuse existing button/status styles where possible.

- [ ] **Step 5: Run admin UI tests and build**

Run:

```bash
cd dashboard && pnpm test -- tests/theme-research-report-review.test.tsx tests/app-shell.test.tsx && pnpm build
```

Expected: PASS; user accounts cannot see the route and admin accounts can review reports.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/components/ThemeResearchReportReviewWorkspace.tsx dashboard/src/components/AppShell.tsx dashboard/src/styles.css dashboard/tests/theme-research-report-review.test.tsx dashboard/tests/app-shell.test.tsx
git commit -m "feat: add admin theme report review"
```

## Task 12: Add end-to-end acceptance, operations documentation, and final verification

**Files:**
- Modify: `dashboard/tests/theme-research-full-flow.spec.ts`
- Create: `docs/ops/theme-research-analysis-report-publication.md`

- [ ] **Step 1: Extend the Playwright flow**

Add a fixture-backed flow that:

1. logs in as a normal user and confirms the pending report is undiscoverable;
2. logs in as admin and opens `报告审核`;
3. previews and publishes the report;
4. logs back in as the normal user;
5. opens Theme Research, reads the report, and verifies the PDF download response;
6. indexes a second version and confirms version one stays current until approval;
7. publishes version two and confirms version one remains in history.

Use API seeding/cleanup helpers scoped to the test database and temporary report root; do not depend on production artifacts.

- [ ] **Step 2: Write the operations runbook**

Document exact production settings, expected directory/manifest layout, permissions, schema command, one-shot scan command, diagnostic output, canary publication, rollback, and recovery from checksum/version conflicts. Include these commands:

```bash
python -m stock_research.theme_research_report_schema --apply
python -m stock_research.theme_research_report_index --root /absolute/report/root
```

State explicitly that application releases must preserve the configured report root and that the web process only needs read access to finalized versions.

- [ ] **Step 3: Run focused backend verification**

Run:

```bash
pytest tests/test_theme_research_report_manifest.py tests/test_theme_research_report_index.py tests/test_dashboard_theme_research_reports.py tests/test_dashboard_theme_research.py tests/test_dashboard_auth_service.py -v
```

Expected: PASS.

- [ ] **Step 4: Run PostgreSQL integration verification**

Run:

```bash
pytest tests/integration/test_theme_research_report_store_postgres.py -v
```

Expected: PASS against the dedicated test service.

- [ ] **Step 5: Run frontend verification**

Run:

```bash
cd dashboard && pnpm test -- tests/client.test.ts tests/theme-research-report-reader.test.tsx tests/theme-research-report-review.test.tsx tests/theme-research-workspace.test.tsx tests/app-shell.test.tsx && pnpm build
```

Expected: all Vitest tests pass and the production build succeeds.

- [ ] **Step 6: Run Playwright acceptance**

Run:

```bash
cd dashboard && pnpm exec playwright test tests/theme-research-full-flow.spec.ts
```

Expected: PASS for pending isolation, admin publication, normal-user reading/download, and immutable version replacement.

- [ ] **Step 7: Verify the absence of prohibited controls and path leakage**

Run:

```bash
rg -n "生成报告|上传报告|markdown_relative_path|pdf_relative_path|manifest_relative_path" dashboard/src/components/ThemeResearch* dashboard/src/api/types.ts
```

Expected: no generate/upload labels in the new Theme Research report components; relative-path fields do not appear in normal-user TypeScript contracts or rendered components.

- [ ] **Step 8: Commit**

```bash
git add dashboard/tests/theme-research-full-flow.spec.ts docs/ops/theme-research-analysis-report-publication.md
git commit -m "test: verify theme report publication flow"
```

## Final Acceptance Checklist

- [ ] A valid finalized manifest is indexed automatically as `pending_review`.
- [ ] Repeated scans are no-ops and conflicting bytes under the same version are rejected.
- [ ] Pending and rejected versions cannot be discovered by normal accounts.
- [ ] Only admin accounts see `报告审核` and can publish/reject with CSRF protection.
- [ ] Publishing a new version archives the previous current version atomically.
- [ ] Approved Markdown is sanitized and readable online.
- [ ] Optional PDF downloads pass through an authenticated endpoint.
- [ ] Server paths and checksums never appear in normal-user payloads.
- [ ] Theme Research contains no generation or upload control.
- [ ] Backend, PostgreSQL integration, frontend, build, and Playwright suites pass.
