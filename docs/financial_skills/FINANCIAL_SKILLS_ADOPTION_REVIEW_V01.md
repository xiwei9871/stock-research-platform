# 官方金融 Skills × A 股研究平台 适配评估 V0.1（公开版）

日期：2026-11-01 ｜ 性质：只读调研 + 隔离 POC 汇总，research_only，不构成投资建议

> 公开版说明：本文只包含 Anthropic 官方仓库分析、平台已公开代码中的模块名、可公开核验的上市公司定期报告数字，以及去除内部研究内容后的 POC 汇总。内部研究 case 的 claim、证据 ID、券商线索和四份 POC 原始输出不在公开版中，保留在内部研究分支。F1 设计中的例子是合成示例，不代表对任何公司的研究结论。

## 0. 结论摘要

| 决策问题 | 结论 | 证据等级 |
|---|---|---|
| Q1 最值得复用的三个 Equity Research Skills | thesis-tracker、earnings-analysis（只取方法）、catalyst-calendar（用确定性规则实现） | SOURCE_VERIFIED + 单次 POC |
| Q2 Market Researcher Agent | 不采用 Agent 本体，只抽取三个做法：读文档的子代理只返回经 schema 校验的 JSON；只有一个 worker 持有写权限；每个产物完成后人工停顿复核。若以后要复用本体，必须先改掉只接受 ASCII 的 schema（§4） | SOURCE_VERIFIED |
| Q3 Financial Analysis 可增强项 | competitive-analysis 的来源等级、同期可比和护城河评分；comps-analysis 的指标口径规范（数值由 SQL 计算）；3-statement-model 的报表勾稽检查 | SOURCE_VERIFIED + ARCHITECTURAL_JUDGMENT |
| Q4 官方金融数据 MCP | 当前不引入，继续使用自有 A 股数据。订阅要求和 A 股覆盖分三档列出（§5），多数项目需要向供应商询价或询问覆盖范围，本文不作绝对判断 | 部分 SOURCE_VERIFIED，多数 NOT_VERIFIED |
| Q5 下一阶段最小功能 | 候选：F1 CAP-07 R1 可证伪研究假设记分卡（§11）。它和统一回测 Gate C 是两条独立工作流，互不阻塞 | ARCHITECTURAL_JUDGMENT，产品价值未验证 |

**结论的证据边界**：
- 四组 POC 每组只运行了一次，由单人评分，没有盲评。
- 适配组的提示词由评估者编写，评估者熟悉平台证据模型。
- 确定性 CAP-01 dossier 引擎的基线对照没有跑成，原因是它需要读取的数据库在运行时不可用。
- 因此 POC 分数只能说明"适配方向有潜力"，不能作为产品验收。

证据等级标签：`SOURCE_VERIFIED`（已读源文件）、`WORKFLOW_TESTED`（隔离 POC 已运行）、`DEPENDENCY_REQUIRED`、`INSTALLATION_REQUIRED`、`NOT_VERIFIED`、`ARCHITECTURAL_JUDGMENT`。

## 1. 调研对象与方法

- 官方仓库：`anthropics/financial-services`，调研 commit `60565064557ca77b12f62aa7877f365d111c129d`（2026-10-28），License 为 Apache-2.0。浅克隆后只读取，没有安装插件，也没有运行仓库内的任何代码。
- 仓库规模：`.claude-plugin/marketplace.json` 注册了 19 个插件；SKILL.md 共 112 个（含 agent-plugins 中的同步副本）；Managed Agent cookbook 有 10 个。
- 目录结构：
  - `plugins/vertical-plugins/`：skill 源文件、commands 和 `.mcp.json`
  - `plugins/agent-plugins/`：命名 Agent 的系统提示词和技能副本
  - `managed-agent-cookbooks/`：`agent.yaml` 和子代理 yaml
  - `plugins/partner-built/`：LSEG、S&P Global
- equity-research 和 financial-analysis 两个插件的 `hooks/hooks.json` 都是 `{"hooks": {}}`。插件不带任何自动校验，质量控制完全依赖提示词。
- 官方 README 第 8 行声明：这些 Agent 只起草工作底稿，不做投资建议，所有输出都要等人工签核。

