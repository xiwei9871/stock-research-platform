# R2B External Evidence Acquisition Phase B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover auditable direct and manual evidence acquisition without weakening SSRF protection or starting the AI PCB research smoke batch.

**Architecture:** Extend the existing R2A discovery, snapshot, immutable storage, and normalization pipeline. Add standalone Schema 2.3 acquisition records, explicit provider/network modes, append-only attempts, formal local import, controlled diagnostics, and optional browser/Docling adapters. Research conclusions and research versions remain outside this implementation.

**Tech Stack:** Python 3.14, requests, jsonschema Draft 2020-12, pypdf, optional Playwright, optional Docling, pytest.

---

### Task 1: Freeze Scope

**Files:**
- Create: `artifacts/research_projects/v2_1/acquisition/phase_b_exact_allowlist.json`
- Modify: `tests/test_research_project_v2_1_r2b_scope_guard.py`

- [ ] Add the exact allowlist before production implementation.
- [ ] Test that every `baseline..HEAD` path is listed and every forbidden prefix remains untouched.
- [ ] Commit the governance boundary separately.

### Task 2: Schema 2.3 and Failure Taxonomy

**Files:**
- Create: `artifacts/research_projects/v2_1/schema/definitions_acquisition_v2_3.schema.json`
- Create: `artifacts/research_projects/v2_1/schema/acquisition_attempt_v2_3.schema.json`
- Create: `artifacts/research_projects/v2_1/schema/evidence_artifact_v2_3.schema.json`
- Create: `artifacts/research_projects/v2_1/schema/manual_import_request_v2_3.schema.json`
- Create: `artifacts/research_projects/v2_1/schema/acquisition_checkpoint_v2_3.schema.json`
- Create: `artifacts/research_projects/v2_1/schema/provider_diagnostic_v2_3.schema.json`
- Create: `src/stock_research/research_project_v2_1/acquisition_failures.py`
- Modify: `src/stock_research/research_project_v2_1/schema.py`
- Test: `tests/test_research_project_v2_1_acquisition_schema.py`
- Test: `tests/test_research_project_v2_1_acquisition_failures.py`

- [ ] Write schema and classification tests and verify they fail because the contracts do not exist.
- [ ] Add only the approved standalone objects and failure codes.
- [ ] Keep the 2.1/2.2 schema dispatch unchanged and add 2.3 standalone dispatch.
- [ ] Verify deterministic validation and failure mapping.
- [ ] Commit schema and taxonomy.

### Task 3: Provider Contracts and Immutable Acquisition Storage

**Files:**
- Create: `src/stock_research/research_project_v2_1/acquisition_contracts.py`
- Create: `src/stock_research/research_project_v2_1/acquisition_storage.py`
- Modify: `src/stock_research/research_project_v2_1/layout.py`
- Test: `tests/test_research_project_v2_1_acquisition_storage.py`

- [ ] Write failing tests for provider results, attempt identity, immutable writes, duplicate acceptance, collision rejection, and partial cleanup.
- [ ] Implement provider/request/result dataclasses and protocols.
- [ ] Implement canonical attempt/checkpoint/raw metadata storage under the layered artifact root.
- [ ] Verify atomic and immutable behavior.
- [ ] Commit contracts and storage.

### Task 4: Explicit Direct HTTP Provider

**Files:**
- Create: `src/stock_research/research_project_v2_1/acquisition_http.py`
- Modify: `src/stock_research/research_project_v2_1/snapshot.py`
- Test: `tests/test_research_project_v2_1_acquisition_http.py`

- [ ] Write failing tests for `trust_env=False`, environment proxy opt-in, no fallback, bounded retry, structured failures, redirect safety, size, MIME, empty content, and attempt persistence.
- [ ] Add an injectable requests Session to the existing transport without changing global requests state.
- [ ] Implement direct provider orchestration around `snapshot_candidate`.
- [ ] Preserve every provider call as an independent attempt.
- [ ] Verify local controlled-server and mock-transport tests.
- [ ] Commit direct HTTP provider.

### Task 5: Manual / Local Import Provider

**Files:**
- Create: `src/stock_research/research_project_v2_1/acquisition_import.py`
- Test: `tests/test_research_project_v2_1_acquisition_import.py`

- [ ] Write failing tests for PDF, HTML, TXT/Markdown, JSON, CSV, incomplete metadata, hashing, duplicate content, provenance, unsupported type, and missing file.
- [ ] Implement bounded safe local reads and MIME validation.
- [ ] Publish immutable raw artifacts through the common storage contract.
- [ ] Return `pending_assessment` without creating an assessment.
- [ ] Commit local import provider.

### Task 6: Normalization and Acquisition Checkpoint

**Files:**
- Create: `src/stock_research/research_project_v2_1/acquisition_normalize.py`
- Test: `tests/test_research_project_v2_1_acquisition_normalize.py`

- [ ] Write failing tests proving raw success and normalization success are independent.
- [ ] Adapt the existing deterministic normalizer and persist parser identity/version/configuration.
- [ ] Add checkpoint assembly that references attempts, artifacts, normalized documents, and pending assessment state.
- [ ] Verify normalization failure preserves raw artifacts.
- [ ] Commit normalization and checkpoint.

### Task 7: Doctor and CLI

**Files:**
- Create: `src/stock_research/research_project_v2_1/acquisition_doctor.py`
- Modify: `src/stock_research/research_project_v2_1/cli.py`
- Test: `tests/test_research_project_v2_1_acquisition_doctor.py`
- Test: `tests/test_research_project_v2_1_acquisition_cli.py`

- [ ] Write failing tests for redacted proxy diagnostics, JSON output, dry-run, explicit project/version, timeout, exit codes, and no fallback.
- [ ] Implement doctor, fetch, import, show-attempt, and smoke command contracts.
- [ ] Keep online smoke opt-in and outside default regression.
- [ ] Commit doctor and CLI.

### Task 8: Optional Browser and Docling Adapters

**Files:**
- Create: `src/stock_research/research_project_v2_1/acquisition_browser.py`
- Modify: `src/stock_research/research_project_v2_1/acquisition_normalize.py`
- Test: `tests/test_research_project_v2_1_acquisition_browser.py`
- Test: `tests/test_research_project_v2_1_acquisition_normalize.py`

- [ ] Write failing tests for runtime available/unavailable, explicit invocation, and no browser fallback.
- [ ] Implement browser runtime detection and optional adapter skeleton.
- [ ] Implement optional Docling adapter with injected parser and distinct representation identity.
- [ ] Verify neither adapter is required by default tests.
- [ ] Commit optional adapters.

### Task 9: Audit and Handoff

**Files:**
- Create: `docs/research_operating_layer_v2_r2b_external_acquisition_phase_b.md`

- [ ] Run Schema 2.3, provider, SSRF, storage, CLI, and scope tests.
- [ ] Run full V2, R1/R2 compatibility, and selected V1 regression suites.
- [ ] Verify v0.2.0/v0.2.1 hashes and forbidden paths.
- [ ] Confirm no online AI PCB smoke batch or research-state mutation occurred.
- [ ] Commit the Phase B report and pause for Phase C approval.
