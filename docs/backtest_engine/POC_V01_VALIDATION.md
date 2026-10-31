# 统一回测执行层 POC V0.1 验证报告

- 任务：BACKTEST-ENGINE-POC-V0.1
- 基线：`origin/main` = `9bd955621bac032ce89d43a17a2bac04aa38e262`
- 分支：`research/unified-backtest-execution-poc-v01`
- **状态：`POC_PARTIAL / NOT_READY_FOR_M3`**
  - Gate A（执行核心）：通过
  - Gate B（旧系统兼容）：通过。TopN、TB 逐日一致；MT 有 2 处已记录的口径差异
  - Gate C（真实历史对照）：**未完成**，原因见 §5
- 生产 EOD、旧回测实现、数据库都没有改动；新引擎没有接入任何生产路径。

## 1. 交付内容

| 路径 | 内容 |
|---|---|
| `src/stock_research/backtest_engine/config.py` | `RealisticExecutionConfig`、按日期分段的印花税表、配置哈希 |
| `src/stock_research/backtest_engine/contracts.py` | 目标权重和行情的输入校验（fail-closed） |
| `src/stock_research/backtest_engine/ledger.py` | `execute_target_weights`：REALISTIC_A_SHARE 现金和股数账户 |
| `src/stock_research/backtest_engine/legacy_compat.py` | `execute_legacy_compat`：旧口径权重空间引擎，只用于回归 |
| `src/stock_research/backtest_engine/adapters.py` | TopN、TB、MT 到目标权重的适配器 |
| `src/stock_research/backtest_engine/topn_compat.py` | TopN 兼容运行和逐日对账函数 |
| `src/stock_research/backtest_engine/metrics.py` | 统一绩效指标定义（每年 252 个交易日） |
| `src/stock_research/backtest_engine/run.py` | 运行入口，写出产物和 `run_manifest.json` |
| `tests/test_backtest_engine_ledger.py` | T01–T10、T13–T18、输入契约测试 |
| `tests/test_backtest_engine_topn_compat.py` | T11：TopN 新旧引擎逐日对账（15 组参数 × 种子，加交易级比对） |
| `tests/test_backtest_engine_strategy_adapters.py` | T12：TB、MT 适配器回归和已知差异 |
| `tests/test_backtest_engine_run_manifest.py` | T10：同一 manifest 重复运行，输出逐字节一致 |
| `docs/backtest_engine/artifacts/topn_legacy_compat_reconciliation_seed42.csv` | TopN 逐日对账样例（合成数据，58 天） |

## 2. 测试结果

命令和结果（本地 `.venv`，Python 3.14.7，pandas 3.1.0）：

```text
.venv/bin/python -m pytest tests/test_backtest_engine_*.py \
  tests/test_vectorized_topn_backtest.py tests/test_market_style_switch_v1.py \
  tests/test_backtest_constraints.py -q
99 passed
```

- 新增测试 42 个，全部通过。
- 原有的 `test_vectorized_topn_backtest.py`、`test_market_style_switch_v1.py`、`test_backtest_constraints.py` 共 57 个测试仍然通过，说明旧代码没有被改动。
- `tests/test_serenity_tight3b_c2_experiment.py` 在 `main` 上本来就无法收集：它导入 `watchdog_runner.backfill.should_send_watchdog_message` 失败，跟本 PR 无关。本 PR 直接调用了 `serenity_tight3b_c2_experiment._simulate_one_config`，这个调用是能工作的。
- GitHub Backend CI 预计仍会失败，原因是 `auction_data.py:9` 中遗留的 `import tushare`，由 Devin 处理。本 PR 不修改竞价采集代码。

### 测试矩阵对照