## 2. 官方能力盘点

### 2.1 Equity Research（9 个）

| Skill | 实际内容 | 关键数据依赖 | 判定 |
|---|---|---|---|
| sector-overview | 88 行清单式流程：TAM、行业结构、价值链、趋势、Top 5-10 公司表、估值、投资含义 | Web/MCP；TAM 须注明出处 | REFERENCE_ONLY |
| thesis-tracker | 67 行：论点、3-5 个支柱、风险、催化剂、记分卡、带日期的更新日志；要求论点可证伪，反证与支持证据同等追踪 | 无 | ADAPT_FOR_A_SHARE |
| earnings-analysis | 228 行，另有 3 个 reference 共 1,142 行：先核对当前日期和发布日期，再做 beat/miss，附引用清单，产出 8-12 页 DOCX | 一致预期、10-Q/EDGAR、电话会纪要 | ADAPT_FOR_A_SHARE（只取方法） |
| earnings-preview | 一致预期表、牛/基/熊情景、期权隐含波动 | 一致预期、期权数据 | REFERENCE_ONLY |
| initiating-coverage | 783 行，参考文件约 5,000 行；5 个任务严格串行，产出 30-50 页首次覆盖报告 | docx/xlsx 技能 | DO_NOT_ADOPT |
| model-update | 把实际值填进现有 Excel 模型，然后修订目标价 | 一个持续维护的卖方模型 | DO_NOT_ADOPT |
| morning-note | 1 页晨会纪要，包含 Top call 和交易建议 | 新闻流 | REFERENCE_ONLY |
| catalyst-calendar | 事件日历、周度预览，事后归档实际结果 | 财报日期数据、IR 页面 | ADAPT_FOR_A_SHARE（确定性实现） |
| idea-generation | 价值/成长/质量/做空筛选，加主题价值链扫描 | 筛选数据 | REFERENCE_ONLY |

### 2.2 Financial Analysis

| Skill | 要点 | 判定 |
|---|---|---|
| competitive-analysis | 来源冲突时按等级取舍：年报 > 业绩会 > 卖方 > 行业报告 > 新闻。要求同一财年、同一口径，每个数字都有引用。护城河分四类评分 | ADAPT_FOR_A_SHARE |
| comps-analysis | 661 行。禁止把 web search 当作主数据源；要求用公式而不是硬编码，附统计块和方法说明 | ADAPT_FOR_A_SHARE（数据换成自有库） |
| 3-statement-model | 填充三表模板，检查报表勾稽；数据提取参考的是 SEC 10-K | REFERENCE_ONLY（只借勾稽规则） |
| dcf-model | 1,263 行的 Excel DCF，WACC 和终值都按美股口径 | DO_NOT_ADOPT |
| audit-xls / clean-data-xls | Excel 公式审计和表格清洗 | DO_NOT_ADOPT |
| LBO 及投行类 skills | 投行和私募交付物 | DO_NOT_ADOPT |

### 2.3 Agents

- **Market Researcher**（`plugins/agent-plugins/market-researcher/agents/market-researcher.md`）：
  - 流程：sector-overview → competitive-analysis → comps（经 CapIQ/FactSet MCP）→ idea-generation → note-writer。
  - Guardrails：第三方材料一律视为不可信；没有出处的数字标 `[UNSOURCED]`；comps 完成后和成稿后各停一次，等人工审批；Agent 不负责分发。
- **Cookbook 三层隔离**（`managed-agent-cookbooks/market-researcher/README.md`）：
  - `sector-reader`：只有 Read/Grep 权限，不连任何 connector，只返回 JSON。
  - `comps-spreader`：只读 MCP。
  - `note-writer`：唯一持有 Write 权限的 worker。
