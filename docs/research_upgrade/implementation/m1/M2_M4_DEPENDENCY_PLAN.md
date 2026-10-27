# M2–M4 依赖计划（仅规划，不执行）

## M2 可信数据层部署（需独立审批，两条迁移分开授权）

| 序 | 动作 | 依赖 | 回滚 |
|---|---|---|---|
| M2-T1 | `core.asset_status_daily` additive 加 5 v2 列 | P1d.3 APPROVAL_MATRIX A 步 | DROP COLUMN |
| M2-T2 | EOD 接入 `emit_eod_v2_flags(enabled=True)` | T1 + 本模块 | 关 enabled |
| M2-T3 | 历史回填（37 批方案已定） | T1+T2 | 按批 DELETE |
| M2-F1 | `finver` schema 生产部署 | 本 DDL | DROP SCHEMA |
| M2-F2 | ingestion 同事务调 `ingest_payload` | F1 | 摘线 |
| M2-F3 | raw_* 历史回放（分批） | F1 | 事件表可重建 |
| M2-F4 | 初版证据分级落地（VERIFIED 仅 finver 可证版本） | F3 | — |

## M3 消费者对照（M2 之后）

四模式矩阵 LEGACY / TRADE_CORRECTED / FINANCE_CORRECTED / FULL_CORRECTED（固定股票池/参数/成本/环境）；接入顺序：point_in_time_finance → finance_ttm → fundamental_pipeline → midtrend → TopN/retention loader。差异归因按域分离。

## M4 研究再认证

结果状态 RESEARCH_VALIDATED / NEEDS_REVALIDATION / LEGACY_REFERENCE / BLOCKED；新结果须可追溯 数据版本×规则版本×策略版本×commit×运行证据；旧报告不覆盖。

## M1 → M2 准入清单（本次交付即审批材料）

- ✅ v2 emit 安全门隔离演练 all_pass；
- ✅ finver append-only 演练 all_pass（真实多版本链复现）；
- ✅ PIT 证据分级接口；
- ✅ Integrity gate + combine 语义；
- 待批生产动作：T1/F1 DDL、T2/F2 接线、T3/F3 回放。
