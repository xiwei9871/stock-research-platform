# Gate 0 — R2.1.2 基线冻结

- 基线：`research/etf-flow-r211-warning-fix` @ `b74beb41`
- 分支：`research/etf-flow-r212-event-audit`（自此基线切出）
- 输入 SHA256：`INPUT_SHA256.txt`（analyze_r211.py、PRE_REGISTERED_RULES.json、WARNING_STATE_DAILY/TRANSITIONS.csv、factors parquet）
- **重放验证**：重跑 `analyze_r211.py` 后 `WARNING_STATE_DAILY.csv` / `WARNING_TRANSITIONS.csv` 与已提交版本 **byte-identical**（SHA256 `d4bd560…` / `e34ccef…`）→ 无 BASELINE_MISMATCH。
- 状态机规则边界：`test_r211.py` 全通过（合成序列逐边界验证），本轮未改任何阈值/权重/状态逻辑。
- 冻结状态全部读自 `../WARNING_STATE_DAILY.csv`，本目录脚本不重新计算 WP/AS/状态。
