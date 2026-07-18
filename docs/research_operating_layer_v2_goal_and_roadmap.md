# Research Operating Layer V2：项目总目标与路线图

更新日期：2026-07-18

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
→ 产业瓶颈与价值迁移判断
→ Bottleneck Readiness Gate
→ 公司解决能力与价值捕获验证
→ Company Value Capture Gate
→ 股票估值、预期和时间窗口评价
→ 分层结论、置信度与失效条件
→ 人工审核与版本发布
→ 事件与指标触发分层更新
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
- typed industry bottleneck 与 Bottleneck Readiness Gate；
- 公司解决能力和价值捕获验证；
- 与公司产业能力分离的股票投资评价；
- 不可变研究版本；
- 项目级更新事件。

V2 对 V1 采用 `additive-only`、`reference-only`、`no-rewrite` 原则。

V2 后续使用三个一等 `research_layer`：

```text
industry_research
→ company_capture
→ stock_evaluation
```

三层共享研究内核，但使用独立证据通道、结论对象和质量门槛。下游只能引用已审核的上游 version 和 Gate result，不能回写上游历史版本。

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
11. 产业研究、公司能力研究和股票评价是三个独立研究层，不能在一次 agent run 中混合完成。
12. 只有通过 Bottleneck Readiness Gate 的产业瓶颈，才能启动 Company Capture Research。
13. Company Industrial Capability Rating 与 Stock Investment Attractiveness Rating 必须分离。

## 非目标

- 不制作作者或网站排行榜。
- 不以来源数量衡量研究完成度。
- 不批量收集文章后直接生成产业结论。
- 不把 V2 重新设计成字段更多的 Theme JSON。
- 不在当前阶段执行生产数据库迁移。
- 不在当前阶段修改现有 Theme Research API 或 Dashboard。
- 不自动生成股票买卖建议。
- 不把首批研究设计 artifact 描述为完整产业报告。
- 不在产业研究阶段生成公司排名、股票池、company rating 或 stock rating。
- 不允许用热门股票名单反向决定产业边界和产业链结构。

## 分阶段路线图

### R0：目标校正与边界冻结

交付：

- 项目总目标；
- V1/V2/Future Promotion 边界；
- 当前架构审计；
- V2 设计规格。

退出条件：V1 27 个主题明确冻结，V2 采用独立 artifact layer，生产写入边界明确。

### R1：Artifact Research Baseline

状态：已完成（2026-07-17）

交付：

- `research_project_v2` JSON Schema；
- 项目 identity、不可变 version、event stream 和 rebuildable index；
- loader 和 semantic validator；
- CLI：list、show、validate、summary、audit-references、diff、gate、rebuild-index（dry run / `--write`）；
- 本地只读 Theme Research V1 / Technology Industry Catalog V1 reference resolver 与 drift audit；
- Research Design Gate、稳定 ID 版本 diff、append-only manifest 和幂等 index rebuild；
- 四个 research-design artifact；
- valid/invalid fixtures；
- 单元测试和文档。

首批项目：

- AI 算力 PCB 价值迁移；
- 人形机器人量产瓶颈；
- 新型储能路线竞争；
- 高端医疗器械商业化路径。

退出条件：已满足。四个项目均只通过 12 项 Research Design Gate；它们保持 `research_design`、`requirements_defined`、`conclusion_status=unavailable`、`investment_status=not_assessed`，没有 Evidence Assessment、公司捕获结论、支持性结论或投资判断。

验证摘要（2026-07-17）：

- V2：`233 passed, 4 warnings`；
- 选定 V1 回归：`373 passed, 4 warnings`；
- scope guard：测试内置 26 个 approved full SHA，逐提交直接执行 `git show`，排序去重并集为 58 个路径，`5 passed`；`/private/tmp` evidence 为可选核对，存在时必须与计算结果精确一致；
- CLI 实跑：四项目 list、四版本 validate、AI pilot show/summary/reference audit/显式 Design Gate、rebuild dry/write/second write 均 exit 0，第二次 write 无 artifact diff；
- focused exit/diff：`6 passed, 2 warnings`；Python compile、25 个 JSON、9 个 JSONL、`git diff --check` 与 forbidden scope scan 均通过。

