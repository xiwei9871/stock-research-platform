# P1d.3 — 生产迁移 Runbook（待审批，默认全部禁止执行）

目标：在 `core.asset_status_daily` 上建立 `limit_state_v2` 体系并让消费方分阶段切换。
每步独立、可单独回滚、需单独人工授权。预演证据：`p1d3_shadow.*`（17.29M 全量）、`prod_replica`（122 万行同形态 UPDATE/回滚演练）、`GRAY_GATE_CORRECTED.json`。

约定：所有命令在 canonical checkout `/Users/xiwei/stock_research` 下执行；DB 连接 `service=research`（192.168.3.187）。

---

## A. 仅执行 additive DDL（加列，不改既有列）

- **启动条件**：人工授权书 #1；低峰窗口（无 EOD 运行时段，避开 15:30–23:00）；已完成 `pg_dump -t core.asset_status_daily` 结构备份或全库快照确认。
- **预检查 SQL**：
  ```sql
  SELECT column_name FROM information_schema.columns
   WHERE table_schema='core' AND table_name='asset_status_daily'
     AND column_name IN ('is_limit_up_v2','is_limit_down_v2',
         'limit_state_v2','limit_rule_id_v2','limit_flags_version');
  -- 期望 0 行（列尚不存在）
  SELECT pg_total_relation_size('core.asset_status_daily');  -- 记录体积
  SELECT count(*) FROM pg_stat_activity WHERE state='active'
    AND query ~ 'asset_status_daily';  -- 期望无长事务占用
  ```
- **操作命令**：
  ```sql
  ALTER TABLE core.asset_status_daily
    ADD COLUMN IF NOT EXISTS is_limit_up_v2      boolean,
    ADD COLUMN IF NOT EXISTS is_limit_down_v2    boolean,
    ADD COLUMN IF NOT EXISTS limit_state_v2      smallint,
    ADD COLUMN IF NOT EXISTS limit_rule_id_v2    text,
    ADD COLUMN IF NOT EXISTS limit_flags_version text;
  ```
- **预期结果**：5 列新增、全 NULL；表不加索引不改 PK；秒级完成（仅元数据）。
- **自动终止条件**：DDL 持有 ACCESS EXCLUSIVE 锁 >10s 未获取（`lock_timeout='10s'` 建议设置）→ 语句自动放弃，改窗口重试。
- **独立回滚命令**：`ALTER TABLE core.asset_status_daily DROP COLUMN is_limit_up_v2, DROP COLUMN is_limit_down_v2, DROP COLUMN limit_state_v2, DROP COLUMN limit_rule_id_v2, DROP COLUMN limit_flags_version;`
- **对 EOD/生产影响**：无——新列全 NULL，v1 读路不变；`verified_v2` 读模式此时仍处于全 missing fail-closed（正确）。
- **需再次授权**：完成 A 后进入 B 前需独立确认。

## B. 启用 V2 EOD 增量写入

- **启动条件**：A 完成并验证；人工授权书 #2；`emit_v2_flags` 代码已随本分支合并上线。
- **预检查 SQL**：
  ```sql
  -- 确认当日 EOD status 行已写入后再 emit（顺序硬性依赖）
  SELECT count(*) FROM core.asset_status_daily
   WHERE trade_date = current_date;  -- 期望 ≈ 全市场行数
  ```
- **操作命令**：在 `build_asset_status_daily` 完成后，EOD 包装脚本追加：
  ```python
  emit_v2_flags(conn, today, today, 'core.asset_status_daily')
  ```
  （或先以 standalone 脚本手工跑 3 个交易日验证，再接线 cron。）
- **预期结果**：当日行 `limit_flags_version='pit_rules_v1'`，`limit_state_v2∈{1,2,3}`；emit 是纯 UPDATE——未预写 status 行则该行不更新（可审计漏写）。
- **自动终止条件**：emit 返回行数 < 当日 status 行数 → 报警并停接线（说明顺序/覆盖异常）。
- **独立回滚命令**：从 EOD 包装移除 emit 调用；已写当日行可 `UPDATE ... SET limit_flags_version=NULL WHERE trade_date=...` 清除。
- **对 EOD/生产影响**：每交易日 +1 次 ~5k 行 UPDATE（毫秒级）；v1 写路不变，双写并行。
- **需再次授权**：B 稳定运行 ≥3 个交易日后进入 C。

## C. 历史批次回填（17.29M 行）

