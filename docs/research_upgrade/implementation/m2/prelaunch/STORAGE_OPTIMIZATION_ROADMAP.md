# STORAGE-R1 优化路线图（决策矩阵）

原则：无损优先 —— 不删有效数据、不删索引为首选、保持查询能力。所有动作逐项审批。

## 阶段路线图

| 序 | 动作 | 空间收益 | 查询影响 | 成本 | 可回滚 | 风险 | 前置 | 状态 |
|---|---|---|---|---|---|---|---|---|
| R0 | **宿主 180GB 非 pgdata 归因**（管理员只读：`du /var/lib/docker`、`docker system df -v`、lsof +L1、journal 用量） | **0–180GB** | 无 | 低 | — | 低 | 宿主访问 | **READY_TO_REQUEST** |
| R1 | **恢复实例实验**（pgstattuple 测索引膨胀率；6 类 SQL 基线计时；索引合并方案 EXPLAIN 对照） | 0（产出证据） | 无 | 中 | — | 零 | 恢复完成（进行中） | RUNNING |
| R2 | **ANALYZE 陈旧统计表**（label/feature_snapshot 等从未 analyze 表） | 0 | **提升计划质量** | 低（只读统计刷新，需批准） | 是 | 极低 | 审批 | READY |
| R3 | **S1-a 索引膨胀修复**：若恢复实例证实膨胀>30% → `REINDEX INDEX CONCURRENTLY`（同定义，不丢能力） | 估 20–60GB | **提升** | 中（重建期间写放大+空间峰值，需等 R0 腾出空间） | 是（保留旧索引至切换） | 中 | R0+R1 | CONDITIONAL |
| R4 | **S1-b 索引合并**：若实例验证合并计划无损 → DROP 被覆盖索引 + CREATE 合并索引 CONCURRENTLY | 估 50–110GB | 需逐 SQL 验证 | 中高 | 是（重建 SQL 已备） | 中 | R1 证据充分 | BLOCKED_BY_EVIDENCE |
| R5 | **staging 保留期策略**（tdx/baostock 若证实已落地 market → 老数据 DELETE 分批） | ≤11GB | 无（staging 非查询路径） | 低 | 数据删后需备份回滚 | 低 | 键匹配率验证 | NEEDS_EVIDENCE |
| R6 | **S2 Parquet 试点**：minute_bar 2020–2023 导出 DuckDB 只读 + 双验 → 审批后 DROP 分区 | **~135GB+** | 分析型更快，点查需路由 | 高（管线+查询改造） | 是（NAS dump+parquet 双副本） | 中高 | R1+B0-C 恢复验证+审批 | DESIGN_READY |
| R7 | **遗留库 cn_a_stock_daily_*** | ~7.5GB | 无 | 低 | dump 后可回滚 | 低 | 证实被取代 | NEEDS_EVIDENCE |
| R8 | **扩容**（新增磁盘/迁移 pgdata） | 根治 | 无 | 硬件+停机窗口 | — | 中 | 容量结论 | HOLD |
| R9 | **A-1/A-2 裸删** | 109GB | eval/历史查询退化 | 低 | 差（重建需空间） | 中高 | **不推荐**，除非盘紧急且接受退化 | KEEP_UNTIL_PROVEN_REDUNDANT |

## 推荐执行序

**立即**：R0（管理员只读命令下发）+ R1（恢复实例实验中，含 B0-C 验收）→ **R2** → 按 R1 证据选 R3/R4 → R5/R7 快速清理 → R6 试点 → 若余量仍紧张再 R8。

## 回答 P1.1 五问

1. **180GB 非 pgdata 是什么**：几乎确定是 `/var/lib/docker`（overlay2+其他容器卷+json 日志）+宿主目录——docker 层证据（pgdata 命名卷路径可见），但需宿主 du 坐实；
2. **无损释放空间**：docker 层日志/dangling 镜像（宿主侧）、索引膨胀重建、staging 老数据、Parquet 迁移——都无需牺牲查询；
3. **是否必须删 A-1/A-2**：**不必须**——有更优路径（R0 归因 + R3 重建 + R6 Parquet）；
4. **是否优先扩容**：若 R0 找回空间+S1 回收 ~60GB，余量回到 ~80–260G 可延后扩容；否则扩容是最稳妥根治项；
5. **当前空间够未来数日**：**够但无缓冲**——~300MB/天有机增长可撑 ~2 月，但单次大 temp spill（历史上累计 276GB spill 证明存在重 spill 负载）可能一次吃掉 20G → 建议即刻下发 R0 清单。
