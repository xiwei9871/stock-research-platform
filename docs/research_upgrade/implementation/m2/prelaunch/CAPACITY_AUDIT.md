# CAPACITY-P1 生产数据库空间治理审计（只读，2026-10-28）

授权边界：只读审计。未执行 DROP / VACUUM FULL / pg_repack / ANALYZE / 任何 DDL/DML。EXPLAIN 均未加 ANALYZE。

## 0. 头条发现（审计改变了两个先前判断）

1. **187 数据盘 98% 满（937G 中仅余 21G）**——通过只读 `COPY FROM PROGRAM 'df'` 实测。pgdata 占 688G（base 687G + wal 881M），**~180GB 被 pgdata 之外占用**（docker 层/其他卷，容器内不可见 → 需宿主级介入，仍部分 UNVERIFIED）。空间治理从"优化"升级为"必要"。
2. **`backup` schema 不是历史垃圾，是活跃 R2 修订工作区**——文件 mtime 显示 `r2_write_manifest*` 写至 10-25、分片批件 10-21~10-23 持续产出，`r2_repair_batch.py`/`r2_rollback_batch.py` 活跃消费。重判 **DO_NOT_TOUCH**。
3. **`label_snapshot`/`feature_snapshot` 并非空表**——`n_live_tup=0` 系从未 ANALYZE 的过期统计，实测 ≥100K 行且有研究代码消费。撤回上一轮"0 活行"表述。

## 1. 容量总账（修正口径：pg_total_relation_size 仅对表/mv 计一次）

| 层 | 占用 | 备注 |
|---|---|---|
| factor | 270GB | `factor_daily` 独占 228GB（堆 75GB + **索引 169GB**） |
| market | 264GB | 分钟线为主 |
| public | 81GB | label_snapshot 45GB、market_daily_bar 22GB、feature_snapshot 14GB |
| raw_baostock | 25GB | 源数据，保留 |
| backup | 15.7GB | R2 活跃工作区 |
| staging | 11GB | 摄取暂存 |
| 其余 | ~12GB | shadow/研究/finance 等 |
| **合计** | **679GB** | = pg_database_size ✓ |

集群另有 `cn_a_stock_daily_hfq/qfq`（各 ~3.7GB）、`stock_research_e2e_test/theme_test`（~41MB）。

## 2. P0-A 索引审计（factor.factor_daily）

四索引全貌（精确字节 + 生命周期统计，stats_reset=NULL → 计数自集群初始化起累计）：

| 索引 | 大小 | 终身扫描 | 约束 | 结论 |
|---|---|---|---|---|
| pkey (trade_date,asset_id,factor_name,calc_version) | 43.7GiB | 3,977,870 | PRIMARY KEY | **DO_NOT_TOUCH** |
| idx_factor_daily_lookup (trade_date,factor_name,calc_version) | 4.7GiB | 836 | 无 | **KEEP**（EXPLAIN 证实为热路径首选） |
| idx_factor_daily_eval_lookup (factor_name,calc_version,trade_date,asset_id) | **55.0GiB** | **25（0 行读）** | 无 | **SAFE_CANDIDATE** |
| idx_factor_daily_asset_history (asset_id,factor_name,calc_version,trade_date DESC) | **54.2GiB** | **202** | 无 | **SAFE_CANDIDATE** |

证据链：
- 定义/依赖：pg_get_indexdef + pg_constraint 核查，两候选均不支撑任何约束；
- 消费代码：`factor_eval_store.py` 两处 `WHERE factor_name=%s AND calc_version=%s AND trade_date BETWEEN`——正是 eval_lookup 的服务形状；asset_history 对应单资产因子时序查询；
- EXPLAIN（无 ANALYZE）：Q1 `trade_date=`→lookup 索引；Q2 评估查询形状→**eval_lookup**；Q3 资产历史形状→**asset_history**。即：两索引是各自形状的**最优计划**，只是这些形状在实际负载中近乎不跑（25+202 次/生命周期）；
- 删除后果：评估/历史查询退化为 ~75GB 堆 seq scan（分钟级），热路径无损；
- 关键约束：**重建需等量临时空间**——在当前 21GB 余量下删了就地无法重建，需先扩空间或在恢复实例做。

## 3. P0-B 膨胀审计

详见 `TABLE_BLOAT_AUDIT.csv`。要点：
- `factor_daily`：死行 29.6%（1.07M/3.63M）≈ **~20GB 堆可回收**；统计新鲜（autoanalyze 运行中）；
- `label_snapshot`（45GB）/`feature_snapshot`（14GB）：有真实数据与研究消费方（labels/features/selection/backtest/snapshot_export），stats 从未刷新 → **NEEDS_EVIDENCE**（先 ANALYZE+消费方盘点）；
- `market_daily_bar`：11.7% 死行 ≈1.2GB，autovacuum 正常 → LOW_PRIORITY；
- 方法学：普通 VACUUM 只复用不缩文件；VACUUM FULL 锁表且需整表空间；`pg_repack` 需扩展 + ~75GB 临时空间——**在 A 索引删除腾空间前，factor_daily repack 物理不可行**。

## 4. P1-C backup schema 盘点

`BACKUP_SCHEMA_INVENTORY.csv`（151 张表全量：大小/扫描/写计数/文件 mtime）。mtime 证据链表明 **R2 修订批作业 10-21~10-25 仍在进行** → **DO_NOT_TOUCH**（R2 验收后整体归档 NAS 再 DROP）。

## 5. P1-D 存储与恢复能力

- 187 宿主盘：937G/用 869G/**余 21G**；180GB 非 pgdata 占用待宿主级确认；
- 遗留小库 `cn_a_stock_daily_*` 7.5GB 合计——若被 market.* 取代可单独审批；
- B0-C：**`L2_BACKUP_VERIFIED` 有效，`FULL_RESTORE_VERIFIED` 未获得**——恢复演练方案待审批，文件校验不等于可恢复。

## 6. 审批单摘要（详见 `CLEANUP_APPROVAL_MATRIX.md`）

| 单号 | 动作 | 收益 | 前置 | 状态 |
|---|---|---|---|---|
| A-1 | DROP idx_factor_daily_eval_lookup | +55.0GiB | 接受 eval 查询 seq-scan 退化 | SAFE_CANDIDATE |
| A-2 | DROP idx_factor_daily_asset_history | +54.2GiB | 同上 | SAFE_CANDIDATE |
| B-1 | label/feature_snapshot ANALYZE+消费方核实 | 待定 | 只读扩展（ANALYZE 批准） | NEEDS_EVIDENCE |
| B-2 | factor_daily pg_repack | ~20GB | A-1/A-2 完成后 | BLOCKED_BY_SPACE |
| C-1 | backup schema 归档+DROP | ~15.7GB | R2 验收完成 | DO_NOT_TOUCH 至今 |
| D-1 | 180GB 非 pgdata 占用排查 | ~180GB | 宿主级访问 | UNVERIFIED |
| D-2 | 遗留小库清理 | ~7.5GB | 确认被 market.* 取代 | NEEDS_EVIDENCE |
