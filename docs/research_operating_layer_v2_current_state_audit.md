# Research Operating Layer V2：当前状态与缺口审计

审计日期：2026-07-17

## 审计范围

本审计针对正在运行的 worktree：

```text
/Users/xiwei/stock_research/.worktrees/research-platform-validation-20260713
```

覆盖：

- Theme Research artifact 和 loader；
- Theme Research PostgreSQL schema；
- Technology Industry Catalog；
- Theme Research API；
- Dashboard 页面；
- 通用 research_case、evidence、review、publication 和 agent run 基础设施。

本审计不修改任何 V1 主题资产。

## 当前资产

当前运行基线包含：

- 27 个 Theme Research 主题；
- 82 条 Technology Industry Catalog L2 产业链；
- 主题节点、来源、命题、价值评估和公司映射；
- research profile 深度研究展示；
- Theme Research artifact、数据库、审查历史和回滚能力；
- Theme Research 与 Daily Review、Watchlist 和 Stock Workspace 的只读集成；
- 通用 research_case、research_claim、evidence_artifact、evidence_link、review_action、publication_snapshot 和 agent_run 表。

## 已有能力

### V1 Theme Research

已有一等对象：

- Theme；
- Theme Node；
- Source Item；
- Content Claim；
- Value Capture Assessment；
- Company Mapping；
- Mapping Evidence；
- Review Event；
- Object Revision；
- Import Run；
- Snapshot。

已有质量控制：

- 来源可靠性和审核状态；
- Claim evidence status；
- Claim platform use status；
- Node review status；
- reviewed claim 的 accepted source gate；
- node evidence strength gate；
- 版本、幂等、回滚和审查历史。

### Technology Industry Catalog

已有：

- L1-L4 产业目录；
- chain kind；
- decomposition method；
- canonical ownership；
- typed edges；
- application composition；
- Theme Research link。

该目录适合作为 V2 的可复用知识引用，不适合作为研究过程容器。

### Dashboard 和 API

当前页面擅长展示：

- 跨主题列表；
- 主题详情；
- 节点分数；
- 来源和命题；
- 公司映射；
- 产业目录结构；
- 深度研究摘要。

当前 API 是以主题为中心的只读资源接口，适合消费知识资产。

### 通用 Research Infrastructure

`research_objects.py` 已有：

- research_case；
- research_claim；
- evidence_artifact；
- evidence_link；
- review_action；
- publication_snapshot；
- agent_run 和 event；
- external delivery。

这些对象可在未来承担下游工作流、审查、发布和 Agent 运行记录，但当前语义偏向股票、交易日、复盘队列和已有决策工作流。

## 核心缺口矩阵

| 能力 | 当前状态 | V2 缺口 | 处理原则 |
|---|---|---|---|
| 研究项目身份 | Theme 或 research_case 近似承担 | 无跨主题长期 Research Project | 新建独立 project identity |
| 问题定义 | 主要存在于文档或 summary | 无结构化 primary question 和 scope | V2 project scope |
| 问题树 | 无通用模型 | 无层级视图和依赖 DAG | question + tree node 分离 |
| Research Router | 有少量 decomposition template | 不能输出组合方法、理由和模块选择 | 新建 router decision |
| 待验证命题 | V1 claim 与 Theme 强绑定 | 无项目级、跨主题 hypothesis | 独立 claim_v2 |
| 反方命题 | 可用普通文本表达 | 无 claim relation | 统一 claim + relation |
| 证据需求 | 采集流程隐含存在 | 无 evidence-before-search contract | evidence requirement |
| 证据评价 | 有来源审核和 claim gate | 无“证据对某命题起何作用”的独立记录 | evidence assessment |
| 因果模型 | 深度研究 summary 中部分表达 | 无 causal node/edge、机制、时滞和边界 | 新建 causal model |
| 价值迁移 | V1 assessment 可表达部分判断 | 无跨节点传导链 | causal value migration |
| 公司兑现 | 有 company mapping | mapping 不等于产品、认证、产能、订单、收入和利润兑现 | company capture assessment |
| 验证指标 | research profile 有自由文本 signals | 缺类型化阈值和机器检查 | validation metric |
| 失效条件 | 风险 claim 可近似表达 | 无独立 invalidation condition | 新建失效对象 |
| 研究版本 | V1 Theme 有版本和 snapshot | 无项目级完整不可变研究快照 | research version |
| 更新事件 | 有 review/import event | 无证据、指标和 drift 驱动的项目事件流 | append-only project event |
| 引用漂移 | V1 内有部分 hash 验证 | 无跨 namespace reference drift | unified reference + resolver |
| 阶段质量门槛 | V1 有对象审核 gate | 无 Design/Evidence/Publication 分段 gate | V2 staged gates |
| 版本 diff | 无项目级 diff | 无对象身份和跨版本分类 | stable IDs + diff rules |

