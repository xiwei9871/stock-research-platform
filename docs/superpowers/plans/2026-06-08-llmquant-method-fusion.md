# LLMQuant Method Fusion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Borrow useful LLMQuant methods into `stock_research` without creating a parallel platform, replacing the A-share data core, or weakening the existing evidence-first research boundary.

**Architecture:** Treat LLMQuant as a method and workflow reference, not as a subsystem to import. Each adopted idea must land inside an existing `stock_research` boundary: agent contracts, run-card evidence, research reports, watchlist review, market regime review, external research mapping, or report delivery. The first implementation slice is documentation and contracts; executable integrations come only after the fusion map is reviewed.

**Tech Stack:** Existing `stock_research` Python modules, Markdown plans/runbooks, JSON evidence artifacts, pytest, existing CLI/report patterns, optional external MCP/data calls only through reviewed adapters.

---

## Fusion Principle

Do not turn `stock_research` into a clone of LLMQuant.

LLMQuant is useful where it improves our current system:

- Better skill/workflow templates for analyst review.
- Better evidence contracts for Agent outputs.
- Better non-structured research material handling.
- Better external project radar for finance Agent tooling.
- Selective external context such as FRED, SEC, 13F, paper search, and wiki-style research references.

LLMQuant is not useful where it competes with our current system:

- It must not replace the A-share PostgreSQL data model.
- It must not replace point-in-time finance and `announcement_date` rules.
- It must not replace factor scoring, factor evaluation, watchlist, backtest, or shadow lifecycle governance.
- It must not create a second Agent framework with incompatible output shapes.
- It must not introduce buy/sell automation or broker/execution state.

Every adoption item must answer: which existing `stock_research` module becomes better?

## Existing System Anchors

Use these anchors when implementing any LLMQuant-inspired change:

- Agent contract and review:
  - `src/stock_research/agents/contracts.py`
  - `src/stock_research/agents/review.py`
- Reports and bundles:
  - `src/stock_research/reports/`
  - `src/stock_research/report_delivery.py`
  - `src/stock_research/report_delivery_openclaw_sender.py`
- Evidence and research infrastructure:
  - `src/stock_research/run_card.py`
  - `src/stock_research/research_infra/`
- Watchlist and shadow review:
  - `src/stock_research/watchlist/`
  - `src/stock_research/operator_decision/`
- News, reports, and narrative:
  - `src/stock_research/news_features.py`
  - `src/stock_research/topn_news_enrichment.py`
  - `src/stock_research/research_narrative.py`
  - `src/stock_research/stock_report_research.py`
- Market regime and risk:
  - `src/stock_research/market_regime_confirmation_v1.py`
  - `src/stock_research/market_style_switch_v1.py`
  - `src/stock_research/reports/risk_alert_report.py`
- External project governance:
  - `docs/quant_system/02_external_research_map.md`
  - `docs/quant_system/06_no_reinvent_wheel_policy.md`

## Adoption Map

| LLMQuant Area | Adopt | Fuse Into | Exclude |
| --- | --- | --- | --- |
| `skills` | Workflow structure, evidence contract, role-specific prompts | Agent contracts, report templates, watchlist/risk/portfolio review | Direct install as production skills without local schema mapping |
| `QuantMind` | Evidence-unit concept for papers/news/reports | Research signal layer and stock report/news enrichment | Separate knowledge graph product in phase one |
| `data-mcp` / LLMQuant Data | FRED, SEC, 13F, paper/wiki search as external context | External data adapters and report artifacts | A-share market/finance replacement |
| `awesome-trading-agents` | External radar taxonomy | External research map | Blind adoption of listed projects |
| `Magents` | Risk/slippage/order-lifecycle concepts for future backtest constraints | Backtest quality checklist and simulation notes | Replacing current vectorized/portfolio/retention backtests |
| Finance Context / docs | Professional report workflow names and review checklist ideas | Runbooks and report layout polish | Copying content into commercial knowledge base |

## Task 1: Add LLMQuant Fusion Governance

**Files:**

- Modify: `docs/quant_system/02_external_research_map.md`
- Modify: `docs/quant_system/06_no_reinvent_wheel_policy.md`
- Test: documentation review only

- [ ] Add LLMQuant rows to `docs/quant_system/02_external_research_map.md` for `skills`, `data-mcp`, `quant-mind`, `awesome-trading-agents`, `Magents`, and Finance Context.
- [ ] For each row, set `可借鉴内容` to method/workflow only and set `不可借鉴内容` to anything that would replace the A-share data core or create a parallel Agent platform.
- [ ] Add a short `LLMQuant 融合边界` section to `docs/quant_system/06_no_reinvent_wheel_policy.md`.
- [ ] State that every LLMQuant-inspired artifact must cite one of the existing system anchors listed in this plan.
- [ ] Verify there are no instructions to install or run external LLMQuant packages as production dependencies.

Acceptance:

