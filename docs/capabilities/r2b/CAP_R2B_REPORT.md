# CAP-R2B 商业兑现、研究变化分级与验证优先级 — 实现与验收报告

- 分支：`feat/cap-r2b-value-tracking`（基于 R2A `57fd9b9a`）
- 范围：A. R2A 三处语义修复；B. CAP-05 兑现阶段；C. CAP-07 变化分级；D. CAP-09 验证任务；E. CAP-10 隔离契约复核
- 边界：research_only；冻结引擎不动；不干扰 DATA-R3-P1c；不接信号

## A. R2A 语义修复（已完成）

### A1 CAP-06 认证/交付车道分离
`compare_competition` 新增 `_cert_delivery_split`：
- `certification_customer_validation` ← 仅 `CustomerValidationRecord` 阶梯阶段（contact→validated，mass_delivery 如实报为交付阶段记录名）；无记录→unknown，仅未审核→pending_review
- `delivery_capability` ← mass_delivery 记录 / 订单 delivered+revenue_recognized / dossier 交付清单证据
- `product_maturity` ← 交付车道派生
- 实证修正：英维克原 `交付=validated`（验证阶段误作交付）→ 现 `认证=validated · 交付=none_seen`；大元泵业 `认证=mass_delivery · 交付=verified_delivered`（泵组件口径，非 CDU 系统）

### A2 CAP-08 双向来源计数
`_split_claim_evidence` 新增 `supporting_source_count` / `counter_source_count` / `support_source_ids` / `counter_source_ids`；`independent_source_count` 改为正反合计去重；excluded 证据来源不计入任何计数。同一年报的不同 evidence_id 仍按 source_id 去重。

### A3 PIT 合规快照
三主题正式快照重新生成，请求 as_of=**2026-10-23**（不晚于当前日期）；`docs/capabilities/r2/` 下 R2A 旧快照为 as_of=2026-10-31/10-28 的请求时点产物，已标记为测试场景（见该目录 README 说明）。信封 as_of 仍标注案例自身 PIT（如人形 2026-10-21）。

## B. CAP-05 商业兑现阶段（六级证据门控）

`assess_commercialization`（reasoning.py）输出 `commercialization_assessment`：

| 阶段 | 合格证据 | 防跳级规则 |
|---|---|---|
| technology_demonstrated | 矩阵 tech_participation/dossier tech_moat 正向 | 仅技术证据 |
| customer_validated | 产品线口径 validated/ecosystem/mass_delivery 验证记录 | 产品能力≠客户认证；非产品线口径只入 note |
| commercial_delivery | mass_delivery 记录 / 订单 delivered·revenue_recognized / dossier 交付清单证据 | 量产声明≠交付（`production_claimed` 不确认） |
| revenue_attributed | `disclosure_scope=product_line` 收入记录 | 板块/公司级收入不填产品线 |
| profitability_visible | 产品线收入+毛利同时可识别 | 收入≠利润 |
| cash_realization_visible | 回款归属记录 | T3 无此记录类型→恒 missing，禁用三表现金流推定 |

字段：`company_code / theme_node_id / product_lines / stage_evidence{confirmed,evidence_ids,source_ids,note} / confirmed_stages / missing_stages / highest_confirmed_stage / attribution_scope / source_ids / as_of`。`value_capture_verdict` 恒 `not_evaluated`。

### 三主题兑现核查表（`cap05_stage_checklist.csv`）

| 公司·节点 | 已确认阶段 | 归属口径 | 解读 |
|---|---|---|---|
| 002837·液冷三节点 | tech_demonstrated+customer_validated | segment | 客户验证通过但**交付/产品线收入/毛利均未确认**——R2A 中曾被误读为"已交付" |
| 603757·泵组件/父节点 | customer_validated+commercial_delivery | unattributed | 泵组件级 mass_delivery+订单交付成立；收入未归属——组件交付≠CDU 系统兑现 |
| 301018 | 无 | segment | 仅 pending 记录 |
| 688686·人形视觉 | tech+revenue_attributed+profitability | product_line | **注意**：收入归属为机器视觉产品线整体（seg_688686_mv），非人形场景订单收入；人形客户验证/交付仍 missing |
| 002371·半导体 | tech_demonstrated | segment | 板块收入不进产品线；交付仅 production_claimed |
| 688037 | 无 | unattributed | 子公司口径 |

