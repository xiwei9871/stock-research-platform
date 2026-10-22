# 03 — Regime Release Candidate (M0.7 / P0-2)

Date: 2026-10-20. Branch: `audit/tech-strategy-m0-20261019`.
Status: **design corrected per review + evidence-backed row classification /
permission-blocked for production write**.

## Review corrections applied

| Reviewer correction | Change in this design |
|---|---|
| 不可直接批准“每日全量重建并覆盖历史 DB 行” | 新方案 = staging 重建 + **版本化差异报告**，历史行改动分类审批后才可写 |
| evidence digest PARTIAL 不能作验收条件 | 已从验收清单移除（轻量 digest 的 PARTIAL 是产品设计语义） |
| 依赖按固定时钟顺序执行 | 改为**完成验证驱动**的顺序执行（上游落地且校验通过才启动下游） |

## 79 行历史情绪分歧的实测分类（repaired-verified evidence）

对 `research.market_emotion_state_daily` 在 2026-06-05 之后的 **79 行**与全量重建
（`m0_5_market_state_recovery_20261020/…/market_emotion_state_daily.csv`, 916 行）逐列比对：

| 指标 | 结果 |
|---|---|
| 行数 | 79；其中 **29 行分歧**，50 行与重建完全一致 |
| emotion_score 分歧 | 29 行（max |Δ| = 8.75） |
| breadth_score / limit_score | 15 / 13 行 |
| emotion_state 档位翻转 | 8 行（如 cold→neutral, neutral→hot） |
| risk_state 翻转 | 12 行 |

按 `updated_at` 相对收盘(15:00)的滞后分类：

| 类别 | 判据 | 行数特征 | 解释 |
|---|---|---|---|
| **PIT 快照（收盘前写入）** | lag ≈ **−1.8h**（~13:12 写，盘中未完结数据） | 分歧行中位数 −1.8h | 用盘中未收口数据计算 → 与收盘后全量重建必然不同 → 这是**可获得性口径差异**，非计算错误 |
| **迟延回填** | lag 68–311h（写入晚数天） | 如 6-23(lag 140h)、6-24(116h)、6-25(92h) | 晚写但用的是当时可得源数据 → 源数据后续修订或口径差异，**无法回溯区分**是源修订还是当时快照窗口 |
| 正常一致 | — | 50 行 | 已正确 |

**结论**：分歧主要属 **PIT/数据可获得时间差异**（收盘前快照 + 迟延回填），已证实计算
函数确定性正确（同日重算 = 重建值）。**不能证明**存在上游源数据修订；也**不能**
把所有 29 行归为"计算错误"——它们是不同写入时点下的各自合法快照。

## 修正后的发布设计（staged rebuild + versioned diff）

1. **每日 staging 重建**（替代"就地追加当日行"）：
   `market-emotion-state-v1-backfill` → staging 目录；`build_market_regime_confirmation_from_frames` → staging。不与生产表对比写入。
2. **版本化差异报告**：staging vs 生产逐日对比，输出行级 diff + 分类标签
   （`pit_snapshot` lag<0 / `late_backfill` lag>24h / `identical`）。差异行**不自动覆盖**。
3. **历史行改写策略**：只有分类为可证明的计算错误、且经明确批准的日期区间，才允许
   版本化覆盖（保留 `source_vintage` 与旧行导出备份）。今日起的新行一律按收盘后口径生成。
4. **原子发布**：校验通过 → 版本目录 + `latest` 指针切换 + DB 事务内 upsert 当日行；
   任何校验失败 → 保留旧发布、阶段 fail-closed。
5. **顺序依赖（非时钟）**：行情落地校验 → emotion 重建校验 → regime 校验（缺调仓日/
   重复/NaN fail-closed）→ 策略 EOD；每步须上游 `READY` 信号而非固定时刻。

## 验收条件（修正版）

- staging 差异报告连续 N 日稳定（漂移只落在当日行）。
- fail-closed 用例全部生效（缺日/重复/NaN/源改写四类注入）。
- **不**以 evidence digest 全 READY 为验收（PARTIAL 为轻量摘要设计语义）。
- EOD 冻结基线回放 equity endpoint 复现 `1.6562725546299535`。

## 本轮实做（代码 + 故障演练，隔离）

新模块 `src/stock_research/regime_daily_update.py`（8 测试绿）：

- `validate_regime_frame`：空表/非法日期/重复/非递增/缺失或 NaN target_exposure/
  最后日≠预期/缺必需调仓日 → 全部 fail-closed `RegimeValidationError`。
- `diff_against_published`：行级 diff（new_date / removed_date / value_changed），
  **数值容差 1e-9**——初版精确比较误报 480 行"变化"，实测均为浮点精度噪声；
  修正后 staging vs canonical = **89 新增日期、0 共享日期内容变化**（前缀稳定性
  正式证实：发布重建版不改写任何历史行的实质值）。
- `publish_versioned` + `rollback_to_version`：版本目录 + `latest` 指针；
  无效输入拒绝发布且旧版本不动；回滚=指针回切。
- 隔离演练 `outputs/research/m0_7_regime_release_drill_20261020/`：
  正常发布→指针移动 ✓；NaN 输入→拒绝且指针不动 ✓；回滚到 20260605 ✓。

即"每日自动更新+历史版本隔离+回滚"所需的核心构件**已经实现并演练**；未接入生产
调度（待批准）。历史行改写按用户要求走"staging 差异报告→分类→审批"，本轮证据
支持"新增发布不改写历史实质值"。

## 仍未执行（等待批准）

- 每日重建+staging+差异报告的代码编写（设计完，未写）。
- 生产 DB 写入/覆盖历史行 —— 需差异报告先经人工分类审批。
- 调度接入（改为完成驱动顺序后接入 daily_close_pipeline 链）。
