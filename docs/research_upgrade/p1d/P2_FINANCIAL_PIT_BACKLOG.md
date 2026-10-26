# P2_FINANCIAL_PIT_BACKLOG — 财务 PIT 审计待办（仅接口+缺口清单，不启动抓取）

P1d 完成后移交 DATA-R3-P2 的准备工作。**本阶段不启动大规模财务抓取。**

## 现状基线（Q2 2026-06-30 universe=5,213 实测）

`akshare_q2_reconciliation.json`：balance+cashflow 双表齐备 **5,199**；双缺 **14**。

## 待建接口（逻辑目标，非已实现）

`financial_pit_at(asset_id, as_of_date) -> {report_period, publication_date, available_at_asof, statement_version, restatement_of}`

要求复用 `tradeability_at` 同一模式：PIT 判定不读当前态字段回写历史。

## P0 审计项（下一阶段）

1. **三表历史季度覆盖**：income/balance/cashflow 分表分季度的资产-期间矩阵；标出哪些季度链断裂（尤其 2018 前、北交所纳入时点、退市股末季）。
2. **`report_period` vs `publication_date` 分离核验**：确认所有三表行带真实披露日（非法定截止日近似）；找出 publication_date 缺失/用 report_period 回填的行——它们会产生前视偏差。
3. **更正与追溯重述版本**：同一 report_period 多版本行的处理策略（最新版? 初版 PIT?）；核对现有 ingestion 是否 UPSERT 覆盖（覆盖 = 历史初版不可复现 = 前视偏差源）。
4. **时点可用性函数**：`t` 时刻某资产某季度数据是否已披露（PIT join：publication_date ≤ t），与 P1d tradeability 同维度并入回测资格。
5. **Q2 universe 覆盖终态**：5,199/5,213 已核实；14 缺口的最终来源证据收口：
   - `source_unavailable_delisted` 13 只（600193/600421/600599/600608/600636/600696/605081/688287/000004/000638/002808/002898/300029）：2026-06/07 退市，EM 接口不再供数，DB 最新期 2026-03-31——**须逐源核实披露截止日前是否已发合法半年报**（不预设 truly_undisclosed）。
   - `truly_undisclosed_at_deadline` 1 只：披露期内确未披露（名单见 reconciliation JSON）。
6. **退市股数据存续策略**：EM 对退市股断供 → PIT 口径下"退市前已披露数据是否保留"必须明确（否则历史回测会丢失这些股票的真实财报 = 存活偏差另一形态，与 P1d 退市宇宙问题同源）。

## 不做项（明确隔离）

- 不启动新一轮 akshare/EM 批量抓取（避免 baostock 黑名单同类事故 + 超出任务书范围）。
- 不修改现有三表 ingestion 语义；P2 先出审计矩阵再定修复。

## 与 P1d 的衔接点

`tradeability_at` 输出已含 `data_version` 维度；财务 PIT 就绪后，`data_ready_*` 家族可扩展 `data_ready_fundamentals`，`restriction_reasons` 增加 `fundamentals_not_published`——接口预留，实现待授权。