- **Earnings Reviewer**：FactSet/Daloopa 拉数 → earnings-analysis → model-update → audit-xls → morning-note → 人工复核。核心依赖是一致预期和电话会纪要，这两项在 A 股基本拿不到。
- `agent.yaml` 中的 model 字段固定为 `claude-opus-4-7`。部署通过 `scripts/deploy-managed-agent.sh` 完成，属于生产 API 路径（§10）。

## 3. 与现有平台的对照（六个场景）

平台已有能力（均为仓库内已公开的代码）：
- `company_intelligence`（CAP-01）：六维公司档案，按 claim 判定，lead_only 证据不计入判定，研究截止日 PIT，sha256 指纹。
- `chain_bottleneck`、`chain_value_matrix`、`chain_t3_evidence`（CAP-02）：产业链节点判定、价值矩阵、分部收入证据。
- `capabilities/`（CAP-03..10）：`ResearchEnvelope` 契约和数据缺口词汇。
- `capabilities/baseline.py`（CAP-07）：追加式版本基线和差异比较。
- `financial_pit`：信号用的财报可用性规则。

| 场景 | 平台现状 | 官方方法的增量 | 结论 |
|---|---|---|---|
| 1 科技卡脖子主题 | 主题 → 节点 → 公司 → 证据已打通；节点级与公司级证据分开计分，lead_only 隔离 | sector-overview 的 why-now、逆风、关键多空争议、观察信号（signposts）；competitive-analysis 的护城河评分和来源等级 | 借鉴章节，不替换引擎 |
| 2 基本面研究 | finance.* 三表，docling 解析的定期报告页级摘录 | earnings-analysis 的日期核验、分部/毛利率/现金流逐项检查、引用清单 | 纳入财报变化说明模板；beat/miss 改为"业绩预告 → 快报 → 定期报告"的勾稽 |
| 3 财务 PIT | `financial_pit` 等确定性规则 | 没有增量。官方 skill 没有 PIT 概念，只要求"发布日期在 3 个月内" | 可用时点只由确定性规则计算，LLM 不参与 |
| 4 策略解释 | `research_narrative` 的支持/反对事实 | thesis-tracker 的证伪条件，以及对反证的同等追踪 | 作为解释层字段，不进入信号 |
| 5 每日简报 | EOD、每日复盘、推送 | morning-note 的"只放一个最重要事项"和"无新闻也是有效结论" | 只借格式，不引入交易建议和评级动作 |
| 6 结论持续跟踪 | CAP-07 有基线时能输出 claim 判定变化；但没有证伪对象，也没有披露驱动的检验点 | thesis-tracker 正好补上这一块 | F1 候选（§11） |

## 4. A 股本土化适配

**ASCII schema 和代码正则**（SOURCE_VERIFIED，官方 commit `6056506`）：

| 文件 | 字段 | pattern |
|---|---|---|
| `managed-agent-cookbooks/market-researcher/subagents/sector-reader.yaml` 第 22 行 | `sector` | `^[A-Za-z0-9 &/._-]+$` |
| 同上 第 31 行 | `facts[].claim` | `^[A-Za-z0-9 .,%$()_/&:-]+$` |
| 同上 第 32 行 | `facts[].source` | `^[A-Za-z0-9 .,_/:-]+$` |
| `managed-agent-cookbooks/earnings-reviewer/subagents/transcript-reader.yaml` 第 22 行 | `ticker` | `^[A-Z.]+$` |
| 同上 第 30 行 | `guidance_notes[]` | `^[A-Za-z0-9 .,%$()_/:-]+$` |
| `managed-agent-cookbooks/model-builder/subagents/data-puller.yaml` 第 25 行 | `ticker` | `^[A-Z.]+$` |
| `managed-agent-cookbooks/pitch-agent/subagents/researcher.yaml` 第 34 行 | `ticker` | `^[A-Z.]+$` |

影响：中文 claim、中文来源名，以及 `600519`、`688012.SH` 这类 A 股代码都无法通过校验。要复用这些子代理，至少需要做三处修改：
- 文本字段放开 Unicode，可用 `^[\p{L}\p{N}\p{P}\p{Zs}$%]+$`，或者只保留 `maxLength` 限制。
- 代码字段改为 `^[0-9]{6}(\.(SH|SZ|BJ))?$`。
- `source` 改为结构化引用，包含公告编号、报告期、页码。

