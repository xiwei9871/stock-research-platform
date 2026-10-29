# V2 历史PIT与对拍
- 快照全部输入即冻结PIT产物（M1特征、M2特征、R3.1周期日表），逐日行为与离线研究一致——同管线，对拍为恒等式（见 V2_ETF_RECONCILIATION.csv）。
- API 回放：trade_date 取 ≤请求日的最近交易日；历史行 ≤当日（测试 test_history_rows_are_pit 验证）。
- ETF 深度不随未来变化：快照是冻结文件，无重算；test_pit_etf_depth_replay 验证 G2 2026-06-30=~104%、10-28=~86%（与R3.1台账一致）。
- 回撤周期只用当时确认状态：dd120 序列同 M1 口径。
