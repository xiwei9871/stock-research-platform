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
- 审计日志
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
- 用户版自动生成 Daily Review Lite 报告

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

数据库上只保留按交易日的弱关联：

- 官方复盘使用 `trade_date`
- 用户复盘也使用 `trade_date`
- 第一版不引入 `official_review_id` 或 `official_run_id`

这样前端可以从某个官方复盘页面跳转“以当前 `trade_date` 新建我的复盘”，但用户记录不依赖官方 run 生命周期。

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
- `role`
- `is_active`

服务端可使用 session cookie 或签名 cookie，但必须稳定识别当前用户身份，并满足以下安全要求：

- `password_hash` 不存明文，使用 `bcrypt` 或 `argon2`
- cookie 必须设置 `HttpOnly=true`
- 生产环境 cookie 必须设置 `Secure=true`
- cookie 建议设置 `SameSite=Lax`
- 只要使用 cookie 登录，所有 `POST/PATCH/DELETE` 都必须带 CSRF 防护
- `POST /api/auth/login` 必须有最小限度的失败限流，至少覆盖同一 IP 和同一 username 的连续失败场景

管理员创建用户时可设置初始密码。第一版可不强制首次登录改密，但系统必须记录 `password_updated_at`。

### Session Identity

`GET /api/auth/me` 必须返回当前身份与权限信息，至少包括：

```json
{
  "id": 1,
  "username": "xiwei",
  "display_name": "Xiwei",
  "role": "admin",
  "is_active": true
}
```

前端根据该接口决定是否显示管理入口。

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

### Review Item Authorization

`user_review_items` 的权限校验必须写死，不允许只按 `item_id` 更新。

所有复盘 item 操作必须同时满足：

- `item.user_id = current_user.id`
- `item.session_id = route.session_id`
- `session.user_id = current_user.id`

实现上建议所有读取、更新、删除都通过 `user_review_items` 与 `user_review_sessions` 的 join 完成，避免单表校验遗漏造成越权。

## Data Model

### users

用途：系统登录主体。

建议字段：

- `id`
- `username`
- `email`
- `password_hash`
- `display_name`
- `role`
- `is_active`
- `created_at`
- `updated_at`
- `last_login_at`
- `password_updated_at`
- `disabled_at`

约束：

- `username` 唯一
- `email` 可空但唯一
- `role in ('admin', 'user')`

说明：

- 第一版使用 `role`，不再使用 `is_admin`
- `disabled_at` 与 `is_active` 一起支持停用审计和状态表达

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
- `deleted_at`

约束：

- `user_id -> users.id`
- `asset_id -> assets.id` 或现有股票主表
- 仅在 `deleted_at IS NULL` 时保证 `user_id + asset_id` 唯一

说明：

- 该表就是“用户默认观察池成员表”，第一版不引入 `watchlists` 主表
- 删除观察池成员使用软删除，保留加入/移除历史
- 如果数据库为 PostgreSQL，建议使用 partial unique index 保证 active member 唯一

### user_review_sessions

用途：用户某个交易日的一次复盘会话。

建议字段：

- `id`
- `user_id`
- `trade_date`
- `title`
- `summary`
- `market_view`
- `position_view`
- `next_action`
- `created_at`
- `updated_at`
- `deleted_at`

说明：

- 第一版允许一个用户同一天有多条复盘 session，避免过早把产品锁成“一天只能有一份复盘”
- `trade_date` 记录复盘归属交易日，`created_at` 记录实际创建时间
- 删除 session 使用软删除

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
- `deleted_at`

建议枚举：

- `decision`: `watch`, `buy_candidate`, `hold`, `reduce`, `sell`, `avoid`, `unsure`
- `conviction`: `low`, `medium`, `high`

说明：

- 第一版 `tags` 可以直接存 JSON 数组，不必引入单独的标签维表
- `user_id` 保留为显式归属字段，便于权限与查询优化
- 删除 item 使用软删除

