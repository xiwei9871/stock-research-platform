# P1 Report Delivery Adapter Plan

## 一、目标

P1-1 `Report Delivery Adapter` 的目标，是把 P0 阶段已经能够稳定生成的研究产物，统一交付到日常使用入口，形成一条“生成 -> 索引 -> 渲染 -> 投递 -> 记录”的交付链路。

第一阶段覆盖的交付对象包括：

- Markdown
- JSON
- CSV
- OpenClaw
- 飞书

第一阶段明确不做：

- 复杂 Web 前端
- 自动交易
- AI Agent 决策

更准确地说，P1-1 不是“再造一套报告系统”，而是把已经存在于 P0 的报告、run_card、evidence bundle、watchlist 产物，统一抽象成一层可交付、可索引、可记录的 adapter。

---

## 二、要交付的报告类型

P1-1 第一阶段至少覆盖以下报告类型：

### 1. 每日市场状态报告

- 市场状态
- 行业/主线状态
- 风险提示
- 当日研究摘要

### 2. 每日 TopN 选股报告

- 当日 TopN 名单
- 分数
- Universe / score version / evidence
- 相关 run_card 摘要

### 3. Watchlist 盯盘报告

- 今日 watchlist 信号
- 风险标签
- 优先级
- explain / notes / reason summary

### 4. 风险预警报告

- 流动性 / 停牌 / 破位 / 过热等风险
- 适合作为即时提醒或收盘提醒

### 5. 因子评估报告

- 因子 gate / eval 结果
- 多 horizon 摘要
- 因子审批结论
- evidence bundle 摘要

### 6. 回测 run_card / evidence bundle 摘要

- TopN / retention / portfolio 回测 run_card
- 关键参数
- 关键指标
- 产物路径

### 7. 每周复盘报告

- 周度市场状态总结
- 本周 TopN / watchlist / 风险 / 因子表现摘要
- 下周继续观察项

---

## 三、现有输入来源

P1-1 应基于当前仓库中已经真实存在的模块与产物输入，不新造一套平行数据流。

### 主研究/日报入口

- [src/stock_research/daily_pipeline.py](/Users/xiwei/stock_research/src/stock_research/daily_pipeline.py)
- [src/stock_research/reports/daily_research_report_cli.py](/Users/xiwei/stock_research/src/stock_research/reports/daily_research_report_cli.py)
- [src/stock_research/research_workflow_cli.py](/Users/xiwei/stock_research/src/stock_research/research_workflow_cli.py)

### 选股 / TopN / selection

- [src/stock_research/factor_store.py](/Users/xiwei/stock_research/src/stock_research/factor_store.py)
- `selection.py`
- Top score / selection 相关 CLI 输出

### Watchlist

- [src/stock_research/watchlist/workflow.py](/Users/xiwei/stock_research/src/stock_research/watchlist/workflow.py)
- [src/stock_research/watchlist/signals.py](/Users/xiwei/stock_research/src/stock_research/watchlist/signals.py)
- [src/stock_research/watchlist/risk.py](/Users/xiwei/stock_research/src/stock_research/watchlist/risk.py)
- [src/stock_research/reports/watchlist_report.py](/Users/xiwei/stock_research/src/stock_research/reports/watchlist_report.py)

### 因子评估

- `factor_eval_batch.py`
- [src/stock_research/factor_eval_batch_cli.py](/Users/xiwei/stock_research/src/stock_research/factor_eval_batch_cli.py)
- [src/stock_research/factor_eval_store.py](/Users/xiwei/stock_research/src/stock_research/factor_eval_store.py)

### 回测与约束

- [src/stock_research/vectorized_topn_backtest.py](/Users/xiwei/stock_research/src/stock_research/vectorized_topn_backtest.py)
- [src/stock_research/retention_backtest.py](/Users/xiwei/stock_research/src/stock_research/retention_backtest.py)
- `portfolio_backtest.py`

### Evidence / run_card

- [src/stock_research/run_card.py](/Users/xiwei/stock_research/src/stock_research/run_card.py)
- `report_run_store.py`
- `daily_research_report_cli.py`

### 现有 CLI 与调度边界

- [src/stock_research/cli.py](/Users/xiwei/stock_research/src/stock_research/cli.py)
- 当前 watchdog / cron / CLI 入口

---

## 四、Adapter 分层设计

P1-1 建议按以下四层抽象，不让“报告渲染逻辑”和“渠道发送逻辑”混在一起。

### 1. `ReportArtifact`

统一抽象一份可交付报告：

- `title`
- `report_type`
- `date`
- `markdown_path`
- `json_path`
- `csv_paths`
- `run_card_path`
- `warnings`
- `severity`
- `summary`

