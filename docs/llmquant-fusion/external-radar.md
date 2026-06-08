# External Radar

This checklist keeps LLMQuant and related finance-agent projects as controlled reference sources. A project can influence `stock_research` only when it is tied to a local anchor and has a clear evidence/storage mapping.

## Quarterly Checklist

| project | url | last_reviewed | license | adoption_status | stock_research_anchor | risk | next_action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LLMQuant Skills | https://github.com/LLMQuant/skills | 2026-06-08 | MIT | template_only | `docs/llmquant-fusion/`, `agents/contracts.py`, `agents/review.py` | Could create a parallel Agent workflow if installed directly | Keep as local internal skill template reference |
| LLMQuant Data / data-mcp | https://github.com/LLMQuant/data-mcp | 2026-06-08 | 待确认 | observe | `docs/llmquant-fusion/external-context-adapters.md` | External data could bypass local PIT and artifact rules | Revisit only after adapter artifact mapping is reviewed |
| LLMQuant QuantMind | https://github.com/LLMQuant/quant-mind | 2026-06-08 | 待确认 | template_only | `research_infra/evidence_units.py` | Separate knowledge graph scope could distract from local evidence layer | Borrow schema ideas only |
| LLMQuant Awesome Trading Agents | https://github.com/LLMQuant/awesome-trading-agents | 2026-06-08 | MIT | observe | `docs/quant_system/02_external_research_map.md` | List entries may be unevenly maintained or incompatible | Review quarterly for candidates |
| LLMQuant Magents | https://github.com/LLMQuant/Magents | 2026-06-08 | 待确认 | observe | backtest quality docs | Could push premature event-driven engine work | Keep as future constraints reference |

## Adoption Status

- `observe`: tracked only; no local integration work.
- `template_only`: methods or templates can be adapted into local docs/contracts.
- `adapter_candidate`: eligible for a local adapter after evidence/storage mapping is reviewed.
- `blocked`: incompatible with current safety, license, data, or architecture boundary.
- `retired`: removed from active observation.

## Promotion Rule

No project moves from `observe` to `adapter_candidate` without:

- a local `stock_research` anchor
- a written artifact-first storage path
- a point-in-time availability rule
- a license check
- tests or documentation proving it cannot bypass review boundaries
