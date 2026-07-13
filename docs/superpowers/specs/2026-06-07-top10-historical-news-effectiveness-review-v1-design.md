# Top10 Historical News Effectiveness Review v1 Design

## 1. Goal

基于已经完成的：

- `outputs/research/top10_historical_news_backfill_20250102_20260519_replacement`

做第一轮历史效果复盘，回答：

1. 历史新闻/公告/研报覆盖本身是否具有解释力；
2. 哪些历史事件特征更像机会确认，哪些更像风险提示；
3. `historical_event_summary` 这种人读摘要是否对应更好的后续表现；
4. 公告类与研报类，在 `Top10` 样本中哪类更有统计价值。

本轮目标不是：

- 把新闻重新接入策略排序；
- 做新的新闻打分模型；
- 做复杂 NLP / LLM 事件分类；
- 做全市场新闻效果研究。

本轮只做：

- `Top10`
- `2025-01-02..2026-05-19`
- 基于现有历史回填产物的 replay 诊断

## 2. Scope

### 2.1 Inputs

主输入：

- [historical_top10_candidates.csv](/Users/xiwei/stock_research/outputs/research/top10_historical_news_backfill_20250102_20260519_replacement/historical_top10_candidates.csv)
- [historical_news_feature_daily.csv](/Users/xiwei/stock_research/outputs/research/top10_historical_news_backfill_20250102_20260519_replacement/historical_news_feature_daily.csv)
- [historical_top10_news_enrichment.csv](/Users/xiwei/stock_research/outputs/research/top10_historical_news_backfill_20250102_20260519_replacement/historical_top10_news_enrichment.csv)

价格标签输入：

- `public.market_daily_bar`
- 主口径：`adjust_type = qfq`

### 2.2 Modules

建议新增：

- `src/stock_research/top10_historical_news_effectiveness_review.py`

CLI：

- `stock-research review-top10-historical-news-effectiveness`

测试：

- `tests/test_top10_historical_news_effectiveness_review.py`

### 2.3 Non-goals

不改：

- `news_source_backfill.py`
- `news_features.py`
- `topn_news_enrichment.py`
- `mid_trend_position_dossier.py`
- 现有策略排序逻辑

## 3. Research Questions

本轮报告重点回答：

1. `coverage` 是否有用
   - `coverage_rows` 对应的样本，后续收益是否优于 `unknown/no coverage`

2. `historical_event_summary` 是否有用
   - 有摘要的样本，后续表现是否更稳定

3. 公告 vs 研报
   - `notice_count_*` 和 `research_report_count_20d` 哪个更有解释力

4. 事件强度是否单调
   - `notice_count_3d / notice_count_10d`
   - `research_report_count_20d`
   是否存在分层单调性

5. 风险事件是否更像负面过滤
   - `risk_notice_count_20d`
   - `rating_action_count_20d = 0` 但存在 notice
   是否更像风险提示

## 4. Chosen Review Structure

本轮分三层做。

### 4.1 Coverage layer

先做最基础的覆盖分层：

- `has_news_feature`
- `news_attention_level != unknown`
- `historical_event_summary 非空`

### 4.2 Source-type layer

按事件来源做分层：

- `notice_only`
- `report_only`
- `notice_and_report`
- `no_historical_event`

判定口径：

- `notice_count_10d > 0`
- `research_report_count_20d > 0`

### 4.3 Feature-intensity layer

对以下字段做强度分层：

- `notice_count_3d`
- `notice_count_10d`
- `research_report_count_20d`
- `rating_action_count_20d`
- `risk_notice_count_20d`

其中：

- `notice_count_3d / notice_count_10d / research_report_count_20d`
  适合做 bucket / monotonic review
- `risk_notice_count_20d`
  更偏 risk filter review

## 5. Outcome Labels

使用后续收益做诊断，不进入选股。

建议生成：

- `future_1d_return`
- `future_3d_return`
- `future_5d_return`
- `future_10d_return`
- `future_20d_return`

并补：

- `future_5d_max_drawdown`
- `future_10d_max_drawdown`
- `future_20d_max_drawdown`

价格口径：

- 来自 `public.market_daily_bar`
- `adjust_type = qfq`

## 6. Join Policy

join 键：

- `trade_date`
- `asset_id`

顺序：

