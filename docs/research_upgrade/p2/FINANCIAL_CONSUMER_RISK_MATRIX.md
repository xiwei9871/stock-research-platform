# 财务消费者风险矩阵（前视偏差面）

## 约定差异

全库消费者统一用 `announcement_date <= as_of`（**公告日当天可用**）；P2 契约采用 **D+1**。公告多为盘后发布（年报/季报常于收盘后挂网），同日约定会让回测在公告日当天**盘前**就"知道"财报——系统性前视泄漏面，量级=每次公告日一天。

## 消费者逐一

| 消费者 | 路径 | 过滤 | 风险 | 处置 |
|---|---|---|---|---|
| 基本面因子 | factor_pipeline → services.point_in_time_finance.get_latest_* | ann<=trade_date | 同日泄漏（小，单日级） | **NEEDS_REVALIDATION**（因子历史值按 D+1 重算后对比） |
| TTM 指标 | services.finance_ttm | ann<=trade_date + period desc | 同日泄漏 + **同键多源漂移**（188,171 键双源不一致→TTM 随源变） + 上年同期用重述后值 | **NEEDS_REVALIDATION** |
| fundamental_pipeline | latest income/balance join | ann<=as_of | 同日泄漏 + 多源漂移 | NEEDS_REVALIDATION |
| midtrend_pit_fundamental_features | pick_first + 自查 lookahead | ann>trade_date 标 lookahead | 同日泄漏（机制上承认 ann=trade_date 合法） | NEEDS_REVALIDATION |
| dashboard asset_profile_fundamentals | anchor_row | ann<=as_of | 同日泄漏（展示层，非回测） | 低风险，建议统一政策 |
| CAP-05/科技产业链商业兑现 | tech_bottleneck 系列脚本 | 不直接读 finance.*（未见 announcement_date 引用） | 间接——若上游因子含同日泄漏则继承；**产品线收入归属与三表 PIT 是正交问题**（整收≠主题线收入） | 接口建议：消费前过 financial_pit_at 门 |
| 策略回测财务条件 | 经 factor_pipeline 因子 | 继承上表 | 继承 | 随因子重验 |

## 已确认的前视泄漏

1. **同日公告泄漏（全平台约定）**：ann<=as_of 使盘后公告当日可用。影响面=所有走财务因子的历史回测点。单日级、但系统性。
2. **同键多源无优先序**：同 (asset,period) 下 akshare 与 baostock 值不同（188,171 键），消费端按 ann desc 取行→源选择随重抓漂移，历史因子不可复现。
3. **重述值回写历史**：初版被同键覆盖后，任何 as_of 都只能看到最新版——历史决策点实际用的是未来版本（版本缺失型前视，不可量化但存在）。

## 建议接口

- 新逻辑统一走 `financial_pit_at`（D+1、fail-closed、version_policy）；
- 修复阶段给 point_in_time_finance/finance_ttm 加 `conservative_same_day=False` 开关（默认改 D+1 前需重验因子/回测）；
- 财务 PIT ≠ 主题产品线归属：CAP-05 不得把整收推断为特定科技线收入。
