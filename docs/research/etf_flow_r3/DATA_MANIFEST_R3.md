# R3 Data Manifest
- 输入：r21 因子 parquet（合并 SHA256 f5eee5bd65f52a6c4b97b764c7d480a60bbf9cdb0189d9635e2b1596d623e6b1）、r1 fund_day.parquet、ETF_UNIVERSE_AND_GROUPS.csv、r2 POLICY_EVENTS.csv —— 上游均已入库/可追溯。
- 派生：analyze_r3.py → FUND_FLOW_CYCLES/DAILY.csv；analyze_r3b.py → 其余 CSV；全部入库。
- 复现：analyze_r3.py && analyze_r3b.py && plot_r3.py && build_html_r3.py && test_r3.py
