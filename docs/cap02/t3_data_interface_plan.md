# CAP-02 T3｜节点数据接口实施计划

日期：2026-10-21 ｜ 分支：`feat/cap-01-company-intelligence` ｜ 状态：设计稿（待批准实施）

## 目标

把节点研究的四个最高优先级缺口变成可入库、可归因、可判定的数据接口：
分产品收入、客户验证、真实订单、竞争供给。**沿用现有证据系统**（`CompanyEvidence`/`ResearchClaim`/`CompanySource` + `tech_bottleneck_review_universe_evidence` + 研报管线），不新建平行注册表。

## 一、现有契约已具备的挂载点（T1/T2 遗产）

| 字段 | 作用 | T3 复用方式 |
|---|---|---|
| `CompanyEvidence.product_line` | 证据产品线归属 | T3 接口的必填字段；分产品收入/订单按产品线写入 |
| `ResearchClaim.claim_role` | 论点经济学角色 | 新增 `revenue_realization` 角色判定价值兑现主张 |
| `evidence_scope` | node/company 级隔离 | 竞争供给证据必须 `node`；公司收入/订单 `company` |
| `checklist_item` | 证据分级（已确认订单/实际交付/量产阶段） | T3 新增 checklist：`分产品收入`、`客户验证`、`竞争供给` |
| `review_status` + `verdict_weight` | 计数/展示分级 | 一手披露→accepted；券商线索→lead_only；内部核查→accepted 仅限可验证事实 |
| `published_at/available_at/ingested_at` | 严格 PIT | 接口输出强制三日期；入库时间取 `ru_*` 数据集真实入库戳 |

## 二、四个数据接口（按优先级）

### I1 分产品收入 `segment_revenue`

- **输入源**：年报/中报"经营情况讨论"分产品收入表（已在 `ru_*` 摘录层）、招股书业务构成、业绩说明会纪要
- **schema**（写入 evidence 层，非新表）：
  ```
  evidence_id: seg_{stock}_{line}_{period}
  dimension: financial_realization
  checklist_item: 分产品收入
  product_line: <node line key>
  excerpt: "分产品收入 xx 亿元，占比 y%（报告期 p，页码/表号）"
  ```
- **判定消费**：`financial_realization` claim + 矩阵 `revenue_profit` 格
- **缺口语义**：未披露分产品收入 → `needs_evidence`，禁止推算占比

### I2 客户验证 `customer_validation`

- **输入源**：公告/年报客户案例、定点/入围公告、供应商名录披露、产线验证里程碑
- **schema**：`checklist_item: 客户验证`，`product_line` 必填；`evidence_scope: company`
- **判定消费**：commercialization claim（区别于订单——验证≠订单）；节点 `certification_barrier` 门的公司侧输入

### I3 真实订单 `verified_orders`

- **输入源**：中标公告、合同公告、采购订单披露（区别于"合作""框架协议"）
- **schema**：`checklist_item: 已确认订单|中标合同`，必须含金额/数量或不可推回的明确表述；`product_line` 必填
- **判定消费**：矩阵 `verified_orders` → `verified_order` 级；交付里程碑继续 `verified_delivery`，量产表述 `production_claimed`
- **硬规则**：框架协议、战略合作、意向书 → 一律 `lead_only` + checklist `量产阶段`（不给 verified_*）

### I4 竞争供给 `rival_supply`

- **输入源**：竞对公司公告、行业产能统计、券商产业链图谱（仅线索）
- **schema**：`evidence_scope: node`，`checklist_item: 替代路线存在性|供应格局`，`claim_role: market_structure|non_substitutability` 由绑定 claim 决定
- **判定消费**：process_irreplaceability 门；`market_structure` 论点独立于稀缺性判定（R2.1 机制）

## 三、来源追踪（source tracking）

新增 `CompanySource` 行继续走现有模型，T3 要求：

| 字段 | 要求 |
|---|---|
| `source_type` | company_filing（公告/年报）优先；industry_data 限内部核查记录；broker_report 只作线索 |
| `reliability_level` | S1 披露原文 / S2 内部核查 / S3 券商观点 |
| `uri` | 原始文件路径或研报 ID，必填 |
| `page_or_section` | 页码级定位，必填 |
| `ingested_at` | 取数据集真实入库戳，禁手写 |

## 四、DATA 线任务拆分（不阻塞现有开发）

| 优先级 | 任务 | 产出 |
|---|---|---|
| P0 | 三案例公司年报分产品收入段核查（002837/002371/688686） | `seg_*` 证据行或"未披露"明确记录 |
| P0 | 液冷环节竞争供给清单核实（申菱/三花/大元的液冷业务一手披露） | `rival_*` node-scope 证据 |
| P1 | 客户验证线索扫描（公告库按产品线过滤） | `cust_*` 证据行 |
| P1 | 订单级证据鉴别（公告文本分类：合同/中标 vs 框架/意向） | `ord_*` 证据行 |
| P2 | 批量推广到评审池其余成员 | 批量 `seg_/cust_/ord_` 行 |

## 五、实施边界

- 全部 research_only；不落生产表；无调度变更；无信号/准入接入
- T3 只扩展 case/feed 层数据接口与约定；引擎/矩阵/报告层已有消费位
- 先在三节点完成接口验证，再评估批量推广
