# News Title Semantic Classification v1 Design

## 1. Goal

在不引入 LLM、不新增新闻源、不扩大到正文解析的前提下，为现有 public news fallback 链增加一层 deterministic 标题语义分类，使 `topn_news_enrichment` 和 `mid_trend_position_dossier` 的新闻块更可读，也为后续诊断保留结构化统计基础。

本轮目标不是做新闻情绪总分，也不是把新闻直接接入全市场打分层。本轮只做：

1. 标题级别分类计数；
2. TopN enrichment 摘要增强；
3. 保持 replay / live 现有边界不变。

## 2. Scope

只改两层：

1. `src/stock_research/news_features.py`
2. `src/stock_research/topn_news_enrichment.py`

配套测试文件：

1. `tests/test_news_features.py`
2. `tests/test_topn_news_enrichment.py`

不改：

- `news_source_backfill.py`
- `mid_trend_position_dossier.py`
- schema / table 结构
- CLI 接口名
- 新闻源接入范围

## 3. Constraints

### 3.1 Deterministic only

本轮只允许 rule-based / keyword-based 分类，不引入：

- LLM 摘要
- embedding / semantic search
- 外部在线推理依赖

### 3.2 Title-first

本轮分类只看 `title`，不解析 `content`。原因：

- 当前 source 质量不稳定，正文噪音更大；
- 先把标题层做稳，成本最低；
- 后续若要扩正文，应作为 v2。

### 3.3 No scoring changes

本轮不把新闻分类直接接入：

- mid trend funnel 打分
- watchlist 策略打分
- position decision label 生成

新闻仍然只用于增强解释层与后续 diagnostics。

## 4. Semantic Categories

第一版固定 4 类，不再扩张。

### 4.1 `capital_flow`

含义：资金关注、融资杠杆、主力流向类标题。

关键词示例：

- 主力
- 资金
- 抢筹
- 加仓
- 融资
- 融资客
- 杠杆

### 4.2 `broker_reco`

含义：券商推荐、金股、评级/看好类标题。

关键词示例：

- 券商
- 金股
- 推荐
- 看好
- 评级
- 上调
- 增持

实现约束：

- 第一版允许使用更具体的短语/上下文匹配来降低明显误判；
- 例如 `券商看好`、`金股推荐`、`评级上调`、`上调评级`、`买入评级`、`增持评级` 这类标题应命中；
- 但像单独的 `看好后市` 这类没有券商/评级上下文的泛正向措辞，不要求命中该类。

### 4.3 `business_catalyst`

含义：订单、经营、产品、景气、突破类标题。

关键词示例：

- 订单
- 中标
- 新品
- 景气
- 扩产
- 突破
- 签约

### 4.4 `risk_event`

含义：风险、减持、监管、诉讼、亏损、停牌类标题。

关键词示例：

- 风险
- 减持
- 监管
- 诉讼
- 亏损
- 停牌
- 问询

实现约束：

- 第一版允许使用更具体的风险事件短语来降低明显误判；
- 例如 `风险提示`、`风险警示`、`监管问询`、`问询函`、`减持`、`诉讼`、`亏损`、`停牌` 这类标题应命中；
- 但像单独的 `经营存在风险` 这类泛风险措辞，不要求命中该类。

## 5. Feature-Layer Changes

在 `news_features.py` 的 `NEWS_FEATURE_COLUMNS` 中新增 4 个字段：

- `headline_capital_flow_count_3d`
- `headline_broker_reco_count_3d`
- `headline_business_catalyst_count_3d`
- `headline_risk_event_count_3d`

计算口径：

- 窗口：`window_3d`
- 输入：`title_3d`
- 规则：某条标题命中该类任意关键词，则该标题对该类计数 `+1`

允许同一标题同时命中多类；本轮不做互斥分类。

保留现有字段：

- `headline_keyword_positive_count_3d`
- `headline_keyword_risk_count_3d`

它们继续存在，作为旧兼容字段与粗粒度诊断字段。

## 6. Enrichment-Layer Changes

`topn_news_enrichment.py` 的摘要生成逻辑改成分层优先级：

### 6.1 `news_consensus_summary`

优先顺序：

1. `broker_reco > 0`
   - `近3日券商推荐类新闻X条，关注度{attention}`
2. `capital_flow > 0`
   - `近3日资金关注类新闻X条，关注度{attention}`
3. `business_catalyst > 0`
   - `近3日经营催化类新闻X条，关注度{attention}`
4. 仍无命中但 feature 存在
   - `近3日未见明显正向新闻，关注度{attention}`

### 6.2 `news_risk_summary`

优先顺序：

1. `risk_event > 0`
   - `近3日风险事件类新闻X条`
2. 否则若 feature 存在但无风险命中
   - `近3日未见风险关键词新闻`

### 6.3 `theme_catalyst_summary`

优先顺序：

1. `business_catalyst > 0`
   - `近3日经营/主题催化新闻X条`
2. 否则若 `broker_reco > 0`
   - `近3日券商催化类新闻X条`
3. 否则若 `capital_flow > 0`
   - `近3日资金关注类新闻X条`
4. 否则若 feature 存在
   - `近3日未见重大/主线催化新闻`

### 6.4 `overnight_catalyst_note`

保留当前口径：

- `overnight_news_count > 0`
  - `隔夜催化新闻X条`
- 否则若 feature 存在且全计数为 0
  - `近3日未见隔夜催化新闻`

## 7. Quality Rules

### 7.1 Missing coverage

如果候选未匹配到任何 feature：

- `news_attention_level = unknown`
- `news_risk_attention_flag = None`
- 所有 summary 继续为空

这条语义不能破坏。

### 7.2 Covered but quiet

如果候选命中了 feature，但 4 类标题计数都为 0：

- 继续使用当前 fallback 逻辑
- 不要空白

### 7.3 Dirty input tolerance

新增分类计数字段也必须复用现有“脏值安全”风格：

- 空值 -> 0
- 非法文本 -> 0

## 8. Testing

至少覆盖：

1. `news_features`
   - 某个标题命中 `capital_flow`
   - 某个标题命中 `broker_reco`
   - 某个标题命中 `business_catalyst`
   - 某个标题命中 `risk_event`
   - 同一标题允许多类命中

2. `topn_news_enrichment`
   - `broker_reco` 命中时，优先生成券商推荐类摘要
   - `capital_flow` 命中时，生成资金关注类摘要
   - `business_catalyst` 命中时，生成经营催化类摘要
   - `risk_event` 命中时，生成风险事件类摘要
   - 无分类命中但 feature 存在时，仍走 fallback
   - 无 feature 时，仍保持 `unknown + empty summaries`

## 9. Expected Real-World Improvement

针对当前 `2026-06-02` public fallback 样本，目标是把：

- `近3日未见明显正向新闻，关注度low`

升级成更可读的类别化结论，例如：

- `近3日资金关注类新闻1条，关注度low`
- `近3日券商推荐类新闻1条，关注度low`
- `近3日经营/主题催化新闻1条`

也就是说，本轮追求的是“从泛化提示升级到可读标签化摘要”，不是追求新闻逻辑已经足够深。

## 10. Non-Goals

本轮明确不做：

- 正文级别解析
- 新闻源扩展
- 新闻情绪分
- 新闻直接接策略排序
- 行业主题抽取
- LLM 摘要
