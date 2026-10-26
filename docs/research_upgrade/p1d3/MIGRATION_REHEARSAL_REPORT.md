# P1d.3 — V2 历史交易资格受控迁移预演报告

分支 `fix/p1d3-migration-rehearsal` · 预演表 `p1d3_shadow.asset_status_daily_v2`（隔离 schema，生产表零改动）

## 结论

- **全量预演完成**：`core.asset_status_daily` 全部 **17,294,002** 行在影子表中完成 v1 列拷贝 + V2 flag 重算写入，总耗时 **901.2s（~19,189 行/s 端到端）**。
- **幂等**：重跑同批次 → checksum 完全一致（small/large 两批均 `idempotent=true`）。
- **回滚**：整批 DELETE → 重跑 → checksum 与原值一致（`restored_identical=true`；大批次演练 151s 内完成删除+重算+回写）。
- **断点续跑**：`p1d3_shadow.migration_log` 按批次记录 done；`--resume` 跳过已完成批次。

## 方法论（与生产迁移方案一致）

按自然年分 37 批（1990–2026）：
1. `INSERT ... SELECT` 拷贝 v1 列（is_limit_up/down、is_suspended）+ `batch_id` 标记；
2. `emit_v2_flags()` → `compute_pit_limit_flags()` 共享规则引擎重算 → `ON CONFLICT` upsert V2 列（`is_limit_up_v2/down_v2`、`limit_state_v2`、`limit_rule_id_v2`、`limit_flags_version='pit_rules_v1'`）；
3. `migration_log` checkpoint + **per-batch `conn.commit()`**；
4. 批内 metrics：rows/seconds/v1-vs-v2 diff。

## 全表普查：v1≠v2 差异 = **84,844 行**

本次预演顺带完成 1,729 万行**全量普查**（此前 62,937 为高风险制度区间的定向扫描子集口径）。差异集中在：

| 年份 | 差异行 | 主要原因 |
|---|---|---|
| 2015 | 16,610 | 牛市期间涨停潮 + IPO 窗口集中 |
| 2016 | 6,982 | 熔断/ST 规则边界 |
| 2020 | 6,077 | 创业板改革切换（8/24 前后 10%→20%） |
| 2019 | 5,592 | 科创板开市 + 创业板改革前段 |
| 2018 | 5,574 | ST/退市窗口 |
| 2017 | 4,180 | — |

84,844 ≠ 62,937：前者是全表 v1≠v2 行级差异（含扫描子集之外的现代窗口误标与旧值 NULL 行）；后者是去重后高风险区间的确认误标键数。两者口径不同，均如实保留。

## 预演发现的生产迁移要点

1. **DSM 溢出**：首个失败 run 在 `year_2017` 批触发 `DiskFull: could not resize shared memory segment` —— 容器 `/dev/shm` 受限 + 上下文三表 join 的并行 hash。处置：会话级 `SET max_parallel_workers_per_gather = 0`（共享库上更友好）+ `run_batch_safe` 自动二分降级。正式迁移需同样设置或更小批次。
2. **事务粒度**：`connect()` 仅在干净退出时 commit——单事务整轮意味着后期崩溃全部回滚。已改为 per-batch commit，与正式迁移 runner 的 checkpoint 语义一致。
3. **成本**：17.29M 行重算+写约 **15 分钟**（单连接、无并行）。生产表内 UPDATE 会持行锁；建议正式迁移采用「影子表全量构建 → 校验 → 按年批 UPDATE 或列级回填」路径，避开交易时段。
4. **EOD 增量**：`emit_v2_flags(conn, date, date, target)` 对单日窗口与批量共用同一引擎；正式启用顺序为 **先 ALTER 加列 → EOD 当日 emit → 再分批回填历史**（见 EOD_V2_WRITE_DESIGN.md）。

## 产物

- `MIGRATION_REHEARSAL.json` — 37 批 metrics + drill 结果 + migration_log
- `GRAY_READ_VALIDATION.json` — 灰度读路验证
- 脚本：`scripts/p1d3_migration_rehearsal.py`、`scripts/p1d3_gray_read_check.py`
