# AI PCB Stage A Scope Correction and Stage A2 Plan

## Decision

The completed AI Compute PCB Stage A is an append-only `global_industry_reference_acquisition`, not an equity-candidate acquisition.

```text
investment_market_scope = A_share
corrected_stage_role = global_industry_reference_acquisition
evidence_assessment_allowed = industry_claim_level_only
company_level_assessment_allowed = false
stage_b_authorized = false
```

The original acquisition checkpoint remains authoritative for acquisition facts:

- checkpoint ID: `acquisition_checkpoint:a5f7627d8726c9405ba67a75`;
- canonical content hash: `a5f7627d8726c9405ba67a7527826edb0cff26ee777287e33cb55442bace660e`;
- file-byte SHA-256: `e2b91137df1c01a7fa7b30c8ed9cdd8b052e30ad3a57a274519fab20cb2f07ae`.

The correction does not overwrite the checkpoint or any candidate, attempt, raw artifact, normalized artifact, normalization history, provenance, blocked result, duplicate result or publication-date status.

## Global entity roles

The following entities have the same governance overlay:

| Entity | Role | Investment candidate | A-share review universe | Company scoring | Signal | Admission |
| --- | --- | --- | --- | --- | --- | --- |
| NVIDIA | global industry reference | false | false | false | false | false |
| Intel / Habana | global industry reference | false | false | false | false | false |
| Cisco | global industry reference | false | false | false | false | false |
| Broadcom | global industry reference | false | false | false | false | false |
| Lightmatter | global industry reference | false | false | false | false | false |
| Supermicro | global industry reference | false | false | false | false | false |

Lightmatter Passage remains usable as an ER04 boundary or alternative-route reference. This role carries no company or stock conclusion.

## Evidence boundary

The existing ER01–ER05 definitions are preserved.

Global primary artifacts may later support industry-level claims about:

- AI compute and accelerator architecture;
- scale-up, scale-out and rack-level topology;
- electrical and optical interconnect boundaries;
- product specifications and technical capability limits;
- component, material, equipment and manufacturing requirements;
- upstream demand mechanisms and technology substitution risk;
- value-chain segments that should be examined in the A-share market.

They cannot directly support a claim that an A-share company:

- has entered a specific supply chain;
- has completed qualification;
- has effective mass-production capacity;
- has received orders;
- has recognized revenue or profit;
- has a defined exposure or beneficiary rank;
- is investable at the current price.

The controlling invariants are:

```text
global_reference_coverage != a_share_candidate_coverage
primary_source_count != evidence_sufficiency
industry_claim_support != company_exposure_support
```

A future company-specific assessment requires company announcements, annual reports, exchange inquiries, investor-relations records, product material, customer evidence or independently auditable supply-chain evidence.

## Preserved acquisition rules

- Blocked candidates count toward attempt coverage only.
- Exact-content duplicates count as one evidence chain during assessment.
- Suspected common-origin sources default to one provisional evidence chain.
- Unknown publication dates remain unknown and retain freshness warnings.
- ER05 denominator reconciliation remains open.
- Widen remains fail-closed without a security exception.
- Network acquisition remains explicit direct HTTP with provider-local `trust_env=False`.

## Stage A2 — A-share Supply-chain Mapping

Stage A2 acquisition has not started. Its status is `planned`, and it is `research_only`.

### Purpose

Stage A2 will translate traceable global technology and system facts into A-share supply-chain research hypotheses. It will not treat overseas demand growth as proof that a domestic listed company benefits.

The required object flow is:

```text
global_technology_claim
    -> component_or_process_requirement
    -> value_chain_segment
    -> a_share_candidate_hypothesis
    -> company_specific_evidence_requirement
```

The invalid shortcut is:

```text
NVIDIA demand growth
    -> A-share company necessarily benefits
```

### Inputs

- ER01–ER05;
- the immutable Stage A acquisition checkpoint;
- acquired global industry reference artifacts;
- future industry-claim-level assessments;
- unresolved boundaries, counter candidates, duplicates and freshness warnings.

### Planned outputs

- a traceable list of component and process requirements;
- a value-chain segment map;
- direct, indirect, substitution and high-uncertainty path classifications;
- A-share candidate discovery rules;
- a draft candidate universe for later human review;
- company-specific Evidence Requirements for every retained hypothesis.

The draft universe is not generated in this task.

### Candidate mapping dimensions

The following are discovery dimensions, not confirmed beneficiaries:

- high-speed PCB;
- high-layer-count PCB;
- HDI;
- high-speed copper-clad laminate and critical resin;
- high-speed connectors;
- copper and high-speed cable assemblies;
- optical modules;
- optical components and optical chips;
- switches and network equipment;
- servers and rack systems;
- power;
- liquid cooling;
- advanced packaging;
- testing and manufacturing equipment;
- domestic switching, interface or interconnect chips;
- other segments derived from ER01–ER05 evidence.

Every retained dimension must be traceable to industry-reference evidence. A category is removed or narrowed if the evidence does not support it.

### Acceptance criteria

1. Every candidate segment traces to an ER01–ER05 industry reference artifact.
2. Technology requirements are mapped to components or processes before company discovery.
3. Direct, indirect, substitution and high-uncertainty paths remain distinct.
4. Each company hypothesis has company-specific Evidence Requirements before assessment.
5. Global primary-source coverage is never counted as A-share company coverage.
6. No company-level conclusion is created from industry evidence alone.

### Forbidden outputs

Stage A2 does not create:

- company scores;
- stock recommendations;
- signals;
- admissions;
- portfolios;
- strategies;
- trades;
- watchlist or review-universe writes;
- Dashboard, API or database mutations.

## Stop condition

Work stops after this scope correction and Stage A2 plan. Starting A-share candidate discovery or acquisition requires a separate authorization and a new append-only checkpoint or research artifact.
