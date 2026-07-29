from __future__ import annotations

import math
from decimal import Decimal
from fractions import Fraction

import numpy as np
import pandas as pd
import pytest

from stock_research.consumer_oversold.features import (
    compute_fundamental_features,
    compute_hard_risk_features,
    compute_valuation_features,
)


FINANCE_NUMERIC = {
    "revenue_ttm": 100.0,
    "revenue_growth": 0.10,
    "np_parent_ttm": 10.0,
    "profit_growth": 0.08,
    "gross_margin": 0.40,
    "net_margin": 0.10,
    "roe": 0.12,
    "ocf_to_np": 1.10,
    "debt_ratio": 0.45,
    "equity_parent": 50.0,
    "operating_cash_flow": 11.0,
}


def finance_row(
    asset_id: str,
    report_period: str,
    announcement_date: str,
    **overrides: object,
) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "report_period": report_period,
        "announcement_date": announcement_date,
        **FINANCE_NUMERIC,
        **overrides,
    }


def fundamental_row(asset_id: str, **overrides: object) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "latest_announcement_date": pd.Timestamp("2025-03-31"),
        "latest_revenue_growth": 0.00,
        "normal_revenue_growth": 0.10,
        "latest_net_margin": 0.05,
        "normal_net_margin": 0.10,
        "positive_profit_periods": 8,
        "stable_positive_earnings": True,
        "latest_equity_parent": 50.0,
        "latest_debt_ratio": 0.45,
        "latest_operating_cash_flow": 10.0,
        "prior_operating_cash_flow": 9.0,
        "second_prior_operating_cash_flow": 8.0,
        **overrides,
    }


def current_row(asset_id: str, **overrides: object) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "as_of_date": "2025-04-30",
        "consumer_subindustry": "food",
        "current_market_cap": 100.0,
        "net_debt": 5.0,
        "pe_ttm": 10.0,
        "ps_ttm": 1.0,
        "ev_ebitda": 8.0,
        "revenue_ttm": 100.0,
        "np_parent_ttm": 10.0,
        "ebitda_ttm": 15.0,
        **overrides,
    }


def monthly_history(
    asset_id: str,
    method: str,
    values: list[float],
    *,
    subindustry: str = "food",
    start: str = "2023-01-31",
) -> list[dict[str, object]]:
    dates = pd.date_range(start, periods=len(values), freq="ME")
    rows = []
    for date, value in zip(dates, values, strict=True):
        row = {
            "asset_id": asset_id,
            "valuation_date": date,
            "consumer_subindustry": subindustry,
            "pe_ttm": np.nan,
            "ps_ttm": np.nan,
            "ev_ebitda": np.nan,
        }
        row[method] = value
        rows.append(row)
    return rows


def test_fundamentals_are_point_in_time_use_latest_announcement_and_eight_period_median():
    rows = []
    for index in range(9):
        period = pd.Timestamp("2022-12-31") + pd.offsets.QuarterEnd(index)
        rows.append(
            finance_row(
                "B",
                period.date().isoformat(),
                (period + pd.Timedelta(days=30)).date().isoformat(),
                revenue_growth=float(index + 1),
                operating_cash_flow=float(index + 1),
            )
        )
    rows.extend(
        [
            finance_row("A", "2024-12-31", "2025-02-01", revenue_growth=1.0),
            finance_row("A", "2024-12-31", "2025-03-01", revenue_growth=3.0),
            finance_row("A", "2025-03-31", "2025-05-01", revenue_growth=99.0),
        ]
    )

    result = compute_fundamental_features(pd.DataFrame(rows), trade_date="2025-04-30")

    assert result["asset_id"].tolist() == ["A", "B"]
    a = result.set_index("asset_id").loc["A"]
    assert a["latest_report_period"] == pd.Timestamp("2024-12-31")
    assert a["latest_announcement_date"] == pd.Timestamp("2025-03-01")
    assert a["latest_revenue_growth"] == 3.0
    b = result.set_index("asset_id").loc["B"]
    assert b["history_periods"] == 8
    assert b["latest_revenue_growth"] == 9.0
    assert b["normal_revenue_growth"] == pytest.approx(5.5)
    assert b["prior_operating_cash_flow"] == 8.0
    assert b["second_prior_operating_cash_flow"] == 7.0
    assert b["revenue_growth_delta_to_prior"] == 1.0
    assert b["positive_profit_periods"] == 8
    assert b["stable_positive_earnings"]
    assert a["positive_profit_periods"] == 1
    assert not a["stable_positive_earnings"]


