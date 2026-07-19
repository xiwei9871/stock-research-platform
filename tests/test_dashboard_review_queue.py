import pytest

from stock_research.dashboard import review_queue
from stock_research.strategy_publication_contracts import (
    build_publication_identity,
    get_publication_contract,
)


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


def test_manifest_strategy_rows_use_versioned_artifact_not_stale_root_mirror(tmp_path, monkeypatch):
    root_mirror = tmp_path / "strategy_mid_trend_review.csv"
    versioned = tmp_path / "strategy_runs" / "mid_trend" / "publish-1" / "review.csv"
    versioned.parent.mkdir(parents=True)
    root_mirror.write_text(
        "trade_date,asset_id,rank,strategy_id\n2026-07-18,CN:SH:600001,1,mid_trend\n",
        encoding="utf-8",
    )
    versioned.write_text(
        "trade_date,asset_id,rank,strategy_id\n2026-07-18,CN:SH:600002,1,mid_trend\n",
        encoding="utf-8",
    )
    identity = build_publication_identity(get_publication_contract("mid_trend"))
    version_dir = versioned.parent
    output_paths = {
        "equity_path": str(version_dir / "equity.csv"),
        "positions_path": str(version_dir / "positions.csv"),
        "trades_path": str(version_dir / "trades.csv"),
        "review_path": str(versioned),
        "summary_path": str(version_dir / "summary.json"),
        "publication_manifest_path": str(version_dir / "publication_manifest.json"),
    }
    summary = {
        "engine_version": "mid_trend_v1",
        "top_n": 5,
        "transaction_cost_bps": 10.0,
        "max_position_weight": 0.2,
        "adjust_type": "hfq",
        "frequency": "weekly",
        "benchmark_variant": "top5_weekly_max2_selective_trend_holding_protection_v1",
        "publication_identity": identity,
    }
    monkeypatch.setattr(
        review_queue,
        "load_latest_data_run_manifest",
        lambda trade_date: [
            {
                "module": "strategy_mid_trend",
                "status": "success",
                "trade_date": trade_date,
                "run_id": "r1",
                "artifact_path": str(versioned),
                "metadata": {
                    "publication_identity": identity,
                    "identity_schema_version": "strategy_publication_identity_v1",
                    "artifact_version": "strategy_artifact_v1",
                    "publish_id": "publish-1",
                    "publication_manifest_path": str(versioned.parent / "publication_manifest.json"),
                    "output_paths": output_paths,
                    "summary": summary,
                },
            }
        ],
    )

    rows = review_queue._load_manifest_strategy_rows(trade_date="2026-07-18", limit=50)

    assert [row["asset_id"] for row in rows] == ["CN:SH:600002"]


def test_v1_manifest_rejects_root_mirror_as_artifact_path(tmp_path, monkeypatch):
    root_mirror = tmp_path / "strategy_mid_trend_review.csv"
    root_mirror.write_text(
        "trade_date,asset_id,rank,strategy_id\n2026-07-18,CN:SH:600001,1,mid_trend\n",
        encoding="utf-8",
    )
    identity = build_publication_identity(get_publication_contract("mid_trend"))
    monkeypatch.setattr(review_queue, "_manifest_strategy_contract_valid", lambda module: True)
    monkeypatch.setattr(
        review_queue,
        "load_latest_data_run_manifest",
        lambda trade_date: [
            {
                "module": "strategy_mid_trend",
                "status": "success",
                "trade_date": trade_date,
                "run_id": "r1",
                "artifact_path": str(root_mirror),
                "metadata": {
                    "identity_schema_version": "strategy_publication_identity_v1",
                    "publication_identity": identity,
                    "artifact_version": "strategy_artifact_v1",
                    "publish_id": "publish-1",
                    "publication_manifest_path": str(tmp_path / "publication_manifest.json"),
                    "output_paths": {"review_path": str(root_mirror)},
                    "summary": {"publication_identity": identity},
                },
            }
        ],
    )

    assert review_queue._load_manifest_strategy_rows(trade_date="2026-07-18", limit=50) == []


def test_manifest_strategy_rows_reject_v1_identity_mismatch(tmp_path, monkeypatch):
    artifact = tmp_path / "review.csv"
    artifact.write_text(
        "trade_date,asset_id,rank,strategy_id\n2026-07-18,CN:SH:600002,1,mid_trend\n",
        encoding="utf-8",
    )
    identity = build_publication_identity(get_publication_contract("mid_trend"))
    identity["config_fingerprint"] = "wrong"
    monkeypatch.setattr(
        review_queue,
        "load_latest_data_run_manifest",
        lambda trade_date: [
            {
                "module": "strategy_mid_trend",
                "status": "success",
                "trade_date": trade_date,
                "run_id": "r1",
                "artifact_path": str(artifact),
                "metadata": {
                    "identity_schema_version": "strategy_publication_identity_v1",
                    "publication_identity": identity,
                    "summary": {"publication_identity": identity},
                },
            }
        ],
    )

    assert review_queue._load_manifest_strategy_rows(trade_date="2026-07-18", limit=50) == []


