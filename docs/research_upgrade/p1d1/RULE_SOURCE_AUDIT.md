# P1d.1 RULE_SOURCE_AUDIT — 历史涨跌幅规则来源核验

生成口径：`src/stock_research/tradeability.py::LIMIT_RULES`（22 条），逐条对应
`HISTORICAL_RULE_MATRIX.csv`。`verified=False` 的规则在 resolver 中一律返回
`rule_unknown`（fail-closed），绝不降级为默认可交易。

## 官方来源对照

| rule_id | 适用面 | 生效区间 | 比例 | 官方依据 | verified |
|---|---|---|---|---|---|
| pre_19961216_no_limit | 全 A | ~1996-12-13 | 无涨跌幅 | 1996-12-16 起 A 股恢复 ±10% 涨跌幅限制（沪深交易所公告，此前不设） | ✅ |
| main_10pct | 主板普通 | 1996-12-16~ | ±10% | 沪深交易所交易规则 | ✅ |
| main_st_5pct | 主板 ST/*ST | 1998-04-22~ | ±5% | 沪深交易所风险警示制度（1998-04-22 ST 制度实施） | ✅ |
| main_delisting_arrangement_10pct | 主板退市整理期 | 全期 | ±10% | 沪深退市整理期交易机制 | ✅ |
| main_ipo_day1_prereg_cap | 主板 IPO 首日（注册制前） | 2014-01-17~2023-04-07 | 申报上限+44%/下限-36%（次日回 ±10%） | 沪深新股上市首日交易机制（2014-01 起申报价格笼子） | ✅ |
| main_ipo_fullreg_window5 | 主板 IPO（全面注册制） | 2023-04-10~ | 前 5 个交易日不设涨跌幅，其后 ±10% | 全面注册制交易规则（2023-04-10 首批主板注册制新股上市） | ✅ |
| main_relisting_day1_no_limit | 主板重新上市 | 全期 | 首日不设涨跌幅 | 沪深退市公司重新上市实施办法 | ✅ |
| chinext_10pct_pre_20200824 | 创业板普通（改革前） | ~2020-08-21 | ±10% | 注册制改革前创业板随深市主板 ±10% | ✅ |
| chinext_ipo_day1_prereg_cap | 创业板 IPO 首日（注册制前） | 2014-01-17~2020-08-21 | +44%/-36% 申报笼子 | 深市新股首日交易机制 | ✅ |
| chinext_st_5pct_pre_20200824 | 创业板 ST/*ST（改革前） | ~2020-08-21 | ±5% | **深证上〔2020〕620 号**过渡条款确认改革前风险警示股适用 ±5%（原交易规则 3.3.15） | ✅ |
| chinext_20pct_from_20200824 | 创业板普通（改革后） | 2020-08-24~ | ±20% | **深证上〔2020〕515 号《深圳证券交易所创业板交易特别规定》2.1** | ✅ |
| chinext_ipo_window5_from_20200824 | 创业板 IPO（注册制） | 2020-08-24~ | 前 5 交易日无涨跌幅 | 同上 2.1 | ✅ |
| chinext_st_20pct_from_20200824 | 创业板 ST（改革后） | 2020-08-24~ | ±20% | 创业板交易特别规定 + 620 号"改革后风险警示股 20%" | ✅ |
| chinext_delist_arr_pre_reform_10pct | 创业板退市整理期·跨改革过渡 | entry < 2020-08-24 | ±10% | **深证上〔2020〕620 号**：实施前已进入且实施时仍在整理期者维持 ±10% | ✅ |
| chinext_delist_arr_post_reform_20pct | 创业板退市整理期·改革后进入 | entry ≥ 2020-08-24 | ±20% | 同上：实施后新进入者适用 20% | ✅ |
| star_20pct_since_20190722 | 科创板普通 | 2019-07-22~ | ±20% | **上证发〔2019〕23 号《上海证券交易所科创板股票交易特别规定》第十八条** | ✅ |
| star_ipo_window5 | 科创板 IPO | 2019-07-22~ | 前 5 交易日无涨跌幅 | 同上 | ✅ |
| star_st_20pct | 科创板 ST | 2019-07-22~ | ±20% | 科创板风险警示随板块 ±20% | ✅ |
| star_delist_arr_20pct | 科创板退市整理期 | 2019-07-22~ | ±20% | 科创板退市制度安排 | ✅ |
| beijing_30pct_since_20211115 | 北交所普通 | 2021-11-15~ | ±30% | 北交所交易规则（试行），2021-11-15 开市 | ✅ |
| beijing_ipo_day1_no_limit | 北交所新股 | 2021-11-15~ | 首日不设涨跌幅（其后 ±30%） | 同上 | ✅ |
| beijing_st_30pct | 北交所风险警示 | 2021-11-15~ | ±30% | **未找到独立官方文本确认北交所风险警示股是否同 ±30%** | ❌ → `rule_unknown` |

## 关键裁决记录

1. **620 号过渡实现方式**：resolver 不按 trade_date 直接切规则，而按
   `delisting_arrangement_entered`（进入整理期日期）在
   `chinext_delist_arr_pre_reform_10pct` / `chinext_delist_arr_post_reform_20pct`
   间选择；进入日期缺失 → `rule_unknown`。见 `tradeability.py` resolver 段。
2. **主板 IPO 首日 ≠ 普通 10%**：2014-01-17~2023-04-06 首日使用 +44%/-36% 申报
   价格笼子（day1_up_pct/day1_down_pct），第 2 交易日起回落 ±10%。全面注册制
   （2023-04-10）起改为前 5 交易日无涨跌幅。禁止用普通 10% 代替。
3. **上市"首五日"一律按交易所历 open 日序号**（`market.trading_calendar`），
   跨周末/节假日不错位；`list_date+N 自然日`被明确禁止。
4. **unverified → rule_unknown**：北交所 ST 规则未找到独立官方确认文本，
   保留规则行但 `verified=False`，resolver 返回 `rule_unknown` 并保留资格阻断。
   `unrestricted_unknown_period` 默认放行语义已移除。

## 残留待核（下阶段）

- 北交所风险警示股官方文本（当前 fail-closed）；
- 暂停上市恢复/吸收合并换股上市首日等特殊 event_class（现走 `rule_unknown`）；
- 1990-12-19 沪市首日 `is_st=True` 的 24 行——ST 制度 1998-04-22 才存在，
  状态行本身疑似数据错误，已按 `RULE_UNKNOWN` 计入对账清单待数据层修复。
