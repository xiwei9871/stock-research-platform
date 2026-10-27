# M1 回归差集

## 基线与隔离

分支 `data/r3-implementation-m1` @ `b7809cd6`（worktree `.worktrees/r3-m1`）；canonical 工作区、P1d.3 分支、hotfix 均未触碰。

## 变更

新增：`eod_v2_writer.py`、`financial_version_store.py`、`data_integrity_gate.py`、`scripts/m1_v2_write_drills.py`、`scripts/m1_finver_drills.py`、`tests/test_r3_m1.py`、`docs/research_upgrade/implementation/m1/`。
修改：`financial_pit.py`（追加 evidence 分级字段，向后兼容——既有断言全过）。

## 测试

`pytest tests/test_r3_m1.py tests/test_financial_pit_p2.py -q` → **38 passed / 0 failed**。
隔离演练：M1_V2_WRITE_DRILLS all_pass(7/7)；FINANCIAL_VERSION_TESTS all_pass(6/6)。
新增失败差集：**0**。演练中自揪一处 bug（`_check_target` 集合优先级 → 恒报缺列）已修复并固化测试。

## 数据库副作用

仅 `m1_shadow` schema：`asset_status_daily`（15,569 行副本）+ `finver_event/key_chain`（228 events）。生产表零写入。