1. `historical_top10_candidates`
2. left join `historical_news_feature_daily`
3. left join `historical_top10_news_enrichment`
4. left join future-return label frame

要求：

- 不因为 feature/enrichment 缺失而丢候选行；
- 缺失样本保留，用于比较 `covered vs uncovered`。

## 7. Output Files

建议输出：

- `top10_historical_news_effectiveness_base.csv`
- `top10_historical_news_effectiveness_coverage_summary.csv`
- `top10_historical_news_effectiveness_source_type_summary.csv`
- `top10_historical_news_effectiveness_feature_bucket_summary.csv`
- `top10_historical_news_effectiveness_report.md`

## 8. Summary Tables

### 8.1 Coverage summary

字段：

- `coverage_group`
- `sample_count`
- `avg_future_1d_return`
- `avg_future_3d_return`
- `avg_future_5d_return`
- `avg_future_10d_return`
- `avg_future_20d_return`
- `win_rate_5d`
- `win_rate_10d`
- `avg_future_10d_max_drawdown`
- `avg_future_20d_max_drawdown`

建议分组：

- `no_news_feature`
- `news_feature_only`
- `historical_summary_present`

### 8.2 Source-type summary

字段：

- `source_type_group`
- `sample_count`
- `avg_future_1d_return`
- `avg_future_3d_return`
- `avg_future_5d_return`
- `avg_future_10d_return`
- `avg_future_20d_return`
- `win_rate_5d`
- `win_rate_10d`
- `avg_future_20d_max_drawdown`

建议分组：

- `notice_only`
- `report_only`
- `notice_and_report`
- `no_historical_event`

### 8.3 Feature bucket summary

字段：

- `feature_name`
- `bucket`
- `sample_count`
- `avg_future_3d_return`
- `avg_future_5d_return`
- `avg_future_10d_return`
- `avg_future_20d_return`
- `win_rate_5d`
- `avg_future_10d_max_drawdown`

建议 bucket 数：

- 先做 `0 / 1 / 2+`

原因：

- 这批历史事件特征是离散计数，没必要先上 10 分位。

## 9. Interpretation Rules

本轮只做解释，不下策略结论。

### 9.1 Useful signal

如果某分层同时满足：

1. `sample_count` 不太小；
2. `avg_future_5d_return / avg_future_10d_return` 为正；
3. `win_rate_5d / win_rate_10d` 高于对照组；
4. 回撤没有显著恶化；

可标记为：

- `useful_signal`

### 9.2 Risk signal

如果某分层满足：

1. 收益不佳或为负；
2. `future_max_drawdown` 更差；
3. 胜率更低；

则标记为：

- `risk_signal`

### 9.3 Weak signal

如果有方向但不稳定，或 `sample_count` 太少：

- `weak_signal`

## 10. Report Questions

`top10_historical_news_effectiveness_report.md` 重点回答：

1. 历史事件覆盖是否比无覆盖更有用；
2. `historical_event_summary` 非空是否对应更好的后续表现；
3. `notice_only / report_only / notice_and_report` 哪类最好；
4. `risk_notice_count_20d` 是否更像 risk filter；
5. 是否值得把部分历史事件字段进入下一轮策略诊断层。

## 11. CLI

建议命令：

```bash
stock-research review-top10-historical-news-effectiveness \
  --base-dir outputs/research/top10_historical_news_backfill_20250102_20260519_replacement \
  --adjust-type qfq \
  --output-dir outputs/research/top10_historical_news_effectiveness_review_v1
```

参数：

- `--base-dir`
- `--adjust-type`
- `--output-dir`

## 12. Tests

至少覆盖：

1. 能从 base/enrichment/features 拼出完整 base frame；
2. future return labels 能生成；
3. `coverage_summary` 能生成；
4. `source_type_summary` 能生成；
5. `feature_bucket_summary` 能生成；
6. 缺失 feature/enrichment 时不崩；
7. 报告文件能生成。

## 13. Recommendation

下一步不再继续扩接入层，先做：

- `Top10 historical news effectiveness review v1`

先回答“这些历史事件字段有没有解释力”，再决定是否：

1. 把 `cninfo` 纳入正式默认历史主链；
2. 把某些事件字段推进到更正式的策略诊断层；
3. 把历史事件类型做更细分类。