@pytest.mark.parametrize("field,value", [("report_period", "bad"), ("announcement_date", "bad")])
def test_fundamentals_reject_invalid_dates(field, value):
    row = finance_row("A", "2024-12-31", "2025-03-01")
    row[field] = value
    with pytest.raises(ValueError, match=field):
        compute_fundamental_features(pd.DataFrame([row]), trade_date="2025-04-30")


@pytest.mark.parametrize("value", [np.inf, -np.inf, True, "1.0"])
def test_fundamentals_reject_non_finite_bool_and_string_numbers(value):
    row = finance_row("A", "2024-12-31", "2025-03-01", revenue_growth=value)
    with pytest.raises(ValueError, match=r"A.*revenue_growth"):
        compute_fundamental_features(pd.DataFrame([row]), trade_date="2025-04-30")


def test_fundamentals_reject_duplicate_same_period_and_announcement():
    row = finance_row("A", "2024-12-31", "2025-03-01")
    with pytest.raises(ValueError, match="A"):
        compute_fundamental_features(pd.DataFrame([row, row]), trade_date="2025-04-30")


def test_fundamentals_accept_finite_database_decimal_as_float():
    result = compute_fundamental_features(
        pd.DataFrame(
            [
                finance_row(
                    "A",
                    "2024-12-31",
                    "2025-03-01",
                    revenue_growth=Decimal("0.009411"),
                )
            ]
        ),
        trade_date="2025-04-30",
    ).iloc[0]
    assert result["latest_revenue_growth"] == pytest.approx(0.009411)
    assert isinstance(result["latest_revenue_growth"], float)


@pytest.mark.parametrize("invalid", [Decimal("NaN"), Decimal("Infinity")])
def test_fundamentals_reject_non_finite_database_decimal(invalid):
    row = finance_row("A", "2024-12-31", "2025-03-01", revenue_growth=invalid)
    with pytest.raises(ValueError, match=r"A.*revenue_growth"):
        compute_fundamental_features(pd.DataFrame([row]), trade_date="2025-04-30")


def test_fundamentals_reject_fraction_despite_real_number_protocol():
    row = finance_row(
        "A", "2024-12-31", "2025-03-01", revenue_growth=Fraction(1, 3)
    )
    with pytest.raises(ValueError, match=r"A.*revenue_growth"):
        compute_fundamental_features(pd.DataFrame([row]), trade_date="2025-04-30")


def test_valuation_selects_pe_for_positive_profit_and_uses_exact_scenarios():
    history = monthly_history("A", "pe_ttm", [10.0] * 24)
    result = compute_valuation_features(
        pd.DataFrame([current_row("A")]),
        pd.DataFrame(history),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]

    assert result["valuation_method"] == "pe_normalized_profit"
    assert result["reference_multiple"] == 10.0
    assert result["valid_history_observations"] == 24
    assert result["valuation_percentile_source"] == "self_history"
    assert result["industry_history_months"] == 0
    assert not result["valuation_self_history_insufficient"]
    assert result["valuation_percentile_coverage"]
    assert result["pessimistic_market_cap"] == pytest.approx(40.0)
    assert result["base_market_cap"] == pytest.approx(106.5 * 0.0825 * 8.5)
    assert result["optimistic_market_cap"] == pytest.approx(108.0 * 0.09 * 10.0)
    assert result["base_upside"] == pytest.approx(106.5 * 0.0825 * 8.5 / 100.0 - 1.0)


