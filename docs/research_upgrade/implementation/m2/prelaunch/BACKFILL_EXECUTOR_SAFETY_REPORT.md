# P0-B 回填执行器安全边界修复报告 — `scripts/m2_t_backfill.py`

## B1 目标识别（修复前：`--dsn` 完全绕过 `--allow-prod`）

| 机制 | 实现 |
|---|---|
| 身份核验 | 连接后从 `conn.info`（host/port/dbname）分类，**不依赖任何命令行标志** |
| 分类 | `prod`（192.168.3.187:5432/stock_research）/ `test`（localhost + 库名含 test）/ `unknown` |
| unknown | 写模式一律 `refused`——任意本地 DSN 不能冒充测试库 |
| prod | 需 `--allow-prod` **且** `--prod-confirm "192.168.3.187:5432:stock_research"`（手打身份=双重许可）；prod 目标表仅限 `core.asset_status_daily` |
| 表范围 | 正则 `^<schema>.asset_status*` + v2 契约列检查 |
| 默认模式 | `--mode dry-run`（全流程真实执行、最终整体回滚） |

## B2 checkpoint DDL 分离

- 自动建表已删除；`ops_m2.v2_backfill_checkpoint` 必须由独立评审 SQL（`sql/ops_m2_checkpoint_schema.sql`）先行部署；
- 缺失/列不符 → `blocked`；checkpoint 存独立 `ops_m2` schema，不在业务 schema 偷建对象；
- 字段：target/trade_date/flags_version/status/row_count/checksum/run_id/started_at/finished_at。

## B3 全量对账（修复前：只看 checkpoint status）

- 计划 = 目标表实际交易日全集 ∩ 区间；`pending`(无ckpt)+`retry_running`+`wrong_version` 全部入列；
- 完成后审计：逐日比对 checkpoint(done+同版本) **与** 实际 v2 覆盖数（`covered_n<base_n` → `data_incomplete`）；
- `coverage_ok` 仅当应处理集合**全部**核销且数据一致——ckpt 标 done 但数据被清的案例实测被捕获（A12）。

## B4 停止与水位

- `--stop-file`（文件存在即于下一批次前停）+ SIGTERM/SIGINT（主线程）；当前批次完成后退出，`stopped` 态幂等续跑；
- `--max-wal-mb`：每批次实测 `pg_ls_waldir` 增量超限即 blocked；
- 磁盘：本地目标 `df(data_directory)` 实测 `<min_free_mb` 阻断；**远端宿主磁盘不可测时写模式默认拒绝**（测试实例可显式 `--disk-unmeasurable-ack`，生产不可豁免）。

## 对抗验收（BACKFILL_ADVERSARIAL_TESTS.json，stock_m2_test）

**15/15 全过**：DSN 绕过拒绝、非测试库拒绝、越界表拒绝、prod 双重许可（mock 身份）、prod dry-run 免许可、ckpt 缺失阻断、错版本返工、漏登记检出、kill→续跑、崩溃回滚不留脏写、重复跑零批次、stop-file 阻断+续跑、磁盘水位阻断、ckpt-data 不一致检出。
