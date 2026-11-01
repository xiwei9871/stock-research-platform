# 统一回测执行层 POC V0.1 验证报告

- 任务：BACKTEST-ENGINE-POC-V0.1
- 基线：`origin/main` = `9bd955621bac032ce89d43a17a2bac04aa38e262`
- 分支：`research/unified-backtest-execution-poc-v01`
- **状态（V0.1.1）：`POC_PARTIAL / NOT_READY_FOR_M3`**
  - Gate A（执行核心）：通过；V0.1.1 修复了评审提出的 P0/P1 问题（§0）
  - Gate B（旧系统兼容）：通过，仅合成数据。TopN、TB 逐日一致；MT 有 2 处已记录的口径差异。TB/MT 的结果属于 `FROZEN_SIGNAL_REPLAY`
  - Gate C（真实历史对照）：**未完成**。只读导出脚本已交付（§5），但本轮没有拿到真实数据，没有运行任何真实历史对照
- 生产 EOD、旧回测实现、数据库都没有改动；新引擎没有接入任何生产路径。

## 0. V0.1.1 整改（针对 PR #16 评审）

| 评审项 | 处理 | 测试 |
|---|---|---|
| P0 空仓信号丢失 | 新增必填的 `signal_schedule`：列出每个决策日。日程中有、但没有目标行的日子 = `ALL_CASH_TARGET`（清仓）；不在日程中的日子 = `NO_SIGNAL`（继续持有）。目标行的日期不在日程中会报错。每次决策写入 `signals.csv`（`signal_type`） | `test_t19_*`、`test_t19b_*` |
| P0 时点检查 | `signal_ts` 必填，必须带时区；缺失、无法解析、不带时区、不在 `signal_date` 当天、晚于截止时点都会拒绝。截止时点和时区（默认 `Asia/Shanghai`）可配置，15:00 收盘信号和 20:30 盘后信号是两种不同的研究定义，同一次研究不能混用。可选的 `inputs_asof_ts` 单独校验"信号所用输入的最晚可用时间不晚于信号时间"；没有声明时，结果标为 `input_availability_check=NOT_DECLARED`，**不能据此证明输入没有前视** | `test_t16_*`、`test_t16b_*` ×5、`test_t16c_*` |
| P1 行情状态 | `adjust_type` 改为必填，而且必须是 `raw`（缺失也拒绝）；停牌状态改为三态解析，无法识别的字符串视为未知，而不是 False；`preclose` 缺失或 ≤0 时拒单（`preclose_missing`）；涨跌停价 NaN = 状态未知，拒单；`+inf`/`0` = 当天无涨跌幅限制（新股窗口） | `test_t09b_*`、`test_t15_*` |
| P1 公司行为模型 | 结果和 manifest 中写明 `corporate_action_model=TOTAL_RETURN_APPROX_FACTOR_REINVEST`：这是全收益近似，不是现金分红到账的真实账户 | `test_t14_*` |
| TB/MT 信号来源 | 适配器输出的每一行都带 `signal_provenance=FROZEN_SIGNAL_REPLAY`；manifest 记录 `signal_provenance` 和 `universe_label`（TB 的 153 只名单必须写 `EX_POST_UNIVERSE`）。V0.1.1 没有实现 `FULL_STRATEGY_REPLAY` | `test_adapters_tag_*` |
| 基准与超额收益 | `summarize(..., benchmark=)`：统计口径见 `metrics.py` 文件头（日度算术超额，按 √252 年化 TE 和 IR，基准缺失的天数单独计数） | `test_t10_*` |
| 真实数据准备链 | `backtest_engine/snapshot.py`，见 §5 | `test_backtest_engine_snapshot.py` ×3 |

**FROZEN_SIGNAL_REPLAY 的含义**：TB 和 MT 的决策取自旧模拟器的输出，不会对新引擎中的实际持仓（买入受阻、卖出受阻、权重漂移）作出反应。所以它只能衡量执行规则带来的影响，不能作为完整策略的可信度结论。

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
| `src/stock_research/backtest_engine/snapshot.py` | V0.1.1：只读导出（`export`）+ 离线准备引擎行情（`build`），涨跌停价复用 `tradeability` |
| `tests/test_backtest_engine_snapshot.py` | V0.1.1：涨跌停价推导、缺失状态 fail-closed、新股窗口判定 |
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
112 passed            # V0.1.1；V0.1 为 99
```

- 引擎测试 55 个（V0.1 为 42 个）：ledger 27、topn_compat 16、strategy_adapters 8、snapshot 3、run_manifest 1，全部通过。全部是合成数据。
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

## 5. Gate C：数据准备链已交付，真实对照未运行

### 5.1 现状

- 本地 `outputs/research/` 中没有带 `preclose`、复权因子、涨跌停价的行情快照。
- 185 恢复实例 `m2_l2_restore` 的只读访问在 V0.1 中被权限策略拦截；本轮没有再尝试，也没有绕过。
- 因此**本轮没有任何真实历史对照结果**。§4 的所有结论都只来自合成数据。

### 5.2 只读导出与准备脚本（`backtest_engine/snapshot.py`）

由有权限的执行者在能访问恢复实例的机器上运行第一步，其余步骤离线完成：

```bash
# 1. 只读导出（只对恢复实例或副本；事务为 REPEATABLE READ, READ ONLY，
#    启动时检查 transaction_read_only=on 并记录服务器身份）
python -m stock_research.backtest_engine.snapshot export \
  --service <restore_service> --start 2023-06-01 --end 2023-12-29 \
  --assets-file assets.txt --adj-source-version <v> --calendar-source-version <v> \
  --out-dir snapshot_raw/
