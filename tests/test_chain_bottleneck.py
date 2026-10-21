"""CAP-02 T1/T2 contract tests: node-scope binding, bottleneck verdict, matrix."""

from __future__ import annotations

from stock_research.chain_bottleneck import build_node_dossier, load_node_case
from stock_research.chain_value_matrix import build_value_matrix
from stock_research.company_intelligence import (
    CompanyEvidence,
    CompanySource,
    ResearchClaim,
)


def _src(sid, stype="industry_data", publisher="第三方研究", published="2025-08-19",
         ingested="2026-09-22"):
    return CompanySource(
        source_id=sid, source_type=stype, publisher=publisher,
        published_at=published, ingested_at=ingested,
    )


def _nev(eid, aspect="capacity_constraint", direction="support", scope="node",
         review="accepted", src=None, checklist=""):
    return CompanyEvidence(
        evidence_id=eid, source_id=src or f"src_{eid}", dimension=aspect,
        direction=direction, excerpt=f"node excerpt {eid}", review_status=review,
        checklist_item=checklist, evidence_scope=scope,
    )


def _nc(cid, aspect, eids, role=""):
    return ResearchClaim(claim_id=cid, dimension=aspect,
                         claim_text=f"node claim {cid}", evidence_ids=tuple(eids),
                         claim_role=role)


def _node(evidence, sources, claims, members=(), as_of="2026-10-20"):
    return build_node_dossier(
        node_id="n1", node_name="测试节点", as_of=as_of,
        node_claims=claims, evidence=evidence, sources=sources,
        member_companies=members,
    )


def test_company_scope_evidence_cannot_prove_node_bottleneck():
    """核心验收：公司级证据绑定节点论点 → 剔除并报 scope 绑定告警。"""
    ev = [_nev("e_company", "capacity_constraint", "support", scope="company")]
    d = _node(ev, [_src("src_e_company")], [_nc("nc1", "capacity_constraint", ["e_company"])])
    claim = d["node_claims"][0]
    assert claim["verdict"] == "unknown"
    assert claim["binding_errors"] == ["e_company"]
    assert "nc1:e_company" in d["binding_warnings"]
    assert d["aspects"]["capacity_constraint"]["verdict"] == "needs_evidence"


def test_two_core_aspects_supported_establishes_bottleneck():
    ev = [
        _nev("e_cap", "capacity_constraint", "support", checklist="供需缺口/排队"),
        _nev("e_proc", "process_irreplaceability", "support", checklist="工艺独有性"),
    ]
    d = _node(ev, [_src("src_e_cap"), _src("src_e_proc")],
              [_nc("nc_cap", "capacity_constraint", ["e_cap"], role="supply_scarcity"),
               _nc("nc_proc", "process_irreplaceability", ["e_proc"], role="non_substitutability")])
    assert d["conclusion"]["node_verdict"] == "bottleneck_established"


def test_hype_supported_blocks_established():
    """炒作成分被证实的节点不能判 bottleneck_established。"""
    ev = [
        _nev("e_cap", "capacity_constraint", "support"),
        _nev("e_proc", "process_irreplaceability", "support"),
        _nev("e_hype", "hype_only", "support"),
    ]
    d = _node(ev, [_src("src_e_cap"), _src("src_e_proc"), _src("src_e_hype")],
              [_nc("nc_cap", "capacity_constraint", ["e_cap"], role="supply_scarcity"),
               _nc("nc_proc", "process_irreplaceability", ["e_proc"], role="non_substitutability"),
               _nc("nc_hype", "hype_only", ["e_hype"], role="hype")])
    assert d["conclusion"]["node_verdict"] == "bottleneck_unverified"


def test_lead_only_evidence_excluded_from_node_verdict():
    ev = [_nev("e1", "capacity_constraint", "support", review="lead_only")]
    d = _node(ev, [_src("src_e1")], [_nc("nc1", "capacity_constraint", ["e1"])])
    assert d["node_claims"][0]["verdict"] == "needs_evidence"
    assert "e1" in d["node_claims"][0]["unverified_evidence_ids"]


def test_node_pit_late_ingestion_excluded():
    ev = [_nev("e1", "capacity_constraint", "support", src="s_late")]
    src = [_src("s_late", published="2026-11-01", ingested="2026-11-05")]
    d = _node(ev, src, [_nc("nc1", "capacity_constraint", ["e1"])], as_of="2026-10-20")
    assert "e1" in d["post_asof_excluded"]
    assert d["node_claims"][0]["verdict"] == "unknown"


def test_node_dossier_fingerprint_differs_by_as_of():
    ev = [_nev("e1", "capacity_constraint", "support")]
    claims = [_nc("nc1", "capacity_constraint", ["e1"])]
    a = _node(ev, [_src("src_e1")], claims, as_of="2026-10-20")
    b = _node(ev, [_src("src_e1")], claims, as_of="2026-10-21")
    assert a["dossier_fingerprint"] != b["dossier_fingerprint"]


