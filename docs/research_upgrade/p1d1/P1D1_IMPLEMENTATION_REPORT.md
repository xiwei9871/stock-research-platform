# P1d.1 IMPLEMENTATION REPORT — 历史交易资格纠偏与回测安全验收

基线：`data/p1d-tradeability-audit @ c7929b80` ｜ 分支：`fix/p1d1-historical-tradeability-gate`
性质：审计+修正既有设施，零生产执行路径改动、零信号/参数改动、零部署。

## 改动清单

| 文件 | 性质 | 内容 |
|---|---|---|
| `src/stock_research/tradeability.py` | 重写扩展（949+ 行） | P0-A~E 规则引擎/交易日序号/fail-closed/法定价/版本门禁 |
| `src/stock_research/lhb_eligibility.py` | 对齐修复 | `_regime_and_threshold` 路由统一规则引擎，trade_date 不再被丢弃 |
| `tests/test_tradeability_p1d.py` | 夹具更新 | 22 条 P1d 对抗测试期望值对齐修正后语义，不回退 |
| `tests/test_tradeability_p1d1.py` | 新增 | 33 条 P1d.1 覆盖 |
| `scripts/p1d1_audit.py` | 新增 | P0-F 双向误标重算 + 边缘案例 + 分钟门禁审计 |
| `scripts/p1d1_shadow_backtest.py` | 新增 | P0-G baseline-vs-shadow 隔离回测 |
| `docs/research_upgrade/p1d1/` | 新增 | 13 项交付物 |

## P0-A 历史规则引擎

- `LIMIT_RULES` 22 条，全字段齐备（rule_id/exchange/board/status_class/
  event/effective_from/to/source/verified + day1 cap + no_limit window）；
- 620 号过渡按 `delisting_arrangement_entered` 日期门控：改革前进入且仍在
  整理期→10%，改革后新进入→20%；进入日期缺失→`rule_unknown`；
- 主板改革前首日 +44%/-36% 申报笼子独立于普通 10%（`day1_*_pct`），
  第 2 交易日起回普通规则；全面注册制前 5 交易日无涨跌幅单独成行；
- `unverified → rule_unknown`（北交所 ST 待官方文本确认，唯一 unverified 行）；
- `unrestricted_unknown_period` 默认放行语义已删除。

## P0-B 真实交易日序号

`load_tradeability_context` 用 `market.trading_calendar` is_open 序列做
bisect：`sess_idx = open_days(list_date, trade_date]`——跨周末/节假日
不错位；list_date 缺失/日历缺失/状态行缺失 → fail-closed UNKNOWN。

## P0-C fail-closed 语义

- universe：`ELIGIBLE/INELIGIBLE/UNKNOWN`；order side：
  `ATTEMPTABLE/RESTRICTED/UNKNOWN`，买卖独立；
- `is_trade=None`/`status absent`/`pct_chg=None`/`trade_status=None` →
  UNKNOWN 不再穿透为可交易；
- 停牌先于 rule_unknown 判定（已知事实不被未知规则掩盖）。

## P0-D 法定价判定

- `legal_limit_price(preclose_raw, eff_pct, side)`：0.01 元 tick 取整；
- `classify_limit_day` 区分 CLOSE_AT_LIMIT/ONE_WAY_LOCKED/
  PCT_NEAR_LIMIT_UNVERIFIED/NO_LIMIT_WINDOW/DATA_INSUFFICIENT——
  不把百分比区间机械等同涨停，不推定排队必成；
- raw/hfq 口径分离：flag 判定一律 raw 价；
- ExecutionPolicy 承载可配置保守假设；同日收盘数据不得用于开盘发单判定
  （shadow 两腿共用同一时点语义，差异仅来自规则值）。

## P0-E 分钟版本门禁

见 `MINUTE_VERSION_GATE_AUDIT.md`：done key 3,077/2,293、74 终态缺口、
59 备用源、15 无 key、600153 隔离——与 P1c 基线一致；features pin
不解除分钟缺口。

## P0-F 误标重算（双向）

见 `FALSE_POSITIVE_FALSE_NEGATIVE.md`：**63,821 行 CONFIRMED_MISLABEL**
（FP 20,082 / FN 43,739）+ 24 RULE_UNKNOWN + 98,274 CORRECT。
每行含 `old_flag/historical_rule/legal_limit_price/limit_class/
classification/session_index` 于 `LIMIT_FLAG_RECONCILIATION.csv`。

## P0-G 回测影响

见 `BACKTEST_CONSUMER_INVENTORY.md` + `BACKTEST_SHADOW_REPORT.md`：
- 消费路径全清单（含两条执行路径"门哑/SQL 崩"的基础设施发现）；
- shadow：manual_v1×top20×daily×2024-01-02~2026-10-23，63 差异键全部
  可解释，rule_unknown 归因 0，净值差 −0.72pp；
- 受影响回测标注 `NEEDS_REVALIDATION`（见清单末节）。

## P1-H 存储方案

见 `STORAGE_MIGRATION_PLAN.md`：方案 A（v2 列灰度）已隔离验证
（p1d1_shadow schema，369,681 行样本，幂等 0 差，PK 零漂移）；
生产表未动一行。

## 既有缺陷的附带修复决策

`lhb_eligibility._regime_and_threshold` 属于任务书"修复/对齐历史规则"范围：
它是存量唯一仍在运行的历史规则旁路（LHB 资格判定 daily 在跑），
不修复则平台上同时存在两套互相矛盾的历史规则答案。修复方式=路由统一
引擎而非另写规则表。

## 测试

- `.venv/bin/pytest tests/test_tradeability_p1d.py` → **22 passed**（不回退）
- `.venv/bin/pytest tests/test_tradeability_p1d1.py` → **33 passed**
- 聚焦回归（13 文件，覆盖全部触碰模块）→ **414 passed, 0 failed**
- 真实 DB 边界：`TRADEABILITY_FAIL_CLOSED_TESTS.json` 14/14 edge cases，
  errors=[]；RULE_UNKNOWN 24 行全部 1990-12-19 ST 数据异常（fail-closed 正确）
- 新增失败数：**0**（详见 REGRESSION_DIFF.md）

## 禁止项自查

| 禁止项 | 状态 |
|---|---|
| 修改生产回测成交规则 | ✅ 未改（backtest_constraints 零改动） |
| 全表重写 17.29M 行 status_daily | ✅ 未动，仅 p1d1_shadow 隔离 schema |
| 改正式信号/调仓频率/参数 | ✅ 未改 |
| 静默覆盖旧误标 | ✅ 旧 flag 原样保留，差异全部出清单 |
| 未来收盘判历史盘中 | ✅ 两腿同时点语义；无盘中粒度承诺 |
| 未知状态放行 | ✅ fail-closed，UNKNOWN≠可交易 |
| 新建平行资格系统 | ✅ 复用同一 LIMIT_RULES/calendar/status/执行门；LHB 旁路已收敛进同一引擎 |
| 干扰 EOD/调度 | ✅ 全部本地脚本，未碰 crontab/launchd |
| 合并 main/部署 | ✅ 独立分支，未部署 |
