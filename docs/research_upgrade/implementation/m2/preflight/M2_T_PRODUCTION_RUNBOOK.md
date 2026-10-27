# M2-T Production Runbook（T1–T4）

**每步独立审批；批准 T1 不授权 T2–T5。**

## T1 — additive DDL

```sql
-- 执行 docs/.../sql/T1_asset_status_daily_v2_columns.sql
-- lock_timeout=5s；失败→重试窗口避开 EOD 20:00-22:00
```
执行前：`SELECT count(*), pg_size_pretty(...) FROM core.asset_status_daily`（17.3M/3GB 记录基线）。
执行后：post-check 5 列 is_nullable=YES。失败处理：锁超时→业务低峰重试；不得重试 >3 次无上报。
**回滚**：V2 未写数据 → `DROP COLUMN`（DDL 级回滚）；已写数据 → 不 DROP，走 E3 分级。

## T2 — 代码部署（开关 OFF）

部署 `eod_v2_writer.py`（含 `run_eod_v2_stage`）。验证：开关 OFF 时 stage 返回 blocked 且 V1 路径零变化；`import` 无错。回滚=代码回退。

## T3 — 增量启用（canary）

接入点：`daily_incremental._build_asset_status_step` 之后追加 V2 step（own-txn stage）。
- 首日 canary 日期范围由审批指定（建议单交易日）；
- 成功条件：`status=written`，`matched==base`，`invalid==0`，checkpoint 落 `v2_backfill_checkpoint`；
- 失败：`incomplete`/`blocked` → stage 已 rollback → 报警，不推进 V2 水位，V1 照常；
- 灰度 3 个连续交易日无 incomplete 后进入常态。

## T4 — 历史回填（执行器 `scripts/m2_t_backfill.py`）

**前置硬条件：备份证据（当前缺失 → 本步 BLOCKED）。**

```
python scripts/m2_t_backfill.py --service research --allow-prod \
  --target core.asset_status_daily --version pit_rules_v1 \
  --start 1990-12-19 --end <today> --throttle-ms 200
```

- 每日期一批事务：emit + 行数/合法性验证 + checkpoint commit；
- `running` 残留=被 kill 的批，下次运行自动重领；
- 限流 `--throttle-ms`；WAL 无归档→监控 `pg_ls_waldir` 大小与磁盘水位，超阈值 `--stop`（checkpoint 保留）；
- 结束全量审计：`audit_pending` 必须为空 + Gate 抽查 V2_READY；
- 17.3M 行不可承诺时长——按批监控推进速率。

**禁止**：用 `p1d3_migration_rehearsal.py` 改文档当生产回填（它默认 shadow 表）。

## T5 — 消费者灰度（M3 准入，不在本包）

## 常发故障处置

| 症状 | 处置 |
|---|---|
| stage incomplete | 查 missing_keys 对应资产是否缺 master/bar；补缺后重跑该日 |
| foreign version | 有人写入异版——停写排查来源，checkpoint 不动 |
| 回填速度异常 | 降并发=单进程已串行；增 throttle；查 dead tuples/锁等待 |
| V2 状态全 NULL | 检查 emit 是否被 enabled=False 挡住（开关语义） |
