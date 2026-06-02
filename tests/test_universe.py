import json
from pathlib import Path

import pandas as pd
import pytest

import stock_research.cli as cli
from stock_research.cli import build_parser
from stock_research.services import universe_service


def _assets_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600001",
                "ts_code": "600001.SH",
                "symbol": "600001",
                "name": "Main Board",
                "exchange": "SSE",
                "board": "main",
                "list_date": "2020-01-01",
                "is_beijing": False,
                "is_star": False,
                "is_chinext": False,
            },
            {
                "asset_id": "CN:SZ:300001",
                "ts_code": "300001.SZ",
                "symbol": "300001",
                "name": "Chinext",
                "exchange": "SZSE",
                "board": "chinext",
                "list_date": "2020-01-01",
                "is_beijing": False,
                "is_star": False,
                "is_chinext": True,
            },
            {
                "asset_id": "CN:SH:688001",
                "ts_code": "688001.SH",
                "symbol": "688001",
                "name": "STAR",
                "exchange": "SSE",
                "board": "star",
                "list_date": "2020-01-01",
                "is_beijing": False,
                "is_star": True,
                "is_chinext": False,
            },
            {
                "asset_id": "CN:BJ:830001",
                "ts_code": "830001.BJ",
                "symbol": "830001",
                "name": "Beijing",
                "exchange": "BSE",
                "board": "beijing",
                "list_date": "2020-01-01",
                "is_beijing": True,
                "is_star": False,
                "is_chinext": False,
            },
            {
                "asset_id": "CN:SH:600002",
                "ts_code": "600002.SH",
                "symbol": "600002",
                "name": "ST Main",
                "exchange": "SSE",
                "board": "main",
                "list_date": "2020-01-01",
                "is_beijing": False,
                "is_star": False,
                "is_chinext": False,
            },
            {
                "asset_id": "CN:SH:600003",
                "ts_code": "600003.SH",
                "symbol": "600003",
                "name": "Suspended Main",
                "exchange": "SSE",
                "board": "main",
                "list_date": "2020-01-01",
                "is_beijing": False,
                "is_star": False,
                "is_chinext": False,
            },
            {
                "asset_id": "CN:SZ:002001",
                "ts_code": "002001.SZ",
                "symbol": "002001",
                "name": "Recent IPO",
                "exchange": "SZSE",
                "board": "main",
                "list_date": "2026-04-20",
                "is_beijing": False,
                "is_star": False,
                "is_chinext": False,
            },
            {
                "asset_id": "CN:SH:600004",
                "ts_code": "600004.SH",
                "symbol": "600004",
                "name": "Low Liquidity",
                "exchange": "SSE",
                "board": "main",
                "list_date": "2020-01-01",
                "is_beijing": False,
                "is_star": False,
                "is_chinext": False,
            },
            {
                "asset_id": "CN:SH:600005",
                "ts_code": "600005.SH",
                "symbol": "600005",
                "name": "Long Suspended",
                "exchange": "SSE",
                "board": "main",
                "list_date": "2020-01-01",
                "is_beijing": False,
                "is_star": False,
                "is_chinext": False,
            },
            {
                "asset_id": "CN:SH:600006",
                "ts_code": "600006.SH",
                "symbol": "600006",
                "name": "Missing Industry",
                "exchange": "SSE",
                "board": "main",
                "list_date": "2020-01-01",
                "is_beijing": False,
                "is_star": False,
                "is_chinext": False,
            },
        ]
    )


def _statuses_frame() -> pd.DataFrame:
    rows = []
    for asset_id in [
        "CN:SH:600001",
        "CN:SZ:300001",
        "CN:SH:688001",
        "CN:BJ:830001",
        "CN:SH:600002",
        "CN:SH:600003",
        "CN:SZ:002001",
        "CN:SH:600004",
        "CN:SH:600005",
        "CN:SH:600006",
    ]:
        rows.append(
            {
                "trade_date": "2026-05-18",
                "asset_id": asset_id,
                "is_trade": True,
                "is_st": asset_id == "CN:SH:600002",
                "is_suspended": asset_id == "CN:SH:600003",
            }
        )
    return pd.DataFrame(rows)


