# P1d.3 — 生产变更审批矩阵（默认全部 DENIED）

| 动作 | 类型 | 生产影响 | 可回滚性 | 启动条件 | 需独立授权 | 预演证据 |
|---|---|---|---|---|---|---|
| A. additive DDL | schema 变更 | 元数据级，秒级，不触行 | 秒级 DROP COLUMN | 授权#1 + 低峰窗口 + 备份确认 | ✅ 是 | prod_replica 同 DDL 已跑通 |
| B. V2 EOD 增量写入 | EOD 序列扩展 | +5k 行/日 UPDATE | 移除 emit 调用即可 | A 完成 + 授权#2 | ✅ 是 | emit 守卫 + EOD/回填交叉演练 |
| C. 历史回填 | 17.29M 行 UPDATE | ~20min、~4-5GB WAL、行锁 | 列级 UPDATE 清零（已验证 checksum 复原） | B 稳定 + 授权#3 + WAL 余量 | ✅ 是 | 影子全量 + prod_replica 122万行实测 |
| D. 消费者灰度 | 代码 config 切换 | 无写路径 | `qualification_mode` 改回 | C 校验 + 授权#4 | ✅ 是 | 4 窗口灰度门禁全过 |
| E. 重新验收 | 研究产物层 | 无运行时改动 | 不发布即回滚 | D 稳定 1 周 + 授权#5 | ✅ 是 | shadow 对照方法论既有 |

## 当前状态

| 项 | 状态 |
|---|---|
| A–E 全部 | **未授权 — 均未执行** |
| 生产表写次数（本轮） | **0** |
| 隔离资产 | `p1d3_shadow.asset_status_daily_v2`（17.29M 完整副本可复用为回填比对源）、`migration_log`、`prod_replica`（演练后可 DROP） |
| 阻塞项 | 无技术阻塞；纯审批决策 |

## 审批清单建议（每步签署）

1. DDL 窗口与备份确认；
2. EOD 接线 commit 上 main 的代码评审；
3. 回填窗口、WAL 余量与中断预案签字；
4. 每个消费者的切换顺序与回归负责人；
5. NEEDS_REVALIDATION 清单的重验收口径。
