# CAP-02 T1/T2 三节点对照报告

日期：2026-10-21 ｜ 分支：`feat/cap-01-company-intelligence` ｜ research-only

## 一、节点判定结果（R2 修正后）

R2 变更：液冷 `bottleneck_rejected` → `bottleneck_unverified`（多供应商存在只反驳'独家工艺'论点，不反驳产能缺口；无产能证据时不得否定节点）。`verified_orders` 改为严格分级（verified_order/verified_delivery/production_claimed/unverified）——量产≠订单，交付里程碑≠订单；新增 dossier as_of 兼容性检查，未来公司画像不得进入历史节点矩阵。

R2.1 变更（本次）：节点 claim 增加 `claim_role`（supply_scarcity/non_substitutability/market_structure/entry_barrier/hype）。`bottleneck_established` 只允许 supply_scarcity/non_substitutability 角色 claim 触发；`bottleneck_rejected` 仅限 supply_scarcity 主张被 counted 证据反驳——非独家性被反驳只杀该机制不杀节点。价值矩阵商业化证据增加 `product_line` 归因：储能温控(BattCool)交付不再计入数据中心液冷节点（002837 → `node_attribution_unknown`），北方华创前道设备交付正确归属（002371 → `verified_delivery`）。

## 一、节点判定结果

| 节点 | 判定 | 置信度 | 成员画像 |
|---|---|---|---|
| 数据中心液冷环节 `ai_power_liquid_cooling` | **bottleneck_unverified** | 0.30 | 英维克(unverified，订单格 node_attribution_unknown)、申菱/三花(无画像) |
| 半导体前道设备 `semi_front_end_equipment` | **bottleneck_unverified** | 0.30 | 北方华创(needs_evidence) |
| 人形机器人视觉感知 `humanoid_vision_sensing` | **needs_evidence** | 0.15 | 奥普特(needs_evidence, concept_only=high) |

## 二、关键验收点逐项验证

| 验收点 | 结果 | 证据 |
|---|---|---|
| 公司技术强 ≠ 节点瓶颈 | PASS | 英维克 dossier 六维 partially_supported，但液冷节点判 rejected——M1 已核查记录（accepted）证实"具备液冷供给能力的上市公司不止一家" |
| 无商业化证据 ≠ 有订单收入 | PASS | 矩阵中 `verified_orders` 区分 verified/claimed_unverified/none_seen；奥普特=claimed_unverified |
| lead_only/PIT 不定不参与节点结论 | PASS | 液冷 3 条券商竞对线索全部 lead_only→`unverified_evidence_ids` 可见不计数；capacity claim 0/0 → unknown |
| 公司级证据绑定节点论点被剔除 | PASS | 英维克年报风险段（company scope）绑定产能论点 → `binding_warnings` 记录 + 剔除；北方华创 1000 台里程碑同理 |
| 主题高关联不自动成立 | PASS | 奥普特映射 98 分；人形视觉节点仍 needs_evidence（节点级证据为零） |
| 可追踪 | PASS | 每节点 dossier_fingerprint = as_of+证据集+规则版本；claim→evidence_id→页码→时间戳 |
| 结构化缺口 | PASS | 三节点各 8-9 条 research_gaps（供需缺口量化、认证周期、性能对比等），可直接交 DATA 线 |

## 三、判定语义说明（继承自 CAP-01-R1.1）

- `bottleneck_established` 需 ≥2 核心门槛（产能/工艺/认证/性能）达 partially_supported 以上且炒作门槛未被证实；
- 任一核心门槛 contradicted → `bottleneck_rejected`；同一论点内部冲突 → `contested`；不同论点分化 → `mixed`；
- `lead_only`/`pending` 证据一律不计入；`pit_uncertain`/`post_asof` 证据退出判定。

## 四、三节点经济学含义（研究观点，非结论）

- **液冷**（R2修正后）：公司能力成立≠节点瓶颈。'非独家供应'作为已核实论点单独保留（mixed：与'工艺稀缺'同门分化）；产能缺口无任何节点级证据→未证实而非被否定。
- **半导体设备**：国产化率低+扩产是真实需求侧证据（partially），但"无第二供应商"这类垄断性论点只有 lead_only 竞对线索——产能缺口量化、认证周期是最高优先级缺口。
- **人形视觉**：概念标的映射热度与可验证供给证据之间存在明确差距——节点研究价值在于证明这一点，而非否定公司。

## 五、复现命令

```bash
cd /Users/xiwei/stock_research/.worktrees/cap-01
for c in liquid_cooling_node semi_equipment_node humanoid_vision_node; do
  PYTHONPATH=src .venv/bin/python -m stock_research.cli chain-bottleneck-dossier \
    --case docs/cap02/cases/$c.json \
    --dossier-dir outputs/research/company_intelligence \
    --output-dir outputs/research/chain_bottleneck \
    --code-sha "$(git rev-parse --short HEAD)"
done
```

输出：`outputs/research/chain_bottleneck/{node_id}_node.{json,md}`

## 六、已知边界

1. 节点级证据目前全部来自已有语料/核查记录（M1 文档、券商线索、公司年报行业段）；无产能/交期一手数据接入——列入 DATA 线 P0 缺口；
2. 价值矩阵成员公司若无 CAP-01 dossier 则行内全部 unknown/unevaluated（申菱、三花、芯源微当前即此状态）；
3. `bottleneck_rejected` 仅在产能/供给约束主张本身被 counted 节点级证据反驳时触发——'工艺非独家'不再推翻整个节点（R2）。已核实的供应商名单事实独立成 claim 保留。
