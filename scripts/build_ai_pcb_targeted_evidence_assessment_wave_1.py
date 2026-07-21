from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.snapshot import _publish_bytes
from stock_research.research_project_v2_1.targeted_assessment import (
    AUTHORIZED_ER_IDS,
    compute_er_assessment,
    render_assessment_report,
    validate_assessment_artifact,
    validate_persisted_assessment_report,
)


LAYOUT = LayeredResearchLayout.default()
ANALYSIS_NAME = "ai_pcb_targeted_evidence_assessment_wave_1_v1.json"
REPORT_NAME = "ai_pcb_targeted_evidence_assessment_wave_1_v1.md"
ASSESSMENT_CREATED_AT = "2026-07-21T22:31:00Z"

SOURCES = {
    "a01_cei": ("evidence_artifact:69c8eeb0e78fa58323fc09e9", "normalized_document:8da679d8934c639b303024e3"),
    "a01_framework": ("evidence_artifact:4c00b05bf11e4dc7b47d36cb", "normalized_document:3289c4bd4757cb5b6c747709"),
    "a04_cei": ("evidence_artifact:291792bb9ba603b04bd4382f", "normalized_document:451442cedcaab779e04be686"),
    "a02_cei": ("evidence_artifact:eef74cc4d075e6b996599fc3", "normalized_document:8071e914d22caaed45914cac"),
    "a02_framework": ("evidence_artifact:3545a22276fe30d8dcb1440c", "normalized_document:1f503b4ce9f191fdd7e225ca"),
    "a03_rtlr": ("evidence_artifact:c65c0a4065ea826e834d838d", "normalized_document:4b83f07ad106253dd795aeeb"),
    "a03_framework": ("evidence_artifact:64f3622e79337c21853fa4bd", "normalized_document:91e431f42a1b1de42ec23ae9"),
    "b01_table": ("evidence_artifact:6e7d5f108e1ac7833d41b219", "normalized_document:f5daf52f0ba2e511f6f7f90c"),
    "b02_isola": ("evidence_artifact:6d6a80e65b045e0a9025c910", "normalized_document:0e3c7fd470c06f407d0d07a3"),
    "b02_paper": ("evidence_artifact:11d564e0e47f4118abc6d0c1", "normalized_document:72b1be30c0a4d52262534438"),
}


