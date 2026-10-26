# P0-E 财务指标计算口径核验（季度/累计/TTM）

## A 股披露口径

| 表 | 口径 | 单季推导 |
|---|---|---|
| balance_sheet | **时点存量** | 无需差分，期末值即口径 |
| income_statement | **年初至期末累计（YTD）** | Q1=原值；Q2单季=H1−Q1；Q3单季=9M−H1；Q4单季=FY−9M |
| cash_flow | **年初至期末累计（YTD）** | 同上 |

把半年报/三季报累计值直接当单季值 = 错误（会高估 Q2/Q3）。

## 现有实现核验：`services/finance_ttm.py`

- `load_income_ttm_rows` 取 `announcement_date <= trade_date` 且 `report_period <= trade_date` 的行，按 period desc + ann desc 排序；
- `calc_ttm_from_cumulative_rows`：TTM = 本期累计 + 上年FY − 上年同期累计（标准 YTD→TTM 公式）；
- 输入行若含未来版本：仅按 ann 过滤 —— **机制正确**；
- **缺口**：(a) 同日可用约定（ann<=trade_date）与 D+1 保守政策差一天；(b) 同键多源时排序只按 ann/period，无 source 偏好 → akshare/baostock 数值不一致（188,171 键）会导致 **TTM 随选源漂移**；(c) 上年同期若被重述，TTM 用的是重述后旧数——属"最新版历史口径"，需在契约中声明或改用 `initial_public` 版本。

## 规则清单

1. 单季值必须由相邻累计差分，缺失前置期间 → **不得静默填零**（返回 None/标记 data_insufficient）；
2. TTM 四个组成期间都必须满足同一 as_of 的公开性（ann < as_of 严格）；
3. 同比/环比的"上年同期"应取同一 version_policy 下的版本，禁止初版对重述版混算；
4. balance 时点表无累计问题，但**同键多源漂移**同样适用；
5. report_type='FY' 与 'Q' 并存：FY 行=年报累计（=Q4累计），差分时优先用 FY 行减 9M 行；若 9M 缺失不得用 FY 当 Q4。

## 对抗样本要求（P0-G 已落 tests/test_financial_pit_p2.py）

- as_of 介于 H1 公告与 Q3 公告之间 → TTM 只能含到 H1；
- 上年同期重述后 → latest_public TTM 变、initial_public TTM 不变；
- Q2 缺但 H1 有 → Q2 单季不可算（标记而非填零）。