### audit_logs

用途：记录关键认证、管理和私有数据操作，作为第一版最小审计层。

建议字段：

- `id`
- `actor_user_id`
- `action`
- `target_type`
- `target_id`
- `metadata`
- `ip_address`
- `user_agent`
- `created_at`

第一版至少记录：

- `login_success`
- `login_failed`
- `logout`
- `admin_create_user`
- `admin_reset_password`
- `admin_disable_user`
- `admin_enable_user`
- `watchlist_add_item`
- `watchlist_remove_item`
- `watchlist_update_item`
- `review_create_session`
- `review_update_session`
- `review_delete_session`
- `review_create_item`
- `review_update_item`
- `review_delete_item`

## Backend API

### Authentication

建议接口：

- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`

规则：

- `login` 成功后建立 cookie session
- `logout` 失效当前 session 并记录审计日志
- `me` 返回当前用户身份和角色，用于前端路由守卫与导航显示

### Admin User Management

建议接口：

- `POST /api/admin/users`
- `GET /api/admin/users`
- `POST /api/admin/users/{id}/reset-password`
- `POST /api/admin/users/{id}/disable`
- `POST /api/admin/users/{id}/enable`

规则：

- 仅 `role=admin` 可访问
- reset password 由管理员直接设置新密码，不返回旧密码，也不保存明文
- 所有管理动作记录到 `audit_logs`

### Personal Watchlist

建议接口：

- `GET /api/my/watchlist`
- `POST /api/my/watchlist/items`
- `DELETE /api/my/watchlist/items/{asset_id}`
- 可选：`PATCH /api/my/watchlist/items/{asset_id}`

规则：

- 仅允许操作当前登录用户的观察池
- `DELETE` 实际执行软删除，即设置 `deleted_at`
- `GET` 默认只返回 `deleted_at IS NULL` 的 active items

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

规则：

- 所有 session 与 item 接口都只允许访问当前登录用户自己的数据
- `DELETE` 对 session 和 item 都执行软删除，即设置 `deleted_at`
- item 写操作必须同时校验 `session_id` 与 `user_id` 归属
- 所有创建、更新、删除动作记录到 `audit_logs`

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

- `管理`
  - `用户管理`
  - 仅 `admin` 可见

### My Watchlist

第一版 `我的观察池` 页面应非常轻：

- 搜索/添加标的
- 删除标的
- 修改 notes
- 查看加入时间

不要求第一版把它和官方观察池深度融合，也不要做成策略池。

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

这两个联动都只通过前端带入 `trade_date` 或 `asset_id`，不在数据库层建立对官方复盘 run 的强依赖。

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
- 仅通过 `trade_date` 做弱关联

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

### Risk 4: Review Item Authorization Drift

如果后端只按 `item_id` 更新或删除复盘 item，极易出现跨用户越权。

Mitigation:

- item 接口强制同时校验 `item_id + session_id + current_user.id`
- 查询统一走 `item JOIN session`
- 将该规则写入实现与测试要求

### Risk 5: History Loss From Hard Delete

如果观察池和复盘直接物理删除，会丢失用户行为轨迹和问题排查线索。

Mitigation:

- 第一版全面采用软删除
- 关键操作进入 `audit_logs`

## Success Criteria

第一版完成后，应满足：

- 管理员可创建、启停、重置用户
- 用户可用账号密码登录
- 登录链路具备密码 hash、cookie 安全属性、CSRF 防护和最小限流
- 用户可查看官方复盘
- 用户拥有一个默认私有观察池
- 用户可新增、软删除、备注自己的观察池标的
- 用户可创建和维护自己的复盘记录与复盘 item
- 复盘 session 与 item 默认采用软删除
- 用户不可修改官方复盘
- 用户不可访问其他用户私有数据
- 关键认证、管理和私有写操作会进入 `audit_logs`
- 整套模型不引入用户自定义策略能力