设计原则：

- `ReportArtifact` 只描述“这份报告是什么、有哪些产物、严重程度如何”
- 不负责发送
- 不负责外部渠道格式

### 2. `DeliveryChannel`

统一抽象交付目标：

- `local`
- `feishu`
- `openclaw`
- `future_web`

设计原则：

- 渠道枚举要稳定
- 第一阶段只实际实现 `local`
- `feishu` / `openclaw` 先定义 adapter 接口

### 3. `DeliveryAdapter`

负责：

- `render`
- `validate`
- `send`
- `record delivery result`

设计原则：

- 一个 adapter 不直接依赖业务逻辑模块，只消费 `ReportArtifact`
- 所有发送前先做 artifact 校验
- dry-run 应该是一等能力，而不是临时 flag

### 4. `DeliveryLog`

统一记录一次交付结果：

- `delivery_id`
- `report_type`
- `channel`
- `status`
- `sent_at`
- `error_message`
- `artifact_paths`

设计原则：

- 先本地落地
- 先保证可追踪
- 不急于先建数据库表

---

## 五、P1-1 实施阶段

### Phase 1：Local Delivery Adapter

- 统一把报告复制/索引到 `outputs/reports/daily/`
- 生成 `manifest.json`
- 不接外部服务

目标：

- 先把“交付前的本地产物标准化”做好
- 让所有报告有统一入口，而不是 scattered files

### Phase 2：OpenClaw Skill Adapter

- 输出 OpenClaw 可消费 JSON
- 暂不直接调用 OpenClaw
- 先定义接口

目标：

- 先把结构定下来
- 不让 P1-1 被外部执行环境耦死

### Phase 3：飞书 Adapter

- 支持 webhook 或机器人消息
- 先 dry-run
- 不硬编码 token
- token 走环境变量

目标：

- 先保证消息体结构和渠道抽象正确
- 不在第一阶段接真实服务依赖

### Phase 4：Delivery Log

- 记录每次报告是否成功发送
- 本地 JSONL 或数据库表二选一
- 第一阶段先用 JSONL

目标：

- 给交付链增加审计能力
- 和 `run_card / evidence trail` 保持一致的可追踪思路

### Phase 5：Report Schedule

- 每日收盘后报告
- 每周复盘报告
- watchlist 风险即时提醒预留

目标：

- 先明确 schedule 边界
- 不在 P1-1 直接做复杂调度系统

---

## 六、禁止事项

P1-1 明确禁止：

- 不自动下单
- 不发未经审核的买卖建议
- 不硬编码 webhook / token
- 不把 AI 推理伪装成事实
- 不访问真实外部服务，除非显式 dry-run 关闭
- 不做复杂 Web

更高层原则：

- P1-1 是“交付 adapter”，不是“自动投研决策层”
- 所有发出的结论都应来自现有 artifacts / evidence，而不是凭空生成

---

## 七、P1-1 最小开发任务清单

### 1. 统一 `ReportArtifact` 数据结构

- 目标
  给现有报告产物统一 metadata 容器
- 建议文件
  - `src/stock_research/report_delivery/artifact.py`
- 测试文件
  - `tests/test_report_delivery_artifact.py`
- CLI
  - 无
- 输出产物
  - Python dataclass / schema
- 是否需要真实外部服务
  - 否

### 2. 本地 manifest builder

- 目标
  从 `ReportArtifact` 生成 `manifest.json`
- 建议文件
  - `src/stock_research/report_delivery/manifest.py`
- 测试文件
  - `tests/test_report_delivery_manifest.py`
- CLI
  - 无
- 输出产物
  - `manifest.json`
- 是否需要真实外部服务
  - 否

### 3. Local Delivery Adapter

- 目标
  把报告复制/索引到统一本地目录
- 建议文件
  - `src/stock_research/report_delivery/local_adapter.py`
- 测试文件
  - `tests/test_report_delivery_local_adapter.py`
- CLI
  - 可选 `report-delivery-local`
- 输出产物
  - 统一目录下的 md/json/csv/run_card 索引
- 是否需要真实外部服务
  - 否

### 4. Daily report artifact adapter

- 目标
  把日报现有输出包装成 `ReportArtifact`
- 建议文件
  - `src/stock_research/report_delivery/adapters/daily_report_adapter.py`
- 测试文件
  - `tests/test_daily_report_delivery_adapter.py`
- CLI
  - 复用现有日报 CLI
- 输出产物
  - daily `ReportArtifact`
- 是否需要真实外部服务
  - 否

### 5. Watchlist report artifact adapter

- 目标
  把 watchlist report 工作流包装成统一 artifact
- 建议文件
  - `src/stock_research/report_delivery/adapters/watchlist_adapter.py`
