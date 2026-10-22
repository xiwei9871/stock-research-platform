# 03 — Intraday Feature Recovery Validation (M0.7 / P0-3)

Date: 2026-10-20. Status: **isolated validation PASSED / production backfill
awaiting approval**.

## Stale chain

`factor.stock_intraday_features_daily` + `factor.industry_intraday_features_daily`
最新 **2026-08-03**；`build-intraday-features-daily` CLI 存在但无任何调度。影子
健康报告判定两表 DEGRADED（可选增强，非阻断）。

## 隔离验证（compute-only，零生产写）

`intraday_features` 结构为 load → build(纯函数) → upsert 三段，故隔离验证 =
load+build 后落 CSV、跳过 upsert。代码：
`src/stock_research/intraday_features.py:44/98/219/261`。

样本：最近两个已收盘交易日。

| 交易日 | minute bars | 覆盖股票 | 特征行 | 幂等 | 
|---|---|---|---|---|
| 2026-10-16 | 249,072 | 5,189 | 51,890 (5189×10) | 复算字节级一致 ✓ |
| 2026-10-19 | 248,928 | 5,186 | 51,860 (5186×10) | ✓ |

特征清单（10 项）：`morning_return, close_to_vwap, intraday_return,
afternoon_return, amount_front_1h_ratio, amount_tail_1h_ratio,
close_position_in_day, intraday_volatility_5min, last_30m_return,
max_intraday_drawdown`。

三大消费特征分布（与停更前 8-03 的 5,193×10 规模同量级）：

| feature | 10-19 mean | std | min | max |
|---|---|---|---|---|
| morning_return | −0.00390 | 0.0240 | −0.220 | 0.217 |
| close_to_vwap | 0.00556 | 0.0118 | −0.086 | 0.132 |
| intraday_return | 0.00382 | 0.0269 | −0.224 | 0.236 |

覆盖率与 `market_daily_bar` 当日 5,186 只完全一致 → 分钟线源完整。

证据：`outputs/research/m0_7_intraday_validation_20261020/stock_intraday_features_{20261016,20261019}.csv`

## PostgreSQL staging 回填测试（本轮新增，已执行）

为支持安全的回填验证，给 upsert 增加了 `target_table` 参数（默认仍为正式表，
行为不变；`tests/test_intraday_features.py` 新增针对性测试，4 passed）。
在生产库 `staging` schema 建镜像表并实跑 2 个缺口日：

| 交易日 | stock_rows | 覆盖资产 | industry_rows | 重跑幂等 | 
|---|---|---|---|---|
| 2026-08-04 | 51,920 | 5,192 | 415 | pass2 相同行数，ON CONFLICT 更新 ✓ |
| 2026-08-05 | 51,940 | 5,194 | 415 | ✓ |

- 耗时：4 个 day-build 共 64.8s（≈16s/日）→ 全缺口 ~55 交易日估算 <30 分钟。
- 三大消费特征零 NULL，分布与停更前同量级。
- 证据表：`staging.stock_intraday_features_daily` / `staging.industry_intraday_features_daily`（staging schema 内的测试表，可整表 DROP 回滚）。

**小批量生产恢复申请（待批准）**：先回填 8-04→8-31（约 20 个交易日，~104 万行
upsert），观察一周无异常再续 9 月以后批次；接入 platform_ready 链 `technical_features`
之后、`lhb_shortline` 之前。

## 恢复方案（设计，待批准）

1. **调度接入**：platform_ready 链 `technical_features` 之后、`lhb_shortline` 之前
   插入 `build-intraday-features-daily`（依赖 minute5 完成）。
2. **历史回填**：`backfill-intraday-features-daily` 对 8-04→今日按交易日分批；
   upsert `ON CONFLICT (trade_date,asset_id,feature_name,adjust_type)` 幂等已具备。
3. **批量写规模**：单日 ~51,860 stock rows + 行业行；upsert 压力低。
4. **质检**：三个消费特征各自覆盖率检查（不可用整表 MAX），叠加
   missing_trading_days 中间断档检查。
5. **PIT 口径**：历史研究按 trade_date 消费，回填为历史补数不回改——安全。

## 未执行/待批准

- 生产库批量回填（8-04 起 ~50+ 交易日）。
- platform_ready 调度接入（生产配置变更）。
- 失败重试/窗口边界（分钟线缺失日的处理策略）。
