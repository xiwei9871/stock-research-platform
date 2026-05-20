import stock_research.data_quality as data_quality


def test_run_data_quality_normalizes_leaf_checks(monkeypatch):
    calls = []

    monkeypatch.setattr(
        data_quality,
        "run_data_audit",
        lambda **kwargs: [
            {
                "dataset": "market_daily_bar",
                "status": "short_history",
                "rows": 10,
                "date_count": 2,
                "min_date": "2024-01-01",
                "max_date": "2024-01-02",
            },
            {
                "dataset": "factor.factor_approval",
                "status": "empty",
                "rows": 0,
                "date_count": 0,
                "min_date": None,
                "max_date": None,
            },
        ],
    )
    monkeypatch.setattr(
        data_quality,
        "summarize_finance_coverage",
        lambda **kwargs: [
            {"check": "missing_balance_sheet", "status": "blocked", "rows": 2},
            {"check": "announcement_before_report_period", "status": "warning", "rows": 1},
        ],
    )
    monkeypatch.setattr(
        data_quality,
        "find_latest_common_label_date",
        lambda **kwargs: {
            "latest_common_date": "2026-01-30",
            "date_count": 122,
            "horizons": [5, 10],
        },
    )
    monkeypatch.setattr(
        data_quality,
        "check_factor_label_coverage",
        lambda **kwargs: {
            "status": "ok",
            "factor_date_count": 122,
            "factor_complete_date_count": 122,
            "missing_horizons": [],
            "short_label_horizons": [],
            "required_factor_names": ["ret_20"],
            "unavailable_factor_names": [],
            "reasons": [],
        },
    )
    monkeypatch.setattr(
        data_quality,
        "candidate_factor_names",
        lambda: calls.append("candidate_factor_names") or ["ret_20"],
    )

    report = data_quality.run_data_quality(
        expected_start_date="1990-12-01",
        start_date="2024-01-01",
        end_date="2026-01-30",
        horizons=[5, 10],
        factor_names=None,
        calc_version="v1",
        min_label_dates=20,
        require_industry_membership=False,
    )

    assert calls == ["candidate_factor_names"]
    assert report["overall_status"] == "blocked"
    assert report["generated_at"]
    assert report["blocked_checks"] == ["factor.factor_approval", "missing_balance_sheet"]
    assert report["warning_checks"] == ["market_daily_bar", "announcement_before_report_period"]
    assert report["checks"][0]["kind"] == "data_audit"
    assert report["checks"][0]["source"] == "data_audit"
    assert "details" in report["checks"][0]
    assert report["checks"][0]["status"] == "warning"
    assert report["checks"][0]["metrics"]["rows"] == 10
    checks_by_name = {check["check_name"]: check for check in report["checks"]}
    assert checks_by_name["latest_common_label_date"]["status"] == "ok"
    assert checks_by_name["latest_common_label_date"]["source"] == "research_preflight"
    assert "details" in checks_by_name["latest_common_label_date"]
    assert checks_by_name["factor_label_coverage"]["metrics"] == {
        "factor_date_count": 122,
        "complete_factor_date_count": 122,
    }
    assert checks_by_name["factor_label_coverage"]["source"] == "research_preflight"
    assert "details" in checks_by_name["factor_label_coverage"]


