# CAP-01 三案例结果与人工验收报告

日期：2026-10-21 ｜ 分支：`feat/cap-01-company-intelligence` ｜ 全部输出为 research-only

## 一、三案例引擎输出（真实可追溯证据）

| 案例 | 代码 | 总体判定 | 置信度 | 关键维度结果 |
|---|---|---|---|---|
| 英维克（液冷/AI 数据中心温控） | 002837 | unverified (R0: contested) | 0.25 | 全维度 partially_supported；独占性 claim needs_evidence(4 条 lead_only 线索不计入)；液冷收入可量化 claim needs_evidence |
| 北方华创（半导体设备国产替代） | 002371 | needs_evidence (R0: contested) | 0.20 | 技术壁垒/商业化/竞争优势 partially_supported；分部收入 claim needs_evidence（未披露≠反证）；客户验证 claim unknown |
| 奥普特（人形机器人负向对照） | 688686 | needs_evidence | 0.20 | 工业视觉技术 partially_supported；机器人商业化 needs_evidence（越疆合作线索为 lead_only 不计入）；产业链/财务/竞争优势 needs_evidence |

证据全部来自 `research.tech_bottleneck_review_universe_evidence` 页级摘录（公司定期报告一手披露）+ M1 已核查券商线索（单一来源标注 `lead_only`）。**未虚构任何订单、客户、营收、份额或技术参数**。

### 负向对照行为验证

奥普特在 Theme 映射中 `priority_score=98.0`、`dependency` 高关联，但引擎输出 `needs_evidence`：

- 人形机器人商业化 claim（`c_hm_robot_biz`）支持/反驳 = 0/0 → `needs_evidence` 而非正面；
- "提前布局机器人赛道"（年报 p26）被判为定位性表述 `unclear`，不计作商业化证据；
- 工业机器视觉主业的技术壁垒证据（p11/22/28）如实给出 `partially_supported`——**公司级关联与产品级证据被分开计分**。

这正是验收目标："不因公司名称与热门主题相关就自动给出高评价"。

### R1 判定语义修正（2026-10-21）

按初审意见完成四项修复（claim 级判定 / 审核分级 / 严格 PIT / 全量指纹）：

- **claim 独立裁定**：维度结论由 claim 判定聚合；英维克"独占性"(needs_evidence)、"差异化能力"(partially_supported)、"性能对比"(unknown) 三个论点各自保留结论——"有竞对"不再推翻"有优势"
- **审核分级**：`lead_only`/`pending` 证据可见（matrix + pending_verification 清单）但不计入 verdict；`confirmed` 需 ≥2 独立来源（source_id + source_type + publisher 三重独立）且全部 accepted
- **严格 PIT**：ingested_at 为绑定约束（迟到入库→post_asof 排除）；无入库证时按日期上下界判断，区间跨截止日 → pit_uncertain 退出判定；年报类 year 精度不猜精确日
- **"未披露"语义**：证据缺失类条目标 `unclear`（absence-of-evidence），不再误作 refute——北方华创分部收入 claim 由 contradicted 修正为 needs_evidence
- **指纹覆盖全文**：正文/方向/审核状态/claim 绑定/来源时间全部入 sha256；复核记录绑定 dossier_fingerprint 形成可追溯版本

### PIT（研究截止）行为——R1 严格化

`ingested_at` 为绑定约束：已证入库 ≤ 截止日 → 在范围（发表精度单独标记 `published_precision`）；入库晚于截止日 → `post_asof_excluded`；无入库证时按发表/可获取日的上下界判定，区间跨截止日或全无日期 → `pit_uncertain`，全部退出 claim/维度判定且矩阵可见。三案例 ru_* 证据的 ingested_at 取自 DB 数据集入库戳（2026-09-22），非推断值。

## 二、与旧研究流程的基线对照

| 项 | 旧流程（review-universe 证据列表 + M1 dossier） | CAP-01 引擎 |
|---|---|---|
| 结论形态 | 人工阅读全部摘录后自行归纳 | 六维判定 + 每论点支持/反驳计数 + 总体判定 |
| 证据不足 | 依赖读者自觉 | 显式 `unknown`/`needs_evidence`，禁止自动正面 |
| 反证 | 散见于摘录，可漏读 | `bear_case` 集中陈列；反证直接改判维度 |
| 主题≠证据 | `priority_score` 与证据混在一起 | 负向对照实测：98 分主题关联仍判 `needs_evidence` |
| 旧观点误用 | 无截止概念 | 截止后证据进入 `post_asof_excluded` |
| 缺口交接 | 口头/文档 | `research_gaps` 结构化（维度/缺项/需来源/优先级），可直接喂 DATA 线 |
| 可复现 | 无 | `input_snapshot`（含证据集 sha256）+ `code_sha` + 版本化结果文件 |

## 三、五项人工评估指标（首轮自评，待人工复核签字）

| 指标 | 结果 | 依据 |
|---|---|---|
| 核心问题回答完整度 | 中-良 | 六维全覆盖；财务兑现因公开披露口径受限如实降级 |
| 关键事实可追溯率 | 高 | 每条判定可展开到 evidence_id→页码→来源类型→时间戳 |
| 无依据/错误断言数 | 0（自评） | 全部输出源自真实摘录/已核查线索；待人工逐条抽查 |
| 反证与风险识别 | 良 | 主动纳入竞争对矛盾证据；年报风险段入池；"无明确反证"本身被标为缺口 |
| 对后续研究行动帮助 | 良 | 每案 10-15 条结构化缺口；含需要的数据类型与优先级 |

**注意**：以上为开发者自评基线。按验收要求，准确率/投资收益提升不做任何声称；人工逐条核验是 CAP-01.5 的正式门槛。

## 四、复现命令

```bash
cd /Users/xiwei/stock_research/.worktrees/cap-01
for c in 002837_envicool 002371_naura 688686_aoopte_negative; do
  PYTHONPATH=src .venv/bin/python -m stock_research.cli company-intelligence-dossier \
    --case docs/cap01/cases/$c.json \
    --output-dir outputs/research/company_intelligence \
    --code-sha "$(git rev-parse --short HEAD)"
done
```

输出：`outputs/research/company_intelligence/{code}_dossier.{json,md}`

## 五、工作台入口

- 页面：`/research/tech-bottleneck/review-universe`（现有复盘工作台内嵌面板，未新建 dashboard）
- API：`GET /api/research/company-intelligence/dossiers`、`GET/POST …/stocks/{code}/dossier[.md|reviews]`
- 入口：选中复盘股票自动联动，或在"企业研究画像代码"输入框直接输入代码
- 复核：面板内按 claim 记录 accepted/disagreed/needs_more_evidence/rejected + 意见 → 写入同目录 `*_reviews.jsonl` 侧车（研究态，无生产库写入）

## 六、已知边界

1. `direction`/`checklist_item` 由案例 JSON 策展（人工标注），引擎不做自动方向推断——NLP 归类属于后续能力；
2. 负向案例证据池仅覆盖定期报告摘录；存在未被摘录承载的真实机器人业务信息的可能——这正是 `research_gaps` 要表达的；
3. 复核意见写文件侧车而非 `research.research_claim` 表（遵守"不启用新的生产写入"边界）；如需入库需单独审批。
