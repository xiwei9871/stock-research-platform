from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import review_queue


def _score(asset_id, rank, score_total=80.0):
    return {
        "trade_date": "2026-06-08",
        "asset_id": asset_id,
        "rank": rank,
        "score_total": score_total,
        "score_version": "manual_v1",
        "score_components": {},
    }


def _strategy_position(asset_id, rank, strategy_id="mid_trend", strategy_name="Mid Trend Combo"):
    return {
        "trade_date": "2026-06-12",
        "asset_id": asset_id,
        "rank": rank,
        "score_total": 90.0 - rank,
        "score_version": "strategy_topn",
        "score_components": {},
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "strategy_run_id": f"{strategy_id}:run",
        "source_type": "strategy_topn",
        "source_name": strategy_name,
        "source_rank": rank,
        "review_tier": "top5_focus" if rank <= 5 else "top10_watch",
    }


def _digest(asset_id, *, bucket="strong", score=80, facts=None, risks=None, warnings=None):
    return {
        "asset_id": asset_id,
        "canonical_asset_id": asset_id,
        "trade_date": "2026-06-08",
        "title": f"{bucket} evidence",
        "score": score,
        "bucket": bucket,
        "facts": facts
        if facts is not None
        else [
            {"kind": "strategy", "label": "TopN candidate"},
            {"kind": "news", "label": "Recent news"},
        ],
        "risk_flags": risks or [],
        "source_refs": {"strategy_asset_id": asset_id},
        "next_actions": [
            {
                "key": "review_stock",
                "label": "Review Stock",
                "workspace": "stock",
                "asset_id": asset_id,
                "query": asset_id,
            },
            {
                "key": "open_news",
                "label": "Open News",
                "workspace": "news",
                "asset_id": asset_id,
                "query": asset_id,
            },
        ],
        "warnings": warnings or [],
    }


def test_build_review_queue_defaults_to_active_strategy_top10_groups(monkeypatch):
    rows = [
        _strategy_position("CN:SZ:000001", 1, strategy_id="mid_trend", strategy_name="Mid Trend Combo"),
        _strategy_position("CN:SZ:000002", 6, strategy_id="mid_trend", strategy_name="Mid Trend Combo"),
        _strategy_position("CN:SH:600001", 1, strategy_id="tech_bottleneck", strategy_name="Tech Bottleneck Combo"),
    ]
    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda **kwargs: {"latest_market_date": "2026-06-12", "topn_preview": [_score("LEGACY.SZ", 1, 99)]},
    )
    monkeypatch.setattr(
        review_queue,
        "load_active_strategy_topn_rows",
        lambda *, trade_date, limit: rows,
        raising=False,
    )
    monkeypatch.setattr(
        review_queue,
        "build_evidence_digest",
        lambda asset_id, **kwargs: _digest(asset_id, bucket="strong", score=88),
    )

    payload = review_queue.build_review_queue(trade_date=None, limit=10)

    assert payload["review_mode"] == "strategy_topn"
    assert payload["score_version"] == "strategy_topn"
    assert payload["trade_date"] == "2026-06-12"
    assert [group["bucket"] for group in payload["groups"]] == ["strategy:mid_trend", "strategy:tech_bottleneck"]
    assert payload["groups"][0]["label"] == "Mid Trend Combo"
    assert [item["asset_id"] for item in payload["groups"][0]["items"]] == ["CN:SZ:000001", "CN:SZ:000002"]
    assert payload["groups"][0]["items"][0]["review_tier"] == "top5_focus"
    assert payload["groups"][0]["items"][1]["review_tier"] == "top10_watch"
    assert payload["groups"][0]["items"][0]["source_type"] == "strategy_topn"
    assert payload["groups"][0]["items"][0]["strategy_id"] == "mid_trend"
    assert payload["groups"][0]["items"][0]["strategy_run_id"] == "mid_trend:run"


