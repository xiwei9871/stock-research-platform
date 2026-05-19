# P0 Universe Layer

## 1. 为什么 Universe Layer 是第一个 P0 任务

当前 `stock_research` 仓库已经有因子、回测、行业研究、日报等能力，但股票池口径并不统一：

- `src/stock_research/services/index_universe_service.py` 只处理指数成分股的 point-in-time membership
- `src/stock_research/backtest.py`、`retention_backtest.py`、`selection.py` 各自内嵌了 ST、停牌、流动性等过滤
- `factor_pipeline.py`、`features.py`、`labels.py` 并不承担统一 universe 过滤职责

这会导致后续因子、回测、日报、watchlist 看到的样本集不一致。  
因此 Universe Layer 必须先落地，作为后续 P0 开发的共同口径层。

## 2. 当前实现的文件

本轮新增或修改：

- `src/stock_research/services/universe_service.py`
- `src/stock_research/cli.py`
- `tests/test_universe.py`

本轮复用的现有基础：

- `src/stock_research/services/index_universe_service.py`
- `src/stock_research/services/asset_status_service.py`
- `src/stock_research/schema.py`

## 3. UniverseConfig 字段说明

`UniverseConfig` 当前包含这些核心字段：

- `as_of_date`
- `include_boards`
- `exclude_boards`
- `exclude_st`
- `exclude_suspended`
- `min_listed_days`
- `include_recent_ipo`
- `min_avg_turnover_amount`
- `min_avg_volume`
- `liquidity_lookback_days`
- `exclude_long_suspended`
- `max_suspended_days`
- `include_watchlist`
- `watchlist_only`
- `allow_missing_industry`
- `allow_missing_valuation`
- `preset`
- `watchlist_codes`

设计原则：

- 保留 point-in-time 日期
- 允许 preset 驱动默认口径
- 允许少量阈值覆盖
- 暂不引入大依赖或复杂配置系统

## 4. Preset 说明

### `research_default`

普通研究和回测默认股票池：

- 纳入主板、创业板
- 排除科创板、北交所
- 排除 ST / *ST
- 排除当日停牌
- 默认要求上市满 120 天
- 默认看 20 日流动性
- 默认启用成交额阈值过滤
- 默认启用长期停牌过滤

### `include_recent_ipo`

用于次新股研究：

- 仍排除科创板、北交所、ST、当日停牌
- 放宽上市天数阈值
- 对上市天数低于普通研究阈值但仍被纳入的股票，显式标记 `recent_ipo_allowed`

### `watchlist_check`

用于人工自选池检查：

- 只评估 watchlist 中股票
- 不因为是 watchlist 就自动纳入
- 即使股票被排除，也仍返回结果
- 风险原因会完整保留，例如：
  - `st`
  - `suspended`
  - `listed_days_below_min:*`
  - `low_turnover_amount`
  - `excluded_board:*`

## 5. CLI 用法

当前采用与现有 CLI 风格一致的平铺命令，而不是嵌套子命令。

### 生成 universe 摘要

```bash
stock-research build-universe \
  --date 2026-05-18 \
  --preset research_default \
  --output outputs/universe/2026-05-18/
```

### 解释单只股票

```bash
stock-research explain-universe \
  --date 2026-05-18 \
  --code 000001.SZ \
  --preset research_default
```

### 检查 watchlist

```bash
stock-research check-watchlist-universe \
  --date 2026-05-18 \
  --watchlist path/to/watchlist.csv \
  --preset watchlist_check \
  --output outputs/universe/watchlist/
```

## 6. 输出文件说明

`build-universe` 和 `check-watchlist-universe` 会输出：

- `universe_members.csv`
- `universe_included.csv`
- `universe_excluded.csv`
- `universe_summary.json`
- `universe_warnings.md`

其中：

- `universe_members.csv` 保留每只股票的纳入/排除与 reason
- `universe_included.csv` 用于后续筛选和回测直接消费
- `universe_excluded.csv` 用于审计和排查过滤规则
- `universe_summary.json` 用于程序化读取
- `universe_warnings.md` 用于记录缺失行业、watchlist 缺码等警告

## 7. 和后续 Factor Registry、Backtest、Watchlist 的关系

### 与 Factor Registry 的关系

- Universe Layer 先决定“哪些股票进入研究样本”
- Factor Registry 再决定“对这些股票计算哪些因子、如何注册与验证”

### 与 Backtest 的关系

- `vectorized_topn_backtest.py` 已开始复用 Universe Layer
- `retention_backtest.py` 已开始复用 Universe Layer
- `portfolio_backtest.py` 已开始复用 Universe Layer
- 后续更高层 workflow 仍应继续复用同一输出，而不是各自散写 ST/停牌/流动性过滤

### 与 Watchlist 的关系

- 当前仅支持从 CSV 载入 watchlist 做独立检查
- 后续 watchlist workflow 可以直接复用同一规则解释层

## 8. 当前未做事项

本轮明确未做：

- 未接入真实远端 PostgreSQL 审计
- 未新增 watchlist schema
- 未把 Universe Layer 接入更高层 watchlist workflow / Agent 工作流
- 未做 Factor Registry
- 未做 run_card
- 未做回测质量增强
- 未做 AI Agent 报告层

## 9. 当前结论

Universe Layer 已经以低侵入方式落地：

- 采用 `services/` 目录风格，和现有仓库一致
- 先完成纯 DataFrame 级别规则计算
- 数据库查询保持薄封装
- 提供 preset、explain、artifact 输出和 CLI

## 10. Universe Layer 已接入的下游模块

1. `vectorized_topn_backtest.py`：已接入。
2. `retention_backtest.py`：已接入。
3. `selection.py / TopN 工作流`：已接入。
4. `portfolio_backtest.py`：已接入。
5. `watchlist workflow`：未接入。

这使得下一轮可以直接做两件事之一：

1. 进入 Factor Registry
2. 先把 Universe Layer 接入一个现有回测模块
