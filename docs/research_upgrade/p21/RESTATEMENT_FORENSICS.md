# P2.1-D 历史重述取证（raw payload hash 序列）

复现：`scripts/p21_restatement_forensics.py` → `restatement_forensics.json`

## 证据基底

| 源 | 行数 | 说明 |
|---|---|---|
| raw_akshare.finance_payload | 16,586 | 2026-05~10 抓取窗，fetched_at + payload_hash |
| raw_baostock.finance_payload | **0** | **表存在但从未写入——baostock 侧重述证据永久不可得** |

## 版本事件矩阵（asset × endpoint × period 分组，15,720 键）

| 分类 | 键数 | 含义 |
|---|---|---|
| single_fetch | 14,874 | 仅一次快照，无任何版本证据 |
| duplicate_refetch | 293 | 多次抓取 hash 相同——内容未变 |
| payload_changed_same_metrics | 553 | hash 变但追踪指标不变——元数据/字段顺序抖动 |
| **metrics_changed** | **0** | **追踪指标数值变化——观测窗内零次** |
| initial_recoverable / unrecoverable | 0 / 0 | — |

## 结论

1. 观测窗（~5.5 个月）内未捕获任何数值级重述事件；payload 变化全部是元数据抖动。
2. **历史重述（发生于首次抓取前）从此证据链不可恢复**——初版不可证明，坐实 `historical_version_missing` 为默认分类。
3. raw 载荷是唯一的前向取证源：从现在起每次抓取都在积累版本证据。
4. baostock 侧：载荷表从未启用，且 baostock 财务字段覆盖残缺（audit 中 118k+ revenue 单源缺失）→ 版本化修复应以 akshare_em 为主源，baostock 降为指标表（indicator_quarter）来源。

## 版本化修复方案（建议，本轮不改 Schema）

1. 三表新增 additive 列：`statement_version int`（同源同键内单调）、`superseded_at timestamptz NULL`、`is_initial_public bool`（证据可证时）；
2. 写方改 append-only：同 (asset,period,type,source) 数值变化 → 新 version 行 + 旧行 superseded_at 标记；同值重抓 → 仅 updated_at；
3. raw payload 抓取常态化并保留全历史（已是），hash 序列作为重述探测器；
4. announcement_date 语义修正：新增 `first_disclosed_at`（初始披露）与 `reannouncement_date`（再披露），EM 现值归入后者。
