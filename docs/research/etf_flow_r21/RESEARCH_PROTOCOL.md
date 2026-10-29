# ETF-FLOW-R2.1 研究协议

目标：验证 ETF 规模归一化资金流是否对未来 20–120 个交易日的**中期风险**提供增量信息。
非择时、非交易信号、非机构归因。research_only。

## 流程
1. `analyze_r21.py`：复用 R1.1/R2 衍生数据 → WP/AS 分数 → 状态机 → 前瞻风险/提前量/误报/A-B-C 增量 → 全部 CSV。
2. `plot_r21.py`：9 张 PNG。
3. `build_html_r21.py`：单文件离线 HTML。
4. `test_r21.py`：完整性断言。

## 口径
- `Fw(t) = 窗口净申购合计 / 窗口期初组合 AUM`（先合计金额、再除规模）。
- `WP = 0.4·pctl(-F20)+0.3·pctl(outshare20)+0.2·pctl(-F40)+0.1·pctl(-accel)`；AS 对称。
  百分位为扩展窗口、PIT、min 252 交易日。
- 状态机：NORMAL→WATCH(WP≥70,5d)→ELEVATED(WP≥80,5d)→HIGH_PRESSURE(WP≥85,10d 或 WP≥75 且 outshare40≥0.6,10d)；
  降级 RECOVERING(WP<60,5d 或 AS≥65,10d)→NORMAL(20d)。全部阈值预注册（见 PRE_REGISTERED_RULES.json），未回测调参。
- 风险事件：`fwd_mdd60 ≤ -10% / -15%`（严格峰谷）。
- A 价格基线：ret20≤-3% 或 vol60≥扩展 p80；B：WP≥70；C：A∨B。
- 校准：logistic 仅用 2020–2023 训练集拟合，OOS 直接应用。

## 样本划分
train 2020–2023 / valid 2024–2025 / 2026 touched（假设受 2026 案例启发，非盲测）。

## 数据
输入为 R1.1 修正序列（公司行为剔除口径 `flow_use`）。parquet 中间产物在 `data/`（未入库）。
