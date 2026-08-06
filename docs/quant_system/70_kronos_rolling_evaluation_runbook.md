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

## 0. 执行位置与命令约定

- 标注为“本地研究仓库”的命令在研究代码所在机器执行；先进入 `/path/to/stock_research`，并使用本地 `rtk` wrapper（例如 `rtk python3`、`rtk pytest`）。`/path/to/stock_research` 是占位路径，执行前替换为实际绝对路径。
- 标注为“187 远程 shell”的命令在 187 上执行，使用普通 shell 命令，不加 `rtk` 前缀。`rtk` 不是 187 的前置条件，也不要把本地 wrapper 前缀复制到远程命令中。
- 本 runbook 不提供 SSH 登录命令、密码或令牌值。远程命令假定操作者已经进入 187，并且安全环境变量已按现有部署方式加载。

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

另开 187 远程 shell 检查。当前客户端要求 `X-Kronos-Token`，令牌只从 187 的安全环境变量读取；不要把令牌值写进命令、历史记录、日志或报告：

```bash
: "${KRONOS_INTERNAL_TOKEN:?请先从 187 的安全环境加载 KRONOS_INTERNAL_TOKEN，不要回显令牌值}"
curl -fsS -H "X-Kronos-Token: ${KRONOS_INTERNAL_TOKEN}" http://127.0.0.1:8123/health
curl -fsS -H "X-Kronos-Token: ${KRONOS_INTERNAL_TOKEN}" http://127.0.0.1:8124/health
```

如果安全环境不允许在 shell 中注入令牌，则使用仓库的已认证客户端执行 health/model 预检；不要改用未认证的 `curl`，也不要手工填写令牌值。

人工核对：

- 8123 的 `model` 是 `Kronos-small`；
- 8124 的 `model` 是 `Kronos-base`；
- 没有把一个模型的健康响应当成另一个模型使用；
- 服务状态、模型身份和权重身份均写入本次操作记录。

### 2.3 单股票预测、显存和延迟

用一个临时的单股票输入目录做预检；`--allow-smoke` 只允许用于此类预检，不可用于正式 20 股票结论。以下是本地研究仓库命令，可按实际日期替换占位路径和日期：

```bash
cd /path/to/stock_research
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

预测前后各采集一次，并在请求期间观察峰值。以下命令在 187 远程 shell 执行，不使用 `rtk`：

```bash
nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv
```

记录以下证据：

- `/health` 原始响应及模型/权重身份；
- 单股票预测是否成功、返回时间戳是否与冻结快照一致、`sample_count` 是否为 20；
- `run_manifest.csv` 中的 `latency_ms`；
- GPU 型号、预测前/峰值/预测后显存和 GPU 利用率；
- 服务日志中的加载错误、CUDA OOM、超时或异常响应。

### 2.4 GPU 显存不足时的串行切换

本仓库没有经过验证的 Kronos service-switch 脚本或 systemd unit，也不提供任何精确的切换命令。串行切换是硬前置条件，不是可以临时发挥的操作步骤。如果 8124 无法加载 base 或出现 CUDA OOM，只有在满足下面的前置条件后才能考虑串行切换：

1. 在停止 8123 **之前**，从 187 服务负责人取得当前环境专用、已批准的正向命令（small → base）和反向命令（base → small）。同时取得进程/日志位置、health 验证步骤和失败处置方式。
2. 在不影响生产的条件下对正向/反向流程做 dry-run 或等价的安全演练，逐条把命令、操作者、时间、输出摘要和验证结果记录到操作记录中；必须先验证反向回滚可执行。
3. 只有在正向命令、反向命令和回滚验证都已记录并确认可用后，才可停止 8123，按服务负责人提供的流程串行加载 base。
4. 串行切换后先查已认证的 `/health`，再做同一只股票的单次预检；身份或显存不合格就立即执行已验证的反向命令。
5. base 评估结束后执行已验证的反向命令，确认 8123 恢复 `Kronos-small`，再关闭临时进程和归档日志。

如果服务负责人无法及时提供环境专用的正向/反向命令，或无法在停产前验证回滚，则停止 base 评估，保持 8123 上的生产 small 继续运行。**本仓库不供应、也不应推断任何替代切换命令。**

**安全底线：永远不要在 rollback 尚未准备好之前停止生产服务。** 任何切换失败都标记为 `unavailable`/`model_error`，不能当作预测准确率为零，也不能自动 fallback。

## 3. 正式实验 CLI

### 3.1 Prepare：一次性冻结输入

正式实验要求由操作者提供的 universe 规范化后恰好 20 只股票；仓库不内置或假定某个 `evaluation_universe_20.csv`。不要使用 `--allow-smoke`。准备阶段会冻结历史窗口、未来真实行情、参数、代码版本和输入指纹。

下面的 `UNIVERSE_FILE` 必须替换为操作者实际准备的**绝对路径**。先做存在性预检；文件不存在时不得启动实验：

```bash
cd /path/to/stock_research
UNIVERSE_FILE=/absolute/path/to/operator-supplied/evaluation_universe_20.csv
test -f "$UNIVERSE_FILE" || { echo "universe file does not exist: $UNIVERSE_FILE" >&2; exit 1; }
rtk python3 scripts/run_kronos_rolling_evaluation.py prepare \
  --universe-file "$UNIVERSE_FILE" \
  --start-date 2025-01-02 \
  --end-date 2025-01-31 \
  --output-dir outputs/research/kronos_rolling_eval/2025-01
```

以上是本地研究仓库命令，`UNIVERSE_FILE` 由操作者负责提供并核对为 20 只股票；它不是本仓库已经存在的配置文件。

### 3.2 Predict：相同快照分别运行两个模型

先跑 small：

```bash
cd /path/to/stock_research
rtk python3 scripts/run_kronos_rolling_evaluation.py predict \
  --model small \
  --output-dir outputs/research/kronos_rolling_eval/2025-01 \
  --predict-url http://192.168.3.187:8123
```

完成 base 的 `/health` 预检和显存检查后，再跑 base：

```bash
cd /path/to/stock_research
rtk python3 scripts/run_kronos_rolling_evaluation.py predict \
  --model base \
  --output-dir outputs/research/kronos_rolling_eval/2025-01 \
  --predict-url http://192.168.3.187:8124
```

若采用串行切换，base 命令的 URL 使用已确认恢复运行的 8123。两个阶段必须指向同一个 `output-dir`，不得重新 prepare；CLI 会先做模型身份检查，拒绝 mismatch，不读取 dashboard 数据。

### 3.3 Report：只从实验目录生成报告

```bash
cd /path/to/stock_research
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
| `insufficient_truth` | 当前 data builder 会把整个 snapshot 标为 `insufficient_truth`；该 snapshot 在所有 horizon 上都排除出评分和基线。补齐完整未来真实行情后，必须重新 `prepare`，才能重新纳入评估。 |
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
