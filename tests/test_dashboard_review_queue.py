import copy
import os
from pathlib import Path

import pytest
from types import SimpleNamespace

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
    monkeypatch.setattr(review_queue, "SETTINGS", SimpleNamespace(output_root=tmp_path))
    versioned = (
        tmp_path
        / "research"
        / "strategy_daily_eod"
        / "2026-07-18"
        / "strategy_runs"
        / "mid_trend"
        / "publish-1"
        / "review.csv"
    )
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
    for key, path in output_paths.items():
        if key != "review_path":
            Path(path).write_text("{}\n", encoding="utf-8")
    summary = {
        "engine_version": "mid_trend_v1",
        "top_n": 5,
        "transaction_cost_bps": 10.0,
        "max_position_weight": 0.2,
        "adjust_type": "hfq",
        "frequency": "weekly",
        "benchmark_variant": "top5_weekly_max2_selective_trend_holding_protection_v1",
        "publication_identity": identity,
        "performance_effective_date": "2026-07-18",
    }
    monkeypatch.setattr(
        review_queue,
        "load_latest_data_run_manifest",
        lambda trade_date: [
            {
                "module": "strategy_mid_trend",
                "status": "success",
                "trade_date": trade_date,
                "latest_trade_date": trade_date,
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
    monkeypatch.setattr(
        review_queue,
        "_load_strategy_manifest_snapshot",
        lambda **kwargs: ([], {"mid_trend"}),
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
    monkeypatch.setattr(review_queue, "_load_strategy_artifact_topn_rows", lambda **kwargs: [])
    monkeypatch.setattr(review_queue, "_load_db_strategy_position_rows", lambda **kwargs: [])
    monkeypatch.setattr(review_queue, "_load_asset_names", lambda asset_ids: {})

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
    version_dir = (
        tmp_path
        / "research"
        / "strategy_daily_eod"
        / "2026-07-18"
        / "strategy_runs"
        / "mid_trend"
        / "publish-1"
    )
    paths = {
        "equity_path": version_dir / "equity.csv",
        "positions_path": version_dir / "positions.csv",
        "trades_path": version_dir / "trades.csv",
        "review_path": version_dir / "review.csv",
        "summary_path": version_dir / "summary.json",
    }
    version_dir.mkdir(parents=True, exist_ok=True)
    paths["equity_path"].write_text("trade_date,equity\n", encoding="utf-8")
    paths["positions_path"].write_text("trade_date,asset_id\n", encoding="utf-8")
    paths["trades_path"].write_text("trade_date,asset_id\n", encoding="utf-8")
    paths["review_path"].write_text(
        "trade_date,asset_id,rank,strategy_id\n2026-07-18,CN:SH:600002,1,mid_trend\n",
        encoding="utf-8",
    )
    paths["summary_path"].write_text("{}\n", encoding="utf-8")
    (version_dir / "publication_manifest.json").write_text("{}\n", encoding="utf-8")
    identity = build_publication_identity(get_publication_contract("mid_trend"))
    return {
        "module": "strategy_mid_trend",
        "status": "success",
        "trade_date": "2026-07-18",
        "latest_trade_date": "2026-07-18",
        "run_id": "r1",
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
            "summary": {
                "publication_identity": identity,
                "performance_effective_date": "2026-07-18",
                "engine_version": "mid_trend_v1",
                "top_n": 5,
                "transaction_cost_bps": 10.0,
                "max_position_weight": 0.2,
                "adjust_type": "hfq",
                "frequency": "weekly",
                "benchmark_variant": (
                    "top5_weekly_max2_selective_trend_holding_protection_v1"
                ),
            },
        },
    }


def _replace_manifest_path_root(module, source_root, declared_root):
    metadata = module["metadata"]
    path_keys = (
        "equity_path",
        "positions_path",
        "trades_path",
        "review_path",
        "summary_path",
        "publication_manifest_path",
    )
    module["artifact_path"] = str(
        declared_root / Path(module["artifact_path"]).relative_to(source_root)
    )
    for container in (metadata, metadata["output_paths"]):
        for key in path_keys:
            if key in container:
                container[key] = str(
                    declared_root / Path(container[key]).relative_to(source_root)
                )


def test_v1_manifest_rejects_complete_version_from_different_trade_date(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(review_queue, "SETTINGS", SimpleNamespace(output_root=tmp_path))
    module = _v1_versioned_manifest(tmp_path)
    module["trade_date"] = "2026-07-17"
    module["latest_trade_date"] = "2026-07-17"
    monkeypatch.setattr(review_queue, "load_latest_data_run_manifest", lambda trade_date: [module])
    monkeypatch.setattr(review_queue, "_manifest_strategy_contract_valid", lambda candidate: True)

    assert review_queue._manifest_strategy_artifact_path_valid(module) is False


def test_v1_manifest_rows_expose_generic_publication_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(review_queue, "SETTINGS", SimpleNamespace(output_root=tmp_path))
    module = _v1_versioned_manifest(tmp_path)
    module["metadata"]["summary"].update(
        {
            "engine_version": "mid_trend_v1",
            "top_n": 5,
            "transaction_cost_bps": 10.0,
            "max_position_weight": 0.2,
            "adjust_type": "hfq",
            "frequency": "weekly",
            "benchmark_variant": (
                "top5_weekly_max2_selective_trend_holding_protection_v1"
            ),
        }
    )
    monkeypatch.setattr(
        review_queue, "load_latest_data_run_manifest", lambda trade_date: [module]
    )

    rows = review_queue._load_manifest_strategy_rows(trade_date="2026-07-18", limit=50)
    queue = review_queue._strategy_review_queue(
        rows=rows,
        selected_trade_date="2026-07-18",
        score_version="strategy_topn",
        lookback_days=90,
    )
    item = next(group for group in queue["groups"] if group["bucket"] == "strategy:mid_trend")[
        "items"
    ][0]
    identity = build_publication_identity(get_publication_contract("mid_trend"))

    assert item["contract_id"] == identity["contract_id"]
    assert item["identity_schema_version"] == identity["identity_schema_version"]
    assert item["config_fingerprint"] == identity["config_fingerprint"]
    assert item["publication_policy"] == identity["publication_policy"]
    assert item["artifact_version"] == "strategy_artifact_v1"
    assert item["publication_manifest_path"].endswith(
        "/strategy_runs/mid_trend/publish-1/publication_manifest.json"
    )
    assert item["performance_as_of_date"] == "2026-07-18"
    assert item["contract_status"] == "success"

    rows, blocked = review_queue._load_strategy_manifest_snapshot(
        trade_date="2026-07-17",
        limit=50,
    )

    assert rows == []
    assert blocked == {"mid_trend"}


def test_manifest_review_row_snapshot_round_trip_preserves_trusted_evidence(
    tmp_path, monkeypatch
):
    from stock_research.review_evidence_snapshots import build_review_item_snapshot

    monkeypatch.setattr(review_queue, "SETTINGS", SimpleNamespace(output_root=tmp_path))
    module = _v1_versioned_manifest(tmp_path)
    local_review_path = Path(module["artifact_path"])

    rows = review_queue._read_manifest_strategy_artifact(
        local_review_path,
        trade_date="2026-07-18",
        limit=50,
        manifest=module,
    )
    queue = review_queue._strategy_review_queue(
        rows=rows,
        selected_trade_date="2026-07-18",
        score_version="strategy_topn",
        lookback_days=90,
    )
    item = next(
        group for group in queue["groups"] if group["bucket"] == "strategy:mid_trend"
    )["items"][0]
    payload = build_review_item_snapshot(item)["review_item_payload"]

    assert set(payload["source_manifest"]) == {
        "module",
        "strategy_id",
        "trade_date",
        "latest_trade_date",
        "metadata",
    }
    assert set(payload["source_manifest"]["metadata"]) == {
        "artifact_version",
        "publication_identity",
        "publication_manifest_path",
        "output_paths",
        "summary",
    }
    assert review_queue._snapshot_publication_contract_valid(
        payload, trade_date="2026-07-18"
    ) is True

    incomplete = copy.deepcopy(payload)
    del incomplete["source_manifest"]["metadata"]["publication_identity"]
    assert review_queue._snapshot_publication_contract_valid(
        incomplete, trade_date="2026-07-18"
    ) is False


@pytest.mark.parametrize(
    "extra_row",
    [
        "2026-07-18,CN:SH:600003,2,tech_bottleneck\n",
        (
            "2026-07-18,CN:SH:600003,2,mid_trend,mid_trend:balanced:legacy\n"
        ),
    ],
)
def test_manifest_rejects_entire_mixed_strategy_artifact(extra_row, tmp_path, monkeypatch):
    monkeypatch.setattr(review_queue, "SETTINGS", SimpleNamespace(output_root=tmp_path))
    module = _v1_versioned_manifest(tmp_path)
    review_path = Path(module["artifact_path"])
    if "legacy" in extra_row:
        review_path.write_text(
            "trade_date,asset_id,rank,strategy_id,contract_id\n"
            "2026-07-18,CN:SH:600002,1,mid_trend,"
            f"{module['metadata']['publication_identity']['contract_id']}\n"
            + extra_row,
            encoding="utf-8",
        )
    else:
        review_path.write_text(
            "trade_date,asset_id,rank,strategy_id\n"
            "2026-07-18,CN:SH:600002,1,mid_trend\n"
            + extra_row,
            encoding="utf-8",
        )
    module["metadata"]["summary"].update(
        {
            "engine_version": "mid_trend_v1",
            "top_n": 5,
            "transaction_cost_bps": 10.0,
            "max_position_weight": 0.2,
            "adjust_type": "hfq",
            "frequency": "weekly",
            "benchmark_variant": "top5_weekly_max2_selective_trend_holding_protection_v1",
        }
    )
    monkeypatch.setattr(
        review_queue, "load_latest_data_run_manifest", lambda trade_date: [module]
    )

    rows, blocked = review_queue._load_strategy_manifest_snapshot(
        trade_date="2026-07-18", limit=50
    )

    assert rows == []
    assert blocked == {"mid_trend"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("performance_as_of_date", "2026-07-19"),
        ("performance_as_of_date", "not-a-date"),
        ("performance_as_of_date", ""),
        ("trade_date", ""),
        ("contract_id", "mid_trend:balanced:legacy"),
        ("artifact_version", "strategy_artifact_v999"),
        (
            "publication_manifest_path",
            (
                "/srv/outputs/research/strategy_daily_eod/2026-07-18/strategy_runs/"
                "tech_bottleneck/publish-1/publication_manifest.json"
            ),
        ),
    ],
)
def test_persisted_strategy_snapshot_fails_closed_for_stale_or_mixed_contract(
    field, value, monkeypatch
):
    from stock_research import review_evidence_snapshots

    identity = build_publication_identity(get_publication_contract("mid_trend"))
    payload = {
        "score_version": "strategy_topn",
        "trade_date": "2026-07-18",
        "asset_id": "CN:SH:600002",
        "strategy_id": "mid_trend",
        "rank": 1,
        "contract_id": identity["contract_id"],
        "identity_schema_version": identity["identity_schema_version"],
        "config_fingerprint": identity["config_fingerprint"],
        "publication_policy": identity["publication_policy"],
        "artifact_version": "strategy_artifact_v1",
        "publication_manifest_path": (
            "/srv/outputs/research/strategy_daily_eod/2026-07-18/strategy_runs/"
            "mid_trend/publish-1/publication_manifest.json"
        ),
        "performance_as_of_date": "2026-07-18",
        "contract_status": "success",
    }
    payload[field] = value
    monkeypatch.setattr(
        review_evidence_snapshots,
        "list_review_item_snapshots",
        lambda **kwargs: [{"review_item_payload": payload}],
    )

    assert review_queue._load_strategy_snapshot_rows(
        trade_date="2026-07-18", limit=50
    ) == []


def test_persisted_lhb_snapshot_accepts_stale_performance_bound_to_manifest(monkeypatch):
    from stock_research import review_evidence_snapshots

    identity = build_publication_identity(get_publication_contract("lhb_shortline"))
    payload = {
        "score_version": "strategy_topn",
        "trade_date": "2026-07-18",
        "asset_id": "CN:SZ:001399",
        "strategy_id": "lhb_shortline",
        "rank": 1,
        "contract_id": identity["contract_id"],
        "identity_schema_version": identity["identity_schema_version"],
        "config_fingerprint": identity["config_fingerprint"],
        "publication_policy": identity["publication_policy"],
        "artifact_version": "strategy_artifact_v1",
        "publication_manifest_path": (
            "/srv/outputs/research/strategy_daily_eod/2026-07-18/strategy_runs/"
            "lhb_shortline/publish-1/publication_manifest.json"
        ),
        "performance_as_of_date": "2026-07-17",
        "contract_status": "success",
        "publication_manifest": {
            "strategy_id": "lhb_shortline",
            "trade_date": "2026-07-18",
            "performance_as_of_date": "2026-07-17",
            "artifact_version": "strategy_artifact_v1",
            "publication_identity": identity,
            "publication_manifest_path": (
                "/srv/outputs/research/strategy_daily_eod/2026-07-18/strategy_runs/"
                "lhb_shortline/publish-1/publication_manifest.json"
            ),
        },
    }
    monkeypatch.setattr(
        review_evidence_snapshots,
        "list_review_item_snapshots",
        lambda **kwargs: [{"review_item_payload": payload}],
    )

    rows = review_queue._load_strategy_snapshot_rows(
        trade_date="2026-07-18", limit=50
    )

    assert len(rows) == 1
    assert rows[0]["performance_as_of_date"] == "2026-07-17"

    payload["publication_manifest"] = {
        "module": "strategy_lhb_shortline",
        "trade_date": "2026-07-18",
        "latest_trade_date": "2026-07-18",
        "metadata": {
            "artifact_version": "strategy_artifact_v1",
            "publication_identity": identity,
            "publication_manifest_path": payload["publication_manifest_path"],
            "summary": {"performance_effective_date": "2026-07-16"},
        },
    }

    assert review_queue._load_strategy_snapshot_rows(
        trade_date="2026-07-18", limit=50
    ) == []


def test_persisted_snapshot_rejects_manifest_path_trade_date_mismatch(monkeypatch):
    from stock_research import review_evidence_snapshots

    identity = build_publication_identity(get_publication_contract("mid_trend"))
    payload = {
        "score_version": "strategy_topn",
        "trade_date": "2026-07-18",
        "asset_id": "CN:SH:600002",
        "strategy_id": "mid_trend",
        "rank": 1,
        "contract_id": identity["contract_id"],
        "identity_schema_version": identity["identity_schema_version"],
        "config_fingerprint": identity["config_fingerprint"],
        "publication_policy": identity["publication_policy"],
        "artifact_version": "strategy_artifact_v1",
        "publication_manifest_path": (
            "/srv/outputs/research/strategy_daily_eod/2026-07-17/strategy_runs/"
            "mid_trend/publish-1/publication_manifest.json"
        ),
        "performance_as_of_date": "2026-07-17",
        "contract_status": "success",
    }
    monkeypatch.setattr(
        review_evidence_snapshots,
        "list_review_item_snapshots",
        lambda **kwargs: [{"review_item_payload": payload}],
    )

    assert review_queue._load_strategy_snapshot_rows(
        trade_date="2026-07-18", limit=50
    ) == []


def test_persisted_snapshot_rejects_self_asserted_publication_path(monkeypatch):
    from stock_research import review_evidence_snapshots

    identity = build_publication_identity(get_publication_contract("mid_trend"))
    payload = {
        "score_version": "strategy_topn",
        "trade_date": "2026-07-18",
        "asset_id": "CN:SH:600002",
        "strategy_id": "mid_trend",
        "rank": 1,
        "contract_id": identity["contract_id"],
        "identity_schema_version": identity["identity_schema_version"],
        "config_fingerprint": identity["config_fingerprint"],
        "publication_policy": identity["publication_policy"],
        "artifact_version": "strategy_artifact_v1",
        "publication_manifest_path": (
            "/srv/outputs/research/strategy_daily_eod/2026-07-18/strategy_runs/"
            "mid_trend/publish-1/publication_manifest.json"
        ),
        "performance_as_of_date": "2026-07-17",
        "contract_status": "success",
    }
    monkeypatch.setattr(
        review_evidence_snapshots,
        "list_review_item_snapshots",
        lambda **kwargs: [{"review_item_payload": payload}],
    )

    assert review_queue._load_strategy_snapshot_rows(
        trade_date="2026-07-18", limit=50
    ) == []


@pytest.mark.parametrize("embedded_end_date", ("2026-07-19", "not-a-date", "2026-07-16"))
def test_persisted_snapshot_rejects_invalid_embedded_end_date_fallback(
    embedded_end_date, monkeypatch
):
    from stock_research import review_evidence_snapshots

    identity = build_publication_identity(get_publication_contract("mid_trend"))
    manifest_path = (
        "/srv/outputs/research/strategy_daily_eod/2026-07-18/strategy_runs/"
        "mid_trend/publish-1/publication_manifest.json"
    )
    payload = {
        "score_version": "strategy_topn",
        "trade_date": "2026-07-18",
        "asset_id": "CN:SH:600002",
        "strategy_id": "mid_trend",
        "rank": 1,
        "contract_id": identity["contract_id"],
        "identity_schema_version": identity["identity_schema_version"],
        "config_fingerprint": identity["config_fingerprint"],
        "publication_policy": identity["publication_policy"],
        "artifact_version": "strategy_artifact_v1",
        "publication_manifest_path": manifest_path,
        "performance_as_of_date": "2026-07-17",
        "contract_status": "success",
        "source_manifest": {
            "module": "strategy_mid_trend",
            "trade_date": "2026-07-18",
            "latest_trade_date": "2026-07-18",
            "metadata": {
                "artifact_version": "strategy_artifact_v1",
                "publication_identity": identity,
                "publication_manifest_path": manifest_path,
                "summary": {"end_date": embedded_end_date},
            },
        },
    }
    monkeypatch.setattr(
        review_evidence_snapshots,
        "list_review_item_snapshots",
        lambda **kwargs: [{"review_item_payload": payload}],
    )

    assert review_queue._load_strategy_snapshot_rows(
        trade_date="2026-07-18", limit=50
    ) == []


@pytest.mark.parametrize("trade_date", ("2026-7-18", "../2026-07-18", "not-a-date", ""))
def test_v1_manifest_rejects_malformed_trade_date(trade_date, tmp_path, monkeypatch):
    monkeypatch.setattr(review_queue, "SETTINGS", SimpleNamespace(output_root=tmp_path))
    module = _v1_versioned_manifest(tmp_path)
    module["trade_date"] = trade_date
    module["latest_trade_date"] = trade_date

    assert review_queue._manifest_strategy_artifact_path_valid(module) is False


@pytest.mark.parametrize("missing_field", ("trade_date", "latest_trade_date"))
def test_v1_manifest_requires_both_trade_date_fields_and_blocks_all_fallbacks(
    missing_field, tmp_path, monkeypatch
):
    monkeypatch.setattr(review_queue, "SETTINGS", SimpleNamespace(output_root=tmp_path))
    module = _v1_versioned_manifest(tmp_path)
    del module[missing_field]
    monkeypatch.setattr(review_queue, "load_latest_data_run_manifest", lambda trade_date: [module])
    monkeypatch.setattr(review_queue, "_manifest_strategy_contract_valid", lambda candidate: True)
    monkeypatch.setattr(
        review_queue,
        "_load_strategy_artifact_topn_rows",
        lambda **kwargs: [
            {"trade_date": "2026-07-18", "asset_id": "A", "strategy_id": "mid_trend"}
        ],
    )
    monkeypatch.setattr(review_queue, "_load_db_strategy_position_rows", lambda **kwargs: [])
    monkeypatch.setattr(review_queue, "_load_asset_names", lambda asset_ids: {})

    assert review_queue._manifest_strategy_artifact_path_valid(module) is False
    rows, blocked = review_queue._load_strategy_manifest_snapshot(
        trade_date="2026-07-18",
        limit=50,
    )
    assert rows == []
    assert blocked == {"mid_trend"}
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
            {"trade_date": "2026-07-18", "asset_id": "B", "strategy_id": "mid_trend", "rank": 1}
        ],
    )
    monkeypatch.setattr(review_queue, "load_top_scores_for_dashboard", lambda *args, **kwargs: [])

    assert review_queue.build_review_queue(trade_date="2026-07-18")["review_mode"] == "score_topn"


def test_v1_manifest_does_not_relocate_arbitrary_outputs_prefix(tmp_path, monkeypatch):
    monkeypatch.setattr(review_queue, "SETTINGS", SimpleNamespace(output_root=tmp_path))
    module = _v1_versioned_manifest(tmp_path)
    _replace_manifest_path_root(module, tmp_path, Path("/evil/outputs"))

    assert review_queue._manifest_strategy_artifact_path_valid(module) is False


def test_v1_manifest_relocates_approved_internal_synced_output_root(tmp_path, monkeypatch):
    monkeypatch.setattr(review_queue, "SETTINGS", SimpleNamespace(output_root=tmp_path))
    module = _v1_versioned_manifest(tmp_path)
    _replace_manifest_path_root(
        module,
        tmp_path,
        Path("/mnt/internal/stock_research/outputs"),
    )

    assert review_queue._manifest_strategy_artifact_path_valid(module) is True


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
def test_v1_manifest_rejects_each_missing_required_file(
    path_key, tmp_path, monkeypatch
):
    monkeypatch.setattr(review_queue, "SETTINGS", SimpleNamespace(output_root=tmp_path))
    module = _v1_versioned_manifest(tmp_path)
    module.update({"status": "success", "trade_date": "2026-07-18", "run_id": "r1"})
    Path(module["metadata"]["output_paths"][path_key]).unlink()
    monkeypatch.setattr(review_queue, "load_latest_data_run_manifest", lambda trade_date: [module])
    monkeypatch.setattr(review_queue, "_manifest_strategy_contract_valid", lambda candidate: True)

    rows, blocked = review_queue._load_strategy_manifest_snapshot(
        trade_date="2026-07-18",
        limit=50,
    )

    assert rows == []
    assert blocked == {"mid_trend"}


@pytest.mark.parametrize("file_kind", ("directory", "fifo", "symlink"))
def test_v1_manifest_rejects_non_regular_required_file(
    file_kind, tmp_path, monkeypatch
):
    monkeypatch.setattr(review_queue, "SETTINGS", SimpleNamespace(output_root=tmp_path))
    module = _v1_versioned_manifest(tmp_path)
    module.update({"status": "success", "trade_date": "2026-07-18", "run_id": "r1"})
    equity_path = Path(module["metadata"]["output_paths"]["equity_path"])
    equity_path.unlink()
    if file_kind == "directory":
        equity_path.mkdir()
    elif file_kind == "fifo":
        os.mkfifo(equity_path)
    else:
        external = tmp_path / "external-equity.csv"
        external.write_text("trade_date,equity\n", encoding="utf-8")
        equity_path.symlink_to(external)
    monkeypatch.setattr(review_queue, "load_latest_data_run_manifest", lambda trade_date: [module])
    monkeypatch.setattr(review_queue, "_manifest_strategy_contract_valid", lambda candidate: True)

    rows, blocked = review_queue._load_strategy_manifest_snapshot(
        trade_date="2026-07-18",
        limit=50,
    )

    assert rows == []
    assert blocked == {"mid_trend"}


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
    tmp_path, monkeypatch, container_name, path_key
):
    monkeypatch.setattr(review_queue, "SETTINGS", SimpleNamespace(output_root=tmp_path))
    module = _v1_versioned_manifest(tmp_path)
    assert review_queue._manifest_strategy_artifact_path_valid(module) is True
    container = (
        module["metadata"]
        if container_name == "metadata"
        else module["metadata"]["output_paths"]
    )
    container[path_key] = str(tmp_path / f"stale-{path_key}")

    assert review_queue._manifest_strategy_artifact_path_valid(module) is False


