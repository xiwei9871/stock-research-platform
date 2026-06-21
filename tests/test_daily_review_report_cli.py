import importlib
import json
from pathlib import Path

import pytest


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "daily_review_v1"


def _import_cli():
    return importlib.import_module("stock_research.reports.daily_review_report_cli")


def _read_json(relative_path: str) -> dict | list:
    return json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))


def _fixture_inputs() -> dict[str, object]:
    return {
        "data_readiness": _read_json("source_payloads/data_readiness.json"),
        "market_review": _read_json("source_payloads/market_review.json"),
        "lhb_review": _read_json("source_payloads/lhb_review.json"),
        "mid_trend_review": _read_json("source_payloads/mid_trend_review.json"),
        "technical_bottleneck_review": _read_json(
            "source_payloads/technical_bottleneck_review.json"
        ),
        "holding_reviews": _read_json("source_payloads/holding_reviews.json"),
    }


def test_daily_review_report_cli_parser_accepts_arguments():
    cli = _import_cli()

    args = cli.build_parser().parse_args(
        [
            "--trade-date",
            "2026-06-20",
            "--output-root",
            "/tmp/daily-review",
            "--apply-report-run-schema",
            "--record-run",
        ]
    )

    assert args.trade_date == "2026-06-20"
    assert args.output_root == "/tmp/daily-review"
    assert args.apply_report_run_schema is True
    assert args.record_run is True


def test_run_daily_review_report_orchestrates_loader_build_and_write(monkeypatch, tmp_path):
    cli = _import_cli()
    fixture_inputs = _fixture_inputs()
    calls: dict[str, object] = {}
    built_review = {"run_id": "daily_review_v1_20260620_2200", "status": "partial"}
    report_paths = {"json_path": str(tmp_path / "daily_review.json")}

    def fake_load_daily_review_inputs(trade_date):
        calls["load_trade_date"] = trade_date
        return fixture_inputs

    def fake_build_daily_review(**kwargs):
        calls["build_kwargs"] = kwargs
        return built_review

    def fake_write_daily_review_package(review, *, output_root, record_run):
        calls["write_kwargs"] = {
            "review": review,
            "output_root": output_root,
            "record_run": record_run,
        }
        return report_paths

    schema_calls: list[str] = []
    monkeypatch.setattr(cli, "load_daily_review_inputs", fake_load_daily_review_inputs)
    monkeypatch.setattr(cli, "build_daily_review", fake_build_daily_review)
    monkeypatch.setattr(cli, "write_daily_review_package", fake_write_daily_review_package)
    monkeypatch.setattr(cli, "apply_report_run_schema", lambda: schema_calls.append("schema"))

    result = cli.run_daily_review_report(
        trade_date="2026-06-20",
        output_root=tmp_path,
        apply_report_run_schema_first=True,
        record_run=True,
    )

    assert schema_calls == ["schema"]
    assert calls["load_trade_date"] == "2026-06-20"
    assert calls["build_kwargs"] == {
        "trade_date": "2026-06-20",
        "run_id": "daily_review_v1_20260620_2200",
        **fixture_inputs,
    }
    assert calls["write_kwargs"] == {
        "review": built_review,
        "output_root": tmp_path,
        "record_run": True,
    }
    assert result == {"review": built_review, "report_paths": report_paths}


def test_run_daily_review_report_rejects_placeholder_loader_bundle(monkeypatch, tmp_path):
    cli = _import_cli()
    build_called = False
    write_called = False

    def fake_build_daily_review(**kwargs):
        nonlocal build_called
        build_called = True
        return {}

    def fake_write_daily_review_package(review, *, output_root, record_run):
        nonlocal write_called
        write_called = True
        return {}

    monkeypatch.setattr(
        cli,
        "load_daily_review_inputs",
        lambda trade_date: {
            "data_readiness": {},
            "market_review": {},
            "lhb_review": {},
            "mid_trend_review": {},
            "technical_bottleneck_review": {},
            "holding_reviews": [],
        },
    )
    monkeypatch.setattr(cli, "build_daily_review", fake_build_daily_review)
    monkeypatch.setattr(cli, "write_daily_review_package", fake_write_daily_review_package)

    with pytest.raises(ValueError, match="daily review inputs"):
        cli.run_daily_review_report(
            trade_date="2026-06-20",
            output_root=tmp_path,
        )

    assert build_called is False
    assert write_called is False


def test_run_daily_review_report_rejects_non_dict_holding_review_rows(monkeypatch, tmp_path):
    cli = _import_cli()

    monkeypatch.setattr(
        cli,
        "load_daily_review_inputs",
        lambda trade_date: {
            **_fixture_inputs(),
            "holding_reviews": ["bad-row"],
        },
    )

    with pytest.raises(ValueError, match="holding_reviews rows must be dict objects"):
        cli.run_daily_review_report(
            trade_date="2026-06-20",
            output_root=tmp_path,
        )


def test_daily_review_report_cli_main_prints_report_paths(monkeypatch, capsys, tmp_path):
    cli = _import_cli()
    calls = []

    def fake_runner(**kwargs):
        calls.append(kwargs)
        return {
            "report_paths": {
                "package_root": str(tmp_path / "2026-06-20"),
                "json_path": str(tmp_path / "2026-06-20" / "daily_review.json"),
                "markdown_path": str(tmp_path / "2026-06-20" / "daily_review.md"),
                "evidence_paths": {
                    "market_state": str(tmp_path / "2026-06-20" / "evidence" / "market_state.json"),
                    "lhb_review": str(tmp_path / "2026-06-20" / "evidence" / "lhb_review.json"),
                },
            }
        }

    monkeypatch.setattr(
        "sys.argv",
        [
            "python -m stock_research.reports.daily_review_report_cli",
            "--trade-date",
            "2026-06-20",
            "--output-root",
            str(tmp_path),
            "--apply-report-run-schema",
            "--record-run",
        ],
    )

    cli.main(runner=fake_runner)

    assert calls == [
        {
            "trade_date": "2026-06-20",
            "output_root": Path(tmp_path),
            "apply_report_run_schema_first": True,
            "record_run": True,
        }
    ]
    assert capsys.readouterr().out.splitlines() == [
        f"daily_review_v1|package_root|{tmp_path / '2026-06-20'}",
        f"daily_review_v1|json_path|{tmp_path / '2026-06-20' / 'daily_review.json'}",
        f"daily_review_v1|markdown_path|{tmp_path / '2026-06-20' / 'daily_review.md'}",
        (
            "daily_review_v1|evidence_paths.market_state|"
            f"{tmp_path / '2026-06-20' / 'evidence' / 'market_state.json'}"
        ),
        (
            "daily_review_v1|evidence_paths.lhb_review|"
            f"{tmp_path / '2026-06-20' / 'evidence' / 'lhb_review.json'}"
        ),
    ]
