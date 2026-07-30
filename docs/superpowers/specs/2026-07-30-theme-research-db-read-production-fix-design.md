# Theme Research Production DB Read Fix Design

**Goal:** Restore the external Theme Research workspace from the existing PostgreSQL canonical data without making optional artifact scoring support a hard runtime dependency.

## Confirmed Root Cause

The production `/api/research/theme-decomposition/themes` request returns HTTP 500 because `THEME_RESEARCH_READ_SOURCE=artifact`. The canonical API image contains application source but not `artifacts/theme_decomposition`, so artifact loading fails with `PRIORITY_POLICY_DIRECTORY_NOT_FOUND`.

PostgreSQL is healthy and contains 2 themes, 34 nodes, 24 sources, 12 claims, and 4 company mappings. Production documentation already declares PostgreSQL authoritative and artifact reads an emergency fallback.

The existing DB loader has a second defect: `load_db_context()` calls the complete artifact package loader before reading DB content. That incorrectly makes static policy and crosswalk files mandatory even in DB mode. The file already contains `_build_scoped_priority_context()`, which intentionally treats this scoring support as optional and returns `priority_status="unavailable"` when it cannot be loaded.

## Approved Architecture

1. Change `load_db_context()` to build the canonical theme and mapping packages from PostgreSQL first.
2. Pass DB nodes and mappings to `_build_scoped_priority_context()`.
3. Return DB-backed themes, nodes, sources, claims, and company mappings regardless of whether optional policy/crosswalk support exists.
4. When support exists, preserve node priorities, company priorities, evidence gaps, and review queue. When absent, return empty priority collections and `priority_status="unavailable"` without raising.
5. Change the production environment from `THEME_RESEARCH_READ_SOURCE=artifact` to `db` and restart through the canonical release workflow.

No database rows are created, changed, imported, or deleted.

## Rejected Alternatives

- Copying the full artifact tree into the image keeps production dependent on file snapshots and conflicts with PostgreSQL authority.
- Manually copying files to the server would be lost or drift during later releases.

## Testing

- Add a failing DB-context test where the full artifact loader raises `FileNotFoundError`; DB themes must still be returned with unavailable priority support.
- Keep parity behavior covered when optional support is available.
- Run the focused Theme Research DB/API tests and the complete backend test file covering dashboard theme research.
- Run the complete dashboard frontend suite and production build because the release changes both API behavior and deployment state.
- After deployment, verify the themes endpoint returns 200, the Theme Research list renders two themes, a theme detail opens, and API logs contain no new artifact-directory exception.

## Operational Rollback

If the DB read path fails independently, restore the previous production environment value and restart the API. This rollback changes only the read source and does not mutate canonical data.
