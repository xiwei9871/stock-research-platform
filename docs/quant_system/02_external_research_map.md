# 外部项目调研映射表

本文不 clone 外部仓库，仅基于公开仓库信息和本项目当前建设方向整理“借鉴什么、不借鉴什么”的映射。License 如本轮未做源码级核验，则标注“待确认”。

| 项目名 | URL | License | 可借鉴内容 | 不可借鉴内容 | 对应本系统模块 | 优先级 | 是否需要试跑 | 是否需要迁移接口 | 风险提示 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Vibe-Trading | https://github.com/HKUDS/Vibe-Trading | Apache-2.0 | Alpha Zoo 组织方式；`qlib158` / `Alpha101` / `GTJA191` / academic alpha 分类；`run_card`；lookahead guard；factor bench；MCP / CLI / FastAPI 工具化思路 | 不要整体照搬其系统边界，不要把主项目改造成另一个通用平台 | Factor Registry；Factor Validation；Backtest run_card；Research tooling | P0 | 是 | 是 | 需防止把“外部 alpha 库”直接塞进主流水线而缺少本地 PIT 与数据质量约束 |
| daily-stock-analysis | https://github.com/ZhuLinsen/daily_stock_analysis | MIT | 每日股票分析结构；自选股报告；风险提示；推送组织；OpenClaw Skill 思路 | 不适合作为核心回测引擎；不要把其日更流程直接替换本仓库现有日流水线 | Watchlist Layer；Report Layer；OpenClaw Integration | P1 | 否 | 部分需要 | 重点借鉴报告编排和推送节奏，不借鉴其作为“核心研究底座”的定位 |
| AlphaSift | https://github.com/ZhuLinsen/alphasift | Apache-2.0 | A 股全市场扫描；LLM ranking；risk-aware scoring；auditable evaluation | 不要让 LLM ranking 直接替代可回测因子与规则；不要把不可验证结论写入交易建议 | Stock Screener Layer；AI Agent Research Layer；Opportunity Discovery | P1 | 是 | 是 | 最大风险是“发现流程”与“回测流程”脱节，导致好看但不可复现 |
| AlphaEvo | https://github.com/ZhuLinsen/alphaevo | 待确认 | 策略 DSL；回测编排；失败归因；结构化改写；复测；evidence trail | 不要让“策略进化”先于基础数据质量、因子注册、回测质量门禁建设 | Strategy Lab；run_card / evidence trail；Backtest diagnostics | P1 | 否 | 是 | 过早引入 DSL 会增加复杂度；建议在 MVP 完成后接入 |
| TradingAgents-CN | https://github.com/hsliuping/TradingAgents-CN | 待确认 | 中文多 Agent 投研报告结构；技术/基本面/新闻/风险分工；多空辩论；组合经理汇总 | 不复制 `app/`、`frontend/` 等专有或受限代码；不照搬“人类团队模拟”话术 | AI Agent Research Layer；Report Layer | P1 | 否 | 否 | 重点是角色职责与报告结构，不是 UI，也不是直接产出买卖结论 |
| Qlib | https://github.com/microsoft/qlib | MIT | Alpha158 / Alpha360 思路；因子表达式；ML pipeline；数据处理；回测分析方法 | 不把当前项目整体改造为 Qlib 数据格式和工程骨架；不替换 PostgreSQL 主库 | Factor Layer；Factor Validation；ML-ready export | P1 | 否 | 部分需要 | 可以借鉴方法和接口抽象，但不能反向绑架本项目数据模型 |
| RQAlpha | https://github.com/ricequant/rqalpha | 待确认 | 事件驱动回测；账户/订单/持仓模型；手续费、滑点、涨跌停、停牌等真实交易约束 | 现阶段不要重写完整事件驱动引擎；不要推翻已有向量化 TopN / portfolio / retention 框架 | Backtest Layer；Simulation Layer | P1 | 否 | 部分需要 | 最大风险是过早工程化，拖慢 P0 交付 |
| QuantsPlaybook | https://github.com/hugo2046/QuantsPlaybook | 待确认 | 券商金工研报复现策略；RSRS；QRS；筹码分布；凸显性因子；多因子模型；组合优化 | 不直接相信外部收益结论；不把研报复现代码原样迁入主项目 | Factor Research；Candidate Factor Library；Strategy Materials | P1 | 否 | 否 | 只能作为“候选素材库”，所有策略必须用自有数据库重验 |
| AKShare | https://github.com/akfamily/akshare | 待确认 | 辅助数据采集；行情、财务、指数、行业、资金流、公告新闻等补充源 | 不作为唯一正式数据源；不允许只调用接口不落库 | Data Layer；Supplemental Data Sources | P0 | 否 | 否 | 风险在于接口漂移和数据质量波动，必须配套原始 payload 落库和质量检查 |
| TA-Lib / pandas-ta | https://github.com/TA-Lib/ta-lib-python | BSD-2-Clause | MACD、RSI、BOLL、ATR、ADX、KDJ、均线、波动率、蜡烛图形态等基础指标 | 不要自己重复手写整套基础技术指标库；不要把库 API 直接泄漏到业务层 | Factor Layer；Technical Feature Layer | P0 | 否 | 是 | 需要加一层统一指标适配接口，避免未来库替换成本高 |
| LLMQuant Skills | https://github.com/LLMQuant/skills | MIT | 金融 Agent workflow 组织方式；router `SKILL.md` + workflow 清单；证据约束；风险、组合、股票、宏观复核模板 | 不直接安装为生产 skills；不创建第二套 Agent 输出结构；不允许绕过 `AgentObservation` 和 `ReviewAgent` | AI Agent Research Layer；Report Layer；Watchlist Review；Risk Review | P1 | 否 | 否 | 只能作为内部 skill 草案参考，所有输出必须映射到本仓库 agent contract 和 evidence trail |
| LLMQuant Data / data-mcp | https://github.com/LLMQuant/data-mcp | 待确认 | FRED、SEC、13F、论文/百科搜索等外部上下文源；MCP 工具描述方式 | 不替换 A 股行情、财务、因子、评分、交易日历或 PIT 主库；不直接把外部返回写入研究结论 | External Context；Report Artifacts；Research Evidence | P2 | 否 | 是 | 未来只允许通过 adapter 写 artifact，再转成本地 evidence；第一阶段不接生产数据源 |
| LLMQuant QuantMind | https://github.com/LLMQuant/quant-mind | 待确认 | 非结构化 papers/news/reports 的 evidence unit、语义检索、RAG/知识抽取思路 | 不新建独立知识图谱产品；不复制内容库；不绕过本地来源、可用时间和缺失标注 | Research Signal Layer；Stock Report Research；News Enrichment | P1 | 否 | 部分需要 | 借鉴 schema 和流程，不迁移外部运行时；所有材料必须保留 source_path 和 available_at |
| LLMQuant Awesome Trading Agents | https://github.com/LLMQuant/awesome-trading-agents | MIT | Finance Agent / MCP / Skills 外部雷达分类；项目发现清单 | 不按榜单盲目引入；不把列表项目升级为依赖前跳过本地边界评估 | External Research Map；No-Reinvent-Wheel Governance | P1 | 否 | 否 | 仅作为季度观察源，每个候选项目必须绑定本仓库 anchor 后再评估 |
| LLMQuant Magents | https://github.com/LLMQuant/Magents | 待确认 | 多策略仿真、risk/slippage/order lifecycle 等回测约束概念 | 不替换当前 TopN / portfolio / retention 回测；不引入订单、账户、券商或自动执行状态 | Backtest Quality Checklist；Simulation Notes | P2 | 否 | 否 | 只记录为未来真实交易约束参考，不进入当前评分和 watchlist 主链 |
| LLMQuant Finance Context / Docs | https://github.com/LLMQuant/docs | 待确认 | 华尔街投研流程、晨会、thesis tracking、catalyst calendar、复核清单等报告方法 | 不复制内容进入商业知识库；不让海外市场流程覆盖 A 股交易约束 | Report Layer；Runbooks；Research Review Templates | P2 | 否 | 否 | 只借鉴报告结构和复核语言，必须本地化到 A 股数据和人工复核边界 |

