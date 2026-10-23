# CAP-R2A 回归差集

## 全量后端套件

- 命令：`PYTHONPATH=src .venv/bin/python -m pytest tests/ --tb=no -q`（worktree 根目录）
- 结果：**299 failed / 4774 passed / 87 skipped**（22m15s）
- R1 封版基线：299 failed（`/tmp/cap_final_failures.txt`）
- **差集：0 新增 / 0 消失**（逐条 diff，DIFF_LINES=0）
- 299 条全部为既存 `outputs/` 环境依赖失败，与 R1 基线逐条一致。

## 聚焦套件

| 套件 | 命令 | 结果 |
|---|---|---|
| capability 契约（含 R2A 对抗） | `pytest tests/test_capabilities.py -q`（仓库根） | 34 绿（其中 10 项 `test_r2a_*` 对抗场景） |
| 前端 | `cd dashboard && pnpm test` | 443 绿（41 文件） |
| 前端构建 | `cd dashboard && pnpm build` | 通过 |

## 对抗场景覆盖（tests/test_capabilities.py `test_r2a_*`）

1. 一手支持与一手反证并存 → `contested`
2. 多引用指向同一底层来源 → `independent_source_count` 去重
3. 父子节点重复引用同一证据 → source 级去重，不重复计独立确认
4. 仅 lead_only 线索 → 不提升结论
5. 产品认证缺客户认证 → barrier `unverified`，替代解释保留
6. 组件交付缺系统级业务证据 → delivery 不升级 revenue
7. 板块收入缺产品线归属 → `disclosed_broader_scope` + attribution gap
8. 来源晚于 as_of → 不进入判定
9. 无可比公司/口径不一致 → `not_comparable`/`partially_comparable` + 原因
10. 缺失源/错误源/空数据 → 受控回退，不造正面结论

## CAP-01/02 不变性

冻结引擎未改动；`node_verdict` 逐值不变性由契约测试锁定；CAP-04 技术评估不覆盖 node_verdict。
