# A 股多因子选股研究平台建设框架 v1

## 系统定位

本系统不是自动交易系统，也不是券商下单系统，而是 A 股多因子选股、趋势动量跟踪、板块确认、市场状态过滤、回测验证和每日盯盘建议系统。

核心目标：

- 每天对 A 股 5000+ 股票统一打分。
- 生成 Top10、Top20、Top30、Top100 股票池。
- 用市场情绪、板块趋势和个股过热状态做二次过滤。
- 输出 Buy Watch、Observe、Hold、Reduce、Exit 等人工决策建议。
- 通过回测和因子评价验证策略是否有效。
- 不接自动交易，最终买卖仍由人决策。

一句话定位：用成熟因子和开源框架思想做轮胎，用自建数据库和自研策略逻辑做车身。

## 技术路线

```text
数据源：AKShare + Baostock
数据库：PostgreSQL
基础数据层：日线行情 + 基本面 + 股本 + 行业 + 指数 + 公司行为
因子来源：自研基础因子 + Alpha101 + GTJA191 + Qlib Alpha158/360 思想
因子评价：IC、RankIC、分组收益、换手率、行业/市值暴露
回测框架：自研组合模拟，借鉴 vectorbt 向量化思想和 RQAlpha 生命周期设计
策略核心：V3 趋势动量多因子框架
输出结果：每日 TopN 股票池、持仓建议、回测报告、因子评价报告
```

## 分层架构

```text
AStock Research Platform
├── 1. 数据采集层 Data Loader
├── 2. 研究数据库层 Research DB
├── 3. 因子计算层 Factor Engine
├── 4. 因子评价层 Factor Evaluation
├── 5. 多因子打分层 Scoring Engine
├── 6. 回测与策略层 Backtest / Strategy
└── 7. 报告与盯盘层 Report / Dashboard
```

## 数据库原则

PostgreSQL 按 schema 分层：

```text
raw_akshare      AKShare 原始数据
raw_baostock     Baostock 原始数据
core             股票基础信息、行业、交易日、状态
finance          财报、财务指标、股本、公司行为
market           行情、指数、行业行情、市场宽度
factor           因子结果、每日打分
backtest         回测结果、持仓、交易日志
```

关键原则：

- 原始数据和标准化数据分开。
- 稳定字段和动态字段分开。
- 财报必须有 `report_period` 和 `announcement_date`。
- 行业、ST、股本、指数成分等变化类数据必须支持历史版本。
- 因子计算和回测必须使用 `announcement_date <= trade_date`，避免未来函数。

## 阶段规划

### 阶段 1：研究数据库骨架

目标：把日线行情库升级为研究库。

交付物：

- PostgreSQL 表结构。
- raw 层快照机制。
- 股票代码映射。
- upsert 工具。
- `core.asset_master`
- `core.asset_status_daily`
- `core.industry_membership`
- `market.index_daily_bar`
- `market.industry_daily_bar`
- point-in-time 财报查询服务。

### 阶段 2：财报与基本面

目标：支持价值、成长、质量因子。

交付物：

- `finance.income_statement`
- `finance.balance_sheet`
- `finance.cash_flow`
- `finance.indicator_quarter`
- `finance.share_capital_event`
- `finance.corporate_action`
- `valuation_service`

### 阶段 3：基础因子库

目标：实现第一批 40-60 个核心因子。

模块：

- `factors.trend`
- `factors.momentum`
- `factors.volume_price`
- `factors.sector`
- `factors.risk`
- `factors.value`
- `factors.growth`
- `factors.quality`
- `factors.alpha101`
- `factors.gtja191`
- `factors.qlib_alpha`

第一批先落地可复用基础函数，不全量复刻 Alpha101 / GTJA191。

当前进展：

- 已落地 `factors.trend`、`factors.momentum`、`factors.volume_price`、`factors.sector`、`factors.risk` 的基础 pandas 实现。
- 已为 `factors.value`、`factors.growth`、`factors.quality`、`factors.alpha101`、`factors.gtja191`、`factors.qlib_alpha` 预留清晰边界。
- Alpha101、GTJA191、Qlib 当前只作为参考来源，不作为项目主框架或强依赖。
- 已落地第一批外部参考因子：Alpha101-style、GTJA191-style、Qlib-style 代表性 pandas 实现。
- 外部参考因子已进入 `factor.factor_daily`，但进入 `factor.stock_score_daily` 前仍需通过 `factor_eval` 评价门禁。

### 阶段 4：因子评价系统

目标：判断因子是否真的有效。

交付物：

- IC
- RankIC
- ICIR
- 分组收益
- Top-Bottom 收益
- 换手率
- 分年份表现
- 分市场状态表现
- 行业暴露和市值暴露

当前进展：

