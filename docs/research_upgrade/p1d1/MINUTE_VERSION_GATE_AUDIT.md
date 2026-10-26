# P1d.1 MINUTE_VERSION_GATE_AUDIT — 分钟资格绑定真实 ledger/版本

## 口径

分钟资格不再由 `stock_minute_bar` 行数推断，改由 R2/P1c 数据链的完成凭证决定：

| 证据源 | 用途 |
|---|---|
| `outputs/research/data01r1_finance_q2_20261020/r2_downstream_minute_done.json` | 分钟 done key 台账（qfq 派生验证通过才写入） |
| `outputs/research/data01r1_finance_q2_20261020/factor_gap_155_reconciliation.json` | 终态 FACTOR_GAP 隔离清单 |
| `factor.technical_feature_rebuild_state` | features pin 完成状态（`full_history_v1`） |
| `core.asset_status_daily` / `market.stock_minute_bar` | 状态与行情本体（行数仅作旁证） |

## 审计结果（与 P1c 基线一致）

| 指标 | 值 |
|---|---|
| 分钟 done keys / 资产 | **3,077 keys / 2,293 股** |
| 终态 FACTOR_GAP 资产 | **74 股** |
| 其中备用源已覆盖 done | **59 股**（按实际 source/version 判定为分钟可用） |
| 无任何 done key | **15 股**：600058, 600095, 600107, 600130, 600156, 600165, 600169, 600222, 600360, 600590, 600717, 603721, 688689, 002155, 301117 |
| POST_DIFF 审计隔离 | **CN:SH:600153**（保持隔离，不因其他凭证解封） |

## 判定规则验证（tests/test_tradeability_p1d1.py 覆盖）

- `full_history_v1 pinned complete` **不解除**分钟 FACTOR_GAP —— 日频资格与分钟
  资格独立维度，features pin 只证明日频因子版本，不证明分钟 key 存在；
- 59 只备用源覆盖资产按 done ledger 中实际 `source/version` 放行分钟资格；
- 15 只无 done key 资产即使 `stock_minute_bar` 有原始行也**不得放行**——行数
  不证明 qfq 派生验证通过；
- 600153 维持 POST_DIFF 隔离；
- `data_ready_minute` 与 `data_ready_daily` 独立返回，研究可用性与真实交易资格
  分别表达；
- `data_quality_blocks` 不再作为唯一阻断依据——阻断由 ledger 凭证推导。

## 产物

`TRADEABILITY_FAIL_CLOSED_TESTS.json::minute_gate` 含上述全部数值与清单，
由 `scripts/p1d1_audit.py` 每次运行从台账实时重算。
