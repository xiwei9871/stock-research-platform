# R4 日线滚动复权修订机制 — 最小代码设计（隔离开发稿，未上线）

状态：**已批准隔离开发，未批准生产调度**。本文档仅为设计稿，不激活任何调度。

## 1. 问题定义

`market_daily_bar` 的 `qfq`/`hfq` 行按日写入后从不回头修订。供应商（baostock）会在除权除息发生后回溯修订 qfq（下调除权日前历史价）与 hfq（上调除权日后价格）。库存因此与源端漂移，且 `adjustment_factor`/`corporate_action`/qfq 分钟线/技术因子全部基于错误底层值派生，错误静默、不触发 freshness 告警。

已实证（2026-10-20）：600016 除权日 09-15，库存 qfq(09-14)=3.71=raw，源端已修订为 3.59；qfq 分钟线除权日前=raw；qfq_factor=1.0。

## 2. 检测：供应商历史修订

每日收盘管线内新增 `detect-adjustment-revisions` 步骤（在当日新数据写入之后、因子派生之前）：

- **触发集**：`market_daily_bar` raw 序列中 `preclose != prev_close`（容差 0.1%）的除权日探测 —— 与 R2 已验证的 603 事件同口径，成本为一次窗口扫描。
- **修订探测**：对候选股重新拉取 baostock qfq/hfq 日线（单 session，顺序执行），与库存逐行 diff 收盘价。仅在 |live−stored|/stored > 0.05% 时判定修订。
- **滚动窗口**：默认回看 120 个自然日（覆盖年报/中报分红密集期）；另加**窗口外校验**——每季度对全部活跃股做一次 1 年期 preclose 跳变全扫，捕获窗口外迟到事件。
- 纯 raw 侧探测（preclose 跳变）不依赖源端连接，可先标记候选再择机对拍，避免每次调度都全量 live 拉取。

## 3. raw 保护

- 修订步骤只允许写 `adjust_type IN ('qfq','hfq')` 的行；写入路径强制 `adjust_type` 白名单断言。
- `raw` 行的任何 UPDATE/DELETE 在修订任务内禁止（代码层硬约束 + 单元测试）。

## 4. 复权因子与派生重建

- 底层 qfq/hfq 修正后，对受影响股重跑 `build-adjustment-factors`（asset-scoped，非全市场）。
- `corporate_action` 由因子跳变派生：重跑后校验——事件数应 ≥ 检测到的 preclose 跳变数；对每股校验事件日 `factor_after/factor_before ≈ preclose/prev_close`。
- **qfq 分钟线**：除权日之前的所有 qfq 分钟分区需按新因子重写（除权日后因子=1 不变）。影响窗口 = 该股分钟线历史起点 → 除权日前一日。按月分区重 derive。
- **技术因子**：`stock_technical_features_daily` 基于 qfq，受影响窗口 = max(上市首日, 最长均线窗口 ma120 所需回溯) → 除权日+120 交易日后因子收敛为止；为安全起见对该股全历史重算（幂等 upsert）。

## 5. PIT / 版本隔离

- 修订行写 `source='baostock'`、`source_version` 携带修订批次号（如 `revision_20261020_r1`），与日常增量 `source_version` 区分。
- `updated_at` 天然区分写入时间——PIT 回放按 `as_of_date` 读数时须结合 `updated_at <= as_of` 过滤（现状已有该列）。
- 修订批次写 `market.minute_bar_backfill_job` 同款审计表（新建 `market.adjustment_revision_job`）：asset_id / ex_date / affected_rows / old_factor / new_factor / batch_id / applied_by / applied_at / rollback_ref。

## 6. 人工审核与回滚

- **阈值**：单日修订幅度 >5%、单次批次 >50 股、或 hfq 因子变化 >10% → 批次标记 `needs_review`，不落库，输出 diff 报告等人审。
- **回滚**：修订前把目标行 COPY 至 `backup.*`（本次 R2 已用 `backup.market_daily_bar_r2_samples_20261020` 模式）；回滚 = 备份行 upsert 回写 + 因子重建 + 审计表记 `rolled_back`。

## 7. 最小代码落点

| 组件 | 位置 | 性质 |
|---|---|---|
| `detect_preclose_events()` | `loaders/` 或新 `adjustment_revision.py` | 新增，纯 SQL |
| `diff_live_vs_stored(asset)` | 复用 baostock 查询封装 | 新增 |
| `apply_adjustment_revision(assets)` | 受控写 qfq/hfq + 审计 | 新增 |
| 因子/事件/分钟线/技术因子重建 | 复用现有 builder，按 asset 切片 | 复用 |
| 调度挂接 | `run_daily_close_pipeline_cron.sh` 中可选开关 | **默认关闭**，待批准 |

## 8. 验收清单（上线前）

- [ ] raw 行零改动的测试断言
- [ ] 修订幅度阈值触发 needs_review 的测试
- [ ] 因子重建后 corporate_action 事件与 preclose 跳变一致性校验
- [ ] 分钟线分区重写只对除权日前分区生效
- [ ] 回滚端到端演练（备份→改→回滚→diff=0）
