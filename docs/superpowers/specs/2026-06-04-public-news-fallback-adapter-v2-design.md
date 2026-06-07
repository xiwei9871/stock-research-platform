# Public News Fallback Adapter v2 Design

## 1. Goal

在不购买 `Tushare` 新闻权限的前提下，给现有新闻链补一条可运行的公开源 fallback 路线，使这条链：

- 能为 `Top5/Top10` 提供真实新闻输入；
- 能继续复用现有的：
  - `news_feature_backfill`
  - `topn_news_enrichment`
  - `mid_trend_position_dossier`
- 不需要推倒已完成的数据层、特征层、dossier 集成。

## 2. Current Problem

当前真实链路已经跑通过一次，但结果是：

- `news-source-backfill -> permission_denied`
- `news_feature_mentions.csv -> 0 rows`
- `news_feature_daily.csv -> 0 rows`
- `topn_news_enrichment.csv -> 全部 unknown / thin`

这说明工程链已经通，但**新闻源不可用**，而不是 feature/enrichment/dossier 有根本性问题。

因此下一步不是重写后半段，而是替换 `source` 层。

## 3. Scope

v2 只做公开源 fallback adapter：

1. `AKShare stock_news_em`
2. `CNInfo announcement / search-based announcement adapter`

v2 不做：

- 新的新闻评分体系
- 新闻直接接入全市场打分
- LLM 自由摘要
- 新闻与公告统一事件引擎
- 舆情/社媒/论坛

## 4. Chosen Strategy

采用两层 source 策略：

### Layer A: TopN 个股新闻

优先接：

- `AKShare stock_news_em`

用途：

- 给 `Top5/Top10` 直接补个股新闻
- 解决“新闻链完全空白”的问题

### Layer B: 法定公告事件

补充接：

- `CNInfo` 公告检索/抓取

用途：

- 为风险事件提供更硬的公告层信号
- 补足“新闻不一定覆盖，但公告必须披露”的场景

## 5. Why This Order

### 5.1 AKShare first

`AKShare stock_news_em` 最适合当前阶段，原因是：

1. 它是个股维度；
2. 不需要先做复杂主题映射；
3. 和当前 `Top5/Top10` 工作流天然匹配；
4. 接入成本最低；
5. 能最快把 dossier 里的“新闻/催化跟踪”从空白变成可读。

官方文档：

- `AKShare 股票数据` 文档中明确有 `stock_news_em(symbol=...)`，描述为“东方财富指定个股的新闻资讯数据”。
- 文档地址：
  https://akshare.akfamily.xyz/data/stock/stock.html

### 5.2 CNInfo second

`CNInfo` 更适合作为公告/硬事件层，而不是直接替代新闻层，原因是：

1. 它是法定披露平台，适合风险和公告事件；
2. 它不是天然的“个股新闻流”接口；
3. 对研究来说价值高，但更偏：
   - 公告
   - 风险提示
   - 定期报告
   - 交易异动说明

官方站点：

- https://www.cninfo.com.cn/

## 6. Source Positioning

### 6.1 AKShare stock news

定位：

- `news-like source`

适合填充：

- `title`
- `published_at`
- `source_name`
- `url`
- `content/summary`

### 6.2 CNInfo announcements

定位：

- `event-like disclosure source`

适合填充：

- 风险公告
- 业绩预告/快报
- 重大合同
- 问询/监管/澄清
- 减持/停牌/异动说明

因此 v2 不应强行把两者混成同一种“新闻热度”。

## 7. Architecture

在现有 `news_source_backfill.py` 上扩展 provider，不推倒现有 contract。

### 7.1 Keep existing downstream contracts

保留：

- `research.news_event_source`
- `research.news_event_mention`
- `research.news_feature_daily`
- `topn_news_enrichment.csv`
- dossier news block

### 7.2 Expand source provider layer

新增两个 provider：

- `akshare_stock_news_em`
- `cninfo_announcement`

建议模块边界：

- `news_source_backfill.py`
  - 保留统一 runner
  - 增加 provider dispatch

若文件开始变大，可拆：

- `news_source_backfill_akshare.py`
- `news_source_backfill_cninfo.py`

但 v2 第一版可以先保守留在一个模块里。

## 8. Provider Contracts

### 8.1 `akshare_stock_news_em`

输入：

- `symbol`

输出需要标准化成现有 `news_event_source` 行：

- `source_event_id`
- `source_name = akshare_stock_news_em`
- `source_channel = eastmoney_stock_news`
- `title`
- `content`
- `published_at`
- `url`
- `language = zh`
- `metadata`

### 8.2 `cninfo_announcement`

输入：

- `ts_code` / `stock_name`
- `start_date`
- `end_date`

输出标准化为：

- `source_event_id`
- `source_name = cninfo_announcement`
- `source_channel = disclosure_announcement`
- `title`
- `content` 或空
- `published_at`
- `url`
- `language = zh`
- `metadata`

