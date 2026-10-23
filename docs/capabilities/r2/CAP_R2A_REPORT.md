# CAP-R2A 产业链竞争假设与证据推理增强 — 实现与验收报告

- 分支：`feat/cap-r2-evidence-reasoning`（基于 R1 `f5155149`）
- 范围：CAP-04 / CAP-06 / CAP-08 推理增强（P0）；CAP-05 事实位、CAP-07 假设快照、CAP-09 研究判断区（P1 衔接）
- 边界：research_only；不重构 CAP-01/02 冻结引擎；不改 node_verdict；不接正式信号/准入；不依赖 DATA-R3

## 1. 架构

新增纯推理层 `src/stock_research/capabilities/reasoning.py`，被 CAP-04/06/08 adapter 调用：

| 模块 | 输出 |
|---|---|
| `supply_constraint_assessment` | 需求增长 / 产能受限 / 有效交付受限 / 供应商数量有限 / 认证门槛限供 — 五项独立判定 |
| `substitutability_assessment` | 功能替代存在 / 替代性能达标 / 切换认证成本 / 切换时间 / 替代已商业化 |
| `entry_barrier_assessment` | 产品认证 / 客户认证 / 量产线验证 / 长期供应资格 / 良率可靠性 |
| `compare_competition` | 同节点同产品口径 pairwise `comparison_scope` |
| `hypothesis_assessment` | 每条 claim 的状态、支持/反证、替代解释、决定性缺口、修订触发、独立来源数 |
| `theme_synthesis` | 主题级：已有发现 / 竞争假设 / 未决问题 / 下一验证目标 / 覆盖 |

判定词汇：`verified` / `plausibly_constrained` / `partial` / `unverified` / `no_evidence`；
假设状态：`supported` / `contested` / `unresolved` / `refuted` / `risk_flagged`。
证据不足一律 `unverified`/`unresolved`，不输出正/负 verdict；不覆盖 CAP-02 `node_verdict`。

## 2. 语义红线（任务书 → 实现 → 实测）

| 红线 | 实现机制 | 实测表现 |
|---|---|---|
| 需求增长 ≠ 供给短缺 | demand_growth 与 capacity_limited 分列；demand 仅在有需求维度证据时判 partial，否则 no_evidence | 液冷 CDU demand=`no_evidence`，supply 整体 `unverified` |
| 多供应商 ≠ 可替代 | supplier_count 是供给子项；替代性单独评估（功能/性能/切换成本/时间/商业化） | `nc_multi_supplier` 归 market_structure，subst 仍 `unverified` |
| 产品认证 ≠ 客户认证 | barrier 五项拆分；product_cert 与 customer_cert 独立证据维度 | 半导体 `nc_cert_barrier`：`unverified` + 替代解释“产品级测试认证≠客户认证” |
| 交付 ≠ 收入/毛利 | CAP-05 delivery/order/revenue/margin 独立事实位；delivery 不升级 revenue | 002837 `validated` 交付但 revenue=`missing` |
| 板块收入 ≠ 产品线 | margin_state `disclosed_broader_scope` → `attribution_unknown` gap | 002371 保留 segment 口径标注，不进产品线 |
| 同证据多引用不重复计数 | `independent_source_count` 按底层 source_id 去重 | `nc_multi_supplier` srcs=2（cninfo_002837_ar2025 + cninfo_301018_ar2025） |
| 父子案例共享证据非独立确认 | lineage 标记 + source 级去重 | 父节点 `ai_power_liquid_cooling` 与子节点证据不重复计 |
| lead_only/pending/超 as_of 不提升结论 | 证据审核状态 + PIT 过滤后参与判定 | 契约测试 `test_r2a_lead_only_evidence_cannot_promote` 等 |
| 支持+反证并存 → contested | hypothesis 同时收集 supporting/counter，冲突即 contested | 契约测试覆盖 |
| 跨口径不比较 | `comparison_scope` 四档；母子公司同集团标 partially | 002371×688037 `partially_comparable`（同一集团/母子公司口径） |

