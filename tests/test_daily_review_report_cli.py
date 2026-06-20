import importlib
import json
from pathlib import Path


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "daily_review_v1"


def _import_cli():
    return importlib.import_module("stock_research.reports.daily_review_report_cli")


def _read_json(relative_path: str) -> dict | list:
    return json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))


def _load_fixture_inputs() -> dict[str, object]:
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


def test_run_daily_review_report_writes_package_from_monkeypatched_inputs(monkeypatch, tmp_path):
    cli = _import_cli()
    expected_review = _read_json("expected_daily_review.json")
    expected_markdown = (FIXTURE_ROOT / "expected_daily_review.md").read_text(encoding="utf-8")

    monkeypatch.setattr(cli, "load_daily_review_inputs", lambda trade_date: _load_fixture_inputs())

    result = cli.run_daily_review_report(
        trade_date="2026-06-20",
        output_root=tmp_path,
    )

    report_paths = result["report_paths"]
    assert Path(report_paths["json_path"]).exists()
    assert Path(report_paths["markdown_path"]).exists()
    assert Path(report_paths["manifest_path"]).exists()
    assert json.loads(Path(report_paths["json_path"]).read_text(encoding="utf-8")) == {
        **expected_review,
        "report_paths": report_paths,
    }
    assert Path(report_paths["markdown_path"]).read_text(encoding="utf-8") == expected_markdown
    assert json.loads(Path(report_paths["manifest_path"]).read_text(encoding="utf-8")) == {
        "trade_date": "2026-06-20",
        "run_id": "daily_review_v1_20260620_2200",
        "report_type": "daily_review_v1",
        "schema_version": "daily_review_v1",
        "status": "partial",
        "warnings": ["source_missing:lhb_feed"],
        "report_paths": report_paths,
        "data_readiness": _load_fixture_inputs()["data_readiness"],
    }
    assert result["review"] == {
        **expected_review,
        "report_paths": report_paths,
    }


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
                "manifest_path": str(tmp_path / "2026-06-20" / "manifest.json"),
                "evidence_paths": {"market_state": str(tmp_path / "market_state.json")},
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
        f"daily_review_v1|manifest_path|{tmp_path / '2026-06-20' / 'manifest.json'}",
        f"daily_review_v1|evidence_paths|{{'market_state': '{tmp_path / 'market_state.json'}'}}",
    ]
