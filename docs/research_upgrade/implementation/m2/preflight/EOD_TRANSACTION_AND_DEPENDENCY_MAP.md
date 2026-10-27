# M2-0-A1/A2 — 真实调用链与事务边界核查（读源码+只读验证）

## EOD 链路（生产实际）

```
LaunchAgent com.stockresearch.strategy-eod-publish (20:30)
  └─ scripts/run_strategy_daily_eod_cron.sh (ROOT=canonical main)
       ├─ wait_for_daily_pipeline_status()
       │    └─ check_strategy_daily_eod_dependencies()  ← hotfix wait-gate
       │         读 ops.daily_pipeline_status (daily/deps/minute5_status)
       │         + factor.stock_score_daily (score_version='manual_v1')
       │         rc: 0=ready / 3=waitable / 4=real-failure
       └─ python -m stock_research.cli run-strategy-daily-eod
            └─ run_strategy_daily_eod() → _run_strategy_daily_eod_once()
                 └─ commit_strategy_publication() → connect() 独立事务
```

**`core.asset_status_daily` 的构建是另一条链**（上游 pipeline，非本 cron）：
`daily_incremental._build_asset_status_step` / `daily_close_pipeline` →
`build_asset_status_daily_for_service` → **自己的 `connect(service)` 事务**
（build + quality assert + commit）。

### 关键结论（如实记录）

- 基础状态构建与策略发布**天然是两个事务、两个任务**；V2 emit 不存在"天然同事务"。
- **V2 接入点**：独立阶段 `run_eod_v2_stage(service, trade_date, …)`（新增于 eod_v2_writer.py）——自己的事务，只在 `written`/`idempotent` 时 commit，`blocked`/`incomplete` 显式 rollback。
- 接入方式（T3 时执行）：在 `daily_incremental` 的 `_build_asset_status_step` 之后追加一个 V2 step，或在 EOD cron 的 wait-gate 后追加 V2 段。**推荐前者**（贴近基础状态提交点，失败可重跑且不影响策略发布）。
- frontier 规则：`res["committed"]==True` 才允许推进 V2 水位；V2 失败不得被 V1 成功状态掩盖——V2 stage 的 res.status 应写入 EOD 状态表（部署时接线，本轮未动）。
- 现有 wait-gate 只检查 `ops.daily_pipeline_status` + score_daily；**V2 不加入 wait-gate 的可等条件**（否则 V2 故障会让 EOD 空等）。

## 财务抓取链路（生产实际）

三个 raw-写入入口，**raw payload 与规范化 UPSERT 已在同一事务内**：

| 入口 | 载荷 | 事务 |
|---|---|---|
| `sync_em_profit_sheet_for_asset`（gap 抓取主链） | 1× income EM | `connect` 单事务：store_finance_payload + upsert_income |
| `sync_finance_statements_for_asset` | 2× balance+cash EM | 同事务：2 payload + 2 upsert |
| `sync_sina_finance_statements_for_asset` | 2× balance+cash Sina | 同事务 |
| `sync_finance_for_period`（baostock） | **无 raw 保存** | flush 每批 connect() 事务 |

- `store_raw_payload` INSERT 无 RETURNING（目前只返回 hash）——finver 需要 raw_payload_id；新增 `financial_ingest_integration.store_finance_payload_and_version`（RETURNING id, fetched_at）解决。
- **finver 接入点**：在上述三个函数的事务体内，raw INSERT 后调 `fvs.ingest_payload`——天然满足 `raw → event → observation → chain` 原子性（已在 F5/F6 演练证明：任一步失败整体回滚，raw 不会孤儿存在）。
- baostock 链路无 raw → finver 无证据来源 → `unknown_source` 覆盖缺口如实记录，F4 回放只覆盖 akshare。
- 多入口重复抓取：gap 主链 + statements 链同写不同 endpoint，键空间以 endpoint 隔离，无覆盖冲突。

## 独立测试实例（E4 判定）

本地 PG16 `stock_m2_test`（127.0.0.1，与生产 192.168.3.187 不同实例）——
全部写入演练在此执行；m1_shadow 位于生产库内，本轮未向其写。
