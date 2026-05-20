# Data Quality Layer Design

## 1. Goal

为现有研究库补一层统一的 Data Quality Layer，用最小闭环把以下三类检查收敛到同一入口和同一结果契约下：

- `data_audit.py`：表级行数、日期覆盖、历史长度检查
- `finance_audit.py`：三表完整性与公告日期一致性检查
- `research_preflight.py`：研究运行前置阻断条件检查

第一版目标不是新增检查能力，而是统一“怎么跑”和“结果长什么样”，为后续扩展数据质量规则、日报、run card 接线提供稳定边界。

## 2. Scope

### In Scope

- 新增统一聚合模块，编排三类已有检查
- 新增统一结果 schema
- 新增统一 CLI 入口
- 支持文本输出和 JSON 输出
- 为统一层补充单元测试和 CLI 测试

### Out of Scope

- 不新增新的数据质量检查项
- 不重写现有 SQL 逻辑
- 不把 `quality.py` 的日常写库检查并入统一层
- 不新增数据库表或 artifact 落库逻辑
- 不移除或重命名现有 `data-audit` / `finance-audit` / `research-preflight` 命令

## 3. Current State

当前仓库里已有三条可用但分散的检查路径：

- `data-audit`：输出 `data_audit|...` 文本行，状态语义包含 `ok`、`empty`、`short_history`
- `finance-audit`：输出 `finance_audit|...` 文本行，状态语义包含 `ok`、`warning`、`blocked`
- `research-preflight`：输出 `research_preflight|...` 文本行，状态语义以 `ok` / `blocked` 为主

这些路径能分别解决局部问题，但缺少：

- 统一总入口
- 统一 status 语义
- 统一 JSON 结果结构
- 跨检查 summary 和 overall status

因此它们还不能被视为一个稳定的 Data Quality Layer。

## 4. Design Principles

- 叶子检查保留原样：已有检查函数继续作为独立叶子能力存在
- 统一层只做编排：不在第一版里重写底层检查逻辑
- 结果先统一、规则后扩展：先固定 schema 和 status 语义，再追加新检查
- 向后兼容：旧 CLI 入口继续保留，避免破坏现有脚本
- 只读优先：第一版不写库，不引入新的持久化依赖

## 5. Proposed Architecture

新增模块：

- `src/stock_research/data_quality.py`

职责：

- 调用 `run_data_audit()`
- 调用 `summarize_finance_coverage()`
- 调用 `find_latest_common_label_date()`
- 调用 `check_factor_label_coverage()`
- 按需调用 `check_industry_membership_coverage()`
- 把不同来源结果归一化成统一检查对象
- 计算 `overall_status`
- 输出统一文本行和统一 JSON 对象

保留现有模块：

- `src/stock_research/data_audit.py`
- `src/stock_research/finance_audit.py`
- `src/stock_research/research_preflight.py`

这些模块继续保留原有对外函数与原有 CLI 路径。第一版只允许做最小兼容增强，例如抽小 helper 或稳定字段格式，但不改变其核心检查语义。

## 6. Unified Result Contract

### Per-check object

统一层中的每个检查项都归一化为以下结构：

```json
{
  "check_name": "factor_label_coverage",
  "status": "ok",
  "kind": "research_preflight",
  "source": "research_preflight",
  "metrics": {
    "factor_date_count": 122,
    "complete_factor_date_count": 122
  },
  "details": {
    "missing_horizons": [],
    "short_label_horizons": [],
    "required_factor_names": ["momentum_20d"]
  }
}
```

字段定义：

- `check_name`：统一层稳定检查名
- `status`：统一后的状态值
- `kind`：检查类别，例如 `data_audit`、`finance_audit`、`research_preflight`
- `source`：来源模块名
- `metrics`：适合 summary/监控的数值指标
- `details`：补充上下文，允许列表和结构化字段

### Aggregate object

统一总结果为：

```json
{
  "overall_status": "warning",
  "generated_at": "2026-05-20T12:00:00+08:00",
  "checks": [],
  "blocked_checks": ["factor_label_coverage"],
  "warning_checks": ["finance_announcement_before_report_period"]
}
```

字段定义：

- `overall_status`：总状态
- `generated_at`：生成时间，ISO 8601
- `checks`：所有归一化检查项
- `blocked_checks`：`status == blocked` 的 `check_name`
- `warning_checks`：`status == warning` 的 `check_name`

## 7. Status Semantics

统一层采用以下状态集合：

- `ok`
- `warning`
- `blocked`

状态映射规则：

- `data_audit.ok` -> `ok`
- `data_audit.short_history` -> `warning`
- `data_audit.empty` -> `blocked`
- `finance_audit.ok` -> `ok`
- `finance_audit.warning` -> `warning`
- `finance_audit.blocked` -> `blocked`
- `research_preflight.ok` -> `ok`
- `research_preflight.blocked` -> `blocked`
- `quality.fail` 不纳入第一版统一层；若未来接入，默认映射为 `blocked`

`overall_status` 计算规则：

- 只要任一检查为 `blocked`，总状态为 `blocked`
- 否则只要任一检查为 `warning`，总状态为 `warning`
- 否则为 `ok`

## 8. CLI Design

保留现有命令：

