# P2.1 回归差集

## 基线

worktree `.worktrees/r3-p21`，分支 `fix/r3-p21-financial-pit-shadow` @ `23ad1d40`（canonical 工作区与 P1d.3 分支均未触碰）。

## 变更

- `src/stock_research/financial_pit.py` **重写**（模块为 P2 新增、无既有调用方，行为变化按契约修正，非回归）：
  - 两级选择：先选目标报告期（默认最新已公开，非最早），再按 version_policy + source_preference 选版本；
  - 非法 as_of/report_period → ValueError（fail-closed）；
  - source_preference 显式参数 + 字母序稳定兜底；
  - 新增 pit_status `historical_version_missing`（initial_public 遇再披露签名行）；
  - operational availability 无证据 → None(UNKNOWN) + 理由标注；
  - restated 判定改为**同源多公告日**（多源不再误判重述）。
- `tests/test_financial_pit_p2.py` 扩至 17 例（新增非法输入、最新期默认、多源稳定、源优先、重述双策略、历史版本缺失、TTM 期间独立门）。
- 新增 scripts：`p21_reconciliation_audit.py`、`p21_consumer_shadow.py`、`p21_restatement_forensics.py`（均只读）。

## 测试

| 命令 | 结果 |
|---|---|
| `pytest tests/test_financial_pit_p2.py -q` | **17 passed / 0 failed** |

新增失败差集：**0**（无既有代码路径被修改）。

## 行为变化备忘

`announcement_date <= as_of` 在 P2 版曾为"同日可见"；P2.1 改为严格 `ann < as_of`（D+1）——`test_announcement_day_itself_is_blocked` 固化该语义。
