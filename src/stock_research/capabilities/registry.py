"""CAP-00 capability registry — the CAP-00..CAP-10 capability map.

Each entry is a descriptor, not an implementation: it records the research
question, the existing reuse entry point, I/O contract, R0 minimum,
degradation behaviour, R1 acceptance, and DATA interface.  Keep this file
declarative — the executable skeleton lives in ``adapters.py``.
"""

from __future__ import annotations

from typing import Any

CAPABILITIES: dict[str, dict[str, Any]] = {
    "CAP-00": {
        "name": "总体架构与标准契约",
        "question": "各能力之间如何共享主题/节点/公司/产品线/证据/版本状态？",
        "reuse": "本包 contract.py + registry.py",
        "inputs": "能力描述符", "outputs": "ResearchEnvelope + 依赖图",
        "r0": "契约、注册表、依赖图、骨架可调用",
        "degraded": "n/a", "r1_gate": "全链路 smoke 通过",
        "data_interface": "无",
    },
    "CAP-01": {
        "name": "公司深度研究",
        "question": "公司技术/客户/订单/财务是否被证据支持？",
        "reuse": "company_intelligence.build_dossier / feed / report",
        "inputs": "case JSON + 证据 feed", "outputs": "六维 dossier",
        "r0": "冻结现有 dossier（已封版）",
        "degraded": "needs_evidence/unknown", "r1_gate": "已验收",
        "data_interface": "公司年报/公告/研报证据",
    },
    "CAP-02": {
        "name": "产业链节点研究",
        "question": "节点是否存在技术/工艺/供给瓶颈？",
        "reuse": "chain_bottleneck + chain_value_matrix + chain_t3_evidence",
        "inputs": "node case + dossier + T3 records", "outputs": "node dossier + 价值矩阵",
        "r0": "冻结（已封版）",
        "degraded": "bottleneck_unverified/needs_evidence", "r1_gate": "已验收",
        "data_interface": "T3 segment/validation/order/rival records",
    },
    "CAP-03": {
        "name": "主题研究编排",
        "question": "主题→节点→公司→研究任务如何串通？",
        "reuse": "theme_decomposition + theme_company_mapping + node case 目录",
        "inputs": "theme_id 或 case 目录", "outputs": "研究任务编排（节点/公司/待办）",
        "r0": "case 目录驱动的编排信封",
        "degraded": "theme package 缺失 → 从 case 文件枚举节点",
        "r1_gate": "主题→节点→公司链路无断裂",
        "data_interface": "主题拆解包/映射包",
    },
    "CAP-04": {
        "name": "技术路线与供需约束",
        "question": "技术路线、替代品、国产化、供需瓶颈视图？",
        "reuse": "node dossier 的 claim_role/五门 + evidence",
        "inputs": "node dossier", "outputs": "技术/供需视图信封",
        "r0": "claim_role 聚合视图",
        "degraded": "needs_evidence",
        "r1_gate": "稀缺/可替代/格局/壁垒/炒作五维齐全",
        "data_interface": "技术路线资料、竞品一手披露",
    },
    "CAP-05": {
        "name": "产业经济与价值分配",
        "question": "成本价值量、产品收入、盈利兑现关系？",
        "reuse": "chain_value_matrix + segment_cell + order_cell",
        "inputs": "node dossier + T3 records", "outputs": "revenue/margin/order 状态矩阵",
        "r0": "矩阵格状态信封（无数据输出 unknown+gap）",
        "degraded": "revenue_state=unknown + data_gaps",
        "r1_gate": "三节点矩阵一致输出",
        "data_interface": "分产品财报、订单、毛利",
    },
    "CAP-06": {
        "name": "竞争优势与同业比较",
        "question": "同节点/同产品线公司如何比较护城河证据？",
        "reuse": "价值矩阵行 + rival_supply + claim verdicts",
        "inputs": "node dossier + T3 records", "outputs": "同业比较表 + moat 证据位",
        "r0": "成员×维度对照信封",
        "degraded": "unverified",
        "r1_gate": "比较口径一致、不夸大",
        "data_interface": "竞品一手披露、份额/定价证据",
    },
    "CAP-07": {
        "name": "动态跟踪与催化因素",
        "question": "新事件是否改变既有研究状态？",
        "reuse": "指纹链 + news/policy 管线",
        "inputs": "基线信封指纹 + 新 run", "outputs": "变化清单",
        "r0": "指纹 diff 报告（无基线 → unknown）",
        "degraded": "unknown + gap(baseline)",
        "r1_gate": "变更可被追溯到证据差异",
        "data_interface": "公告/新闻事件流",
    },
    "CAP-08": {
        "name": "综合研判与反证",
        "question": "汇总证据、竞争假设、结论和不确定性？",
        "reuse": "本包聚合器（消费上游信封）",
        "inputs": "CAP-03..07 信封", "outputs": "综合研判 + 优先级 + 验证清单",
        "r0": "聚合信封（支持/反证/缺口/优先级）",
        "degraded": "上游全 unknown → partial + 全量 gaps",
        "r1_gate": "结论可追溯到上游指纹链",
        "data_interface": "全部上游 gaps 汇总",
    },
    "CAP-09": {
        "name": "研究工作台",
        "question": "研究链路如何统一浏览/复核/派发任务？",
        "reuse": "dashboard api + company_intelligence 面板 + review workflow",
        "inputs": "信封集合", "outputs": "视图指针 + 审核队列",
        "r0": "端点清单信封（不重建 UI）",
        "degraded": "端点缺失标注",
        "r1_gate": "统一入口可浏览三主题链路",
        "data_interface": "无（展示层）",
    },
    "CAP-10": {
        "name": "策略优化与验证",
        "question": "研究结论能否用于策略验证？（与研究隔离）",
        "reuse": "backtest/factor/strategy 基础设施",
        "inputs": "（隔离）策略资产清单", "outputs": "能力指针信封",
        "r0": "资产清单 + 隔离标记，不接信号",
        "degraded": "not_evaluated",
        "r1_gate": "研究结论不自动进入信号/准入",
        "data_interface": "无（复用现有策略数据）",
    },
}


def dependency_graph() -> dict[str, list[str]]:
    """CAP 依赖图（上游 → 下游）。"""
    return {
        "CAP-03": ["CAP-02", "CAP-01"],
        "CAP-04": ["CAP-02"],
        "CAP-05": ["CAP-04", "CAP-02", "CAP-01"],
        "CAP-06": ["CAP-05", "CAP-02"],
        "CAP-07": ["CAP-04", "CAP-05", "CAP-06"],
        "CAP-08": ["CAP-03", "CAP-04", "CAP-05", "CAP-06", "CAP-07"],
        "CAP-09": ["CAP-08"],
        "CAP-10": [],   # 与研究线隔离，仅复用策略基础设施
    }
