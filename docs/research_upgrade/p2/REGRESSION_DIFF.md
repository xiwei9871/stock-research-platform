# P2 回归差集

## 基线

- 分支 `data/r3-p2-financial-pit-audit` 自用户本地修改状态创建（含 P1d.3 产物的本地回退，未触碰）；
- 本轮**全部为新文件**，未修改任何既有源码/测试/生产表。

## 测试

| 命令 | 结果 |
|---|---|
| `.venv/bin/pytest tests/test_financial_pit_p2.py -q` | **10 passed / 0 failed** |

全部为真实数据库断言（同日阻断、哨兵 fail-closed、退市历史可查、幂等、多版本策略），非合成数据。

## 相对基线新增失败

0 —— 本轮未改动任何被既有测试覆盖的代码路径；`financial_pit.py` 为纯新增模块，无既有调用方。

## 代码变更清单

新增：
- `src/stock_research/financial_pit.py`（PIT 接口，只读）
- `scripts/p2_financial_pit_audit.py`（只读审计脚本）
- `tests/test_financial_pit_p2.py`
- `docs/research_upgrade/p2/`（13 项产物）

修改：**无**。
