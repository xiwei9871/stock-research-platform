# R2B.1 → R2C 语义差异

## 结论：纯增量，零语义漂移

对三主题逐字段比对（`r2b1_*.json` vs `r2c_*.json`）：

| 比对面 | 结果 |
|---|---|
| CAP-01 / CAP-02 findings | **逐字节相同**（冻结 verdict 未动） |
| CAP-05 confirmed 阶段判定 | 三主题 0 处 confirmed 翻转 |
| CAP-05 attribution 字段 | pl/theme/theme_rev 全部相同 |
| CAP-06 cert_facts 四事实 | 相同 |
| CAP-07 变化分类语义 | 相同（R2B.1 规则未改） |
| CAP-08 假设评估 | 相同 |

## 新增（additive）字段

| 字段 | 位置 | 内容 |
|---|---|---|
| `research_gaps[]` | chain out | 公司×节点×维度缺口清单（8 类，gap_id 内容哈希，basis 可追溯） |
| `verification_tasks[]` 增强 | chain out + workbench index | +research_gap_id(s)/suggested_sources/completion_criteria/verification_status/last_material_change |
| `competing_hypotheses[]` | chain out | 3 真实案例×2 假设卡片 |
| `research_gap_summary` | workbench index | 缺口 category/band 聚合 |
| `verification_ledger.json` | `outputs/research/cap_workbench/<theme>/` | append-only 任务状态历史（新增运行时产物，gitignored 工作区） |

## 任务数量变化（信息项，非结论变化）

| 主题 | R2B.1 任务数 | R2C 任务数 | 原因 |
|---|---|---|---|
| ai_power | 30 | 31 | 缺口驱动任务并入（按 gap 补 low/medium），去重按既有 key |
| humanoid | ~9 | 10 | 同上 + risk_flagged 假设缺口 |
| semi | ~13 | 14 | 同上 |

任务语义不变：`status` 恒 `proposed`，只读、不接队列；新增字段为闭环
元数据，不改变任务是否被提出的判定。

## 行为修复（P0c，非语义）

`run_platform_ready_{build,check}_cron.sh` 心跳循环：僵尸/PID 复用
子进程不再被误判为存活（只影响测试与运维脚本健壮性，与研究语义无关）。
