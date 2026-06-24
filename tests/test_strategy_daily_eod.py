import json

import pandas as pd

from stock_research import strategy_daily_eod_store


def test_build_status_payload_returns_expected_fields():
    payload = strategy_daily_eod_store.build_status_payload(
        trade_date="2026-06-24",
        status="running",
        dependency_check_status="success",
        lhb_shortline_status="running",
        mid_trend_status="skipped",
        tech_bottleneck_status="failed",
        review_rows=12,
        output_dir="/tmp/eod",
        summary_path="/tmp/eod/summary.md",
        error_summary="mid trend source timeout",
    )

    assert payload == {
        "trade_date": "2026-06-24",
        "status": "running",
        "dependency_check_status": "success",
        "lhb_shortline_status": "running",
        "mid_trend_status": "skipped",
        "tech_bottleneck_status": "failed",
        "review_rows": 12,
        "output_dir": "/tmp/eod",
        "summary_path": "/tmp/eod/summary.md",
        "error_summary": "mid trend source timeout",
    }

    assert strategy_daily_eod_store.build_status_payload.__annotations__["review_rows"] is int


def test_strategy_daily_eod_status_schema_contains_expected_columns():
    sql = strategy_daily_eod_store.STRATEGY_DAILY_EOD_STATUS_SQL.lower()

    assert "create table if not exists ops.strategy_daily_eod_status" in sql
    assert "trade_date date primary key" in sql
    assert "status text not null check (status in ('success', 'failed', 'running', 'skipped'))" in sql
    assert "dependency_check_status text not null check (dependency_check_status in ('success', 'failed', 'running', 'skipped'))" in sql
    assert "review_rows integer not null default 0" in sql
    assert "output_dir text" in sql
    assert "summary_path text" in sql
    assert "error_summary text" in sql
    assert "updated_at timestamptz not null default now()" in sql
    assert "lhb_shortline_status text not null" in sql
    assert "lhb_shortline_status in ('success', 'failed', 'running', 'skipped')" in sql
    assert "mid_trend_status text not null" in sql
    assert "mid_trend_status in ('success', 'failed', 'running', 'skipped')" in sql
    assert "tech_bottleneck_status text not null" in sql
    assert "tech_bottleneck_status in ('success', 'failed', 'running', 'skipped')" in sql


class _Connection:
    pass


class _Context:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


def test_apply_strategy_daily_eod_status_schema_executes_schema_sql(monkeypatch):
    conn = _Connection()
    calls: list[tuple[object, str]] = []

    monkeypatch.setattr(strategy_daily_eod_store, "connect", lambda service: _Context(conn))
    monkeypatch.setattr(
        strategy_daily_eod_store,
        "execute",
        lambda passed_conn, sql: calls.append((passed_conn, sql)),
    )

    strategy_daily_eod_store.apply_strategy_daily_eod_status_schema()

    assert calls == [(conn, strategy_daily_eod_store.STRATEGY_DAILY_EOD_STATUS_SQL)]


def test_run_strategy_daily_eod_returns_failed_when_dependency_check_fails(tmp_path, monkeypatch):
    from stock_research import strategy_daily_eod

    apply_calls: list[str] = []
    monkeypatch.setattr(
        strategy_daily_eod,
        "apply_strategy_daily_eod_status_schema",
        lambda: apply_calls.append("called"),
    )

    result = strategy_daily_eod.run_strategy_daily_eod(
        trade_date="2026-06-24",
        output_root=tmp_path,
        dependency_checker=lambda *_args, **_kwargs: {
            "status": "failed",
            "reason": "deps missing",
        },
    )

    assert apply_calls == ["called"]
    assert result["status"] == "failed"
    assert result["dependency_check"] == {"status": "failed", "reason": "deps missing"}
    assert result["strategy_status"] == {
        "lhb_shortline": {"status": "skipped", "reason": "dependency_check_failed"},
        "mid_trend": {"status": "skipped", "reason": "dependency_check_failed"},
        "tech_bottleneck": {"status": "skipped", "reason": "dependency_check_failed"},
    }


