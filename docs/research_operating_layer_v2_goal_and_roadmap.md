# Research Operating Layer V2：项目总目标与路线图

更新日期：2026-07-17

## 项目定位

本项目的研究对象不是任何具体作者、账号、网站或研究机构，也不是继续扩充一个以主题数量为中心的产业百科。

外部作者、机构、论文、报告、视频、公司披露和专业网站只承担三种角色：

1. 高质量研究动作的观察样本；
2. 可复用专业知识和证据的输入来源；
3. 检查本项目研究质量的专业基准。

项目的核心目标是建立一套领域无关、可持续运行的 Research Operating Layer，使系统能够把模糊的产业、技术或投资主题转化为边界清楚、证据可审计、因果关系完整、结论可验证并能够持续更新的研究项目。

目标流程是：

```text
模糊主题输入
→ 问题定义
→ 范围界定
→ Research Router
→ 问题树
→ 待验证命题
→ 证据需求设计
→ 定向证据采集
→ 正反证据评价
→ 因果建模
→ 约束与价值迁移判断
→ 公司价值捕获验证
→ 结论与置信度
→ 验证指标与失效条件
→ 人工审核
→ 版本发布
→ 事件与指标触发更新
→ 传导到下游研究和决策工作流
```

## V1、V2 与未来沉淀层

### V1：产业知识底座

现有 27 个 Theme Research 主题、产业节点、来源、命题、公司映射、深度研究资料和 Technology Industry Catalog 继续作为冻结的知识资产。

V1 本阶段保持：

- 不修改；
- 不覆盖；
- 不迁移；
- 不自动补写；
- 不因 V2 设计改变现有 API 和页面行为。

### V2：Research Project / Research Operating Layer

V2 负责记录围绕具体问题展开的研究过程：

- 研究项目身份；
- 问题与边界；
- Router 决策；
- 问题树；
- 待验证命题和命题关系；
- 证据需求和证据评价；
- 因果节点和因果边；
- 验证指标和失效条件；
- 公司价值捕获验证；
- 不可变研究版本；
- 项目级更新事件。

V2 对 V1 采用 `additive-only`、`reference-only`、`no-rewrite` 原则。

### Future Promotion：成熟知识沉淀

V2 结论不会自动改写 V1。未来如需把成熟研究沉淀为新的规范知识资产，必须经过独立的人工审核和 promotion workflow。该流程不属于当前基线阶段。

## 核心设计原则

1. 研究项目不等同于主题，一个项目可以跨主题或只引用部分主题节点。
2. Research Project 是稳定身份，Research Version 是不可变完整快照。
3. 先定义问题和证据需求，再采集资料。
4. 来源存在不等于命题成立，证据作用必须经过 Evidence Assessment。
5. 正方、反方、替代和边界命题使用同一套 Claim 模型。
6. 问题依赖图必须是 DAG，因果图允许显式反馈环。
7. 事实、解释、假设和预测必须区分。
8. 公司映射不等于价值捕获，产品、认证、产能、订单、收入和利润必须分阶段验证。
9. 质量门槛分为 Research Design、Evidence Readiness 和 Publication 三个 Gate，不使用单一总分代替结构性检查。
10. Artifact 基线不依赖数据库、Dashboard、research_case 或下游策略系统运行。

## 非目标

- 不制作作者或网站排行榜。
- 不以来源数量衡量研究完成度。
- 不批量收集文章后直接生成产业结论。
- 不把 V2 重新设计成字段更多的 Theme JSON。
- 不在当前阶段执行生产数据库迁移。
- 不在当前阶段修改现有 Theme Research API 或 Dashboard。
- 不自动生成股票买卖建议。
- 不把首批研究设计 artifact 描述为完整产业报告。

## 分阶段路线图

### R0：目标校正与边界冻结

交付：

- 项目总目标；
- V1/V2/Future Promotion 边界；
- 当前架构审计；
- V2 设计规格。

退出条件：V1 27 个主题明确冻结，V2 采用独立 artifact layer，生产写入边界明确。

### R1：Artifact Research Baseline

交付：

- `research_project_v2` JSON Schema；
- 项目 identity、不可变 version、event stream 和 rebuildable index；
- loader 和 semantic validator；
- CLI：list、show、validate、summary、audit-references、diff、gate；
- 四个 research-design artifact；
- valid/invalid fixtures；
- 单元测试和文档。

首批项目：

- AI 算力 PCB 价值迁移；
- 人形机器人量产瓶颈；
- 新型储能路线竞争；
- 高端医疗器械商业化路径。

退出条件：四个项目只通过 Research Design Gate，没有虚构证据、支持性结论或投资判断。

### R2：Reference Resolver 与 Drift Audit

交付：

- Theme Research V1 resolver；
- Industry Catalog V1 resolver；
- evidence_artifact resolver；
- external document/dataset reference contract；
- content hash 和 hash scope 实现；
- missing、hash mismatch、version mismatch、type mismatch、deprecated 和 duplicate 检查；
- reference drift update event。

退出条件：V1 或外部证据变化不会静默改变历史 Research Version。

### R3：Evidence Workflow Baseline

交付：

- Evidence Requirement 工作流；
- Evidence Assessment；
- 正反证据与冲突检索；
- freshness 和 independence 检查；
- Evidence Readiness Gate；
- 至少两个项目进入证据采集阶段。

退出条件：来源链接不能绕过 assessment，关键命题的覆盖状态可审计。

### R4：Causal And Company Capture Validation

交付：

- 因果节点和因果边；
- claim relation；
- typed validation metric；
- typed invalidation condition；
- company capture 分阶段验证；
- Publication Gate 基线。

退出条件：研究能说明价值为何迁移、通过什么机制迁移、公司是否真正兑现以及如何被后续指标推翻。

### R5：Database Shadow Mapping

前提：R1-R4 artifact 结构稳定且经过人工审核。

交付：

- 数据库 schema 终稿；
- artifact-to-DB dry-run importer；
- append-only version snapshot；
- normalized query tables；
- 权限、回滚和审计设计；
- artifact/DB parity 检查。

本阶段开始前必须重新取得生产 migration 授权。

### R6：API、Research Workbench 与下游适配

交付顺序：

1. 只读 Research Project API；
2. 独立 Research Workbench 入口；
3. research_case adapter；
4. review/publication adapter；
5. watchlist 和 strategy research adapter；
6. Future Promotion 设计。

现有 `/theme-research` 页面继续兼容，不为展示 V2 改写 27 个主题。

## 成功标准

Research Operating Layer V2 成功的标志不是主题数量增加，而是：

- 任意模糊主题都能形成明确研究问题和停止条件；
- 系统能选择适合的研究方法；
- 命题和证据需求先于资料堆积；
- 因果关系和中间机制可检查；
- 正反证据、冲突和不确定性可见；
- 历史版本不可变；
- 引用漂移能够被发现；
- 结论具备验证指标和失效条件；
- 研究过程可以跨主题且不会污染 V1；
- AI 自动化与人工审核边界明确。