# 2. 离线：合并行情、状态、主数据、复权因子；用 tradeability 规则生成涨跌停价
python -m stock_research.backtest_engine.snapshot build --raw-dir snapshot_raw/ --out-dir snapshot/
```

- 导出内容：`public.market_daily_bar`（只取 raw）、`core.asset_status_daily`、`core.asset_master`、`market.adjustment_factor`（指定 `source_version`）、`market.trading_calendar`。不写库，不改恢复实例。
- `build` 产物：`bars.csv`、`calendar.csv`、`snapshot_manifest.json`（原始文件和输出文件的 sha256、`snapshot_id`、`tradeability` 合约版本、质量统计：缺状态行、缺 preclose 行、规则未知行、无涨跌幅限制行、缺复权因子行、按规则 id 计数）。
- 涨跌停价：调用 `tradeability.resolve_limit_rule` 和 `legal_limit_price`，与 `compute_pit_limit_flags` 使用同一套板块、ST、新股窗口判定。只有在交易日历覆盖上市日时才计算上市后第几个交易日，避免把老股误判为新股窗口（`test_ipo_window_only_when_calendar_covers_listing`）。
- 已知局限：`build` 中 ST 状态取自 `asset_status_daily.is_st`；退市整理期等状态没有单独处理，相关行在 `resolve_limit_rule` 中会落入 `rule_unknown` 并按 fail-closed 拒单。

### 5.3 Gate C 实验设计（拿到数据后执行）

| 实验 | 对比 | 目的 |
|---|---|---|
| C1 | 旧引擎原始结果 vs 新引擎 LEGACY_COMPAT | 真实数据上的历史兼容性 |
| C2 | LEGACY_COMPAT vs REALISTIC_A_SHARE（同一组冻结信号） | 量化成交时点、成本、权重漂移、受阻成交的影响 |
| C3 | 信号与时点校验 | 检查股票池、财务数据、市场状态序列是否有前视 |

- 数据范围：覆盖 2023-08-28 印花税调整，以及发生过涨跌停、停牌、除权除息的证券。TB 和 MT 若在 2023 年没有真实信号，要另外补上它们实际使用的窗口（TB 2025-01～2026-06，MT 2026-01 起），不能用没有信号的行情充数。
- 输出：逐日 NAV、回撤、持仓、成交、成本、未成交数量和原因、收益差异，以及基准超额收益。
- 标签：TB 用 153 只名单时必须写 `universe_label=EX_POST_UNIVERSE`；TB 和 MT 都是 `FROZEN_SIGNAL_REPLAY`。如果只完成冻结信号重放，最终状态只能是 `FROZEN_SIGNAL_REPLAY_VALIDATED`，不能宣称完整策略可信。
- C3 不是执行引擎能单独完成的：需要逐个核对股票池生成时间、财务字段的可用时间、市场状态序列的更新时间。V0.1.1 只提供了 `inputs_asof_ts` 这一检查入口。

## 6. 可复现性

`python -m stock_research.backtest_engine.run --targets ... --bars ... --calendar ... --output-dir ... --strategy-id ... --data-snapshot-id ...`

输出：`equity_daily.csv`、`positions_daily.csv`、`trades.csv`、`corporate_actions.csv`、`summary.json`、`run_manifest.json`。

manifest 分成两部分：
- `deterministic`：引擎版本、模式、配置及其哈希、信号截止时点、输入文件 sha256、数据快照 id、覆盖范围、局限说明、各输出文件的 sha256。同一输入两次运行时，这部分完全一致（T10）。
- `runtime`：git commit、Python 和 pandas 版本、平台、运行时间。

所有输入路径都必须显式传入，引擎不会自己去找"最新文件"。

## 7. 是否可以启动 M3-lite

**还不能（`NOT_READY_FOR_M3`）。** 剩余条件：

1. 授权执行 §5.2 的只读导出（185 恢复实例或其他只读副本）。
2. 用导出的快照跑完 §5.3 的 C1、C2，并写出 C3 的逐项核对结果。
3. 如果 M3 要回答"策略本身是否可信"，而不只是"执行规则影响多大"，TB 和 MT 还需要 `FULL_STRATEGY_REPLAY`：把它们的选股和保护退出逻辑从旧模拟器中拆出来，按新引擎的实际持仓重新生成决策。V0.1.1 没有做。

以上都不需要修改生产代码、EOD 或数据库。
