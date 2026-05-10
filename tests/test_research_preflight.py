import stock_research.research_preflight as research_preflight


class _context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False


def test_check_factor_label_coverage_reports_overlap(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params):
        calls.append((sql, params))
        if "factor.factor_daily" in sql:
            return [
                {
                    "min_date": "2026-05-01",
                    "max_date": "2026-05-10",
                    "date_count": 10,
                }
            ]
        return [
            {
                "horizon": 5,
                "min_date": "2026-05-01",
                "max_date": "2026-05-08",
                "date_count": 8,
            }
        ]

    monkeypatch.setattr(research_preflight, "connect", lambda service: _context(object()))
    monkeypatch.setattr(research_preflight, "fetch_all", fake_fetch_all)

    result = research_preflight.check_factor_label_coverage(
        factor_names=["alpha101_delta_close_1_rank"],
        start_date="2026-05-01",
        end_date="2026-05-10",
        horizons=[5],
    )

    assert result["status"] == "ok"
    assert result["factor_date_count"] == 10
    assert result["label_horizons"][5]["date_count"] == 8
    assert "factor.factor_daily" in calls[0][0]
