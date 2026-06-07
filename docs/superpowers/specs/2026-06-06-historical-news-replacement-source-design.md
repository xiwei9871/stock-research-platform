# Historical News Replacement Source Design

## 1. Goal

在保留现有 `AKShare stock_news_em` 近端新闻增强链的前提下，设计一套**真正能覆盖 `2025-01-01..至今`** 的历史替代数据源方案，服务：

1. `Top10 historical news backfill`
2. `Top5/Top10` 历史解释层
3. 风险事件、机构关注、硬催化的 replay 诊断

本轮目标不是：

- 再找一个“万能历史媒体新闻源”
- 直接把历史新闻接入全市场选股打分
- 构建全市场舆情系统

本轮要解决的是：

> 在 `2025-01-01..至今` 的 replay 口径下，哪些公开来源**真的有历史深度**，并且能稳定映射到个股、事件日期和结构化特征。

## 2. Current State

当前新闻链分成两部分：

### 2.1 已经可用的近端新闻增强层

现有链路：

- `news_source_backfill.py`
- `news_features.py`
- `topn_news_enrichment.py`
- `mid_trend_position_dossier.py`

当前 public fallback 主源：

- `AKShare stock_news_em`

这条链已经能为最近几天的 `Top5/Top10` 生成：

- `news_attention_level`
- 标题语义分类
- 子类语义
- `news_compact_summary`

因此它应当保留。

### 2.2 当前历史层的真实问题

`AKShare stock_news_em` 不适合作为 `2025-01-01..至今` 的历史主源。

本地实际探针结果：

- `stock_news_em` 默认只取第一页，AKShare 封装本身不够
- 即使直接走东方财富搜索接口分页，也只能下探到大约 `2025-12`
- 无法覆盖 `2025-01..2025-11`

实测例子：

- `600183`: 最老约到 `2025-12-09`
- `300201`: 最老约到 `2025-12-08`
- `300408`: 最老约到 `2025-12-07`
- `688390`: 最老约到 `2025-12-10`

因此：

- `stock_news_em` 可保留为**近端媒体新闻层**
- 不能继续承担**历史 replay 主源**

## 3. Design Principle

历史层不再追求“纯媒体新闻源统一解决”。

改为采用：

1. **近端媒体新闻层**
2. **历史公告/研报主链**
3. **后续可选监管事件层**

也就是：

- 近端看“媒体热度和短催化”
- 历史看“公告、研报、法定披露和机构覆盖”

这是更稳定、更可回放的结构。

## 4. Chosen Source Set

### 4.1 Keep: `AKShare stock_news_em`

定位：

- `recent_media_news`

用途：

- 近端 `T-3 / T-5` 新闻增强
- dossier 中的短期催化、媒体关注、短线风险块

不承担：

- `2025-01-01..至今` 历史主回填

官方文档：

- AKShare 股票新闻文档：
  https://akshare.akfamily.xyz/data/stock/stock.html

### 4.2 Add: `CNInfo disclosure announcements`

定位：

- `disclosure_notice`

用途：

- 风险提示
- 业绩预告/业绩快报
- 重大合同/投资/担保
- 减持/回购/股权激励
- 问询回复/澄清/异常波动说明

为什么入选：

1. 官方法定披露源
2. 个股映射稳定
3. 有明确公告日期
4. 对 replay 边界清晰
5. 本地实测可覆盖 `2025-01`

官方入口：

- CNInfo 公告检索：
  https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search

本地实测：

- `600183`: `57` 条，最早 `2025-01-10`
- `300201`: `61` 条，最早 `2025-01-02`
- `688390`: `75` 条，最早 `2025-01-01`

### 4.3 Add: `Eastmoney individual notice`

定位：

- `disclosure_notice`

用途：

- 补充公告标题和公告类型
- 提供更易做 deterministic 分类的 `公告类型`

为什么入选：

1. 个股粒度明确
2. 可按日期窗口拉取
3. 本地实测可覆盖 `2025-01`
4. `公告类型` 字段对规则化风险识别有价值

