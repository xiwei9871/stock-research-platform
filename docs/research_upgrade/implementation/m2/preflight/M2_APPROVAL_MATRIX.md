# M2 审批矩阵 — 每动作独立授权

**批准任一步不授权后续步骤。两条链互不绑定。**

| 步 | 动作 | 前置条件 | 停止条件 | 本轮状态 |
|---|---|---|---|---|
| T1 | `core.asset_status_daily` +5 列 | SQL 已评审、lock_timeout 演练、避开 EOD 窗口 | 锁超时×3 / post-check 不符 | 就绪待批 |
| T2 | writer/stage 代码部署（OFF） | T1 完成 | 部署异常 | 就绪待批 |
| T3 | 增量 canary（单日→3 日） | T1+T2、Gate require_v2 可评 | incomplete/异版/foreign | 就绪待批 |
| T4 | 历史回填 17.3M | **备份证据（缺→BLOCKED）**、checkpoint 执行器、磁盘水位确认 | 水位/异常率/人工停止 | **BLOCKED** |
| F1 | `finver` schema | SQL 已评审 | post-check 不符 | 就绪待批 |
| F2 | 抓取侧代码（OFF） | F1 完成 | 部署异常 | 就绪待批 |
| F3 | canary 资产追加写 | F1+F2 | failed/unknown_source 非零 | 就绪待批 |
| F4 | raw 历史回放 | F3 验证、回放器 checkpoint | 速率异常/人工停止 | 就绪待批 |
| T5/F5 | 消费者灰度 | M3 准入 | — | 本轮不申请 |

## 首个可申请动作

**T1 或 F1**（互不依赖，建议分开申请分开执行）。

## 仍被禁止

- 生产 DDL 之外的任何生产写入；EOD 接线；正式消费者切换；
- T4 在无备份证据时执行；baostock 全市场重抓；合并 main；
- 修改 canonical/P1d.3 worktree；将排练脚本当生产回填。
