# Kronos 可配置滚动评估引擎设计：2026 年 7 月 small 实验

## 目标

本设计首先完成一个可复用的 Kronos 滚动评估引擎，再用一份参数配置评估 `small` 模型在最近市场阶段的实际预测表现：从 2026-07-01 开始，随机固定选取 20 只股票，按交易日滚动生成未来 10 根日 K 预测；准确性只以未来第 1 个交易日为主指标，同时保留未来第 1、3、5、10 根 K 的预测结果，供后续分析。

以后相同类型的实验只修改 JSON 配置，不再为每次实验创建新的专用脚本或重新设计数据流。当前实验是通用引擎的第一份配置。

本实验必须区分两类结果：

1. **历史可评分层**：预测时点的下一交易日真实 K 已经入库，允许计算准确率。
2. **最新预测层**：使用最近一个可用交易日作为输入，生成未来 10 根日 K，但真实结果尚未全部出现，只标记为待验证，不能混入准确率。

这样既能覆盖“2026 年 7 月至今”的滚动窗口，也不会为了等待完整 10 日真实数据而丢弃最近的预测。

## 设计原则：固定引擎、参数驱动

评估流程固定为：

`加载配置 → 校验参数 → 冻结数据和股票池 → 建立滚动快照 → 调用模型 → 校验 OHLC → 计算指标 → 生成冻结报告`

可调内容全部进入配置文件，包括模型、日期、频率、输入窗口、预测长度、采样路径数、股票池模式、随机种子、评分 horizon 和是否生成最新预测。引擎代码只负责稳定执行这条流程。

只有在新增模型适配器、数据频率、指标或输出格式时才修改代码；改变某次实验的日期、股票数量、模型或评价窗口，不应修改代码。

本项目不新增 YAML 依赖，首版使用 Python 标准库可解析的 JSON 配置；配置文件必须带 `schema_version`，运行时进行字段、类型、范围和组合约束校验。

## 方案选择

- **每次编写专用脚本**：短期最快，但会重复实现选股、滚动、评分和报告，容易再次出现规则漂移；不采用。
- **一个通用引擎 + JSON 参数文件**：初始需要整理接口，但之后实验只改参数，结果结构统一、便于复现；本设计采用。
- **实验管理页面或数据库注册表**：可进一步支持批量运行和网页比较，但会引入 UI、权限和状态管理，不作为本轮前置条件。

## 范围与不变项

### 实验参数

| 参数 | 取值 | 说明 |
|---|---:|---|
| 模型 | `small` | 本轮只测 small，不调用 base，不启用 fallback |
| 输入窗口 | 250 根日 K | 每个滚动时点只使用该时点之前的真实 qfq 日 K |
| 预测长度 | 10 根日 K | 每次都生成第 1、3、5、10 根预测 |
| 主准确性 horizon | 1 | 只有未来 1 个交易日进入主正确率统计 |
| 保留 horizon | 1、3、5、10 | 作为预测输出和辅助分析，不改变本轮主指标 |
| 路径数 | 20 | 沿用当前 Kronos 采样配置，对每个 horizon 使用聚合后的预测结果 |
| 模型随机种子 | `20260806` | 与现有评估保持一致，便于复现 |
| 股票数量 | 20 | 从冻结的合格股票池中随机抽取 |
| 股票池随机种子 | `20260808` | 与模型采样种子分离，保证选股可复现 |
| 起始日期 | `2026-07-01` | 滚动预测起点 |
| 截止日期 | 执行时查询 | 取数据库中实际可用的最新交易日，不把当前自然日硬编码为行情截止日 |
| 复权 | `qfq` | 与现有 Kronos 工作台和历史评估保持一致 |

上表是当前实验配置的值，不是写死在引擎中的常量。未来实验可通过同一配置结构替换这些值。

每个滚动时点的输入都来自数据库中该时点以前的真实数据；绝不把前一次预测的 OHLC 作为下一次输入，避免递归误差和数据泄漏。

### 股票池

股票池在实验准备阶段一次性确定并冻结，不随滚动日期变化。候选股票必须满足：

- `asset_master.market = 'CN_A'`；
- 在实验准备日处于可交易/已上市状态；
- 排除 ST、退市及明显不可交易标的；
- `market_daily_bar.adjust_type = 'qfq'`；
- 在 2026-06-30 之前至少有 250 根可用日 K，确保 2026-07-01 的首个输入窗口不使用未来信息。

从候选池中使用 `universe_seed=20260808` 做不放回随机抽样，恰好得到 20 只。输出必须同时保存：

- `universe.csv`：代码、名称、市场、抽样顺序；
- 候选池数量；
- 候选池筛选条件；
- 随机种子；
- 候选池和最终股票池的内容哈希。

实验报告以冻结的 `universe.csv` 为准，重跑不能静默更换股票。

## C 方案的数据语义

