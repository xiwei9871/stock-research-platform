# Decomposition Method Library v1

Updated: 2026-07-10

## Purpose

Phase 3 turns theme decomposition from two theme-specific examples into a reusable research method library. A new theme can now be initialized from a selected template and immediately validated by the existing `theme_decomposition_v1_5` loader.

The library remains read-only and offline. It does not write to the database, map companies, generate recommendations, or bypass the Phase 1.5 evidence gates.

## Template Library

The three templates are stored under:

```text
artifacts/theme_decomposition/decomposition_templates/
  system_bottleneck_template.json
  head_to_toe_template.json
  manufacturing_process_template.json
```

### System Bottleneck

Use for demand-driven systems such as AI power, AI compute, industrial software dependencies, and selected semiconductor-equipment themes.

```text
demand shock -> system boundary -> system bottleneck -> chain nodes
-> supply constraints -> value migration -> localization -> company-mapping queue
```

The existing `ai_power_value_capture_v1` theme is registered as an example.

### Head To Toe

Use for complex machines that can be decomposed by physical region and functional system, especially humanoid robotics.

```text
whole system -> physical regions -> functional systems -> components
-> technical routes -> BOM/value -> bottlenecks -> localization
```

The existing `humanoid_robotics_head_to_toe_v1` theme is registered as an example.

### Manufacturing Process

Use for process-intensive themes such as semiconductor equipment and advanced manufacturing.

```text
process flow -> equipment -> materials -> process control -> yield bottleneck
-> value capture -> localization and verification -> company-mapping queue
```

## Common Schema

Every template uses `decomposition_template_v1` and contains:

- template identity and family;
- compatible existing `theme_type` values;
- eight ordered research steps;
- required inputs, output dimensions, and quality gates for each step;
- seven generic node archetypes with parent-child relationships;
- allowed claim types and value bases;
- evidence-source requirements;
- initialization defaults;
- the existing `theme_decomposition_v1_5` output schema;
- example theme IDs where available.

The loader rejects duplicate or non-contiguous step order, missing quality gates, invalid node or claim types, orphan node archetypes, invalid source-review requirements, and incompatible theme initialization.

## Initialization

The initializer is generic. It does not contain separate code paths for AI power, robotics, or semiconductor equipment. Template behavior comes from the JSON artifact.

Example:

```bash
.venv/bin/python -m stock_research.decomposition_templates initialize \
  --template system_bottleneck_v1 \
  --theme-id ai_compute_supply_v1 \
  --theme-name "AI Compute Supply" \
  --theme-type ai_compute \
  --last-updated 2026-07-10
```

The result is a valid draft artifact containing:

- canonical theme metadata;
- empty source, claim, node, and value-assessment collections;
- an empty evidence-policy state;
- a compact projection of the selected template under the existing `decomposition_templates` field.

This keeps one output schema and one validation path. Researchers then add theme-specific nodes and evidence through the existing workflow.

## CLI

```bash
.venv/bin/python -m stock_research.decomposition_templates validate
.venv/bin/python -m stock_research.decomposition_templates summary
.venv/bin/python -m stock_research.decomposition_templates show \
  --template manufacturing_process_v1
```

Use `--output <path>` with `initialize` to write a generated artifact. Without it, the CLI prints JSON to stdout.

## Extension Rules

A future template must:

1. use the common schema and loader;
2. target existing canonical `theme_type`, `node_type`, `claim_type`, and `value_basis` enums;
3. provide quality gates for every research step;
4. preserve source and evidence review requirements;
5. produce `theme_decomposition_v1_5` until a separately reviewed schema migration is approved;
6. keep company mapping optional and downstream of reviewed nodes and evidence.

## Current Boundary

Phase 3 provides methods and initialization, not completed research. A generated theme is intentionally empty and draft. Phase 2B evidence work remains unfinished, and Phase 4 company mapping must not infer company relevance directly from a template.
