# M1 故障恢复报告（隔离演练证据）

## 已演练故障

| 故障 | 场景 | 结果 |
|---|---|---|
| 事务中断 | V2 emit 期间 statement_timeout 注入 → QueryCanceled → conn.rollback() | **0 残留行**；重试恢复一致（checksum 匹配） |
| 版本漂移 | 当日已载 pit_rules_v1 时请求 vX 写入 | **blocked**，无部分写入 |
| 基础缺失 | 无当日行的日期请求 emit | **blocked**（不产生孤立 flag 行） |
| 开关关闭 | enabled=False | **blocked**，零副作用 |
| 重复执行 | 同日二次 emit | **idempotent**，checksum 不变 |
| 未知状态 | shadow_state∈{rule_unknown, data_insufficient} | 0 行被强置 v2 bool → **fail-closed** |
| 版本层重复抓取 | 同指纹 payload 重放 | identical_bump，事件数不变 |
| 元数据抖动 | UPDATE_DATE 变、指标不变 | 不产版本 |
| 空提取 | payload 行无指标字段 | `empty_metrics` 计数，不判"无变化" |
| 注入防护 | 目标表/schema 标识符正则 | 非法即拒（测试固化） |

## M2 部署时才暴露的风险（记录）

- 大批量 UPDATE 在容器 DSM 限制的并行计划下可能 OOM（P1d.3 已验证需 `max_parallel_workers_per_gather=0`）；
- emit 依赖 compute_pit_limit_flags 当日期行情完整性——生产接入需在 EOD 顺序中硬约束；
- finver 与三表双写的原子性：须同事务，否则事件层与规范表漂移。