def test_run_data_quality_adds_preflight_and_optional_membership(monkeypatch):
    monkeypatch.setattr(data_quality, "run_data_audit", lambda **kwargs: [])
    monkeypatch.setattr(data_quality, "summarize_finance_coverage", lambda **kwargs: [])
    monkeypatch.setattr(
        data_quality,
        "find_latest_common_label_date",
        lambda **kwargs: {
            "latest_common_date": "2026-01-30",
            "date_count": 80,
            "horizons": [5, 10, 20, 60],
        },
    )
    monkeypatch.setattr(
        data_quality,
        "check_factor_label_coverage",
        lambda **kwargs: {
            "status": "blocked",
            "factor_date_count": 50,
            "factor_complete_date_count": 10,
            "missing_horizons": [20, 60],
            "short_label_horizons": [5],
            "required_factor_names": ["ret_20"],
            "unavailable_factor_names": ["late_factor"],
            "reasons": ["missing_label_horizons"],
        },
    )
    monkeypatch.setattr(
        data_quality,
        "check_industry_membership_coverage",
        lambda **kwargs: {
            "status": "blocked",
            "market_rows": 100,
            "covered_rows": 70,
            "missing_rows": 30,
            "date_count": 2,
        },
    )
    monkeypatch.setattr(data_quality, "candidate_factor_names", lambda: ["ret_20", "late_factor"])

    report = data_quality.run_data_quality(
        expected_start_date="1990-12-01",
        start_date="2024-01-01",
        end_date="2026-01-30",
        horizons=[5, 10, 20, 60],
        factor_names=None,
        calc_version="v1",
        min_label_dates=20,
        require_industry_membership=True,
    )

    check_names = [item["check_name"] for item in report["checks"]]
    assert check_names == [
        "latest_common_label_date",
        "factor_label_coverage",
        "industry_membership_coverage",
    ]
    assert report["generated_at"]
    assert report["checks"][0]["status"] == "ok"
    assert report["checks"][0]["metrics"] == {"latest_common_date": "2026-01-30", "date_count": 80}
    assert report["checks"][2]["metrics"] == {
        "market_rows": 100,
        "covered_rows": 70,
        "missing_rows": 30,
        "date_count": 2,
    }
    assert report["checks"][2]["source"] == "research_preflight"
    assert "details" in report["checks"][2]


def test_run_data_quality_uses_candidate_factors_for_falsy_factor_names(monkeypatch):
    calls = []

    monkeypatch.setattr(data_quality, "run_data_audit", lambda **kwargs: [])
    monkeypatch.setattr(data_quality, "summarize_finance_coverage", lambda **kwargs: [])
    monkeypatch.setattr(
        data_quality,
        "find_latest_common_label_date",
        lambda **kwargs: {
            "latest_common_date": "2026-01-30",
            "date_count": 80,
            "horizons": [5, 10],
        },
    )
    monkeypatch.setattr(
        data_quality,
        "candidate_factor_names",
        lambda: calls.append("candidate_factor_names") or ["ret_20"],
    )
    monkeypatch.setattr(
        data_quality,
        "check_factor_label_coverage",
        lambda **kwargs: calls.append(kwargs["factor_names"])
        or {
            "status": "ok",
            "factor_date_count": 80,
            "factor_complete_date_count": 80,
            "missing_horizons": [],
            "short_label_horizons": [],
            "required_factor_names": ["ret_20"],
            "unavailable_factor_names": [],
            "reasons": [],
        },
    )

    data_quality.run_data_quality(
        expected_start_date="1990-12-01",
        start_date="2024-01-01",
        end_date="2026-01-30",
        horizons=[5, 10],
        factor_names=[],
        calc_version="v1",
        min_label_dates=20,
        require_industry_membership=False,
    )

    assert calls == ["candidate_factor_names", ["ret_20"]]


def test_formatters_emit_stable_summary_and_check_lines():
    report = {
        "overall_status": "warning",
        "checks": [{}, {}, {}],
        "blocked_checks": [],
        "warning_checks": ["market_daily_bar"],
    }
    summary = data_quality.format_data_quality_summary_line(report)
    check = {
        "check_name": "factor_label_coverage",
        "status": "blocked",
        "kind": "research_preflight",
        "metrics": {"factor_date_count": 0},
    }
    check_line = data_quality.format_data_quality_check_line(check)
    lines = list(
        data_quality.iter_data_quality_lines(
            {
                **report,
                "checks": [check],
            }
        )
    )

    assert summary == "data_quality|summary|warning|checks|3|blocked|0|warning|1"
    assert check_line == (
        "data_quality|factor_label_coverage|blocked|kind|research_preflight|"
        "factor_date_count|0"
    )
    assert lines == [
        "data_quality|summary|warning|checks|1|blocked|0|warning|1",
        "data_quality|factor_label_coverage|blocked|kind|research_preflight|factor_date_count|0",
    ]