def test_run_strategy_daily_eod_returns_failed_when_one_strategy_runner_fails(tmp_path, monkeypatch):
    from stock_research import strategy_daily_eod

    apply_calls: list[str] = []
    monkeypatch.setattr(
        strategy_daily_eod,
        "apply_strategy_daily_eod_status_schema",
        lambda: apply_calls.append("called"),
    )

    result = strategy_daily_eod.run_strategy_daily_eod(
        trade_date="2026-06-24",
        output_root=tmp_path,
        dependency_checker=lambda *_args, **_kwargs: {"status": "success"},
        lhb_shortline_runner=lambda *_args, **_kwargs: {"status": "success", "review_rows": 2},
        mid_trend_runner=lambda *_args, **_kwargs: {"status": "failed", "reason": "runner boom"},
        tech_bottleneck_runner=lambda *_args, **_kwargs: {"status": "success", "review_rows": 3},
    )

    assert apply_calls == ["called"]
    assert result["status"] == "failed"
    assert result["dependency_check"] == {"status": "success"}
    assert result["strategy_status"] == {
        "lhb_shortline": {"status": "success", "review_rows": 2},
        "mid_trend": {"status": "failed", "reason": "runner boom"},
        "tech_bottleneck": {"status": "success", "review_rows": 3},
    }


def test_run_strategy_daily_eod_returns_structured_failure_when_dependency_checker_raises(tmp_path, monkeypatch):
    from stock_research import strategy_daily_eod

    monkeypatch.setattr(
        strategy_daily_eod,
        "apply_strategy_daily_eod_status_schema",
        lambda: None,
    )

    result = strategy_daily_eod.run_strategy_daily_eod(
        trade_date="2026-06-24",
        output_root=tmp_path,
        dependency_checker=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("deps boom")),
    )

    assert result["status"] == "failed"
    assert result["dependency_check"] == {
        "status": "failed",
        "reason": "dependency_checker_exception: deps boom",
    }
    assert result["strategy_status"] == {
        "lhb_shortline": {"status": "skipped", "reason": "dependency_check_failed"},
        "mid_trend": {"status": "skipped", "reason": "dependency_check_failed"},
        "tech_bottleneck": {"status": "skipped", "reason": "dependency_check_failed"},
    }


def test_run_strategy_daily_eod_returns_structured_failure_when_strategy_runner_raises(tmp_path, monkeypatch):
    from stock_research import strategy_daily_eod

    monkeypatch.setattr(
        strategy_daily_eod,
        "apply_strategy_daily_eod_status_schema",
        lambda: None,
    )

    result = strategy_daily_eod.run_strategy_daily_eod(
        trade_date="2026-06-24",
        output_root=tmp_path,
        dependency_checker=lambda *_args, **_kwargs: {"status": "success"},
        lhb_shortline_runner=lambda *_args, **_kwargs: {"status": "success", "review_rows": 1},
        mid_trend_runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("runner boom")),
        tech_bottleneck_runner=lambda *_args, **_kwargs: {"status": "success", "review_rows": 4},
    )

    assert result["status"] == "failed"
    assert result["strategy_status"] == {
        "lhb_shortline": {"status": "success", "review_rows": 1},
        "mid_trend": {"status": "failed", "reason": "strategy_runner_exception: runner boom"},
        "tech_bottleneck": {"status": "success", "review_rows": 4},
    }


def test_run_strategy_daily_eod_returns_structured_failure_when_summary_write_raises(tmp_path, monkeypatch):
    from stock_research import strategy_daily_eod

    monkeypatch.setattr(
        strategy_daily_eod,
        "apply_strategy_daily_eod_status_schema",
        lambda: None,
    )

    def fake_write_text(self, data, encoding):
        raise OSError("disk full")

    monkeypatch.setattr(strategy_daily_eod.Path, "write_text", fake_write_text)

    result = strategy_daily_eod.run_strategy_daily_eod(
        trade_date="2026-06-24",
        output_root=tmp_path,
        dependency_checker=lambda *_args, **_kwargs: {"status": "success"},
        lhb_shortline_runner=lambda *_args, **_kwargs: {"status": "success", "review_rows": 1},
        mid_trend_runner=lambda *_args, **_kwargs: {"status": "success", "review_rows": 2},
        tech_bottleneck_runner=lambda *_args, **_kwargs: {"status": "success", "review_rows": 3},
    )

    assert result["status"] == "failed"
    assert result["reason"] == "summary_write_exception: disk full"
    assert result["summary_path"] == str(tmp_path / "2026-06-24" / "strategy_eod_publish_summary.json")


