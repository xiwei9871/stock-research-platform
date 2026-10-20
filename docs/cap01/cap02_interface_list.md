# CAP-02 需要的数据接口与能力清单（来自 CAP-01 实测缺口）

CAP-01 三案例运行后，引擎以下结构化缺口需要 DATA 线/CAP-02 提供接口。按优先级排序。

## P0 — 直接影响判定正确性

1. **分部/分产品收入毛利接口**
   - 现状：定期报告摘录中"液冷收入""各设备线收入"未单独披露 → 英维克、北方华创 `financial_realization` 均被判 contradicted
   - 需要：`segment_revenue(ts_code, product_line) → {revenue, gross_margin, period, source_page}`
   - 来源：年报分部报告、经营讨论分产品表（docling 结构化抽取）

2. **客户验证/订单证据标准化通道**
   - 现状：英维克年报客户名单只有"具名公司认可"表述；北方华创下游 fab 验证摘录缺失
   - 需要：`customer_validation_evidence(ts_code) → {customer, product, stage(送样/小批量/批量), source_type, page}`，来源：定点公告、投资者关系活动记录、招股书/问询回复

3. **竞争对手结构化对照**
   - 现状：竞对信息靠 M1 手工核查（申菱/三花/大元/普达特），`lead_only` 单源
   - 需要：`peer_comparison(ts_code, product_line) → [{peer, metric, value, source}]`，按产品线而非公司级对照（CAP-03 前置）

## P1 — 提升判定粒度

4. **"定位性表述"与商业化证据的区分标注**
   - 现状："提前布局机器人赛道"被人工标 `unclear`；需要证据表增加 `evidence_substantive_level`（定位/意向/送样/订单/收入）字段或分类规则

5. **报告级 published_at/available_at 元数据**
   - 现状：M0.5 遗留——29 篇日期仍待批准回填；filing 摘录按标题推断年/月，精度不足
   - 需要：`stock_report_source.publish_date` 全量回填 + filing 摘录行级披露日期

6. **公告类证据接入**
   - 现状：案例证据池几乎全部是定期报告；定点/中标/并购公告未系统入池
   - 需要：`announcement` 类 source 的页级摘录进入 `tech_bottleneck_review_universe_evidence` 同构通道

## P2 — 自动化增强

7. **evidence direction 自动预分类**（支持/反证/定位性），人工只复核——当前全靠案例策展
8. **跨案例证据复用**：同一券商线索（如液冷行业图谱）服务多家公司，需要 `evidence_id` 跨 case 引用机制
9. **审核意见入库通道**：当前 JSONL 侧车；如获批写 `research.research_claim` 需迁移接口

## 不需要新建的东西（CAP-02 边界）

- 不新建证据注册表——以上全部走现有 `research.evidence_artifact`/`evidence_link`/`stock_report_source` 通道
- 不改引擎判定逻辑——CAP-02 只提供更细输入，判定阈值/规则保持 CAP-01 语义

---

## CAP-02 第一阶段最小实施任务清单（获批准的后备计划）

目标：在不新建证据注册表、不改正式选股的前提下，把 CAP-01 公司维度的六维判定复用到"产业链节点"维度。

### T1（复用）节点瓶颈分级模型
- 输入：`theme_decomposition` 现有 node（产业链环节）+ 该节点全部公司映射
- 输出：节点级判定 `{node_id, bottleneck_verdict, gate_items: {产能约束,工艺约束,认证周期,技术性能,炒作成分}}`，沿用 CAP-01 的 UNKNOWN/NEEDS_EVIDENCE 与 lead_only 不计入判定语义
- 代码：新模块 `chain_bottleneck.py`，共享 `company_intelligence.py` 的 verdict/PIT/指纹函数

### T2（复用）价值分配证据视图
- 对每个节点聚合其公司 claim：谁有可验证收入 vs 谁只有概念关联
- 输出：节点-公司矩阵 `{node_id, company, 商业化claim判定, 财务兑现claim判定, 证据强度}`
- 直接读 CAP-01 dossier JSON + `theme_research_company_mapping`，无新表

### T3 数据接口（交 DATA 线，见上方 P0 清单）
- 分部收入、客户验证、竞对结构化 —— CAP-02 不自行采集，只消费

### T4 验收用节点（复用现有主题，不新建）
- 候选节点：AI供电液冷（英维克已在案）、半导体设备平台（北方华创+普达特竞对线索已在案）、人形机器人视觉（奥普特负例已在案）

边界同 CAP-01：research_only、零生产写入、无信号/准入改动。
