# M0 现状与缺口审计：科技卡脖子策略 × 科技主题研究

**数据基准日：** 2026-10-19（Asia/Shanghai；外网 readiness 最后一次取样时间为 23:26 +08）
**范围：** GitHub `main`、正式科技卡脖子策略、Theme Research 生产数据库、stock-prod 外网运行状态、已存在的回测与研究产物。
**阶段边界：** 只读审计；未改代码、正式策略、质量池、主题审核状态或生产数据库。只新增本 M0 审计文件和配套 lineage CSV。
**工作区说明：** 本机 `README.md` 修改和未跟踪 `docs/README.md` 是先前获批的文档整理，仍未提交；不属于本 M0 变更，也没有提交或推送。

## Gate 结论

M0 的现状盘点和证据路径已完成，审计结果供人工审核。当前不应进入正式策略改版或 M2 challenger 试验：虽然正式策略有可读的 EOD 产物，但市场状态输入存在超过四个月的断档，严格候选池的文件名与实际行数不符，且选股 v2 的 PIT 输入、回放和 V7 人工审批产物在当前工作区缺失。现有回测因此还不是一个可比较、可重放的冻结基线。

M1 可以在审核后复用既有主题、来源、claim、node、mapping 和审核门，先做 AI 供电、半导体设备、人形机器人三个 research-only pilot。策略改动仍被 Gate 阻断，直到候选池、市场状态时点、来源可用时点和基线版本被核实并冻结。

本轮审计发现的优先数据风险：

1. **47 篇研报日期未入库。** 本地原始批次清单使用 `date`，标准化清单及数据库的 `publish_date` / `report_date` 对这 47 篇为空。科技候选研究脚本要求 `e.report_date >= 2024-01-01`，因此这些报告不会进入该关键词通道。此次 M0 未写库修复。
2. **正式策略的市场暴露输入过期。** Regime 文件最新日期为 2026-06-05；2026-10-16 EOD 回放的 21 个双周调仓日中，有 9 个没有精确日期暴露值，代码在缺值时使用 `1.0`。
3. **Theme Research 的 PIT 与新鲜度字段不足。** 生产 source 表没有 `available_at` / `collected_at` 列，provenance 为空；13 篇 source 缺 `publish_date`，已知日期的 255 篇早于 90 天。系统没有独立 `stale` 状态或过期策略。
4. **现有“v2 / v7”设计不能从当前 ignored artifacts 重现。** 相关代码和测试在 GitHub `main`，但其设计、PIT、proposal、manual-review 输入目录缺失或为空；相关定向测试因此有 33 项 `FileNotFoundError`。
5. **生产发布状态不完全一致。** EOD 状态表和本地发布摘要记录 10-19 成功；外网 readiness 仍为 `PARTIAL`，并报告缺少精确日期正式 strategy manifest 和 review/evidence snapshot 问题。外网 review queue 目前有 15 个 Top5 项，15 个 evidence digest 均为 `PARTIAL`，缺 `full_evidence_digest`。

## 1. 审计方法与边界

- GitHub `origin/main` 由 `git ls-remote origin refs/heads/main` 核验；本机 `main`、本地 `origin/main` 与远端 `main` 均为 `f2b832948aba953847548007eb5e21f03e062e94`。
- 生产状态通过外网 GET API、`theme_research_runtime` 和 `stock_research` 只读 PostgreSQL session、stock-prod 只读文件列表核验。Theme Research DB session 明确返回 `transaction_read_only=on`。
- M0 没有调用生产写 API、发布命令、schema migration、cron、EOD 修复或回测写入入口。
- 10-19 EOD 运行是在审计过程中由既有调度产生，不是本轮触发。运行记录与外网状态的时间差异列在第 2 节。
- 证据矩阵在 `docs/research_upgrade/00_feature_lineage_matrix.csv`。Git 忽略的 `outputs/` 和 `reports/` 属于运行输入或审计产物；本轮没有清理、移动或覆盖它们。

## 2. GitHub main 与生产版本

### GitHub main

