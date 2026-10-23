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


def test_cap07_baseline_semantics(tmp_path):
    """CAP-07 R1: 版本化基线 + 内容级 diff（非仅指纹）。"""
    from stock_research.capabilities.baseline import (
        load_baselines, save_baseline,
    )
    store = str(tmp_path / "baselines")
    snap_v1 = {"node_verdict": "unverified", "dossier_fingerprint": "fp_a",
               "claims": {"c1": {"verdict": "needs_evidence"}},
               "economics": {"002837": {"revenue": "missing"}},
               "cap_statuses": {"CAP-04": "ok"}}
    # 无基线 → unknown + CAP-07 归属 gap
    no_base = cap07_changes("n1", snap_v1, None, AS_OF, RUN_ID)
    assert no_base.status == "unknown"
    assert no_base.data_gaps[0].owner == "CAP-07"
    # 版本化保存；同内容重跑不追加（deduped）
    r1 = save_baseline(store, "n1", snap_v1)
    assert r1["version"] == 1
    r_dup = save_baseline(store, "n1", snap_v1)
    assert r_dup.get("deduped") is True
    assert len(load_baselines(store, "n1")) == 1
    # 同内容 diff → state_changed False
    same = cap07_changes("n1", snap_v1, load_baselines(store, "n1"), AS_OF, RUN_ID)
    assert same.findings["state_changed"] is False
    # 增删改三类：claim 变更 + evidence 新增/删除
    snap_v2 = {**snap_v1,
               "claims": {"c1": {"verdict": "confirmed"},
                          "c_new": {"verdict": "partially_supported"}},
               "evidence_refs": ["e1", "e2"],
               "dossier_fingerprint": "fp_b"}
    diff = cap07_changes("n1", snap_v2, load_baselines(store, "n1"), AS_OF, RUN_ID)
    assert diff.findings["state_changed"] is True
    ch = diff.findings["changes"]
    assert any(c["kind"] == "changed" and c["field"] == "claim:c1"
               and c["to"] == "confirmed" for c in ch)
    assert any(c["kind"] == "added" and c["field"] == "claim:c_new" for c in ch)
    assert any(c["kind"] == "added" and c["field"].startswith("evidence_ref:") for c in ch)
    assert diff.findings["baseline_version"] == 1
    # 变更后追加为 v2
    r2 = save_baseline(store, "n1", snap_v2)
    assert r2["version"] == 2
    # 删除类：evidence_refs 清空 → removed
    snap_v3 = {**snap_v2, "evidence_refs": []}
    diff3 = cap07_changes("n1", snap_v3, load_baselines(store, "n1"), AS_OF, RUN_ID)
    assert any(c["kind"] == "removed" for c in diff3.findings["changes"])


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
    """同一 claim_id 只计一次支持（五桶均去重）。"""
    out = run_research_chain(
        "liquid_cooling", SUBNODE_CASES, DOSSIER_DIR, AS_OF, RUN_ID)
    for envs in out["per_node"].values():
        s = envs["CAP-08"]["findings"]
        for bucket in ("favorable_support", "market_structure",
                       "counter_evidence", "hype_risks", "unresolved"):
            cids = [e["claim_id"] for e in s[bucket]]
            assert len(cids) == len(set(cids)), bucket


def test_pipeline_as_of_violation_degrades_not_silent():
    """P0-3: 晚案例数据不得生成早时点信封 → not_evaluated + 错误说明。"""
    out = run_research_chain(
        "liquid_cooling", SUBNODE_CASES[:1], DOSSIER_DIR, "2026-01-01", RUN_ID)
    assert out["errors"]
    key = next(iter(out["per_node"]))
    assert out["per_node"][key]["CAP-04"]["status"] == "not_evaluated"
    assert "as_of violation" in out["per_node"][key]["CAP-04"]["findings"]["error"]


