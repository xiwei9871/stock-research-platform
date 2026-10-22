# M0.5 + M1 Gate Review

**As of:** 2026-10-20 · **Branch:** `audit/tech-strategy-m0-20261019`
**交付物：** `01_data_integrity_recovery_report.md` · `01_baseline_reproducibility_report.md` · `01_report_metadata_remediation_plan.md` · `01_theme_competitive_moat_pilot.md` · 本文件
**附：** `01_report_metadata_dry_run_diff.csv`（dry-run 明细）；冻结清单 `outputs/research/m0_5_baseline_freeze_20261020/m0_5_baseline_freeze_manifest_v1.json`

## 1. 状态总表（按用户要求四分）

### ✅ 已修复且验证通过

| 项 | 证据 |
|---|---|
| 市场状态数据链 | 重建 916 行 regime/emotion（2023-01-03..2026-10-19），与旧件共同 827 行逐字段一致（`historical_differences=[]`）；SHA 已冻结 |
| 缺值满额敞口（1.0 默认） | serenity C2 已 fail-closed：调仓日缺行/重复/NaN→`ValueError` 列日期；旧输入实测被拒、新输入复现 equity 1.6563；4 个新测试通过 |
| `strict_153` vs 148 溯源 | `review(153) − exclusions(5) == final(148)` 集合恒等验证；5 只全部为 `st_or_delisting_risk_name`（*ST沐邦/ST臻镭/*ST宝实/ST京蓝/*ST大立）；逐只时间口径记录 |
| V2/V7 缺失文件恢复 | 957 文件 manifest + SHA-256；33 个 FileNotFoundError 全部消除（rsync 防覆盖行为保留，18 处不一致保留本地） |
| EOD/readiness 对账 | 原因查明：发布 staging 时序导致快照步骤每天 skipped→auto-repair 22:49 补齐数据但不回填 manifest 状态→readiness 如实报 PARTIAL；`full_evidence_digest` 缺失为轻量 digest 设计行为 |
| 25 主题导出 | 21 表/6,939 行 REPEATABLE-READ 一致性快照 + manifest + SHA-256（只读，零生产写） |
| M1 主题 pilot | 3 个 dossier（英维克液冷/北方华创/人形机器人负对照）：每条结论标注 verified/estimated/unknown，反证与证据缺口列出；**M1 按门槛未通过（partial）——如实记录** |

### 📐 已设计但尚未执行

| 项 | 说明 |
|---|---|
| readiness 修复方案 | A：auto-repair 快照持久化后回填 `review_evidence_snapshots` manifest 状态（最小可回滚）；B：快照步骤移到 promotion 后或传 staging root；C：readiness 改用快照表覆盖口径 |
| 主题恢复演练 | 导出→staging 库导入→逐行比对→晚于快照的人工审核一律跳过（只增不改） |
| `strict_153` 文件名更正 | 建议改为实际数量或含口径的名称（正式变更） |

### ⏸ 受生产权限限制等待批准

| 项 | 需要的批准 |
|---|---|
| 47 篇报告日期补录 | 生产写批准（29 篇自动+18 篇人工队列；含原值快照回滚方案） |
| regime 正式路径更新 | `TECH_BOTTLENECK_V1_MARKET_EXPOSURE_PATH` 指向全量重建文件（或同路径重生成）——**上线 fail-closed 代码的硬前置** |
| fail-closed 代码合并/部署 | 审计分支已验；合并 main + 部署属正式发布批准 |
| 主题库恢复 | 任何生产恢复均为写操作 |

### ⚠️ 仍存在的数据/证据缺口

| 缺口 | 影响 |
|---|---|
| V7 谱系 11 行原始输入不存在 | 5 个测试持续失败（270/281、348/359）；**不可补造**；M2 前需决定：重生成该谱系 或 修订测试契约至恢复谱系 |
| M1 主题证据不足 | 客户验证/份额/毛利/现金流/竞品对比普遍 `unknown`；47 篇新报告未入库前主题来源仍陈旧（最新 7-10） |
| `financial_as_of_date`/`technical_as_of_date` 陈旧（5-22/6-05） | PIT 合法但陈旧；陈旧特征是否拒绝属 M2 策略设计决策 |
| 全量 pytest 未跑完 | 不能作全绿声明；M0 定向集 425 passed / 5 failed |
| PDF 访问控制 | 外网 PDF 路由未校验登录且不执行 `public_access=false`（M0 已记录，本轮未改） |

## 2. 关键风险声明

1. **fail-closed 与 regime 工件的部署耦合：** 若只合并 fail-closed 代码而不更新 regime 路径，nightly EOD 会从下个交易日起**直接失败**（这正是设计的 fail-closed 行为）。两项必须作为一次受控变更一起上，或先只更新数据工件。
2. **旧 EOD 曲线不可作 M2 对照：** 9/21 调仓日含 1.0 填充（5 日影响敞口），收益/回撤/交易数均被改变。M2 消融实验基线必须用 `m0_5_frozen_baseline_2026-10-19_v1`。
3. **readiness PARTIAL 不是数据缺失：** 快照数据实际完整（每日 15 项），但 manifest 状态长期记 skipped；修复前先按"记账不一致"处理，避免误读为发布失败。

## 3. M2 放行建议

**建议：条件放行**——在以下三点完成后进入 M2 正式策略优化：

1. 批准并执行 regime 正式路径更新 + fail-closed 代码合并/部署（一次受控变更，可回滚）。
2. 对 V7 谱系 blocker 作出书面决定（重生成 or 修订契约）。
3. 批准 47 篇日期补录（或明确推迟，并在 M2 证据口径中排除该批报告）。

M1 主题 pilot 不阻塞 M2：它已产出可用的证据框架与诚实的能力边界（当前来源不足以支撑"护城河已成立"结论），后续按相同标准补充客户/财务/竞品证据即可，不要求 M0.5 全部收尾。

## 4. 本轮提交清单（待 commit/push 至审计分支）

- 5 份交付文档 + `01_report_metadata_dry_run_diff.csv`
- 代码：`serenity_tight3b_c2_experiment.py`（fail-closed）、`tests/test_serenity_tight3b_c2_experiment.py`（+2 用例）、`tests/test_tech_bottleneck_v1_market_exposure.py`（新增 2 用例）
- 不提交：`README.md`、`docs/README.md`（前项整理，保持独立）；本地 outputs/ 恢复产物与备份（gitignored，清单已记录哈希）
- 不合并 main；不部署；不写生产库。