## 为什么不能直接扩展 V1

V1 的 canonical ownership 是 Theme。它适合保存相对稳定的产业结构和审核知识，但不适合表达：

- 一个研究项目跨越多个主题；
- 同一主题并行存在多个不同问题；
- 同一问题存在互相冲突的命题；
- 研究失败或结论失效但 V1 知识仍有效；
- 历史策略决策绑定特定研究版本。

把这些能力继续塞进 Theme artifact 会重新产生混合职责。

## 为什么不能直接复用 research_case

`research_case` 具有可复用基础，但当前字段和工作流假设包括：

- trade_date；
- asset_id；
- theme 自由文本；
- review queue 来源；
- 决策和发布快照。

Research Operating Layer 需要支持多年期、跨主题、无股票对象、尚未形成结论的研究设计。因此：

- research_case 不作为 V2 canonical parent；
- evidence_artifact/evidence_link 的理念可以复用；
- review、agent_run、publication 可作为未来 adapter；
- adapter 必须绑定明确 `project_id + version_id`。

## 页面缺口

现有 `/theme-research` 是知识浏览器，不是研究项目工作台。缺少：

- 项目生命周期；
- scope 和 Router；
- 问题树；
- 命题关系；
- 证据需求覆盖；
- 正反证据评价；
- 因果链；
- 验证指标和失效条件；
- Research Version diff；
- Reference Drift；
- Gate 状态。

当前阶段不修改页面。未来应增加独立 Research Workbench，而不是把上述内容挤入 Theme Detail。

## API 缺口

当前 API 以 Theme 为根，缺少：

- project collection/detail；
- version collection/detail；
- version diff；
- gate result；
- reference audit；
- update event；
- question/claim/causal graph read model。

当前阶段不新增 API。R6 前先稳定 artifact contract。

## 风险

1. 把 V2 重新实现成大而全 Theme JSON。
2. 直接扩展 research_case，导致 V2 被交易日和股票对象绑架。
3. Reference 只支持 V1，无法吸收新证据。
4. 来源直接挂到 Claim，绕过 Evidence Assessment。
5. 状态压缩成一个 status，无法表达已发布项目中的争议命题。
6. 可变 version 文件破坏历史审计。
7. 自动接受 drift，历史研究结论被静默改变。
8. 初始研究设计被误读为完成的产业报告。
9. 过早做数据库、API 和前端，固化尚未验证的对象模型。

## 审计结论

现有系统已经拥有优质的 V1 知识资产、证据审核、产业目录、数据库版本和下游研究基础设施，但缺少以具体问题为中心的研究运行层。

推荐保持：

```text
V1 Theme Research / Industry Catalog
          ↓ reference-only
Research Operating Layer V2
          ↓ explicit future adapters
research_case / review / publication / watchlist / strategy
```

第一阶段应采用 artifact-first、offline、read-only 的独立 V2 baseline，不执行生产迁移。
