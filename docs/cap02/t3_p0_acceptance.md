# CAP-02 T3 P0 验收报告（终校版）

日期：2026-10-21 ｜ 基线：`e2119bd5` → 终校语义校准

## 审核统计（自动生成 `t3_audit_stats`）

CLI 输出 `t3_audit|{"accepted": 11, "lead_only": 4, "n": 16, "pending": 1}`

- 分产品记录 6：accepted 5 / pending 1（002371 unextracted）
- 竞对供给 3：accepted 1（申菱格局事实）/ lead_only 2（大元/三花）
- 客户验证 4：accepted 3（Intel validated、NVIDIA ecosystem、申菱板块客户）/ lead_only 1（越疆）
- 订单 3：accepted 2（申菱板块增长、英维克无重大合同披露）/ lead_only 1（越疆意向）

## 终校三处语义修正

| 修正 | 实现 | 效果 |
|---|---|---|
| "重大合同不适用"不否定订单 | `no_major_contract_disclosure` 独立事实位，不占订单阶段；真实订单存在时不覆盖 | 002837 ord: `no_major_contract_disclosure`（若后续有合同证据则让位） |
| 板块客户关系≠产品认证 | `CustomerValidationRecord.scope`：product_line / industry_board / company；非产品线 → `validated_at_industry_board` | 301018 valdel: `validated_at_industry_board`（非 validated） |
| Intel/NVIDIA 分级拆分 | Intel 测试验证=`validated`；NVIDIA MGX 生态成员=`ecosystem`（新 stage） | 002837 valdel: `validated`（Intel 级，不与生态成员合并） |
| 板块订单+72% | `stage=growth` 聚合增长事实，不入 ORDER_STAGES | 301018 ord: `order_growth_at_industry_board` |

## 竞对反证边界

- `RivalSupplyRecord.substitution_verified`：仅产品序列披露 → refute 证据封顶 `pending`；有适配/性能/产能/认证实证才可 accepted
- 申菱 refute 行现 pending（无"同等有效替代"实证）；roster 行保持 accepted（格局事实成立）
- M1 派生内部摘要降 `pending`（非独立第二来源）→ `nc_nonexclusive_suppliers` = partially_supported（申菱一手单源），`nc_process_scarce` = needs_evidence

## PIT 与来源校验

- `_pit_ok` 三日期统一：published/available/ingested 任一超截止 → 排除；发表晚于入库矛盾 → 排除；全缺 → 排除
- `_source_ok`：I2/I3 accepted 须 `source_id + (uri|page) + published + ingested`，缺字段降级候选

## 三节点最终矩阵

| 节点 | verdict | 行 |
|---|---|---|
| 液冷 | bottleneck_unverified | 002837: disclosed_broader_scope / validated / no_major_contract_disclosure；301018: disclosed_broader_scope / validated_at_industry_board / order_growth_at_industry_board；002050: missing / none_seen |
| 半导体设备 | bottleneck_unverified | 002371: unextracted / none_seen；688037: missing / none_seen |
| 人形视觉 | needs_evidence | 688686: missing / pending_review（越疆 lead_only 入队） |

## DATA 线缺口清单（移交）

1. 北方华创 2025 年报分产品表（电子工艺装备/电子元器件）——PDF 未入库
2. 三花智控液冷一手披露（ru_* 零覆盖）
3. 大元泵业 CDU 泵产品与适配证据（仅券商线索）
4. 英维克/申菱数据中心液冷**单线**收入、产能、液冷产品级客户认证

## 复现命令

```bash
cd /Users/xiwei/stock_research/.worktrees/cap-01
.venv/bin/pytest tests/test_chain_bottleneck.py -q   # 33 passed
for c in liquid_cooling_node semi_equipment_node humanoid_vision_node; do
  PYTHONPATH=src .venv/bin/python -m stock_research.cli chain-bottleneck-dossier \
    --case docs/cap02/cases/$c.json \
    --dossier-dir outputs/research/company_intelligence \
    --output-dir outputs/research/chain_bottleneck \
    --code-sha "$(git rev-parse --short HEAD)"
done
```

边界：research_only、零生产写入、无信号/准入变更、未部署。