def test_build_review_queue_defaults_to_display_gate_date(monkeypatch):
    captured: dict[str, object] = {}
    rows = [
        {
            **_strategy_position("CN:SZ:000001", 1, strategy_id="mid_trend", strategy_name="Mid Trend Combo"),
            "trade_date": "2026-06-17",
        }
    ]
    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda **kwargs: {"latest_market_date": "2026-06-18", "latest_score_date": "2026-06-18", "topn_preview": []},
    )
    monkeypatch.setattr(review_queue, "load_latest_data_run_manifest", lambda: [{"trade_date": "2026-06-18"}])
    monkeypatch.setattr(
        review_queue,
        "select_display_date",
        lambda modules, latest_market_date: {
            "display_trade_date": "2026-06-17",
            "candidate_trade_date": latest_market_date,
            "display_status": "ready",
        },
    )

    def fake_strategy_rows(*, trade_date, limit):
        captured["trade_date"] = trade_date
        captured["limit"] = limit
        return rows

    monkeypatch.setattr(review_queue, "load_active_strategy_topn_rows", fake_strategy_rows, raising=False)

    payload = review_queue.build_review_queue(trade_date=None, limit=10)

    assert captured == {"trade_date": "2026-06-17", "limit": 10}
    assert payload["trade_date"] == "2026-06-17"
    assert payload["groups"][0]["items"][0]["asset_id"] == "CN:SZ:000001"


def test_build_review_queue_strategy_mode_uses_lightweight_digest(monkeypatch):
    rows = [_strategy_position("CN:SZ:000001", 1, strategy_id="mid_trend", strategy_name="Mid Trend Combo")]
    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda **kwargs: {"latest_market_date": "2026-06-12", "topn_preview": []},
    )
    monkeypatch.setattr(review_queue, "load_active_strategy_topn_rows", lambda *, trade_date, limit: rows, raising=False)

    def fail_full_digest(*args, **kwargs):
        raise AssertionError("strategy review list should not block on full evidence digest")

    monkeypatch.setattr(review_queue, "build_evidence_digest", fail_full_digest)

    payload = review_queue.build_review_queue(trade_date=None, limit=10)

    item = payload["groups"][0]["items"][0]
    assert item["digest"]["title"] == "Mid Trend Combo Top5 重点复盘"
    assert item["source_kinds"] == ["strategy"]
    assert item["next_action_count"] == 1


def test_build_review_queue_strategy_mode_keeps_lhb_and_meaningful_review_metrics(monkeypatch):
    rows = [
        {
            **_strategy_position("CN:SH:600198", 1, strategy_id="lhb_shortline", strategy_name="LHB Shortline Combo"),
            "trade_date": "2026-06-05",
            "stock_name": "金钼股份",
            "score_total": 10.0,
            "source_type": "strategy_artifact",
            "review_tier": "top5_focus",
            "review_notes": ["龙虎榜候选：follow_pool_core"],
            "risk_flags": [{"key": "filled_trade_loss", "label": "最近成交回撤 -1.1%", "severity": "warning"}],
        },
        {
            **_strategy_position("CN:SZ:300951", 1, strategy_id="mid_trend", strategy_name="Mid Trend Combo"),
            "trade_date": "2026-06-02",
            "score_total": 73.76,
            "review_notes": ["中趋势候选：pullback_reacceleration_watch"],
            "warnings": ["完整新闻/研报证据未在列表页展开"],
        },
        {
            **_strategy_position("CN:SZ:300408", 1, strategy_id="tech_bottleneck", strategy_name="Tech Bottleneck Combo"),
            "trade_date": "2026-06-04",
            "score_total": 65.0,
            "review_notes": ["技术瓶颈排名 #1"],
        },
    ]
    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda **kwargs: {"latest_market_date": "2026-06-12", "topn_preview": []},
    )
    monkeypatch.setattr(review_queue, "load_active_strategy_topn_rows", lambda *, trade_date, limit: rows, raising=False)

    payload = review_queue.build_review_queue(trade_date=None, limit=10)

    assert payload["trade_date"] == "2026-06-05"
    assert any("策略复盘数据最新日期 2026-06-05" in warning for warning in payload["warnings"])
    assert any("Mid Trend Combo 复盘数据最新日期 2026-06-02" in warning for warning in payload["warnings"])
    assert any("Tech Bottleneck Combo 复盘数据最新日期 2026-06-04" in warning for warning in payload["warnings"])
    labels = [group["label"] for group in payload["groups"]]
    assert labels == ["LHB Shortline Combo", "Mid Trend Combo", "Tech Bottleneck Combo"]
    lhb = payload["groups"][0]["items"][0]
    assert lhb["display_name"] == "金钼股份"
    assert lhb["stock_code"] == "CN:SH:600198"
    assert lhb["stock_name"] == "金钼股份"
    assert lhb["score"] == 10.0
    assert lhb["risk_count"] == 1
    assert lhb["warning_count"] >= 1
    assert "龙虎榜候选" in lhb["digest"]["facts"][1]["label"]
    assert lhb["digest"]["next_actions"][0]["asset_id"] == "CN:SH:600198"
    assert lhb["digest"]["next_actions"][0]["query"] == "金钼股份"
    mid = payload["groups"][1]["items"][0]
    assert mid["score"] == 73.76
    assert mid["warning_count"] >= 1
    tech = payload["groups"][2]["items"][0]
    assert tech["score"] == 65.0
    assert tech["digest"]["facts"][1]["label"] == "技术瓶颈排名 #1"


