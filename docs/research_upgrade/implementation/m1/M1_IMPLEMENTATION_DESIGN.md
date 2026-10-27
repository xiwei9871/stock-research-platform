# M1 实施设计

## 范围

M1 = 阻止新增错误与证据损失。不做历史回填、不动生产。

| 子项 | 交付 | 状态 |
|---|---|---|
| M1-B | `eod_v2_writer.emit_eod_v2_flags` — emit_v2_flags 的安全门封装 | 实现+隔离演练 PASS |
| M1-C | `financial_version_store` — append-only 版本事件层 | 实现+隔离演练 PASS |
| M1-D | `financial_pit` 证据分级（VERIFIED/INFERRED/UNKNOWN + data_version + missing_reason） | 实现+测试 |
| M1-E | `data_integrity_gate` — READY/DEGRADED/BLOCKED | 实现+评估 |

## 关键设计取舍

1. **版本层独立而非加列**：三表 PK 无版本号，加普通列+旧 UPSERT 仍会覆盖 → 独立 `finver_event`（append-only）+ `finver_key_chain`（latest 指针）。生产三表语义零改动。
2. **emit 封装而非重写**：复用 `emit_v2_flags` 契约守卫；封装加开关、base-row 前置、版本固定、指标回报。
3. **fingerprint 归一**：指标按 round(v,4) 规范化后 hash —— 精度内抖动不产版本；字段级 `field_class` 决定 change_class。
4. **观测≠披露**：`first_seen_at` 只证明平台观测时刻；`announcement_evidence` 独立分级（vendor_supplied_date / unknown）；供应商数值变化 ≠ 公司正式更正。
5. **fingerprint 唯一约束** `(asset,st,ep,period,type,fingerprint)`：同指纹天然幂等；同键不同指纹 → version_seq+1 + supersedes 链接。

## 不变更清单

生产三表、UPSERT 语义、EOD 调度、hotfix、正式因子、回测结果、P1d.3 分支。
