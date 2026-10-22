# M0.5 Report Metadata Remediation Plan（47 篇研报日期补录）

**As of:** 2026-10-20 · **状态：** ⚠️ dry-run 完成、方案已定；生产数据库写入**等待单独批准**
**输入证据：**
- 源清单：`outputs/research/stock_report_import_100_20261019/stock_report_library_manifest_107.csv`（107 行：100 新 + 7 复用；47 行 DB `publish_date`/`report_date` 为空）
- dry-run 差异表：`docs/research_upgrade/01_report_metadata_dry_run_diff.csv`（47 行，SHA-256 `14f98acb…`）
- PDF 字段回填：`outputs/research/stock_report_import_100_20261019/stock_report_pdf_field_backfill.csv`（100 行；99 解析、1 无文本层）

## 1. 问题与口径

- 47 篇报告（全部来自 `theme_batch4` 批）在原始下载清单 `download_manifest_remaining47.csv` 中以 `date` 列存有发布日期，但标准化清单与生产 `research.stock_report_*` 的 `publish_date`/`report_date` 均为 NULL。
- 现有卡脖子关键词支持查询 `…_load_report_keyword_support` 硬性要求 `e.report_date >= DATE '2024-01-01'` → 这 47 篇**当前不进入证据消费**。
- 三个日期口径区分：`source_date`（来源/清单日期）、`event_date`（报告封面发布日）、`available_at`（入库可获取日=下载/导入日）。

## 2. dry-run 结果（未写库）

| 分类 | 数量 | 处理建议 |
|---|---|---|
| `cover_date_match`（清单日期=封面日期 token） | 29 | `report_date`/`publish_date` 采用该日期；可信度高 |
| `cover_date_other`（清单与封面日期冲突） | 11 | 不自动写入；逐篇人工裁决以封面日期为准或标注来源日期口径 |
| `no_cover_date_found`（PDF 无可提取封面日期） | 7 | 不自动写入；人工核验（部分为扫描件/无文本层） |
| 关键词命中复核 | 10 命中 / 其中 6 在 match 组 / 4 未决 | 命中但日期未决者同样留待人工 |

- 原则：**只自动补能同时被"清单日期"和"封面日期"独立印证的 29 篇**；18 篇进入人工核验队列，绝不猜日期、不统一填导入日。
- `available_at` 一律取实际下载/导入时间（有台账），不与发布日混用。

## 3. 证据消费前后对照（修复后预期）

| 维度 | 修复前（当前） | 修复后（批准后） |
|---|---|---|
| `report_date >= 2024-01-01` 通过 | 0/47 | 29 自动 + ≤18 人工确认 |
| 卡脖子关键词支持可用标题 | 0 篇 | 最多 47 篇（以人工核完为准） |
| `latest_publish_date` 汇总 | 停在 2026-10-13 | 推进至真实最晚发布日（清单内最晚 2026-10-18） |
| 信号/准入 | 不变（`auto_trade_enabled=false`、`used_for_signal=false` 保持） | 不变——仅使报告**可被查询**，证据是否采用仍走现有审核 |

## 4. 执行方案（等批准）

1. **申请窗口：** 生产写批准（限定 `research.stock_report_source.publish_date` 与事件 `report_date` 两列、47 行范围）。
2. **写入内容：** 29 篇直接写 `report_date=publish_date=封面/清单日期`；11 篇冲突逐篇裁决后再写；7 篇人工核验；全部 47 行写 `available_at=下载时间`、`metadata.date_remediation={source:'m0_5_dry_run', category}` 留痕。
3. **可回滚：** 写前导出 47 行原值快照（字段级 CSV+sha256）；写后 diff 报告；回滚=按快照还原两列。
4. **验证：** 重跑 `_load_report_keyword_support` 计数（前后对照写入 dry-run 表新列）；重跑 `research_reports` manifest 行 `latest_trade_date` 核对；抽样 5 篇人工比对面页。
5. **不做：** 不修改 PDF 文件、不改 `public_access`、不触发任何特征/信号计算。

## 5. 关联风险（已记录，不在本方案处理）

- 外网 PDF 路由未校验登录且不执行 `public_access=false`（M0 §访问边界）；本方案只补日期，不改访问控制——若需收敛，单独申请。
