# B0-3 推荐备份架构 — 分层、适度复杂度

不建设数据库高可用集群（与平台规模不匹配）。四层防御：

| 层 | 内容 | 频率 | 保留 | 建议 RPO/RTO（建议值，非已批 SLA） |
|---|---|---|---|---|
| **L1 变更前表级快照** | `pg_dump -Fc -t <变更表>`（T1 前打 asset_status_daily；F1 前打 finver+raw_akshare.finance_payload） | 每次获批变更前 | ≥90 天 | RPO=变更时点；RTO=小时级 |
| **L2 周期性全库逻辑** | `pg_dump -Fc` 全库，夜间低谷 | 周（686GB 约数小时，需实测） | 4 周 | RPO≤7天；RTO=日级 |
| **L3 物理基备+归档** | `pg_basebackup` + `archive_mode=on` 至 NAS | 基备月级+持续归档 | 基备2代+WAL 14天 | RPO≤15min；RTO=小时级 |
| **L4 finver 审计事件** | finver 三表 `pg_dump -Fc -t 'finver.*'` | 日（写入启用后） | ≥180 天 | 审计证据单独长保留 |

## 执行与落地

- 执行节点：stock-prod(185) 脚本节点 → NAS `/mnt/data1` 或 `//192.168.3.253`（21T 余量充足；L3 全量+压缩按 ~200-400GB 预算仍充裕）；
- `prod_backup_dryrun.sh` 提供全部命令模板，默认 dry-run；
- 备份文件强制 `sha256` + `pg_restore -l` 头校验；
- **每次 L1/L2 后做一次独立实例恢复抽样**（restore+checksum），否则只记 BACKUP_FOUND 不记 VERIFIED。

## 独立审批点（对齐 P0-D）

- B0-A：方案+资源审批（本文档）；
- B0-B：首次受控备份执行（L1 先行，L3 全量单独排窗）；
- B0-C：恢复演练（独立实例）；
- 归档配置变更（`archive_mode`/`archive_command`）：**独立审批动作**，不在 B0-B 隐含范围内。
