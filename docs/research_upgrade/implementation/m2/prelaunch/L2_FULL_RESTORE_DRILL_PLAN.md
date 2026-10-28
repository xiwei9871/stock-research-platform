# L2 全库独立恢复演练方案（待审批 — 未执行）

状态：**DRAFT_FOR_APPROVAL**。本文件仅为方案；任何执行需单独授权。

## 目标

将 NAS 上的 `full_stock_research_20261028_081226.dump`（41.3GiB，sha256 `023068df…2555ff`）在 185 `/mnt/data1` 的**独立** PG16 容器中完整恢复，用行数 + 抽样 checksum 对账生产，获得 `FULL_RESTORE_VERIFIED`。

## 边界（与生产零交互）

- 恢复实例监听 `127.0.0.1:55432`（185 本地），datadir=`/mnt/data1/l2_restore/pgdata`，容器名 `m2_l2_restore`；
- 唯一触生产的动作是**只读**对账查询（行数/md5），与现行只读核查同级；
- 不导入任何生产写流量；恢复实例 postgres 密码随机、不开放外部访问。

## 容量 Gate（预检）

| 项 | 阈值 | 当前实测 |
|---|---|---|
| `/mnt/data1` 可用 | ≥800GB | **1.1T ✅** |
| 恢复 datadir 预估 | ~686GB | — |
| WAL 增长 | `wal_level=minimal` + `max_wal_senders=0` → 实测 2.3GB 恢复仅 16MB WAL | — |
| 安全余量 | ≥200GB | ~400GB ✅ |

## 执行步骤

1. 校验 NAS dump 的 `.sha256`（重算比对，读侧）；
2. `docker run -d --name m2_l2_restore -v /mnt/data1/l2_restore/pgdata:/var/lib/postgresql/data -v /mnt/Public/stock_research_backup/L2:/backup:ro postgres:16.4-alpine -c wal_level=minimal -c max_wal_senders=0 -c archive_mode=off -c fsync=off`；
3. `pg_restore -d template1 --create` 或先 `CREATE DATABASE stock_research_drill` 后 `pg_restore -d`（-Fc 直接恢复，预计 2–4h）；
4. 监控：每 300s 记录 datadir 增长、data1 余量、容器健康；磁盘余量 <150GB 自动 `docker kill`；
5. 对账（恢复实例 vs 生产，均为只读）：
   - 行数：`core.asset_status_daily`、`raw_akshare.finance_payload`、`factor.factor_daily` 等 5–8 张代表表全等；
   - UTC 归一化 md5：抽样表/抽样日期与生产比对（沿用 L1 已验证方法）；
   - schema 覆盖：22 个业务 schema 全部存在。
6. 证据落盘：`RESTORE_VERDICT.json` + 对账明细 → 提交仓库；
7. **数据目录保留待审批清理**（沿用受控清理流程，不自动删）。

## 停止条件

data1 余量 <150GB、容器异常退出、restore 报错、超过 6h 未完成 → 中止并保留诊断。

## 授权请求范围

仅本次全库恢复演练（185 本地资源 + 生产只读对账）。不附带 T1/F1/T4/WAL 配置等任何其他生产变更。