def test_valuation_accepts_finite_database_decimal_current_and_history():
    current = current_row("A", current_market_cap=Decimal("100.0"), pe_ttm=Decimal("10.0"))
    history = monthly_history("A", "pe_ttm", [Decimal("10.0")] * 24)
    result = compute_valuation_features(
        pd.DataFrame([current]),
        pd.DataFrame(history),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]
    assert result["current_multiple"] == 10.0
    assert result["reference_multiple"] == 10.0
    assert isinstance(result["current_multiple"], float)
    assert isinstance(result["reference_multiple"], float)


def test_valuation_negative_pe_falls_through_to_ps_and_positive_ebitda_precedes_ps():
    ps = compute_valuation_features(
        pd.DataFrame([current_row("A", pe_ttm=-2.0, np_parent_ttm=-1.0, ebitda_ttm=-1.0)]),
        pd.DataFrame(monthly_history("A", "ps_ttm", [1.0] * 24)),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]
    assert ps["valuation_method"] == "ps_normalized_margin"
    assert ps["current_multiple"] == 1.0

    ev = compute_valuation_features(
        pd.DataFrame([current_row("A", pe_ttm=-2.0, np_parent_ttm=-1.0)]),
        pd.DataFrame(monthly_history("A", "ev_ebitda", [8.0] * 24)),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]
    assert ev["valuation_method"] == "ev_ebitda"
    assert ev["base_market_cap"] == pytest.approx(15.0 * 1.065 * 6.8 - 5.0)


def test_valuation_rejects_fundamentals_announced_after_as_of_date():
    with pytest.raises(ValueError, match=r"A.*latest_announcement_date.*as_of_date"):
        compute_valuation_features(
            pd.DataFrame([current_row("A", as_of_date="2025-03-01")]),
            pd.DataFrame(monthly_history("A", "pe_ttm", [10.0] * 24)),
            pd.DataFrame(
                [fundamental_row("A", latest_announcement_date=pd.Timestamp("2025-03-02"))]
            ),
        )


def test_valuation_short_company_history_rejects_stale_peer_history():
    history = monthly_history("A", "pe_ttm", [4.0] * 23)
    for peer in ("B", "C", "D"):
        history += monthly_history(peer, "pe_ttm", [8.0] * 24)
    history.append(
        {
            "asset_id": "A",
            "valuation_date": "2025-05-31",
            "consumer_subindustry": "food",
            "pe_ttm": 1000.0,
            "ps_ttm": np.nan,
            "ev_ebitda": np.nan,
        }
    )
    result = compute_valuation_features(
        pd.DataFrame([current_row("A")]),
        pd.DataFrame(history),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]

    assert result["valuation_self_history_insufficient"]
    assert result["valid_history_observations"] == 23
    assert math.isnan(result["reference_multiple"])
    assert result["industry_peer_assets"] == 0
    assert result["industry_history_months"] == 0
    assert not result["valuation_percentile_coverage"]
    assert math.isnan(result["valuation_percentile"])
    assert result["valuation_percentile_source"] == "unavailable"
    assert result["valuation_method"] == "unavailable"


def test_valuation_short_history_requires_three_distinct_industry_peers():
    history = monthly_history("A", "pe_ttm", [4.0] * 23)
    for peer in ("B", "C"):
        history += monthly_history(peer, "pe_ttm", [8.0] * 24, start="2023-05-31")
    result = compute_valuation_features(
        pd.DataFrame([current_row("A")]),
        pd.DataFrame(history),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]
    assert result["valuation_method"] == "unavailable"
    assert result["industry_peer_assets"] == 2
    assert math.isnan(result["reference_multiple"])


def test_valuation_counts_distinct_months_not_duplicate_rows():
    history = monthly_history("A", "pe_ttm", [4.0] * 23)
    history.append({**history[-1], "valuation_date": pd.Timestamp("2024-11-15"), "pe_ttm": 5.0})
    history += monthly_history("B", "pe_ttm", [8.0] * 24)
    result = compute_valuation_features(
        pd.DataFrame([current_row("A")]),
        pd.DataFrame(history),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]
    assert result["valid_history_observations"] == 23
    assert result["valuation_self_history_insufficient"]


