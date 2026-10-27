# M2-0-A — 生产只读评估（2026-10-27 实测）

## 环境实测

| 项 | 实测值 | 证据 |
|---|---|---|
| PG 版本 | **PostgreSQL 16.13**（Debian 容器，x86_64） | `version()` |
| 数据库 | `stock_research` @ 172.24.0.2（DB 宿主机 192.168.3.187 的容器网络） | `inet_server_addr` |
| 生产运行代码 | canonical `/Users/xiwei/stock_research` on `main@9bd95562`；LaunchAgent `com.stockresearch.strategy-eod-publish` 20:30 触发 `run_strategy_daily_eod_cron.sh` | plist + cron 脚本 |
| `core.asset_status_daily` | **17,299,191 行 / 3008 MB**，范围 1990-12-19→2026-10-26；仅 pkey 索引；**无 V2 列** | information_schema + count |
| 财务三表 | income 549,987 / balance 313,734 / cash_flow 313,006 | count |
| `raw_akshare.finance_payload` | 16,586 行 / **2554 MB**，观测窗 2026-07-09→10-23 | count |
| `raw_baostock.finance_payload` | 空表 — baostock 抓取**不写 raw**（`baostock_finance_ingestion` 无 payload 保存） | count + 代码 |
| finver 三表 | 仅存在于 `m1_shadow`（演练产物）；生产 schema 无 | information_schema |
| 连接/长事务 | 活动连接 1；>10min 长事务 0 | pg_stat_activity |
| 库体积 | **686 GB**（pg_database_size） | 实测 |
| WAL | archive_mode=**off**、archive_command 禁用、wal 目录 880MB、**副本 0** | SHOW + pg_stat_replication |
| 共享缓冲 | shared_buffers=128MB（异常低，16GB 主机） | SHOW |
| 表健康 | balance/cash_flow 各 ~50k dead tuples（近日批量更新痕迹）；asset_status_daily autovac 正常 | pg_stat_user_tables |

## 备份与恢复核验 —— **RESTORE_NOT_VERIFIED**

- 仓库、cron、launchd 中**未发现 pg_dump / pg_basebackup / 归档工具**任何证据；
- `archive_mode=off` → 无连续归档，**无 PITR 能力**；
- 副本数 0，无高可用/只读副本；
- 无恢复演练记录。

**结论：当前唯一"回滚"是逻辑层（重跑/反向 UPDATE/列丢弃）。任何生产变更的审批必须把"先做一次 pg_dump 或快照"列为前置条件。** T1 为 additive DDL 风险低；T4 17.3M 行 UPDATE 在无备份状态下风险不可接受——F/T 两条链的写步骤都要求先建立备份证据。

## 风险清单（入审批材料）

1. T1 `ALTER TABLE ADD COLUMN`（5 nullable 列）：PG16 下不加默认值的 ADD COLUMN 是元数据级操作，**不重写表**（3GB 表秒级完成），但需 `lock_timeout=5s` 防锁等待；无索引新增。
2. T4 回填 17.3M 行：预计 WAL 增量 ~数 GB（无归档仅占用 pg_wal 目录，需确认磁盘水位）；必须分批+checkpoint；**备份前置硬性要求**。
3. F1 新 schema：零风险。
4. F4 raw 回放 16,586 载荷（2.5GB 载荷列扫描）：只读生产+写 finver，单连接顺序回放即可，预计分钟级。
5. `shared_buffers=128MB` 偏低：大批量回填时 IO 主要走 OS cache，不测速不承诺时长。
