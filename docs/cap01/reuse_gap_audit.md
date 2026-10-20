# CAP-01 现有能力复用与差距清单

审计范围：`src/stock_research/theme_*.py`、`research_evidence_registry.py`、
`tech_bottleneck_*`、dashboard 研究 API、yanbaoke 语料与 PDF 管线、M1 dossier。
基线分支：`audit/tech-strategy-m0-20261019@8f29ac36`（worktree `cap-01`）。

## 已有、直接复用（不重写）

| 能力 | 位置 | 形态 |
|---|---|---|
| 三级研究对象模型 | `theme_research_store.py` + `research.*` 表 | source_item / content_claim / mapping_evidence_item（claim_id、source_id、publish_date、excerpt_locator 页码定位、confidence、evidence_status、platform_use_status），带状态机校验、快照、幂等导入、串行化事务 |
| claim/source/node 审核 | `theme_research_store.review_*` + `dashboard/app.py` `/api/research/theme-decomposition/*` | 人工审核端点 + review history + rollback |
| 研究报告注册与阅读 | `theme_research_report_store.register_report_manifest`、`dashboard/theme_research_reports.py` | markdown+PDF manifest → `pending_review` → admin publish → 既有阅读器；天然满足"人工审核与记录不同意见" |
| research_only 护栏 | `theme_research_priority.py` GUARDRAIL_FIELDS + FORBIDDEN_DIMENSIONS | `price/valuation/return/momentum/technical_signal` 已硬性禁止；`used_for_signal`/`used_for_admission` 字段就位 |
| 页码证据摘录管线 | `outputs/research/tech_bottleneck_review_universe_yanbaoke_pilot2_20261019/` | `reports_pagewise_v2/<code>_<name>_evidence_brief.md`（20 家）：分节摘录 + `[P...]`公司披露/`[B...]`券商观点标签 + 第 N 页；`page_citation_manifest_v3.csv`、`download_manifest.csv`、`pdf_parse_audit_v3.csv` |
| 研报语料与映射 | `theme_research_yanbaoke_quota_fill100_20261019/`、`tech_bottleneck_a_share_candidate_universe_yanbaoke100_20261019/` | 474 篇下载队列 + 100 篇已取语料；`theme_company_mappings.csv`（主题→公司→materiality，含 `concept_only`）；`research.stock_report_source/event` 按股票检索 |
| 券商报告 PDF 访问 | `dashboard/research_reports.py` + `/api/research-reports/{id}/pdf` | 会话鉴权（public_access 修复待单独批准，不在本线） |
| 公司-主题上下文 | `dashboard/theme_research_context.load_asset_theme_context` | 按 asset_id 反查所属主题/节点/claims |
| M1 dossier 试点 | `docs/research_upgrade/01_theme_competitive_moat_pilot.md`、`02_theme_moat_evidence_deepening.md` | 英维克/北方华创六维草稿（客户验证/份额/毛利多为 `unknown` 已如实标注） |
| 证据回灌队列范式 | `tech_bottleneck_evidence_workflow.py` | missing/weak/partial/strong 分级 + backfill queue，供研究缺口输出仿照 |
| 证据工件表 | `research_evidence_registry.py` → `research.evidence_artifact` | content_hash + payload 注册（digest/review snapshot 类） |

## 真正缺失（CAP-01 新建）

| 缺口 | 说明 |
|---|---|
| 公司级六维证据模型 | 现有 claim 绑定 theme/node；无"公司×六维（技术壁垒/产业链地位/商业化能力/竞争优势/财务兑现/风险与反证）"的画像结构；evidence 缺 `evidence_direction`（support/refute/unclear）与 `available_at`/`ingested_at`（现有仅 publish_date + mtime 代理） |
| 公司研究引擎 | 无"输入 stock_code → 聚合证据 → 输出画像/证据矩阵/正反分析/缺口/结论"的可重复流程；无 UNKNOWN/NEEDS_EVIDENCE 强制语义 |
| 反证主动整理 | brief 有"风险与反证"节但无逐条 direction 标注，无同维冲突证据检测 |
| 公司画像直达入口 | 工作台按 theme 浏览；缺 stock_code 直达画像（最小集成=经现有 report 注册管线进入 pending_review，复用鉴权阅读器，不新建页面） |
| 结构化研究缺口输出 | 需可交给 DATA 线的字段级需求清单（仿 backfill queue 但面向公司维度） |
| 证据可用性时序 | `publish_date` ≠ `available_at`；引擎须携带 `evidence_asof`/`input_snapshot` 并在 PIT 语义下标注"事后才获得"的证据 |

## 结论

底层 claim/evidence/source 存储、审核流、PDF 语料、research_only 护栏全部就位；
CAP-01 只新增**公司维度聚合与分析层**（models + evidence feed + engine + report），
通过现有 manifest/审核管线暴露结果，零新 dashboard 页面、零生产写入。