def test_check_strategy_daily_eod_dependencies_fails_when_status_row_missing(monkeypatch):
    from stock_research import strategy_daily_eod

    conn = _Connection()
    monkeypatch.setattr(strategy_daily_eod, "connect", lambda service: _Context(conn))
    monkeypatch.setattr(strategy_daily_eod, "fetch_all", lambda passed_conn, sql, params: [])

    result = strategy_daily_eod.check_strategy_daily_eod_dependencies("2026-06-24")

    assert result == {
        "status": "failed",
        "reason": "daily_pipeline_status missing",
    }


def test_check_strategy_daily_eod_dependencies_accepts_partial_success(monkeypatch):
    from stock_research import strategy_daily_eod

    conn = _Connection()
    monkeypatch.setattr(strategy_daily_eod, "connect", lambda service: _Context(conn))
    monkeypatch.setattr(
        strategy_daily_eod,
        "fetch_all",
        lambda passed_conn, sql, params: [
            {
                "daily_status": "partial_success",
                "minute5_status": "success",
                "deps_status": "success",
            }
        ],
    )

    result = strategy_daily_eod.check_strategy_daily_eod_dependencies("2026-06-24")

    assert result == {
        "status": "success",
        "daily_status": "partial_success",
        "minute5_status": "success",
        "deps_status": "success",
    }


LHB_REVIEW_COLUMNS = [
    "trade_date",
    "asset_id",
    "rank",
    "score_total",
    "score_source",
    "score_explanation",
    "strategy_id",
    "strategy_name",
    "strategy_run_id",
    "source_type",
    "source_name",
    "source_rank",
    "review_tier",
]

TECH_REVIEW_COLUMNS = [
    "trade_date",
    "asset_id",
    "rank",
    "bottleneck_score",
    "score_total",
    "score_source",
    "score_explanation",
    "strategy_id",
    "strategy_name",
    "strategy_run_id",
    "source_type",
    "source_name",
    "source_rank",
    "review_tier",
]


def test_build_lhb_shortline_strategy_eod_writes_review_csv_from_pipeline_output(tmp_path):
    from stock_research import strategy_daily_eod

    calls: list[dict[str, object]] = []

    def fake_runner(**kwargs):
        calls.append(kwargs)
        watchlist_path = tmp_path / "lhb_watchlist.csv"
        pd.DataFrame(
            [
                {
                    "trade_date": "2026-06-24",
                    "ts_code": "000002.SZ",
                    "auction_enhanced_score": 81.5,
                },
                {
                    "trade_date": "2026-06-24",
                    "ts_code": "000001.SZ",
                    "auction_enhanced_score": 96.0,
                },
            ]
        ).to_csv(watchlist_path, index=False)
        return {"paths": {"daily_watchlist": str(watchlist_path)}}

    result = strategy_daily_eod.build_lhb_shortline_strategy_eod(
        trade_date="2026-06-24",
        output_dir=tmp_path,
        pipeline_runner=fake_runner,
    )

    review_path = tmp_path / "strategy_lhb_shortline_review.csv"
    review = pd.read_csv(review_path)

    assert calls and calls[0]["trade_date"] == "2026-06-24"
    assert result == {
        "status": "success",
        "review_rows": 2,
        "paths": {"review": str(review_path)},
    }
    assert list(review.columns) == LHB_REVIEW_COLUMNS
    assert review[["asset_id", "rank", "score_total", "source_rank"]].to_dict(orient="records") == [
        {"asset_id": "000001.SZ", "rank": 1, "score_total": 96.0, "source_rank": 1},
        {"asset_id": "000002.SZ", "rank": 2, "score_total": 81.5, "source_rank": 2},
    ]
    assert set(review["score_source"]) == {"auction_enhanced_score"}
    assert set(review["strategy_run_id"]) == {"strategy-eod-2026-06-24-local"}


