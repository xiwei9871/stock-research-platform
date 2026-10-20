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
