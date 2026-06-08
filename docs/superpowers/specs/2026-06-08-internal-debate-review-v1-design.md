# Internal Debate Review v1 Design

## Purpose

Internal Debate Review v1 absorbs the useful part of TradingAgents' research organization structure into the existing `run-internal-skill-review` workflow. It adds a narrow debate and final-review layer after our local artifacts are produced, without adopting TradingAgents' runtime, trading loop, portfolio execution, or simulated brokerage behavior.

The goal is to make daily research reviews more adversarial and auditable: every accepted review packet should expose the supporting case, the opposing case, risk-manager concerns, and a portfolio-style summary for human review.

## Scope

In scope:

- Add deterministic offline debate output to `run-internal-skill-review`.
- Keep all inputs as local artifacts already passed through `--artifact-path`.
- Emit structured JSON fields for `bull_case`, `bear_case`, `risk_manager_review`, `portfolio_review_summary`, `evidence_conflicts`, `missing_evidence`, and `operator_questions`.
- Render the same sections in `internal_skill_review.md`.
- Continue routing the underlying `AgentReport` through `ReviewAgent`.
- Preserve review-only behavior: no score mutation, no watchlist mutation, no dashboard mutation, no broker/order/account/cash/position mutation.

Out of scope:

- Importing or running the TradingAgents codebase.
- Adding autonomous trader, execution, simulated exchange, or portfolio rebalancing agents.
- Letting debate output change factor scores, candidate eligibility, watchlist state, or delivery state.
- Adding live LLM calls. v1 is deterministic and artifact-first.

## Architecture

The existing `run_internal_skill_review()` remains the CLI entry point and review boundary. It already loads local artifacts, builds three `AgentObservation` records, runs `ReviewAgent`, and writes JSON/Markdown artifacts.

Internal Debate Review v1 adds a small local data model and builder inside this workflow:

- `InternalDebateReview` stores the organization-style review output.
- `DebateCase` stores a role, conclusion, cited evidence ids, and notes.
- `_build_internal_debate_review()` derives deterministic debate content from loaded artifacts and the `ReviewAgent` result.
- `InternalSkillReviewResult` exposes `debate_review_json_path`.

The implementation should stay in `src/stock_research/internal_skill_review.py` unless the file becomes hard to read. This keeps v1 intentionally narrow and avoids creating a parallel agent subsystem.

## Data Flow

1. CLI receives `--trade-date`, repeated `--artifact-path`, and `--output-dir`.
2. `_load_artifacts()` reads local files and infers evidence types.
3. `_build_agent_report()` creates the existing `risk`, `watchlist`, and `review` observations.
4. `ReviewAgent().review(report)` validates safety and evidence rules.
5. `_build_internal_debate_review()` creates deterministic debate sections from the same local artifacts:
   - `bull_case` uses TopN, position review, market state, and run card artifacts when available.
   - `bear_case` uses risk alerts, market state, missing artifacts, and review issues.
   - `risk_manager_review` emphasizes risk alerts, evidence gaps, and any rejected review issues.
   - `portfolio_review_summary` gives a final human-review summary with no trading instruction.
6. The workflow writes:
   - `agent_report.json`
   - `review_agent_result.json`
   - `internal_debate_review.json`
   - `internal_skill_review.md`

## Error Handling

Missing artifacts do not crash the workflow. They are recorded as warnings and included in `missing_evidence`.

If all evidence is missing, the existing `ReviewAgent` rejection remains authoritative. The debate review should still write a JSON and Markdown artifact explaining that the packet failed because evidence was missing.

## Testing

Tests should cover:

- A normal artifact packet writes `internal_debate_review.json` with bull, bear, risk, and portfolio sections.
- Missing artifacts are represented in `missing_evidence` and Markdown.
- Debate output does not introduce banned trading instructions.
- The CLI parser and dispatch expose the new artifact path without changing existing command arguments.

## Success Criteria

- The feature is usable through the existing `run-internal-skill-review` command.
- Existing output files remain backward compatible.
- New debate output is deterministic, artifact-cited, and review-only.
- The test suite for internal skill review, agent contracts, evidence units, and CLI parsing passes.
