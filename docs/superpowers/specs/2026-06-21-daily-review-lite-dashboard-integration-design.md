# Daily Review Lite Dashboard Integration Design

## Goal

将 `Daily Review Lite` 从独立前端实现接入现有 `5174` 内网 dashboard，作为与 `复盘队列`、`市场监控`、`新闻` 等模块同级的二级 workspace，并让它成为“每日复盘报告”的正式 dashboard 入口之一。

本次设计聚焦于前端 dashboard 集成，不重做 Lite 后端 contract，不替换旧 `复盘队列`，也不在第一版中做深层跨模块联动。

## Scope

本次集成包括：

- 在现有 dashboard 左侧 workspace 导航中新增 `Daily Review Lite`
- 将该入口放在 `复盘队列` 和 `市场监控` 之间
- 进入该 workspace 时直接加载 Lite 主视图，不先增加选择页
- 使用 dashboard 级 URL 状态承载 `workspace` 和 `trade_date`
- 支持默认加载最近一个可复盘交易日
- 支持从 URL 中读取 `trade_date`
- 将现有 Lite 页面能力封装为 dashboard 内部 workspace，而不是独立替换首页
- 增加对应的 dashboard 级测试与 browser smoke

## Non-Goals

本次不做：

- 下线或替换现有 `复盘队列`
- 将 Lite 深度嵌入现有个股工作台、图表工作台或策略实验台
- 将 Lite 数据流并入当前 `App.tsx` 的大工作台数据请求链
- 改 Lite 后端 API contract
- 引入完整前端 router 体系
- 做“每天自动生成复盘报告”的后端调度或产物链路改造

## Product Direction

### Workspace Positioning

`Daily Review Lite` 第一版应作为现有 dashboard 的一个新增同级 workspace，并与旧 `复盘队列` 并存。

这不是临时跳转页，也不是独立 demo 入口，而是 dashboard 内正式的信息架构节点。

### Entry Behavior

点击 `Daily Review Lite` 后直接进入 Lite 主视图。

不增加中间选择页。默认行为为：

1. 若 URL 中存在合法 `trade_date`，优先使用该日期
2. 否则使用最近一个可复盘交易日

### Coexistence Strategy

第一版采取并存策略：

- 旧 `复盘队列` 保留
- 新 `Daily Review Lite` 作为并行入口上线
- 首页和旧工作台暂时不重定向到 Lite

这样可以先验证 Lite 是否能承接“每日复盘报告主入口”的职责，再决定是否做更深迁移。

## Frontend Architecture

### High-Level Structure

现有 `5174` dashboard 应继续保持单一前端入口，但内部改为“shell + workspace”结构。

建议拆分为两个层次：

- `DashboardShell`
  - 负责左侧导航
  - 负责 workspace 选中状态
  - 负责 URL 状态同步
  - 负责渲染当前 workspace 内容
- 各 workspace 页面
  - `WorkbenchWorkspace`
  - `DailyReviewLiteWorkspace`
  - 其他现有 workspace

### Why Not Keep Growing `App.tsx`

当前 [dashboard/src/App.tsx](/Users/xiwei/stock_research/dashboard/src/App.tsx) 已经承载了大量工作台聚合逻辑。如果直接把 Lite 逻辑继续叠加进去，会把：

- dashboard shell
- workspace 切换
- 工作台数据流
- Lite 数据流

混在一个更大的组件里，后续很难维护。

因此第一版应明确分离：

- shell 负责导航和入口
- Lite workspace 只负责 Lite 页面本身

### Workspace Routing

第一版不引入完整 router，使用轻量 URL 状态即可。

建议形态：

- `/?workspace=daily-review-lite`
- `/?workspace=daily-review-lite&trade_date=2026-06-19`

需要支持：

- 首次打开 dashboard 时根据 URL 选择 workspace
- 切换 workspace 时更新 URL
- Lite workspace 内切换日期时更新 `trade_date`
- 其他 workspace 不依赖 `trade_date` 时可忽略该参数

### Daily Review Lite Workspace

新增 `DailyReviewLiteWorkspace`，内部直接承载现有 Lite 页面能力。

它的职责应限定为：

