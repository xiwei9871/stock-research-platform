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

## 结论

**BACKUP_NOT_FOUND + RESTORE_NOT_VERIFIED 维持不变。** 恢复演练管线本身已验证可用；生产恢复能力依赖 B0-B（首次受控备份）与 B0-C（恢复演练）两个独立审批动作完成。
