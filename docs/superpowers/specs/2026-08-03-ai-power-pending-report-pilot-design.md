# AI Power Pending Report Pilot Design

## Status

Approved in conversation on 2026-08-03. This document is awaiting the user's written-spec review before implementation planning begins.

## Goal

Generate one production-quality, traceable Theme Research report draft for `ai_power_value_capture_v1`, register it as exactly one immutable `pending_review` version, and make it available to the `admin` account in the Theme Research report-review workspace without publishing it to ordinary users.

## Current State

- Production currently runs release `082b9ca8879edf5ea603c33099124f52badb01e7`.
- That release does not expose the Theme Research report-review API or index diagnostics endpoints.
- Production's fixed report root contains no report files.
- `research.theme_research_report_version` exists but contains zero rows.
- The complete manifest, index, PostgreSQL review workflow, admin UI, permission boundaries, and release gates already exist on `release/theme-research-reports-20260801`.
- No real Theme Research narrative-report generator exists yet; current report tests use fixtures.

The implementation must preserve all changes in the current production release. It must not deploy an older branch wholesale or roll back the dashboard synchronization schedule change introduced by `082b9ca8`.

## Confirmed Product Decisions

- The pilot theme is `ai_power_value_capture_v1` (AI power-supply value chain).
- The pilot is a formal review draft based only on existing canonical Theme Research artifacts and evidence already stored by the system.
- The pilot does not perform fresh internet research or introduce new external sources.
- The dashboard continues to provide no report-generation or report-upload controls.
- The report is generated in the backend, finalized under the fixed report root, and indexed through the existing manifest contract.
- The first pilot is Markdown plus `manifest.json`. PDF generation is deferred to a later immutable version so Chinese-font/PDF rendering cannot block the first review canary.
- The generated version must enter `pending_review`; it must not be automatically published.
- This delivery stops after verifying that `admin` can open and review the draft. It does not approve or reject the report.
- Ordinary authenticated users must not discover or read the pending version.

## Options Considered

### 1. Restore the formal workflow and generate a Markdown pilot

This is the selected approach. It restores the already-built report workflow on top of the current production baseline, adds one deterministic generator, produces an immutable Markdown report and manifest, and indexes the result through the authorized indexer service.

Benefits:

- smallest production-safe scope;
- preserves the designed audit, checksum, role, and review boundaries;
- creates a reproducible canary rather than a one-off database record;
- avoids Chinese PDF rendering becoming a prerequisite for admin review.

### 2. Restore the workflow and require Markdown plus PDF immediately

This gives a fuller reviewer experience but adds font discovery, renderer packaging, PDF reproducibility, and production rendering failure modes. It is deferred until the Markdown review path is proven.

### 3. Insert a pending row directly into PostgreSQL

Rejected. It bypasses filesystem finalization, manifest validation, checksums, indexer authorization, and the initial audit event. It would not prove the production workflow.

## Architecture

### Production integration baseline

Create an isolated release branch/worktree from the current production commit `082b9ca8`. Integrate the existing Theme Research report publication commits onto that baseline, resolving conflicts without discarding production scheduler or dashboard changes. The resulting release must pass the existing report schema, role-isolation, read-only mount, API, frontend, and external release gates.

The implementation must not use the dirty primary worktree at `/Users/xiwei/stock_research` for feature edits. Existing unrelated changes there belong to the user and must remain untouched.

### Pilot generator

Add a focused backend module and operator command for generating one report version. The public generation interface accepts:

- canonical repository/artifact root;
- report output root;
- `theme_id`, restricted in this pilot to `ai_power_value_capture_v1`;
- explicit immutable version, initially `2026-08-03.1`;
- explicit generation timestamp and pipeline run identifier when deterministic tests require them.

The generator reads the existing canonical packages through their validated loaders instead of parsing arbitrary JSON independently:

- theme and industry-chain nodes;
- company mappings;
- node and company research priorities;
- technology-bottleneck crosswalk context where applicable;
- evidence items, claims, sources, and evidence gaps.

It must not mutate canonical Theme Research artifacts, review-universe data, scores, signals, admissions, or user data.

### Report structure

The generated Chinese Markdown contains these fixed sections:

1. title, version, generated time, and research-only notice;
2. executive summary and scope boundary;
3. AI power-supply industry-chain structure;
4. value-capture and bottleneck analysis;
5. power supply, liquid cooling, grid connection, and data-center supporting links;
6. key company mappings with materiality and evidence status;
7. evidence strengths and unresolved evidence gaps;
8. risks, counter-evidence, and limitations;
9. source index with stable source/evidence identifiers;
10. admin review checklist.

The report must contain no trading instruction, target price, buy/sell recommendation, automatic admission decision, or claim that exceeds the underlying evidence status.

### Atomic artifact finalization

The generator writes only inside the configured report root:

