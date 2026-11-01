# 任务B：185 隔离实例索引重建复验（2026-10-28/29）

环境：`m2_l2_restore`（PG16.4, wal_level=minimal, 185 `/mnt/data1`）。命令：`REINDEX (VERBOSE) INDEX CONCURRENTLY`（与拟议生产路径一致）。恢复证据已先固化（B0-C FULL_RESTORE_VERIFIED + QUERY_PERFORMANCE_BASELINE.json 已提交）。

## 重建实测

| 索引 | 重建前 | 重建后 | 耗时 | CPU(u/s) |
|---|---|---|---|---|
| factor_daily_pkey (32.7G) | 35,074,277,376 | 35,074,277,376 | 3,828s (64min) | 695/243 |
| idx_factor_daily_eval_lookup (35.1G) | 37,669,240,832 | 37,669,240,832 | 3,312s (55min) | 1315/232 |
| idx_factor_daily_asset_history (32.7G) | 35,142,139,904 | 35,142,139,904 | 3,136s (52min) | 1248/208 |
| idx_factor_daily_lookup (4.2G) | 4,460,068,864 | 4,460,068,864 | 673s (11min) | 519/69 |

尺寸不变是预期的：恢复实例的索引本来就是高密度新建（pkey 叶密度 90.19%）。**生产节省已在 STORAGE-R1 由"生产 vs 同定义新建"对比给出：合计 ~57GB**。本轮验证的是重建成本与安全性。

## 成本与峰值（185 实测）

| 项 | 实测 | 生产推算 |
|---|---|---|
| WAL/索引 | pkey ~27GB；eval ~32GB；asset_history ~30GB；lookup ~7GB | **≈0.85–1.0× 索引体积**（minimal 下仍全量记 WAL；生产 wal_level=replica 量级相同） |
| 磁盘瞬时峰值 | data1 used 峰值 1,223,198MB，较基线 +64GB（37.7GB 索引期间） | 单个大索引 CONCURRENTLY 需 **≈65GB 余量**（新索引+WAL+sort temp+余量） |
| 时间 | 52–64min/大索引 | 生产 IO 相当或更差，按 60–90min/个估 |
| 锁 | 全程对读写不阻塞；**首尾等老事务快照** | 须选无长事务窗口（同 L2 gate：xact<10min） |

## W2/W3 复验（要求重点）

| 负载 | 重建前(冷基线) | 重建后 | 计划 | 结果一致性 |
|---|---|---|---|---|
| W2 单资产时序 (asset_history) | 186,775ms | **13.79ms** | Index Scan asset_history（计划不变） | md5 `532d777e…` 前=后 ✅ |
| W3 回测批读 (eval_lookup) | 376,738ms | **2,982ms** | Index Scan eval_lookup（计划不变） | md5 `09a58c8a…` 前=后 ✅ |

**诚实归因**：重建前后计时差异不能全部归于索引密度——基线是恢复刚完成的冷缓存态，复验是暖缓存+已 ANALYZE。但可断言：**计划未退化、结果逐字节一致、无负优化**。冷/热差异本身提示生产实施时应伴随 ANALYZE 与缓存预热评估。

**索引膨胀 vs heap/TOAST 分工确认**：慢查询瓶颈是 610M×~120B 胖行的 heap 随机取数（索引扫描仅毫秒级），印证 STORAGE-R1 结论——收益来自密度修复的 I/O 缩减，不是"删掉坏索引"。

## 事故记录（对生产实施有价值）

1. **僵尸 worker**：客户端被杀后 CONCURRENTLY 重建的并行 worker 继续跑且持快照 → 会拖住后续 CONCURRENTLY 的快照等待；须先清理残留会话。
2. **`_ccnew` 碎片**：中断的 CONCURRENTLY 重建留下 `indisvalid=f` 的 `*_ccnew` 索引（本次 2 个 0 字节已 DROP CONCURRENTLY 清理）；生产执行失败路径必须含碎片检查清单。
3. **死锁**：`DROP INDEX CONCURRENTLY` 与 `REINDEX CONCURRENTLY` 在同年表上并行触发死锁（DROP 胜出，REINDEX 成牺牲品）→ **factor_daily 的维护操作必须串行**，禁止与其他 DDL 并发。

## 生产实施最低安全余量（推算）

| 前提 | 数值 |
|---|---|
| 可用磁盘 | ≥65GB/次（单大索引）；当前 20.5GB → **必须先完成宿主侧回收或扩容** |
| WAL/pg_wal 余量 | ≥35GB 瞬时（wal_keep/checkpoint 会推高） |
| 窗口 | 无 >10min 长事务 + 无同表 DDL（60–90min/个，4 个可拆 4 次执行，可回滚=删新索引即弃） |
| 失败清理 | 检查并 DROP `*_ccnew` invalid 碎片 |

## 结论
REINDEX CONCURRENTLY 路线在隔离实例验证通过：同定义重建**结果一致、计划不变、不阻塞读写**，代价是 ~60min/大索引、~65GB 瞬时空间、~30GB WAL。当前生产余量 20.5GB **不满足**——实施顺序：先宿主侧 ~186GB 归因回收（任务A清单）→ 单索引试点（建议 lookup→pkey→eval→asset_history）→ 每次后核对 `pg_stat_progress`、无效碎片与查询基线。
