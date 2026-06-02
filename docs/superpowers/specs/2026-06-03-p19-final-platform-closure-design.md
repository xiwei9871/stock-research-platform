# P19 Final Platform Closure Design

## Objective

P19 closes the stock research platform foundation by creating a final,
operator-readable release readiness package. It consolidates P0-P18 into a
single phase index, audits the final platform surfaces, defines a smoke matrix,
and writes the final runbook and completion review.

## Problem

The platform now has many completed phases: data foundation, daily operations,
dashboard workbench, operator review, outcome analytics, experiment replay,
shadow watchlist, shadow outcome tracking, shadow analytics review, shadow
review decisions, follow-up queue, and follow-up resolution review.

Each phase is documented, but the final state is spread across many files. P19
must make the whole system reviewable without reopening feature development.

## Recommended Approach

Use a documentation-first closure phase with lightweight verification helpers
only if needed.

This is the right choice because the foundation work is already implemented
through P18. The risk now is not missing a new feature; the risk is an unclear
operating boundary, incomplete handoff, or accidental confusion between
review-only artifacts and production actions.

## Architecture

P19 has five artifacts:

1. Phase index: summarizes P0-P18 and links scope/runbook/completion documents.
2. Readiness audit: checks CLI, schema, dashboard, operator/shadow artifacts,
   and safety boundaries.
3. Smoke matrix: lists final verification commands and expected outputs.
4. Final release runbook: gives a practical operating order and failure rules.
5. Completion review: gives the final done/not-done statement and backlog split.

No new runtime service is introduced. No database schema is required unless the
readiness audit reveals a small missing documentation-only check. Any code added
in P19 must be narrowly scoped to verification/report generation and must not
write production state.

## Data Flow

P19 reads:

- `docs/quant_system/*.md`
- existing tests and CLI command definitions
- dashboard tests and runbooks
- current git state

P19 writes:

- final P19 documentation artifacts only, unless a focused verification helper
  is justified by a failing audit.

## Safety Model

P19 inherits the P12-P18 review-only safety model:

- shadow outputs are not production approvals,
- P18 resolution labels are not trading signals,
- dashboard review panels are read-only,
- all production promotion remains out of scope.

P19 also protects unrelated main-worktree changes by running in a dedicated
worktree and ignoring mid-trend, strong-winner, and unrelated watchlist dirty
changes.

## Testing And Verification

P19 verification should include:

- a final backend focused smoke set covering P17/P18 and dashboard app routes,
- dashboard Vitest client/app shell tests,
- dashboard build,
- Playwright dashboard smoke,
- `git diff --check`,
- document link/path sanity where practical.

The final smoke matrix must record exact commands and expected evidence.

## Deliverables

- `docs/quant_system/64_p19_final_platform_closure_scope_freeze.md`
- `docs/quant_system/65_p19_platform_phase_index.md`
- `docs/quant_system/66_p19_release_readiness_audit.md`
- `docs/quant_system/67_p19_final_smoke_matrix.md`
- `docs/quant_system/68_p19_final_release_runbook.md`
- `docs/quant_system/69_p19_final_platform_closure_completion.md`
- `docs/superpowers/plans/2026-06-03-p19-final-platform-closure.md`

## Non-Goals

- Do not add new research strategy logic.
- Do not modify production scoring logic.
- Do not implement trading.
- Do not resolve unrelated dirty changes in the main worktree.
- Do not merge or push without explicit confirmation.

## Success Criteria

P19 succeeds when a future operator can answer:

- What phases exist from P0-P18?
- Which commands verify the final platform?
- Which documents explain safe daily operation?
- Which parts are review-only and cannot be treated as production approval?
- What future work remains outside this completed foundation?