```text
<report-root>/
  .staging-<run-id>/
    report.md
    manifest.json
  ai_power_value_capture_v1/
    2026-08-03.1/
      report.md
      manifest.json
```

Required sequence:

1. validate the report root, theme ID, version, and absence of an existing final version;
2. create a private hidden staging directory on the same filesystem;
3. write final UTF-8 Markdown bytes;
4. calculate the Markdown SHA-256;
5. write the v1 manifest last, including generator provenance and source-artifact metadata;
6. fsync files and relevant directories where supported;
7. set the expected read-only final permissions;
8. atomically rename the complete staging version into `<theme_id>/<version>`;
9. never modify finalized bytes.

On any error before the atomic rename, the final version directory must not exist. Re-running with an existing final version must fail closed rather than overwrite it.

### Indexing and review state

After artifact finalization, run the existing one-shot indexer using `theme_research_report_indexer_app` through the configured index service. Manifest validation and the registration stored procedure create exactly one version row with:

- `theme_id = ai_power_value_capture_v1`;
- `version = 2026-08-03.1`;
- `status = pending_review`;
- one initial system audit event.

The generator itself must not write report tables. Repeated indexing of identical bytes returns `unchanged`; checksum or identity conflicts fail without changing the existing row.

### Admin experience and access control

The restored admin route `/admin/theme-research/report-review` lists the pending pilot. `admin` can open the report metadata and safely rendered Markdown preview. The review controls remain available, but this delivery does not invoke publish or reject.

Pending report list, document, and artifact endpoints remain admin-only. Ordinary authenticated users receive no pending version in theme report history and cannot retrieve the pending document directly. There remains no frontend generation or upload button.

## Error Handling

- Missing or invalid canonical theme artifacts: stop before creating a final report directory.
- Unsupported theme ID or unsafe version/path: reject before filesystem writes.
- Existing final version: fail closed; require a new immutable version.
- Markdown generation or checksum failure: remove only the private staging directory and leave no final version.
- Manifest validation failure: do not index.
- Unknown theme, checksum conflict, or database registration failure: retain finalized files for operator diagnosis but do not bypass the indexer or edit PostgreSQL manually.
- Release schema, mount, service-role, API, or external gate failure: do not claim production completion; preserve the previous running release when the deployment mechanism permits.
- Admin page or authorization regression: stop before generating the production pilot if the isolated end-to-end review canary fails.

## Testing Strategy

### Generator unit tests

- deterministic Markdown for fixed canonical inputs and timestamp;
- all required sections and stable evidence/source identifiers are present;
- unsupported themes and unsafe versions are rejected;
- trading-language guardrails reject prohibited output;
- manifest contains the exact Markdown checksum and generator provenance;
- finalization is atomic and never overwrites an existing version;
- a generation failure leaves no final version directory.

### Existing report workflow tests

- manifest validation and file-boundary tests;
- indexer idempotency and conflict tests;
- PostgreSQL schema, role separation, pending registration, audit events, and admin transitions;
- API tests for admin pending list/preview and ordinary-user invisibility;
- frontend tests for the admin review queue and absence of generate/upload controls;
- isolated full-flow Playwright test.

### Release verification

- build from a clean current-production-based release worktree;
- verify report root is the configured read-only API mount;
- verify schema version and independent runtime/indexer/reviewer identities;
- verify external readiness and release provenance;
- verify the admin pending API returns exactly the pilot report;
- verify a normal user cannot discover or read it;
- inspect the actual admin review page in the browser.

## Deployment Sequence

1. integrate and verify the report workflow on top of `082b9ca8`;
2. deploy the code and schema with the report root still empty;
3. verify admin review APIs and UI are present with an empty queue;
4. run the pilot generator against the production canonical artifact root and fixed report root;
5. run the authorized one-shot indexer;
6. verify exactly one `pending_review` database row and initial audit event;
7. verify admin preview and ordinary-user invisibility;
8. leave the report pending for the user's human review.

## Acceptance Criteria

- Production code includes the current `082b9ca8` changes and the formal Theme Research report workflow.
- The fixed report root contains exactly one finalized pilot version directory for `ai_power_value_capture_v1/2026-08-03.1`.
- The pilot directory contains valid immutable `report.md` and `manifest.json` files with matching checksums.
- PostgreSQL contains exactly one new report version in `pending_review` and its initial system audit event.
- The `admin` account sees “AI供电产业链分析报告” in the report-review queue and can open the complete Markdown preview.
- An ordinary authenticated user cannot list or retrieve the pending report.
- The frontend exposes no generate or upload control.
- The report remains pending; no approval, rejection, archive, or public publication occurs during this delivery.
- Internal and external deployments report the same release ID and pass their release gates.

## Deferred Work

- fresh external research and source acquisition;
- Chinese PDF rendering and download for this report;
- automatic recurring generation for all themes;
- reviewer edits inside the dashboard;
- automatic publication;
- generation/upload controls in the frontend.
