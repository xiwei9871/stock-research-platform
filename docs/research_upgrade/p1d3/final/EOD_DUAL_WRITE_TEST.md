# P1d.3 — EOD V2 双写演练（隔离副本）

脚本 `scripts/p1d3_eod_dual_write_drill.py`；JSON `EOD_DUAL_WRITE.json` —— **all_pass=true**

## 双写形态（可关闭）

`build_asset_status_daily(conn, start, end, emit_v2_target=...)`：
- `emit_v2_target=None`（默认，生产现状）→ 仅 v1 写入，行为不变；
- 启用后同函数内 v1 INSERT + `emit_v2_flags` 纯 UPDATE 在**同一事务**——半完成批次不可能推进成功水位；
- 未给明确 start/end + 启用开关 → `ValueError` 前置拒绝无界 v2 emit；
- 目标表缺 v2 契约列 → `RuntimeError` 拒绝（未授权前生产上必然失败）。

## 演练断言（eod_replica，4 个连续交易日）

| 断言 | 结果 |
|---|---|
| 每日 v1 行 + v2 emit 单事务完成（~5,037 行/日，v2=rows） | ✅ |
| 同一日重复执行 → hash 不变（同输入同输出） | ✅ |
| 批内注入真实 UndefinedTable → 整日回滚，0 行残留 | ✅ |
| abort 后重试 → 完整落地 | ✅ |
| 全部行 `limit_state_v2∈{1,2,3}` + rule_id + version 非空 | ✅ |

## v1 静态阈值的处置

`build_asset_status_daily` 的 CASE 阈值保持不动（v1 生产兼容链仍需要它）——双写期 v1 照写、v2 走规则引擎；v1 误标持续产生但已由 v2 列承载正确判定，消费方切换 verified_v2 后不再读 v1。退役 v1 写入属后续独立任务。
