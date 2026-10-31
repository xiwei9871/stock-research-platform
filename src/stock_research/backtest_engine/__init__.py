"""Unified backtest execution engine (POC V0.1, research only).

Strategies emit target weights; the engine handles orders, fills, the
cash/share ledger, costs and daily valuation. Not wired into production EOD.
"""

from stock_research.backtest_engine.config import (
    ENGINE_VERSION,
    MODE_LEGACY_COMPAT,
    MODE_REALISTIC,
    RealisticExecutionConfig,
    StampDutySchedule,
)
from stock_research.backtest_engine.contracts import ContractError
from stock_research.backtest_engine.ledger import execute_target_weights
from stock_research.backtest_engine.legacy_compat import (
    LegacyCompatConfig,
    execute_legacy_compat,
)
from stock_research.backtest_engine.metrics import summarize

__all__ = [
    "ENGINE_VERSION", "MODE_LEGACY_COMPAT", "MODE_REALISTIC", "ContractError",
    "LegacyCompatConfig", "RealisticExecutionConfig", "StampDutySchedule",
    "execute_legacy_compat", "execute_target_weights", "summarize",
]
