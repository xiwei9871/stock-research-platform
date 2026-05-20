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
    assert report["checks"][0]["metrics"] == {
        "latest_common_date": "2026-01-30",
        "date_count": 80,
        "requested_end_date": "2026-01-30",
    }
    assert report["checks"][2]["metrics"] == {
        "market_rows": 100,
        "covered_rows": 70,
        "missing_rows": 30,
        "date_count": 2,
    }
    assert report["checks"][2]["source"] == "research_preflight"
    assert "details" in report["checks"][2]


def test_latest_common_label_date_exposes_requested_end_date_context(monkeypatch):
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
        "check_factor_label_coverage",
        lambda **kwargs: {
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

    report = data_quality.run_data_quality(
        expected_start_date="1990-12-01",
        start_date="2024-01-01",
        end_date="2026-01-01",
        horizons=[5, 10],
        factor_names=["ret_20"],
        calc_version="v1",
        min_label_dates=20,
        require_industry_membership=False,
    )

    check = next(item for item in report["checks"] if item["check_name"] == "latest_common_label_date")
    assert check["metrics"] == {
        "latest_common_date": "2026-01-30",
        "date_count": 80,
        "requested_end_date": "2026-01-01",
    }
    assert check["details"]["extends_beyond_requested_end_date"] is True


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


def test_run_data_quality_blocks_empty_horizons(monkeypatch):
    monkeypatch.setattr(data_quality, "run_data_audit", lambda **kwargs: [])
    monkeypatch.setattr(data_quality, "summarize_finance_coverage", lambda **kwargs: [])
    monkeypatch.setattr(data_quality, "find_latest_common_label_date", lambda **kwargs: (_ for _ in ()).throw(ValueError("horizons must not be empty")))
    monkeypatch.setattr(
        data_quality,
        "check_factor_label_coverage",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("horizons must not be empty")),
    )

    report = data_quality.run_data_quality(
        expected_start_date="1990-12-01",
        start_date="2024-01-01",
        end_date="2026-01-30",
        horizons=[],
        factor_names=["ret_20"],
        calc_version="v1",
        min_label_dates=20,
        require_industry_membership=False,
    )

    latest = next(item for item in report["checks"] if item["check_name"] == "latest_common_label_date")
    coverage = next(item for item in report["checks"] if item["check_name"] == "factor_label_coverage")
    assert latest["status"] == "blocked"
    assert "empty_horizons" in latest["details"]["reasons"]
    assert latest["metrics"]["requested_end_date"] == "2026-01-30"
    assert coverage["status"] == "blocked"
    assert "empty_horizons" in coverage["details"]["reasons"]


def test_run_data_quality_blocks_when_candidate_factors_are_empty(monkeypatch):
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
    monkeypatch.setattr(data_quality, "candidate_factor_names", lambda: [])
    monkeypatch.setattr(
        data_quality,
        "check_factor_label_coverage",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("no factor names are available for the requested window")),
    )

    report = data_quality.run_data_quality(
        expected_start_date="1990-12-01",
        start_date="2024-01-01",
        end_date="2026-01-30",
        horizons=[5, 10],
        factor_names=[],
        calc_version="v1",
        min_label_dates=20,
        require_industry_membership=False,
    )

    coverage = next(item for item in report["checks"] if item["check_name"] == "factor_label_coverage")
    assert coverage["status"] == "blocked"
    assert "no_usable_factor_names" in coverage["details"]["reasons"]
    assert coverage["details"]["resolved_factor_names"] == []


def test_run_data_quality_blocks_when_start_date_missing(monkeypatch):
    calls = []
    monkeypatch.setattr(
        data_quality,
        "run_data_audit",
        lambda **kwargs: calls.append(("data_audit", kwargs))
        or [
            {
                "dataset": "market_daily_bar",
                "status": "ok",
                "rows": 10,
                "date_count": 2,
                "min_date": "2024-01-01",
                "max_date": "2024-01-02",
            }
        ],
    )
    monkeypatch.setattr(
        data_quality,
        "summarize_finance_coverage",
        lambda **kwargs: calls.append(("finance_audit", kwargs))
        or [{"check": "missing_balance_sheet", "status": "blocked", "rows": 2}],
    )

    def fail_find_latest_common_label_date(**kwargs):
        raise AssertionError("find_latest_common_label_date should not be called")

    monkeypatch.setattr(data_quality, "find_latest_common_label_date", fail_find_latest_common_label_date)

    report = data_quality.run_data_quality(
        expected_start_date="1990-12-01",
        start_date=None,
        end_date=None,
        horizons=[5, 10],
        factor_names=["ret_20"],
        calc_version="v1",
        min_label_dates=20,
        require_industry_membership=False,
    )

    assert calls == [
        ("data_audit", {"expected_start_date": "1990-12-01"}),
        ("finance_audit", {}),
    ]
    assert report["overall_status"] == "blocked"
    assert report["generated_at"]
    assert report["blocked_checks"] == [
        "missing_balance_sheet",
        "latest_common_label_date",
        "factor_label_coverage",
    ]
    assert report["checks"][0]["check_name"] == "market_daily_bar"
    assert report["checks"][1]["check_name"] == "missing_balance_sheet"
    latest = report["checks"][2]
    coverage = report["checks"][3]
    assert latest["check_name"] == "latest_common_label_date"
    assert latest["status"] == "blocked"
    assert latest["kind"] == "research_preflight"
    assert latest["source"] == "research_preflight"
    assert latest["metrics"]["date_count"] == 0
    assert latest["details"]["reasons"] == ["missing_start_date"]
    assert coverage["check_name"] == "factor_label_coverage"
    assert coverage["status"] == "blocked"
    assert coverage["kind"] == "research_preflight"
    assert coverage["source"] == "research_preflight"
    assert coverage["metrics"] == {
        "factor_date_count": 0,
        "complete_factor_date_count": 0,
    }
    assert coverage["details"]["reasons"] == ["missing_start_date"]


