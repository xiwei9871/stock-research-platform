# P1d.3 — 灰度读路验证（verified_v2 @ 影子表）

`load_vectorized_topn_inputs(qualification_mode="verified_v2",
status_table="p1d3_shadow.asset_status_daily_v2")` vs `corrected_shadow`，
四个制度窗口逐键比对 —— 详见 `GRAY_READ_VALIDATION.json`。

## 结果（4/4 窗口 PASS）

| 窗口 | 行 | verified | missing | verified 键 flag mismatch | verified 被误标 missing | rule_id 覆盖 |
|---|---|---|---|---|---|---|
| 2024-06 | 24,185 | 24,150 | 35 | 0 | 0 | 100% |
| 2019-08（科创/改革前） | 24,175 | 24,161 | 14 | 0 | 0 | 100% |
| 2023-04（主板注册制） | 24,175* | 24,161 | 14 | 0 | 0 | 100% |
| 1996-12（无涨跌幅年代） | 1,959 | 1,959 | 0 | 0 | 0 | 100% |

- verified 键上 v2 表读出的 flag 与规则引擎实时重算**零差异** —— 影子表数据与读路契约正确；
- `limit_state_v2 != 1` 的行全部 `limit_state_missing` 且 `data_insufficient`（该四窗口内无 rule_unknown 实例），无一条 verified 被误置 missing；
- `limit_rule_id_v2` 100% 覆盖 —— 每条 v2 判定可追溯到规则。

*两个窗口行数接近为巧合（相邻交易日股票池规模相当），逐窗明细见 JSON。
