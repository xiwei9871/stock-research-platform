# P1d.3 — EOD V2 增量写入设计（未授权生产启用）

## 现状问题

`build_asset_status_daily` 用静态 CASE 阈值写 `is_limit_up/down` —— 这正是 62,937+ 误标的生产者。**若历史修复完成后 EOD 继续用旧逻辑写 v1 列，误标会持续新增。**

## 设计：`emit_v2_flags`（`core_data.py`）

```python
emit_v2_flags(conn, start_date, end_date, target_table,
              flags_version="pit_rules_v1")
```

- 与批量迁移**同一共享引擎** `compute_pit_limit_flags` —— 不存在平行规则实现；
- **守卫**：目标表缺 `{is_limit_up_v2, is_limit_down_v2, limit_state_v2, limit_rule_id_v2, limit_flags_version}` 任一列 → `RuntimeError` 拒绝写入（生产表当前无 v2 列 → 现在调用必然失败，无法误写）；
- 写入 `ON CONFLICT (trade_date, asset_id) DO UPDATE` —— 幂等可重跑；
- `limit_state_v2` 枚举：`1 verified / 2 rule_unknown / 3 data_insufficient` —— 与 loader `verified_v2` 读路契约一致（`DISTINCT FROM 1` → fail-closed）。

## 正式启用顺序（需单独授权）

1. `ALTER TABLE core.asset_status_daily ADD COLUMN` × 5（v2 四列 + `limit_flags_version`）—— 只加列不改既有列，向后兼容；
2. EOD 序列：`build_asset_status_daily`（v1 照写，过渡期保留）→ `emit_v2_flags(conn, today, today, 'core.asset_status_daily')`；
3. 历史回填：按 `p1d3_migration_rehearsal.py` 的分批/checkpoint/commit 模式，迁移窗口执行；
4. 读路灰度：消费方 `qualification_mode` 逐步 `legacy → corrected_shadow → verified_v2`，每步回归差集；
5. 全部消费方稳定后，才考虑退役 v1 写入（长期目标，不在本轮）。

## 一致性保证

- EOD 写入与回填用**同一个函数** —— 新数据与迁移数据规则一致；
- `rule_unknown`（北交所 ST 等未核实规则）与 `data_insufficient`（缺 close/preclose）不自动回退 v1 —— `COALESCE(v2,v1)` 仍为禁止模式；
- v1 列在过渡期继续由旧逻辑写入（下游仍在消费），其误标已在 `NEEDS_REVALIDATION` 清单中声明。