- 已落地 `factor_eval.ic`，支持按交易日横截面计算 IC 和 RankIC。
- 已落地 `factor_eval.quantile_return`，支持按交易日分位数组收益和 Top-Bottom 收益差。
- 已落地 `factor_eval.turnover`，支持 TopN 成分换手率。
- 已落地 `factor_eval.report`，提供轻量因子评价汇总入口。
- 已落地因子评价门禁：支持多周期评价、分年份诊断、分组表现、行业/市值暴露诊断，以及 `factor.factor_approval` 审批状态记录。

### 阶段 5：多因子打分与 TopN 股票池

目标：每天给全市场股票打分。

交付物：

- `factor.factor_daily`
- `factor.stock_score_daily`
- Top10 / Top20 / Top30 / Top100
- 行业内排名
- 市场状态
- 板块状态
- 个股过热状态

当前进展：

- 已落地 `scoring.winsorize`，支持按交易日横截面去极值。
- 已落地 `scoring.standardize`，支持按交易日 z-score 标准化。
- 已落地 `scoring.rank_score`，支持按交易日把因子转成 0-100 排名分，并支持高值更好 / 低值更好两种方向。
- 已落地 `scoring.composite_score`，支持人工权重合成总分、排序和版本标记。
- 已落地 `scoring.pipeline`，支持从长表因子数据生成综合股票得分。
- 已落地 `factor.factor_daily`、`factor.stock_score_daily` 表结构和索引。
- 已落地 `factor_store`，支持因子长表 upsert、综合得分 upsert、TopN 读取，以及从长表因子计算并写入综合得分。
- 下一步需要补 CLI 命令和每日流水线，把基础因子计算、因子存储、综合打分串起来。

### 阶段 6：V3 策略回测

目标：验证 V3 是否有效。

交付物：

- `strategies.v3_trend_momentum`
- TopN 轮动回测
- 持仓模拟
- 退出规则
- 绩效指标
- 回测报告

当前进展：

- 已落地第一版 vectorbt 风格 TopN 回测核心：支持 `factor.stock_score_daily` 输入加载、daily / weekly rebalance、等权持仓、最大持仓数量、交易成本、换手率、资金曲线、调仓交易明细和基础 summary。
- 已落地第一版 RQAlpha 风格策略生命周期层：提供 `prepare_data`、`before_market`、`generate_signals`、`rebalance`、`after_market`、`generate_report`，用于研究流程编排，不接自动交易、不改 V3 阈值。
- 已落地 TopN research workflow：可把策略生命周期、向量化回测和绩效 tear sheet 串成一个可复用研究流程，暂不接 CLI。

### 阶段 7：每日选股与盯盘报告

目标：形成日常可用工具。

交付物：

- 每日 TopN 报告
- 市场状态报告
- 板块强度报告
- 持仓建议报告
- 风险提示报告

当前进展：

- 已落地每日 TopN 报告：输出排名、股票、总分、评分版本和 score components，并明确 TopN 只是候选股票池，不是买入信号。
- 已落地板块强度报告助手：从 `market.industry_daily_bar` 加载行业日线，计算 5 日收益、20 日收益、成交额 5/20 强度和综合排名，并输出 markdown / CSV。该报告只作为研究观察，不构成交易指令。
- 已落地市场状态报告助手：从 `market.index_daily_bar` 加载指数日线，计算 5/20/60 日收益、MA20、MA60、20 日回撤、成交额 5/20 强度，并输出 `bullish`、`neutral`、`defensive` 状态和风险等级。该状态只作为过滤器，不构成交易指令。
- 已落地风险提示报告助手：组合市场状态、板块强度、TopN 候选和 P0 特征，输出市场防御、弱板块、短期过热、高波动、深回撤、低流动性等结构化风险提示。风险提示只作为研究过滤器，不构成交易指令。
- 已落地持仓复核报告助手：把当前持仓与 TopN 排名、市场状态、风险提示交叉，输出 `review`、`monitor`、`blocked` 等人工复核状态和原因，不输出买卖指令。
- 已落地日报聚合入口：把 TopN、市场状态、板块强度、风险提示和回测报告路径汇总成一个日度研究索引，作为人工复核入口。
- 已落地日报编排层：从内存中的研究结果一次性写出 TopN、市场状态、板块强度、风险提示、持仓复核和日报索引，后续可接 CLI 或定时任务。
- 已落地独立日报模块 CLI：通过 `python -m stock_research.reports.daily_research_report_cli` 生成阶段 7 日报。
- 已落地主 `stock-research run-daily-research-report` 入口，输出与模块 CLI 相同的稳定报告路径。
- 已补齐日报 CLI 的候选行业上下文：TopN 候选会按 `core.industry_membership` 的 point-in-time 记录补充行业代码和名称，用于弱板块风险判断。
- 已落地报告运行记录：提供独立 `report.report_run` schema 初始化和写入函数，日报 CLI 可通过 `--apply-report-run-schema --record-run` 持久化生成的报告路径。
- 已补强持仓复核的组合级风险摘要：报告中显示总权重、最大行业权重，以及是否超过配置阈值。
- 已落地日报 cron 命令生成器：生成可人工安装的工作日日报 cron 行，不自动修改系统定时任务。

