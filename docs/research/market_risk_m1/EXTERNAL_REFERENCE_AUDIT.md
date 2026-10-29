# 外部参考审计（M1 阶段1）
## 开源仓库可达性
| 指定仓库 | 状态 | 处置 |
|---|---|---|
| gkoss6701/Market-Breadth-Detector | **未找到**（疑似更名/删除） | 用同类替代审计：tradermonty/market-breadth-analysis（SPX广度，MA%+峰值检测+回测，MIT）、jamesdellinger/market_breadth（复现Breadth.app 20d-SMA广度，其底层为hk-lei A股广度代码）、finskills breadth skill（6分量0-100健康分模板） |
| jwbradley/MarketBreadth | **未找到**（该账号19个公开仓库中无此名） | 记录为 UNAVAILABLE |
| orloworks/market-regimes | 存在 | 规则制regime识别（crisis/volatile/choppy等5态，22年日数据，无ML），MIT——regime分类命名可借鉴，逻辑不直接迁移 |
| alphapapi-ctrl/market-intelligence-platform | **未找到** | 近似项 noivuduc/market-intelligence-dashboard（宏观+广度+流动性+options语境层，MIT，明确"非信号层"） |
| microsoft/qlib | 存在 | 全栈ML量化平台，对本POC过重；未引入 |
| bankrollhunter/market-breadth | 存在（附加） | A股+美股广度（Tushare+MySQL），广度口径可参考 |

## 可复用逻辑（已吸收进M1特征设计）
- %above-MA20/60、20d新高占比：与StockCharts风格一致，已由 market_daily_bar 现算。
- 广度复合分（finskills 6分量）→ 参考其"分量缺失时权重再分配"思路，M1未采用（避免隐含权重寻优）。
- regime 5态命名 → 用于文档表述，不影响状态机。
- "信息/语境层而非信号层"（noivuduc定位）→ 与最终建议一致。

## 声明
商业产品（SentimenTrader/StockCharts/TrendSpider/Koyfin/开盘啦/Choice）无法访问其算法实现，审计限于公开文档级功能描述，见 COMMERCIAL_PRODUCT_COMPARISON.md；不存在README级冒充代码审计。