def test_load_active_strategy_topn_rows_prefers_newer_db_rows_over_stale_artifacts(monkeypatch):
    artifact_rows = [
        {
            **_strategy_position("CN:SZ:000001", 1, strategy_id="mid_trend", strategy_name="Mid Trend Combo"),
            "trade_date": "2026-06-05",
            "source_type": "strategy_artifact",
        },
        {
            **_strategy_position(
                "CN:SH:600198",
                1,
                strategy_id="lhb_shortline",
                strategy_name="LHB Shortline Combo",
            ),
            "trade_date": "2026-06-15",
            "source_type": "strategy_artifact",
        },
    ]
    db_rows = [
        {
            **_strategy_position("CN:SZ:300951", 1, strategy_id="mid_trend", strategy_name="Mid Trend Combo"),
            "trade_date": "2026-06-15",
            "source_type": "strategy_topn",
        },
        {
            **_strategy_position(
                "CN:SH:600519",
                1,
                strategy_id="tech_bottleneck",
                strategy_name="Tech Bottleneck Combo",
            ),
            "trade_date": "2026-06-14",
            "source_type": "strategy_topn",
        },
    ]
    monkeypatch.setattr(review_queue, "_load_strategy_artifact_topn_rows", lambda *, trade_date, limit: artifact_rows)
    monkeypatch.setattr(review_queue, "_load_db_strategy_position_rows", lambda *, trade_date, limit: db_rows)
    monkeypatch.setattr(review_queue, "_load_live_strategy_score_rows", lambda *, trade_date, limit: [])
    monkeypatch.setattr(review_queue, "_attach_asset_names", lambda rows: rows)

    rows = review_queue.load_active_strategy_topn_rows(trade_date="2026-06-15", limit=10)

    assert [(row["strategy_id"], row["asset_id"], row["trade_date"], row["source_type"]) for row in rows] == [
        ("mid_trend", "CN:SZ:300951", "2026-06-15", "strategy_topn"),
        ("lhb_shortline", "CN:SH:600198", "2026-06-15", "strategy_artifact"),
        ("tech_bottleneck", "CN:SH:600519", "2026-06-14", "strategy_topn"),
    ]


def test_load_active_strategy_topn_rows_rejects_live_score_fallback_for_strategy_review(monkeypatch):
    artifact_rows = [
        {
            **_strategy_position("CN:SZ:000001", 1, strategy_id="mid_trend", strategy_name="Mid Trend Combo"),
            "trade_date": "2026-06-02",
            "source_type": "strategy_artifact",
        }
    ]
    db_rows = [
        {
            **_strategy_position("CN:SZ:000002", 1, strategy_id="mid_trend", strategy_name="Mid Trend Combo"),
            "trade_date": "2026-05-18",
            "source_type": "strategy_topn",
        }
    ]
    live_rows = [
        {
            **_strategy_position("CN:SZ:300951", 1, strategy_id="mid_trend", strategy_name="Mid Trend Combo"),
            "trade_date": "2026-06-15",
            "source_type": "strategy_live_score",
        }
    ]
    monkeypatch.setattr(review_queue, "_load_strategy_artifact_topn_rows", lambda *, trade_date, limit: artifact_rows)
    monkeypatch.setattr(review_queue, "_load_db_strategy_position_rows", lambda *, trade_date, limit: db_rows)
    monkeypatch.setattr(review_queue, "_load_live_strategy_score_rows", lambda *, trade_date, limit: live_rows)
    monkeypatch.setattr(review_queue, "_attach_asset_names", lambda rows: rows)

    rows = review_queue.load_active_strategy_topn_rows(trade_date="2026-06-15", limit=10)

    assert [(row["strategy_id"], row["asset_id"], row["trade_date"], row["source_type"]) for row in rows] == [
        ("mid_trend", "CN:SZ:000001", "2026-06-02", "strategy_artifact"),
    ]