- 测试文件
  - `tests/test_watchlist_report_delivery_adapter.py`
- CLI
  - 复用 watchlist CLI
- 输出产物
  - watchlist `ReportArtifact`
- 是否需要真实外部服务
  - 否

### 6. TopN report artifact adapter

- 目标
  包装 TopN / selection 结果
- 建议文件
  - `src/stock_research/report_delivery/adapters/topn_adapter.py`
- 测试文件
  - `tests/test_topn_report_delivery_adapter.py`
- CLI
  - 可选 `topn-delivery-preview`
- 输出产物
  - TopN `ReportArtifact`
- 是否需要真实外部服务
  - 否

### 7. Factor eval artifact adapter

- 目标
  包装 factor eval / gate / approval 结果
- 建议文件
  - `src/stock_research/report_delivery/adapters/factor_eval_adapter.py`
- 测试文件
  - `tests/test_factor_eval_delivery_adapter.py`
- CLI
  - 复用 factor eval CLI
- 输出产物
  - factor eval `ReportArtifact`
- 是否需要真实外部服务
  - 否

### 8. OpenClaw delivery payload renderer

- 目标
  输出 OpenClaw 可消费 JSON，不直接发送
- 建议文件
  - `src/stock_research/report_delivery/openclaw_adapter.py`
- 测试文件
  - `tests/test_report_delivery_openclaw_adapter.py`
- CLI
  - `report-delivery-openclaw-preview`
- 输出产物
  - OpenClaw payload JSON
- 是否需要真实外部服务
  - 否

### 9. Feishu delivery dry-run adapter

- 目标
  构造飞书消息体并支持 dry-run
- 建议文件
  - `src/stock_research/report_delivery/feishu_adapter.py`
- 测试文件
  - `tests/test_report_delivery_feishu_adapter.py`
- CLI
  - `report-delivery-feishu --dry-run`
- 输出产物
  - Feishu message preview JSON / text
- 是否需要真实外部服务
  - 否，第一阶段 dry-run only

### 10. Delivery log writer

- 目标
  记录每次交付结果到 JSONL
- 建议文件
  - `src/stock_research/report_delivery/log.py`
- 测试文件
  - `tests/test_report_delivery_log.py`
- CLI
  - 复用 delivery CLI
- 输出产物
  - `delivery_log.jsonl`
- 是否需要真实外部服务
  - 否

---

## 八、推荐第一个开发任务

最推荐的第一个开发任务是：

> **Local Delivery Adapter**

原因：

- 不依赖飞书 / OpenClaw
- 不依赖外部服务
- 可以先统一本地产物目录、manifest、artifact index
- 后续 `feishu` / `openclaw` / `future_web` 都可以站在这层之上扩展
- 能先把“报告是什么、有哪些文件、如何索引”这件事稳定下来

你的判断是对的：

> **先做 `P0 scoped review + 分主题提交` 是对的；现在进入 P1 后，最稳的起点就是 `Local Delivery Adapter`。**

---

## 实施进展补充（2026-05-20）

- `Local Delivery Adapter` 已开始实现，当前基线已落在 `report_delivery.py` 与 CLI `report-delivery-local`。
- 本地输出目录约定为 `OUTPUT_DIR/manifest.json`、`OUTPUT_DIR/delivery_log.jsonl`（非 dry-run）以及 `OUTPUT_DIR/artifacts/` 下的按 `artifact_id` 分组副本。
- `manifest.json` 当前包含：`generated_at`、`trade_date`、`channel`、`artifact_count`、`report_types`、`requires_attention_count`、`high_severity_count`、`artifacts`、`warnings`、`errors`。其中 `artifacts` 记录 `artifact_id`、`report_type`、`title`、`trade_date`、`generated_at`、`markdown_path`、`json_path`、`csv_paths`、`run_card_path`、`evidence_dir`、`warnings`、`severity`、`summary`、`tags`、`recommended_channels`、`requires_attention`、`delivery_priority`、`metadata`。
- `delivery_log.jsonl` 当前每条记录包含：`delivery_id`、`generated_at`、`channel`、`status`、`trade_date`、`artifact_count`、`manifest_path`、`error_message`。
- CLI 示例：`.venv/bin/stock-research report-delivery-local --trade-date 2026-05-20 --input-dir outputs/reports/daily --output-dir outputs/report_delivery/2026-05-20 --no-dry-run`

## Artifact Classification

当前 local adapter 的分类规则保持单一来源，后续 OpenClaw / Feishu adapter 直接复用这些字段即可，不再重复推断。

