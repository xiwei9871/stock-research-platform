# 03 — MidTrend Dependency Resolution (M0.7 / P1)

Date: 2026-10-20. Status: **historical dirs restored+verified (isolated) /
切片语义问题已定位 / 契约修正待批准**。

## 只读复制（完成）

从 stock-prod `/home/jqz/code/stock-research-platform-main/outputs/research/`
复制两目录到隔离路径 `outputs/research/m0_7_midtrend_restore_20261020/`
（**不回写 canonical outputs**，避免掩盖 EOD 的真实缺失）：

- `current_mid_trend_strategy_v2_top10_candidate_20250101_20260612/`（11 文件）
- `midtrend_pit_attribution_canonical_and_daily_review_lite_v1_20260628/`（16 文件）
- 共 27 文件 + `SHA256MANIFEST.txt` 全量哈希清单。

## 关键发现：这不是"数据停更"，是"静态回放被当日化切片消费"

`strategy_daily_eod.py:1283-1313` 的 `_write_trade_date_slice` 把
`current_mid_trend_strategy_v2_top10_candidate_daily_holdings.csv`（窗口
**2025-01-02→2026-06-12**，3480 行）和 `trade_changes.csv`（2640 行，同窗）按
`trade_date` 过滤切片。

- 该目录是一次性 V2 回测产物，**本就不含 6-13 之后的日期**——6-13 起每日空切片
  是**结构性必然**，不是停更故障。
- 同理 `midtrend_pit_attribution_..._20260628` 为冻结归因工件。
- **平台内没有任何"每日生成 midtrend_v2_top10 候选"的实时管线**——恢复历史目录
  只能恢复可复现性，不能让 10 月切片变新鲜。

## 解决方案（待批准，按用户原则区分三类）

| 输入 | 真实身份 | 建议 |
|---|---|---|
| `midtrend_v2_top10_candidate.csv` / `trade_changes.csv` 切片 | 静态回测回放工件 | **标记 `research_only`**，停止每日 emit 空切片；或加"仅当 trade_date ∈ 工件窗口才产出"契约 |
| `midtrend_canonical_pit_review_labels.*` / `post_exit_watch_lite.*` | 冻结归因研究工件 | 同上，research_only + 版本化引用 |
| 顶层 `mid_trend_watch_funnel_detail.csv` 兜底（5-19 陈旧） | 陈旧兜底文件 | fallback 触发时 manifest 写 `fallback_used=true` + `degradation_reason`；不能静默用 5 个月前数据 |
| 每日 `strategy_mid_trend_review/trades/equity` | 真实每日产物（fresh） | 维持 required |

即：把这些 midtrend 输入在 Gate 注册为 `static_frozen`（版本/hash 校验，不做日期
新鲜度）或 `research_only`（退出正式每日依赖），**停止让 EOD 把冻结工件包装成当日
数据**——这是比"恢复目录"更根本的修复。

## 本轮实做：冻结工件与正式输入分离（代码级，release candidate）

`strategy_daily_eod._write_trade_date_slice` 现在接受 `artifact_status` 输出参数，
`midtrend_daily_review_artifacts_manifest.csv` 新增 `artifact_status` 列：

| status | 含义 |
|---|---|
| `daily_valid` | 切片对当日有行（真实每日产物） |
| `research_only_out_of_window` | 静态工件窗口外空切片（6-13 后的 v2 top10/trade_changes） |
| `research_only_frozen` | 冻结工件整文件复制（canonical PIT 三件） |
| `missing_source` | 源缺失 |

效果：manifest 消费者能区分"每日有效输入"与"历史研究工件"——冻结工件不再伪装成
当日数据。代码变更，279 个 midtrend 相关测试全过；未部署（发布需批准）。

## 未执行/待批准

- 契约改造（EOD 切片函数加 window/research_only 标记）— 代码变更待批准。
- 顶层 funnel 兜底的 fallback 契约 —— 代码变更待批准。
- 目录若决定回到 canonical 路径（非隔离）— 待批准。