def test_build_lhb_shortline_strategy_eod_writes_empty_review_when_watchlist_has_no_rows(tmp_path):
    from stock_research import strategy_daily_eod

    def fake_runner(**kwargs):
        watchlist_path = tmp_path / "lhb_watchlist_empty.csv"
        pd.DataFrame(
            columns=[
                "trade_date",
                "ts_code",
                "stock_name",
                "watch_group",
            ]
        ).to_csv(watchlist_path, index=False)
        return {"paths": {"daily_watchlist": str(watchlist_path)}}

    result = strategy_daily_eod.build_lhb_shortline_strategy_eod(
        trade_date="2026-06-24",
        output_dir=tmp_path,
        pipeline_runner=fake_runner,
    )

    review_path = tmp_path / "strategy_lhb_shortline_review.csv"
    review = pd.read_csv(review_path)

    assert result == {
        "status": "success",
        "review_rows": 0,
        "paths": {"review": str(review_path)},
    }
    assert review.empty
    assert list(review.columns) == LHB_REVIEW_COLUMNS


def test_build_lhb_shortline_strategy_eod_fails_when_runner_does_not_produce_watchlist(tmp_path):
    from stock_research import strategy_daily_eod

    result = strategy_daily_eod.build_lhb_shortline_strategy_eod(
        trade_date="2026-06-24",
        output_dir=tmp_path,
        pipeline_runner=lambda **_kwargs: {"paths": {}},
    )

    assert result == {
        "status": "failed",
        "reason": "required_generated_file_missing: daily_watchlist",
    }


def test_build_mid_trend_strategy_eod_uses_latest_selected_variant_slice(tmp_path):
    from stock_research import strategy_daily_eod

    funnel_detail_path = tmp_path / "mid_trend_watch_funnel_detail.csv"
    pd.DataFrame(
        [
            {
                "trade_date": "2026-06-24",
                "asset_id": "CN:SZ:000001",
                "rank": 20,
                "score_total": 72.2,
                "mid_trend_funnel_score": 91.0,
            },
            {
                "trade_date": "2026-06-24",
                "asset_id": "CN:SZ:000002",
                "rank": 10,
                "score_total": 65.5,
                "mid_trend_funnel_score": 88.5,
            },
        ]
    ).to_csv(funnel_detail_path, index=False)

    def fake_runner(**kwargs):
        positions_path = tmp_path / "mid_trend_shadow_weekly_control_positions.csv"
        pd.DataFrame(
            [
                {
                    "variant_name": "top5_weekly_max2_selective_trend_holding_protection_v1",
                    "rebalance_date": "2026-06-16",
                    "asset_id": "CN:SZ:999999",
                    "weight": 0.2,
                },
                {
                    "variant_name": "baseline_top5_weekly",
                    "rebalance_date": "2026-06-23",
                    "asset_id": "CN:SZ:777777",
                    "weight": 0.2,
                },
                {
                    "variant_name": "top5_weekly_max2_selective_trend_holding_protection_v1",
                    "rebalance_date": "2026-06-23",
                    "asset_id": "CN:SZ:000002",
                    "weight": 0.2,
                },
                {
                    "variant_name": "top5_weekly_max2_selective_trend_holding_protection_v1",
                    "rebalance_date": "2026-06-23",
                    "asset_id": "CN:SZ:000001",
                    "weight": 0.2,
                },
            ]
        ).to_csv(positions_path, index=False)
        return {"paths": {"positions": str(positions_path)}}

    result = strategy_daily_eod.build_mid_trend_strategy_eod(
        trade_date="2026-06-24",
        output_dir=tmp_path,
        weekly_control_runner=fake_runner,
        funnel_detail_path=funnel_detail_path,
    )

    review_path = tmp_path / "strategy_mid_trend_review.csv"
    review = pd.read_csv(review_path)

    assert result == {
        "status": "success",
        "review_rows": 2,
        "paths": {"review": str(review_path)},
    }
    assert list(review.columns) == LHB_REVIEW_COLUMNS
    assert review["asset_id"].tolist() == ["CN:SZ:000002", "CN:SZ:000001"]
    assert review["rank"].tolist() == [1, 2]
    assert review["score_total"].tolist() == [88.5, 91.0]
    assert set(review["score_source"]) == {"mid_trend_funnel_score"}