- `data-audit`
- `finance-audit`
- `research-preflight`

新增聚合命令：

- `data-quality`

第一版 CLI 行为：

- 默认运行三类检查并输出统一文本行
- 支持 `--json` 输出统一聚合对象
- 默认打印一行 summary，再打印各检查项
- 当存在 `blocked` 检查时退出码为 `1`
- 当不存在 `blocked` 检查时退出码为 `0`

建议参数：

- `--start-date`
- `--end-date`
- `--horizons`
- `--factor-names`
- `--calc-version`
- `--min-label-dates`
- `--require-industry-membership`
- `--expected-start-date`
- `--json`

这些参数直接复用现有叶子检查所需参数，不在第一版引入额外推导规则。若用户未提供研究窗口参数，则沿用现有 `research-preflight` 的默认日期推导方式。

## 9. Text Output Format

为兼容现有 shell/log 使用方式，统一层默认输出逐行文本。

第一行输出 summary：

```text
data_quality|summary|warning|checks|7|blocked|0|warning|1
```

后续每行输出单个检查：

```text
data_quality|factor_label_coverage|ok|kind|research_preflight
data_quality|finance_missing_balance_sheet|blocked|kind|finance_audit
data_quality|market_daily_bar|warning|kind|data_audit
```

第一版文本输出只承诺稳定以下字段：

- 前缀 `data_quality`
- `check_name`
- `status`
- `kind`

额外指标可跟在末尾，但测试将只锁定稳定骨架和关键 metric 字段，避免无意义的格式脆弱性。

## 10. Check Inventory For V1

第一版统一层纳入的检查包括：

### From `data_audit`

- `market_daily_bar`
- `raw_baostock.daily_bar_payload`
- `raw_baostock.industry_snapshot_payload`
- `market.index_daily_bar`
- `market.index_constituent`
- `market.trading_calendar`
- `market.adjustment_factor`
- `market.corporate_action`
- `label_snapshot`
- `feature_snapshot`
- `factor.factor_daily`
- `factor.stock_technical_features_daily`
- `core.asset_lifecycle_event`
- `core.industry_membership`
- `market.industry_daily_bar`
- `finance.income_statement`
- `finance.balance_sheet`
- `finance.cash_flow`
- `factor.factor_approval`
- `ingest.batch_job`

### From `finance_audit`

- `missing_balance_sheet`
- `missing_cash_flow`
- `missing_announcement_date`
- `announcement_before_report_period`

### From `research_preflight`

- `latest_common_label_date`
- `factor_label_coverage`
- `industry_membership_coverage` when `--require-industry-membership` is enabled

`latest_common_label_date` 在统一层里视为单独检查项，而不是只作为 coverage 附属字段，这样 summary 和 JSON 可以直接暴露标签对齐状态。

## 11. Testing Strategy

新增：

- `tests/test_data_quality.py`

覆盖内容：

- 统一聚合对象 shape
- status 映射
- `overall_status` 计算
- summary line formatter 稳定性
- `--require-industry-membership` 的条件纳入逻辑

增补现有：

- `tests/test_factor_cli.py`

覆盖内容：

- `data-quality` 默认文本输出
- `data-quality --json`
- 有 `blocked` 检查时 CLI 退出码
- 无 `blocked` 检查时 CLI 退出码

不重写现有：

- `tests/test_data_audit.py`
- `tests/test_finance_audit.py`
- `tests/test_research_preflight.py`

这些测试继续分别保护叶子检查的原始行为。

## 12. Risks And Mitigations

### Risk: status 语义混淆

`empty`、`short_history`、`blocked`、`fail` 当前来自不同模块，若不先统一语义，会导致总入口结果不可比较。

Mitigation:

- 统一层只暴露 `ok` / `warning` / `blocked`
- 在 spec 中固定映射表
- 通过单测锁定映射行为

### Risk: CLI 参数重复和行为漂移

若新命令重新发明参数，会和既有 `research-preflight` 出现双重默认值和双重窗口推导。

Mitigation:

- 第一版直接复用现有参数语义
- 默认日期推导与现有 `research-preflight` 保持一致

### Risk: 过早并入日常写库质量检查

`quality.py` 有单独的日常写表逻辑，和研究前置检查并非同一层责任。

Mitigation:

- 第一版明确不并入 `quality.py`
- 只在状态语义上预留未来兼容空间

## 13. Implementation Boundaries

第一版实现完成的标志：

- 可以通过一个统一命令跑完三类既有检查
- 可以拿到稳定 JSON 结构
- 可以拿到稳定 summary + per-check 文本输出
- 可以根据 `blocked` 状态正确返回退出码
- 现有三个旧命令继续可用

第一版不以“覆盖所有质量问题”为完成条件，而以“统一层边界被固定”为完成条件。

## 14. Recommendation

按本设计推进第一版，实现顺序应为：

1. 新增 `data_quality.py` 统一聚合层
2. 在 `cli.py` 新增 `data-quality` 命令
3. 补 `tests/test_data_quality.py`
4. 在 `tests/test_factor_cli.py` 增补新命令测试

完成后，再基于同一统一层继续收敛：

- `quality.py` 的日常检查语义
- 报告层引用
- run card / evidence trail 接线
