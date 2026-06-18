import builtins
import importlib
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from stock_research.dashboard.display_date_gate import select_display_date


def _module(trade_date, module, *, status="success", summary=None, run_id=None):
    return {
        "run_id": run_id or f"strategy-eod-{trade_date}-local",
        "trade_date": trade_date,
        "latest_trade_date": trade_date,
        "module": module,
        "status": status,
        "metadata": {"summary": summary or {}},
    }


def _valid_strategy_summary(strategy_id):
    if strategy_id == "lhb_shortline":
        return {
            "engine_version": "lhb_shortline_v1",
            "phase18c_strategy": "auction_enhanced_rerank",
            "risk_profile": "balanced",
            "top_n": 5,
            "transaction_cost_bps": 10.0,
            "adjust_type": "hfq",
            "frequency": "daily",
            "total_return": 0.1,
            "max_drawdown": -0.02,
        }
    if strategy_id == "mid_trend":
        return {
            "engine_version": "mid_trend_v1",
            "variant_name": "top5_weekly_max_2_replacements",
            "benchmark_variant": "top5_weekly_max_2_replacements",
            "top_n": 5,
            "transaction_cost_bps": 20.0,
            "adjust_type": "hfq",
            "frequency": "weekly",
            "total_return": 0.2,
            "max_drawdown": -0.1,
        }
    return {
        "engine_version": "tech_bottleneck_v1",
        "universe": "strict_153_st_only_financial_state",
        "frequency": "biweekly",
        "protection_name": "rank_exit_top10_1d",
        "top_n": 3,
        "transaction_cost_bps": 20.0,
        "adjust_type": "hfq",
        "total_return": 0.3,
        "max_drawdown": -0.1,
    }


def _ready_modules(trade_date):
    return [
        _module(trade_date, "daily_bars"),
        _module(trade_date, "technical_features"),
        _module(trade_date, "score_topn"),
        _module(trade_date, "lhb_features"),
        _module(trade_date, "review_queue_strategy_manifest"),
        _module(trade_date, "strategy_lhb_shortline", summary=_valid_strategy_summary("lhb_shortline")),
        _module(trade_date, "strategy_mid_trend", summary=_valid_strategy_summary("mid_trend")),
        _module(trade_date, "strategy_tech_bottleneck", summary=_valid_strategy_summary("tech_bottleneck")),
    ]


def test_select_display_date_keeps_prior_ready_date_before_cutoff(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.display_date_gate.load_strategy_contracts",
        lambda profile="balanced": {},
    )
    now = datetime(2026, 6, 18, 20, 10, tzinfo=ZoneInfo("Asia/Shanghai"))

    result = select_display_date(
        [*_ready_modules("2026-06-17"), *_ready_modules("2026-06-18")],
        now=now,
        latest_market_date="2026-06-18",
    )

    assert result["display_trade_date"] == "2026-06-17"
    assert result["latest_market_date"] == "2026-06-18"
    assert result["candidate_trade_date"] == "2026-06-18"
    assert result["candidate_status"] == "before_cutoff"


def test_select_display_date_has_no_display_date_before_cutoff_without_prior_ready_date(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.display_date_gate.load_strategy_contracts",
        lambda profile="balanced": {},
    )
    now = datetime(2026, 6, 18, 20, 10, tzinfo=ZoneInfo("Asia/Shanghai"))

    result = select_display_date(
        _ready_modules("2026-06-18"),
        now=now,
        latest_market_date="2026-06-18",
    )

    assert result["display_trade_date"] == ""
    assert result["candidate_status"] == "before_cutoff"


def test_select_display_date_uses_ready_stale_candidate_before_cutoff(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.display_date_gate.load_strategy_contracts",
        lambda profile="balanced": {},
    )
    now = datetime(2026, 6, 18, 20, 10, tzinfo=ZoneInfo("Asia/Shanghai"))

    result = select_display_date(
        [*_ready_modules("2026-06-16"), *_ready_modules("2026-06-17")],
        now=now,
        latest_market_date="2026-06-17",
    )

    assert result["display_trade_date"] == "2026-06-17"
    assert result["candidate_status"] == "ready"


def test_select_display_date_switches_after_cutoff_when_today_ready(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.display_date_gate.load_strategy_contracts",
        lambda profile="balanced": {},
    )
    now = datetime(2026, 6, 18, 20, 40, tzinfo=ZoneInfo("Asia/Shanghai"))

    result = select_display_date(
        [*_ready_modules("2026-06-17"), *_ready_modules("2026-06-18")],
        now=now,
        latest_market_date="2026-06-18",
    )

    assert result["display_trade_date"] == "2026-06-18"
    assert result["display_status"] == "ready"
    assert result["strategy_ready"] == "3/3"


def test_select_display_date_reports_fallback_latest_market_date(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.display_date_gate.load_strategy_contracts",
        lambda profile="balanced": {},
    )
    now = datetime(2026, 6, 18, 20, 40, tzinfo=ZoneInfo("Asia/Shanghai"))

    result = select_display_date(
        [*_ready_modules("2026-06-16"), *_ready_modules("2026-06-17")],
        now=now,
    )

    assert result["latest_market_date"] == "2026-06-17"
    assert result["candidate_trade_date"] == "2026-06-17"


def test_display_date_gate_imports_without_strategy_contracts(monkeypatch):
    import stock_research.dashboard.display_date_gate as display_date_gate

    real_import = builtins.__import__

    def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "stock_research.strategy_contracts":
            raise ModuleNotFoundError(name)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.delitem(sys.modules, "stock_research.strategy_contracts", raising=False)
    monkeypatch.setattr(builtins, "__import__", blocked_import)
    reloaded = importlib.reload(display_date_gate)

    now = datetime(2026, 6, 18, 20, 40, tzinfo=ZoneInfo("Asia/Shanghai"))
    result = reloaded.select_display_date(
        _ready_modules("2026-06-18"),
        now=now,
        latest_market_date="2026-06-18",
    )

    assert result["display_trade_date"] == "2026-06-18"
    assert result["contract_valid"] == "3/3"
    monkeypatch.setattr(builtins, "__import__", real_import)
    importlib.reload(reloaded)


def test_select_display_date_does_not_mix_modules_across_runs(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.display_date_gate.load_strategy_contracts",
        lambda profile="balanced": {},
    )
    run_a = [
        {**row, "run_id": "run-a"}
        for row in _ready_modules("2026-06-18")
        if row["module"] != "score_topn"
    ]
    run_b = [
        {**row, "run_id": "run-b"}
        for row in _ready_modules("2026-06-18")
        if row["module"] != "daily_bars"
    ]
    now = datetime(2026, 6, 18, 20, 40, tzinfo=ZoneInfo("Asia/Shanghai"))

    result = select_display_date(
        [*run_a, *run_b],
        now=now,
        latest_market_date="2026-06-18",
    )

    assert result["display_trade_date"] == ""
    assert result["display_status"] == "missing"
    assert result["candidate_status"] == "incomplete"
    assert len(result["blocking_reasons"]) == 1
    assert result["blocking_reasons"][0] in {"missing:daily_bars", "missing:score_topn"}
