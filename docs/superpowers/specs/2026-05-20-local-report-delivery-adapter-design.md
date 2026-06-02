# Local Report Delivery Adapter Design

## 1. Goal

为 `stock_research` 增加一层本地报告交付适配器，把 P0 已稳定生成的报告、`run_card`、evidence bundle 统一收集、索引并输出到标准本地目录，供后续 OpenClaw、飞书、Web、AI Agent 复用。

第一阶段只实现：

- 本地 artifact 收集
- `manifest.json` 生成
- `delivery_log.jsonl` 生成
- 本地 CLI
- dry-run 安全模式

第一阶段不实现：

- 飞书发送
- OpenClaw 调用
- Web 前端
- AI Agent 决策
- 自动交易

## 2. Scope

### In Scope

- 新增 Local Delivery Adapter 模块
- 支持混合输入模式：
  - `--input-dir` 路径扫描
  - 显式路径补充输入
- 收集 Markdown / JSON / CSV / `run_card` / evidence bundle
- 生成 `manifest.json`
- 生成 `delivery_log.jsonl`
- 新增本地 CLI 命令
- 增加单元测试和 CLI 测试

### Out of Scope

- 不访问真实外部服务
- 不发送飞书
- 不调用 OpenClaw
- 不改现有报告生成逻辑
- 不改现有 `run_card` / evidence bundle 逻辑
- 不做复杂 Web

## 3. Current State

当前仓库已经能生成多类本地研究产物，但它们分散在不同模块和目录下：

- `daily_pipeline.py`
  - 产出 `report_paths`
  - 产出 `run_card`
- `reports/daily_research_report_cli.py`
  - 产出日报 markdown/csv bundle
  - 产出 `run_card`
- `reports/watchlist_report.py`
  - 产出 markdown/json/csv
- `run_card.py`
  - 稳定产出：
    - `run_card.json`
    - `run_card.md`
    - `metrics.json`
    - `config_snapshot.json`
    - `data_coverage.json`
    - `warnings.md`
    - `evidence/manifest.json`

这些产物目前“能生成”，但还没有统一的本地交付索引层。

## 4. Design Principles

- 只做 adapter，不重写现有报告
- 本地优先：先把产物标准化索引到本地目录
- dry-run 默认安全
- 输入尽量宽松，输出尽量标准化
- 混合输入模式优先，避免被目录结构差异卡住

## 5. Module Location

第一阶段放在：

- `src/stock_research/report_delivery.py`

理由：

- 第一阶段逻辑规模仍小
- 当前仓库已有多个单文件工具模块
- 等 `local / feishu / openclaw / future_web` 明显扩张后，再拆成包更合理

## 6. Core Data Structures

### 6.1 `ReportArtifact`

字段：

- `artifact_id`
- `report_type`
- `title`
- `trade_date`
- `generated_at`
- `markdown_path`
- `json_path`
- `csv_paths`
- `run_card_path`
- `evidence_dir`
- `warnings`
- `severity`
- `summary`
- `metadata`

职责：

- 表示一份可交付研究产物
- 描述“这是什么报告、有哪些文件、风险级别如何”
- 不负责发送

### 6.2 `DeliveryResult`

字段：

- `delivery_id`
- `channel`
- `status`
- `artifact_count`
- `output_dir`
- `manifest_path`
- `delivery_log_path`
- `errors`
- `generated_at`

职责：

- 表示一次本地交付执行的结果
- 可用于 CLI 输出和后续 delivery log 记录

### 6.3 `LocalDeliveryAdapter`

方法：

- `collect_artifacts(...)`
- `build_manifest(...)`
- `deliver_local(...)`
- `write_delivery_log(...)`

职责：

- 聚合输入路径
- 标准化 artifact metadata
- 写入 manifest / log
- 提供 dry-run 与真实本地交付两种执行路径

## 7. Input Model

第一阶段采用混合模式：

### 7.1 路径扫描输入

支持：

- `--input-dir`

从目录中识别：

- `*.md`
- `*.json`
- `*.csv`
- `run_card.json`
- `evidence/manifest.json`

### 7.2 显式补充输入

支持可选显式路径：

- `--report-dir`
- `--run-card-dir`
- `--artifact-path`（可重复）

设计目标：

- 先兼容当前目录结构还未完全统一的现实
- 后续等 report family 更稳定，再逐步收敛到更严格的输入契约

## 8. Output Directory Convention

第一阶段建议输出到：

```text
outputs/report_delivery/YYYY-MM-DD/
  manifest.json
  delivery_log.jsonl
  artifacts/
    ...
```

例子：

```text
outputs/report_delivery/2026-05-20/
  manifest.json
  delivery_log.jsonl
  artifacts/
    daily_topn_2026-05-20_manual_v1.md
    watchlist_report_2026-05-20_core.md
    run_card/
```

### 8.1 `manifest.json`

至少包含：

- `generated_at`
- `trade_date`
- `channel`
- `artifact_count`
- `artifacts`
- `warnings`
- `errors`