def test_valuation_rejects_duplicate_asset_and_normalized_date_before_monthly_sampling():
    history = monthly_history("A", "pe_ttm", [10.0] * 24)
    history.append({**history[0], "valuation_date": "2023-01-31 18:30:00"})
    with pytest.raises(ValueError, match=r"A.*2023-01-31"):
        compute_valuation_features(
            pd.DataFrame([current_row("A")]),
            pd.DataFrame(history),
            pd.DataFrame([fundamental_row("A")]),
        )


def test_retail_unstable_earnings_use_ps_instead_of_mechanical_pe():
    result = compute_valuation_features(
        pd.DataFrame(
            [
                current_row(
                    "A",
                    consumer_subindustry="retail_duty_free",
                    ebitda_ttm=-1.0,
                )
            ]
        ),
        pd.DataFrame(
            monthly_history(
                "A", "ps_ttm", [1.0] * 24, subindustry="retail_duty_free"
            )
        ),
        pd.DataFrame([fundamental_row("A", stable_positive_earnings=False)]),
    ).iloc[0]
    assert result["valuation_method"] == "ps_normalized_margin"


def test_retail_prefers_ev_even_with_stable_positive_earnings():
    result = compute_valuation_features(
        pd.DataFrame([current_row("A", consumer_subindustry="tourism_hospitality")]),
        pd.DataFrame(
            monthly_history(
                "A", "ev_ebitda", [8.0] * 24, subindustry="tourism_hospitality"
            )
        ),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]
    assert result["valuation_method"] == "ev_ebitda"


def test_tourism_falls_through_from_ev_without_reference_to_ps():
    result = compute_valuation_features(
        pd.DataFrame([current_row("A", consumer_subindustry="tourism_hospitality")]),
        pd.DataFrame(
            monthly_history(
                "A", "ps_ttm", [1.0] * 24, subindustry="tourism_hospitality"
            )
        ),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]
    assert result["valuation_method"] == "ps_normalized_margin"
    assert result["reference_multiple"] == 1.0


def test_general_consumer_falls_through_from_pe_without_reference_to_ev():
    result = compute_valuation_features(
        pd.DataFrame([current_row("A")]),
        pd.DataFrame(monthly_history("A", "ev_ebitda", [8.0] * 24)),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]
    assert result["valuation_method"] == "ev_ebitda"
    assert result["reference_multiple"] == 8.0


def test_general_consumer_falls_through_from_short_pe_history_to_complete_ps():
    history = monthly_history("A", "ps_ttm", [1.0] * 24)
    for row in history[:15]:
        row["pe_ttm"] = 10.0
    result = compute_valuation_features(
        pd.DataFrame([current_row("A")]),
        pd.DataFrame(history),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]
    assert result["valuation_method"] == "ps_normalized_margin"
    assert result["valid_history_observations"] == 24
    assert result["valuation_percentile_coverage"]


def test_valuation_falls_from_one_month_pe_to_twenty_month_industry_ps_atomically():
    history = monthly_history("A", "ps_ttm", [1.0] * 20, start="2023-08-31")
    history[0]["pe_ttm"] = 10.0
    for peer, value in (("B", 2.0), ("C", 3.0), ("D", 4.0)):
        peer_history = monthly_history(peer, "ps_ttm", [value] * 20, start="2023-08-31")
        peer_history[0]["pe_ttm"] = 20.0
        history += peer_history

    result = compute_valuation_features(
        pd.DataFrame([current_row("A")]),
        pd.DataFrame(history),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]

    assert result["valuation_method"] == "ps_normalized_margin"
    assert result["current_multiple"] == 1.0
    assert result["reference_multiple"] == 3.0
    assert result["valid_history_observations"] == 20
    assert result["industry_peer_assets"] == 3
    assert result["industry_history_months"] == 20
    assert result["valuation_percentile"] == 0.0
    assert result["valuation_depression_percentile"] == 1.0
    assert result["valuation_percentile_source"] == "industry_history"
    assert result["valuation_percentile_coverage"]
    assert math.isfinite(result["base_upside"])


