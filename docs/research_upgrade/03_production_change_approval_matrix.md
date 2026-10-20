# 03 — Production Change Approval Matrix (M0.7)

Date: 2026-10-20. 每项列出：变更、影响范围、前置条件、回滚、验收。
**本轮全部待批准；隔离开发/Shadow/只读验证已获授权。**

| # | 变更 | 影响范围 | 前置条件 | 回滚 | 验收标准 | 状态 |
|---|---|---|---|---|---|---|
| 1 | **Regime+fail-closed 受控发布**（情绪每日重建+regime每日更新+精确日校验） | tech_bottleneck EOD、serenity 回放 | staging 差异报告稳定 N 日；失败演练通过；差异行分类人工审批 | `latest` 指针回切 + DB 版本分区恢复 | 次日出现新 regime 行；回放复现 1.6562725546；**不**要求 digest 全 READY | 设计/待批准 |
| 2 | **Freshness Gate 每日 shadow 报告**（cron 只读跑 `run_freshness_sweep` 出 CSV） | 无（只读） | Gate 模块已就绪 | 移除 cron 即回滚 | 报告按时产出且与人工抽查一致 | **可先行批准（零风险）** |
| 3 | **Gate 接入 manifest/readiness**（写 input_date/coverage/source_version/fallback_used/degradation_reason/health_status） | manifest 结构、dashboard readiness | shadow 观察 N 日无误报 | 回退 manifest 生成版本 | 字段齐全且与实测一致 | 待 shadow 观察期 |
| 4 | **required 输入 BLOCKED→禁止发布** | 正式发布门禁 | shadow 期无 required 误报 | 阈值回退 | 过期必需输入被正确拦截 | shadow 观察后 |
| 5 | **Intraday 特征调度接入**（platform_ready 插入 build-intraday-features-daily） | factor 两表恢复日更 | 隔离验证已通过（覆盖率=市场全量、幂等、分布正常） | 移除该步骤 | 当日 5,186×10 特征行落库 | 设计/待批准 |
| 6 | **Intraday 历史回填**（backfill-intraday-features-daily 8-04→今） | factor 两表批量 upsert ~2.6M 行 | 分批+断点；隔离幂等已证 | 按日期删除重填 | 中间断档为0、覆盖率达标 | 设计/待批准 |
| 7 | **TDX open_call 日更恢复** | `stock_auction_bar` open_call 增量 | 工具已从 `8dd57c88` 恢复 + 28 测试绿 + 真实只读抓取验证（9-08 可抓 99.2%，价格一致 100%）；host 脚本动态日期 + launchd StartCalendarInterval 最小修改 | 停用该步骤 | open_call:tdx Gate 项转 READY、当日覆盖≈5k | **待批准（调度+生产首抓）** |
| 7a | **TDX 两日生产试补**（2026-09-08 + 2026-10-19，market+staging upsert） | `stock_auction_bar` open_call 2 日 | 只读验证已通过；备份快照+限定 source='tdx' DELETE 回滚 | 试补行删除 | matched≥99%、价格一致≥99.9%、Gate 当日 READY | **待批准（首次生产写）** |
| 7b | **TDX 缺口历史回填**（9-08→10-20 共 25 日中剩余 23 日） | `stock_auction_bar` open_call | 7a 通过后执行；单日窗口逐日 watchdog | 按日 DELETE source='tdx' | 全缺口日覆盖达标、零 failed | 待批准 |
| 8 | **v2 适配版竞价增强因子**（研究版） | lhb_backtest 研究路径 | v2 detail：open 侧任意 source（TDX 优先）、`signal_last_5m_return` 显式命名、竞价专有字段置 NULL 不补零；与 v1 对拍已证明 0 Top5 翻转（79 日） | 不部署 v2，v1 行为不变 | 新旧版本差异报告稳定；PIT 边界验证 | **待批准（代码合并，非生产行为）** |
| 8b | ~~Tushare 竞价恢复~~ | — | **已否决**：用户决定不购买权限；close_call 历史专有数据不可完整还原 → STATIC_FROZEN 保留研究限制 | — | — | 关闭 |
| 9 | **MidTrend 切片契约**（manifest `artifact_status` 列：daily_valid/research_only_out_of_window/research_only_frozen/missing_source） | mid_trend EOD manifest | **代码已实现**（release candidate，未部署） | 恢复 emit | manifest 可区分每日有效输入与冻结工件 | **待批准部署** |
| 10 | **顶层 funnel 兜底→DEGRADED 契约** | mid_trend EOD | — | 恢复兜底 | fallback_used/degradation_reason 入 manifest | 设计/待批准 |
| 11 | **derive_qfq 口径统一**（minute_backfill 改 daily_bar 自推导） | 历史分钟回填正确性 | 等价性对拍 | 恢复旧逻辑 | 除权股回填结果一致 | 设计/低优先 |
| 12 | **PDF 权限修复**（`public_access=false` 未执行） | 外网付费报告泄露面 | 最小权限补丁+回归测试 | 恢复路由 | 未授权访问被拒 | 独立 Gate/待批准 |
| 13 | P2：`corporate_action`/`stock_auction_detail`/`staging.tushare_auction` 退役确认 | 保留表不删除（用户指示） | 确认外部消费者不存在 | — | 只标注 deprecated，不删数据 | 待确认 |
| 14 | **Intraday staging→生产小批量回填**（8-04→8-31 约20日 ~104万行 upsert） | factor 两表 | staging 实测已通过（幂等/零NULL/16s·日） | 按日期删除重填 | staging↔prod 等价、覆盖率达标 | **待批准（审批包见 03_intraday_recovery_validation.md）** |
| 15 | **Regime 版本化发布接入**（`regime_daily_update` publish_versioned 到 canonical 消费路径） | tech_bottleneck/serenity 市场敞口 | 模块已实现+演练；staging 差异审批通过 | `latest` 指针回切 | 89 新日期入正式路径，0 历史改写 | 待批准 |

## 建议放行顺序

1. **先行（零风险）**：#2 shadow 报告 cron。
2. **配合 Regime**：#1（须 staging+差异分类审批后）→ #3/#4（shadow 观察数日后接入）。
3. **数据恢复**：#5 调度接入 → #6 分批回填；#7 由用户权限决定；#8 为备选。
4. **契约层**：#9/#10 一并改 manifest 语义。
5. **独立**：#11 低优先；#12 独立安全 Gate；#13 仅标注。
