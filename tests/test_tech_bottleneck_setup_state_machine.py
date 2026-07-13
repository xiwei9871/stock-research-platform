from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_setup_state_machine.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_setup_state_machine", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_allowed_states_are_research_only() -> None:
    module = _load_module()

    assert module.ALLOWED_STATES == {
        "research_candidate",
        "technical_watch",
        "compression_setup",
        "breakout_candidate",
        "failed_setup",
    }


def test_breakout_candidate_is_not_buy_signal() -> None:
    module = _load_module()
    row = pd.Series(
        {
            "price_vs_ma60": 0.08,
            "price_vs_ma20": 0.04,
            "range_contraction_20d": 0.6,
            "atr_percentile_60d": 0.3,
            "distance_to_breakout_level": 0.01,
            "close_above_breakout_20d": True,
            "relative_strength_state": "strong",
            "recent_drawdown_risk_flag": False,
            "limit_up_flag": False,
        }
    )

    state, reason = module.classify_state(row)

    assert state == "breakout_candidate"
    assert "buy" not in reason.lower()


def test_failed_setup_requires_reason() -> None:
    module = _load_module()
    row = pd.Series(
        {
            "price_vs_ma60": -0.12,
            "price_vs_ma20": -0.08,
            "range_contraction_20d": 1.2,
            "atr_percentile_60d": 0.8,
            "distance_to_breakout_level": -0.2,
            "close_above_breakout_20d": False,
            "relative_strength_state": "weak",
            "recent_drawdown_risk_flag": True,
            "limit_up_flag": False,
        }
    )

    state, reason = module.classify_state(row)

    assert state == "failed_setup"
    assert reason


def test_no_trading_language_validator_rejects_forbidden_words() -> None:
    module = _load_module()
    df = pd.DataFrame(
        {
            "recommended_action_for_reviewer": ["monitor_setup", "buy_now"],
            "current_state": ["technical_watch", "breakout_candidate"],
        }
    )

    with pytest.raises(ValueError, match="trading language"):
        module.validate_no_trading_language(df)


def test_forward_returns_are_research_only() -> None:
    module = _load_module()
    good = pd.DataFrame({"used_for_signal": [False, False]})
    module.validate_forward_returns_research_only(good)

    bad = pd.DataFrame({"used_for_signal": [False, True]})
    with pytest.raises(ValueError, match="used_for_signal"):
        module.validate_forward_returns_research_only(bad)


def test_pit_date_validation_rejects_future_price_or_technical_data() -> None:
    module = _load_module()
    good = pd.DataFrame(
        {
            "trade_date": ["2026-06-12"],
            "price_date": ["2026-06-12"],
            "technical_as_of_date": ["2026-06-11"],
        }
    )
    module.validate_pit_dates(good)

    bad = pd.DataFrame(
        {
            "trade_date": ["2026-06-12"],
            "price_date": ["2026-06-15"],
            "technical_as_of_date": ["2026-06-12"],
        }
    )
    with pytest.raises(ValueError, match="lookahead"):
        module.validate_pit_dates(bad)


def test_allowed_review_actions_are_non_trading_language() -> None:
    module = _load_module()
    lower_actions = " ".join(sorted(module.ALLOWED_REVIEW_ACTIONS)).lower()
    for word in module.FORBIDDEN_TRADING_WORDS:
        assert word not in lower_actions
