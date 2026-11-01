# 187 备份退出生产盘 — 新调度方案（待审批，未实施）

## 背景
原 `postgres-backup` 容器（crond 周日 00:00 `pg_dumpall|gzip` 写入同盘 volume）已停止（exited, unless-stopped）。原配置已存证：
`0 0 * * 0 pg_dumpall -h postgres -U postgres | gzip > /backups/.all-databases-$ts.sql.gz.tmp && mv && find -delete-old`
**恢复办法**：`docker start postgres-backup` 即还原（容器未删）。

## 新方案：NAS 直写 + fail-closed

执行节点 **185**（沿用 L2 已验证链路：`postgres:16.x-alpine` 客户端 → `pg_dump -Fc` → NAS），调度沿用现有 `scripts/m2_l2_backup.sh`（已具备全部 gate，已在生产验证过一次成功执行）。

| 设计要求 | 实现（沿用已验证脚本） |
|---|---|
| 数据直落 NAS | `docker run -v /mnt/Public/stock_research_backup/L2:/backup` 写 NAS 挂载点 |
| 禁止回退本地盘 | 无本地路径分支；目标路径硬编码 NAS |
| NAS 不可用即失败告警 | preflight：`mountpoint -q /mnt/Public` + probe 写测，失败 `exit 1` + 告警 |
| 容量检查 | `df` 余量 < 产物上限×2 则中止 |
| 完整性 | `.tmp` → `sha256sum` → `pg_restore -l` 列 22 schema → 合格才转正 |
| 清单 | `MANIFEST_L2_*.json` + `.sha256` + `.list` |
| 保留周期 | 保留最近 4 代，超期删最老（仅 L2 命名空间内，非通配） |
| 失败通知 | runner 输出 FAIL 行 + 日志；可接 OpenClaw 心跳告警 |
| 不产生本地临时件 | 全部临时文件在 NAS 同目录 `.tmp_` 前缀 |

调度建议：185 `cron` 每周 1 次（建议周三 02:00，避开周日高峰与月末批），生产侧只读，窗口内长事务门（>10min 中止）沿用。

## Docker 日志防涨（建议管理员执行，未实施）
现状：多容器 `LogConfig.Config={}` 无限制——mongo 事故日志已 16.1GB 且仍在写。
建议 `daemon.json`：
```json
{"log-driver":"json-file","log-opts":{"max-size":"100m","max-file":"3"}}
```
需 `dockerd` 重载并重建容器生效（或逐容器 `--log-opt` 重建）。叠加建议：尽快处理 tradingagents-mongodb 的崩溃循环本身（ENOSPC 受害者，现为持续日志写入源）。

## 待办/风险
- 需管理员执行：daemon.json 日志轮转、mongo 修复或暂停。
- NAS 挂载可用性依赖 185 `/mnt/Public`（CIFS）——建议加 NAS 断连监控告警。
- L2 现为每周级全量；如需更短 RPO 需另议 WAL 归档（当前 archive_mode=off）。

## P0-D 修订：与 `scripts/m2_l2_backup.sh` 的差距对照（已落实到 `scripts/l2_weekly_nas_backup.sh`）

| 要求 | 原脚本 | 新设计 |
|---|---|---|
| NAS 挂载有效性 | 仅 `df`（未挂载时返回本地盘统计，可能误写本地） | `mountpoint -q` + `/proc/mounts` 必须是 cifs/nfs/smb3，**无本地回退分支** |
| 容量不足 fail-closed | ≥500GB 阈值 | 保留 + 上述挂载门 |
| 告警 | 仅日志行 | `alert()` 钩子（FAIL/SUCCESS/留存清理），可接 OpenClaw 心跳/webhook |
| 保留与校验 | sha256+`pg_restore -l`+manifest | + schema 数 ≥20 断言 + **keep-4 保留轮转（仅 L2 命名空间）** |
| 凭证 | `PGPASSWORD=mqkj1234` 明文内嵌 | `PGPASSFILE`（chmod 600，容器只读挂载） |
| 全局对象 | 无 | `pg_dumpall --globals-only` sidecar（角色/表空间） |
| 与旧备份互斥 | 无 | Gate1：docker API 校验 `postgres-backup` 必须 `exited`，否则中止 |
| 不用 187 磁盘做临时落点 | 直写 NAS | 同 + mount 验证兜底 |
| 窗口/长事务/监控/可杀 | 已有 | 保留（去掉夜间窗口硬编码，由调度器决定时刻） |

未实施项：调度注册、PGPASS_FILE 创建、daemon.json 日志轮转、mongo 容器修复。
