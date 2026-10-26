# P0-C 财报日期语义与 PIT Gate 契约

## 日期字段语义（严格区分）

| 字段 | 含义 | 本库载体 | 粒度 |
|---|---|---|---|
| report_period_end | 报告所属期末 | `report_period` | date |
| announcement_date | 公开披露日期 | `announcement_date` | **date（无时刻）** |
| published_at | 披露具体时刻 | **不存在** | — |
| first_seen_at | 平台首次获取 | 无独立列，`updated_at` 近似（重抓会刷新） | timestamp |
| ingested_at | 入库时刻 | `updated_at`（min=首次，max=最近） | timestamp |
| revision_published_at | 重述披露时间 | 无显式列；多版本时=后一行 ann | — |
| as_of | 策略决策时点 | 调用方传入 | date/datetime |

**历史公开可用性** 与 **平台当时持有** 是两个维度：
`publicly_available_at_asof`（ann 语义）≠ `operationally_available_at_asof`（updated_at 语义，仅证据允许时给出）。

## 哨兵与缺失

- `announcement_date='1900-01-01'` = 日期缺失哨兵（balance 71 行 / cash_flow 22 行），**必须 fail-closed**，不得当作"很久以前已披露"；
- 同日披露无法区分盘前/盘后 → **保守可用政策：公告日 D 的数据自 D+1 起可知**；
- `report_period` 绝不可替代 `announcement_date`。

## 逻辑接口 `financial_pit_at`

实现：`src/stock_research/financial_pit.py`

```
financial_pit_at(conn, asset_id, as_of, statement_type,
                 report_period=None, version_policy='latest_public')
```

输出字段：report_period / statement_type / source / publication_evidence /
publicly_available_at_asof / operationally_available_at_asof /
selected_statement_version / restatement_of / pit_status /
restriction_reasons / evidence_trace。

pit_status 枚举：
| 值 | 含义 |
|---|---|
| verified_public | 唯一版本，公告日 < as_of |
| restated_selected | 同源多公告日版本，按 version_policy 选中 |
| not_yet_published | 期间已结束但公告日晚于等于 as_of |
| publication_date_missing | 仅有哨兵/NULL 公告日（fail-closed） |
| period_not_reported | 无任何行 |

version_policy：`latest_public` / `initial_public`，仅作用于 as_of 时点**已公开**的行。

## Gate 规则

- `not_yet_published` / `publication_date_missing` / `period_not_reported` → **不返回数字**，由调用方 fail-closed；
- `restated_selected` → 返回数字但附 restatement_of 证据链；
- `operationally_available_at_asof=False` → 数据当时已公开但平台尚未入库（operational gap），restriction_reasons 标注；
- 禁止 `COALESCE(新表, 旧表)` 绕过缺失；禁止用 updated_at 当公告日。

## 与现行消费者约定的差异（重要）

全库现有消费者用 `announcement_date <= as_of`（**同日可用**）。本契约采用 **D+1**。同日差异即潜在前视泄漏面——量化见 FINANCIAL_CONSUMER_RISK_MATRIX.md。接口本身不替换现有读层，是审计/新逻辑的统一入口。
