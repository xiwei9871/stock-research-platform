# Home Strategy Review Queue Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make each enabled-strategy card open the review queue with the matching official strategy selected.

**Architecture:** AppShell owns the route handoff and passes the requested strategy ID into ReviewQueueWorkspace. ReviewQueueWorkspace resolves that ID against loaded groups before applying its existing default-selection fallback. HomeCockpit provides human-facing review action text while the separate Strategy Lab entry remains unchanged.

**Tech Stack:** React, TypeScript, Vitest/Testing Library, Playwright

---

### Task 1: Lock the route and selection contract with failing tests

**Files:**
- Modify: `dashboard/tests/home-cockpit.test.tsx`
- Modify: `dashboard/tests/review-queue-workspace.test.tsx`

- [x] Change the AppShell test to click `查看 Mid Trend Combo 复盘` and expect `/review-queue?strategy_id=mid_trend` plus the Mid Trend review group.
- [x] Add a ReviewQueueWorkspace test with `initialStrategyId="tech_bottleneck"` and verify the Tech Bottleneck group is selected even when it is empty.
- [x] Run `cd dashboard && pnpm test -- home-cockpit.test.tsx review-queue-workspace.test.tsx` and confirm the new expectations fail for the missing behavior.

### Task 2: Implement the review queue deep link

**Files:**
- Modify: `dashboard/src/components/AppShell.tsx`
- Modify: `dashboard/src/components/HomeCockpit.tsx`
- Modify: `dashboard/src/components/ReviewQueueWorkspace.tsx`

- [x] Replace the card handoff with `/review-queue?strategy_id=<official-id>` and activate `reviewQueue`.
- [x] Pass the route strategy ID to ReviewQueueWorkspace on initial load and location changes.
- [x] Extend initial queue selection to prefer `strategy:<strategy_id>` or an item with the matching `strategy_id`, then retain the existing fallback.
- [x] Change the card action text to `查看 {strategy_name} 复盘`.
- [x] Run the focused Vitest command and confirm both tests pass.

### Task 3: Update browser consistency checks and verify

**Files:**
- Modify: `dashboard/tests/e2e/p0/review-publication.spec.ts`
- Modify: `dashboard/tests/e2e/eod/eod-critical.spec.ts`

- [x] Update home-card journeys to expect `/review-queue?strategy_id=<official-id>` and the matching selected review region.
- [x] Run the focused frontend unit tests.
- [x] Run the focused Playwright P0 publication test and EOD publication-consistency test.
- [x] Run `cd dashboard && pnpm build`.
- [x] Review `git diff` for scope and commit the verified change.
