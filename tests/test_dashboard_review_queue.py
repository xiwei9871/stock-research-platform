import csv
from pathlib import Path

import pytest

from stock_research.dashboard import review_queue


STRATEGY_MODULES = {
    "strategy_lhb_shortline": ("lhb_shortline", "LHB Shortline Combo"),
    "strategy_mid_trend": ("mid_trend", "Mid Trend Combo"),
    "strategy_tech_bottleneck": ("tech_bottleneck", "Tech Bottleneck Combo"),
}


def _write_strategy_review(path: Path, *, strategy_id: str, strategy_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "trade_date",
                "asset_id",
                "rank",
                "score_total",
                "strategy_id",
                "strategy_name",
                "source_type",
                "source_name",
                "source_rank",
                "review_tier",
            ],
        )
        writer.writeheader()
        offset = {"lhb_shortline": 0, "mid_trend": 10, "tech_bottleneck": 20}[strategy_id]
        for rank in range(1, 6):
            writer.writerow(
                {
                    "trade_date": "2026-07-24",
                    "asset_id": f"CN:SH:{600000 + offset + rank:06d}",
                    "rank": rank,
                    "score_total": 90 - rank,
                    "strategy_id": strategy_id,
                    "strategy_name": strategy_name,
                    "source_type": "strategy_manifest",
                    "source_name": f"strategy_{strategy_id}",
                    "source_rank": rank,
                    "review_tier": "top5_focus",
                }
            )


def _patch_release_queue_dependencies(monkeypatch, modules):
    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda **kwargs: {"latest_market_date": "2026-07-24", "latest_score_date": "2026-07-24"},
    )
    monkeypatch.setattr(review_queue, "load_latest_data_run_manifest", lambda **kwargs: modules)
    monkeypatch.setattr(review_queue, "_attach_asset_names", lambda rows: rows)
    monkeypatch.setattr(
        review_queue,
        "_active_strategy_names",
        lambda: {strategy_id: strategy_name for strategy_id, strategy_name in STRATEGY_MODULES.values()},
    )


def _successful_modules(artifact_paths):
    modules = []
    for module, (strategy_id, _) in STRATEGY_MODULES.items():
        modules.append(
            {
                "module": module,
                "status": "success",
                "trade_date": "2026-07-24",
                "latest_trade_date": "2026-07-24",
                "run_id": "release-run",
                "artifact_path": str(artifact_paths[module]),
                "metadata": (
                    {"candidate_snapshot_latest_date": "2026-07-24"}
                    if strategy_id == "tech_bottleneck"
                    else {}
                ),
            }
        )
    return modules


def _assert_release_queue_is_5_by_3(result):
    assert result["trade_date"] == "2026-07-24"
    assert result["requested_trade_date"] == "2026-07-24"
    assert {group["strategy_id"] for group in result["groups"]} == {
        "lhb_shortline",
        "mid_trend",
        "tech_bottleneck",
    }
    assert all(group["count"] == 5 for group in result["groups"])
    assert all(group["data_trade_date"] == "2026-07-24" for group in result["groups"])
    assert all(group["freshness_status"] == "current" for group in result["groups"])


@pytest.mark.parametrize("path_style", ["old_absolute", "repo_relative", "date_relative"])
def test_review_queue_relocates_manifest_artifacts_to_explicit_release_root(
    monkeypatch, tmp_path, path_style
):
    release_root = tmp_path / "clean-release"
    strategy_root = release_root / "outputs" / "research" / "strategy_daily_eod"
    date_root = strategy_root / "2026-07-24"
    artifact_paths = {}
    for module, (strategy_id, strategy_name) in STRATEGY_MODULES.items():
        filename = f"{module}_review.csv"
        _write_strategy_review(date_root / filename, strategy_id=strategy_id, strategy_name=strategy_name)
        if path_style == "old_absolute":
            artifact_paths[module] = Path(
                f"/Users/xiwei/stock_research/outputs/research/strategy_daily_eod/2026-07-24/{filename}"
            )
        elif path_style == "repo_relative":
            artifact_paths[module] = Path(
                f"outputs/research/strategy_daily_eod/2026-07-24/{filename}"
            )
        else:
            artifact_paths[module] = Path(filename)

    _patch_release_queue_dependencies(monkeypatch, _successful_modules(artifact_paths))
    unrelated_cwd = tmp_path / "unrelated"
    unrelated_cwd.mkdir()
    monkeypatch.chdir(unrelated_cwd)

    result = review_queue.build_review_queue(
        trade_date="2026-07-24",
        strategy_output_root=strategy_root,
    )

    _assert_release_queue_is_5_by_3(result)


