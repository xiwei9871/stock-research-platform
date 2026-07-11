# Theme Research Ingestion v1 Implementation Plan

**Goal:** Implement Phase 8 as a deterministic, artifact-first ingestion, review, and promotion pipeline that cannot bypass existing evidence gates.

**Architecture:** A new `theme_research_ingestion` module owns local adapters, normalized sources, rule-based claim extraction, theme-node matching, immutable run packages, append-only reviews, and atomic promotion. Existing `theme_decomposition_v1_5` remains the canonical schema and validator.

**Tech Stack:** Python 3 standard library, existing Docling parser wrapper, JSON/JSONL artifacts, argparse, pytest.

## Task 1: Define run and adapter contracts

**Files:**
- Create: `tests/test_theme_research_ingestion.py`
- Create: `src/stock_research/theme_research_ingestion.py`

- [x] Add failing tests for manual JSON, text, HTML, Docling, and existing-record normalization.
- [x] Add deterministic canonical JSON, SHA-256, stable IDs, and normalized document records.
- [x] Make malformed inputs and parser failures return stable validation codes.

## Task 2: Extract claims and match themes/nodes

**Files:**
- Modify: `tests/test_theme_research_ingestion.py`
- Modify: `src/stock_research/theme_research_ingestion.py`

- [x] Add failing tests for deterministic sentence extraction and claim-type classification.
- [x] Add failing tests for explicit theme hints, node aliases, token matching, and unmatched claims.
- [x] Implement `rule_based_sentence_v1` and deterministic `theme_node_matcher_v1`.
- [x] Verify automation never proposes reviewed claims or accepted S4 sources.

## Task 3: Build immutable versioned run packages

**Files:**
- Modify: `.gitignore`
- Modify: `tests/test_theme_research_ingestion.py`
- Modify: `src/stock_research/theme_research_ingestion.py`

- [x] Add failing tests for exact run file layout, concurrent idempotent re-ingestion, and run validation.
- [x] Implement atomic content-addressed run-directory creation and immutable manifest/checksums.
- [x] Ignore local `artifacts/theme_decomposition/ingestion_runs/` output.

## Task 4: Add append-only human review

**Files:**
- Modify: `tests/test_theme_research_ingestion.py`
- Modify: `src/stock_research/theme_research_ingestion.py`

- [x] Add failing tests for all decisions, required reviewer/comment, and latest-event projection.
- [x] Add S4 and reviewed-claim guardrail tests.
- [x] Implement hash-chained append-only JSONL events with stable IDs and policy validation.

## Task 5: Add promotion preview and atomic promotion

**Files:**
- Modify: `tests/test_theme_research_ingestion.py`
- Modify: `src/stock_research/theme_research_ingestion.py`

- [x] Add failing tests for preview contents and source-before-claim ordering.
- [x] Add tests for expected hash mismatch, full-package validation, and invalid candidate rollback.
- [x] Add tests for locked atomic promotion, two-phase audit, rollback, and idempotent reruns.
- [x] Assert nodes, scores, assessments, and unrelated artifact fields remain unchanged.

## Task 6: Integrate CLI

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_theme_research_ingestion.py`

- [x] Add CLI and direct-policy tests for ingest, validate, summary, queue, review, preview, and promote.
- [x] Register `theme-research-ingestion` in the shared CLI.
- [x] Emit structured JSON success and error responses.

## Task 7: Documentation and verification

**Files:**
- Create: `docs/theme_research_ingestion_v1.md`
- Modify: `docs/theme_driven_research_engine_roadmap.md`
- Modify: `docs/theme_decomposition_research_baseline_v1.md`

- [x] Document adapters, run package, review decisions, promotion procedure, and boundaries.
- [x] Mark Phase 8 implemented in the roadmap without changing Phase 9 scope.
- [x] Run focused tests and the complete relevant Theme Research regression suite; start the full backend suite and document its unrelated stale-input failure.
- [x] Run CLI smoke tests against the checked-in sample input.
- [x] Request repeated independent code review and resolve all high/medium findings.
