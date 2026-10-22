# M0.5 Data Integrity & Baseline Recovery Report

**As of:** 2026-10-20
**Branch:** `audit/tech-strategy-m0-20261019`
**Scope:** 恢复可信、可复现的策略研究环境。未做正式策略参数优化；未写生产数据库；未部署；未改质量池/准入/信号。
**状态图例：** ✅ 已修复且验证通过 · 🧪 已实现/已验证但未部署 · 📐 已设计未执行 · ⏸ 等待生产权限 · ⚠️ 仍存在缺口

---

## 1. Regime 数据停滞根因 ✅（根因确认）/ ✅（数据链已恢复）

### 根因（三条，全部验证）

1. **静态工件不再更新。** 正式路径常数 `TECH_BOTTLENECK_V1_MARKET_EXPOSURE_PATH` 指向一次性生成的 `market_regime_confirmation_v1_tight3b_bt100_20230103_20260605/market_regime_confirmation_daily.csv`（827 行，max `2026-06-05`，SHA-256 `2898f1f5…f4771`，mtime 2026-10-17 未变）。没有任何 cron/launchd 任务会重建该文件；行情库本身已更新到 `2026-10-19`。
2. **`_extend_market_exposure` 只补一个端点行。** 该函数仅在 `end_date` 追加一条"最后状态"行（827→828 行），**不补中间的 6-05 到 10-19 日期**。因此 daily EOD 的 `data_as_of_date` 每天前进，但 regime 中间缺口依旧。
3. **模拟器缺值默认 1.0。** `serenity_tight3b_c2_experiment._normalize_market_exposure` 对 `target_exposure` 做 `.fillna(1.0)`，且 `_simulate_one_config` 用 `exposure_by_date.get(trade_date, 1.0)`——**缺失日期=满额风险敞口**。2026 年内 21 个双周调仓日中 **9 个**（6-15、6-29、7-13、7-27、8-10、8-24、9-07、9-21、10-08）在旧输入中无精确日期，全部以 1.0 计入。

### 恢复结果（已验证）

- 用只读 `service=stock_research` 重建情绪与 regime 全链：916 行，`2023-01-03..2026-10-19`。
  - `outputs/research/m0_5_market_state_recovery_20261020/emotion_state_v1_20230103_20261019/market_emotion_state_daily.csv`（SHA-256 `1f238f47…e42cf`）
  - `outputs/research/m0_5_market_state_recovery_20261020/regime_confirmation_v1_20230103_20261019/market_regime_confirmation_daily.csv`（SHA-256 `300cfa51…3083c2`）
- **历史不改写验证：** 新旧 regime 在共同 827 行历史上 `historical_differences=[]`（逐字段一致），旧文件原样保留。
- 政策事件输入 `data/manual/policy_events_market_regime_v1.csv` 未改动（SHA-256 `2f8ea610…c83d99`）。

### Fail-closed 修复 🧪（审计分支代码，未部署）

- `src/stock_research/serenity_tight3b_c2_experiment.py`：
  - `_normalize_market_exposure` 移除 `.fillna(1.0)`，改为保留 NaN 供校验；缺列时抛错。
  - `_simulate_one_config` 在取敞口前调用 `_validate_market_exposure_coverage`：调仓日缺行、重复行、NaN/非有限值分别抛出带日期清单的 `ValueError`；取数从 `.get(d,1.0)` 改为 `exposure_by_date[d]`。
- 回归测试：`tests/test_serenity_tight3b_c2_experiment.py`（6 passed，含 2 个新 fail-closed 用例）、`tests/test_tech_bottleneck_v1_market_exposure.py`（新增，2 passed）。
- **真实数据验证：** 10-19 快照 + 旧 regime 输入 → `ValueError: market exposure missing exact rebalance dates: 2026-06-15, 2026-06-29, …`（fail-closed）；同一快照 + 重建 regime → 正常通过且复现 equity end `1.6562725546`。
- ⚠️ **部署前置依赖：** 该代码若上线，nightly EOD 会在旧静态 regime 文件下直接失败——必须先重生成 `TECH_BOTTLENECK_V1_MARKET_EXPOSURE_PATH` 指向的全量 regime 工件（新文件已就绪，见 §1 恢复结果；常数更新属正式变更，列入 Gate）。

### 反事实影响（PIT 合法，历史结果保留）

| 输入 | equity end | 累计收益 | max DD | turnover | 交易成本 | 平均敞口 | trades |
|---|---|---|---|---|---|---|---|
| 旧（9 个调仓日缺值→1.0） | 1.5595 | +55.95% | −27.49% | 9.64 | 0.00964 | 0.9553 | 61 |
| 重建全量 regime | 1.6563 | +65.63% | −24.55% | 9.76 | 0.00976 | 0.8868 | 72 |

