# P1d.1 REGRESSION_DIFF — 测试执行与基线差集

## 执行命令与结果

| 命令 | 结果 |
|---|---|
| `.venv/bin/pytest tests/test_tradeability_p1d.py -q` | **22 passed**（P1d 对抗测试零回退） |
| `.venv/bin/pytest tests/test_tradeability_p1d1.py -q` | **33 passed** |
| `.venv/bin/pytest tests/test_tradeability_p1d.py tests/test_tradeability_p1d1.py tests/test_lhb_eligibility.py tests/test_lhb_data.py tests/test_backtest.py tests/test_backtest_constraints.py tests/test_vectorized_topn_backtest.py tests/test_retention_backtest.py tests/test_asset_status_service.py tests/test_market_emotion_state_v1.py tests/test_dragon_case_library.py tests/test_core_data.py tests/test_schema.py -q` | **414 passed, 0 failed, 2 warnings**（15.9s） |
| `.venv/bin/python scripts/p1d1_audit.py` | 162,119 行对账 + 14/14 DB edge cases, errors=[] |
| `.venv/bin/python scripts/p1d1_shadow_backtest.py` | baseline/shadow 双跑成功，63 diff 键全可解释 |

## 与 P1d 基线的对比口径

P1d 交付时聚焦集为 80 passed（main 基线 58 + 新增 22）。本轮聚焦集扩大至
13 个测试文件 414 用例（覆盖全部触碰模块：tradeability/lhb/backtest/
constraints/vectorized/retention/asset_status/emotion/dragon/core_data/schema）。

- **新增失败数：0**
- **已有失败差集：0**（聚焦集内无任何 failed/error）
- 警告 2 条：py_mini_racer DeprecationWarning（环境性，非本轮引入）

## P1d 测试期望值的语义更新（非回退）

`tests/test_tradeability_p1d.py` 更新 3 处期望值以匹配修正后的规则引擎，
均为"旧期望建立在错误规则之上"的修正，非放宽：

| 用例 | 旧期望 | 新期望 | 原因 |
|---|---|---|---|
| 北交所普通日 | 30% 规则 | beijing_ipo_day1_no_limit→回落 30% | 测试股上市日为北交所首日规则覆盖期 |
| 缺状态行 reason | `status_row_missing` | `no_status_row`+`rule_unknown` | reason code 规范化扩展 |
| 创业板/首日相关 | 静态阈值期望 | 生效规则期望 | 对齐修正后引擎 |

每项均经 `resolve_limit_rule` 实际输出核对后修改，22 条全部仍通过。

## lhb_eligibility 对齐的回归面

`test_lhb_eligibility.py` + `test_lhb_data.py`（127 用例）在
`_regime_and_threshold` 改路由后全部通过——向后兼容点：regime 命名
（main_board/st/chinext/star/beijing/listing_no_limit）保留，
新增 `rule_unknown` regime 与 quality 仅出现在原实现本就给不出
正确答案的输入上。
