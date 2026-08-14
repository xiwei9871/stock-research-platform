# Kronos Rolling Evaluation Runbook

版本：2026-08-14

范围：研究评估、模型预检、结果验收。**不改线上个股工作台、不写生产预测缓存、不触发交易。**

## 1. 187 当前事实

| 项目 | 当前值 |
|---|---|
| Kronos 服务目录 | `/home/mqkj/kronos` |
| 生产端口 | `8123` |
| 生产模型 | `Kronos-small` |
| base 权重 | 已安装，可做预检/评估 |

生产服务当前只加载一个模型。small/base 对比必须使用同一批冻结输入快照；不能让两个模型分别重新查询实时数据库。

本 runbook 不记录密码、令牌、认证头、私钥或其他凭据。预测命令所需认证信息必须从**运行研究 CLI 的主机**上的安全环境配置读取；仅在 187 上配置令牌而未在 CLI 主机加载并不能工作。令牌禁止写入命令行、日志和实验报告。

## 0. 执行位置与命令约定

- 标注为“本地研究 CLI 主机”的命令在运行研究代码的机器执行；先进入 `/path/to/stock_research`，并使用本地 `rtk` wrapper（例如 `rtk python3`、`rtk pytest`）。从该主机访问 187 上的 Kronos 服务时，8124 的地址是 `http://192.168.3.187:8124`，8123 同理使用 `http://192.168.3.187:8123`。`/path/to/stock_research` 是占位路径，执行前替换为实际绝对路径。
- 如果研究 CLI 本身运行在 187 上，`http://127.0.0.1:8124` 等价于 `http://192.168.3.187:8124`；无论 CLI 在哪里运行，令牌环境变量都必须安全存在于**运行 CLI 的那台主机**，不能只存在于 187 的服务进程环境中。
- 标注为“187 远程 shell”的命令在 187 上执行，使用普通 shell 命令，不加 `rtk` 前缀。`rtk` 不是 187 的前置条件，也不要把本地 wrapper 前缀复制到远程命令中。
- 本 runbook 不提供 SSH 登录命令、密码或令牌值。187 远程 shell 命令假定操作者已经进入 187，并且服务端环境已按现有部署方式加载；研究 CLI 命令另外要求 CLI 主机自身安全加载所需令牌环境变量。

## 2. Base 安全预检与模型切换

### 2.1 固定执行顺序

严格按以下顺序执行，不能跳步：

1. 在运行研究代码的 CLI 主机执行 2.2 的认证生产预检。命令必须成功，并输出规范化身份 `Kronos-small`；如果服务不可用、令牌未加载或身份不匹配，立即停止，**不得启动任何 8124 进程**。
2. 只有 2.2 成功后，才在 187 的独立终端/会话执行 2.3，启动 8124；不得占用或停止 8123。
3. 8124 启动后，执行 2.4 的认证 base health/identity 检查；通过后才可执行单股票预检和正式评估。
4. `/health` 返回的模型身份必须与请求模型完全一致。身份不一致时停止，不能 fallback 到当前活动模型。
5. 只有确认 GPU 显存足够、回滚动作已准备好，才允许考虑串行切换；正式评估前至少做一次单股票、单截止日预测，并记录 `sample_count=20`、输出时间戳完整性、GPU 显存和端到端延迟。

### 2.2 启动 8124 前认证检查生产 Kronos-small

**在执行任何启动 8124 的命令之前**，先在运行研究代码的 CLI 主机执行以下探针。它只访问 `192.168.3.187:8123`，使用仓库现有的 `KronosClient` 和 `assert_model()`；失败时以非零状态退出，不会打印异常详情或令牌，也不得继续执行 2.3。

