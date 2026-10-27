# B0 NAS 备份落地执行报告（2026-10-27）

## 执行摘要

| 动作 | 结果 |
|---|---|
| L1 dump 复制到 NAS | ✅ `//192.168.3.253/Public/stock_research_backup/L1/asset_status_daily_20261027_164259.dump`（206MB），sha256 `e85233c2…429ace` **与源一致**；本机与 data1 副本保留 |
| PG16 客户端 @185 | ✅ 容器方式：`postgres:16.4-alpine` 镜像已在库，`docker run --rm` 即用即弃，**未动 PG14 安装** |
| finance_payload L1 | ✅ docker pg_dump16 直落 NAS：718MB `.tmp_`→校验→定名 `finance_payload_20261027_173205.dump`，sha256 `f3ec2d90…ddec4` + `pg_restore -l` 头校验通过 |
| 独立实例恢复 | ✅ 185 临时容器 `m2_restore_drill`（PG16.4，datadir on /mnt/data1）：**16,586 行**恢复；UTC 归一化 md5 与生产 **完全一致**（首次裸 md5 差异系时区渲染，非数据差异） |
| 判定 | **`raw_akshare.finance_payload`: BACKUP_FOUND + TABLE_RESTORE_VERIFIED** |

## L2 全库 dry-run 与资源预检（未执行真实 dump）

| 检查 | 结果 |
|---|---|
| schema-only dump 连通性 | ✅ 0.32s / 662KB（本机 PG18 客户端） |
| heap+toast 输入体量 | **312.5GB**（heap 310GB + toast 2.5GB；索引不含在 data dump 内，恢复时重建） |
| L2 单次产物估算 | **估 30–130GB**（10–40% 压缩率区间，JSON 负载压缩好、数值列较差） |
| `pg_basebackup` 前置 | ✅ `IDENTIFY_SYSTEM` 应答正常 → replication 协议放行，L3 路径技术上可行（仍待配置审批） |
| `/mnt/data1` 余量 | 1.1T（36% 用） |
| **恢复演练容量** | 需求 = 数据目录 ~686GB；dump 从 NAS 读取不占地 → 余量 **~414GB（38%）✅ 达标**；若 dump 也放 data1 则需 ~856GB 余 ~244GB（22%，偏紧） |

**恢复演练推荐：dump 留 NAS（cifs 读入没问题），data1 只承载恢复出的数据目录。**

## NAS 目录与 L2 设计

```
/mnt/Public/stock_research_backup/
  L1/            # 关键表变更前快照：{table}_{YYYYMMDD_HHMMSS}.dump[.sha256]
  L2/            # 全库逻辑：full_stock_research_{YYYYMMDD_HHMMSS}.dump[.sha256][.list]
  L3/            # 物理基备+WAL（待审批）
  MANIFEST.json  # 每份产物登记：file/sha256/source/db/scope/created/restored_at/verdict
```

约定：
- 一律 `.tmp_` 前缀写入 → `sha256sum` + `pg_restore -l` 双校验 → 去前缀转正；
- cifs 0777 挂载下文件 root 所有属正常（forceuid），以 sha256 而非属主做信任锚；
- 保留：L1 ≥90 天、L2 4 代、L3 2 代+WAL14 天、finver ≥180 天（建议值）；
- **过期清理永远人工审批**——本轮起不允许脚本自动 rm；清理动作 = `MANIFEST.json` 标记 expired + 人工 rm；
- 每次 L1/L2 后独立实例恢复抽样，结果写回 MANIFEST `restored_at/verdict`。

## 遗留事项

- 演练容器已删；datadir 残留 `/mnt/data1/restore_drill/pgdata`（容器 uid 属主，jqz 无权删）→ **需 sudo 清理**：`sudo rm -rf /mnt/data1/restore_drill`；
- 187 宿主访问、archive_mode、L2 真实 dump 均待独立审批。
