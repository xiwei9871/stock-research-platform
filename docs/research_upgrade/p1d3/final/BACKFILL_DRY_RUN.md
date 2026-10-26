# P1d.3 — 历史回填 Dry-Run（隔离环境，生产零写入）

证据：`p1d3_shadow.asset_status_daily_v2`（17.29M 全量）、`prod_replica`（122 万行生产形态）、`MIGRATION_REHEARSAL.json`、`V2_UPDATE_ROLLBACK.json`。

## 分批方案（实测）

- **顺序**：自然年 37 批（1990→2026），每批独立事务 commit；`migration_log` 记录 batch_id/range/status/rows/seconds/error → `--resume` 跨进程续跑；
- **单批事务**：v1 列拷贝 + v2 emit（纯 UPDATE）+ stats + log 更新，一批一事务；最大批 2025 年 ~125 万行 / ~73s；
- **失败恢复**：异常 → rollback → `failed_split` → 数据日期中点二分递归（深度上限 6）；已 done 子批永不重算（真实异常注入验证）；
- **幂等**：同批重跑 checksum 一致；
- **吞吐**：~19,189 行/s 端到端（重算+写），全量 901s ≈ 15 分钟。

## 资源成本（prod_replica 实测 → 全量外推）

| 项 | 月批实测 | 全量外推 |
|---|---|---|
| UPDATE 耗时 | 0.7–1.5s / 7.5–11.6 万行 | ~15–20 分钟 |
| WAL | 16–42MB/批 | **~4–5GB**（执行前查归档/复制余量） |
| 锁 | RowExclusiveLock（不阻塞读写） | 同左 |
| DSM | 年批 join 曾触发 DiskFull → `max_parallel_workers_per_gather=0` + 二分已化解 | 同左 |
| 影子表磁盘 | — | ~1.2GB（可复用为回填比对源） |

## 新旧差异（每批 diff_rows 已入 JSON）

全表 v1≠v2 行级差异 **84,844**；分类（`FULL_DIFF_CLASSIFICATION.csv`）：v1 确认误标 76,031、data_insufficient 8,191、v1 NULL→v2 确认 617、rule_unknown 5、other 0。

## 无法自动修复（保留 UNKNOWN，不强行填补）

- `rule_unknown`（5 行）：1990-12-19 沪市首日的异常 ST 状态行——ST 制度 1998 年才存在，规则表无覆盖 → 保留 `rule_unknown`；
- `data_insufficient`（387,314 行）：raw bar close/preclose 缺失 → 保留 state=3，读路 fail-closed；
- 北交所 ST 规则未获官方文本核实 → 相关键同样走 rule_unknown 路径。

## 校验摘要（对账）

迁移完成后按批执行：`count(*)=原表`、`limit_state_v2` 分布对账、`md5(asset_id||date||v2 cols)` 与影子表比对（演练已建 checksum 函数）。

## 回滚

列级 `UPDATE ... SET v2列=NULL WHERE 批范围`——实测 checksum 归零、v1 checksum 全程不变、~13s/122 万行。
