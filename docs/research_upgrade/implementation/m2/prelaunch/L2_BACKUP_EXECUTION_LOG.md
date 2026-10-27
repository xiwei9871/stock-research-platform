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

## 结果

_（执行完成后填）_

## 状态定义

- `L2_BACKUP_VERIFIED` = 备份完成+文件级校验通过（**不**等于可恢复）；
- `FULL_RESTORE_VERIFIED` = 需下一轮独立恢复演练后获得。