| 编号 | 场景 | 结果 | 测试 |
|---|---|---|---|
| T01 | T 日信号，T+1 开盘成交 | 通过 | `test_t01_*` |
| T02 | 权重随价格自然漂移 | 通过 | `test_t02_*` |
| T03 | 开盘即涨停，买入受阻，现金保留 | 通过 | `test_t03_*` |
| T04 | 跌停卖不出，继续持仓，下一交易日重试 | 通过 | `test_t04_*` |
| T05 | 停牌不成交 | 通过 | `test_t05_*` |
| T06 | 2023-08-25 卖出按 10bp、2023-08-28 卖出按 5bp 计印花税 | 通过 | `test_t06_*` |
| T07 | 非等权目标和现金留存 | 通过 | `test_t07_*` |
| T08 | 资金不足，按整手减少；不足一手则拒单，现金不为负 | 通过 | `test_t08_*` |
| T09 | 停牌状态或涨跌停价缺失时 fail-closed | 通过 | `test_t09_*` |
| T10 | 相同输入两次运行结果一致；manifest 输出逐字节一致 | 通过 | `test_t10_*` ×2 |
| T11 | TopN 兼容模式与原引擎逐日对账 | 通过，最大误差 0.0（阈值 1e-10） | `test_t11_*` ×16 |
| T12 | TB、MT 兼容适配，差异有归因 | TB 通过（≤1e-10）；MT 在约定内通过，并有一个已知差异的测试 | `test_t12_*` ×5 |
| T13 | T+1 卖出限制 | 通过（见 §3.3 说明） | `test_t13_*` |
| T14 | 除权除息日不出现虚假收益跳变；`fail_closed` 策略下缺少因子则报错 | 通过 | `test_t14_*` ×2 |
| T15 | 用复权价执行被拒绝 | 通过 | `test_t15_*` |
| T16 | 信号时间晚于截止时点被拒绝；截止时点可配置（如 20:30） | 通过 | `test_t16_*` |
| T17 | 卖出受阻后目标改变，待卖单按新目标更新 | 通过 | `test_t17_*` |
| T18 | 现金流水、持仓市值、NAV 对账；资产守恒；无 NaN 或负现金 | 通过 | `test_t18_*` |

## 3. REALISTIC_A_SHARE 执行模型

### 3.1 每个执行日 D 的事件顺序

D 是信号日之后的下一个交易日。

1. **公司行为**：持有股数乘以 `adj_factor[D] / adj_factor[上次]`，相当于分红送股按除权价再投资。这样既不会把现金分红重复计入，也不会出现价格跳空带来的虚假亏损。
2. **卖出**：先处理新信号的卖单，再重试之前受阻的待卖单。新信号会覆盖同一资产的旧待卖目标。
3. **买入**：只在有新信号的日子进行。按目标权重从大到小排序，同权重按资产代码排序；按整手买入；买入受阻则取消当次订单，资金留在现金里，不追价。
4. **估值**：按 D 日未复权收盘价计算市值；停牌或没有行情的持仓用最近一次收盘价估值。

### 3.2 价格口径

| 数据 | 用途 |
|---|---|
| D 日未复权 `open`（或 `close`，由 `fill_price` 配置） | 成交价，再加减滑点 |
| `preclose`、`limit_up_price`、`limit_down_price` | 判断涨跌停，以及在交易前给持仓定价 |
| `adj_factor` | 只用于公司行为调整股数 |
| 成交金额 | 计算佣金（含最低佣金）、印花税、滑点 |

`validate_price_bars` 会拒绝 `adjust_type` 不是 `raw` 的输入。这一点是针对 TB 默认使用 `hfq` 价格的风险（`tech_bottleneck_v1.py:54`）专门加的。

### 3.3 保守近似和已知局限

如果要把引擎的结论当作历史真实交易标准，下面这些都必须先知道：

