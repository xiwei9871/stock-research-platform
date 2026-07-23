from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2_1.consolidated_assessment import (
    AUTHORIZATION_NAME,
    CONSOLIDATED_AUTHORIZED_ER_IDS,
    render_consolidated_assessment_report,
    validate_consolidated_assessment_artifact,
    validate_persisted_consolidated_assessment_report,
)
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.snapshot import _publish_bytes
from stock_research.research_project_v2_1.targeted_assessment import compute_er_assessment


LAYOUT = LayeredResearchLayout.default()
ANALYSIS_NAME = "ai_pcb_targeted_evidence_assessment_wave_1b_consolidated_v1.json"
REPORT_NAME = "ai_pcb_targeted_evidence_assessment_wave_1b_consolidated_v1.md"
CREATED_AT = "2026-07-23T03:00:00Z"

SOURCES = {
    "a02_cei": (
        "evidence_artifact:eef74cc4d075e6b996599fc3",
        "normalized_document:8071e914d22caaed45914cac",
    ),
    "a02_framework": (
        "evidence_artifact:3545a22276fe30d8dcb1440c",
        "normalized_document:1f503b4ce9f191fdd7e225ca",
    ),
    "a04_cei": (
        "evidence_artifact:291792bb9ba603b04bd4382f",
        "normalized_document:451442cedcaab779e04be686",
    ),
    "b01_table": (
        "evidence_artifact:6e7d5f108e1ac7833d41b219",
        "normalized_document:f5daf52f0ba2e511f6f7f90c",
    ),
    "b02_isola": (
        "evidence_artifact:6d6a80e65b045e0a9025c910",
        "normalized_document:0e3c7fd470c06f407d0d07a3",
    ),
    "b02_paper": (
        "evidence_artifact:11d564e0e47f4118abc6d0c1",
        "normalized_document:72b1be30c0a4d52262534438",
    ),
    "nist_a04": (
        "evidence_artifact:92ca57b518be8af5cb15e31d",
        "normalized_document:fd60b1b4e815747495188397",
    ),
    "nist_b01": (
        "evidence_artifact:7305a7ff435cc1e69d72485f",
        "normalized_document:c9b935aa14bdf30fe3c8a640",
    ),
    "ieee_3ck": (
        "evidence_artifact:5cf8a72e4f4c6a9043a474c5",
        "normalized_document:019803185d3da18b4d1f2486",
    ),
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def locator(source: str, section_index: int, note: str) -> dict[str, Any]:
    artifact_id, document_id = SOURCES[source]
    wrapper = _load(LAYOUT.evidence_normalized_dir / f"{document_id}.json")
    section = wrapper["normalized_document"]["sections"][section_index]
    return {
        "artifact_id": artifact_id,
        "normalized_document_id": document_id,
        "section_index": section_index,
        "section_hash": section["section_hash"],
        "heading": section.get("heading"),
        "locator_note": note,
    }


def claim(
    claim_id: str,
    er_id: str,
    text: str,
    *,
    scope: str,
    generation: str,
    rate: str,
    frequency: str,
    distance: str,
    topology: str,
    test_method: str,
    denominator: str,
    locators: list[dict[str, Any]],
    chains: list[str],
    status: str,
    reason: str,
    maximum: str,
    claim_type: str = "fact",
    stance: str = "support",
    independence: str = "single_primary_chain",
    evidence_strength: str = "high",
    confidence: str = "medium",
    freshness: str = "unknown",
    limitations: list[str] | None = None,
    counterevidence: list[str] | None = None,
    alternatives: list[str] | None = None,
    missing: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "er_id": er_id,
        "claim_text": text,
        "claim_type": claim_type,
        "scope": scope,
        "product_or_standard_generation": generation,
        "rate": rate,
        "frequency": frequency,
        "distance": distance,
        "topology": topology,
        "test_method": test_method,
        "denominator": denominator,
        "evidence_locators": locators,
        "evidence_stance": stance,
        "evidence_chain_ids": chains,
        "source_independence_status": independence,
        "freshness_status": freshness,
        "assessment_status": status,
        "evidence_strength": evidence_strength,
        "confidence": confidence,
        "assessment_reason": reason,
        "limitations": list(limitations or []),
        "counterevidence": list(counterevidence or []),
        "alternative_explanations": list(alternatives or []),
        "missing_evidence": list(missing or []),
        "maximum_supported_cognition": maximum,
    }


def build_claims() -> list[dict[str, Any]]:
    baseline = _load(
        LAYOUT.analysis_dir / "ai_pcb_targeted_evidence_assessment_wave_1_v1.json"
    )
    retained = [
        deepcopy(row)
        for row in baseline["atomic_claims"]
        if row["er_id"] in CONSOLIDATED_AUTHORIZED_ER_IDS
        and row["claim_id"]
        not in {"W1-A04-C02", "W1-B01-C03"}
    ]
    no_industry = [
        "The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure."
    ]
    retained.extend(
        [
            claim(
                "CON-A04-C02",
                "PCB-ER-A04",
                "NIST Technical Note 1520 defines insertion loss and describes a two-line-length method that subtracts common calibration and sample-holder mismatch when those effects are equivalent between measurements.",
                scope="NIST Technical Note 1520 conductor-loss measurement discussion",
                generation="NIST Technical Note 1520, explicitly dated July 2001",
                rate="not a protocol-rate test",
                frequency="method discussion; cited examples are technology-specific",
                distance="two compared line lengths",
                topology="patterned transmission-line structures",
                test_method="insertion loss and two-line-length subtraction",
                denominator="two line lengths with equivalent calibration and sample-holder mismatch",
                locators=[
                    locator("nist_a04", 63, "NIST defines insertion loss in the conductor-loss section."),
                    locator("nist_a04", 64, "NIST describes two-line subtraction and its assumptions."),
                ],
                chains=["evidence_chain:nist-tn-1520"],
                status="sufficient",
                reason="The technical note directly defines the scoped method and its matching assumption.",
                maximum="limited_metrology_method_understanding",
                independence="independent_national_metrology_source",
                freshness="stale",
                limitations=no_industry
                + ["The 2001 method discussion is not evidence that all current high-speed fixtures or production coupons use the same implementation."],
            ),
            claim(
                "CON-A04-C03",
                "PCB-ER-A04",
                "NIST states that reference-plane calibration for patterned structures can use TRL algorithms with transmission lines of varying lengths plus short and open structures.",
                scope="NIST patterned-structure reference-plane calibration discussion",
                generation="NIST Technical Note 1520, explicitly dated July 2001",
                rate="not a protocol-rate test",
                frequency="method dependent",
                distance="calibration-line lengths are method inputs",
                topology="patterned test structures",
                test_method="TRL reference-plane calibration",
                denominator="one stated TRL calibration structure set",
                locators=[locator("nist_a04", 58, "NIST describes reference-plane calibration and TRL standards.")],
                chains=["evidence_chain:nist-tn-1520"],
                status="sufficient",
                reason="The reference-plane calibration method is directly described.",
                maximum="limited_metrology_method_understanding",
                independence="independent_national_metrology_source",
                freshness="stale",
                limitations=no_industry
                + ["This does not establish a complete modern fixture-removal or IEEE 370 compliance workflow."],
            ),
            claim(
                "CON-A04-C04",
                "PCB-ER-A04",
                "The consolidated evidence does not establish how a production test coupon maps to an actual high-speed channel, nor the applicability limits of modern fixture-removal and de-embedding implementations.",
                scope="Modern production coupon and fixture-removal practice",
                generation="current practice not established",
                rate="not established",
                frequency="not harmonized",
                distance="coupon-to-channel mapping not established",
                topology="production channel and coupon relationship",
                test_method="missing modern full-text method evidence",
                denominator="modern coupon, fixture and actual-channel denominator unresolved",
                locators=[
                    locator("nist_a04", 58, "The NIST source describes calibration but not current production coupon equivalence."),
                    locator("nist_a04", 136, "NIST states that no single method covers all relevant parameters."),
                ],
                chains=["evidence_chain:nist-tn-1520"],
                status="insufficient",
                reason="A limited metrology baseline exists, but the requested modern coupon and fixture boundary remains unsupported.",
                maximum="limited_metrology_method_understanding",
                claim_type="judgment",
                stance="mixed",
                independence="independent_method_source_but_scope_gap_remains",
                evidence_strength="medium",
                confidence="low",
                freshness="stale",
                limitations=no_industry,
                missing=["Current full-text de-embedding/fixture method and auditable coupon-to-channel validation."],
            ),
            claim(
                "CON-B01-C03",
                "PCB-ER-B01",
                "NIST states that dielectric properties depend on frequency, anisotropy, temperature and other specimen conditions, and that no single measurement technique characterizes all materials across all frequencies and temperatures.",
                scope="NIST dielectric-measurement method limits",
                generation="NIST Technical Note 1520, explicitly dated July 2001",
                rate="not applicable",
                frequency="method- and band-dependent",
                distance="not applicable",
                topology="material specimens and patterned structures",
                test_method="multiple resonant, coaxial, waveguide and transmission-line methods",
                denominator="one method, specimen construction and stated environmental condition at a time",
                locators=[
                    locator("nist_b01", 22, "NIST describes property dependencies and method-specific applicability."),
                    locator("nist_b01", 136, "NIST concludes that one method is insufficient across all parameters."),
                ],
                chains=["evidence_chain:nist-tn-1520"],
                status="sufficient",
                reason="The source directly supports a scoped measurement-comparability boundary.",
                maximum="general_method_comparability_context",
                independence="independent_national_metrology_source",
                freshness="stale",
                limitations=no_industry
                + ["The source does not identify the method used for the acquired Isola table or provide a second supplier comparison."],
            ),
            claim(
                "CON-B01-C05",
                "PCB-ER-B01",
                "The consolidated evidence cannot map the acquired Isola Dk/Df declarations to a verified test method, uncertainty statement or a denominator matched to another supplier.",
                scope="Cross-source comparison of the Isola table",
                generation="Isola I-Tera table plus NIST method overview",
                rate="not applicable",
                frequency="Isola table spans 2-20 GHz; method mapping absent",
                distance="not applicable",
                topology="laminate core and prepreg constructions",
                test_method="supplier table method not identified",
                denominator="cross-supplier method, specimen and condition denominator unresolved",
                locators=[
                    locator("b01_table", 0, "The supplier table declares values but does not expose a verified method in the normalized section."),
                    locator("nist_b01", 22, "NIST explains why method and conditions constrain comparability."),
                ],
                chains=["evidence_chain:isola-i-tera-dkdf", "evidence_chain:nist-tn-1520"],
                status="insufficient",
                reason="An independent method framework exists, but it cannot be linked to the supplier declaration denominator.",
                maximum="supplier_specific_parameter_plus_method_boundary",
                claim_type="judgment",
                stance="mixed",
                independence="independent_method_context_but_no_second_supplier_parameter_chain",
                evidence_strength="medium",
                confidence="low",
                freshness="mixed",
                limitations=no_industry,
                missing=["Formal method for the Isola values, a denominator-matched second supplier, and independent modern material measurement."],
            ),
            claim(
                "CON-A02-C05",
                "PCB-ER-A02",
                "One IEEE P802.3ck contribution analyzes 107 repository channels, selects a highlighted subset below 29 dB insertion loss, and reports the subset insertion-loss distribution.",
                scope="IEEE P802.3ck May 2019 backplane COM contribution",
                generation="IEEE P802.3ck May 2019 contribution",
                rate="task-force scope states 100/200/400 Gb/s interfaces; per-lane denominator is not explicit in the cited slides",
                frequency="not explicitly harmonized in the normalized slides",
                distance="individual channel lengths are not listed in the cited slides",
                topology="contributed traditional backplane channels",
                test_method="repository channel set and COM analysis",
                denominator="107 repository channels; highlighted subset below 29 dB insertion loss",
                locators=[
                    locator("ieee_3ck", 4, "The contribution states the full channel-set size."),
                    locator("ieee_3ck", 5, "The highlighted subset lists channel insertion-loss values."),
                    locator("ieee_3ck", 6, "The contribution defines the sub-29 dB selection rule."),
                    locator("ieee_3ck", 7, "The contribution reports insertion-loss distribution statistics."),
                ],
                chains=["evidence_chain:ieee-802-3ck-backplane-com-2019"],
                status="sufficient",
                reason="The contribution directly documents this bounded channel-set analysis.",
                maximum="single_working_group_measurement_set",
                independence="independent_from_oif_but_not_independent_replication",
                evidence_strength="high",
                confidence="medium",
                limitations=no_industry
                + ["The slides do not provide a harmonized physical length, topology composition or de-embedding denominator for cross-standard comparison."],
            ),
            claim(
                "CON-A02-C06",
                "PCB-ER-A02",
                "Within that IEEE contribution, COM pass rates vary with equalizer assumptions including transmitter taps, floating-tap span, device capacitance and post-cursor settings; insertion loss alone does not determine the reported COM outcome.",
                scope="IEEE P802.3ck contribution's stated COM experiment",
                generation="IEEE P802.3ck May 2019 contribution",
                rate="task-force scope only",
                frequency="implicit in the task-force COM model, not restated as a comparison frequency",
                distance="contributed channel set; physical lengths not harmonized",
                topology="backplane channel models",
                test_method="10,292 COM runs with stated equalizer parameter variations",
                denominator="the contribution's fixed channel set and COM model configuration",
                locators=[
                    locator("ieee_3ck", 10, "The contribution states the COM run count and baseline tap assumptions."),
                    locator("ieee_3ck", 11, "The contribution identifies significant equalizer and device parameters."),
                    locator("ieee_3ck", 12, "The contribution reports pass percentages for selected cases."),
                ],
                chains=["evidence_chain:ieee-802-3ck-backplane-com-2019"],
                status="sufficient",
                reason="The experiment directly varies equalizer/model parameters and reports different outcomes.",
                maximum="single_working_group_measurement_set",
                independence="independent_from_oif_but_not_independent_replication",
                evidence_strength="high",
                confidence="medium",
                limitations=no_industry,
                alternatives=["Channel topology, package model and other COM assumptions also affect the outcome."],
            ),
            claim(
                "CON-A02-C07",
                "PCB-ER-A02",
                "Combining OIF and IEEE evidence still does not establish a general rate-distance relationship because rate, Nyquist frequency, physical reach, channel composition, reference plane and de-embedding are not harmonized across the two evidence chains.",
                scope="Cross-standard rate, reach and channel-metric comparison",
                generation="OIF 112G/448G and IEEE P802.3ck May 2019 contexts",
                rate="not harmonized",
                frequency="not harmonized",
                distance="not harmonized",
                topology="OIF interface classes versus IEEE contributed backplane channels",
                test_method="normative OIF definitions versus one IEEE COM contribution",
                denominator="cross-standard denominator unresolved",
                locators=[
                    locator("a02_cei", 622, "OIF uses its clause-specific COM and test-point denominator."),
                    locator("ieee_3ck", 4, "IEEE uses a repository channel set without a cross-standard denominator."),
                    locator("ieee_3ck", 10, "IEEE COM outcomes depend on the stated model assumptions."),
                ],
                chains=["evidence_chain:oif-cei-05.3", "evidence_chain:ieee-802-3ck-backplane-com-2019"],
                status="insufficient",
                reason="The new chain adds a bounded experiment but not the common denominator required for general comparison.",
                maximum="multi_standard_limited_metric_understanding",
                claim_type="judgment",
                stance="mixed",
                independence="two_organizations_but_non_equivalent_denominators",
                evidence_strength="medium",
                confidence="low",
                limitations=no_industry,
                missing=["A harmonized comparison with explicit rate, Nyquist frequency, reach, topology, reference plane and de-embedding."],
            ),
        ]
    )
    return sorted(retained, key=lambda row: row["claim_id"])


def build_excluded_records() -> list[dict[str, Any]]:
    baseline = _load(
        LAYOUT.analysis_dir / "ai_pcb_targeted_evidence_assessment_wave_1_v1.json"
    )
    excluded = list(deepcopy(baseline["excluded_records"]))
    wave_1b = LAYOUT.root / "acquisition/wave_1b"
    attempts = [
        json.loads(line)
        for line in (wave_1b / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    excluded.extend(
        {
            "record_id": row["attempt_id"],
            "record_type": "wave_1b_acquisition_attempt",
            "reason": f"{row['status']} Wave 1b records cannot be claim evidence.",
        }
        for row in attempts
        if row["status"] != "acquired"
    )
    checkpoint = _load(wave_1b / "acquisition_checkpoint.json")
    excluded.extend(
        {
            "record_id": attempt_id,
            "record_type": "wave_1b_preflight_attempt",
            "reason": "Preflight records have zero evidence coverage.",
        }
        for attempt_id in checkpoint.get("preflight_attempt_ids", [])
    )
    excluded.extend(
        [
            {
                "record_id": "evidence_artifact:8be4a0df1a729993d56f5088",
                "artifact_id": "evidence_artifact:8be4a0df1a729993d56f5088",
                "record_type": "landing_page_identity_mismatch",
                "reason": "The IEEE landing page is not the IEEE 370 full standard and resolved to a mismatched identity.",
            },
            {
                "record_id": "evidence_artifact:24cebdac88b8cd9fc13c162d",
                "artifact_id": "evidence_artifact:24cebdac88b8cd9fc13c162d",
                "record_type": "overview_only",
                "reason": "The PCI-SIG overview is contextual and is not channel-measurement evidence.",
            },
            {
                "record_id": "evidence_artifact:0d692e4fad8a60be4244af2c",
                "artifact_id": "evidence_artifact:0d692e4fad8a60be4244af2c",
                "record_type": "index_only",
                "reason": "The IEEE index is discovery-only and cannot be claim evidence.",
            },
            {
                "record_id": "evidence_artifact:6afe3531d76f867d0a8620aa",
                "artifact_id": "evidence_artifact:6afe3531d76f867d0a8620aa",
                "record_type": "source_shape_mismatch",
                "reason": "The NIST document is not an independent replication of the B02 copper-roughness experiment.",
            },
            {
                "record_id": "evidence_artifact:a906a111c3b689ac19c58f3a",
                "artifact_id": "evidence_artifact:a906a111c3b689ac19c58f3a",
                "record_type": "recovery_identity_mismatch",
                "reason": "The acquired USC content does not match the frozen B02 target identity.",
            },
            {
                "record_id": "normalized_document:c3ff111a56925e8c6836494f",
                "record_type": "resume_duplicate_normalized_representation",
                "reason": "Equivalent resume output does not increase locator independence or evidence-chain count.",
            },
            {
                "record_id": "normalized_document:500ae7dcaae88360df0e9c72",
                "record_type": "resume_duplicate_normalized_representation",
                "reason": "Equivalent resume output does not increase locator independence or evidence-chain count.",
            },
            {
                "record_id": "acquisition_capability_validation_only",
                "record_type": "capability_benchmark_artifacts",
                "reason": "Capability-hardening diagnostics and benchmark artifacts are not research evidence.",
            },
        ]
    )
    recovery_attempts = [
        json.loads(line)
        for line in (
            LAYOUT.root / "acquisition/wave_1b_recovery_pilot/attempts.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line
    ]
    excluded.extend(
        {
            "record_id": row["attempt_id"],
            "record_type": "recovery_acquisition_attempt",
            "reason": "Failed or manually unavailable recovery target cannot be claim evidence.",
        }
        for row in recovery_attempts
        if row["status"] != "acquired"
    )
    return excluded


def build_artifact() -> dict[str, Any]:
    authorization = _load(LAYOUT.governance_dir / AUTHORIZATION_NAME)
    claims = build_claims()
    independent_counts = {
        "PCB-ER-A04": 2,
        "PCB-ER-B01": 2,
        "PCB-ER-B02": 2,
        "PCB-ER-A02": 2,
    }
    gaps = {
        "PCB-ER-A04": ["Current full-text fixture-removal and coupon-to-channel methodology."],
        "PCB-ER-B01": ["Verified supplier test method, denominator-matched second supplier, and independent current measurement."],
        "PCB-ER-B02": ["Original publication identity/date and independent matched replication."],
        "PCB-ER-A02": ["Cross-standard rate/reach comparison with harmonized channel composition and de-embedding."],
    }
    reasons = {
        "PCB-ER-A04": "NIST adds an independent, dated metrology chain for insertion-loss and reference-plane calibration, but modern fixture-removal and coupon-to-channel applicability remain unsupported.",
        "PCB-ER-B01": "NIST establishes why method and specimen conditions constrain comparison, while the material values remain one Isola supplier chain without a verified method or matched second supplier.",
        "PCB-ER-B02": "Wave 1 still supports only one bounded roughness experiment plus supplier context; Recovery added no identity-matched B02 evidence.",
        "PCB-ER-A02": "The IEEE contribution adds an independent bounded channel/COM experiment, but rate, reach, topology, reference plane and de-embedding remain non-comparable with OIF evidence.",
    }
    next_actions = {
        "PCB-ER-A04": "manual_source_resolution_for_current_deembedding_and_coupon_method",
        "PCB-ER-B01": "manual_source_resolution_for_test_method_and_second_supplier",
        "PCB-ER-B02": "manual_publication_identity_resolution_then_stop_or_reassess",
        "PCB-ER-A02": "expert_denominator_review_before_any_additional_source_work",
    }
    er_assessments = []
    for er_id in CONSOLIDATED_AUTHORIZED_ER_IDS:
        row = compute_er_assessment(
            er_id,
            claims,
            independent_chain_count=independent_counts[er_id],
            remaining_evidence_gaps=gaps[er_id],
            recommended_next_action=next_actions[er_id],
        )
        row["overall_status_reason"] = reasons[er_id]
        er_assessments.append(row)

    bindings = authorization["input_bindings"]
    artifact = {
        "schema_version": "2.8.0",
        "artifact_type": "targeted_evidence_assessment_consolidated",
        "assessment_id": "targeted_evidence_assessment:ai_pcb:wave_1b_consolidated:v1",
        "project_id": "research_project:ai_compute_pcb_industry_bottleneck",
        "assessment_wave": "targeted_evidence_assessment_wave_1b_consolidated_v1",
        "execution_mode": "offline_read_only_consolidated_evidence_assessment",
        "renderer_version": "targeted_evidence_assessment_consolidated_markdown_v1",
        "input_bindings": {
            **bindings,
            "execution_authorization_id": authorization["authorization_id"],
            "execution_authorization_hash": authorization["content_hash"],
        },
        "authorization_consumed": True,
        "authorized_er_ids": list(CONSOLIDATED_AUTHORIZED_ER_IDS),
        "eligible_recovery_artifact_ids": [
            "evidence_artifact:5cf8a72e4f4c6a9043a474c5"
        ],
        "canonical_representation_register": [
            {
                "raw_content_hash": "50983b38c26460255f89668f3fe76eb9759b879c3ea6cce31483f468e61c97e2",
                "canonical_normalized_document_id": "normalized_document:22497cde16ab00ae7b720c87",
                "resume_duplicate_ids": ["normalized_document:c3ff111a56925e8c6836494f"],
                "eligible_for_assessment": False,
            },
            {
                "raw_content_hash": "701d2fbd43167f5f40a02e51c6ad58bef346dcc49c5fb502d5a268dc195cdad4",
                "canonical_normalized_document_id": "normalized_document:019803185d3da18b4d1f2486",
                "resume_duplicate_ids": ["normalized_document:500ae7dcaae88360df0e9c72"],
                "eligible_for_assessment": True,
            },
        ],
        "evidence_chain_register": [
            {
                "chain_id": "evidence_chain:oif-cei-05.3",
                "source_owner": "OIF",
                "artifact_ids": [SOURCES["a02_cei"][0], SOURCES["a04_cei"][0]],
                "independence_group": "oif_cei_05_3_exact_content",
            },
            {
                "chain_id": "evidence_chain:oif-cei-448g-framework",
                "source_owner": "OIF",
                "artifact_ids": [SOURCES["a02_framework"][0]],
                "independence_group": "oif_cei_448g_framework_exact_content",
            },
            {
                "chain_id": "evidence_chain:isola-i-tera-dkdf",
                "source_owner": "Isola",
                "artifact_ids": [SOURCES["b01_table"][0]],
                "independence_group": "isola_supplier_materials",
            },
            {
                "chain_id": "evidence_chain:isola-hsd-guide",
                "source_owner": "Isola",
                "artifact_ids": [SOURCES["b02_isola"][0]],
                "independence_group": "isola_hsd_supplier_guide",
            },
            {
                "chain_id": "evidence_chain:mitsui-shibaura-roughness-paper",
                "source_owner": "Mitsui/Shibaura authors; SMTnet host",
                "artifact_ids": [SOURCES["b02_paper"][0]],
                "independence_group": "mitsui_shibaura_roughness_experiment",
            },
            {
                "chain_id": "evidence_chain:nist-tn-1520",
                "source_owner": "NIST",
                "artifact_ids": [SOURCES["nist_a04"][0], SOURCES["nist_b01"][0]],
                "independence_group": "nist_tn_1520_exact_content",
            },
            {
                "chain_id": "evidence_chain:ieee-802-3ck-backplane-com-2019",
                "source_owner": "IEEE 802.3 working group contribution",
                "artifact_ids": [SOURCES["ieee_3ck"][0]],
                "independence_group": "ieee_802_3ck_backplane_com_2019",
            },
        ],
        "atomic_claims": claims,
        "er_assessments": er_assessments,
        "evidence_increment_summary": {
            "PCB-ER-A04": "NIST changes the upper bound from one OIF definition to limited metrology-method understanding.",
            "PCB-ER-B01": "NIST adds method-comparability context but not a second supplier parameter chain or method mapping.",
            "PCB-ER-B02": "No eligible Recovery evidence; the prior bounded experiment and provenance gap remain.",
            "PCB-ER-A02": "IEEE adds a bounded channel/COM experiment and an independent organization, but not a harmonized rate-distance denominator.",
        },
        "unresolved_evidence_targets": [
            {
                "target_id": "manual_target:B02_publication_identity",
                "er_id": "PCB-ER-B02",
                "classification": "manual_source_resolution_candidate",
                "priority": "P0",
                "why_unresolved": "The paper title, authors and affiliations are visible, but original venue, stable identifier and formal date remain unverified.",
                "required_human_action": "Confirm publisher or conference record, DOI or stable identifier, and explicit publication date without changing the technical evidence chain.",
                "stop_condition": "Stop after one authoritative identity record is found or authoritative records cannot confirm the publication identity.",
                "future_action_authorized": False,
            },
            {
                "target_id": "manual_target:B01_test_method_and_second_supplier",
                "er_id": "PCB-ER-B01",
                "classification": "manual_source_resolution_candidate",
                "priority": "P0",
                "why_unresolved": "The Isola declarations lack a verified method mapping and no denominator-matched second supplier is available.",
                "required_human_action": "Resolve one formal Dk/Df method or equivalent method record and one second-supplier declaration with explicit frequency, specimen and value-status fields.",
                "stop_condition": "Stop if only purchase pages, method-free datasheets or non-comparable specimen conditions are available.",
                "future_action_authorized": False,
            },
            {
                "target_id": "manual_target:A04_modern_deembedding_coupon_method",
                "er_id": "PCB-ER-A04",
                "classification": "manual_source_resolution_candidate",
                "priority": "P1",
                "why_unresolved": "NIST provides a limited calibration baseline but not a current full-text fixture-removal and coupon-to-channel method.",
                "required_human_action": "Resolve one current authoritative full-text method for de-embedding, fixture removal and coupon applicability, ideally Keysight, Anritsu or an equivalent standard source.",
                "stop_condition": "Stop if available material remains overview-only or cannot state reference plane, fixture and applicability limits.",
                "future_action_authorized": False,
            },
            {
                "target_id": "expert_target:A02_cross_standard_denominator",
                "er_id": "PCB-ER-A02",
                "classification": "expert_technical_review_candidate",
                "priority": "P1",
                "why_unresolved": "OIF and IEEE evidence use different channel sets, assumptions and metric denominators.",
                "required_human_action": "A signal-integrity reviewer should decide whether any current OIF and IEEE metrics are legitimately comparable and specify the minimum shared denominator.",
                "stop_condition": "Stop if rate, frequency, reach, topology, reference plane and equalization cannot be aligned without new primary measurements.",
                "future_action_authorized": False,
            },
            {
                "target_id": "stop_target:Panasonic_same_entry",
                "er_id": "PCB-ER-B01",
                "classification": "stop_investment_recommended",
                "priority": "P2",
                "why_unresolved": "The authorized bounded retry timed out and no new identifier or access path exists.",
                "required_human_action": "None unless a new exact official document identifier or legal stable entry is supplied externally.",
                "stop_condition": "Do not retry the same entry under the current evidence plan.",
                "future_action_authorized": False,
            },
        ],
        "consolidated_answer": {
            "understood": [
                "OIF-specific insertion-loss and COM definitions",
                "a limited NIST metrology baseline for insertion loss, two-line subtraction and TRL reference-plane calibration",
                "Isola-specific Dk/Df declarations and the conditions visible in its table",
                "one bounded copper-roughness experiment",
                "one IEEE P802.3ck channel-set and COM equalizer experiment",
            ],
            "scope_limited_understanding": [
                "A04 is limited to OIF plus an older NIST metrology baseline, not current production coupon practice",
                "B01 remains supplier-specific despite independent method context",
                "B02 remains one experiment without verified publication provenance or replication",
                "A02 is multi-organization but not a harmonized rate-distance comparison",
            ],
            "machine_public_acquisition_ceiling": [
                "B01 method mapping and second-supplier comparability",
                "B02 publication identity and independent replication",
                "A04 current fixture-removal and coupon applicability",
                "A02 cross-standard denominator reconciliation",
            ],
            "manual_evidence_candidates": [
                "B02 publication identity",
                "B01 formal method and second supplier",
                "A04 current full-text de-embedding/coupon method",
                "A02 expert denominator review",
            ],
            "stop_investment_items": [
                "Panasonic same-entry retry without a new exact identifier",
                "additional automated Recovery using the exhausted five targets",
            ],
        },
        "excluded_records": build_excluded_records(),
        "known_non_blocking_engineering_issues": [
            {
                "issue_code": "resume_normalization_not_idempotent",
                "current_bundle_modified": False,
                "assessment_effect": "canonical representations selected; duplicate outputs do not increase evidence or chain counts",
                "fix_required_before_next_formal_acquisition": True,
            }
        ],
        "governance": {
            "network_access": False,
            "new_acquisition": False,
            "recovery_acquisition": False,
            "cognition_update": False,
            "gap_review_update": False,
            "gate_update": False,
            "automatic_manual_task_authorization": False,
            "company_mapping_authorized": False,
            "stage_a2_authorized": False,
            "stage_b_authorized": False,
            "wave_2_authorized": False,
        },
        "provenance": {
            "created_by": "Codex",
            "actor_type": "codex",
            "agent_run_id": "ai-pcb-targeted-evidence-assessment-wave-1b-consolidated-v1",
            "created_at": CREATED_AT,
            "created_in_version": "research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
            "review_status": "unreviewed",
        },
        "content_hash": "",
    }
    artifact["content_hash"] = content_sha256(
        artifact, excluded_paths={("content_hash",)}
    )
    return artifact


def main() -> None:
    artifact = build_artifact()
    validate_consolidated_assessment_artifact(artifact, layout=LAYOUT)
    report = render_consolidated_assessment_report(artifact)
    validate_persisted_consolidated_assessment_report(artifact, report)
    _publish_bytes(LAYOUT.analysis_dir, ANALYSIS_NAME, canonical_bytes(artifact))
    _publish_bytes(LAYOUT.reports_dir, REPORT_NAME, report)
    print(
        json.dumps(
            {
                "assessment_id": artifact["assessment_id"],
                "assessment_hash": artifact["content_hash"],
                "report_hash": sha256(report).hexdigest(),
                "claim_count": len(artifact["atomic_claims"]),
                "unresolved_target_count": len(artifact["unresolved_evidence_targets"]),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