def test_run_data_quality_blocks_industry_membership_when_start_date_missing(monkeypatch):
    monkeypatch.setattr(data_quality, "run_data_audit", lambda **kwargs: [])
    monkeypatch.setattr(data_quality, "summarize_finance_coverage", lambda **kwargs: [])

    def fail_find_latest_common_label_date(**kwargs):
        raise AssertionError("find_latest_common_label_date should not be called")

    monkeypatch.setattr(data_quality, "find_latest_common_label_date", fail_find_latest_common_label_date)

    report = data_quality.run_data_quality(
        expected_start_date="1990-12-01",
        start_date=None,
        end_date=None,
        horizons=[5, 10],
        factor_names=["ret_20"],
        calc_version="v1",
        min_label_dates=20,
        require_industry_membership=True,
    )

    check_names = [check["check_name"] for check in report["checks"]]
    assert check_names == [
        "latest_common_label_date",
        "factor_label_coverage",
        "industry_membership_coverage",
    ]
    industry = report["checks"][2]
    assert report["blocked_checks"] == check_names
    assert industry["status"] == "blocked"
    assert industry["kind"] == "research_preflight"
    assert industry["source"] == "research_preflight"
    assert industry["metrics"] == {
        "market_rows": 0,
        "covered_rows": 0,
        "missing_rows": 0,
        "date_count": 0,
    }
    assert industry["details"]["reasons"] == ["missing_start_date"]


def test_run_data_quality_blocks_when_derived_end_date_missing(monkeypatch):
    calls = []
    monkeypatch.setattr(
        data_quality,
        "run_data_audit",
        lambda **kwargs: calls.append(("data_audit", kwargs))
        or [
            {
                "dataset": "market_daily_bar",
                "status": "ok",
                "rows": 10,
                "date_count": 2,
                "min_date": "2024-01-01",
                "max_date": "2024-01-02",
            }
        ],
    )
    monkeypatch.setattr(
        data_quality,
        "summarize_finance_coverage",
        lambda **kwargs: calls.append(("finance_audit", kwargs))
        or [{"check": "missing_balance_sheet", "status": "blocked", "rows": 2}],
    )

    def fail_check_factor_label_coverage(**kwargs):
        raise AssertionError("check_factor_label_coverage should not be called")

    latest_calls = []
    monkeypatch.setattr(
        data_quality,
        "find_latest_common_label_date",
        lambda **kwargs: latest_calls.append(kwargs)
        or {
            "latest_common_date": None,
            "date_count": 0,
            "horizons": kwargs["horizons"],
        },
    )
    monkeypatch.setattr(data_quality, "check_factor_label_coverage", fail_check_factor_label_coverage)

    report = data_quality.run_data_quality(
        expected_start_date="1990-12-01",
        start_date="2024-01-01",
        end_date=None,
        horizons=[5, 10],
        factor_names=["ret_20"],
        calc_version="v1",
        min_label_dates=20,
        require_industry_membership=False,
    )

    assert calls == [
        ("data_audit", {"expected_start_date": "1990-12-01"}),
        ("finance_audit", {}),
    ]
    assert latest_calls == [{"start_date": "2024-01-01", "horizons": [5, 10]}]
    assert report["overall_status"] == "blocked"
    assert report["generated_at"]
    assert report["blocked_checks"] == [
        "missing_balance_sheet",
        "latest_common_label_date",
        "factor_label_coverage",
    ]
    assert report["checks"][0]["check_name"] == "market_daily_bar"
    assert report["checks"][1]["check_name"] == "missing_balance_sheet"
    latest = report["checks"][2]
    coverage = report["checks"][3]
    assert latest["metrics"] == {
        "latest_common_date": None,
        "date_count": 0,
    }
    assert latest["details"]["reasons"] == ["missing_latest_common_date"]
    assert coverage["details"]["reasons"] == ["missing_latest_common_date"]


