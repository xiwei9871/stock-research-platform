# CAP-01-R1 三案例修改前后对照

R0 = 维度级汇总判定（claim 不独立裁定，lead_only/pending 参与计数）
R1 = claim 级判定 + 审核分级 + 严格 PIT。commit `81ebf84b` → R1。

## 002837 英维克

总体: `contested` → `unverified`

| 维度 | R0 | R1 |
|---|---|---|
| 产业链地位 | partially_supported | partially_supported |
| 商业化能力 | partially_supported | partially_supported |
| 竞争优势 | contradicted | partially_supported |
| 财务兑现 | contested | partially_supported |
| 风险与反证 | confirmed | partially_supported |
| 技术壁垒 | partially_supported | partially_supported |

| Claim | 论点（截） | R1 判定 | 支持/反驳 | 待验证线索 |
|---|---|---|---|---|
| `c_tech_full_chain` | 公司掌握'热源到冷源'全链条液冷技术平台（Coolinside、两相冷板、射… | partially_supported | 3/0 | 0 |
| `c_chain_node` | 公司是数据中心/算力温控链条的关键节点供应商（覆盖头部互联网与运营商客户）… | partially_supported | 3/0 | 0 |
| `c_comm_customers` | 液冷产品已获主流算力芯片厂商与头部算力设备制造商认可并被规模采购… | partially_supported | 3/0 | 1 |
| `c_comm_delivery` | 液冷/储能温控产品已进入批量交付与量产阶段… | partially_supported | 2/0 | 0 |
| `c_edge_capability` | '全链条'液冷供给能力构成相对同行的差异化优势… | partially_supported | 2/0 | 0 |
| `c_edge_uniqueness` | 液冷全链条供给能力在国内为独占/唯一（市场不存在同类供给）… | needs_evidence | 0/0 | 4 |
| `c_edge_perf` | 公司产品相对竞品在性能/成本/交付上具有可量化的比较优势… | unknown | 0/0 | 0 |
| `c_fin_quantifiable` | 液冷相关业务的收入规模、毛利与现金流贡献可以量化追溯… | needs_evidence | 0/0 | 0 |
| `c_fin_rd_intensity` | 公司维持高强度研发投入（H1'25 研发费用4.46亿元、占营收7.35%）… | partially_supported | 1/0 | 0 |
| `c_risk_competition` | 存在行业竞争加剧与技术路线绕开（屏蔽泵/磁悬浮等替代方案）风险… | partially_supported | 1/0 | 2 |

## 002371 北方华创

总体: `contested` → `needs_evidence`

| 维度 | R0 | R1 |
|---|---|---|
| 产业链地位 | partially_supported | partially_supported |
| 商业化能力 | partially_supported | partially_supported |
| 竞争优势 | contradicted | partially_supported |
| 财务兑现 | contradicted | needs_evidence |
| 风险与反证 | partially_supported | partially_supported |
| 技术壁垒 | partially_supported | partially_supported |

| Claim | 论点（截） | R1 判定 | 支持/反驳 | 待验证线索 |
|---|---|---|---|---|
| `c_tech_platform` | 公司具备平台化半导体设备矩阵：刻蚀、薄膜沉积、热处理、湿法、离子注入，并购芯… | partially_supported | 5/0 | 1 |
| `c_chain_substitution` | 公司处于半导体设备国产替代核心节点，受益于国产化率提升与AI算力驱动的扩产周… | partially_supported | 2/0 | 0 |
| `c_comm_scale_delivery` | 主力装备实现规模化量产交付：立式炉/PVD/刻蚀设备均达到第1000台交付里… | partially_supported | 2/0 | 0 |
| `c_comm_customer_validation` | 核心装备已通过下游头部晶圆厂的量产线验证（具名客户）… | unknown | 0/0 | 0 |
| `c_edge_leader` | 公司作为国内半导体设备平台型龙头，其覆盖广度构成持续竞争优势… | partially_supported | 3/0 | 1 |
| `c_fin_by_line` | 各设备产品线的收入贡献与毛利可量化追溯… | needs_evidence | 0/0 | 0 |
| `c_fin_cashflow` | 并购扩张带来的投资性现金流压力可量化… | needs_evidence | 0/0 | 0 |
| `c_risk_iteration` | 存在技术更新迭代风险与新兴领域(量子/光电/化合物)验证不及预期风险… | partially_supported | 2/0 | 0 |

## 688686 奥普特

总体: `needs_evidence` → `needs_evidence`

| 维度 | R0 | R1 |
|---|---|---|
| 产业链地位 | unknown | needs_evidence |
| 商业化能力 | needs_evidence | needs_evidence |
| 竞争优势 | needs_evidence | needs_evidence |
| 财务兑现 | needs_evidence | needs_evidence |
| 风险与反证 | partially_supported | partially_supported |
| 技术壁垒 | partially_supported | partially_supported |

| Claim | 论点（截） | R1 判定 | 支持/反驳 | 待验证线索 |
|---|---|---|---|---|
| `c_hm_vision_tech` | 公司在工业机器视觉领域具备自研成像/3D视觉/软硬件平台技术(可迁移至机器人… | partially_supported | 4/0 | 0 |
| `c_hm_robot_biz` | 公司在人形机器人领域已形成明确的客户订单、批量交付或收入贡献… | needs_evidence | 0/0 | 1 |
| `c_hm_chain_node` | 公司是人形机器人视觉感知环节的关键节点供应商… | needs_evidence | 0/0 | 0 |
| `c_hm_fin` | 机器人相关业务收入占比与毛利可量化… | needs_evidence | 0/0 | 0 |
| `c_hm_risk` | 核心技术泄露/人才流失及新业务投入期亏损风险… | partially_supported | 1/0 | 0 |
