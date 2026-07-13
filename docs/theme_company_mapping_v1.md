# Theme Company Mapping v1

Updated: 2026-07-10

## Purpose

Phase 4 adds a read-only mapping layer:

```text
theme -> theme node -> company -> excerpt-level evidence
```

The mapping answers what product or service connects a company to a node and how material that relationship is. It does not provide valuation, recommendations, price targets, trading signals, or automatic watchlist admission.

## Artifact And Loader

Sample artifact:

`artifacts/theme_decomposition/company_mappings/ai_power_company_mapping_v1.json`

Loader:

`src/stock_research/theme_company_mapping.py`

The runtime is offline, standard-library only, and does not write to the database.

## Mapping Fields

The roadmap fields are implemented directly:

- `company_code`
- `company_name`
- `market`
- `mapped_node_id`
- `mapping_type`
- `confidence`
- `evidence_ids`
- `revenue_relevance`
- `bottleneck_relevance`
- `notes`

Additional quality-control fields are required:

- `mapping_id`
- `theme_id`
- `business_stage`
- `business_materiality`
- `product_or_service`
- `relationship_summary`
- `review_status`

## Business Stage Separation

`primary_business` means an accepted filing or official source directly places the mapped product or service in current operations.

`reserve_stage` means the company has disclosed development, testing, planned capacity, or a future route, but current material revenue is not established. It must use `business_materiality = reserve_only` and cannot claim material revenue.

`concept_exposure` means the available evidence is only thematic association, company mention, or an unverified market narrative. It must use `business_materiality = concept_only` and `revenue_relevance = none`, and it cannot be promoted to `reviewed`.

## Evidence Model

Company mappings reference excerpt-level `evidence_item` records rather than raw source IDs alone. Each evidence item contains:

- source ID;
- evidence type;
- report page or section locator;
- paraphrased evidence summary;
- related company codes;
- related theme-node IDs.

Every mapping status, including `draft`, `research_lead`, and `blocked`, must retain at least one evidence item. A mapping artifact is self-contained: its mappings cannot borrow evidence or sources from another artifact, and all nodes in the artifact must belong to its declared theme.

Accepted `S0`/`S1` sources must include usable title, publisher, publication date, and URL/reference metadata. Evidence locators/summaries and the company relationship description are validated as non-empty strings so the read model has a stable JSON contract.

A reviewed mapping must have:

1. confidence of at least `0.7`;
2. at least one accepted `S0` or `S1` source supporting the direct relationship;
3. accepted direct product, service, or customer-relationship evidence;
4. evidence scoped to the same company and node;
5. explicit business stage, revenue relevance, bottleneck relevance, and business materiality.
6. accepted `revenue_materiality` evidence when it claims material, meaningful, or limited revenue, or a core/meaningful business segment.

A company mention by itself cannot support a reviewed mapping. Weaker sources may be retained as supplemental context, but they cannot satisfy the reviewed relationship or materiality gates.

## Revenue Relevance

- `material`: the filing directly discloses mapped-product or tightly matching segment revenue as material to the company;
- `meaningful`: a directly matching disclosed segment is meaningful but not dominant;
- `limited`: directly matching disclosed revenue is small;
- `undisclosed`: a direct product relationship exists but exact mapped-node revenue is not separately disclosed;
- `none`: no current revenue is established.

Broader segment revenue cannot automatically be assigned to a narrower node. This is why data-center product revenue does not become UPS-only, HVDC-only, or liquid-cooling-only revenue.

## Read Model

The package loader retains normalized sources, evidence items, and mappings. The `show-theme` and `show-company` commands return each mapping with an expanded `evidence` array; every evidence item includes its excerpt locator, summary, and resolved `source`. Callers therefore do not need to join opaque evidence IDs themselves.

## AI Power Samples

| Company | Node | Relationship | Revenue relevance | Filing conclusion |
|---|---|---|---|---|
| 英维克 `002837.SZ` | `liquid_cooling` | Direct product | `undisclosed` | The filing lists an end-to-end liquid-cooling portfolio; only the broader machine-room temperature-control segment is quantified |
| 科华数据 `002335.SZ` | `ups` | Direct product | `undisclosed` | UPS and AIDC power products are directly disclosed; only the broader data-center product segment is quantified |
| 欧陆通 `300870.SZ` | `server_power_supply` | Direct product | `material` | Data-center power generated 45.17% of revenue and the filing identifies server/GPU power products |
| 中恒电气 `002364.SZ` | `hvdc_power` | Direct product | `undisclosed` | HVDC products and scaled data-center deployments are disclosed; only broader data-center power revenue is quantified |

All four mappings use 2025 annual reports published through CNINFO. They are research mappings, not investment conclusions.

## CLI

```bash
.venv/bin/python -m stock_research.theme_company_mapping validate
.venv/bin/python -m stock_research.theme_company_mapping summary
.venv/bin/python -m stock_research.theme_company_mapping show-theme \
  --theme-id ai_power_value_capture_v1
.venv/bin/python -m stock_research.theme_company_mapping show-company \
  --company-code 300870.SZ
```

## Current Boundary

- only the AI-power sample has company mappings;
- Phase 2B humanoid evidence remains unfinished, so robotics companies are not mapped yet;
- mappings are artifacts, not DB rows;
- existing tech-bottleneck admission and review decisions are untouched;
- Phase 5 will add a reversible crosswalk to the existing tech-bottleneck universe.