- `main`、`origin/main`、GitHub `main` 当前均为 `f2b83294`，工作区在本轮开始前不是完全干净：只有 `README.md` 修改和未跟踪 `docs/README.md`，均为之前获批的文档整理。
- 外网 runtime `release_id=4d7f6aa8d3c29af6b337a4d0473d82da88c234f4`。发布脚本以 `git rev-parse HEAD` 作为 release id，因此生产版本是 2026-10-14 的 Git commit `4d7f6aa8`，比当前 `main` 落后 6 个提交。
- 外网 `/release.json` 与本地 `dashboard/dist/release.json` 均为 `4d7f6aa8`。本次抽查的正式策略、Theme Research 核心模块在 `4d7f6aa8..main` 之间没有代码 diff；6 个提交主要含 EOD/cron/内部 dashboard 运维变化及 AGENTS 文档。
- `README.md@origin/main` 仍写旧分支 `factor-scoring-daily-pipeline`，并将已退役的 `127.0.0.1:8765` 描述为 Ops Snapshot 入口；这与 `AGENTS.md` 的 canonical `main` / 内部 dashboard retired 说明冲突。工作区 README 的文档修订尚未提交，不能当作 GitHub main 内容。
- M0 没有部署。canonical `main` 仍有上述文档未提交改动；release 脚本会拒绝 dirty checkout。

### 外网运行状态

`https://stock.manqiaotechnology.com/api/platform/readiness` 在 2026-10-19 23:26 返回 HTTP 200、`status=PARTIAL`：

- `latest_market_date=2026-10-19`，`latest_trade_date=2026-10-19`，外网 strategy artifact date 也是 10-19。
- warnings：`exact-date official strategy manifest unavailable for 2026-10-19`、`review queue empty; snapshot step skipped`；`review_evidence_snapshots` 为 partial。
- `ops.strategy_daily_eod_status` 的 10-19 行却是 `success`，三个策略也都是 `success`，review_rows=15；本地 `strategy_eod_publish_summary.json` 标为 `status=success,publishable=true`。
- 同一 10-19 日期的 `/api/review-queue` 返回 3 个 strategy group、共 15 个 Top5 项；`ops.review_item_snapshot` 与 `ops.evidence_digest_snapshot` 各有 15 行。但 15 个 evidence digest 均为 `PARTIAL`，缺少 `full_evidence_digest`。本地发布摘要中的 `review_evidence_snapshots_summary.json` 则记录 `snapshot_status=skipped,row_count=0`。

以上是当前运行状态之间的可复核不一致，不推断其根因，也不在 M0 修复。需要在后续运维 Gate 中对齐发布摘要、DB snapshots、readiness 与 review-queue 消费路径。

## 3. 两条真实数据链

### 3.1 主题研究：主题 → 节点 → 公司映射 → 证据/审核 → 前台

```text
report / company filing / official source
  -> research.theme_research_source_item
  -> research.theme_research_content_claim + theme_research_claim_source / claim_node
  -> research.theme_research_node + value_assessment
  -> research.theme_research_company_mapping
       + mapping_evidence_item + company_mapping_evidence
  -> review status / review_event / object_revision
  -> GET /api/research/theme-decomposition/themes/{id}[/nodes|sources|claims|companies]
  -> dashboard/src/components/ThemeResearchWorkspace.tsx
  -> GET /api/assets/{asset_id}/theme-research-context
  -> dashboard/src/components/StockWorkspace.tsx
```

生产 API 返回 25 个主题；只读 DB 查询得到相同的 25 themes、270 nodes、268 source items、308 claims、236 company mappings。主要当前状态：

| 对象 | 当前数量与状态 |
|---|---|
| Themes | 25：24 `reviewed`，1 `draft` |
| Nodes | 270：220 `reviewed`，36 `needs_evidence`，14 `draft` |
| Sources | 268：255 `accepted`，7 `needs_full_text`，6 `lead_only` |
| Claims | 308：301 `reviewed`，2 `draft`，2 `research_lead`，3 `blocked`；evidence status 为 290 `verified`、13 `partially_verified`、3 `unverified`、2 `contradicted` |
| Company mappings | 236，均为 `reviewed`、`primary_business`；102 条 `revenue_relevance=undisclosed` |
| Value assessments | 213 |

可见证据不等于已证明竞争力：`reviewed` 表示当前平台审核状态，不代表收入、客户验证、份额、价值捕获已全部证实。236 条映射中有 102 条收入相关性未披露；生产映射证据类型集中在 product relationship（220）、revenue materiality（199）、business stage（79）和 service relationship（15），没有 `customer_validation` 或 `capacity_order` 类型记录。