```bash
cd /path/to/stock_research
rtk python3 - <<'PY'
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path("src").resolve()))
from stock_research.kronos_evaluation_client import KronosClient, KronosClientError

url = "http://192.168.3.187:8123"
expected_model = "small"  # KronosClient 的规范化身份，对外标记为 Kronos-small
try:
    token = os.environ["KRONOS_INTERNAL_TOKEN"]
except KeyError:
    raise SystemExit(
        "STOP: KRONOS_INTERNAL_TOKEN is not loaded in the CLI host environment."
    ) from None

try:
    with KronosClient(url, token=token, timeout=30) as client:
        health = client.assert_model(expected_model)
except KronosClientError:
    raise SystemExit(
        "STOP: authenticated 8123 health/model preflight failed; do not start 8124."
    ) from None

if health.get("model") != expected_model:
    raise SystemExit(
        "STOP: 8123 normalized identity is not Kronos-small; do not start 8124."
    )

print(f"{url} status=ok normalized_model=Kronos-small")
PY
```

如果 CLI 主机的安全环境尚未加载 `KRONOS_INTERNAL_TOKEN`，先按现有凭据管理流程加载；令牌只存在于安全环境变量中，不要手工填写、回显、写入日志或通过进程参数传递令牌值。

### 2.3 在 8124 启动 Kronos-base

仅在 2.2 成功后，在 187 的独立终端/会话执行以下命令，不要占用或停止 8123：

```bash
cd /home/mqkj/kronos
KRONOS_MODEL_NAME=Kronos-base \
/home/mqkj/miniconda3/envs/kronos/bin/python -m uvicorn service.app:app \
  --host 0.0.0.0 --port 8124
```

### 2.4 启动后认证检查 8124 的 Kronos-base

8124 启动后，从研究 CLI 主机执行以下认证检查。它是启动后的第二道门：只接受规范化身份 `base`（对外标记为 `Kronos-base`）；失败或 mismatch 时停止后续评估，不得 fallback：

```bash
cd /path/to/stock_research
rtk python3 - <<'PY'
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path("src").resolve()))
from stock_research.kronos_evaluation_client import KronosClient, KronosClientError

url = "http://192.168.3.187:8124"
expected_model = "base"  # KronosClient 的规范化身份，对外标记为 Kronos-base
try:
    token = os.environ["KRONOS_INTERNAL_TOKEN"]
except KeyError:
    raise SystemExit(
        "STOP: KRONOS_INTERNAL_TOKEN is not loaded in the CLI host environment."
    ) from None

try:
    with KronosClient(url, token=token, timeout=30) as client:
        health = client.assert_model(expected_model)
except KronosClientError:
    raise SystemExit(
        "STOP: authenticated 8124 health/model preflight failed; stop evaluation."
    ) from None

if health.get("model") != expected_model:
    raise SystemExit(
        "STOP: 8124 normalized identity is not Kronos-base; stop evaluation."
    )

print(f"{url} status=ok normalized_model=Kronos-base")
PY
```

人工核对：

- 8123 的 `model` 是 `Kronos-small`；
- 8124 的 `model` 是 `Kronos-base`；
- 8123 的预检在启动 8124 之前已成功，且没有把一个模型的健康响应当成另一个模型使用；
- 服务状态、模型身份和权重身份均写入本次操作记录。

### 2.5 单股票预测、显存和延迟

用一个临时的单股票输入目录做预检；`--allow-smoke` 只允许用于此类预检，不可用于正式 20 股票结论。以下是本地研究 CLI 主机命令，可按实际日期替换占位路径和日期；该示例访问 187 上的 8124，不是 CLI 主机的 loopback 地址：

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
  --predict-url http://192.168.3.187:8124 \
  --token-env KRONOS_INTERNAL_TOKEN
```

如果这组 CLI 命令实际在 187 上执行，`--predict-url http://127.0.0.1:8124` 等价；此时 `KRONOS_INTERNAL_TOKEN` 仍必须安全存在于运行该 CLI 的 187 环境中。研究 CLI 在其他主机上运行时，必须使用 `http://192.168.3.187:8124`，并在该 CLI 主机加载令牌环境变量。

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

### 2.6 GPU 显存不足时的串行切换

本仓库没有经过验证的 Kronos service-switch 脚本或 systemd unit，也不提供任何精确的切换命令。串行切换是硬前置条件，不是可以临时发挥的操作步骤。如果 8124 无法加载 base 或出现 CUDA OOM，只有在满足下面的前置条件后才能考虑串行切换：