@pytest.mark.parametrize("missing_kind", ("removed", "blank"))
def test_v1_manifest_requires_top_level_publication_manifest_path(
    missing_kind, tmp_path, monkeypatch
):
    monkeypatch.setattr(review_queue, "SETTINGS", SimpleNamespace(output_root=tmp_path))
    module = _v1_versioned_manifest(tmp_path)
    if missing_kind == "removed":
        del module["metadata"]["publication_manifest_path"]
    else:
        module["metadata"]["publication_manifest_path"] = ""

    assert module["metadata"]["output_paths"]["publication_manifest_path"]
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
    monkeypatch.setattr(review_queue, "SETTINGS", SimpleNamespace(output_root=tmp_path))
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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("identity_schema_version", "strategy_publication_identity_v999"),
        ("artifact_version", "strategy_artifact_v999"),
    ],
)
def test_unknown_publication_declaration_rejects_manifest(field, value, tmp_path, monkeypatch):
    monkeypatch.setattr(review_queue, "SETTINGS", SimpleNamespace(output_root=tmp_path))
    module = _v1_versioned_manifest(tmp_path)
    module["metadata"][field] = value

    assert review_queue._manifest_publication_declaration_valid(module) is False
    if field == "artifact_version":
        assert review_queue._manifest_strategy_artifact_path_valid(module) is False


