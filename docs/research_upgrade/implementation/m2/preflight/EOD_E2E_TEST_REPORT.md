# M2-0-C2 — EOD E2E 演练报告（独立测试实例）

实例：`stock_m2_test` @ 127.0.0.1（PostgreSQL 16.14，独立于生产 16.13 容器）。
数据：`docs/.../eod_e2e_results.json` — **9/9 PASS**。

## 真实调用链复现

`build_asset_status_daily`（独立事务提交，生产同形态）→ `run_eod_v2_stage`（独立事务）。

| 场景 | 结果 | 证据 |
|---|---|---|
| S0 基础状态自提交 | 3 日 × 8 行 | per_date |
| S1 V2 stage written | `written` + committed | S1 |
| S2 幂等重放 | `idempotent` + checksum 不变 | S2 |
| S3 开关 OFF | `blocked`，0 行被 flag，不 commit | S3 |
| S4 UPDATE 中途超时注入 | abort → rollback → checksum 前后一致 → 重试 `written`+committed | S4 |
| S5 缺口资产（无 master） | `incomplete`（missing=1），stage 显式 rollback 不 commit | S5/S5b |
| S6 状态分布 | state-2/3 行不产出确定性布尔 | S6 |
| S7 异版污染 | `blocked`，不 commit | S7 |

## 证明的接入性质

- 阶段独立可恢复：kill/超时不留半成品（checksum 证明）；
- `written`/`idempotent` 才 commit——frontier 条件诚实；
- `incomplete` 不回滚调用方也会误报——stage 内部 rollback 兜底；
- V1 列全程未被 V2 写触碰（checksum 含 v1 字段比对）。
