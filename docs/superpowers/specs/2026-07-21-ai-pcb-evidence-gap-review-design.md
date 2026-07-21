# AI PCB Evidence Gap Review and Targeted Research Design v1

## Purpose

Convert the ten frozen AI PCB cognition gaps into an offline, executable research design. The stage does not acquire evidence, reassess existing evidence, decide PCB bottlenecks, infer value migration, or create company/equity objects.

## Architecture

The existing cognition package remains immutable and is referenced by content hash. A single integrated JSON artifact is the only research-design fact source. A deterministic renderer produces the sole Markdown report. A concentrated validator recomputes upstream bindings, the ten-gap universe, unique four-group assignment, atomic question and ER completeness, public-evidence ceilings, stopping rules, inference boundaries, authorization flags, and report consistency.

No public CLI expansion is needed. The established Python loader/validator pattern is sufficient for deterministic tests and future read-only integration.

## Formal outputs

- `artifacts/research_projects/v2_1/analysis/ai_pcb_evidence_gap_review_and_targeted_research_design_v1.json`
- `artifacts/research_projects/v2_1/reports/ai_pcb_evidence_gap_review_and_targeted_research_design_v1.md`

Schema, code, tests, method notes and an exact allowlist support these outputs but are not additional research products.

## Data model

The artifact contains immutable upstream bindings, offline execution policy, four group definitions, ten gap-review records, an atomic Evidence Requirement registry, source-class capability boundaries, cross-level inference rules, stopping-state definitions, governance flags and provenance.

Each gap review retains the upstream `gap_id` and original description, assigns exactly one group, separates grounded input from research-design hypotheses, lists atomic questions and ER IDs, states public availability and evidence ceiling, and records minimum sufficiency, contradiction search, stop conditions, prohibited conclusions, priority and dependencies.

Every new ER is atomic. It identifies one research question, the required facts and source classes, independence and freshness rules, comparison scope, denominator, sufficiency, contradiction and stopping rules, maximum cognition level, and prohibited inferences. `future_acquisition_authorized` is always false.

## Fixed grouping

- Group A: `GAP-SIGNAL`, `GAP-LOSS`, `GAP-LAYERS`
- Group B: `GAP-LAMINATE`
- Group C: `GAP-BACKDRILL`, `GAP-LAMINATION`, `GAP-THERMAL`, `GAP-TEST`, `GAP-YIELD`
- Group D: `GAP-CAPACITY`

Group A/B evidence cannot directly support Group C/D conclusions. Process difficulty cannot establish effective capacity. Effective-capacity evidence cannot establish value migration without separate cost, price, supply-demand and profit-allocation evidence.

## Public evidence ceilings

Availability is a design judgment only: `likely_publicly_available`, `partially_publicly_available`, `unlikely_publicly_available`, `structurally_limited`, or `unknown`.

Ceilings distinguish technical mechanism, engineering difficulty, bounded manufacturing capability and structural public limits. Yield, customer qualification and qualified effective capacity are explicitly allowed to terminate at `structurally_limited`; the design must not assume that more searching resolves them.

## Determinism and validation

The artifact uses canonical JSON and a self-excluding SHA-256 content hash. The report uses stable ID ordering, UTF-8, NFC and LF line endings. Validation fails when upstream hashes drift, a gap is missing or duplicated, a group is invalid, an ER is non-atomic or incomplete, a structurally limited issue is promised as fully resolvable, authorization is enabled, downstream semantics appear, or the report differs from renderer output.

## Scope

The implementation may add one schema, one focused module, one focused test file, the two outputs, a method note and an exact allowlist. It must not modify acquisition, normalized evidence, cognition package/audit/report, project versions, API, Dashboard, database, strategy, company or equity layers.
