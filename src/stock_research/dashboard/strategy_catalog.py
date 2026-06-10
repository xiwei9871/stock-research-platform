from typing import Any


def list_strategy_catalog() -> list[dict[str, Any]]:
    return [
        {
            "strategy_id": "manual_v1_topn_rotation",
            "strategy_name": "Manual V1 TopN Rotation",
            "status": "diagnostic",
            "description": "Internal manual_v1 TopN baseline for diagnostics, not a validated combo strategy.",
            "factor_groups": ["momentum", "trend", "volume_price", "risk", "sector"],
            "signal_inputs": ["factor.stock_score_daily", "market_daily_bar"],
            "default_parameters": {
                "score_version": "manual_v1",
                "top_n": 20,
                "rebalance_frequency": "weekly",
                "max_positions": 20,
                "transaction_cost_bps": 10,
                "adjust_type": "hfq",
            },
            "latest_evidence": "",
            "primary_action": "Internal baseline",
        },
        {
            "strategy_id": "lhb_shortline",
            "strategy_name": "LHB Shortline Combo",
            "status": "runnable",
            "description": (
                "基于龙虎榜资金行为和盘中强弱确认，筛选短线资金关注度高、追涨风险可控的股票；"
                "组合用小仓位分散持有，并对冲高回落、涨停失败等风险做提前退出。"
            ),
            "factor_groups": ["资金行为", "竞价强弱", "盘中量价", "风险退出", "仓位控制"],
            "signal_inputs": [
                "龙虎榜净买占比",
                "机构净买",
                "重复上榜",
                "竞价强弱",
                "盘中量价确认",
                "冲高回落风险",
                "涨停失败风险",
                "分散仓位控制",
            ],
            "default_parameters": {
                "score_version": "manual_v1",
                "top_n": 20,
                "rebalance_frequency": "weekly",
                "max_positions": 20,
                "transaction_cost_bps": 10,
                "adjust_type": "hfq",
            },
            "latest_evidence": "2026区间净值 1.6341，最大回撤 -1.96%（实际明细 2026-01-05 至 2026-06-05）",
            "primary_action": "Run backtest",
        },
        {
            "strategy_id": "mid_trend",
            "strategy_name": "Mid Trend Combo",
            "status": "runnable",
            "description": (
                "从中期趋势股票池中选择趋势强、成交活跃、回撤可控的股票；每周调仓，"
                "限制单周替换数量，避免因为短期波动过度换仓。"
            ),
            "factor_groups": ["趋势强度", "收益动量", "成交活跃", "回撤控制", "持仓保护"],
            "signal_inputs": [
                "20日趋势强度",
                "20日收益",
                "成交活跃度",
                "价格回撤",
                "趋势延续质量",
                "持仓保护",
                "每周最多替换2只",
                "Top5组合",
            ],
            "default_parameters": {
                "score_version": "manual_v1",
                "top_n": 5,
                "rebalance_frequency": "weekly",
                "max_positions": 5,
                "transaction_cost_bps": 20,
                "adjust_type": "hfq",
            },
            "latest_evidence": "2026区间净值 1.5599，最大回撤 -17.52%（实际明细 2026-01-05 至 2026-06-02）",
            "primary_action": "Run backtest",
        },
        {
            "strategy_id": "tech_bottleneck",
            "strategy_name": "Tech Bottleneck Combo",
            "status": "runnable",
            "description": (
                "在趋势候选股中进一步寻找技术形态和成交确认较强的股票，偏向突破前后仍能保持强势的标的；"
                "用技术过滤减少弱反弹和假突破。"
            ),
            "factor_groups": ["技术形态", "趋势候选", "成交确认", "突破质量", "回撤控制"],
            "signal_inputs": [
                "技术瓶颈形态",
                "20日收益",
                "成交量确认",
                "收盘位置",
                "回撤控制",
                "趋势候选池",
                "假突破过滤",
                "Top5自适应调仓",
            ],
            "default_parameters": {
                "score_version": "manual_v1",
                "top_n": 5,
                "rebalance_frequency": "weekly",
                "max_positions": 5,
                "transaction_cost_bps": 20,
                "adjust_type": "hfq",
            },
            "latest_evidence": "2026区间净值 1.2351，最大回撤 -12.58%（实际明细 2026-01-05 至 2026-06-05）",
            "primary_action": "Run backtest",
        },
        {
            "strategy_id": "position_control",
            "strategy_name": "Position Control Overlay",
            "status": "diagnostic",
            "description": "Internal risk overlay used inside combo strategies, not a standalone Backtest Lab strategy.",
            "factor_groups": ["risk"],
            "signal_inputs": ["exposure cap", "risk budget", "drawdown state"],
            "default_parameters": {
                "score_version": "manual_v1",
                "top_n": 20,
                "rebalance_frequency": "weekly",
                "max_positions": 20,
                "transaction_cost_bps": 10,
                "adjust_type": "hfq",
            },
            "latest_evidence": "strategy_validation",
            "primary_action": "Internal overlay",
        },
    ]