### 历史可评分层

对每只股票，从 2026-07-01 起按实际交易日逐日建立 origin。只要该 origin 的下一交易日真实 K 已经存在，就纳入历史滚动评分；未来第 3、5、10 个交易日的真实 K 如果已经存在则一并保存，但它们不作为本轮主准确率的必要条件。

因此，历史层的主评分覆盖范围是：

`2026-07-01` 至数据库最新可获得交易日的前一个交易日。

如果某个 origin 缺少下一交易日真实 K，则不能计算 h=1，记录为未评分并说明原因，不得用后续日期补齐。

### 最新预测层

另取每只股票最近一个有完整 250 根输入日 K 的交易日作为 latest origin，生成未来 10 根日 K。该批结果单独标记为 `forecast_only` / `pending_truth`：

- 可以展示预测值；
- 可以保存 1、3、5、10 horizon 的预测；
- 不写入任何准确率、方向命中率或基准比较结果；
- 后续真实 K 到齐后，必须通过新的评估批次重新评分，不在本次报告中回填。

未来交易日时间戳必须来自项目现有交易日历解析逻辑，并在 manifest 中冻结；不能用简单自然日序列替代交易日历。如果当前环境无法得到足够的未来交易日历，latest forecast 仍保留输入和 `pending_calendar` 状态，实验历史评分不受影响。

## 预测和聚合规则

每个 origin 调用现有 Kronos small 预测链路，固定生成 20 条采样路径。对每个未来 horizon：

- 保留原始路径数据，便于审计异常；
- 使用现有聚合规则生成展示用 OHLC 预测；
- 在输出中注明聚合方法和路径数量；
- 对每条预测执行 OHLC 合法性校验：`high >= max(open, close)`、`low <= min(open, close)`、`high >= low`，并拒绝 NaN、无穷值及非正价格。

本实验只允许使用 small 模型。运行 manifest、服务健康检查和每个结果文件都要记录实际模型身份；如果实际模型不是 small、发生 fallback 或服务返回非法 OHLC，该 origin 失败并进入错误报告，不能悄悄改用其他模型或修正后当作成功。

## 准确性定义

主指标只计算 h=1，按股票和全体股票分别汇总。

对预测收盘价 `pred_close[t+1]` 与真实收盘价 `real_close[t+1]`：

- 预测收益率：`pred_return = pred_close[t+1] / close[t] - 1`；
- 真实收益率：`real_return = real_close[t+1] / close[t] - 1`；
- 绝对收益误差：`abs(pred_return - real_return)`；
- 方向命中：`sign(pred_return) == sign(real_return)`，预测和真实均为 0 时视为命中；
- 可选的价格误差：保存相对价格误差，但不替代收益率误差作为主指标。

同时计算一个不使用 Kronos 的 persistence baseline：

`baseline_close[t+1] = close[t]`，`baseline_return = 0`。

报告至少包含：

- 20 只股票的 h=1 样本数、方向命中率、平均绝对收益误差、中位绝对收益误差；
- Kronos small 与 persistence baseline 的差值；
- 按交易日的横截面汇总，观察模型是否在某些日期集中失效；
- h=3、h=5、h=10 的预测覆盖数量和待验证数量，但明确标记为辅助输出，不宣称本轮已完成准确率评估。

## 输出目录和文件

实验输出根目录固定为：

`outputs/research/kronos_rolling_eval/<experiment_id>/`

当前实验使用 `experiment_id=2026-07-small-rolling`。每次运行必须使用独立的 experiment id，禁止覆盖已有结果。

目录至少包含：

- `manifest.json`：完整配置、代码版本、数据库行情最大日期、模型身份、seed、时间范围、运行时间和状态；
- `universe.csv`：冻结的 20 只股票；
- `universe_selection.json`：候选池筛选与哈希信息；
- `snapshots/`：每只股票每个 origin 的输入覆盖、未来时间戳和 truth status；
- `forecast_bars/`：每个 origin 的 h=1/3/5/10 预测 OHLC；
- `realized_bars/`：已经存在的真实 OHLC；
- `metrics_by_stock.csv`：每只股票 h=1 主指标；
- `metrics_by_date.csv`：按 origin 日期的 h=1 汇总；
- `metrics_summary.json`：总体指标、baseline 对比、覆盖率和错误统计；
- `latest_forecast.json`：最新 `forecast_only` 预测及其 pending 状态；
- `report.md`：可读实验报告，分开列出历史评分层和最新预测层。

所有输出都必须是一次运行的冻结快照。报告不能在生成后重新查询数据库或在线预测来补数据。

## 通用引擎和配置

所有实验使用同一个入口：

`scripts/run_kronos_experiment.py --config configs/<experiment>.json`

当前 C 实验的第一份配置为：

`configs/kronos_2026_07_small_rolling.json`

配置采用以下结构，示例本身是合法 JSON：

