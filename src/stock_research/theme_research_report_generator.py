from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from stock_research.theme_company_mapping import load_theme_company_mapping_package
from stock_research.theme_decomposition import load_theme
from stock_research.theme_research_priority import load_theme_research_priority_package


PILOT_THEME_ID = "ai_power_value_capture_v1"
GENERATOR_NAME = "theme-research-report-pipeline"
GENERATOR_VERSION = "1.0.0"

_VERSION_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}\.[1-9][0-9]*$")
_SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_PROHIBITED_TRADING_PHRASES = (
    "买入",
    "卖出",
    "目标价",
    "buy recommendation",
    "sell recommendation",
)


class PilotReportGenerationError(ValueError):
    pass


@dataclass(frozen=True)
class PilotReportInputs:
    theme: dict[str, Any]
    nodes: tuple[dict[str, Any], ...]
    sources: tuple[dict[str, Any], ...]
    claims: tuple[dict[str, Any], ...]
    company_mappings: tuple[dict[str, Any], ...]
    node_priorities: tuple[dict[str, Any], ...]
    company_priorities: tuple[dict[str, Any], ...]
    evidence_gaps: tuple[dict[str, Any], ...]
    artifact_versions: tuple[str, ...]


def load_ai_power_report_inputs(
    *,
    repository_root: Path,
    theme_id: str = PILOT_THEME_ID,
) -> PilotReportInputs:
    if theme_id != PILOT_THEME_ID:
        raise PilotReportGenerationError(f"unsupported pilot theme: {theme_id}")
    root = repository_root.absolute()
    artifact_root = root / "artifacts" / "theme_decomposition"
    mapping_root = artifact_root / "company_mappings"
    policy_root = artifact_root / "priority_policies"
    crosswalk_root = artifact_root / "tech_bottleneck_crosswalks"

    theme_detail = load_theme(theme_id, artifact_root)
    mapping_package = load_theme_company_mapping_package(mapping_root, artifact_root)
    priority_package = load_theme_research_priority_package(
        policy_dir=policy_root,
        theme_artifact_dir=artifact_root,
        theme_mapping_dir=mapping_root,
        crosswalk_dir=crosswalk_root,
        repository_root=root,
    )
    return PilotReportInputs(
        theme=theme_detail["theme"],
        nodes=tuple(sorted(theme_detail["nodes"], key=lambda row: row["node_id"])),
        sources=tuple(
            sorted(theme_detail["sources"], key=lambda row: row["source_id"])
        ),
        claims=tuple(
            sorted(theme_detail["claims"], key=lambda row: row["claim_id"])
        ),
        company_mappings=tuple(
            sorted(
                (
                    row
                    for row in mapping_package["company_mappings"]
                    if row["theme_id"] == theme_id
                ),
                key=lambda row: row["mapping_id"],
            )
        ),
        node_priorities=tuple(
            row
            for row in priority_package["node_priorities"]
            if row["theme_id"] == theme_id
        ),
        company_priorities=tuple(
            row
            for row in priority_package["company_priorities"]
            if row["theme_id"] == theme_id
        ),
        evidence_gaps=tuple(
            row
            for row in priority_package["evidence_gap_priorities"]
            if row["theme_id"] == theme_id
        ),
        artifact_versions=tuple(
            priority_package["theme_package"]["artifact_versions"]
        ),
    )


