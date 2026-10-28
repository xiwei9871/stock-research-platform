# L2 全库备份执行日志（B0-B 批准，2026-10-27）

## 预检 Gate（19:05 CST，全部通过）

| Gate | 结果 |
|---|---|
| 生产身份 | `172.24.0.2:5432 / stock_research / PG 16.13 Debian` |
| PG 客户端 | `postgres:16.4-alpine` → `pg_dump 16.4`（同主版本） |
| 生产状态 | 长事务 0、锁等待 0、副本 0、db 678GB |
| NAS 余量 | 20.3T（≥500GB 阈值） |
| `/backup/L2`→NAS 映射 | probe 文件容器写→宿主见→限定路径删除 ✅ |
| 可停止性 | `docker run --name m2_l2_dump` → `docker kill` 即停，生产只读快照不受影响 |
| 空间腾挪 | 未删任何既有文件 |

## 执行机制

`185:/home/jqz/m2_l2_backup.sh`（nohup pid 3765073）：
- 睡到窗口（22:30–09:00）；
- 窗口内重跑预检（pg_isready、长事务=0、NAS ≥500GB、可写 probe）；
- `pg_dump -Fc` → NAS `.tmp_` 文件；后台监控每 120s 记录产物大小+生产活动连接；09:00 deadline 强制 `docker kill`；
- rc=0 → sha256 + `pg_restore -l` → 转正 + `.sha256`/`.list`/`MANIFEST_L2_*.json`；
- 任何失败仅删本次 `.tmp_` 限定路径，记录 FAIL 日志；
- 全程日志：`185:/mnt/data1/stock_research_backup/l2_run_<date>.log`。

## 结果（2026-10-27 22:30 窗口 — FAIL-CLOSED ABORT）

**备份未执行。** 窗口内二次预检在 22:30:37 发现生产存在 **1 个长事务**，Gate 按设计 fail-closed 中止：

```text
[2026-10-27 19:05:35] runner started; waiting for 22:30-09:00 window
[2026-10-27 22:30:36] in window; running preflight
192.168.3.187:5432 - accepting connections
[2026-10-27 22:30:37] FAIL: long transactions present: 1
```

核实（2026-10-28 08:03）：
- NAS `L2/` 目录为空——**零字节产出**，无 `.tmp_` 残留；
- `m2_l2_dump` 容器不存在；runner 进程已退出；
- `pg_dump` 从未启动（此前 `pgrep` 计数为 ssh 命令行自匹配，非真实进程）；
- L1 产物（asset_status_daily ×2 + finance_payload + .sha256）完好无损；
- 生产侧无任何影响——dump 未开始即终止。

**状态：`L2_NOT_RUN_PREFLIGHT_BLOCKED`**（长事务门）。`L2_BACKUP_VERIFIED` / `FULL_RESTORE_VERIFIED` 均未获得。

**根因分析：** 22:30 与夜间 EOD 管线重叠（21:00 finalize、22:00 repair、22:15 deploy sync 均写生产库）。窗口起点需后移到夜间任务收敛之后（建议 ≥00:30），下一轮执行前先在 22:00–00:30 采样 `pg_stat_activity` 确认长事务来源与消散时间，再定窗口。

## 结果（2026-10-28 08:12 即时执行 — L2_BACKUP_VERIFIED）

用户确认无管线运行并批准立即执行（窗口约束由审批人覆盖）。`m2_l2_backup_now.sh`（同预检/监控/转正逻辑，去掉窗口等待与 09:00 killer）于 08:12:26 启动：

| 项 | 实测 |
|---|---|
| 执行窗口 | 08:12:27 → **10:19:53**（rc=0，2h7m26s） |
| 产物 | `full_stock_research_20261028_081226.dump` |
| 大小 | **44,327,786,055 B（41.3 GiB）**——678GB 库 → 6.5% 压缩比，落在预估 30–130GB 区间 |
| SHA256 | `023068df97f194aa67f0e9da6d168307c0ad06a7f0fbddab51edf490072555ff` |
| `pg_restore -l` | 通过；归档含 **22 个业务 schema**（backtest/backup/core/event/factor/finance/fundamental/identity/ingest/m1_shadow/market/ops/p1d1_shadow/p1d3_shadow/p1d3_test/raw_akshare/raw_baostock/report/research/simulation/staging/watchlist），grep SCHEMA 计数 26 |
| 转正链 | `.tmp_` → sha256 → `-l` → 改名 → `.sha256` + `.list` + `MANIFEST_L2_20261028_081226.json`（verdict `L2_BACKUP_VERIFIED`） |
| 监控 | 每 120s 记录产物大小+生产连接；全程 prod_active/total ≈ **2/7**，无锁等待尖峰 |
| 速率 | ~20GB/h 平均（CIFS 限速），峰值 ~430MB/min |
| 残留 | `.tmp_` 零残留、容器已 `--rm`、runner 已退出 |
| 快照一致性 | pg_dump -Fc 单事务快照，覆盖启动时刻（08:12:27）全部数据；开始后写入不在归档内 |

**状态：`L2_BACKUP_VERIFIED`**（文件级校验通过）。**`FULL_RESTORE_VERIFIED` 未获得**——待独立恢复演练。

**生产影响：0。** 备份为单连接只读快照；dump 结束后复核长事务=0。

## 恢复演练资源重估（2026-10-28）

- `/mnt/data1`：1.8T 总量，**1.1T 可用**（36% 已用）；`restore_drill{,2}` 残留仅 8KB（容器卷已回收，剩空目录）。
- 恢复需 ~686GB 数据目录（`wal_level=minimal` 下 WAL 可忽略）→ 余量 **~400GB（37%）**，容量判定 **可行**。
- dump 保留在 NAS 由容器挂载读入，不占 data1。
- 演练方案见 `L2_FULL_RESTORE_DRILL_PLAN.md`（待审批，未执行）。

## 状态定义

- `L2_BACKUP_VERIFIED` = 备份完成+文件级校验通过（**不**等于可恢复）；
- `FULL_RESTORE_VERIFIED` = 需下一轮独立恢复演练后获得。
