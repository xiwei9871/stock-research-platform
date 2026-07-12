# Technology Industry Catalog v1

## Purpose

Technology Industry Catalog v1 is the read-only, artifact-first structural catalog for technology research. It provides the industry tree that Theme Research and Theme Decomposition can project into; it does not replace their evidence, claim-review, or workflow records.

The catalog also complements the existing Tech Bottleneck review universe. That universe is a company-coverage baseline, while this catalog starts from technology and industry structure. A catalog node can exist without a listed-company mapping, and an existing reviewed company does not define the catalog boundary.

## Taxonomy and Chain Kinds

The hierarchy is:

```text
L1 sector
  L2 chain
    L3 segment, system, process stage, or technical route
      L4 research object, component, equipment, material, software, service, or route
```

- **L1 sector** is the durable top-level technology sector for navigation and coverage reporting.
- **L2 chain** is an independently researchable industry chain with its own boundaries, decomposition method, and review needs.
- **L3** is the organizing layer for a system subsystem, manufacturing stage, infrastructure-flow stage, or technical route.
- **L4** is the research object: the smallest canonical unit that can later carry evidence and company-mapping work.

Every L2 declares one `chain_kind`:

- `canonical_industry_chain`: the canonical home for industry nodes. Use it for stable supply-chain structures such as semiconductor manufacturing equipment or humanoid robots and embodied intelligence.
- `application_theme_chain`: a cross-industry application view. Use it when the chain is composed from existing canonical nodes, such as AI data-center power.
- `frontier_technology_chain`: a route-oriented view for technologies whose product and supply-chain boundaries are not yet stable. Use it to compare routes, enabling conditions, maturity, and commercialization gates.

## Ownership, Composition, and Edges

Each canonical research object has one canonical ownership path. Cross-chain relationships use typed edges rather than copying the node into another tree. Supported edge types are `depends_on`, `enables`, `supplies`, `uses`, `substitutes`, `competes_with`, and `downstream_of`.

Application-theme L4 roles are projections, not duplicate components. They use `canonical_node_refs`, and each application role has a matching record under `artifacts/technology_industry_catalog/v1/theme_compositions/`. This preserves a single canonical owner and allows an application view to aggregate the relevant objects. Keep company mappings on canonical L4 nodes when that later work is introduced; v1 does not write or automate company mappings.

Avoiding duplicate nodes keeps evidence, ownership, and future company coverage attributable to one research object. It also lets a relationship such as a robot joint using a motor or reducer be expressed precisely with a typed edge or canonical reference instead of creating competing copies.

## Current Inventory

The current `summary` reports 10 sectors and 82 L2 chains. Of those, 13 are structurally detailed because they contain both L3 and L4 nodes; 69 are unexpanded skeletons. These counts are a snapshot of the current artifacts and will evolve as branches expand.

The three primary pilots are:

- `semiconductor_manufacturing_equipment`
- `humanoid_robots_embodied_intelligence`
- `ai_data_center_power`

Structural completeness, evidence completeness, and company coverage are different measures. Structural completeness asks whether the L3/L4 tree exists. Evidence completeness asks whether claims and source review are sufficient. Company coverage asks whether relevant companies are mapped with appropriate support. v1 reports only structural completeness.

`status` is a lifecycle label, not a structural-detail flag:

- `skeleton`: registered baseline awaiting substantive work.
- `draft`: working content not yet reviewed.
- `reviewed`: content that has passed its applicable review.
- `published`: released catalog content.

A `skeleton` chain can have structural detail, and a `draft`, `reviewed`, or `published` status does not by itself establish evidence completeness or company coverage.

## Operator Commands

Run these commands from the repository root:

```bash
.venv/bin/python -m stock_research.cli technology-industry-catalog validate
.venv/bin/python -m stock_research.cli technology-industry-catalog summary
.venv/bin/python -m stock_research.cli technology-industry-catalog show --chain ai_data_center_power
```

For programmatic lookup, load once and use the exact-match helper:

```python
from stock_research.technology_industry_catalog import (
    find_industry_chain,
    get_industry_chain,
    load_industry_catalog,
)

catalog = load_industry_catalog()
chain = find_industry_chain(catalog, "AI data-center power")
detail = get_industry_chain(catalog, chain["chain_id"])
```

Chain lookup compares IDs, names, and aliases with `strip()` plus `casefold()`. It does not use fuzzy matching. A matching alias on more than one chain raises `AMBIGUOUS_CHAIN_ALIAS`; an absent or blank lookup raises `CHAIN_NOT_FOUND`.

## Adding an L2 Skeleton

1. Edit `artifacts/technology_industry_catalog/v1/chains.json` and add the L2 record with a stable `chain_id`, `sector_id`, `chain_name`, `chain_kind`, and `decomposition_method`.
2. Set the intended `order` and lifecycle `status`; describe the chain boundary through `scope` and `exclusions`, and add exact aliases in `aliases`.
3. Keep the chain independently researchable. Do not add a chain solely because it is a component, market label, or a different view of an existing canonical object.
4. Update the relevant catalog tests, including `tests/test_technology_industry_catalog_skeleton.py` when its inventory or expected skeleton metadata changes.
5. Run catalog validation and summary to confirm the chain is accepted and reported as intended.

## Expanding L3 and L4

Add nodes in a chain artifact under `artifacts/technology_industry_catalog/v1/nodes/`. Each node must carry the required `chain_id`, `parent_node_id`, `level`, `node_kind`, and `status` fields. L3 nodes have a null parent; L4 nodes name an L3 parent in the same chain. Canonical L4 nodes use one unique `canonical_key` and the required `primary_path`.

For an application theme, create `application_role` nodes with `canonical_node_refs` that point to existing canonical nodes, then add the matching composition entry in `theme_compositions/`. Do not recreate the referenced component. Add a row to `edges.json` only for a real typed relationship and ensure its node and source references resolve. Run `validate` after every artifact change; validation rejects duplicate canonical ownership, invalid parents, incompatible node kinds, unresolved references, and application roles without a matching composition.

## v1 Boundary

v1 is limited to versioned catalog artifacts, the loader, and the read-only CLI. It does not perform database writes, schema migrations, dashboard writes, automated company mapping, or fabricated evidence-completeness reporting. Theme Research, Theme Decomposition, and the Tech Bottleneck review universe remain their existing systems of record for their respective workflows.