def test_run_data_quality_blocks_industry_membership_when_derived_end_date_missing(monkeypatch):
    monkeypatch.setattr(data_quality, "run_data_audit", lambda **kwargs: [])
    monkeypatch.setattr(data_quality, "summarize_finance_coverage", lambda **kwargs: [])

    def fail_check_factor_label_coverage(**kwargs):
        raise AssertionError("check_factor_label_coverage should not be called")

    def fail_check_industry_membership_coverage(**kwargs):
        raise AssertionError("check_industry_membership_coverage should not be called")

    monkeypatch.setattr(
        data_quality,
        "find_latest_common_label_date",
        lambda **kwargs: {
            "latest_common_date": None,
            "date_count": 0,
            "horizons": kwargs["horizons"],
        },
    )
    monkeypatch.setattr(data_quality, "check_factor_label_coverage", fail_check_factor_label_coverage)
    monkeypatch.setattr(
        data_quality,
        "check_industry_membership_coverage",
        fail_check_industry_membership_coverage,
    )

    report = data_quality.run_data_quality(
        expected_start_date="1990-12-01",
        start_date="2024-01-01",
        end_date=None,
        horizons=[5, 10],
        factor_names=["ret_20"],
        calc_version="v1",
        min_label_dates=20,
        require_industry_membership=True,
    )

    check_names = [check["check_name"] for check in report["checks"]]
    assert check_names == [
        "latest_common_label_date",
        "factor_label_coverage",
        "industry_membership_coverage",
    ]
    industry = report["checks"][2]
    assert report["blocked_checks"] == check_names
    assert industry["status"] == "blocked"
    assert industry["kind"] == "research_preflight"
    assert industry["source"] == "research_preflight"
    assert industry["metrics"] == {
        "market_rows": 0,
        "covered_rows": 0,
        "missing_rows": 0,
        "date_count": 0,
    }
    assert industry["details"]["reasons"] == ["missing_latest_common_date"]


def test_run_data_quality_reuses_derived_latest_snapshot(monkeypatch):
    latest_calls = []
    coverage_calls = []
    monkeypatch.setattr(data_quality, "run_data_audit", lambda **kwargs: [])
    monkeypatch.setattr(data_quality, "summarize_finance_coverage", lambda **kwargs: [])
    monkeypatch.setattr(
        data_quality,
        "find_latest_common_label_date",
        lambda **kwargs: latest_calls.append(kwargs)
        or {
            "latest_common_date": "2026-01-30",
            "date_count": 80,
            "horizons": [5, 10],
        },
    )
    monkeypatch.setattr(
        data_quality,
        "check_factor_label_coverage",
        lambda **kwargs: coverage_calls.append(kwargs)
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

    report = data_quality.run_data_quality(
        expected_start_date="1990-12-01",
        start_date="2024-01-01",
        end_date=None,
        horizons=[5, 10],
        factor_names=["ret_20"],
        calc_version="v1",
        min_label_dates=20,
        require_industry_membership=False,
    )

    assert latest_calls == [{"start_date": "2024-01-01", "horizons": [5, 10]}]
    assert coverage_calls[0]["end_date"] == "2026-01-30"
    latest = next(item for item in report["checks"] if item["check_name"] == "latest_common_label_date")
    assert latest["metrics"] == {
        "latest_common_date": "2026-01-30",
        "date_count": 80,
        "requested_end_date": "2026-01-30",
    }


def test_run_data_quality_blocks_when_derived_end_date_lookup_raises(monkeypatch):
    calls = []
    monkeypatch.setattr(
        data_quality,
        "run_data_audit",
        lambda **kwargs: calls.append(("data_audit", kwargs))
        or [
            {
                "dataset": "market_daily_bar",
                "status": "ok",
                "rows": 10,
                "date_count": 2,
                "min_date": "2024-01-01",
                "max_date": "2024-01-02",
            }
        ],
    )
    monkeypatch.setattr(
        data_quality,
        "summarize_finance_coverage",
        lambda **kwargs: calls.append(("finance_audit", kwargs))
        or [{"check": "missing_balance_sheet", "status": "blocked", "rows": 2}],
    )
    monkeypatch.setattr(
        data_quality,
        "find_latest_common_label_date",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("horizons must not be empty")),
    )

    def fail_check_factor_label_coverage(**kwargs):
        raise AssertionError("check_factor_label_coverage should not be called")

    monkeypatch.setattr(data_quality, "check_factor_label_coverage", fail_check_factor_label_coverage)

    report = data_quality.run_data_quality(
        expected_start_date="1990-12-01",
        start_date="2024-01-01",
        end_date=None,
        horizons=[],
        factor_names=["ret_20"],
        calc_version="v1",
        min_label_dates=20,
        require_industry_membership=False,
    )

    assert calls == [
        ("data_audit", {"expected_start_date": "1990-12-01"}),
        ("finance_audit", {}),
    ]
    assert report["overall_status"] == "blocked"
    assert report["blocked_checks"] == [
        "missing_balance_sheet",
        "latest_common_label_date",
        "factor_label_coverage",
    ]
    latest = report["checks"][2]
    coverage = report["checks"][3]
    assert latest["details"]["reasons"] == ["empty_horizons"]
    assert coverage["details"]["reasons"] == ["empty_horizons"]


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
