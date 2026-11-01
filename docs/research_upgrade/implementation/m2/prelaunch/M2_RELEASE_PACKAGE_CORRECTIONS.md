# P0-A/B M2 发布包勘误 — e73ef14 → fix/r3-m2-prelaunch-safety

## C-1 FINAL_GATE.json 语法修复（P0-A）

- M2-0 的 `preflight/FINAL_GATE.json` 含多行字符串拼接，非法 JSON → 已由生成器重写，标准解析通过；
- 新增 `tests/test_m2_release_artifacts.py` 机器验收：全部 `.json` 可解析、必备文件存在、SHA256 manifest 复算匹配、gate 状态词合法且 final_state 与 blocked 门不矛盾；
- preflight `SHA256_MANIFEST.txt` 已重算（18 项 ok/bad=0）。

## C-2 回填执行器重写（P0-B，详见 BACKFILL_EXECUTOR_SAFETY_REPORT.md）

- `--dsn` 不再绕过生产保护（连接身份核验）；
- checkpoint DDL 分离为 `sql/ops_m2_checkpoint_schema.sql`（生产须评审后手工部署）；
- 全量对账覆盖应处理日期全集+数据一致性；
- 真 stop 机制（stop-file+信号）与 WAL/磁盘水位；
- **T4 runbook 修订点**：生产执行命令必须为
  `m2_t_backfill.py --service stock_research --mode write --allow-prod --prod-confirm "192.168.3.187:5432:stock_research" --stop-file <path>`；
  远程宿主磁盘不可测 → T4 前必须在备份/演练节点实测或提供容量证据，否则执行器自拒。

## C-3 Integrity Gate 准入增强（P0-C，详见 FINVER_WRITER_READINESS.md）

- finver WRITER_READY 现要求新鲜写证据或受控心跳；DATA_READY 绑定声明范围+raw 对账；
- `evaluate_eod_canary`（T3 准入）：逐日核验版本/完整性/v1 不变（`v1_digest` 前后对比）；
- `evaluate_requirements` 现输出 `satisfied` 与 `combined`——LEGACY 不满足 V2 声明、SCHEMA 不满足 DATA 声明、未声明依赖不放行。

## C-4 Runbook 修订（作用于 preflight 两个 runbook）

- **M2_T_PRODUCTION_RUNBOOK**：T4 前置增补——checkpoint SQL 已评审部署、B0-B 备份完成且 TABLE_RESTORE_VERIFIED、磁盘证据就绪、执行器命令按 C-2 更新；
- **M2_F_PRODUCTION_RUNBOOK**：F3 验收增补——Gate 必须用 `evaluate_finver_writer`（staleness_hours≤48 或 heartbeat_at）判定 WRITER_READY；F4 回放后 DATA_READY 需 expected_endpoints 覆盖+对账通过；
- 两包其余内容不变；preflight 文档保持冻结，本勘误为权威补丁。
