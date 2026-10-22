# 02 — PDF Access Security Review (M0.6, task F)

Date: 2026-10-20. Branch: `audit/tech-strategy-m0-20261019` @ `1149c763`.

## Verdict: CONFIRMED EXPOSURE — remediation designed; **no code changed; fix ships under separate approval**

## Findings (verified against code + live prod)

1. **`public_access` is stored and displayed but never enforced on the PDF path.**
   `load_research_report_pdf_path` (`dashboard/research_reports.py:259`) selects only
   `source_url, metadata` — `public_access` is not in the query — and hands the file to
   `FileResponse` (`app.py` `/api/research-reports/{id}/pdf`). The flag IS selected into
   list/document payloads (`:130,:188,:230,:253`) — informational only.
2. **Dashboard auth is off in production.** `dashboard_auth_required` defaults `False`
   (`config.py:103`); the `api-1` container has no `STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED`
   env; the middleware (`app.py:694`) is therefore inert. Live check 2026-10-20:
   `GET /api/research-reports?limit=1` → **200** without credentials
   (`/api/auth/me` → 401 only because that endpoint checks its own session).
3. **Report IDs are enumerable.** The unauthenticated list API exposes `report_id`s; each
   ID then serves its PDF. All 107 imported yanbaoke PDFs carry `public_access=false`
   (paid-license content) and are currently world-readable by anyone who can reach
   `https://stock.manqiaotechnology.com`.

## Blast radius

Metadata/search APIs were presumably intended open (the site is public-facing); the
license exposure is the PDF bytes. The `source_url` fallback inside
`_pdf_path_candidates` can also return a non-PDF URL — worth confirming the route only
serves resolved local PDF paths (`_safe_existing_pdf_path` does gate to existing files).

## Minimal fix proposal (separate approval package, NOT mixed with regime release)

Two-line-of-defense change, no schema migration:

1. In `load_research_report_pdf_path`: add `public_access` to the SELECT; if the report is
   `public_access=false`, require a valid dashboard session — return `None` (route → 404)
   or raise 403. Keep `public_access=true` rows open.
2. Document/enforce at the route: `research_report_pdf` checks session only when needed —
   avoids forcing login on the public catalog.
3. Regression tests (test-first): unauthenticated fetch of a `public_access=false` report
   → 401/403/404; `public_access=true` → 200; authenticated session → 200 for both; list
   API unchanged.
4. Deploy note: enabling `STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED=true` is the alternative
   (gates all `/api/*`) — bigger blast radius, not recommended alone since public catalog
   browsing is a product feature.

## Data created during review

None beyond this document. No logs of report IDs, no config changes, no prod writes.
The interim state (PDFs readable) is documented risk pending approval — flagging for
prioritization given paid-license content exposure.