1. 在停止 8123 **之前**，从 187 服务负责人取得当前环境专用、已批准的正向命令（small → base）和反向命令（base → small）。同时取得进程/日志位置、health 验证步骤和失败处置方式。
2. 在不影响生产的条件下对正向/反向流程做 dry-run 或等价的安全演练，逐条把命令、操作者、时间、输出摘要和验证结果记录到操作记录中；必须先验证反向回滚可执行。
3. 只有在正向命令、反向命令和回滚验证都已记录并确认可用后，才可停止 8123，按服务负责人提供的流程串行加载 base。
4. 串行切换后先查已认证的 `/health`，再做同一只股票的单次预检；身份或显存不合格就立即执行已验证的反向命令。
5. base 评估结束后执行已验证的反向命令，确认 8123 恢复 `Kronos-small`，再关闭临时进程和归档日志。

如果服务负责人无法及时提供环境专用的正向/反向命令，或无法在停产前验证回滚，则停止 base 评估，保持 8123 上的生产 small 继续运行。**本仓库不供应、也不应推断任何替代切换命令。**

**安全底线：永远不要在 rollback 尚未准备好之前停止生产服务。** 任何切换失败都标记为 `unavailable`/`model_error`，不能当作预测准确率为零，也不能自动 fallback。

## 3. 配置驱动实验（推荐入口）

新的可复用入口是：

```text
scripts/run_kronos_experiment.py --config configs/<experiment>.json --stage <stage>
```

它把配置加载、股票池冻结、交易日滚动快照、单模型预测、指标和报告串成一个固定流程。首份配置是
`configs/kronos_2026_07_small_rolling.json`，对应输出目录：

```text
outputs/research/kronos_rolling_eval/2026-07-small-rolling/
```

本轮配置驱动实验使用日线（`frequency=1d`）、qfq 和一个已注册模型；入口不连接 dashboard，不写个股工作台或生产预测缓存。

### 3.1 JSON schema 和关键参数

配置必须是 `schema_version=1` 的 JSON 对象，不能增加未定义字段。当前配置结构如下：

| JSON 路径 | 当前实验值 | 作用 |
|---|---:|---|
| `experiment_id` | `2026-07-small-rolling` | 输出目录名和冻结实验身份；新实验必须使用新值。 |
| `model.name` | `small` | 只能是 `small` 或 `base`，一次只运行一个模型。 |
| `model.fallback` | `false` | 必须为 `false`；服务身份不匹配时失败，不自动换模型。 |
| `model.seed` | `20260806` | 模型采样随机种子。 |
| `model.sample_count` | `20` | 每个 origin 的采样路径数，不是股票数量。 |
| `data.frequency` | `1d` | 预测频率，当前只允许日 K。 |
| `data.adjust_type` | `qfq` | 复权口径。 |
| `data.input_window` | `250` | 每个 origin 使用此前真实日 K 的根数。 |
| `data.start_date` | `2026-07-01` | 滚动预测起点。 |
| `data.end_date` | `latest_available` | `prepare` 时解析为数据库实际最新交易日并冻结。 |
| `universe.mode` | `random` | `random` 使用候选池随机抽样；也支持 `explicit`。 |
| `universe.count` | `20` | 股票数；随机模式必须配合 `universe.seed`。 |
| `universe.seed` | `20260808` | 随机股票池复现种子。 |
| `universe.market` | `CN_A` | 候选市场。 |
| `universe.asset_ids` | `null` | random 必须为空；explicit 时填固定股票列表且数量相等。 |
| `prediction.forecast_horizon` | `10` | 每个 origin 预测未来 10 根日 K。 |
| `prediction.report_horizons` | `[1,3,5,10]` | 保留并报告的 horizon。 |
| `prediction.include_latest_forecast` | `true` | 是否把最新 origin 作为待验证预测层保留。 |
| `evaluation.primary_horizon` | `1` | 主准确率 horizon；本实验只以 h=1 做主结论。 |
| `evaluation.baseline` | `persistence` | 与“下一日收盘等于 origin 收盘”基准比较。 |

加载器会校验字段类型、日期、范围、组合关系和配置 fingerprint。`primary_horizon` 必须出现在
`report_horizons` 中且不超过 `forecast_horizon`；`sample_count` 为 1–100，当前实验固定 20。