def test_review_queue_prefers_canonical_date_manifest_over_database_paths(monkeypatch, tmp_path):
    strategy_root = tmp_path / "release" / "outputs" / "research" / "strategy_daily_eod"
    date_root = strategy_root / "2026-07-24"
    combined = date_root / "review_queue_strategy_manifest.csv"
    for module, (strategy_id, strategy_name) in STRATEGY_MODULES.items():
        per_strategy = date_root / f"{module}_review.csv"
        _write_strategy_review(per_strategy, strategy_id=strategy_id, strategy_name=strategy_name)
    rows = []
    for path in sorted(date_root.glob("strategy_*_review.csv")):
        with path.open(encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle))
    with combined.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    outside_paths = {module: tmp_path / "outside" / f"{module}.csv" for module in STRATEGY_MODULES}
    _patch_release_queue_dependencies(monkeypatch, _successful_modules(outside_paths))
    monkeypatch.chdir(tmp_path)

    result = review_queue.build_review_queue(
        trade_date="2026-07-24",
        strategy_output_root=strategy_root,
    )

    _assert_release_queue_is_5_by_3(result)


@pytest.mark.parametrize("escape_kind", ["traversal", "symlink"])
def test_review_queue_rejects_manifest_artifacts_escaping_explicit_root(
    monkeypatch, tmp_path, escape_kind
):
    strategy_root = tmp_path / "release" / "outputs" / "research" / "strategy_daily_eod"
    date_root = strategy_root / "2026-07-24"
    outside = tmp_path / "outside.csv"
    _write_strategy_review(outside, strategy_id="lhb_shortline", strategy_name="LHB Shortline Combo")
    date_root.mkdir(parents=True)
    if escape_kind == "traversal":
        unsafe_path = "../../../../outside.csv"
    else:
        unsafe_link = date_root / "strategy_lhb_shortline_review.csv"
        unsafe_link.symlink_to(outside)
        unsafe_path = unsafe_link.name
    artifact_paths = {module: unsafe_path for module in STRATEGY_MODULES}
    _patch_release_queue_dependencies(monkeypatch, _successful_modules(artifact_paths))

    result = review_queue.build_review_queue(
        trade_date="2026-07-24",
        strategy_output_root=strategy_root,
        use_strategy_snapshots=False,
    )

    assert all(group["count"] == 0 for group in result["groups"])
    assert all(group["freshness_status"] == "missing" for group in result["groups"])


@pytest.mark.parametrize("unsafe_style", ["untrusted_absolute", "traversal_before_suffix"])
def test_review_queue_does_not_relocate_untrusted_canonical_suffix_paths(
    monkeypatch, tmp_path, unsafe_style
):
    strategy_root = tmp_path / "release" / "outputs" / "research" / "strategy_daily_eod"
    date_root = strategy_root / "2026-07-24"
    artifact_paths = {}
    for module, (strategy_id, strategy_name) in STRATEGY_MODULES.items():
        filename = f"{module}_review.csv"
        _write_strategy_review(date_root / filename, strategy_id=strategy_id, strategy_name=strategy_name)
        if unsafe_style == "untrusted_absolute":
            artifact_paths[module] = Path(
                f"/srv/untrusted-copy/outputs/research/strategy_daily_eod/2026-07-24/{filename}"
            )
        else:
            artifact_paths[module] = Path(
                f"../../external/outputs/research/strategy_daily_eod/2026-07-24/{filename}"
            )
    _patch_release_queue_dependencies(monkeypatch, _successful_modules(artifact_paths))

    result = review_queue.build_review_queue(
        trade_date="2026-07-24",
        strategy_output_root=strategy_root,
        use_strategy_snapshots=False,
    )

    assert all(group["count"] == 0 for group in result["groups"])
    assert all(group["freshness_status"] == "missing" for group in result["groups"])


