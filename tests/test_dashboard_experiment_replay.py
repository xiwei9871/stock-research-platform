from stock_research.dashboard import experiment_replay


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_load_experiment_replay_summary_returns_read_only_rows(monkeypatch):
    captured = {}

    def fake_connect(service):
        captured["service"] = service
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "replay_result_id": "p11-replay:001",
                "run_id": "p11-replay-run-2026-06-30",
                "proposal_id": "p10-proposal:001",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "replay_start_date": "2026-01-01",
                "replay_end_date": "2026-05-31",
                "replay_input_artifact_paths": ["inputs/p11/replay_candidates.csv"],
                "validation_method": "offline replay",
                "replay_status": "passed_offline_replay",
                "sample_count": 24,
                "passed_count": 18,
                "failed_count": 6,
                "metric_summary": {"win_rate": 0.75},
                "failure_reason": "",
                "defer_reason": "",
                "replay_artifact_path": "outputs/p11/operator_experiment_replay_2026-01-01_2026-05-31.json",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(experiment_replay, "connect", fake_connect)
    monkeypatch.setattr(experiment_replay, "fetch_all", fake_fetch_all)

    result = experiment_replay.load_experiment_replay_summary(
        start_date="2026-01-01",
        end_date="2026-06-30",
        status="passed_offline_replay",
        limit=10,
        service="stock_research_test",
    )

    assert "FROM ops.operator_experiment_replay_result" in captured["sql"]
    assert "replay_status = %s" in captured["sql"]
    assert "ORDER BY replay_end_date DESC" in captured["sql"]
    assert captured["params"] == ["2026-01-01", "2026-06-30", "passed_offline_replay", 10]
    assert captured["service"] == "stock_research_test"
    assert result == [
        {
            "replay_result_id": "p11-replay:001",
            "run_id": "p11-replay-run-2026-06-30",
            "proposal_id": "p10-proposal:001",
            "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
            "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
            "replay_start_date": "2026-01-01",
            "replay_end_date": "2026-05-31",
            "replay_input_artifact_paths": ["inputs/p11/replay_candidates.csv"],
            "validation_method": "offline replay",
            "replay_status": "passed_offline_replay",
            "sample_count": 24,
            "passed_count": 18,
            "failed_count": 6,
            "metric_summary": {"win_rate": 0.75},
            "failure_reason": "",
            "defer_reason": "",
            "replay_artifact_path": "outputs/p11/operator_experiment_replay_2026-01-01_2026-05-31.json",
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "production_write_enabled": False,
        }
    ]


def test_load_experiment_replay_summary_without_status_filter(monkeypatch):
    captured = {}
    monkeypatch.setattr(experiment_replay, "connect", lambda service: FakeConnect())

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return []

    monkeypatch.setattr(experiment_replay, "fetch_all", fake_fetch_all)

    result = experiment_replay.load_experiment_replay_summary(
        start_date="2026-01-01",
        end_date="2026-06-30",
        limit=5,
        service="stock_research_test",
    )

    assert result == []
    assert "replay_status = %s" not in captured["sql"]
    assert captured["params"] == ["2026-01-01", "2026-06-30", 5]