def test_official_manifest_contract_validation_fails_closed(monkeypatch, tmp_path):
    module = _v1_versioned_manifest(tmp_path)

    missing_summary = copy.deepcopy(module)
    missing_summary["metadata"]["summary"] = {}
    assert review_queue._manifest_strategy_contract_valid(missing_summary) is False

    monkeypatch.setattr(
        review_queue,
        "load_strategy_contracts",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("registry unavailable")),
    )
    assert review_queue._manifest_strategy_contract_valid(module) is False

    monkeypatch.setattr(review_queue, "load_strategy_contracts", lambda **kwargs: {})
    assert review_queue._manifest_strategy_contract_valid(module) is False


@pytest.mark.parametrize(
    "publish_id",
    ("", ".", "..", "a/b", "a\\b", "bad space", "非ascii"),
)
def test_publish_id_must_be_safe_single_path_component(publish_id):
    assert review_queue._safe_publish_id(publish_id) is False


def test_v1_manifest_rejects_external_strategy_runs_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(
        review_queue,
        "SETTINGS",
        SimpleNamespace(output_root=tmp_path / "trusted_outputs"),
    )
    module = _v1_versioned_manifest(tmp_path / "external")

    assert review_queue._manifest_strategy_artifact_path_valid(module) is False


def test_v1_manifest_rejects_symlinked_version_directory(tmp_path, monkeypatch):
    output_root = tmp_path / "outputs"
    monkeypatch.setattr(review_queue, "SETTINGS", SimpleNamespace(output_root=output_root))
    trusted_parent = (
        output_root
        / "research"
        / "strategy_daily_eod"
        / "2026-07-18"
        / "strategy_runs"
        / "mid_trend"
    )
    trusted_parent.mkdir(parents=True)
    external_version = tmp_path / "external" / "publish-1"
    external_version.mkdir(parents=True)
    (trusted_parent / "publish-1").symlink_to(external_version, target_is_directory=True)
    module = _v1_versioned_manifest(output_root)

    assert review_queue._manifest_strategy_artifact_path_valid(module) is False