def _liquidity_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-05-18",
                "asset_id": "CN:SH:600001",
                "avg_turnover_amount": 100_000_000.0,
                "avg_volume": 10_000_000.0,
                "suspended_days_lookback": 0,
            },
            {
                "trade_date": "2026-05-18",
                "asset_id": "CN:SZ:300001",
                "avg_turnover_amount": 90_000_000.0,
                "avg_volume": 9_000_000.0,
                "suspended_days_lookback": 0,
            },
            {
                "trade_date": "2026-05-18",
                "asset_id": "CN:SH:688001",
                "avg_turnover_amount": 90_000_000.0,
                "avg_volume": 9_000_000.0,
                "suspended_days_lookback": 0,
            },
            {
                "trade_date": "2026-05-18",
                "asset_id": "CN:BJ:830001",
                "avg_turnover_amount": 90_000_000.0,
                "avg_volume": 9_000_000.0,
                "suspended_days_lookback": 0,
            },
            {
                "trade_date": "2026-05-18",
                "asset_id": "CN:SH:600002",
                "avg_turnover_amount": 80_000_000.0,
                "avg_volume": 8_000_000.0,
                "suspended_days_lookback": 0,
            },
            {
                "trade_date": "2026-05-18",
                "asset_id": "CN:SH:600003",
                "avg_turnover_amount": 80_000_000.0,
                "avg_volume": 8_000_000.0,
                "suspended_days_lookback": 1,
            },
            {
                "trade_date": "2026-05-18",
                "asset_id": "CN:SZ:002001",
                "avg_turnover_amount": 70_000_000.0,
                "avg_volume": 7_000_000.0,
                "suspended_days_lookback": 0,
            },
            {
                "trade_date": "2026-05-18",
                "asset_id": "CN:SH:600004",
                "avg_turnover_amount": 1_000_000.0,
                "avg_volume": 100_000.0,
                "suspended_days_lookback": 0,
            },
            {
                "trade_date": "2026-05-18",
                "asset_id": "CN:SH:600005",
                "avg_turnover_amount": 70_000_000.0,
                "avg_volume": 7_000_000.0,
                "suspended_days_lookback": 8,
            },
            {
                "trade_date": "2026-05-18",
                "asset_id": "CN:SH:600006",
                "avg_turnover_amount": 70_000_000.0,
                "avg_volume": 7_000_000.0,
                "suspended_days_lookback": 0,
            },
        ]
    )


def _industries_frame() -> pd.DataFrame:
    rows = []
    for asset_id in [
        "CN:SH:600001",
        "CN:SZ:300001",
        "CN:SH:688001",
        "CN:BJ:830001",
        "CN:SH:600002",
        "CN:SH:600003",
        "CN:SZ:002001",
        "CN:SH:600004",
        "CN:SH:600005",
    ]:
        rows.append(
            {
                "trade_date": "2026-05-18",
                "asset_id": asset_id,
                "industry": "Bank",
            }
        )
    return pd.DataFrame(rows)


def _build_result(config: universe_service.UniverseConfig) -> universe_service.UniverseResult:
    return universe_service.build_universe_from_frames(
        assets=_assets_frame(),
        statuses=_statuses_frame(),
        liquidity=_liquidity_frame(),
        industries=_industries_frame(),
        config=config,
    )


def test_research_default_includes_main_board_stock():
    result = _build_result(universe_service.get_universe_preset("2026-05-18", "research_default"))
    assert "600001.SH" in result.included_codes


def test_research_default_includes_chinext_stock():
    result = _build_result(universe_service.get_universe_preset("2026-05-18", "research_default"))
    assert "300001.SZ" in result.included_codes


def test_research_default_excludes_star_stock():
    result = _build_result(universe_service.get_universe_preset("2026-05-18", "research_default"))
    member = result.member_map["688001.SH"]
    assert member.included is False
    assert "excluded_board:star" in member.exclude_reasons


def test_research_default_excludes_beijing_stock():
    result = _build_result(universe_service.get_universe_preset("2026-05-18", "research_default"))
    member = result.member_map["830001.BJ"]
    assert member.included is False
    assert "excluded_board:beijing" in member.exclude_reasons


def test_research_default_excludes_st_stock():
    result = _build_result(universe_service.get_universe_preset("2026-05-18", "research_default"))
    member = result.member_map["600002.SH"]
    assert member.included is False
    assert "st" in member.exclude_reasons


def test_research_default_excludes_suspended_stock():
    result = _build_result(universe_service.get_universe_preset("2026-05-18", "research_default"))
    member = result.member_map["600003.SH"]
    assert member.included is False
    assert "suspended" in member.exclude_reasons