现有 warning 为非阻塞 deprecation warning，主要来自 `jsonschema.RefResolver` 与 Python 3.14 下的 `py_mini_racer`。

### R2A：Industry Evidence Acquisition Baseline

交付：

- 独立 `artifacts/research_projects/v2_1/` root 与 `research_layer=industry_research` 的兼容 artifact contract；
- Industry Evidence Requirement 和 Search Plan；
- 来源发现、抓取、下载与不可变快照；
- PDF、网页和数据集解析与标准化；
- evidence_artifact、external document 和 dataset resolver；
- 来源独立性、新鲜度、转载循环和冲突检测；
- 命题级 Industry Evidence Assessment；
- reference drift update event；
- 四个新 Industry Project 对 R1 pilot version 的不可变引用。

退出条件：四个 Industry Project 能从 Evidence Requirement 生成定向 Search Plan，外部资料能够被快照、解析、评价和审计；本阶段不生成公司或股票评级。

### R2B：Industry Chain And Bottleneck Research

交付：

- 系统架构、制造流程或技术路线模型；
- 标准产业节点和节点依赖；
- typed `industry_bottleneck`；
- 系统、技术、工艺、材料设备、供给产能、认证生态和经济性七类瓶颈；
- 瓶颈机制、严重程度、持续时间、替代路线和缓解条件；
- 价值迁移、验证指标、反方命题和失效条件；
- Industry Evidence Readiness Gate；
- Bottleneck Readiness Gate。

退出条件：至少两个 pilot 的核心瓶颈通过 Bottleneck Readiness Gate；未通过 Gate 的瓶颈不得进入公司筛选。

### R3：Company Solution Mapping

交付：

- 从已审核 bottleneck 推导 required capability；
- 技术解决路线和候选公司发现；
- 产品、规格、专利、送样和认证验证；
- 有效产能、良率、交付和供应能力验证；
- 订单、收入和利润转化验证；
- 七级 Company Capability Stage；
- 公司证据通道与独立交叉验证。

退出条件：候选公司必须绑定已通过 Gate 的 bottleneck；公司研究不得读取股价、估值或交易拥挤度。

### R4：Company Value Capture Assessment

交付：

- Company Industrial Capability Rating；
- bottleneck match、技术壁垒、商业化阶段和市场份额评价；
- qualification、effective capacity、订单、收入和利润证据；
- 业务重要性、利润弹性、持续性和替代风险；
- Company Value Capture Gate。

退出条件：能够回答公司是否真正解决产业问题并捕获产业价值，但不回答股票当前是否值得投资。

### R5：Stock Investment Rating And Strategy Transmission

交付：

- 与公司产业能力评分分离的 Stock Investment Attractiveness Rating；
- 当前价格、估值、市场预期和预期差；
- 催化、兑现周期、上下行情景和失效条件；
- 流动性、波动、交易拥挤度和组合约束；
- watchlist、strategy hypothesis 和下游策略传导。

退出条件：股票评价绑定明确 company assessment、评价时点、价格来源和时间窗口；不能用股票表现反向证明公司能力。

### R6：Database Shadow Mapping

前提：R1-R5 artifact 结构稳定且经过人工审核。

交付：

- 数据库 schema 终稿；
- artifact-to-DB dry-run importer；
- append-only version snapshot；
- normalized query tables；
- 权限、回滚和审计设计；
- artifact/DB parity 检查。

本阶段开始前必须重新取得生产 migration 授权。

### R7：API、Research Workbench 与下游适配

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
- 产业研究能够在不生成公司或股票排名的前提下识别和验证 typed bottleneck；
- 未通过 Bottleneck Readiness Gate 的瓶颈不能启动公司映射；
- 公司产业能力评价不读取股价和估值，股票投资评价不能绕过公司价值捕获验证；
- 公司产业能力评分和股票投资吸引力评分可以同时存在且不会相互覆盖；
- AI 自动化与人工审核边界明确。
