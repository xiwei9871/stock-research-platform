# M2-F-RELEASE-CANDIDATE — 财务版本层发布包

| 项 | 值 |
|---|---|
| 源码 commit | `da7009bf` 起，集成于 `release/r3-m2-preflight` |
| 核心模块 | `financial_version_store.py`（事件层）、`financial_ingest_integration.py`（raw+finver 同事务入口） |
| Schema 版本 | `finver` schema 三表（event/observation/key_chain） |
| 迁移 SQL | `sql/F1_finver_schema.sql`（未执行） |
| 开关默认 | `finver_enabled=False`（参数级） |
| 回放设计 | 只读 raw_akshare + 写 finver，单进程顺序，按 fetched_at 分组键回放 |

## 已验证正确性（FINVER_CONCURRENCY_AND_REPLAY_TESTS.json，7/7）

- A→B→A 三事件保留（指纹≠身份）；连续重复抓取只产 observation；
- **双连接并发同键**：advisory lock 串行化，seq 无碰撞、链无孤儿；
- **乱序回放**：旧内容迟到 → `late_arrival_repeat` 挂旧事件，head 不回归（head=max first_seen）；
- raw 成功+event 失败 → **整体回滚**，raw 不孤儿；
- `read_as_of` = 平台观察时序语义；
- 覆盖计数：processed/new_version/identical/changed/missing_period/unknown_source/failed。

## 数据身份与覆盖（D2 结论）

键 = `asset_id + statement_type + endpoint + report_period + report_type`。
- 支持源：EM 三表 endpoint、sina_report、share_change_cninfo；
- 不支持/无证据源：**baostock**（无 raw 保存，未知字段命名——计数为 unknown_source 不静默丢弃）；
- 行内缺 REPORT_DATE → `missing_period` 计数，不静默吞；
- 观测窗仅 2026-07 起：**不得宣称历史多年已具备完整 PITR 版本链**，历史初版统一按证据分级（INFERRED/UNKNOWN）。

## 发布分步（每步独立审批，与 T 链解耦）

| 步 | 动作 | 前置 | 回滚 |
|---|---|---|---|
| **F1** | finver schema DDL | SQL 已测试库验证 | 未写数据前 DROP SCHEMA |
| **F2** | 部署抓取侧代码，OFF | 单测过 | 代码回退 |
| **F3** | canary 资产启用追加写 | 三个入口事务体内调用；观察 counters | 关开关；事件保留（审计证据不删） |
| **F4** | 历史 raw 分批回放 | raw 表 16,586 载荷；乱序安全已证 | 暂停续跑；事件不删 |
| **F5** | 财务消费者灰度 | M3 准入 | — |

## 部署前检查 / 部署后验收

- Gate `evaluate_financial('finver')`：F1 后应为 DEGRADED（schema 在无写证据不升 READY）；F3 写证据后 READY；
- 抽查链：n_versions==事件数、latest_event_id 指向 max first_seen、observation 引用存在的 event；
- `arrived_out_of_order`/`late_arrival_repeat` 计数监控（回放期非零属正常，常态期应≈0）。

## 监控与停止

- 观测 `finver_observation` 增长速率 vs 抓取量；observation 增而 event 不增=全部 identical（正常）；
- 人工停止=关 finver_enabled；事件表不删（E3 审计保留原则）。
