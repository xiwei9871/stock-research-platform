# CAPACITY-P1 清理审批矩阵（只读审计产出 — 未执行任何操作）

⚠️ **背景紧急度**：187 数据盘 `/dev/mapper/root-*` **937G 总 / 869G 用 / 仅 21G 余（98%）**。pgdata 占 688G，另有 ~180GB 非 pgdata 占用（UNVERIFIED，需宿主层查）。任何 repack/索引重建都先需要释放空间。

## A. 索引审批单（factor.factor_daily）

### A-1 `idx_factor_daily_eval_lookup` — 55.0GiB

| 项 | 内容 |
|---|---|
| 定义 | `btree(factor_name, calc_version, trade_date, asset_id)`，无约束依赖 |
| 使用 | 生命周期 **25 次扫描 / 0 行读**（stats 从未 reset）——但它是 `factor_eval_store.py` 评估查询的**设计索引**（factor_name+calc_version+date_range 形状，EXPLAIN 证实选中它） |
| 删除 SQL | `DROP INDEX CONCURRENTLY factor.idx_factor_daily_eval_lookup;` |
| 窗口 | 低活动时段（避开 evaluate 批作业）；CONCURRENTLY 不取表锁，但失败会留 INVALID 索引需重 drop |
| 性能影响 | 评估批量查询退化为 ~75GB 堆 seq scan（分钟级/次）；热路径（trade_date= 单日、单资产查询）不受影响 |
| 重建方案 | `CREATE INDEX CONCURRENTLY idx_factor_daily_eval_lookup ON factor.factor_daily USING btree (factor_name, calc_version, trade_date, asset_id);` —— **注意：重建需 ~55GB 临时空间，删后若盘仍紧张则无法原地重建**，须先在更大空间恢复实例或扩容后重建 |
| 回滚 | 仅重建一途；L2 dump 含索引定义可恢复 |
| 建议状态 | **SAFE_CANDIDATE**（条件：接受评估查询退化为 seq scan） |

### A-2 `idx_factor_daily_asset_history` — 54.2GiB

| 项 | 内容 |
|---|---|
| 定义 | `btree(asset_id, factor_name, calc_version, trade_date DESC)`，无约束依赖 |
| 使用 | 生命周期 **202 次扫描 / 4.1M 行读**——单资产因子时序查询形状，频次极低 |
| 删除 SQL / 重建 | 同 A-1 模式（`DROP/CREATE INDEX CONCURRENTLY`），重建同样需 ~54GB 空间 |
| 性能影响 | 单资产因子历史查询退化为 seq scan |
| 建议状态 | **SAFE_CANDIDATE**（同条件） |

### A-3 不动
`factor_daily_pkey`（43.7GiB，主键约束，398 万次扫描）与 `idx_factor_daily_lookup`（4.7GiB，当前热路径首选）→ **DO_NOT_TOUCH / KEEP_ACTIVE**。

## B. 表膨胀/空表审批项

| 对象 | 真实证据 | 建议动作 | 状态 |
|---|---|---|---|
| `factor.factor_daily` 堆 | 29.6% 死行 ≈ **~20GB** 可回收 | `pg_repack`（先装扩展；**需 ~75GB 临时空间 → 必须先删 A 索引腾空间**） | **NEEDS_EVIDENCE**（依赖 A 先执行） |
| `public.label_snapshot` | heap 18.5GB+idx 29.6GB；**有真实数据（≥100K 行）**，stats 从未 analyze 故死行未知；labels.py/selection/backtest 在消费 | 先 `ANALYZE` 摸清真实死行；若快照已被 research 新表取代则整表归档后 DROP | **NEEDS_EVIDENCE** |
| `public.feature_snapshot` | heap 7.4GB+idx 7.8GB；同上 | 同上 | **NEEDS_EVIDENCE** |
| `public.market_daily_bar` | 11.7% 死行 ≈ ~1.2GB，autovacuum 正常维护 | 不单独处理 | **LOW_PRIORITY** |

## C. backup schema —— **DO_NOT_TOUCH（本轮最大修正）**

文件 mtime 证据：`r2_write_manifest*` 至 **2026-10-25** 仍在写、`market_daily_bar_r2_b*` 分片 10-21~10-23 持续产生、`scripts/r2_revision/r2_{repair,rollback}_batch.py` 活跃消费。**这是进行中的 R2 修订工作区，不是历史快照**。15.7GB 在 R2 验收完成前不可动。完成后的归档方案：L2 已含全量 → 可整体 `pg_dump -n backup` 归档 NAS 后 DROP SCHEMA。

## D. 宿主机存储 —— **CRITICAL**

| 事实 | 来源 |
|---|---|
| 937G 盘仅余 21G（98%） | `COPY FROM PROGRAM 'df'` 实测（只读） |
| pgdata=688G（base 687G + wal 881M） | `du` 实测 |
| **~180GB 非 pgdata 占用**（docker 层/其他卷/日志） | df−du 差值，容器内不可见 → **UNVERIFIED，需宿主 SSH 或运维查** |
| 遗留小库 `cn_a_stock_daily_hfq/qfq` 各 ~3.7GB | pg_database_size；若已被 market.* 取代可单独审批 DROP |

**连锁影响**：A-1/A-2 删除是唯一能即刻腾出 ~109GB 且不新增占用的动作；B 的 repack 在 A 完成前**物理不可行**；建议同时追查 180GB 非 pgdata 占用。

## E. B0-C 状态维护

`L2_BACKUP_VERIFIED` 保持有效；**`FULL_RESTORE_VERIFIED` 仍未获得**——独立恢复演练方案（`L2_FULL_RESTORE_DRILL_PLAN.md`）待审批。文件级校验 ≠ 可恢复，本条不因容量审计而改变。
