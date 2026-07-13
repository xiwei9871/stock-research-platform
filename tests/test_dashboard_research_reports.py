from stock_research.dashboard import research_reports


class DummyConnection:
    pass


class DummyConnect:
    def __init__(self, service: str):
        self.service = service
        self.conn = DummyConnection()

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


def test_research_report_summary_separates_readable_pdf_reports(monkeypatch):
    calls = []

    def fake_connect(service: str):
        assert service == "svc"
        return DummyConnect(service)

    def fake_fetch_all(conn, sql, params=None):
        calls.append(sql)
        if "COUNT(DISTINCT s.report_id) AS total_reports" in sql:
            return [
                {
                    "total_reports": 58781,
                    "covered_stocks": 3388,
                    "latest_publish_date": "2026-07-09",
                    "latest_feature_date": "2026-06-30",
                    "source_count": 7,
                    "readable_report_count": 1634,
                    "web_index_report_count": 57147,
                }
            ]
        return []

    monkeypatch.setattr(research_reports, "connect", fake_connect)
    monkeypatch.setattr(research_reports, "fetch_all", fake_fetch_all)

    summary = research_reports.load_research_report_summary(service="svc")

    assert summary["total_reports"] == 58781
    assert summary["readable_report_count"] == 1634
    assert summary["pdf_report_count"] == 1634
    assert summary["web_index_report_count"] == 57147
    assert "metadata ? 'yanbaoke'" in calls[0]
