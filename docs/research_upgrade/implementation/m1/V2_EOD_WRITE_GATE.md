# M1-B V2 EOD 写入 Gate（隔离验收）

实现：`eod_v2_writer.emit_eod_v2_flags`；演练：`scripts/m1_v2_write_drills.py` → `M1_V2_WRITE_DRILLS.json`。

## 前置条件（任一不满足 → blocked，零写入）

| 条件 | 实现 |
|---|---|
| 开关 | `enabled=False` 默认 OFF |
| Schema 契约 | 目标表须含 5 v2 列 + asset_id/trade_date |
| 基础状态先行 | `trade_date` 当日行数 > 0（emit 纯 UPDATE，基础未提交即拒绝） |
| 版本固定 | 当日已存在不同 `limit_flags_version` → 拒绝（不静默混版） |
| 幂等 | 当日全部行已载同版本 → `idempotent` 早退 |

## 演练结果（`m1_shadow.asset_status_daily`，3 真实交易日 15,569 行）

| 场景 | 结果 |
|---|---|
| 连续 3 日写入 | written，computed_keys>0/日 |
| 同日重复执行 | idempotent，checksum 前后一致 |
| 基础行缺失日期 | blocked |
| 开关 OFF | blocked |
| 版本冲突 | blocked |
| statement_timeout 注入 | aborted→rollback→0 残留 |
| unknown 状态 fail-closed | 0 行 state∈{2,3} 被置 v2 bool |
| 指标回报 | computed/matched/state_dist/missing_keys 全记录 |

**all_pass = true**。演练中发现并修复一个真实 bug：`_check_target` 集合运算 `|`/`-` 优先级 → 目标恒报缺列（已加括号修正，测试固化）。

## 生产接入顺序（M2 待批）

`ALTER core.asset_status_daily ADD 5 v2 列` → EOD 内 emit_eod_v2_flags(enabled=True) 于 build_asset_status_daily 之后同事务 → 部分失败即整日回滚，不推进 frontier。