def test_valuation_industry_fallback_requires_eighteen_distinct_months():
    history = monthly_history("A", "ps_ttm", [1.0] * 17, start="2023-12-31")
    for peer in ("B", "C", "D"):
        history += monthly_history(peer, "ps_ttm", [2.0] * 17, start="2023-12-31")

    result = compute_valuation_features(
        pd.DataFrame([current_row("A", pe_ttm=-1.0, ebitda_ttm=-1.0)]),
        pd.DataFrame(history),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]

    assert result["valuation_method"] == "unavailable"
    assert result["valuation_percentile_source"] == "unavailable"
    assert result["industry_peer_assets"] == 0
    assert result["industry_history_months"] == 0
    assert math.isnan(result["reference_multiple"])
    assert math.isnan(result["valuation_percentile"])


def test_valuation_industry_fallback_requires_three_distinct_peers():
    history = monthly_history("A", "ps_ttm", [1.0] * 20, start="2023-09-30")
    for peer in ("B", "C"):
        history += monthly_history(peer, "ps_ttm", [2.0] * 20, start="2023-09-30")

    result = compute_valuation_features(
        pd.DataFrame([current_row("A", pe_ttm=-1.0, ebitda_ttm=-1.0)]),
        pd.DataFrame(history),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]

    assert result["valuation_method"] == "unavailable"
    assert result["industry_peer_assets"] == 2
    assert result["industry_history_months"] == 0
    assert result["valuation_percentile_source"] == "unavailable"


def test_valuation_industry_fallback_requires_peer_history_fresh_within_one_month():
    history = monthly_history("A", "ps_ttm", [1.0] * 20, start="2023-07-31")
    for peer in ("B", "C", "D"):
        history += monthly_history(peer, "ps_ttm", [2.0] * 20, start="2023-07-31")

    result = compute_valuation_features(
        pd.DataFrame([current_row("A", pe_ttm=-1.0, ebitda_ttm=-1.0)]),
        pd.DataFrame(history),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]

    assert result["industry_peer_assets"] == 0
    assert result["industry_history_months"] == 0
    assert result["valuation_method"] == "unavailable"
    assert result["valuation_percentile_source"] == "unavailable"
    assert math.isnan(result["reference_multiple"])


def test_valuation_industry_percentile_and_reference_exclude_target_asset():
    history = monthly_history("A", "ps_ttm", [1000.0] * 20, start="2023-09-30")
    for peer in ("B", "C", "D"):
        history += monthly_history(peer, "ps_ttm", [2.0] * 20, start="2023-09-30")

    result = compute_valuation_features(
        pd.DataFrame([current_row("A", pe_ttm=-1.0, ebitda_ttm=-1.0, ps_ttm=3.0)]),
        pd.DataFrame(history),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]

    assert result["reference_multiple"] == 2.0
    assert result["valuation_percentile"] == 1.0
    assert result["valuation_percentile_source"] == "industry_history"


def test_valuation_industry_panel_rejects_one_long_peer_and_two_single_point_peers():
    history = monthly_history("A", "ps_ttm", [1.0] * 10, start="2024-07-31")
    history += monthly_history("B", "ps_ttm", [2.0] * 18, start="2023-11-30")
    history += monthly_history("C", "ps_ttm", [3.0], start="2025-04-30")
    history += monthly_history("D", "ps_ttm", [4.0], start="2025-04-30")

    result = compute_valuation_features(
        pd.DataFrame([current_row("A", pe_ttm=-1.0, ebitda_ttm=-1.0)]),
        pd.DataFrame(history),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]

    assert result["valuation_method"] == "unavailable"
    assert result["industry_peer_assets"] == 1
    assert result["industry_history_months"] == 0
    assert result["valuation_percentile_source"] == "unavailable"


