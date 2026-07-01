from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_announcement_external_fetch_adapter.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_announcement_external_fetch_adapter", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _sample_fulltext_fetch_plan() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "样本A",
                "announcement_id": "https://example.com/a.html",
                "announcement_title": "样本A重大合同公告",
                "announcement_date": "2026-01-02",
                "source_url": "https://example.com/a.html",
                "raw_source_name": "announcement_structured_outputs",
                "current_extraction_method": "keyword_title_only",
                "recommended_fetch_method": "fetch_source_url",
                "fetch_priority": "high",
                "human_review_required": True,
            },
            {
                "asset_id": "CN:SZ:000002",
                "symbol": "000002",
                "name": "样本B",
                "announcement_id": "missing-url",
                "announcement_title": "样本B风险提示公告",
                "announcement_date": "2026-01-03",
                "source_url": "",
                "raw_source_name": "announcement_structured_outputs",
                "current_extraction_method": "keyword_title_only",
                "recommended_fetch_method": "fetch_source_url",
                "fetch_priority": "high",
                "human_review_required": True,
            },
        ]
    )


def test_external_fetch_plan_covers_fetch_source_url_rows_and_cache_keys(tmp_path: Path) -> None:
    module = _load_module()

    plan = module.build_external_fetch_plan(_sample_fulltext_fetch_plan(), tmp_path)

    assert len(plan) == 2
    assert plan["cache_key"].fillna("").astype(str).str.len().gt(0).all()
    assert plan.loc[plan["source_url"].fillna("").eq(""), "fetch_required"].eq(False).all()
    assert plan.loc[plan["source_url"].fillna("").ne(""), "fetch_required"].eq(True).all()


def test_fetch_failure_does_not_crash_and_audit_contains_failure_metrics(tmp_path: Path) -> None:
    module = _load_module()
    plan = module.build_external_fetch_plan(_sample_fulltext_fetch_plan(), tmp_path)

    def failing_fetcher(url: str, timeout: float):
        raise OSError("network blocked")

    results = module.execute_fetch_plan(plan, failing_fetcher=failing_fetcher, sleep_seconds=0)
    audit = module.build_quality_audit(plan, results)
    lookup = dict(zip(audit["metric"], audit["value"]))

    assert len(results) == 2
    assert int(float(lookup["network_unavailable_rows"])) >= 1
    assert "text_extraction_ratio" in lookup
    assert int(float(lookup["lookahead_violation_rows"])) == 0


def test_text_cache_manifest_does_not_mark_title_only_as_text_available(tmp_path: Path) -> None:
    module = _load_module()
    plan = module.build_external_fetch_plan(_sample_fulltext_fetch_plan(), tmp_path)
    results = module.execute_fetch_plan(plan, failing_fetcher=lambda url, timeout: (_ for _ in ()).throw(OSError("offline")), sleep_seconds=0)

    manifest = module.build_text_cache_manifest(results)

    assert not manifest["text_available"].astype(bool).any()
    assert not manifest["text_cache_path"].fillna("").astype(str).str.contains("title", case=False).any()


def test_success_html_extracts_text_cache(tmp_path: Path) -> None:
    module = _load_module()
    plan = module.build_external_fetch_plan(_sample_fulltext_fetch_plan().iloc[[0]].copy(), tmp_path)
    html = "<html><body><h1>样本A重大合同公告</h1><p>公司签订重大合同，客户验证明确，风险事项需复核。</p></body></html>".encode("utf-8")

    results = module.execute_fetch_plan(
        plan,
        failing_fetcher=lambda url, timeout: module.FetchResponse(200, "text/html; charset=utf-8", html),
        sleep_seconds=0,
    )
    manifest = module.build_text_cache_manifest(results)

    assert results.iloc[0]["fetch_status"] == "success_html"
    assert results.iloc[0]["text_extracted"] is True
    assert manifest.iloc[0]["text_available"] is True
    assert Path(manifest.iloc[0]["text_cache_path"]).exists()


def test_outputs_have_no_actionable_trading_language(tmp_path: Path) -> None:
    module = _load_module()
    plan = module.build_external_fetch_plan(_sample_fulltext_fetch_plan(), tmp_path)
    results = module.execute_fetch_plan(plan, failing_fetcher=lambda url, timeout: (_ for _ in ()).throw(OSError("offline")), sleep_seconds=0)
    manifest = module.build_text_cache_manifest(results)

    text = " ".join(plan.astype(str).agg(" ".join, axis=1).tolist())
    text += " " + " ".join(results.astype(str).agg(" ".join, axis=1).tolist())
    text += " " + " ".join(manifest.astype(str).agg(" ".join, axis=1).tolist())

    assert not module.contains_actionable_trading_language(text)