9 个缺值调仓日中 4 个重建后仍为 1.0（bull_trend），5 个应为 0.7（trend_decay/neutral）——即旧结果在 5 个调仓日被多配了 30% 敞口，且交易次数、回撤、终值全部改变。差异表：`outputs/research/m0_5_market_state_recovery_20261020/market_regime_rebalance_coverage_diff.csv`。结论：**旧 EOD 曲线不可作为 M2 challenger 的对照基线**；M2 对照必须基于重建基线（见 `01_baseline_reproducibility_report.md`）。

## 2. `strict_153` vs 148 完整溯源 ✅

证据目录 `outputs/research/m0_5_strict153_lineage_20261020/`（自 stock-prod 同目录恢复，本地原目录仅有最终 CSV）：

| 文件 | 行数 | SHA-256 |
|---|---|---|
| `candidate_st_only_financial_state_review.csv` | 153 | `e7d61ea8…f668f` |
| `candidate_st_only_exclusions.csv` | 5 | `49682629…cb72` |
| `strict_153_st_only_financial_state_candidates.csv` | 148 | （基线输入，见冻结清单） |
| `financial_state_summary.csv` | 4 | `c0ba91fe…731c0` |

- 集合恒等已验证：`review(153) − exclusions(5) == final(148)` 且 `final ∪ excl == review`（`lineage_verification.json`）。文件名中"153"指评审池数量，最终保留 148。
- **5 只剔除股全部为 `st_or_delisting_risk_name`**（`filter_decision=exclude`；时间口径均为各自 `first_hit_date`/`fundamental_trade_date`）：

| asset_id | 名称 | first_hit_date | 链条 | 财务状态 |
|---|---|---|---|---|
| CN:SH:603398 | *ST沐邦 | 2025-09-19 | 半导体材料 | financial_pressure_review |
| CN:SH:688270 | ST臻镭 | 2025-08-15 | 数据中心光纤/高速连接器 | no_clear_financial_hard_risk |
| CN:SZ:000595 | *ST宝实 | 2026-05-29 | 电网/能源基础设施 | financial_data_missing |
| CN:SZ:000711 | ST京蓝 | 2026-02-06 | 半导体材料 | financial_pressure_review |
| CN:SZ:002214 | *ST大立 | 2025-10-17 | 高端传感器 | financial_pressure_review |

