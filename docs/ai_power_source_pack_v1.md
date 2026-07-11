# AI Power Source Pack v1

Updated: 2026-07-10

## Purpose

This Phase 2A package turns the AI-power sample from a placeholder decomposition into a traceable, read-only evidence baseline. It does not write to the database, access the network at runtime, map companies, or produce investment recommendations.

Artifacts:

- `artifacts/theme_decomposition/source_packs/ai_power_source_pack_v1.json`
- `artifacts/theme_decomposition/source_packs/ai_power_claim_review_v1.json`
- `artifacts/theme_decomposition/source_packs/ai_power_node_evidence_matrix_v1.json`

Loader:

- `src/stock_research/ai_power_source_pack.py`

## Source Review Result

Seven public sources are accepted at section or transcript level:

| Source | Accepted use | Explicit limitation |
|---|---|---|
| U.S. DOE data-center demand article | Quantified U.S. demand growth and system response | Official summary, not the underlying LBNL report |
| J.P. Morgan, Powering the AI Revolution | Demand-to-power and grid-capacity framing | Institutional analysis, not a power-system dataset |
| J.P. Morgan, Grid Resilience | Grid buildout and long infrastructure cycles | Does not prove equipment margins or localized scarcity |
| J.P. Morgan, Data Center Surge transcript | Power-denominated capacity, AI workload buildout, capital intensity | Expert commentary, not engineering certification |
| NVIDIA GB200 NVL72 | Rack-scale and liquid-cooled product architecture | Vendor material cannot establish industry economics |
| NVIDIA 800 VDC architecture page | Declared future power route, fewer conversion stages, lower current and copper use | Roadmap evidence, not proof of adoption timing |
| NVIDIA 800 VDC technical blog | Rack power-density and future power-train design | Vendor-authored; profit pools need independent evidence |

Four sources remain `needs_full_text`:

- the original 2024 LBNL report, because local retrieval redirected to an access challenge;
- IEA `Energy and AI`, because the report page was blocked in the current environment;
- exact OCP power specifications, because the official Power page returned access denied;
- a precise domestic broker report with title, date, full text, and excerpts.

Secondary media and the short-video topic remain `lead_only`. They cannot support reviewed claims or reviewed nodes.

## Claim Decisions

Reviewed:

- AI and data-center expansion materially increase electricity demand;
- grid capacity and interconnection are material deployment constraints;
- rack-scale AI systems increase power-density pressure;
- 800 VDC is a documented emerging technical route;
- liquid cooling has a documented role in a reviewed high-density rack product.

Blocked:

- higher rack power does not automatically mean copper captures more value in every architecture, because the 800 VDC route explicitly reduces current, copper use, and cable bulk;
- transformers, switchgear, UPS, PDU, and conversion suppliers do not benefit uniformly, because a mature native DC route can remove, compact, relocate, or change some conventional stages.

Research lead only:

- China localization and listed-company substitution claims remain unverified until product-level filings, customer qualification, market share, and revenue-materiality evidence are attached.

## Node Evidence Result

The evidence matrix covers all 13 canonical nodes.

Nodes upgraded to `reviewed` with `evidence_strength = 3`:

- `grid_connection`
- `hvdc_power`
- `ai_server_integration`
- `liquid_cooling`

This means the node's role or technical route is supported. It does not mean the existing value-capture score, supplier economics, localization gap, or stock mapping is confirmed.

Seven nodes remain explicit evidence gaps, including transformer, switchgear, UPS, copper interconnect, SiC/GaN power semiconductors, power generation, and data-center EPC. Server power supply and rack distribution are classified as `technical_route_only`: their function is visible, but BOM, certification, scarcity, and profit-pool evidence are missing.

## Runtime And Validation

The runtime is offline and standard-library only.

```bash
.venv/bin/python -m stock_research.ai_power_source_pack validate
.venv/bin/python -m stock_research.ai_power_source_pack summary
.venv/bin/pytest tests/test_ai_power_source_pack.py tests/test_theme_decomposition.py -q
```

The validator enforces:

- all three artifacts are present and versioned;
- accepted sources have a public URL, reviewed-document state, evidence locator, paraphrased evidence summary, and limitations;
- reviewed claims reference accepted sources;
- all source, claim, and node references resolve;
- every canonical AI-power node appears exactly once in the evidence matrix;
- reviewed nodes have accepted evidence and evidence strength of at least three.

## Remaining Work

Phase 2A does not establish a complete answer to who captures value. The next evidence work should acquire exact OCP specifications, the LBNL and IEA full reports, utility interconnection and equipment lead-time data, domestic broker full text, company filings, and operator reference designs. Company mapping remains deferred to Phase 4.