- The governance docs make LLMQuant a bounded reference source.
- The docs explicitly reject parallel platform drift.
- No Python code changes are required for this task.

## Task 2: Define Internal Skill Fusion Templates

**Files:**

- Create: `docs/llmquant-fusion/internal-skill-template.md`
- Create: `docs/llmquant-fusion/risk-review-skill.md`
- Create: `docs/llmquant-fusion/watchlist-memo-skill.md`
- Create: `docs/llmquant-fusion/position-review-skill.md`
- Test: documentation review only

- [ ] Create an internal skill template that requires these sections: `Purpose`, `Existing stock_research inputs`, `Required evidence`, `Allowed outputs`, `Forbidden outputs`, `AgentObservation mapping`, `ReviewAgent checks`.
- [ ] Create `risk-review-skill.md` mapped to risk alert reports, market state, watchlist diagnostics, and shadow review artifacts.
- [ ] Create `watchlist-memo-skill.md` mapped to TopN reports, factor results, news enrichment, stock report research, and run cards.
- [ ] Create `position-review-skill.md` mapped to virtual portfolio, position review report, sector exposure, market regime, and risk alerts.
- [ ] In each skill draft, require output fields that can be converted into `AgentObservation`: `data_facts`, `factor_results`, `backtest_findings`, `agent_reasoning`, `unverified_hypotheses`, and `evidence`.
- [ ] In each skill draft, forbid direct instructions such as `必须买入`, `立即买入`, `must buy`, `sell now`, `自动下单`, and any broker/order/account mutation.

Acceptance:

- The skill drafts read like extensions of `stock_research`, not LLMQuant-branded imports.
- Every draft can be reviewed by the existing `ReviewAgent` contract.
- Every draft names concrete existing reports or artifacts as inputs.

## Task 3: Add Agent Skill Output Contract Tests

**Files:**

- Create: `tests/test_llmquant_fusion_agent_contracts.py`
- Modify only if needed: `src/stock_research/agents/contracts.py`
- Modify only if needed: `src/stock_research/agents/review.py`

- [ ] Write a test that creates a valid `AgentReport` from a risk-review-style observation and verifies `ReviewAgent().review(report).status == "passed"`.
- [ ] Write a test that creates a watchlist memo observation without evidence and verifies the review status is `rejected` with a `missing_evidence` blocker.
- [ ] Write a test that includes `必须买入` in `agent_reasoning` and verifies the review status is `rejected` with a `banned_trading_instruction` blocker.
- [ ] Run `pytest tests/test_llmquant_fusion_agent_contracts.py -q`.
- [ ] If the tests pass with existing code, commit only the test file.
- [ ] If a test exposes a real contract gap, make the smallest contract/review change needed and re-run the test.

Acceptance:

- LLMQuant-inspired skill outputs are constrained by the existing Agent review boundary.
- No new Agent schema is introduced unless an existing contract gap is proven by a failing test.

## Task 4: Define Research Evidence Unit Contract

**Files:**

- Create: `src/stock_research/research_infra/evidence_units.py`
- Create: `tests/test_research_infra_evidence_units.py`
- Document: `docs/llmquant-fusion/evidence-unit-contract.md`

- [ ] Define an `EvidenceUnit` dataclass with: `evidence_id`, `source_type`, `source_id`, `asset_id`, `ts_code`, `available_at`, `trade_date`, `title`, `summary`, `claims`, `risks`, `source_path`, `confidence`, `metadata`.
- [ ] Support `source_type` values: `stock_report`, `pdf`, `public_news`, `announcement`, `macro_series`, `external_paper`, `manual_review`.
- [ ] Add validation that rejects empty `evidence_id`, empty `source_type`, empty `available_at`, and unsupported `source_type`.
- [ ] Add validation that rejects `available_at > trade_date` unless `metadata["post_close_review"] == True`.
- [ ] Add `to_dict()` and `from_dict()` helpers.
- [ ] Add tests for valid round-trip, unsupported source type, and point-in-time rejection.
- [ ] Document that this contract is inspired by QuantMind-style evidence extraction but remains a local `stock_research` schema.

Acceptance:

- Research/report/news evidence can be normalized without adding a knowledge graph or external dependency.
- Point-in-time rules are enforced at the evidence-unit boundary.

## Task 5: Add Thin Evidence Unit Converters

**Files:**

- Modify: `src/stock_research/research_infra/evidence_units.py`
- Test: `tests/test_research_infra_evidence_units.py`
- Document: `docs/llmquant-fusion/evidence-unit-contract.md`

- [ ] Add `evidence_unit_from_news_record(record: dict[str, object]) -> EvidenceUnit`.
- [ ] Add `evidence_unit_from_stock_report_record(record: dict[str, object]) -> EvidenceUnit`.
- [ ] The news converter must read `ts_code`, `trade_date`, `published_at` or `available_at`, `title`, `summary`, and `source_path`.
- [ ] The stock report converter must read `ts_code`, `trade_date`, `available_at` or `report_date`, `title`, `summary`, and `source_path`.
- [ ] If optional fields are missing, set `claims=[]`, `risks=[]`, `confidence=0.0`, and add the missing field names to `metadata["missing_fields"]`.
- [ ] Add tests for both converters using small dictionaries.
- [ ] Do not modify existing news/report pipelines in this task.

