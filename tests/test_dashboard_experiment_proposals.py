from stock_research.dashboard import experiment_proposals


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_load_experiment_proposals_summary_returns_read_only_rows(monkeypatch):
    captured = {}

    def fake_connect(service):
        captured["service"] = service
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "proposal_id": "p10-proposal:001",
                "run_id": "p10-proposals-2026-05-31",
                "review_date": "2026-05-31",
                "proposal_title": "Replay dashboard top-N",
                "hypothesis": "Dashboard top-N candidates should be replayed offline.",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "source_analytics_group_ids": ["decision_label:candidate"],
                "source_diagnostic_refs": ["top_forward_return:5:decision_label:candidate"],
                "source_artifact_paths": ["outputs/p9/analytics.json"],
                "expected_validation_method": "offline replay",
                "risk_notes": "No production scoring change in P10.",
                "reviewer_id": "reviewer-a",
                "status": "approved_for_experiment",
                "proposal_artifact_path": "outputs/p10/operator_experiment_proposals_2026-05-31.json",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "promotion_enabled": False,
            }
        ]

    monkeypatch.setattr(experiment_proposals, "connect", fake_connect)
    monkeypatch.setattr(experiment_proposals, "fetch_all", fake_fetch_all)

    result = experiment_proposals.load_experiment_proposals_summary(
        start_date="2026-05-01",
        end_date="2026-06-30",
        status="approved_for_experiment",
        limit=10,
        service="stock_research_test",
    )

    assert "FROM ops.operator_experiment_proposal" in captured["sql"]
    assert "status = %s" in captured["sql"]
    assert "ORDER BY review_date DESC" in captured["sql"]
    assert captured["params"] == ["2026-05-01", "2026-06-30", "approved_for_experiment", 10]
    assert captured["service"] == "stock_research_test"
    assert result == [
        {
            "proposal_id": "p10-proposal:001",
            "run_id": "p10-proposals-2026-05-31",
            "review_date": "2026-05-31",
            "proposal_title": "Replay dashboard top-N",
            "hypothesis": "Dashboard top-N candidates should be replayed offline.",
            "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
            "source_analytics_group_ids": ["decision_label:candidate"],
            "source_diagnostic_refs": ["top_forward_return:5:decision_label:candidate"],
            "source_artifact_paths": ["outputs/p9/analytics.json"],
            "expected_validation_method": "offline replay",
            "risk_notes": "No production scoring change in P10.",
            "reviewer_id": "reviewer-a",
            "status": "approved_for_experiment",
            "proposal_artifact_path": "outputs/p10/operator_experiment_proposals_2026-05-31.json",
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "promotion_enabled": False,
        }
    ]


def test_load_experiment_proposals_summary_without_status_filter(monkeypatch):
    captured = {}
    monkeypatch.setattr(experiment_proposals, "connect", lambda service: FakeConnect())

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return []

    monkeypatch.setattr(experiment_proposals, "fetch_all", fake_fetch_all)

    result = experiment_proposals.load_experiment_proposals_summary(
        start_date="2026-05-01",
        end_date="2026-06-30",
        limit=5,
        service="stock_research_test",
    )

    assert result == []
    assert "status = %s" not in captured["sql"]
    assert captured["params"] == ["2026-05-01", "2026-06-30", 5]