def test_manifest_artifact_resolver_rejects_external_symlink_pointing_into_root(tmp_path):
    strategy_root = tmp_path / "release" / "outputs" / "research" / "strategy_daily_eod"
    artifact = strategy_root / "2026-07-24" / "strategy_lhb_shortline_review.csv"
    _write_strategy_review(artifact, strategy_id="lhb_shortline", strategy_name="LHB Shortline Combo")
    external_link = tmp_path / "external.csv"
    external_link.symlink_to(artifact)

    resolved = review_queue._resolve_manifest_artifact_path(
        external_link,
        strategy_output_root=strategy_root.resolve(),
        trade_date="2026-07-24",
    )

    assert resolved is None


def test_manifest_artifact_resolver_rejects_root_symlink_pointing_outside(tmp_path):
    strategy_root = tmp_path / "release" / "outputs" / "research" / "strategy_daily_eod"
    outside = tmp_path / "outside.csv"
    _write_strategy_review(outside, strategy_id="lhb_shortline", strategy_name="LHB Shortline Combo")
    root_link = strategy_root / "2026-07-24" / "strategy_lhb_shortline_review.csv"
    root_link.parent.mkdir(parents=True)
    root_link.symlink_to(outside)

    resolved = review_queue._resolve_manifest_artifact_path(
        root_link,
        strategy_output_root=strategy_root.resolve(),
        trade_date="2026-07-24",
    )

    assert resolved is None


def test_manifest_artifact_resolver_accepts_regular_file_inside_root(tmp_path):
    strategy_root = tmp_path / "release" / "outputs" / "research" / "strategy_daily_eod"
    artifact = strategy_root / "2026-07-24" / "strategy_lhb_shortline_review.csv"
    _write_strategy_review(artifact, strategy_id="lhb_shortline", strategy_name="LHB Shortline Combo")

    resolved = review_queue._resolve_manifest_artifact_path(
        artifact,
        strategy_output_root=strategy_root.resolve(),
        trade_date="2026-07-24",
    )

    assert resolved == artifact.resolve()


@pytest.mark.parametrize("path_style", ["embedded_prefix", "repeated_prefix", "empty_suffix"])
def test_manifest_artifact_resolver_requires_single_leading_repo_prefix(tmp_path, path_style):
    strategy_root = tmp_path / "release" / "outputs" / "research" / "strategy_daily_eod"
    if path_style == "embedded_prefix":
        raw_path = Path(
            "untrusted/outputs/research/strategy_daily_eod/2026-07-24/strategy_lhb_shortline_review.csv"
        )
        mapped = strategy_root / "2026-07-24" / "strategy_lhb_shortline_review.csv"
    elif path_style == "repeated_prefix":
        raw_path = Path(
            "outputs/research/strategy_daily_eod/outputs/research/strategy_daily_eod/"
            "2026-07-24/strategy_lhb_shortline_review.csv"
        )
        mapped = strategy_root / "outputs/research/strategy_daily_eod/2026-07-24/strategy_lhb_shortline_review.csv"
    else:
        raw_path = Path("outputs/research/strategy_daily_eod")
        mapped = None
    if mapped is not None:
        _write_strategy_review(mapped, strategy_id="lhb_shortline", strategy_name="LHB Shortline Combo")

    resolved = review_queue._resolve_manifest_artifact_path(
        raw_path,
        strategy_output_root=strategy_root.resolve(),
        trusted_release_root=(tmp_path / "release").resolve(),
        trade_date="2026-07-24",
    )

    assert resolved is None


