# Top10 Historical News Backfill Design

## 1. Goal

为 `mid_trend_shadow_top10` 的历史样本补齐新闻增强数据，形成一条可复盘的 `Top10 historical news backfill` 链路，用于验证：

1. 哪些日期和股票真实出现了新闻共振；
2. `news_compact_summary` 在历史样本中是否有解释力；
3. 哪些短句模式更常对应强票或风险票。

本轮目标不是：

- 建全市场新闻库；
- 做 Top50/Top500 新闻回填；
- 把新闻直接接入策略打分。

本轮只做：

- `Top10`
- `2025-01-02..2026-05-19`
- replay-only historical backfill

## 2. Scope

输入主口径：

- [mid_trend_shadow_top10.csv](/Users/xiwei/stock_research/outputs/research/mid_trend_shadow_top10.csv)

当前已确认范围：

- `trade_date` 最小值：`2025-01-02`
- `trade_date` 最大值：`2026-05-19`
- 总行数：`3243`
- 总交易日：`328`

涉及模块：

1. `src/stock_research/news_source_backfill.py`
2. `src/stock_research/news_features.py`
3. `src/stock_research/topn_news_enrichment.py`
4. `src/stock_research/cli.py`

测试：

1. `tests/test_public_news_fallback_adapter.py`
2. `tests/test_news_features.py`
3. `tests/test_topn_news_enrichment.py`

不改：

- `mid_trend_position_dossier.py`
- `news_source_backfill` 的单日 `topn-news-source-backfill` 现有接口
- 策略排序逻辑

## 3. Historical Backfill Policy

### 3.1 Primary universe

历史回填主口径只使用 `Top10`。

原因：

- 当前真实决策支持链围绕 `Top5/Top10`；
- 新闻源仍是 public fallback，噪音成本较高；
- 先把高价值候选补全，比直接放大到 `Top50` 更合理。

### 3.2 Window

历史窗口固定为：

- `2025-01-02`
- 到 `2026-05-19`

这不是“今天为止”的全量市场新闻库，而是**当前已有历史 Top10 样本窗**。

### 3.3 Replay only

这条链路只允许：

- `replay`

不允许：

- `live`

因为目标是历史复盘，不是当天辅助判断。

## 4. Output Model

本轮不直接写数据库。

先采用：

- 文件产物

原因：

- 先验证回填链是否可持续运行；
- 避免把未审计的历史 public news 数据直接写进正式库；
- 便于先做人审和覆盖审计。

如果这一版稳定，再考虑增量写库。

## 5. Pipeline

历史回填链路分四步。

### 5.1 Historical candidate source

从 `mid_trend_shadow_top10.csv` 提取：

- `trade_date`
- `asset_id`
- `ts_code`
- `stock_name`

按交易日切片。

### 5.2 Historical source backfill

对每个 `trade_date` 的 Top10 候选，调用现有 public fallback source：

- `akshare_stock_news_em`

生成：

- `news_source_backfill_events.csv`

并继续保留：

- `matched_candidates`

### 5.3 Historical feature backfill

基于 source events 生成：

- `news_feature_mentions.csv`
- `news_feature_daily.csv`

模式固定：

- `replay`

### 5.4 Historical enrichment

基于每个 trade_date 的 Top10 候选和 feature 文件生成：

- `topn_news_enrichment.csv`

要求：

- 包含现有大类摘要；
- 包含子类摘要；
- 包含 `news_compact_summary`。

## 6. New Command

建议新增一个专用 CLI，而不是强行复用单日命令。

命令：

```bash
stock-research historical-top10-news-backfill \
  --top10-path outputs/research/mid_trend_shadow_top10.csv \
  --start-date 2025-01-02 \
  --end-date 2026-05-19 \
  --provider akshare_stock_news_em \
  --output-dir outputs/research/top10_historical_news_backfill_20250102_20260519
```

参数：

- `--top10-path`
- `--start-date`
- `--end-date`
- `--provider`
- `--sample-trade-dates` 可选
- `--output-dir`

### 6.1 `--sample-trade-dates`

用于小样本 smoke，不是正式回填主口径。

例如：

- `--sample-trade-dates 20`

表示只取窗口内前 20 个交易日做快速试跑。

## 7. Output Files

建议输出：

- `historical_top10_candidates.csv`
- `historical_news_source_events.csv`
- `historical_news_feature_mentions.csv`
- `historical_news_feature_daily.csv`
- `historical_top10_news_enrichment.csv`
- `historical_top10_news_backfill_summary.csv`
- `historical_top10_news_backfill_report.md`

## 8. Summary Metrics

`historical_top10_news_backfill_summary.csv` 至少包含：

- `trade_date_count`
- `candidate_rows`
- `unique_ts_code_count`
- `source_event_rows`
- `mention_rows`
- `feature_rows`
- `enrichment_rows`
- `coverage_rows`
- `coverage_rate`
- `compact_summary_nonempty_rows`
- `capital_broker_resonance_rows`
- `risk_without_catalyst_rows`

## 9. Report Questions

`historical_top10_news_backfill_report.md` 重点回答：

1. 历史 Top10 有多少行能拿到新闻覆盖？
2. `news_compact_summary` 非空比例是多少？
3. 哪类 compact summary 最常见？
4. `资金 + 券商共振` 在历史上出现了多少次？
5. `风险但无新增催化` 在历史上出现了多少次？
6. 哪些日期/股票最值得回看？

## 10. Non-Goals

本轮不做：

- `Top50 historical news backfill`
- 全市场新闻数据库
- 自动写入 `research.news_*`
- LLM 摘要
- 新闻直接用于选股打分
