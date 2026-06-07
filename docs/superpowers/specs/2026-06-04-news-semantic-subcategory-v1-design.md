# News Semantic Subcategory v1 Design

## 1. Goal

在现有 `news title semantic classification v1` 的四大类基础上，再增加一层 deterministic 子类，让 `topn_news_enrichment` 和 `mid_trend_position_dossier` 的新闻块从“大类标签”升级到“更具体的可读标签”。

本轮目标不是：

- 扩新闻源
- 引入 LLM
- 解析正文
- 把新闻直接接入策略打分

本轮只做：

1. 标题子类计数；
2. enrichment 子类优先摘要；
3. 保持现有 replay / live 边界不变。

## 2. Scope

只改：

1. `src/stock_research/news_features.py`
2. `src/stock_research/topn_news_enrichment.py`

测试：

1. `tests/test_news_features.py`
2. `tests/test_topn_news_enrichment.py`

不改：

- `news_source_backfill.py`
- `mid_trend_position_dossier.py`
- `schema`
- CLI 名称

## 3. Design Principles

### 3.1 Deterministic only

仍然只允许 rule-based / keyword-based 子类判断。

### 3.2 Title-only

只看 `title`，不解析 `content`。

### 3.3 Subcategory sits under existing buckets

子类只是在现有四大类下面再细分，不替代大类。

也就是说：

- 大类字段继续保留
- 新增子类字段
- enrichment 优先读子类，没有子类命中再回退到大类摘要

### 3.4 Readability first, but still countable

输出必须同时满足：

1. 人能直接读懂
2. 后续还能做统计诊断

### 3.5 Window policy

本轮主摘要窗口固定使用 `3日`，不是 `5日`。

原因：

- 当前新闻层主要服务于 `Top5/Top10` 和当前持仓的短周期解释；
- 个股新闻催化通常在 `T ~ T+2` 的解释力更强；
- `5日` 更适合作为补充观察窗口，而不是替代当前主摘要。

因此本轮约束是：

- 所有子类摘要主口径：`3日`
- 现有 `news_count_5d` 等基础字段继续保留
- `5日` 观察层可作为后续 dossier 展示增强项，但不在本轮实现范围内

## 4. Subcategory Taxonomy

第一版固定 4 组大类、11 个子类，不继续扩张。

### 4.1 `capital_flow`

#### `main_force_flow`

含义：主力资金、抢筹、加仓类。

关键词示例：

- 主力
- 抢筹
- 加仓
- 资金流入

#### `margin_flow`

含义：融资、融资客、杠杆资金类。

关键词示例：

- 融资
- 融资客
- 杠杆资金

#### `capital_flow_generic`

含义：资金关注类宽口径回退。

关键词示例：

- 资金

### 4.2 `broker_reco`

#### `gold_stock`

含义：金股、月度组合、重点推荐类。

关键词示例：

- 金股
- 月度组合
- 推荐组合

#### `rating_action`

含义：评级上调、买入评级、增持评级、目标价类。

关键词示例：

- 评级上调
- 上调评级
- 买入评级
- 增持评级
- 目标价

#### `broker_positive_view`

含义：券商/研报明确看好类。

关键词示例：

- 券商看好
- 券商推荐
- 券商研报
- 研报

### 4.3 `business_catalyst`

#### `order_bid`

含义：订单、中标、签约类。

关键词示例：

- 订单
- 中标
- 签约

#### `product_breakthrough`

含义：新品、技术突破、产品落地类。

关键词示例：

- 新品
- 突破
- 首发

#### `industry_boom`

含义：景气、扩产、行业高景气类。

关键词示例：

- 景气
- 扩产
- 供需改善

### 4.4 `risk_event`

#### `regulatory_inquiry`

含义：监管问询、问询函、风险提示类。

关键词示例：

- 监管问询
- 监管问询函
- 问询函
- 风险提示
- 风险警示

#### `shareholder_reduction`

含义：减持、清仓减持类。

关键词示例：

- 减持
- 清仓减持

#### `litigation_penalty`

含义：诉讼、处罚、立案类。

关键词示例：

- 诉讼
- 处罚
- 立案

#### `loss_warning`

含义：亏损、预亏、业绩风险类。

关键词示例：

- 亏损
- 预亏
- 业绩下滑

## 5. Feature Layer Changes

### 5.1 Existing fields stay

保留现有：

- 四个大类字段
- `headline_keyword_positive_count_3d`
- `headline_keyword_risk_count_3d`

### 5.2 New subcategory count fields

在 `NEWS_FEATURE_COLUMNS` 中新增：

- `headline_main_force_flow_count_3d`
- `headline_margin_flow_count_3d`
- `headline_capital_flow_generic_count_3d`
- `headline_gold_stock_count_3d`
- `headline_rating_action_count_3d`
- `headline_broker_positive_view_count_3d`
- `headline_order_bid_count_3d`
- `headline_product_breakthrough_count_3d`
- `headline_industry_boom_count_3d`
- `headline_regulatory_inquiry_count_3d`
- `headline_shareholder_reduction_count_3d`
- `headline_litigation_penalty_count_3d`
- `headline_loss_warning_count_3d`