### 3.2 股票池和滚动窗口

- random 模式在 `prepare` 阶段一次性冻结候选池和最终 20 只股票，记录筛选条件、seed、候选池/最终股票池 fingerprint；不会随 origin 改变。
- 候选池按 `CN_A`、已上市/可交易、排除 ST/退市等规则筛选，并要求起始日前有足够的 250 根 qfq 日 K。
- 每个 origin 按交易日逐日滚动；输入只使用该时点以前的真实 bars，绝不把上一个 origin 的预测写回下一次输入。
- `latest_available` 在 `prepare` 时解析并写入 sidecar/实验元数据，不能用当前自然日冒充行情截止日；未来 horizon 时间戳来自交易日历。
- `20` 股票和 `20` 采样路径是两个独立参数：前者是 `universe.count`，后者是 `model.sample_count`。

### 3.3 small/base 切换和无 fallback 约束

切换逻辑模型只改 JSON 的 `model.name`，例如：

```json
"model": {
  "name": "base",
  "fallback": false,
  "seed": 20260806,
  "sample_count": 20
}
```

然后为新的冻结结果使用新的 `experiment_id`，再执行同一入口。运行时会先调用服务 `/health`，并要求实际
model identity 与配置完全一致；`fallback=true`、多模型配置、身份 mismatch、非法 OHLC、模型/GPU/网络失败
都必须停止或记录为失败，不能用另一个模型补齐。

当前 `KronosEvaluationConfig` 的默认预测地址是 `http://192.168.3.187:8123`。因此 base 实验除了改 JSON，
还必须先按本 runbook 第 2 节完成 base 服务身份、显存和回滚预检，并确保配置驱动 CLI 访问的地址实际提供
`base`。当前 JSON schema 没有预测 URL 字段，不能把 8124 直接写进 JSON；如果 base 只临时运行在 8124，
不要假设新入口会自动切换端口，也不要通过 fallback 绕过 mismatch。small 是默认安全模型，base 的端口/进程
切换仍属于服务运维动作，不在本 Task 修改代码。

### 3.4 stage 和执行命令

`prepare`、`predict`、`report` 和 `run` 都是合法 stage。首次执行时，完整 `run` 与分阶段流程二选一：

```bash
cd /path/to/stock_research

# 分阶段方式的第一步：只冻结配置、股票池、行情边界和 rolling snapshots；
# 会访问真实 PostgreSQL，不调用 GPU。完成后应使用下面带 --resume 的 predict/report。
rtk python3 scripts/run_kronos_experiment.py \
  --config configs/kronos_2026_07_small_rolling.json \
  --stage prepare

# 首次完整运行：prepare → predict → report。
# 需要 CLI 主机已安全加载 KRONOS_INTERNAL_TOKEN。
rtk python3 scripts/run_kronos_experiment.py \
  --config configs/kronos_2026_07_small_rolling.json \
  --stage run
```

分阶段运行时，已有输出目录会保护性拒绝写入，因此后两个阶段必须显式恢复同一实验：

```bash
rtk python3 scripts/run_kronos_experiment.py \
  --config configs/kronos_2026_07_small_rolling.json \
  --stage predict --resume

rtk python3 scripts/run_kronos_experiment.py \
  --config configs/kronos_2026_07_small_rolling.json \
  --stage report --resume
```

`predict` 只从冻结 snapshots 调用配置模型；`report` 只从冻结目录生成指标、基准、比较表和报告。两者都不
重新查询 live universe 或 dashboard endpoint。

### 3.5 `--resume`、fingerprint 和覆盖保护

- 第一次运行不加 `--resume`；输出目录已存在时，任何会写入 artifacts 的 stage 都会拒绝执行。
- `--resume` 只允许继续同一个 `experiment_id` 且配置 fingerprint 完全相同的实验；fingerprint 不匹配立即失败。
- `prepare`、`predict`、`report`、`run` 在已有目录上都必须带 `--resume`，不能只给 `predict/report` 放行。
- CLI 使用进程生命周期锁和事务式 sidecar 发布，避免并发首次运行或半成品 sidecar 覆盖结果；不要手工删除隐藏
  journal、lock、stage 或 backup 文件。
