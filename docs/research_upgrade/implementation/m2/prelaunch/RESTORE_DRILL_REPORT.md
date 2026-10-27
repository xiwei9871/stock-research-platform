# B0-4 恢复演练报告

## 已执行（独立实例 stock_m2_test，本机 PG16.14）

| 步骤 | 结果 |
|---|---|
| `pg_dump -Fc -t core.asset_status_daily`（24 行 fixture） | rc=0，2669B |
| `TRUNCATE` 后 `pg_restore --data-only` | rc=1（warning） |
| 恢复后行数+md5 对账 | **24/24 行，checksum 完全一致** |
| 判定 | **`TABLE_RESTORE_VERIFIED`（独立实例、小样本）** |

## 发现的兼容性问题

- 本机 pg_dump/pg_restore 客户端为 Homebrew PG18 系，服务器 16.14：`SET transaction_timeout = 0` 报 unrecognized（warning，恢复仍完成）。**生产恢复工具链必须用与服务器同主版本的客户端（16.x）**，已写入 runbook 前置检查。

## 未执行 / 判定

| 项 | 判定 | 原因 |
|---|---|---|
| 生产全库恢复 | `RESTORE_NOT_VERIFIED` | 无现存备份；686GB 恢复需 ≥700GB 独立盘，当前无资源，未获批执行 |
| 生产关键表恢复 | `RESTORE_NOT_VERIFIED` | 生产 dump 未执行（B0-B 待批）；本演练只证明工具链有效，不构成生产数据可恢复证据 |
| 187 卷快照恢复 | `BACKUP_UNVERIFIED` | 宿主机不可达，无法确认快照存在性 |

## 已执行 — 生产 L1（B0-B 批准，2026-10-27 16:43 CST）

| 步骤 | 结果 |
|---|---|
| `pg_dump -Fc -t core.asset_status_daily`（生产，本机执行） | 29s，206MB（3GB→7%） |
| `pg_restore -l` 头校验 + sha256 | 通过 `e85233c2…429ace` |
| 持久化 | `185:/mnt/data1/stock_research_backup/L1/`（sha256 复验一致） |
| 恢复到独立实例 `stock_restore_drill`（本机 PG16） | 17,299,191 行，min/max 日期一致 |
| 4 个抽样交易日 md5 逐行对账 | **全部一致**（2020-06-15/2025-01-02/2026-10-23/2026-10-26） |
| 判定 | **`TABLE_RESTORE_VERIFIED`（生产产物，core.asset_status_daily 范围）** |

注意：恢复需先 `CREATE SCHEMA core`（`-t` dump 不含 schema DDL）——已写入 runbook 前置步骤。客户端 18.3 vs 服务端 16.13 仍有 `transaction_timeout` 警告（恢复完成，数据无损）。

## 结论（更新后）

| 范围 | 判定 |
|---|---|
| `core.asset_status_daily`（L1 范围） | **BACKUP_FOUND + TABLE_RESTORE_VERIFIED** |
| 全库 686GB | **BACKUP_NOT_FOUND + RESTORE_NOT_VERIFIED** |
| 187 卷快照 | **BACKUP_UNVERIFIED** |

**表级恢复证据存在，不等于全库灾难恢复已验证。** T1（该表 additive DDL）的恢复前置已满足；T4（大批量写）按审批矩阵仍建议 ≥L2 兜底。