def test_pipeline_envelope_labeled_with_case_pit():
    """早案例数据可答晚请求——信封以案例自身 PIT 标注。"""
    out = run_research_chain(
        "humanoid", ["docs/cap02/cases/humanoid_vision_node.json"],
        DOSSIER_DIR, AS_OF, RUN_ID)  # case.as_of = 2026-10-21
    assert not out["errors"]
    env = out["per_node"]["humanoid_vision_sensing"]["CAP-04"]
    assert env["as_of"] == "2026-10-21"


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


def test_cap08_five_bucket_evidence_split():
    """R1: hype→风险桶；market_structure→描述性格局（不自动反证）；可追溯。"""
    out = run_research_chain(
        "humanoid", ["docs/cap02/cases/humanoid_vision_node.json"],
        DOSSIER_DIR, AS_OF, RUN_ID)
    f = out["per_node"]["humanoid_vision_sensing"]["CAP-08"]["findings"]
    hype_ids = [e["claim_id"] for e in f["hype_risks"]]
    assert "nc_vision_hype" in hype_ids
    assert not any(e["claim_id"] == "nc_vision_hype" for e in f["favorable_support"])
    # 液冷 multi-supplier 格局论点 → market_structure 描述桶，**不是反证**
    out2 = run_research_chain(
        "liquid_cooling", SUBNODE_CASES[2:3], DOSSIER_DIR, AS_OF, RUN_ID)
    e8 = out2["per_node"]["liquid_cooling_pump_components"]["CAP-08"]
    f2 = e8["findings"]
    assert any(e["claim_id"] == "nc_multi_supplier" for e in f2["market_structure"])
    assert not any(e["claim_id"] == "nc_multi_supplier" for e in f2["counter_evidence"])
    # 追溯：每条桶内条目带 claim_text + evidence_ids + source_ids
    for bucket in ("favorable_support", "market_structure", "hype_risks"):
        for e in f2[bucket]:
            assert "hypothesis" in e and "evidence_ids" in e and "source_ids" in e
    # 信封级 evidence_refs 非空（上游指纹不替代原始引用）
    assert e8["evidence_refs"]


def test_cap03_theme_db_orchestration():
    """R1: 主题读层自动编排 — 液冷节点发现 4 case；映射带 review_status。"""
    from stock_research.capabilities.adapters import cap03_orchestrate_theme
    env = cap03_orchestrate_theme("ai_power_value_capture_v1", AS_OF, RUN_ID)
    assert env.status == "ok"
    f = env.findings
    assert f["read_source"] in {"artifact", "db", "compare"}
    assert f["node_count"] == 13
    lc = [n for n in f["nodes"] if n["node_id"] == "liquid_cooling"][0]
    assert len(lc["runnable_cases"]) == 4  # 父 + 3 子节点
    # 映射带审核状态；未审核映射只生成待研究任务
    assert lc["mapped_companies"][0]["review_status"] == "reviewed"
    assert lc["mapped_companies"][0]["company_code"] == "002837.SZ"
    # node_case 缺失 → 能力覆盖任务（非外部数据缺口）
    assert "hvdc_power" in f["coverage_gap_nodes"]
    assert not any(g.item == "node_case:hvdc_power" for g in env.data_gaps)
    cov_tasks = [t for t in f["research_tasks"]
                 if t.get("task_type") == "coverage_gap"]
    assert any(t["subject_id"] == "hvdc_power" for t in cov_tasks)