def test_valuation_fresh_single_points_do_not_refresh_a_stale_long_peer():
    history = monthly_history("A", "ps_ttm", [1.0] * 10, start="2024-07-31")
    history += monthly_history("B", "ps_ttm", [2.0] * 18, start="2023-09-30")
    history += monthly_history("C", "ps_ttm", [3.0], start="2025-04-30")
    history += monthly_history("D", "ps_ttm", [4.0], start="2025-04-30")

    result = compute_valuation_features(
        pd.DataFrame([current_row("A", pe_ttm=-1.0, ebitda_ttm=-1.0)]),
        pd.DataFrame(history),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]

    assert result["valuation_method"] == "unavailable"
    assert result["industry_peer_assets"] == 0
    assert result["industry_history_months"] == 0


def test_valuation_industry_panel_equal_weights_months_not_peer_record_density():
    history = monthly_history("A", "ps_ttm", [1.0] * 10, start="2024-07-31")
    history += monthly_history("B", "ps_ttm", [100.0] * 20, start="2023-08-31")
    history += monthly_history("C", "ps_ttm", [1.0] * 18, start="2023-10-31")
    history += monthly_history("D", "ps_ttm", [1.0] * 18, start="2023-10-31")
    history += monthly_history("E", "ps_ttm", [100.0] * 18, start="2023-10-31")

    result = compute_valuation_features(
        pd.DataFrame(
            [current_row("A", pe_ttm=-1.0, ebitda_ttm=-1.0, ps_ttm=50.0)]
        ),
        pd.DataFrame(history),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]

    assert result["valuation_method"] == "ps_normalized_margin"
    assert result["industry_peer_assets"] == 4
    assert result["industry_history_months"] == 18
    assert result["reference_multiple"] == 50.5
    assert result["valuation_percentile"] == 0.5


def test_valuation_industry_panel_counts_only_months_with_three_qualified_peers():
    history = monthly_history("A", "ps_ttm", [1.0] * 10, start="2024-07-31")
    history += monthly_history("B", "ps_ttm", [2.0] * 18, start="2023-11-30")
    history += monthly_history("C", "ps_ttm", [3.0] * 18, start="2023-11-30")
    history += monthly_history("D", "ps_ttm", [4.0] * 17, start="2022-01-31")
    history += monthly_history("D", "ps_ttm", [4.0], start="2025-04-30")

    result = compute_valuation_features(
        pd.DataFrame([current_row("A", pe_ttm=-1.0, ebitda_ttm=-1.0)]),
        pd.DataFrame(history),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]

    assert result["industry_peer_assets"] == 3
    assert result["industry_history_months"] == 1
    assert result["valuation_method"] == "unavailable"


def test_valuation_self_history_uses_company_reference_when_peer_panel_is_insufficient():
    history = monthly_history("A", "pe_ttm", [10.0] * 24)
    history += monthly_history("B", "pe_ttm", [2.0] * 18, start="2023-11-30")

    result = compute_valuation_features(
        pd.DataFrame([current_row("A")]),
        pd.DataFrame(history),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]

    assert result["valuation_method"] == "pe_normalized_profit"
    assert result["valuation_percentile_source"] == "self_history"
    assert result["industry_peer_assets"] == 1
    assert result["industry_history_months"] == 0
    assert result["reference_multiple"] == 10.0


def test_valuation_preferred_method_uses_fresh_industry_history_before_complete_ps():
    history = monthly_history("A", "ps_ttm", [1.0] * 24, start="2023-05-31")
    history[0]["pe_ttm"] = 10.0
    for peer in ("B", "C", "D"):
        peer_history = monthly_history(peer, "pe_ttm", [8.0] * 18, start="2023-11-30")
        history += peer_history

    result = compute_valuation_features(
        pd.DataFrame([current_row("A")]),
        pd.DataFrame(history),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]

    assert result["valuation_method"] == "pe_normalized_profit"
    assert result["valuation_percentile_source"] == "industry_history"
    assert result["industry_history_months"] == 18
    assert result["valid_history_observations"] == 1


def test_general_consumer_keeps_pe_when_pe_and_ps_histories_are_complete():
    history = monthly_history("A", "ps_ttm", [1.0] * 24)
    for row in history:
        row["pe_ttm"] = 10.0
    result = compute_valuation_features(
        pd.DataFrame([current_row("A")]),
        pd.DataFrame(history),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]
    assert result["valuation_method"] == "pe_normalized_profit"
    assert result["valid_history_observations"] == 24