- 改日期、模型、股票池、输入窗口、预测长度、sample count、report horizons 或 primary horizon 时，先复制 JSON，
  修改参数并换一个新的 `experiment_id`；不要对旧目录使用 `--resume` 试图“改参数续跑”。

### 3.6 输出目录和 sidecar

每次实验独立写入 `outputs/research/kronos_rolling_eval/<experiment_id>/`，主要文件如下：

```text
experiment.json              # runner 冻结的低层配置、股票池和快照元数据
experiment_config.json       # 规范化 JSON、resolved end_date、provenance、config_fingerprint
universe.csv                 # 冻结股票及 position
universe_selection.json      # 候选池、筛选条件、seed、选择顺序和 fingerprint
input_snapshots/             # 每只股票/每个 origin 的真实输入、未来时间戳和 truth 状态
run_manifest.csv             # 每个模型运行单元的状态、身份、延迟和错误原因
forecast_bars.parquet        # 预测 OHLC/路径和 horizon
realized_bars.parquet        # 已存在的真实未来 bars
metrics_by_stock_horizon.csv
metrics_by_model_horizon.csv
model_comparison.csv
latest_forecast.json         # 最新 origin 的预测、realized/pending horizon 和状态
report.md                    # 可读报告
```

`experiment_config.json` 和 `universe_selection.json` 是恢复前必须通过 fingerprint/内容一致性校验的 sidecar；
`latest_forecast.json` 只从冻结 snapshots、manifest 和 forecast artifacts 生成，不回查数据库。所有输出应作为一次
运行的冻结快照归档。

### 3.7 报告状态和评分口径

| 状态 | 含义 | 是否进入准确率 |
|---|---|---|
| `ready` | 预测窗口和完整 truth 可用。 | 是，按已有 horizon 评分。 |
| `partial_truth` | h=1 truth 已有，但 h=3/5/10 等后续 truth 尚未全部到齐。 | h=1 可评分；未到齐的 horizon 标为 pending。 |
| `forecast_only` | 最新 origin 有完整未来交易日历但尚无真实 future bar。 | 否，只展示预测。 |
| `pending_truth` | 指标行级状态，目标 horizon 的真实 bar 尚未到齐。 | 否。 |
| `pending_calendar` | 未来交易日历不足以构造完整预测窗口。 | 否，不能用自然日补齐。 |
| `insufficient_input` | origin 前可用真实历史少于 input window。 | 否。 |
| `insufficient_truth` | h=1 所需真实 truth 不可用，且不满足 partial/forecast-only 条件。 | 否。 |
| `invalid_input` | 重复日期、NaN/无穷或非法 OHLC。 | 否，保留错误原因。 |
| `model_error` / `unavailable` / `timeout` / `transport_error` / `protocol_error` | 模型、服务、GPU、网络或响应契约失败。 | 否，不当作准确率为零。 |

本实验 `primary_horizon=1`：准确率、方向命中率、绝对收益误差和 persistence baseline 只使用 h=1 的已实现
真实值。h=3/5/10 仍保存预测和覆盖/待验证数量，但 `forecast_only`、`pending_truth`、`pending_calendar` 不得
混入准确率或模型比较的分母。报告中的 primary coverage 会同时列出 scored、pending 和 failed 数量。

## 4. 安全测试与聚焦回归（不连接真实 DB/GPU）

以下测试显式指定文件，不依赖裸 `pytest` discovery；Kronos client、数据库选择器和预测调用均通过测试 seam/mock
隔离，适合在不连接真实 PostgreSQL、Kronos 服务或 GPU 的环境执行：

```bash
cd /path/to/stock_research
rtk pytest -q \
  tests/test_kronos_experiment_config.py \
  tests/test_kronos_experiment_universe.py \
  tests/test_kronos_experiment_cli.py \
  tests/test_kronos_evaluation_types.py \
  tests/test_kronos_evaluation_data.py \
  tests/test_kronos_evaluation_client.py \
  tests/test_kronos_evaluation_metrics.py \
  tests/test_kronos_evaluation_runner.py \
  tests/test_kronos_rolling_evaluation_cli.py

rtk git diff --check
```

