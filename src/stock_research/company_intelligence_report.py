"""CAP-01 dossier rendering: structured JSON + readable Markdown report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_research.company_intelligence import DIMENSIONS


_VERDICT_LABEL = {
    "confirmed": "已证实",
    "partially_supported": "部分支持",
    "contested": "正反冲突",
    "contradicted": "存在反证",
    "needs_evidence": "需要补证",
    "unknown": "未知",
    "established": "成立",
    "unverified": "未证实",
}
_DIRECTION_LABEL = {"support": "支持", "refute": "反驳", "unclear": "不明确"}


def render_dossier_markdown(dossier: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(
        f"# {dossier['company_code']} {dossier['company_name']}｜企业竞争力研究画像"
    )
    lines.append("")
    lines.append(
        f"研究截止: {dossier['as_of']} ｜ 总体结论: "
        f"{_VERDICT_LABEL.get(dossier['conclusion']['overall_verdict'], dossier['conclusion']['overall_verdict'])}"
        f"（置信度 {dossier['conclusion']['confidence']:.2f}）"
    )
    lines.append("研究底稿，非操作建议；未进入选股准入或任何信号。")
    lines.append("")

    lines.append("## 一、六维结论")
    lines.append("")
    lines.append("| 维度 | 判定 | 置信度 | 支持/反驳 | 缺项 |")
    lines.append("|---|---|---|---|---|")
    for key, label in DIMENSIONS.items():
        dim = dossier["dimensions"][key]
        missing = "、".join(dim["missing_checklist_items"]) or "-"
        lines.append(
            f"| {label} | {_VERDICT_LABEL.get(dim['verdict'], dim['verdict'])} "
            f"| {dim['confidence']:.2f} | {dim['support_count']}/{dim['refute_count']} | {missing} |"
        )
    lines.append("")

    lines.append("## 二、关键论点与证据矩阵")
    lines.append("")
    for claim in dossier["claims"]:
        verdict = _VERDICT_LABEL.get(claim.get("verdict", ""), claim.get("verdict", ""))
        unverified = claim.get("unverified_evidence_ids") or []
        lead_note = f"；待验证线索 {len(unverified)} 条" if unverified else ""
        lines.append(
            f"- `{claim['claim_id']}` [{DIMENSIONS.get(claim['dimension'], claim['dimension'])}] "
            f"{claim['claim_text']} — 判定 **{verdict}**"
            f"（支持 {claim['support_count']} / 反驳 {claim['refute_count']}{lead_note}）"
        )
    lines.append("")
    lines.append("| 证据 | 维度 | 方向 | 页码/章节 | 来源类型 | 发布 | 入库 | PIT | 判定权重 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for row in dossier["evidence_matrix"]:
        precision = row.get("published_precision", "")
        pub = row["published_at"] or "-"
        if precision and precision != "day":
            pub = f"{pub}({precision})"
        lines.append(
            f"| `{row['evidence_id']}` | {DIMENSIONS.get(row['dimension'], row['dimension'])} "
            f"| {_DIRECTION_LABEL.get(row['direction'], row['direction'])} "
            f"| {row['page_or_section'] or '-'} | {row['source_type']} "
            f"| {pub} | {row['ingested_at'] or '-'} "
            f"| {row.get('pit_status', '-')} | {row.get('verdict_weight', '-')} |"
        )
    lines.append("")

    lines.append("## 三、正反两面分析")
    lines.append("")
    lines.append("### 支持面")
    for row in dossier["bull_case"]:
        excerpt = row["excerpt"].replace("\n", " ")[:160]
        lines.append(
            f"- [{DIMENSIONS.get(row['dimension'], row['dimension'])}] "
            f"{excerpt}（`{row['evidence_id']}` {row['page_or_section']}，{row['source_type']}，{row['published_at']}）"
        )
    if not dossier["bull_case"]:
        lines.append("- （无可用支持证据）")
    lines.append("")
    lines.append("### 反证与风险")
    for row in dossier["bear_case"]:
        excerpt = row["excerpt"].replace("\n", " ")[:160]
        lines.append(
            f"- [{DIMENSIONS.get(row['dimension'], row['dimension'])}] "
            f"{excerpt}（`{row['evidence_id']}` {row['page_or_section']}，{row['source_type']}，{row['published_at']}）"
        )
    if not dossier["bear_case"]:
        lines.append("- （未检索到明确反证——本身是一个缺口，见研究缺口）")
    lines.append("")

    lines.append("## 四、研究缺口")
    lines.append("")
    lines.append("| 维度 | 缺口 | 原因 | 需要来源 | 优先级 |")
    lines.append("|---|---|---|---|---|")
    for gap in dossier["research_gaps"]:
        lines.append(
            f"| {DIMENSIONS.get(gap['dimension'], gap['dimension'])} | {gap['missing_item']} "
            f"| {gap['reason']} | {'/'.join(gap['needed_source_types'])} | {gap['priority']} |"
        )
    lines.append("")

    lines.append("## 五、研究结论")
    lines.append("")
    lines.append(
        f"- 总体判定: **{_VERDICT_LABEL.get(dossier['conclusion']['overall_verdict'], dossier['conclusion']['overall_verdict'])}**"
        f"（置信度 {dossier['conclusion']['confidence']:.2f}）"
    )
    if dossier["conclusion"]["main_uncertainties"]:
        lines.append("- 主要不确定性:")
        for item in dossier["conclusion"]["main_uncertainties"]:
            lines.append(f"  - {item}")
    if dossier["conclusion"]["verification_conditions"]:
        lines.append("- 下一步验证条件:")
        for item in dossier["conclusion"]["verification_conditions"][:15]:
            lines.append(f"  - {item}")
    if dossier.get("post_asof_excluded"):
        lines.append(
            f"- PIT 排除: {len(dossier['post_asof_excluded'])} 条证据可用时间晚于研究截止，未参与判定: "
            + "、".join(dossier["post_asof_excluded"])
        )
    if dossier.get("pit_uncertain"):
        lines.append(
            f"- PIT 不定: {len(dossier['pit_uncertain'])} 条证据时间精度不足或缺失，未参与判定: "
            + "、".join(dossier["pit_uncertain"])
        )
    if dossier.get("pending_verification"):
        lines.append("- 待验证线索（不参与判定）:")
        for row in dossier["pending_verification"]:
            excerpt = row["excerpt"].replace("\n", " ")[:120]
            lines.append(
                f"  - `{row['evidence_id']}` [{DIMENSIONS.get(row['dimension'], row['dimension'])}] "
                f"{excerpt}（{row['source_type']}，{row['published_at']}）"
            )
    lines.append("")

    lines.append("## 附: 输入快照与护栏")
    lines.append("")
    snapshot = dossier.get("input_snapshot") or {}
    for key in sorted(snapshot):
        value = snapshot[key]
        text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        lines.append(f"- `{key}`: {text[:200]}")
    guard = dossier["guardrails"]
    lines.append(
        f"- 护栏: research_only={guard['research_only']}, used_for_signal={guard['used_for_signal']},"
        f" used_for_admission={guard['used_for_admission']},"
        f" requires_human_review={guard['requires_human_review']}"
    )
    lines.append("")
    return "\n".join(lines)


def write_dossier_outputs(
    dossier: dict[str, Any],
    output_dir: str | Path,
    *,
    code_sha: str = "",
) -> dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{dossier['company_code']}_dossier.json"
    md_path = output / f"{dossier['company_code']}_dossier.md"
    payload = dict(dossier)
    if code_sha:
        payload.setdefault("input_snapshot", {})["code_sha"] = code_sha
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_dossier_markdown(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
