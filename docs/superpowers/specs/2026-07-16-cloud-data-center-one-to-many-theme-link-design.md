# Cloud Data Center One-to-Many Theme Link Design

## Goal

Complete the final Wave B theme, `cloud_data_center_infrastructure_value_chain_v1`, while preserving the Industry Catalog as the canonical structural directory and the Theme Research package as the readable research layer.

The approved design allows one research node to map to multiple canonical catalog nodes when the research node intentionally represents a family or integrated stage that is decomposed more finely in the catalog.

## Current Constraint

`technology_industry_catalog._validate_node_links()` currently rejects any repeated `theme_node_id`. That enforces a one-to-one research-node-to-catalog-node relationship even when the catalog has several semantically complete child nodes for one integrated research node.

The cloud data-center catalog already contains a detailed L3/L4 facility, cooling, delivery, commissioning, and operations tree. Splitting the deep-research theme into one node per catalog leaf would make the research harder to read and would duplicate conclusions, claims, evidence, and company mappings.

## Approved Mapping Model

`theme_links.json` continues to use the existing list shape:

```json
{
  "theme_node_id": "thermal_liquid_cooling_systems",
  "catalog_node_id": "data_center_cold_plate"
}
```

The validator changes from theme-node uniqueness to pair and ownership uniqueness:

1. A `theme_node_id` may appear more than once within one theme link.
2. The pair `(theme_node_id, catalog_node_id)` must be unique.
3. A `catalog_node_id` may appear only once within one theme link.
4. The catalog node must belong to the theme link's canonical `chain_id`.
5. A linked research node cannot also appear in `unmapped_theme_node_ids`.
6. Every research node must still be accounted for by at least one link or by the unmapped list.
7. Projection and dashboard read models preserve every pair; they must not collapse repeated research-node rows into a dictionary keyed only by `theme_node_id`.

This keeps the schema backward compatible: existing one-to-one theme links remain valid without migration.

## Cloud Theme Structure

The deep-research package will contain ten readable research nodes:

1. Data-center facility systems and modular deployment
2. Power availability and electrical architecture dependency
3. Backup power, storage, and resilience dependency
4. Thermal and liquid-cooling systems
5. Heat rejection, chillers, pumps, and waste-heat recovery
6. Water, refrigerant, and environmental constraints
7. DCIM, monitoring, and energy-management platforms
8. Design, integration, EPC, commissioning, and certification
9. Facility operations and lifecycle services
10. Customer deployment, utilization, and commercial validation

Nodes 2, 3, 6, and 10 remain unmapped unless a complete canonical node exists in the cloud data-center chain. Power equipment, storage, grid, and generic industrial-software ownership remain on their respective canonical chains.

## Canonical Node Links

The approved one-to-many links are:

| Research node | Canonical catalog nodes |
|---|---|
| Facility systems and modular deployment | `data_center_facility_systems_services`, `modular_data_center_system` |
| Thermal and liquid-cooling systems | `data_center_cold_plate`, `immersion_cooling_system`, `spray_cooling_system`, `coolant_distribution_unit`, `liquid_cooling_quick_connector`, `liquid_cooling_pipe_system`, `data_center_coolant`, `liquid_cooling_leak_detection_system` |
| Heat rejection and heat recovery | `data_center_chiller`, `liquid_cooling_pump`, `data_center_heat_exchanger`, `data_center_waste_heat_recovery_system` |
| DCIM and monitoring | `data_center_infrastructure_management_platform` |
| Design, integration, delivery, and commissioning | `data_center_electrical_design_service`, `liquid_cooling_integration_service`, `data_center_epc_service`, `data_center_commissioning_certification_service` |
| Facility operations | `data_center_facility_operations_service` |

The theme-link notes must state why each group is a complete family/stage mapping rather than a partial semantic overlap.

## Research and Evidence Contract

The cloud package uses the same deep-research contract as the other Wave B/C themes:

- 10 research nodes
- At least 10 accepted sources and at least 4 primary sources
- At least 10 claims
- At least 8 reviewed company mappings
- Seven readable sections: conclusions, value chain, profit pools and barriers, catalysts/validation/risks, beneficiaries, sources, and evidence gaps
- Exact source identity across theme, source pack, matrix, and company mapping
- Direct source-to-claim-to-node support; broad annual-report claims cannot attach a source to unrelated nodes
- Product, revenue/materiality, and risk/stage evidence for each reviewed company mapping

The prepared research target is 11 accepted primary sources, 13 claims, and 11 reviewed mappings. Final counts may increase during implementation but may not fall below the batch gates.

## Data Flow and Read Models

1. The catalog loader validates the link pairs and canonical ownership.
2. `project_theme_to_catalog()` returns all link pairs and the unmapped node list.
3. Catalog cards and node detail views continue to deep-link to the single cloud research theme.
4. Several catalog leaves may therefore open the same research theme, with the corresponding research node retained as navigation context when the consumer supports it.
5. Theme Research remains the source of readable conclusions, evidence, and company mappings; the catalog remains the structural taxonomy.

No database schema change is required. The link remains a JSON list of pairs, and the deep-research import path is unchanged.

## Error Handling

The catalog loader must fail closed with `THEME_CATALOG_NODE_LINK_INVALID` for:

- Duplicate `(theme_node_id, catalog_node_id)` pairs
- Reuse of one catalog node by two research nodes in the same theme
- Missing research-node references
- Missing catalog-node references
- Catalog nodes owned by another chain
- A research node present in both linked and unmapped sets
- Research nodes omitted from both linked and unmapped sets

The error should include the offending pair and JSON path.

## Testing

Implementation must start with failing tests for:

1. A valid one-to-many cloud link that the current validator rejects.
2. Duplicate pair rejection.
3. Duplicate catalog-node ownership rejection.
4. Cross-chain catalog-node rejection.
5. Linked/unmapped overlap rejection.
6. Projection preserving all one-to-many pairs.
7. Dashboard catalog cards and theme routes resolving the cloud theme.
8. Four cloud research artifacts satisfying the Wave B batch verifier.
9. Source, claim, node, matrix, mapping, and readable-section semantic boundaries.
10. Full Wave B readiness changing from 4/5 to 5/5 without regressing Waves A or C.

## Rollout and Compatibility

The change is additive and backward compatible. Existing theme links remain valid. The validator becomes more expressive but stricter about duplicate pairs and catalog-node ownership.

Rollout is complete only when:

- Wave B reports 5/5 ready.
- The full next-fifteen batch reports 15/15 ready.
- Backend, catalog, dashboard, and frontend route tests pass.
- Independent spec and quality reviews have no Critical or Important findings.
- The 5174 Theme Research and Industry Catalog views show the cloud theme and its company/evidence content.

## Non-Goals

- Do not split the cloud research theme into one theme node per catalog leaf.
- Do not move power equipment, storage, grid, server, networking, or generic software ownership into the cloud facility chain.
- Do not add database tables or change the public theme-link JSON shape.
- Do not implement Wave D as part of this change.
