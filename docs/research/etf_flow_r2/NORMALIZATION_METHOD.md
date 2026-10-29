# NORMALIZATION_METHOD — 规模归一化口径

## 主指标（比例），绝对金额仅辅助

- **F1(t)** = 当日净申购 / 上一交易日组合净资产
- **Fw(t)** = 窗口 w 日净申购合计 / 窗口期初（t−w）组合净资产，w∈{5,10,20,40,60}
- 组合口径：**金额先加总、再除以组合规模**（不平均各基金比例）
- `cum_i20`（每日比例之和）仅作历史对照，**不**称作 ETF 资产增长率

## 持续性

- inshare20/outshare20：20 日净入/净出天数占比
- pos_streak/neg_streak：连续净入/净出交易日数
- 流入基金 AUM 覆盖率：fund_day 当日 flow>0 基金 mv 占比（衍生，见 fund_day.parquet）

## 加速度

- accel = F5 − F20_prev20（非重叠前 20 窗口，避免机械重叠）

## 分母质量（E 项）

- AUM = Σ shares×NAV；公司行为日（官方+算法确认）mv/nav_ret/flow_use 置 NaN——共 263 基金日掩码，分母由其余基金构成。
- 覆盖率：fund_day 中 mv 非 NaN 行占比 ≥99.9%；极端小基金（<1 亿）对组合比例影响<0.1%，未做剔除阈值但记录其存在。
- 新上市基金自首个完整份额+NAV 日起纳入（无回填）。
- 组合成分敏感性：unverified 候选日纳入 vs 剔除（flow_use vs flow_use_strict）——G2/G1 事件集两口径逐日相同（`../etf_flow_r1/SENSITIVITY_CORP_ACTION.csv`）。

## 指数口径

G2=沪深300、G9=上证50、G4k=科创50、G3/G1=中证全指（真实）；G5–G8=市值加权代理（中证主题指数仅至 2024-06）——`idx_source` 字段逐行标注 `real:*` / `proxy:mv_weighted`。