来源以 company filings 为主：248 条；official article 9、official report 3、broker report 2、media article 2、social post 2、video claim 2。两个 broker reports 均为 S2/`needs_full_text`，当前 Theme Research DB 没有吸收本批 100 篇 stock-report library 的证据关系。Themes API 各主题 `source_count` 合计261，source_item表有268条active rows；其中3条没有 theme-source link。两种计数的其余差异未在 M0 完全对账，不把“source count”混作同一口径。

**新鲜度和审核历史：** Theme `last_updated` 是 2026-07-10 至 2026-07-16；主题对象最大 `updated_at` 是 2026-07-31。Source `publish_date` 最新 2026-07-10，13 条为空；255 条 dated sources 早于 90 天，8 条早于一年。Schema 没有 stale 状态或 TTL，也没有 `available_at` / `collected_at` 字段；source provenance 当前没有这些时间键。全库只有 2 条 Theme Research `review_event`（1 次 source transition、1 次 rollback），而当前 reviewed claims/mappings 数量远高于此；不能仅凭当前 status 推断每条都保有逐条审核事件。

**任务书指定文档与生产的对照：** `docs/theme_research_database_v1.md` 记载的 2026-07-11 bootstrap 数量（2 themes/34 nodes/24 sources/12 claims/10 assessments/4 mappings）是旧快照；当前生产只读 DB 为25/270/268/308/213/236。`docs/ops/theme-research-25-production-restore-20260731.md` 的25/270/268/308/236与当前生产 counts 相符，但本次核验只能确认数量仍相符，不能把7-31快照当作最近更新。`docs/theme_research_workflow_integration_v1.md` 所述“AI供电 reviewed、人形机器人 draft、research-only/不入 signal/admission”与当前 API 状态相符；roadmap 仍把人形机器人 2B 列为证据缺口。

Theme 报告版本表目前只有一条 `pending_review`：AI 供电 `2026-08-03.1`，PDF 路径为空。stock-prod 报告根目录有 `manifest.json` 与 `report.md`，没有 PDF；本机 `reports/theme-research/` 不存在。普通 Theme report 读取路由要求用户 session，审核路由另有管理员/CSRF gate。

**Artifact fallback 缺口：** 当前 checkout 的 Theme Research artifacts 仅包含 2 themes、34 nodes、20 sources、12 claims；company mapping artifact 仅 4 mappings；本地 priority queue 为21项。生产 DB 是25 themes/270 nodes/236 mappings。唯一 theme-to-Tech-Bottleneck crosswalk 是 AI Power：4 个 AI power mappings 中2个 linked、2个 coverage gaps。若生产 DB 失效后切到文档所称的 artifact fallback，当前 checkout 的 artifact 包不能重建完整 25-theme DB 状态。

### 3.2 正式科技卡脖子：候选 → PIT snapshot → 排名 → 组合/回测 → EOD

```text
outputs/research/strategy_daily_eod/<date>/tech_bottleneck_candidate_source/
  strict_153_st_only_financial_state_candidates.csv
  + public.market_daily_bar (adjust_type=hfq)
  + market_regime_confirmation_daily.csv
  -> build_point_in_time_candidate_snapshots()
  -> _bottleneck_score()
  -> Top5 / biweekly / 10 bps / max position 20% / rank_exit_top10_1d
  -> strategy_tech_bottleneck_{review,equity,positions,trades}.csv
  -> ops.data_run_manifest + ops.strategy_daily_eod_status
  -> external readiness / review queue
```

正式配置来自 `strategy_publication_contracts.py` 与 `tech_bottleneck_eod.py`：`strict_153_st_only_financial_state`、Top5、双周调仓、10 bps、单票上限20%、hfq、`rank_exit_top10_1d`。另一个直接 V1 frame builder 的默认值是 weekly/20 bps；做比较时必须显式使用正式 contract，不能混用默认值。

候选评分的实际公式在 `tech_bottleneck_candidates.py`：`0.45 × normalized hit_count + 0.25 × first-hit freshness + 0.30 × 1 - close/rolling-120d-high`。其中 `freshness` 是距 `first_hit_date` 的天数，不是来源或证据的新鲜度；低位项是距滚动120日高点的价格位置。这是证据命中、首次命中年龄、个股价格位置排序；没有将公司竞争壁垒、收入兑现、财务质量或估值作为排名因子。Base CSV 有财务字段和 `financial_as_of_date`，但这些主要用于候选过滤/PIT eligibility，不进入该 score。