def test_workbench_index_consistency(tmp_path):
    """索引=最终研究结果：五桶/证据引用/指纹/覆盖状态/缺口数一致。"""
    from stock_research.capabilities.pipeline import run_theme_chain
    wb = str(tmp_path / "wb")
    out = run_theme_chain(
        "ai_power_value_capture_v1", DOSSIER_DIR, AS_OF, RUN_ID,
        baseline_dir=str(tmp_path / "b"), workbench_dir=wb)
    import json
    idx = json.loads(
        open(f"{wb}/ai_power_value_capture_v1/index.json").read())
    assert idx["theme_id"] == "ai_power_value_capture_v1"
    case_nodes = [n for n in idx["nodes"] if n.get("status") != "no_case"]
    uncovered = [n for n in idx["nodes"] if n.get("status") == "no_case"]
    assert len(case_nodes) == len(out["per_node"])
    # 主题 13 节点、4 个有案例 → 无案例节点入索引而非静默消失
    assert uncovered and all(n["coverage_owner"] == "CAP-02" for n in uncovered)
    assert idx["covered_node_count"] < idx["theme_node_count"]
    # 每节点五桶齐全 + 顶层证据引用/指纹（非 findings 误取）
    for n in case_nodes:
        for b in ("favorable_support", "market_structure",
                  "counter_evidence", "hype_risks", "unresolved"):
            assert b in n["synthesis"], (n["node_id"], b)
        assert isinstance(n["evidence_refs"], list)
        assert len(n["upstream_fingerprints"]) == 4
        env8 = out["per_node"][n["node_id"]]["CAP-08"]
        assert n["evidence_refs"] == env8["evidence_refs"]
        assert n["upstream_fingerprints"] == env8["upstream_fingerprints"]
        assert n["node_verdict"] == \
            out["per_node"][n["node_id"]]["CAP-04"]["findings"]["node_verdict"]
        # 子案例归属主题节点（不是独立主题节点）
        assert n["theme_node_id"] == "liquid_cooling"
    # 索引缺口数 == 最终 backlog（含 cap03 主题读层缺口合并后）
    assert sum(idx["gap_summary"].values()) == len(idx["gap_backlog"]) \
        == len(out["gap_backlog"])
    # CAP-03 信封必须是主题库版本（带 read_source），不是 case 列表版
    assert out["envelopes"]["CAP-03"]["findings"].get("read_source") in {
        "artifact", "db", "compare"}


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


def test_cap07_three_run_idempotent_no_metadata_growth(tmp_path):
    """UAT-A: 全链路连跑 3 次 —— 首跑建基线，后两跑无新研究事实不得追加。

    CAP-07 自身状态 / envelope 指纹 / baseline_count 均为运行元数据，
    不构成研究事实变化，不得造成循环版本增长。"""
    from stock_research.capabilities.baseline import load_baselines
    store = str(tmp_path / "baselines")
    env7_runs = []
    for i in range(3):
        out = run_research_chain(
            "liquid_cooling", SUBNODE_CASES, DOSSIER_DIR, AS_OF,
            f"{RUN_ID}-r{i}", baseline_dir=store)
        env7_runs.append(out["per_node"]["liquid_cooling_cdu_system"]["CAP-07"])
    versions = load_baselines(store, "liquid_cooling_cdu_system")
    assert len(versions) == 1, f"baselines grew: {len(versions)}"
    assert env7_runs[0]["status"] == "unknown"          # 首跑无基线
    assert env7_runs[1]["findings"]["state_changed"] is False
    assert env7_runs[2]["findings"]["state_changed"] is False
    assert env7_runs[2]["findings"]["baseline_version"] == 1


def test_cap07_pit_replay_ignores_future_baselines(tmp_path):
    """历史回放不得与未来日期基线比较，也不得覆盖较新历史。"""
    from stock_research.capabilities.baseline import (
        diff_baselines, load_baselines, save_baseline,
    )
    store = str(tmp_path / "baselines")
    future = {"as_of": "2026-10-31", "node_verdict": "unverified",
              "claims": {}, "economics": {}, "evidence_refs": []}
    save_baseline(store, "n1", future)
    # 回放更早时点：未来基线被跳过，不视为已有基线
    replay = {"as_of": "2026-10-25", "node_verdict": "unverified",
              "claims": {}, "economics": {}, "evidence_refs": []}
    d = diff_baselines(replay, load_baselines(store, "n1"))
    assert d["baseline_found"] is False
    assert d["skipped_future_versions"] == 1
    # 回放快照追加为新版本——较新历史（as_of 10-31）保留不被覆盖
    rec = save_baseline(store, "n1", replay)
    assert rec["version"] == 2
    versions = load_baselines(store, "n1")
    assert versions[0]["as_of"] == "2026-10-31"  # 原版本仍在
    # 再回到新时点：对比的是最新 PIT-eligible 基线
    newer = {"as_of": "2026-10-31", "node_verdict": "contested",
             "claims": {}, "economics": {}, "evidence_refs": []}
    d2 = diff_baselines(newer, versions)
    assert d2["baseline_found"] is True
    assert d2["baseline_version"] == 2  # eligible: v1(10-31)…排序按追加
    assert any(c["field"] == "node:node_verdict" for c in d2["changes"])


