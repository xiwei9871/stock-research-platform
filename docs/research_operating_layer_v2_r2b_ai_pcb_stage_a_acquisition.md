# Research Operating Layer V2 R2B — AI Compute PCB Stage A Acquisition

## 1. Normalization Stabilization result

Broadcom raw HTML `evidence_artifact:164d6d7a272660c4edad6aeb` was reproduced entirely offline. The original raw artifact and the Phase C normalization failure remain immutable.

A minimal HTML parser fallback now extracts explicit semantic description metadata only when no visible semantic body exists. It produced a new representation:

- document: `normalized_document:719ca6dd8d68ac5a36ad2508`;
- locator: `html:meta:name:description`;
- raw hash remains `b0e55cb3d8d8eabe454b8b7ea2382e8751edbe6d6ad46ade580a2b814f8d181c`.

No browser, Docling default, script execution or raw-artifact rewrite was used.

## 2. Broadcom failure root cause

The response is valid UTF-8 HTML, not compressed or malformed. Its body contains an empty React mount point and scripts; the product title and description are present in `<title>` and explicit meta tags. The prior parser deliberately ignored non-visible metadata and therefore returned `HTML has no visible semantic content`.

The fix accepts only `meta[name=description]` and `meta[property=og:description]`, deduplicates identical text and emits auditable meta locators. A title without a semantic description still does not make an empty page valid.

## 3. Stage A Requirement Universe

The authoritative universe was derived from v0.2.0 requirements whose `requirement_type` is `A_system_product_facts`:

- ER01: overall architecture-to-PCB system question;
- ER02: AI server versus general-purpose server topology;
- ER03: accelerator, switch, NIC/DPU and backplane relationships by generation;
- ER04: compute-node versus rack/network content location and electrical/optical boundary;
- ER05: server/rack/accelerator/port denominator sensitivity.

ER06 onward was not included. ER17 remains a later Stage E requirement; Lightmatter was reacquired under ER04 only as a Stage A boundary candidate.

## 4. Executed and unexecuted ERs

All five Stage A ERs have acquisition attempts. `unattempted_requirement_ids` is empty.

This records acquisition coverage only. No ER was marked satisfied, complete or closed.

## 5. Candidate overview

The final Stage A checkpoint contains 15 unique candidate IDs across NVIDIA, Intel/Habana, Cisco, Broadcom, Lightmatter and Supermicro.

| ER | Acquired primary candidates | Additional result |
|---|---|---|
| ER01 | Intel Gaudi architecture; NVIDIA DGX SuperPOD B200 | NVIDIA Widen PDF remained blocked/failed |
| ER02 | NVIDIA DGX B200; Cisco UCS C240 M7 | Supermicro GPU-system URL blocked |
| ER03 | NVIDIA BlueField-2; NVIDIA DGX H100; Broadcom Tomahawk 5 | — |
| ER04 | NVIDIA DPU overview; Broadcom Tomahawk 5; Lightmatter Passage | optical boundary retained without stance |
| ER05 | NVIDIA SuperPOD B200; NVIDIA DGX H100; Broadcom Tomahawk 5 | denominator reconciliation deferred |

Search snippets, V1 source-pack text and unknown third-party reposts were not promoted.

## 6. Acquisition attempt overview

Final checkpoint totals:

- 16 attempts;
- 13 acquired;
- 2 blocked;
- 1 historical failed attempt;
- provider distribution: `direct_http=16`;
- proxy distribution: `direct=16`.

Every attempt used zero retries and no automatic provider fallback.

## 7. Successful HTML and PDF

The checkpoint contains:

- 12 acquired HTML artifacts;
- 1 acquired PDF artifact, the NVIDIA BlueField-2 DPU product brief;
- 13 normalized representations.

The two repeated official documents reuse content-addressed raw bytes instead of writing duplicate raw files.

## 8. Official and primary-source coverage

Each Stage A ER has at least two acquired primary/official candidate artifacts recorded in `primary_source_coverage`.

This is source acquisition coverage, not evidence sufficiency. Independent professional secondary and engineering-source discovery remains incomplete while the search provider is unavailable.

## 9. Counter and boundary candidates

Lightmatter Passage was acquired under ER04 as an optical-interconnect boundary candidate. It has no evidence stance, strength, directness or claim relationship.

No Stage E claim or bottleneck evaluation was started.

## 10. Blocked and failed attempts

- Widen attempt `057c44df439c4f842a4108a5`: immutable pre-fix `unknown_failure`;
- Widen retry `d9322b574d572032111aeeff`: fail-closed `security_policy_blocked`;
- Supermicro attempt `9f6f1ae5c590178fea41859c`: fail-closed `security_policy_blocked` because the connected peer could not be verified after its redirect behavior.

None produced raw artifacts or fallback attempts.

## 11. Widen-like redirect cases

The two Widen attempts are explicitly listed in `widen_like_redirect_attempt_ids`. No Widen-specific exception, trusted-peer bypass or DNS-only peer substitution was added.

The Supermicro case exposed the same peer-unavailable class but is tracked separately as an inaccessible candidate rather than being labelled as Widen.

## 12. Raw artifacts

The checkpoint references 13 evidence-artifact identities backed by 11 unique raw SHA-256 values. Every raw file is stored under its content hash and passed byte-size and SHA-256 verification.

No `.part`, `.tmp` or partial artifact remains.

## 13. Normalized artifacts

All 13 Stage A raw artifact identities have a selected normalized representation. HTML used the deterministic standard-library parser; the PDF used `pypdf`.

Every normalized document references its raw artifact ID and therefore the immutable raw content hash.

## 14. Normalization failures