def test_v1_manifest_missing_identity_does_not_fall_back_to_root_artifact(tmp_path, monkeypatch):
    root_mirror = tmp_path / "strategy_mid_trend_review.csv"
    root_mirror.write_text(
        "trade_date,asset_id,rank,strategy_id\n2026-07-18,CN:SH:600001,1,mid_trend\n",
        encoding="utf-8",
    )
    module = {
        "module": "strategy_mid_trend",
        "status": "success",
        "trade_date": "2026-07-18",
        "artifact_path": str(tmp_path / "missing-version" / "review.csv"),
        "metadata": {"identity_schema_version": "strategy_publication_identity_v1"},
    }
    monkeypatch.setattr(review_queue, "load_latest_data_run_manifest", lambda trade_date: [module])
    monkeypatch.setattr(review_queue, "_load_strategy_artifact_topn_rows", lambda **kwargs: [
        {"trade_date": "2026-07-18", "asset_id": "CN:SH:600001", "strategy_id": "mid_trend"}
    ])
    monkeypatch.setattr(review_queue, "_load_db_strategy_position_rows", lambda **kwargs: [])
    monkeypatch.setattr(review_queue, "_load_asset_names", lambda asset_ids: {})

    rows = review_queue.load_active_strategy_topn_rows(trade_date="2026-07-18", limit=50)

    assert rows == []


def test_build_review_queue_rejects_snapshot_fallback_for_identity_aware_strategy(monkeypatch):
    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda **kwargs: {"latest_market_date": "2026-07-18"},
    )
    monkeypatch.setattr(review_queue, "_load_manifest_strategy_rows", lambda **kwargs: [])
    monkeypatch.setattr(
        review_queue,
        "_identity_aware_manifest_strategy_ids",
        lambda **kwargs: {"mid_trend"},
    )
    monkeypatch.setattr(
        review_queue,
        "_load_strategy_snapshot_rows",
        lambda **kwargs: [
            {
                "trade_date": "2026-07-18",
                "asset_id": "CN:SH:600001",
                "strategy_id": "mid_trend",
                "strategy_name": "Mid Trend Combo",
                "rank": 1,
            }
        ],
    )
    monkeypatch.setattr(review_queue, "load_active_strategy_topn_rows", lambda **kwargs: [])
    monkeypatch.setattr(review_queue, "load_top_scores_for_dashboard", lambda *args, **kwargs: [])

    result = review_queue.build_review_queue(trade_date="2026-07-18")

    assert result["review_mode"] == "score_topn"


def test_artifact_version_v1_without_identity_rejects_manifest_root_and_snapshot_fallbacks(
    tmp_path, monkeypatch
):
    root_mirror = tmp_path / "strategy_mid_trend_review.csv"
    root_mirror.write_text(
        "trade_date,asset_id,rank,strategy_id\n2026-07-18,CN:SH:600001,1,mid_trend\n",
        encoding="utf-8",
    )
    module = {
        "module": "strategy_mid_trend",
        "status": "success",
        "trade_date": "2026-07-18",
        "artifact_path": str(root_mirror),
        "metadata": {"artifact_version": "strategy_artifact_v1"},
    }
    monkeypatch.setattr(review_queue, "load_latest_data_run_manifest", lambda trade_date: [module])
    monkeypatch.setattr(
        review_queue,
        "_load_strategy_artifact_topn_rows",
        lambda **kwargs: [
            {
                "trade_date": "2026-07-18",
                "asset_id": "CN:SH:600001",
                "strategy_id": "mid_trend",
            }
        ],
    )
    monkeypatch.setattr(review_queue, "_load_db_strategy_position_rows", lambda **kwargs: [])
    monkeypatch.setattr(review_queue, "_load_asset_names", lambda asset_ids: {})

    assert review_queue._load_manifest_strategy_rows(trade_date="2026-07-18", limit=50) == []
    assert review_queue.load_active_strategy_topn_rows(trade_date="2026-07-18", limit=50) == []

    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda **kwargs: {"latest_market_date": "2026-07-18"},
    )
    monkeypatch.setattr(
        review_queue,
        "_load_strategy_snapshot_rows",
        lambda **kwargs: [
            {
                "trade_date": "2026-07-18",
                "asset_id": "CN:SH:600001",
                "strategy_id": "mid_trend",
                "strategy_name": "Mid Trend Combo",
                "rank": 1,
            }
        ],
    )
    monkeypatch.setattr(review_queue, "load_top_scores_for_dashboard", lambda *args, **kwargs: [])

    assert review_queue.build_review_queue(trade_date="2026-07-18")["review_mode"] == "score_topn"