这些 pattern 是官方用来防提示注入的一层防护。放开字符集后，需要在我方补上同等强度的约束，例如引用必须能解析到已入库的证据 ID。

**数据与制度差异**：
- **数据来源**：官方体系默认 SEC EDGAR、10-K/10-Q、电话会纪要和 Bloomberg/FactSet 一致预期。A 股对应的是巨潮资讯、沪深北交易所披露、互动易、问询函和自有数据库。A 股电话会纪要很少，稳定的一致预期也难以获得。
- **会计准则**：中国企业会计准则下没有 GAAP/non-GAAP 的二分，"扣非归母净利润"起类似作用，需要单列。
- **披露期限**：年报 4/30 前，半年报 8/31 前，一季报 4/30 前，三季报 10/31 前。
- **业绩预告、快报和更正**：业绩预告和快报有触发规则，更正公告要进入版本链。这些都用确定性规则处理。
- **估值习惯**：以 PE/PB/PS 为主，成长科技股常用 PEG、市值/收入，EV/EBITDA 用得少。
- **行业分类**：沿用平台的"主题 → 节点"体系，不使用 GICS。
- **治理与政策**：关联交易、控股股东变化，以及政策类催化剂（专项、大基金、出口管制清单）需要单独的事件类型。
- **不交给 skill 的内容**：涨跌停、T+1、成交模拟仍由统一回测引擎处理。

## 5. 官方金融数据 MCP：订阅与 A 股覆盖

`plugins/vertical-plugins/financial-analysis/.mcp.json` 声明了 12 个 HTTP MCP：Daloopa、Morningstar、S&P Kensho、FactSet、Moody's、MT Newswires、Aiera、LSEG、PitchBook、Chronograph、Egnyte、Box。配置中只有 URL，没有认证信息。本轮没有尝试连接其中任何一个。

| 项目 | 已核实（仓库原文） | 未知 | 需商业询价 / 供应商确认 |
|---|---|---|---|
| 订阅要求 | 官方 README 第 136 行："MCP access may require a subscription or API key from the provider"；S&P README 要求 Capital IQ Pro 或 Kensho LLM-ready API 订阅；LSEG README 第 61-62 行要求有效凭证和对应的数据权限（entitlements） | 其余 10 个 MCP 的具体要求，仓库里没有写 | 全部 12 个的价格和授权条款 |
| 是否有免费档 | 仓库没有声明任何一个免费 | 是否有试用或免费档 | 同左 |
| A 股覆盖 | 仓库内没有任何一处声明覆盖沪深北交易所。全仓搜索 China/Shanghai/Shenzhen，只在 earnings-analysis 中作为地理分部示例出现一次 | 各供应商的实际覆盖：股票、财报、历史长度 | 需要供应商书面确认 A 股的覆盖、口径和延迟 |
| 历史与频率 | LSEG CONNECTORS.md 列出 `qa_historical_equity_price`、`tscc_historical_pricing_summaries`（日内到月度）、`qa_ibes_consensus` | 历史起点、更新延迟 | — |
| 我方开通情况 | 未开通，也未连接 | — | — |
| 再分发风险 | — | 合同条款 | 商业数据经 LLM 写入我方产物或仓库前，必须先确认条款 |

结论：当前不引入。原因是自有数据已覆盖 A 股财报与行情，而官方 MCP 的 A 股覆盖和成本都未知，不是因为已经证明它们"不能用"。A 股一致预期是唯一的真实缺口；如果以后有产品需要，可以单独向 LSEG 询价 IBES 的 A 股覆盖情况。

## 6. POC 中发现的 PIT 现象：重新分类

初版报告把"`available_at == published_at` 不符合 D+1"直接写成数据缺陷，这个判断不严谨。重新核对后，结论是**这不是数据缺陷，而是两套 PIT 语义没有在字段层面写清楚**。

