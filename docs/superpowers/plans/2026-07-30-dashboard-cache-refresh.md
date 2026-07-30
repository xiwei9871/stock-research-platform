# Dashboard Cache Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent stale dashboard entry documents after release and reload an updated open client when it regains focus.

**Architecture:** Nginx marks mutable entry responses and release metadata as no-store while retaining immutable caching for hashed assets. A framework-independent release watcher compares the bundle's embedded `VITE_RELEASE_ID` with `/release.json`; `App` installs the watcher for the full login/authenticated lifecycle.

**Tech Stack:** React 19, TypeScript, Vite, Vitest, Pytest, Nginx, canonical dashboard release scripts.

---

## Task 1: Specify the Mutable and Immutable Cache Contract

**Files:**
- Modify: `tests/test_dashboard_release_scripts.py`
- Modify: `deploy/dashboard-nginx.conf`

- [ ] Add a failing test that requires `no-store, no-cache, must-revalidate` for `/index.html`, `/release.json`, and SPA fallback responses, while retaining `public, immutable` under `/assets/`.
- [ ] Run the focused Pytest test and confirm it fails against the existing config.
- [ ] Update the Nginx configuration with exact-match locations for mutable files and a no-store SPA fallback policy.
- [ ] Run the focused test again and confirm it passes.

## Task 2: Specify Runtime Release Detection

**Files:**
- Create: `dashboard/tests/releaseRefresh.test.ts`
- Create: `dashboard/src/releaseRefresh.ts`

- [ ] Add failing unit tests for an empty current release, matching and different releases, visible/hidden events, overlapping checks, malformed metadata, fetch failure, cleanup, and one-time reload behavior.
- [ ] Run only `releaseRefresh.test.ts` and confirm RED because the release watcher does not exist.
- [ ] Implement an injectable `installReleaseRefresh` function that registers focus/visibility listeners, fetches cache-busted release metadata with `cache: 'no-store'`, deduplicates checks, silently retries after errors, reloads once on mismatch, and returns cleanup.
- [ ] Run the focused unit tests and confirm GREEN.

## Task 3: Install the Watcher at the Application Root

**Files:**
- Modify: `dashboard/src/App.tsx`
- Create or modify: `dashboard/src/vite-env.d.ts`
- Modify: `dashboard/tests/canonical-frontend-entry.test.ts`

- [ ] Add a failing source-level or component test proving `App` installs the release watcher with `import.meta.env.VITE_RELEASE_ID` and cleans it up.
- [ ] Run the focused test and confirm RED.
- [ ] Add the root `useEffect`, pass the embedded release ID, and return the watcher cleanup.
- [ ] Add Vite client type declarations if required by TypeScript.
- [ ] Run the focused test and TypeScript build checks and confirm GREEN.

## Task 4: Verify the Complete Change

**Files:**
- Verify all modified files.

- [ ] Run `rtk git diff --check`.
- [ ] Run the complete dashboard Vitest suite.
- [ ] Run the focused release-script Pytest coverage.
- [ ] Run the production dashboard build with a non-empty test release ID and inspect `dist/release.json`.
- [ ] Review the final diff against the approved design.

## Task 5: Publish and Verify Externally

**Files:**
- Use: `deploy/sync_dashboard_release.sh`
- Use: `deploy/check_dashboard_release.sh`

- [ ] Commit the implementation on `feat/dashboard-cache-refresh`.
- [ ] Fast-forward the clean canonical release root to the feature branch commit.
- [ ] Run the canonical release sync with the production environment file and expected trade date.
- [ ] Confirm the release gate reports the new release commit.
- [ ] Confirm external `/`, `/index.html`, and `/release.json` responses include the no-store policy.
- [ ] Confirm an external hashed asset still returns immutable caching.
- [ ] Confirm the external release metadata and API readiness provenance match the deployed commit.