不要把 `scripts/run_kronos_experiment.py --stage prepare` 当作安全 dry-run：它会访问数据库并冻结实际输出；
不要在没有服务和 token 的环境执行 `--stage predict` 或 `--stage run`。

## 5. Legacy 三阶段 CLI（兼容已有冻结目录）

### 5.1 Prepare：一次性冻结输入

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

### 5.2 Predict：相同快照分别运行两个模型

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

### 5.3 Report：只从实验目录生成报告

```bash
cd /path/to/stock_research
rtk python3 scripts/run_kronos_rolling_evaluation.py report \
  --output-dir outputs/research/kronos_rolling_eval/2025-01
```

### 5.4 冻结快照与 no-dashboard 语义

- `prepare` 之后，`predict` 和 `report` 不重新查询 PostgreSQL 或当前 live universe，也不调用 `/api/assets/...` 或其他 dashboard endpoint；它们读取完整的冻结实验目录，包括 `experiment.json`、`universe.csv`、`input_snapshots/`、`run_manifest.csv`、Parquet 预测/真实产物，以及适用的指标、报告和 recovery/report journal 文件。
- 不把评估结果写入线上个股工作台或生产 Kronos cache。
- small/base 必须复用相同 `snapshot_key` 和 `input_fingerprint`；模型、权重、参数和 seed 单独记录。
- 每次请求的 20 条采样路径不是 20 个股票；报告同时保留代表路径、P10/P50/P90 和真实未来 bars。

## 6. Legacy 产物保存、失败、恢复与续跑

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

## 7. Legacy 验收

### 7.1 代码验收（固定命令）

```bash
rtk pytest -q tests/test_kronos_evaluation_types.py tests/test_kronos_evaluation_data.py tests/test_kronos_evaluation_client.py tests/test_kronos_evaluation_metrics.py tests/test_kronos_evaluation_runner.py tests/test_kronos_rolling_evaluation_cli.py
rtk git diff --check
```

### 7.2 真实实验验收清单

在 small/base 两份 manifest（或同一 manifest 中的两个 model 分组）上确认：

- `snapshot_key` 集合完全相同；
- 每个相同 `snapshot_key` 的 `input_fingerprint` 完全相同；
- manifest 中所有运行单元都有明确状态，状态计数之和等于应运行单元数，没有静默丢行；
- `health_model_identity`、`response_model_identity` 与请求模型一致，没有 mismatch、fallback 或用另一个模型补齐；
- 每个模型的 `sample_count`、seed、输入窗口和 forecast horizon 符合 `experiment.json`；
- `report.md` 有 `h=1/3/5/10` 四个 horizon 的覆盖/指标行，并明确包含 `persistence` 和 `drift` 两个基线；同时在 `metrics_by_model_horizon.csv` 核对两基线行；
- `model_comparison.csv` 有 small/base 的配对比较、样本覆盖和置信区间；
- `latency_ms`、GPU 显存、服务身份和失败原因均可追溯到日志或 manifest。

### 7.3 结果解释边界

- **预测准确性**：看 1/3/5/10 日的收益误差、方向命中、P10–P90 覆盖率和分位数损失，并与 persistence、drift 同时比较；单票或单日不能代表整体能力。
- **模型能力**：small/base 只有在相同快照、相同 seed、相同运行单元下的配对差异才可比较；结论使用 `small_preferred`、`base_preferred`、`no_clear_winner` 或 `not_proven`。
- **延迟与工程成本**：GPU 显存、推理延迟、失败率是独立维度。base 即使某些 accuracy 指标较好，也不能忽略显存/延迟/可用性成本。
- **数据失败**：输入不足、真实行情不足和非法数据不能混入准确率分母；模型/GPU/网络失败不能被当成模型能力差，也不能由另一个模型 fallback 补齐。

**Kronos-base 不因参数更多而预设更好。** 只有在配对指标、区间校准、覆盖率、延迟和失败率共同支持时，才可提出 base 优于 small；一个月滚动窗口仍只是初步证据。
