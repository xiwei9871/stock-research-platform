# M1-A 工程基线与集成地图（只读核验，2026-10-27）

## 分支/提交关系

| 引用 | SHA | 状态 |
|---|---|---|
| origin/main | `9bd95562` | = PR#12 已合并 P2 审计分支 `23ad1d40`；**P2.1 修正（b7809cd6）未合并** |
| 本分支 M1 | `data/r3-implementation-m1` @ `b7809cd6` | 含 P2.1 修正接口 + P1d.3 emit 引擎（经 `9cd9e2c1` hotfix 链） |
| P1d.3 迁移 | `data/p1d3-v2-migration` @ `3ef96602` | 独立，未动 |
| hotfix 链 | `34de8b0d`/`9cd9e2c1` | 已在 M1 基线历史中（经 `425041b5`→`23ad1d40`→`b7809cd6`） |

## 能力 → 代码来源

| 能力 | 位置 | 部署依赖 |
|---|---|---|
| V2 flag 计算 | `tradeability.compute_pit_limit_flags` | 无外部依赖，读行情+规则表 |
| V2 UPDATE emit | `core_data.emit_v2_flags`（纯 UPDATE，契约自守） | 需目标表有 5 个 v2 列（生产未加） |
| EOD 状态构建 | `core_data.build_asset_status_daily` | 生产 EOD 调度调用，本轮未改 |
| 财务 PIT 接口 | `financial_pit.financial_pit_at`（P2.1 修正版） | 新模块，无生产调用方 |
| Raw payload 留存 | `raw_akshare.finance_payload`（ingestion 已写入） | 16,586 行；baostock 表空 |
| EOD wait-gate | `9cd9e2c1` hotfix | 生产在用，未触碰 |
| **M1-B gate** | `eod_v2_writer.emit_eod_v2_flags`（新） | 纯封装 emit_v2_flags，默认 OFF |
| **M1-C 版本层** | `financial_version_store` + `m1_shadow.finver_*` | 独立事件层，生产三表零改动 |
| **M1-E gate** | `data_integrity_gate` | 只读检查 |

## 生产调用链核验（未改）

EOD：调度 → `build_asset_status_daily`（v1 写）→ 下游因子/评分。财务：akshare/baostock ingestion → 三表 UPSERT + raw payload append。**本轮两条链均未改动。**

## 既有隔离资产

`p1d1_shadow`、`p1d3_shadow`（17.29M 影子表保留）、`m1_shadow`（本轮：asset_status_daily 3 日副本 + finver_event/key_chain）。