def test_tourism_falls_through_from_short_ev_history_to_complete_ps():
    history = monthly_history(
        "A", "ps_ttm", [1.0] * 24, subindustry="tourism_hospitality"
    )
    for row in history[:23]:
        row["ev_ebitda"] = 8.0
    result = compute_valuation_features(
        pd.DataFrame([current_row("A", consumer_subindustry="tourism_hospitality")]),
        pd.DataFrame(history),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]
    assert result["valuation_method"] == "ps_normalized_margin"
    assert result["valid_history_observations"] == 24


def test_valuation_is_unavailable_when_all_candidate_self_histories_are_short():
    history = monthly_history("A", "ps_ttm", [1.0] * 23)
    for row in history[:20]:
        row["ev_ebitda"] = 8.0
    for row in history[:15]:
        row["pe_ttm"] = 10.0
    result = compute_valuation_features(
        pd.DataFrame([current_row("A")]),
        pd.DataFrame(history),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]
    assert result["valuation_method"] == "unavailable"
    assert not result["valuation_percentile_coverage"]
    assert math.isnan(result["valuation_percentile"])


def test_auto_oem_prefers_ps_even_with_stable_positive_earnings():
    result = compute_valuation_features(
        pd.DataFrame([current_row("A", consumer_subindustry="auto_oem")]),
        pd.DataFrame(
            monthly_history("A", "ps_ttm", [1.0] * 24, subindustry="auto_oem")
        ),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]
    assert result["valuation_method"] == "ps_normalized_margin"


def test_valuation_unavailable_when_company_and_industry_reference_are_missing():
    result = compute_valuation_features(
        pd.DataFrame([current_row("A")]),
        pd.DataFrame(monthly_history("B", "pe_ttm", [-1.0] * 24, subindustry="other")),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]
    assert result["valuation_method"] == "unavailable"
    assert math.isnan(result["reference_multiple"])
    assert math.isnan(result["base_upside"])


def test_valuation_percentile_is_high_when_current_multiple_is_expensive():
    history = monthly_history("A", "pe_ttm", list(range(1, 25)))
    result = compute_valuation_features(
        pd.DataFrame([current_row("A", pe_ttm=24.0)]),
        pd.DataFrame(history),
        pd.DataFrame([fundamental_row("A")]),
    ).iloc[0]
    assert result["valuation_percentile"] == 1.0
    assert result["valuation_depression_percentile"] == 0.0


@pytest.mark.parametrize("field,value", [("current_market_cap", 0.0), ("pe_ttm", True), ("net_debt", "5")])
def test_valuation_rejects_invalid_current_numbers(field, value):
    row = current_row("A")
    row[field] = value
    with pytest.raises(ValueError, match=r"A.*" + field):
        compute_valuation_features(
            pd.DataFrame([row]),
            pd.DataFrame(monthly_history("A", "pe_ttm", [10.0] * 24)),
            pd.DataFrame([fundamental_row("A")]),
        )


def test_valuation_rejects_duplicate_current_assets_and_invalid_history_date():
    row = current_row("A")
    history = pd.DataFrame(monthly_history("A", "pe_ttm", [10.0] * 24))
    with pytest.raises(ValueError, match="duplicate asset_id"):
        compute_valuation_features(pd.DataFrame([row, row]), history, pd.DataFrame([fundamental_row("A")]))
    history["valuation_date"] = history["valuation_date"].astype(object)
    history.loc[0, "valuation_date"] = "bad"
    with pytest.raises(ValueError, match="valuation_date"):
        compute_valuation_features(pd.DataFrame([row]), history, pd.DataFrame([fundamental_row("A")]))


