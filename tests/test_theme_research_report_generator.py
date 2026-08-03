from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from stock_research.theme_research_report_generator import (
    PILOT_THEME_ID,
    PilotReportGenerationError,
    PilotReportInputs,
    generate_ai_power_pending_report,
    render_ai_power_report_markdown,
)
from stock_research.theme_research_report_manifest import (
    ReportManifestLimits,
    load_report_manifest,
)


GENERATED_AT = datetime.fromisoformat("2026-08-03T10:00:00+08:00")


def pilot_inputs() -> PilotReportInputs:
    return PilotReportInputs(
        theme={
            "theme_id": PILOT_THEME_ID,
            "theme_name": "AI供电产业链",
            "summary": "AI算力基础设施的供电、散热与配套价值链。",
            "status": "reviewed",
        },
        nodes=(
            {
                "node_id": "server_power_supply",
                "node_name": "服务器电源",
                "node_type": "core_component",
                "description": "服务器侧电源转换与供电。",
                "value_capture_score": 5,
                "bottleneck_score": 4,
                "localization_gap_score": 3,
                "supply_tightness_score": 3,
                "evidence_strength": 4,
                "node_review_status": "reviewed",
            },
        ),
        sources=(
            {
                "source_id": "source-1",
                "title": "公司年度报告",
                "publisher": "示例公司",
                "publish_date": "2026-03-31",
                "reliability_level": "S1",
                "review_status": "accepted",
                "url_or_ref": "local:source-1",
            },
        ),
        claims=(
            {
                "claim_id": "claim-1",
                "claim_text": "高功率密度提升电源与散热要求。",
                "claim_type": "bottleneck",
                "confidence": 0.9,
                "evidence_status": "verified",
                "platform_use_status": "reviewed",
                "supporting_source_ids": ["source-1"],
            },
        ),
        company_mappings=(
            {
                "mapping_id": "mapping-1",
                "company_code": "300870.SZ",
                "company_name": "欧陆通",
                "mapped_node_id": "server_power_supply",
                "business_materiality": "meaningful_segment",
                "relationship_summary": "服务器电源相关业务。",
                "review_status": "reviewed",
                "evidence_ids": ["evidence-1"],
            },
        ),
        node_priorities=(
            {
                "node_id": "server_power_supply",
                "priority_score": 78.0,
                "priority_class": "deep_research_priority",
                "recommended_action": "deep_node_research",
            },
        ),
        company_priorities=(
            {
                "mapping_id": "mapping-1",
                "company_research_priority_score": 75.6,
                "priority_band": "high",
                "integration_status": "linked_existing_universe",
                "existing_review_context": {"status": "pending_review"},
            },
        ),
        evidence_gaps=(
            {
                "node_id": "transformer",
                "node_name": "变压器",
                "evidence_gap_score": 3,
                "recommended_action": "collect_node_evidence",
            },
        ),
        artifact_versions=("theme_decomposition_v1_6",),
        mapping_sources=(
            {
                "source_id": "mapping-source-1",
                "title": "公司公告",
                "publisher": "示例公司",
                "publish_date": "2026-03-31",
                "reliability_level": "S0",
                "review_status": "accepted",
                "url_or_ref": "local:mapping-source-1",
            },
        ),
        mapping_evidence_items=(
            {
                "evidence_id": "evidence-1",
                "source_id": "mapping-source-1",
                "evidence_type": "product_relationship",
                "evidence_summary": "公告确认服务器电源产品关系。",
            },
        ),
    )


def test_render_ai_power_report_is_deterministic_and_review_only():
    first = render_ai_power_report_markdown(pilot_inputs(), generated_at=GENERATED_AT)
    second = render_ai_power_report_markdown(pilot_inputs(), generated_at=GENERATED_AT)

    assert first == second
    for heading in (
        "# AI供电产业链分析报告",
        "## 核心结论与研究边界",
        "## 产业链结构",
        "## 价值量与关键瓶颈",
        "## 重点公司映射",
        "## 证据强弱与待补缺口",
        "## 风险、反证与局限",
        "## 来源索引",
        "## Admin 人工审核清单",
    ):
        assert heading in first
    assert "source-1" in first
    assert "claim-1" in first
    assert "mapping-1" in first
    assert "evidence-1" in first
    assert "mapping-source-1" in first
    assert "不构成投资建议" in first
    assert all(phrase not in first for phrase in ("目标价", "买入", "卖出"))


def test_generate_writes_valid_markdown_manifest_and_no_pdf(tmp_path: Path):
    result = generate_ai_power_pending_report(
        inputs=pilot_inputs(),
        report_root=tmp_path,
        version="2026-08-03.1",
        generated_at=GENERATED_AT,
        pipeline_run_id="pilot-run-1",
    )

    version_dir = tmp_path / PILOT_THEME_ID / "2026-08-03.1"
    markdown = (version_dir / "report.md").read_bytes()
    manifest = json.loads((version_dir / "manifest.json").read_text(encoding="utf-8"))
    assert result["version_dir"] == str(version_dir)
    assert manifest["title"] == "AI供电产业链分析报告"
    assert manifest["artifacts"] == {
        "markdown": {
            "path": "report.md",
            "sha256": hashlib.sha256(markdown).hexdigest(),
        }
    }
    assert manifest["metadata"]["pipeline_run_id"] == "pilot-run-1"
    assert manifest["metadata"]["research_only"] is True
    assert not (version_dir / "report.pdf").exists()

    loaded = load_report_manifest(
        version_dir / "manifest.json",
        report_root=tmp_path,
        limits=ReportManifestLimits(65536, 10485760, 52428800),
    )
    assert loaded.theme_id == PILOT_THEME_ID
    assert loaded.pdf is None


