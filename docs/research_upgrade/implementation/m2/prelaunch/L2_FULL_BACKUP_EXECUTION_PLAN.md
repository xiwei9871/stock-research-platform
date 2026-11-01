# L2 全库逻辑备份 — 限定范围执行计划（申请审批）

**本计划仅申请一次全库 `pg_dump -Fc` 执行权。不附带任何生产 Schema/数据/配置变更。**

## 范围与边界

| 项 | 值 |
|---|---|
| 动作 | `pg_dump -Fc` 全库 `stock_research`（只读快照） |
| 执行点 | 185 容器 `postgres:16.4-alpine`（PG16 客户端，与服务器同主版本） |
| 目的地 | `//192.168.3.253/Public/stock_research_backup/L2/`（NAS，20.3T 余） |
| 命名 | `.tmp_full_stock_research_{YYYYMMDD_HHMMSS}.dump` → 双校验 → `full_stock_research_{ts}.dump` + `.sha256` + `.list` |
| 明确不做 | 生产 DDL/DML、`archive_mode`、pg_hba、schema 变更、自动删除 |

## 资源与时间窗

| 项 | 估算/约束 |
|---|---|
| 输入 | heap+toast **312.5GB 实测**（索引不含在 data dump） |
| 产物 | **估 30–130GB**（10–40% 压缩率） |
| 时长 | **估 1.5–3 小时**（L1 3GB→29s 外推；不承诺） |
| 窗口 | 建议 **22:30 之后**（避开 09:15–15:30 行情、20:30–22:15 EOD+sync 链），次日 09:00 前必须完成或终止 |
| 吞吐 | 单连接顺序读；NAS 写 ~50-100MB/s 级（718MB 实测 ~90s） |
| 负载护栏 | `pg_dump` 为只读快照；执行前跑 `prod_readiness_check.py`：无长事务、无锁积压、无异常活动 |

## 停止条件（任一触发即中止）

- `pg_stat_activity` 出现因 dump 产生的锁等待；
- NAS 目标盘剩余 < 产物估算 ×1.3；
- 执行跨出批准窗口；
- dump 进程错误/连接中断 → 删 `.tmp_` 文件，不留半成品。

## 完成标准（全部满足才算 BACKUP_FOUND）

1. `.dump` 落 NAS 转正名；
2. `sha256` 与 `pg_restore -l` 双校验通过并落盘 `.sha256`/`.list`；
3. `MANIFEST.json` 登记 file/sha256/bytes/pg_version/scope；
4. **文件存在 ≠ 恢复已验证**——`RESTORE_VERIFIED` 须经下一步独立恢复演练。

## L2 恢复演练预案（backup 成功后再单独走）

- 目标：185 `/mnt/data1/restore_full/pgdata` + `postgres:16.4-alpine` 临时容器，`wal_level=minimal,max_wal_senders=0`；
- **容量实测已证**：`wal_level=minimal` 下 3GB 表恢复仅 16MB WAL → 全库 datadir ≈ 686GB+少量 WAL；
- 空间账：data1 可用 1.1T − 686GB datadir ≈ **414GB（38%）余量**，dump 读自 NAS 不占地；
- 验收：全表行数对账 + 抽样表 md5 + 关键 schema 完整性；
- 演练产物属临时证据，清理需管理员受控删除（现有 `restore_drill/`、`restore_drill2/` 残留 ~4.6GB，待 sudo 清理，**本轮不删**）。

## 批准后执行序列

```
prod_readiness_check.py (service=stock_research)   # 只读预检
docker run --rm postgres:16.4-alpine pg_dump -Fc \
  -h 192.168.3.187 -d stock_research \
  -f /backup/L2/.tmp_full_stock_research_<ts>.dump
sha256sum .tmp_*.dump && pg_restore -l .tmp_*.dump > .tmp_*.list
mv .tmp_* -> official names ; write MANIFEST.json entry
```

**本计划批准后，仅允许执行以上序列。**
