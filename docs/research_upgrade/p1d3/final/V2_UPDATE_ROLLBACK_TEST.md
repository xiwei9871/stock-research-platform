# P1d.3 — 生产形态 V2 UPDATE 与列级回滚演练

副本表 `p1d3_shadow.prod_replica`（`LIKE core.asset_status_daily INCLUDING ALL` + 2024 全年 1,221,332 行拷贝 + 同形态 5 列 additive DDL）。结果 `V2_UPDATE_ROLLBACK.json` —— **all_pass=true**

## 月度批次实测（UPDATE ... FROM shadow）

| 指标 | 实测 |
|---|---|
| 批次数 | 12（月度） |
| 更新总行数 | 1,221,332 |
| 单批 rows | 75k–116k |
| 单批耗时 | 0.7–1.5s（合计 ~12.8s） |
| 单批 WAL | 16–42MB（合计 ~291MB → 全表 17.29M 外推 ~4.1GB） |
| 锁 | `RowExclusiveLock`（持表行锁，不阻塞读写） |

## 断言

| 断言 | 结果 |
|---|---|
| `statement_timeout=50ms` 注入 QueryCanceled → 中止后 0 行残留 | ✅ |
| 12/12 批回填完成（v2_rows == 副本行数） | ✅ |
| v1 列 checksum 全程不变（UPDATE/回滚前后 3 次校验） | ✅ |
| 列级回滚（v2 列置 NULL）→ checksum 回到更新前镜像 | ✅ |
| EOD emit（2024-07-01 当日）先于月批回填执行 → 全日单一 `pit_rules_v1` 版本、与影子值 0 mismatch | ✅ |

## 生产映射结论

- **WAL**：全表回填预计 ~4–5GB WAL——执行前必须确认归档/复制余量（写入 runbook C 预检查）；
- **锁**：仅 `RowExclusiveLock`，与 EOD INSERT（不同键）兼容；仍建议避开 EOD 窗口；
- **中断**：批次级全有或全无（0 部分提交已验证），`--resume` 续跑；
- **回滚**：列级 UPDATE 置 NULL，实测 12.8s 级、checksum 归零、v1 无损；
- **emit 形态**：纯 UPDATE——生产表 NOT NULL v1 列使 INSERT..ON CONFLICT 不可行（仲裁前先校验 proposed row），该坑已在副本上复现并排除。