def test_manifest_loader_failure_blocks_all_official_fallbacks(monkeypatch):
    calls = 0

    def fail_loader(*, trade_date):
        nonlocal calls
        calls += 1
        raise RuntimeError("manifest unavailable")

    monkeypatch.setattr(review_queue, "load_latest_data_run_manifest", fail_loader)
    monkeypatch.setattr(
        review_queue,
        "_load_strategy_artifact_topn_rows",
        lambda **kwargs: [
            {"trade_date": "2026-07-18", "asset_id": "A", "strategy_id": "mid_trend"}
        ],
    )
    monkeypatch.setattr(
        review_queue,
        "_load_db_strategy_position_rows",
        lambda **kwargs: [
            {"trade_date": "2026-07-18", "asset_id": "B", "strategy_id": "lhb_shortline"}
        ],
    )
    monkeypatch.setattr(review_queue, "_load_asset_names", lambda asset_ids: {})

    assert review_queue.load_active_strategy_topn_rows(trade_date="2026-07-18", limit=50) == []
    assert calls == 1

    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda **kwargs: {"latest_market_date": "2026-07-18"},
    )
    monkeypatch.setattr(
        review_queue,
        "_load_strategy_snapshot_rows",
        lambda **kwargs: [
            {"trade_date": "2026-07-18", "asset_id": "C", "strategy_id": "tech_bottleneck", "rank": 1}
        ],
    )
    monkeypatch.setattr(review_queue, "load_top_scores_for_dashboard", lambda *args, **kwargs: [])
    calls = 0

    assert review_queue.build_review_queue(trade_date="2026-07-18")["review_mode"] == "score_topn"
    assert calls == 1