```json
{
  "schema_version": 1,
  "experiment_id": "2026-07-small-rolling",
  "model": {
    "name": "small",
    "fallback": false,
    "seed": 20260806,
    "sample_count": 20
  },
  "data": {
    "frequency": "1d",
    "adjust_type": "qfq",
    "input_window": 250,
    "start_date": "2026-07-01",
    "end_date": "latest_available"
  },
  "universe": {
    "mode": "random",
    "count": 20,
    "seed": 20260808,
    "market": "CN_A",
    "asset_ids": null
  },
  "prediction": {
    "forecast_horizon": 10,
    "report_horizons": [1, 3, 5, 10],
    "include_latest_forecast": true
  },
  "evaluation": {
    "primary_horizon": 1,
    "baseline": "persistence"
  }
}
```

引擎分为以下职责清晰的阶段：

1. **配置加载器**：读取 JSON、填充仅有明确文档的默认值、校验 schema 和参数组合，并把规范化后的配置写入 manifest；
2. **股票池选择器**：支持冻结的 `asset_ids` 和带 seed 的随机候选池，输出选择过程、数量和哈希；
3. **数据快照器**：按配置读取行情、冻结行情截止日和交易日历，建立只包含真实历史数据的 rolling origins；
4. **模型适配器**：根据 `model.name` 调用 small/base 等已注册模型，核对实际模型身份，禁止未配置的 fallback；
5. **结果校验器**：校验 20 路原始路径、聚合 OHLC 和错误状态；
6. **评估器**：按照 `primary_horizon` 和 `report_horizons` 计算指标，严格排除 `forecast_only`；
7. **报告器**：生成统一目录、manifest、预测文件、评分文件和可读报告。

这些模块通过稳定的数据对象通信；日期、模型、股票数量和 horizon 的变化不应改变模块接口。

配置校验至少包括：

- `model.name` 必须是已注册模型；`fallback=false` 时实际模型不匹配必须失败；
- `input_window`、`forecast_horizon`、`sample_count` 和 universe count 必须为正整数；
- `primary_horizon` 必须出现在 `report_horizons` 中且不超过 `forecast_horizon`；
- `end_date=latest_available` 时必须把数据库实际最大交易日写入 manifest；
- `universe.mode=random` 必须有 seed，`asset_ids` 模式必须冻结并校验数量；
- 输出目录已存在时拒绝覆盖，除非显式使用新的 experiment id。

现有 snapshot 状态需要明确扩展或等价表达：

- `ready`：至少具备 h=1 truth，可评分；
- `partial_truth`：预测窗口已生成，但 h=3/5/10 truth 不完整；仍可评分 h=1；
- `forecast_only`：没有真实 future bar，只能展示预测；
- `insufficient_input`、`invalid_input`、`error`：按现有错误语义处理。

报告层必须按 `scored_horizons` 过滤，而不能继续以“10 根真实 K 全部存在”作为唯一成功条件，否则会错误丢弃本轮应评分的 h=1 样本。

## 验收标准

实现和运行完成后，必须满足：

1. 当前配置选出的股票池恰好 20 只，随机选择可由 `universe_seed=20260808` 重现；
2. 每只股票从 2026-07-01 开始按交易日滚动，输入窗口为真实 qfq 日 K 的 250 根；
3. 每个可运行 origin 都生成 h=1/3/5/10 预测，模型身份始终为 small，sample count 始终为 20；
4. h=1 的历史评分不要求 h=3/5/10 truth 已齐全，且没有把 forecast-only 结果混入准确率；
5. 最新预测层明确显示 `forecast_only` / `pending_truth`，并保存未来 10 根预测；
6. 所有成功预测均通过 OHLC 合法性检查，错误 origin 有明确错误原因；
7. 任何滚动 origin 都没有使用模型前一次的预测作为输入；
8. 报告包含 Kronos small 与 persistence baseline 的 h=1 对比；
9. 运行结束后可仅凭输出目录复核股票池、数据边界、配置、模型身份、预测和评分，不需要重新访问数据库；
10. 自动化测试覆盖：配置校验、随机股票池可复现、部分 truth 可评分、forecast-only 排除评分、OHLC 校验、无 fallback 和结果冻结；
11. 使用同一引擎把当前配置中的日期、模型、股票数量或 horizon 改成另一组合法值时，不需要修改 Python 代码，输出结构仍然一致；
12. 运行 manifest 保存规范化配置和配置文件哈希，能够复现一次实验所使用的全部参数。

## 不在本轮范围内

- 不运行 base 模型；
- 不比较 5 分钟、10 分钟、20 分钟或 30 分钟级别；
- 不修改个股工作台、内外网部署或在线预测 API；
- 不把 h=3/5/10 的未完成真实结果包装成准确率；
- 不依据本轮结果直接修改交易策略或下单规则。