正式候选源文件名含 `strict_153`，实际本次 10-19 文件有 **148 个 unique asset_id**。最新 10-19 candidate snapshot 有 148 个股票、23,952 行、189 个 trade dates（2026-01-05 至 2026-10-19）；各行 `candidate_as_of_date`、`financial_as_of_date`、`technical_as_of_date` 均经校验不晚于 `trade_date`。但对当前 148 个 source rows，`financial_as_of_date` 最大仅 2026-05-22，`technical_as_of_date` 最大仅 2026-06-05；每日 `data_as_of_date` 推进不能代替底层基本面/技术字段的新鲜度。

市场 regime 暴露文件 `market_regime_confirmation_v1_tight3b_bt100_20230103_20260605/market_regime_confirmation_daily.csv` 最新日期为 2026-06-05。`_extend_market_exposure()` 只在 requested end date 追加一行；组合模拟按精确 `trade_date` 查找暴露，找不到时使用 `1.0`。在 2026-01-05 至 2026-10-19 的21个双周调仓日中，6-05之后有9个调仓日没有暴露行，且 end-date 追加行没有覆盖这些中间日期。故近期 regime overlay 并非可靠的日频输入，且缺日期时默认全暴露；不能将当前 baseline 解释为已验证的回撤/行业 regime 控制结果。

### 3.3 Review Universe 与正式策略隔离

`GET /api/research/tech-bottleneck/review-universe/{summary,stocks,stocks/{code}/evidence,stocks/{code}/sources,decision-summary}` 服务的 359 行 dataset 在 `dashboard/src/pages/TechBottleneckReviewPage.tsx` 展示。API 统计 252 `v5_hydrated`、29 `v5_targeted_hydrated`、78 `v7_proposal_new`；source index 1,013行、evidence index 8,077行。359行 `frontend_review_status` 全部 `pending_review`，decision summary 为 0 reviewed/359 pending；`used_for_signal=0`、`used_for_admission=0`、数据库写入与 reviewer write 均关闭。

这359行与正式 `strict_153` strategy pool 是不同对象；当前页面的 `quality_pool` 字样是研究层状态，不等于正式准入。API 同时报告 `new_pdf_download_count=0`、`evidence_backfill_performed=false`；因此这次 stock report library 导入没有进入该 review-universe 的 source/evidence index。

## 4. 正式基线与现有回测

### 当前正式 EOD 产物

调度器在 M0 审计期间完成 2026-10-19 EOD；本轮没有触发该任务。可复核路径：`outputs/research/strategy_daily_eod/2026-10-19/`。本地发布摘要为 `status=success,publishable=true`，3个正式策略成功，Top5 review rows 合计15。`ops.strategy_daily_eod_status` 同日也为 success。

科技卡脖子官方历史 equity 文件截至 10-19：

- `strategy_tech_bottleneck_equity.csv`：189行，2026-01-01 至 2026-10-19；初始 equity 1.0、末值 1.55948，累计约 +55.95%，最大回撤 -27.49%。
- 同一产物：turnover 合计 9.64、transaction_cost 合计 0.00964；trades 61行、positions 926行；10-19 仍为4只实际持仓/0.8 exposure。
- 10-19 review Top5 在 `strategy_tech_bottleneck_review.csv`，来源同一正式 strategy run。

这是一段当年运行曲线，不是预先冻结的样本外检验；当前输出没有独立 holdout 标签、置信区间、成本敏感性或参数搜索记录。不得把 +55.95% 单独当作新增特征有效的证据。

### 已有 regime 对照

`outputs/research/industry_regime_gated_backtest_*` 是 `industry_focus_v2` 行业 Top20 软权重实验，不是 Tech Bottleneck 股票策略。其 `baseline_top20` after-cost 累计 -0.25%、最大回撤 -28.70%；`v2_soft_weight` -21.82%/-45.97%；`regime_gated_soft_weight` -37.71%/-50.86%；`regime_gated_smooth_weight` -17.88%/-35.51%。报告明确结论是正向行业增强未证明有效，不能把该结果当成 Tech Bottleneck regime challenger 的收益证据。

