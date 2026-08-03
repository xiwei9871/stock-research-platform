# AI Power Pending Report Pilot Runbook

本手册只用于生成并登记首份 AI 供电产业链人工审核初稿。执行结束时，报告必须保持 `pending_review`；本手册禁止批准、驳回、归档或公开发布。

## 不可变身份

- Theme：`ai_power_value_capture_v1`
- Version：`2026-08-03.1`
- Title：`AI供电产业链分析报告`
- Generator：`theme-research-report-pipeline/1.0.0`
- Pipeline run ID：`production-ai-power-pilot-20260803`
- Target database state：`pending_review`
- PDF：首轮不生成

## 固定路径

- 远端代码根：`/home/jqz/code/stock-research-platform-main`
- 报告宿主根：`/home/jqz/code/stock-research-platform-main/reports/theme-research`
- 容器报告根：`/app/reports/theme-research`
- 最终版本目录：`ai_power_value_capture_v1/2026-08-03.1`

API 服务对报告根只能使用只读挂载。仅一次性生成容器可以在本次执行中对报告根使用读写挂载；生成完成后立即退出。

## 执行顺序

1. 确认当前线上 release，并确认候选代码包含该线上版本之后的所有变更。
2. 确认最终版本目录不存在，数据库不存在相同 `(theme_id, version)`，报告根没有同名 staging。
3. 使用候选 API 镜像启动一次性生成容器：主题 artifacts 和 outputs 只读，报告根读写。
4. 生成器写入隐藏 staging、计算 Markdown SHA-256、最后写 manifest，并原子重命名为最终版本目录。
5. 使用只读容器调用正式 manifest loader，核对主题、版本、标题、文件边界和 checksum。
6. 通过 `theme_research_report_indexer` service 执行一次 one-shot scan。
7. 首次扫描必须为 `discovered=1`、`indexed=1`、`invalid=0`、`errors=[]`。
8. 第二次扫描必须为 `indexed=0`、`unchanged=1`，证明幂等。
9. 数据库必须恰好出现一条 `pending_review` 版本和一条 system 初始审核事件。
10. admin 审核队列必须出现该报告；approved-user 报告列表不得出现该 pending 版本。
11. 停止在 admin 预览页面，不发送 publish 或 reject 请求。

## 生成命令

在远端代码根执行以下完整命令。`PILOT_RELEASE_ID` 必须是已通过外网 release gate 的完整 Git SHA；容器使用部署用户 uid/gid，主题资料和 outputs 只读，只有专用报告根可写：

```bash
PILOT_RELEASE_ID=<完整发布SHA>
REMOTE_ROOT=/home/jqz/code/stock-research-platform-main

docker run --rm \
  --user "$(id -u):$(id -g)" \
  --mount type=bind,src="$REMOTE_ROOT/artifacts/theme_decomposition",dst=/app/artifacts/theme_decomposition,readonly \
  --mount type=bind,src="$REMOTE_ROOT/outputs",dst=/app/outputs,readonly \
  --mount type=bind,src="$REMOTE_ROOT/reports/theme-research",dst=/app/reports/theme-research \
  "stock-research-dashboard-api:$PILOT_RELEASE_ID" \
  python -m stock_research.theme_research_report_generator \
    --repository-root /app \
    --report-root /app/reports/theme-research \
    --theme-id ai_power_value_capture_v1 \
    --version 2026-08-03.1 \
    --generated-at 2026-08-03T10:00:00+08:00 \
    --pipeline-run-id production-ai-power-pilot-20260803
```

容器内的等价生成命令为：

```bash
python -m stock_research.theme_research_report_generator \
  --repository-root /app \
  --report-root /app/reports/theme-research \
  --theme-id ai_power_value_capture_v1 \
  --version 2026-08-03.1 \
  --generated-at 2026-08-03T10:00:00+08:00 \
  --pipeline-run-id production-ai-power-pilot-20260803
```

生成结果必须只有 `report.md` 和 `manifest.json`。不得手工修改生成后的任何字节。

## 索引命令

通过带有正式 env、PostgreSQL service 文件和只读报告挂载的 API one-shot 容器执行：

```bash
cd /home/jqz/code/stock-research-platform-main
PILOT_RELEASE_ID=<完整发布SHA>
STOCK_RESEARCH_RELEASE_ID="$PILOT_RELEASE_ID" \
STOCK_RESEARCH_FRONTEND_BUILD_ID="$PILOT_RELEASE_ID" \
DASHBOARD_REMOTE_ENV_FILE=/home/jqz/code/stock-research-platform-main/.dashboard_runtime_env \
DASHBOARD_PGSERVICE_FILE=/home/jqz/code/stock-research-platform-main/.pg_service.conf \
THEME_RESEARCH_REPORT_HOST_ROOT=/home/jqz/code/stock-research-platform-main/reports/theme-research \
docker compose --project-name stock_research_dashboard \
  -f deploy/dashboard-release.compose.yml \
  run --rm --no-deps api \
  python -m stock_research.theme_research_report_index \
    --root /app/reports/theme-research \
    --service theme_research_report_indexer
```

该 compose service 将报告根挂载为只读，并将 `.pg_service.conf` 只读挂载到 `/app/.pg_service.conf`。容器内的等价索引命令为：

```bash
python -m stock_research.theme_research_report_index \
  --root /app/reports/theme-research \
  --service theme_research_report_indexer
```

生成器不得直接写报告表；索引必须经 `theme_research_report_indexer_app` 的独立登录身份和登记函数完成。

## 数据库验收

```sql
SELECT report_version_id, theme_id, version, title, status, row_version
FROM research.theme_research_report_version
WHERE theme_id = 'ai_power_value_capture_v1'
  AND version = '2026-08-03.1';
```

要求恰好一行，`status='pending_review'`、`row_version=1`。

```sql
SELECT from_status, to_status, actor_user_id
FROM research.theme_research_report_review_event
WHERE report_version_id = '<上一步 report_version_id>'
ORDER BY created_at;
```

要求只有初始事件，`to_status='pending_review'`、`actor_user_id='system'`。

## 权限与页面验收

- `GET /api/admin/theme-research/reports?status=pending_review`：admin 可见且总数为 1。
- admin detail endpoint：可读取安全渲染后的完整正文。
- `GET /api/research/theme-decomposition/themes/ai_power_value_capture_v1/reports`：pending 版本不可见。
- 普通用户 direct document endpoint：pending 版本必须返回不可发现结果。
- `/admin/theme-research/report-review`：显示标题、版本、待审核状态和完整预览。
- 发布与驳回控件可以显示，但本手册禁止点击。

## 失败与重试边界

- 原子重命名前失败：生成器只清理自己的隐藏 staging，最终版本目录不得出现。
- 最终版本已存在：立即失败，禁止覆盖。
- manifest 或 checksum 无效且尚未索引：保留诊断，将无效目录移动到专用备份/隔离位置后使用新的版本号；不得原地修补。
- 已索引后发现内容问题：保留原版本和审核记录，使用新的不可变版本重新生成。
- 数据库登记失败：禁止手工插入或修改状态，修复 indexer/service 后重扫相同字节。
- 发布门禁、角色隔离或普通用户权限验证失败：停止，不生成生产报告或不宣称完成。

## 最终停止点

执行完成后的唯一允许状态：

```text
The report is ready for human review and remains pending_review.
No approval, rejection, archive, or public publication was performed.
```
