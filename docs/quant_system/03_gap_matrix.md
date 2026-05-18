# 差距矩阵

本矩阵用于把“当前仓库已有能力”与“目标半自动量化研究系统”之间的差距拆成可执行建设项。建议落点文件/目录尽量对齐当前仓库，而不是新建平行项目。

| 模块 | 当前已有能力 | 缺失能力 | 参考项目 | 建议实现方式 | 优先级 | 工作量估计 | 风险 | 建议落点文件/目录 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 数据层 | 已有 `schema.py`、`core_data.py`、`corporate_actions.py`、`minute_data.py`、`ingest_jobs.py`，并区分 `core/market/finance/factor/ingest` schema | 缺 `watchlist`、`portfolio_position`、`trade_log`、`news`、`announcement`、`valuation_daily`、`northbound_flow` 等目标表；旧 `public.*` 与新 schema 双轨并存 | AKShare、Qlib | 继续沿 `schema.py` 扩展新 schema；新增表只进新 schema，不再扩展 `public.*` | P0 | M | 旧表与新表并存导致调用混乱 | `src/stock_research/schema.py`、`src/stock_research/core_data.py` |
| 数据质量层 | 已有 `quality.py`、`data_audit.py`、`finance_audit.py`、`research_preflight.py` | 缺统一 Data Quality Layer、固定报告格式、PIT 审计模板、覆盖率/异常价/缺失报告 | Vibe-Trading、Qlib | 把现有巡检函数整理成统一报告生成器和 CLI | P0 | M | 现有质量检查偏简单，扩展时容易碎片化 | `src/stock_research/quality.py`、`src/stock_research/data_audit.py`、`src/stock_research/research_preflight.py` |
| Universe 层 | 已有 `services/index_universe_service.py`、`industry_membership_service.py`；回测里有 ST/流动性过滤 | 缺统一 A 股 universe 规则：主板/创业板纳入、科创板/北交所排除、上市天数、低流动性、长期停牌、次新可选 | AlphaSift、Qlib | 新增统一 universe builder，供 screener/backtest/report 共用 | P0 | M | 若分散在回测和选股里继续各写各的，会形成未来维护地雷 | `src/stock_research/universe/` 或 `src/stock_research/services/` |
| Factor Registry | 已有 `factor_config.py`、`candidate_factor_names()`、`factor.factor_approval` | 缺统一 metadata：`factor_id`、category、formula、direction、neutralization、evidence_path、status 等 | Vibe-Trading、Qlib | 将 `factor_config.py` 拆成 `registry + score config`；每个因子有元数据记录 | P0 | M | 若直接改动太大，易影响现有因子流水线 | `src/stock_research/factor_config.py`、`src/stock_research/factors/` |
| Factor Store | 已有 `factor.factor_daily`、`factor.stock_score_daily`、`factor_store.py`、`factor_pipeline.py` | 缺统一 source lineage、registry 约束、基本面因子完整接线、指标适配层 | Vibe-Trading、TA-Lib / pandas-ta | 保留现有落库与评分接口，在写入前增加 registry 校验和 source metadata | P0 | M | 现有 technical / sector / external alpha 接线逻辑与 future 基本面接线易变复杂 | `src/stock_research/factor_store.py`、`src/stock_research/factor_pipeline.py` |
| 因子验证 | 已有 IC、RankIC、quantile return、turnover、exposure、multi-horizon、gate | 缺统一报告标准、样本外流程、中性化标准、未来函数门禁、evidence 输出 | Vibe-Trading、Qlib、AlphaEvo | 以 `factor_eval/` 为中心增加标准 artifacts：md/csv/json/run_card | P0 | M | 若报告标准不先统一，后续 Agent 报告层无法稳定引用 | `src/stock_research/factor_eval/`、`src/stock_research/factor_eval_store.py` |
| TopN 回测 | 已有 `backtest.py` 和 `vectorized_topn_backtest.py`，支持基础交易成本和日/周调仓 | 缺完整真实交易约束：印花税、滑点、涨跌停、停牌、行业仓位、单票仓位、可复现 run_card | RQAlpha、Vibe-Trading | 以 `vectorized_topn_backtest.py` 为主骨架补约束和 run_card，不再扩张旧 `backtest.py` | P0 | M | 旧回测与新回测口径不一致 | `src/stock_research/vectorized_topn_backtest.py` |
| Retention 回测 | 已有持仓保留、观察池、MA20 退出、stop loss、entry filter | 缺独立 watchlist 驱动、过热/破位/回踩/启动信号模块化、统一风险标签 | daily-stock-analysis、TradingAgents-CN | 保留 `retention_backtest.py` 作为 watchlist 模拟骨架，上层增加 signal/risk/report 分层 | P0 | M | 若直接把所有盯盘规则堆进回测文件，会难维护 | `src/stock_research/retention_backtest.py`、新增 `watchlist/` |
| Portfolio 回测 | 已有账户级初始资金、lot size、资金曲线、交易明细 | 缺行业上限、单票上限、动态总仓位、市场环境仓位控制、模拟组合状态表 | RQAlpha、QuantsPlaybook | 在现有账户级框架上补仓位约束和组合状态输出 | P1 | M | 与 TopN/Retention 的规则源可能分叉 | `src/stock_research/portfolio_backtest.py` |
| run_card / evidence trail | 专题研究里已有局部 evidence，如 `dragon_case_library.py`、`technical_method_validation.py` | 缺全局统一回测/因子/报告 run_card；缺统一 `run_card.json` / `run_card.md` | Vibe-Trading、AlphaEvo | 抽象成独立 artifacts 生成层，被 factor/backtest/report 复用 | P0 | S-M | 若不统一，所有结果都难以追溯和复现 | `src/stock_research/reporting.py`、`src/stock_research/report_run_store.py`、新建 `run_card/` |
| watchlist 盯盘 | 目前只有 `technical_feature_promotion_audit.py` 的 `watchlist_readiness`，以及 `retention_backtest.py` 的观察池结构 | 缺真实 watchlist 表、规则、日报、风险分层、今日必看列表 | daily-stock-analysis、AlphaSift、TradingAgents-CN | 新建 watchlist layer，读取手工池并输出信号/风险/优先级 | P0 | M | 没有统一 watchlist 状态表会导致报告和回测脱节 | 新建 `src/stock_research/watchlist/`、`reports/watchlist_*` |
| 行业/市场状态 | 已有 focus v1/v2、mainline regime、gated backtest、industry risk control | 缺统一 `Regime Layer` API；缺与 screener/watchlist 的固定输入输出契约 | Vibe-Trading、Qlib | 保留研究模块，增加标准 regime snapshot 产物供上游调用 | P0 | M | 行业研究模块很多，命名和口径需要统一 | `src/stock_research/industry_focus_v2.py`、`src/stock_research/industry_mainline_regime.py` |
| AI Agent 报告层 | 当前已有日报、risk alert、position review；没有独立 Agent 层 | 缺角色边界、证据约束、未验证标记、输出分级：观察/候选/谨慎/剔除 | TradingAgents-CN、daily-stock-analysis、AlphaSift | 在 reports 之上增加 agent orchestration 规则，不直接改变底层研究逻辑 | P1 | M | 若先做 Agent 文案、不做证据约束，会产生幻觉型报告 | 新建 `src/stock_research/agents/`、`reports/agent_*` |
| 每日报告 | 已有 TopN、市场状态、行业强度、风险提醒、持仓复盘、bundle | 缺 watchlist 专报、每周因子表现、每周策略复盘、月度健康报告统一模板 | daily-stock-analysis、AlphaEvo | 复用 `reports/`，按 report family 增补模板与调度入口 | P0 | S-M | 报告过多但口径不统一，会降低可用性 | `src/stock_research/reports/`、`daily_research_report_workflow.py` |
| OpenClaw / 飞书接口 | 已有 `feishu_notify.py`，watchdog 已能发消息；CLI 已接 `openclaw-bin` | 缺面向研究报告的统一推送协议，缺可复用 connector 层 | daily-stock-analysis、TradingAgents-CN | 保留现有通知底座，后续增加 report delivery adapter | P1 | S | 现有接口偏运维告警，不是投研报告分发接口 | `src/stock_research/feishu_notify.py`、watchdog 文件 |
| 模拟组合 | `portfolio_backtest.py` 已具备基础账户模拟 | 缺长期虚拟组合状态、调仓记录、风险预算、组合绩效归因 | RQAlpha、QuantsPlaybook | 在 portfolio 模拟上增加组合状态表和建议层输出，不接实盘 | P2 | M | 若过早复杂化，会拖慢 P0 交付 | `src/stock_research/portfolio_backtest.py`、未来 `simulation/` |
| 半自动交易接口预留 | 当前只有研究、回测、报告和通知，没有交易接口 | 缺建议单、人工确认单、候选买卖单结构、券商接口抽象预留 | RQAlpha、AlphaEvo | 只做接口预留和建议结构，不连接真实下单 | P2 | S-M | 任何与真实下单耦合都可能越过当前阶段边界 | 未来 `src/stock_research/trade_advice/`、`schema.py` |

## 优先级解释

### P0

这些模块直接决定是否能在当前仓库内形成“可持续迭代的量化研究主链”：

- 数据层
- 数据质量层
- Universe 层
- Factor Registry
- Factor Store
- 因子验证
- TopN 回测
- Retention 回测
- run_card / evidence trail
- watchlist 盯盘
- 行业/市场状态
- 每日报告

### P1

这些模块建立在 P0 主链稳定之后：

- Portfolio 回测增强
- AI Agent 报告层
- OpenClaw / 飞书接口增强

### P2

这些模块暂时不应提前展开：

- 模拟组合完整产品化
- 半自动交易接口预留

## 结论

当前仓库最适合的建设方式不是“大重构”，而是：

1. 保留现有因子、回测、行业研究、报告工作流资产。
2. 先补统一层：
   Universe、Registry、run_card、Quality、Watchlist。
3. 让未来所有新功能围绕这些统一层生长，而不是继续平行加文件。
