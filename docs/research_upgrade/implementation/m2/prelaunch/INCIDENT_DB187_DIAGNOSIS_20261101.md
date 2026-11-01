# 生产数据库 187 不可用事故诊断（2026-11-01，只读）

## 结论（RUNTIME_VERIFIED）
- **根因**：宿主机磁盘 936.8GB 写满至 0 可用。每周日 00:00 的容器化 `pg_dumpall|gzip` 备份任务把全库 dump 写入**与数据目录同盘**的 volume，00:00–00:58 写 ~20.6GB 后盘满 → checkpointer 写 `pg_logical/replorigin_checkpoint.tmp`（KB 级）失败 → `PANIC: No space left on device` → 每 ~15s 崩溃重试循环至今。
- **不是数据损坏**：WAL 重放瞬间完成（C13/D3F3AB0→D402ED0），redo done 干净；唯一阻塞是恢复末尾 checkpoint 的少量写空间。
- **EOD 失败是受害不是原因**：首个 recovery mode 报错 01:08 在盘满之后。
- **次生损害**：同主机 mongodb 因 ENOSPC 进入崩溃重启循环（1063 次重启、json 日志 16.1GB 仍在增长）；redis 崩 13 次后自愈。

## 关键实测
| 项 | 值 |
|---|---|
| 磁盘 | ext4 936.8G 用 891.6G 余 0；inode 1%；~47G 保留块被 root 进程继续消耗 |
| postgres 容器 | running 19d，RestartCount 0，非 OOM，内部 postmaster 循环重试 |
| pgdata | 704,524MB 完好；pg_wal 1025MB 正常；10-28 以来仅 +574MB |
| 事故文件 | 备份卷 `.all-databases-20261101-....tmp` 20.6GB（11-01 00:00→00:58）+ 10-10 失败残留 19.7GB + 10-25 完整 dump 40.7GB |
| 容器日志 | ~31GB 无 rotation（mongodb 16.1G、surveillance 11.6G、redis 3.4G） |
| 备份保全 | NAS 10-28 42GB dump + sha256 完好；185 演练实例存活可用 |

## 恢复方案（按风险升序，未执行）
1. 删备份卷内两个失败 `.tmp` 残留（~40GB，零数据损失）→ postgres 自动完成 checkpoint 上线；**无需重启/resetwal/恢复**。
2. truncate 崩溃循环容器的 json 日志（~30GB）。
3. 复发阻断：备份任务改投 NAS 或暂停（否则 11-08 00:00 重演）；mongo 修复或停循环；dockerd 配 log rotation。

## 定时任务
恢复后自动连库任务将按时刻触发；建议恢复后先核 `ops.data_run_manifest`/`ops.strategy_daily_eod_status`（10-30、10-31），重批量任务（minute5-split、tdx backfill）建议暂停至首个 EOD 成功，待审批。
