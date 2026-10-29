# Market Monitor V2 集成设计（只读，未改生产）

## 四区结构（不合成单一总分）
1. **情绪区**：现有 emotion_score + 五分量（直接复用 `market_emotion_state_v1` 输出与 compute_market_emotion_row）。
2. **持续性区**（新增只读）：lowvol_streak、lowvol20、pct_ma60_d20、breadth_bad_streak、mcc_osc/mcc_sum——均由 market_daily_bar/asset_status_daily 聚合，T+1。
3. **ETF资金区**（新增只读）：ETF_OBSERVATION_FEATURES.csv 中 READY 行；扩散项显式标 DATA_MISSING。
4. **市场阶段区**：dd120状态(≥−5/−5~−10/≤−10/≤−20)+周期起止+修复进程描述（非预测）。

## 数据契约
- 全部T+1批量聚合；单文件离线任务即可（复用 extract_m1 的SQL），入 research schema 新只读表或 parquet 供 API 读取。
- 缓存：日线一次/日；历史序列按日追加。
- PIT保障：所有rolling/expanding仅回看；无前瞻列。
- 解释口径：每区附"描述性状态≠预测"标注；预警类字段一律 NOT_EVALUATED。

## 对现有页面最小改动
MarketMonitorWorkspace.tsx 新增一个只读 panel 组（4卡），数据来自新增 /api/market_regime_state（只读查询）；不动 emotion 展示与现有路由。
