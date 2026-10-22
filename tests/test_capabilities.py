"""CAP-00 contract tests — envelope shape, degradation, chain smoke."""

from __future__ import annotations

import pytest

from stock_research.capabilities.contract import (
    GAP_KINDS, DataGap, ResearchEnvelope, STATUSES, make_envelope,
)
from stock_research.capabilities.adapters import (
    cap03_orchestrate, cap07_changes, cap09_workbench, cap10_strategy_bridge,
)
from stock_research.capabilities.pipeline import run_research_chain
from stock_research.capabilities.registry import CAPABILITIES, dependency_graph

AS_OF = "2026-10-22"
RUN_ID = "cap00-r0-test"

SUBNODE_CASES = [
    "docs/cap02/cases/liquid_cooling_cdu_system_node.json",
    "docs/cap02/cases/liquid_cooling_coldplate_manifold_node.json",
    "docs/cap02/cases/liquid_cooling_pump_components_node.json",
]
DOSSIER_DIR = "outputs/research/company_intelligence"


def test_envelope_required_fields_and_isolation_flags():
    env = make_envelope("CAP-05", "node", "n1", AS_OF, RUN_ID, status="unknown")
    d = env.to_dict()
    for field in ("capability_id", "subject_type", "subject_id", "as_of",
                  "run_id", "status", "findings", "evidence_refs",
                  "uncertainties", "data_gaps", "fingerprint",
                  "rule_version", "research_only", "used_for_signal",
                  "used_for_admission", "upstream_fingerprints"):
        assert field in d, field
    assert d["research_only"] is True
    assert d["used_for_signal"] is False and d["used_for_admission"] is False
    assert env.fingerprint and len(env.fingerprint) == 64


def test_envelope_fingerprint_sensitive_to_findings_and_upstream():
    a = make_envelope("CAP-05", "node", "n1", AS_OF, RUN_ID,
                      findings={"x": 1})
    b = make_envelope("CAP-05", "node", "n1", AS_OF, RUN_ID,
                      findings={"x": 2})
    c = make_envelope("CAP-05", "node", "n1", AS_OF, RUN_ID,
                      findings={"x": 1}, upstream_fingerprints=["u1"])
    assert a.fingerprint != b.fingerprint != c.fingerprint


def test_invalid_gap_kind_rejected():
    with pytest.raises(ValueError):
        DataGap(kind="not_a_kind", item="x")
    with pytest.raises(ValueError):
        make_envelope("CAP-05", "node", "n1", AS_OF, RUN_ID, status="bogus")


def test_registry_covers_cap00_to_cap10():
    expected = {f"CAP-{i:02d}" for i in range(11)}
    assert expected <= set(CAPABILITIES)
    graph = dependency_graph()
    assert "CAP-08" in graph and set(graph["CAP-08"]) == {
        "CAP-03", "CAP-04", "CAP-05", "CAP-06", "CAP-07"}
    for cap, spec in CAPABILITIES.items():
        for f in ("question", "reuse", "r0", "degraded"):
            assert f in spec, (cap, f)


def test_cap03_orchestrate_three_subnodes():
    env = cap03_orchestrate("liquid_cooling", SUBNODE_CASES, AS_OF, RUN_ID)
    assert env.status == "ok"
    assert len(env.findings["nodes"]) == 3
    ids = {n["node_id"] for n in env.findings["nodes"]}
    assert len(ids) == 3
    assert env.findings["task_count"] > 0


def test_cap03_empty_cases_degrades_unknown_with_gap():
    env = cap03_orchestrate("empty_theme", [], AS_OF, RUN_ID)
    assert env.status == "unknown"
    assert env.data_gaps and env.data_gaps[0].kind == "missing_source"


def test_cap07_baseline_semantics():
    no_base = cap07_changes("n1", "fp_x", None, AS_OF, RUN_ID)
    assert no_base.status == "unknown"
    assert no_base.data_gaps[0].item.startswith("baseline_fingerprint")
    same = cap07_changes("n1", "fp_x", ["fp_x"], AS_OF, RUN_ID)
    assert same.findings["state_changed"] is False
    diff = cap07_changes("n1", "fp_y", ["fp_x"], AS_OF, RUN_ID)
    assert diff.findings["state_changed"] is True


def test_cap10_isolation():
    env = cap10_strategy_bridge(AS_OF, RUN_ID)
    assert env.status == "not_evaluated"
    assert env.research_only and not env.used_for_signal and not env.used_for_admission


def test_cap09_reuses_existing_endpoints():
    env = cap09_workbench(AS_OF, RUN_ID)
    assert env.status == "ok"
    assert any("dashboard" in e for e in env.findings["reuse_endpoints"])


def test_end_to_end_chain_liquid_cooling():
    """三液冷子节点全链路 smoke — 不中断、语义齐全、gap 全合法。"""
    out = run_research_chain(
        "liquid_cooling", SUBNODE_CASES, DOSSIER_DIR, AS_OF, RUN_ID)
    assert out["envelopes"]["CAP-03"]["status"] == "ok"
    assert len(out["per_node"]) == 3
    for node_id, envs in out["per_node"].items():
        for cap in ("CAP-04", "CAP-05", "CAP-06", "CAP-07", "CAP-08"):
            env = envs[cap]
            assert env["status"] in STATUSES, (node_id, cap)
            assert env["research_only"] and not env["used_for_signal"]
            for g in env["data_gaps"]:
                assert g["kind"] in GAP_KINDS
        # CAP-04 必须有真实 verdict 视图，不是占位
        assert envs["CAP-04"]["findings"]["node_verdict"]
        assert envs["CAP-04"]["findings"]["claim_count"] > 0
        # CAP-08 引用了上游指纹链
        assert len(envs["CAP-08"]["upstream_fingerprints"]) == 4
    # gap backlog 非空且每条带归属
    assert out["gap_backlog"]
    for g in out["gap_backlog"]:
        assert g["kind"] in GAP_KINDS and g["owner"] == "DATA"


def test_chain_never_fabricates_positive_findings():
    """无成员 dossier 的节点：CAP-05 不输出 verified，只输出 gap。"""
    out = run_research_chain(
        "liquid_cooling", SUBNODE_CASES, DOSSIER_DIR, AS_OF, RUN_ID)
    for node_id, envs in out["per_node"].items():
        econ = envs["CAP-05"]["findings"]["economics"]
        for code, e in econ.items():
            if e["revenue_state"] in {"missing", "undisclosed", "unextracted"}:
                assert e["value_capture_verdict"] != "verified"