Acceptance:

- Existing pipelines can opt into evidence units later.
- The first converter slice is read-only and does not change current report output.

## Task 6: Create External Context Adapter Design

**Files:**

- Create: `docs/llmquant-fusion/external-context-adapters.md`
- Modify: `docs/quant_system/06_no_reinvent_wheel_policy.md`
- Test: documentation review only

- [ ] Document allowed external context categories: FRED macro, SEC filings, 13F holdings, external paper search, external wiki/reference search.
- [ ] Document blocked categories for phase one: A-share prices, A-share finance rows, A-share factor scores, trade signals, broker/order/account data.
- [ ] Define the required adapter output shape: `source`, `query`, `retrieved_at`, `available_at`, `payload_path`, `summary`, `evidence_units`, `warnings`.
- [ ] Require all external payloads to be stored as artifacts before they can appear in a report or Agent observation.
- [ ] Require external context to be labelled as `external_context`, not as primary A-share evidence.
- [ ] Add the same rules as a compact paragraph in `docs/quant_system/06_no_reinvent_wheel_policy.md`.

Acceptance:

- Future LLMQuant Data/MCP usage is possible but cannot bypass our storage and evidence rules.
- External context remains supplemental and auditable.

## Task 7: Update Report and Watchlist Runbooks

**Files:**

- Modify: `docs/daily-factor-pipeline-runbook.md`
- Modify: `docs/dashboard-workbench-runbook.md`
- Modify: `docs/quant_system/59_p17_shadow_decision_follow_up_queue_runbook.md`
- Modify: `docs/quant_system/62_p18_shadow_follow_up_resolution_review_runbook.md`

- [ ] Add a short section to the daily pipeline runbook explaining where internal skill review can be inserted after report bundle generation and before delivery.
- [ ] Add a dashboard runbook note that internal skill outputs are review artifacts, not dashboard state mutation.
- [ ] Add a P17 note that watchlist memo skills may propose follow-up questions but cannot promote candidates.
- [ ] Add a P18 note that risk/position review skills may summarize resolution evidence but cannot change resolution labels.
- [ ] Verify all notes point back to `docs/llmquant-fusion/internal-skill-template.md`.

Acceptance:

- Operational docs show exactly where the fused skills fit.
- Review-only boundaries remain explicit in daily and shadow workflows.

## Task 8: Add External Radar Maintenance Loop

**Files:**

- Create: `docs/llmquant-fusion/external-radar.md`
- Modify: `docs/quant_system/02_external_research_map.md`

- [ ] Create a quarterly review checklist for LLMQuant and related finance-agent projects.
- [ ] Include fields: `project`, `url`, `last_reviewed`, `license`, `adoption_status`, `stock_research_anchor`, `risk`, `next_action`.
- [ ] Add adoption statuses: `observe`, `template_only`, `adapter_candidate`, `blocked`, `retired`.
- [ ] Add a rule that no project moves from `observe` to `adapter_candidate` without a local evidence/storage mapping.
- [ ] Link the checklist from `docs/quant_system/02_external_research_map.md`.

Acceptance:

- External project learning becomes a controlled maintenance process.
- The radar prevents ad hoc copying and keeps every project tied to a local anchor.

## Recommended First Slice

Start with Tasks 1, 2, and 3 only.

This first slice gives us:

- Governance language that prevents platform drift.
- Three local skill drafts that fit our existing reports.
- Tests proving those outputs remain constrained by the current `ReviewAgent`.

Do not start external MCP/data integration until the internal skill contract is reviewed and accepted.

## Verification

After implementing the first slice, run:

```bash
.venv/bin/pytest tests/test_llmquant_fusion_agent_contracts.py tests/test_agent_contracts.py -q
```

Expected:

- All tests pass.
- Existing agent contract tests remain unchanged in behavior.

For documentation-only tasks, run:

```bash
rg -n "LLMQuant|llmquant|外部上下文|internal-skill-template" docs/quant_system docs/llmquant-fusion docs/superpowers/plans/2026-06-08-llmquant-method-fusion.md
```

Expected:

- LLMQuant references appear only as bounded method references.
- No instruction says to replace the A-share data core, create a parallel Agent platform, or automate trading.

## Scope Guardrails

- No production dependency on LLMQuant packages in the first slice.
- No database migration in the first slice.
- No network access in tests.
- No change to factor scoring, watchlist scoring, backtest results, or dashboard state.
- No copy-paste of LLMQuant content beyond short cited labels and local paraphrased method descriptions.
- Every future executable adapter must write artifacts first and convert those artifacts into local evidence units before reports can consume them.
