# Research Narrative Layer Design

## 1. Goal

新增一个可复用的中间层，用于把项目内已有的研报/PDF/行业公司资料，整理成：

1. `research_fact_sheet`
2. `research_decision_narrative`

该中间层不直接承担最终报告渲染职责，而是为下游模块提供更深、更可读、也更可复盘的研究信息底座。

## 2. Why

当前 `position_dossier`、`portfolio_review`、`workpack` 都已经具备一定的结构化字段，但仍存在三个核心问题：

1. 研报信息太薄
   - 主要还是 `report_count / target_price / forecast_count / risk_summary`
   - 缺少真正能支撑判断的“机构逻辑、分歧点、行业位置、产品位置、护城河、隐含前提”

2. narrative synthesis 不存在
   - 目前更像“字段拼句子”
   - 很多正文仍然只是：
     - 取一个字段直接填到句子里
     - 或重复同一句内容充当多个段落

3. 下游模块重复造叙事
   - `position_dossier`
   - `portfolio_review`
   - `workpack`
   都开始各自拼“可读内容”
   - 如果不抽出中间层，后面会越来越乱

## 3. Scope

第一版只处理：

- 研报/PDF提取结果
- 行业/公司资料字段
- 与持仓/候选结合后的研究叙事

第一版不处理：

- 新闻舆情
- 公告事件
- LLM 自由生成摘要
- 全市场实时抓取

## 4. Positioning

该模块定位为：

- `research evidence -> research facts -> decision narrative`

它不是：

- 最终报告模块
- 评分模块
- 搜索抓取模块

## 5. Chosen Architecture

新增独立模块：

- `src/stock_research/research_narrative.py`

对外暴露两层核心能力：

1. `build_research_fact_sheet(...)`
2. `build_research_decision_narrative(...)`

上游输入是结构化研究数据，下游消费方包括：

- `mid_trend_position_dossier`
- `mid_trend_portfolio_review`
- `stock_report_workpack`
- 后续 `watchlist`

## 6. Layer 1: Research Fact Sheet

### 6.1 Purpose

这一层只做“归纳事实”，不直接下判断。

它的职责是回答：

- 当前这只票有哪些研究事实
- 哪些事实是偏支持
- 哪些事实是偏反对
- 哪些关键资料缺失

### 6.2 Data groups

第一版字段按 6 组组织。

#### A. Coverage & quality

- `report_count_90d`
- `broker_coverage_count`
- `latest_rating`
- `target_price_median`
- `target_upside_median`
- `profit_forecast_count`
- `pdf_risk_section_count`
- `research_support_score`
- `research_confidence`

#### B. Bull-case facts

- `bull_case_summary`
- `key_growth_driver`
- `institution_consensus_note`
- `positive_rating_summary`
- `target_price_basis_note`

#### C. Bear-case facts

- `bear_case_summary`
- `key_risk_driver`
- `negative_research_note`
- `institution_disagreement_note`
- `risk_summary_compact`

#### D. Industry & company position

- `industry_position_note`
- `product_position_note`
- `moat_or_scarcity_note`
- `industry_mainline_context`
- `theme_alignment_note`

#### E. Assumption & valuation

- `analyst_core_assumption`
- `valuation_anchor_note`
- `expectation_dependency_note`

#### F. Data completeness

- `has_target_price`
- `has_profit_forecast`
- `has_industry_position`
- `has_product_position`
- `has_moat_note`
- `has_bull_case`
- `has_bear_case`

### 6.3 Fact sheet output contract

第一版输出为单行结构化对象，最少包含：

- 基础标识
  - `asset_id`
  - `ts_code`
  - `stock_name`
  - `trade_date`
- 上述 6 组字段

若部分字段缺失，不报错，统一留空或布尔 `False`。

## 7. Layer 2: Research Decision Narrative

### 7.1 Purpose

这一层基于 `research_fact_sheet` 生成“可读判断”。

职责是回答：

- 这只票为什么值得持有 / 不值得持有
- 最关键支持与反对是什么
- 后面要盯什么

### 7.2 Decision narrative fields

第一版输出字段：

- `one_line_judgment`
- `support_fact_1`
- `support_fact_2`
- `support_fact_3`
- `oppose_fact_1`
- `oppose_fact_2`
- `watch_point`
- `falsification_condition`
- `what_is_working_summary`
- `industry_position_summary`
- `institution_view_summary`
- `valuation_summary`
- `risk_summary`
- `decision_confidence`
- `narrative_quality_flag`

