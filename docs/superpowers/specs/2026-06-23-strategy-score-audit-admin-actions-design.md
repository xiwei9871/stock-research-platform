# Strategy Score Audit Admin Actions Design

## Goal

Add an operator-facing anomaly handling layer on top of the existing strategy score audit.

The purpose is not only to show:

- overall audit status
- anomaly count
- anomaly type counts

but also to answer:

1. Is this anomaly a system fault or an expected observation?
2. Does it need an immediate rerun?
3. Does it need a code/data follow-up instead?
4. What is the next safe action for an operator?

## Problem

The current home dashboard can already surface:

- `策略打分审计`
- `正常 / 需关注 / 待补齐 / 不可用`
- anomaly counts

This is enough to detect that something is off, but not enough to handle it.

When the operator sees:

- `5 条异常`

the next question is immediate:

- what are these anomalies?
- which strategy is affected?
- can I ignore it today?
- should I rerun something?
- if rerun is useless, what should I do instead?

Without an anomaly handling layer, the audit remains a warning light without a procedure.

## Scope

This design covers:

- a normalized anomaly type dictionary
- operator-facing severity and treatment classification
- a lightweight dashboard action panel
- safe action recommendations

This design does not cover:

- automatic repair of every anomaly
- arbitrary command execution from the browser
- broker/live trading actions
- full ticketing or workflow engine integration

## Product Shape

The operator experience should have two layers.

### Layer 1: Status Strip

Keep the existing compact home status cell:

- `策略打分审计`
- status
- anomaly row count

This remains the quick scan layer.

### Layer 2: Handling Panel

When `overall_status = warning`, render a dedicated operator panel directly below the status strip.

The panel should answer:

- what kind of anomaly this is
- which strategies are affected
- whether this is a known observation or a real fault
- what actions are safe

## Anomaly Classification Model

Every anomaly type must map to four decision fields:

1. `severity`
2. `treatment_class`
3. `operator_message`
4. `recommended_actions`

### Severity

Allowed values:

- `info`
- `observe`
- `retry`
- `investigate`
- `critical`

Meaning:

- `info`: audit note only
- `observe`: known, explainable, not a blocking fault
- `retry`: likely recoverable by rerunning a deterministic artifact step
- `investigate`: likely data/code lineage problem
- `critical`: publication trust is broken and requires immediate attention

### Treatment Class

Allowed values:

- `known_observation`
- `rerunnable_artifact_gap`
- `lineage_gap`
- `system_fault`

Meaning:

- `known_observation`: explainable anomaly that does not invalidate core usage
- `rerunnable_artifact_gap`: artifact likely missing or stale; rerun is meaningful
- `lineage_gap`: underlying data/score lineage is incomplete; rerun alone is not enough
- `system_fault`: output is likely incorrect or inconsistent

## Phase 1 Dictionary

The first version should explicitly support the anomaly types already in the score audit spec.

### `mapped_score_without_raw_score`

Interpretation:

- published/display score exists
- mapped compatibility score exists
- raw candidate score is missing

Default classification:

- severity: `observe`
- treatment_class: `known_observation`

Operator message:

- `页面分数可用，但原始候选分未穿透到审计链。`

Recommended actions:

- `view_detail`
- `mark_known_observation`
- `create_follow_up_task`

Not recommended:

- `rerun_strategy_publish`

Reason:

- if the same upstream logic still lacks raw score lineage, rerun will reproduce the same anomaly

### `missing_candidate_source`

Interpretation:

- selected row has no recoverable source lineage

Default classification:

- severity: `investigate`
- treatment_class: `lineage_gap`

Recommended actions:

- `view_detail`
- `create_follow_up_task`

### `missing_published_score_source`

Interpretation:

- score exists, but score source field is blank

Default classification:

- severity: `investigate`
- treatment_class: `lineage_gap`

Recommended actions:

- `view_detail`
- `create_follow_up_task`

### `missing_display_score_source`

Interpretation:

- display score exists, but display source is blank

Default classification:

- severity: `investigate`
- treatment_class: `lineage_gap`

Recommended actions:

- `view_detail`
- `create_follow_up_task`

### `missing_raw_candidate_score`

Interpretation:

- selected row lacks any raw candidate score and is not an allowed mapped-score observation

Default classification:

- severity: `investigate`
- treatment_class: `lineage_gap`

Recommended actions:

- `view_detail`
- `create_follow_up_task`

### `published_display_score_mismatch`

Interpretation:

- UI score differs from published score without a declared transform rule

Default classification:

- severity: `critical`
- treatment_class: `system_fault`

Recommended actions:

- `view_detail`
- `rerun_audit`
- `create_follow_up_task`

### `published_score_mismatch`

Interpretation:

- strategy-specific publish mapping rule failed

Default classification:

- severity: `critical`
- treatment_class: `system_fault`

Recommended actions:

- `view_detail`
- `rerun_audit`
- `create_follow_up_task`

### `stale_source`

Interpretation:

- candidate or source date is older than the platform trade date

Default classification:

- severity: `retry`
- treatment_class: `rerunnable_artifact_gap`

Recommended actions:

- `view_detail`
- `rerun_audit`
- `rerun_daily_review`

### `rank_only_placeholder_score`

Interpretation:

- score was synthesized from rank rather than real score lineage

Default classification:

- severity: `investigate`
- treatment_class: `lineage_gap`

Recommended actions:

- `view_detail`
- `create_follow_up_task`

### `unknown_selection_reason`

Interpretation:

- selected row has no interpretable reason/eligibility context

Default classification:

- severity: `retry`
- treatment_class: `rerunnable_artifact_gap`

Recommended actions:

- `view_detail`
- `rerun_audit`
- `create_follow_up_task`

## Action Set

Phase 1 action keys:

- `view_detail`
- `mark_known_observation`
- `rerun_audit`
- `rerun_daily_review`
- `create_follow_up_task`

### `view_detail`

Behavior:

- open or expand a detail panel that shows:
  - anomaly type
  - affected strategy
  - sample rows
  - score/source fields

This is always safe.

### `mark_known_observation`

Behavior:

- UI-only acknowledgement for the current session or persisted operator note later

Phase 1 may keep this as:

- a visual acknowledgement action only
- no backend write required yet

This action is only shown for anomalies classified as `known_observation`.

### `rerun_audit`

Behavior:

- rerun only the audit artifact generation step
- do not rerun the full strategy engine

This action is shown only for anomalies classified as `rerunnable_artifact_gap` or `system_fault`.

### `rerun_daily_review`

Behavior:

- rerun or regenerate the dashboard-facing daily review artifact package

This action is useful when the issue is downstream artifact completeness rather than score lineage itself.

### `create_follow_up_task`

Behavior:

- Phase 1 can be a placeholder operator action that creates a structured local note or issue stub

This action is appropriate for:

- lineage gaps
- repeated known observations that should be fixed later
- critical issues after inspection

## Home Panel Requirements

When `overall_status = warning`, the home panel should show:

1. top summary
- anomaly total
- affected strategies

2. anomaly chips
- anomaly type label
- count

3. sample rows
- asset
- strategy
- anomaly label

4. treatment headline
- `已知观察项`
- `可重试`
- `需排查`
- `严重异常`

5. actions
- only the actions allowed by the highest-priority anomaly class on the page

## Priority Rules

If multiple anomaly types exist on one day, the home panel should compute the dominant treatment state with this precedence:

1. `critical`
2. `investigate`
3. `retry`
4. `observe`
5. `info`

This prevents a serious mismatch from being visually diluted by lower-severity observations.

## Why Generic “Rerun” Is Wrong

The UI must not imply that rerun solves every anomaly.

Example:

- `mapped_score_without_raw_score`

This is not a missing file.
This is not necessarily a failed job.
It is a score lineage explainability gap.

If the browser only shows a generic:

- `重跑`

operators will expect the anomaly to disappear after rerun, which is misleading.

Therefore the UI must separate:

- anomalies that are fixable by rerun
- anomalies that require explanation or engineering follow-up

## Dashboard Phase 1 Recommendation

Phase 1 should implement:

1. anomaly dictionary in frontend logic or shared config
2. home handling panel
3. three action buttons:
   - `查看明细`
   - `标记为已知观察项`
   - `创建修复任务`

Phase 1 should not yet implement browser-triggered reruns unless the rerun API is already safe and deterministic.

## Acceptance Criteria

This design is satisfied when:

- a warning audit on home renders a handling panel
- `mapped_score_without_raw_score` is shown as `已知观察项`
- the panel clearly distinguishes affected strategy and anomaly type
- the panel does not imply rerun will fix every anomaly
- safe actions are visible to the operator
