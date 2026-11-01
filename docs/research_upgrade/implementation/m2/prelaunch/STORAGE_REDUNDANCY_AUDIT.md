# STORAGE-R1 无损存储冗余与性能优化审计（2026-10-28）

边界：生产全只读；重实验在 185 恢复实例（与 B0-C `FULL_RESTORE` 合流）。未执行 DROP/REINDEX/VACUUM FULL/pg_repack/DELETE/迁移。A-1/A-2 依指令重归 **KEEP_UNTIL_PROVEN_REDUNDANT**。

**里程碑：B0-C `FULL_RESTORE_VERIFIED` ✅** —— 41.3GB L2 dump 于 185 隔离实例 8h19m 完整恢复；行数/抽样 checksum/分区边界全对账（详见 `L2_BACKUP_EXECUTION_LOG.md` 恢复节；已知假象：alpine musl vs Debian glibc 的 collation 排序差异致 text-ORDER-BY md5 不一致，字节排序后数据 IDENTICAL）。

**恢复附带铁证：恢复后 pgdata 仅 ~518GB vs 生产 679GB → 生产整体膨胀/死空间 ≈161GB**，与分解估算一致。

## P0 真实空间归因（`PHYSICAL_STORAGE_BREAKDOWN.csv`）

分层口径（全部实测，无 df−du 臆断）：

| 层 | 量 | 证据 |
|---|---|---|
| 宿主盘 ext4 | 937G 总 / 869G 用 / **20.5G 可用**（另 ~47G 为 root 保留块） | `df` 服务端实测 |
| pgdata | **688G**（base 687 + wal 0.88） | `du` 服务端实测 |
| 库 stock_research | 679G（堆估 ~280G + **索引估 ~233G** + 死元组估 ~28G + TOAST/FSM 残余） | pg_database_size + 逐表分解 |
| 遗留小库 | cn_a_stock_daily_hfq/qfq 7.5G + 测试库 0.04G | pg_database_size |
| **非 pgdata 差额** | **~180G 未归因** | 与 `/var/lib/docker`（overlay2/其他卷/容器 json 日志）及宿主目录同盘，容器内不可见 |

**180GB 归因对账**：容器内 `du /` 仅见 688G(pgdata)+0.4G(usr)。mount 表证实 pgdata 是命名卷 `postgresql_postgres_data`，宿主 `/var/lib/docker/*` 与其余宿主目录同在一个 ext4 → 差额几乎必然在 docker 数据根 + 宿主系统，**但不排除**其他业务卷。宿主侧只读核查清单（管理员执行）：`du -sh /var/lib/docker/{overlay2,volumes,containers} | sort -rh`、`docker system df -v`、`find / -xdev -size +1G`、`journalctl --disk-usage`、检查已删未释放文件 `lsof +L1`。

## P1 索引优化（`INDEX_BLOAT_AND_OVERLAP.csv`）

factor_daily 四索引共 **169.3GB vs 堆 75.2GB**（2.25:1 极罕见）。关键结构事实：**四个索引覆盖同一组 4 列**（trade_date/asset_id/factor_name/calc_version），只是列序不同——每份都是 610.7M 行的全量键序副本。

| 索引 | 角色 | 结论 |
|---|---|---|
| pkey (td,asset,factor,ver) | 唯一约束+热路径 | DO_NOT_TOUCH |
| lookup (td,factor,ver) | 日期扫描首选（较短键宽） | KEEP_ACTIVE |
| eval_lookup (factor,ver,td,asset) | eval 查询形状最优（25 次/终身） | **KEEP_UNTIL_PROVEN_REDUNDANT** |
| asset_history (asset,factor,ver,td DESC) | 单资产时序形状（202 次） | **KEEP_UNTIL_PROVEN_REDUNDANT** |