- 最终 148 只中无 ST 名称；财务状态分布：no_clear 123 / pressure_review 18 / pre_inflection 8 / data_missing 4。剔除原因统一为名称含 ST/*ST（退市风险），不是财务打分不足；其中 4 只本身已有财务压力/缺失记录。⚠️ 建议后续把文件名改为含实际数量，避免再误导（改名属正式变更，列入 Gate 备注）。

## 3. V2/V7 ignored artifacts 恢复 ⚠️（部分恢复，存在不可恢复 blocker）

- 恢复机制：stock-prod 副本 → 本机 gitignored `outputs/research/`，`rsync --ignore-existing`（拒绝覆盖非空目录的安全行为已保留并记录一次触发）；逐文件 SHA-256 清单 `outputs/research/m0_5_market_state_recovery_20261020/artifact_restore_manifest.csv`：**957 文件、939 一致、18 不一致**（不一致处保留本地版本，未覆盖，主要为 data-gap 等价性与人工评审产物）。
- 测试改善：M0 定向集 **33 个 FileNotFoundError → 5 个失败**（`425 passed, 5 failed`，见 §7）。缺失文件类错误全部消除。
- ⚠️ **不可恢复 blocker：** 测试契约要求 V5=281 / V6=307 / V7=359，恢复出的谱系为 V2=181 → V3=205 → V4=246 → V5=270 → V6=296 → V7=348。溯源定位缺口在 V2 基线少 10 行与 V4 latent 输入少 1 行（共 11 行）；本机、归档、stock-prod 均未找到对应 191/42 行的原始清单。**未补造数据**；这 5 个测试失败如实保留，M2 前需重新生成或明确接受旧谱系并重写测试契约（二者都需用户决定）。

## 4. EOD success vs readiness PARTIAL 对账 ✅（原因已查明）

事实链（只读核查）：

1. `ops.data_run_manifest`（trade_date=2026-10-19）：17 行，除 `review_evidence_snapshots=skipped` 外全部 success；`review_queue_strategy_manifest` 15 行 success。
2. `review_evidence_snapshots_summary.json` 警告：`exact-date official strategy manifest unavailable` + `review queue empty; snapshot step skipped`（22:46:58）。
3. `ops.review_item_snapshot`/`ops.evidence_digest_snapshot` 对 10-19 **确有各 15 行**，写入时间 **22:49:16-17**——`eod_auto_repair`（22:49:14 起）的 `review_evidence_snapshots` 修复动作在发布产物提升到 canonical 路径后重建队列并持久化了快照。
4. 但修复动作**没有回填 `review_evidence_snapshots` 的 manifest 状态**——仍记 skipped → readiness 继续判 PARTIAL。近 8 个交易日该模块全部为 skipped（同一 staging 时序问题），但快照表实际每日都有数据。
5. `full_evidence_digest`：live 队列的每条 digest 由 `_strategy_lightweight_digest` 生成，其 `overall_status=PARTIAL`、`missing_evidence=[full_evidence_digest]` 是**硬编码的轻量设计**（提示"完整证据请打开个股工作台"），不是 15 条数据缺失；持久化 digest 快照（15 行，overall_status 全 PARTIAL）已在 `ops.evidence_digest_snapshot`。

**根因表述：** 发布管线在 staging 阶段跑快照步骤时，canonical `review_queue_strategy_manifest.csv` 与 `strategy_*` CSV 尚未提升 → 队列空 → skipped；auto-repair 兜底把数据补齐但不修正 manifest 状态。`PARTIAL` 不是数据缺失，是**状态记账不一致**。

**修复方案 📐（设计，待批准）：**
- A（最小）：auto-repair 快照成功持久化后，为同一 trade_date+module 回写 `review_evidence_snapshots` manifest 条目（success、row_count、artifact_path）。可审计、可回滚（仅状态行）。
- B：把快照步骤移到 promotion 之后执行（消除对 repair 的依赖），或向 `build_review_queue` 传 staging `strategy_output_root`/`trusted_release_root`。改动面更大。
- C：readiness 用快照表实际覆盖数而非仅模块 status——属展示口径决策，建议与 A 二选一或叠加。
- 轻量 PARTIAL digest 是否视为降级是产品口径问题；如需区分，可在 readiness 增加 `ops.evidence_digest_snapshot` 覆盖维度（M2+ 决定）。

## 5. 25 主题备份/导出与恢复验证 ✅（导出完成）/ 📐（恢复演练未执行）

- 已执行只读 `REPEATABLE READ READ ONLY` 一致性快照导出：**21 张 `research.theme_research_*` 表、6,939 行**（theme 25 / node 270 / source_item 268 / content_claim 308 / company_mapping 236 / theme_source 966 / object_revision 1,836 等，全量计数见 manifest）。
- 产物：`outputs/research/m0_5_theme_research_backup_20261020/theme_research_logical_export_v1.json.gz`（1,034,123 B，SHA-256 `cf50e316…46e44e`，权限 0600）+ `theme_research_export_manifest_v1.json`（含逐表行数与连接证据）。逻辑导出，**不含 PDF 二进制**。
- 恢复验证方案 📐（未执行，需批准）：校验导出 SHA-256 → 导入独立 staging 库（非生产）→ 逐表行数+逐行 canonical JSON 比对 → 检查主外键完整性。**防覆盖规则：** 仅追加缺失行；凡目标行 `updated_at` 或 `review_event`/`object_revision` 时间晚于快照时间一律跳过（保护较新人工审核）；review_event 只增不改；全程可审计（恢复批次+逐行比对报告）。生产恢复属写操作，须单独批准。

## 6. 47 篇研报日期补录 ⚠️（dry-run 完成，等待写权限）

- dry-run 明细 `docs/research_upgrade/01_report_metadata_dry_run_diff.csv`：47 行源记录均含原始下载日期；按 PDF 封面日期 token 分类为 29 `cover_date_match` / 11 `cover_date_other`（冲突，需人工裁决）/ 7 `no_cover_date_found`。
- 未写生产库（须单独批准）；详见 `01_report_metadata_remediation_plan.md`。

## 7. 验证与测试状态

| 项 | 结果 |
|---|---|
| M0 定向测试集（20 文件）+ serenity + 新 fail-closed | **425 passed / 5 failed / 27 warnings**（18.2s） |
| 5 个失败 | 全部为 V7 谱系版本差异（270≠281、348≠359），非代码回归 |
| fail-closed 新增用例 | 4/4 pass（serenity 2 + tech_bottleneck_v1 2） |
| 真实数据 fail-closed | 旧输入抛缺失日期 ValueError ✅；重建输入通过且复现 1.6563 ✅ |
| 全量 pytest | 本阶段未跑完（M0 曾 59% 中断），不作全绿声明 |

## 8. 交付边界确认

- 生产数据库会话全部 `transaction_read_only=on`；本轮零生产写。
- 正式策略参数（top_n=5、biweekly、10bps、0.2、hfq、rank_exit_top10_1d）未改。
- 质量池/准入/信号/Top5 未改；V7 全部产物仍为 research-only（V7 ledger：52 pending / 26 hold / 0 approved）。
- 唯一代码改动：serenity 模拟器 fail-closed（+2 测试文件改动/新增），在审计分支未部署；部署前必须先生成全量 regime 工件（§1）。
- README.md / docs/README.md 仍未提交，未混入本阶段。