## 逐项落地判断

### P0：应尽快纳入设计，但不要求本轮开发

- Vibe-Trading：
  用于因子注册、`run_card`、lookahead guard、factor bench 思路整理。
- AKShare：
  继续作为补充数据源，但必须坚持“先落 PostgreSQL，再进入研究层”。
- TA-Lib / pandas-ta：
  用于替代未来继续手写基础技术指标的方向。

### P1：在 P0 主链稳定后接入

- daily-stock-analysis：
  优先借鉴 watchlist / 日报 / 推送结构。
- LLMQuant Skills：
  优先借鉴 risk / portfolio / equities / macro 的 workflow 结构，但要改写为本仓库内部 skill 草案，并映射到 `AgentObservation`、`ReviewAgent`、report bundle、run_card 和 watchlist evidence。
- LLMQuant QuantMind：
  借鉴 evidence unit 和非结构化材料抽取思路，用于后续研报、新闻、论文、公告的统一证据层；第一阶段不做独立知识图谱产品。
- LLMQuant Awesome Trading Agents：
  作为外部项目雷达来源，不作为依赖来源。
- AlphaSift：
  用于全市场扫描与 auditable opportunity discovery。
- AlphaEvo：
  用于策略证据链与失败归因。
- TradingAgents-CN：
  用于“我 + AI Agent”投研角色分层。
