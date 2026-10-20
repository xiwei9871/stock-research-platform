"""Contract tests for the CAP-01 company intelligence engine."""
from __future__ import annotations

from stock_research.company_intelligence import (
    CompanyEvidence,
    CompanySource,
    ResearchClaim,
    build_company_dossier,
)


def _src(source_id="S1", source_type="company_filing", published="2026-03-01",
         available="2026-03-02", reliability="S1", publisher="pub",
         ingested="2026-03-05"):
    return CompanySource(
        source_id=source_id,
        source_type=source_type,
        title=f"title-{source_id}",
        publisher=publisher,
        published_at=published,
        available_at=available,
        ingested_at=ingested,
        reliability_level=reliability,
    )


def _ev(eid, dimension, direction="support", source_id="S1", page="p10",
        confidence="high", review="accepted", excerpt="x"):
    return CompanyEvidence(
        evidence_id=eid,
        source_id=source_id,
        dimension=dimension,
        direction=direction,
        excerpt=excerpt,
        page_or_section=page,
        confidence=confidence,
        review_status=review,
    )


def _claim(cid, dimension, text="claim", evidence_ids=()):
    return ResearchClaim(
        claim_id=cid, dimension=dimension, claim_text=text,
        evidence_ids=tuple(evidence_ids),
    )


def _dossier(claims, evidence, sources, as_of="2026-10-20", **kw):
    return build_company_dossier(
        company_code="002837", company_name="英维克",
        as_of=as_of, claims=claims, evidence=evidence, sources=sources, **kw
    )


def test_dimension_without_any_evidence_is_unknown():
    d = _dossier([], [], [])
    for dim in d["dimensions"].values():
        assert dim["verdict"] == "unknown"
        assert dim["confidence"] == 0.0


def test_pending_or_unclear_evidence_only_is_needs_evidence():
    claims = [_claim("c1", "commercialization", evidence_ids=["e1"])]
    ev = [
        _ev("e1", "commercialization", direction="unclear", review="pending"),
    ]
    d = _dossier(claims, ev, [_src()])
    assert d["dimensions"]["commercialization"]["verdict"] == "needs_evidence"


def test_single_source_support_is_partially_supported():
    claims = [_claim("c1", "commercialization", evidence_ids=["e1", "e2"])]
    ev = [_ev("e1", "commercialization"), _ev("e2", "commercialization", page="p11")]
    d = _dossier(claims, ev, [_src()])
    dim = d["dimensions"]["commercialization"]
    assert dim["verdict"] == "partially_supported"
    assert dim["confidence"] > 0.0


def test_independent_source_types_promote_to_confirmed():
    claims = [_claim("c1", "tech_moat", evidence_ids=["e1", "e2"])]
    ev = [_ev("e1", "tech_moat", source_id="S1"),
          _ev("e2", "tech_moat", source_id="S2")]
    d = _dossier(claims, ev, [_src("S1", "company_filing", publisher="公司披露"),
                              _src("S2", "broker_report", publisher="券商A")])
    assert d["dimensions"]["tech_moat"]["verdict"] == "confirmed"


def test_refuting_only_evidence_is_contradicted():
    claims = [_claim("c1", "commercialization", evidence_ids=["e1"])]
    ev = [_ev("e1", "commercialization", direction="refute")]
    d = _dossier(claims, ev, [_src()])
    assert d["dimensions"]["commercialization"]["verdict"] == "contradicted"


def test_support_and_refute_surface_conflict_not_silence():
    claims = [_claim("c1", "competitive_edge", evidence_ids=["e1", "e2"])]
    ev = [_ev("e1", "competitive_edge", direction="support"),
          _ev("e2", "competitive_edge", direction="refute", page="p12")]
    d = _dossier(claims, ev, [_src()])
    dim = d["dimensions"]["competitive_edge"]
    assert dim["verdict"] == "contested"
    assert len(dim["conflicts"]) == 1


def test_evidence_published_after_as_of_is_excluded_and_recorded():
    claims = [_claim("c1", "financial_realization", evidence_ids=["e1"])]
    ev = [_ev("e1", "financial_realization")]
    src = [_src(published="2026-11-01", available="2026-11-02",
                ingested="2026-11-05")]
    d = _dossier(claims, ev, src, as_of="2026-10-20")
    assert d["dimensions"]["financial_realization"]["verdict"] == "unknown"
    assert "e1" in d["post_asof_excluded"]


