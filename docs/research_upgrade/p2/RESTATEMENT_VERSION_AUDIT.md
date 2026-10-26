# P0-D 初版财报、更正与追溯重述审计

## 版本保存机制

PK = (asset_id, report_period, report_type, announcement_date, source)。

| 情形 | 行为 | 评估 |
|---|---|---|
| 重述且公告日变化 | 新增行，旧版保留 | ✅ 机制上可追踪 |
| 重述且公告日不变 | UPSERT 原地覆盖 | ❌ 初始值永久丢失 |
| 重抓取内容不变 | UPSERT 同值更新 updated_at | 无害 |
| 供应商数值冲突 | 不同 source 各存一行 | ⚠️ 188,171 个 income 键 akshare/baostock revenue 不一致（见下） |

## 实测证据

- **多公告日键**：income 0 / balance 10 / cash_flow 9。抽查全部 10 个 balance 键：两个版本 `total_assets` 完全相同——全部为**再披露（re-announcement）**，非数值重述。
- **income_statement 5,213 资产、~55 万行，0 个数值级版本链**——不是"A 股从不重述"，而是两个源的实际行为：(a) 东财接口对同一期间只回传最新一条记录（其公告日多为初始日或最新披露日，实测 max ann=2026-08-31 对应半年报季末重传）；(b) 同公告日重述 → 覆盖。
- **结论：初版/重述数值对在当前库中不可重建**，统一标 `HISTORICAL_VERSION_MISSING`。不能把"当前行"倒填为"当时初始值"。
- **唯一取证源**：`raw_akshare.finance_payload` / `raw_baostock.finance_payload`（fetched_at + payload_hash，16,586+ 行）——同一期间多次抓取且 payload_hash 不同 = 数值变化证据；hash 相同 = 无变化。修复阶段应以此为重述检测基线。

## 跨供应商冲突（另一类"版本"）

- income：188,171 个 (asset,period) 键 akshare_em_profit_sheet 与 baostock revenue 不同（部分 np_parent 也不同）。量级过大，主要疑因为口径/精度差异（baostock 字段映射 vs 东财全表），而非全部是真冲突——需在修复阶段抽样归因。
- 消费端 `point_in_time_finance` 按 ann desc/period desc 取一行 → **同键多源时选哪一家取决于公告日排序，无 source 偏好规则**——同一 as_of 可能因供应商重抓而换源。

## 版本选择策略（financial_pit.version_policy）

- `latest_public`：as_of 时点已公开的各版本中取公告日最新——回测默认；
- `initial_public`：取最早公告日版本——用于"初版披露"研究；
- 二者都只在 `announcement_date < as_of` 的行中选（D+1 保守）。

## 修复方向（不改库）

1. 对 raw_*_payload 按 (asset,period) × fetched_at 做 hash 序列 → 重建真实重述事件清单；
2. 需要版本化时新增 `statement_version`/`supersedes` 列（additive），写方改为版本追加而非同键覆盖；
3. 同键多源消费方需显式 source 优先序（建议 baostock 指标表走 indicator_quarter，三表以 akshare_em 为准），写进契约。