### 5.3 Counting rules

窗口：

- `window_3d`

输入：

- `title_3d`

规则：

- 一条标题可同时命中多个子类
- 子类命中后，其所属大类字段也继续按现有逻辑统计

## 6. Enrichment Summary Priority

本节所有摘要文案默认都指向 `3日` 窗口。

### 6.1 `news_consensus_summary`

优先级：

1. `gold_stock`
   - `近3日券商金股/推荐新闻X条，关注度{attention}`
2. `rating_action`
   - `近3日评级/目标价新闻X条，关注度{attention}`
3. `broker_positive_view`
   - `近3日券商看好类新闻X条，关注度{attention}`
4. `main_force_flow`
   - `近3日主力资金关注新闻X条，关注度{attention}`
5. `margin_flow`
   - `近3日融资/杠杆资金新闻X条，关注度{attention}`
6. `capital_flow_generic`
   - `近3日资金关注类新闻X条，关注度{attention}`
7. `order_bid`
   - `近3日订单/中标新闻X条，关注度{attention}`
8. `product_breakthrough`
   - `近3日新品/突破新闻X条，关注度{attention}`
9. `industry_boom`
   - `近3日行业景气新闻X条，关注度{attention}`
10. covered but no subcategory
   - 回退到当前 quiet fallback

### 6.2 `news_risk_summary`

优先级：

1. `regulatory_inquiry`
   - `近3日监管问询/风险提示新闻X条`
2. `shareholder_reduction`
   - `近3日减持类风险新闻X条`
3. `litigation_penalty`
   - `近3日诉讼/处罚类风险新闻X条`
4. `loss_warning`
   - `近3日亏损/业绩风险新闻X条`
5. covered but no risk subcategory
   - `近3日未见风险关键词新闻`

### 6.3 `theme_catalyst_summary`

优先级：

1. `order_bid`
   - `近3日订单/中标催化新闻X条`
2. `product_breakthrough`
   - `近3日新品/突破催化新闻X条`
3. `industry_boom`
   - `近3日景气/扩产催化新闻X条`
4. `gold_stock`
   - `近3日券商金股催化新闻X条`
5. `rating_action`
   - `近3日评级催化新闻X条`
6. `main_force_flow`
   - `近3日主力资金关注新闻X条`
7. `margin_flow`
   - `近3日融资/杠杆资金新闻X条`
8. `capital_flow_generic`
   - `近3日资金关注类新闻X条`
9. covered but no subcategory
   - `近3日未见重大/主线催化新闻`

### 6.4 `overnight_catalyst_note`

保持现有口径：

- `overnight_news_count > 0`
  - `隔夜催化新闻X条`
- 否则 covered quiet path 才允许
  - `近3日未见隔夜催化新闻`

## 7. Compatibility Rules

### 7.1 Missing coverage

未命中任何 feature 的候选，继续保持：

- `news_attention_level = unknown`
- summary 全空
- `news_risk_attention_flag = None`

### 7.2 Mixed-schema rows

如果某文件中：

- 新子类字段存在
- 但某一行子类字段是空/脏值
- 同时 legacy / 大类字段仍有有效值

则该行应优先保留旧有可解释路径，不允许因为脏子类字段而把摘要错误降级。

### 7.3 Dirty sentinel handling

子类字段如果是：

- `""`
- `N/A`
- `-1`
- 其他非数值垃圾

都不能强制切进 subcategory mode。

## 8. Testing

至少覆盖：

1. `news_features`
- 每个核心子类至少 1 个正例
- 同一标题多子类命中
- 明显误判负例

2. `topn_news_enrichment`
- `gold_stock`
- `rating_action`
- `broker_positive_view`
- `main_force_flow`
- `margin_flow`
- `order_bid`
- `product_breakthrough`
- `industry_boom`
- `regulatory_inquiry`
- `shareholder_reduction`
- `litigation_penalty`
- `loss_warning`
- covered quiet fallback
- no coverage blank semantics
- mixed-schema row
- dirty subcategory values

## 9. Expected Real Output Improvement

当前 v1 大类输出：

- `近3日资金关注类新闻1条`
- `近3日券商推荐类新闻1条`

本轮期望升级为：

- `近3日主力资金关注新闻1条`
- `近3日融资/杠杆资金新闻1条`
- `近3日券商金股/推荐新闻1条`
- `近3日评级/目标价新闻1条`
- `近3日订单/中标新闻1条`
- `近3日监管问询/风险提示新闻1条`

## 10. Non-Goals

本轮不做：

- 新闻正文解析
- 行业主题抽取
- LLM 摘要
- 新闻评分
- 新闻进入策略排序