### Selection v2 / PIT 与 Quality Pool v7

`scripts/run_tech_bottleneck_research_selection_layer_v2_*` 已有设计、输入重建、候选生成和 event-level PIT replay 代码。其计划变量覆盖 announcement/fundamental、Baostock valuation percentile、Baidu cross-validation、事件风险、30/60/90/120日 forward-return 结果；PIT 逻辑按 `first_admission_date` 截断。它是历史 watchlist event-level review/forward-return 分析，不等同于含交易成本、持仓和涨跌停约束的投资组合 backtest。

但当前这些 source input/output 目录均缺失：`tech_bottleneck_research_selection_layer_v2_design/`、`tech_bottleneck_research_selection_layer_v2_pit_input_reconstruction_v1/`、`tech_bottleneck_research_selection_layer_v2_pit_replay_v1/`、`tech_bottleneck_research_selection_layer_v2_generator_v1/`，以及其 announcement/fundamental/valuation/watchlist 数据目录。测试设计预期 102 个 standard admission events；当前没有 replay artifact 可核验该事件数、各规则的实际覆盖率或样本外指标。

Quality Pool v7 也有 proposal、manual-review、manual-approval-ingest 代码和测试，但三个专属 output 目录为空。上游 V5 manifest、V6 proposal/manual approval 文件也缺失。可复用的相邻成果是 `latent_manual_review_standard_equivalence_gate_v1`：52 个 proposal、1,097条页码引用、52条 primary-source-supported；配套 backfill 有52只、156份PDF、1,097条页码引用。它明确保持 `research_only`，没有自动加池或改变信号/准入。该结果不等于已生成或批准 V7 quality pool。

## 5. 研报数据与科技管线

外网 `/api/research-reports/summary` 当前返回 59,355 distinct reports、3,391 covered stocks、latest publish date 2026-10-13、latest feature date 2026-07-23；source 中 `研报客 API` 2,173条。DB 实际 `stock_report_source` 59,355行、`stock_report_event` 59,356行（部分报告关联多个股票）；其中整体有890个 source `publish_date=NULL`、891个 event `report_date=NULL`。

本地 100 篇新报告台账显示四批中的 `theme_batch4` 47篇都在原始 `download_manifest_remaining47.csv` 以 `date` 保存日期，但标准化清单 `publish_date` 为空；生产 source/event 中这47篇对应的 `publish_date` 与 `report_date` 也是 NULL。原始 manifest 日期有效、最晚 2026-10-18，而生产 summary 的 `latest_publish_date` 仍停在 2026-10-13。其余53篇新报告日期有值。全部100篇报告保持 `public_access=false`，关联事件 `auto_trade_enabled=false`；PDF文件可通过现有 stock report route 阅读。

现有本地报告库清单为107条（100个首次下载 UUID、7条复用）；67条有明确股票代码，40条保留为主题/行业报告；107条都有本地 PDF 路径且 `public_access=false`。本批100篇的结构化 PDF backfill 为99 `parsed`、1 `empty_text`；该 backfill 提取目标价/评级/预测/风险等结构字段，不等于逐页 claim 已进入 Tech Bottleneck evidence index。

**对之前“26篇新标题命中科技卡脖子关键词”的更正：** `report_keyword_usage_audit.csv` 是新标题与 pipeline keyword 的文本重叠审计，不是页码级 evidence，也不等于实际被本次 candidate run 使用。26条重叠中，16条 `report_date` 非空，10条来自缺日期的 `theme_batch4`，会被现有 SQL 的 `e.report_date >= 2024-01-01` 排除。该 SQL没有 `report_date <= as_of_date` 上界；即使日期补齐，也不能直接把它用于历史 PIT 回放。候选生成器消费的是报告标题/summary/industry_view/company_view关键词，不是PDF逐页 claim。

新100篇 stock reports 当前没有加入 Theme Research 的 `theme_research_source_item`，也未加入359行 Tech Bottleneck review-universe evidence/source index。Stock report feature table 最新日为 2026-07-23，没有10-19新 feature row。因而“PDF可读”“元数据关键词命中”“页码证据审核”“PIT可用”“competitive moat 已验证”是五个不同状态；本次导入只完成前两层的一部分。