**无损优化候选（恢复实例实测证据，`QUERY_PERFORMANCE_BASELINE.json` / `INDEX_BLOAT_AND_OVERLAP.csv`）**：
1. **REINDEX CONCURRENTLY 密度修复（首推）**——生产 vs 同定义全新构建对比：pkey 43.7G→32.7G（**膨胀 25.3%**）、eval 55.0G→35.1G（**36.3%**）、asset_history 54.2G→32.7G（**39.6%**）、lookup 4.7G→4.2G（11.4%）；**factor_daily 合计可回收 ~57GB，不改定义、查询零影响**。新 pkey 叶密度实测 90.19%。约束：重建需 ~等量临时空间（~35–40GB/个），当前 21G 余量下**不可行**，须先 R0 归因或其他释放；
2. 慢查询真因：W2/W3 实测 186.8s/376.7s 但瓶颈是 **610M 行×~120B 胖行的 heap+TOAST 随机取数**，索引已是最优——删索引救不了慢查询，反而是 REINDEX+ANALYZE 能减少 I/O；
3. `lookup` 仅 4.2G 的机理：3 列键重复度极高触发 btree dedup——已是近最优，不动；
4. 任何变更需"查询结果一致 + 计划不退化"双验收。

## P2 重复与快照（`DATA_DUPLICATION_MATRIX.csv`）

| 结论 | 证据 |
|---|---|
| 分钟线 default(2020–23) vs 月度分区(2024–26)：**零重叠** | 分区界 disjoint + default 实际范围 2020-01-02~2023-12-29 |
| `unpartitioned_backup`：96 行测试残留 136KB | 可忽略清理候选 |
| `public.market_daily_bar`：**非重复，是 canonical 日线**（market 无 stock 级日线表） | schema 盘点 |
| factor_daily calc_version：v1=610.67M(99.999%) + rolling=5.5K，**无冗余版本** | GROUP BY 实测（并修正 n_live_tup 陈旧统计） |
| label/feature_snapshot：**canonical 长表**（67.6M/63.3M 行），stats 从未刷新 | 列结构+消费代码 |
| staging→market 落地重叠（tdx auction / baostock 分钟线）：**UNTESTED**，恢复实例上做键匹配率 | 待定 |
| backup schema：**R2 活跃工作区** DO_NOT_TOUCH | mtime 证据 |
| 遗留库 cn_a_stock_daily_*：待证被 market.* 取代 | NEEDS_EVIDENCE |

## P3 压缩分层（`DUCKDB_PARQUET_FEASIBILITY.md`）

S1（PG 内部优化）先行 → S2（冻结分钟线 2020–2024 → Parquet+DuckDB，净释放估 180–240GB，副本 25–40GB）分段评估 → S3（零复制联邦）搁置。S2 前置：行数/checksum 双验、查询路由改造量、备份代际覆盖。

## P4 性能基线（`QUERY_PERFORMANCE_BASELINE.json`）

6 类代表工作负载将在恢复实例用 `EXPLAIN ANALYZE` 实测记录：单日全市场因子、单资产多年时序、回测批量读取、分钟线区间、多因子筛选、EOD 增量。验收门=结果一致+核心查询不退化+净收益可量化+可回滚+资源受控。

## 增长与风险

- 有机增长 **~250–300MB/天**（factor ~86MB + 分钟线 ~133MB + 杂项）→ 纯按速率 ~2 个月余量；
- **真正风险是峰值**：temp_bytes 累计 276GB 说明重 spill 常态存在，单次大排序可吃掉 20G 余量；索引重建/repack 均不可行（空间不足）；
- WAL 低峰 ~18MB/天（夜批有峰），881MB 稳态。

## 决策（`STORAGE_OPTIMIZATION_ROADMAP.md`）

**不必须删 A-1/A-2**；优先级改为：① 宿主 180GB 归因（管理员只读清单）→ ② 恢复实例索引密度+计划验证 → ③ S1 无损优化分批 → ④ S2 冻结数据 Parquet 试点 → ⑤ 必要时扩容。当前 20.5G 可用对未来数个交易日**够用但无安全余量**，一次异常 spill 即触顶。
