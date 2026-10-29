# POLICY_SOURCE_AUDIT — 政策事件来源审计

`POLICY_EVENTS.csv` 共 11 条：official_action 5、official_document 2、official_statement 1、broker_interpretation 1、hypothesis 2。

## 核实方式

| 日期 | 事件 | 核实状态 |
|---|---|---|
| 2022-03-16 | 金融委专题会议 | 官方通稿事实，URL 为政府网站域名（未逐字复核全文） |
| 2023-08-27 | 印花税减半等 | 官方发布事实 |
| 2023-10-11 | 汇金增持四大行 | 汇金官网公告列表确认（huijin-inv.cn） |
| 2023-10-23 | 汇金买入ETF公告 | **已核实**：新华网 c_1129933214 + 汇金官网公告 |
| 2024-02-06 | 汇金扩大增持+证监会表态 | 用户提供的 csrc 出处，与公开报道一致 |
| 2024-04-12 | 新国九条 | 国务院文件事实 |
| 2024-09-24 | SFISF+回购增持再贷款 | 国新办发布会，多方官方报道一致 |
| 2025-01-22 | 中长期资金入市方案 | **已核实**：csrc 原文页 c7535174 + 新华社 |
| 2025-04-07 | 汇金/诚通/国新增持 | confidence=medium：日期按媒体集中报道（4-7/4-8），未逐条复核公告号 |

## 分层纪律

- `broker_interpretation`（2026-01 慢牛解读）与 `hypothesis`（2026-07 托底归因）只作背景，**不进入信号、不作为事实**。
- `policy_on` 标记只用 official_action/official_document 日期；`publication_date` 与 `event_date` 同日处理（公告收盘后发布的，市场影响自次日，但本研究仅作状态分层、不构造交易信号，故从宽）。
- 未覆盖所有官方表态（抽样重要节点）；后续扩充需逐条补 URL 与公告号。