- **启动条件**：A+B 完成；人工授权书 #3；确认窗口（建议周末）；`scripts/p1d3_migration_rehearsal.py` 已把 `SHADOW_TABLE`/`target` 指向 `core.asset_status_daily`（需一次显式目标切换改动，改动本身即授权动作的一部分）。
- **预检查 SQL**：
  ```sql
  SELECT count(*) FROM core.asset_status_daily
   WHERE limit_flags_version IS NOT NULL;  -- 应仅含 B 阶段 EOD 行
  SELECT max(trade_date) FROM p1d3_shadow.migration_log;  -- 影子证据存在
  SELECT count(*) FROM pg_locks l JOIN pg_class c ON l.relation=c.oid
   WHERE c.relname='asset_status_daily' AND mode='AccessExclusiveLock';
  ```
- **操作命令**：
  ```bash
  .venv/bin/python scripts/p1d3_migration_rehearsal.py --resume
  # 年度 37 批 + 自动二分；每批独立事务 commit；migration_log checkpoint
  ```
- **预期结果**：按预演吞吐 ~19k 行/s，全量 **~15–20 分钟**；每批 UPDATE 持 `RowExclusiveLock`（不阻塞读写）；单批 WAL ~20–40MB（实测），全量 ~4–5GB WAL——**须先确认归档/复制端 WAL 余量**。
- **自动终止条件**：DSM/DiskFull → 自动二分降级（已演练）；连续 3 批失败 → 脚本退出保留 checkpoint；`pg_stat_activity` 检测到 EOD 任务排队 → 人工暂停，次日续 `--resume`。
- **独立回滚命令**：`UPDATE core.asset_status_daily SET is_limit_up_v2=NULL,is_limit_down_v2=NULL,limit_state_v2=NULL,limit_rule_id_v2=NULL,limit_flags_version=NULL WHERE trade_date BETWEEN <批范围>;`（列级回滚已演练：checksum 归零、v1 不受影响。）
- **对 EOD/生产影响**：UPDATE 行锁与 EOD INSERT 无冲突（不同键）；建议仍避开 EOD 窗口。B 的当日 emit 与回填交错已被演练证明版本一致（同引擎）。
- **需再次授权**：C 校验通过后进入 D。

## D. 逐消费者灰度切换（读路）

- **启动条件**：C 完成 + 全量校验（v2 行数=17,294,002；verified 行 flag 与 corrected_shadow 抽样一致——GRAY 门禁已提供方法）；人工授权书 #4。
- **预检查 SQL**：
  ```sql
  SELECT limit_state_v2, count(*) FROM core.asset_status_daily GROUP BY 1;
  -- 期望 state=1 占绝对多数；2/3 少量且无 NULL state（NULL=未覆盖）
  ```
- **操作命令**：按消费者逐个改 `qualification_mode`（config/调用点），顺序建议：隔离回测 → dashboard 只读 → 正式回测。每改一个跑该消费者回归 + 与 corrected_shadow 对照一周。
- **预期结果**：`verified_v2` 读出的 flag 与规则引擎一致（影子表已证 0 mismatch）；`rule_unknown/data_insufficient` 行 continue fail-closed。
- **自动终止条件**：任一消费者出现 verified flag 与 corrected_shadow 不一致 >0 → 回退该消费者到 `corrected_shadow`。
- **独立回滚命令**：`qualification_mode` 改回 `corrected_shadow`（代码路径常设，无数据变更）。
- **对 EOD/生产影响**：无写路径变化。
- **需再次授权**：D 全部消费者稳定 ≥1 周后进入 E。

## E. 正式回测与依赖数据重新验收

- **启动条件**：D 完成；人工授权书 #5。
- **预检查/操作**：按 `NEEDS_REVALIDATION` 清单逐策略重跑（vectorized/retention/dashboard/mid_trend/serenity/dragon/emotion/LHB），与 legacy 基线对比并逐项归因差异。
- **预期结果**：差异全部可归因到 rule_id/缺失态；新基线文档化。
- **自动终止条件**：出现无法归因差异 → 暂停发布新基线，回到 D 排查。
- **独立回滚**：不发布重验结果即等同回滚；既有产物不覆盖（新目录/新版本号）。
- **对生产影响**：仅研究产物层，无实时信号改动（正式信号变更属单独任务书）。
- **需再次授权**：E 通过即迁移完成；退役 v1 写入/列属后续独立任务。
