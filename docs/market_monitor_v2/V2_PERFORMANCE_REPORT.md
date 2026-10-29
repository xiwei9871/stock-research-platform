# V2 性能
- /api/market-monitor/regime-state 首次 ~0.59s（parquet惰性加载）；命中 eod_response_cache 后毫秒级。
- 快照读取 LRU 缓存（parquet一次性载入 ~1892行/4950行，内存 <50MB）。
- 新增请求：每次切日期/市场 = 1 个 regime-state 请求（四市场卡同包返回，无需4次）。
- 无每次重算ETF周期：快照离线一次性生成。
