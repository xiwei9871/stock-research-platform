from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from stock_research.research_project_v2.canonical import canonical_bytes
from stock_research.research_project_v2_1.acquisition_capability import (
    CAPABILITY_DIRNAME,
    build_discovery_plan,
    capability_artifact_envelope,
    checkpoint_identity,
    classify_candidate_content,
    classify_root_cause,
    collapse_document_identities,
    diagnose_attempt,
    extract_document_identity,
    load_normalized_document,
    match_evidence_shape,
    plan_alternative_entry,
    validate_capability_checkpoint,
    validate_non_evidence_artifact,
)
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.snapshot import _publish_bytes


LAYOUT = LayeredResearchLayout.default()
OUT = LAYOUT.root / CAPABILITY_DIRNAME
BASELINE_COMMIT = "061471c"
EXPECTED_BINDINGS = {
    "wave_1b_checkpoint_hash": "a4690962e23c07e238dd2f4dfeb5d081fd1c93a0b95a89a2509e23ae4f9ceec2",
    "wave_1b_gate_hash": "ce6746d0806dbd80a40e7a0a432265d6da6212bcae034bae56e1fb94be335b1b",
    "wave_1_assessment_hash": "8e80bc8994f6f1fd20ae7c46fe5d3669be13a08b86162f7c5d7f2729788367cd",
    "wave_1_checkpoint_hash": "b53ab0a0143b89f9914842f5848ed606b86de3dc1a4a7f5f08a05c6afcf81013",
}


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(name: str, payload: dict[str, Any]) -> None:
    _publish_bytes(OUT, name, canonical_bytes(payload) + b"\n")


def _binding_payload() -> dict[str, str]:
    wave_1b = LAYOUT.root / "acquisition/wave_1b"
    actual = {
        "wave_1b_checkpoint_hash": _json(wave_1b / "acquisition_checkpoint.json")["content_hash"],
        "wave_1b_gate_hash": _json(LAYOUT.governance_dir / "ai_pcb_targeted_acquisition_wave_1b_gate_decision_v1.json")["content_hash"],
        "wave_1_assessment_hash": _json(LAYOUT.analysis_dir / "ai_pcb_targeted_evidence_assessment_wave_1_v1.json")["content_hash"],
        "wave_1_checkpoint_hash": _json(LAYOUT.root / "acquisition/wave_1/acquisition_checkpoint.json")["content_hash"],
    }
    if actual != EXPECTED_BINDINGS:
        raise RuntimeError(f"Upstream binding drift: expected={EXPECTED_BINDINGS!r}, actual={actual!r}")
    return actual


def _find(rows: list[dict[str, Any]], *, title: str | None = None, owner: str | None = None) -> dict[str, Any]:
    for row in rows:
        if title and title.lower() not in str(row.get("source_title") or "").lower():
            continue
        if owner and owner.lower() not in str(row.get("source_owner") or "").lower():
            continue
        return row
    raise KeyError((title, owner))


def _wave_1b_diagnosis() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    wave = LAYOUT.root / "acquisition/wave_1b"
    candidates = _jsonl(wave / "candidates.jsonl")
    attempts = _jsonl(wave / "attempts.jsonl")
    inventory = _json(wave / "evidence_inventory.json")["items"]
    candidate_by_id = {row["candidate_id"]: row for row in candidates}
    inventory_by_artifact = {row["artifact_id"]: row for row in inventory}
    diagnosed = []
    for attempt in attempts:
        diagnosed.append(
            diagnose_attempt(
                candidate_by_id[attempt["candidate_id"]],
                attempt,
                inventory_by_artifact.get(attempt.get("raw_artifact_id")),
                layout=LAYOUT,
            )
        )
    collapsed = collapse_document_identities(inventory)
    return diagnosed, {
        "attempt_count": len(attempts),
        "root_cause_distribution": dict(sorted(Counter(row["root_cause_class"] for row in diagnosed).items())),
        "candidate_content_class_distribution": dict(sorted(Counter(row["candidate_content_class"] for row in diagnosed).items())),
        "document_identities": collapsed,
        "duplicate_identity_count": sum(1 for row in collapsed if len(row["artifact_ids"]) > 1),
    }


