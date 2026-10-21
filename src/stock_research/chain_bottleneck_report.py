"""CAP-02 node dossier rendering: JSON + readable Markdown."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_research.chain_bottleneck import NODE_ASPECTS


_VERDICT_LABEL = {
    "confirmed": "已证实",
    "partially_supported": "部分支持",
    "contested": "正反冲突",
    "contradicted": "存在反证",
    "mixed": "结论分化",
    "needs_evidence": "需要补证",
    "unknown": "未知",
    "bottleneck_established": "瓶颈成立",
    "bottleneck_unverified": "瓶颈未证实",
    "bottleneck_rejected": "瓶颈被反驳",
}
_DIRECTION_LABEL = {"support": "支持", "refute": "反驳", "unclear": "不明确"}
_SCOPE_LABEL = {"node": "节点级", "company": "公司级"}


def render_node_markdown(dossier: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# {dossier['node_name']}｜产业链节点瓶颈研究（{dossier['node_id']}）")
    lines.append("")
    verdict = dossier["conclusion"]["node_verdict"]
    lines.append(
        f"研究截止: {dossier['as_of']} ｜ 节点判定: "
        f"{_VERDICT_LABEL.get(verdict, verdict)}（置信度 {dossier['conclusion']['confidence']:.2f}）"
    )
    lines.append("节点级研究底稿；公司能力强不自动推出节点瓶颈。")
    lines.append("")

    members = dossier.get("member_companies") or []
    if members:
        lines.append("## 一、节点成员公司")
        lines.append("")
        lines.append("| 代码 | 公司 | 映射类型 | 主题优先级 |")
        lines.append("|---|---|---|---|")
        for m in members:
            lines.append(
                f"| {m.get('stock_code','')} | {m.get('company_name','')} "
                f"| {m.get('mapping_type','')} | {m.get('priority_score','')} |"
            )
        lines.append("")

    lines.append("## 二、瓶颈五门判定")
    lines.append("")
    lines.append("| 门槛 | 判定 | 置信度 | 支持/反驳 | 待验证 | 缺项 |")
    lines.append("|---|---|---|---|---|---|")
    for key, label in NODE_ASPECTS.items():
        asp = dossier["aspects"][key]
        missing = "、".join(asp["missing_checklist_items"]) or "-"
        lines.append(
            f"| {label} | {_VERDICT_LABEL.get(asp['verdict'], asp['verdict'])} "
            f"| {asp['confidence']:.2f} | {asp['support_count']}/{asp['refute_count']} "
            f"| {asp['unverified_count']} | {missing} |"
        )
    lines.append("")

    lines.append("## 三、节点论点与证据")
    lines.append("")
    for claim in dossier["node_claims"]:
        v = _VERDICT_LABEL.get(claim.get("verdict", ""), claim.get("verdict", ""))
        unv = claim.get("unverified_evidence_ids") or []
        errs = claim.get("binding_errors") or []
        note = f"；待验证线索 {len(unv)} 条" if unv else ""
        if errs:
            note += f"；⚠ 越界绑定 {len(errs)} 条已剔除({','.join(errs)})"
        lines.append(
            f"- `{claim['claim_id']}` [{NODE_ASPECTS.get(claim['dimension'], claim['dimension'])}] "
            f"{claim['claim_text']} — **{v}**"
            f"（支持 {claim['support_count']} / 反驳 {claim['refute_count']}{note}）"
        )
    lines.append("")
    lines.append("| 证据 | 门槛 | 范围 | 方向 | 页码 | 来源类型 | 发布 | 入库 | PIT | 权重 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for row in dossier["evidence_matrix"]:
        pub = row["published_at"] or "-"
        prec = row.get("published_precision", "")
        if prec and prec != "day":
            pub = f"{pub}({prec})"
        lines.append(
            f"| `{row['evidence_id']}` | {NODE_ASPECTS.get(row['aspect'], row['aspect'])} "
            f"| {_SCOPE_LABEL.get(row['evidence_scope'], row['evidence_scope'])} "
            f"| {_DIRECTION_LABEL.get(row['direction'], row['direction'])} "
            f"| {row['page_or_section'] or '-'} | {row['source_type']} "
            f"| {pub} | {row['ingested_at'] or '-'} | {row['pit_status']} | {row['verdict_weight']} |"
        )
    lines.append("")

    matrix = dossier.get("value_matrix")
    if matrix:
        lines.append("## 四、价值分配矩阵（节点 × 公司）")
        lines.append("")
        cols = matrix["columns"]
        lines.append(
            "| 代码 | 公司 | " + " | ".join(cols.values()) + " | dossier |"
        )
        lines.append("|---|---|" + "---|" * (len(cols) + 1))
        for r in matrix["rows"]:
            lines.append(
                f"| {r['stock_code']} | {r['company_name']} "
                f"| {_VERDICT_LABEL.get(r['tech_participation'], r['tech_participation'])} "
                f"| {_VERDICT_LABEL.get(r['validation_delivery'], r['validation_delivery'])} "
                f"| {r['verified_orders']} "
                f"| {_VERDICT_LABEL.get(r['revenue_profit'], r['revenue_profit'])} "
                f"| {r['concept_only_risk']} | {r.get('dossier_fingerprint','')[:10]} |"
            )
        lines.append("")
        lines.append("注：分产品收入未披露的公司如实标 needs_evidence，不推算收入份额。")
        lines.append("")

    lines.append("## 五、研究缺口（交 DATA 线）")
    lines.append("")
    lines.append("| 门槛 | 缺口 | 原因 | 优先级 |")
    lines.append("|---|---|---|---|")
    for gap in dossier["research_gaps"]:
        lines.append(
            f"| {NODE_ASPECTS.get(gap['aspect'], gap['aspect'])} | {gap['missing_item']} "
            f"| {gap['reason']} | {gap['priority']} |"
        )
    lines.append("")

    if dossier.get("binding_warnings"):
        lines.append("## 六、越界绑定告警（已剔除，不参与判定）")
        lines.append("")
        for w in dossier["binding_warnings"]:
            lines.append(f"- `{w}`")
        lines.append("")

    lines.append("## 附: 快照与护栏")
    lines.append("")
    snap = dossier.get("input_snapshot") or {}
    lines.append(f"- dossier_fingerprint: `{dossier['dossier_fingerprint']}`")
    lines.append(f"- evidence_set_sha256: `{snap.get('evidence_set_sha256','')}`")
    lines.append(f"- rule_version: `{snap.get('rule_version','')}`")
    if dossier.get("post_asof_excluded"):
        lines.append(f"- PIT 排除: {'、'.join(dossier['post_asof_excluded'])}")
    if dossier.get("pit_uncertain"):
        lines.append(f"- PIT 不定: {'、'.join(dossier['pit_uncertain'])}")
    g = dossier["guardrails"]
    lines.append(
        f"- 护栏: research_only={g['research_only']}, used_for_signal={g['used_for_signal']}, "
        f"used_for_admission={g['used_for_admission']}"
    )
    lines.append("")
    return "\n".join(lines)


def write_node_outputs(
    dossier: dict[str, Any],
    output_dir: str | Path,
    *,
    code_sha: str = "",
) -> dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{dossier['node_id']}_node.json"
    md_path = output / f"{dossier['node_id']}_node.md"
    payload = dict(dossier)
    if code_sha:
        payload.setdefault("input_snapshot", {})["code_sha"] = code_sha
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_node_markdown(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
