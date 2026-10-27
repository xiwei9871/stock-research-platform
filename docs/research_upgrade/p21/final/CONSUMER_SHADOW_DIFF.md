# P2.1-Final-B Shadow 修正核销（两级语义重算）

复现：`scripts/p21_consumer_shadow_v2.py` → `CONSUMER_SHADOW_CORRECTED.json` + `consumer_shadow_diff_v2.csv`（285,351 行）。

## v1 → v2 差异归因

| | v1（裸元组比对） | v2（两级选择） |
|---|---|---|
| 变化总数 | 286,704 | **285,351** |
| 报告期变化 | 283,392（含混口径） | **282,179** |
| 同期版本变化 | 未区分 | **6** |
| 来源变化 | 未区分 | **0** |
| 失去可用（corrected 无报表） | 未区分 | **3,166** |
| 公告证据不足（哨兵资产） | 未统计 | income 0 / balance 9 / cash_flow 11（单独标记，非变化） |

v1−v2 差 1,353：v1 的裸 (ann,rp) 比对会把"不同行但同 rp+同 ann"计为变化；v2 两级归并后不再重复计数。**headline 结论不变：约 28.5 万资产×日期级选择差异，98.9% 为报告期切换。**

## 真实路径抽样核验（非模拟器冒充）

对四条路径各抽真实资产，直接执行消费者真实 SQL（`ORDER BY announcement_date DESC, report_period DESC LIMIT 1`）与 shadow 选择器对比：**9/9 样本 `period_match=true`**（income 3 / balance 3 / cash_flow 3，见 CONSUMER_SHADOW_CORRECTED.json.real_path_spot_checks）。

顺带坐实第二个风险：income 样本真实选出 `source='baostock'`——真实路径在 ann+period 并列时**无 source 优先序、选源不稳定**，与 census 的跨源冲突结论互相印证。

## 仍未做

正式策略收益/换手/回撤差异——属修复阶段范围；本轮给出的受影响日期全集（1381 个评估日中命中的披露截止窗日期）即重验收范围。
