# P1-D 公告证据分级与最终核销

## 双源一键一对核验

| 检查 | 结果 |
|---|---|
| `COUNT(DISTINCT asset_id, report_period, report_type)` ∩（akshare_em_profit_sheet × baostock） | **230,363** |
| akshare_em_profit_sheet 侧同键多行 | **0**（每键严格一行） |
| baostock 侧同键多行 | **0** |
| 结论 | 230,363 确为精确一键一对 join，无多版本倍增污染 |

## Q2 14 只证据等级终态

| 等级 | 含义 | 数量 | 资产 |
|---|---|---|---|
| L3 external_announcement | 有公司公告/交易所决定文本证据（存档于 recon JSON） | 1 | CN:SZ:002731（*ST萃华） |
| L2 db_delist_plus_source_absent | asset_master 退市日 + EM 断供 + DB 末期 2026-03-31 | 13 | 600193/600421/600599/600608/600636/600696/605081/688287/000004/000638/002808/002898/300029 |

## 002731 证据明细（复核后）

- 公司公告 2026-09-01：未能在法定期限（2026-08-31）披露 2026 半年报（前期财务数据及期初数无法确认）——证据形态为 **recon 存档描述性引用**（epaper.cs.com.cn / 深交所公告渠道标注），**无公告编号/URL 逐条存档**；
- 深交所终止上市决定 2026-10-15；退市整理期 2026-10-23 起，预计最后交易日 2026-11-12；
- DB 核验（2026-10-22 recon）：三表最新报告期均 2025-09-30，库内无 2026Q2 行；本轮复核 `asset_master.delist_date` 仍为 NULL（退市整理中）；
- **independent_verification: UNKNOWN_with_stored_descriptive_evidence** — 不声称已逐条核对公告原件，证据等级如实标注。
