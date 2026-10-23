# CAP-R2B.1 回归差集

## 全量后端套件

- 命令：`PYTHONPATH=src .venv/bin/python -m pytest tests/ --tb=no -q`（worktree 根目录）
- 结果：**299 failed / 4791 passed / 87 skipped**（24m10s）
- 基线：R2B 全量 299 failed / 4784 passed（`/tmp/r2b_failures.txt`）
- **逐条差集 = 0**（299 条失败完全一致，全部为既存 `outputs/` 环境依赖；通过数 +7 = 新增 R2B.1 契约测试）

### 运行备注

`test_platform_ready_scripts.py` 中一个测试在 59% 处挂起约 14 分钟：`run_platform_ready_build_cron.sh` 的 `run_step` 心跳循环 `kill -0 $step_pid` 未能感知 step 退出（疑似 PID 复用/收割竞态，脚本既有缺陷），手动 kill 卡住的脚本子进程后套件继续。该测试本就在 R2B 基线 299 失败集内，差集不变。与本改动无关——R2B.1 只触及 `capabilities/` 内存逻辑、dashboard 前端、`tests/test_capabilities.py`。

## 聚焦套件

| 套件 | 结果 |
|---|---|
| `pytest tests/test_capabilities.py -q` | **51 绿**（44 R2B + 7 R2B.1） |
| 聚焦（capabilities + chain_bottleneck + company_intelligence 等） | **406 绿** |
| `cd dashboard && pnpm test` | **443 绿**（41 文件） |
| `cd dashboard && pnpm build` | 通过（仅 chunk-size 警告） |

## R2B.1 新增契约测试（7）

| 测试 | 覆盖验收场景 |
|---|---|
| test_r2b1_dual_attribution_product_line_vs_theme | 688686 机器视觉收入归产品线、人形场景收入 unknown |
| test_r2b1_cert_four_facts_split | 四事实独立；mass_delivery 仅入交付；生态≠具名客户验证 |
| test_r2b1_stage_gate_trace | 无合格证据引用的 confirmed 阶段降级 + 五元 trace |
| test_r2b1_same_source_duplicate_ingestion | 同源重复采集 → non_substantive |
| test_r2b1_same_source_new_fact | 同源新合格反证 → material 研究变化 |
| test_r2b1_stable_task_id_reorder | 任务重排/重跑 ID 不变 |
| test_r2b1_stable_task_id_cross_node_merge | 跨父子节点同需求合并 + related_node_ids |

## R2B 断言修订

`test_r2b_cert_delivery_fields_separated` 原断言 `认证=mass_delivery` 固化了被审核标记的错误语义，已更新为四事实断言（contact + verified_delivered + product_certified + none_seen）；`test_r2b_chain_flags_research_only` 等 3 处同步更新。

## CAP-01/02 不变性

冻结引擎零改动；`node_verdict` 与 claim verdict 判定不变性由原契约测试持续锁定。PIT（as_of=2026-10-23）、幂等、research_only/used_for_signal=False/used_for_admission=False 全部保持。