**两套规则，各自用途不同**（均为 SOURCE_VERIFIED，见公开代码）：

| 规则 | 位置 | 语义 | 用途 |
|---|---|---|---|
| 研究截止 PIT | `company_intelligence._pit_status`、`chain_t3_evidence._pit_ok` | 日期 ≤ 研究截止日即在范围内；`ingested_at` 为约束条件；日期精度不足或日期互相矛盾时排除 | 研究档案："截至某日能看到什么" |
| 信号 PIT | `financial_pit.financial_pit_at` | 数据库只有日级公告日，无法证明发布发生在盘前还是盘后，所以保守处理：公告日 D 当天不可用，D+1 起可用；`1900-01-01` 视为缺失并 fail closed | 策略信号、回测 |

**样例记录**：上市公司 2025 年年度报告，巨潮公告编号 1225122918。
- 公开下载路径中的日期为 `finalpage/2026-04-18`，记录的 `published_at` 和 `available_at` 都是 2026-04-18。
- 2026-04-18 是星期六，当天没有交易时段，所以"当日可用"在信号层面没有实际意义。
- 公告的具体发布时刻不在数据中，只有日级精度。

**分类结论**：

| 情况 | 判定 |
|---|---|
| 日级 `available_at == published_at`，只用于研究截止 PIT | 正确：研究层按日期判断 |
| 同一记录用于信号 | 由 `financial_pit` 按当时生效的规则计算 known_at，不能直接读 `available_at` |
| 有精确公告时刻，且早于信号截止时点 | 如果当时生效的规则允许按真实时刻判定，可以当日使用。当前库里只有日级日期，所以现行规则保守处理为 D+1 |
| 缺日期、日期互相矛盾、或日期精度跨越截止日 | 两套规则都排除（fail closed） |

**建议**（交给数据质量流程处理，本轮不改代码）：
1. 为 `available_at` 写清字段文档，说明它是"公开披露日（日级）"，不是信号可用时刻。
2. 如果以后要支持当日使用，需新增 `known_at`（带时区的精确时刻）和 `known_at_precision` 两个字段，并按记录生效时的规则版本计算。

## 7. 同一份年报对应两个 source_id：重新分类

初版报告写的是"同一份年报挂两个 source_id，去重未完成"。核对公开代码后，这两个 ID 属于**不同的标识命名空间**，本身不算错误：

| ID 格式 | 生成位置 | 粒度 |
|---|---|---|
| `ru_{stock_code}_{row_index}` | `company_intelligence_feed.py`：每条 review-universe 证据行生成一个 source | 页级证据行。同一份年报的不同页会有不同的 ID |
| `cninfo_{stock_code}_ar{year}` | `docs/cap02/t3/t3_source_manifest.json`：带 `announcement_id`、sha256、页数 | 文档级 |

**这种 ID 差异会不会让判定虚高？** CAP-01 的 `_is_independent` 规定，判定为 confirmed 需要同时满足三个条件：source_id 不同、source_type 不同、publisher 非空且不同。同一份年报拆出的多个行级 source 共享 source_type 和 publisher，所以不会被当成两份独立证据。

**真实存在的不足**：
- 行级 source 没有文档级关联键，比如 `announcement_id`。因此无法自动把它和文档级记录对齐。
- 部分行级 source 的 `published_at` 只有年精度，而文档级记录有日精度。

**建议**：在行级 source 中增加 `document_ref`（字段内容为巨潮 announcement_id），并从文档级记录继承日精度。分类为数据质量改进（`attribution_unknown` 一类），不属于数据错误。

## 8. POC 结果摘要（安全版）

详细内容见 `POC_COMPARISON_V01.md`。四份原始输出包含内部研究 case 内容，不随公开版发布。

| POC | 官方方法组 | A 股适配组 |
|---|---|---|
| A 半导体前道设备主题 | 2.95 / 5 | 4.50 / 5 |
| B 单家上市公司财报与论点跟踪 | 3.10 / 5 | 4.65 / 5 |

