# 回归报告
- 后端 pytest：test_market_regime_service.py **11 passed**（新增 PIT/AUM/版本切换/周期重置 4 项）+ monitor/emotion 回归 39 项早前通过。
- 前端：**443 passed / 41 files**；tsc+vite build 通过。
- 旧断言语义零改动（仅补 mock 与新增用例）。
- 修复中发现的真 bug：①etf_cycles 全局max泄漏；②eod缓存键缺版本；③同日期无法重试；④RO竞态——均已修复并有测试。
