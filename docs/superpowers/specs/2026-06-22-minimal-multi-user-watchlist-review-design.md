# Minimal Multi-User Watchlist And Review Design

## Goal

在现有官方研究与复盘系统之上，引入第一版最小多用户能力，使管理员能够创建用户，用户能够登录、维护自己的私有观察池，并记录自己的复盘，而不改变官方复盘对象和官方策略链路。

本次设计只做：

- 管理员创建用户
- 账号密码登录
- 每个用户一个私有观察池
- 每个用户一套私有复盘记录
- 用户可查看官方复盘

本次不做用户自定义策略平台。

## Scope

本次范围包括：

- 用户表与基础认证
- 管理员级用户管理入口
- 用户私有观察池数据模型与 API
- 用户私有复盘记录数据模型与 API
- dashboard 中新增“我的观察池”和“我的复盘”入口
- 官方复盘与个人复盘并存，但对象完全分开

## Non-Goals

本次不做：

- 公开注册
- 邀请码注册
- 企业 SSO / 第三方登录
- 多观察池
- 用户修改官方复盘
- 用户自定义策略
- 用户回测/回撤
- 团队共享观察池
- 完整的后台管理系统

## Product Boundary

### Domain Split

第一版产品必须明确拆成三域：

- `官方域`
  - 官方策略
  - 官方复盘队列
  - 官方 `Daily Review Lite`
  - 普通用户只读

- `用户域`
  - 用户账号
  - 用户私有观察池
  - 用户私有复盘记录

- `管理域`
  - 管理员创建用户
  - 重置密码
  - 启用/停用账号

### Official Vs Personal Review

官方复盘与个人复盘并存，但完全分开。

第一版规则：

- 用户可以查看官方复盘
- 用户不能修改官方复盘
- 用户复盘是自己的记录对象，不挂接到官方复盘对象里

这意味着：

- 官方 `Daily Review Lite` 继续是系统产物
- 用户复盘只是用户自己的 review journal

### Watchlist Model

第一版每个用户只有一个默认私有观察池。

不做：

- 多观察池
- 官方观察池与个人观察池混合 filter
- 观察池共享

这样可以把第一版数据隔离压到最简单的边界上。

## Authentication And Access Model

### User Creation

第一版采用管理员创建用户，不开放公开注册。

管理员能力：

- 创建用户
- 重置密码
- 启用/停用用户

普通用户能力：

- 登录
- 查看官方复盘
- 管理自己的观察池
- 管理自己的复盘记录

### Login Method

第一版采用账号密码登录。

最小字段支持：

- `username` 或 `email`
- `password_hash`
- `is_active`
- `is_admin`

可以使用 session cookie 或签名 cookie，但服务端必须能识别当前用户身份。

### Permission Rules

普通用户：

- 可读官方复盘
- 可读写自己的观察池
- 可读写自己的复盘
- 不可读写其他用户私有数据
- 不可管理用户

管理员：

- 具备普通用户能力
- 额外具备用户管理能力

第一版故意不默认提供“管理员查看所有用户私有复盘”的产品入口，避免把管理能力与隐私数据审阅能力绑定在一起。

## Data Model

### users

用途：系统登录主体。

建议字段：

- `id`
- `username`
- `email`
- `password_hash`
- `display_name`
- `is_active`
- `is_admin`
- `created_at`
- `updated_at`
- `last_login_at`

### user_watchlist_items

用途：用户默认私有观察池中的标的集合。

建议字段：

- `id`
- `user_id`
- `asset_id`
- `trade_date_added`
- `source`
- `notes`
- `created_at`
- `updated_at`

约束：

- `user_id + asset_id` 唯一

说明：

这张表就是“用户默认观察池成员表”。第一版不引入 `watchlists` 主表。

### user_review_sessions

用途：用户某日的一次复盘会话。

建议字段：

- `id`
- `user_id`
- `review_date`
- `title`
- `summary`
- `market_view`
- `position_view`
- `next_action`
- `created_at`
- `updated_at`

说明：

第一版允许一个用户同一天有多条复盘 session，避免过早把产品锁成“一天只能有一份复盘”。

### user_review_items

用途：复盘会话中的逐标的判断与记录。

建议字段：

- `id`
- `session_id`
- `user_id`
- `asset_id`
- `decision`
- `conviction`
- `tags`
- `notes`
- `follow_up_required`
- `created_at`
- `updated_at`

