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
                "top_n": 5,
                "rebalance_frequency": "daily",
                "max_positions": None,
                "max_position_weight": 0.2,
                "transaction_cost_bps": 10,
                "adjust_type": "hfq",
            },
            "latest_evidence": (
                "lhb_shortline_v1.1 实时从 DB 基础表重算；默认启用 "
                "first_risk80_gradient_2d90_3d80_4d70 市场仓位控制。"
                "Top5/20%/10bps 净值约 2.6069，最大回撤约 -5.32%。"
            ),
            "latest_metrics": {
                "as_of_date": "2026-06-08",
                "total_return_pct": 160.7,
                "max_drawdown_pct": -5.32,
                "latest_day_return_pct": None,
                "latest_day_drawdown_pct": None,
                "signal_status": "no_position_rows",
                "signal_count": None,
            },
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
            "latest_metrics": {
                "as_of_date": "2026-06-02",
                "total_return_pct": 55.99,
                "max_drawdown_pct": -17.52,
                "latest_day_return_pct": None,
                "latest_day_drawdown_pct": None,
                "signal_status": "no_position_rows",
                "signal_count": None,
            },
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
            "latest_evidence": (
                "严格科技瓶颈池 + ST剔除 + 每周Top5 + 市场环境仓位控制。"
                "2026-01-01 至 2026-06-08 净值约 1.6007，最大回撤约 -8.30%。"
            ),
            "latest_metrics": {
                "as_of_date": "2026-06-08",
                "total_return_pct": 60.07,
                "max_drawdown_pct": -8.30,
                "latest_day_return_pct": None,
                "latest_day_drawdown_pct": None,
                "signal_status": "no_position_rows",
                "signal_count": None,
            },
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
