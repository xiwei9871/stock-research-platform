# CAP-R2C Audit — 研究缺口、反证与验证任务闭环

基线：`fix/cap-r2b1-evidence-scope` @ `9a7164e3`
范围：`research_only` 研究能力升级。不生成股票推荐、不触碰信号/准入/生产调度、不使用 Tushare、PIT 口径保持 as_of=2026-10-23。

## P0 — R2B.1 验收补充

### P0a 阶段 trace 完整性（机器可读核验）

`capabilities/trace_audit.py`：resolver 由 T3 记录库
（`docs/cap02/t3/t3_records.json`，30 条）、公司 dossier
`evidence_matrix`（65 条）与 T3 source manifest（65 source_id）构建；
对每条 `trace[]` 元素逐一校验
`record_id → source_id → review_status → scope → effective_as_of`
五元可解析性。

三主题实际结果（**72 个阶段组合**，与任务书口径一致）：

| 主题 | 阶段行 | confirmed | 全部解析 | gate_breach | partial_trace |
|---|---|---|---|---|---|
| ai_power_value_capture_v1 | 54 | 8 | 8 | 0 | 0 |
| humanoid_robotics_head_to_toe_v1 | 6 | 0 | — | 0 | 0 |
| semi_equipment | 12 | 1 | 1 | 0 | 0 |
| **合计** | **72** | **9** | **9** | **0** | **0** |

`trace_complete=False` 的 63 行全部为**未确认阶段缺有效
trace**——即 R2B.1 gate 正确降级的 expected_gap，不是本轮新增故障。
分类输出为 `resolved / gate_breach / partial_trace / expected_gap` 四态，
机器可读（`validate_stage_traces` 返回行级记录）。

### P0b 299 项既存失败分类

`pytest --lf`（295 条）逐条按错误签名分类：

| 类别 | 占比（估） | 证据 | 风险 |
|---|---|---|---|
| 环境依赖（缺 `outputs/research/...` 上游产物 / 陈旧输入） | ~85% | `FileNotFoundError`、"Expected 596 doubled tech input rows, found 316" 等——脚本对缺失上游硬失败，测试断言子进程 returncode | 无代码风险；补产物即过 |
| 断言计数漂移（缺输入导致池规模变小，`assert 267 == 281`） | ~10% | 与上同根因 | 同上 |
| **真实代码漂移** | 1 处 | `test_dashboard_release_scripts`：`eltdx==3.1.3` 在 `pyproject.toml` 声明但缺于 `deploy/dashboard-api-requirements.{in,lock}` | 部署时 dashboard 缺依赖——**已记录，本轮不修**（范围外） |
| 测试基建（断言漂移 + 心跳挂起） | platform_ready 系列 | 见 P0c | 已修 14/14 |

### P0c 心跳挂起根因与修复

**根因**：`scripts/run_platform_ready_build_cron.sh`（及同型
`run_platform_ready_check_cron.sh`）的 `run_step`/心跳循环以
`kill -0 "$pid"` 判活。已退出但未被 wait 的子进程是僵尸，`kill -0`
对僵尸恒真 → 循环永不退出（实测 `platform_ready_build` 子进程退出后
空转 12+ 分钟，CPU 0%）。

**修复（仅测试范围验证过的脚本缺陷，未动生产调度）**：循环内加入
`pipeline_process_alive` 检查——`ps` 探测 pid 的 `stat`（排除 `Z`
僵尸态）与 `ppid==$$`（排除 PID 复用的外来进程）。未修复代码在
`test_platform_ready_scripts.py` 上实测挂起 6 分钟（kill 后判失败），
修复后 14/14 通过，3.5s 完成。同文件 4 条既存断言漂移（`日志:` vs
`详细日志:` 前缀，源自 `4d7f6aa8` 的 Feishu 摘要压缩 + 输出路径
`eod_auto_repair/2026-06-29`）一并更正为生产文本。

## P1 — 研究缺口清单

`capabilities/research_gaps.py`：`build_gap_inventory(per_node,
cap03_findings, theme_id, as_of)` 按 公司×主题×节点×维度 发缺口行，
`gap_id` = 内容哈希（重跑稳定）。八类全覆盖：

| category | 来源 | ai_power | humanoid | semi |
|---|---|---|---|---|
| searched_not_found | 状态 ∈ {missing, none_seen, unknown, undisclosed, no_major_contract_disclosure, claims_only} | 68 | 6 | 14 |
| not_searched | 公司无任何 dossier/记录（searched_anything=False） | 0 | 0 | 0 |
| out_of_node_scope | 状态=out_of_node_scope / trace 标 OOS | 3 | 3 | 2 |
| insufficient_granularity | 状态 ∈ {disclosed_broader_scope, *_at_industry_board, validated_unspecified_customer} | 4 | 3 | 4 |
| pending_review | 状态=pending_review / 假设 risk_flagged | 1 | 2 | 1 |
| contradictory_evidence | 假设 contested（合格正反并存） | 0 | 0 | 0 |
| stale_evidence | trace 有记录但最新证据 ≥2 年 | 0 | 0 | 0 |
| out_of_pit | 状态=out_of_pit | 0 | 0 | 0 |