def test_load_active_strategy_topn_rows_reads_manifest_strategy_artifacts(monkeypatch, tmp_path):
    artifact = tmp_path / "mid_trend_review.csv"
    artifact.write_text(
        "\n".join(
            [
                "trade_date,asset_id,rank,score_total,strategy_id,strategy_name,source_type,stock_name,review_notes,warnings",
                '2026-06-16,CN:SZ:300951,1,88.5,mid_trend,Mid Trend Combo,strategy_manifest,博硕科技,"[""真实执行""]","[]"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        review_queue,
        "load_latest_data_run_manifest",
        lambda *, trade_date: [
            {
                "module": "strategy_mid_trend",
                "status": "success",
                "artifact_path": str(artifact),
                "latest_trade_date": trade_date,
                "run_id": "strategy-eod-2026-06-16-local",
            }
        ],
    )
    monkeypatch.setattr(review_queue, "_load_strategy_artifact_topn_rows", lambda *, trade_date, limit: [])
    monkeypatch.setattr(review_queue, "_load_db_strategy_position_rows", lambda *, trade_date, limit: [])
    monkeypatch.setattr(review_queue, "_attach_asset_names", lambda rows: rows)

    rows = review_queue.load_active_strategy_topn_rows(trade_date="2026-06-16", limit=10)

    assert [(row["strategy_id"], row["asset_id"], row["trade_date"], row["source_type"]) for row in rows] == [
        ("mid_trend", "CN:SZ:300951", "2026-06-16", "strategy_manifest")
    ]
    assert rows[0]["stock_name"] == "博硕科技"
    assert rows[0]["review_notes"] == ["真实执行"]


def test_load_active_strategy_topn_rows_skips_contract_mismatched_manifest(monkeypatch, tmp_path):
    artifact = tmp_path / "mid_trend_review.csv"
    artifact.write_text(
        "\n".join(
            [
                "trade_date,asset_id,rank,strategy_id,strategy_name,source_type,stock_name",
                "2026-06-17,CN:SH:601963,1,mid_trend,Mid Trend Combo,strategy_manifest,重庆银行",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    class Contract:
        strategy_id = "mid_trend"
        profile = "balanced"
        engine = "mid_trend_v1"
        variant = "top5_weekly_max_2_replacements"
        top_n = 5
        frequency = "weekly"
        protection_name = None
        transaction_cost_bps = 20.0
        adjust_type = "hfq"
        contract_id = "mid_trend:balanced:test"

    monkeypatch.setattr(review_queue, "load_strategy_contracts", lambda profile="balanced": {"mid_trend": Contract()})
    monkeypatch.setattr(
        review_queue,
        "load_latest_data_run_manifest",
        lambda *, trade_date: [
            {
                "module": "strategy_mid_trend",
                "status": "success",
                "artifact_path": str(artifact),
                "latest_trade_date": trade_date,
                "run_id": "strategy-eod-2026-06-17-local",
                "metadata": {
                    "summary": {
                        "engine_version": "mid_trend_v1",
                        "variant_name": "old_wrong_variant",
                        "top_n": 5,
                        "transaction_cost_bps": 20.0,
                        "adjust_type": "hfq",
                        "frequency": "weekly",
                    }
                },
            }
        ],
    )
    monkeypatch.setattr(review_queue, "_load_strategy_artifact_topn_rows", lambda *, trade_date, limit: [])
    monkeypatch.setattr(review_queue, "_load_db_strategy_position_rows", lambda *, trade_date, limit: [])
    monkeypatch.setattr(review_queue, "_attach_asset_names", lambda rows: rows)

    rows = review_queue.load_active_strategy_topn_rows(trade_date="2026-06-17", limit=10)

    assert rows == []


def test_load_manifest_strategy_rows_rejects_stale_tech_candidate_snapshot(monkeypatch, tmp_path):
    artifact = tmp_path / "tech_bottleneck_review.csv"
    artifact.write_text(
        "\n".join(
            [
                "trade_date,asset_id,rank,score_total,strategy_id,strategy_name,source_type,stock_name",
                "2026-06-18,CN:SZ:300408,1,0.6375,tech_bottleneck,Tech Bottleneck Combo,strategy_manifest,三环集团",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        review_queue,
        "load_latest_data_run_manifest",
        lambda *, trade_date: [
            {
                "module": "strategy_tech_bottleneck",
                "status": "success",
                "artifact_path": str(artifact),
                "trade_date": "2026-06-18",
                "latest_trade_date": "2026-06-18",
                "run_id": "strategy-eod-2026-06-18-local",
                "metadata": {
                    "candidate_snapshot_latest_date": "2026-06-17",
                },
            }
        ],
    )

    rows = review_queue._load_manifest_strategy_rows(trade_date="2026-06-18", limit=10)

    assert rows == []


def test_load_manifest_strategy_rows_rejects_missing_tech_candidate_snapshot(monkeypatch, tmp_path):
    artifact = tmp_path / "tech_bottleneck_review.csv"
    artifact.write_text(
        "\n".join(
            [
                "trade_date,asset_id,rank,score_total,strategy_id,strategy_name,source_type,stock_name",
                "2026-06-18,CN:SZ:300408,1,0.6375,tech_bottleneck,Tech Bottleneck Combo,strategy_manifest,三环集团",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        review_queue,
        "load_latest_data_run_manifest",
        lambda *, trade_date: [
            {
                "module": "strategy_tech_bottleneck",
                "status": "success",
                "artifact_path": str(artifact),
                "trade_date": "2026-06-18",
                "latest_trade_date": "2026-06-18",
                "run_id": "strategy-eod-2026-06-18-local",
                "metadata": {},
            }
        ],
    )

    rows = review_queue._load_manifest_strategy_rows(trade_date="2026-06-18", limit=10)

    assert rows == []


def test_manifest_strategy_artifacts_normalize_strategy_scores(monkeypatch, tmp_path):
    artifact = tmp_path / "strategy_review.csv"
    artifact.write_text(
        "\n".join(
            [
                "trade_date,asset_id,rank,score_total,strategy_id,strategy_name,source_type,stock_name",
                "2026-06-17,CN:SZ:002636,1,,lhb_shortline,LHB Shortline Combo,strategy_manifest,金安国纪",
                "2026-06-17,CN:SH:601963,2,,mid_trend,Mid Trend Combo,strategy_manifest,重庆银行",
                "2026-06-17,CN:SZ:300408,1,0.6375,tech_bottleneck,Tech Bottleneck Combo,strategy_manifest,三环集团",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        review_queue,
        "load_latest_data_run_manifest",
        lambda *, trade_date: [
            {
                "module": "review_queue_strategy_manifest",
                "status": "success",
                "artifact_path": str(tmp_path),
                "latest_trade_date": trade_date,
                "run_id": "strategy-eod-2026-06-17-local",
            },
            {
                "module": "strategy_lhb_shortline",
                "status": "success",
                "artifact_path": str(artifact),
                "latest_trade_date": trade_date,
                "run_id": "strategy-eod-2026-06-17-local",
            },
        ],
    )
    monkeypatch.setattr(review_queue, "_load_strategy_artifact_topn_rows", lambda *, trade_date, limit: [])
    monkeypatch.setattr(review_queue, "_load_db_strategy_position_rows", lambda *, trade_date, limit: [])
    monkeypatch.setattr(review_queue, "_attach_asset_names", lambda rows: rows)

    rows = review_queue.load_active_strategy_topn_rows(trade_date="2026-06-17", limit=10)

    by_asset = {row["asset_id"]: row for row in rows}
    assert by_asset["CN:SZ:002636"]["score_total"] is None
    assert by_asset["CN:SH:601963"]["score_total"] is None
    assert by_asset["CN:SZ:300408"]["score_total"] == 63.75
    assert by_asset["CN:SZ:002636"]["score_source"] is None
    assert by_asset["CN:SZ:300408"]["score_source"] == "bottleneck_score"


def test_build_review_queue_groups_all_buckets_and_sorts(monkeypatch):
    score_rows = [
        _score("000003.SZ", 3, 70),
        _score("000001.SZ", 1, 90),
        _score("000002.SZ", 2, 60),
    ]
    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda **kwargs: {
            "latest_market_date": "2026-06-08",
            "topn_preview": score_rows,
        },
    )
    monkeypatch.setattr(review_queue, "load_top_scores_for_dashboard", lambda *args: score_rows)
    digests = {
        "000001.SZ": _digest("000001.SZ", bucket="mixed", score=62),
        "000002.SZ": _digest("000002.SZ", bucket="strong", score=81),
        "000003.SZ": _digest("000003.SZ", bucket="thin", score=30, facts=[]),
    }
    monkeypatch.setattr(review_queue, "build_evidence_digest", lambda asset_id, **kwargs: digests[asset_id])

    payload = review_queue.build_review_queue(
        trade_date="2026-06-08", score_version="manual_v1", limit=20, review_mode="score_topn"
    )

    assert payload["trade_date"] == "2026-06-08"
    assert [group["bucket"] for group in payload["groups"]] == ["strong", "mixed", "risk_heavy", "thin"]
    assert [group["count"] for group in payload["groups"]] == [1, 1, 0, 1]
    strong_item = payload["groups"][0]["items"][0]
    assert strong_item["queue_id"] == "2026-06-08:manual_v1:000002.SZ"
    assert strong_item["rank"] == 2
    assert strong_item["score"] == 60.0
    assert strong_item["digest_title"] == "strong evidence"
    assert strong_item["source_kinds"] == ["strategy", "news"]
    assert strong_item["next_action_count"] == 2


def test_build_review_queue_item_includes_lineage_and_evidence_status(monkeypatch):
    score_rows = [
        {
            "trade_date": "2026-06-12",
            "asset_id": "000001.SZ",
            "rank": 3,
            "score_total": 88.5,
            "score_version": "manual_v1",
            "score_components": {"momentum": 0.62, "quality": 0.26},
        }
    ]
    digest = _digest("000001.SZ", bucket="mixed", score=88, warnings=["research report source partial"])
    digest.update(
        {
            "latest_trade_date": "2026-06-12",
            "run_id": "eod-2026-06-12-local",
            "digest_key": "2026-06-12:manual_v1:000001.SZ",
            "overall_status": "PARTIAL",
            "missing_evidence": ["research_reports"],
            "partial_evidence": ["news"],
            "lineage": {
                "run_id": "eod-2026-06-12-local",
                "latest_trade_date": "2026-06-12",
                "score_version": "manual_v1",
                "topn_rank": 3,
                "factor_as_of": "2026-06-12",
                "manifest_modules": [{"module": "news", "tier": "tier2", "status": "partial"}],
            },
        }
    )
    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda **kwargs: {"latest_market_date": "2026-06-12", "topn_preview": score_rows},
    )
    monkeypatch.setattr(review_queue, "load_top_scores_for_dashboard", lambda *args: score_rows)
    monkeypatch.setattr(review_queue, "build_evidence_digest", lambda asset_id, **kwargs: digest)
    monkeypatch.setattr(
        review_queue,
        "load_latest_data_run_manifest",
        lambda trade_date=None: [
            {
                "run_id": "eod-2026-06-12-local",
                "trade_date": "2026-06-12",
                "latest_trade_date": "2026-06-12",
                "module": "score_topn",
                "tier": "tier1",
                "status": "success",
                "warnings": [],
            }
        ],
        raising=False,
    )

    payload = review_queue.build_review_queue(
        trade_date="2026-06-12", score_version="manual_v1", limit=20, review_mode="score_topn"
    )

    item = payload["groups"][1]["items"][0]
    assert item["run_id"] == "eod-2026-06-12-local"
    assert item["latest_trade_date"] == "2026-06-12"
    assert item["generated_at"] == "2026-06-12T00:00:00+00:00"
    assert item["source_type"] == "score_topn"
    assert item["source_name"] == "manual_v1_topn"
    assert item["source_rank"] == 3
    assert item["topn_rank"] == 3
    assert item["score_components"] == {"momentum": 0.62, "quality": 0.26}
    assert item["strategy_name"] is None
    assert item["strategy_run_id"] is None
    assert item["factor_as_of"] == "2026-06-12"
    assert item["digest_key"] == "2026-06-12:manual_v1:000001.SZ"
    assert item["digest_url_path"].startswith("/api/evidence-digest?")
    assert "asset_id=000001.SZ" in item["digest_url_path"]
    assert item["stock_workspace_url_path"] == "/stock/000001.SZ?trade_date=2026-06-12"
    assert item["evidence_status"] == "PARTIAL"
    assert item["missing_evidence"] == ["research_reports"]
    assert item["partial_evidence"] == ["news"]
    assert item["missing_evidence_count"] == 1
    assert item["partial_evidence_count"] == 1
    assert item["warnings_count"] >= 2
    assert item["manifest_modules"] == [{"module": "news", "tier": "tier2", "status": "partial"}]
    assert any("strategy_run_id unavailable" in warning for warning in item["warnings"])


def test_build_review_queue_loads_scores_for_explicit_trade_date(monkeypatch):
    captured = {"top_scores": None, "digest": []}

    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda **kwargs: {
            "latest_market_date": "2026-06-08",
            "latest_score_date": "2026-06-08",
            "topn_preview": [_score("LATEST.SZ", 1, 99)],
        },
    )

    def fake_top_scores(trade_date, score_version, top_n):
        captured["top_scores"] = (trade_date, score_version, top_n)
        return [
            {
                "trade_date": trade_date,
                "asset_id": "HISTORICAL.SZ",
                "rank": 1,
                "score_total": 88.0,
                "score_version": score_version,
                "score_components": {},
            }
        ]

    def fake_digest(asset_id, **kwargs):
        captured["digest"].append((asset_id, kwargs["trade_date"]))
        return _digest(asset_id, bucket="strong", score=88)

    monkeypatch.setattr(review_queue, "load_top_scores_for_dashboard", fake_top_scores, raising=False)
    monkeypatch.setattr(review_queue, "build_evidence_digest", fake_digest)

    payload = review_queue.build_review_queue(
        trade_date="2026-06-01", score_version="manual_v1", limit=20, review_mode="score_topn"
    )

    assert captured["top_scores"] == ("2026-06-01", "manual_v1", 20)
    assert payload["groups"][0]["items"][0]["asset_id"] == "HISTORICAL.SZ"
    assert captured["digest"] == [("HISTORICAL.SZ", "2026-06-01")]


def test_build_review_queue_is_deterministic_for_same_eod_inputs(monkeypatch):
    monkeypatch.setattr(review_queue, "load_latest_data_run_manifest", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda **kwargs: {"latest_market_date": "2026-06-08", "topn_preview": [_score("000001.SZ", 1, 90)]},
    )
    monkeypatch.setattr(
        review_queue,
        "build_evidence_digest",
        lambda asset_id, **kwargs: _digest(asset_id, bucket="strong", score=88),
    )

    first = review_queue.build_review_queue(trade_date=None, score_version="manual_v1", limit=20, review_mode="score_topn")
    second = review_queue.build_review_queue(trade_date=None, score_version="manual_v1", limit=20, review_mode="score_topn")

    assert first == second
    assert first["generated_at"] == "2026-06-08T00:00:00+00:00"


def test_build_review_queue_degrades_digest_failure_to_thin_item(monkeypatch):
    score_rows = [_score("000001.SZ", 1, 90)]
    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda **kwargs: {"latest_market_date": "2026-06-08", "topn_preview": score_rows},
    )
    monkeypatch.setattr(review_queue, "load_top_scores_for_dashboard", lambda *args: score_rows)

    def fail_digest(asset_id, **kwargs):
        raise RuntimeError("digest unavailable")

    monkeypatch.setattr(review_queue, "build_evidence_digest", fail_digest)

    payload = review_queue.build_review_queue(
        trade_date="2026-06-08", score_version="manual_v1", limit=20, review_mode="score_topn"
    )

    thin = next(group for group in payload["groups"] if group["bucket"] == "thin")
    assert thin["count"] == 1
    item = thin["items"][0]
    assert item["asset_id"] == "000001.SZ"
    assert item["warning_count"] == 1
    assert "digest unavailable" in item["digest"]["warnings"][0]
    assert any("digest unavailable" in warning for warning in payload["warnings"])


def test_build_review_queue_bounds_limit_and_uses_latest_market_date(monkeypatch):
    captured = {}
    monkeypatch.setattr(review_queue, "load_latest_data_run_manifest", lambda *args, **kwargs: [])

    def fake_summary(**kwargs):
        captured.update(kwargs)
        return {"latest_market_date": "2026-06-08", "topn_preview": []}

    monkeypatch.setattr(review_queue, "load_platform_summary", fake_summary)

    payload = review_queue.build_review_queue(
        trade_date=None, score_version="manual_v1", limit=999, lookback_days=999, review_mode="score_topn"
    )

    assert captured["top_n"] == 50
    assert payload["trade_date"] == "2026-06-08"
    assert payload["warnings"] == []


def test_build_review_queue_bounds_lower_limit_and_upper_lookback_for_digest(monkeypatch):
    captured = {"summary": None, "digest": None}

    def fake_summary(**kwargs):
        captured["summary"] = kwargs
        return {"latest_market_date": "2026-06-08", "topn_preview": [_score("000001.SZ", 1, 90)]}

    def fake_digest(asset_id, **kwargs):
        captured["digest"] = kwargs
        return _digest(asset_id)

    monkeypatch.setattr(review_queue, "load_platform_summary", fake_summary)
    monkeypatch.setattr(review_queue, "build_evidence_digest", fake_digest)

    review_queue.build_review_queue(
        trade_date=None, score_version="manual_v1", limit=0, lookback_days=999, review_mode="score_topn"
    )

    assert captured["summary"]["top_n"] == 1
    assert captured["digest"]["lookback_days"] == 365


def test_build_review_queue_uses_latest_score_date_when_market_date_missing(monkeypatch):
    captured = {}
    monkeypatch.setattr(review_queue, "load_latest_data_run_manifest", lambda *args, **kwargs: [])

    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda **kwargs: {"latest_score_date": "2026-06-07", "topn_preview": [_score("000001.SZ", 1, 90)]},
    )

    def fake_digest(asset_id, **kwargs):
        captured.update(kwargs)
        return _digest(asset_id)

    monkeypatch.setattr(review_queue, "build_evidence_digest", fake_digest)

    payload = review_queue.build_review_queue(trade_date=None, score_version="manual_v1", review_mode="score_topn")

    assert payload["trade_date"] == "2026-06-07"
    assert captured["trade_date"] == "2026-06-07"


def test_build_review_queue_uses_empty_trade_date_when_summary_has_no_dates(monkeypatch):
    captured = {}
    monkeypatch.setattr(review_queue, "load_latest_data_run_manifest", lambda *args, **kwargs: [])

    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda **kwargs: {"topn_preview": [_score("000001.SZ", 1, 90)]},
    )

    def fake_digest(asset_id, **kwargs):
        captured.update(kwargs)
        return _digest(asset_id)

    monkeypatch.setattr(review_queue, "build_evidence_digest", fake_digest)

    payload = review_queue.build_review_queue(trade_date=None, score_version="manual_v1", review_mode="score_topn")

    assert payload["trade_date"] == ""
    assert payload["generated_at"] == ""
    assert captured["trade_date"] == ""


def test_review_queue_endpoint_forwards_query(monkeypatch):
    captured = {}

    def fake_queue(*, trade_date=None, score_version="manual_v1", limit=20, lookback_days=90):
        captured.update(
            {
                "trade_date": trade_date,
                "score_version": score_version,
                "limit": limit,
                "lookback_days": lookback_days,
            }
        )
        return {"trade_date": trade_date, "score_version": score_version, "generated_at": "", "groups": [], "warnings": []}

    monkeypatch.setattr(dashboard_app, "build_review_queue", fake_queue)
    client = TestClient(dashboard_app.app)

    response = client.get(
        "/api/review-queue",
        params={"trade_date": "2026-06-08", "score_version": "manual_v2", "limit": 12, "lookback_days": 45},
    )

    assert response.status_code == 200
    assert captured == {
        "trade_date": "2026-06-08",
        "score_version": "manual_v2",
        "limit": 12,
        "lookback_days": 45,
    }
