"""Contract tests for the CAP-01 company intelligence engine."""
from __future__ import annotations

from stock_research.company_intelligence import (
    CompanyEvidence,
    CompanySource,
    ResearchClaim,
    build_company_dossier,
)


def _src(source_id="S1", source_type="company_filing", published="2026-03-01",
         available="2026-03-02", reliability="S1"):
    return CompanySource(
        source_id=source_id,
        source_type=source_type,
        title=f"title-{source_id}",
        publisher="pub",
        published_at=published,
        available_at=available,
        ingested_at="2026-03-05",
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
    claims = [_claim("c1", "commercialization")]
    ev = [
        _ev("e1", "commercialization", direction="unclear", review="pending"),
    ]
    d = _dossier(claims, ev, [_src()])
    assert d["dimensions"]["commercialization"]["verdict"] == "needs_evidence"


def test_single_source_support_is_partially_supported():
    claims = [_claim("c1", "commercialization")]
    ev = [_ev("e1", "commercialization"), _ev("e2", "commercialization", page="p11")]
    d = _dossier(claims, ev, [_src()])
    dim = d["dimensions"]["commercialization"]
    assert dim["verdict"] == "partially_supported"
    assert dim["confidence"] > 0.0


def test_independent_source_types_promote_to_confirmed():
    claims = [_claim("c1", "tech_moat")]
    ev = [_ev("e1", "tech_moat", source_id="S1"),
          _ev("e2", "tech_moat", source_id="S2")]
    d = _dossier(claims, ev, [_src("S1", "company_filing"),
                              _src("S2", "broker_report")])
    assert d["dimensions"]["tech_moat"]["verdict"] == "confirmed"


def test_refuting_only_evidence_is_contradicted():
    claims = [_claim("c1", "commercialization")]
    ev = [_ev("e1", "commercialization", direction="refute")]
    d = _dossier(claims, ev, [_src()])
    assert d["dimensions"]["commercialization"]["verdict"] == "contradicted"


def test_support_and_refute_surface_conflict_not_silence():
    claims = [_claim("c1", "competitive_edge")]
    ev = [_ev("e1", "competitive_edge", direction="support"),
          _ev("e2", "competitive_edge", direction="refute", page="p12")]
    d = _dossier(claims, ev, [_src()])
    dim = d["dimensions"]["competitive_edge"]
    assert dim["verdict"] == "contested"
    assert len(dim["conflicts"]) == 1


def test_evidence_published_after_as_of_is_excluded_and_recorded():
    claims = [_claim("c1", "financial_realization")]
    ev = [_ev("e1", "financial_realization")]
    src = [_src(published="2026-11-01", available="2026-11-02")]
    d = _dossier(claims, ev, src, as_of="2026-10-20")
    assert d["dimensions"]["financial_realization"]["verdict"] == "unknown"
    assert "e1" in d["post_asof_excluded"]


def test_concept_only_company_keeps_low_confidence():
    """Theme-adjacent name without commercialization evidence -> needs_evidence,
    never silently positive."""
    claims = [_claim("c1", "commercialization", "robot orders exist")]
    ev = [_ev("e1", "commercialization", direction="unclear",
              source_id="S1", confidence="low", excerpt="公司表示正关注机器人赛道")]
    d = _dossier(claims, ev, [_src(source_type="media_article", reliability="S3")])
    dim = d["dimensions"]["commercialization"]
    assert dim["verdict"] == "needs_evidence"
    assert d["conclusion"]["overall_verdict"] in {"needs_evidence", "unverified"}


def test_research_gaps_list_missing_checklist_items():
    claims = [_claim("c1", "commercialization")]
    ev = [_ev("e1", "commercialization")]
    d = _dossier(claims, ev, [_src()])
    gap_dims = {g["dimension"] for g in d["research_gaps"]}
    # missing dimensions produce gaps; commercialization has evidence so it
    # may still list sub-items but the never-evidenced dims must appear
    assert "tech_moat" in gap_dims
    assert "financial_realization" in gap_dims


def test_dossier_outputs_and_guardrails():
    claims = [_claim("c1", "tech_moat")]
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
