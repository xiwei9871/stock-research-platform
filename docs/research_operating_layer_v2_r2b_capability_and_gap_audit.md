# Research Operating Layer V2 R2B Capability And Gap Audit

更新日期：2026-07-20

## 1. Audit Purpose

本审计只判断 R2A 是否足以支撑 R2B 的两个深度 Pilot：

- `ai_compute_pcb_industry_bottleneck`
- `high_end_medical_device_industry_bottleneck`

本轮不采集外部资料、不创建证据 artifact、不修改任何 project version，也不评价公司或股票。

审计对象是当前工作区中已经落盘并通过 R2A 验收的 schema、loader、semantic validator、evidence workflow、gate、CLI、scope guard 和两个 `v0.1.0` Design Version。

## 2. Executive Conclusion

R2A 已经覆盖 R2B 所需的大部分治理和证据基础，可以直接复用：

- stable project identity 与 immutable research version；
- canonical JSON、content hash、manifest、lineage 和 provenance；
- scope、Router、问题、问题树、claim、claim relation；
- evidence requirement、Search Plan、source discovery、secure snapshot 和 normalized document；
- evidence assessment、independence、freshness、conflict summary；
- causal node、causal edge、validation metric、invalidation condition；
- Industry Design Gate、index、CLI、安全路径和 commit-attributed scope guard。

R2A 不能直接完整表达 R2B 的核心研究产物。存在八个真实 gap：

1. 没有一等 `industry_model_node` / `industry_model_edge`，无法把系统架构、制造流程或生命周期与因果图分开表达。
2. 没有一等 `bottleneck_hypothesis`，无法结构化记录瓶颈类型、范围、持续时间、替代路线、缓解条件和范围限定状态。
3. 没有结构化 `value_migration_analysis`；目前只有 `causal_node.node_kind=value_migration`，不足以区分 quantity、content、ASP、margin、capital intensity 等价值来源。
4. 没有 `bottleneck_readiness_review` 和 Bottleneck Readiness Gate。
5. Industry evidence target 只支持 project、question、claim 和 causal edge，不能直接绑定 bottleneck、industry model node 或 value migration analysis。
6. Industry evidence 以单值 role 混合表达立场与用途，无法同时表达例如 `opposes + mechanism`，也不能稳定统计 context、validation 和 invalidation。
7. `incorporated_event_ids` 只是 version 字段；当前没有项目级 append-only research update event 流。该 gap 真实存在，但尚未证明是 R2B 最小闭环的阻塞项。
8. V2.1 没有覆盖新增 R2B object family 的 stable-ID diff 或 CLI diff。

结论：R2B 不需要重建证据基础设施，但在 Phase 2 开始前需要一个小型、additive-only、migration-free 的 R2B extension profile。Phase 1 只提交设计，不修改 schema 或代码。

## 3. Current Pilot Audit

### 3.1 AI Compute PCB Design Version

当前版本：`research_version:ai_compute_pcb_industry_bottleneck:0.1.0`

已有能力：

- scope 已排除公司清单、公司评级、股票评级和投资建议；
- Router 为 `system_architecture + manufacturing_process`；
- 6 个问题覆盖 primary、mechanism、constraint、economics、counterfactual 和 validation；
- 2 条 hypothesis claim，含一条 counter claim；
- 7 条 evidence requirement 和 7 个 Search Plan；
- 5 个 causal node、4 条 causal edge；
- 1 个 validation metric 和 1 个 invalidation condition；
- evidence assessment 为零，结论状态为 `unavailable`，投资状态为 `not_assessed`。

不足：

- Scope 仍以 rack 内 PCB 和材料为主，没有清楚拆分 server board、switch board、backplane、accelerator card、NIC/DPU 和 optical/electrical boundary。
- 当前 Router decision 未选用已有的 `infrastructure_economics`，且 method enum 尚未表达 `constraint_analysis` 和 `value_migration` 模块。
- 问题树只有 6 个节点，无法驱动架构、制造、材料、设备、供需、有效产能、认证、替代路线和伪卡点的独立证据任务。
- 初始 claim 把多个可能瓶颈合并在一句话内，不能分别确认或否定。
- 7 条 requirement 使用相同的泛化来源组合，未按 BOM、信号完整性、材料、良率、产能、认证、价格和替代技术设计证据口径。
- causal model 是有效骨架，但把产业结构节点和因果节点混用。
- 单一指标 `normalized_high_speed_pcb_value_per_ai_rack` 无法区分数量、面积、层数、材料等级、良率、ASP 和供给壁垒。

### 3.2 High-End Medical Device Design Version

当前版本：`research_version:high_end_medical_device_industry_bottleneck:0.1.0`

已有能力：

- scope 已排除公司和股票研究；
- Router 为 `lifecycle + regulation + system_architecture`；
- 6 个问题覆盖 primary、mechanism、constraint、economics、counterfactual 和 validation；
- 2 条 hypothesis claim，含一条 counter claim；
- 7 条 evidence requirement 和 7 个 Search Plan；
- 5 个 causal node、4 条 causal edge；
- 1 个 validation metric 和 1 个 invalidation condition；
- evidence assessment 为零，结论状态为 `unavailable`，投资状态为 `not_assessed`。

不足：

