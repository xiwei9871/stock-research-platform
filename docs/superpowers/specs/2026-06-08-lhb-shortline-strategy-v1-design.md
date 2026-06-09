# LHB Shortline Strategy v1 Design

## 1. 目标

本设计定义龙虎榜短线策略 v1 的整体研究框架。目标不是自动交易，也不是把龙虎榜做成单独追涨信号，而是构建两个稳定输出：

1. **选股入池**：每天识别值得观察的短线情绪票，分成可跟、强弹性观察、谨慎观察、回避四类。
2. **撤退信号**：对已经进入观察池或持仓跟踪的短线票，识别资金撤退、结构失败、情绪退潮等退出确认。

交易执行不自动化；系统只输出观察池、风险解释、撤退提示和历史有效性报告。

## 2. 策略定位

龙虎榜在本系统中不是买点触发器，而是资金行为确认层。

完整决策链为：

```text
市场情绪周期 -> 主线板块 -> 个股事件结构 -> LHB 资金行为 -> 次日确认 -> 撤退信号
```

各层职责：

- 市场情绪周期：决定短线是否可做。
- 主线板块：决定资金聚焦方向。
- 个股事件结构：决定候选股票是否有短线辨识度。
- LHB 资金行为：判断资金是在承接、分歧还是撤退。
- 次日确认：避免盘后信号次日失效。
- 撤退信号：识别失败结构和资金撤退，提示离场或降级。

## 3. 不做什么

短期明确不做：

- 不自动下单。
- 不输出实盘买入/卖出指令。
- 不把 future return 参与任何当日分数、入池或撤退判断。
- 不把单日龙虎榜净买额直接当作买点。
- 不把所有高风险/高波动样本剔除；超短线本身需要保留高弹性观察层。
- 不追求一次性完整回测，先做历史回放和规则校准。

## 4. 数据输入

### 4.1 龙虎榜数据

现有表和特征：

- `market.lhb_top_list_daily`
- `market.lhb_top_inst_daily`
- `factor.lhb_event_features_daily`

核心字段：

- `on_lhb`
- `lhb_reason`
- `lhb_net_buy_amount`
- `lhb_net_buy_ratio`
- `lhb_buy_amount`
- `lhb_sell_amount`
- `institution_net_buy`
- `top_seat_concentration`
- `repeat_on_list_count_3d`
- `repeat_on_list_count_5d`
- `lhb_one_day_pump_risk`
- `lhb_after_limit_up`
- `lhb_after_break_limit`
- `lhb_after_reversal`

### 4.2 Dragon / 主线诊断

复用现有 Dragon 研究输出：

- `dragon_role`
- `dragon_status_score`
- `dragon_entry_score`
- `dragon_risk_score`
- `entry_window`
- `entry_window_v2`
- `overheat_avoid`
- `crowded_late_entry`
- `industry_focus_score_v2`
- `industry_rank`

### 4.3 市场情绪和主线环境

可复用或后续补充：

- 市场成交额
- 涨停数量
- 跌停数量
- 连板高度
- 炸板率
- 昨日涨停溢价
- 高位亏钱效应
- 市场风格/主线强度

输出统一成：

- `short_market_state`
- `short_allowed`
- `market_risk_level`

### 4.4 个股事件结构

候选事件：

- `continuous_limit_up`
- `break_then_reversal`
- `second_wave`
- `failed_second_wave`
- `weak_to_strong`
- `dragon_pullback`
- `high_open_low_close_failure`
- `one_day_pump`
- `a_kill_failure`

事件结构只来自当时可观察信息；未来收益只用于诊断。

## 5. 统一事件回放表

下一阶段核心产物是 `lhb_shortline_event_replay_v1.csv`。每一行代表一个可观察短线事件，而不是一笔交易。

建议字段：