**限制**（必须连同分数一起阅读）：
- 每组只运行了一次。
- 评分由单人完成，没有盲评。
- 适配组的提示词由评估者编写，评估者熟悉平台证据模型，所以分差中有一部分来自提示词更贴近评分标准。
- 只覆盖了一个主题、一家公司。
- 确定性 CAP-01 引擎的基线对照没有跑成：它需要读取的数据库在运行时处于恢复模式，因此该项为 `NOT_VERIFIED`。
- 本轮没有对数据库做任何写入或重试。

**可以支撑的结论**：
- 两组都没有编造数字。从输出中抽查了 20 个数字或日期，全部能在输入中找到原文。官方方法要求的 `[UNSOURCED]` 标注确实起了作用。
- 官方组约 40% 的章节因为缺少一致预期、估值倍数、TAM 和市场份额而为空；输出是叙述性文字，无法直接映射到 `ResearchEnvelope`。
- 适配组的增益主要来自平台已有的 claim/证据模型，再加上 thesis-tracker 的证伪条件和更新日志。

**不能支撑的结论**：产品价值已经验证，或者官方方法在有付费数据时表现如何（后者为 `INSTALLATION_REQUIRED` + `DEPENDENCY_REQUIRED`）。

POC 中引用的上市公司公开数字，来源为北方华创（002371）2025 年年度报告，报告期 2025FY，巨潮公告编号 1225122918，披露日 2026-04-18，第 31-32 页"营业收入构成"：
- 营业收入 39,353,112,419.78 元，同比 +30.85%。
- 电子工艺装备分部收入 36,731,219,888.81 元，占比 93.34%，毛利率 39.18%。该分部包含真空及新能源装备，不等于半导体前道设备收入。

POC 只用这些数字检验方法能否正确引用，不构成对该公司的研究结论。

## 9. 能力取舍

- **复用（ADAPT_FOR_A_SHARE）**：
  - thesis-tracker：证伪条件、支柱记分卡、更新日志。
  - earnings-analysis：日期核验、引用清单、分部/毛利率/现金流逐项检查。
  - catalyst-calendar：用确定性规则实现。
  - competitive-analysis：来源等级、同期可比、护城河评分。
  - comps-analysis：只用指标口径规范。
- **借鉴（REFERENCE_ONLY）**：
  - sector-overview、morning-note、idea-generation、earnings-preview 的章节结构。
  - 3-statement-model 的报表勾稽规则。
  - Agent 的三层隔离和人工停顿模式。
- **不引入（DO_NOT_ADOPT）**：
  - initiating-coverage、model-update、dcf-model、audit-xls、clean-data-xls、LBO/投行类 skill。
  - 当前阶段的全部数据 MCP 和合作方插件。
  - 任何评级、目标价或交易建议类输出。

## 10. 集成架构与两种部署方式

- **Layer 1：确定性数据与计算**（保持不变）。包括 PostgreSQL、数据管线、因子、`financial_pit`、统一回测和 EOD。新增的披露日历和同业指标表也放在这一层，由 Python/SQL 计算。
- **Layer 2：研究方法层**。不安装官方插件。被采纳的方法以**仓库内版本化的提示词和 schema** 形式落地。输入只接受 Layer 1 的证据 ID，输出落到 `ResearchEnvelope` 或 CAP-01/07 的结构化字段。LLM 负责归纳和解释，数字一律来自证据引用。
- **Layer 3：研究产品层**。复用现有 dashboard 的能力 API 和公司档案 API、Watchlist 以及每日简报。不新增数据库，也不新增 Agent 编排平台。
- **开发侧与生产侧是两件事**：
  - 开发侧：在 Claude Code 中使用 skill，成本是会话 token，权限限于本机，适合方法试验。能在这里跑通，不代表生产可用。
  - 生产侧：通过 Messages API 或 Managed Agents（`POST /v1/agents`）调用。需要管理 API key、按调用计费、校验输出 schema、处理失败重试、保留审计日志。官方 cookbook 还要求提供 CapIQ/FactSet 的 MCP URL。本轮没有验证这条路径（`NOT_VERIFIED`），上线前需要单独评审。