def test_build_mid_trend_strategy_eod_fails_when_default_funnel_detail_resolution_fails(tmp_path, monkeypatch):
    from stock_research import strategy_daily_eod

    monkeypatch.setattr(
        strategy_daily_eod,
        "resolve_default_funnel_detail_path",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError("no funnel detail artifact")),
    )

    result = strategy_daily_eod.build_mid_trend_strategy_eod(
        trade_date="2026-06-24",
        output_dir=tmp_path,
        weekly_control_runner=lambda **_kwargs: {"paths": {}},
    )

    assert result == {
        "status": "failed",
        "reason": "funnel_detail_path_resolution_failed: no funnel detail artifact",
    }


def test_build_tech_bottleneck_strategy_eod_scales_bottleneck_score(tmp_path):
    from stock_research import strategy_daily_eod

    candidate_path = tmp_path / "tech_bottleneck_evidence_adjusted_candidates.csv"
    pd.DataFrame(
        [
            {
                "trade_date": "2026-06-24",
                "asset_id": "CN:SZ:300002",
                "bottleneck_score": 0.52,
            },
            {
                "trade_date": "2026-06-24",
                "asset_id": "CN:SZ:300001",
                "bottleneck_score": 0.75,
            },
            {
                "trade_date": "2026-06-23",
                "asset_id": "CN:SZ:399999",
                "bottleneck_score": 0.99,
            },
        ]
    ).to_csv(candidate_path, index=False)

    result = strategy_daily_eod.build_tech_bottleneck_strategy_eod(
        trade_date="2026-06-24",
        output_dir=tmp_path,
        candidate_path=candidate_path,
    )

    review_path = tmp_path / "strategy_tech_bottleneck_review.csv"
    review = pd.read_csv(review_path)

    assert result == {
        "status": "success",
        "review_rows": 2,
        "paths": {"review": str(review_path)},
    }
    assert list(review.columns) == TECH_REVIEW_COLUMNS
    assert review[["asset_id", "bottleneck_score", "score_total", "rank"]].to_dict(orient="records") == [
        {
            "asset_id": "CN:SZ:300001",
            "bottleneck_score": 0.75,
            "score_total": 75.0,
            "rank": 1,
        },
        {
            "asset_id": "CN:SZ:300002",
            "bottleneck_score": 0.52,
            "score_total": 52.0,
            "rank": 2,
        },
    ]


def test_build_tech_bottleneck_strategy_eod_fails_when_candidate_file_is_missing(tmp_path):
    from stock_research import strategy_daily_eod

    missing_candidate_path = tmp_path / "missing_candidates.csv"

    result = strategy_daily_eod.build_tech_bottleneck_strategy_eod(
        trade_date="2026-06-24",
        output_dir=tmp_path,
        candidate_path=missing_candidate_path,
    )

    assert result == {
        "status": "failed",
        "reason": f"source_artifact_missing: {missing_candidate_path}",
    }


def test_run_strategy_daily_eod_uses_default_adapter_runners_when_not_injected(tmp_path, monkeypatch):
    from stock_research import strategy_daily_eod

    monkeypatch.setattr(strategy_daily_eod, "apply_strategy_daily_eod_status_schema", lambda: None)

    def make_runner(review_rows):
        def _runner(**kwargs):
            return {"status": "success", "review_rows": review_rows, "paths": {"review": str(kwargs["output_dir"])}}

        return _runner

    monkeypatch.setattr(strategy_daily_eod, "build_lhb_shortline_strategy_eod", make_runner(1))
    monkeypatch.setattr(strategy_daily_eod, "build_mid_trend_strategy_eod", make_runner(2))
    monkeypatch.setattr(strategy_daily_eod, "build_tech_bottleneck_strategy_eod", make_runner(3))

    result = strategy_daily_eod.run_strategy_daily_eod(
        trade_date="2026-06-24",
        output_root=tmp_path,
        dependency_checker=lambda *_args, **_kwargs: {"status": "success"},
    )

    assert result["status"] == "success"
    assert result["review_rows"] == 6
    assert result["strategy_status"] == {
        "lhb_shortline": {
            "status": "success",
            "review_rows": 1,
            "paths": {"review": str(tmp_path / "2026-06-24")},
        },
        "mid_trend": {
            "status": "success",
            "review_rows": 2,
            "paths": {"review": str(tmp_path / "2026-06-24")},
        },
        "tech_bottleneck": {
            "status": "success",
            "review_rows": 3,
            "paths": {"review": str(tmp_path / "2026-06-24")},
        },
    }