- `trade_date`
- `ts_code`
- `stock_name`
- `short_market_state`
- `short_allowed`
- `market_risk_level`
- `industry_name`
- `mainline_flag`
- `industry_rank`
- `industry_focus_score_v2`
- `dragon_role`
- `dragon_entry_score`
- `dragon_risk_score`
- `entry_window_v2`
- `event_structure`
- `event_date`
- `lhb_event_date`
- `lhb_behavior_type`
- `lhb_replay_action`
- `lhb_replay_reason`
- `lhb_risk_score`
- `lhb_risk_level`
- `lhb_negative_net_buy`
- `lhb_institution_selling`
- `lhb_high_pump_risk`
- `lhb_after_event_attention`
- `next_day_confirmation`
- `exit_signal`
- `exit_reason`
- `future_1d_return`
- `future_3d_return`
- `future_5d_return`
- `future_10d_return`
- `future_5d_max_drawdown`
- `future_10d_max_drawdown`
- `limit_up_within_5d`
- `a_kill_within_5d`
- `second_wave_success`

其中 future 字段仅用于报告和校准，不能参与当日分类。

## 6. LHB 行为分类

### 6.1 承接型

`lhb_behavior_type = support`

典型条件：

- `lhb_net_buy_amount > 0`
- `institution_net_buy >= 0`
- 无明显 `lhb_negative_net_buy`
- 无明显 `lhb_institution_selling`
- 个股处于可跟事件结构，如二波、弱转强、断板反包、龙回头
- 市场不是退潮

输出倾向：

- `follow_candidate`

### 6.2 高弹性分歧型

`lhb_behavior_type = high_elasticity`

典型条件：

- `lhb_high_pump_risk = true`
- 高换手、高集中度、重复上榜、放量
- 没有负净买/机构卖出
- 个股仍有强排名或强事件结构

输出倾向：

- `high_elasticity_follow`
- 或 `watch_only`

说明：

高 pump 不再单独作为硬风险。它既可能是一日游风险，也可能是短线强弹性来源，需要通过主线、结构、次日确认区分。

### 6.3 撤退型

`lhb_behavior_type = withdrawal`

典型条件：

- `lhb_negative_net_buy = true`
- `lhb_institution_selling = true`
- Dragon/LHB 双高风险
- 失败结构出现后又有 LHB 关注
- 事件后上榜但价格结构走弱

输出倾向：

- `avoid_withdrawal`
- `exit_confirmation`

## 7. 入池规则

### 7.1 follow_watch

入池条件：

- `short_allowed = true`
- `mainline_flag = true` 或行业强度排名靠前
- `event_structure` 属于可跟结构
- `dragon_role` 属于龙头、核心、中军、二波候选或强势修复
- LHB 为承接型或无撤退信号
- `dragon_risk_score` 和 `lhb_risk_score` 不同时高

用途：

- 作为次日重点观察对象。
- 不代表立即买入。

### 7.2 high_elasticity_watch

入池条件：

- 排名靠前或辨识度高
- 有高 pump、高换手、爆量、重复上榜
- 未出现负净买/机构卖出
- 市场不是明显退潮

用途：

- 保留情绪票弹性，不被风险层全部剔除。
- 需要次日确认后才可升级。

### 7.3 avoid_watch

入池条件：

- 负净买或机构卖出
- 失败结构或高位退潮
- Dragon/LHB 风险共振
- 事件后上榜但价格转弱

用途：

- 作为回避池。
- 如果已在观察或持有跟踪中，触发撤退评估。

### 7.4 exit_watch

入池条件：

- 已入池股票出现失败结构
- 分歧后 1-3 日未修复
- LHB 出现撤退型信号
- 高开低走、冲高回落、破位、板块退潮

用途：

- 提示降级或撤退。
- 不自动交易。

## 8. 次日确认

次日确认是独立层，不能省略。

候选输出：

- `confirmed_strength`
- `failed_open`
- `intraday_fade`
- `repair_after_low_open`
- `no_confirmation`

