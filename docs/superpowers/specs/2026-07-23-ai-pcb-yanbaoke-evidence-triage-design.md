# AI PCB Yanbaoke Evidence Triage v1 Design

## Objective

Perform a one-time, offline, read-only triage of the 474-report Yanbaoke batch to identify PCB, laminate, copper-foil, manufacturing, and test-related reports that are useful as source-discovery leads or contextual material.

The triage does not update the existing AI PCB Evidence Assessment, cognition package, evidence requirements, company universe, strategy data, or database.

## Inputs and immutability

The audit reads the existing artifacts under:

`outputs/research/theme_company_yanbaoke_20260723/`

Primary inputs are:

- `theme_company_mappings.csv`
- `yanbaoke_download_queue_474.csv`
- `download/yanbaoke_direct_uuid_downloads.csv`
- downloaded readable PDF files referenced by the manifest
- existing duplicate and historical-download metadata

All inputs remain unchanged. The audit performs no network access and no database writes.

## Selection method

The audit examines all 474 queue entries rather than relying only on a fixed company list.

An entry becomes a triage candidate when its title, mapped theme, company identity, structured metadata, or readable body contains specific evidence of relevance to one or more of:

- PCB, high-layer PCB, HDI, mSAP, package substrate, backplane, or high-speed board design;
- copper-clad laminate, dielectric material, resin, Dk, or Df;
- copper foil, HVLP, VLP, RTF, surface profile, or roughness;
- PCB manufacturing, imaging, drilling, lamination, testing, reliability, or related production equipment.

Generic occurrences of words such as “AI”, “server”, “high speed”, “material”, or “network” are insufficient by themselves.

The expected review set is approximately 20–30 reports, but there is no fixed quota. Relevance controls inclusion.

## Content identity and duplicate governance

Reports with the same report identity or raw content hash are one content document. Historical and current-batch records remain visible, but duplicates do not increase:

- document count;
- source independence;
- evidence-chain count;
- technical ER coverage.

The triage records duplicate or common-origin indicators without modifying the existing manifests.

## Classification model

Each selected report receives exactly one primary classification:

- `primary_source_lead`: contains a traceable lead to a company filing, standard, paper, data sheet, measurement report, or other original source;
- `contextual_industry`: useful for industry background but not direct technical or company evidence;
- `company_evidence_lead`: useful as an entry point for future company-specific verification;
- `investment_opinion_non_evidence`: predominantly valuation, recommendation, benefit, ranking, or investment opinion and not usable as evidence.

Additional flags may record overlapping utility, but they do not replace the primary classification.

## Technical ER mapping

The audit may map selected reports to the current technical gaps:

- `PCB-ER-A02`: rate, distance, topology, and measurable channel relationships;
- `PCB-ER-A04`: insertion-loss measurement, fixture removal, de-embedding, reference plane, or coupon methodology;
- `PCB-ER-B01`: Dk/Df test methods and parameter comparability;
- `PCB-ER-B02`: copper-foil profile, roughness, surface treatment, and measured loss relationships.

For each ER, the allowed triage dispositions are:

- `source_discovery_only`;
- `contextual_candidate`;
- `not_relevant`.

The audit must not assign `direct_evidence`, `sufficient`, a claim stance, a confidence upgrade, or an independent evidence-chain count.

## Required fields

The structured result records at least:

- report UUID and stable queue identity;
- title, company, broker or publisher, publication-date status, and local PDF path;
- raw/content hash when available;
- primary classification and classification reason;
- cited or named original-source types;
- traceable source leads and their verification status;
- A02/A04/B01/B02 disposition and relevance reason;
- duplicate/common-origin status;
- limitations and prohibited use;
- manual-review priority.

Publication dates are copied only from established input metadata. The audit does not infer dates from file names, URLs, download timestamps, or copyright text.

## Outputs

The audit writes only these files under the existing run directory:

- `ai_pcb_evidence_triage_v1.csv`: one row per selected content identity;
- `ai_pcb_evidence_triage_audit_v1.json`: input hashes, rules, counts, validation results, and aggregate classifications;
- `ai_pcb_evidence_triage_summary_v1.md`: a human-readable projection of the structured results.

The CSV and JSON are the structured audit sources. The Markdown summary must not introduce reports, source leads, ER mappings, or conclusions absent from them.

## Validation and failure handling

The audit fails closed when:

- an input manifest cannot be parsed;
- a selected row cannot be traced to the queue or download manifest;
- a referenced PDF is missing where the manifest claims a successful download;
- duplicate content is counted as independent evidence;
- an ER disposition exceeds the allowed triage values;
- a report is presented as direct evidence or as satisfying an ER;
- existing inputs change during the run.

Unreadable PDFs may remain selected based on structured metadata, but must be marked `body_not_reviewable` and cannot receive a content-derived source lead.

## Acceptance criteria

- All 474 queue entries are considered.
- Selection is relevance-based rather than quota-based.
- Every selected report has one primary classification.
- Duplicate reports collapse to one content identity for counts.
- Every A02/A04/B01/B02 mapping uses only the permitted triage dispositions.
- Investment conclusions are explicitly excluded from evidence use.
- Existing AI PCB assessment and cognition artifacts remain untouched.
- No network, database, acquisition, company-universe, or strategy write occurs.
- All output CSV/JSON files parse successfully and aggregate counts reconcile.
- The summary states whether the batch provides direct technical evidence, source-discovery leads, company-level leads, or only contextual information.