def test_review_queue_asset_normalization_uses_shared_strict_identity():
    assert review_queue._asset_id_from_ts_code("600000.SSE") == "CN:SH:600000"
    assert review_queue._asset_id_from_ts_code("000001.SZSE") == "CN:SZ:000001"
    assert review_queue._asset_id_from_ts_code("CN:SH:") == ""
    assert review_queue._asset_id_from_ts_code("CN:XX:000001") == ""
    assert review_queue._asset_id_from_ts_code("ABC.SH") == ""


def test_review_queue_dedupes_equivalent_asset_encodings():
    rows = [
        {"asset_id": "CN:SH:600000"},
        {"asset_id": "600000.SSE"},
        {"asset_id": "600001.SH"},
    ]

    assert review_queue._dedupe_records_by_asset(rows) == [rows[0], rows[2]]


def _patch_stale_strategy_fallback(monkeypatch):
    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda **kwargs: {
            "latest_market_date": "2026-07-24",
            "latest_score_date": "2026-07-24",
            "topn_preview": [],
        },
    )
    monkeypatch.setattr(review_queue, "_load_manifest_strategy_rows", lambda **kwargs: [])
    monkeypatch.setattr(review_queue, "_load_strategy_snapshot_rows", lambda **kwargs: [])
    monkeypatch.setattr(
        review_queue,
        "load_active_strategy_topn_rows",
        lambda **kwargs: [
            {
                "trade_date": "2026-06-01",
                "asset_id": "CN:SZ:000001",
                "strategy_id": "mid_trend",
                "strategy_name": "Mid Trend Combo",
                "rank": 1,
                "score_total": 88.0,
            }
        ],
    )
    monkeypatch.setattr(
        review_queue,
        "_active_strategy_names",
        lambda: {
            "lhb_shortline": "LHB Shortline Combo",
            "mid_trend": "Mid Trend Combo",
            "tech_bottleneck": "Tech Bottleneck Combo",
        },
    )
    monkeypatch.setattr(
        review_queue,
        "load_top_scores_for_dashboard",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not fall through to score Top-N")),
    )


def _assert_strategy_queue_failed_closed(result):
    assert result["requested_trade_date"] == "2026-07-24"
    assert result["trade_date"] == "2026-07-24"
    assert result["review_mode"] == "strategy_topn"
    assert all(group["count"] == 0 for group in result["groups"])
    assert all(group["freshness_status"] == "missing" for group in result["groups"])
    assert all(group["items"] == [] for group in result["groups"])
    assert "exact-date official strategy manifest unavailable for 2026-07-24" in result["warnings"]


def test_default_strategy_review_queue_rejects_stale_fallback_rows(monkeypatch):
    _patch_stale_strategy_fallback(monkeypatch)

    result = review_queue.build_review_queue()

    _assert_strategy_queue_failed_closed(result)


def test_explicit_strategy_review_queue_rejects_stale_fallback_rows(monkeypatch):
    _patch_stale_strategy_fallback(monkeypatch)

    result = review_queue.build_review_queue(trade_date="2026-07-24")

    _assert_strategy_queue_failed_closed(result)


def test_strategy_review_queue_rejects_row_with_stale_underlying_data_date(monkeypatch):
    _patch_stale_strategy_fallback(monkeypatch)
    monkeypatch.setattr(
        review_queue,
        "load_active_strategy_topn_rows",
        lambda **kwargs: [
            {
                "trade_date": "2026-07-24",
                "latest_trade_date": "2026-06-01",
                "asset_id": "CN:SZ:000001",
                "strategy_id": "mid_trend",
                "strategy_name": "Mid Trend Combo",
                "rank": 1,
                "score_total": 88.0,
            }
        ],
    )

    result = review_queue.build_review_queue(trade_date="2026-07-24")

    _assert_strategy_queue_failed_closed(result)


