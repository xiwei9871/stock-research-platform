from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_eastmoney_notice_url_adapter.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_eastmoney_notice_url_adapter", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _sample_fetch_plan(tmp_path: Path) -> pd.DataFrame:
    html_path = tmp_path / "external" / "cache" / "html" / "sample.html"
    html_path.parent.mkdir(parents=True)
    html_path.write_text(
        """
        <html><head>
          <meta name="mobile-agent" content="format=html5; url=https://np-info.eastmoney.com/wap/notice/?infocode=AN202604271821634468">
        </head><body>
          <script>var stockInfo={"code":"688002","name":"样本A","infocode":"AN202604271821634468"};</script>
          <div class="content_text" id="notice_content"></div>
          <a class="pdf-link" href="#">查看PDF原文</a>
        </body></html>
        """,
        encoding="utf-8",
    )
    return pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688002",
                "symbol": "688002",
                "name": "样本A",
                "announcement_id": "https://data.eastmoney.com/notices/detail/688002/AN202604271821634468.html",
                "announcement_title": "样本A重大合同公告",
                "announcement_date": "2026-04-27",
                "source_url": "https://data.eastmoney.com/notices/detail/688002/AN202604271821634468.html",
                "raw_source_name": "announcement_structured_outputs",
                "current_extraction_method": "keyword_title_only",
                "fetch_required": True,
                "fetch_priority": "high",
                "url_domain": "data.eastmoney.com",
                "html_cache_path": str(html_path),
                "raw_cache_path": str(tmp_path / "external" / "cache" / "raw" / "sample.bin"),
                "pdf_cache_path": str(tmp_path / "external" / "cache" / "pdf" / "sample.pdf"),
                "text_cache_path": str(tmp_path / "external" / "cache" / "text" / "sample.txt"),
            },
            {
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "样本B",
                "announcement_id": "non-eastmoney",
                "announcement_title": "样本B风险提示公告",
                "announcement_date": "2026-01-03",
                "source_url": "https://example.com/notices/abc.html",
                "raw_source_name": "announcement_structured_outputs",
                "current_extraction_method": "keyword_title_only",
                "fetch_required": True,
                "fetch_priority": "high",
                "url_domain": "example.com",
                "html_cache_path": "",
                "raw_cache_path": "",
                "pdf_cache_path": "",
                "text_cache_path": "",
            },
        ]
    )


def test_url_inventory_covers_input_rows_and_flags_eastmoney(tmp_path: Path) -> None:
    module = _load_module()

    inventory = module.build_url_inventory(_sample_fetch_plan(tmp_path), pd.DataFrame())

    assert len(inventory) == 2
    assert int(inventory["is_eastmoney_url"].sum()) == 1
    assert inventory.loc[0, "url_pattern"] == "eastmoney_notice_detail"
    assert inventory.loc[0, "contains_notice_id_hint"] is True


def test_resolution_plan_extracts_stable_strategy_and_candidate_urls(tmp_path: Path) -> None:
    module = _load_module()
    inventory = module.build_url_inventory(_sample_fetch_plan(tmp_path), pd.DataFrame())

    plan = module.build_resolution_plan(inventory, tmp_path)
    eastmoney_plan = plan.loc[plan["is_eastmoney_url"].astype(bool)].iloc[0]

    assert len(plan) == 2
    assert eastmoney_plan["resolution_required"] is True
    assert eastmoney_plan["resolution_strategy"] in {
        "parse_cached_html_for_json_state",
        "parse_url_for_notice_id",
        "parse_cached_html_for_pdf_url",
        "try_eastmoney_metadata_api",
    }
    assert eastmoney_plan["candidate_notice_id"] == "AN202604271821634468"
    assert "np-cnotice-stock.eastmoney.com" in eastmoney_plan["candidate_api_url"]
    assert len(eastmoney_plan["cache_key"]) > 8


def test_page_shell_is_not_marked_as_text_available(tmp_path: Path) -> None:
    module = _load_module()
    inventory = module.build_url_inventory(_sample_fetch_plan(tmp_path).iloc[[0]].copy(), pd.DataFrame())
    plan = module.build_resolution_plan(inventory, tmp_path)
    shell = (
        "<html><body>东方财富网 &gt; 数据中心 &gt; 公告大全 "
        "公告日期： - 当前第 1 页 上一页 下一页 共 页 "
        "<div id='notice_content'></div></body></html>"
    ).encode("utf-8")

    results = module.resolve_eastmoney_notices(
        plan,
        fetcher=lambda url, timeout: module.FetchResponse(200, "text/html; charset=utf-8", shell),
        sleep_seconds=0,
    )
    manifest = module.build_pdf_text_manifest(results)

    assert results.iloc[0]["resolution_status"] == "parse_failed"
    assert results.iloc[0]["text_extracted"] is False
    assert manifest.iloc[0]["text_available"] is False
    assert manifest.iloc[0]["pdf_available"] is False


def test_direct_pdf_result_is_cached_without_text_claim(tmp_path: Path) -> None:
    module = _load_module()
    inventory = module.build_url_inventory(_sample_fetch_plan(tmp_path).iloc[[0]].copy(), pd.DataFrame())
    plan = module.build_resolution_plan(inventory, tmp_path)
    plan.loc[:, "candidate_pdf_url"] = "https://pdf.dfcfw.com/pdf/H2_AN202604271821634468_1.pdf"
    plan.loc[:, "resolution_strategy"] = "direct_pdf_url"

    results = module.resolve_eastmoney_notices(
        plan,
        fetcher=lambda url, timeout: module.FetchResponse(200, "application/pdf", b"%PDF-1.4 sample"),
        sleep_seconds=0,
    )
    manifest = module.build_pdf_text_manifest(results)

    assert results.iloc[0]["resolution_status"] == "resolved_pdf"
    assert manifest.iloc[0]["pdf_available"] is True
    assert manifest.iloc[0]["text_available"] is False
    assert Path(manifest.iloc[0]["pdf_cache_path"]).exists()


def test_quality_audit_contains_required_metrics(tmp_path: Path) -> None:
    module = _load_module()
    inventory = module.build_url_inventory(_sample_fetch_plan(tmp_path), pd.DataFrame())
    plan = module.build_resolution_plan(inventory, tmp_path)
    results = module.resolve_eastmoney_notices(
        plan,
        fetcher=lambda url, timeout: (_ for _ in ()).throw(OSError("network blocked")),
        sleep_seconds=0,
    )
    manifest = module.build_pdf_text_manifest(results)
    audit = module.build_quality_audit(inventory, plan, results, manifest)
    lookup = dict(zip(audit["metric"], audit["value"]))

    for metric in ["resolved_pdf_rows", "text_available_rows", "manual_required_rows", "lookahead_violation_rows"]:
        assert metric in lookup
    assert int(float(lookup["lookahead_violation_rows"])) == 0


def test_outputs_have_no_actionable_trading_language(tmp_path: Path) -> None:
    module = _load_module()
    inventory = module.build_url_inventory(_sample_fetch_plan(tmp_path), pd.DataFrame())
    plan = module.build_resolution_plan(inventory, tmp_path)

    text = " ".join(inventory.astype(str).agg(" ".join, axis=1).tolist())
    text += " " + " ".join(plan.astype(str).agg(" ".join, axis=1).tolist())

    assert not module.contains_actionable_trading_language(text)
