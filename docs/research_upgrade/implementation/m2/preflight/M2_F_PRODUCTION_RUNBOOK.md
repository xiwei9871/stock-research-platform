# M2-F Production Runbook（F1–F5）

**财务链独立审批，不与交易资格 V2 捆绑。**

## F1 — finver schema

执行 `sql/F1_finver_schema.sql`（新 schema，零存量风险）。验证：Gate `evaluate_finver_schema('finver')` → `SCHEMA_READY` 层真、WRITER/DATA 层假（此时 DEGRADED 是正确状态）。
回滚：未写入前 `DROP SCHEMA finver CASCADE`。

## F2 — 代码部署（OFF）

部署 `financial_ingest_integration.py` + `financial_version_store.py`。调用点改造（部署时做）：三个 sync 入口的事务体内，把 `store_finance_payload` 替换为 `store_finance_payload_and_version(..., finver_enabled=<switch>)`。开关 OFF 时行为与现状逐字节一致（仅多一个 RETURNING id，无性能影响）。回滚=代码回退。

## F3 — canary 启用

- 选 5–10 只资产（建议含已发生重述的观测样本）启用 finver_enabled；
- 验收：每次抓取后 `finver_observation` 出现对应 raw_payload_id；重复抓取 `identical` 计数增、event 不增；
- `unknown_source`/`missing_period`/`failed` 计数归零告警线；
- 事件表**不删**（审计证据）。

## F4 — 历史 raw 回放（16,586 载荷）

- 单进程顺序回放（乱序安全已证，无需预排序——但 `arrived_out_of_order` 计数会记录乱序度）；
- 分批 checkpoint（建议按 fetched_at 月份分批，~17 批）；
- 预计分钟级~小时级，不承诺时长；观察内存（单连接流式读）；
- 结束后链审计：orphan_heads=0、seq 密度、head=max first_seen；
- **不抓新数据**——只回放存量 raw。

## F5 — 消费者灰度（M3 准入）

## 常发故障处置

| 症状 | 处置 |
|---|---|
| raw 已写 event 丢失 | 不可能（同事务）；若 observation 缺 raw_payload_id 说明走了旧路径 |
| 同键事件爆炸 | 查是否 payload 解析差异（normalize 口径）；指纹含全指标 |
| 回放速度慢 | 载荷列 2.5GB——流式读、不要一次拉全表 |
| head 指向旧版本 | 报 bug——head=max first_seen 是强约束，F4 已防回归 |

## PIT 读取边界（对接消费方须知）

`first_seen_at`=平台首次观察≠市场首披；初版不可证→INFERRED/UNKNOWN 不得标 VERIFIED；2026-07 前数据不存在完整版本链证据。