## 11. 下一阶段候选：F1 CAP-07 R1 可证伪研究假设记分卡

目标：对每个研究判断回答一个问题——"出现什么事实，就说明这个判断不再成立？"。然后由证据驱动状态变化；出现反例时，提示需要复核。

这是**产品候选，价值尚未验证**。单次 POC 的评分不能作为依据。验收方式见 §11.6。

### 11.1 当前 `ResearchClaim` 的真实结构（SOURCE_VERIFIED）

`src/stock_research/company_intelligence.py` 中的 `@dataclass(frozen=True) class ResearchClaim`：

| 字段 | 类型 / 默认值 |
|---|---|
| `claim_id` | str |
| `dimension` | str |
| `claim_text` | str |
| `evidence_ids` | tuple[str, ...] = () |
| `review_status` | str = "pending" |
| `claim_role` | str = ""（节点级角色，例如 supply_scarcity） |

兼容性约束：
1. `_input_fingerprint` 会把这 6 个字段全部写入 sha256。如果给 `ResearchClaim` 加字段并纳入指纹，所有已有 dossier 的指纹都会变化，CAP-07 会把这种变化误报为"研究事实变化"。
2. `company_intelligence_feed` 构造 claim 时只读取前 5 个字段。新字段即使写进 case JSON，也会被静默丢弃。
3. 这个 dataclass 是 frozen 的，不适合在原记录上追加状态历史。

### 11.2 推荐：不改 `ResearchClaim`，新增两类独立对象

**判断依据**：
- 证伪条件是对 claim 的**研究设计**；状态变化是对 claim 的**观测记录**。两者的生命周期都和 claim 判定不同。
- 放在原记录上会破坏已有指纹，也无法追溯某次状态变化是由哪条证据、在哪个规则版本下触发的。

**`ClaimFalsifier`**（研究设计，带版本，可人工审核）：

```
falsifier_id, claim_id, version, review_status   # pending|accepted|rejected
condition_type      # metric_threshold | disclosure_event | evidence_direction
condition           # 结构化条件，见下
falsifier_text      # 人可读描述；可由 LLM 起草，必须人工 accepted 才生效
min_source_level    # 例如 S1（公司定期报告/公告）
required_review     # 触发证据必须为 accepted；lead_only 只提示，不触发
next_testable_disclosure:
  disclosure_type   # annual_report | semiannual_report | q1_report | q3_report
                    # | earnings_preannouncement | earnings_express | inquiry_reply
  report_period     # 例如 2026FY
  window_end        # 由确定性披露日历计算（法定期限，或交易所预约日）
  window_basis      # statutory | exchange_reservation
rule_version
```

`condition` 的三种形态：
- `metric_threshold`：`{metric, scope, comparator, threshold, periods}`。示例为合成示例："相关业务收入同比增速 < 0，连续 2 期"。由 SQL 在 `financial_pit` 给出的 as_of 版本上自动判定。
- `disclosure_event`：`{event_type, keywords?, counterparty?}`。示例为合成示例："出现关键客户验证终止的公告"。只能产生**待复核**事件，不能自动改变状态。
- `evidence_direction`：出现某个维度上 `direction=refute`、已 accepted、来源等级达到 `min_source_level` 的新证据时，生成待复核事件。

**`ClaimStatusEvent`**（观测记录，追加式，不修改不删除，参照 `capabilities/baseline.py` 的版本化存储）：

```
event_id, claim_id, falsifier_id?, as_of
prev_status, new_status          # supported|partially_supported|needs_evidence|unknown|falsified|needs_review
trigger_evidence_ids
trigger_known_at                 # 触发证据的可用时点（见 11.3）
pit_basis                        # research_cutoff | financial_pit_signal
rule_version, dossier_fingerprint
decided_by                       # rule | reviewer:<id>
review_status
```

`status_history` 不作为字段存在。它是按 claim_id 过滤 `ClaimStatusEvent` 后得到的视图。

### 11.3 证伪规则如何使用来源、披露时间和 PIT

