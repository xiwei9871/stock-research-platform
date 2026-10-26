# Stock Research 存储与定时任务治理 — A 阶段审计报告 V1

日期：2026-10-26 · 范围：`~/stock_research`（只读审计，未执行任何删除）
产物：`inventory.csv`(2886 项）· `references_hits.csv`(476 项引用命中）· `dup_groups.csv`（真实跨批次重复）· `launchagent_audit.json` · `dry_run_plan.csv`

## 0. ⚠️ 优先发现（与磁盘无关但必须报告）

**10-23（上周五）策略发布失败**:`strategy-eod-publish` 退出码 1,LHB/Mid Trend/Tech Bottleneck 全部 failed（依赖成功）;`platform-ready-check` 报 `external_sync_failed`。下一个交易日（10-27）运行需关注，失败是真实状态不是陈旧日志。

## 1. 定时任务审计结论

| 任务 | 频率 | 结论 | 证据 |
|---|---|---|---|
| dashboard-daily-sync | 22:15 | **保留** | 发布链路正常，release gate 通过至 10-23 |
| strategy-eod-publish | 20:30 | **保留但需修复** | 10-23 失败（见 §0) |
| platform-ready-check | 21:30 | **保留** | 它是捕获上述失败的监控 |
| r2-minute-rebuild-watchdog | 每 5min | **停用候选** ✅ | `minute phase done` 标记存在，watchdog 连续空转写 "done marker present, watchdog idle" |
| factor-gate-backfill-watchdog | 每 30min | **停用候选** ✅ | completion sentinel 自 **5-22** 起 current，每次运行仅输出 "skipped" |
| tdx-auction-backfill-watchdog | 17:10/18:10/19:40 | **保留** | daily 模式，sentinel `complete:2026-10-23`；实际承担每日竞价采集，非一次性回填 |

停用方式（项目惯例）：`launchctl bootout gui/$UID/<label>` + plist 移入 `~/Library/LaunchAgents/.disabled/`。**保留脚本与配置，可逆。**

## 2. 存储结构

`outputs/research` = **7.06GB**(CSV 2.9G + JSON 2.1G + PDF 2.0G + 其他），其中 ~25 个大项占 6.4G,2352 个长尾小项仅 250MB。另有 .venv 1.34G、data/manual 312MB（手工原始输入，不可再生）、dashboard/node_modules 236MB。

### 大项定性

| 项 | 大小 | 定性 |
|---|---|---|
| `data01r1_finance_q2_20261020/r2_downstream_features_done.json` | **2.01GB** | 断点续传账本（`date\|symbol → done`),**不是原始数据**；数据已入 Postgres(187)；重建已完成 → 压缩候选 |
| dragon_*_diagnostics.csv ×4 + dragon_case_event ×1 | **1.62GB** | 研究诊断 CSV,166 天前，仅按需研究命令消费（不在每日 EOD 路径）→ 压缩候选 |
| tech_bottleneck_* 采集批次 ×7 | **1.44GB** | 研报 PDF 证据包，被 consolidation/review 脚本引用；删除前提是"已入 review queue / 远端有副本"→ 验证后删 |
| stock_report_library + theme/yanbaoke 批次 | **0.63GB** | 研报 PDF；与其他批次存在 sha256 级重复 → 去重 + 验证后删 |
| `strategy_daily_eod` | 266MB | **保护**：每日发布产物，每晚整目录 rsync 到远端，远端有完整镜像 |
| `mid_trend_watch_funnel_detail.csv` | 198MB | **保护**:AGENTS.md 硬输入，`strategy_daily_eod.py` 运行时读取 |
| `data/manual` | 312MB | **保护**：手工原始输入（310 PDF)，不可重采 |
| `web_lhb_shortline_v1_runs` | 107MB | LHB 研究运行产物 → 核实生产/消费角色后定 |

### 真实重复（sha256)

PDF 在多个批次间重复存储（library ↔ theme_research ↔ tech_bottleneck pilots)，单个 10-25MB，合计约 **150-200MB** 可去重。（注：dup_groups.csv 中 r2 ledger 的"重复"是扫描器对同一路径的双重计数，非真实副本。)

## 3. DRY_RUN 清理计划

见 `dry_run_plan.csv`。分级：

- **P1 压缩归档（推荐本轮执行）**:9 个大文件 gzip。账本/诊断类文本压缩率 ~90%。**预估回收 ~3.3GB**，零删除，完全可逆（`gunzip` 即恢复）。
- **P1 去重**：跨批次同内容 PDF，保留 canonical 副本。预估 ~150MB。先逐组核实消费方。
- **P2 验证后删（下轮）**:tech_bottleneck/theme/report_library PDF 批次 ~2.4GB。**前提：确认远端/数据库已有可靠副本 + 研报已全部入 review queue。** 未验证前不动。
- **P3 任务治理**：停用 2 个已完成 watchdog。

**达标情况**:P1+P3 一轮约 **3.4GB**（达到 3-5GB 目标下限）,P2 验证通过后可再 ~2.4GB。

## 4. 已核对保护项（不碰）

`serenity_bottleneck_baseline_*`、`market_regime_confirmation_*`、`market_emotion_state_*`、`mid_trend_watch_funnel_detail.csv`、`strategy_daily_eod/`、`reports/`、`data/manual/`、`.venv`、两个 docling 发布目录（本地已近空，实体在远端）。

## 5. 残留风险与限制

- 未核对远端 Postgres(192.168.3.187）行级引用——P2 删除前需远程验证副本/入库
- `data/manual` 若含非公开研报，属"难重采"类，已列长期保留
- inventory 的 size 为逻辑字节和，与 du 口径（APFS 实际块）略有差异
- 长尾 2352 项仅 250MB，建议下轮按"无引用 + >90d"批处理，不必逐个人工审

## 6. 长期治理（C 阶段）建议

- 保留期表：正式 DB/EOD 最新 90 天 / 诊断 CSV 30 天压缩、关键版归档 / 中间产物 14 天 / 难重采原始数据 + 审计证据长期归档
- 每周体检脚本：`storage_healthcheck.py`（见本目录）——体积与增量 top20、无引用过期候选、异常增长报警，默认 DRY_RUN
- 架构层（长期，不本轮做）：采集/计算与 Mac 解耦的迁移评估（baostock/TDX 主机绑定，需独立验证）