- 读取 dashboard 传入的 `tradeDate`
- 调用现有 `/api/daily-review-lite`
- 渲染 Lite 视图

它不应承担：

- 旧工作台的行情图和个股交互
- 旧复盘队列的数据装配
- 跨策略实验数据聚合

## Page Structure Inside Dashboard

### Top Bar

Lite workspace 顶部保留完整模块栏，至少包含：

- 标题：`Daily Review Lite`
- `trade_date` 选择器
- 来源状态：`report.run` / `fallback` / `no run selected`
- run id
- artifact health
- 返回 dashboard 其他模块的清晰入口

### Main Content

主内容区继续使用现有 Lite section stack：

1. `Data Readiness`
2. `Market Review`
3. `Strategy Summaries`
4. `Holding Review`
5. `Operator Plan`
6. `Next-day Checklist`
7. `Artifacts`

### Dashboard-Level Linking

第一版只做轻联动：

- 从 dashboard 其他模块跳入 Lite 时可带 `trade_date`
- Lite 内保留跳回 `复盘队列` 或主 dashboard 入口
- 不做与个股工作台、图表区、实验面板的深联动

## Date Rules

### Priority

Lite workspace 的日期来源优先级：

1. 明确传入的 `trade_date` URL 参数
2. dashboard 内部跳转透传的日期
3. 最近一个可复盘交易日

### First-Version Fallback Rule

如果前端暂时没有后端“最近可复盘交易日”专用接口，允许第一版先使用本地日期规则：

- 工作日使用当天
- 周六回退到周五
- 周日回退到周五

但该逻辑必须是动态的，不能再冻结为固定历史日期。

## Testing Strategy

### Keep Existing Lite Coverage

现有 Lite 页面级测试继续保留，覆盖：

- 默认日期规则
- `ready`
- `partial`
- `empty`
- `failed`
- artifact URL contract

### Add Dashboard Workspace Tests

需要新增 dashboard workspace 级测试，至少覆盖：

- 左侧导航出现 `Daily Review Lite`
- 点击后 workspace 正确切换
- URL 中 `workspace` 和 `trade_date` 正确同步
- 通过 URL 直接进入 Lite workspace 时页面正确加载

### Browser Smoke

需要新增或扩展 `5174` dashboard 级 smoke，验证：

1. 打开 dashboard 首页
2. 点击 `Daily Review Lite`
3. 成功进入 Lite workspace
4. 可见：
   - `Daily Review Lite`
   - 来源标签
   - `Strategy Summaries`

### Verification Boundary

第一版不要求把所有旧 browser smoke 重构成新的 workspace-aware 套件，只补足 Lite 接入需要的覆盖。

## Rollout Plan

第一版 rollout 采取低风险策略：

- 新增 Lite workspace
- 保留旧 `复盘队列`
- 不调整其他 workspace 的数据装配方式
- 不改变 Lite 后端 API

这样可以让 dashboard 尽快获得“正式的每日复盘报告入口”，同时把回滚成本控制在最小范围。

## Risks And Mitigations

### Risk 1: `App.tsx` 继续膨胀

如果直接在现有 `App.tsx` 中叠加 Lite 状态和 UI，后续维护成本会快速上升。

Mitigation:

- 先拆出 shell / workspace 边界
- Lite 作为独立 workspace 页面接入

### Risk 2: Lite 与旧复盘强耦合

如果第一版就做深层联动，会放大范围并拖慢落地。

Mitigation:

- 第一版只做轻联动
- 保持并存

### Risk 3: 日期默认值再次冻结

固定历史日期会让 dashboard 默认打开时直接落到 stale/empty 状态。

Mitigation:

- 用 URL 参数或动态最近交易日规则
- 在测试中覆盖默认日期逻辑

## Success Criteria

集成完成后，以下条件应成立：

- `5174` dashboard 左侧出现 `Daily Review Lite` 同级入口
- 它位于 `复盘队列` 之后、`市场监控` 之前
- 点击该入口后直接进入 Lite 主视图
- 默认会加载最近可复盘交易日
- URL 可表达当前 workspace 和 `trade_date`
- 旧 `复盘队列` 继续可用
- Lite 页面和 dashboard 级测试均通过
- Lite browser smoke 通过