def test_concept_only_company_keeps_low_confidence():
    """Theme-adjacent name without commercialization evidence -> needs_evidence,
    never silently positive."""
    claims = [_claim("c1", "commercialization", "robot orders exist",
                     evidence_ids=["e1"])]
    ev = [_ev("e1", "commercialization", direction="unclear",
              source_id="S1", confidence="low", excerpt="公司表示正关注机器人赛道")]
    d = _dossier(claims, ev, [_src(source_type="media_article", reliability="S3")])
    dim = d["dimensions"]["commercialization"]
    assert dim["verdict"] == "needs_evidence"
    assert d["conclusion"]["overall_verdict"] in {"needs_evidence", "unverified"}


def test_research_gaps_list_missing_checklist_items():
    claims = [_claim("c1", "commercialization", evidence_ids=["e1"])]
    ev = [_ev("e1", "commercialization")]
    d = _dossier(claims, ev, [_src()])
    gap_dims = {g["dimension"] for g in d["research_gaps"]}
    # missing dimensions produce gaps; commercialization has evidence so it
    # may still list sub-items but the never-evidenced dims must appear
    assert "tech_moat" in gap_dims
    assert "financial_realization" in gap_dims


def test_dossier_outputs_and_guardrails():
    claims = [_claim("c1", "tech_moat", evidence_ids=["e1", "e2"])]
    ev = [_ev("e1", "tech_moat", direction="support"),
          _ev("e2", "tech_moat", direction="refute", page="p9")]
    d = _dossier(claims, ev, [_src()])
    assert set(d) >= {"company_code", "as_of", "dimensions", "evidence_matrix",
                      "bull_case", "bear_case", "research_gaps", "conclusion",
                      "guardrails", "input_snapshot"}
    assert d["guardrails"]["research_only"] is True
    assert d["guardrails"]["used_for_signal"] is False
    # evidence matrix rows carry locator + direction + timestamps
    row = d["evidence_matrix"][0]
    assert {"evidence_id", "dimension", "direction", "page_or_section",
            "source_id", "published_at"} <= set(row)


def test_claim_links_specific_evidence_and_unlinked_evidence_warns():
    claims = [_claim("c1", "tech_moat", evidence_ids=["e1"])]
    ev = [_ev("e1", "tech_moat"), _ev("e9", "tech_moat")]
    d = _dossier(claims, ev, [_src()])
    claim_row = d["claims"][0]
    assert claim_row["evidence_ids"] == ["e1"]
    # e9 still participates in the dimension tally but is not bound to c1
    assert set(d["dimensions"]["tech_moat"]["evidence_ids"]) == {"e1", "e9"}


# ---------- CAP-01-R1: claim-level verdicts, review tiers, strict PIT, fingerprint ----------


def _ev2(eid, dim="tech_moat", direction="support", review="accepted",
        src=None, checklist=""):
    return CompanyEvidence(
        evidence_id=eid, source_id=src or f"src_{eid}", dimension=dim,
        direction=direction, excerpt=f"excerpt {eid}", review_status=review,
        checklist_item=checklist,
    )


def _src2(sid, stype="company_filing", publisher="公司披露", published="2025-08-19",
         ingested="2026-09-22", reliability="S1"):
    return CompanySource(
        source_id=sid, source_type=stype, publisher=publisher,
        published_at=published, ingested_at=ingested, reliability_level=reliability,
    )


def _claim2(cid, dim, eids):
    return ResearchClaim(claim_id=cid, dimension=dim, claim_text=f"claim {cid}",
                         evidence_ids=tuple(eids))


def _build2(evidence, sources, claims, as_of="2026-10-20"):
    return build_company_dossier(
        company_code="T001", company_name="测试", as_of=as_of,
        claims=claims, evidence=evidence, sources=sources,
    )


def test_claim_level_verdicts_keep_distinct_propositions_separate():
    """同维度下不同论点不互相污染：被反证的论点与有支持的论点各自保留。"""
    evidence = [
        _ev2("e_sup", "competitive_edge", "support", "accepted", "s_filing"),
        _ev2("e_ref", "competitive_edge", "refute", "accepted", "s_broker"),
    ]
    sources = [
        _src2("s_filing", "company_filing", "公司披露"),
        _src2("s_broker", "broker_report", "券商A"),
    ]
    claims = [
        _claim2("c_uniqueness", "competitive_edge", ["e_ref"]),
        _claim2("c_capability", "competitive_edge", ["e_sup"]),
    ]
    d = _build2(evidence, sources, claims)
    by_id = {c["claim_id"]: c for c in d["claims"]}
    assert by_id["c_uniqueness"]["verdict"] == "contradicted"
    assert by_id["c_capability"]["verdict"] == "partially_supported"
    # 维度聚合：一个论点被推翻 + 一个有支持 → contested，而非整体 contradicted
    assert d["dimensions"]["competitive_edge"]["verdict"] == "contested"