### 8.2 `delivery_log.jsonl`

每行至少包含：

- `delivery_id`
- `generated_at`
- `channel`
- `status`
- `trade_date`
- `artifact_count`
- `manifest_path`
- `error_message`

## 9. Artifact Collection Semantics

第一阶段不强行依赖统一业务输出 schema，而是按“文件存在 + 类型可识别”进行标准化。

### 9.1 支持的第一批输入来源

优先支持：

1. `daily_pipeline` 输出目录
2. `run_card` / evidence bundle 目录
3. `daily_research_report_cli` 输出目录
4. selection / TopN 输出目录
5. watchlist report 输出目录

### 9.2 `report_type` 分类建议

第一阶段可按文件名 / 目录名推断：

- `daily_research`
- `topn`
- `watchlist`
- `risk_alerts`
- `market_state`
- `sector_strength`
- `position_review`
- `run_card`
- `evidence_bundle`
- `unknown`

如果无法准确判断：

- 保留 `artifact_type = "unknown"`
- 不报错
- 在 manifest 中记录 warning

## 10. Local Delivery Behavior

### 10.1 Dry-run

默认 `--dry-run`。

dry-run 行为：

- 不复制文件
- 不写 `delivery_log.jsonl`
- 可写预览 manifest 到临时或目标目录
- CLI 输出摘要：
  - artifact count
  - warnings
  - output dir

### 10.2 Non dry-run

非 dry-run 行为：

- 生成 `manifest.json`
- 生成 `delivery_log.jsonl`
- 可将 artifact 复制或建立标准索引到 `artifacts/`
- 不访问任何外部服务

第一阶段允许选择“复制文件”或“只记录原始路径 + 建 manifest 索引”，但建议先实现复制到本地交付目录，便于形成稳定交付快照。

## 11. CLI Design

新增命令建议：

```bash
stock-research report-delivery-local \
  --trade-date 2026-05-20 \
  --input-dir outputs/reports \
  --output-dir outputs/report_delivery/2026-05-20 \
  --dry-run
```

建议参数：

- `--trade-date` 必填
- `--input-dir`
- `--report-dir`
- `--run-card-dir`
- `--artifact-path` 可重复
- `--output-dir`
- `--dry-run`

CLI 约束：

- 默认 dry-run
- 不访问外部服务
- 不需要 token
- 不触发飞书
- 不触发 OpenClaw

## 12. Validation Rules

第一阶段验证包括：

- 输入路径存在性
- 支持文件类型识别
- manifest 可 JSON 序列化
- `artifact_count` 与实际收集结果一致

路径不存在时：

- 不崩溃
- 返回明确错误或 warning

空目录时：

- 不崩溃
- `artifact_count = 0`
- manifest 中记录 warning

## 13. Testing Strategy

新增：

- `tests/test_report_delivery.py`

至少覆盖：

1. 可以从 fake report 目录收集 markdown/json/csv artifact
2. 可以识别 `run_card` / evidence bundle
3. 可以生成 `manifest.json`
4. 可以生成 `delivery_log.jsonl`
5. dry-run 不写正式 delivery log
6. 非 dry-run 会写 delivery log
7. 空 `input_dir` 产生 warning 而不是崩溃
8. manifest 中 `artifact_count` 正确
9. 不访问外部服务
10. 路径不存在时错误信息明确

如果 CLI 有现成测试风格，则补：

- `tests/test_factor_cli.py`
  或
- 单独 `tests/test_report_delivery_cli.py`

## 14. Risks And Mitigations

### Risk: 当前目录结构不统一

不同报告模块返回路径字段不完全一致。

Mitigation:

- 第一阶段走混合模式
- 扫描优先 + 显式路径补充
- 不能识别时记 `unknown` 而不是报错

### Risk: 过早耦合外部渠道

如果第一阶段直接接飞书 / OpenClaw，会让本地交付边界不稳定。

Mitigation:

- 第一阶段仅 `local`
- `openclaw` / `feishu` 先在后续阶段做 adapter

### Risk: 改动现有报告生成逻辑

如果 Local Adapter 反向要求现有报告模块重写输出，会扩大范围。

Mitigation:

- 明确 adapter 只消费现有产物
- 不反向修改业务报告逻辑

## 15. Completion Criteria

第一阶段完成的标志：

- 存在独立 Local Delivery Adapter 模块
- 可扫描本地报告产物
- 可生成 `manifest.json`
- 可生成 `delivery_log.jsonl`
- 有 dry-run
- 有 CLI
- 有测试
- 不访问外部服务
- 不接飞书
- 不接 OpenClaw
- 不改变现有报告生成逻辑
- 不自动交易

## 16. Recommendation

第一阶段最推荐的第一个实现任务是：

- `Local Delivery Adapter`

原因：

- 不依赖外部服务
- 风险最低
- 能先统一本地 artifact 索引与 manifest
- 为后续 OpenClaw / 飞书 / Web / AI Agent 提供稳定输入层

