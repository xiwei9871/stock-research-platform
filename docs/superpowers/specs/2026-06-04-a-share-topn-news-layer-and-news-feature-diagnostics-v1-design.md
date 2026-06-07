# A股 TopN News Layer & News Feature Diagnostics v1 Design

## 1. Goal

新增一条可回放、可扩展的新闻数据与特征链，服务两个目标：

1. 为 `Top5/Top10` 候选提供新闻增强资料层；
2. 为后续验证“新闻是否具有风险解释力或机会解释力”提供 deterministic 诊断底座。

第一版不把新闻直接接入全市场选股打分，不做自动交易信号，不做新闻情绪黑盒分数。

## 2. Why

当前项目在以下几层已经具备结构：

- 全市场筛选：`Top500 -> Top50 -> Top10 -> Top5`
- 结构化证据层：`portfolio_review`
- 正式持仓报告层：`position_dossier`
- 研报叙事层：`research_narrative`

但新闻仍是空白，这带来三个现实问题：

1. `Top5/Top10` 的正式报告资料仍偏薄
   - 只有研报/PDF、主线、技术、基本面排雷
   - 缺少“近期是否有事件催化、是否新闻密集、是否盘前/隔夜集中发酵”这层信息

2. 无法验证新闻到底是机会信号还是风险信号
   - 强票可能因为主线催化而新闻变多
   - 高位退潮票也可能因为关注度极高而新闻变多
   - 不做数据层和诊断，很容易把“热闹”误判成“机会”

3. 以后就算接新闻，也缺少 PIT 边界
   - 如果没有按 `trade_date` 可得信息落库和聚合，后续所有回放都会有后视偏差风险

## 3. Scope

第一版只做：

- A 股新闻原始事件层
- 新闻到证券/主题的 mention 层
- 按 `asset_id + trade_date` 的新闻特征层
- `Top5/Top10` 新闻增强摘要层
- 新闻诊断产物与报告

第一版不做：

- 全市场新闻打分直接入 `factor_daily`
- 自动化新闻情绪分数
- 新闻驱动的实时交易信号
- 自由生成式 LLM 全文总结
- 新闻舆情与公告合并成统一事件引擎

## 4. Key Positioning

新闻在本项目里的定位，第一版明确分成两层：

1. **Deterministic data layer**
   - 解决“有什么新闻、什么时候出现、来自谁、是否密集”
   - 强调可回放、可测试、可聚合

2. **TopN enhancement layer**
   - 只对 `Top5/Top10` 做更深的新闻事实增强
   - 用于人读报告，不直接参与全市场排序

第一版不做第三层：

- `news_score` 直接入策略排序

## 5. Data Source Choice

### 5.1 Preferred source

第一版首选 `Tushare` 的新闻接口：

- `news`
- `major_news`

原因：

1. 中文 A 股财经源更匹配当前项目；
2. 历史长度够用，适合回放；
3. 字段结构比通用网页搜索 API 更容易标准化；
4. 与现有项目的 A 股数据生态更一致。

### 5.2 Source caveat

新闻接口有权限要求，不应默认假设任何 token 都可用。

因此第一版需要显式支持：

- `source_status = available`
- `source_status = permission_denied`
- `source_status = disabled`

当新闻源不可用时：

- CLI 不崩溃；
- 输出 warning；
- 诊断报告明确说明该段缺失；
- 不生成误导性的空“正向结论”。

### 5.3 Future source extensibility

设计上允许后续增加：

- 财联社/东方财富等可授权源
- 通用新闻 API
- 自有爬虫或付费资讯源

但第一版 spec 不要求同时落地多源抓取。

## 6. Chosen Architecture

新增三个层次，职责清楚分开：

### 6.1 Raw event layer

建议新增模块：

- `src/stock_research/news_source_backfill.py`

职责：

- 拉取原始新闻；
- 标准化字段；
- 去重；
- 落入事件源表。

### 6.2 Mention and feature layer

建议新增模块：

- `src/stock_research/news_features.py`

职责：

- 做证券 mention 标准化；
- 生成 `asset_id + trade_date` 级别的新闻特征；
- 供后续诊断和 dossier 使用。

### 6.3 TopN enhancement layer

建议新增模块：

- `src/stock_research/topn_news_enrichment.py`

职责：

- 只对 `Top5/Top10` 候选做新闻增强；
- 生成“事件催化、风险提示、隔夜催化、新闻一致点”这类人读层事实；
- 供 `position_dossier` / `portfolio_review` 消费。

## 7. Storage Design

建议新增三张表。

### 7.1 `research.news_event_source`

原始新闻事件表。

核心字段：

- `source_event_id`
- `source_name`
- `source_channel`
- `title`
- `content`
- `published_at`
- `collected_at`
- `language`
- `url`
- `hash_key`
- `source_status`
- `metadata`

说明：

- `hash_key` 用于去重；
- `metadata` 保留原始源字段和抓取上下文；
- 第一版允许 `content` 为空，但 `title` 和 `published_at` 不应为空。

### 7.2 `research.news_event_mention`

新闻到资产/主题的映射表。

核心字段：

