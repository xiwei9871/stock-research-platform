# CAP-R2C 回归差集

## 全量后端套件

- 命令：`PYTHONPATH=src .venv/bin/python -m pytest tests/ -q`（worktree 根目录）
- 结果：**295 failed / 4816 passed / 87 skipped**（6m44s）
- 基线：R2B.1 全量 **299 failed / 4791 passed / 87 skipped**（24m10s）
- **失败差集 = −4**：减少的 4 条全部为
  `tests/test_platform_ready_scripts.py` 中被修复的测试基建问题
  （心跳挂起根因修复 + 4 条既存断言漂移更正为生产文本）。
  其余 295 条失败与基线逐条一致（`--lf` 输出与全量 FAILED 清单 diff = 0）。
- 通过数 +25 = 新增测试（`test_cap_r2c.py` 16 + `test_platform_ready_step_liveness.py` 5）+ 修复的 4 条。
- 运行时长 24m→6.7m：R2B.1 期间的 ~14 分钟挂起段（run_step 僵尸误判）已随 P0c 修复消除，无新挂起。

## 295 条既存失败分类（P0b）

| 类别 | 处置 |
|---|---|
| 环境依赖：缺 `outputs/research/...` 上游产物 / 陈旧输入（FileNotFoundError、"Expected N rows found M"、openclaw jobs.json 等） | 占绝大多数；非代码失败；补产物即过；本轮不修（任务书允许） |
| 真实代码漂移 ×1 | `eltdx==3.1.3` 声明于 pyproject 但缺 `deploy/dashboard-api-requirements.{in,lock}` → `test_dashboard_release_scripts` 失败。已记录入审计文档，范围外未修 |
| 测试基建 | platform_ready 系列 4 条——**本轮已修** |

## 聚焦套件

| 套件 | 结果 |
|---|---|
| `pytest tests/test_capabilities.py tests/test_cap_r2c.py -q` | **67 绿**（51 + 16 R2C） |
| `pytest tests/test_platform_ready_scripts.py tests/test_platform_ready_step_liveness.py -q` | **19 绿**（14 + 5） |
| 前端 | 未改动 dashboard/，R2B.1 的 443 绿状态保持（无前端变更） |

## R2C 新增契约测试（16 + 5）

P0a×4：五元 trace 解析通过 / 不可解析记录检出 / 未确认阶段缺 trace 定性为 expected_gap / 非法 review_status·scope 检出。
P0c×5：僵尸子进程判死 / 非本子进程(PID 复用)判死 / run_step 不误判 / LIB_ONLY 守卫 / 同类脚本同修复。
P1×5：八类 taxonomy / oos+granularity / not_searched 区分 / contradictory+stale / gap_id 稳定+basis。
P2×2：分项可解释 / 头节点阻断缺口优先于覆盖缺口。
P3×1：真实案例双假设结构（688686 形态）。
P4×3：任务携带 gap 链接字段 / ledger proposed→resolved→reopened / 重复采集不产生新任务不重置状态。
