# P0-C1 finver WRITER 准入 — 新鲜度与范围绑定

`data_integrity_gate.evaluate_finver_writer(conn, schema, ...)` 新增层。

## 判定逻辑

| 层 | 条件 |
|---|---|
| SCHEMA_READY | 三表+列+PK/FK（沿用 evaluate_finver_schema） |
| **WRITER_READY** | `staleness_hours` 内存在 `finver_observation.seen_at`，**或** 调用方提供 `heartbeat_at`（受控作业心跳证据）。**历史行永不能证明活跃 writer** |
| **DATA_READY** | WRITER_READY ∧ events>0 ∧ orphan_heads=0 ∧ n_versions 对账一致 ∧ orphan_observation=0 ∧ **raw_without_observation=0** ∧ `expected_endpoints` 全覆盖（未声明范围→恒 False） |

## 对账项（每层如实输出）

- `last_write_at`/`last_event_at`；raw 行数；`raw_without_observation`（raw 已存但无 observation）；`orphan_observation`（observation 指向不存在的 raw）；`per_endpoint` 覆盖拆分；`orphan_heads`；`nversions_mismatch`。

## 验收（INTEGRITY_GATE_FINAL.json → W 组）

- 陈旧 observation → WRITER_READY=False ✅
- heartbeat_at 证据 → True ✅
- 新鲜 observation → True ✅
- 未声明 expected_endpoints → DATA_READY=False ✅
- 声明范围+链一致 → True ✅
- 未对账 raw（已存未观测）→ raw_without_observation=1 且 DATA_READY=False ✅
- n_versions 篡改 → 检出且 DATA_READY=False ✅

## 消费方契约（evaluate_requirements 扩展）

`financial` 需求可声明：`require_writer`/`staleness_hours`/`heartbeat_at`/`expected_endpoints`/`min_state`（schema|writer|data）/`allow_degraded`。每域输出 `satisfied`；任一声明域不满足 → combined=BLOCKED 并附 `reason`。