def render_ai_power_report_markdown(
    inputs: PilotReportInputs,
    *,
    generated_at: datetime,
) -> str:
    _validate_inputs(inputs, generated_at)
    node_priority = {row["node_id"]: row for row in inputs.node_priorities}
    company_priority = {
        row["mapping_id"]: row for row in inputs.company_priorities
    }
    lines = [
        "# AI供电产业链分析报告",
        "",
        f"- 主题 ID：`{PILOT_THEME_ID}`",
        f"- 生成时间：{generated_at.isoformat()}",
        "- 状态：系统生成的人工审核初稿",
        "- 边界：仅用于研究与人工审核，不构成投资建议，不用于信号或准入。",
        "",
        "## 核心结论与研究边界",
        "",
        str(inputs.theme.get("summary") or "暂无主题摘要。"),
        "",
        "本报告仅汇总系统中已经存在并通过结构校验的主题、节点、公司映射、证据和优先级结果；未执行新的外部资料抓取。",
        "",
        "## 产业链结构",
        "",
        "| 节点 | 类型 | 描述 | 审核状态 |",
        "|---|---|---|---|",
    ]
    for node in sorted(
        inputs.nodes,
        key=lambda row: (-_number(row.get("value_capture_score")), row["node_id"]),
    ):
        lines.append(
            f"| {_cell(node.get('node_name'))} (`{node['node_id']}`) | "
            f"{_cell(node.get('node_type'))} | {_cell(node.get('description'))} | "
            f"{_cell(node.get('node_review_status'))} |"
        )

    lines.extend(
        [
            "",
            "## 价值量与关键瓶颈",
            "",
            "| 节点 | 价值量 | 卡脖子 | 国产差距 | 供给 | 证据 | 研究优先级 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for node in sorted(
        inputs.nodes,
        key=lambda row: (
            -_number(node_priority.get(row["node_id"], {}).get("priority_score")),
            row["node_id"],
        ),
    ):
        priority = node_priority.get(node["node_id"], {})
        lines.append(
            f"| {_cell(node.get('node_name'))} | {_number(node.get('value_capture_score')):g} | "
            f"{_number(node.get('bottleneck_score')):g} | "
            f"{_number(node.get('localization_gap_score')):g} | "
            f"{_number(node.get('supply_tightness_score')):g} | "
            f"{_number(node.get('evidence_strength')):g} | "
            f"{_number(priority.get('priority_score')):g} |"
        )

    lines.extend(["", "### 供电、液冷、电网与数据中心配套", ""])
    linked_nodes = [
        node
        for node in inputs.nodes
        if any(
            token in f"{node.get('node_id', '')} {node.get('node_name', '')}".lower()
            for token in (
                "power",
                "cool",
                "grid",
                "data_center",
                "供电",
                "液冷",
                "电网",
                "变压器",
                "数据中心",
            )
        )
    ]
    if linked_nodes:
        for node in sorted(linked_nodes, key=lambda row: row["node_id"]):
            lines.append(
                f"- **{_cell(node.get('node_name'))}** (`{node['node_id']}`)："
                f"{_cell(node.get('description'))}"
            )
    else:
        lines.append("- 当前结构化节点中没有单独标记的供电或散热配套节点，需由 admin 核对主题边界。")

    lines.extend(
        [
            "",
            "## 重点公司映射",
            "",
            "| 公司 | 节点 | 业务重要性 | 映射审核 | 研究优先级 | 交叉评审状态 | 关系摘要 |",
            "|---|---|---|---|---:|---|---|",
        ]
    )
    for mapping in sorted(inputs.company_mappings, key=lambda row: row["mapping_id"]):
        priority = company_priority.get(mapping["mapping_id"], {})
        lines.append(
            f"| {_cell(mapping.get('company_name'))} (`{mapping.get('company_code', '')}`) | "
            f"`{mapping.get('mapped_node_id', '')}` | "
            f"{_cell(mapping.get('business_materiality'))} | "
            f"{_cell(mapping.get('review_status'))} | "
            f"{_number(priority.get('company_research_priority_score')):g} | "
            f"{_cell(priority.get('integration_status', 'not_crosswalk_scoped'))} | "
            f"{_cell(mapping.get('relationship_summary'))} |"
        )

    lines.extend(["", "## 证据强弱与待补缺口", ""])
    if inputs.evidence_gaps:
        for gap in sorted(
            inputs.evidence_gaps,
            key=lambda row: (-_number(row.get("evidence_gap_score")), row["node_id"]),
        ):
            lines.append(
                f"- `{gap['node_id']}` {_cell(gap.get('node_name'))}："
                f"证据缺口 {_number(gap.get('evidence_gap_score')):g}，"
                f"建议动作 `{gap.get('recommended_action', 'collect_node_evidence')}`。"
            )
    else:
        lines.append("- 当前优先级包未列出独立证据缺口；admin 仍需逐项核对来源完整性。")

    lines.extend(["", "## 风险、反证与局限", ""])
    risk_claims = [
        claim
        for claim in inputs.claims
        if claim.get("claim_type") == "risk"
        or claim.get("evidence_status")
        in {"unverified", "contradicted", "partially_verified"}
    ]
    if risk_claims:
        for claim in sorted(risk_claims, key=lambda row: row["claim_id"]):
            lines.append(
                f"- `{claim['claim_id']}` [{claim.get('evidence_status', 'unknown')}] "
                f"{_cell(claim.get('claim_text'))}"
            )
    else:
        lines.append("- 当前结构化资料未提供独立风险观点；这不代表风险不存在，admin 应重点检查反证与边界条件。")
    lines.append("- 公司映射仅表示研究关联，不等于收入确认、订单兑现、竞争优势或投资结论。")
    lines.append("- 证据状态为草稿、部分验证或未验证的内容不得在审核时升级为确定性结论。")

    lines.extend(
        [
            "",
            "## 来源索引",
            "",
            "| 来源 ID | 标题 | 发布者 | 日期 | 可靠性 | 审核状态 |",
            "|---|---|---|---|---|---|",
        ]
    )
    for source in sorted(inputs.sources, key=lambda row: row["source_id"]):
        lines.append(
            f"| `{source['source_id']}` | {_cell(source.get('title'))} | "
            f"{_cell(source.get('publisher'))} | {_cell(source.get('publish_date'))} | "
            f"{_cell(source.get('reliability_level'))} | "
            f"{_cell(source.get('review_status'))} |"
        )

    lines.extend(["", "### 观点索引", ""])
    for claim in sorted(inputs.claims, key=lambda row: row["claim_id"]):
        refs = ", ".join(
            f"`{value}`" for value in claim.get("supporting_source_ids", [])
        )
        lines.append(
            f"- `{claim['claim_id']}` [{claim.get('evidence_status', 'unknown')}] "
            f"{_cell(claim.get('claim_text'))}；来源：{refs or '无'}。"
        )

    lines.extend(
        [
            "",
            "## Admin 人工审核清单",
            "",
            "- [ ] 核对产业链节点是否完整且命名准确。",
            "- [ ] 核对重点公司关系是否被证据支持。",
            "- [ ] 核对风险、反证和证据缺口是否充分披露。",
            "- [ ] 确认报告没有交易指令、价格预测或自动准入结论。",
            "- [ ] 决定批准发布或填写可操作的驳回原因。",
            "",
        ]
    )
    result = "\n".join(lines)
    _reject_prohibited_trading_language(result)
    return result


def generate_ai_power_pending_report(
    *,
    inputs: PilotReportInputs,
    report_root: Path,
    version: str,
    generated_at: datetime,
    pipeline_run_id: str,
) -> dict[str, Any]:
    _validate_inputs(inputs, generated_at)
    if not _VERSION_RE.fullmatch(version):
        raise PilotReportGenerationError(f"invalid immutable version: {version}")
    if not _SAFE_RUN_ID_RE.fullmatch(pipeline_run_id):
        raise PilotReportGenerationError("invalid pipeline run id")
    if not report_root.is_absolute():
        raise PilotReportGenerationError("report root must be absolute")

    root = report_root.absolute()
    root.mkdir(parents=True, exist_ok=True)
    theme_dir = root / PILOT_THEME_ID
    theme_dir.mkdir(mode=0o750, exist_ok=True)
    final_dir = theme_dir / version
    if final_dir.exists():
        raise PilotReportGenerationError(f"report version already exists: {final_dir}")

    staging = Path(
        tempfile.mkdtemp(prefix=f".staging-{pipeline_run_id}-", dir=root)
    )
    try:
        markdown_text = render_ai_power_report_markdown(
            inputs,
            generated_at=generated_at,
        )
        _reject_prohibited_trading_language(markdown_text)
        markdown_path = staging / "report.md"
        markdown_path.write_text(markdown_text, encoding="utf-8", newline="\n")
        markdown_bytes = markdown_path.read_bytes()
        markdown_sha256 = hashlib.sha256(markdown_bytes).hexdigest()
        manifest = {
            "schema_version": "theme_research_report_manifest_v1",
            "theme_id": PILOT_THEME_ID,
            "version": version,
            "title": "AI供电产业链分析报告",
            "summary": "基于现有主题节点、公司映射、证据与研究优先级生成的人工审核初稿。",
            "generated_at": generated_at.isoformat(),
            "generator": {
                "name": GENERATOR_NAME,
                "version": GENERATOR_VERSION,
            },
            "artifacts": {
                "markdown": {
                    "path": "report.md",
                    "sha256": markdown_sha256,
                }
            },
            "metadata": {
                "pipeline_run_id": pipeline_run_id,
                "artifact_versions": list(inputs.artifact_versions),
                "node_count": len(inputs.nodes),
                "company_mapping_count": len(inputs.company_mappings),
                "source_count": len(inputs.sources),
                "claim_count": len(inputs.claims),
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            },
        }
        manifest_path = staging / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        os.chmod(markdown_path, 0o440)
        os.chmod(manifest_path, 0o440)
        _fsync_regular_file(markdown_path)
        _fsync_regular_file(manifest_path)
        _fsync_directory(staging)
        os.replace(staging, final_dir)
        os.chmod(final_dir, 0o550)
        _fsync_directory(theme_dir)
        return {
            "status": "generated",
            "theme_id": PILOT_THEME_ID,
            "version": version,
            "version_dir": str(final_dir),
            "manifest_path": str(final_dir / "manifest.json"),
        }
    finally:
        if staging.exists():
            try:
                os.chmod(staging, 0o750)
            except OSError:
                pass
            shutil.rmtree(staging)


def _validate_inputs(inputs: PilotReportInputs, generated_at: datetime) -> None:
    if inputs.theme.get("theme_id") != PILOT_THEME_ID:
        raise PilotReportGenerationError(
            f"unsupported pilot theme: {inputs.theme.get('theme_id', '')}"
        )
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise PilotReportGenerationError("generated_at must include a timezone")
    required = {
        "nodes": inputs.nodes,
        "sources": inputs.sources,
        "claims": inputs.claims,
        "company mappings": inputs.company_mappings,
        "artifact versions": inputs.artifact_versions,
    }
    for label, values in required.items():
        if not values:
            raise PilotReportGenerationError(f"pilot inputs require {label}")


def _reject_prohibited_trading_language(text: str) -> None:
    lowered = text.lower()
    hits = [phrase for phrase in _PROHIBITED_TRADING_PHRASES if phrase.lower() in lowered]
    if hits:
        raise PilotReportGenerationError(
            f"prohibited trading language found: {', '.join(hits)}"
        )


def _cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def _number(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _fsync_regular_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme-research-report-generator")
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--report-root", type=Path, required=True)
    parser.add_argument("--theme-id", default=PILOT_THEME_ID)
    parser.add_argument("--version", required=True)
    parser.add_argument("--generated-at", required=True)
    parser.add_argument("--pipeline-run-id", required=True)
    args = parser.parse_args(argv)
    inputs = load_ai_power_report_inputs(
        repository_root=args.repository_root,
        theme_id=args.theme_id,
    )
    result = generate_ai_power_pending_report(
        inputs=inputs,
        report_root=args.report_root,
        version=args.version,
        generated_at=datetime.fromisoformat(args.generated_at),
        pipeline_run_id=args.pipeline_run_id,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