- `report_type` 支持：`run_card_bundle`、`risk_alert_report`、`must_watch_report`、`watchlist_signal_report`、`watchlist_report`、`factor_eval_report`、`daily_topn_report`、`daily_market_report`、`backtest_report`、`generic_report`
- `severity` 规则：非 `risk_alert_report` 默认 `info`；`risk_alert_report` 从 markdown / JSON 中提取 `critical`、`high`、`medium`、`low`、`info`，取最高级别
- `summary` 提取规则：优先 JSON 摘要，其次 markdown 摘要，再回退到文件名；`daily_topn_report` 和 `run_card_bundle` 允许更专门的摘要逻辑
- `recommended_channels` 规则：`run_card_bundle` 和 `daily_topn_report` 为 `["local", "openclaw"]`，其余当前默认 `["local"]`
- `requires_attention` 规则：若 artifact 原本标记为 `requires_attention`，或 `severity` 为 `high` / `critical`，则为真
- `delivery_priority` 映射：当前实现以较小数字表示更高优先级；默认值 `10`，后续可按渠道和报告类型细化
- 与未来 adapter 的关系：OpenClaw / Feishu 只负责把已分类的 `ReportArtifact` 映射成各自 payload；它们不应重新定义 severity 或 attention 语义，只消费 manifest 中的结果字段

## OpenClaw Export Adapter

- 第一阶段只做 export-only，不直接发送到 OpenClaw
- 输入使用本地 `manifest.json`，由 CLI 显式传入
- 输出固定为 `openclaw_manifest.json`、`openclaw_items.jsonl`、`openclaw_delivery_log.jsonl`
- `recommended_action` 由 `report_type` 决定，`run_card_bundle` / `daily_topn_report` / `watchlist_report` / `must_watch_report` / `risk_alert_report` / `factor_eval_report` / `backtest_report` 各自映射到稳定动作，其余回退到 `review_report`
- `openclaw_route` 由 `requires_attention` 和 `report_type` 决定，注意力优先路由到 `research_alert`
- CLI 示例：`.venv/bin/stock-research report-delivery-openclaw-export --trade-date 2026-05-20 --manifest outputs/delivery/2026-05-20/manifest.json --output-dir outputs/report_delivery/openclaw/2026-05-20 --include-all --min-severity medium`
- `--dry-run` 只影响结果状态和 manifest/log 记录，不阻止本地文件写出
- 后续 live sender 要单独拆成另一个 adapter，不复用 export-only 命令的发送职责

## OpenClaw Sender v0

- 和 `OpenClaw Export Adapter` 的关系：`report-delivery-openclaw-export` 负责把本地 manifest 转成 `openclaw_manifest.json` / `openclaw_items.jsonl`，`report-delivery-openclaw-send` 负责读取这两个文件并把 payload 送出；两者是前后串联的两步，不是同一个职责
- 默认行为：`report-delivery-openclaw-send` 默认 `--dry-run`，真实发送必须显式加 `--no-dry-run`
- `send_preview.json`：dry-run 和 real-send 都要写预览文件，预览内容必须可复查，但不能包含 token
- `send_log.jsonl`：记录一次发送的摘要结果，至少包含 `send_id`、`status`、`dry_run`、`item_count`、`sent_count`、`failed_count`、`skipped_count`、`preview_path`、`endpoint_host`
- 环境变量：当前支持 `OPENCLAW_ENDPOINT`、`OPENCLAW_TOKEN`、`OPENCLAW_TIMEOUT_SECONDS`；`OPENCLAW_TOKEN` 仅走环境变量，不提供 CLI 覆盖参数，`OPENCLAW_ENDPOINT` 和 `OPENCLAW_TIMEOUT_SECONDS` 仍可通过 CLI 显式指定
- CLI 示例：

```bash
.venv/bin/stock-research report-delivery-openclaw-send \
  --trade-date 2026-05-20 \
  --manifest outputs/report_delivery/openclaw/2026-05-20/openclaw_manifest.json \
  --items outputs/report_delivery/openclaw/2026-05-20/openclaw_items.jsonl \
  --output-dir outputs/report_delivery/openclaw_send/2026-05-20 \
  --dry-run
```

- 真实发送安全条件：`--no-dry-run` 时必须提供 `--endpoint`，并且同时满足 `--allow-live-send`、`--limit 1`、非空 `--route-allowlist`、`--severity-max` 在 smoke-test envelope 内、`--test-mode`
- token 安全：token 不得打印到 stdout，不得写入 `send_preview.json`，不得写入 `send_log.jsonl`
- 和未来 Feishu adapter 的关系：`OpenClaw Sender v0` 先把渠道发送边界和安全策略定住，后续 Feishu adapter 只需要沿用同一套 dry-run / logging / safety gate 约定，不需要重写发送框架