剩余缺口：

- 日报定时任务已具备 cron 行生成器，但尚未自动安装到系统 cron / OpenClaw cron。
- 持仓复核仍不输出买卖指令或仓位建议，只提供人工复核状态和风险摘要。
- 因子评价门禁已实现，但外部参考因子的批量评价和审批运行还需要实际数据执行。

## 当前执行顺序

```text
1. 研究数据库基础设施
2. 因子库基础设施
3. 因子评价和打分
4. V3 策略和回测
5. 每日选股与盯盘报告
```

## 外部轮子参考清单与使用边界

本项目是自建 A 股多因子选股研究平台，不直接依赖第三方在线量化平台，也不把大型开源量化框架整体作为主系统。开发时遵守“借鉴思想、拆解模块、适配本项目”的原则。

一句话定位：

```text
Qlib 学因子组织范式。
Alpha101 和 GTJA191 提供价量因子来源。
Alphalens 提供因子评价标准。
vectorbt 提供向量化回测思想。
RQAlpha 提供策略生命周期参考。
empyrical / pyfolio 提供绩效分析参考。
```

### 因子库参考

Qlib：

- GitHub: https://github.com/microsoft/qlib
- 重点参考 Alpha158、Alpha360、benchmark 组织方式、A 股 / CSI300 示例、因子数据组织方式、训练 / 验证 / 测试切分方式、报告评价指标设计。
- 使用边界：不要把 Qlib 作为本项目主框架；不要强依赖 Qlib 数据格式；不要一开始引入深度学习模型；可以把 Alpha158 / Alpha360 的因子思想拆解为 pandas/numpy 函数；在 `factors/qlib_alpha.py` 中预留接口，先实现少量代表性因子。

WorldQuant 101 Formulaic Alphas：

- 参考仓库: https://github.com/yli188/WorldQuant_alpha101_code
- 参考仓库: https://github.com/wpwpwpwpwpwpwpwpwp/Alpha-101-GTJA-191
- 重点参考 101 Formulaic Alphas 的价量因子公式、横截面 rank、rolling correlation、rolling covariance、time-series rank、decay linear、delta、delay、signed power。
- 使用边界：不要一次性实现全部 101 个因子；第一版只实现 5-10 个容易验证、适合 A 股日线数据的因子；每个因子必须写清楚输入字段、输出含义、是否可能产生未来函数；所有 rolling 计算只能使用当前日及以前数据；放在 `factors/alpha101.py`；因子进入正式打分前必须经过 `factor_eval` 评价。

GTJA 191 Alpha：

- DolphinDB 官方实现说明: https://github.com/dolphindb/DolphinDBModules/blob/master/gtja191Alpha/README_CN.md
- Python 参考仓库: https://github.com/wpwpwpwpwpwpwpwpwp/Alpha-101-GTJA-191
- 重点参考国泰君安 191 Alpha 短周期价量因子、A 股语境下的量价因子设计、因子入参规范、因子命名规范、短周期价量特征构造方式。
- 使用边界：不要一次性实现全部 191 个因子；第一版只实现 5-10 个短周期价量类因子；优先选择和趋势、动量、量价确认、风险过滤相关的因子；放在 `factors/gtja191.py`；每个因子必须有 docstring 和单元测试；因子进入正式打分前必须经过 IC、RankIC、分组收益评价。

### 因子评价参考

Alphalens：

- 原始项目: https://github.com/quantopian/alphalens
- 维护版本: https://github.com/stefan-jansen/alphalens-reloaded
- 维护版本: https://github.com/cloudQuant/alphalens
- 重点参考 Returns Analysis、Information Coefficient Analysis、Turnover Analysis、Grouped Analysis、Quantile Return、Factor Tear Sheet。
- 使用边界：不强制把 Alphalens 作为项目依赖；优先复刻核心思想；在 `factor_eval/` 中实现 `calc_ic`、`calc_rank_ic`、`calc_quantile_return`、`calc_top_bottom_spread`、`calc_factor_turnover`、`generate_factor_eval_report`；因子评价必须支持 `forward_return_5d`、`forward_return_10d`、`forward_return_20d`、`forward_return_60d`；所有 forward return 必须通过未来收益 `shift(-n)` 生成，不能污染因子计算。

### 回测框架参考

vectorbt：

