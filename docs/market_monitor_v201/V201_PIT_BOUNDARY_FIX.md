# V2.0.1 PIT 边界修复

## 修复项
1. **ETF周期最大深度泄漏（P0）**：原实现从 `etf_cycles.json` 读全周期 `max_depth_pct`，历史查询会看到未来峰值。修复：
   - `etf_cycles.json` 移除 `max_depth_pct` 字段（从源头消除）。
   - API 改为返回 `cycle_max_depth_pct_to_date` / `cycle_max_withdrawal_pct_to_date`——仅对 ≤查询日且属于当前周期的行求 max。
   - 测试 `test_pit_max_depth_never_future`：2026-06-15 查 G2 max_to_date=86.0%（不泄漏7月104.4%），2026-10-28 查=104.4%。
2. **快照版本混入（P1）**：`eod_response_cache` 键未含快照版本 → 指针翻转后仍返回旧缓存。修复：路由缓存键纳入 `active_snapshot_version()`（resolved-dir+manifest）。实测 vA↔vB 热切换即时生效。
3. **快照缺失 500 → ERROR**：快照文件缺失时 API 返回 `{status:ERROR, modules:{}}` 而非异常崩溃；前端展示错误文案+重试按钮。

## PIT 已验证不变量
- 历史日行 ≤ 查询日（test_history_rows_are_pit）。
- 周期内 max 只累计到查询日。
- 周期切换时 cum_flow/aum0 正确重置（test_cycle_reset_changes_denominator）。
- 扩散指标永远 DATA_MISSING 不置零。