另一个 research-only A-share discovery run 产出 3,227 candidates：Tier B 1,008、Tier C 60、Excluded 2,159、Tier A 0；keyword-hit CSV 共3,095行，其中 report-metadata channel 1,717行、覆盖1,008只股票，另有 keyword-scan 1,378行。全部3,227行 `research_only=true`、`used_for_signal=false`、`used_for_admission=false`。该 run 的 `seed_watchlist_count=0`，15个预期 hardening 输入文件全部缺失，acceptance 为 `conditionally_ready_with_data_gaps`。这些 metadata 关键词结果只支持候选发现，不是已验证的瓶颈论断或回测增量。

**访问控制风险：** 生产 `/api/research-reports/{report_id}/pdf` 在未登录请求下可返回 HTTP 206 的 PDF 内容；远端 `.env.dashboard` 未设置 `STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED`。路由按允许根目录解析 PDF，但不检查 `public_access`。因此，即使100篇新导入行标记 `public_access=false`，当前付费报告仍可被外网访客直接访问；若非预期授权范围，需要单独立项处理。M0 只读取5字节验证响应，没有下载全文，也没有改权限代码。

## 6. Gap Matrix（按研究价值、可信度与代价排序）

| 优先级 | 状态 | 研究价值 / 可信度 / 代价 | 缺口与事实 | 证据 |
|---|---|---|---|---|
| P0 | `blocked_by_data` | 高 / 高 / 低 | 47篇新报告缺 `publish_date` 与 `report_date`；同时 stock report PDF 路由不执行 `public_access`。先确认访问授权，再做受控日期回填；不要把这些报告称为已经进入 PIT 管线。 | 本文件第5节；`normalized_100_download_manifest.csv`；`report_keyword_usage_audit.csv`；`app.py:1672-1682` |
| P0 | `blocked_by_data` | 高 / 高 / 中 | 当前正式策略使用的 regime 文件止于 2026-06-05；9/21 个 6-05 之后的双周调仓日没有精确暴露值，代码默认 `1.0`。在重做 baseline 前须明确缺值策略并更新输入。 | 第4节；`market_regime_confirmation_daily.csv`；`serenity_tight3b_c2_experiment.py:336-356` |
| P0 | `partially_implemented` | 高 / 高 / 中 | 可读的 10-19 正式 EOD 曲线存在，但 strategy readiness 仍为 PARTIAL；发布摘要、manifest availability、review/evidence snapshots 状态不一致。先冻版本、输入hash、run id、参数和工件，形成可重跑 baseline。 | `/api/platform/readiness`；`strategy_eod_publish_summary.json`；`ops.strategy_daily_eod_status`；review snapshot API |
| P1 | `partially_implemented` | 高 / 中 / 中 | v2 PIT/ablation 设计和测试存在，但本机输入与回放产物目录缺失，102事件预期没有实际 artifact 支撑。重用现有代码，补齐输入后再报告样本量、缺失率、事件级 forward returns。 | `scripts/run_tech_bottleneck_research_selection_layer_v2_*`；对应测试；第8节 |
| P1 | `partially_implemented` | 高 / 中 / 中 | Tech Bottleneck 当前排名是 hit-count/first-hit freshness/120日低位分；财务仅参与静态 candidate filter，估值不在正式分数里。需要将moat/财务/估值作为独立、可解释的 shadow challenger，不改正式 Top5。 | `tech_bottleneck_candidates.py:388-399`；`tech_bottleneck_eod.py:28-37` |
| P1 | `partially_implemented` | 高 / 中 / 中 | 生产主题、来源、claim、node、mapping审核系统已存在；但所有source缺 `available_at`/freshness状态，95-101日没有更新且大量日期为空，难以做历史 PIT 复原。复用既有版本与审核模型，补显式时点和 revalidation 规则。 | `theme_research_db_schema.py:68-188`；DB counts in 第3节 |
| P1 | `partially_implemented` | 高 / 中 / 中 | 生产 DB 有236 reviewed mappings，local artifact fallback 只有4；crosswalk只覆盖AI Power 4条中的2个linked/2个coverage gap。先定义三pilot的映射/evidence覆盖，不新建门户。 | local artifact summary；`theme_tech_bottleneck_crosswalk_v1.json`；外网 themes API |
| P1 | `missing` | 高 / 中 / 中 | 还没有可复核的“主题产业瓶颈 × 公司壁垒 × 财务兑现 × 估值/市场状态”独立机会研究层；Theme `research_priority_score` 明确不含价格/估值/时机。应另建版本化评估，不能复用该分数做买入排序。 | `theme_research_priority.py:71-105`；task brief M1/M2 |
| P1 | `blocked_by_data` | 高 / 高 / 低 | V7 代码存在；V5/V6与V7 proposal/manual review输入缺失。review-universe虽标78条 `v7_proposal_new`，359条仍全部 pending、0人工裁决、0准入。必须先恢复/校验提案来源和审批账本。 | `/api/research/tech-bottleneck/review-universe/summary`、`decision-summary`；V7 outputs目录；`quality_pool_layer_v7_*` tests |
| P2 | `already_implemented` | 中 / 高 / 低 | 已有独立Theme Research表格页、Stock Workspace上下文、Tech Bottleneck只读review页、受控 Theme report审核与发布。不要重建第二套门户/审核系统。 | `dashboard/src/components/ThemeResearchWorkspace.tsx`；`StockWorkspace.tsx`；`TechBottleneckReviewPage.tsx`；`theme_research_report_store.py` |
| P2 | `partially_implemented` | 中 / 中 / 低 | A股全市场候选探索输出3,227行（Tier B 1,008、Tier C 60、Tier A 0），全部research-only、signal/admission=0；缺种子清单且硬化包15个预期文件全缺。它是高召回发现集，不是策略池或已确认卡点公司名单。 | `a_share_candidate_universe.json`、`a_share_candidate_guardrails.json` |

