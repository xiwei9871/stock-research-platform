# P2.1-Final-A Raw Payload 解析与版本取证（修正版）

复现：`scripts/p21_forensics_v2.py` → `RESTATEMENT_FORENSICS_CORRECTED.json`

## v1 的两个确认缺陷

1. `extract_metrics()` 只认 dict 顶层 / `data`/`result` 键——真实 akshare 载荷是 **list[dict]**（每快照 9~48 个报告期行），全部解析为空 → 空字典被误判"指标不变"；
2. `period_key()` 在 list 载荷上取不到 REPORT_DATE → 同资产同端点的所有期坍缩进 `'unknown'` 分组——**15,720 个分组键的定义错误**。

## 修正后的解析器

- `to_rows()`：支持 `list[dict]`、dict、`{data|result|rows: [...]}` 包装、不可解析 → 空；
- 行级 `REPORT_DATE` 展开为 (asset_id, endpoint, report_period) 真实分组键；
- `classify_fields()` 标准化数值比较，逐字段分类：`missing`（单快照缺字段）/ `null_asymmetry` / `precision`（≤1e-4 相对差）/ `changed` / `equal` / `metadata_only`（UPDATE_DATE 等元字段豁免）；
- **空提取 = 覆盖失败单独计数，永不作"不变"判据**；
- 指标列过滤 `*_YOY`/`*DATE`/元字段。

## 重算结果

- 展开快照行 **959,839**（16,586 载荷）；真实分组键 **930,620**（v1 的 15,720 作废）；
- 提取覆盖：extracted_nonempty 955,490 / no_period_key 4,349（sina/cninfo 异构载荷）/ unparseable 0；
- 分类矩阵：single_fetch 905,750 / equal 12,524 / payload_changed_same_metrics 12,274 / null_asymmetry_delta 36 / precision_only 2 / **metrics_changed 34**；
- 72 个差异事件含原始证据指针（raw id、首末 fetched_at、字段级 diff、hash 序列）；
- **观测窗内捕获 34 个真实指标变化**——集中于 `stock_cash_flow_sheet_by_report_em` 的 2025-06-30 期，2026-08-28→2026-10-21 两次抓取间 EM 侧改写了 ASSET_IMPAIRMENT/OPERATE_PAYABLE_ADD 等字段。**首次快照保留 → 34 键初版可恢复**（initial_recoverable=72 个事件级快照）；
- baostock 载荷表仍为空（0 行）——该侧重述证据永久缺失。

## 对 v1 结论的影响

v1 的"metrics_changed=0"建立在错误解析之上，本版为有效口径；无论重算结果如何，**初版可证明性结论不变**：载荷历史仅覆盖 2026-05 起的抓取窗，更早的重述事件在证据链外。
