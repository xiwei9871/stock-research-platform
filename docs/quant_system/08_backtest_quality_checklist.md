# 回测质量检查清单

本文定义当前系统以后对每一个因子、策略、TopN 组合、watchlist 信号都必须执行的质量检查。没有通过本清单的结果，不允许进入策略池、模拟组合或 Agent 强结论层。

## 1. 未来函数检查

### 必查项

- 财务数据是否按披露日可用
- 行业分类是否使用当时版本
- ST 状态是否时点还原
- 指数成分股是否时点还原
- 信号生成日与交易执行日是否错开
- 是否错误使用未来收益构造特征

### 当前仓库关注点

- 财务 PIT 方向：
  `src/stock_research/schema.py`
  `src/stock_research/services/point_in_time_finance.py`
- 标签与未来收益：
  `src/stock_research/labels.py`
- 行业归属：
  `src/stock_research/services/industry_membership_service.py`
- 指数成分：
  `src/stock_research/services/index_universe_service.py`

### 检查问题

- 当前因子是否只读取 `announcement_date <= trade_date` 的财务行
- 当前行业归属是否按 `start_date/end_date` 回放
- 当前指数成分是否按历史窗口回放
- 当前信号是否在 T 日收盘生成、T+1 日开盘执行

### 未通过处理

- 直接标记为 `rejected`

## 2. Survivorship Bias

### 必查项

- 是否包含退市股票
- 是否只用了当前仍上市股票
- 是否错误排除了历史 ST
- 是否忽略历史停牌

### 当前仓库关注点

- 资产生命周期：
  `src/stock_research/dimensions.py`
  `src/stock_research/schema.py` 中 `core.asset_lifecycle_event`
- 资产主表：
  `core.asset_master`

### 检查问题

- 回测输入 universe 是否按历史日期构造，而不是按当前资产主表静态过滤
- 历史被 ST、停牌、退市的股票是否仍出现在历史样本中

### 未通过处理

- 若仅使用当前仍上市股票做历史回测，直接 `rejected`

## 3. 价格与复权

### 必查项

- 前复权 / 后复权 / 不复权口径是否明确
- 复权因子是否正确
- OHLC 是否合法
- 是否存在异常跳变

### 当前仓库关注点

- `market.adjustment_factor`
- `market.corporate_action`
- `market_daily_bar`
- `src/stock_research/corporate_actions.py`

### 检查问题

- 因子计算和回测是否使用一致的复权口径
- 同一策略在 `hfq/qfq/raw` 下的解释是否一致
- 是否检测异常跳空、负价、high < low 等非法 bar

### 未通过处理

- 口径不清或复权错误，至少 `candidate` 降级，严重时 `rejected`

## 4. 交易约束

### 必查项

- 涨停买不进
- 跌停卖不出
- 停牌不可交易
- 一字板不可成交
- 成交额过低不可交易
- 最小成交量过滤

### 当前仓库关注点

- `src/stock_research/backtest.py`
- `src/stock_research/vectorized_topn_backtest.py`
- `src/stock_research/retention_backtest.py`
- `src/stock_research/portfolio_backtest.py`

### 检查问题

- 是否只做了“涨停买不进”而遗漏“跌停卖不出”
- 是否把停牌日错误计为正常成交
- 是否对一字板和极低流动性做了成交限制

### 未通过处理

- 交易约束缺失时，最高只能评为 `candidate`

## 5. 成本

### 必查项

- 佣金
- 印花税
- 滑点
- 冲击成本
- 调仓成本
- 换手率影响

### 当前仓库关注点

- 当前已有基础成本：
  `src/stock_research/vectorized_topn_backtest.py`
- 未来需统一到三类回测

### 检查问题

- 是否只扣了佣金，没有印花税
- 滑点是否被忽略
- 高换手策略对成本是否敏感

### 未通过处理

- 未计入成本的高频调仓策略直接 `rejected`

## 6. 调仓逻辑

### 必查项

- 信号日
- 执行日
- 调仓频率
- 开盘 / 收盘执行
- 部分成交假设
- 持仓保留规则
- 剔除规则

### 当前仓库关注点

- `vectorized_topn_backtest.py`
- `retention_backtest.py`
- `portfolio_backtest.py`
- `strategy_lifecycle.py`

### 检查问题

- 是否在收盘信号日当天按收盘成交
- 周调仓是否正确取可执行交易日
- 持仓保留和剔除规则是否与报告口径一致

### 未通过处理

- 时点错位直接 `rejected`

## 7. 风控

### 必查项