def locator(source: str, section_index: int, note: str) -> dict[str, Any]:
    artifact_id, document_id = SOURCES[source]
    wrapper = json.loads(
        (LAYOUT.evidence_normalized_dir / f"{document_id}.json").read_text(encoding="utf-8")
    )
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
        "freshness_status": "unknown",
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
    no_industry = ["The statement does not establish PCB manufacturing capability, capacity, bottleneck, value migration or company exposure."]
    return [
        claim("W1-A01-C01", "PCB-ER-A01", "OIF CEI-112G-LR-PAM4 defines a 36-58 Gsym/s PAM4 point-to-point differential interface over PCB copper traces, permits cable substitution, and specifies a reach of up to 1000 mm of backplane and two connectors.", scope="CEI-112G-LR-PAM4 Clause 27 only", generation="OIF-CEI-05.3 / CEI-112G-LR-PAM4", rate="36-58 Gsym/s PAM4", frequency="rate-defined; no cross-standard frequency comparison", distance="up to 1000 mm backplane and two connectors", topology="point-to-point balanced differential; unidirectional", test_method="normative interface and channel definition", denominator="one CEI-112G-LR-PAM4 lane/channel", locators=[locator("a01_cei", 620, "Clause 27 interface, medium and reach definition.")], chains=["evidence_chain:oif-cei-05.3"], status="sufficient", reason="The normative clause directly states the scoped interface characteristics.", maximum="standard_interface_definition", limitations=no_industry, missing=["Independent engineering interpretation outside OIF."]),
        claim("W1-A01-C02", "PCB-ER-A01", "OIF CEI-112G-XSR-PAM4 defines an extra-short-reach 36-58 Gsym/s PAM4 point-to-point electrical interface.", scope="CEI-112G-XSR-PAM4 Clause 24 only", generation="OIF-CEI-05.3 / CEI-112G-XSR-PAM4", rate="36-58 Gsym/s PAM4", frequency="not independently assessed", distance="extra-short-reach class; no physical-length generalization", topology="point-to-point electrical", test_method="normative interface definition", denominator="one CEI-112G-XSR-PAM4 interface", locators=[locator("a01_cei", 522, "Clause 24 defines XSR signaling and topology.")], chains=["evidence_chain:oif-cei-05.3"], status="sufficient", reason="The clause directly defines the scoped interface class.", maximum="standard_interface_definition", limitations=no_industry),
        claim("W1-A01-C03", "PCB-ER-A01", "The OIF 448G framework places same-PCBA chip-to-chip links through PCB trace or board cable with up to one connector in the MR application space.", scope="OIF 448G framework application taxonomy", generation="OIF-FD-CEI-448G-01.0", rate="448G framework context", frequency="not a normative compliance value", distance="same PCBA, daughter card or short mid-plane", topology="chip-to-chip through PCB trace or board cable, up to one connector", test_method="framework taxonomy, not measured compliance", denominator="one framework-defined MR application space", locators=[locator("a01_framework", 40, "Framework section 4.6 defines the MR application space.")], chains=["evidence_chain:oif-cei-448g-framework"], status="sufficient", reason="The framework directly states this taxonomy; sufficiency is limited to what the framework says.", maximum="framework_application_definition", evidence_strength="medium", limitations=no_industry),
        claim("W1-A01-C04", "PCB-ER-A01", "The OIF 448G framework describes a traditional chip-to-module VSR link as host PCB trace, connector and module PCB trace, while noting cabled-host alternatives.", scope="OIF 448G framework chip-to-module discussion", generation="OIF-FD-CEI-448G-01.0", rate="higher-rate/448G framework context", frequency="not a normative compliance value", distance="chip-to-module VSR application space", topology="host PCB or cabled host to pluggable module", test_method="framework architecture discussion", denominator="one framework-defined VSR application", locators=[locator("a01_framework", 39, "Framework section 4.5 describes traditional and cabled-host VSR links.")], chains=["evidence_chain:oif-cei-448g-framework"], status="sufficient", reason="The architecture alternatives are directly stated in the framework.", maximum="framework_application_definition", evidence_strength="medium", limitations=no_industry),

        claim("W1-A02-C01", "PCB-ER-A02", "Within CEI-112G-LR-PAM4, channel compliance is normative through COM, while the plotted insertion-loss limit is explicitly informative.", scope="CEI-112G-LR-PAM4 channel compliance only", generation="OIF-CEI-05.3 / CEI-112G-LR-PAM4", rate="36-58 Gsym/s", frequency="0.05 GHz through the clause-defined range", distance="the Clause 27 LR channel", topology="test points T-to-R", test_method="COM per IEEE 802.3 procedure as modified by the cited clause; informative IL curve", denominator="one Clause 27 T-to-R channel at its specified baud rate", locators=[locator("a02_cei", 622, "Clause 27 defines COM computation and channel test points."), locator("a02_cei", 625, "Clause 27 labels insertion loss informative rather than normative.")], chains=["evidence_chain:oif-cei-05.3"], status="sufficient", reason="The standard directly distinguishes the normative and informative metrics.", maximum="single_standard_measurement_definition", limitations=no_industry),
        claim("W1-A02-C02", "PCB-ER-A02", "OIF CEI assigns different 112G XSR, MR and LR channel classes to different physical/application reaches, so measurements must retain the named class denominator.", scope="OIF CEI 112G reach-class definitions", generation="OIF-CEI-05.3", rate="36-58 Gsym/s PAM4", frequency="class-specific", distance="XSR, MR and LR are separate scoped classes", topology="class-specific point-to-point channels", test_method="normative class definitions", denominator="one named CEI reach class; classes cannot be pooled", locators=[locator("a02_cei", 522, "XSR class definition."), locator("a02_cei", 600, "MR class definition."), locator("a02_cei", 620, "LR class definition.")], chains=["evidence_chain:oif-cei-05.3"], status="sufficient", reason="The standard provides distinct class definitions; the claim does not compare performance across classes.", maximum="standard_comparison_denominator", limitations=no_industry),
        claim("W1-A02-C03", "PCB-ER-A02", "The OIF 448G framework states that 448G-PAM4 implies 224 GBd and 112 GHz Nyquist and attributes an approximately 90 GHz channel-bandwidth limit largely to connector technology.", scope="OIF 448G framework scenario, not released IA", generation="OIF-FD-CEI-448G-01.0", rate="448 Gb/s PAM4 / 224 GBd", frequency="112 GHz Nyquist; cited ~90 GHz limit", distance="BGA-to-BGA framework example", topology="package/connector channel example", test_method="framework calculation and cited figure; independent method not supplied in Wave 1", denominator="one 448G-PAM4 framework scenario", locators=[locator("a02_framework", 30, "Framework table and narrative relate modulation order, baud and Nyquist frequency.")], chains=["evidence_chain:oif-cei-448g-framework"], status="insufficient", reason="The arithmetic and framework statement are visible, but the underlying connector dataset and independent measurement provenance are not established.", maximum="framework_hypothesis_only", claim_type="inference", evidence_strength="medium", confidence="low", limitations=no_industry, alternatives=["Higher-order modulation changes the Nyquist denominator.", "Equalization and connector architecture may alter the operational boundary."], missing=["Independent channel measurements with defined fixture, de-embedding and geometry."]),
        claim("W1-A02-C04", "PCB-ER-A02", "The framework's reported 67/85/100/106 GHz connector operational limits are not yet comparable evidence of a general rate-distance relationship.", scope="Figure 29 connector examples in OIF 448G framework", generation="OIF-FD-CEI-448G-01.0", rate="448G framework", frequency="67-106 GHz reported examples", distance="connector/interconnect examples", topology="OSFP/CPC examples", test_method="figure-level SDD21 discussion; full setup and common denominator unavailable", denominator="unresolved across connector examples", locators=[locator("a02_framework", 52, "Framework describes Figure 29 SDD21 examples."), locator("a02_framework", 53, "Framework continues connector-limit discussion.")], chains=["evidence_chain:oif-cei-448g-framework"], status="open", reason="The normalized text reports limits but does not establish a common test setup, distance, geometry or independent data origin.", maximum="contextual_boundary_only", claim_type="judgment", stance="contextual", evidence_strength="low", confidence="low", limitations=no_industry, missing=["Original measurement records and a unified denominator."]),

        claim("W1-A03-C01", "PCB-ER-A03", "OIF EEI-112G-RTLR specifies retimed/equalized egress and linear ingress for a 36-56 Gsym/s chip-to-module interface, with up to 16 dB ball-to-ball channel loss including one connector.", scope="OIF EEI-112G-RTLR only", generation="OIF-EEI-112G-RTLR-01.0", rate="36-56 Gsym/s PAM4", frequency="Nyquist-frequency loss budget in the cited agreement", distance="chip-to-module channel", topology="retimed transmitter egress, linear receiver ingress", test_method="normative implementation agreement", denominator="one EEI-112G-RTLR chip-to-module lane", locators=[locator("a03_rtlr", 3, "RTLR abstract defines architecture, rate and channel budget."), locator("a03_rtlr", 8, "Scope and requirements define egress/ingress functions and reach.")], chains=["evidence_chain:oif-rtlr-112g"], status="sufficient", reason="The agreement directly defines the scoped architecture.", maximum="single_standard_architecture_definition", limitations=no_industry),
        claim("W1-A03-C02", "PCB-ER-A03", "The RTLR agreement permits cables to replace part of the PCB copper path and specifies at least 200 mm host PCB trace, one connector and 20 mm module PCB trace in its scoped requirement.", scope="OIF EEI-112G-RTLR requirement", generation="OIF-EEI-112G-RTLR-01.0", rate="36-56 Gsym/s PAM4", frequency="agreement-specific", distance="200 mm host PCB + connector + 20 mm module PCB minimum capability", topology="host-to-module copper/cable channel", test_method="normative requirement", denominator="one RTLR host-to-module channel", locators=[locator("a03_rtlr", 8, "Requirement states PCB reach and cable substitution.")], chains=["evidence_chain:oif-rtlr-112g"], status="sufficient", reason="The requirement directly states the scoped physical path.", maximum="single_standard_architecture_definition", limitations=no_industry),
        claim("W1-A03-C03", "PCB-ER-A03", "The OIF framework identifies direct-drive CPO as a possible way to reduce electrical connector/channel reach limitations, while explicitly leaving deployment readiness uncertain.", scope="OIF 448G future-framework discussion", generation="OIF-FD-CEI-448G-01.0", rate="448G framework", frequency="framework scenario", distance="scale-up/scale-out and CPO scenario", topology="direct-drive co-packaged optics", test_method="future-framework discussion, not comparative field evidence", denominator="one stated framework option", locators=[locator("a03_framework", 31, "Framework presents CPO option and readiness caveat.")], chains=["evidence_chain:oif-cei-448g-framework"], status="sufficient", reason="The claim is limited to accurately reporting the framework's option and caveat.", maximum="framework_route_option", evidence_strength="medium", limitations=no_industry),
        claim("W1-A03-C04", "PCB-ER-A03", "Wave 1 does not establish which combination of equalization, retiming, cable, advanced modulation, FEC or optical placement is superior outside the cited OIF application spaces.", scope="Cross-route comparison beyond OIF definitions", generation="112G RTLR and 448G framework", rate="112G and 448G contexts are not pooled", frequency="route-specific", distance="route-specific", topology="multiple electrical/optical alternatives", test_method="no independent comparative experiment in Wave 1", denominator="unresolved across routes", locators=[locator("a03_framework", 39, "Framework lists VSR retiming/linear/equalization alternatives."), locator("a03_framework", 40, "Framework lists MR electrical, cable and optical alternatives."), locator("a03_framework", 42, "Framework distinguishes longer optical links and retimed/linear interfaces.")], chains=["evidence_chain:oif-cei-448g-framework"], status="open", reason="Alternatives are identified, but comparative power, BER, latency, reach and cost evidence is absent.", maximum="alternative_route_register", claim_type="judgment", stance="contextual", evidence_strength="medium", confidence="low", limitations=no_industry, missing=["Independent route-comparison measurements with matched scope and denominator."]),

        claim("W1-A04-C01", "PCB-ER-A04", "For CEI-112G-LR-PAM4, OIF defines the channel between test points T and R, computes normative COM with stated frequency/baud parameters, and labels the insertion-loss curve informative.", scope="OIF CEI-112G-LR-PAM4 only", generation="OIF-CEI-05.3 / Clause 27", rate="36-58 Gsym/s", frequency="0.05 GHz through clause-defined upper range", distance="Clause 27 LR channel", topology="T-to-R differential channel", test_method="OIF/IEEE-derived COM; informative IL curve", denominator="one Clause 27 T-to-R channel", locators=[locator("a04_cei", 622, "Clause defines test points and COM procedure."), locator("a04_cei", 625, "Clause labels insertion-loss recommendation informative.")], chains=["evidence_chain:oif-cei-05.3"], status="sufficient", reason="The standard directly defines the scoped metric hierarchy.", maximum="single_standard_definition_only", limitations=no_industry),
        claim("W1-A04-C02", "PCB-ER-A04", "Wave 1 does not contain usable independent evidence for de-embedding, fixture removal or test-coupon methodology.", scope="Independent measurement methodology beyond OIF", generation="not established", rate="not established", frequency="not established", distance="not established", topology="not established", test_method="missing", denominator="not_defined", locators=[], chains=[], status="not_assessable", reason="The NIST candidate was blocked and no other normalized independent measurement-method document is available.", maximum="single_standard_definition_only", claim_type="judgment", stance="non_evidence", evidence_strength="very_low", confidence="low", limitations=no_industry, missing=["Independent measurement methodology covering fixtures, de-embedding and coupons."]),
        claim("W1-A04-C03", "PCB-ER-A04", "OIF's single-standard definitions cannot be treated as evidence of all industry insertion-loss measurement practice.", scope="Industry-wide measurement practice", generation="not established", rate="not pooled", frequency="not pooled", distance="not pooled", topology="not pooled", test_method="only one standard family available", denominator="industry practice denominator unresolved", locators=[locator("a04_cei", 625, "OIF clause is one scoped standard definition.")], chains=["evidence_chain:oif-cei-05.3"], status="open", reason="No independent standard, metrology paper or instrument-method source is usable in Wave 1.", maximum="single_standard_definition_only", claim_type="judgment", stance="contextual", evidence_strength="low", confidence="low", limitations=no_industry, missing=["Independent standards/metrology comparison."]),

        claim("W1-B01-C01", "PCB-ER-B01", "Isola's I-Tera MT40 table declares construction-specific Dk and Df values at 2, 5, 10, 15 and 20 GHz together with resin content and thickness.", scope="I-Tera MT40 supplier table only", generation="I-Tera MT40 Revision L", rate="not specified", frequency="2/5/10/15/20 GHz", distance="not applicable", topology="core and prepreg material constructions", test_method="not stated in the normalized table", denominator="one listed I-Tera construction/resin-content/thickness row", locators=[locator("b01_table", 0, "Core table lists Dk/Df, frequencies, resin content and thickness."), locator("b01_table", 2, "Prepreg table lists the same scoped fields.")], chains=["evidence_chain:isola-i-tera-dkdf"], status="sufficient", reason="The table directly supports only the supplier-declared row values.", maximum="supplier_specific_parameter_and_method_understanding", independence="single_supplier_chain", evidence_strength="medium", limitations=no_industry, missing=["Test method, direction, environment and independent validation."]),
        claim("W1-B01-C02", "PCB-ER-B01", "Within the I-Tera table, declared Dk/Df values are indexed by glass construction, resin content and thickness, so row-level construction is part of the comparison denominator.", scope="I-Tera MT40 table structure", generation="I-Tera MT40 Revision L", rate="not specified", frequency="2-20 GHz columns", distance="not applicable", topology="material constructions", test_method="supplier table organization", denominator="same frequency and one specified construction/resin/thickness row", locators=[locator("b01_table", 0, "Core rows show construction and resin-content dependence."), locator("b01_table", 2, "Prepreg rows show construction and resin-content dependence.")], chains=["evidence_chain:isola-i-tera-dkdf"], status="sufficient", reason="The table structure directly establishes the required row denominator; it does not establish causality.", maximum="supplier_specific_parameter_and_method_understanding", independence="single_supplier_chain", evidence_strength="medium", limitations=no_industry),
        claim("W1-B01-C03", "PCB-ER-B01", "Wave 1 cannot determine the Dk/Df test method, directionality, humidity/temperature conditions or whether table values are nominal, typical or guaranteed.", scope="I-Tera measurement-method interpretation", generation="I-Tera MT40 Revision L", rate="not applicable", frequency="2-20 GHz", distance="not applicable", topology="material specimens", test_method="not stated in usable normalized evidence", denominator="not_defined", locators=[], chains=[], status="not_assessable", reason="The normalized table contains values and revision history but not the required method metadata; the additional Isola paper failed normalization.", maximum="supplier_specific_parameter_and_method_understanding", claim_type="judgment", stance="non_evidence", evidence_strength="very_low", confidence="low", limitations=no_industry, missing=["Usable method document and independent test record."]),
        claim("W1-B01-C04", "PCB-ER-B01", "The acquired B01 evidence cannot support cross-supplier Dk/Df comparability or whole-channel performance.", scope="Cross-supplier and board-level inference", generation="not established", rate="not established", frequency="not harmonized", distance="not applicable", topology="not applicable", test_method="only one usable supplier chain", denominator="cross-supplier denominator unresolved", locators=[locator("b01_table", 0, "The usable evidence is an Isola-specific table.")], chains=["evidence_chain:isola-i-tera-dkdf"], status="insufficient", reason="Rogers acquisition failed, the second Isola PDF is encrypted, and no independent test source is usable.", maximum="supplier_specific_parameter_and_method_understanding", claim_type="judgment", stance="contextual", independence="single_supplier_chain", evidence_strength="low", confidence="low", limitations=no_industry, missing=["Second supplier with harmonized method and independent material testing."]),

        claim("W1-B02-C01", "PCB-ER-B02", "Isola's high-speed design guide states that rough copper increases resistance and that its electrical impact grows with data rate.", scope="Isola supplier guide statement", generation="supplier HSD guide", rate="qualitative higher-data-rate context", frequency="not tied to a complete test method", distance="not specified", topology="PCB conductor surfaces", test_method="supplier presentation; method not shown for the quoted percentage", denominator="supplier-stated rough versus smoother conductor context", locators=[locator("b02_isola", 15, "Guide states resistance and data-rate effects of roughness."), locator("b02_isola", 16, "Guide illustrates longer current path around surface profile.")], chains=["evidence_chain:isola-hsd-guide"], status="sufficient", reason="Sufficient only as a record of the supplier's scoped technical statement, not as independent quantitative proof.", maximum="supplier_specific_roughness_context", independence="supplier_primary_only", evidence_strength="medium", confidence="low", limitations=no_industry, missing=["Independent measurement matching the stated percentage."]),
        claim("W1-B02-C02", "PCB-ER-B02", "The Isola guide distinguishes RTF, LP and VLP foil profiles and reports example Rq values for RTF and VLP.", scope="Isola guide foil taxonomy", generation="supplier HSD guide", rate="not specified", frequency="not specified", distance="not applicable", topology="copper foil surfaces", test_method="supplier presentation", denominator="the guide's named foil-profile examples", locators=[locator("b02_isola", 17, "Guide defines foil-profile categories and example Rq values.")], chains=["evidence_chain:isola-hsd-guide"], status="sufficient", reason="The foil taxonomy and example values are directly stated.", maximum="supplier_specific_roughness_context", independence="supplier_primary_only", evidence_strength="medium", limitations=no_industry),
        claim("W1-B02-C03", "PCB-ER-B02", "The Mitsui/Shibaura paper describes four-layer evaluation boards with microstrip/stripline and differential/single-ended structures, three dielectrics, 100/200/300 mm lengths, and VNA S21/Sdd21 measurement from 300 kHz to 20 GHz.", scope="The cited evaluation-board experiment only", generation="paper's experimental setup", rate="not a protocol-rate test", frequency="300 kHz-20 GHz", distance="100/200/300 mm; cited comparison at 200 mm", topology="microstrip and stripline; single-ended and differential", test_method="Agilent E5071C VNA S21/Sdd21 measurement", denominator="one stated geometry, dielectric, length and frequency", locators=[locator("b02_paper", 2, "Paper defines board stack, line types, impedances, materials and lengths."), locator("b02_paper", 3, "Paper defines VNA, frequency range and S-parameter measurements.")], chains=["evidence_chain:mitsui-shibaura-roughness-paper"], status="sufficient", reason="The normalized paper text directly specifies the experimental denominator.", maximum="single_experiment_engineering_understanding", independence="vendor_academic_joint_source", evidence_strength="high", limitations=no_industry),
        claim("W1-B02-C04", "PCB-ER-B02", "In the paper's 200 mm G1 stripline experiment at 20 GHz, lower bonding-side Rz was associated with lower measured signal loss; NP-VSP was reported at about 17% lower total loss than RTF.", scope="One paper's G1 200 mm stripline comparison", generation="paper's copper-foil experiment", rate="not a protocol-rate test", frequency="20 GHz", distance="200 mm", topology="stripline in dielectric G1", test_method="Rz/Rq by two non-contact profilometers and VNA loss measurement", denominator="same G1 dielectric, 200 mm stripline and 20 GHz comparison", locators=[locator("b02_paper", 8, "Paper defines Rz/Rq instruments and foil measurements."), locator("b02_paper", 13, "Paper reports Rz versus 20 GHz loss for 200 mm G1 stripline."), locator("b02_paper", 14, "Paper summarizes the scoped loss result.")], chains=["evidence_chain:mitsui-shibaura-roughness-paper"], status="sufficient", reason="The experiment states geometry, material, frequency, roughness metric and measured relationship.", maximum="single_experiment_engineering_understanding", independence="vendor_academic_joint_source", evidence_strength="high", limitations=no_industry, alternatives=["Dielectric and conductor-loss separation depends on the paper's regression model.", "Foil treatment and adhesion changes may covary with measured roughness."]),
        claim("W1-B02-C05", "PCB-ER-B02", "The roughness paper's authors and affiliations are identifiable, but Wave 1 does not verify its original publication venue or publication date from normalized content.", scope="Source provenance for the roughness paper", generation="unknown publication version", rate="not applicable", frequency="not applicable", distance="not applicable", topology="not applicable", test_method="repository copy; original venue absent from normalized text", denominator="one document copy", locators=[locator("b02_paper", 0, "Title page identifies authors and affiliations but not a publication venue/date.")], chains=["evidence_chain:mitsui-shibaura-roughness-paper"], status="open", reason="The SMTnet-hosted PDF exposes authorship and institutions but not a confirmed original venue/date.", maximum="source_provenance_partially_verified", claim_type="judgment", stance="contextual", independence="vendor_academic_joint_source", evidence_strength="medium", confidence="low", limitations=no_industry, missing=["Original publisher/venue record and publication date."]),
        claim("W1-B02-C06", "PCB-ER-B02", "Wave 1 does not establish that the paper's roughness-loss result generalizes across suppliers, modern high-speed geometries, frequencies or production boards.", scope="Industry-wide generalization", generation="not established", rate="not established", frequency="beyond 20 GHz not established", distance="beyond cited lengths not established", topology="beyond cited structures not established", test_method="one supplier guide and one vendor-academic experiment", denominator="industry denominator unresolved", locators=[locator("b02_paper", 13, "The measured relationship is explicitly tied to one experiment."), locator("b02_isola", 32, "Supplier guide stresses equal test conditions for comparisons.")], chains=["evidence_chain:mitsui-shibaura-roughness-paper", "evidence_chain:isola-hsd-guide"], status="insufficient", reason="The two chains are distinct but neither provides independent replication across a harmonized production denominator.", maximum="bounded_experimental_relationship", claim_type="judgment", stance="mixed", independence="partially_independent_but_not_replication", evidence_strength="medium", confidence="low", limitations=no_industry, missing=["Independent replication with matched geometry, material, roughness metric and frequency."]),
    ]


