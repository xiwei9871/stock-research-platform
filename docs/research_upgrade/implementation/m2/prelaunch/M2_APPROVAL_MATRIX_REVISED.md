# M2 审批矩阵（修订版）— 插入 B0 保障阶段

**批准任一步不授权后续步骤；备份文件生成 ≠ 恢复已验证。**

| 阶段 | 动作 | 前置条件 | 停止/回滚 | 本轮状态 |
|---|---|---|---|---|
| **B0-A** | 备份方案+资源审批 | 只读核查（已完成：BACKUP_NOT_FOUND） | — | **已批准（L1 范围）** |
| **B0-B** | 首次受控备份（L1 表级先行，L2/L3 排窗） | B0-A 批准 + 资源确认 | kill 作业；半成品文件删除 | **L1(asset_status_daily) 已执行**；finance_payload L1 与 L2/L3 待续批 |
| **B0-C** | 独立实例恢复验证 | B0-B 产物 | — | **L1 已通过**（17.3M 行 checksum 一致） |
| T1 | asset_status_daily +5 列 | **对应表恢复保障已验证（L1 dump+恢复演练）** + DDL 窗口已批 | 锁超时×3 / post-check 不符 | **恢复前置已满足，可申请（需 DDL 窗口批准）** |
| F1 | finver 空 schema | 恢复保障（至少 L2/L3 或表级兜底达成）+ SQL 已批 | 未写数据前 DROP SCHEMA | 待 B0-C（至少 L1 兜底可论证） |
| T2 | writer/stage 部署（OFF） | T1 完成 | 代码回退 | 待 T1 |
| T3 | 增量 canary | T1+T2 + `evaluate_eod_canary` 逐日验收 | 关 enabled；incomplete 不推水位 | 待 T2 |
| F2 | 抓取侧部署（OFF） | F1 完成 | 代码回退 | 待 F1 |
| F3 | canary 资产版本写 | F1+F2 + `evaluate_finver_writer` 新鲜度验收 | 关开关；事件保留 | 待 F2 |
| T4 | 17.3M 回填 | **可恢复备份（≥L1 表级 VERIFIED，建议 L2/L3）+ checkpoint SQL 部署 + 回填器安全验收（已 15/15）+ 磁盘/WAL 水位证据** | stop-file/SIGTERM；ckpt 续跑 | **BLOCKED（无备份）** |
| F4 | raw 历史回放 | F3 + checkpoint/范围验收 + 资源 Gate | 暂停续跑；事件不删 | 待 F3 |
| T5/F5 | 消费者灰度 | M3 准入 | — | 不申请 |

## 首个可申请动作

**B0-A**（备份方案与资源审批）——所有生产写动作的前置。

## 禁止重申

- 生产 DDL/写入/EOD 接线/消费者切换/合并 main；
- 宿主机卷快照方案在未取得 187 访问权前不得当作已验证保障；
- "备份文件已生成"一律不得记为"恢复已验证"。
