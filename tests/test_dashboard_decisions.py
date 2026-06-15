from stock_research.dashboard import decisions


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_load_asset_decision_history_returns_read_only_rows(monkeypatch):
    captured = {}

    def fake_connect(service):
        captured["service"] = service
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "review_date": "2026-05-30",
                "review_session_id": "morning-review",
                "event_id": "operator_decision:morning-review:0:abc",
                "asset_id": "000001.SZ",
                "stock_code": "000001.SZ",
                "stock_name": "Alpha",
                "decision_label": "candidate",
                "evidence_artifact_id": "dashboard:topn:2026-05-30",
                "evidence_path": "outputs/p6/topn.json",
                "source_context": (
                    '{"source":"dashboard_topn","run_id":"eod-2026-06-12-local",'
                    '"digest_key":"2026-06-12:manual_v1:000001.SZ",'
                    '"review_item_snapshot_id":"review_item_snapshot:abc",'
                    '"evidence_digest_snapshot_id":"evidence_digest_snapshot:def",'
                    '"evidence_as_of":"2026-06-12","review_item_as_of":"2026-06-12"}'
                ),
                "requires_follow_up": True,
                "follow_up_note": "check next close strength",
                "notes": "strong score",
                "manual_review_required": True,
                "auto_trade_enabled": False,
            }
        ]

    monkeypatch.setattr(decisions, "connect", fake_connect)
    monkeypatch.setattr(decisions, "fetch_all", fake_fetch_all)

    result = decisions.load_asset_decision_history(
        "000001.SZ",
        start_date="2026-05-01",
        end_date="2026-05-30",
        limit=10,
        service="stock_research_test",
    )

    assert "FROM ops.operator_decision_event" in captured["sql"]
    assert "ORDER BY review_date DESC" in captured["sql"]
    assert captured["params"] == ["000001.SZ", "2026-05-01", "2026-05-30", 10]
    assert captured["service"] == "stock_research_test"
    assert result == [
        {
            "review_date": "2026-05-30",
            "review_session_id": "morning-review",
            "event_id": "operator_decision:morning-review:0:abc",
            "asset_id": "000001.SZ",
            "stock_code": "000001.SZ",
            "stock_name": "Alpha",
            "decision_label": "candidate",
            "evidence_artifact_id": "dashboard:topn:2026-05-30",
            "evidence_path": "outputs/p6/topn.json",
            "source_context": (
                '{"source":"dashboard_topn","run_id":"eod-2026-06-12-local",'
                '"digest_key":"2026-06-12:manual_v1:000001.SZ",'
                '"review_item_snapshot_id":"review_item_snapshot:abc",'
                '"evidence_digest_snapshot_id":"evidence_digest_snapshot:def",'
                '"evidence_as_of":"2026-06-12","review_item_as_of":"2026-06-12"}'
            ),
            "run_id": "eod-2026-06-12-local",
            "digest_key": "2026-06-12:manual_v1:000001.SZ",
            "review_item_snapshot_id": "review_item_snapshot:abc",
            "evidence_digest_snapshot_id": "evidence_digest_snapshot:def",
            "evidence_as_of": "2026-06-12",
            "review_item_as_of": "2026-06-12",
            "snapshot_linkage_status": "linked",
            "snapshot_linkage_warnings": [],
            "requires_follow_up": True,
            "follow_up_note": "check next close strength",
            "notes": "strong score",
            "manual_review_required": True,
            "auto_trade_enabled": False,
        }
    ]


def test_load_asset_decision_history_marks_missing_snapshot_linkage(monkeypatch):
    def fake_fetch_all(conn, sql, params):
        return [
            {
                "review_date": "2026-05-30",
                "review_session_id": "morning-review",
                "event_id": "operator_decision:morning-review:0:abc",
                "asset_id": "000001.SZ",
                "stock_code": "000001.SZ",
                "stock_name": "Alpha",
                "decision_label": "candidate",
                "evidence_artifact_id": "dashboard:topn:2026-05-30",
                "evidence_path": "outputs/p6/topn.json",
                "source_context": "dashboard_topn",
                "requires_follow_up": False,
                "follow_up_note": "",
                "notes": "",
                "manual_review_required": True,
                "auto_trade_enabled": False,
            }
        ]

    monkeypatch.setattr(decisions, "connect", lambda service: FakeConnect())
    monkeypatch.setattr(decisions, "fetch_all", fake_fetch_all)

    result = decisions.load_asset_decision_history(
        "000001.SZ",
        start_date="2026-05-01",
        end_date="2026-05-30",
    )

    assert result[0]["snapshot_linkage_status"] == "missing"
    assert result[0]["run_id"] == ""
    assert result[0]["digest_key"] == ""
    assert result[0]["snapshot_linkage_warnings"] == ["snapshot linkage unavailable"]