def build_excluded_records() -> list[dict[str, Any]]:
    wave = LAYOUT.root / "acquisition/wave_1"
    attempts = [json.loads(line) for line in (wave / "attempts.jsonl").read_text().splitlines() if line]
    checkpoint = json.loads((wave / "acquisition_checkpoint.json").read_text())
    inventory = json.loads((wave / "evidence_inventory.json").read_text())["items"]
    excluded = [
        {"record_id": attempt["attempt_id"], "record_type": "acquisition_attempt", "reason": f"{attempt['status']} records cannot be claim evidence."}
        for attempt in attempts if attempt["status"] != "acquired"
    ]
    excluded.extend(
        {"record_id": attempt_id, "record_type": "engineering_preflight_attempt", "reason": "Engineering preflight attempt has zero evidence coverage."}
        for attempt_id in checkpoint["engineering_preflight_attempt_ids"]
    )
    excluded.extend(
        {"record_id": item["artifact_id"], "artifact_id": item["artifact_id"], "record_type": "normalization_failed_artifact", "reason": "Encrypted or normalization-failed raw artifact has no usable normalized-text locator."}
        for item in inventory if item["normalization_status"] != "normalized"
    )
    return excluded


def build_artifact() -> dict[str, Any]:
    claims = build_claims()
    gap_map = {
        "PCB-ER-A01": ["Independent engineering interpretation outside OIF."],
        "PCB-ER-A02": ["Independent rate/reach measurements with a common denominator and disclosed de-embedding."],
        "PCB-ER-A03": ["Independent comparison of equalization, retiming, cable and optical alternatives."],
        "PCB-ER-A04": ["Independent de-embedding, fixture and test-coupon methodology."],
        "PCB-ER-B01": ["Usable test-method metadata, second supplier and independent material test."],
        "PCB-ER-B02": ["Original venue/date and independent replication under matched experimental conditions."],
    }
    independent_counts = {
        "PCB-ER-A01": 1, "PCB-ER-A02": 1, "PCB-ER-A03": 1,
        "PCB-ER-A04": 1, "PCB-ER-B01": 1, "PCB-ER-B02": 2,
    }
    ers = []
    for er_id in AUTHORIZED_ER_IDS:
        row = compute_er_assessment(
            er_id, claims,
            independent_chain_count=independent_counts[er_id],
            remaining_evidence_gaps=gap_map[er_id],
            recommended_next_action="human_review_for_possible_wave_1b_design",
        )
        row["overall_status_reason"] = {
            "PCB-ER-A01": "Scoped OIF definitions are clear, but all evidence comes from one standards organization and lacks independent engineering interpretation.",
            "PCB-ER-A02": "Normative 112G definitions are usable, while 448G rate/frequency comparisons lack independent measurements and a unified denominator.",
            "PCB-ER-A03": "OIF defines RTLR and identifies alternatives, but no independent comparative evidence ranks the alternatives.",
            "PCB-ER-A04": "Only a single OIF standard definition is usable; independent de-embedding and coupon methodology is absent.",
            "PCB-ER-B01": "Only one usable Isola supplier chain exists, with no stated test method or cross-supplier denominator.",
            "PCB-ER-B02": "One supplier guide and one vendor-academic experiment support bounded statements, but provenance and independent replication remain incomplete.",
        }[er_id]
        ers.append(row)
    artifact = {
        "schema_version": "2.7.0",
        "artifact_type": "targeted_evidence_assessment",
        "assessment_id": "targeted_evidence_assessment:ai_pcb:wave_1:v1",
        "project_id": "research_project:ai_compute_pcb_industry_bottleneck",
        "assessment_wave": "targeted_evidence_assessment_wave_1_v1",
        "execution_mode": "offline_read_only_evidence_assessment",
        "renderer_version": "targeted_evidence_assessment_markdown_v1",
        "input_bindings": {
            "checkpoint_id": "targeted_acquisition_checkpoint:b53ab0a0143b89f9914842f5",
            "checkpoint_hash": "b53ab0a0143b89f9914842f5848ed606b86de3dc1a4a7f5f08a05c6afcf81013",
            "gate_hash": "38f48163bfdc825b6f3afc12e95a9cc99c59c0fccc809fbe4e86460405d509ea",
        },
        "authorized_er_ids": list(AUTHORIZED_ER_IDS),
        "evidence_chain_register": [
            {"chain_id": "evidence_chain:oif-cei-05.3", "source_owner": "OIF", "artifact_ids": [SOURCES["a01_cei"][0], SOURCES["a04_cei"][0], SOURCES["a02_cei"][0]], "independence_group": "oif_cei_05_3_exact_content"},
            {"chain_id": "evidence_chain:oif-cei-448g-framework", "source_owner": "OIF", "artifact_ids": [SOURCES["a01_framework"][0], SOURCES["a02_framework"][0], SOURCES["a03_framework"][0]], "independence_group": "oif_cei_448g_framework_exact_content"},
            {"chain_id": "evidence_chain:oif-rtlr-112g", "source_owner": "OIF", "artifact_ids": [SOURCES["a03_rtlr"][0]], "independence_group": "oif_rtlr_112g"},
            {"chain_id": "evidence_chain:isola-i-tera-dkdf", "source_owner": "Isola", "artifact_ids": [SOURCES["b01_table"][0]], "independence_group": "isola_supplier_materials"},
            {"chain_id": "evidence_chain:isola-hsd-guide", "source_owner": "Isola", "artifact_ids": [SOURCES["b02_isola"][0]], "independence_group": "isola_hsd_supplier_guide"},
            {"chain_id": "evidence_chain:mitsui-shibaura-roughness-paper", "source_owner": "Mitsui/Shibaura authors; SMTnet host", "artifact_ids": [SOURCES["b02_paper"][0]], "independence_group": "mitsui_shibaura_roughness_experiment"},
        ],
        "atomic_claims": claims,
        "er_assessments": ers,
        "excluded_records": build_excluded_records(),
        "governance": {
            "network_access": False, "new_acquisition": False,
            "cognition_update": False, "gap_review_update": False, "gate_update": False,
            "company_mapping_authorized": False, "stage_a2_authorized": False,
            "stage_b_authorized": False, "wave_1b_authorized": False,
        },
        "provenance": {
            "created_by": "Codex", "actor_type": "codex",
            "agent_run_id": "ai-pcb-targeted-evidence-assessment-wave-1-v1",
            "created_at": ASSESSMENT_CREATED_AT,
            "created_in_version": "research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
            "review_status": "unreviewed",
        },
        "content_hash": "",
    }
    artifact["content_hash"] = content_sha256(artifact, excluded_paths=(("content_hash",),))
    return artifact


def main() -> None:
    artifact = build_artifact()
    validate_assessment_artifact(artifact, layout=LAYOUT)
    report = render_assessment_report(artifact)
    validate_persisted_assessment_report(artifact, report)
    _publish_bytes(LAYOUT.analysis_dir, ANALYSIS_NAME, canonical_bytes(artifact))
    _publish_bytes(LAYOUT.reports_dir, REPORT_NAME, report)
    print(json.dumps({
        "assessment_id": artifact["assessment_id"],
        "assessment_hash": artifact["content_hash"],
        "report_hash": sha256(report).hexdigest(),
        "claim_count": len(artifact["atomic_claims"]),
    }))


if __name__ == "__main__":
    main()
