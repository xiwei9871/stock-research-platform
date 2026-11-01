# B0-1 生产备份现状核查 — stock_research @ 192.168.3.187

核查时间：2026-10-27。方法：DB 只读 SQL + 可达宿主机（stock-prod/185）与 NAS 遍历 + 本机 launchd/crontab。

## 逐项结论

| 核查对象 | 结果 |
|---|---|
| PG 数据目录 | `/var/lib/postgresql/data`（官方 docker postgres 路径） |
| Docker volume/快照 | **UNVERIFIED**——187 仅开放 22/5432，无 SSH 凭据，无法确认卷是否有快照机制 |
| WAL 归档 | `archive_mode=off`、`archive_command=(disabled)`、`archive_timeout=0` |
| 副本 | `pg_stat_replication`=0；`wal_level=replica`（具备建副本条件但未建） |
| pg_wal 现量 | 880MB |
| pg_dump 产物 | NAS `/postgresBackup` 94 个 dump 全部属 **192.168.3.88:9097 的 manq/mq_platform**，与 stock_research 无关 |
| 备份作业 | `185:/home/jqz/scripts/pg_backup.sh` 指向 192.168.3.88:9097；**不在 crontab**，末次产物 2025-11-13（~11 个月前，已停） |
| 185 crontab/systemd | 无针对 187/stock_research 的备份 job |
| 本机 launchd/crontab | 无 DB 备份项（dashboard-daily-sync/mem-watchdog/eod-publish 等均非 DB 备份） |
| NAS 其他目录 | `msDataBackup/`、`工作文件备份/` 等未见 stock_research dump |
| 对象存储/异地 | 未发现 |
| 恢复演练记录 | 无 |

## 判定

| 维度 | 判定 |
|---|---|
| stock_research 备份存在性 | **`BACKUP_NOT_FOUND`** |
| 187 宿主机卷快照 | **`BACKUP_UNVERIFIED`**（不可达，不能断定无快照；也不能当证据） |
| 恢复能力 | **`RESTORE_NOT_VERIFIED`** |

## 可用资源（供 B0-3 架构选型）

- NAS `//192.168.3.253`（59T，余 21T）：185 已挂载 `/mnt/Public`、`~/NAS`；适合落地 pg_dump/pg_basebackup 产物；
- 185（mqtestserver）：`/` 余 255G、`/mnt/data1` 余 1.1T；可作备份执行节点或中转；
- 本机：Homebrew PG16.14 独立实例（`stock_m2_test` 等）可作恢复演练目标；
- 187 不可 SSH → 备份执行只能从外部（pg_dump/pg_basebackup over 5432），或需用户协助开通宿主机访问。

## 缺口

- 686GB 全库无任何可恢复副本；单表/单日事故与全库灾难均无兜底；
- 无 WAL 归档 → 即使将来做了 basebackup 也只能恢复到备份时点（无 PITR）；
- 任何 T1/T4/F1-F4 动作前必须建立 B0 保障层。
