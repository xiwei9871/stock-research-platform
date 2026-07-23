# LHB Dashboard Confirmation Semantics — Phase B Plan

## Goal

Separate T-close pending candidates from candidates that have actually passed T+1 confirmation, while preserving watch, risk-watch, and retreat states through EOD artifacts and Dashboard readers.

## Tasks

1. Add table-driven tests for mapping rule layer/action/fill status to `pending_confirmation`, `confirmed_follow`, `watch_only`, `risk_watch`, and `retreat`.
2. Carry `confirmation_state`, `phase12a_rule_layer`, `phase12a_rule_action`, and `fill_status` through the strategy review CSV and score audit.
3. Preserve the fields in manifest and artifact Dashboard readers.
4. Make lightweight digest labels state-specific. Pending rows must say `Top5 次日确认待定` and must not say `Top5 重点复盘`; confirmed rows say `已确认可跟踪`.
5. Re-run EOD publication for `2026-07-14` and one historical date with confirmed candidates, then verify state counts and wording.

## Verification

Run focused EOD, score-audit, and Dashboard review-queue tests, followed by a 2026-07-14 artifact assertion that all eligible same-day Top5 rows are pending rather than confirmed.
