# UI/UX 与研究工作流评审 V0.2

基线 `9bd95562`。本轮只读代码，没有启动前端，也没有访问线上站点的具体页面。下文 `CV` = 代码中已核实（CODE_VERIFIED），`INF` = 推断（INFERRED）。

## 1. 导航现状

`dashboard/src/components/AppShell.tsx:84-113`：普通用户 15 项，管理员另外 2 项（`ADMIN_NAV_ITEMS`）。CV

| 类型 | 导航项 |
|---|---|
| 用户任务入口（9） | 首页、复盘队列、每日复盘、市场监控、新闻、研报、个股工作台、观察池、主题研究 |
| 技术或模块页（6） | 能力研究、Docling 报告审计、卡脖子复盘、因子实验室、策略实验室、生成报告 |
| 管理（2） | 报告审核、用户管理 |

以上分类是我的判断（INF）。问题在于：任务入口和"模块的产物浏览页"平铺在同一层，用户要先知道某个结果是哪个模块产出的，才知道去哪里找。

## 2. 页面 → API → 数据来源（摘要）

| 页面 | 主要数据来源 | 备注 |
|---|---|---|
| 首页 | platform summary、readiness、market-monitor、review-queue、publish-gate、strategy-score-audit 等 | 汇总入口，但不能直接从这里进入某只股票 |
| 复盘队列 | manifest 优先，读取 `artifact_path` 指向的 CSV；没有时回退到数据库行 | 显示 `run_id`，CV |
| 个股工作台 | `core.asset_master`、行业概念、`factor_daily`、`finance.*`、东财行情快照 | 数据全部来自数据库，不读任何策略产物，CV |
| 因子实验室 | `factor.factor_daily` | 只有因子库和评分预览，**没有 IC 结果** |
| 策略实验室·验证 | **fixture**（`strategy_validation.py:313` 写死的示例 run） | 把示例数据当成真实结果展示，CV |
| 策略目录 | 代码里写死的指标和 `as_of_date`（`strategy_catalog.py:58,97,139`） | 日期停在 2026-06，CV |
| 能力研究 | `outputs/research/cap_workbench/<theme>/index.json` | 只能按主题进入 |
| 观察池 | `watchlist.watchlist_daily_signal` | 只读，没有写入 API |
| 市场监控 | `research.market_emotion_state_daily` 等 | 没有数据时回退到 mock 或兜底数据 |

## 3. 模拟一次个股研究

样本：10-29 Tech Bottleneck 排名第 1 的候选。

| 步骤 | 实际路径 | 跳转次数 | 问题 |
|---|---|---|---|
| 发现 | 首页 → 复盘队列 → 条目 | 2 | 首页没有直接进入个股的入口，CV |
| 进入个股页 | `onOpenStock` 只修改 React 状态，不修改 URL | +1 | 刷新、后退、分享都会丢失当前股票，CV |
| 看基本面 | 个股页的业务质量、公司基础信息区块 | 0（向下滚动） | 可以看到 |
| 看估值 | 后端已经计算 `valuation_snapshot`（PE-TTM、PB，`asset_profile.py:68,315-340`），**前端没有任何组件引用它** | — | 数据存在但用户看不到，CV |
| 看"谁标记了它、什么时候" | 个股页只显示 watchlist 信号和一个 evidence-digest 的 run_id | — | **这个信息在任何地方都没有**，CV |
| 看数据截止时间和可信度 | 图表显示"截至 {endDate}"；复盘队列有分组新鲜度标签 | 部分 | 个股页没有"正式发布 / 实验 / 降级"的区分，CV |
| 加入观察 | 没有 POST/PUT watchlist 的路由 | — | **做不到**，CV |
| 能力研究跳回个股 | 普通 `<a href>` 链接，整页刷新 | — | 上下文丢失，CV |

## 4. 可信数据表达

| 问题 | 位置 | 影响 |
|---|---|---|
| 默认展示日期写死 `2026-06-18` | `AppShell.tsx:115`（readiness 和 summary 都失败时使用）、`DataExplorerWorkspace.tsx:7` | 回退时没有任何提示（INF：代码里没找到提示横幅） |
| 市场监控默认日期 `2026-06-12`，取自 mock 模块 | `market-monitor/mockData.ts:76` | 用户可能把 mock 数据当成真实行情 |
| 卡脖子页面是打包进前端的静态数据（快照日期 2026-07-02） | `techBottleneckReadonlyData.ts` 等 | 不随每日运行更新 |
| 策略指标和日期写死 | `strategy_catalog.py` | 首页展示的是 6 月份的指标 |
| 验证数据来自 fixture | `strategy_validation.py:313` | 最严重：把示例数据当作研究证据展示 |
| 不能从页面直接打开运行证据 | 复盘队列只显示 run_id，没有 manifest 详情页 | 无法追溯 |
| 多市场显示 | `StockWorkspace.tsx:150` 把以 "6" 开头的代码判为 `.SH`，其余都判为 `.SZ`（BJ 股票会被标错）；`HomeCockpit.tsx:88` 写死 `Asia/Shanghai`；全站没有币种字段，单位"元/亿"直接写在标签文字里 | 代码 CV |

## 5. 目标信息架构（DESIGN，不要求现在改导航）

我不建议按"今日 / 发现 / 研究 / 验证 / 跟踪"五个动词来分。原因是用户每天实际做的事情是"处理变化"，研究对象是股票和主题。所以建议按**研究对象 + 每日处理**组织：

| 一级 | 内容 | 由哪些现有页面合并或下沉而来 |
|---|---|---|
| 今日 | 运行状态（含失败和降级）、新出现或发生变化的研究线索、待复核事项 | 首页、复盘队列、每日复盘 |
| 股票 | 个股页（URL 带代码）：基础信息、估值、财务、**研究线索时间线**、证据、观察状态 | 个股工作台、研报、新闻（作为个股页的标签页） |
| 主题 | 主题和产业链、CAP 结果、成分股（可跳到个股页） | 主题研究、能力研究、卡脖子复盘 |
| 市场 | 市场监控、板块、资金 | 市场监控 |
| 实验室 | 因子、回测、数据探查、Docling 审计 | 因子实验室、策略实验室、生成报告（降为二级） |

核心不在页面怎么排，而在后端先提供三个跨模块的数据契约：
1. `GET /api/assets/{asset_id}/leads`：研究线索时间线，见 RUNTIME 报告 §4 的方案 C。
2. 每个 API 响应带统一的 `provenance` 块：`as_of`、`run_id`、`status`（official / experimental / fixture / fallback）、`source`、`currency`、`timezone`。
3. 观察池写入 API，并且只保留一个写入方。

## 6. 断点排序（按对用户的影响）

1. 策略实验室的验证页展示 fixture 数据。
2. 没法加入观察池。
3. 个股页看不到"谁、什么时候标记了它"。
4. 估值已经计算出来但没有展示。
5. 写死的默认日期和 mock 数据在回退时静默生效，没有提示。
6. 股票不在 URL 里，刷新、后退、分享都会丢失。
7. 个股页没有可信度标签。
8. 17 个导航项平铺，任务入口和模块页混在一起。