def test_successful_legacy_manifest_without_publication_declarations_is_rejected(
    tmp_path, monkeypatch
):
    artifact = tmp_path / "strategy_mid_trend_review.csv"
    artifact.write_text(
        "trade_date,asset_id,rank,strategy_id\n2026-07-18,CN:SH:600002,1,mid_trend\n",
        encoding="utf-8",
    )
    module = {
        "module": "strategy_mid_trend",
        "status": "success",
        "trade_date": "2026-07-18",
        "run_id": "legacy-r1",
        "artifact_path": str(artifact),
        "metadata": {},
    }
    monkeypatch.setattr(review_queue, "load_latest_data_run_manifest", lambda trade_date: [module])

    rows = review_queue._load_manifest_strategy_rows(trade_date="2026-07-18", limit=50)

    assert rows == []

@pytest.mark.parametrize("status", ("failed", "partial", "skipped"))
def test_non_success_current_manifest_blocks_root_and_snapshot_fallbacks(
    status, tmp_path, monkeypatch
):
    module = _v1_versioned_manifest(tmp_path)
    module.update({"status": status, "trade_date": "2026-07-18", "run_id": "r1"})
    calls = 0

    def load_manifest(*, trade_date):
        nonlocal calls
        calls += 1
        return [module]

    monkeypatch.setattr(review_queue, "load_latest_data_run_manifest", load_manifest)
    monkeypatch.setattr(review_queue, "_load_strategy_artifact_topn_rows", lambda **kwargs: [
        {"trade_date": "2026-07-18", "asset_id": "A", "strategy_id": "mid_trend"}
    ])
    monkeypatch.setattr(review_queue, "_load_db_strategy_position_rows", lambda **kwargs: [])
    monkeypatch.setattr(review_queue, "_load_asset_names", lambda asset_ids: {})

    assert review_queue.load_active_strategy_topn_rows(trade_date="2026-07-18", limit=50) == []
    assert calls == 1

    monkeypatch.setattr(review_queue, "load_platform_summary", lambda **kwargs: {"latest_market_date": "2026-07-18"})
    monkeypatch.setattr(review_queue, "_load_strategy_snapshot_rows", lambda **kwargs: [
        {"trade_date": "2026-07-18", "asset_id": "A", "strategy_id": "mid_trend", "rank": 1}
    ])
    monkeypatch.setattr(review_queue, "load_top_scores_for_dashboard", lambda *args, **kwargs: [])
    calls = 0

    assert review_queue.build_review_queue(trade_date="2026-07-18")["review_mode"] == "score_topn"
    assert calls == 1
