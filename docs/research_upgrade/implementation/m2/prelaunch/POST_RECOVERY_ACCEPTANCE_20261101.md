# 187 恢复后验收（2026-11-01，只读）

## G1 连接恢复：PASS（前一轮已验）

## G2 数据完整性：PASS（区分发布 vs 写入）

| 对象 | 实测 | 判定 |
|---|---|---|
| `ops.strategy_daily_eod_status` | 最后成功 publish = **2026-10-29**；10-30=`failed`（tabulate ImportError，非 DB 故障） | 发布口径以 10-29 为最后成功 |
| `ops.data_run_manifest` | 10-29 全模块 success；**10-30 无 manifest 行**（未 finalize） | 10-30 需人工重跑补齐（待审批） |
| `core.asset_status_daily` | 17,319,946 行，max=10-30 | 数据已写入且保留 |
| `public.market_daily_bar` | max=10-30 | ✓ |
| `factor.factor_daily` | max=10-30 | ✓ |
| `market.stock_minute_bar_2026_10` | max=10-30 15:00 完整收盘 | ✓ |
| `label/feature_snapshot` | max=07-27/08-27（非日更产物，正常） | ✓ |

**结论**：10-30 的原始行情/因子数据已落库并在事故中完整保留；缺的是 10-30 的 EOD 状态位与 manifest finalize——属于"未发布"，不是"数据丢失"。

## G3 防复发就绪：PARTIAL

| 项 | 状态 |
|---|---|
| 同盘备份源 | ✅ 已停（postgres-backup exited，unless-stopped） |
| NAS 新方案 | ✅ 设计验证完成 `scripts/l2_weekly_nas_backup.sh`（**未启用**） |
| mongodb | ✅ 磁盘释放后自愈（18:56 起 running，日志正常）——残留：16.1GB 日志文件待轮转 |
| Docker 日志轮转 | ⚠️ 需管理员改 daemon.json（方案在提案文档） |
| 磁盘余量 | 78.2GB（91%）——安全但偏紧，仍建议宿主扩容/继续归因清理 |

## 11-02（周一，交易日）写库任务矩阵

| 时刻 | 任务 | 写库 | 风险 |
|---|---|---|---|
| 05:30 | stock-trading-calendar-sync | 轻 | 低 |
| 09:15–15:10 | open-auction collectors（本机 crontab） | 轻 | 低 |
| 16:00 | stock-daily-close-daily | 中 | 中 |
| 17:00 | stock-daily-close-minute5-split | **重**（分钟线批量） | 中 |
| 18:30 | stock-daily-close-finalize | 中 | 中 |
| 19:00 | stock-platform-ready-build | 中 | 中 |
| 19:40 | stock-strategy-daily-eod | **重** | 中 |
| 19:55 | stock-platform-ready-check | 轻 | 低 |
| 常驻 | launchd tdx-watchdog/eod-publish/daily-sync | 轻 | 低 |
| — | minute/technical-feature/factor-gate backfill watchdogs | — | **已 disabled**，无重跑风暴 |

评估：任务分时排列、无并行风暴；DB 已正常 checkpoint。**无需暂停**；建议顺序保持原时刻表，人工盯 17:00 minute5-split 与 19:40 EOD 两个重点。10-30 EOD 重跑与 manifest 补齐需单独审批。

## 最终状态
`POST_RECOVERY_REVIEW_COMPLETE / CHANGE_APPROVAL_REQUIRED`
待审批：① `l2_weekly_nas_backup.sh` 调度启用（含 PGPASS_FILE 落位）；② 10-30 EOD 补跑；③ dockerd 日志轮转与 mongo 日志清理；④ 宿主扩容/非 pgdata 深度清理。
