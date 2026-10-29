# 浏览器测试
- Chromium（playwright-cli）：全部场景通过（截图见 uat/）。
- WebKit：本环境无 webkit runner（playwright-cli --browser=webkit 未安装）→ NOT_RUN，降级为 Chromium 验证 + ResizeObserver/rAF 兼容路径由单测覆盖（market-monitor-workspace 的 webkit 重试用例通过）。