def test_research_default_excludes_recent_ipo_by_listed_days():
    result = _build_result(universe_service.get_universe_preset("2026-05-18", "research_default"))
    member = result.member_map["002001.SZ"]
    assert member.included is False
    assert "listed_days_below_min:120" in member.exclude_reasons


def test_include_recent_ipo_preset_allows_recent_ipo_and_marks_reason():
    result = _build_result(universe_service.get_universe_preset("2026-05-18", "include_recent_ipo"))
    member = result.member_map["002001.SZ"]
    assert member.included is True
    assert "recent_ipo_allowed" in member.include_reasons


def test_research_default_excludes_low_liquidity_stock():
    result = _build_result(universe_service.get_universe_preset("2026-05-18", "research_default"))
    member = result.member_map["600004.SH"]
    assert member.included is False
    assert "low_turnover_amount" in member.exclude_reasons


def test_research_default_excludes_long_suspended_stock():
    result = _build_result(universe_service.get_universe_preset("2026-05-18", "research_default"))
    member = result.member_map["600005.SH"]
    assert member.included is False
    assert "long_suspended" in member.exclude_reasons


def test_watchlist_check_keeps_watchlist_rows_visible_without_hiding_risk():
    config = universe_service.get_universe_preset(
        "2026-05-18",
        "watchlist_check",
        watchlist_codes=["600002.SH", "600004.SH"],
    )
    result = _build_result(config)

    assert result.total_candidates == 2
    st_member = result.member_map["600002.SH"]
    illiquid_member = result.member_map["600004.SH"]
    assert st_member.included is False
    assert "watchlist_member" in st_member.include_reasons
    assert "st" in st_member.exclude_reasons
    assert illiquid_member.included is False
    assert "low_turnover_amount" in illiquid_member.exclude_reasons


def test_watchlist_only_without_watchlist_codes_returns_empty_result_with_warning():
    config = universe_service.get_universe_preset("2026-05-18", "watchlist_check")

    result = _build_result(config)

    assert result.total_candidates == 0
    assert result.included_count == 0
    assert result.excluded_count == 0
    assert "watchlist_only_without_watchlist_codes" in result.warnings


def test_universe_result_counts_and_summary_are_correct():
    result = _build_result(universe_service.get_universe_preset("2026-05-18", "research_default"))
    assert result.total_candidates == 10
    assert result.included_count == 3
    assert result.excluded_count == 7
    assert result.summary_by_reason["exclude"]["st"] == 1


def test_explain_stock_returns_exclude_reasons():
    service = universe_service.UniverseService(
        frame_loader=lambda config, watchlist_codes=None: universe_service.UniverseFrames(
            assets=_assets_frame(),
            statuses=_statuses_frame(),
            liquidity=_liquidity_frame(),
            industries=_industries_frame(),
            warnings=[],
        )
    )
    config = universe_service.get_universe_preset("2026-05-18", "research_default")
    member = service.explain_stock("600004.SH", "2026-05-18", config)

    assert member.stock_code == "600004.SH"
    assert member.included is False
    assert "low_turnover_amount" in member.exclude_reasons


def test_filter_dataframe_keeps_only_included_codes():
    service = universe_service.UniverseService(
        frame_loader=lambda config, watchlist_codes=None: universe_service.UniverseFrames(
            assets=_assets_frame(),
            statuses=_statuses_frame(),
            liquidity=_liquidity_frame(),
            industries=_industries_frame(),
            warnings=[],
        )
    )
    config = universe_service.get_universe_preset("2026-05-18", "research_default")
    df = pd.DataFrame(
        [
            {"stock_code": "600001.SH", "value": 1},
            {"stock_code": "600004.SH", "value": 2},
            {"stock_code": "300001.SZ", "value": 3},
        ]
    )

    filtered = service.filter_dataframe(df, config, code_col="stock_code")

    assert filtered["stock_code"].tolist() == ["600001.SH", "300001.SZ"]


def test_filter_dataframe_by_universe_supports_asset_id_column():
    result = _build_result(universe_service.get_universe_preset("2026-05-18", "research_default"))
    frame = pd.DataFrame(
        [
            {"asset_id": "CN:SH:600001", "value": 1},
            {"asset_id": "CN:SH:600004", "value": 2},
        ]
    )

    filtered = universe_service.filter_dataframe_by_universe(
        frame,
        result,
        asset_id_col="asset_id",
    )

    assert filtered["asset_id"].tolist() == ["CN:SH:600001"]


