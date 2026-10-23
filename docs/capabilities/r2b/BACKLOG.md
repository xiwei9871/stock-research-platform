# R2B 剩余 backlog 对照（CAP / DATA）

## DATA 线缺口（28 条去重，`gap_backlog_r2b.csv`）

| 类型 | 数量 | 代表项 | 说明 |
|---|---|---|---|
| missing_source | 25 | product_revenue:{002837,301018,002050,603757,688037,002371,688686}、product_gross_margin:*、verifiable_order:* | 产品线收入/毛利/可核实订单均缺一手来源——兑现阶段的主要解锁项 |
| attribution_unknown | 3 | product_gross_margin:002371 等 | 板块毛利存在但产品线不可归属 |

## CAP 线覆盖缺口

- ai_power：12 主题节点无案例（`coverage_gap_nodes`，owner CAP-02）
- humanoid：20 主题节点无案例
- semi_equipment：无 theme_db 包，仅 case 模式（1 节点）

## 验证任务（`verification_tasks`，只读 proposed）

| 主题 | 总数 | high | 主要方向 |
|---|---|---|---|
| ai_power | 46 | 10 | 各节点 supply_scarcity/cert_barrier 决定性缺口（capacity_or_leadtime、customer_cert_cycle_cost 等） |
| humanoid | 27 | 4 | 视觉节点四假设 decisive gaps + hype 独立证据 |
| semi_equipment | 8 | 3 | process_monopoly/cert_barrier/perf_gap 未决假设 |

## 结构性遗留

- 现金回款阶段：T3 无 `cash_collections` 记录类型——需 DATA 定义产品线回款归属来源
- 主题场景归属：产品线收入无法区分"同产品线内特定场景订单"（如人形 vs 工业视觉）
- CAP-09 任务清单未接研究任务队列（复用队列另行立项）
- CAP-10 与正式回测集成：另行授权