def _v1_versioned_manifest(tmp_path):
    version_dir = tmp_path / "strategy_runs" / "mid_trend" / "publish-1"
    paths = {
        "equity_path": version_dir / "equity.csv",
        "positions_path": version_dir / "positions.csv",
        "trades_path": version_dir / "trades.csv",
        "review_path": version_dir / "review.csv",
        "summary_path": version_dir / "summary.json",
    }
    identity = build_publication_identity(get_publication_contract("mid_trend"))
    return {
        "module": "strategy_mid_trend",
        "artifact_path": str(paths["review_path"]),
        "metadata": {
            "identity_schema_version": "strategy_publication_identity_v1",
            "artifact_version": "strategy_artifact_v1",
            "publish_id": "publish-1",
            "publication_identity": identity,
            "publication_manifest_path": str(version_dir / "publication_manifest.json"),
            **{key: str(path) for key, path in paths.items()},
            "output_paths": {
                **{key: str(path) for key, path in paths.items()},
                "publication_manifest_path": str(version_dir / "publication_manifest.json"),
            },
            "summary": {"publication_identity": identity},
        },
    }


@pytest.mark.parametrize(
    ("container_name", "path_key"),
    [
        *[("metadata", key) for key in (
            "equity_path",
            "positions_path",
            "trades_path",
            "review_path",
            "summary_path",
        )],
        *[("output_paths", key) for key in (
            "equity_path",
            "positions_path",
            "trades_path",
            "review_path",
            "summary_path",
        )],
        ("metadata", "publication_manifest_path"),
        ("output_paths", "publication_manifest_path"),
    ],
)
def test_v1_manifest_rejects_any_declared_official_path_outside_version_dir(
    tmp_path, container_name, path_key
):
    module = _v1_versioned_manifest(tmp_path)
    assert review_queue._manifest_strategy_artifact_path_valid(module) is True
    container = (
        module["metadata"]
        if container_name == "metadata"
        else module["metadata"]["output_paths"]
    )
    container[path_key] = str(tmp_path / f"stale-{path_key}")

    assert review_queue._manifest_strategy_artifact_path_valid(module) is False


@pytest.mark.parametrize(
    "path_key",
    (
        "equity_path",
        "positions_path",
        "trades_path",
        "review_path",
        "summary_path",
        "publication_manifest_path",
    ),
)
@pytest.mark.parametrize("missing_kind", ("removed", "blank"))
def test_v1_manifest_requires_complete_output_paths_and_blocks_all_fallbacks(
    tmp_path, monkeypatch, path_key, missing_kind
):
    module = _v1_versioned_manifest(tmp_path)
    module.update({"status": "success", "trade_date": "2026-07-18", "run_id": "r1"})
    if missing_kind == "removed":
        del module["metadata"]["output_paths"][path_key]
    else:
        module["metadata"]["output_paths"][path_key] = ""
    monkeypatch.setattr(review_queue, "load_latest_data_run_manifest", lambda trade_date: [module])
    monkeypatch.setattr(review_queue, "_manifest_strategy_contract_valid", lambda candidate: True)
    monkeypatch.setattr(
        review_queue,
        "_load_strategy_artifact_topn_rows",
        lambda **kwargs: [
            {
                "trade_date": "2026-07-18",
                "asset_id": "CN:SH:600001",
                "strategy_id": "mid_trend",
            }
        ],
    )
    monkeypatch.setattr(review_queue, "_load_db_strategy_position_rows", lambda **kwargs: [])
    monkeypatch.setattr(review_queue, "_load_asset_names", lambda asset_ids: {})

    assert review_queue._manifest_strategy_artifact_path_valid(module) is False
    assert review_queue._load_manifest_strategy_rows(trade_date="2026-07-18", limit=50) == []
    assert review_queue.load_active_strategy_topn_rows(trade_date="2026-07-18", limit=50) == []

    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda **kwargs: {"latest_market_date": "2026-07-18"},
    )
    monkeypatch.setattr(
        review_queue,
        "_load_strategy_snapshot_rows",
        lambda **kwargs: [
            {
                "trade_date": "2026-07-18",
                "asset_id": "CN:SH:600001",
                "strategy_id": "mid_trend",
                "strategy_name": "Mid Trend Combo",
                "rank": 1,
            }
        ],
    )
    monkeypatch.setattr(review_queue, "load_top_scores_for_dashboard", lambda *args, **kwargs: [])

    assert review_queue.build_review_queue(trade_date="2026-07-18")["review_mode"] == "score_topn"
