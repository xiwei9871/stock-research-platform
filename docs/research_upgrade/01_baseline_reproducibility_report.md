# M0.5 Baseline Reproducibility Report

**Baseline ID:** `m0_5_frozen_baseline_2026-10-19_v1`
**Frozen at:** 2026-10-20 · **Branch:** `audit/tech-strategy-m0-20261019`
**冻结清单：** `outputs/research/m0_5_baseline_freeze_20261020/m0_5_baseline_freeze_manifest_v1.json`（含全部输入 SHA-256）
**性质：** 研究用基线（research_only）。不用于生产信号；M2 challenger 的对照必须以此（或其显式重跑）为准。

## 1. 冻结配置

| 项 | 值 |
|---|---|
| engine | `tech_bottleneck_v1`（serenity C2 核心，rank-snapshot 模式） |
| 区间 | 2026-01-01 → 2026-10-19（189 交易日） |
| top_n / 调仓 / 成本 / 权重上限 / 复权 / 保护 | 5 / biweekly / 10bps / 0.2 / hfq / rank_exit_top10_1d |
| 股票池 | `strict_153_st_only_financial_state`（评审 153 − ST 剔除 5 = **148**） |
| 代码版本 | 本分支 serenity C2 fail-closed 版；旧 `.get(d,1.0)` 行为仅用于"旧输入"对照记录 |

## 2. 输入哈希（摘录，全表见冻结清单）

| 输入 | SHA-256（前 12） | 行数 | 覆盖 |
|---|---|---|---|
| 候选源 CSV（基线目录原件） | `78532da5bb0d` | 148 | first_hit 2025-08-15..2026-05-29 |
| 10-19 EOD 候选源副本 | `4838fd257788` | 148 | 同上（每日复制生成） |
| PIT 日度快照 | `c78a178a04f3` | 23,952 | 189 日 × 148 资产 |
| 旧 regime（停滞输入，仅留档对照） | `2898f1f590f1` | 827 | 2023-01-03..2026-06-05 |
| **重建 regime（基线输入）** | `300cfa5154e1` | 916 | 2023-01-03..2026-10-19 |
| 重建情绪链 | `1f238f477e47` | 916 | 同上 |
| 行情（只读库） | — | 4,634,877 | 916 日，2023-01-03..2026-10-19 |
| 政策事件 | `2f8ea6102007` | 1 | 2024-09-24 financial_policy |

## 3. 基线结果（重建 regime，PIT 合法）

| equity end | 累计收益 | max DD | turnover | 成本 | 平均敞口 | trades | equity 行 | position 行 |
|---|---|---|---|---|---|---|---|---|
| 1.6562725546 | +65.63% | −24.55% | 9.76 | 0.00976 | 0.8868 | 72 | 189 | 926 |

- 复跑校验：fail-closed 代码下用同一快照+重建 regime 重算，equity end `1.6562725546` 一致（确定性）。
- 旧输入对照（留档，不再作为基线）：equity end 1.5595 / +55.95% / DD −27.49%——9 个调仓日被 1.0 填充，其中 5 个应为 0.7。**历史输出文件原样保留，未改写。**

## 4. 复现步骤

```bash
# 数据输入（只读）
# 1) market_daily_bar / asset_status_daily: service=stock_research, SET TRANSACTION READ ONLY
# 2) regime 重建脚本输出目录: outputs/research/m0_5_market_state_recovery_20261020/
# 回测（内存帧，无输出改写）
python - <<'PY'
# snapshots=read 10-19 tech_bottleneck_daily_candidates.csv
# prices=market_daily_bar hfq 2026-01-01..2026-10-19 (148 assets)
# exposure=read 重建 market_regime_confirmation_daily.csv
# build_tech_bottleneck_v1_from_rank_snapshots(top_n=5,biweekly,10bps,0.2,hfq)
PY
```

失败语义：任一调仓日缺 `target_exposure`（缺行/重复/NaN/非有限）→ `ValueError` 并列出日期；无满额回退。

## 5. 可复现性缺口（如实）

| 缺口 | 状态 |
|---|---|
| V2→V7 谱系测试 | ⚠️ 5 failed：恢复谱系 270/296/348 ≠ 契约 281/307/359；缺 11 行原始输入，来源不存在于本机/归档/远端，未补造；M2 前需用户决定重生成或修订契约 |
| regime 正式路径常数 | ⚠️ `TECH_BOTTLENECK_V1_MARKET_EXPOSURE_PATH` 仍指向 20260605 旧文件；上线 fail-closed 代码前必须更新常数或重生成该路径工件（正式变更，待 Gate） |
| 47 篇报告日期 | ⏸ 待写批准；当前基线不含这些报告的证据贡献 |
| 全量 pytest | ⚠️ 未完成全绿验证；M0 定向集 425 passed / 5 failed |
| `financial_as_of_date`/`technical_as_of_date` 滞后 | ⚠️ 静态种子自带（最新 5-22/6-05）；PIT 合法但陈旧，是否拒绝陈旧特征属 M2 设计问题 |

## 6. Gate 判定输入

- ✅ 可复现基线已冻结：版本+配置+输入 hash+覆盖率齐备，重跑确定性一致。
- ✅ 市场状态缺口已解决（数据链重建+代码 fail-closed）。
- ✅ 148/153 逐条解释且集合恒等验证。
- ⚠️ V7 谱系 blocker 需决策；47 篇报告待写批准；readiness 修复方案待批准。