官方入口：

- 东方财富公告大全：
  https://data.eastmoney.com/notices/hsa/5.html

AKShare 已有接口：

- `stock_individual_notice_report(security, begin_date, end_date)`

本地实测：

- `600183`: `60` 条，最早 `2025-01-10`
- `300201`: `63` 条，最早 `2025-01-02`
- `688390`: `77` 条，最早 `2025-01-01`

### 4.4 Add: `Eastmoney research report`

定位：

- `institution_report`

用途：

- 机构覆盖
- 评级动作
- 目标价
- 盈利预测
- 历史关注度和机构支持强弱

为什么入选：

1. 历史深度够
2. 直接映射个股
3. 对 `Top10` 历史解释价值高
4. 与现有 PDF 研报链天然兼容

官方入口：

- 东方财富个股研报：
  https://data.eastmoney.com/report/stock.jshtml

AKShare 已有接口：

- `stock_research_report_em(symbol)`

本地实测：

- `600183`: 窗口内 `21` 篇，最早 `2025-01-27`
- `300408`: 窗口内 `15` 篇，最早 `2025-04-27`
- `688390`: 窗口内 `12` 篇，最早 `2025-04-29`

### 4.5 Phase 2 Optional: `SSE / SZSE regulatory inquiry`

定位：

- `regulatory_event`

用途：

- 问询函
- 监管函
- 纪律处分
- 交易所重点风险事件

为何不进第一期主链：

1. 接口和页面结构分散
2. 规则复杂度更高
3. 当前先把公告/研报主链跑通更值

官方入口：

- 上交所问询监管：
  https://www.sse.com.cn/regulation/supervision/inquiries/
- 深交所监管问询：
  https://www.szse.cn/disclosure/supervision/inquire/

## 5. Rejected Sources

### 5.1 Reject as historical primary: `AKShare stock_news_em`

原因：

1. 历史深度不够到 `2025-01`
2. 属于搜索结果型媒体流，不是完整归档
3. 对 replay 历史窗存在天然缺口

结论：

- 保留为近端增强
- 不进入历史主链

### 5.2 Reject for v1: generic portal crawling

包括但不限于：

- 新浪财经
- 财联社网页层
- 证券时报网搜索抓取
- 通用网页搜索 API

原因：

1. 历史分页和稳定性不可靠
2. 个股映射脏
3. PIT 边界难控
4. 去重和事件归并成本高

## 6. Architecture

### 6.1 Two-layer news architecture

#### Layer A: Near-end media news

来源：

- `akshare_stock_news_em`

事件族：

- `recent_media_news`

窗口：

- 近端 `3d / 5d`

用途：

- 当前 dossier 的媒体关注、短催化、短风险摘要

#### Layer B: Historical replacement source chain

来源：

- `cninfo_disclosure_announcement`
- `eastmoney_individual_notice`
- `eastmoney_research_report`

事件族：

- `disclosure_notice`
- `institution_report`

窗口：

- `2025-01-01..至今`

用途：

- historical replay
- Top10 历史解释
- 风险/催化/机构关注特征

### 6.2 Add `event_family`

建议在 source rows 的统一 schema 中新增：

- `event_family`

允许值：

- `recent_media_news`
- `disclosure_notice`
- `institution_report`
- `regulatory_event`

原因：

1. 媒体新闻和法定公告不能混成同一种热度
2. 下游特征需要分来源解释
3. dossier 需要区分“媒体关注”和“硬事件”

## 7. Provider Contract

### 7.1 `cninfo_disclosure_announcement`

标准化字段：

- `source_event_id`
- `source_name = cninfo_disclosure_announcement`
- `event_family = disclosure_notice`
- `source_channel = cninfo_disclosure`
- `title`
- `content = ""` 允许为空
- `published_at`
- `url`
- `language = zh`
- `asset_id`
- `ts_code`
- `stock_name`
- `metadata`

`metadata` 建议保留：

