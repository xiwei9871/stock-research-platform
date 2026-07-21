# AI PCB 产业认知综合基线 v1

本阶段把既有 Stage A normalized evidence 转化为一个严格受证据约束的产业认知基线。它不补采资料、不研究公司、不评价股票，也不授权 Stage A2 或 Stage B。

## 产物职责

- `ai_pcb_industry_cognition_package_v1.json` 是唯一认知事实源，保存问题、证据定位、原子命题、系统模型、机制、因果边、路线比较、有限系统瓶颈判断、未验证骨架和证据缺口。
- `ai_pcb_industry_cognition_report_v1.md` 是固定 renderer 对 package 的只读投影，不得增加 package 中不存在的事实或判断。
- `ai_pcb_industry_cognition_audit_v1.json` 由 validator 重算，保存覆盖矩阵、能力边界、阻塞项和八个审计问题的确定性回答，不保存新的认知对象。

## Grounding 规则

正式证据 locator 必须同时绑定 immutable raw artifact、normalized document、section index 和 section hash。Hash 漂移会使 locator 失效。Search snippet、candidate 描述和采集元数据不属于正文证据。

原子 claim 的 grounded 状态由 validator 重算。直接支持、适用范围、来源链、日期状态、冲突与证据强度共同限制 assessment confidence。Contextual evidence 可以限定结论，但不能单独建立 grounded claim，也不贡献领域覆盖。

Grounded mechanism 只能综合 grounded claims 的共同覆盖范围。Grounded causal edge 还必须有支持“关系本身”的命题，不能因为起点和终点各自成立就推断因果。

## 已形成与未形成的认知

现有资料足以形成 AI 计算系统、加速器内部互连、外部网络、DPU 和光互连边界的部分证据化认知。它不足以形成信号完整性、插损、高速覆铜板、背钻、压合、对位、测试、良率或有效产能的证据化解释。

因此后者被物理隔离为 `unverified_mechanism_skeletons` 和 `evidence_gap_referrals`。Skeleton 不参与 grounded coverage、瓶颈判断、价值变化判断或公司映射 readiness。

## 只读 CLI

```text
research-project-v2-1 cognition validate
research-project-v2-1 cognition show
research-project-v2-1 cognition audit
research-project-v2-1 cognition render
```

四个命令只读取 package、report 和 audit。`show` 使用 audit 的同一计算结果；`audit` 先完成结构、绑定和 grounding 校验；`render` 只输出规范化 Markdown。公开 CLI 不提供 create、build、fix、refresh 或 acquire。

## 能力上限

只要 PCB 材料、制造、测试和良率仍不可评估，完整 AI PCB 产业认知就不能标记为 achieved；只要关键机制仍是 skeleton，就不能形成 PCB 产业瓶颈或价值迁移判断；只要 evidence gaps 未经人工复核，就不能进入公司映射。

当前下一动作固定为 `evidence_gap_review`。这不代表自动补采授权。
