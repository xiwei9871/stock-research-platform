from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.dragon_case_library import (
    apply_source_backfill,
    CASE_LIBRARY_COLUMNS,
    build_case_library,
    build_case_library_from_seed_and_bars,
    build_case_factor_snapshot,
    build_article_seed_suggestions,
    build_failure_event_rule_v21_curated_view,
    build_failure_event_rule_v21_transition_matrix,
    build_failure_event_rule_v2_diagnostics,
    build_failure_target_audit,
    build_factor_alignment_audit,
    build_local_candidate_source_priority,
    build_matching_summary,
    build_source_backfill_report,
    build_source_backfill_tasks,
    build_source_backfill_workpack,
    build_source_backfill_check_report,
    compare_source_backfill_curated,
    build_web_case_curated_library,
    build_web_case_factor_review,
    build_web_search_targets,
    build_web_case_source_evidence,
    expand_web_article_seeds,
    import_web_seeds,
    diagnose_case_library,
    identify_a_kill_failure,
    identify_break_limit_day,
    identify_limit_up_events,
    identify_reversal_day,
    identify_second_wave_start,
    read_case_seed,
    read_web_article_seed,
    read_web_case_seed,
    run_failure_event_rule_v2_diagnostics,
    run_dragon_case_web_verify,
    verify_web_candidates,
)


def test_case_seed_can_be_read(tmp_path):
    seed_path = tmp_path / "seed.csv"
    seed_path.write_text(
        "stock_name,ts_code,case_year,theme,case_type,role,approximate_start_date,approximate_end_date,source_title,source_url,notes\n"
        "Sample,000001.SZ,2024,AI,continuous_limit_up,theme_leader,2024-01-02,2024-01-20,manual,,note\n",
        encoding="utf-8",
    )

    seed = read_case_seed(seed_path)

    assert len(seed) == 1
    assert seed.iloc[0]["stock_name"] == "Sample"
    assert seed.iloc[0]["case_type"] == "continuous_limit_up"


def test_case_library_has_required_fields(tmp_path):
    seed = pd.DataFrame(
        [
            {
                "stock_name": "Dragon",
                "ts_code": "000001.SZ",
                "case_year": 2024,
                "theme": "AI",
                "case_type": "continuous_limit_up",
                "role": "theme_leader",
                "approximate_start_date": "2024-01-01",
                "approximate_end_date": "2024-02-28",
                "source_title": "manual",
                "source_url": "",
                "notes": "",
            }
        ]
    )

    library = build_case_library_from_seed_and_bars(seed, _sample_case_bars())

    assert set(CASE_LIBRARY_COLUMNS).issubset(library.columns)
    assert library.iloc[0]["max_limit_up_count"] >= 3


def test_limit_up_streak_detects_consecutive_limit_ups():
    events = identify_limit_up_events(_sample_case_bars())

    row = events[events["asset_id"] == "000001.SZ"].iloc[0]
    assert row["max_limit_up_count"] == 3
    assert row["streak_start_date"] == "2024-01-03"
    assert row["streak_end_date"] == "2024-01-05"


def test_break_limit_day_detects_first_non_limit_after_streak():
    bars = identify_limit_up_events(_sample_case_bars(), include_daily_flags=True)
    dragon = bars[bars["asset_id"] == "000001.SZ"]

    break_day = identify_break_limit_day(dragon, "2024-01-05")

    assert break_day == "2024-01-08"


def test_reversal_day_detects_fanbao_after_break():
    bars = identify_limit_up_events(_sample_case_bars(), include_daily_flags=True)
    dragon = bars[bars["asset_id"] == "000001.SZ"]

    reversal = identify_reversal_day(dragon, "2024-01-08")

    assert reversal == "2024-01-10"


def test_second_wave_start_detects_breakout_after_pullback():
    bars = identify_limit_up_events(_sample_case_bars(), include_daily_flags=True)
    dragon = bars[bars["asset_id"] == "000001.SZ"]

    second_wave = identify_second_wave_start(dragon, "2024-01-08")

    assert second_wave == "2024-01-15"


def test_a_kill_failure_detects_drop_after_break():
    bars = identify_limit_up_events(_sample_case_bars(), include_daily_flags=True)
    failed = bars[bars["asset_id"] == "000002.SZ"]

    a_kill = identify_a_kill_failure(failed, "2024-01-05")

    assert a_kill == "2024-01-08"