- `source_event_id`
- `asset_id`
- `ts_code`
- `stock_name`
- `mention_role`
- `mention_confidence`
- `theme_name`
- `theme_confidence`
- `mapping_method`
- `trade_date`

说明：

- 第一版 `mapping_method` 以 deterministic 规则为主：
  - 证券代码命中
  - 中文简称命中
  - 主题关键词命中
- 实现上采用 surrogate primary key，以允许 `asset_id` / `theme_name`
  在单条 mention 上独立为空；不使用会隐式强制非空的复合主键。
- 后续可加入更强的 NLP/LLM 映射，但第一版不依赖它。

### 7.3 `research.news_feature_daily`

按 `asset_id + trade_date` 聚合后的 PIT 新闻特征表。

核心字段：

- `trade_date`
- `asset_id`
- `ts_code`
- `news_count_1d`
- `news_count_3d`
- `news_count_5d`
- `major_news_count_3d`
- `source_diversity_3d`
- `overnight_news_count`
- `preopen_news_count`
- `headline_keyword_positive_count_3d`
- `headline_keyword_risk_count_3d`
- `theme_news_burst_flag`
- `news_first_seen_gap`
- `news_attention_level`
- `metadata`

说明：

- 第一版只做 deterministic 聚合；
- `news_attention_level` 是规则分层字段，不是自由打分；
- `metadata` 可记录源分布和窗口细节。

## 8. Replay vs Live

新闻层必须和当前 `position_dossier` 一样，明确区分 `replay` 与 `live`。

### 8.1 Replay mode

严格只使用 `trade_date` 当日及之前可得的新闻。

规则：

- `published_at <= as_of_cutoff`
- 不允许读取未来标题、未来正文、未来聚合特征

用途：

- 回放验证
- 诊断报告
- 历史复盘

### 8.2 Live mode

允许在 `Top5/Top10` 已出之后，补当天最新新闻资料。

用途：

- 今日候选增强
- 正式持仓讨论
- 候选调入/调出比较

约束：

- `live` 结果不得拿去冒充历史 replay 指标；
- 所有 live 增强应单独标识来源时间。
- 当前实现的 `live` 仅适用于单日 overlay / dossier 增强；
  不应用于历史 diagnostics 或 ranged replay 分析。

## 9. Deterministic News Features v1

第一版建议先落这组特征，不做抽象情绪分。

### 9.1 Volume / attention

- `news_count_1d`
- `news_count_3d`
- `news_count_5d`
- `major_news_count_3d`
- `source_diversity_3d`

### 9.2 Timing / catalyst

- `overnight_news_count`
- `preopen_news_count`
- `news_first_seen_gap`
- `theme_news_burst_flag`

### 9.3 Headline keyword buckets

建议做两组确定性关键词桶：

- `headline_keyword_positive_count_3d`
  - 如：中标、订单、涨价、扩产、突破、合作、业绩预增、政策支持

- `headline_keyword_risk_count_3d`
  - 如：减持、问询、监管、澄清、风险提示、业绩下修、停牌核查、闪崩、跌停

关键词集第一版应显式版本化，不要隐式散落在代码里。

### 9.4 Source-specific counts

如果源字段稳定，可附加：

- `cls_count_3d`
- `eastmoney_count_3d`
- `wallstreetcn_count_3d`
- `sina_count_3d`

第一版不是必需字段，但结构应预留。

## 10. News Attention and Risk Buckets

第一版只做离散分层，不做连续新闻分数。

建议新增：

- `news_attention_level`
  - `low`
  - `medium`
  - `high`
  - `burst`

- `news_risk_attention_flag`
  - `True/False`

初版规则例子：

- `burst`
  - `news_count_3d` 很高，且 `source_diversity_3d` 高
- `high`
  - `news_count_3d` 或 `major_news_count_3d` 显著高于常态
- `news_risk_attention_flag`
  - 风险关键词计数高
  - 或隔夜/盘前风险型新闻集中

这一步定位是诊断层，不是买入分层。

## 11. TopN News Enrichment v1

第一版只增强 `Top5/Top10`。

建议输出一张增强表：

- `research.news_topn_enrichment_daily`
  或先以 CSV 产物形式验证，再决定是否入库。

字段建议：

- `trade_date`
- `asset_id`
- `ts_code`
- `stock_name`
- `news_consensus_summary`
- `news_risk_summary`
- `theme_catalyst_summary`
- `overnight_catalyst_note`
- `news_attention_level`
- `news_risk_attention_flag`
- `news_enrichment_quality_flag`

补充实现约束：

- 如果 `trade_date + asset_id` 在输入新闻特征里重复，第一版采用
  file-order `last-row-wins`，这是最小稳定契约，不代表 freshness-aware
  聚合。

### 11.1 What it should answer

对每只 TopN 候选，第一版至少回答：

1. 近期有没有明显催化；
2. 催化是公司级还是主题级；
3. 风险型新闻是否在升温；
4. 是否存在隔夜/盘前集中发酵；
5. 这层新闻更像支持还是更像拥挤/风险。

### 11.2 LLM position

第一版 architecture 允许 LLM，但位置被严格限制在 TopN 增强层。