初版可先用日线近似：

- 次日收益
- 次日高到收回落
- 次日收盘位置
- 次日是否涨停
- 次日是否大幅低开后修复

后续如果有分钟线，再升级为盘中确认。

## 9. 撤退信号

撤退信号分两类。

### 9.1 硬撤退

`exit_signal = hard_exit`

条件：

- A 杀开始
- 失败二波确认
- 负净买 + 机构卖出
- Dragon/LHB 风险共振
- 板块主线退潮且个股破位

### 9.2 降级观察

`exit_signal = reduce_watch`

条件：

- 高 pump 后次日无确认
- 冲高回落明显
- 分歧后 1-3 日未修复
- 过热但无承接
- 高弹性票失去排名或辨识度

输出应保留 `exit_reason`，避免黑箱化。

## 10. 历史有效性报告

### 10.1 Follow 有效性

分组维度：

- `lhb_behavior_type`
- `lhb_replay_action`
- `event_structure`
- `dragon_role`
- `entry_window_v2`
- `short_market_state`
- `mainline_flag`

指标：

- 样本数
- 未来 1/3/5/10 日平均收益
- 胜率
- 最大回撤
- 涨停率
- A 杀率
- 二波成功率

### 10.2 Exit 有效性

分组维度：

- `exit_signal`
- `exit_reason`
- `event_structure`
- `lhb_behavior_type`
- `market_risk_level`

指标：

- 触发后 1/3/5 日平均收益
- 触发后最大回撤
- 是否减少 A 杀
- 是否误杀强二波
- 触发提前量

## 11. 分阶段实施

### Phase 1: 统一事件回放表

目标：

- 合并 LHB、Dragon、事件结构、市场环境、future diagnostics。
- 输出 `lhb_shortline_event_replay_v1.csv`。
- 不接实盘。

验收：

- 每行有明确 `event_structure`、`lhb_behavior_type`、`lhb_replay_action`。
- future 字段只在报告中出现。

### Phase 2: Follow / Avoid 规则校准

目标：

- 验证承接型、高弹性型、撤退型 LHB 行为。
- 识别哪些组合值得入池。

输出：

- `lhb_follow_effectiveness_v1.csv`
- `lhb_follow_rule_audit_v1.md`

### Phase 3: Exit 规则校准

目标：

- 验证撤退信号能否减少 A 杀和失败二波损失。
- 识别误杀强二波的规则。

输出：

- `lhb_exit_effectiveness_v1.csv`
- `lhb_exit_rule_audit_v1.md`

### Phase 4: 观察池生成

目标：

- 每日输出四类观察池：
  - `follow_watch`
  - `high_elasticity_watch`
  - `avoid_watch`
  - `exit_watch`

输出：

- `daily_lhb_shortline_watchlist.csv`
- `daily_lhb_shortline_watchlist.md`

### Phase 5: 与现有 watchlist 合流

目标：

- 将 LHB 短线观察池接入现有 watchlist，但仍不做自动交易。
- 保留 `watch_group`、`risk_note`、`opportunity_note`、`exit_reason`。

输出：

- `watchlist_diagnostics_YYYY-MM-DD_diagnostics_v1.csv` 带有 `lhb_shortline_*` 字段。
- `watchlist_diagnostics_must_watch_YYYY-MM-DD_diagnostics_v1.csv` 能展示 LHB 入池和撤退原因。

### Phase 6: 策略有效性复盘面板

目标：

- 不再继续堆新规则，先验证 Phase 1-5 形成的分组是否有效。
- 回答两个问题：
  - 什么样的 `follow_watch` / `high_elasticity_watch` 值得跟？
  - 什么样的 `avoid_watch` / `exit_watch` 真的应该跑？
- 建立一套可以反复运行的短线策略复盘面板，避免凭少量案例主观调参。

输入：

