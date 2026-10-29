# 特征连续性审计
- 全部特征以 market_daily_bar/asset_status_daily/index_daily_bar + ETF因子parquet 当日值构建；rolling/expanding 均向后看。
- emotion 分由 `build_market_emotion_state_from_frames` 纯函数重算（DB表仅自2026-06-23起存储）；连板streak跨chunk边界用60日重叠+边界剔除保证。
- 广度 pct_above_ma20/60、20d新高占比：逐股rolling后按日聚合；min_periods 控制早期NaN。
- ETF特征经 analyze_r31.engine（已通过27点截断重放测试）；breadth_out 在头部组为 SMALL_UNIVERSE。
- 缺口：McClellan累计线未实现；无外部估值/利率特征。宏观维度为纯市场内生量。