说明：

第一版 `tags` 可以直接存 JSON 数组，不必引入单独的标签维表。

## Backend API

### Authentication

建议接口：

- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`

### Admin User Management

建议接口：

- `POST /api/admin/users`
- `GET /api/admin/users`
- `POST /api/admin/users/{id}/reset-password`
- `POST /api/admin/users/{id}/disable`
- `POST /api/admin/users/{id}/enable`

### Personal Watchlist

建议接口：

- `GET /api/my/watchlist`
- `POST /api/my/watchlist/items`
- `DELETE /api/my/watchlist/items/{asset_id}`
- 可选：`PATCH /api/my/watchlist/items/{asset_id}`

规则：

- 仅允许操作当前登录用户的观察池

### Personal Reviews

建议接口：

- `GET /api/my/reviews`
- `POST /api/my/reviews`
- `GET /api/my/reviews/{session_id}`
- `PATCH /api/my/reviews/{session_id}`
- `DELETE /api/my/reviews/{session_id}`

复盘 item：

- `POST /api/my/reviews/{session_id}/items`
- `PATCH /api/my/reviews/{session_id}/items/{item_id}`
- `DELETE /api/my/reviews/{session_id}/items/{item_id}`

### Official Review APIs Stay Read-Only

现有官方复盘接口保持不变并继续只读：

- `GET /api/daily-review-lite`
- 官方 artifact endpoint
- 其他 dashboard 只读接口

第一版不要新增任何用户写官方复盘的接口。

## Frontend Product Shape

### Navigation

登录后 dashboard 左侧导航建议分成：

- `官方`
  - `复盘队列`
  - `Daily Review Lite`
  - `市场监控`
  - 其他官方 workspace

- `我的`
  - `我的观察池`
  - `我的复盘`

### My Watchlist

第一版 `我的观察池` 页面应非常轻：

- 搜索/添加标的
- 删除标的
- 修改 notes
- 查看加入时间

不要求第一版把它和官方观察池深度融合。

### My Reviews

第一版 `我的复盘` 不做成用户版 Lite 报告。

建议采用：

- 复盘列表页
- 复盘详情页

详情页结构：

- 顶部 session 字段：
  - `title`
  - `summary`
  - `market_view`
  - `position_view`
  - `next_action`
- 下方 item 列表：
  - 标的
  - 决策
  - 信心
  - 标签
  - 备注
  - follow-up 标记

### Official And Personal Coexistence

用户登录后可以：

- 看官方复盘
- 管理自己的观察池
- 写自己的复盘

但第一版不要把用户内容直接嵌进官方复盘对象里。

最多只做两个轻联动：

- `加入我的观察池`
- `以当前 trade_date 新建我的复盘`

## Rollout Strategy

第一版 rollout 应保持保守：

- 官方复盘功能不变
- 用户观察池和用户复盘作为新域引入
- 不重做 `Daily Review Lite`
- 不引入用户自定义策略

目标不是把平台一次做成完整多租户策略系统，而是先验证：

- 多用户是否真的有观察池与私有复盘需求
- 官方复盘与个人复盘并存是否顺手

## Risks And Mitigations

### Risk 1: Official And Personal Data Coupling

如果把用户复盘直接绑到官方复盘对象上，后续权限和审计会很难理清。

Mitigation:

- 第一版对象完全分开
- 用户只读官方域

### Risk 2: Too Much Product Scope

如果第一版同时做多观察池、自定义策略、回测，会把复杂度放大到平台级重构。

Mitigation:

- 每用户单观察池
- 只做复盘记录流
- 自定义策略延后

### Risk 3: Overpowered Admin

如果管理员天然能看所有用户私有复盘，会放大隐私与审计问题。

Mitigation:

- 第一版仅赋予用户管理能力
- 私有复盘查看能力后续单独设计

## Success Criteria

第一版完成后，应满足：

- 管理员可创建、启停、重置用户
- 用户可用账号密码登录
- 用户可查看官方复盘
- 用户拥有一个默认私有观察池
- 用户可新增/删除/备注自己的观察池标的
- 用户可创建和维护自己的复盘记录与复盘 item
- 用户不可修改官方复盘
- 用户不可访问其他用户私有数据
- 整套模型不引入用户自定义策略能力
