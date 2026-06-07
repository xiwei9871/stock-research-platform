# News Compact Summary v1 Design

## 1. Goal

在现有 `topn_news_enrichment` 的结构化新闻字段之上，新增一层 deterministic 的一句话短摘要，使 dossier 从“标签列表”提升到“结构化短句”。

本轮目标不是替代现有字段，而是增加一个更适合人读的摘要层。

## 2. Scope

只改：

1. `src/stock_research/topn_news_enrichment.py`
2. `src/stock_research/mid_trend_position_dossier.py`

测试：

1. `tests/test_topn_news_enrichment.py`
2. `tests/test_mid_trend_position_dossier.py`

不改：

- `news_source_backfill.py`
- `news_features.py`
- 新闻源
- CLI 名称

## 3. New Field

在 `TOPN_NEWS_ENRICHMENT_COLUMNS` 中新增：

- `news_compact_summary`

这个字段的定位是：

- 给人读的一句话
- 基于已生成的子类语义
- 不替代已有 `news_consensus_summary / news_risk_summary / theme_catalyst_summary`

## 4. Summary Composition Rules

### 4.1 General rules

- 主窗口继续使用 `3日`
- deterministic only
- 只基于已知子类命中情况组合，不做语言生成
- no coverage 时保持空

### 4.2 Positive resonance

如果同时命中：

- 资金类子类（`main_force_flow / margin_flow / capital_flow_generic`）
- 券商类子类（`gold_stock / rating_action / broker_positive_view`）

则生成：

- `近3日{资金子类文案} + {券商子类文案}共振`

示例：

- `近3日主力资金关注 + 券商金股推荐共振`
- `近3日融资/杠杆资金关注 + 评级上调共振`

### 4.3 Catalyst plus capital

如果同时命中：

- 经营催化类子类（`order_bid / product_breakthrough / industry_boom`）
- 资金类子类

则生成：

- `近3日{经营催化子类文案} + {资金子类文案}`

示例：

- `近3日订单/中标催化 + 主力资金关注`
- `近3日新品/突破催化 + 融资/杠杆资金关注`

### 4.4 Risk without new catalyst

如果命中任一风险子类：

- `regulatory_inquiry`
- `shareholder_reduction`
- `litigation_penalty`
- `loss_warning`

且没有任何正向/催化子类，则生成：

- `近3日{风险子类文案}但无新增催化`

示例：

- `近3日监管问询但无新增催化`
- `近3日减持风险但无新增催化`
- `近3日诉讼/处罚风险但无新增催化`

### 4.5 Single subtype only

如果只命中一个明确子类，则直接输出：

- `近3日{子类文案}`

示例：

- `近3日主力资金关注`
- `近3日券商金股推荐`
- `近3日订单/中标催化`

### 4.6 Covered but quiet

如果：

- 有 news feature coverage
- 没有任何子类命中

则输出：

- `近3日无明显新增催化`

### 4.7 No coverage

如果：

- `news_attention_level = unknown`
- no feature coverage

则：

- `news_compact_summary = ""`

## 5. Subtype Phrase Mapping

内部需要固定子类 -> 文案映射。

建议第一版：

- `main_force_flow` -> `主力资金关注`
- `margin_flow` -> `融资/杠杆资金关注`
- `capital_flow_generic` -> `资金关注`
- `gold_stock` -> `券商金股推荐`
- `rating_action` -> `评级上调/目标价催化`
- `broker_positive_view` -> `券商看好`
- `order_bid` -> `订单/中标催化`
- `product_breakthrough` -> `新品/突破催化`
- `industry_boom` -> `景气/扩产催化`
- `regulatory_inquiry` -> `监管问询`
- `shareholder_reduction` -> `减持风险`
- `litigation_penalty` -> `诉讼/处罚风险`
- `loss_warning` -> `亏损/业绩风险`

## 6. Display Layer Change

在 `mid_trend_position_dossier` 的“新闻/催化跟踪”块最前面增加一行：

- `新闻短摘要：{news_compact_summary}`

展示顺序改为：

1. 新闻短摘要
2. 新闻关注度
3. 新闻共识
4. 新闻风险
5. 主题催化
6. 隔夜催化
7. 风险新闻关注

## 7. Testing

至少覆盖：

1. `topn_news_enrichment`
- 资金 + 券商 共振
- 经营催化 + 资金
- 风险但无催化
- 单一子类
- covered quiet
- no coverage blank

2. `mid_trend_position_dossier`
- markdown 中出现 `新闻短摘要：...`
- 位置在新闻块最前面

## 8. Non-Goals

本轮不做：

- 多句摘要
- LLM 改写
- 跨 `5日` 窗口
- 正文级摘要
- 新闻打分