## 3. 三主题结果（`r2_*.json` 快照）

### AI 供电/液冷（4 案例节点 / 16 主题节点）

| 节点 | supply | subst | barrier | 假设要点 |
|---|---|---|---|---|
| liquid_cooling_cdu_system | unverified | unverified | unverified | 供给稀缺/认证壁垒/炒作 → unresolved；多供应商 → supported（格局事实） |
| liquid_cooling_coldplate_manifold | unverified | unverified | unverified | 同上结构 |
| ai_power_liquid_cooling（父） | unverified | unverified | unverified | hype_component → risk_flagged；非独家供应商 → supported |
| liquid_cooling_pump_components | unverified | unverified | unverified | 泵组件交付不构成系统级 CDU 证据 |

- 002837×301018：`directly_comparable`（同一节点同一产品口径）
- 主题摘要：13 条未决、下一验证目标 = product_revenue/product_gross_margin/verifiable_order（002837/301018/002050/603757）

### 人形机器人（1 案例节点 / 21 主题节点）

- humanoid_vision_sensing：三区全 unverified；5 条假设 4 unresolved + `nc_vision_hype` risk_flagged（概念热度驱动，非交付证据）
- 工业机器视觉能力 ≠ 人形规模化供应链——无正向结论生成

### 半导体设备（case 模式，无主题包）

- supply=`plausibly_constrained`（`nc_import_substitution_demand` supported，独立来源 1；替代解释明确“多供应商格局可吸收需求增长”，决定性缺口 delivery_shortfall/supplier_count）
- `nc_process_monopoly`/`nc_cert_barrier`/`nc_perf_gap`/`nc_hype_component` → unresolved
- 002371×688037：`partially_comparable`（母子公司口径，产品线归属需注意）

## 4. P1 衔接

- **CAP-05**：revenue_disclosure / margin_disclosure / order_evidence / delivery_evidence / cash_collection 五事实位独立；realization_state 不由 delivery 自动升级
- **CAP-07**：`_node_snapshot` 增加 `hypothesis_states`（assessment_state 参与身份/diff）；派生字段与运行元数据仍排除——幂等性质不变
- **CAP-09**：节点卡片新增“研究判断”区（三区子项判定 + 可比口径 + 假设记录：状态/替代解释/决定性缺口/修订触发）；主题级“主题研究摘要”块（已有发现/竞争假设/未决/下一验证/覆盖）

## 5. 测试

- R2A 对抗契约：**34 绿**，覆盖任务书 10 对抗场景（一手正反并存、同源多引用、父子共享证据、lead_only、产品认证缺客户认证、组件交付缺系统证据、板块收入缺归属、超 as_of、无可比/口径不一致、缺失源/空数据回退）+ CAP-01/02 判定不变性
- 聚焦后端：**24 绿**（tests/test_capabilities.py）
- 前端：**443 绿**（41 文件）+ `pnpm build` 通过
- 全量回归：见 `REGRESSION_DIFF.md`

## 6. 复现

```bash
cd <repo> && PYTHONPATH=src .venv/bin/python -m stock_research.capabilities.cli cap-chain-smoke \
  --theme ai_power_value_capture_v1 --theme-db --as-of 2026-10-31 \
  --baseline-dir outputs/research/cap_baselines --workbench-dir outputs/research/cap_workbench \
  --json-out docs/capabilities/r2/r2_ai_power_value_capture_v1.json
# humanoid 同理；semi_equipment 走 case 模式 run_research_chain
```

## 7. 遗留问题（移交 R2B）

- CAP-05 兑现阶段分析仍为事实位聚合，阶段化推理与 DATA 线补数联动未完成
- CAP-07 变化检测覆盖假设状态，但“新证据实质改变观点”的语义分级（minor/material）待 R2B
- CAP-09 为只读展示，研究任务优先级化未实现
- 半导体主题无 theme_db 包，仅 case 模式可跑（覆盖缺口如实展示）
- 全部结论级假设仍偏 unresolved——真实瓶颈判定依赖 DATA 线补产能/交期/认证周期证据
