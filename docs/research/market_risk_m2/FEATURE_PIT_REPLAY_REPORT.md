# PIT验证
- 特征构造全部单向滚动/扩张；M2_TEMPORAL_FEATURES.parquet 继承M1已通过的特征截断重放测试（test_m1.py test_features_pit）。
- ETF特征经R3.1引擎27点重放一致。
- 2026压力测试所有归一化分位仅使用 ≤2025-12-31 历史分布。
