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
    # gap backlog 非空且每条带归属（CAP-07 基线归 CAP-07，数据缺口归 DATA）
    assert out["gap_backlog"]
    for g in out["gap_backlog"]:
        assert g["kind"] in GAP_KINDS
        assert g["owner"] in {"DATA", "CAP-07"}


def test_chain_never_fabricates_positive_findings():
    """P0-2: R0 无精确产品线收入 → value_capture 一律 not_evaluated。"""
    out = run_research_chain(
        "liquid_cooling", SUBNODE_CASES, DOSSIER_DIR, AS_OF, RUN_ID)
    for node_id, envs in out["per_node"].items():
        econ = envs["CAP-05"]["findings"]["economics"]
        for code, e in econ.items():
            assert e["value_capture_verdict"] == "not_evaluated", (node_id, code)
            # 三个格子保持独立事实位，不合并
            for f in ("revenue_state", "delivery_state", "order_state"):
                assert f in e


def test_cap04_views_classified_by_claim_role_not_dimension():
    """P0-1: market_structure role 不得混入 scarcity/substitutability 视图。"""
    from stock_research.capabilities.adapters import cap04_tech_supply
    env, _, _ = cap04_tech_supply(
        "docs/cap02/cases/liquid_cooling_pump_components_node.json",
        DOSSIER_DIR, AS_OF, RUN_ID)
    views = env.findings["views"]
    assert set(views) >= {"supply_scarcity", "non_substitutability",
                          "market_structure", "entry_barrier", "hype"}
    multi = [c for v in views.values() for c in v
             if c["claim_id"] == "nc_multi_supplier"][0]
    # 多供应商 claim 维度虽是 process_irreplaceability，但 role 是格局
    assert multi["claim_role"] == "market_structure"
    assert multi in views["market_structure"]
    for v in ("supply_scarcity", "non_substitutability", "entry_barrier", "hype"):
        assert multi not in views[v]


def test_cap08_dedupes_support_by_claim_id():
    """同一 claim_id 只计一次支持。"""
    out = run_research_chain(
        "liquid_cooling", SUBNODE_CASES, DOSSIER_DIR, AS_OF, RUN_ID)
    for envs in out["per_node"].values():
        s = envs["CAP-08"]["findings"]
        cids = [x.split(":")[1].split("=")[0] for x in s["supports"]]
        assert len(cids) == len(set(cids))
        assert s["support_claim_count"] == len(s["supports"])


def test_pipeline_as_of_mismatch_degrades_not_silent():
    """P0-3: 案例 as_of 与请求不一致 → not_evaluated + 错误说明。"""
    out = run_research_chain(
        "liquid_cooling", SUBNODE_CASES[:1], DOSSIER_DIR, "2026-01-01", RUN_ID)
    assert out["errors"]
    key = next(iter(out["per_node"]))
    assert out["per_node"][key]["CAP-04"]["status"] == "not_evaluated"
    assert "as_of mismatch" in out["per_node"][key]["CAP-04"]["findings"]["error"]


def test_pipeline_invalid_case_isolated():
    """坏 case 报错但其他节点继续。"""
    out = run_research_chain(
        "liquid_cooling", SUBNODE_CASES + ["docs/cap02/cases/NO_SUCH.json"],
        DOSSIER_DIR, AS_OF, RUN_ID)
    assert len(out["errors"]) == 1
    assert len(out["per_node"]) == 4  # 3 合法 + 1 错误信封


def test_cap03_invalid_case_recorded_not_skipped():
    env = cap03_orchestrate("t", ["docs/cap02/cases/liquid_cooling_cdu_system_node.json",
                                  "docs/cap02/cases/NO_SUCH.json"], AS_OF, RUN_ID)
    assert env.status == "partial"
    assert len(env.findings["invalid_cases"]) == 1
    # product_lines 必须是 JSON 数组类型
    assert isinstance(env.findings["nodes"][0]["product_lines"], list)


def test_gap_backlog_deduped_with_owners():
    """P1: (node,kind,item,owner) 去重 + source_capabilities + CAP-07 归属。"""
    out = run_research_chain(
        "liquid_cooling", SUBNODE_CASES, DOSSIER_DIR, AS_OF, RUN_ID)
    keys = [(g["node_id"], g["kind"], g["item"], g["owner"])
            for g in out["gap_backlog"]]
    assert len(keys) == len(set(keys))
    baseline = [g for g in out["gap_backlog"]
                if g["item"].startswith("baseline_fingerprint")]
    assert baseline and all(g["owner"] == "CAP-07" for g in baseline)
    for g in out["gap_backlog"]:
        assert g["source_capabilities"]