- 单票最大仓位
- 单行业最大仓位
- 最大持仓数量
- 止损
- 止盈
- 移动止损
- MA20 破位退出
- 市场状态过滤
- 行业状态过滤

### 当前仓库关注点

- `retention_backtest.py` 已有部分止损、MA20 退出
- `industry_regime_gated_backtest.py`、`industry_exposure_risk_control.py` 已有行业层风险控制思路

### 检查问题

- 风控是否只写在说明里、没有进入回测
- 行业与市场状态过滤是否真实参与执行

### 未通过处理

- 口头风控未编码到回测中，不能评 `validated`

## 8. 评价指标

### 必查项

- 年化收益
- 超额收益
- 最大回撤
- 夏普
- Calmar
- 胜率
- 盈亏比
- 换手率
- 持仓天数
- 最大连续亏损
- 分年度收益
- 分市场状态收益

### 当前仓库关注点

- `src/stock_research/performance_metrics.py`
- `src/stock_research/performance_tearsheet.py`

### 检查问题

- 是否只看总收益率
- 是否遗漏回撤与换手
- 是否缺少分年度或分状态观察

### 未通过处理

- 缺核心指标的结果不得进入策略池

## 9. 稳健性

### 必查项

- 分年度
- 牛市 / 熊市 / 震荡市
- 大盘强 / 弱
- 行业强 / 弱
- 大票 / 小票
- 高流动性 / 低流动性
- 样本内 / 样本外
- 参数敏感性

### 当前仓库关注点

- 行业与 regime 研究基础：
  `industry_focus_v2.py`
  `industry_mainline_regime.py`
- 因子多周期/分段能力：
  `factor_eval/period.py`
  `factor_eval/segment.py`

### 检查问题

- 收益是否只集中在单一年份
- 是否只在强市场有效
- 样本外是否显著退化

### 未通过处理

- 只能在单一区间有效的策略，不得高于 `candidate`

## 10. 过拟合检查

### 必查项

- 参数是否过多
- 是否反复调参
- 是否只在一个区间有效
- 是否收益来自极少数股票
- 是否对交易成本敏感
- 是否换手过高

### 当前仓库关注点

- 因子 gate 与审批基础：
  `factor.factor_approval`
  `factor_eval/gate.py`
- 行业 gated backtest 与 retention 规则存在逐步叠加风险

### 检查问题

- 参数数量是否已经超过策略解释能力
- 回测是否依赖极少数极端样本
- 成本稍微上升后结果是否崩塌

### 未通过处理

- 明显过拟合的策略标记为 `deprecated` 或 `rejected`

## 11. 输出产物

每次回测必须输出：

- `run_card.md`
- `run_card.json`
- `metrics.json`
- `trades.csv`
- `positions.csv`
- `equity_curve.csv`
- `config_snapshot.json`
- `data_coverage.json`
- `warnings.md`

当前仓库已经有部分相近产物：

- `performance_tearsheet.py` 可输出报告与 CSV
- `report_run_store.py` 可记录报告运行

后续必须统一收敛为标准 artifacts。

## 12. 回测结论分级

每次回测必须给出以下分级之一：

- `rejected`：不可信或明显无效
- `candidate`：有潜力但证据不足
- `validated`：通过基础验证
- `production_candidate`：可进入模拟组合
- `deprecated`：曾有效但已失效

### 分级原则

- 只要未来函数、成本、涨跌停、停牌约束不完整，就不能高于 `candidate`
- 通过样本外与稳健性检查，才能进入 `validated`
- 通过基础验证且可进入模拟组合，才可评为 `production_candidate`

## 13. 禁止事项

- 不允许只看收益率
- 不允许忽略最大回撤
- 不允许忽略交易成本
- 不允许忽略涨跌停和停牌
- 不允许信号日当天收盘信号当天成交
- 不允许没有 run_card 的回测进入策略池
- 不允许没有样本外测试的策略进入模拟组合

## 14. 建议执行方式

后续每次回测前后，应至少执行以下流程：

1. 检查数据覆盖与 PIT 约束。
2. 记录策略配置与数据口径。
3. 运行回测。
4. 输出标准 artifacts。
5. 用本清单逐项打勾。
6. 给出分级结论。
7. 只有 `validated` 以上结果才进入后续 watchlist / 模拟组合层。

## 15. 结论

本清单的核心目的，不是让回测变慢，而是防止系统以后出现“收益率很好但完全不可交易、不可复现、不可解释”的伪结果。当前仓库已经有不错的回测与评估基础，下一步必须把这些质量要求从经验规则升级为强制门禁。