### 7.3 Narrative quality

`narrative_quality_flag` 第一版建议枚举：

- `rich`
- `medium`
- `thin`

判定依据：

- `rich`：支持/反对/行业位置/估值/机构视角大部分齐全
- `medium`：有基础研究信息，但部分缺失
- `thin`：大部分只能退化到弱证据或占位信息

## 8. Input Sources

第一版只用项目内已有来源。

### 8.1 Primary

- `mid_trend_research_packet_candidates.csv`
- `stock_report_feature_daily` PIT 结果
- PDF 提取字段
- `portfolio_review.csv`

### 8.2 Optional but supported

若已有这些字段，也直接接：

- `industry_position_note`
- `product_position_note`
- `moat_or_scarcity_note`
- `negative_research_note`
- `institution_names`
- `target_price`
- `target_upside`
- `latest_rating`

### 8.3 Excluded in v1

- 新闻舆情
- 公告
- 实时网页搜索结果
- 手工粘贴长文本

## 9. Required vs Enhanced Fields

### 9.1 Required fields

第一版稳定生成 narrative 至少依赖：

- `asset_id`
- `ts_code`
- `stock_name`
- `research_support_score`
- `latest_pdf_risk_summary`
- `main_positive_evidence`
- `main_risk_evidence`
- `final_label`
- `why_hold_or_change`

### 9.2 Enhanced fields

有则更深，没有则降级：

- `target_price_median`
- `profit_forecast_count`
- `industry_position_note`
- `product_position_note`
- `moat_or_scarcity_note`
- `negative_research_note`
- `target_upside_median`
- `latest_rating`
- `institution_consensus_note`
- `institution_disagreement_note`

## 10. Synthesis Rules

### 10.1 Deterministic only

第一版只做 deterministic rule-based synthesis：

- 规则
- 组合
- 截断/排序
- 模板化表达

不使用 LLM 自由生成文本。

### 10.2 Fact first, judgment second

顺序必须是：

1. 先事实层
2. 再判断层

不允许直接从原始字段跳到正文输出。

### 10.3 No hidden inference

所有 narrative 字段都必须能回溯到明确上游字段。

例如：

- `support_fact_1` 不能凭空生成
- `institution_view_summary` 必须来自机构覆盖/评级/目标价/分歧字段

## 11. Downstream Integration

### 11.1 Position Dossier

`mid_trend_position_dossier` 后续应改为消费：

- `research_fact_sheet`
- `research_decision_narrative`

而不是自己继续拼 narrative。

### 11.2 Portfolio Review

`mid_trend_portfolio_review` 继续保留结构化 evidence，但展示层可以逐步改用：

- `support_fact_*`
- `oppose_fact_*`
- `one_line_judgment`

### 11.3 Workpack

`stock_report_workpack` 可以用 fact sheet 增强候选票研究卡。

## 12. Replay vs Live

### 12.1 Replay

严格使用 `as-of trade_date` 可得研究资料。

### 12.2 Live

允许使用当日增强的研报/公司资料，但仍然来自项目内结构化输入，不直接网页抓取。

第一版 narrative 层不因 mode 改变结构，只改变可用输入范围。

## 13. Testing Requirements

至少覆盖：

1. `research_fact_sheet` 能生成。
2. `research_decision_narrative` 能生成。
3. 缺少增强字段时能降级，不崩溃。
4. `support_fact_*` / `oppose_fact_*` 不为空时必须可追溯到上游输入。
5. `narrative_quality_flag` 能按数据完整度分层。
6. `replay` / `live` 模式下输入过滤正确。
7. 下游模块可消费中间层输出。

## 14. Non-goals

第一版不做：

- 新闻舆情 narrative
- 公告 narrative
- 自动外部搜索增强
- 生成式研报长文
- 最终评分系统

## 15. Likely API

第一版推荐接口：

```python
def build_research_fact_sheet_from_frames(...) -> pd.DataFrame:
    ...


def build_research_decision_narrative_from_fact_sheet(...) -> pd.DataFrame:
    ...
```

必要时也可补：

```python
def run_research_narrative(...) -> dict[str, Any]:
    ...
```

## 16. Next Step

进入 implementation plan，明确：

1. 模块文件边界
2. 字段映射规则
3. fact -> narrative 规则
4. 下游接入顺序（先 dossier）
