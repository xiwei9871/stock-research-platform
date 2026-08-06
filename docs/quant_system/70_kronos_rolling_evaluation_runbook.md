# Kronos Rolling Evaluation Runbook

版本：2026-08-07

范围：研究评估、模型预检、结果验收。**不改线上个股工作台、不写生产预测缓存、不触发交易。**

## 1. 187 当前事实

| 项目 | 当前值 |
|---|---|
| Kronos 服务目录 | `/home/mqkj/kronos` |
| 生产端口 | `8123` |
| 生产模型 | `Kronos-small` |
| base 权重 | 已安装，可做预检/评估 |

生产服务当前只加载一个模型。small/base 对比必须使用同一批冻结输入快照；不能让两个模型分别重新查询实时数据库。

本 runbook 不记录密码、令牌、认证头、私钥或其他凭据。预测命令所需认证信息只从 187 上已有的安全环境配置读取，禁止写入命令行、日志和实验报告。

## 2. Base 安全预检与模型切换

### 2.1 预检原则

1. 先确认生产 `8123` 健康且身份为 `Kronos-small`，保留生产服务不动。
2. 优先在独立端口 `8124` 启动 base；只有确认 GPU 显存足够、回滚动作已准备好，才允许考虑串行切换。
3. `/health` 返回的模型身份必须与请求模型完全一致。身份不一致时停止，不能 fallback 到当前活动模型。
4. 正式评估前至少做一次单股票、单截止日预测，并记录 `sample_count=20`、输出时间戳完整性、GPU 显存和端到端延迟。

### 2.2 在 8124 启动 Kronos-base

在 187 的独立终端/会话执行以下命令，不要占用或停止 8123：

```bash
cd /home/mqkj/kronos
KRONOS_MODEL_NAME=Kronos-base \
/home/mqkj/miniconda3/envs/kronos/bin/python -m uvicorn service.app:app \
  --host 0.0.0.0 --port 8124
```

另开终端检查：

```bash
rtk curl -fsS http://127.0.0.1:8123/health
rtk curl -fsS http://127.0.0.1:8124/health
```

人工核对：

- 8123 的 `model` 是 `Kronos-small`；
- 8124 的 `model` 是 `Kronos-base`；
- 没有把一个模型的健康响应当成另一个模型使用；
- 服务状态、模型身份和权重身份均写入本次操作记录。

### 2.3 单股票预测、显存和延迟

用一个临时的单股票输入目录做预检；`--allow-smoke` 只允许用于此类预检，不可用于正式 20 股票结论。可按实际日期替换下面的占位路径和日期：

```bash
rtk python3 scripts/run_kronos_rolling_evaluation.py prepare \
  --universe-file /path/to/one_stock.csv \
  --start-date 2025-01-02 \
  --end-date 2025-01-02 \
  --output-dir /tmp/kronos-base-preflight \
  --allow-smoke

rtk python3 scripts/run_kronos_rolling_evaluation.py predict \
  --model base \
  --output-dir /tmp/kronos-base-preflight \
  --predict-url http://127.0.0.1:8124
```

预测前后各采集一次，并在请求期间观察峰值：

```bash
rtk nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv
```

记录以下证据：

- `/health` 原始响应及模型/权重身份；
- 单股票预测是否成功、返回时间戳是否与冻结快照一致、`sample_count` 是否为 20；
- `run_manifest.csv` 中的 `latency_ms`；
- GPU 型号、预测前/峰值/预测后显存和 GPU 利用率；
- 服务日志中的加载错误、CUDA OOM、超时或异常响应。

### 2.4 GPU 显存不足时的串行切换

如果 8124 无法加载 base 或出现 CUDA OOM：

1. 立即停止研究进程（8124），保留 8123 生产 small 运行。
2. 使用现有、已批准的 service-switch 流程串行加载 base；不要临时改造启动脚本。
3. 在停止 8123 **之前**，把该流程的反向命令（base → small）、进程/日志位置和验证步骤写入操作记录，并先确认可执行。没有可用回滚命令时，禁止停止生产。
4. 串行切换后先查 `/health`，再做同一只股票的单次预检；身份或显存不合格就立即执行反向切换。
5. base 评估结束后执行反向 service-switch，确认 8123 恢复 `Kronos-small`，再关闭临时进程和归档日志。

**安全底线：永远不要在 rollback 尚未准备好之前停止生产服务。** 任何切换失败都标记为 `unavailable`/`model_error`，不能当作预测准确率为零，也不能自动 fallback。

## 3. 正式实验 CLI

### 3.1 Prepare：一次性冻结输入

正式实验要求 universe 规范化后恰好 20 只股票；不要使用 `--allow-smoke`。准备阶段会冻结历史窗口、未来真实行情、参数、代码版本和输入指纹。

```bash
rtk python3 scripts/run_kronos_rolling_evaluation.py prepare \
  --universe-file config/kronos/evaluation_universe_20.csv \
  --start-date 2025-01-02 \
  --end-date 2025-01-31 \
  --output-dir outputs/research/kronos_rolling_eval/2025-01
```

### 3.2 Predict：相同快照分别运行两个模型

先跑 small：

```bash
rtk python3 scripts/run_kronos_rolling_evaluation.py predict \
  --model small \
  --output-dir outputs/research/kronos_rolling_eval/2025-01 \
  --predict-url http://192.168.3.187:8123
```

完成 base 的 `/health` 预检和显存检查后，再跑 base：

```bash
rtk python3 scripts/run_kronos_rolling_evaluation.py predict \
  --model base \
  --output-dir outputs/research/kronos_rolling_eval/2025-01 \
  --predict-url http://192.168.3.187:8124
```