def test_value_matrix_maps_dossier_verdicts_and_flags_concept_only():
    dossier_strong = {
        "company_code": "002837", "company_name": "英维克",
        "dossier_fingerprint": "fp1",
        "conclusion": {"overall_verdict": "unverified"},
        "dimensions": {
            "tech_moat": {"verdict": "partially_supported"},
            "commercialization": {"verdict": "partially_supported"},
            "financial_realization": {"verdict": "partially_supported"},
        },
        "claims": [
            {"claim_id": "c1", "dimension": "commercialization",
             "verdict": "partially_supported", "evidence_ids": ["e1"]},
        ],
        "evidence_matrix": [
            {"evidence_id": "e1", "checklist_item": "量产/订单", "verdict_weight": "counted"},
        ],
    }
    dossier_concept = {
        "company_code": "688686", "company_name": "奥普特",
        "dossier_fingerprint": "fp2",
        "conclusion": {"overall_verdict": "needs_evidence"},
        "dimensions": {
            "tech_moat": {"verdict": "partially_supported"},
            "commercialization": {"verdict": "needs_evidence"},
            "financial_realization": {"verdict": "needs_evidence"},
        },
        "claims": [{"claim_id": "c2", "dimension": "commercialization",
                    "verdict": "needs_evidence", "evidence_ids": []}],
        "evidence_matrix": [],
    }
    members = [
        {"stock_code": "002837", "company_name": "英维克", "mapping_type": "direct_product", "priority_score": 78.8},
        {"stock_code": "688686", "company_name": "奥普特", "mapping_type": "dependency", "priority_score": 98.0},
        {"stock_code": "000000", "company_name": "无画像", "mapping_type": "dependency", "priority_score": 50.0},
    ]
    m = build_value_matrix(
        node_id="n1", node_name="节点", as_of="2026-10-20",
        member_companies=members,
        dossier_by_code={"002837": dossier_strong, "688686": dossier_concept},
    )
    by_code = {r["stock_code"]: r for r in m["rows"]}
    assert by_code["002837"]["verified_orders"] == "production_claimed"  # 量产≠订单
    assert by_code["002837"]["concept_only_risk"] == "low"
    assert by_code["688686"]["concept_only_risk"] == "high"
    assert by_code["688686"]["validation_delivery"] == "needs_evidence"
    assert by_code["000000"]["dossier"] == "missing"


# ---------- CAP-02-R2: conservative node verdict + strict order/delivery cell ----------


def test_multi_supplier_exists_but_scarcity_still_unverified():
    """多供应商存在（工艺非独家被反驳）≠ 供给瓶颈被否定。产能无证据 → 未证实，非 rejected。"""
    ev = [
        _nev("e_rival", "process_irreplaceability", "refute", review="accepted", src="s_r"),
    ]
    d = _node(ev, [_src("s_r", "broker_report", "券商A")],
              [_nc("nc_capacity", "capacity_constraint", []),
               _nc("nc_process", "process_irreplaceability", ["e_rival"])])
    assert d["node_claims"][1]["verdict"] == "contradicted"
    assert d["aspects"]["process_irreplaceability"]["verdict"] == "contradicted"
    assert d["conclusion"]["node_verdict"] == "bottleneck_unverified"  # 非 rejected


def test_scarcity_claim_affirmatively_refuted_is_rejected():
    """只有产能/供给约束主张本身被反证（accepted 节点证据）才 bottleneck_rejected。"""
    ev = [
        _nev("e_glut", "capacity_constraint", "refute", review="accepted", src="s_r"),
    ]
    d = _node(ev, [_src("s_r")],
              [_nc("nc_capacity", "capacity_constraint", ["e_glut"], role="supply_scarcity")])
    assert d["conclusion"]["node_verdict"] == "bottleneck_rejected"


def test_two_generic_tech_aspects_cannot_establish_bottleneck():
    """认证/性能两项一般性支持（无产能或可替代性证据）不能确立瓶颈。"""
    ev = [
        _nev("e_cert", "certification_barrier", "support"),
        _nev("e_perf", "performance_gap", "support"),
    ]
    d = _node(ev, [_src("src_e_cert"), _src("src_e_perf")],
              [_nc("nc_cert", "certification_barrier", ["e_cert"]),
               _nc("nc_perf", "performance_gap", ["e_perf"])])
    assert d["conclusion"]["node_verdict"] == "bottleneck_unverified"
    assert d["conclusion"]["node_verdict"] != "bottleneck_established"


def test_scarcity_plus_second_core_establishes_bottleneck():
    """产能（或可替代性限制）有实证 + 第二核心门支持 + 无炒作 → established。"""
    ev = [
        _nev("e_cap", "capacity_constraint", "support", checklist="供需缺口/排队"),
        _nev("e_cert", "certification_barrier", "support", checklist="认证周期"),
    ]
    d = _node(ev, [_src("src_e_cap"), _src("src_e_cert")],
              [_nc("nc_cap", "capacity_constraint", ["e_cap"], role="supply_scarcity"),
               _nc("nc_cert", "certification_barrier", ["e_cert"], role="entry_barrier")])
    assert d["conclusion"]["node_verdict"] == "bottleneck_established"


