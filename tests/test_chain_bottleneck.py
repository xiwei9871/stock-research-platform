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


# ---------- CAP-02-T3: segment revenue + rival supply interface ----------

from stock_research.chain_t3_evidence import (
    SegmentRevenueRecord, RivalSupplyRecord,
    load_t3_records, segment_cell, segment_records_for, rival_supply_as_evidence,
)


def _seg(rid="seg1", code="002837", line="dc_liquid_cooling", scope="product_line",
         revenue=1e9, gm=0.3, review="pending"):
    return SegmentRevenueRecord(
        record_id=rid, stock_code=code, product_line=line,
        product_line_label=line, report_period="2025FY",
        disclosure_scope=scope, revenue=revenue, gross_margin=gm,
        source_id="s1", published_at="2026-04-21", ingested_at="2026-10-21",
        review_status=review,
    )


def test_segment_cell_states():
    # 精确产品线披露
    assert segment_cell([_seg(review="accepted")])["state"] == "disclosed"
    # 更宽口径段（含该线但未拆）
    assert segment_cell([_seg(scope="segment", review="accepted")])["state"] == "disclosed_broader_scope"
    # 明确未披露
    assert segment_cell([_seg(scope="undisclosed", review="accepted")])["state"] == "undisclosed"
    # 未抽取 ≠ 未披露
    assert segment_cell([_seg(scope="unextracted", review="accepted")])["state"] == "unextracted"
    assert segment_cell([])["state"] == "missing"


def test_segment_records_node_filter():
    recs = [_seg("a", "002837", "dc_liquid_cooling"),
            _seg("b", "002837", "ess_thermal"),
            _seg("c", "002371", "semi_front_end")]
    out = segment_records_for(recs, "002837", {"dc_liquid_cooling"})
    assert [r.record_id for r in out] == ["a"]


def test_rival_record_becomes_pending_node_evidence():
    rec = RivalSupplyRecord(
        record_id="rv1", rival_stock_code="301018", rival_name="申菱",
        node_id="n1", stage="量产", supply_facts="CDU全套+产能爬坡",
        source_id="s_riv", published_at="2026-04-27", ingested_at="2026-10-19",
        review_status="pending",
    )
    ev, src = rival_supply_as_evidence(rec)
    assert ev.evidence_scope == "node"
    assert ev.review_status == "pending"
    # pending 竞对证据进入待验证列表，不参与论点计数
    d = _node([ev], [src], [_nc("nc1", "process_irreplaceability", ["rv1"], role="non_substitutability")])
    assert d["node_claims"][0]["verdict"] == "needs_evidence"
    assert "rv1" in d["node_claims"][0]["unverified_evidence_ids"]


def test_validation_delivery_node_filtered():
    """机房/储能交付证据不能给半导体节点供货。"""
    from stock_research.chain_value_matrix import _validation_delivery_cell
    dossier = {
        "claims": [{"claim_id": "c1", "dimension": "commercialization",
                    "verdict": "partially_supported", "evidence_ids": ["e1"]}],
        "evidence_matrix": [{"evidence_id": "e1", "checklist_item": "实际交付",
                             "verdict_weight": "counted", "product_line": "ess_thermal"}],
        "dimensions": {"commercialization": {"verdict": "partially_supported"}},
    }
    assert _validation_delivery_cell(dossier, {"semi_front_end"}) == "node_attribution_unknown"
    assert _validation_delivery_cell(dossier, {"ess_thermal"}) == "partially_supported"


def test_t3_records_roundtrip(tmp_path):
    p = tmp_path / "t3.json"
    p.write_text('{"segment_records":[{"record_id":"s1","stock_code":"002837","product_line":"x","product_line_label":"X线","report_period":"2025FY","disclosure_scope":"product_line","source_id":"src1","revenue":100}],"rival_supply":[{"record_id":"r1","rival_stock_code":"301018","rival_name":"申菱","node_id":"n1","supply_facts":"facts","source_id":"s2"}]}')
    t3 = load_t3_records(p)
    assert len(t3["segment_records"]) == 1 and len(t3["rival_supply"]) == 1


# ---------- T3 收口: pending隔离 / PIT / source_type / 指纹 / 板块订单归因 ----------

from stock_research.chain_t3_evidence import (
    CustomerValidationRecord, OrderRecord, validation_cell, order_cell, t3_fingerprint,
)