每行 `basis` 携带可追溯引用（record_id/evidence_id/状态值），非模型
文字认定。维度：product_certification / ecosystem_participation /
customer_validation / commercial_delivery / revenue_attribution /
profitability / order_evidence / cash_realization /
theme_application_attribution / stage trace / hypothesis:<id> /
node_case。

## P2 — 可解释优先级

`score_gap_priority`：五个分项（conclusion_impact / bottleneck_impact /
evidence_availability / timeliness_need / dedup_cost）→
band ∈ {high, medium, low} + 自然语言 `reason`。分项规则全部确定性
（维度权重 × 节点 decisive/head 标记 × 闭合证据是否存在 × 缺口类别），
无黑箱分数，且 `reason` 明示不构成投资吸引力/交易信号。
实测分布：ai_power 53 low / 22 medium；高优先级集中于
customer_validation、commercial_delivery、revenue_attribution 维度。

## P3 — 三案例竞争假设

`COMPETING_HYPOTHESES.json`：每案 H_broad（宽口径：公司事实直接支撑
主题结论）vs H_narrow（窄口径：事实仅在公司既有口径成立），各带
supporting / counter / pending 证据与 decisive_verification。

- **688686@humanoid_vision_sensing**：`narrow_supported`。支持宽读的仅
  `seg_688686_mv_2025FY`（机器视觉产品线整体），反证含
  theme_application_attribution=unknown + delivery/cert 全未决。
  决定性验证：人形场景级收入或具名客户验证记录。
- **603757@liquid_cooling_pump_components**：`narrow_supported`。组件
  交付（mass_delivery/verified_delivered）真实，但 customer_validation
  仅 contact 级、无 CDU 系统级认证记录。决定性验证：CDU 系统级
  validated 记录或具名客户验收。
- **002837@liquid_cooling_cdu_system**：`narrow_supported`。生态参与
  out_of_node_scope、commercial_delivery=none_seen、revenue missing——
  验证≠交付未被证据闭合。决定性验证：产品线范围交付/验收记录。

## P4 — 验证任务闭环

- 任务全字段：`task_id`（vt-<sha1[:10]> 稳定哈希）、`research_gap_id`/
  `research_gap_ids`、`related_node_ids`、`required_evidence`、
  `suggested_sources`、`completion_criteria`、`priority_reason`、
  `verification_status`、`last_material_change`。
- **三主题任务→缺口挂接率 100%**（31/31、10/10、14/14），高优先级
  任务全部可追溯。
- `capabilities/task_ledger.py`：按主题落
  `outputs/research/cap_workbench/<theme>/verification_ledger.json`，
  append-only 历史：
  - 同一 task_id 重复采集 = no-op（单条 history）；
  - 任务不再被生成 → `resolved`（缺口关闭），历史追加；
  - material 反证（`direction=counter` 或 material 的
    `same_source_new_fact`）触及任务节点 → `reopened` +
    `last_material_change`；
  - 任何刷新不静默覆盖判定。
- 重跑验证：semi_equipment 连跑两次，14 task_id / 21 gap_id 逐一致。

## P5 — 三主题验收指标核对

| 指标 | 结果 |
|---|---|
| confirmed 阶段来源可解析 | 9/9 resolved，0 gate_breach |
| 高优先级任务→缺口可追溯 | 12/12（全部任务 55/55） |
| 重排/重跑任务身份稳定 | task_ids/gap_ids 逐一致 |
| 同源重复采集无虚假变化 | R2B.1 `duplicate_ingestion→non_substantive` 契约保持 |
| 同源新反证触发重评估 | ledger `reopened` 单测 + material same_source_new_fact 通道 |
| CAP-01/02 判断不变 | 三主题 findings 逐字节相同 |
| 无新信号/生产写入 | `research_only=true, used_for_signal=false, used_for_admission=false`；CAP-10 隔离契约测试保持绿 |

## 文件

- `RESEARCH_GAP_INVENTORY.csv` — 111 条缺口全量（含分项评分）
- `EVIDENCE_PRIORITY_EXPLANATION.csv` — high/medium 缺口评分明细
- `COMPETING_HYPOTHESES.json` — 3 案例×2 假设
- `VERIFICATION_TASK_CLOSURE.json` — 任务字段+各主题 ledger 状态+语义
- `SEMANTIC_DIFF.md` / `REGRESSION_DIFF.md`
- `r2c_{theme}.json` — 三主题全量链输出
