# M2-T-RELEASE-CANDIDATE — 交易资格 V2 发布包

| 项 | 值 |
|---|---|
| 源码 commit | `da7009bf9571691fdf0f9b644246b8b3f963f21c` 起，集成于 `release/r3-m2-preflight` |
| 依赖基线 | 规则引擎 `compute_pit_limit_flags`（main 既有）、writer `eod_v2_writer.py`、stage `run_eod_v2_stage` |
| Schema 版本 | `core.asset_status_daily` +5 nullable 列 |
| 迁移 SQL | `sql/T1_asset_status_daily_v2_columns.sql`（未执行） |
| 校验 SQL | 同文件尾部 post-check |
| 开关默认 | `enabled=False`（writer 参数级） |
| 回填执行器 | `scripts/m2_t_backfill.py`（checkpoint+throttle+stop+audit） |

## 发布分步（每步独立审批）

| 步 | 动作 | 前置证据 | 回滚 |
|---|---|---|---|
| **T1** | 五列 additive DDL | 本包 SQL + lock_timeout 演练（测试库已执行） | 未写数据前可 DROP COLUMN；写入后按 E3 分级 |
| **T2** | 部署 writer/stage 代码，开关 OFF | 单测 47 过、E2E 9/9 | 代码回退；零数据影响 |
| **T3** | 小范围启用增量 + canary 日期 | 接入点挂 `_build_asset_status_step` 后；stage res.status 落 EOD 状态 | 关开关=立即停写 |
| **T4** | 历史分批回填 | **备份证据必备**（当前 RESTORE_NOT_VERIFIED → BLOCKED）；执行器 checkpoint 续跑 | 停跑+checkpoint 保留；数据按版本可清 |
| **T5** | 消费者灰度 | 属 M3 准入 | — |

## 部署前检查（T3 前）

- `require_v2=True` Gate 对目标日期返回 V2_READY；
- canary 首日：matched==base、state_dist 无异常、checkpoint done；
- wait-gate 未引入 V2 可等条件（防死等）。

## 部署后只读验收

- `evaluate_tradeability(require_v2, expected_version='pit_rules_v1', trade_dates=[canary])` → V2_READY；
- 抽查 10 键：`limit_state_v2∈{0,1,2,3}`、rule_id 非空、版本串一致；
- EOD 日志含 stage status 行；异常路径停 frontier。

## 监控与人工停止

- 日级 checkpoint 表 + Gate 日评；missing>0 或 foreign version → 停 T4；
- 人工停止 = 关 enabled（代码级）/ kill 回填进程（checkpoint 保留续跑）。