- **开盘涨停一律视为买不进，开盘跌停一律视为卖不出。** 不模拟盘中打开涨停板，因此对"开盘封板后又打开"的情况偏保守。
- **没有成交量约束**：不限制参与率，不模拟冲击成本，滑点是固定的 bp。
- **卖出数量**：清仓时允许卖出零股，部分减仓按整手向下取整；买入一律整手。
- **T+1 卖出限制**：引擎每天先卖后买，同一天买入的股票当天不可能再卖出，所以 `t_plus_1_unsellable` 只是防御性检查。T13 验证的是当天买入的股票最早次日才卖出。
- **下单数量的定价基准**：买卖股数按交易前 NAV（持仓按 `preclose` 计价）计算，实际成交用开盘价。开盘跳空较大时，部分买单可能因现金不足被缩量，状态记为 `partial`。
- **公司行为**：`factor_reinvest` 把现金分红视为按除权价再投资。这在收益口径上等价于全收益，但不是"分红到账为现金"的真实账户。可以切换到 `fail_closed` 模式。配股、缩股、退市清算等没有单独建模。
- **涨跌停价**：引擎直接使用输入的 `limit_up_price` / `limit_down_price`，不自己计算。输入方应该用 `tradeability.resolve_limit_rule` / `legal_limit_price` 生成这两个价格（复用现有规则，不另写一套）。V0.1 没有实现这个数据准备脚本。
- **基准和超额收益**：没有实现。

## 4. LEGACY_COMPAT 回归结果

### 4.1 TopN

- 方法：`topn_target_weights` 直接调用旧模块自己的 `_normalize_scores`、`_rebalance_dates`、`_target_weights_for_date` 来生成目标权重，保证选股完全一致；然后交给 `execute_legacy_compat`（`fill_lag=1`，带同样的成交约束和成本）。
- 覆盖：5 组参数（每日/每周调仓、`transaction_cost_bps`、三项成本、`max_position_weight`、`max_positions`、`block_missing_limit_state`）× 3 个种子；合成数据中随机标注涨停、跌停、停牌。
- 结果：每日净值、净收益、成本的最大绝对误差都是 **0.0**（阈值 1e-10），日期集合完全一致；交易级比对中，成交权重、成本、`skip_reason` 也完全一致。
- 样例：`docs/backtest_engine/artifacts/topn_legacy_compat_reconciliation_seed42.csv`。

### 4.2 Tech Bottleneck

- 方法：TB 的选股、保护退出（rank_exit / ATR / MA）与市场暴露逻辑，都交织在 `_simulate_one_config` 内部。适配器（`positions_to_target_weights`）取旧模拟器每天的决策后权重作为目标，然后在 `fill_lag=0`、无成交约束、20bp 单边成本的设置下由新引擎执行。
- 结果：2 个种子 × 每周、每月调仓，净值误差 ≤ 1e-10，成本误差 ≤ 1e-12。
- 局限：这验证的是"执行口径可以复现"，不是"TB 的选股可以从策略代码中独立抽出来"。要在真实口径下运行 TB，需要先用旧模拟器生成每日决策权重，再交给 REALISTIC 引擎执行。这种做法的前提是：保护退出条件只用 T 日收盘之前的信息，代码里确实如此（`serenity_tight3b_c2_experiment.py:376-393`），可以在 T+1 开盘执行。
- **股票池标记**：用 `strict_153_*` 名单得到的任何 TB 结果，都必须标为 `EX_POST_UNIVERSE / LEGACY_REPRODUCTION_ONLY`。V0.1 没有用真实数据运行 TB。

### 4.3 Mid Trend