def test_cap07_diff_includes_sourced_revenue_facts(tmp_path):
    """内容 diff 覆盖有来源的产品线收入/毛利数值，不只是状态。"""
    from stock_research.capabilities.baseline import diff_baselines
    f1 = [{"product_line": "liquid_cooling_pump", "period": "2025H1",
           "revenue": 1.0, "gross_margin": 0.3, "source_id": "cninfo_x"}]
    f2 = [{**f1[0], "gross_margin": 0.35}]
    base = {"as_of": "2026-10-22",
            "economics": {"002837": {"revenue": "disclosed",
                                     "revenue_facts": f1}},
            "claims": {}, "evidence_refs": []}
    cur = {"as_of": "2026-10-22",
           "economics": {"002837": {"revenue": "disclosed",
                                    "revenue_facts": f2}},
           "claims": {}, "evidence_refs": []}
    d = diff_baselines(cur, [dict(base, version=1)])
    hits = [c for c in d["changes"] if "revenue_facts" in c["field"]]
    assert hits and hits[0]["kind"] == "changed"


# ---------------- CAP-R2A adversarial contract tests -----------------

def _mk_claim(cid, role="supply_scarcity", verdict="unknown",
              dim="capacity_constraint", evids=(), text=""):
    return {"claim_id": cid, "claim_text": text or cid, "claim_role": role,
            "dimension": dim, "verdict": verdict, "evidence_ids": list(evids)}


def _mk_ev(eid, sid="s1", direction="support", review="accepted",
           pit="in_scope", weight="counted", dim="capacity_constraint",
           excerpt=""):
    return {"evidence_id": eid, "source_id": sid, "direction": direction,
            "aspect": dim, "dimension": dim, "excerpt": excerpt,
            "review_status": review, "pit_status": pit,
            "verdict_weight": weight}


def test_r2a_support_plus_counter_is_contested():
    """一手支持 + 一手反证 → contested，不只保留支持。"""
    from stock_research.capabilities.reasoning import hypothesis_state_map
    c = _mk_claim("h1", verdict="partially_supported", evids=("e1", "e2"))
    idx = {"e1": _mk_ev("e1"), "e2": _mk_ev("e2", direction="refute")}
    assert hypothesis_state_map([c], idx)["h1"] == "contested"


def test_r2a_same_underlying_source_counts_once():
    """多条引用指向同一底层年报 → independent_source_count=1。"""
    from stock_research.capabilities.reasoning import assess_hypotheses
    c = _mk_claim("h1", verdict="confirmed", evids=("e1", "e2", "e3"))
    idx = {e: _mk_ev(e, sid="cninfo_002837_ar2025") for e in ("e1", "e2", "e3")}
    h = assess_hypotheses([c], idx, "n1", "2026-10-22")[0]
    assert h["independent_source_count"] == 1


