# M1-E DATA Integrity Gate

实现：`data_integrity_gate.py`；评估产物：`GATE_EVAL.json`。

## 状态机

- `READY`：契约+证据+覆盖满足；
- `DEGRADED`：数据在但证据/覆盖不确定；
- `BLOCKED`：来源/版本/必要证据缺失 → 不得作可信消费；
- `combine()`：**BLOCKED 永远占优**，READY 不能覆盖另一域的 BLOCKED。

## 域检查（只读）

tradeability：v2 列契约、flags_version 单一性、行数；
financial_pit：哨兵公告行数、raw payload 存量、版本化键数、版本层存在性。

## 当前评估

| 域 | 状态 | 理由 |
|---|---|---|
| tradeability（生产表） | READY | v1 状态完备；v2 列未上生产但 require_v2=False |
| financial_pit | DEGRADED | 93 哨兵行 + 三表无版本层（finver 仅隔离存在）+ ann>180d 异常未归因 |
| 组合 | DEGRADED | — |

M2 部署后目标：financial_pit → READY（finver 上线 + 哨兵核销）；财务+交易组合用于策略时按 combine()。
