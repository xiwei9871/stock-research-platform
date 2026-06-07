from __future__ import annotations

import pandas as pd
import pytest

from stock_research.research_infra.attribution_cards import (
    AttributionCard,
    AttributionCardValidationError,
    build_attribution_cards_from_frame,
    export_attribution_cards,
    render_attribution_card_markdown,
)


def test_attribution_card_is_jsonable_and_preserves_review_fields() -> None:
    card = AttributionCard(
        case_id="case:mid-trend:000001.SZ:2026-06-06",
        asset_id="asset:000001.SZ",
        ts_code="000001.SZ",
        trade_date="2026-06-06",
        strategy_context="mid_trend_review",
        failure_or_success_type="failure",
        primary_cause="research_coverage_gap",
        secondary_causes=["market_regime_mismatch"],
        evidence={
            "research_support_score": None,
            "missingness_reason": "no_fresh_report",
        },
        counterfactual="Would require fresh coverage before promotion.",
        preventability="preventable",
        recommended_rule_change="Block promotion when coverage_freshness_score is missing.",
        confidence="medium",
    )

    payload = card.to_dict()
    assert payload["primary_cause"] == "research_coverage_gap"
    assert payload["secondary_causes"] == ["market_regime_mismatch"]
    assert payload["evidence"]["missingness_reason"] == "no_fresh_report"
    assert payload["preventability"] == "preventable"


def test_attribution_card_rejects_invalid_cause_category() -> None:
    with pytest.raises(AttributionCardValidationError) as exc:
        AttributionCard(
            case_id="case:bad",
            asset_id="asset:000001.SZ",
            ts_code="000001.SZ",
            trade_date="2026-06-06",
            strategy_context="mid_trend_review",
            failure_or_success_type="failure",
            primary_cause="unknown_cause",
            secondary_causes=[],
            evidence={"reason": "fixture"},
            counterfactual="N/A",
            preventability="unknown",
            recommended_rule_change="N/A",
            confidence="low",
        )

    assert "primary_cause" in str(exc.value)
    assert "unknown_cause" in str(exc.value)


def test_attribution_card_requires_evidence_and_counterfactual() -> None:
    with pytest.raises(AttributionCardValidationError) as exc:
        AttributionCard(
            case_id="case:missing",
            asset_id="asset:000001.SZ",
            ts_code="000001.SZ",
            trade_date="2026-06-06",
            strategy_context="mid_trend_review",
            failure_or_success_type="failure",
            primary_cause="bad_buy",
            secondary_causes=[],
            evidence={},
            counterfactual="",
            preventability="preventable",
            recommended_rule_change="N/A",
            confidence="medium",
        )

    message = str(exc.value)
    assert "evidence" in message
    assert "counterfactual" in message


def test_render_attribution_card_markdown_includes_review_sections() -> None:
    card = AttributionCard(
        case_id="case:missed-winner",
        asset_id="asset:000002.SZ",
        ts_code="000002.SZ",
        trade_date="2026-06-06",
        strategy_context="topn_review",
        failure_or_success_type="failure",
        primary_cause="missed_winner",
        secondary_causes=["industry_regime_mismatch"],
        evidence={"future_return_20d": 0.32, "rank_at_entry": 42},
        counterfactual="Candidate would enter TopN with industry regime boost.",
        preventability="partly_preventable",
        recommended_rule_change="Review regime-conditioned score uplift.",
        confidence="medium",
    )

    markdown = render_attribution_card_markdown(card)

    assert markdown.startswith("# Attribution Card: case:missed-winner")
    assert "## Cause" in markdown
    assert "missed_winner" in markdown
    assert "## Counterfactual" in markdown
    assert "Review regime-conditioned score uplift." in markdown


def test_build_attribution_cards_from_frame_maps_rows_to_cards() -> None:
    frame = pd.DataFrame(
        [
            {
                "case_id": "case:drawdown",
                "asset_id": "asset:000003.SZ",
                "ts_code": "000003.SZ",
                "trade_date": "2026-06-06",
                "strategy_context": "watchlist_review",
                "failure_or_success_type": "failure",
                "primary_cause": "drawdown_control",
                "secondary_causes": ["data_quality_gap"],
                "evidence": {"max_drawdown_20d": -0.18},
                "counterfactual": "Reduce exposure after drawdown breach.",
                "preventability": "preventable",
                "recommended_rule_change": "Trigger drawdown-control review at -15%.",
                "confidence": "high",
            }
        ]
    )

    cards = build_attribution_cards_from_frame(frame)
    assert len(cards) == 1
    assert cards[0].primary_cause == "drawdown_control"
    assert cards[0].secondary_causes == ["data_quality_gap"]


def test_export_attribution_cards_returns_jsonable_rows() -> None:
    card = AttributionCard(
        case_id="case:replacement",
        asset_id="asset:000004.SZ",
        ts_code="000004.SZ",
        trade_date="2026-06-06",
        strategy_context="portfolio_review",
        failure_or_success_type="failure",
        primary_cause="replacement_failure",
        secondary_causes=[],
        evidence={"replaced_return_20d": 0.18, "replacement_return_20d": -0.04},
        counterfactual="Keep original candidate.",
        preventability="partly_preventable",
        recommended_rule_change="Require replacement evidence margin.",
        confidence="medium",
    )

    assert export_attribution_cards([card]) == [card.to_dict()]