- GitHub: https://github.com/polakowo/vectorbt
- 重点参考向量化回测思想、signals matrix、entries / exits 信号矩阵、`Portfolio.from_signals` 设计思想、多股票 / 多参数批量回测、快速绩效统计。
- 使用边界：不要求直接依赖 vectorbt；本项目自己实现 `backtest/vectorized_engine.py`；重点学习输入输出结构和向量化思想；必须支持 TopN 股票池轮动回测、daily / weekly rebalance、交易成本、换手率、等权持仓、最大持仓数量。

RQAlpha：

- GitHub: https://github.com/ricequant/rqalpha
- 重点参考策略生命周期、`before_trading`、`handle_bar`、`after_trading`、多证券回测结构、可扩展 Mod 设计思想。
- 使用边界：不要整体引入 RQAlpha；不做自动交易接口；不接券商；可以参考其策略生命周期，把本项目策略组织为 `prepare_data`、`before_market`、`generate_signals`、`rebalance`、`after_market`、`generate_report`。

backtesting.py / backtrader：

- 可作为轻量参考，但不是第一优先级。
- 使用边界：本项目核心是全市场 TopN 多因子轮动，不是单股票技术指标回测；不要把单股票回测框架作为主系统。

### 绩效分析参考

empyrical：

- GitHub: https://github.com/quantopian/empyrical
- 维护版本: https://github.com/stefan-jansen/empyrical-reloaded
- 重点参考 annual_return、annual_volatility、max_drawdown、sharpe_ratio、sortino_ratio、calmar_ratio、alpha_beta、stability_of_timeseries。
- 使用边界：可直接依赖，也可自行实现常用指标；本项目至少要实现累计收益、年化收益、最大回撤、波动率、夏普比率、Calmar、胜率、平均持仓天数、年化换手率。

pyfolio / pyfolio-reloaded：

- GitHub: https://github.com/quantopian/pyfolio
- GitHub: https://github.com/stefan-jansen/pyfolio-reloaded
- 重点参考组合风险分析、tear sheet 报告、回撤分析、收益分布分析。
- 使用边界：不强制直接依赖；可以学习报告组织方式；本项目自己生成 `backtest_report.xlsx`、`backtest_report.md`、净值曲线、回撤曲线。

当前进展：

- 已落地第一版绩效指标和 tear sheet：支持累计收益、年化收益、年化波动率、最大回撤、Sharpe、Sortino、Calmar、胜率、平均持仓天数、年化换手率，并可输出 markdown、metrics CSV、equity CSV、positions CSV。

### 技术指标库参考

TA-Lib：

- GitHub: https://github.com/ta-lib/ta-lib-python

pandas-ta / pandas-ta-classic：

- 可参考其技术指标实现方式。

使用边界：

- 基础指标尽量自己实现，例如 MA、RET、ATR、OBV、波动率、最大回撤。
- 复杂指标可以参考实现。
- 不要让技术指标库成为核心强依赖。

### 开发要求

1. 引用外部项目时，先阅读 README、License、核心实现文件。
2. 不要直接复制大段代码进入项目，除非确认许可证允许。
3. 即使参考外部代码，也必须改写为适配本项目数据结构的 pandas/numpy 函数。
4. 所有外部参考因子必须写明 `source`：`qlib`、`alpha101`、`gtja191`、`custom`。
5. 每个因子必须进入 `factor.factor_daily`，并记录 `factor_name`、`factor_group`、`factor_value`、`calc_version`、`source_data_version`。
6. 所有因子必须通过 `factor_eval` 评价后，才允许进入 `factor.stock_score_daily`。
7. 当前阶段优先完成趋势因子、动量因子、板块相对强度因子、量价确认因子、风险/过热过滤因子、少量 Alpha101、少量 GTJA191、Alphalens 风格因子评价、vectorbt 风格 TopN 回测。

### 不做事项

1. 不要把 Qlib 整体作为项目主框架。
2. 不要把 RQAlpha 整体作为项目主框架。
3. 不要接自动交易。
4. 不要接券商接口。
5. 不要直接上复杂机器学习模型。
6. 不要一次性实现 Alpha101 全部因子。
7. 不要一次性实现 GTJA191 全部因子。
8. 不要跳过因子评价直接进入实盘建议。
9. 不要使用未来数据。
10. 不要使用公告日之后才可见的财报数据参与历史回测。

## 核心原则

1. 不造无意义的轮子，但要自建适合自己的平台。
2. 数据源可以用 AKShare / Baostock，数据库必须自己掌控。
3. GitHub 和论文提供因子、框架和验证方法，不直接绑定平台。
4. 财报必须按公告日期控制可用时间。
5. 因子必须先评价，再进入策略。
6. TopN 不是买入信号，只是候选资格。
7. 市场状态和板块状态是 V3 的核心过滤器。
8. 过热过滤是防止追高的关键。
9. 回测重点不是收益最高，而是验证策略逻辑是否稳健。
10. 第一阶段不做自动交易，不做新闻舆情，不做复杂机器学习。