- `lhb_shortline_event_replay_v1.csv`
- `daily_lhb_shortline_watchlist_YYYYMMDD.csv`
- `watchlist_diagnostics_YYYY-MM-DD_diagnostics_v1.csv`
- future return / max drawdown / limit-up / A-kill 字段，仅用于复盘。

核心分组：

- `watch_group`
- `lhb_behavior_type`
- `lhb_replay_action`
- `event_structure`
- `entry_window_v2`
- `mainline_flag`
- `short_market_state`
- `market_risk_level`
- `exit_signal`
- `exit_reason`

核心指标：

- 样本数。
- 未来 1/3/5/10 日平均收益。
- 未来 1/3/5/10 日胜率。
- 未来 5/10 日最大回撤。
- 5 日内涨停率。
- 5 日内 A 杀率。
- 二波成功率。
- 撤退信号触发后是否减少回撤。
- 撤退信号误杀率：触发 exit 后仍走出强二波或高收益。
- 撤退信号漏报率：未触发 exit 但随后出现 A 杀或大回撤。

输出：

- `lhb_shortline_strategy_effectiveness_detail_v1.csv`
- `lhb_shortline_strategy_effectiveness_summary_v1.csv`
- `lhb_shortline_follow_combo_effectiveness_v1.csv`
- `lhb_shortline_exit_combo_effectiveness_v1.csv`
- `lhb_shortline_strategy_effectiveness_v1.md`

验收：

- 能列出 Top follow 组合、Top high elasticity 组合、Top avoid/exit 组合。
- 能区分“高弹性可观察”和“真实撤退风险”。
- 报告中明确标记样本数不足的组合，不允许小样本结论直接进入规则。
- 不改变当日入池逻辑，只做复盘和证据沉淀。

### Phase 7: 规则校准与版本化

目标：

- 基于 Phase 6 复盘证据，对 Phase 4/5 的入池和撤退规则做一次有约束的校准。
- 所有规则变更必须有分组证据支持，不能因为个别案例临时加条件。
- 形成版本化规则，方便后续比较 v1、v1.1、v1.2 的效果。

规则校准方向：

- `follow_watch`：
  - 强化主线、事件结构、LHB 承接行为之间的共振条件。
  - 对低胜率组合降级为 `watch_only`。
  - 对样本稳定且收益/回撤比好的组合保留入池。

- `high_elasticity_watch`：
  - 保留高 pump、高换手、高关注度带来的弹性。
  - 对 A 杀率过高、最大回撤过大的组合增加降级或回避条件。
  - 避免把高弹性样本简单归为硬风险。

- `avoid_watch` / `exit_watch`：
  - 对命中率高、提前量好的撤退信号保留或升权。
  - 对误杀率高的 exit 条件降权。
  - 明确哪些 exit 是硬撤退，哪些只是降级观察。

版本字段：

- `lhb_shortline_rule_version`
- `lhb_shortline_follow_rule_id`
- `lhb_shortline_exit_rule_id`
- `lhb_shortline_rule_confidence`
- `lhb_shortline_rule_sample_count`

输出：

- `lhb_shortline_rule_calibration_v1.md`
- `lhb_shortline_rule_registry_v1.csv`
- 更新后的 `daily_lhb_shortline_watchlist_v1` 输出字段。
- 更新后的 watchlist diagnostics LHB 合流逻辑。

验收：

- 每条规则都有 `rule_id`、触发条件、历史样本数、核心收益/风险指标。
- 规则变更前后可对比，不覆盖旧版本。
- 当日输出不使用 future 字段。

### Phase 8: 日常运行链路固定化

目标：

- 把 LHB 短线策略从研究脚本推进到可重复运行的日常流程。
- 每个交易日能稳定产出“观察池 + 撤退信号 + 复盘入口”，但仍不自动交易。
- 将运行产物接入已有 watchlist runbook 和 diagnostics 报告体系。

日常流程：

