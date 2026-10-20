# CAP-01 三案例结果与人工验收报告

日期：2026-10-21 ｜ 分支：`feat/cap-01-company-intelligence` ｜ 全部输出为 research-only

## 一、三案例引擎输出（真实可追溯证据）

| 案例 | 代码 | 总体判定 | 置信度 | 关键维度结果 |
|---|---|---|---|---|
| 英维克（液冷/AI 数据中心温控） | 002837 | contested | 0.35 | 技术壁垒 部分支持(5/0)；商业化 部分支持(5/0)；竞争优势 **存在反证**(0/4)；财务兑现 **正反冲突**(1/1)；风险 已证实(3/0) |
| 北方华创（半导体设备国产替代） | 002371 | contested | 0.35 | 技术壁垒 部分支持(5/0)；商业化 部分支持(2/0，1000 台里程碑)；竞争优势 **存在反证**(0/1，普达特)；财务兑现 **存在反证**(0/1，产品线未拆分)；风险 部分支持 |
| 奥普特（人形机器人负向对照） | 688686 | needs_evidence | 0.20 | 技术壁垒 部分支持(4/0，工业视觉)；商业化 **needs_evidence**(0/0)；产业链地位 **unknown**(0/0)；财务/竞争优势 needs_evidence |

证据全部来自 `research.tech_bottleneck_review_universe_evidence` 页级摘录（公司定期报告一手披露）+ M1 已核查券商线索（单一来源标注 `lead_only`）。**未虚构任何订单、客户、营收、份额或技术参数**。

### 负向对照行为验证

奥普特在 Theme 映射中 `priority_score=98.0`、`dependency` 高关联，但引擎输出 `needs_evidence`：

- 人形机器人商业化 claim（`c_hm_robot_biz`）支持/反驳 = 0/0 → `needs_evidence` 而非正面；
- "提前布局机器人赛道"（年报 p26）被判为定位性表述 `unclear`，不计作商业化证据；
- 工业机器视觉主业的技术壁垒证据（p11/22/28）如实给出 `partially_supported`——**公司级关联与产品级证据被分开计分**。

这正是验收目标："不因公司名称与热门主题相关就自动给出高评价"。

### 冲突证据不被折叠

- 英维克 `c_edge_uniqueness`（全链条稀缺性）：公司年报自述支持 vs 申菱环境"液冷全方案出海先锋"、三花液冷收入翻倍、国金风液同源图谱、大元泵业屏蔽泵适配 Kyber——4 条反驳使该论点 `contradicted`，总体判 `contested`；反驳证据在矩阵与 bear_case 中全部保留可见。
- 北方华创 `c_fin_by_line`：分部收入不可拆分 → `contradicted`，而非默认"龙头所以财务兑现好"。

### PIT（研究截止）行为

引擎按 `published_at → available_at → ingested_at` 顺序取证据有效时间，晚于 `as_of` 的证据进入 `post_asof_excluded` 并保留记录（单元测试覆盖；三案例真实来源均早于 2026-10-20，故实输出为空列表）。

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