- “高端医疗器械”仍过宽。深度研究必须选择跨产品可比较的商业化机制，同时禁止把不同风险等级、适应证和采购路径的数据直接混合。
- Router 缺少 `commercialization` 和 `constraint_analysis`。
- 生命周期没有拆成研发验证、注册、临床证据、医院准入、预算、招标、安装验收、医生培训、活跃使用、维护、耗材/软件和回款。
- 当前 causal edge 把“活跃装机”到“医院准入约束”表达为正向边，方向与生命周期顺序需要重建。
- 单一指标 `active_install_base_conversion_rate_12m` 不足以区分获批、投标、中标、安装、开机、检查/手术量、耗材复购、服务收入和回款。
- requirement 尚未区分监管、临床、采购、使用、服务、生态和经济性证据。

### 3.3 Pilots Explicitly Not Executed

以下项目本轮保持 `v0.1.0` Design Version，不增加问题、不采集资料、不创建新版本：

- `humanoid_robot_industry_bottleneck`
- `new_energy_storage_industry_bottleneck`

## 4. Capability Coverage Matrix

| R2B need | R2A coverage | Decision |
|---|---|---|
| Scope confirmation | `snapshot.scope` 完整覆盖 | 直接复用 |
| Router review | 支持 primary/secondary/manual override | 扩展 method enum 与 required modules |
| Research question tree | question + tree node + DAG 语义 | 直接复用 |
| Fact/interpretation/hypothesis/forecast | claim.epistemic_type | 直接复用 |
| Counter claim | claim_kind + claim_relation | 直接复用 |
| Evidence requirement | 已有 target、来源、独立性、新鲜度、coverage | 小幅增加 geography/product/stop fields |
| Source acquisition | R2A Search Plan/Discovery/Snapshot/Normalize | 直接复用，不建网站库 |
| Evidence assessment | artifact/document/locator/role/quality/conflict | 扩展 target type；2.2 拆分 evidence stance/function |
| Independence/freshness/conflict | 已实现并可审计 | 直接复用 |
| Industry architecture/process/lifecycle | 只能勉强借用 causal node | 新增 industry model node/edge |
| Bottleneck register | 无一等对象 | 新增 bottleneck hypothesis |
| Causal model | causal node/edge 可复用 | edge 增加 counter claim link |
| Value migration | 只有 value_migration node kind | 新增结构化 analysis |
| Validation/invalidation | 类型化阈值已存在 | 扩展 target type |
| Bottleneck Readiness Gate | 不存在 | 新增 gate + immutable review result |
| Versioning/hash/lineage | 完整 | 直接复用 |
| Research update events | 只有 incorporated_event_ids 占位 | 非阻塞；最低路径保持空，另行批准后再实现 |
| Stable-ID diff | R1 有，V2.1 未覆盖新增 object family | 扩展 V2.1 diff |
| CLI | 11 个 R2A 命令 | 后续只增加 gate/diff 必要入口 |
| Scope attribution | 精确 commit/path guard 已有模式 | 为 R2B 建立独立批准提交集合 |

## 5. What Does Not Need To Change

以下内容不应因 R2B 重写：

- project identity、project pointers、version manifest 和 index；
- canonical hash 和 immutable version publication；
- loader 的 lineage、provenance 和 managed-path security；
- discovery、snapshot、normalization、assessment 持久化协议；
- source relationship、independence、freshness 和 conflict 计算；
- R1/V1 reference-only 边界；
- R2A 的四个 `v0.1.0` version；
- root CLI delegation；
- Dashboard、API、数据库和生产 migration。

## 6. Minimum Extension Decision

建议采用 `schema_version 2.2.0` 的 R2B extension profile，而不是复制一套 Research Project V3：

- 旧 `v0.1.0` artifacts 继续由 2.1 schema 验证；
- 新增 2.2 Industry version schema，不修改旧 version bytes；
- R2B 新 version 使用新增 required arrays；
- semantic validator 对存在的 R2B arrays 执行严格 ID、target、relation 和 provenance 校验；
- 新对象使用 stable ID，并进入 diff object family；
- 不执行数据库迁移，也不回写 R1/V1。

详细字段见 `docs/research_operating_layer_v2_r2b_schema_extension_proposal.md`。

### Alternatives Considered

1. **No schema change：全部编码成 claim + causal node。** 变更最少，但会把 industry structure、bottleneck status、value dimensions 和 readiness review 塞进自由文本，无法可靠审计或 diff，不推荐。
2. **Minimal 2.2 profile（推荐）。** 保留 R2A 基础设施，只增加真实缺失的一等对象和 target links；旧 2.1 artifacts 不迁移。
3. **新建独立 R2B package、数据库或 Research Project V3。** 隔离最强，但重复 loader/evidence/governance，违反本轮 YAGNI、migration-free 和 additive-only 边界，不采用。

## 7. Phase 1 Stop Decision

Phase 1 到此只允许形成审计、问题树、候选 hypothesis、证据矩阵、Source Acquisition Plan、Gate 规范和后续实施计划。

在用户确认下列决策前，不开始 Phase 2：

1. 是否接受八项 gap，并同意 research update event 暂不进入最低 Phase 2 路径；
2. 是否接受 AI Pilot 的 rack + network 双边界；
3. 是否接受 Medical Pilot 采用跨产品商业化漏斗、但所有证据必须按产品类别分层；
4. 是否接受 Phase 2 先创建 `v0.2.0 research_design`，Phase 3 再创建 `v0.3.0 review_candidate`，两版 `incorporated_event_ids` 暂为空；
5. 是否接受两个 Pilot 串行执行，先 AI PCB、后 High-End Medical Device。