def test_segment_pending_not_in_trusted_state():
    """pending 分产品数字只进 candidate_facts，state 不被提升。"""
    rec = _seg("a", "002837", "dc_liquid_cooling", scope="product_line", review="pending")
    cell = segment_cell([rec])
    assert cell["state"] == "pending_review"
    assert cell["facts"] == [] and cell["candidate_facts"]
    acc = _seg("b", "002837", "dc_liquid_cooling", scope="product_line", review="accepted")
    cell2 = segment_cell([rec, acc])
    assert cell2["state"] == "disclosed" and len(cell2["candidate_facts"]) == 1


def test_segment_pit_future_ingest_excluded():
    """as_of 历史时点读不到未来入库的 T3 数字。"""
    rec = _seg("a", "002837", "dc_liquid_cooling", review="accepted")
    rec2 = SegmentRevenueRecord(**{**rec.__dict__, "ingested_at": "2026-11-01"})
    assert segment_cell([rec2], as_of="2026-10-21")["state"] == "missing"
    assert segment_cell([rec2], as_of="2026-11-02")["state"] == "disclosed"


def test_rival_source_type_preserved():
    """券商线索不得被标成 company_filing。"""
    rec = RivalSupplyRecord(
        record_id="rv", rival_stock_code="603757", rival_name="大元", node_id="n1",
        supply_facts="x", source_id="B_dayuan", source_type="broker_report",
        reliability_level="S3", review_status="lead_only",
        published_at="2026-08-19", ingested_at="2026-10-19",
    )
    _ev, src = rival_supply_as_evidence(rec)
    assert src.source_type == "broker_report" and src.reliability_level == "S3"


def test_t3_fingerprint_changes_with_content_and_review():
    a = _seg("a", "002837", "x", review="pending")
    b = _seg("a", "002837", "x", review="accepted")
    assert t3_fingerprint([a], []) != t3_fingerprint([b], [])
    c = SegmentRevenueRecord(**{**a.__dict__, "revenue": 999})
    assert t3_fingerprint([a], []) != t3_fingerprint([c], [])


def test_board_order_not_product_line_order():
    """板块订单+72%不得归因为液冷单线订单。"""
    rec = OrderRecord(
        record_id="o1", stock_code="301018", product_line="dc_liquid_cooling",
        stage="contracted", scope="industry_board", review_status="accepted",
        source_id="s1", page_or_section="p10", published_at="2026-04-27",
        ingested_at="2026-10-19",
    )
    cell = order_cell([rec], "301018", {"dc_liquid_cooling"}, "2026-10-21")
    assert cell["state"] == "contracted_at_industry_board"  # 明示口径，不升级
    rec2 = OrderRecord(**{**rec.__dict__, "scope": "product_line"})
    assert order_cell([rec2], "301018", {"dc_liquid_cooling"}, "2026-10-21")["state"] == "verified_contracted"


def test_validation_stage_tiers():
    rec = CustomerValidationRecord(
        record_id="c1", stock_code="002837", product_line="dc_liquid_cooling",
        stage="validated", customer="Intel/NVIDIA MGX", review_status="accepted",
        source_id="s1", page_or_section="p9", published_at="2026-04-21",
        ingested_at="2026-10-19",
    )
    assert validation_cell([rec], "002837", {"dc_liquid_cooling"}, "2026-10-21")["state"] == "validated"
    lead = CustomerValidationRecord(**{**rec.__dict__, "review_status": "lead_only"})
    assert validation_cell([lead], "002837", {"dc_liquid_cooling"}, "2026-10-21")["state"] == "pending_review"


# ---------- T3 终校: 三处语义边界 + 订单优先级 ----------

def _ord(**kw):
    base = dict(record_id="o", stock_code="X", product_line="dc_liquid_cooling",
                stage="contracted", scope="product_line", source_id="S1",
                page_or_section="p1", published_at="2026-04-01",
                available_at="2026-04-01", ingested_at="2026-10-19",
                review_status="accepted")
    base.update(kw); return OrderRecord(**base)


def _cv(**kw):
    base = dict(record_id="c", stock_code="X", product_line="dc_liquid_cooling",
                stage="validated", customer="cust", scope="product_line",
                source_id="S1", page_or_section="p1", published_at="2026-04-01",
                available_at="2026-04-01", ingested_at="2026-10-19",
                review_status="accepted")
    base.update(kw); return CustomerValidationRecord(**base)


