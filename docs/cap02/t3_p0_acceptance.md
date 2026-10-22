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


## DATA 线证据补全（2026-10-21 二轮）

### 新增一手/次级来源核验结果

| 目标 | 结果 | 处置 |
|---|---|---|
| 002371 年报 PDF | cninfo 回填目录文件已于 10-19 清空；ru_* 仅含 p14-43 经营讨论，无分产品表 | 维持 `unextracted`（附缺失原因）；缺口未关闭 |
| 002371 FY2025 总营收 | 交银国际 2026-05-06 券商报告：39,353M(+30.9%)，净利 5,522M | `pending` 候选（source_type=broker_report/S3，不冒充 filing；不进可信结论） |
| 002050 三花 | 全库零覆盖（仅他司年报中作为客户被提及） | `missing` 缺口未关闭 |
| 603757 大元 | ru_* 仅 2022 半年报（民用屏蔽泵），无液冷/CDU 一手内容 | `lead_only` 缺口未关闭（仅券商线索） |
| 英维克液冷单线收入 | 年报仅披露机房温控/机柜温控两大类 | `undisclosed` 已核实（accepted 事实级，不推算） |
| 申菱液冷单线收入 | 数据服务板块含多类产品未拆分 | `undisclosed` 已核实（同上） |

### 语义校准

- `cust_301018_topcust` → `customer_relationship_disclosed_at_industry_board`（板块客户关系事实级，不冒产品认证）
- `demotion_reason` 透传：`incomplete_source` / `review_not_accepted`
- `SegmentRevenueRecord` + `source_type`/`reliability_level`；`undisclosed` 排 `broader` 之后（有板块数据不误报未披露）

### 自动统计（t3_audit_stats）

`{"accepted": 13, "lead_only": 4, "n": 19, "pending": 2}`

- +2 accepted（英维克/申菱液冷单线 undisclosed 事实级记录）
- +1 pending（002371 券商引用总营收候选）

### 三节点矩阵变化

- 301018 valdel: `validated_at_industry_board` → **`customer_relationship_disclosed_at_industry_board`**
- 002371 rev: unextracted + 候选 `seg_002371_total_2025FY`（review_not_accepted）
- 002837/301018 rev 仍 `disclosed_broader_scope`（液冷单线 undisclosed 已核实事实入 facts）
- 节点判定不变：unverified / unverified / needs_evidence

### 未关闭缺口（继续交 DATA 线）

1. 002371 年报分产品表（需重新采集 cninfo PDF 或可信表格）
2. 三花智控一手披露（需新采集：年报/公告/定增问询）
3. 大元泵业 CDU 泵适配/认证（需新采集：年报或定点公告）
4. 液冷单线收入拆分：两家公司均已核实"未单独披露"——**缺口转化为已核实结论**，除非中报/定增文件拆分否则永久缺口


## DATA-D1 定向采集（2026-10-22）

### 新采一手来源（cninfo 官方源）

| 文件 | 公告 ID | 大小 | 核验页 |
|---|---|---|---|
| 北方华创 2025 年报 | 1225122918 | 1.86MB/233p | p31-33 分产品表、p104 审计报告交叉验证 |
| 三花智控 2025 年报 | 1225026522 | 1.27MB/185p | p14-15 收入构成、全文液冷/CDU 零命中核查 |
| 大元泵业 2025 年报摘要 | 1225160102 | 1.08MB/15p | p3-4 液冷温控领域业务定位 |
| 大元泵业 2026 半年报 | 1225509042 | 2.15MB/163p | p17-18 CDU 泵交付/认证/客户 |

### 关闭缺口（4→1）

1. **002371 分产品表 ✅ 关闭**：电子工艺装备 36,731,219,888.81 元（93.34%)/毛利 39.18%(-2.33pct)/+32.57%；电子元器件 2,579,277,891.07 元（6.55%)/毛利 52.95%；总营收 39,353,112,419.78 元（+30.85%）与审计报告 3,935,311.24 万一致；p33 集成电路设备营收同比+50%+（叙述级）。矩阵 rev: unextracted→**disclosed_broader_scope**（装备分部含真空新能源，大于前道节点）
2. **002050 三花 ✅ 关闭（已核实无液冷披露）**：全文"液冷""CDU"零命中；制冷零部件板块仅"推进数据中心领域项目"表述；p137 冷板=新能源车电池水冷板。rev: missing→disclosed_broader_scope；rival 保持 lead_only（不支撑供应商格局）
3. **603757 大元 ✅ 关闭（超预期一手证据）**：In-Rack CDU 泵 2025 交付~3 万台+2026H1~2 万台；In-Row 22/37kw 完成单机测试认证含 **UL**；曙光 8000 十万卡超算浸没泵组**供应完成**；客户覆盖英维克/申菱/Vertiv/台达等 17 家温控厂商（送样+订单对接）。**矩阵新行：valdel=mass_delivery，ord=verified_delivered**
4. **液冷单线收入 ❌ 开放**：002837/301018/002050 均已核实年报未拆分——缺口保留待中报/定增材料

### 仍缺

- 英维克/申菱/三花液冷单线收入（结构性未披露，待中报或定增拆分）
- 大元液冷收入金额（仅台数交付，未披露金额）
- 002371 客户验证/订单级证据（年报"重大合同不适用"）

### 矩阵差异（before → after）

- 002371: unextracted → **disclosed_broader_scope**（36.73B 装备分部，accepted）
- 002050: missing → **disclosed_broader_scope**（18.58B 制冷零部件，accepted）
- 603757（新行）: **mass_delivery + verified_delivered**——液冷节点首个可核实交付级事实
- nc_nonexclusive_suppliers: 2 accepted supports（申菱+大元 roster）
- nc_process_scarce: needs_evidence（大元 refute 仍封顶 pending——泵供给≠系统替代）
- 节点判定不变：液冷 unverified / 半导体 unverified / 人形 needs_evidence

### 统计（t3_audit_stats 自动）

`{"accepted": 25, "lead_only": 3, "n": 28}`（unextracted 记录已由原表覆盖移除）

校准：`revenue_yoy` 小数比例统一（30.9→0.309）；candidate_facts 透传 source_type/reliability/source_id/page；undisclosed 限定为"已核查 2025 年报口径"，液冷单线数字缺口保留。