- `announcement_type` 若可判定
- `announcement_id`
- `org_id`
- 原始返回字段

### 7.2 `eastmoney_individual_notice`

标准化字段：

- `source_event_id`
- `source_name = eastmoney_individual_notice`
- `event_family = disclosure_notice`
- `source_channel = eastmoney_notice`
- `title`
- `content = ""`
- `published_at`
- `url`
- `language = zh`
- `asset_id`
- `ts_code`
- `stock_name`
- `metadata`

`metadata` 建议保留：

- `notice_type`
- 原始 `代码/名称/公告类型`

### 7.3 `eastmoney_research_report`

标准化字段：

- `source_event_id`
- `source_name = eastmoney_research_report`
- `event_family = institution_report`
- `source_channel = eastmoney_research`
- `title`
- `content = ""`
- `published_at`
- `url`
- `language = zh`
- `asset_id`
- `ts_code`
- `stock_name`
- `metadata`

`metadata` 建议保留：

- `broker_name`
- `rating`
- `industry`
- `target_pe_fields`
- `profit_forecast_fields`
- `pdf_url`

## 8. Feature Strategy

历史替代源进入特征层时，不与现有近端媒体新闻直接混算一组。

建议拆成三组：

### 8.1 Disclosure notice features

示例：

- `notice_count_3d`
- `notice_count_10d`
- `risk_notice_count_20d`
- `earnings_notice_count_20d`
- `governance_notice_count_20d`
- `contract_investment_notice_count_20d`

### 8.2 Institution report features

示例：

- `research_report_count_20d`
- `rating_action_count_20d`
- `target_price_available_flag`
- `profit_forecast_available_flag`
- `broker_coverage_count_90d`

### 8.3 Near-end media features

继续保留现有：

- `news_count_1d`
- `news_count_3d`
- `headline_*`
- `news_compact_summary`

## 9. Historical Backfill Policy

历史回填主口径继续只做：

- `Top10`
- replay-only

但 source 组合从原来的：

- `akshare_stock_news_em`

改成：

- `cninfo_disclosure_announcement`
- `eastmoney_individual_notice`
- `eastmoney_research_report`

`stock_news_em` 仍可作为补充近端源，但不再要求它覆盖整个历史窗。

## 10. Recommended Build Order

### Phase 1

先接：

1. `eastmoney_individual_notice`
2. `eastmoney_research_report`

原因：

- 接入成本最低
- AKShare 现成
- 个股映射稳定

### Phase 2

再接：

3. `cninfo_disclosure_announcement`

原因：

- 官方源
- 对东财公告层形成交叉校验

### Phase 3

最后考虑：

4. `sse/szse regulatory inquiry`

## 11. Output Expectation

替代源方案落地后，`2025-01-01..至今` 的历史 Top10 回填应至少做到：

1. 公告/研报层覆盖不再是 0
2. 大多数 `Top10` 历史候选都能匹配到：
   - 公告事件
   - 或机构研报
3. dossier / diagnostics 可以区分：
   - 媒体关注
   - 硬公告催化
   - 机构支持
   - 风险披露

## 12. Success Criteria

本设计落地后，至少满足：

1. 不再把 `stock_news_em` 当历史主源
2. 至少接入 2 个真正具备历史深度的个股源
3. `2025-01-01..至今` 的样本窗能产出非空 source rows
4. 下游能按 `event_family` 区分事件类型
5. 历史 Top10 回填覆盖率显著高于现有 `stock_news_em` 方案

## 13. Recommendation

最终推荐口径：

- **近端新闻增强层**
  - `akshare_stock_news_em`

- **历史替代主链**
  - `eastmoney_individual_notice`
  - `eastmoney_research_report`
  - `cninfo_disclosure_announcement`

- **二期风险增强**
  - `sse/szse regulatory inquiry`

一句话总结：

> 历史层不要继续找“一个能补全一切的媒体新闻源”，而应采用“近端媒体新闻 + 历史公告/研报主链”的分层结构。
