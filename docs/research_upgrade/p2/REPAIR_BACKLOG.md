# P2 修复清单（修复阶段独立审批后再执行）

| # | 问题 | 严重度 | 修复内容 | 依赖来源 | 成本估计 |
|---|---|---|---|---|---|
| R1 | 初始版本被同公告日覆盖 | **P0** | 三表加 `statement_version`/`supersedes_at` 列（additive）；写方改版本追加；从 raw_*_payload hash 序列回溯已发生重述 | raw_akshare/baostock.finance_payload | 中（DDL+写方+一次回溯脚本） |
| R2 | 同日公告泄漏（ann<=as_of 约定） | **P0** | 消费层引入 availability_lag 政策参数（默认 D+1）；重算受影响因子并对比 | 无（纯代码+重算） | 中；需重跑因子+回归回测 |
| R3 | 同键多源数值漂移（188,171 键） | P1 | 契约定 source 优先序（建议三表以 akshare_em 为准、指标走 indicator_quarter）；抽样归因差异（口径/精度/真冲突） | 双源已在库 | 低-中 |
| R4 | 哨兵公告日（93 行：balance 71 + cf 22） | P1 | 逐条补证据（原始公告/其他源）；补不出则永久标 publication_date_missing | 东财/巨潮公告检索 | 低（行数少） |
| R5 | ann>period+180d 异常大（income 76,039 / balance 33,570 / cf 53,637） | P1 | 归因：baostock pubDate 语义 vs 真实披露日；若为回填日期混入需剔除 | raw payload + 官方公告抽样 | 中（量大，先抽样归因再决定批量策略） |
| R6 | 14 家 2026-06-30 双缺 | P1 | 13 家退市→标记 source_unavailable_delisted 终态；002731→truly_undisclosed 已坐实 | 已坐实，无需再抓取 | 极低（标记即可） |
| R7 | 无 published_at（时刻） | P2 | 新抓取开始采集披露时间戳（巨潮/东财详情页）；历史不可补→永久 day 粒度+D+1 | 抓取改造 | 中 |
| R8 | 退市股版本冻结 | P2 | 13 家 raw payload hash 快照归档 | 已在库 | 低 |
| R9 | 2018 前长期历史覆盖分层 | P2 | 按 STATEMENT_COVERAGE_MATRIX 低覆盖期归因（未披露/未抓取/源无）；北交所覆盖单列 | 见矩阵 | 中（分批定向） |
| R10 | financial_pit_at 接入消费方 | P1 | 作为 Gate 包在 point_in_time_finance/finance_ttm 前层（新逻辑） | 本契约 | 低 |

**不修项**：历史已丢失的初版数值本身不可凭空恢复（只能标 HISTORICAL_VERSION_MISSING 并从 R1 起防新增）。
