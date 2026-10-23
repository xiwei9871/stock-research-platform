# CAP-R2B 回归差集

## 全量后端套件

- 命令：`PYTHONPATH=src .venv/bin/python -m pytest tests/ --tb=no -q`（worktree 根目录）
- 结果：**299 failed / 4784 passed / 87 skipped**（25m07s）
- 基线：R1 封版 299 failed（`/tmp/cap_final_failures.txt`）
- **逐条差集 = 0**（diff 行数 0；新增 10 个测试全部通过，通过数 4774→4784）
- 299 条失败全部为既存 `outputs/` 环境依赖问题，与基线逐条一致

## 聚焦套件

| 套件 | 结果 |
|---|---|
| `pytest tests/test_capabilities.py -q` | 44 绿（R2A 34 + R2B 10） |
| 聚焦（capabilities + chain_bottleneck + company_intelligence） | 116 绿 |
| `cd dashboard && pnpm test` | 443 绿（41 文件；一次并发 flake 重跑全绿） |
| `cd dashboard && pnpm build` | 通过 |

## R2B 新增契约测试

| 测试 | 覆盖 |
|---|---|
| test_r2b_cert_delivery_fields_separated | A1 认证/交付车道分离 |
| test_r2b_directional_source_counts | A2 正/反来源分别计数+合计去重 |
| test_r2b_stage_evidence_gated_no_skip | B 阶段门控不跳级 |
| test_r2b_delivery_without_revenue_no_upgrade | B 交付≠收入、板块≠产品线 |
| test_r2b_pl_revenue_and_margin_unlock_stages | B 产品线收入+毛利解锁两阶段；现金仍缺 |
| test_r2b_materiality_rules_auditable | C 分级：假设翻转 material、同源重采 non_substantive、cap_status metadata_only |
| test_r2b_stage_flip_tracked_in_snapshot | C stages 变化入快照 diff |
| test_r2b_verification_tasks_proposed_only | D 任务 proposed/去重/优先级/不自动执行 |
| test_r2b_cap10_isolation_contract | E 生产模块零引用 + 隔离标志 |
| test_r2b_chain_flags_research_only | E 链路 research_only 不变量 |

## CAP-01/02 不变性

冻结引擎零改动；`node_verdict` 与 claim verdict 判定不变性由原契约测试持续锁定。