def test_diagnose_tolerates_missing_optional_diagnostics(tmp_path):
    case_path = tmp_path / "cases.csv"
    cases = build_case_library_from_seed_and_bars(_seed_frame(), _sample_case_bars())
    cases.to_csv(case_path, index=False)

    result = diagnose_case_library(
        case_path=case_path,
        bars=_sample_case_bars(),
        start_date="2024-01-01",
        end_date="2024-02-28",
        output_dir=tmp_path,
        optional_diagnostic_paths={"dragon_v1_3": tmp_path / "missing.csv"},
    )

    assert Path(result["paths"]["event_diagnostics"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()
    assert result["warnings"]


def test_markdown_report_can_be_generated(tmp_path):
    result = build_case_library(
        seed=_seed_frame(),
        bars=_sample_case_bars(),
        output_dir=tmp_path,
        start_date="2024-01-01",
        end_date="2024-02-28",
    )
    diagnosis = diagnose_case_library(
        case_path=result["paths"]["case_library"],
        bars=_sample_case_bars(),
        start_date="2024-01-01",
        end_date="2024-02-28",
        output_dir=tmp_path,
    )

    report = Path(diagnosis["paths"]["markdown_report"]).read_text(encoding="utf-8")
    assert "# Dragon Case Library v1 报告" in report
    assert "案例库" in report


def test_case_library_cli_prints_outputs(monkeypatch, capsys):
    def fake_build(**kwargs):
        return {
            "paths": {"case_library": "/tmp/dragon_case_library.csv"},
            "case_library": [1, 2, 3],
            "auto_candidates": [1, 2],
        }

    monkeypatch.setattr(cli, "run_dragon_case_library_build", fake_build)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "dragon-case-library-build",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-02-28",
            "--output-dir",
            "/tmp",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert "dragon_case_library_build|case_library|/tmp/dragon_case_library.csv" in out
    assert "dragon_case_library_build|cases|3" in out
    assert "dragon_case_library_build|auto_candidates|2" in out


def test_web_seed_can_be_read(tmp_path):
    seed_path = tmp_path / "web_seed.csv"
    seed_path.write_text(
        "stock_name,ts_code,case_year,theme,case_type,source_title,source_url,source_date,source_type,approximate_start_date,approximate_end_date,source_note\n"
        "Dragon,000001.SZ,2024,AI,break_then_reversal,headline,https://example.com,2024-01-10,news,2024-01-01,2024-02-28,note\n",
        encoding="utf-8",
    )
    seed = read_web_case_seed(seed_path)
    assert len(seed) == 1
    assert seed.iloc[0]["source_type"] == "news"


def test_web_article_seed_can_be_read(tmp_path):
    seed_path = tmp_path / "article_seed.csv"
    seed_path.write_text(
        "article_id,source_title,source_url,source_date,source_type,source_confidence,mentioned_stocks,mentioned_themes,mentioned_case_types,notes\n"
        "art_1,headline,https://example.com,2024-01-10,news,0.8,Dragon|Pump,AI|Theme,second_wave|one_day_pump,note\n",
        encoding="utf-8",
    )
    seed = read_web_article_seed(seed_path)
    assert len(seed) == 1
    assert seed.iloc[0]["article_id"] == "art_1"


def test_article_seed_expands_to_stock_level_and_dedupes(tmp_path):
    article_seed = pd.DataFrame(
        [
            {
                "article_id": "art_1",
                "source_title": "headline",
                "source_url": "https://example.com/1",
                "source_date": "2024-01-10",
                "source_type": "news",
                "source_confidence": 0.8,
                "mentioned_stocks": "Dragon|Pump|Dragon",
                "mentioned_themes": "AI|Theme",
                "mentioned_case_types": "second_wave|one_day_pump",
                "notes": "note",
            }
        ]
    )
    asset_lookup = pd.DataFrame(
        [
            {"stock_name": "Dragon", "ts_code": "000001.SZ"},
            {"stock_name": "Pump", "ts_code": "000003.SZ"},
        ]
    )
    result = expand_web_article_seeds(
        article_seed=article_seed,
        output_path=tmp_path / "web_seed.csv",
        output_dir=tmp_path,
        asset_lookup=asset_lookup,
        start_date="2024-01-01",
        end_date="2026-05-13",
    )
    seeds = result["web_seed"]
    assert len(seeds) == 2
    assert set(seeds["stock_name"]) == {"Dragon", "Pump"}
def test_unmatched_stock_goes_to_unmatched_output(tmp_path):
    article_seed = pd.DataFrame(
        [
            {
                "article_id": "art_1",
                "source_title": "headline",
                "source_url": "https://example.com/1",
                "source_date": "2024-01-10",
                "source_type": "news",
                "source_confidence": 0.8,
                "mentioned_stocks": "UnknownName",
                "mentioned_themes": "AI",
                "mentioned_case_types": "second_wave",
                "notes": "note",
            }
        ]
    )
    result = expand_web_article_seeds(
        article_seed=article_seed,
        output_path=tmp_path / "web_seed.csv",
        output_dir=tmp_path,
        asset_lookup=pd.DataFrame(columns=["stock_name", "ts_code"]),
        start_date="2024-01-01",
        end_date="2026-05-13",
    )
    unmatched = result["unmatched"]
    assert len(unmatched) == 1
    assert unmatched.iloc[0]["stock_name"] == "UnknownName"
    assert {"normalized_stock_name", "possible_matches", "unmatched_reason"}.issubset(unmatched.columns)


def test_source_confidence_mapping_and_coverage_report(tmp_path):
    article_seed = pd.DataFrame(
        [
            {
                "article_id": "art_1",
                "source_title": "headline",
                "source_url": "https://example.com/1",
                "source_date": "2024-01-10",
                "source_type": "stcn",
                "source_confidence": "",
                "mentioned_stocks": "Dragon",
                "mentioned_themes": "AI",
                "mentioned_case_types": "second_wave",
                "notes": "note",
            }
        ]
    )
    asset_lookup = pd.DataFrame([{"stock_name": "Dragon", "ts_code": "000001.SZ"}])
    result = expand_web_article_seeds(
        article_seed=article_seed,
        output_path=tmp_path / "web_seed.csv",
        output_dir=tmp_path,
        asset_lookup=asset_lookup,
        start_date="2024-01-01",
        end_date="2026-05-13",
    )
    summary = result["coverage"]
    seed = result["web_seed"]
    assert Path(result["paths"]["coverage"]).exists()
    assert float(seed.iloc[0]["source_confidence"]) > 0.0
    assert {"year", "source_type", "article_count", "stock_seed_count"}.issubset(summary.columns)


def test_stock_name_normalization_matches_st_prefix_and_spaces(tmp_path):
    article_seed = pd.DataFrame(
        [
            {
                "article_id": "art_1",
                "source_title": "headline",
                "source_url": "https://example.com/1",
                "source_date": "2024-01-10",
                "source_type": "news",
                "source_confidence": 0.8,
                "mentioned_stocks": "*ST 信通",
                "mentioned_themes": "重组",
                "mentioned_case_types": "weak_to_strong",
                "notes": "note",
            }
        ]
    )
    asset_lookup = pd.DataFrame([{"stock_name": "*ST信通", "ts_code": "600289.SH"}])
    result = expand_web_article_seeds(
        article_seed=article_seed,
        output_path=tmp_path / "web_seed.csv",
        output_dir=tmp_path,
        asset_lookup=asset_lookup,
        start_date="2024-01-01",
        end_date="2026-05-13",
    )
    assert result["web_seed"].iloc[0]["ts_code"] == "600289.SH"


def test_web_candidates_can_be_generated(tmp_path):
    seed_path = tmp_path / "web_seed.csv"
    seed_path.write_text(
        "stock_name,ts_code,case_year,theme,case_type,source_title,source_url,source_date,source_type,approximate_start_date,approximate_end_date,source_note\n"
        "Dragon,000001.SZ,2024,AI,break_then_reversal,headline,https://example.com,2024-01-10,news,2024-01-01,2024-02-28,note\n",
        encoding="utf-8",
    )
    result = import_web_seeds(seed_path, tmp_path)
    candidates = result["web_candidates"]
    assert len(candidates) == 1
    assert "web_candidate_id" in candidates.columns
    assert Path(result["paths"]["web_candidates"]).exists()


def test_local_market_verifies_claimed_case_type():
    candidates = _web_candidates_frame()
    verified = verify_web_candidates(candidates, _sample_web_case_bars())
    case_types = dict(zip(verified["ts_code"], verified["verified_case_type"], strict=False))
    assert case_types["000001.SZ"] == "second_wave"
    assert case_types["000002.SZ"] == "a_kill_failure"
    assert case_types["000003.SZ"] == "one_day_pump"


def test_failed_reversal_and_failed_second_wave_can_be_identified():
    candidates = pd.DataFrame(
        [
            {
                "web_candidate_id": "web_1001",
                "stock_name": "FailRev",
                "ts_code": "000004.SZ",
                "case_year": 2024,
                "theme": "Test",
                "claimed_case_type": "failed_reversal",
                "source_title": "rev",
                "source_url": "https://example.com/rev",
                "source_date": "2024-01-10",
                "source_type": "news",
                "source_confidence": 0.8,
                "approximate_start_date": "2024-01-01",
                "approximate_end_date": "2024-02-28",
                "imported_at": "2026-05-14T00:00:00",
            },
            {
                "web_candidate_id": "web_1002",
                "stock_name": "FailWave",
                "ts_code": "000005.SZ",
                "case_year": 2024,
                "theme": "Test",
                "claimed_case_type": "failed_second_wave",
                "source_title": "wave",
                "source_url": "https://example.com/wave",
                "source_date": "2024-01-10",
                "source_type": "news",
                "source_confidence": 0.8,
                "approximate_start_date": "2024-01-01",
                "approximate_end_date": "2024-02-28",
                "imported_at": "2026-05-14T00:00:00",
            },
        ]
    )
    verified = verify_web_candidates(candidates, _sample_failure_type_bars())
    case_types = dict(zip(verified["ts_code"], verified["verified_case_type"], strict=False))
    assert case_types["000004.SZ"] == "failed_reversal"
    assert case_types["000005.SZ"] == "failed_second_wave"


def test_case_confidence_and_curated_filter_work():
    candidates = _web_candidates_frame()
    verified = verify_web_candidates(candidates, _sample_web_case_bars())
    factor_review = build_web_case_factor_review(verified, _sample_web_case_bars(), diagnostics_map={})
    curated = build_web_case_curated_library(verified, factor_review)
    assert "case_confidence_score" in curated.columns
    assert (curated["event_verified"] == True).all()
    assert not (curated["verification_score"] < 0.55).any()


def test_source_evidence_table_can_be_generated():
    candidates = _web_candidates_frame()
    verified = verify_web_candidates(candidates, _sample_web_case_bars())
    evidence = build_web_case_source_evidence(verified)
    assert {"case_id", "web_candidate_id", "source_title", "evidence_score"}.issubset(evidence.columns)
    assert len(evidence) == len(verified)


def test_missing_dragon_diagnostics_do_not_crash_web_factor_review(tmp_path):
    candidates = _web_candidates_frame()
    verified = verify_web_candidates(candidates, _sample_web_case_bars())
    review = build_web_case_factor_review(
        verified,
        _sample_web_case_bars(),
        diagnostics_map={},
    )
    assert len(review) > 0


def test_web_verify_outputs_and_report_can_be_generated(tmp_path, monkeypatch):
    seed_path = tmp_path / "web_seed.csv"
    seed_path.write_text(
        "stock_name,ts_code,case_year,theme,case_type,source_title,source_url,source_date,source_type,approximate_start_date,approximate_end_date,source_note\n"
        "Dragon,000001.SZ,2024,AI,second_wave,headline,https://example.com,2024-01-10,news,2024-01-01,2024-02-28,note\n",
        encoding="utf-8",
    )
    imported = import_web_seeds(seed_path, tmp_path)
    monkeypatch.setattr(
        "stock_research.dragon_case_library.load_case_library_bars_for_ts_codes",
        lambda **kwargs: _sample_web_case_bars(),
    )
    result = run_dragon_case_web_verify(
        candidate_path=imported["paths"]["web_candidates"],
        start_date="2024-01-01",
        end_date="2024-02-28",
        output_dir=tmp_path,
    )
    assert Path(result["paths"]["event_verification"]).exists()
    assert Path(result["paths"]["factor_review"]).exists()
    assert Path(result["paths"]["curated_library"]).exists()
    assert Path(result["paths"]["source_evidence"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()
    report = Path(result["paths"]["markdown_report"]).read_text(encoding="utf-8")
    assert "Seed 扩充结果" in report
    assert "Factor Alignment Audit" in report
    assert "A Kill Rule Audit" in report
    assert "为什么匹配这么少" in report
    assert "Case Factor Snapshot" in report
    assert "Web Search Targets" in report


def test_matching_summary_distinguishes_three_match_stages():
    seed = pd.DataFrame([{"stock_name": "Dragon", "ts_code": "000001.SZ"}])
    verified = pd.DataFrame([{"web_candidate_id": "web_0001", "event_verified": True}])
    alignment = pd.DataFrame(
        [
            {
                "relative_day": 0,
                "has_dragon_v1_2": True,
                "has_dragon_v1_3": False,
                "has_industry_focus": False,
                "has_market_regime": False,
                "final_missing_reason": "",
            },
            {
                "relative_day": 0,
                "has_dragon_v1_2": False,
                "has_dragon_v1_3": False,
                "has_industry_focus": False,
                "has_market_regime": False,
                "final_missing_reason": "outside_diagnostics_date_range",
            },
        ]
    )
    summary = build_matching_summary(seed=seed, verified=verified, alignment_audit=alignment)

    assert set(summary["match_stage"]) == {
        "stock_name_to_ts_code",
        "web_candidate_to_local_event_verification",
        "case_event_to_diagnostics",
    }
    diag_row = summary.loc[summary["match_stage"] == "case_event_to_diagnostics"].iloc[0]
    assert diag_row["matched_count"] == 1
    assert diag_row["total_count"] == 2


def test_factor_alignment_audit_identifies_range_universe_and_nearby_match():
    verified = pd.DataFrame([{"web_candidate_id": "web_0001", "ts_code": "000001.SZ", "stock_name": "Dragon"}])
    factor_review = pd.DataFrame(
        [
            {
                "web_candidate_id": "web_0001",
                "ts_code": "000001.SZ",
                "stock_name": "Dragon",
                "event_type": "second_wave_start",
                "event_date": "2024-01-06",
                "relative_day": 0,
                "trade_date": "2024-01-08",
                "dragon_status_score": None,
                "dragon_entry_score": None,
                "dragon_risk_score": None,
                "industry_focus_score_v2": None,
                "market_regime": None,
            },
            {
                "web_candidate_id": "web_0002",
                "ts_code": "000999.SZ",
                "stock_name": "Missing",
                "event_type": "peak",
                "event_date": "2024-06-10",
                "relative_day": 0,
                "trade_date": "2024-06-10",
                "dragon_status_score": None,
                "dragon_entry_score": None,
                "dragon_risk_score": None,
                "industry_focus_score_v2": None,
                "market_regime": None,
            },
        ]
    )
    diagnostics_map = {
        "dragon_v1_2": pd.DataFrame(
            [
                {"trade_date": "2024-01-08", "asset_id": "000001.SZ", "dragon_status_score": 0.5},
                {"trade_date": "2024-06-11", "asset_id": "000999.SZ", "dragon_status_score": 0.6},
            ]
        ),
        "market_regime": pd.DataFrame([{"trade_date": "2024-06-12", "market_regime": "risk_on"}]),
    }
    audit = build_factor_alignment_audit(verified, factor_review, diagnostics_map)

    assert {"within_3_trade_days_match", "final_alignment_status", "final_missing_reason"}.issubset(audit.columns)
    first = audit.loc[audit["web_candidate_id"] == "web_0001"].iloc[0]
    assert bool(first["event_date_non_trading_day"]) is True
    assert bool(first["exact_date_match"]) is True
    second = audit.loc[audit["web_candidate_id"] == "web_0002"].iloc[0]
    assert bool(second["within_3_trade_days_match"]) is True
    assert second["final_missing_reason"] == "date_not_in_diagnostics"


def test_case_factor_snapshot_can_be_generated_without_dragon_diagnostics():
    verified = verify_web_candidates(_web_candidates_frame().head(1), _sample_web_case_bars())
    factor_review = build_web_case_factor_review(verified, _sample_web_case_bars(), diagnostics_map={})
    curated = build_web_case_curated_library(verified, factor_review)
    snapshot = build_case_factor_snapshot(curated, _sample_web_case_bars())

    assert len(snapshot) > 0
    assert {"future_5d_return", "pre_5d_return", "amount_vs_20d"}.issubset(snapshot.columns)
    assert "dragon_status_score" not in snapshot.columns


def test_web_search_targets_can_be_generated_from_auto_candidates():
    auto_candidates = pd.DataFrame(
        [
            {
                "case_id": "auto_1",
                "ts_code": "000001.SZ",
                "stock_name": "Dragon",
                "case_year": 2024,
                "case_type": "second_wave",
                "start_date": "2024-01-01",
                "peak_date": "2024-01-15",
                "stage_return": 1.2,
                "max_drawdown": -0.18,
                "max_limit_up_count": 3,
            },
            {
                "case_id": "auto_2",
                "ts_code": "000002.SZ",
                "stock_name": "Failed",
                "case_year": 2025,
                "case_type": "a_kill_failure",
                "start_date": "2025-03-01",
                "peak_date": "2025-03-10",
                "stage_return": 0.5,
                "max_drawdown": -0.42,
                "max_limit_up_count": 2,
            },
        ]
    )
    targets = build_web_search_targets(auto_candidates)

    assert len(targets) == 2
    assert "suggested_search_query" in targets.columns
    assert "2024 Dragon second_wave".split()[0] not in ""
    assert targets.iloc[0]["suggested_search_query"]


def test_curated_library_can_distinguish_web_and_local_origins():
    verified = verify_web_candidates(_web_candidates_frame().head(1), _sample_web_case_bars())
    factor_review = build_web_case_factor_review(verified, _sample_web_case_bars(), diagnostics_map={})
    local_auto_candidates = pd.DataFrame(
        [
            {
                "case_id": "auto_1",
                "ts_code": "000099.SZ",
                "stock_name": "Local",
                "case_year": 2025,
                "theme": "LocalTheme",
                "case_type": "second_wave",
                "stage_return": 0.8,
                "max_drawdown": -0.2,
                "max_limit_up_count": 2,
                "first_limit_up_date": "2025-01-02",
                "peak_date": "2025-01-10",
            }
        ]
    )
    curated = build_web_case_curated_library(verified, factor_review, local_auto_candidates=local_auto_candidates)

    assert {"source_origin", "web_source_available", "local_event_verified", "needs_web_source", "suggested_search_query"}.issubset(curated.columns)
    assert set(curated["source_origin"]) == {"web_seed_verified", "local_auto_candidate"}


def test_failure_target_audit_covers_failure_types():
    curated = pd.DataFrame(
        [
            {"case_id": "c1", "ts_code": "000001.SZ", "stock_name": "AKill", "case_year": 2024, "source_origin": "local_auto_candidate"},
            {"case_id": "c2", "ts_code": "000002.SZ", "stock_name": "FRev", "case_year": 2024, "source_origin": "local_auto_candidate"},
            {"case_id": "c3", "ts_code": "000003.SZ", "stock_name": "FWave", "case_year": 2025, "source_origin": "local_auto_candidate"},
            {"case_id": "c4", "ts_code": "000004.SZ", "stock_name": "Pump", "case_year": 2025, "source_origin": "local_auto_candidate"},
            {"case_id": "c5", "ts_code": "000005.SZ", "stock_name": "HOCL", "case_year": 2026, "source_origin": "local_auto_candidate"},
        ]
    )
    snapshot = pd.DataFrame(
        [
            {"case_id": "c1", "ts_code": "000001.SZ", "stock_name": "AKill", "event_type": "break_limit", "event_date": "2024-01-10", "relative_day": 0, "trade_date": "2024-01-10", "stage_return": 0.8, "max_drawdown": -0.25, "pre_5d_return": 0.22, "future_3d_return": -0.07, "future_5d_return": -0.12, "future_10d_return": -0.18, "future_5d_max_drawdown": -0.14, "future_10d_max_drawdown": -0.2, "amount_vs_20d": 1.8, "high_to_close_drawdown": -0.03, "close_position_in_day": 0.42, "max_limit_up_count": 3, "limit_up_count_before_event": 2},
            {"case_id": "c2", "ts_code": "000002.SZ", "stock_name": "FRev", "event_type": "reversal", "event_date": "2024-02-10", "relative_day": 0, "trade_date": "2024-02-10", "stage_return": 0.5, "max_drawdown": -0.18, "pre_5d_return": 0.15, "future_3d_return": -0.04, "future_5d_return": -0.08, "future_10d_return": -0.11, "future_5d_max_drawdown": -0.1, "future_10d_max_drawdown": -0.12, "amount_vs_20d": 1.3, "high_to_close_drawdown": -0.06, "close_position_in_day": 0.21, "max_limit_up_count": 2, "limit_up_count_before_event": 1},
            {"case_id": "c3", "ts_code": "000003.SZ", "stock_name": "FWave", "event_type": "second_wave_start", "event_date": "2025-03-10", "relative_day": 0, "trade_date": "2025-03-10", "stage_return": 0.9, "max_drawdown": -0.2, "pre_5d_return": 0.2, "future_3d_return": -0.03, "future_5d_return": -0.07, "future_10d_return": -0.09, "future_5d_max_drawdown": -0.11, "future_10d_max_drawdown": -0.14, "amount_vs_20d": 1.4, "high_to_close_drawdown": -0.03, "close_position_in_day": 0.35, "max_limit_up_count": 2, "limit_up_count_before_event": 1},
            {"case_id": "c4", "ts_code": "000004.SZ", "stock_name": "Pump", "event_type": "first_limit_up", "event_date": "2025-04-10", "relative_day": 0, "trade_date": "2025-04-10", "stage_return": 0.18, "max_drawdown": -0.1, "pre_5d_return": 0.09, "future_3d_return": -0.06, "future_5d_return": -0.05, "future_10d_return": -0.02, "future_5d_max_drawdown": -0.08, "future_10d_max_drawdown": -0.08, "amount_vs_20d": 2.2, "high_to_close_drawdown": -0.05, "close_position_in_day": 0.28, "max_limit_up_count": 1, "limit_up_count_before_event": 0},
            {"case_id": "c5", "ts_code": "000005.SZ", "stock_name": "HOCL", "event_type": "peak", "event_date": "2026-05-10", "relative_day": 0, "trade_date": "2026-05-10", "stage_return": 0.35, "max_drawdown": -0.12, "pre_5d_return": 0.12, "future_3d_return": -0.05, "future_5d_return": -0.04, "future_10d_return": -0.06, "future_5d_max_drawdown": -0.09, "future_10d_max_drawdown": -0.12, "amount_vs_20d": 1.6, "high_to_close_drawdown": -0.09, "close_position_in_day": 0.18, "max_limit_up_count": 1, "limit_up_count_before_event": 0},
        ]
    )
    audit = build_failure_target_audit(curated, snapshot)
    got = dict(zip(audit["stock_name"], audit["suggested_case_type"], strict=False))
    assert got["AKill"] == "a_kill_failure"
    assert got["FRev"] == "failed_reversal"
    assert got["FWave"] == "failed_second_wave"
    assert got["Pump"] == "one_day_pump"
    assert got["HOCL"] == "high_open_low_close_failure"


def test_failure_event_rule_v2_refines_failure_boundaries(tmp_path):
    curated = pd.DataFrame(
        [
            {"case_id": "c1", "ts_code": "000001.SZ", "stock_name": "AKill", "case_year": 2024, "verified_case_type": "failed_second_wave", "success_or_failure": "failure"},
            {"case_id": "c2", "ts_code": "000002.SZ", "stock_name": "FRev", "case_year": 2024, "verified_case_type": "break_then_reversal", "success_or_failure": "mixed"},
            {"case_id": "c3", "ts_code": "000003.SZ", "stock_name": "Pump", "case_year": 2025, "verified_case_type": "weak_to_strong", "success_or_failure": "unknown"},
            {"case_id": "c4", "ts_code": "000004.SZ", "stock_name": "HOCL", "case_year": 2026, "verified_case_type": "second_wave", "success_or_failure": "failure"},
        ]
    )
    snapshot = pd.DataFrame(
        [
            {"case_id": "c1", "ts_code": "000001.SZ", "stock_name": "AKill", "event_type": "second_wave_start", "event_date": "2024-01-10", "relative_day": 0, "trade_date": "2024-01-10", "stage_return": 0.9, "pre_3d_return": 0.18, "pre_5d_return": 0.30, "future_1d_return": -0.05, "future_3d_return": -0.11, "future_5d_return": -0.18, "future_10d_return": -0.24, "future_5d_max_drawdown": -0.19, "future_10d_max_drawdown": -0.28, "amount_vs_20d": 2.6, "high_to_close_drawdown": -0.05, "close_position_in_day": 0.22, "is_limit_up_day": False, "is_break_limit_event": True, "is_reversal_event": False, "is_second_wave_event": True, "is_a_kill_event": False, "limit_up_count_before_event": 3, "max_limit_up_count": 3},
            {"case_id": "c2", "ts_code": "000002.SZ", "stock_name": "FRev", "event_type": "reversal", "event_date": "2024-02-10", "relative_day": 0, "trade_date": "2024-02-10", "stage_return": 0.45, "pre_3d_return": 0.08, "pre_5d_return": 0.16, "future_1d_return": -0.01, "future_3d_return": -0.05, "future_5d_return": -0.08, "future_10d_return": -0.09, "future_5d_max_drawdown": -0.10, "future_10d_max_drawdown": -0.12, "amount_vs_20d": 1.7, "high_to_close_drawdown": -0.04, "close_position_in_day": 0.30, "is_limit_up_day": True, "is_break_limit_event": False, "is_reversal_event": True, "is_second_wave_event": False, "is_a_kill_event": False, "limit_up_count_before_event": 1, "max_limit_up_count": 2},
            {"case_id": "c3", "ts_code": "000003.SZ", "stock_name": "Pump", "event_type": "first_limit_up", "event_date": "2025-03-10", "relative_day": 0, "trade_date": "2025-03-10", "stage_return": 0.16, "pre_3d_return": 0.02, "pre_5d_return": 0.05, "future_1d_return": -0.04, "future_3d_return": -0.08, "future_5d_return": -0.07, "future_10d_return": -0.04, "future_5d_max_drawdown": -0.09, "future_10d_max_drawdown": -0.10, "amount_vs_20d": 2.4, "high_to_close_drawdown": -0.03, "close_position_in_day": 0.45, "is_limit_up_day": True, "is_break_limit_event": False, "is_reversal_event": False, "is_second_wave_event": False, "is_a_kill_event": False, "limit_up_count_before_event": 0, "max_limit_up_count": 1},
            {"case_id": "c4", "ts_code": "000004.SZ", "stock_name": "HOCL", "event_type": "peak", "event_date": "2026-05-10", "relative_day": 0, "trade_date": "2026-05-10", "stage_return": 0.42, "pre_3d_return": 0.12, "pre_5d_return": 0.20, "future_1d_return": -0.03, "future_3d_return": -0.07, "future_5d_return": -0.09, "future_10d_return": -0.10, "future_5d_max_drawdown": -0.11, "future_10d_max_drawdown": -0.13, "amount_vs_20d": 2.0, "high_to_close_drawdown": -0.10, "close_position_in_day": 0.18, "is_limit_up_day": False, "is_break_limit_event": True, "is_reversal_event": False, "is_second_wave_event": False, "is_a_kill_event": False, "limit_up_count_before_event": 2, "max_limit_up_count": 2},
        ]
    )

    result = build_failure_event_rule_v2_diagnostics(curated=curated, case_factor_snapshot=snapshot, output_dir=tmp_path)
    audit = result["audit"]
    got = dict(zip(audit["stock_name"], audit["suggested_case_type_v2"], strict=False))

    assert got["AKill"] == "a_kill_failure"
    assert got["FRev"] == "failed_reversal"
    assert got["Pump"] == "one_day_pump"
    assert got["HOCL"] == "high_open_low_close_failure"
    assert audit[audit["stock_name"] == "AKill"].iloc[0]["boundary_tag"] == "a_kill_over_failed_second_wave"
    assert Path(result["paths"]["audit"]).exists()
    assert Path(result["paths"]["report"]).read_text(encoding="utf-8").startswith("# Failure Event Rule v2")


def test_failure_event_rule_v21_does_not_escalate_plain_peak_to_a_kill(tmp_path):
    curated = pd.DataFrame(
        [
            {"case_id": "c1", "ts_code": "000001.SZ", "stock_name": "PeakWave", "case_year": 2024, "verified_case_type": "second_wave", "success_or_failure": "success"},
            {"case_id": "c2", "ts_code": "000002.SZ", "stock_name": "BreakKill", "case_year": 2024, "verified_case_type": "failed_second_wave", "success_or_failure": "failure"},
        ]
    )
    snapshot = pd.DataFrame(
        [
            {"case_id": "c1", "ts_code": "000001.SZ", "stock_name": "PeakWave", "event_type": "peak", "event_date": "2024-09-06", "relative_day": 0, "trade_date": "2024-09-06", "stage_return": 2.0, "pre_3d_return": 0.25, "pre_5d_return": 0.55, "future_1d_return": -0.08, "future_3d_return": -0.17, "future_5d_return": -0.29, "future_10d_return": -0.31, "future_5d_max_drawdown": -0.29, "future_10d_max_drawdown": -0.31, "amount_vs_20d": 3.0, "high_to_close_drawdown": 0.0, "close_position_in_day": 1.0, "is_limit_up_day": False, "is_break_limit_event": False, "is_reversal_event": False, "is_second_wave_event": False, "is_a_kill_event": False, "limit_up_count_before_event": 0, "max_limit_up_count": 0},
            {"case_id": "c2", "ts_code": "000002.SZ", "stock_name": "BreakKill", "event_type": "break_limit", "event_date": "2024-09-09", "relative_day": 0, "trade_date": "2024-09-09", "stage_return": 1.1, "pre_3d_return": 0.18, "pre_5d_return": 0.32, "future_1d_return": -0.07, "future_3d_return": -0.16, "future_5d_return": -0.22, "future_10d_return": -0.24, "future_5d_max_drawdown": -0.22, "future_10d_max_drawdown": -0.29, "amount_vs_20d": 2.2, "high_to_close_drawdown": 0.09, "close_position_in_day": 0.12, "is_limit_up_day": False, "is_break_limit_event": True, "is_reversal_event": False, "is_second_wave_event": True, "is_a_kill_event": False, "limit_up_count_before_event": 2, "max_limit_up_count": 2},
        ]
    )

    result = build_failure_event_rule_v2_diagnostics(curated=curated, case_factor_snapshot=snapshot, output_dir=tmp_path)
    audit = result["audit"]
    got = dict(zip(audit["stock_name"], audit["suggested_case_type_v2"], strict=False))

    assert got["PeakWave"] == "failed_second_wave"
    assert got["BreakKill"] == "a_kill_failure"
    assert audit[audit["stock_name"] == "PeakWave"].iloc[0]["boundary_tag"] == "failed_second_wave_without_deep_a_kill"


def test_failure_event_rule_v21_curated_view_and_transition_matrix():
    curated = pd.DataFrame(
        [
            {"case_id": "c1", "ts_code": "000001.SZ", "stock_name": "A", "case_year": 2024, "verified_case_type": "a_kill_failure", "success_or_failure": "failure", "source_origin": "web_seed_verified", "web_source_available": True, "local_event_verified": True},
            {"case_id": "c2", "ts_code": "000002.SZ", "stock_name": "B", "case_year": 2024, "verified_case_type": "failed_second_wave", "success_or_failure": "failure", "source_origin": "local_auto_candidate", "web_source_available": False, "local_event_verified": True},
        ]
    )
    snapshot = pd.DataFrame(
        [
            {"case_id": "c1", "event_type": "second_wave_start", "event_date": "2024-01-10", "relative_day": 0, "future_5d_return": -0.08, "future_10d_return": -0.09, "future_10d_max_drawdown": -0.12},
            {"case_id": "c2", "event_type": "break_limit", "event_date": "2024-01-15", "relative_day": 0, "future_5d_return": -0.18, "future_10d_return": -0.24, "future_10d_max_drawdown": -0.28},
        ]
    )
    audit = pd.DataFrame(
        [
            {"case_id": "c1", "event_type": "second_wave_start", "event_date": "2024-01-10", "suggested_case_type_v2": "failed_second_wave", "rule_reason": "r1", "rule_confidence": 0.78, "post_5d_return": -0.08, "post_10d_return": -0.09, "post_10d_max_drawdown": -0.12},
            {"case_id": "c2", "event_type": "break_limit", "event_date": "2024-01-15", "suggested_case_type_v2": "a_kill_failure", "rule_reason": "r2", "rule_confidence": 0.90, "post_5d_return": -0.18, "post_10d_return": -0.24, "post_10d_max_drawdown": -0.28},
        ]
    )

    view = build_failure_event_rule_v21_curated_view(curated=curated, case_factor_snapshot=snapshot, failure_rule_audit=audit)
    transitions = build_failure_event_rule_v21_transition_matrix(view)

    got = dict(zip(view["stock_name"], view["verified_case_type_v2_1"], strict=False))
    assert got["A"] == "failed_second_wave"
    assert got["B"] == "a_kill_failure"
    assert "label_change_reason" in view.columns
    assert set(transitions["old_verified_case_type"]) == {"a_kill_failure", "failed_second_wave"}
    assert "avg_future_10d_max_drawdown" in transitions.columns


def test_failure_event_rule_v2_cli(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_failure_event_rule_v2_diagnostics",
        lambda **kwargs: {
            "paths": {
                "audit": "/tmp/audit.csv",
                "summary": "/tmp/summary.csv",
                "report": "/tmp/report.md",
            },
            "audit": pd.DataFrame([1]),
            "summary": pd.DataFrame([1]),
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "dragon-case-failure-event-rules-v2",
            "--case-path",
            "/tmp/curated.csv",
            "--snapshot-path",
            "/tmp/snapshot.csv",
            "--output-dir",
            "/tmp",
        ],
    )
    cli.main()
    out = capsys.readouterr().out
    assert "failure_event_rule_v2|audit|/tmp/audit.csv" in out
    assert "failure_event_rule_v2|report|/tmp/report.md" in out


def test_failure_score_can_sort_priorities():
    curated = pd.DataFrame([{"case_id": "c1", "ts_code": "000001.SZ", "stock_name": "A", "case_year": 2024}])
    snapshot = pd.DataFrame(
        [
            {"case_id": "c1", "ts_code": "000001.SZ", "stock_name": "A", "event_type": "break_limit", "event_date": "2024-01-10", "relative_day": 0, "trade_date": "2024-01-10", "stage_return": 1.0, "max_drawdown": -0.3, "pre_5d_return": 0.3, "future_3d_return": -0.08, "future_5d_return": -0.15, "future_10d_return": -0.2, "future_5d_max_drawdown": -0.15, "future_10d_max_drawdown": -0.2, "amount_vs_20d": 2.0, "high_to_close_drawdown": -0.04, "close_position_in_day": 0.2, "max_limit_up_count": 3, "limit_up_count_before_event": 2},
            {"case_id": "c1", "ts_code": "000001.SZ", "stock_name": "A", "event_type": "peak", "event_date": "2024-01-11", "relative_day": 0, "trade_date": "2024-01-11", "stage_return": 0.2, "max_drawdown": -0.05, "pre_5d_return": 0.1, "future_3d_return": -0.01, "future_5d_return": -0.02, "future_10d_return": -0.02, "future_5d_max_drawdown": -0.03, "future_10d_max_drawdown": -0.04, "amount_vs_20d": 1.1, "high_to_close_drawdown": -0.02, "close_position_in_day": 0.5, "max_limit_up_count": 1, "limit_up_count_before_event": 0},
        ]
    )
    audit = build_failure_target_audit(curated, snapshot).sort_values("failure_score", ascending=False)
    assert audit.iloc[0]["suggested_case_type"] == "a_kill_failure"


def test_local_auto_candidate_can_generate_source_priority_and_article_seed_suggestions():
    curated = pd.DataFrame(
        [
            {"case_id": "c1", "ts_code": "000001.SZ", "stock_name": "LocalA", "case_year": 2024, "verified_case_type": "continuous_limit_up", "source_origin": "local_auto_candidate", "case_confidence_score": 0.6, "needs_web_source": True, "theme": "AI"},
            {"case_id": "c2", "ts_code": "000002.SZ", "stock_name": "LocalB", "case_year": 2025, "verified_case_type": "weak_to_strong", "source_origin": "local_auto_candidate", "case_confidence_score": 0.55, "needs_web_source": True, "theme": "重组"},
        ]
    )
    failure_audit = pd.DataFrame(
        [
            {"case_id": "c1", "event_strength_score": 0.9, "failure_score": 0.8, "suggested_case_type": "failed_second_wave"},
            {"case_id": "c2", "event_strength_score": 0.5, "failure_score": 0.2, "suggested_case_type": "one_day_pump"},
        ]
    )
    priority = build_local_candidate_source_priority(curated, failure_audit)
    suggestions = build_article_seed_suggestions(priority)

    assert "source_priority_score" in priority.columns
    assert priority.iloc[0]["source_priority_score"] >= priority.iloc[1]["source_priority_score"]
    assert "article_seed_template_row" in suggestions.columns
    assert "manual_search_result" in suggestions.iloc[0]["article_seed_template_row"]


def test_web_search_targets_expand_beyond_two_success_types():
    auto_candidates = pd.DataFrame(
        [
            {"case_id": "a1", "ts_code": "000001.SZ", "stock_name": "Dragon", "case_year": 2024, "case_type": "continuous_limit_up", "start_date": "2024-01-01", "peak_date": "2024-01-15", "stage_return": 1.2, "max_drawdown": -0.18, "max_limit_up_count": 3},
            {"case_id": "a2", "ts_code": "000002.SZ", "stock_name": "Weak", "case_year": 2024, "case_type": "weak_to_strong", "start_date": "2024-02-01", "peak_date": "2024-02-10", "stage_return": 0.4, "max_drawdown": -0.1, "max_limit_up_count": 1},
        ]
    )
    curated = pd.DataFrame([{"case_id": "c1", "ts_code": "000003.SZ", "stock_name": "Rev", "case_year": 2024, "source_origin": "web_seed_verified"}])
    snapshot = pd.DataFrame(
        [
            {"case_id": "c1", "ts_code": "000003.SZ", "stock_name": "Rev", "event_type": "reversal", "event_date": "2024-03-10", "relative_day": 0, "trade_date": "2024-03-10", "stage_return": 0.5, "max_drawdown": -0.1, "pre_5d_return": 0.1, "future_3d_return": 0.04, "future_5d_return": 0.08, "future_10d_return": 0.11, "future_5d_max_drawdown": -0.02, "future_10d_max_drawdown": -0.04, "amount_vs_20d": 1.3, "high_to_close_drawdown": -0.02, "close_position_in_day": 0.7, "max_limit_up_count": 2, "limit_up_count_before_event": 1},
            {"case_id": "c1", "ts_code": "000003.SZ", "stock_name": "Rev", "event_type": "first_limit_up", "event_date": "2024-03-01", "relative_day": 0, "trade_date": "2024-03-01", "stage_return": 0.12, "max_drawdown": -0.08, "pre_5d_return": 0.08, "future_3d_return": -0.06, "future_5d_return": -0.05, "future_10d_return": -0.03, "future_5d_max_drawdown": -0.08, "future_10d_max_drawdown": -0.08, "amount_vs_20d": 2.0, "high_to_close_drawdown": -0.05, "close_position_in_day": 0.25, "max_limit_up_count": 1, "limit_up_count_before_event": 0},
        ]
    )
    failure_audit = build_failure_target_audit(curated, snapshot)
    targets = build_web_search_targets(auto_candidates, factor_snapshot=snapshot, curated=curated, failure_target_audit=failure_audit)
    types = set(targets["suggested_case_type"])
    assert "continuous_limit_up" in types
    assert "weak_to_strong" in types
    assert "break_then_reversal" in types
    assert "one_day_pump" in types


def test_source_backfill_tasks_prioritize_failed_reversal_hocl_and_2026():
    suggestions = pd.DataFrame(
        [
            {"suggestion_id": "s1", "ts_code": "000001.SZ", "stock_name": "FR", "case_year": 2024, "suggested_case_type": "failed_reversal", "suggested_source_type": "manual_search_result", "suggested_search_query": "q1", "suggested_search_query_2": "q2", "suggested_search_query_3": "q3", "reason": "r", "priority_score": 0.5, "article_seed_template_row": "row1"},
            {"suggestion_id": "s2", "ts_code": "000002.SZ", "stock_name": "HOCL", "case_year": 2025, "suggested_case_type": "high_open_low_close_failure", "suggested_source_type": "manual_search_result", "suggested_search_query": "q1", "suggested_search_query_2": "q2", "suggested_search_query_3": "q3", "reason": "r", "priority_score": 0.5, "article_seed_template_row": "row2"},
            {"suggestion_id": "s3", "ts_code": "000003.SZ", "stock_name": "2026F", "case_year": 2026, "suggested_case_type": "a_kill_failure", "suggested_source_type": "manual_search_result", "suggested_search_query": "q1", "suggested_search_query_2": "q2", "suggested_search_query_3": "q3", "reason": "r", "priority_score": 0.5, "article_seed_template_row": "row3"},
        ]
    )
    tasks = build_source_backfill_tasks(suggestions)
    ordered = tasks.sort_values("priority_score", ascending=False)["stock_name"].tolist()
    assert ordered[0] in {"FR", "HOCL", "2026F"}
    assert {"backfill_status", "article_seed_template_row", "preferred_source_type"}.issubset(tasks.columns)


def test_source_backfill_report_can_be_generated():
    tasks = pd.DataFrame(
        [
            {"task_id": "t1", "stock_name": "FR", "case_year": 2024, "suggested_case_type": "failed_reversal", "priority_score": 1.2, "backfill_status": "pending"},
            {"task_id": "t2", "stock_name": "HOCL", "case_year": 2026, "suggested_case_type": "high_open_low_close_failure", "priority_score": 1.1, "backfill_status": "pending"},
        ]
    )
    report = build_source_backfill_report(tasks)
    assert "# Dragon Case Source Backfill v1 报告" in report
    assert "failed_reversal" in report
    assert "如何人工补 URL" in report


def test_apply_source_backfill_merges_found_tasks_and_skips_others(tmp_path):
    article_seed = tmp_path / "article.csv"
    article_seed.write_text(
        "article_id,source_title,source_url,source_date,source_type,source_confidence,mentioned_stocks,mentioned_ts_codes,mentioned_themes,mentioned_case_types,notes\n"
        "art_0,old,https://example.com/old,2024-01-01,news,0.8,Dragon,000001.SZ,AI,second_wave,old note\n",
        encoding="utf-8",
    )
    tasks = pd.DataFrame(
        [
            {"task_id": "t1", "ts_code": "000002.SZ", "stock_name": "Found1", "case_year": 2024, "suggested_case_type": "failed_reversal", "priority_score": 1.0, "reason": "r", "suggested_search_query": "q1", "suggested_search_query_2": "q2", "suggested_search_query_3": "q3", "preferred_source_type": "news", "source_url": "https://example.com/1", "source_title": "headline1", "source_date": "2024-02-01", "source_type": "news", "source_confidence": 0.8, "backfill_status": "found", "reviewer_note": "ok", "article_seed_template_row": "row1"},
            {"task_id": "t2", "ts_code": "000003.SZ", "stock_name": "Pending", "case_year": 2024, "suggested_case_type": "one_day_pump", "priority_score": 0.9, "reason": "r", "suggested_search_query": "q1", "suggested_search_query_2": "q2", "suggested_search_query_3": "q3", "preferred_source_type": "news", "source_url": "", "source_title": "", "source_date": "", "source_type": "", "source_confidence": "", "backfill_status": "pending", "reviewer_note": "", "article_seed_template_row": "row2"},
            {"task_id": "t3", "ts_code": "000004.SZ", "stock_name": "Dup", "case_year": 2024, "suggested_case_type": "a_kill_failure", "priority_score": 0.8, "reason": "r", "suggested_search_query": "q1", "suggested_search_query_2": "q2", "suggested_search_query_3": "q3", "preferred_source_type": "news", "source_url": "https://example.com/old", "source_title": "old", "source_date": "2024-01-01", "source_type": "news", "source_confidence": 0.8, "backfill_status": "found", "reviewer_note": "", "article_seed_template_row": "row3"},
            {"task_id": "t4", "ts_code": "000005.SZ", "stock_name": "Bad", "case_year": 2024, "suggested_case_type": "failed_second_wave", "priority_score": 0.7, "reason": "r", "suggested_search_query": "q1", "suggested_search_query_2": "q2", "suggested_search_query_3": "q3", "preferred_source_type": "news", "source_url": "https://example.com/2", "source_title": "headline2", "source_date": "2024-02-01", "source_type": "news", "source_confidence": 1.5, "backfill_status": "found", "reviewer_note": "", "article_seed_template_row": "row4"},
        ]
    )
    tasks_path = tmp_path / "tasks.csv"
    tasks.to_csv(tasks_path, index=False)
    result = apply_source_backfill(tasks_path=tasks_path, article_seed_path=article_seed, output_dir=tmp_path, dry_run=False)
    summary = result["summary"].iloc[0]
    updated = pd.read_csv(article_seed)
    assert int(summary["found_tasks"]) == 3
    assert int(summary["valid_found_tasks"]) == 2
    assert int(summary["inserted_article_seed_rows"]) == 1
    assert int(summary["skipped_duplicate_rows"]) == 1
    assert len(updated) == 2


def test_apply_source_backfill_dry_run_does_not_modify_article_seed(tmp_path):
    article_seed = tmp_path / "article.csv"
    article_seed.write_text(
        "article_id,source_title,source_url,source_date,source_type,source_confidence,mentioned_stocks,mentioned_ts_codes,mentioned_themes,mentioned_case_types,notes\n"
        "art_0,old,https://example.com/old,2024-01-01,news,0.8,Dragon,000001.SZ,AI,second_wave,old note\n",
        encoding="utf-8",
    )
    tasks = pd.DataFrame(
        [{"task_id": "t1", "ts_code": "000002.SZ", "stock_name": "Found1", "case_year": 2024, "suggested_case_type": "failed_reversal", "priority_score": 1.0, "reason": "r", "suggested_search_query": "q1", "suggested_search_query_2": "q2", "suggested_search_query_3": "q3", "preferred_source_type": "news", "source_url": "https://example.com/1", "source_title": "headline1", "source_date": "2024-02-01", "source_type": "news", "source_confidence": 0.8, "backfill_status": "found", "reviewer_note": "", "article_seed_template_row": "row1"}]
    )
    tasks_path = tmp_path / "tasks.csv"
    tasks.to_csv(tasks_path, index=False)
    result = apply_source_backfill(tasks_path=tasks_path, article_seed_path=article_seed, output_dir=tmp_path, dry_run=True)
    updated = pd.read_csv(article_seed)
    assert len(updated) == 1
    assert int(result["summary"].iloc[0]["inserted_article_seed_rows"]) == 1


def test_compare_source_backfill_handles_missing_before_file(tmp_path):
    after = tmp_path / "after.csv"
    pd.DataFrame([{"case_id": "c1", "ts_code": "000001.SZ", "stock_name": "A", "case_year": 2024, "verified_case_type": "second_wave", "source_origin": "web_seed_verified"}]).to_csv(after, index=False)
    result = compare_source_backfill_curated(before_curated_path=tmp_path / "missing.csv", after_curated_path=after, output_dir=tmp_path)
    assert Path(result["paths"]["delta"]).exists()
    assert result["warnings"]


def test_workpack_prioritizes_failed_reversal_hocl_and_2026():
    tasks = pd.DataFrame(
        [
            {"task_id": "t1", "ts_code": "000001.SZ", "stock_name": "FR", "case_year": 2024, "suggested_case_type": "failed_reversal", "priority_score": 1.0, "reason": "r", "preferred_source_type": "financial_media", "backfill_status": "pending"},
            {"task_id": "t2", "ts_code": "000002.SZ", "stock_name": "HOCL", "case_year": 2025, "suggested_case_type": "high_open_low_close_failure", "priority_score": 0.9, "reason": "r", "preferred_source_type": "financial_media", "backfill_status": "pending"},
            {"task_id": "t3", "ts_code": "000003.SZ", "stock_name": "Y26", "case_year": 2026, "suggested_case_type": "one_day_pump", "priority_score": 0.8, "reason": "r", "preferred_source_type": "eastmoney", "backfill_status": "pending"},
            {"task_id": "t4", "ts_code": "000004.SZ", "stock_name": "AK", "case_year": 2024, "suggested_case_type": "a_kill_failure", "priority_score": 1.1, "reason": "r", "preferred_source_type": "financial_media", "backfill_status": "pending"},
        ]
    )
    result = build_source_backfill_workpack(tasks, top_n=3)
    workpack = result["workpack"]
    assert len(workpack) == 3
    assert {"recommended_source_type", "recommended_source_confidence", "confidence_note"}.issubset(workpack.columns)
    assert workpack.iloc[0]["suggested_case_type"] == "failed_reversal"


def test_workpack_markdown_and_next_commands_can_generate(tmp_path):
    tasks = pd.DataFrame(
        [
            {"task_id": "t1", "ts_code": "000001.SZ", "stock_name": "FR", "case_year": 2024, "suggested_case_type": "failed_reversal", "priority_score": 1.0, "reason": "r", "preferred_source_type": "financial_media", "backfill_status": "pending"},
        ]
    )
    result = build_source_backfill_workpack(tasks, top_n=1, output_dir=tmp_path)
    assert Path(result["paths"]["csv"]).exists()
    assert Path(result["paths"]["markdown"]).exists()
    assert Path(result["paths"]["next_commands"]).exists()
    text = Path(result["paths"]["markdown"]).read_text(encoding="utf-8")
    assert "需要人工填写的字段" in text
    sh = Path(result["paths"]["next_commands"]).read_text(encoding="utf-8")
    assert "dragon-case-apply-source-backfill" in sh
    assert "dragon-case-web-verify" in sh


def test_source_backfill_check_report_can_block_lhb():
    summary = pd.DataFrame([{"found_tasks": 5, "invalid_found_tasks": 0, "inserted_article_seed_rows": 5}])
    delta = pd.DataFrame(
        [
            {"metric": "web_seed_verified_count", "before_value": 23, "after_value": 28, "delta": 5},
            {"metric": "failed_reversal_count", "before_value": 1, "after_value": 1, "delta": 0},
            {"metric": "high_open_low_close_failure_count", "before_value": 0, "after_value": 0, "delta": 0},
            {"metric": "2026_count", "before_value": 12, "after_value": 12, "delta": 0},
        ]
    )
    curated = pd.DataFrame([{"source_origin": "web_seed_verified"}] * 28)
    report = build_source_backfill_check_report(summary, delta, curated)
    assert "继续 source backfill" in report
    assert "不进入 LHB" in report



def _seed_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "stock_name": "Dragon",
                "ts_code": "000001.SZ",
                "case_year": 2024,
                "theme": "AI",
                "case_type": "break_then_reversal",
                "role": "theme_leader",
                "approximate_start_date": "2024-01-01",
                "approximate_end_date": "2024-02-28",
                "source_title": "manual",
                "source_url": "",
                "notes": "",
            }
        ]
    )


def _sample_case_bars() -> pd.DataFrame:
    rows = []
    dragon_closes = [
        10.00,
        10.20,
        11.22,
        12.34,
        13.57,
        13.10,
        12.80,
        13.90,
        13.20,
        13.50,
        14.20,
        15.10,
        14.40,
    ]
    failed_closes = [10.0, 10.2, 11.22, 12.34, 13.57, 12.10, 10.90, 9.70, 9.20, 9.0]
    dates = pd.bdate_range("2024-01-01", periods=max(len(dragon_closes), len(failed_closes)))
    for asset_id, name, closes in [
        ("000001.SZ", "Dragon", dragon_closes),
        ("000002.SZ", "Failed", failed_closes),
    ]:
        for index, close in enumerate(closes):
            prev = closes[index - 1] if index else close
            rows.append(
                {
                    "asset_id": asset_id,
                    "ts_code": asset_id,
                    "stock_name": name,
                    "trade_date": dates[index].strftime("%Y-%m-%d"),
                    "open": prev,
                    "high": max(prev, close) * 1.03,
                    "low": min(prev, close) * 0.97,
                    "close": close,
                    "amount": 100_000_000 + index * 20_000_000,
                    "turnover_rate": 5.0 + index * 0.2,
                    "is_st": False,
                    "trade_status": "1",
                }
            )
    return pd.DataFrame(rows)


def _web_candidates_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "web_candidate_id": "web_0001",
                "stock_name": "Dragon",
                "ts_code": "000001.SZ",
                "case_year": 2024,
                "theme": "AI",
                "claimed_case_type": "second_wave",
                "source_title": "headline",
                "source_url": "https://example.com/1",
                "source_date": "2024-01-10",
                "source_type": "news",
                "source_confidence": 0.85,
                "approximate_start_date": "2024-01-01",
                "approximate_end_date": "2024-02-28",
                "imported_at": "2026-05-14T00:00:00",
            },
            {
                "web_candidate_id": "web_0002",
                "stock_name": "Failed",
                "ts_code": "000002.SZ",
                "case_year": 2024,
                "theme": "Reform",
                "claimed_case_type": "a_kill_failure",
                "source_title": "headline2",
                "source_url": "https://example.com/2",
                "source_date": "2024-01-10",
                "source_type": "news",
                "source_confidence": 0.75,
                "approximate_start_date": "2024-01-01",
                "approximate_end_date": "2024-02-28",
                "imported_at": "2026-05-14T00:00:00",
            },
            {
                "web_candidate_id": "web_0003",
                "stock_name": "Pump",
                "ts_code": "000003.SZ",
                "case_year": 2024,
                "theme": "Theme",
                "claimed_case_type": "one_day_pump",
                "source_title": "headline3",
                "source_url": "https://example.com/3",
                "source_date": "2024-01-10",
                "source_type": "eastmoney",
                "source_confidence": 0.70,
                "approximate_start_date": "2024-01-01",
                "approximate_end_date": "2024-02-28",
                "imported_at": "2026-05-14T00:00:00",
            },
        ]
    )


