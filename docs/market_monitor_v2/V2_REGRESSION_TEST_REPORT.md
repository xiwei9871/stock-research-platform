# V2 回归测试报告
- 后端：tests/test_market_regime_service.py 7项 + test_dashboard_market_monitor.py + test_market_emotion_state_v1.py → **39 passed**。
  - 覆盖：payload结构、STALE/PARTIAL/DATA_MISSING、非交易日解析、history无未来行、NULL不置零、对拍M2.1冻结值、ETF深度重放。
- 前端：pnpm test → **443 passed (41 files)**；pnpm build 通过（tsc+vite）。
  - 7个测试文件补充 fetchMarketRegimeState mock；未改动旧断言语义。
- 异常路径：ETF缺失→分组DATA_MISSING；行情缺失→DATA_MISSING；ETF晚于行情→STALE标注；>100%撤离显示原值并附口径说明。
