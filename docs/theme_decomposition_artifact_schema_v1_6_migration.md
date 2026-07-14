# Theme Decomposition Artifact Schema v1.6 Migration

## Purpose

Schema v1.6 adds an optional deep-industry-research profile to the existing Theme Research artifact. Version 1.5 remains supported without modification.

## Compatibility

- `theme_decomposition_v1_5` artifacts continue to load and validate.
- `theme_decomposition_v1_6` artifacts may add one root-level `research_profile`.
- A theme without `research_profile` behaves exactly as before.
- Existing source, claim, node, value-capture, review, ingestion, and database contracts remain unchanged.

## Research Profile

The profile is used only for `industry_chain_deep_research` records and contains:

- `catalog_chain_id`: authoritative Technology Industry Catalog chain;
- `research_kind`: fixed to `industry_chain_deep_research`;
- `industry_stage`: concise lifecycle stage;
- `central_conflict`: primary industrial or economic tension;
- `investment_summary`: one-page research conclusion;
- `value_flow_summary`: ordered value-chain flow;
- `profit_pool_summary`: explanation of value capture and barriers;
- `catalyst_claim_ids`: references to structured catalyst claims;
- `risk_claim_ids`: references to structured risk claims;
- `validation_signals`: observable indicators for thesis validation;
- `evidence_gap_summary`: explicit statement of unresolved evidence.

All fields are required when a profile is present. Referenced catalyst and risk claims must exist in the same theme artifact.

## New Enums

- claim types: `catalyst`, `risk`;
- theme type: `new_energy_storage`.

These additions do not change the existing research-only guardrails. Deep-industry profiles cannot be used for trading signals, admission, recommendations, or order actions.