## 7. 最小增量实施方案（待审核，不在 M0 执行）

### M1：先用现有审核链做3个可反驳的竞争力 pilot

1. **AI供电：** 生产主题为 reviewed，13 nodes、10 sources、8 claims、4 companies、3 evidence gaps；现有 2026-08-03.1 报告仍 pending，不把它当正式发布报告。选择一个已有 reviewed node/company 做 dossier，补产品、收入材料性、客户/订单、国内外竞争、路线绕行/替代、反证和未知项。
2. **半导体设备/材料：** 制造设备主题 11 nodes、10 sources、10 claims、8 companies、2 evidence gaps；材料主题 9 nodes、10 sources、12 claims、10 companies、0 evidence-gap nodes。必须区分“节点有证据”与“公司已兑现收入”。
3. **人形机器人：** 生产主题仍是 draft，21 nodes、7 sources、4 claims、0 company mappings、12 evidence gaps。Pilot 必须验证系统能以 `draft/evidence_gap/unknown` 降级，不建立强竞争力名单凑样例。

复用 `theme_research_source_item`、`content_claim`、node review、`company_mapping`、mapping evidence 与 `review_event`；如确需公司级 moat 评分，只新增一个版本化的研究评估对象/工件。不得改 P10 priority 语义，不得接交易信号或质量池。

### M2：冻结基线后做离线 challenger

1. 以 10-19 EOD 的正式 contract 为参考，冻结具体代码 commit、实际148行候选池、源文件 SHA-256、PIT snapshots、市场价格区间、regime输入、成本/调仓/保护规则和实际发布文件。需先解释“strict_153”与148行的差异。
2. 单独解决6-05后regime缺数。缺失日期必须显式 `unknown/blocker` 或使用已验证的历史可用状态，不得静默按1.0暴露。
3. 恢复 v2 既有 PIT 输入所需文件；以事件日期为 cutoff，逐源验证披露/可用日期；不使用当下已审映射回写历史。v2 当前是 event-level forward-return，不是组合回测；组合验证另用已有 backtest engine并遵循 T+1、停牌/涨跌停、成本、ST、退市和流动性限制。
4. 预先固定时间切片和验证窗口，再依次比较 baseline、`+ reviewed moat`、`+ fundamental quality`、`+ valuation-risk`、`+ drawdown/regime`，每次只加一类特征。输出样本数、缺失率、IC/分层、收益回撤、turnover/cost、行业/市值暴露和成本敏感性；可接受“不改善”结论。
5. 所有 challenger 留在 research/影子模式；不更改 `strategy_daily_eod` 发布、官方 Top5、`used_for_signal`、`used_for_admission` 或 frozen quality pool。

### M3-M4：只在 M1/M2 Gate 通过后

