# R2.1 Data Manifest

- 输入（上游 R1.1/R2 已入库哈希可追溯）：`etf_flow_r1/data/*.parquet`、`fund_day.parquet`（corp-corrected flow_use）、`etf_flow_r2/POLICY_EVENTS.csv`。
- 本地中间产物：`data/factors_*.parquet`（含 WP/AS/state/policy_on），合并 SHA256 `191b87d9aa1686e43010d94b6823c0c97cdd7c072ee5b5f5a8769031259ddeaa`。不入库（.gitignore），由 `analyze_r21.py` 可复现。
- 输出 CSV：WARNING_STATE_DAILY / WARNING_TRANSITIONS / FORWARD_RISK_BY_STATE / ALERT_LEAD_TIME / FALSE_ALERT_AUDIT / INCREMENTAL_VALUE_VS_PRICE / POLICY_REGIME_RESULTS / TECHNOLOGY_WARNING_RESULTS / NORMALIZED_FLOW_FACTORS / ETF_GROUP_MEMBERSHIP —— 全部入库。
- 复现：`python analyze_r21.py && python plot_r21.py && python build_html_r21.py && python test_r21.py`