1. **来源**：触发证据必须同时满足 `review_status=accepted` 和 `reliability_level ≥ min_source_level`。lead_only 证据只生成"线索提示"，不产生状态事件。这与 CAP-01 "lead_only 不计入判定"的规则保持一致。
2. **披露时间**：每个事件记录 `trigger_known_at`。
   - 研究档案使用研究截止 PIT：复用 `_pit_status`，`ingested_at` 为约束条件，日期精度不足时 fail closed。
   - 如果这个事件要用于策略解释，`known_at` 由 `financial_pit` 按当时生效的规则版本计算。当前规则为日级、D+1。
   - LLM 不判定可用时点。
3. **回放**：只有 `as_of ≤ 回放时点` 的事件和 falsifier 版本参与回放。这与 `_eligible_baselines` 排除未来基线的规则相同。
4. **"未披露"不等于证伪**：到了 `next_testable_disclosure.window_end` 仍未看到相关披露，只产生 `needs_evidence` 或数据缺口条目（`truly_undisclosed` / `missing_source`），不会产生 `falsified`。

### 11.4 示例（合成，不代表任何公司）

| 项目 | 内容 |
|---|---|
| 研究假设 | 国产半导体设备在某工艺环节的渗透率持续提升 |
| 支持证据 | 产品验证进展、客户扩展、相关业务收入增长（均为 accepted 的 S1 披露） |
| 证伪条件 | 关键客户验证失败（disclosure_event）；相关业务收入连续 2 期同比下降（metric_threshold）；技术路线被替代（evidence_direction） |
| 下一个可检验节点 | 下一期定期报告（window_end 按法定期限计算）；客户方披露；技术进展公告 |
| 当前状态 | needs_evidence（待验证） |
| 状态如何变化 | 只能由满足 11.3 条件的证据驱动，并写入 ClaimStatusEvent |

### 11.5 改动范围与边界

- 新增模块：`capabilities/thesis_scorecard.py`，包含 ClaimFalsifier、ClaimStatusEvent 的 dataclass、加载器和判定函数。事件和 falsifier 存为文件（JSON），沿用 `atomic_json` 和 baseline 的存储方式。
- 接入点：`adapters.cap07_changes` 在已有 claim 判定 diff 的基础上，附带 falsifier 命中情况和新事件；`ResearchEnvelope.findings` 增加 `scorecard` 字段。
- 新增 CLI 子命令（只读，产出 JSON/markdown）和一个只读 dashboard API。
- 不改 `ResearchClaim`；不改 CAP-01/02 的判定规则和指纹；不改生产数据库；不做迁移；不接入信号、准入或回测。
- 与统一回测 Gate C 互相独立，两边都不依赖对方。

### 11.6 验收：如何证明它提高了研究质量

- **单元测试**：
  - 已有 dossier 的指纹不变。
  - lead_only 证据不产生状态事件。
  - 未来日期的事件和 falsifier 不参与回放。
  - 未披露只产生缺口，不产生 falsified。
  - metric_threshold 在 PIT 版本上判定正确。
- **回放**：用仓库内已有的 3 个公司 case，构造前后两期证据快照，检查状态事件与人工判断是否一致。
- **研究质量（产品验收）**：2 名研究员对"现有 CAP-01 dossier"和"dossier + 记分卡"盲评，覆盖 3 家以上公司，不标注来源。预设两个门槛：
  - 证伪条件中能对应到具体 A 股披露类型的比例 ≥ 80%。
  - 下一期披露发布后，能给出明确状态结论的 claim 占比高于基线。
- **风险**：不涉及外部数据授权。主要维护风险在证伪条件的文字质量，因此保留人工 accepted 环节。

## 12. 复现信息

- 官方仓库：`anthropics/financial-services@60565064557ca77b12f62aa7877f365d111c129d`
- 能力矩阵：`docs/financial_skills/SKILL_CAPABILITY_MATRIX_V01.csv`
- POC 汇总：`docs/financial_skills/POC_COMPARISON_V01.md`
