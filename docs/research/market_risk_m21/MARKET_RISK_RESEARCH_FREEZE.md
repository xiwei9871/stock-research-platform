# 研究封版（M1→M2.1 五轮收口）

| 能力 | 最终状态 |
|---|---|
| 历史风险周期识别 | VERIFIED（19系统性周期,并查集） |
| 市场情绪强度 | VERIFIED（描述层） |
| 市场广度持续性 | VERIFIED（描述层） |
| 量能持续性 | VERIFIED（描述层） |
| ETF资金配置观察 | LIMITED（深度/时长/速度可用;扩散DATA_MISSING） |
| 市场压力状态识别 | LIMITED（域标注可用;G模型未验证） |
| 市场修复状态识别 | LIMITED（描述层;H模型修正后无区分力） |
| 重大风险事前预警 | **NOT_SUPPORTED**（三轮一致） |
| 未来回撤概率校准 | NOT_CALIBRATED |

## READY_FOR_MONITOR_V2
情绪五分量、lowvol/广度streak与比率、mcc指标、ETF READY观察项、dd120周期状态、修复进程描述。

## RESEARCH_ONLY
联合条件信号（POST_HOC）、持续性状态机变体、ETF B3单特征、cyb持续性覆盖个案。

## FROZEN
ETF预测建模（重启条件见ETF_FUTURE_REOPEN_CRITERIA.md）、E/F/G/H预测模型、"事前重大回撤预警"课题——在出现新独立数据与预注册新方案前不再开轮。