## C. CAP-07 实质变化分级

`classify_changes` + `materiality_summary` 给每条 diff 附：`change_category / materiality / affected_hypothesis_ids / before / after / evidence_delta / explanation / action_required`。

规则（可审计）：
- `hypothesis/claim/node` 变化 → `hypothesis_state_changed`；unresolved→supported、supported↔refuted/contested 翻转、已成立假设失支持 → **material**
- `econ:*.delivery/order/stages` → `commercialization_stage_changed`；交付/验证阶段实质跃迁 → material
- `econ:*.revenue/revenue_facts` → `economic_fact_changed`；产品线收入从无到有 → material，板块口径变化 → notable
- `evidence_ref` added → `new_evidence`(notable)；**同一底层 source_id 的重复采集 → non_substantive + source_revision**；removed → notable
- `cap_status` → `metadata_only` / non_substantive
- 新增 `stages` 字段首次出现（before=None）→ notable 非 material（模式新增≠世界变化）
- action：material→`re_review_hypothesis`，notable→`note_for_next_review`，其余 none
- `materiality.requires_re_review` 汇总；重要性=研究判断影响，非价格预测

## D. CAP-09 验证任务工作台

`verification_tasks` 从 CAP-04/05/07/08 输出生成 `proposed` 任务，写入 workbench index `verification_tasks` + 页面"下一步验证任务"区块：

- 字段：task_id/theme_id/node_id/company_code/question/hypothesis_id/required_evidence/owner/priority/priority_reason/source_capabilities/status
- 优先级依据（研究价值，与股价/热度无关）：
  - high：阻断未决核心假设（有决定性缺口）；区分 contested 竞争解释；material 变化需人工复核
  - medium：交付已确认但收入未归属；风险标记需独立证据
  - low：外部数据缺口补齐；CAP-02 覆盖缺口
- 全量 proposed、按优先级排序、按 (node,company,hypothesis,required_evidence) 去重；不触发采集/爬虫/审核流
- 实测：ai_power 46 条（high 10）、人形 27 条（high 4）、半导体 8 条（high 3）

## E. CAP-10 隔离契约

只读审计通过：`stock_research.capabilities` 仅被 `cli.py` 入口、`dashboard/` 只读 API、`capabilities/` 自身引用；无任何策略/信号/准入/回测模块导入。契约测试 `test_r2b_cap10_isolation_contract` 静态扫描全包 + `test_r2b_chain_flags_research_only` 验证信封标志。

## F. 三主题验证结论

- **液冷**：英维克"认证=validated、交付=none_seen"——R2A 误读的交付证据被纠正；大元泵业组件交付成立但不构成 CDU 兑现；46 条验证任务优先指向供给/认证决定性缺口
- **人形**：688686 机器视觉产品线收入归属成立但人形验证/交付未确认；hype 风险标记保持
- **半导体**：母子口径 partially_comparable；002371 板块收入不冒产品线；平台覆盖≠全环节优势

## G. 测试

- `tests/test_capabilities.py`：**44 绿**（R2A 34 + R2B 10 新增）
- 前端：**443 绿**（一次并发 flake 重跑后全绿）+ `pnpm build` 通过
- 全量回归：见 `REGRESSION_DIFF.md`

## 遗留（移交后续）

- 产品线归属无法区分"同产品线内的人形场景收入"（需 DATA 提供更细口径字段）
- 回款阶段暂无 T3 记录类型，待定义 cash_collection 记录
- 验证任务为只读清单，未接研究任务队列/审核流（复用现有队列另行立项）
- 半导体无 theme_db 包仍为 case 模式