- Qlib：
  用于因子表达式和 Alpha158/360 参考。
- RQAlpha：
  用于补回测真实约束，不用于立刻重写引擎。
- QuantsPlaybook：
  用于候选因子素材库。

### P2：只做观察或补充设计

- LLMQuant Data / data-mcp：
  只作为 FRED、SEC、13F、论文/百科搜索等外部上下文候选源；不得替代 A 股主数据，未来必须通过 artifact 和 evidence unit 适配层进入报告。
- LLMQuant Magents：
  只记录其 risk/slippage/order lifecycle 概念，用于未来回测质量检查表，不替换现有回测。
- LLMQuant Finance Context / Docs：
  只借鉴投研工作流和报告复核清单，不复制内容库。

### 本仓库对应关系

将外部项目映射回当前仓库，大致落点如下：

- 因子与 registry：
  `src/stock_research/factor_config.py`
  `src/stock_research/factor_pipeline.py`
  `src/stock_research/factors/`
- 因子评估与证据链：
  `src/stock_research/factor_eval/`
  `src/stock_research/factor_eval_store.py`
- 回测：
  `src/stock_research/vectorized_topn_backtest.py`
  `src/stock_research/portfolio_backtest.py`
  `src/stock_research/retention_backtest.py`
- 行业/市场状态：
  `src/stock_research/industry_focus_v2.py`
  `src/stock_research/industry_mainline_regime.py`
  `src/stock_research/industry_regime_gated_backtest.py`
- 报告与推送：
  `src/stock_research/reports/`
  `src/stock_research/feishu_notify.py`
- Agent 合约与复核：
  `src/stock_research/agents/contracts.py`
  `src/stock_research/agents/review.py`
- 研报、新闻和叙事证据：
  `src/stock_research/stock_report_research.py`
  `src/stock_research/news_features.py`
  `src/stock_research/topn_news_enrichment.py`
  `src/stock_research/research_narrative.py`

## 结论

外部项目的价值主要在三类：

1. 组织方式：
   Vibe-Trading、Qlib、RQAlpha
2. 工作流和报告结构：
   daily-stock-analysis、TradingAgents-CN、AlphaEvo
3. 策略与因子素材：
   QuantsPlaybook、AlphaSift、TA-Lib / pandas-ta

本项目应坚持的边界是：

- 以你自己的 PostgreSQL A 股数据库为核心
- 以现有 `stock_research` 仓库为主线
- 外部项目只提供方法、接口、模块边界和验证思路
- 不做大段复制，不做整仓替换
- LLMQuant 只作为方法参考和外部雷达，不作为并行平台；每个 LLMQuant-inspired artifact 都必须说明它增强了哪个本仓库模块
