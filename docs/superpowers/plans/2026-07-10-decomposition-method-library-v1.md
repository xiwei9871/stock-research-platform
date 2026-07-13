# Decomposition Method Library v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 3's reusable decomposition method library and prove that a new valid `theme_decomposition_v1_5` artifact can be initialized from any template without template-specific code paths.

**Architecture:** Store three versioned JSON templates in one fixed directory and load them through one standard-library Python module. The module validates a common schema, projects a selected template into the existing compact `decomposition_templates` shape, and initializes a canonical read-only theme artifact with empty evidence and node collections. Existing AI-power and humanoid artifacts remain valid and are used as compatibility examples rather than rewritten.

**Tech Stack:** Python 3, standard-library `argparse`, `json`, and `pathlib`, repository JSON artifacts, pytest.

---

### Task 1: Define the common template contract

**Files:**
- Create: `tests/test_decomposition_templates.py`

- [x] Write a failing loader test that expects exactly `system_bottleneck_v1`, `head_to_toe_v1`, and `manufacturing_process_v1`.
- [x] Write failing validation tests for duplicate step order, missing quality gates, invalid claim types, invalid node types, orphan node archetypes, and incompatible theme initialization.
- [x] Write a failing initialization test that passes the generated artifact to `load_theme_package()` and expects a valid `theme_decomposition_v1_5` package.
- [x] Run `rtk .venv/bin/pytest tests/test_decomposition_templates.py -q` and verify collection fails because `stock_research.decomposition_templates` does not exist.

### Task 2: Implement the generic loader and initializer

**Files:**
- Create: `src/stock_research/decomposition_templates.py`

- [x] Implement `load_decomposition_template_library()`, `load_decomposition_template()`, `summarize_decomposition_template_library()`, and `initialize_theme_from_template()`.
- [x] Validate one shared schema covering template identity, compatible theme types, ordered steps, node archetypes, claim types, value bases, source requirements, initialization defaults, examples, and output schema.
- [x] Project rich templates into the existing compact fields: `template_id`, selected `theme_type`, string `steps`, `required_dimensions`, `optional_dimensions`, and `output_schema`.
- [x] Implement `validate`, `summary`, `show`, and `initialize` subcommands. `initialize` prints JSON unless `--output` is provided.
- [x] Re-run the focused test and verify it now fails only because the three template artifacts are absent.

### Task 3: Create the three reusable templates

**Files:**
- Create: `artifacts/theme_decomposition/decomposition_templates/system_bottleneck_template.json`
- Create: `artifacts/theme_decomposition/decomposition_templates/head_to_toe_template.json`
- Create: `artifacts/theme_decomposition/decomposition_templates/manufacturing_process_template.json`

- [x] Encode the roadmap's system-bottleneck flow from demand shock through bottleneck, supply constraint, value migration, evidence, and later company mapping.
- [x] Encode the head-to-toe flow from whole-system structure through functional systems, components, routes, BOM, import dependence, localization, and evidence.
- [x] Encode the manufacturing-process flow from process steps through equipment, materials, yield bottlenecks, overseas leaders, localization, customer verification, and evidence.
- [x] Keep company mapping as an optional downstream dimension and require evidence gates before publication.
- [x] Run the focused tests until green.

### Task 4: Prove compatibility with existing themes

**Files:**
- Modify: `tests/test_decomposition_templates.py`
- Verify: `artifacts/theme_decomposition/ai_power_value_capture_v1.json`
- Verify: `artifacts/theme_decomposition/humanoid_robotics_head_to_toe_v1.json`

- [x] Assert AI power uses the system-bottleneck family and humanoid robotics uses the head-to-toe family through each template's `example_theme_ids`.
- [x] Initialize one `ai_compute`, one `humanoid_robotics`, and one `semiconductor_equipment` theme and validate each through the existing theme loader.
- [x] Assert initialization rejects a theme type outside the selected template's compatibility list.

### Task 5: Document and verify Phase 3

**Files:**
- Create: `docs/decomposition_method_library_v1.md`
- Modify: `docs/theme_driven_research_engine_roadmap.md`
- Modify: `docs/theme_decomposition_research_baseline_v1.md`

- [x] Document schema, template selection rules, initialization workflow, CLI commands, boundaries, and extension rules.
- [x] Mark Phase 3 complete while leaving unfinished Phase 2B visible.
- [x] Run `rtk .venv/bin/pytest tests/test_decomposition_templates.py tests/test_theme_decomposition.py tests/test_ai_power_source_pack.py -q`.
- [x] Run each library CLI command and validate an initialized artifact with `stock_research.theme_decomposition`.
- [x] Validate all JSON files with `jq empty` and inspect the scoped repository status.