## 9. Runner Strategy Change

当前 `news-source-backfill` 是全窗拉源逻辑，适合 `Tushare news`。

v2 需要改成两种模式：

### 9.1 General range mode

保留给：

- `tushare`
- `cninfo`（如果能按时间检索）

### 9.2 TopN source mode

新增一个更适合当前项目的模式：

- 直接输入 `candidates_path`
- 只对 `Top5/Top10` 跑新闻源

这对 `akshare_stock_news_em` 尤其关键，因为它天然是个股接口。

建议新增 CLI：

```bash
stock-research topn-news-source-backfill \
  --candidates-path outputs/research/mid_trend_research_packet_20260602_pdf_enriched/mid_trend_research_packet_candidates.csv \
  --provider akshare_stock_news_em \
  --trade-date 2026-06-02 \
  --output-dir outputs/research
```

## 10. Why TopN Mode Matters

如果坚持全市场新闻拉取，会遇到三个问题：

1. 没必要；
2. 免费源更容易触发限流；
3. 你当前真正需要的是 `Top5/Top10` 解释层，而不是全市场新闻 alpha。

所以 v2 的主口径应当是：

> **先支持 TopN 定向新闻 backfill，再考虑全市场补数。**

## 11. Mention Strategy

### 11.1 AKShare stock news

AKShare 个股新闻本身就是按个股查的，所以：

- 返回事件时就可以直接附带候选资产
- `news_event_mention` 可以直接写一条高置信度 mention

这比全市场自由新闻的证券映射简单很多。

### 11.2 CNInfo announcements

公告检索通常天然带证券代码/简称，因此：

- 也可直接生成高置信度 mention

这意味着：

> v2 不需要先做复杂的 NLP 证券映射，也能得到高质量 TopN 新闻/公告输入。

## 12. Feature Layer Reuse

现有 `news_features.py` 可以直接复用。

只要 source 层输出标准化行：

- `source_event_id`
- `title`
- `content`
- `published_at`
- `source_name`
- `source_channel`

现有逻辑就能继续生成：

- `news_count_1d/3d/5d`
- `major_news_count_3d`
- `headline_keyword_positive_count_3d`
- `headline_keyword_risk_count_3d`
- `news_attention_level`

这也是为什么 v2 不该重做 feature 层。

## 13. Enrichment Layer Reuse

现有 `topn_news_enrichment.py` 继续复用。

只要 feature 表不是空的，就会开始生成：

- `news_consensus_summary`
- `news_risk_summary`
- `theme_catalyst_summary`
- `overnight_catalyst_note`
- `news_attention_level`

同时保留当前语义：

- missing coverage -> `unknown`
- `news_risk_attention_flag` missing -> `None`

## 14. Dossier Layer Reuse

现有 `mid_trend_position_dossier` 已经接好了：

- `--news-enrichment-path`
- `news_enrichment_provided`
- `news_enrichment_used`
- `matched_news_rows`

所以 v2 的主要任务不是再改 dossier，而是给 dossier 喂到真实可用的新闻输入。

## 15. Chosen v2 Rollout

### Phase 1

新增 `akshare_stock_news_em` provider。

目标：

- 跑通 `TopN news source backfill`
- 生成非空 `news_event_source`
- 让 `news_feature_backfill` / `topn_news_enrichment` / dossier 真正有内容

### Phase 2

新增 `cninfo_announcement` provider。

目标：

- 补风险类/公告类硬事件
- 给 dossier 增加更可信的风险说明

### Phase 3

再考虑是否要做：

- `source_priority`
- `news + announcement` 的去重与分层

## 16. Non-goals

v2 不做：

- 新闻情绪分数
- 全市场新闻打分
- LLM 摘要
- 新闻/公告统一事件引擎
- 社交媒体/论坛/舆情平台

## 17. Testing Requirements

v2 实现时至少覆盖：

1. `akshare_stock_news_em` provider 能生成标准化 source rows；
2. `cninfo_announcement` provider 能生成标准化 source rows；
3. `TopN source backfill` 能按候选票输出 source rows；
4. source rows 能直接喂进现有 `news_feature_backfill`；
5. 非空 source 能生成非空 feature；
6. 非空 feature 能生成非空 `topn_news_enrichment`；
7. dossier 能显示真实新闻块，而不只是 `unknown`；
8. 免费源为空/限流时不崩溃，只 warning；
9. 不破坏现有 replay-only diagnostics 口径。

## 18. Recommendation

下一步推荐按这个顺序做：

1. `AKShare stock_news_em` TopN adapter
2. 跑一版真实 `2026-06-02` 链路
3. 确认 dossier 里至少 1-2 只票出现真实新闻块
4. 再补 `CNInfo announcement` adapter

一句话：

> **不买 Tushare 权限的最现实做法，不是重做整个新闻系统，而是把 source 层切到 `AKShare 个股新闻 + 巨潮公告`，继续复用你已经打通的 feature/enrichment/dossier 链。**
