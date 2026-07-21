# AI PCB Targeted Evidence Acquisition Wave 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Acquire and normalize a controlled candidate set for exactly six Gate-authorized AI PCB ERs and produce one audited Wave 1 checkpoint without Evidence Assessment.

**Architecture:** Extend the existing acquisition pipeline with one focused Wave governance module. Global providers/storage remain unchanged; Wave files contain explicit authorization, candidate, attempt, normalization and checkpoint records.

**Tech Stack:** Python 3.14, existing DirectHttpProvider and normalizers, canonical JSON/SHA-256, pytest, public web discovery.

---

### Task 1: Gate and Wave contract
- [ ] Write failing tests for Gate hash, exact-list authorization, internal phase order and rejection of unlisted ERs.
- [ ] Implement the minimum Wave governance validator and candidate contract.
- [ ] Verify and commit.

### Task 2: Acquisition and normalization orchestration
- [ ] Write failing tests for blocked/acquired accounting, raw provenance, normalized traceability, unknown dates and no silent fallback.
- [ ] Implement the focused runner by composing existing provider/storage/normalizer functions.
- [ ] Verify and commit.

### Task 3: Checkpoint validation
- [ ] Write failing tests for duplicate grouping, per-ER attempt/acquired coverage, zero unauthorized coverage, no assessment and downstream authorization flags.
- [ ] Implement inventory/checkpoint builders and deterministic summary renderer.
- [ ] Verify and commit.

### Task 4: Discover and acquire
- [ ] Discover official, standards, engineering-measurement, material-method and boundary candidates for the six ERs.
- [ ] Screen every candidate against exact authorization and source-role requirements.
- [ ] Run internal phases continuously in Gate order using direct HTTP only.
- [ ] Normalize successful HTML/PDF artifacts and record failures without fallback.

### Task 5: Final audit and stop
- [ ] Build candidates/attempts/inventory/checkpoint/summary in the Wave directory.
- [ ] Validate raw hashes, normalized section lineage, duplicates, dates, scope, security and immutable upstreams.
- [ ] Add method note and exact allowlist.
- [ ] Run focused, V2 and V1 regressions; report and stop before Evidence Assessment.