The final Stage A checkpoint has zero current normalization failures.

The original Broadcom failure remains preserved in the Phase C checkpoints. The new metadata-locator representation is additive and does not overwrite that historical record.

## 15. Publication-date unknown status

All 13 acquired Stage A artifacts have `published_at=null` because no explicit, semantically verified publication date was available during acquisition.

The checkpoint records per-artifact:

- `published_at`;
- `updated_at`;
- `accessed_at`;
- `date_status`;
- `date_source`;
- `date_confidence`.

The Broadcom `Last-Modified` metadata, URL years, copyright years and access timestamps were not promoted to publication dates.

## 16. Hash and dedup

Two exact-content duplicate pairs were identified:

- NVIDIA DGX SuperPOD B200 acquired for ER01 and ER05;
- NVIDIA DGX H100 guide acquired for ER03 and ER05.

Independent attempts and evidence-artifact identities are retained, while the raw content-addressed files are reused. Three suspected common-origin groups are recorded for SuperPOD B200, DGX H100 and Broadcom Tomahawk 5.

## 17. Provenance

Candidate, attempt, raw artifact, normalized representation and checkpoint provenance is complete. Required actor, run, timestamp and research-version context fields are present.

No acquisition artifact was promoted to Evidence Assessment.

## 18. Security audit

- `proxy_mode=direct` throughout;
- provider-local `trust_env=False`;
- TLS validation retained;
- DNS, connected-peer and redirect validation retained;
- private/loopback/link-local/reserved blocking retained;
- no browser/manual/proxy fallback;
- no sensitive credential or URL-userinfo persistence;
- `security_violations=[]` in the final checkpoint.

## 19. Stage A checkpoint

- path: `artifacts/research_projects/v2_1/acquisition/checkpoints/acquisition_checkpoint:a5f7627d8726c9405ba67a75.json`;
- checkpoint ID: `acquisition_checkpoint:a5f7627d8726c9405ba67a75`;
- canonical hash: `a5f7627d8726c9405ba67a7527826edb0cff26ee777287e33cb55442bace660e`;
- stage: `stage_a_system_product_facts`;
- status: `pending_assessment`.

No v0.2.2 or v0.3.0 was created.

## 20. Tests and regressions

Pre-closure verification:

- focused parser/schema/checkpoint/scope: `211 passed`;
- V2 / R1-R2 compatibility: `1306 passed`;
- V1 / Theme Research / Dashboard: `449 passed`.

Final completion claims require a fresh post-commit rerun.

## 21. Scope attribution

The exact allowlist is:

`artifacts/research_projects/v2_1/acquisition/stage_a_exact_allowlist.json`

It includes only D0 parser stabilization, Stage A candidates/attempts/raw/metadata/normalization/checkpoint, tests and this report. It forbids project version snapshots, V1, other pilots, Dashboard, API and database paths.

## 22. Unresolved evidence-access gaps

- Search provider remains unavailable.
- Independent professional secondary discovery is incomplete.
- Supermicro accelerator-system page remains blocked by strict peer verification.
- All confirmed publication dates remain unknown.
- ER05 denominator reconciliation requires assessment rather than more acquisition-only counting.

These gaps are preserved and were not filled with low-quality sources.

## 23. Recommendation on Stage A Evidence Assessment

Recommendation: **conditionally proceed to Stage A Evidence Assessment after user confirmation**.

The system-fact acquisition base now spans all five Stage A ERs and multiple primary organizations. Assessment should remain claim-driven, treat publication-date freshness as unknown, avoid counting duplicate/common-origin sources as independent, and allow ER05 to remain unresolved if denominator definitions cannot be reconciled.

## 24. Decisions required before assessment

Confirm whether Stage A Evidence Assessment should:

1. begin with primary-source artifacts while independent-secondary discovery remains incomplete;
2. treat all 13 artifacts as freshness-warning items because publication dates are unknown;
3. exclude the blocked Supermicro and Widen candidates from coverage calculations while retaining their attempts;
4. treat exact duplicates and suspected common-origin groups as one evidence chain during independence review;
5. allow ER05 to remain open if server/rack/accelerator/port denominators cannot be reconciled.

The workflow stops at acquisition and normalization pending those decisions.

## Scope Correction

Stage A acquisition remains technically valid and all original acquisition facts remain unchanged. The original checkpoint, attempts, raw artifacts, normalized representations, blocked results, provenance, duplicate classifications and unknown publication-date states are immutable history.

The current investment boundary is `investment_market_scope = A_share`. Stage A is therefore reclassified through an append-only governance overlay as `global_industry_reference_acquisition`, with status `global_industry_reference_acquisition_complete`.

NVIDIA, Intel / Habana, Cisco, Broadcom, Lightmatter and Supermicro are global industry references only. They provide technology-route, architecture, product-boundary, component-requirement and demand-side context. They are not investment candidates, A-share review-universe members, company-scoring targets, signal targets or admission targets in this project.

The acquired global artifacts may later enter `industry_claim_level_only` assessment. They cannot establish A-share company supply-chain participation, qualification, effective capacity, orders, revenue, profit exposure, beneficiary ranking or investment value. In particular:

```text
global_reference_coverage != a_share_candidate_coverage
primary_source_count != evidence_sufficiency
industry_claim_support != company_exposure_support
```

The formal governance flags are:

```text
company_level_assessment_allowed = false
stage_b_authorized = false
```

Company-level Evidence Assessment is paused. Stage B is not authorized. The next planned step is `Stage A2 — A-share Supply-chain Mapping`; Stage A2 remains research-only and has not started acquisition, candidate generation, scoring or downstream transmission.