def test_filter_dataframe_by_universe_returns_copy_when_result_is_none():
    frame = pd.DataFrame([{"asset_id": "CN:SH:600001", "value": 1}])

    filtered = universe_service.filter_dataframe_by_universe(
        frame,
        None,
        asset_id_col="asset_id",
    )

    assert filtered.equals(frame)
    assert filtered is not frame


def test_filter_dataframe_by_universe_raises_on_missing_identifier_column():
    result = _build_result(universe_service.get_universe_preset("2026-05-18", "research_default"))
    frame = pd.DataFrame([{"value": 1}])

    with pytest.raises(ValueError, match="missing usable universe identifier column"):
        universe_service.filter_dataframe_by_universe(frame, result)


def test_build_universe_from_frames_warns_when_required_columns_are_missing():
    config = universe_service.get_universe_preset("2026-05-18", "research_default")
    broken_assets = _assets_frame().drop(columns=["list_date"])

    with pytest.raises(ValueError, match="missing required columns"):
        universe_service.build_universe_from_frames(
            assets=broken_assets,
            statuses=_statuses_frame(),
            liquidity=_liquidity_frame(),
            industries=_industries_frame(),
            config=config,
        )


def test_cli_accepts_build_universe_command():
    args = build_parser().parse_args(
        [
            "build-universe",
            "--date",
            "2026-05-18",
            "--preset",
            "research_default",
            "--output",
            "outputs/universe/2026-05-18",
        ]
    )

    assert args.command == "build-universe"
    assert args.date == "2026-05-18"
    assert args.preset == "research_default"


def test_cli_accepts_explain_universe_command():
    args = build_parser().parse_args(
        [
            "explain-universe",
            "--date",
            "2026-05-18",
            "--code",
            "000001.SZ",
            "--preset",
            "research_default",
        ]
    )

    assert args.command == "explain-universe"
    assert args.code == "000001.SZ"


def test_cli_accepts_check_watchlist_universe_command():
    args = build_parser().parse_args(
        [
            "check-watchlist-universe",
            "--date",
            "2026-05-18",
            "--watchlist",
            "watchlist.csv",
            "--preset",
            "watchlist_check",
            "--output",
            "outputs/universe/watchlist",
        ]
    )

    assert args.command == "check-watchlist-universe"
    assert args.watchlist == "watchlist.csv"


def test_build_universe_cli_writes_expected_outputs(monkeypatch, tmp_path, capsys):
    result = _build_result(universe_service.get_universe_preset("2026-05-18", "research_default"))
    monkeypatch.setattr(
        cli,
        "build_universe_artifacts",
        lambda **kwargs: kwargs["output_dir"],
    )
    monkeypatch.setattr(
        cli,
        "UniverseService",
        lambda: type(
            "FakeUniverseService",
            (),
            {"build_universe": lambda self, config: result},
        )(),
    )

    cli.main_for_args(
        [
            "build-universe",
            "--date",
            "2026-05-18",
            "--preset",
            "research_default",
            "--output",
            str(tmp_path),
        ]
    )

    lines = capsys.readouterr().out.splitlines()
    assert f"universe_build|output|{tmp_path}" in lines
    assert "universe_build|included|3" in lines


def test_explain_universe_cli_prints_json(monkeypatch, capsys):
    member = universe_service.UniverseMember(
        trade_date="2026-05-18",
        asset_id="CN:SH:600004",
        stock_code="600004.SH",
        stock_name="Low Liquidity",
        board="main",
        listed_days=1000,
        is_st=False,
        is_suspended=False,
        avg_turnover_amount=1_000_000.0,
        avg_volume=100_000.0,
        industry="Bank",
        included=False,
        include_reasons=[],
        exclude_reasons=["low_turnover_amount"],
    )
    monkeypatch.setattr(
        cli,
        "UniverseService",
        lambda: type(
            "FakeUniverseService",
            (),
            {"explain_stock": lambda self, stock_code, as_of_date, config: member},
        )(),
    )

    cli.main_for_args(
        [
            "explain-universe",
            "--date",
            "2026-05-18",
            "--code",
            "600004.SH",
            "--preset",
            "research_default",
        ]
    )

    parsed = json.loads(capsys.readouterr().out)
    assert parsed["stock_code"] == "600004.SH"
    assert parsed["exclude_reasons"] == ["low_turnover_amount"]
