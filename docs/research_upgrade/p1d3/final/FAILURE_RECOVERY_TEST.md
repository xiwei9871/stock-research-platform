# P1d.3 — 批次失败恢复演练（真实 DB 异常注入）

脚本 `scripts/p1d3_failure_recovery_test.py`；结果 `FAILURE_RECOVERY.json` —— **pass=true**

## 演练设计

对 `drill_recovery_2024h1`（2024-06-03~07，25,189 行）在批内注入真实 `UndefinedTable` SQL 异常（执行 `SELECT * FROM __no_such_table__` 中止事务）。

## 断言与结果

| 断言 | 结果 |
|---|---|
| 异常后连接立即可用（`conn.rollback()` 先于拆分） | ✅ |
| 父批记录 `failed_split` + 错误文本 | ✅ |
| 自动拆分为 `_a`(10,074) / `_b`(15,115) 并各自 done | ✅ |
| 重算结果 vs 影子参考 checksum 完全一致 | ✅ |
| 再次进入整批 → **0 次 emit 调用**（committed 子批不重算） | ✅ |
| resume 全部 `skipped_done` | ✅ |
| 跨进程恢复基础：checkpoint 全部落在 `migration_log` 表，任何新进程仅凭表即可续跑 | ✅（结构性） |

## 修复要点（相对上一版）

1. `running` 标记独立 commit —— 崩溃后其他进程立即可见真实状态；
2. 异常 → `conn.rollback()` 撤销中止事务 → 记 `failed_split` → 再二分；
3. `migration_log` 增 `range_start/range_end/error` 列（`ALTER ... IF NOT EXISTS` 兼容旧表）；
4. 进入批前先查 done 子批 → 有则直接下钻，绝不整体重算；
5. `emit_v2_flags` 改为**纯 UPDATE**（Postgres 在冲突仲裁前先校验 proposed row NOT NULL——生产形态表上 INSERT..ON CONFLICT 必炸，本次演练实测复现并修复）。