def test_r2a_lead_only_evidence_never_promotes():
    """lead_only/pending/out-of-PIT 证据进入 excluded，不提升结论。"""
    from stock_research.capabilities.reasoning import (
        assess_hypotheses, hypothesis_state_map)
    c = _mk_claim("h1", verdict="needs_evidence", evids=("e1", "e2", "e3"))
    idx = {
        "e1": _mk_ev("e1", review="lead_only"),
        "e2": _mk_ev("e2", review="pending_review"),
        "e3": _mk_ev("e3", pit="out_of_scope"),
    }
    assert hypothesis_state_map([c], idx)["h1"] == "unresolved"
    h = assess_hypotheses([c], idx, "n1", "2026-10-22")[0]
    assert h["assessment_state"] == "unresolved"
    assert len(h["excluded_evidence"]) == 3
    assert h["independent_source_count"] == 0
    reasons = {e["reason"].split("=")[0] for e in h["excluded_evidence"]}
    assert reasons == {"review_status", "pit_status"}


def test_r2a_product_cert_not_customer_cert():
    """产品通过 Intel/UL 测试 ≠ 客户认证壁垒成立。"""
    from stock_research.capabilities.reasoning import assess_technical
    dossier = {
        "node_id": "n1", "as_of": "2026-10-22",
        "node_claims": [
            _mk_claim("c_cert", role="entry_barrier", verdict="unknown",
                      dim="certification_barrier", evids=("e1",),
                      text="客户认证周期构成壁垒"),
        ],
        "evidence_matrix": [
            _mk_ev("e1", dim="certification_barrier",
                   excerpt="产品通过英特尔测试验证和UL认证"),
        ],
        "value_matrix": {"rows": []},
    }
    ta = assess_technical(dossier)["entry_barrier"]
    assert ta["sub_checks"]["product_certification"]["evidence_ids"] == ["e1"]
    assert ta["sub_checks"]["customer_validation"]["state"] in {
        "no_evidence", "unverified"}
    assert ta["assessment"] == "unverified"


def test_r2a_demand_growth_alone_not_shortage():
    """需求增长论点不推导供给紧缺；多供应商不自动证伪。"""
    from stock_research.capabilities.reasoning import assess_technical
    dossier = {
        "node_id": "n1", "as_of": "2026-10-22",
        "node_claims": [
            _mk_claim("c_dem", role="market_structure",
                      verdict="confirmed", text="AI算力需求高增长"),
            _mk_claim("c_multi", role="market_structure",
                      verdict="partially_supported", evids=("e1",),
                      text="多家已验证供应商"),
        ],
        "evidence_matrix": [_mk_ev("e1")],
        "value_matrix": {"rows": []},
    }
    ta = assess_technical(dossier)["supply_constraint"]
    assert "需求增长" in ta["sub_checks"]["demand_growth"]["note"] or \
        ta["sub_checks"]["demand_growth"]["state"] in {
            "support_seen", "partial", "no_evidence"}
    assert ta["sub_checks"]["supplier_count_limited"]["state"] == "partial"
    # 格局事实 ≠ 紧缺 verdict：assessment 保持 unverified
    assert ta["assessment"] == "unverified"


def test_r2a_component_vs_system_not_comparable():
    """组件供应商与系统厂商 not_comparable；子公司 partially。"""
    from stock_research.capabilities.reasoning import compare_competition
    rows = [
        {"stock_code": "A", "mapping_type": "direct_product",
         "tech_participation": "confirmed", "validation_delivery": "validated",
         "revenue_profit": {"state": "missing"}, "verified_orders": {"state": "none_seen"}},
        {"stock_code": "B", "mapping_type": "direct_component",
         "tech_participation": "confirmed", "validation_delivery": "mass_delivery",
         "revenue_profit": {"state": "missing"}, "verified_orders": {"state": "verified_delivered"}},
        {"stock_code": "C", "mapping_type": "subsidiary",
         "tech_participation": "partial", "validation_delivery": "none_seen",
         "revenue_profit": {"state": "missing"}, "verified_orders": {"state": "none_seen"}},
    ]
    out = compare_competition({"value_matrix": {"rows": rows}}, {})
    by_pair = {(p["a"], p["b"]): p["comparison_scope"]
               for p in out["pairwise_scope"]}
    assert by_pair[("A", "B")] == "not_comparable"
    assert by_pair[("A", "C")] == "partially_comparable"
    assert out["comparison"]["A"]["comparable_with"] == []
    assert "B" in (out["comparison"]["A"]["comparable_with"]
                   + [c for p in out["pairwise_scope"]
                      for c in [p["a"], p["b"]] if c == "B"])  # B列在表中但不可比


