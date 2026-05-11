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
                    "complete_date_count": 10,
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
        min_label_dates=8,
    )

    assert result["status"] == "ok"
    assert result["factor_date_count"] == 10
    assert result["factor_complete_date_count"] == 10
    assert result["label_horizons"][5]["date_count"] == 8
    assert "factor.factor_daily" in calls[0][0]


def test_find_latest_common_label_date_requires_all_horizons(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params):
        calls.append((sql, params))
        return [{"latest_common_date": "2026-01-30", "date_count": 122}]

    monkeypatch.setattr(research_preflight, "connect", lambda service: _context(object()))
    monkeypatch.setattr(research_preflight, "fetch_all", fake_fetch_all)

    result = research_preflight.find_latest_common_label_date(
        start_date="2024-01-01",
        horizons=[5, 10, 20, 60],
    )

    assert result == {
        "latest_common_date": "2026-01-30",
        "date_count": 122,
        "horizons": [5, 10, 20, 60],
    }
    assert "HAVING count(DISTINCT horizon) = %s" in calls[0][0]
    assert calls[0][1] == [
        "forward_return",
        "v1",
        [5, 10, 20, 60],
        "2024-01-01",
        4,
    ]


def test_check_factor_label_coverage_blocks_missing_horizons(monkeypatch):
    def fake_fetch_all(conn, sql, params):
        if "factor.factor_daily" in sql:
            return [
                {
                    "min_date": "2024-01-02",
                    "max_date": "2026-01-30",
                    "date_count": 300,
                    "complete_date_count": 300,
                }
            ]
        return [
            {"horizon": 5, "min_date": "2024-01-02", "max_date": "2026-01-30", "date_count": 300},
            {"horizon": 10, "min_date": "2024-01-02", "max_date": "2026-01-30", "date_count": 300},
        ]

    monkeypatch.setattr(research_preflight, "connect", lambda service: _context(object()))
    monkeypatch.setattr(research_preflight, "fetch_all", fake_fetch_all)

    result = research_preflight.check_factor_label_coverage(
        factor_names=["ret_20", "qlib_ret_5"],
        start_date="2024-01-01",
        end_date="2026-01-30",
        horizons=[5, 10, 20, 60],
        min_label_dates=20,
    )

    assert result["status"] == "blocked"
    assert result["missing_horizons"] == [20, 60]
    assert "missing_label_horizons" in result["reasons"]


def test_check_factor_label_coverage_blocks_incomplete_candidate_dates(monkeypatch):
    def fake_fetch_all(conn, sql, params):
        if "factor.factor_daily" in sql:
            return [
                {
                    "min_date": "2024-01-02",
                    "max_date": "2024-01-31",
                    "date_count": 3,
                    "complete_date_count": 0,
                    "missing_factor_names": [],
                }
            ]
        return [
            {"horizon": 5, "min_date": "2024-01-02", "max_date": "2024-01-31", "date_count": 20},
            {"horizon": 10, "min_date": "2024-01-02", "max_date": "2024-01-31", "date_count": 20},
        ]

    monkeypatch.setattr(research_preflight, "connect", lambda service: _context(object()))
    monkeypatch.setattr(research_preflight, "fetch_all", fake_fetch_all)

    result = research_preflight.check_factor_label_coverage(
        factor_names=["ret_5", "ret_20"],
        start_date="2024-01-01",
        end_date="2024-01-31",
        horizons=[5, 10],
        min_label_dates=2,
    )

    assert result["status"] == "blocked"
    assert result["factor_date_count"] == 3
    assert result["factor_complete_date_count"] == 0
    assert "insufficient_complete_factor_dates" in result["reasons"]


def test_check_factor_label_coverage_blocks_small_label_samples(monkeypatch):
    def fake_fetch_all(conn, sql, params):
        if "factor.factor_daily" in sql:
            return [
                {
                    "min_date": "2026-01-28",
                    "max_date": "2026-01-30",
                    "date_count": 3,
                    "complete_date_count": 3,
                }
            ]
        return [
            {"horizon": 5, "min_date": "2026-01-28", "max_date": "2026-01-30", "date_count": 3},
            {"horizon": 10, "min_date": "2026-01-28", "max_date": "2026-01-30", "date_count": 3},
            {"horizon": 20, "min_date": "2026-01-28", "max_date": "2026-01-30", "date_count": 3},
            {"horizon": 60, "min_date": "2026-01-28", "max_date": "2026-01-30", "date_count": 3},
        ]

    monkeypatch.setattr(research_preflight, "connect", lambda service: _context(object()))
    monkeypatch.setattr(research_preflight, "fetch_all", fake_fetch_all)

    result = research_preflight.check_factor_label_coverage(
        factor_names=["ret_20"],
        start_date="2026-01-28",
        end_date="2026-01-30",
        horizons=[5, 10, 20, 60],
        min_label_dates=20,
    )

    assert result["status"] == "blocked"
    assert result["short_label_horizons"] == [5, 10, 20, 60]
    assert "insufficient_label_dates" in result["reasons"]