若采用串行切换，base 命令的 URL 使用已确认恢复运行的 8123。两个阶段必须指向同一个 `output-dir`，不得重新 prepare；CLI 会先做模型身份检查，拒绝 mismatch，不读取 dashboard 数据。

### 3.3 Report：只从实验目录生成报告

```bash
rtk python3 scripts/run_kronos_rolling_evaluation.py report \
  --output-dir outputs/research/kronos_rolling_eval/2025-01
```

### 3.4 冻结快照与 no-dashboard 语义

- `prepare` 之后，`predict` 和 `report` 只读实验目录中的 `experiment.json`、`universe.csv` 和 `input_snapshots/`。
- 不重新查询 PostgreSQL，不读取当前 live universe，不调用 `/api/assets/...` 或其他 dashboard endpoint。
- 不把评估结果写入线上个股工作台或生产 Kronos cache。
- small/base 必须复用相同 `snapshot_key` 和 `input_fingerprint`；模型、权重、参数和 seed 单独记录。
- 每次请求的 20 条采样路径不是 20 个股票；报告同时保留代表路径、P10/P50/P90 和真实未来 bars。

## 4. 产物保存、失败、恢复与续跑

每个实验目录必须整体保留，不手工编辑或删除其中的隐藏恢复文件：

```text
experiment.json
universe.csv
input_snapshots/
run_manifest.csv
forecast_bars.parquet
realized_bars.parquet
metrics_by_stock_horizon.csv
metrics_by_model_horizon.csv
model_comparison.csv
report.md
```

同时保留运行日志、命令记录、模型 health 响应、GPU/延迟采样和 runner 产生的 transaction/report journal。参数、股票池或日期改变时使用新的实验目录；同一目录只用于同一 generation 的恢复。

### 可恢复运行

- `predict` 中断：确认服务健康和模型身份后，重新执行同一 model 的 predict 命令；已完成单元复用，未完成单元继续执行。
- `report` 中断：重新执行同一 output directory 的 report 命令；runner 会先恢复 journal，再校验 generation 和 Parquet/manifest 一致性。
- 恢复时不要删除 `.kronos_transaction.json`、report journal、stage 或 backup 文件；它们是恢复证据。
- 发现同一 generation 的产物被篡改、模型身份不一致、snapshot fingerprint 不一致或服务 fallback 时，应停止并保留现场，另建目录重跑。

### 状态解释

| 状态/信号 | 含义与处理 |
|---|---|
| `success` | 该股票、截止日、模型运行成功，可进入对应 horizon 指标。 |
| `insufficient_input` | 历史不足 250 根；不补数据，不算作模型准确率。 |
| `insufficient_truth` | 未来真实行情不足；只排除受影响 horizon。 |
| `invalid_input` | 重复日期、NaN 或非法 OHLC；停止该单元并查数据源。 |
| `model_error` / `unavailable` | 模型、GPU、服务加载或健康检查失败；不是预测得分为零。 |
| `timeout` / `transport_error` / `protocol_error` | 网络、超时或响应契约问题；保留原始错误，不 fallback。 |
| `partial` | 仍有成功和失败单元；报告可生成，但必须披露覆盖率和失败分布。 |

## 5. 验收

### 5.1 代码验收（固定命令）

```bash
rtk pytest -q tests/test_kronos_evaluation_types.py tests/test_kronos_evaluation_data.py tests/test_kronos_evaluation_client.py tests/test_kronos_evaluation_metrics.py tests/test_kronos_evaluation_runner.py tests/test_kronos_rolling_evaluation_cli.py
rtk git diff --check
```

### 5.2 真实实验验收清单

在 small/base 两份 manifest（或同一 manifest 中的两个 model 分组）上确认：

- `snapshot_key` 集合完全相同；
- 每个相同 `snapshot_key` 的 `input_fingerprint` 完全相同；
- manifest 中所有运行单元都有明确状态，状态计数之和等于应运行单元数，没有静默丢行；
- `health_model_identity`、`response_model_identity` 与请求模型一致，没有 mismatch、fallback 或用另一个模型补齐；
- 每个模型的 `sample_count`、seed、输入窗口和 forecast horizon 符合 `experiment.json`；
- `report.md` 有 `h=1/3/5/10` 四个 horizon 的覆盖/指标行，并明确包含 `persistence` 和 `drift` 两个基线；同时在 `metrics_by_model_horizon.csv` 核对两基线行；
- `model_comparison.csv` 有 small/base 的配对比较、样本覆盖和置信区间；
- `latency_ms`、GPU 显存、服务身份和失败原因均可追溯到日志或 manifest。

### 5.3 结果解释边界

- **预测准确性**：看 1/3/5/10 日的收益误差、方向命中、P10–P90 覆盖率和分位数损失，并与 persistence、drift 同时比较；单票或单日不能代表整体能力。
- **模型能力**：small/base 只有在相同快照、相同 seed、相同运行单元下的配对差异才可比较；结论使用 `small_preferred`、`base_preferred`、`no_clear_winner` 或 `not_proven`。
- **延迟与工程成本**：GPU 显存、推理延迟、失败率是独立维度。base 即使某些 accuracy 指标较好，也不能忽略显存/延迟/可用性成本。
- **数据失败**：输入不足、真实行情不足和非法数据不能混入准确率分母；模型/GPU/网络失败不能被当成模型能力差，也不能由另一个模型 fallback 补齐。

**Kronos-base 不因参数更多而预设更好。** 只有在配对指标、区间校准、覆盖率、延迟和失败率共同支持时，才可提出 base 优于 small；一个月滚动窗口仍只是初步证据。