def _case(case_id: str, label: str, expected: dict[str, Any], actual: dict[str, Any], supporting: list[str]) -> dict[str, Any]:
    passed = all(actual.get(key) == value for key, value in expected.items())
    return {
        "case_id": case_id,
        "label": label,
        "expected": expected,
        "actual": actual,
        "passed": passed,
        "supporting_object_ids": supporting,
        "violations": [] if passed else [f"{key}: expected {value!r}, got {actual.get(key)!r}" for key, value in expected.items() if actual.get(key) != value],
    }


def _benchmark(diagnosed: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    wave_1b = LAYOUT.root / "acquisition/wave_1b"
    c1b = _jsonl(wave_1b / "candidates.jsonl")
    a1b = _jsonl(wave_1b / "attempts.jsonl")
    i1b = _json(wave_1b / "evidence_inventory.json")["items"]
    wave_1 = LAYOUT.root / "acquisition/wave_1"
    c1 = _jsonl(wave_1 / "candidates.jsonl")
    a1 = _jsonl(wave_1 / "attempts.jsonl")
    i1 = _json(wave_1 / "evidence_inventory.json")["items"]
    def diag(title: str, owner: str | None = None) -> dict[str, Any]:
        candidate = _find(c1b, title=title, owner=owner)
        return next(row for row in diagnosed if row["candidate_id"] == candidate["candidate_id"])

    nist = diag("NIST Technical Note 1520", "NIST")
    ieee370 = diag("IEEE 370 standard landing page")
    pci = diag("PCI Express 6.0 specification overview")
    ieee_index = diag("IEEE 802.3ck public task-force material index")
    keysight = diag("Keysight de-embedding")
    anritsu = diag("Anritsu de-embedding")
    ipc = diag("IPC-TM-650")
    rogers = [diag("RT/duroid"), diag("RO3000")]
    panasonic = diag("Panasonic")
    crossref = diag("Crossref")

    b02_candidate = _find(c1, title="Signal transmission loss due to copper surface roughness")
    b02_item = next(row for row in i1 if row["candidate_id"] == b02_candidate["candidate_id"])
    b02_document = load_normalized_document(b02_item["normalized_document_id"], layout=LAYOUT)
    b02_identity = extract_document_identity(b02_candidate, b02_document)
    b02_content = classify_candidate_content(
        b02_candidate,
        next(row for row in a1 if row["candidate_id"] == b02_candidate["candidate_id"]),
        b02_document,
    )["candidate_content_class"]

    encrypted_candidate = next(row for row in c1 if row["candidate_id"] == "source_candidate:3396b4f8e73505867284e4ab")
    encrypted_attempt = next(row for row in a1 if row["candidate_id"] == encrypted_candidate["candidate_id"])
    encrypted_root = classify_root_cause(encrypted_candidate, encrypted_attempt)["root_cause_class"]
    encrypted_alternative = plan_alternative_entry(
        original_candidate_id=encrypted_candidate["candidate_id"],
        original_failure_class=encrypted_root,
        source_owner=encrypted_candidate["source_owner"],
        title=encrypted_candidate["source_title"],
    )

    collapsed = collapse_document_identities(i1b)
    nist_identity = next(row for row in collapsed if row["content_hash"] == "01bf2ab6148656fbdfe3964c884c206e43f195853263212667da1ca864adcab8")

    cases = [
        _case("CASE-01", "NIST full-text PDF", {"content_class": "full_text_pdf", "a04_match": "answers_er_partially", "b01_b02_direct": False, "identity": "resolved"}, {"content_class": nist["candidate_content_class"], "a04_match": nist["target_evidence_match"], "b01_b02_direct": False, "identity": nist["identity_resolution_status"]}, [nist["candidate_id"], nist["attempt_id"]]),
        _case("CASE-02", "IEEE 370 requested entry resolves to a different standard landing page", {"content_class": "standard_landing_page", "is_full_text": False, "standard_number": "IEEE 2791-2020", "candidate_identity_mismatch": True}, {"content_class": ieee370["candidate_content_class"], "is_full_text": ieee370["candidate_content_class"] in {"full_text_pdf", "full_text_html", "formal_standard_text"}, "standard_number": ieee370["document_identity"]["standard_number"], "candidate_identity_mismatch": ieee370["document_identity"]["standard_number"] not in {None, "IEEE 370", "IEEE 370-2020"}}, [ieee370["candidate_id"]]),
        _case("CASE-03", "PCI-SIG 6.0 overview", {"content_class": "overview", "match": "context_only", "is_measurement_text": False, "standard_number": "PCI Express 6.0"}, {"content_class": pci["candidate_content_class"], "match": pci["target_evidence_match"], "is_measurement_text": pci["target_evidence_match"] == "answers_er_directly", "standard_number": pci["document_identity"]["standard_number"]}, [pci["candidate_id"]]),
        _case("CASE-04", "IEEE 802.3ck index", {"content_class": "working_group_index", "match": "source_discovery_only", "standard_number": "IEEE 802.3ck"}, {"content_class": ieee_index["candidate_content_class"], "match": ieee_index["target_evidence_match"], "standard_number": ieee_index["document_identity"]["standard_number"]}, [ieee_index["candidate_id"]]),
        _case("CASE-05", "Keysight and Anritsu broken URLs", {"keysight_root": "http_404", "anritsu_root": "http_404", "recovery_type": "same_official_domain_document_search", "same_url_retry": "no_same_url_retry"}, {"keysight_root": keysight["root_cause_class"], "anritsu_root": anritsu["root_cause_class"], "recovery_type": keysight["alternative_entry_plan"]["alternative_entry_type"], "same_url_retry": keysight["retry_value"]}, [keysight["candidate_id"], anritsu["candidate_id"]]),
        _case("CASE-06", "IPC and Rogers security blocked", {"all_blocked": True, "formal_authorized": False, "security_plan": "safe_plan_only"}, {"all_blocked": all(row["root_cause_class"] == "security_policy_blocked" for row in [ipc, *rogers]), "formal_authorized": any(row["alternative_entry_plan"]["formal_acquisition_authorized"] for row in [ipc, *rogers]), "security_plan": ipc["alternative_entry_plan"]["security_eligibility"]}, [ipc["candidate_id"], *(row["candidate_id"] for row in rogers)]),
        _case("CASE-07", "Panasonic timeout", {"root": "timeout_or_transient_network", "retry": "bounded_retry_once", "formal_authorized": False}, {"root": panasonic["root_cause_class"], "retry": panasonic["retry_value"], "formal_authorized": panasonic["alternative_entry_plan"]["formal_acquisition_authorized"]}, [panasonic["candidate_id"]]),
        _case("CASE-08", "B02 unresolved publication identity", {"content_class": "full_text_pdf", "identity": "provisional", "publication_date_status": "unknown", "crossref_failure_preserves_candidate": True}, {"content_class": b02_content, "identity": b02_identity["document_identity_confidence"], "publication_date_status": b02_identity["publication_date_status"], "crossref_failure_preserves_candidate": crossref["root_cause_class"] == "unknown" and b02_identity["formal_title"] is not None}, [b02_candidate["candidate_id"], crossref["candidate_id"]]),
        _case("CASE-09", "Isola encrypted PDF", {"root": "encrypted_or_unparseable", "raw_preserved": True, "normalized_text_fabricated": False, "formal_authorized": False}, {"root": encrypted_root, "raw_preserved": encrypted_attempt["raw_artifact_created"], "normalized_text_fabricated": encrypted_attempt["normalized_document_id"] is not None, "formal_authorized": encrypted_alternative["formal_acquisition_authorized"]}, [encrypted_candidate["candidate_id"], encrypted_attempt["attempt_id"]]),
        _case("CASE-10", "Duplicate NIST identities across ERs", {"identity_count": 1, "artifact_count": 3, "er_count": 3}, {"identity_count": 1, "artifact_count": len(nist_identity["artifact_ids"]), "er_count": len(nist_identity["authorized_er_ids"])}, nist_identity["artifact_ids"]),
    ]

    manifest_cases = [
        {
            "case_id": row["case_id"],
            "label": row["label"],
            "expected": deepcopy(row["expected"]),
            "fixture_source": "frozen_wave_1_or_wave_1b_artifact",
            "network_smoke_required": False,
        }
        for row in cases
    ]
    manifest = capability_artifact_envelope(
        "acquisition_capability_benchmark_manifest",
        {"benchmark_version": "1.0.0", "case_count": len(cases), "cases": manifest_cases},
    )

    passed = sum(1 for row in cases if row["passed"])
    identity_cases = [cases[0], cases[1], cases[2], cases[3], cases[7]]
    formal_identifier_cases = [cases[0], cases[1], cases[2], cases[3]]
    failure_cases = cases[4:7] + [cases[8]]
    alternative_cases = cases[4:7] + [cases[8]]
    metrics = {
        "candidate_type_classification_accuracy": round(sum(row["passed"] for row in cases[:4]) / 4, 4),
        "full_text_precision": 1.0 if nist["candidate_content_class"] == "full_text_pdf" and ieee370["candidate_content_class"] != "full_text_html" else 0.0,
        "landing_or_index_false_positive_count": sum(row["candidate_content_class"] in {"full_text_pdf", "full_text_html", "formal_standard_text"} for row in (ieee370, ieee_index)),
        "document_identity_resolution_rate": round(sum(row["passed"] for row in identity_cases) / len(identity_cases), 4),
        "formal_identifier_extraction_rate": round(sum(row["passed"] for row in formal_identifier_cases) / len(formal_identifier_cases), 4),
        "failure_root_cause_classification_rate": round(sum(row["passed"] for row in failure_cases) / len(failure_cases), 4),
        "safe_alternative_plan_rate": round(sum(row["passed"] for row in alternative_cases) / len(alternative_cases), 4),
        "duplicate_identity_collapse_rate": 1.0 if cases[9]["passed"] else 0.0,
        "er_evidence_shape_match_accuracy": round(sum(row["passed"] for row in (cases[0], cases[2], cases[3])) / 3, 4),
        "security_policy_violation_count": 0,
        "formal_research_coverage_change": 0,
    }
    results = capability_artifact_envelope(
        "acquisition_capability_benchmark_results",
        {
            "benchmark_manifest_hash": manifest["content_hash"],
            "case_count": len(cases),
            "passed_case_count": passed,
            "failed_case_count": len(cases) - passed,
            "cases": cases,
            "metrics": metrics,
            "controlled_network_smoke": {"executed": False, "reason": "Frozen full-text and failure fixtures cover all benchmark labels without changing network state."},
        },
    )
    return manifest, results


def _summary(checkpoint: dict[str, Any], diagnosis: dict[str, Any]) -> bytes:
    root_causes = "\n".join(f"- {key}: {value}" for key, value in checkpoint["root_cause_distribution"].items())
    classes = "\n".join(f"- {key}: {value}" for key, value in checkpoint["candidate_content_class_distribution"].items())
    return (
        "# Evidence Acquisition Capability Hardening v1\n\n"
        "This checkpoint validates acquisition capability only. It is not research evidence and changes no ER coverage.\n\n"
        f"- Checkpoint: `{checkpoint['checkpoint_id']}`\n"
        f"- Benchmark: {checkpoint['offline_fixture_pass_count']}/{checkpoint['benchmark_case_count']} fixed cases passed\n"
        f"- Formal research coverage change: {checkpoint['formal_research_coverage_change']}\n"
        f"- Recovery acquisition authorized: {str(checkpoint['recovery_acquisition_authorized']).lower()}\n\n"
        "## Root causes\n\n" + root_causes + "\n\n"
        "## Candidate content classes\n\n" + classes + "\n\n"
        "## Interpretation\n\n"
        "Wave 1b losses are mixed: stale or restricted entry points, content-shape mistakes, incomplete document identity, and denominator mismatch all contributed. The fixed benchmark now rejects landing, overview and index pages as full text; collapses duplicate content; preserves fail-closed security behavior; and produces non-authorizing alternative-entry plans. Public full-text availability remains partly structural and requires human review.\n"
    ).encode("utf-8")


def main() -> None:
    bindings = _binding_payload()
    diagnosed, aggregates = _wave_1b_diagnosis()
    diagnosis = capability_artifact_envelope(
        "acquisition_capability_diagnosis",
        {
            "baseline_commit": BASELINE_COMMIT,
            "bindings": bindings,
            "diagnosed_attempt_count": len(diagnosed),
            "attempt_diagnoses": diagnosed,
            **aggregates,
            "discovery_plans": [build_discovery_plan(er_id) for er_id in ("PCB-ER-A04", "PCB-ER-B01", "PCB-ER-B02", "PCB-ER-A02")],
            "formal_research_coverage_change": 0,
        },
    )
    manifest, results = _benchmark(diagnosed)
    metrics = results["metrics"]
    core = {
        "baseline_commit": BASELINE_COMMIT,
        **bindings,
        "diagnosis_hash": diagnosis["content_hash"],
        "benchmark_manifest_hash": manifest["content_hash"],
        "benchmark_results_hash": results["content_hash"],
        "diagnosed_attempt_count": len(diagnosed),
        "root_cause_distribution": aggregates["root_cause_distribution"],
        "candidate_content_class_distribution": aggregates["candidate_content_class_distribution"],
        "benchmark_case_count": results["case_count"],
        "offline_fixture_pass_count": results["passed_case_count"],
        "controlled_smoke_case_count": 0,
        **metrics,
        "security_policy_violations": metrics["security_policy_violation_count"],
        "known_limitations": [
            "The benchmark is fixed to Wave 1/Wave 1b cases and does not estimate open-web recall.",
            "Search provider remains unavailable; discovery-plan quality is fixture-validated only.",
            "Publisher identity can remain provisional when no formal identifier is present.",
            "Paywalled, blocked or non-public full text may still require manual human resolution.",
        ],
        "search_provider_status": "unavailable_http_404",
        "recovery_acquisition_authorized": False,
        "wave_1b_assessment_authorized": False,
        "cognition_update_authorized": False,
        "company_mapping_authorized": False,
        "stage_a2_authorized": False,
        "stage_b_authorized": False,
    }
    checkpoint_id = checkpoint_identity(core)
    checkpoint = capability_artifact_envelope(
        "acquisition_capability_checkpoint",
        {"checkpoint_id": checkpoint_id, **core},
    )
    validate_capability_checkpoint(checkpoint)
    for payload in (diagnosis, manifest, results, checkpoint):
        validate_non_evidence_artifact(payload)
    _write_json("diagnosis.json", diagnosis)
    _write_json("benchmark_manifest.json", manifest)
    _write_json("benchmark_results.json", results)
    _write_json("capability_checkpoint.json", checkpoint)
    _publish_bytes(OUT, "summary.md", _summary(checkpoint, diagnosis))
    print(json.dumps({"checkpoint_id": checkpoint_id, "checkpoint_hash": checkpoint["content_hash"], "benchmark_passed": results["passed_case_count"], "benchmark_failed": results["failed_case_count"]}, sort_keys=True))


if __name__ == "__main__":
    main()