def test_lead_only_cannot_contradict_or_confirm():
    """lead_only 证据可见但不参与判定。"""
    evidence = [
        _ev2("e_sup", "tech_moat", "support", "accepted", "s_filing"),
        _ev2("e_lead", "tech_moat", "refute", "lead_only", "s_broker"),
    ]
    sources = [_src2("s_filing"), _src2("s_broker", "broker_report", "券商A")]
    claims = [_claim2("c1", "tech_moat", ["e_sup", "e_lead"])]
    d = _build2(evidence, sources, claims)
    c = d["claims"][0]
    assert c["verdict"] == "partially_supported"
    assert c["support_count"] == 1 and c["refute_count"] == 0
    assert "e_lead" in c["unverified_evidence_ids"]
    assert d["dimensions"]["tech_moat"]["verdict"] == "partially_supported"


def test_claim_with_only_lead_only_evidence_is_needs_evidence():
    evidence = [_ev2("e1", "commercialization", "support", "lead_only", "s_b")]
    d = _build2(evidence, [_src2("s_b", "broker_report", "券商A")],
               [_claim2("c1", "commercialization", ["e1"])])
    assert d["claims"][0]["verdict"] == "needs_evidence"
    assert d["dimensions"]["commercialization"]["verdict"] == "needs_evidence"


def test_pending_evidence_cannot_confirm():
    """pending 证据不进入判定计数。"""
    evidence = [
        _ev2("e1", "tech_moat", "support", "pending", "s_f"),
        _ev2("e2", "tech_moat", "support", "pending", "s_b"),
    ]
    sources = [_src2("s_f"), _src2("s_b", "broker_report", "券商A")]
    claims = [_claim2("c1", "tech_moat", ["e1", "e2"])]
    d = _build2(evidence, sources, claims)
    assert d["claims"][0]["verdict"] == "needs_evidence"


def test_confirmed_requires_independent_accepted_sources():
    """confirmed 需 ≥2 source_type + ≥2 publisher + ≥2 source_id，全部 accepted。"""
    evidence = [
        _ev2("e1", "tech_moat", "support", "accepted", "s_f"),
        _ev2("e2", "tech_moat", "support", "accepted", "s_b"),
    ]
    sources = [_src2("s_f"), _src2("s_b", "broker_report", "券商A")]
    d = _build2(evidence, sources, [_claim2("c1", "tech_moat", ["e1", "e2"])])
    assert d["claims"][0]["verdict"] == "confirmed"
    # 同一 publisher 不算独立 → 降级
    sources_same_pub = [_src2("s_f"), _src2("s_b", "broker_report", "公司披露")]
    d2 = _build2(evidence, sources_same_pub, [_claim2("c1", "tech_moat", ["e1", "e2"])])
    assert d2["claims"][0]["verdict"] == "partially_supported"
    # 单一 source_type → 降级
    evidence_one_type = [
        _ev2("e1", "tech_moat", "support", "accepted", "s_f"),
        _ev2("e3", "tech_moat", "support", "accepted", "s_f2"),
    ]
    sources_one_type = [_src2("s_f"), _src2("s_f2")]
    d3 = _build2(evidence_one_type, sources_one_type,
                [_claim2("c1", "tech_moat", ["e1", "e3"])])
    assert d3["claims"][0]["verdict"] == "partially_supported"


def test_unclear_only_claim_is_needs_evidence_not_contradicted():
    """"未披露"类证据（unclear）不能将论点打成反证。"""
    evidence = [_ev2("e1", "financial_realization", "unclear", "accepted", "s_f")]
    d = _build2(evidence, [_src2("s_f")],
               [_claim2("c1", "financial_realization", ["e1"])])
    assert d["claims"][0]["verdict"] == "needs_evidence"


