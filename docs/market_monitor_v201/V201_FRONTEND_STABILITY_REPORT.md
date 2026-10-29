# 前端稳定性修复
- useMemo 中 setOption（渲染期副作用）→ 全部移入 useEffect。
- ResizeObserver 改为图表初始化后才挂载（不再出现空挂载即占观察器；修复与热力图 RO 计数的竞态）。
- tradeDate/market 变化立即清空 payload+两张图——旧数据不会在请求途中冒名新日期。
- 新增错误态重试按钮（同日期重提交此前不会重取）。
- ECharts dispose/RO disconnect 在卸载时执行；监听器解绑。
- 快速切换市场/分组/日期由同一 effect 串行保证（cancelled 标志丢弃过期响应）。
- 443 前端测试 + tsc + vite build 通过；真浏览器交互验证（切换分组/日期/错误恢复）。