def test_generate_rejects_unsupported_theme_and_existing_version(tmp_path: Path):
    with pytest.raises(PilotReportGenerationError, match="unsupported pilot theme"):
        generate_ai_power_pending_report(
            inputs=replace(
                pilot_inputs(),
                theme={**pilot_inputs().theme, "theme_id": "other-theme"},
            ),
            report_root=tmp_path,
            version="2026-08-03.1",
            generated_at=GENERATED_AT,
            pipeline_run_id="pilot-run-other",
        )

    kwargs = {
        "inputs": pilot_inputs(),
        "report_root": tmp_path,
        "version": "2026-08-03.1",
        "generated_at": GENERATED_AT,
    }
    generate_ai_power_pending_report(**kwargs, pipeline_run_id="pilot-run-1")
    with pytest.raises(PilotReportGenerationError, match="already exists"):
        generate_ai_power_pending_report(**kwargs, pipeline_run_id="pilot-run-2")


def test_failed_rename_leaves_no_final_or_staging_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from stock_research import theme_research_report_generator as generator

    def fail_rename(*_args: object) -> None:
        raise OSError("rename failed")

    monkeypatch.setattr(generator.os, "replace", fail_rename)
    with pytest.raises(OSError, match="rename failed"):
        generate_ai_power_pending_report(
            inputs=pilot_inputs(),
            report_root=tmp_path,
            version="2026-08-03.1",
            generated_at=GENERATED_AT,
            pipeline_run_id="rename-failure",
        )
    assert not (tmp_path / PILOT_THEME_ID / "2026-08-03.1").exists()
    assert list(tmp_path.glob(".staging-*")) == []


def test_post_rename_parent_fsync_failure_keeps_committed_final_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from stock_research import theme_research_report_generator as generator

    original_fsync = generator._fsync_directory
    theme_dir = tmp_path / PILOT_THEME_ID

    def fail_parent_fsync(path: Path) -> None:
        if path == theme_dir:
            raise OSError("parent fsync failed")
        original_fsync(path)

    monkeypatch.setattr(generator, "_fsync_directory", fail_parent_fsync)
    with pytest.raises(OSError, match="parent fsync failed"):
        generate_ai_power_pending_report(
            inputs=pilot_inputs(),
            report_root=tmp_path,
            version="2026-08-03.1",
            generated_at=GENERATED_AT,
            pipeline_run_id="post-rename-failure",
        )
    final_dir = theme_dir / "2026-08-03.1"
    assert final_dir.exists()
    assert stat.S_IMODE(final_dir.stat().st_mode) == 0o550
    assert (final_dir / "manifest.json").is_file()
    assert list(theme_dir.glob(".staging-*")) == []


def test_trading_language_fails_before_finalization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from stock_research import theme_research_report_generator as generator

    monkeypatch.setattr(
        generator,
        "render_ai_power_report_markdown",
        lambda *_args, **_kwargs: "建议买入",
    )
    with pytest.raises(PilotReportGenerationError, match="prohibited trading language"):
        generate_ai_power_pending_report(
            inputs=pilot_inputs(),
            report_root=tmp_path,
            version="2026-08-03.1",
            generated_at=GENERATED_AT,
            pipeline_run_id="guardrail",
        )
    assert not (tmp_path / PILOT_THEME_ID / "2026-08-03.1").exists()


@pytest.mark.parametrize(
    "phrase",
    (
        "target price",
        "price target",
        "建议增持",
        "建议减持",
        "做多",
        "做空",
        "看多",
        "看空",
        "BUY",
        "SELL",
        "recommend buying",
        "recommend selling",
        "overweight",
        "underweight",
    ),
)
def test_extended_trading_language_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phrase: str
):
    from stock_research import theme_research_report_generator as generator

    monkeypatch.setattr(
        generator,
        "render_ai_power_report_markdown",
        lambda *_args, **_kwargs: phrase,
    )
    with pytest.raises(PilotReportGenerationError, match="prohibited trading language"):
        generate_ai_power_pending_report(
            inputs=pilot_inputs(),
            report_root=tmp_path,
            version="2026-08-03.1",
            generated_at=GENERATED_AT,
            pipeline_run_id=f"guardrail-{phrase.encode().hex()[:16]}",
        )


def test_renderer_preserves_english_canonical_analysis_with_chinese_review_prompt():
    inputs = pilot_inputs()
    rendered = render_ai_power_report_markdown(
        replace(
            inputs,
            theme={**inputs.theme, "summary": "English theme summary must not be copied."},
            nodes=({**inputs.nodes[0], "description": "English node description must not be copied."},),
            claims=({**inputs.claims[0], "claim_text": "English claim analysis must not be copied."},),
            company_mappings=(
                {**inputs.company_mappings[0], "relationship_summary": "English company analysis must not be copied."},
            ),
        ),
        generated_at=GENERATED_AT,
    )

    for sentence in (
        "English theme summary must not be copied.",
        "English node description must not be copied.",
        "English claim analysis must not be copied.",
        "English company analysis must not be copied.",
    ):
        assert sentence in rendered
    assert rendered.count("中文审核提示") >= 4


def test_renderer_requires_complete_company_mapping_evidence_chain():
    inputs = pilot_inputs()
    with pytest.raises(PilotReportGenerationError, match="mapping evidence chain"):
        render_ai_power_report_markdown(
            replace(inputs, mapping_evidence_items=()),
            generated_at=GENERATED_AT,
        )


def test_generator_cli_help_is_available():
    result = subprocess.run(
        [sys.executable, "-m", "stock_research.theme_research_report_generator", "--help"],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONPATH": "src"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--repository-root" in result.stdout
    assert "--report-root" in result.stdout
    assert "--pipeline-run-id" in result.stdout