def test_hard_risk_emits_all_codes_in_stable_order_and_requires_debt_for_pledge():
    fundamentals = pd.DataFrame(
        [
            fundamental_row(
                "A",
                latest_equity_parent=-1.0,
                latest_debt_ratio=0.90,
                latest_operating_cash_flow=1.0,
                prior_operating_cash_flow=2.0,
                second_prior_operating_cash_flow=3.0,
            ),
            fundamental_row("B"),
        ]
    )
    manual = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "audit_review_status": "triggered",
                "pledge_debt_review_status": "triggered",
                "permanent_impairment_status": "triggered",
            },
            {
                "asset_id": "B",
                "audit_review_status": "clear",
                "pledge_debt_review_status": "triggered",
                "permanent_impairment_status": "clear",
            },
        ]
    )
    result = compute_hard_risk_features(fundamentals, manual).set_index("asset_id")
    assert result.loc["A", "hard_risk_codes"] == (
        "audit_review_triggered|debt_pressure|negative_parent_equity|"
        "ocf_two_period_deterioration|permanent_impairment_flag|pledge_debt_combination"
    )
    assert result.loc["A", "hard_risk_triggered"]
    assert result.loc["B", "hard_risk_codes"] == ""
    assert not result.loc["B", "hard_risk_triggered"]


def test_hard_risk_missing_manual_is_unknown_not_clear():
    result = compute_hard_risk_features(pd.DataFrame([fundamental_row("A")])).iloc[0]
    assert result["hard_risk_codes"] == "hard_risk_review_unknown"
    assert result["hard_risk_review_unknown"]
    assert not result["hard_risk_triggered"]


def test_hard_risk_missing_automated_inputs_marks_review_unknown_but_keeps_triggers():
    fundamentals = pd.DataFrame(
        [fundamental_row("A", latest_equity_parent=np.nan, latest_debt_ratio=0.90)]
    )
    manual = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "audit_review_status": "clear",
                "pledge_debt_review_status": "clear",
                "permanent_impairment_status": "clear",
            }
        ]
    )
    result = compute_hard_risk_features(fundamentals, manual).iloc[0]
    assert result["automated_risk_review_unknown"]
    assert result["hard_risk_review_unknown"]
    assert result["hard_risk_triggered"]
    assert result["hard_risk_codes"] == "debt_pressure|hard_risk_review_unknown"


@pytest.mark.parametrize("missing_status", [None, np.nan, pd.NA, "", "   "])
def test_hard_risk_normalizes_partially_missing_manual_status_to_unknown(missing_status):
    fundamentals = pd.DataFrame([fundamental_row("A", latest_debt_ratio=0.90)])
    manual = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "audit_review_status": missing_status,
                "pledge_debt_review_status": "triggered",
                "permanent_impairment_status": "clear",
            }
        ]
    )

    result = compute_hard_risk_features(fundamentals, manual).iloc[0]

    assert result["hard_risk_review_unknown"]
    assert result["hard_risk_triggered"]
    assert result["hard_risk_codes"] == (
        "debt_pressure|hard_risk_review_unknown|pledge_debt_combination"
    )


def test_hard_risk_rejects_unknown_status_value_and_duplicate_manual_asset():
    fundamentals = pd.DataFrame([fundamental_row("A")])
    manual = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "audit_review_status": "maybe",
                "pledge_debt_review_status": "clear",
                "permanent_impairment_status": "clear",
            }
        ]
    )
    with pytest.raises(ValueError, match="audit_review_status"):
        compute_hard_risk_features(fundamentals, manual)
    manual.loc[0, "audit_review_status"] = "clear"
    with pytest.raises(ValueError, match="duplicate asset_id"):
        compute_hard_risk_features(fundamentals, pd.concat([manual, manual], ignore_index=True))


def test_empty_inputs_return_empty_feature_frames():
    empty_current = pd.DataFrame(columns=current_row("A").keys())
    empty_history = pd.DataFrame(columns=monthly_history("A", "pe_ttm", [1.0])[0].keys())
    empty_fundamentals = pd.DataFrame(columns=fundamental_row("A").keys())
    valuation = compute_valuation_features(empty_current, empty_history, empty_fundamentals)
    risk = compute_hard_risk_features(empty_fundamentals)
    assert valuation.empty and "asset_id" in valuation.columns
    assert risk.empty and "hard_risk_codes" in risk.columns
