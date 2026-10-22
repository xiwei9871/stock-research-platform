# CAP-00 平台能力架构与路线图 V1

日期：2026-10-22 ｜ 状态：R0 骨架已落地 ｜ research_only，未部署，不进入信号/准入

## 一、现有能力盘点（只读审计）

| 已有模块 | 对应 CAP | 状态 |
|---|---|---|
| `company_intelligence` / `_feed` / `_report` + dashboard 面板 | CAP-01 公司研究 | **冻结**（六维 dossier，已验收） |
| `chain_bottleneck` + `chain_value_matrix` + `chain_t3_evidence` | CAP-02 节点研究 | **冻结**（节点判定/矩阵/T3 证据） |
| `theme_decomposition` + `theme_company_mapping` + node case 目录 | CAP-03 主题编排 | **部分已有** — 拆解/映射在，编排信封新增 |
| dossier claim_role 五维聚合 | CAP-04 技术与供需 | **R0 适配层**（无新判定） |
| `chain_value_matrix` rev/ord/valdel 三格 | CAP-05 产业经济 | **R0 适配层**（margin 无矩阵列→如实 unknown） |
| 矩阵行 + CAP-01 dossier 维度 verdict | CAP-06 竞争比较 | **R0 适配层** |
| dossier/envelope 指纹链 | CAP-07 动态跟踪 | **R0**：无基线 → unknown + gap，不做模拟 diff |
| 聚合上游信封 | CAP-08 综合研判 | **R0**：支持/不确定性/缺口/优先级 |
| dashboard api / review workflow / research_queue_* | CAP-09 工作台 | **指针信封**（不重建 UI） |
| backtest / factor_eval / strategy_* / performance_* | CAP-10 策略验证 | **隔离指针**（`not_evaluated`，不接信号） |

## 二、统一研究契约（`capabilities/contract.py`）

所有 CAP 输出 `ResearchEnvelope`：

```
capability_id, subject_type, subject_id, as_of, run_id, status,
findings, evidence_refs, uncertainties, data_gaps,
fingerprint, rule_version, upstream_fingerprints,
research_only=True, used_for_signal=False, used_for_admission=False
```

- `status`：`ok | partial | unknown | not_evaluated`
- `data_gaps.kind`（统一 DATA 线词汇）：
  `missing_source`（缺整个源）/ `unparsed`（源有未解析）/ `pending_review`（已解析待核验）/ `attribution_unknown`（已核验归属不明）/ `truly_undisclosed`（企业确实未披露）/ `pit_incompatible`（历史 PIT 不可用）
- `fingerprint`：sha256(canonical fields + upstream_fingerprints) — 上游变更必然传导指纹
- 退化原则：无数据 → `unknown`/`not_evaluated` + gap 条目，**绝不产出模拟正面结论**

## 三、能力依赖图

```
CAP-03 ─→ CAP-02 + CAP-01（编排消费冻结引擎）
CAP-04 ─→ CAP-02（dossier claim_role 视图）
CAP-05 ─→ CAP-04, CAP-02, CAP-01（矩阵格状态）
CAP-06 ─→ CAP-05, CAP-02（同业比较）
CAP-07 ─→ CAP-04/05/06（指纹 diff）
CAP-08 ─→ CAP-03..07（综合研判）
CAP-09 ─→ CAP-08（浏览/复核入口）
CAP-10 ─→ ∅（与研究线隔离，仅复用策略基础设施）
```

## 四、R0 骨架落点

| 文件 | 内容 |
|---|---|
| `src/stock_research/capabilities/contract.py` | ResearchEnvelope + DataGap + 指纹 |
| `src/stock_research/capabilities/registry.py` | CAP-00..10 描述符 + 依赖图 |
| `src/stock_research/capabilities/adapters.py` | CAP-03..10 瘦适配器（复用冻结引擎） |
| `src/stock_research/capabilities/pipeline.py` | `run_research_chain` 端到端 + gap backlog |
| `cli.py cap-chain-smoke` | 可复现命令入口 |
| `tests/test_capabilities.py` | 11 契约测试 |
| `docs/capabilities/r0_smoke_liquid_cooling.json` | 液冷三子节点 smoke 快照 |

## 五、端到端 smoke 结果（液冷三子节点）

```
cap-chain-smoke --theme liquid_cooling --cases <3 子节点> --as-of 2026-10-22
```

- CAP-03 `ok`：3 节点 / 5 个公司研究任务
- 每节点 CAP-04..08 全部产出信封；节点 verdict 与 dossier 一致 `bottleneck_unverified`
- CAP-05 语义：`revenue_state=missing`（子节点 product_line 口径下无收入记录，**隔离正确**——母公司板块收入不窜入子线）；603757 `delivery=mass_delivery / order=verified_delivered`，`value_capture=not_evaluated`（无收入披露→不冒充 verified）
- CAP-07 全 `unknown`（无基线指纹 — R0 如实退化，不模拟）
- `gap_backlog` 34 条，全部 `missing_source`：product_revenue / product_gross_margin / verifiable_order per company + baseline_fingerprint×3

## 六、DATA 线并行清单（由 backlog 自动生成）

| 类别 | 条目 | 归属 |
|---|---|---|
| missing_source | `product_revenue:*`（各公司分产品收入） | DATA |
| missing_source | `product_gross_margin:*`（矩阵无毛利列） | DATA + CAP-05 R1 |
| missing_source | `verifiable_order:*`（无已验证订单格） | DATA |
| missing_source | `baseline_fingerprint:*`×3（CAP-07 基线） | CAP-07 R1（保存首 run 指纹即关闭） |

**未阻塞项**：所有 CAP 在 gap 下仍产出信封——DATA 补录后重跑 `cap-chain-smoke` 即可自动收敛，无需改代码。

## 七、R1 联调验收条件（下一阶段）

1. 三主题（AI 供电 / 半导体设备 / 人形机器人）各跑通同一链路；
2. CAP-07 保存首轮指纹基线 → diff 有实际意义；
3. CAP-05 `margin_state` 接入真实分产品毛利列；
4. CAP-09 统一入口可在 dashboard 打开任一信封；
5. 接口断裂 / 重复归因 / 语义不一致问题清零（比数据完整优先）。

## 八、边界

- research_only：`used_for_signal=False` / `used_for_admission=False` 全链路透传；
- 不重建已稳定基础设施（CAP-01/02 引擎、dashboard、StrategyLab 全部复用）；
- 未部署生产；未改动任何调度/同步/EOD 路径。