def test_r2a_broader_revenue_not_line_revenue():
    """板块收入不升级为产品线兑现；交付不升级为收入确认。"""
    from stock_research.capabilities.adapters import cap05_value_economics
    dossier = {"value_matrix": {"rows": [
        {"stock_code": "002371",
         "revenue_profit": {"state": "disclosed_broader_scope",
                            "facts": [{"scope": "segment", "revenue": 100,
                                       "gross_margin": 0.4}]},
         "validation_delivery": "validated",
         "verified_orders": {"state": "none_seen"}},
    ]}}
    env = cap05_value_economics("n1", dossier, AS_OF, RUN_ID)
    e = env.findings["economics"]["002371"]
    assert e["commercialization_stage"] != "revenue_visible"
    assert e["commercialization_stage"] == "delivery_seen"
    assert e["margin_state"] == "segment_level"
    assert e["value_capture_verdict"] == "not_evaluated"
    assert e["independent_facts"]["cash"] == "unknown"


def test_r2a_no_comparable_insufficient_evidence():
    """单一成员/口径不明 → 无可比公司如实标注。"""
    from stock_research.capabilities.reasoning import compare_competition
    out = compare_competition({"value_matrix": {"rows": [
        {"stock_code": "X", "mapping_type": "dependency",
         "tech_participation": "partial", "validation_delivery": "pending_review",
         "revenue_profit": {"state": "missing"},
         "verified_orders": {"state": "pending_review"}},
    ]}}, {})
    assert out["pairwise_scope"] == []
    assert out["comparison"]["X"]["comparable_with"] == []


def test_r2a_hypothesis_in_baseline_diff(tmp_path):
    """假设状态变化进入基线 diff（研究事实而非元数据）。"""
    from stock_research.capabilities.baseline import diff_baselines
    base = {"as_of": "2026-10-22", "hypotheses": {"h1": "unresolved"},
            "claims": {}, "economics": {}, "evidence_refs": []}
    cur = {"as_of": "2026-10-22", "hypotheses": {"h1": "contested",
                                                 "h2": "risk_flagged"},
           "claims": {}, "economics": {}, "evidence_refs": []}
    d = diff_baselines(cur, [dict(base, version=1)])
    kinds = {(c["kind"], c["field"]) for c in d["changes"]}
    assert ("changed", "hypothesis:h1") in kinds
    assert ("added", "hypothesis:h2") in kinds


def test_r2a_real_cases_no_positive_fabrication():
    """真实三节点：产品认证不证壁垒、组件交付不证系统、hype 归风险。"""
    from stock_research.capabilities.reasoning import assess_technical
    from stock_research.capabilities.adapters import _build_node_dossier
    # 大元泵组件：交付≠系统级
    d, dbc = _build_node_dossier(
        "docs/cap02/cases/liquid_cooling_pump_components_node.json",
        DOSSIER_DIR)
    ta = assess_technical(d)
    assert ta["entry_barrier"]["assessment"] == "unverified"
    assert ta["entry_barrier"]["sub_checks"]["customer_validation"][
        "state"] in {"no_evidence", "unverified"}
    # 全案例：entry_barrier 不得因产品认证而 supported
    for p in ("liquid_cooling_cdu_system_node.json",
            "liquid_cooling_coldplate_manifold_node.json",
            "semi_equipment_node.json"):
        d2, _ = _build_node_dossier(f"docs/cap02/cases/{p}", DOSSIER_DIR)
        t2 = assess_technical(d2)
        assert t2["entry_barrier"]["sub_checks"]["customer_validation"][
            "state"] in {"no_evidence", "unverified"}, p
