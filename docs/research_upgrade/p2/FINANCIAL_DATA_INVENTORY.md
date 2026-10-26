# P0-A 财务数据资产与消费链盘点

审计时点：2026-10-23（只读，生产零写入）。复现脚本：`scripts/p2_financial_pit_audit.py`，原始数据 `docs/research_upgrade/p2/audit_summary.json`。

## 核心三表

| schema.table | row_count | asset_count | period_range | source 分布 | primary_key | updated_at | publication_date_field | revision_field |
|---|---|---|---|---|---|---|---|---|
| finance.income_statement | 549,987 | 5,213 | 1988-12-31..2026-06-30 | akshare_em_profit_sheet 314,404 / baostock 235,583 | (asset_id, report_period, report_type, announcement_date, source) | 2026-05-10..2026-10-20 | announcement_date (date 粒度) | **无显式字段**；版本靠 PK 中 announcement_date 区分 |
| finance.balance_sheet | 313,734 | 5,213 | 1989-12-31..2026-09-30 | akshare_em 309,669 / akshare_sina 4,065 | 同上 | 2026-05-11..2026-10-23 | 同上；71 行为 '1900-01-01' 哨兵（9 资产） | 同上 |
| finance.cash_flow | 313,006 | 5,213 | 1996-12-31..2026-09-30 | akshare_em 308,880 / akshare_sina 4,126 | 同上 | 同上 | 同上；22 行哨兵（11 资产） | 同上 |

## 辅助表

| schema.table | 说明 |
|---|---|
| finance.indicator_quarter | baostock 衍生指标（roe/roa/margins/yoy 等），PK 含 `calc_version`——唯一带显式版本列的财务表 |
| finance.share_capital_event | 股本变动事件，PK (asset_id,event_date,source)，announcement_date 可 NULL |
| event.earnings_express / event.earnings_forecast | 业绩快报/预告，含 payload_hash、source_endpoint |
| raw_akshare.finance_payload | 16,586 行原始 JSON 载荷（fetched_at + payload_hash）——**唯一的取证级 PIT 证据源** |
| raw_baostock.finance_payload | 同上，baostock 侧原始载荷 |

## 写入方与 UPSERT 规则（P0 风险裁决）

`loaders/baostock_finance_ingestion.py`、`loaders/akshare_finance_statements.py`：
`ON CONFLICT (asset_id, report_period, report_type, announcement_date, source)`。

- 新公告日的重述 → **新增一行**（版本被 PK 天然保留）；
- **同一公告日但数值变化 → 原地覆盖**（UPSERT 更新同键行）——这是确认存在的初始版本丢失通道；
- 实测：income 0 个多公告日键、balance 10 个（值全同，属再披露）、cash_flow 9 个（同）→ 库内**无任何一次数值级重述被完整保留**，`HISTORICAL_VERSION_MISSING` 风险成立。

## 消费链

| 消费者 | 入口 | PIT 过滤 | 语义 |
|---|---|---|---|
| factor_pipeline → services.point_in_time_finance | get_latest_*_rows | `announcement_date <= trade_date` | **同日可用**约定 |
| services.finance_ttm | load_income_ttm_rows | `announcement_date <= trade_date` + 报告期 desc 排序 | 同日可用 + TTM 累计差分 |
| fundamental_pipeline | latest income/balance join | `announcement_date <= as_of` | 同日可用 |
| midtrend_pit_fundamental_features | 各表 pick_first | 自查 `announcement_date > trade_date → lookahead` 标记 | 同日可用 |
| dashboard asset_profile_fundamentals | anchor_row | `announcement_date <= %s` | 同日可用 |
| loaders/akshare_finance_statements、baostock_finance_ingestion | 写入方 | — | 上表 UPSERT |

**全库约定为"公告日当天可用"**。只有日期粒度、无发布时间字段 → 盘后公告会被当日回测使用——见 CONSUMER_RISK_MATRIX。