允许 LLM 做的事情：

- 将多个标题/摘要归并成 `news_consensus_summary`
- 将多条风险信息压缩成 `news_risk_summary`
- 归纳“主题催化一致点”

不允许 LLM 做的事情：

- 直接产出全市场新闻打分
- 直接下交易结论
- 在 replay 模式下使用无法回放的自由搜索结果

换言之：

- **LLM 可以进 TopN explanation layer**
- **LLM 不进入 all-market ranking layer**

## 12. Diagnostics v1

第一版应新增一个诊断 CLI，例如：

- `stock-research news-feature-diagnostics`

用途：

- 验证新闻特征到底更像机会信号还是风险信号；
- 验证哪些新闻特征只在特定环境下有效；
- 验证新闻是否能增强 `TopN` 人工报告，而不是替代策略。

### 12.1 Output artifacts

建议输出：

- `outputs/research/news_feature_bucket_effectiveness.csv`
- `outputs/research/news_feature_regime_effectiveness.csv`
- `outputs/research/topn_news_enrichment_sample.csv`
- `outputs/research/news_feature_diagnostics_report.md`

### 12.2 Diagnostics questions

第一版重点回答：

1. 新闻密度高，是否更像关注度而非机会；
2. `major_news_count_3d` 是否比普通快讯更有解释力；
3. 风险关键词爆发是否更像回撤前兆；
4. 隔夜/盘前催化是否对 `1/3/5d` 更有意义；
5. 新闻特征与主线环境、LHB 风险、研报支撑叠加后，解释力是否提升。

## 13. Integration with Existing Stack

### 13.1 `position_dossier`

第一版只消费 TopN 新闻增强字段，不直接消费原始新闻。

新增正文可用信息：

- 近期催化摘要
- 风险新闻摘要
- 隔夜催化说明
- 新闻关注层级

### 13.2 `portfolio_review`

可在后续加一块轻量新闻证据：

- `news_evidence_summary`
- `news_attention_level`
- `news_risk_attention_flag`

### 13.3 `research_narrative`

后续可把 TopN 新闻增强接入 `research_fact_sheet` 的扩展字段，但第一版不强制耦合。

设计上应保持：

- `research_narrative` 继续是研报/公司资料中间层；
- 新闻作为并列增强层，而不是直接塞进原有研报事实字段。

## 14. Difficulty Assessment

第一版难度评估为 **中高**，但可以开始。

### 14.1 Not hard

- 拉源
- 标准化时间戳
- 去重
- 落库
- 按日聚合

### 14.2 Hard parts

真正难的是：

1. 证券映射
   - 同名简称
   - 一文多股
   - 只提板块不提个股

2. 指标定义
   - “新闻更多”不等于“更好”
   - 很多时候反而意味着高位拥挤或分歧放大

3. PIT 一致性
   - replay / live 必须严格分开

因此结论不是“现在不能做”，而是：

> 可以开始，但要先做数据层和诊断层，不要直接做新闻打分。

## 15. Chosen Rollout

建议按三阶段推进。

### Phase 1

先做 deterministic 新闻数据层：

- `news_event_source`
- `news_event_mention`
- `news_feature_daily`

### Phase 2

只对 `Top5/Top10` 做新闻增强：

- `news_consensus_summary`
- `news_risk_summary`
- `theme_catalyst_summary`
- `overnight_catalyst_note`

这一层允许引入 LLM，但必须缓存结果并区分 `replay/live`。

### Phase 3

做新闻特征诊断：

- 分桶
- 分市场环境
- 与 `LHB` / `研报支撑` / `主线状态` 交叉

只有验证后，才讨论是否把部分 deterministic 新闻字段引入后续观察池或风险层。

## 16. Non-goals

第一版明确不做：

- 新闻 Alpha 因子直接进打分
- 新闻直接决定买卖
- 自由文本情绪分数直接入模
- 全市场 LLM 新闻总结
- 把公告和新闻一次性并表成终局方案

## 17. Testing Requirements

第一版实现时至少覆盖：

1. 新闻源不可用时 CLI 不崩溃；
2. 原始新闻去重逻辑可复现；
3. mention 映射失败时不会错误生成证券特征；
4. `replay` 只使用 `trade_date` 可得新闻；
5. `live` 与 `replay` 结果明确区分；
6. `news_feature_daily` 能生成；
7. `TopN` 新闻增强能生成；
8. 新闻诊断报告在样本不足时不崩溃，只输出 warning；
9. 不把新闻直接接入现有策略排序；
10. 不破坏现有 `portfolio_review / position_dossier / research_narrative`。

## 18. Recommendation

当前建议明确如下：

1. **可以开始引入外部新闻**
   - 但先做 deterministic 数据层和诊断层。

2. **可以开始引入 LLM**
   - 但只放在 `Top5/Top10` 新闻增强层。

3. **当前不建议**
   - 把新闻直接接到全市场选股打分；
   - 把新闻包装成确定性交易信号。

第一版目标不是“让新闻替你做决策”，而是：

> 先让新闻成为可回放、可验证、可用于 TopN 深度讨论的一层事实与诊断信息。
