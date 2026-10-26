# P1d.1 BACKTEST_CONSUMER_INVENTORY — 涨跌停/可交易性字段真实消费路径图

审计日期：P1d.1 分支 HEAD。三类消费语义分开：**(a) 存量 flag 直读**；
**(b) can_open_long/can_close_long 执行门**；**(c) 自建阈值/pct_chg 判断**。

## (a) `is_limit_up` / `is_limit_down` / `is_suspended` 直读

| 路径 | 取数方式 | 影响面 | 状态 |
|---|---|---|---|
| `vectorized_topn_backtest.py:96` | `SELECT ... is_limit_up, is_limit_down, is_suspended FROM market_daily_bar` | top-N 回测执行门 | **硬失败**：`market_daily_bar` 无此三列 → `UndefinedColumn`。该消费方在当前 DB 上无法运行，等同失效 |
| `vectorized_topn_backtest.py:378` `_normalize_price_frame` | 缺失 flag → `fillna(False)` | 同上 | 若列存在但行缺失会静默放行（fail-open 缺口） |
| `market_emotion_state_v1.py:81,181-280` | `FROM core.asset_status_daily` | 连板数/首板/涨停家数/昨涨停今表现等情绪特征 → 反哺 regime/exposure 输入 | 存量误标直接污染情绪序列（涨停计数、连板高度、晋级率） |
| `services/asset_status_service.py:40` | 状态行 dict | `allow_limit_up or not is_limit_up` 运行时门 | 读存量 flag |
| `dashboard/market_monitor.py:227-263` | `s.is_limit_down` 等 | 盘面监控展示 | 展示层，存量误标会错列/漏列 |
| `dashboard/market_anomaly_context.py:103-172` | `COALESCE(status.is_limit_down,false)` | 异动上下文 | 展示层同上 |
| `retention_backtest.py:1871-1872` | `_bars_by_date_asset` 从 bar frame `.get()` | 见 (b) | bar frame 无此列 → 静默 `False` |
| `dashboard/backtests.py:794`、`mid_trend_shadow_backtest.py:223`、`intraday_risk_control_v2.py:368`、`intraday_risk_filter_backtest.py:235`、`serenity_tight3b_c2_experiment.py:952` | `false AS is_limit_*` 字面量 | 各自回测 | **恒定 False**：等价于"永远无涨跌停"假设，语义缺口但与存量误标无关 |

## (b) `can_open_long` / `can_close_long` 执行门（`backtest_constraints.py`）

判定顺序：suspended/trade_status≠"1" → limit_up(buy)/limit_down(sell) → min_amount。

| 调用方 | bar 来源 | flag 可见性 | 结论 |
|---|---|---|---|
| `retention_backtest.py:1347` (buy) / `1427` (sell, pending retry) | `load_backtest_bars`/`load_backtest_inputs` → `market_daily_bar`（无 flag 列，`.get()`→None） | **门是哑的**：`_flag_is_true(None)=False`，涨跌停从不阻断，只有 trade_status/is_st 生效 | **沉默缺口**：本应阻断的成交被放行 |
| `vectorized_topn_backtest.py:604` (buy) / `549,681` (sell+pending retry) | `load_vectorized_topn_inputs`（见 (a)） | SQL 层即崩 | 同 (a) 硬失败 |

**统一发现：两条真实回测执行路径当前都没有"有效的存量 flag 消费"**——
一条 SQL 崩、一条静默 False。P1d.1 shadow 实验（`scripts/p1d1_shadow_backtest.py`）
用语义等价的 `status join` 装载存量 flag 重建 baseline，是首个让该门
真正吃到存量 flag 的对照环境。

## (c) 自建阈值 / pct_chg 判断（不经存量 flag，同类缺陷族）

| 路径 | 逻辑 | 缺陷 |
|---|---|---|
| `dragon_case_library.py:1450 _is_limit_up` | `daily_return >= (is_st ? 4.8% : 9.5%)` | 板块盲：创业板/科创 20% 日的真实涨停判不出，ST 恒 4.8% 覆盖 20% 制度股 |
| `lhb_eligibility.py::_regime_and_threshold` | （旧）ST→-4.8 / 创业→-19 / 科创→-19 / 北→-29 / 主→-9.5，`del trade_date` | **已修复**：P1d.1 改为路由 `tradeability.resolve_limit_rule`，trade_date+listing_age 真实参与，`rule_unknown`→`risk_watch` |
| `market_emotion_state_v1`（limit streak 段） | 存量 flag 连板计数 | 属 (a) |
| `backtest.py`（load_backtest_inputs/bars） | 仅 `trade_status`/`is_st` | 无 flag 消费 |

## (d) 写入侧根因

`core_data.py:519-540`：`is_limit_up = pct_chg >= {静态阈值}` +
`limit_up_price = preclose*(1+thr)`——无制度/日期/上市序号/无涨跌幅窗口感知。
修复方案见 `STORAGE_MIGRATION_PLAN.md`。

## 消费路径结论

- 需要 NEEDS_REVALIDATION 标记的旧回测：**所有使用 vectorized_topn/retention
  执行门且覆盖 2024-01 后窗口的历史结果**（门从未吃到正确 flag）+
  `market_emotion_state_v1` 派生的情绪序列下游（regime 确认、exposure 门控、
  tech_bottleneck 等读取 `market_emotion_state` 的策略输入）+
  `dragon_case_library`/`lhb` 历史资格判定输出；
- 展示层（dashboard monitor/anomaly）无需回测重验，但存量误标修正前
  展示结果不保证正确；
- `false AS` 常量消费方在迁移后应改接正确 flag 而非维持恒 False。