def test_late_ingested_evidence_excluded_from_claim_counts():
    """入库晚于截止日的证据必须同时退出 claim 计数与判定。"""
    evidence = [_ev2("e_late", "tech_moat", "support", "accepted", "s_late")]
    sources = [_src2("s_late", published="2025-01-01", ingested="2026-10-25")]
    d = _build2(evidence, sources, [_claim2("c1", "tech_moat", ["e_late"])])
    assert d["claims"][0]["verdict"] == "unknown"
    assert d["claims"][0]["support_count"] == 0
    assert "e_late" in d["post_asof_excluded"]
    assert d["dimensions"]["tech_moat"]["verdict"] == "unknown"


def test_year_precision_published_with_proven_ingestion_is_in_scope():
    """published 只有年份但入库时间已证 ≤ as_of → 在范围内，标记精度。"""
    evidence = [_ev2("e1", "tech_moat", "support", "accepted", "s1")]
    sources = [_src2("s1", published="2026", ingested="2026-09-22")]
    d = _build2(evidence, sources, [_claim2("c1", "tech_moat", ["e1"])])
    assert d["claims"][0]["verdict"] == "partially_supported"
    row = [r for r in d["evidence_matrix"] if r["evidence_id"] == "e1"][0]
    assert row["published_precision"] == "year"
    assert row["pit_status"] == "in_scope"


def test_year_precision_without_ingest_straddling_cutoff_is_uncertain():
    """published="2026"、无入库证据、as_of 在年内 → PIT 不定，退出判定。"""
    evidence = [_ev2("e1", "tech_moat", "support", "accepted", "s1")]
    sources = [CompanySource(source_id="s1", source_type="company_filing",
                           publisher="公司披露", published_at="2026")]
    d = _build2(evidence, sources, [_claim2("c1", "tech_moat", ["e1"])])
    assert "e1" in d["pit_uncertain"]
    assert d["claims"][0]["verdict"] == "unknown"
    row = [r for r in d["evidence_matrix"] if r["evidence_id"] == "e1"][0]
    assert row["pit_status"] == "uncertain"


def test_no_dates_is_pit_uncertain():
    evidence = [_ev2("e1", "tech_moat", "support", "accepted", "s1")]
    sources = [CompanySource(source_id="s1", source_type="company_filing")]
    d = _build2(evidence, sources, [_claim2("c1", "tech_moat", ["e1"])])
    assert "e1" in d["pit_uncertain"]
    assert d["claims"][0]["verdict"] == "unknown"


def test_post_asof_by_publish_still_excluded():
    evidence = [_ev2("e1", "tech_moat", "support", "accepted", "s1")]
    sources = [_src2("s1", published="2026-12-01", ingested="2026-12-05")]
    d = _build2(evidence, sources, [_claim2("c1", "tech_moat", ["e1"])])
    assert "e1" in d["post_asof_excluded"]
    assert d["claims"][0]["verdict"] == "unknown"


def test_fingerprint_covers_full_content():
    """正文、方向、审核状态、claim 绑定变更都必须改变指纹。"""
    base_ev = [_ev2("e1", src="s1")]
    base_src = [_src2("s1")]
    base_claims = [_claim2("c1", "tech_moat", ["e1"])]
    fp0 = _build2(base_ev, base_src, base_claims)["input_snapshot"]["evidence_set_sha256"]

    changed_excerpt = [CompanyEvidence(
        evidence_id="e1", source_id="s1", dimension="tech_moat",
        direction="support", excerpt="修改后的正文", review_status="accepted")]
    fp1 = _build2(changed_excerpt, base_src, base_claims)["input_snapshot"]["evidence_set_sha256"]
    assert fp1 != fp0

    changed_status = [_ev2("e1", src="s1", review="lead_only")]
    fp2 = _build2(changed_status, base_src, base_claims)["input_snapshot"]["evidence_set_sha256"]
    assert fp2 != fp0

    changed_bind = [_claim2("c1", "tech_moat", [])]
    fp3 = _build2(base_ev, base_src, changed_bind)["input_snapshot"]["evidence_set_sha256"]
    assert fp3 != fp0


def test_dimension_without_claims_uses_pool_floor():
    """无 claim 但有证据的维度 → needs_evidence（存在未评估材料）；空池 → unknown。"""
    evidence = [_ev2("e1", "chain_position", "support", "accepted", "s1")]
    d = _build2(evidence, [_src2("s1")], [])
    assert d["dimensions"]["chain_position"]["verdict"] == "needs_evidence"
    assert d["dimensions"]["tech_moat"]["verdict"] == "unknown"