def test_no_major_contract_disclosure_does_not_override_orders():
    """'重大合同不适用'只说明披露项不适用，不得覆盖已核实订单。"""
    nodisc = _ord(record_id="n", stage="no_major_contract_disclosure", scope="company_total")
    cell = order_cell([nodisc], "X", {"dc_liquid_cooling"}, "2026-10-21")
    assert cell["state"] == "no_major_contract_disclosure"
    real = _ord(record_id="r", stage="contracted")
    cell2 = order_cell([nodisc, real], "X", {"dc_liquid_cooling"}, "2026-10-21")
    assert cell2["state"] == "verified_contracted"
    assert cell2["no_major_contract_disclosure"] is True  # 事实保留但不覆盖


def test_board_order_growth_not_contracted():
    """板块新增订单+72%是增长事实，不是可识别合同。"""
    g = _ord(stage="growth", scope="industry_board")
    cell = order_cell([g], "X", {"dc_liquid_cooling"}, "2026-10-21")
    assert cell["state"] == "order_growth_at_industry_board"
    assert cell["order_growth_facts"]


def test_board_customer_relations_not_product_validated():
    """板块客户关系≠液冷产品级认证。"""
    b = _cv(scope="industry_board")
    cell = validation_cell([b], "X", {"dc_liquid_cooling"}, "2026-10-21")
    assert cell["state"] == "validated_at_industry_board"
    pl = _cv(record_id="c2", scope="product_line", stage="ecosystem")
    cell2 = validation_cell([b, pl], "X", {"dc_liquid_cooling"}, "2026-10-21")
    assert cell2["state"] == "ecosystem"  # 生态成员<validated，分级不合并


def test_rival_refute_capped_without_substitution_verified():
    """产品序列披露不自动构成已接受的'有效替代'反证。"""
    rec = RivalSupplyRecord(
        record_id="rv", rival_stock_code="301018", rival_name="申菱", node_id="n1",
        supply_facts="CDU全序列+智造基地", source_id="S_shl", source_type="company_filing",
        reliability_level="S1", review_status="accepted",
        published_at="2026-04-27", available_at="2026-04-27", ingested_at="2026-10-19",
    )
    ev, _ = rival_supply_as_evidence(rec, direction="refute")
    assert ev.review_status == "pending"  # 封顶待核验
    rec2 = RivalSupplyRecord(**{**rec.__dict__, "substitution_verified": True})
    ev2, _ = rival_supply_as_evidence(rec2, direction="refute")
    assert ev2.review_status == "accepted"  # 有适配/产能实证才放行


def test_incomplete_source_cannot_be_accepted():
    """I2/I3 缺来源字段的'accepted'记录降级为候选。"""
    bad = _cv(uri="", page_or_section="", source_id="")
    cell = validation_cell([bad], "X", {"dc_liquid_cooling"}, "2026-10-21")
    assert cell["state"] == "pending_review"


def test_t3_audit_stats_counts():
    t3 = {"segment_records": [_seg(review="accepted"), _seg(rid="x2")],
          "rival_supply": [], "customer_validation": [_cv()], "orders": [_ord(stage="growth")]}
    from stock_research.chain_t3_evidence import t3_audit_stats
    st = t3_audit_stats(t3)
    assert st["totals"]["accepted"] == 3 and st["totals"]["pending"] == 1
    assert st["totals"]["n"] == 4


def test_percent_fields_use_decimal_ratio():
    """全量 T3 比例字段小数约定：margin/share∈[-1,1]，yoy∈[-1,5)，杜绝 30.9 式百分数。"""
    from stock_research.chain_t3_evidence import load_t3_records
    t3 = load_t3_records("docs/cap02/t3/t3_records.json")
    for r in t3["segment_records"]:
        for f in ("gross_margin", "revenue_share"):
            v = getattr(r, f)
            assert v is None or -1 <= v <= 1, f"{r.record_id}.{f}={v}"
        v = r.revenue_yoy
        assert v is None or -1 <= v < 5, f"{r.record_id}.revenue_yoy={v}"


def test_candidate_facts_carry_source_provenance():
    """券商 S3 候选与公司披露 S1 可直接区分。"""
    broker = _seg(rid="b", review="pending")
    broker = SegmentRevenueRecord(**{**broker.__dict__, "source_type": "broker_report",
                                   "reliability_level": "S3", "source_id": "brk1",
                                   "page_or_section": "p1"})
    cell = segment_cell([broker])
    cf = cell["candidate_facts"][0]
    assert cf["source_type"] == "broker_report" and cf["reliability_level"] == "S3"
    assert cf["source_id"] == "brk1" and cf["page"]
    filing = _seg(rid="f", review="accepted")
    cell2 = segment_cell([filing])
    assert cell2["facts"][0]["source_type"] == "company_filing"
