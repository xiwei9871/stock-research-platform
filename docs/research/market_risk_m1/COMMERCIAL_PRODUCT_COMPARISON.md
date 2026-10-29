# 商业产品对照（文档级审计，无算法实现访问权）
| 产品 | 公开功能 | M1吸收 |
|---|---|---|
| SentimenTrader | 情绪/资金流/历史类比/模型组合 | "多指标共振"思想→Model D；其宣传的历史类比未做（样本不足） |
| StockCharts | 广度、McClellan Summation、新高新低、%above-MA | %above-MA、新高占比已实现；McClellan需AD累计线——列入后续 |
| TrendSpider | 多条件跨周期预警、预警状态管理 | 预警episode化（进入/解除为事件）已采用 |
| Koyfin | 宏观多维监测面板 | HTML分层展示结构参考 |
| 开盘啦 | A股情绪、涨跌停、赚钱效应 | 已由emotion五分量子模块覆盖 |
| Choice | 行情/资金/历史数据 | 数据层由本库market_daily_bar替代 |
