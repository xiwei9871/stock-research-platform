# AI PCB Targeted Evidence Assessment Wave 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a strict offline assessment of the six Wave 1 ERs with precise normalized-section locators and a deterministic report, without updating cognition or downstream research.

**Architecture:** Add one focused schema, validator/loader and renderer. Build one integrated assessment artifact from immutable Wave records, then render and verify one report.

**Tech Stack:** Python 3.14, RFC 8785 canonical JSON, SHA-256, JSON Schema, pytest.

---

### Task 1: Assessment contract and upstream bindings

- [ ] Write failing tests for checkpoint/Gate drift, exact ER scope, blocked/failed/preflight exclusion and normalized-lineage validation.
- [ ] Add the minimal 2.7 schema and focused assessment validator.
- [ ] Run focused tests and commit.

### Task 2: Atomic claims and evidence chains

- [ ] Inspect every usable normalized document section and record exact locators.
- [ ] Write failing tests for duplicate-chain collapse, A02 OIF dependence, B01 Isola single-chain treatment, unknown-date confidence caps and denominator requirements.
- [ ] Build atomic claims and deterministic ER aggregation.
- [ ] Run focused tests and commit.

### Task 3: Deterministic report and persisted artifacts

- [ ] Write failing tests proving report-only projection and rejection of unregistered claims.
- [ ] Add the fixed renderer and persisted-report validator.
- [ ] Generate the assessment JSON and Markdown report.
- [ ] Validate hashes, locators and upstream immutability; commit.

### Task 4: Scope attribution and regression

- [ ] Add a machine-readable exact allowlist and scope-guard coverage.
- [ ] Run focused, V2/R1-R2 and V1/Theme/Dashboard regression groups.
- [ ] Parse all JSON/JSONL, revalidate hashes and confirm a clean worktree.
- [ ] Report results and stop before Wave 1b or cognition update.
