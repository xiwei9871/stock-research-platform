# Dashboard Cache Refresh Design

**Goal:** Ensure the external dashboard stops serving a stale application shell after a deployment and automatically reloads an already-open, updated client when it regains focus after a later release.

## Root Cause

The production Nginx configuration gives hashed files under `/assets/` a long immutable cache lifetime, which is correct, but it does not define an explicit cache policy for `/` or `/index.html`. A browser or intermediary can therefore reuse an older HTML document that still references an older immutable JavaScript bundle. The new account controls are deployed, but a user who receives the stale HTML continues to run the old bundle.

## Cache Policy

- `/`, `/index.html`, SPA fallback responses, and `/release.json` return `Cache-Control: no-store, no-cache, must-revalidate`.
- Hashed files under `/assets/` keep their existing 30-day `public, immutable` policy.
- API proxy behavior is unchanged.

This separates the mutable application entry point from immutable content-addressed assets. A normal navigation or refresh always revalidates the entry point and receives the current asset filenames.

## Runtime Release Detection

The built JavaScript already receives `VITE_RELEASE_ID`, and Vite emits the same value in `/release.json`. The application installs one release watcher at the root:

1. When the window gains focus, or the document becomes visible, request `/release.json` with a timestamp query and `cache: 'no-store'`.
2. Ignore the check when the embedded release ID is empty, as in normal local development.
3. If the returned non-empty release ID differs from the embedded ID, call `window.location.reload()` once.
4. If IDs match, the request fails, or the response is malformed, leave the current page unchanged.
5. Deduplicate overlapping focus and visibility events and prevent repeated reload requests.

The watcher deliberately does not poll while the user is actively working. It checks at a natural interruption boundary—returning to the tab—so it does not unexpectedly discard in-progress input.

## Component Ownership

`App` owns installation and cleanup of the release watcher because it must operate on both the login page and authenticated dashboard. Authentication components and `AppShell` remain unaware of deployment metadata.

The release-checking logic lives in a small framework-independent module. React only installs it in an effect, while unit tests inject `fetch`, release ID, event targets, and reload behavior without mutating browser globals.

## Error Handling

Release checks are best-effort and silent. A transient network error must not block login or dashboard use. The next focus or visible event retries automatically.

## Verification

- Unit tests cover empty current release, same and different releases, hidden/visible transitions, overlapping events, malformed responses, and request failures.
- Release-script tests assert no-store rules for mutable entry points and preservation of immutable asset caching.
- The complete dashboard test suite and production build must pass.
- After deployment, external response headers for `/`, `/index.html`, and `/release.json` must show the no-store policy, while a hashed asset remains immutable.
- The deployed `/release.json`, API readiness provenance, and built bundle must identify the same release commit.

## Rollout Note

An already-open client running the pre-watcher JavaScript cannot discover this change by itself. After this deployment, that client needs one ordinary refresh; a forced cache-clearing refresh should not be necessary because the HTML response is now no-store. Once the new client has loaded, later releases are detected automatically when the tab regains focus.