def _sample_web_case_bars() -> pd.DataFrame:
    rows = _sample_case_bars().to_dict("records")
    pump_closes = [10.0, 10.1, 11.11, 10.6, 10.2, 10.1, 10.0]
    dates = pd.bdate_range("2024-01-01", periods=len(pump_closes))
    for index, close in enumerate(pump_closes):
        prev = pump_closes[index - 1] if index else close
        rows.append(
            {
                "asset_id": "000003.SZ",
                "ts_code": "000003.SZ",
                "stock_name": "Pump",
                "trade_date": dates[index].strftime("%Y-%m-%d"),
                "open": prev,
                "high": max(prev, close) * 1.03,
                "low": min(prev, close) * 0.97,
                "close": close,
                "amount": 80_000_000 + index * 10_000_000,
                "turnover_rate": 4.0 + index * 0.3,
                "is_st": False,
                "trade_status": "1",
            }
        )
    return pd.DataFrame(rows)


def _sample_failure_type_bars() -> pd.DataFrame:
    rows = []
    dates = pd.bdate_range("2024-01-01", periods=12)
    fail_rev = [10.0, 11.0, 12.1, 11.2, 12.3, 11.1, 10.0, 9.6]
    fail_wave = [10.0, 10.3, 11.33, 12.46, 11.8, 11.4, 12.7, 11.5, 10.9, 10.3]
    for asset_id, name, closes in [
        ("000004.SZ", "FailRev", fail_rev),
        ("000005.SZ", "FailWave", fail_wave),
    ]:
        for index, close in enumerate(closes):
            prev = closes[index - 1] if index else close
            rows.append(
                {
                    "asset_id": asset_id,
                    "ts_code": asset_id,
                    "stock_name": name,
                    "trade_date": dates[index].strftime("%Y-%m-%d"),
                    "open": prev,
                    "high": max(prev, close) * 1.03,
                    "low": min(prev, close) * 0.97,
                    "close": close,
                    "amount": 90_000_000 + index * 15_000_000,
                    "turnover_rate": 4.0 + index * 0.2,
                    "is_st": False,
                    "trade_status": "1",
                }
            )
    return pd.DataFrame(rows)