- 方法：`mid_trend_target_weights` 把每日选股行（`invested_weight` 在当天选中的资产间平分）转换成目标权重，在 `fill_lag=0`、无约束、零成本的设置下执行。
- 结果：2 个种子下，净值误差 ≤ 1e-10。前提是统一了日期约定：MT 把 close(t)→close(t+1) 的收益记在 t 日，新引擎记在 t+1 日。
- **已知差异 1（日期约定）**：同一笔收益，MT 记在当天，新引擎记在下一个交易日。对账时需要把日期平移一天。
- **已知差异 2（行情缺失）**：某只股票在 d 日没有行情时，MT 的 `groupby(asset).shift(-1)` 会跨过缺口，把 d-1 到 d+1 的涨跌记在 d-1 日，并在 d 日把该股票从平均中剔除（其余股票的权重被放大）。新引擎对缺失行情记零收益。从 d-1 起两者净值开始偏离。`test_t12_mid_trend_known_difference_missing_price_bar` 固定了这个行为。`ARCHITECTURAL_JUDGMENT`：MT 的处理会把停牌期间的涨跌提前算进收益，属于轻微的前视，新引擎的处理更合理。
- 局限：MT 的生产路径另有资金预算（full/reduced/light）和选股逻辑（`current_mid_trend_strategy_v1.py`）。V0.1 只验证了它的执行函数 `_simulate_equal_weight_daily`，没有用真实数据运行生产 MT。

## 5. Gate C 未完成的原因

真实历史对照需要以下数据：未复权的 OHLC、`preclose`、涨跌停价、停牌状态、复权因子（`market.adjustment_factor`）、交易日历，时间范围最好覆盖 2023 年 8 月。

- 本地 `outputs/research/` 中没有找到带 `preclose`、复权因子或涨跌停价的行情快照（已检索 CSV 和 Parquet）。
- 185 上的 `m2_l2_restore` 恢复实例：本轮尝试用 SSH 只读查看，被权限策略拦截（理由是会读取生产主机）。我没有绕过这个限制。
- 生产库 187：按任务要求不连接。

所以本轮**只有合成 fixture 测试，没有真实历史验证**。T01–T18 的结论只说明引擎逻辑正确，不说明任何策略的历史表现。

### 完成 Gate C 需要的决定

1. 授权只读访问 185 的 `m2_l2_restore`（例如 `psql` 只读账号，或者在 185 上执行导出脚本并把结果放到 NAS）。
2. 导出范围：2023-06-01 到 2023-12-29，TB 153 只 + TopN 当期前 50 名 + MT 漏斗股票，导出 `market_daily_bar`（raw）、`market.adjustment_factor`、`core.asset_status_daily`，用 `tradeability` 生成涨跌停价。按估计大约几十万行，内存远低于 4GB。
3. 把导出文件的 sha256 写入 manifest 的 `data_snapshot_id`，然后对三个策略分别运行：
   - Legacy Original：旧代码
   - Legacy Compat：新引擎，旧口径
   - Realistic A-Share：新引擎，真实口径

   输出净值、回撤、交易级差异、成本差异和未成交影响。

## 6. 可复现性

`python -m stock_research.backtest_engine.run --targets ... --bars ... --calendar ... --output-dir ... --strategy-id ... --data-snapshot-id ...`

输出：`equity_daily.csv`、`positions_daily.csv`、`trades.csv`、`corporate_actions.csv`、`summary.json`、`run_manifest.json`。

manifest 分成两部分：
- `deterministic`：引擎版本、模式、配置及其哈希、信号截止时点、输入文件 sha256、数据快照 id、覆盖范围、局限说明、各输出文件的 sha256。同一输入两次运行时，这部分完全一致（T10）。
- `runtime`：git commit、Python 和 pandas 版本、平台、运行时间。

所有输入路径都必须显式传入，引擎不会自己去找"最新文件"。

## 7. 是否可以启动 M3-lite

**还不能（`NOT_READY_FOR_M3`）。** 剩余条件：

1. 完成 Gate C（§5），需要先授权数据访问。
2. 写数据准备脚本：从只读快照生成未复权行情、涨跌停价和复权因子，涨跌停价复用 `tradeability`。
3. 把 TB 的决策权重导出流程固化为脚本，并加上 `EX_POST_UNIVERSE` 标记。
4. 实现基准收益和超额收益的计算。

这四项都不需要修改生产代码或数据库。
