# P19 Platform Phase Index

## Purpose

This index is the final map for the stock research platform foundation built
through P0-P18. It links each phase to its key documents and states the current
operational role of that phase.

P19 does not redefine prior phases. It makes the completed foundation readable
as one platform.

## Foundation Documents

| Document | Role |
| --- | --- |
| `01_current_state_audit.md` | Initial project state and gap discovery. |
| `02_external_research_map.md` | External research and reference map. |
| `03_gap_matrix.md` | Gap matrix used to prioritize platform foundation work. |
| `04_target_architecture.md` | Target architecture for research, scoring, review, and operations. |
| `05_mvp_implementation_plan.md` | Early MVP implementation framing. |
| `06_no_reinvent_wheel_policy.md` | Policy for preferring existing libraries and proven engines. |
| `07_agent_team_design.md` | Agent/team operating design. |
| `08_backtest_quality_checklist.md` | Backtest quality checklist. |

## Phase Index

| Phase | Purpose | Primary Scope/Runbook Docs | Completion Doc | Operational State |
| --- | --- | --- | --- | --- |
| P0 | Universe and base platform readiness. | `09_p0_universe_layer.md`, `10_technical_feature_performance_plan.md` | `11_p0_completion_and_p1_readiness.md` | Foundation complete; used as platform base. |
| P1 | Report delivery adapter foundation. | `12_p1_report_delivery_adapter_plan.md` | `13_p1_completion_review.md` | Local report delivery path established. |
| P2 | Durable storage and daily operational review. | `14_p2_scope_and_execution_plan.md`, `15_p2_durable_storage_decision.md`, `17_p2_daily_runbook_and_smoke_report.md` | `16_p2_completion_review.md` | Storage/runbook foundation established. |
| P3 | Scope freeze and early production-readiness cleanup. | `18_p3_scope_freeze.md` | `19_p3_completion_review.md` | Phase closed; informs scheduler integration. |
| P4 | Scheduler integration and daily run recording. | `20_p4_scheduler_integration_scope_freeze.md`, `21_p4_scheduler_runbook.md` | `22_p4_completion_review.md` | Scheduler wrapper/run recording documented. |
| P5 | Notification hardening. | `23_p5_notification_hardening_scope_freeze.md`, `24_p5_notification_runbook.md` | `25_p5_completion_review.md` | Notification safety and dry-run behavior documented. |
| P6 | Dashboard workbench integration. | `26_p6_dashboard_workbench_scope_and_execution_plan.md` | `27_p6_completion_review.md` | Read-only research dashboard foundation established. |
| P7 | Operator feedback loop. | `28_p7_operator_feedback_loop_scope_freeze.md`, `29_p7_operator_feedback_loop_runbook.md` | `30_p7_completion_review.md` | Operator decision journal path established. |
| P8 | Decision outcome review. | `31_p8_decision_outcome_review_scope_freeze.md`, `32_p8_decision_outcome_review_runbook.md` | `33_p8_decision_outcome_review_completion.md` | Review-only outcome artifact/read-model path established. |
| P9 | Decision outcome analytics. | `34_p9_decision_outcome_analytics_scope_freeze.md`, `35_p9_decision_outcome_analytics_runbook.md` | `36_p9_decision_outcome_analytics_completion.md` | Outcome analytics artifact/read-model path established. |
| P10 | Experiment promotion governance. | `37_p10_experiment_promotion_governance_scope_freeze.md`, `38_p10_experiment_promotion_governance_runbook.md` | `39_p10_experiment_promotion_governance_completion.md` | Governance artifacts remain review-only; no production promotion. |
| P11 | Experiment execution sandbox. | `40_p11_experiment_execution_sandbox_scope_freeze.md`, `41_p11_experiment_execution_sandbox_runbook.md` | `42_p11_experiment_execution_sandbox_completion.md` | Offline replay sandbox established. |
| P12 | Shadow watchlist experiment. | `43_p12_shadow_watchlist_scope_freeze.md`, `44_p12_shadow_watchlist_runbook.md` | `45_p12_shadow_watchlist_completion.md` | Shadow watchlist remains non-production. |
| P13 | Shadow outcome tracking. | `46_p13_shadow_outcome_tracking_scope_freeze.md`, `47_p13_shadow_outcome_tracking_runbook.md` | `48_p13_shadow_outcome_tracking_completion.md` | Shadow outcomes tracked for review. |
| P14 | Shadow outcome analytics. | `49_p14_shadow_outcome_analytics_scope_freeze.md`, `50_p14_shadow_outcome_analytics_runbook.md` | `51_p14_shadow_outcome_analytics_completion.md` | Shadow outcome analytics grouped for review. |
| P15 | Shadow analytics operational review. | `52_p15_shadow_analytics_operational_review_scope_freeze.md`, `53_p15_shadow_analytics_operational_review_runbook.md` | `54_p15_shadow_analytics_operational_review_completion.md` | Operator review packet for shadow analytics established. |
| P16 | Shadow review decision packet. | `55_p16_shadow_review_decision_packet_scope_freeze.md`, `56_p16_shadow_review_decision_packet_runbook.md` | `57_p16_shadow_review_decision_packet_completion.md` | Decision packet remains review-only. |
| P17 | Shadow decision follow-up queue. | `58_p17_shadow_decision_follow_up_queue_scope_freeze.md`, `59_p17_shadow_decision_follow_up_queue_runbook.md` | `60_p17_shadow_decision_follow_up_queue_completion.md` | Follow-up queue records review work without production action. |
| P18 | Shadow follow-up resolution review. | `61_p18_shadow_follow_up_resolution_review_scope_freeze.md`, `62_p18_shadow_follow_up_resolution_review_runbook.md` | `63_p18_shadow_follow_up_resolution_review_completion.md` | Resolution labels remain review-only and do not mutate P17 rows. |
| P19 | Final platform closure and release readiness. | `64_p19_final_platform_closure_scope_freeze.md`, `68_p19_final_release_runbook.md` | `69_p19_final_platform_closure_completion.md` | Final release readiness package. |

## Platform Layers

| Layer | Covered By | Final State |
| --- | --- | --- |
| Data foundation and daily operations | P0-P5 | Core operational foundation exists with runbooks and smoke checks. |
| Dashboard workbench | P6 | Read-only research dashboard exists and is covered by frontend/backend smoke. |
| Operator decision loop | P7-P11 | Operator decisions, outcomes, analytics, governance, and offline replay are documented and tested. |
| Shadow research loop | P12-P18 | Shadow watchlist, outcomes, analytics, operational review, decisions, follow-up queue, and resolution review are complete as review-only surfaces. |
| Final closure | P19 | Index, readiness audit, smoke matrix, final runbook, and completion review. |

## Safety Summary

The completed foundation is a research and review platform, not an automated
trading system.

- Shadow statuses are not production approvals.
- P18 resolution statuses are review labels only.
- Dashboard panels are read-only.
- Production watchlist promotion, broker actions, orders, cash, positions, and
  execution state remain outside this foundation.
