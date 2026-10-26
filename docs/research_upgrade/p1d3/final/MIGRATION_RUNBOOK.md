# P1d.3 — 正式迁移 Runbook（检查点版 · 默认全部禁止执行）

前置冻结基线：`MIGRATION_FREEZE.json`（run_id `p1d3-freeze-*`、表 17,294,002 行 / 3.0GB / 无分区 / 单 PK、v1 NULL flag 8,806、误标基线三口径、规则引擎 commit、flags_version=`pit_rules_v1`、批次 ledger=`p1d3_shadow.migration_log`）。

每步：**启动条件 → 预检查 → 操作 → 失败退出条件 → 回滚**；相邻步之间必须人工确认。

## 检查点 0 — 备份与状态确认
- 启动：人工授权
- 操作：`pg_dump -t core.asset_status_daily`（或快照确认）；记录 `pg_current_wal_lsn()`；核对 freeze 数字未漂移（行数/索引/分区）
- 失败退出：行数与 freeze 不符 → 停止排查
- 回滚：n/a（未改动）

## 检查点 1 — V2 additive Schema
- 启动：授权 + 低峰窗口（避开 15:30–23:00 EOD）
- 操作：`ALTER TABLE core.asset_status_daily ADD COLUMN IF NOT EXISTS` ×5（见 SCHEMA_AND_VERSION_CONTRACT）；`lock_timeout='10s'`
- 预期：秒级、元数据级、5 列全 NULL
- 失败退出：锁等待超时自动放弃，改窗口
- 回滚：`DROP COLUMN` ×5
- 影响：零——v1 读路不变；verified_v2 此刻仍全 missing（正确 fail-closed）

## 检查点 2 — EOD V2 双写上线
- 启动：#1 验证 + 授权
- 操作：EOD 包装在 `build_asset_status_daily` 传 `emit_v2_target='core.asset_status_daily'`（同事务双写）；先手工跑 3 个交易日再上 cron
- 预期：当日行 `limit_flags_version='pit_rules_v1'`；emit 行数==当日 status 行数
- 失败退出：行数不等 → 停接线报警；emit RuntimeError → 说明 DDL 未生效
- 回滚：移除 emit 参数；当日行 v2 列置 NULL
- 影响：+~5k 行 UPDATE/日；半完成批不可能推进（已演练）

## 检查点 3 — 历史分批回填
- 启动：#2 稳定 ≥3 交易日 + 授权 + 周末窗口 + WAL 余量 ≥5GB
- 操作：`scripts/p1d3_migration_rehearsal.py` 目标切 `core.asset_status_daily`（该切换改动即授权执行的一部分），`--resume` 年度 37 批
- 预期：~15–20min；RowExclusiveLock；`migration_log` 全 done
- 失败退出：连续 3 批失败 → 退出保留 checkpoint；EOD 排队 → 人工暂停次日续
- 回滚：按批 `UPDATE ... SET v2列=NULL`（checksum 归零已验证）
- 逐批对账：行数、state 分布、md5 checksum vs `p1d3_shadow.asset_status_daily_v2`

## 检查点 4 — 消费方灰度
- 启动：#3 对账全过 + 授权
- 操作：按 `CONSUMER_CUTOVER_MATRIX` 顺序逐一切 `qualification_mode`（先隔离回测 → dashboard → 正式回测）；每步该消费者回归 + corrected_shadow 对照 ≥1 窗口
- Gate：verified 键 flag+rule_id+version 与 corrected_shadow 0 mismatch；非 verified 全 fail-closed
- 失败退出：任一不一致 → 该消费者回退 corrected_shadow
- 回滚：模式参数改回（无数据变更）

## 检查点 5 — 历史回测与情绪数据重验
- 启动：#4 全消费者稳定 ≥1 周 + 授权
- 操作：NEEDS_REVALIDATION 清单逐策略重跑，差异逐项归因 rule_id/缺失态；`market_emotion_state_v1` 派生输入重算评估
- 失败退出：不可归因差异 → 暂停发布新基线
- 回滚：不覆盖旧产物（新版本号/新目录）

## 检查点 6 — verified_v2 设默认（后续独立任务）
- 仅在 #5 通过且 v1 依赖清单清空后评估；本轮不覆盖。

## 本轮边界
不执行生产 DDL、不启用 EOD 双写、不做生产 UPDATE、不切回测默认、不影响 EOD 调度。最终状态 `MIGRATION_PREFLIGHT_PASS`——可提交正式审批。