def test_mass_production_is_not_verified_order():
    """量产/交付表述 ≠ 可核实订单：量产 claim → delivery/production 级，不给 verified_order。"""
    from stock_research.chain_value_matrix import _order_claim_state
    dossier = {
        "claims": [{"claim_id": "c1", "dimension": "commercialization",
                    "verdict": "partially_supported", "evidence_ids": ["e1"]}],
        "evidence_matrix": [{"evidence_id": "e1", "checklist_item": "量产阶段",
                             "verdict_weight": "counted"}],
    }
    assert _order_claim_state(dossier) == "production_claimed"
    dossier2 = {
        "claims": [{"claim_id": "c1", "dimension": "commercialization",
                    "verdict": "partially_supported", "evidence_ids": ["e1"]}],
        "evidence_matrix": [{"evidence_id": "e1", "checklist_item": "实际交付",
                             "verdict_weight": "counted"}],
    }
    assert _order_claim_state(dossier2) == "verified_delivery"
    dossier3 = {
        "claims": [{"claim_id": "c1", "dimension": "commercialization",
                    "verdict": "partially_supported", "evidence_ids": ["e1"]}],
        "evidence_matrix": [{"evidence_id": "e1", "checklist_item": "已确认订单",
                             "verdict_weight": "counted"}],
    }
    assert _order_claim_state(dossier3) == "verified_order"


def test_future_company_dossier_excluded_from_historical_node_matrix():
    """公司 dossier as_of 晚于节点截止 → 行标记 pit_incompatible，单元格不可用。"""
    future = {
        "company_code": "688686", "as_of": "2026-11-01",
        "dossier_fingerprint": "fpF",
        "conclusion": {"overall_verdict": "unverified"},
        "dimensions": {"tech_moat": {"verdict": "partially_supported"},
                       "commercialization": {"verdict": "partially_supported"},
                       "financial_realization": {"verdict": "partially_supported"}},
        "claims": [], "evidence_matrix": [],
    }
    m = build_value_matrix(
        node_id="n1", node_name="节点", as_of="2026-10-20",
        member_companies=[{"stock_code": "688686", "company_name": "奥普特"}],
        dossier_by_code={"688686": future},
    )
    row = m["rows"][0]
    assert row["dossier"] == "pit_incompatible"
    assert row["tech_participation"] == "excluded"
    assert row["verified_orders"] == "excluded"


def test_market_structure_plus_barrier_cannot_establish():
    """多供应商事实（market_structure）+ 认证壁垒（entry_barrier）获支持 → 不得 established。"""
    ev = [
        _nev("e_roster", "process_irreplaceability", "support"),
        _nev("e_cert", "certification_barrier", "support"),
    ]
    d = _node(ev, [_src("src_e_roster"), _src("src_e_cert")],
              [_nc("nc_roster", "process_irreplaceability", ["e_roster"], role="market_structure"),
               _nc("nc_cert", "certification_barrier", ["e_cert"], role="entry_barrier")])
    assert d["conclusion"]["node_verdict"] != "bottleneck_established"
    assert d["conclusion"]["node_verdict"] == "bottleneck_unverified"


def test_local_capacity_claim_refuted_not_rejected():
    """market_structure 角色的局部产能 claim 被反证 → 不构成瓶颈主张否定 → 非 rejected。"""
    ev = [_nev("e1", "capacity_constraint", "refute", review="accepted", src="s_r")]
    d = _node(ev, [_src("s_r")],
              [_nc("nc_cap", "capacity_constraint", ["e1"], role="market_structure")])
    assert d["conclusion"]["node_verdict"] != "bottleneck_rejected"


def test_ess_delivery_not_dc_cooling_delivery():
    """储能温控交付证据不能证明数据中心液冷节点交付。"""
    from stock_research.chain_value_matrix import _order_claim_state
    dossier = {
        "claims": [{"claim_id": "c1", "dimension": "commercialization",
                    "verdict": "partially_supported", "evidence_ids": ["e1"]}],
        "evidence_matrix": [{"evidence_id": "e1", "checklist_item": "实际交付",
                             "verdict_weight": "counted", "product_line": "ess_thermal"}],
    }
    assert _order_claim_state(dossier, {"dc_liquid_cooling"}) == "node_attribution_unknown"
    assert _order_claim_state(dossier, {"ess_thermal"}) == "verified_delivery"
    dossier2 = {
        "claims": [{"claim_id": "c1", "dimension": "commercialization",
                    "verdict": "partially_supported", "evidence_ids": ["e1"]}],
        "evidence_matrix": [{"evidence_id": "e1", "checklist_item": "实际交付",
                             "verdict_weight": "counted", "product_line": ""}],
    }
    assert _order_claim_state(dossier2, {"dc_liquid_cooling"}) == "node_attribution_unknown"
