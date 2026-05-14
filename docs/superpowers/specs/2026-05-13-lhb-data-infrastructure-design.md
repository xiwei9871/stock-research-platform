# 龙虎榜数据基础设施设计 v1

## 1. 目标

本轮只做龙虎榜数据基础设施设计，不接策略、不做回测、不参与交易信号。

目标边界：

- 建立 `top_list` / `top_inst` 的入库表结构
- 预留派生特征表
- 设计与案例库的对齐诊断
- 如果实现成本低，可把 schema 先加入研究库
- 不做全量拉取，只允许后续做小样本 schema / upsert 验证

## 2. 数据源

优先顺序：

1. `Tushare top_list`
   - 龙虎榜每日交易明细
2. `Tushare top_inst`
   - 龙虎榜机构成交明细
3. 交易所公开信息
   - 作为后续补充核验来源

要求：

- 字段名尽量与 Tushare 返回保持一致
- 统一保留 `source`
- 保留原始披露口径，不在入库层先做主观加工

## 3. 基础表

### 3.1 `market.lhb_top_list_daily`

字段：

- `trade_date`
- `ts_code`
- `name`
- `close`
- `pct_change`
- `turnover_rate`
- `amount`
- `l_sell`
- `l_buy`
- `l_amount`
- `net_amount`
- `net_rate`
- `amount_rate`
- `float_values`
- `reason`
- `source`
- `created_at`
- `updated_at`

主键建议：

- `(trade_date, ts_code, reason, source)`

说明：

- 同一股票同一日可能因不同上榜原因重复披露，`reason` 需要进主键

### 3.2 `market.lhb_top_inst_daily`

字段：

- `trade_date`
- `ts_code`
- `exalter`
- `buy`
- `buy_rate`
- `sell`
- `sell_rate`
- `net_buy`
- `reason`
- `source`
- `created_at`
- `updated_at`

主键建议：

- `(trade_date, ts_code, exalter, source)`

说明：

- `exalter` 代表机构席位或营业部披露对象

## 4. 派生表

### `factor.lhb_event_features_daily`

字段：

- `trade_date`
- `ts_code`
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
- `lhb_after_limit_up`
- `lhb_after_break_limit`
- `lhb_after_reversal`
- `lhb_one_day_pump_risk`
- `source`

边界：

- 该表是诊断 / 特征预备层
- 本轮不接 Dragon Strategy 打分

## 5. 与案例库对齐

后续输出：

### `outputs/research/dragon_case_lhb_alignment_audit_2024_2026.csv`

字段：

- `case_id`
- `ts_code`
- `stock_name`
- `case_type`
- `event_type`
- `event_date`
- `lhb_on_event_date`
- `lhb_before_event_3d`
- `lhb_after_event_3d`
- `lhb_reason`
- `lhb_net_buy_amount`
- `institution_net_buy`
- `repeat_on_list_count_5d`
- `lhb_alignment_status`

用途：

- 观察经典案例在关键事件日前后是否出现龙虎榜披露
- 不直接作为策略买卖信号

## 6. 小样本验证

允许后续做的小样本验证：

- 单只股票
- 单段日期
- 只验证 schema、读取、upsert

不允许：

- 本轮拉全量
- 本轮把龙虎榜直接混入 Dragon score / entry score / risk score

## 7. 下一步

推荐顺序：

1. 先补案例库 `source_url`
2. 再做 Tushare LHB schema / ingest stub
3. 再做 `dragon_case_lhb_alignment_audit`
4. 最后才考虑是否进入策略特征层