def test_strategy_review_queue_preserves_requested_date_and_reports_group_data_date(monkeypatch):
    monkeypatch.setattr(
        review_queue,
        "_active_strategy_names",
        lambda: {
            "lhb_shortline": "LHB Shortline Combo",
            "mid_trend": "Mid Trend Combo",
            "tech_bottleneck": "Tech Bottleneck Combo",
        },
    )

    result = review_queue._strategy_review_queue(
        rows=[
            {
                "trade_date": "2026-06-01",
                "asset_id": "CN:SZ:000001",
                "strategy_id": "mid_trend",
                "strategy_name": "Mid Trend Combo",
                "rank": 1,
                "score_total": 88.0,
            }
        ],
        selected_trade_date="2026-07-24",
        platform_market_date="2026-07-24",
        score_version="strategy_topn",
        lookback_days=90,
    )

    assert result["requested_trade_date"] == "2026-07-24"
    assert result["trade_date"] == "2026-07-24"
    mid_trend = next(group for group in result["groups"] if group["strategy_id"] == "mid_trend")
    assert mid_trend["strategy_id"] == "mid_trend"
    assert mid_trend["requested_trade_date"] == "2026-07-24"
    assert mid_trend["data_trade_date"] == "2026-06-01"
    assert mid_trend["freshness_status"] == "stale"


def test_strategy_review_queue_marks_empty_official_groups_missing(monkeypatch):
    monkeypatch.setattr(
        review_queue,
        "_active_strategy_names",
        lambda: {
            "lhb_shortline": "LHB Shortline Combo",
            "mid_trend": "Mid Trend Combo",
            "tech_bottleneck": "Tech Bottleneck Combo",
        },
    )

    result = review_queue._strategy_review_queue(
        rows=[],
        selected_trade_date="2026-07-24",
        platform_market_date="2026-07-24",
        score_version="strategy_topn",
        lookback_days=90,
    )

    assert result["requested_trade_date"] == "2026-07-24"
    assert result["trade_date"] == "2026-07-24"
    assert all(group["freshness_status"] == "missing" for group in result["groups"])
    assert all(group["data_trade_date"] == "" for group in result["groups"])


def test_strategy_review_queue_uses_underlying_latest_trade_date_for_freshness(monkeypatch):
    monkeypatch.setattr(
        review_queue,
        "_active_strategy_names",
        lambda: {"mid_trend": "Mid Trend Combo"},
    )

    result = review_queue._strategy_review_queue(
        rows=[
            {
                "trade_date": "2026-07-24",
                "latest_trade_date": "2026-06-01",
                "asset_id": "CN:SZ:000001",
                "strategy_id": "mid_trend",
                "strategy_name": "Mid Trend Combo",
                "rank": 1,
                "score_total": 88.0,
            }
        ],
        selected_trade_date="2026-07-24",
        platform_market_date="2026-07-24",
        score_version="strategy_topn",
        lookback_days=90,
    )

    group = result["groups"][0]
    assert group["data_trade_date"] == "2026-06-01"
    assert group["freshness_status"] == "stale"


def test_review_queue_defaults_to_latest_market_date_when_display_gate_lags(monkeypatch):
    monkeypatch.setattr(review_queue, "load_recent_data_run_manifest", lambda: [{"trade_date": "2026-06-30"}])
    monkeypatch.setattr(
        review_queue,
        "select_display_date",
        lambda modules, latest_market_date: {
            "display_trade_date": "2026-06-30",
            "candidate_trade_date": latest_market_date,
            "display_status": "ready",
        },
    )

    selected = review_queue._default_display_trade_date(
        {
            "latest_market_date": "2026-07-03",
            "latest_score_date": "2026-07-03",
        }
    )

    assert selected == "2026-07-03"


def test_attach_asset_names_keeps_published_lhb_name_when_master_missing(monkeypatch):
    monkeypatch.setattr(review_queue, "_load_asset_names", lambda asset_ids: {})

    rows = review_queue._attach_asset_names(
        [{"asset_id": "CN:SZ:001399", "stock_name": "惠科股份"}]
    )

    assert rows[0]["stock_name"] == "惠科股份"


