# M1-C 财务版本事件层设计（隔离实现）

实现：`financial_version_store.py`；DDL：`fvs.ddl(schema)`（隔离执行于 `m1_shadow`）；演练：`scripts/m1_finver_drills.py` → `FINANCIAL_VERSION_TESTS.json`。

## Schema

`finver_event`（append-only）：
version_event_id PK · asset_id · statement_type · endpoint · report_period · report_type · **metric_fingerprint**(规范化指标 sha256/32) · metrics jsonb · announcement_date + **announcement_evidence** · raw_payload_id + raw_payload_hash · **first_seen_at / last_seen_at** · **version_seq** · **supersedes_event_id** · **change_class** · UNIQUE(asset,st,ep,period,type,fingerprint)

`finver_key_chain`：键 → n_versions + latest_event_id（读路径 O(1)）。

## 写入规则（任务书逐条）

| 场景 | 实现 |
|---|---|
| 同键同指纹重抓 | `identical_bump`（仅刷 last_seen_at），不产版本 |
| 仅元数据变化 | fingerprint 不含元字段 → 同指纹 → bump |
| 精度容差内 | `_norm` round4 归一 → 同指纹；字段级另标 precision_only |
| 数值变化 | 新 event，version_seq+1，supersedes 链接 |
| NULL↔值 | null_asymmetry 版本事件（保留，不判死） |
| 来源不同 | endpoint 入键，互不覆盖 |
| 公告日缺失 | announcement_evidence='unknown'，不倒推 |
| 缺失初版 | 仅存"幸存版本"，evidence 不标 verified |

**区分**：供应商数值变化（change_class）≠ 公司正式更正公告（需外部公告证据另行登记）。

## 演练（FINANCIAL_VERSION_TESTS.json all_pass）

- D1：重放 raw_akshare 中 6 个多 hash 资产 → **4 条真实多版本链复现**（228 events / 223 keys）；
- D2：重放同快照 → 0 新增（幂等）；
- D3：合成指标变化 → version_seq 2；
- D4：元数据变化 → 不产版本；
- D5：as_of 介于两快照间 → 读 v1，之后 → v2；
- D6：无公告日 → evidence=unknown，不伪造日期。

## 读接口

- `latest(conn, schema, key)` → key_chain 直读；
- `read_as_of(conn, schema, key, as_of)` → first_seen_at<=as_of 的最新 version_seq（平台观测语义，非市场首发）。

## 生产接入（M2）

ingestion 在现有 raw payload append 之后同步调 `ingest_payload`（同事务）；历史回放仅对 raw_* 表执行，三表不动。