```text
LHB event features
-> lhb_shortline_event_replay_v1
-> lhb_follow/exit rule audit artifacts
-> daily_lhb_shortline_watchlist_v1
-> build-watchlist-diagnostics --lhb-shortline-path
-> watchlist diagnostics report
```

日常输出：

- 当日 LHB 短线观察池 CSV/MD。
- 当日 watchlist diagnostics CSV/MD。
- 当日 must-watch 列表。
- 当日 exit/avoid 列表。
- 运行摘要：样本数、入池数、撤退数、异常数据提示。

质量控制：

- 输入文件缺失时给出明确 warning，不生成误导性空报告。
- `ts_code` 与 `asset_id` 映射失败时输出 unmatched 明细。
- 当日 LHB 数据为空时，watchlist diagnostics 仍能运行，但报告标记 LHB shortline unavailable。
- 报告中区分“无信号”和“数据缺失”。

输出：

- `docs/watchlist-diagnostics-runbook.md` 增加 LHB shortline 步骤。
- 可选 CLI wrapper，例如 `run-lhb-shortline-daily-v1`。
- `lhb_shortline_daily_run_summary_YYYYMMDD.json`

验收：

- 用一个交易日可以从输入到最终 watchlist diagnostics 一键或少命令跑通。
- 运行日志能解释产物路径和数据缺口。
- 不需要人工改 CSV 文件名或手工拼接中间产物。

### Phase 9: 人工纸面交易复盘闭环

目标：

- 建立不自动下单的人工决策闭环，验证策略在真实节奏里的可用性。
- 记录“系统给了什么、人工怎么判断、次日/后续如何演化”，用于后续规则优化。
- 重点不是模拟完美成交，而是验证信号是否对人工短线决策有帮助。

人工记录对象：

- 入池观察：
  - 是否人工加入重点观察。
  - 观察理由。
  - 次日是否确认。
  - 是否放弃。

- 撤退信号：
  - 是否人工认可撤退。
  - 是否降级观察。
  - 是否认为误杀。
  - 后续 1/3/5 日走势。

- 复盘标签：
  - `manual_follow_decision`
  - `manual_exit_decision`
  - `manual_decision_reason`
  - `next_day_confirmation_review`
  - `post_review_label`
  - `operator_notes`

输出：

- `lhb_shortline_manual_review_YYYYMMDD.csv`
- `lhb_shortline_manual_review_summary_v1.csv`
- `lhb_shortline_manual_review_v1.md`

复盘维度：

- 系统推荐但人工放弃，后续是否走强。
- 系统回避但人工关注，后续是否走弱。
- 系统 exit 与人工 exit 是否一致。
- 人工覆盖是否显著改善风险收益。
- 哪些规则最容易被人工否决。

验收：

- 人工复盘数据不反向污染当日模型，只用于后续研究。
- 每周可以生成一次人工决策复盘报告。
- 能明确回答：系统是否减少了无效关注、是否提前提示撤退、是否漏掉关键强票。

## 12. 成功标准

本策略 v1 成功的标准不是单次收益最高，而是：

- 能稳定解释哪些 LHB 票值得进入观察池。
- 能区分高弹性风险和真实撤退风险。
- 能减少 A 杀和失败二波暴露。
- 不把所有情绪票都过滤掉。
- 所有规则都有历史回放证据。
- 输出可读、可复盘、可人工决策。

## 13. 当前推荐下一步

Phase 1-5 已经完成基础链路：统一事件回放、Follow/Avoid 审计、Exit 审计、每日观察池、与现有 watchlist 合流。

下一步不继续新增零散规则，而是实施 Phase 6：

```text
lhb_shortline_strategy_effectiveness_v1
```

优先产出策略有效性复盘面板，确认哪些组合值得跟、哪些信号该跑。Phase 6 只做复盘验证，不改变当日入池和撤退规则。规则调整放到 Phase 7。