def test_strategy_lightweight_digest_labels_lhb_risk_watch_and_exposes_reason():
    digest = review_queue._strategy_lightweight_digest(
        {
            "asset_id": "CN:SZ:001399",
            "stock_name": "惠科股份",
            "strategy_name": "LHB Shortline Combo",
            "rank": 4,
            "score_total": 69.3698,
            "review_tier": "risk_watch",
            "risk_gate_code": "near_limit_down_followthrough_risk",
            "risk_gate_reason": "当日涨跌幅 -9.99% 触及 main_board 接近跌停阈值 -9.50%",
        },
        "CN:SZ:001399",
        "2026-07-14",
    )

    assert "跌停风险观察" in digest["title"]
    assert digest["risk_flags"] == [
        {
            "code": "near_limit_down_followthrough_risk",
            "message": "当日涨跌幅 -9.99% 触及 main_board 接近跌停阈值 -9.50%",
            "severity": "warning",
        }
    ]


def test_strategy_lightweight_digest_exposes_st_high_risk_warning():
    digest = review_queue._strategy_lightweight_digest(
        {
            "asset_id": "CN:SZ:000078",
            "stock_name": "ST海王",
            "strategy_name": "LHB Shortline Combo",
            "rank": 5,
            "score_total": 66.0,
            "review_tier": "top5_focus",
            "buy_signal_status": "tradable",
            "eligibility_warning_codes": ["st_high_risk"],
        },
        "CN:SZ:000078",
        "2026-07-14",
    )

    assert {
        "code": "st_high_risk",
        "message": "ST高风险",
        "severity": "warning",
    } in digest["risk_flags"]


def test_strategy_lightweight_digest_distinguishes_pending_and_confirmed_lhb_states():
    pending = review_queue._strategy_lightweight_digest(
        {
            "asset_id": "CN:SZ:002463",
            "strategy_name": "LHB Shortline Combo",
            "rank": 1,
            "score_total": 77.0,
            "review_tier": "top5_focus",
            "confirmation_state": "pending_confirmation",
            "phase12a_rule_layer": "pending_intraday",
        },
        "CN:SZ:002463",
        "2026-07-14",
    )
    confirmed = review_queue._strategy_lightweight_digest(
        {
            "asset_id": "CN:SZ:002463",
            "strategy_name": "LHB Shortline Combo",
            "rank": 1,
            "score_total": 77.0,
            "review_tier": "top5_focus",
            "confirmation_state": "confirmed_follow",
            "phase12a_rule_layer": "follow_pool_core",
        },
        "CN:SZ:002463",
        "2026-07-15",
    )

    assert "Top5 次日确认待定" in pending["title"]
    assert "Top5 重点复盘" not in pending["title"]
    assert "已确认可跟踪" in confirmed["title"]


def test_manifest_strategy_reader_preserves_lhb_risk_gate_fields(tmp_path):
    artifact = tmp_path / "strategy_lhb_shortline_review.csv"
    artifact.write_text(
        "trade_date,asset_id,stock_name,rank,score_total,strategy_id,strategy_name,review_tier,"
        "stock_name_source,top5_eligible,risk_gate_code,risk_gate_reason,price_limit_regime,"
        "near_limit_down_threshold,pct_chg,confirmation_state,phase12a_rule_layer,phase12a_rule_action,fill_status\n"
        "2026-07-14,CN:SZ:001399,惠科股份,4,69.3698,lhb_shortline,LHB Shortline Combo,"
        "risk_watch,lhb_top_list_daily,False,near_limit_down_followthrough_risk,接近跌停,main_board,-9.5,-9.991,"
        "risk_watch,pending_intraday,pending,not_follow_allowed\n",
        encoding="utf-8",
    )

    rows = review_queue._read_manifest_strategy_artifact(
        artifact,
        trade_date="2026-07-14",
        limit=50,
        manifest={"run_id": "strategy-eod-2026-07-14-local", "module": "strategy_lhb_shortline"},
    )

    assert rows[0]["stock_name"] == "惠科股份"
    assert rows[0]["stock_name_source"] == "lhb_top_list_daily"
    assert rows[0]["top5_eligible"] is False
    assert rows[0]["risk_gate_code"] == "near_limit_down_followthrough_risk"
    assert rows[0]["risk_gate_reason"] == "接近跌停"
    assert rows[0]["confirmation_state"] == "risk_watch"
    assert rows[0]["phase12a_rule_layer"] == "pending_intraday"
