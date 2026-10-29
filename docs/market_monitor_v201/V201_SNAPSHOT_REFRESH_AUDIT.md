# 快照刷新与一致性审计
- **版本化布局**：`data/<version>/{4 files}` + `data/current` 指针文件；构建先写 `.stage-*` 临时目录，rename 到版本目录，最后原子替换 `current`——读者不会混读半成品。
- **缓存一致性**：parquet lru_cache 以 resolved 目录为键；响应缓存键含 snapshot_version；指针翻转后新请求立即取新版本（实测 vB-test↔v2.0.1 双向切换）。
- **真实边界**：market 至 2026-10-28，ETF 至 2026-10-27 → ETF STALE 标注正常。
- **缺失容错**：目录缺失 → status:ERROR；ETF文件缺失 → etf_flow DATA_MISSING（市场模块仍 READY）。
- **本轮未启用生产调度**；快照刷新 = 手动运行 build_snapshot.py <version>。
