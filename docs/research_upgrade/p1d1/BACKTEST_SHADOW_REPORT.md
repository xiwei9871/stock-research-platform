# P1d.1 BACKTEST_SHADOW_REPORT — Baseline vs Shadow 隔离对照

脚本：`scripts/p1d1_shadow_backtest.py`（可复现，无生产代码改动）。
明细：`BACKTEST_SHADOW_COMPARISON.csv`（63 差异键）+ `BACKTEST_SHADOW_SUMMARY.json`。

## 实验设计（隔离契约）

- 输入：`factor.stock_score_daily@manual_v1` + `public.market_daily_bar@hfq`，
  窗口 **2024-01-02 ~ 2026-10-23**（score 实际覆盖域），`VectorizedTopNConfig`
  top_n=20 / daily / cost=0bps——两腿**同一份 scores、同一份 price 行、同一 config**。
- 唯一变量：`is_limit_up`/`is_limit_down` 列。
  - **Baseline**：存量 `core.asset_status_daily` flag（生产语义等价装载：
    生产 `market_daily_bar` 已无 flag 列，baseline 用 status 表 join 复原）；
  - **Shadow**：P1d.1 规则引擎重算 flag——raw close vs 法定限价（tick 取整）、
    真实上市交易日序号、620 过渡、IPO 窗口；`rule_unknown`/缺原始行情 →
    **fail-closed 双 flag 置 True**（保守阻断）。
- 时点语义：两腿共用同一"执行日 bar 判定"假设，无新增前视；存量与重算
  flag 均为同日收盘判定，差异仅来自**规则正确性**。

## flag 层重算量

| 项 | 值 |
|---|---|
| 重算行数 | 3,470,036 |
| 重算 limit_up=True | 53,353 |
| 重算 limit_down=True | 20,482 |
| rule_unknown fail-closed 行 | 4,552（全部未命中实际策略交易 → 0 笔受其阻断） |

## 结果对比

| 指标 | Baseline（存量 flag） | Shadow（修正 flag） | Δ |
|---|---|---|---|
| trade rows | 9,549 | 9,536 | −13 |
| buy / sell | 4,859 / 4,690 | 4,852 / 4,684 | −7 / −6 |
| skip: limit_up | 380 | 370 | **−10**（存量多阻 10 次） |
| skip: limit_down | 236 | 224 | **−12**（存量多阻 12 次） |
| skip: suspended | 125 | 125 | 0 |
| executed weight | 233.55 | 233.35 | −0.20 |
| avg turnover | 0.6325 | 0.6337 | +0.0012 |
| final equity | 0.3742 | 0.3670 | **−0.72pp** |
| max drawdown | −71.05% | −71.73% | −0.69pp |
| periods | 676 | 676 | = |

## 差异归因（63 键全部可追溯）

| 类型 | 数量 | 解释 |
|---|---|---|
| CHANGED | 32 | 同一键成交权重/skip 变化：主要是存量 **FP flag 移除**后订单不再被误阻（如 600268/600392/600415 卖单、600549 买单），及连带现金/权重级联（600016 买单权重变化） |
| ONLY_BASELINE | 21 | baseline 中"被误阻后的隔日重试/补单"——shadow 首日已成交，无此重试行 |
| ONLY_SHADOW | 10 | shadow 中新增成交（误阻解除后在 shadow 时间线首次出现） |
| 规则归因 | — | main_10pct 42 / main_st_5pct 8 / chinext_st_20pct 4 / star_st_20pct 3 / star_20pct 3 / chinext_20pct 3；**rule_unknown 归因 0** |
| 年份 | — | 2024:8 / 2025:32 / 2026:23 |

**方向判定**：存量 flag 在该窗口**净过度阻断**（多阻 22 次 vs 漏标放行），
即现代窗口内 FP 危害 > FN 危害；shadow 放行被误阻的真实可成交单。
净值差 −0.72pp 为**温和但非零**的真实影响；回撤略深来自被误阻卖单
解除后暴露的真实下行持仓。

## 结论与标注

- **无无法解释的资格放行**：全部差异可映射到规则行；
- **无新增前视**：两腿时点语义一致；
- **NEEDS_REVALIDATION**：凡用 vectorized_topn/retention 执行门跑过
  2024-01 后窗口且假定"存量 flag 正确"的历史回测；覆盖 2020-08-24 前
  创业板窗口的历史回测**全部**需要重验（该制度段 46,160 行实锤误标）；
- 本实验未写任何生产策略记录，未改生产执行路径；
- `rule_unknown` 4,552 行未阻断任何实际交易——fail-closed 成本在该窗口为零，
  但语义保留（防御性正确）。

## 局限声明

- Shadow flag 仍是"收盘判定"语义：日内盘中触板/一字板的成交可行性区分
  在 P0-D 模型中表达，本回测引擎不消费该粒度——两腿同源，不影响对照有效性；
- 收益方向不做预设：本窗口 shadow 收益略低源于真实放行了存量误阻的卖出，
  属机制修正而非策略优劣评价；
- `market_daily_bar` 缺 flag 列属 Gate-2 基础设施发现（消费方硬失败/静默
  False），迁移方案见 STORAGE_MIGRATION_PLAN。
