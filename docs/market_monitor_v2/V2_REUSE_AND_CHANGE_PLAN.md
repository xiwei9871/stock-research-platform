# V2 复用与变更计划
| 项 | 判定 | 说明 |
|---|---|---|
| 市场情绪 | REUSE | 快照沿用 market_emotion_state_v1 重算序列，公式未改 |
| 指数行情/dd120 | REUSE | M1 MACRO_RISK_PIT_FEATURES.parquet |
| 量能/广度持续性 | REUSE | 同 parquet（lowvol_streak, pct_ma60_d20, breadth_bad_streak） |
| McClellan | REUSE | M2_TEMPORAL_FEATURES.parquet 的 mcc_osc/mcc_sum |
| ETF资金周期 | REUSE | R3.1 PIT_CYCLE_DAILY（PIT验证过） |
| 快照生成 | NEW_MINIMAL | build_snapshot.py 离线一次性打包，幂等 |
| regime-state API | NEW_MINIMAL | market_regime_service.py + 1个路由，读快照不查生产库 |
| 前端面板 | NEW_MINIMAL | MarketRegimeSection 挂载于现有 Workspace 末尾 |
| ETF扩散广度 | UNAVAILABLE | DATA_MISSING 如实展示，不造零 |
| E/F/G/H模型 | 不接入 | M2.1冻结 |
