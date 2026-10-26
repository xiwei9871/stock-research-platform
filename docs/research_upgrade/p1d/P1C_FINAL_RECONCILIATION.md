# P1C_FINAL_RECONCILIATION — P1c 资产集合最终核销

状态矩阵：`p1c_asset_key_matrix.csv`（2,353 行，唯一股票 × 数据 key 维度分列，不使用单一 COMPLETE 掩盖维度差异）。

## 终态数字（2026-10-25 实核）

| 集合 | 数量 | 口径 |
|---|---:|---|
| R2 修复报告 COMPLETE（= Minute/Features eligible） | **2,308** | = 2,250 CONFIRMED_DIRTY 修复完成 + 58 REPAIRED 批完成 |
| Minute done keys / 资产 | 3,077 / 2,293 | baostock 2,234 + akshare 838 + eastmoney 5 |
| Features pinned `full_history_v1` | 2,308 | `factor.technical_feature_rebuild_state` 全 complete；ledger 每股 8,750 键全覆盖（done=写验、skipped=当日无 bar） |
| baostock 分钟终态 FACTOR_GAP | 74 keys / 74 资产 | 详见 `FACTOR_GAP_FINAL.md` |
| 原 155 隔离 | 136 恢复 / 19 仍隔离 | `factor_gap_155_reconciliation.json` |

## 任务书各问项逐条回答

**① 59 股差异来源**：任务书口径下 "Minute eligible 2,308 − R2 有效完成 2,249"。快照时点的 2,249 = 2,251 CONFIRMED_DIRTY − 2 POST_DIFF（600151/600153 当时均隔离）。此后修复驱动继续跑完：58 只 REPAIRED 批 + 600151 经 v4val 复核转 COMPLETE → 终态 2,308，**差异已闭合为 0**（非数据问题，是修复进行中的时点快照差）。

**② "features 完成但 Minute 未全部完成"的 15 股**：600058、600095、600107、600130、600156、600165、600169、600222、600360、600590、600717、603721、688689、002155、301117 —— features pinned 但无任何分钟 done key（baostock 因子缺口且无备用源成功）。属真·个股级 adjustment_factor 缺日，分钟级研究不可用、日频研究可用。

**③ 74 ∩ 155 = 10 只**：600058、600095、600107、600130、600156、600165、600169、600222、600360、600717。其余 64 只终态缺口不在原 155 清单（修复后新暴露的个股因子缺日）。

**④ POST_DIFF 最终状态**：
- **600151**：早期批 POST_DIFF → v4val 复核 **COMPLETE**，分钟已 done —— 已解封。
- **600153**：全部批次稳定 **POST_DIFF**（baostock 回拉数据与平台存量系统性不一致）—— **维持审计隔离**，不入修复/分钟/特征宇宙，不自动解封。

**⑤ 分维度可用性**（矩阵列 `daily_research_eligible` / `minute_research_eligible`）：

| 用途 | 资产数 | 构成 |
|---|---:|---|
| 日频研究可用 | 2,344 | 2,308 R2-COMPLETE + 36 ALREADY_CORRECT（原生数据从未脏，日线/分钟/特征存量齐全，未入修复宇宙） |
| 分钟级研究可用 | 2,293 | minute done 资产（含 59 只备用源覆盖 baostock 缺口） |
| 日频可用但分钟不可用 | 51 | 15 无 done key + 36 ALREADY_CORRECT（分钟为原生口径、未走 R2 派生验证，保守标记需单独确认） |
| 仍隔离 | 19 | 见 FACTOR_GAP_FINAL.md |
| POST_DIFF 隔离 | 1 | 600153 |

## 附注

- `ALREADY_CORRECT` 36 只（多为 2023+ 新股）：DB 实测日线 128,844 行 / 分钟 3,960,960 行 / 特征 85,873 行齐全，但因从未进入修复报告故无 R2 ledger 记录；矩阵单列 `r2_status=ALREADY_CORRECT_NOT_REBUILT`。
- 矩阵 `minute_baostock_factor_gap_terminal` 列对 74 只全部置真（含 59 只备用源覆盖），缺口不掩盖。
