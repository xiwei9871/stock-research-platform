# 平台架构审计 V0.2（脱敏版）

状态：`ARCHITECTURE_AUDIT_V02_COMPLETE / AWAITING_DESIGN_REVIEW / NO_PRODUCTION_CHANGES`

| 文件 | 内容 |
|---|---|
| `ARCHITECTURE_CURRENT_STATE_V02.md` | 对此前判断的更正、系统边界、能力地图、整体架构 Mermaid 图 |
| `DATA_ARCHITECTURE_REVIEW_V02.md` | schema 体量与数据角色、factor_daily 四种存储方案对比、数据生命周期、PIT、DuckDB 适用条件、多市场数据契约 |
| `RUNTIME_ARTIFACT_REVIEW_V02.md` | 已有运行能力清点、诊断困难的原因、最小改造 R1–R5、Research Lead 方案对比、10-29 全链路审计 |
| `UIUX_WORKFLOW_REVIEW_V02.md` | 导航、页面到数据的映射、一次个股研究的完整路径、可信度表达、目标信息架构 |
| `ARCHITECTURE_DECISION_PROPOSAL_V02.md` | 六个问题的回答、方案对比、演进路径、待用户决策事项 |
| `DESIGN_REVIEW_AMENDMENT_V02.md` | 针对 PR #19 评审意见的修正：执行尝试身份、通知投递记录、研究线索的真实数据源、财务 PIT 差异审计、provenance 维度拆分、第一阶段最小闭环 |
| `PRIORITY_MATRIX_V02.csv` | 26 项问题的优先级 |

原始证据（数据库统计、调度记录、主机信息）保存在内部受控目录，不进入仓库。
