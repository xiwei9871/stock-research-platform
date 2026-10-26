# P1d.3 — V2 Schema 与版本契约

## 列契约（additive，v1 原样保留）

| 列 | 类型 | 语义 |
|---|---|---|
| `is_limit_up_v2` | boolean | 规则引擎 verified 涨/跌停判定；state≠1 时无业务含义 |
| `is_limit_down_v2` | boolean | 同上 |
| `limit_state_v2` | smallint | **0** not_computed · **1** verified · **2** rule_unknown · **3** data_insufficient |
| `limit_rule_id_v2` | text | 命中规则 ID（`rule_unknown` 亦记录） |
| `limit_flags_version` | text | 计算版本，当前 `pit_rules_v1` |
| `is_suspended` | boolean（v1 复用） | 源数据 PIT 停牌状态（非规则派生），不重写 |

## 硬规则

- **verified 判定** = 规则命中 verified + 原始价（close/preclose raw）+ 历史状态三证据齐全，缺一 → state=2 或 3；
- **unknown/insufficient/not_computed 绝不写成 False** —— flag 列保留计算值但 state 明确非 1，读路以 `limit_state_v2 IS DISTINCT FROM 1` 为 missing；
- **禁止 `COALESCE(v2, v1)`** —— NULL v2 代表未算/未知，不是"沿用旧值"；
- **未校验旧数据不得赋予新版本号** —— `limit_flags_version` 仅由 emit 写 `pit_rules_v1`；
- **写入逻辑与 corrected_shadow 同一引擎** `compute_pit_limit_flags` —— 无平行实现；
- **读路契约**：verified_v2 模式要求五列齐全 + `limit_state_v2=1`，否则该行 missing → fail-closed。

## 版本演化

`limit_flags_version` 单调递增命名（`pit_rules_v1`, `pit_rules_v2`, ...）；规则引擎变更 → 新版本 emit 重算受影响窗口，version 串区分新旧判定；消费方按 (mode, version) 校验一致性。