- M3 复用当前 AppShell、Theme Research、Tech Bottleneck review、Stock Workspace 和现有管理员报告审核/发布流程；展现来源、反证、unknown、时点、policy/data digest 和实验 run id，不开第二门户，不向普通用户展示未审核报告。
- M4 再设计来源到期 `needs_revalidation`、公告事件更新、判断结果回看和运行监控；生产迁移需要备份、dry-run、rollback、权限核验和 release gate。

## 8. 测试与 M0 执行结果

### 本轮定向测试

运行：

```bash
.venv/bin/pytest -q --tb=short \
  tests/test_tech_bottleneck_research_selection_layer_v2_design.py \
  tests/test_tech_bottleneck_research_selection_layer_v2_generator.py \
  tests/test_tech_bottleneck_research_selection_layer_v2_pit_input_reconstruction.py \
  tests/test_tech_bottleneck_research_selection_layer_v2_pit_replay.py \
  tests/test_tech_bottleneck_quality_pool_layer_v7_proposal.py \
  tests/test_tech_bottleneck_quality_pool_layer_v7_manual_review_packet.py \
  tests/test_tech_bottleneck_quality_pool_layer_v7_manual_approval_ingest.py \
  tests/test_tech_bottleneck_pit_evidence_replay.py \
  tests/test_theme_decomposition.py \
  tests/test_theme_company_mapping.py \
  tests/test_theme_research_priority.py \
  tests/test_theme_tech_bottleneck_crosswalk.py \
  tests/test_industry_regime_gated_backtest.py \
  tests/test_strategy_daily_eod.py \
  tests/test_dashboard_backtests.py \
  tests/test_dashboard_theme_research_context.py \
  tests/test_dashboard_theme_research_context_api.py \
  tests/test_theme_research_store.py \
  tests/test_theme_research_db_schema.py \
  tests/test_dashboard_theme_research_reports.py
```

结果：**389 passed, 33 failed, 27 warnings（15.28s）**。33项失败均为 `FileNotFoundError`，原因是对应的 gitignored V2 design/PIT/replay、V5/V6、V7 proposal/manual-review 输入或输出文件当前缺失；例如 V2 `research_selection_v2_feature_dictionary.csv`、V7 `quality_pool_layer_v5_manifest.csv` 和 V7 `v7_manual_review_candidates.csv`。本轮没有恢复这些被忽略的研究产物，也没有把失败伪装成代码测试通过。此前全仓 pytest 在约59%进度被中断并出现失败，不作为完整测试结果。

### 关键核验

- `git ls-remote origin refs/heads/main`、`git rev-parse HEAD` 和 `git rev-parse origin/main` 一致为 `f2b83294...`。
- 外网 release：`4d7f6aa8...`；`/api/platform/readiness` 当前 `PARTIAL`，latest trade/market/strategy artifact 均为 2026-10-19。
- 外网 Theme Research API 与生产只读 DB 交叉确认 25/270/268/308/236 counts。
- `theme_research_runtime` 连接返回 `transaction_read_only=on`；M0 无生产 DB 写入或发布。
- 外网 stock-report PDF 无登录 Range 请求返回 206 `application/pdf`；此次只读取了5个字节确认路由，没有下载全文。
- **本轮没有测试/修改正式策略文件、没有新建审核决定、没有执行回测写入、没有提交或推送。**

## 9. M0 Gate 与待审核决定

**M0 交付状态：审计已完成，等待人工审核。**
**M2 正式策略优化 Gate：暂不通过。** 当前存在市场 regime 时点缺口、实际候选池148与 strict_153 标签差异、缺少可复现的 v2/OOS artifacts，以及 production readiness 与 EOD publish summary 的不一致。不得据此修改正式策略或宣传新增特征有效。

建议审核顺序：

1. 确认是否授权单独修复47篇报告日期字段，并验证原始下载清单、PDF和数据库 report/event 关联一致；只改 dates，不改评分、signals 或 admission。
2. 确认 regime 缺数处理策略及148/153 pool 口径，再形成不可变 baseline run card。
3. 批准后启动 M1 三个主题 pilot；待证据状态、反证、未知项和映射 Gate 通过，再讨论 M2 shadow 实验。

本次交付仍在本机工作区，尚未 commit/push，符合“先交 M0 供审核”的阶段边界。
