# V2 Release Notes
- 新增只读 GET /api/market-monitor/regime-state（快照驱动）。
- MarketMonitorWorkspace 底部新增「市场宏观状态」区：四市场阶段卡、量能/广度持续性双图、ETF分组累计净赎回曲线。
- 新文件：market_regime_service.py、build_snapshot.py、MarketRegimeSection.tsx、快照数据3件、测试1件。
- 修改：app.py(+1路由+import)、client.ts(+类型+fetch)、MarketMonitorWorkspace.tsx(+挂载)、styles.css(+样式)、tests mocks(+fetchMarketRegimeState)。
- 已知限制：ETF数据止于10-27（滞后1日标STALE）；扩散DATA_MISSING；快照为冻结研究基线，后续需离线任务定期再生成。
