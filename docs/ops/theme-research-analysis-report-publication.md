# Theme Research 分析报告发布运维手册

本文档覆盖后台生成、固定目录索引、管理员审核和全员阅读链路。前台不提供“生成报告”或“上传报告”能力；生成系统负责产出最终文件，Web 服务只读取已定稿文件并管理审核状态。

## 生产配置

在应用服务和一次性运维命令中设置同一组环境变量：

```bash
export THEME_RESEARCH_REPORT_ROOT=/srv/stock-research/theme-research-reports
export THEME_RESEARCH_REPORT_SCAN_INTERVAL_SECONDS=60
export THEME_RESEARCH_REPORT_MAX_MANIFEST_BYTES=65536
export THEME_RESEARCH_REPORT_MAX_MARKDOWN_BYTES=10485760
export THEME_RESEARCH_REPORT_MAX_PDF_BYTES=52428800
export THEME_RESEARCH_MIGRATION_SERVICE=stock_research
export THEME_RESEARCH_RUNTIME_SERVICE=theme_research_runtime
```

- `THEME_RESEARCH_REPORT_ROOT` 必须使用跨 release 持久化的绝对目录；不得放在每次发布会替换的代码目录、临时目录或容器可写层。
- 未显式设置根目录时，程序回退到 `STOCK_RESEARCH_REPORTS_ROOT/theme-research`。生产环境必须显式设置，避免 release 切换后指向不同位置。
- 四个数值必须是正整数。上线前按实际报告上限设置，避免正常文件被拒绝，也不要无边界放大。
- migration service 用于建表和校验 DDL；runtime service 仅拥有索引、审核所需的最小表权限。

## 固定目录与 manifest 合同

每个版本只允许位于两级目录下：

```text
/srv/stock-research/theme-research-reports/
└── ai_power_value_capture_v1/
    └── 2026-08-01.1/
        ├── report.md
        ├── report.pdf          # 可选
        └── manifest.json       # 最后写入
```

`theme_id` 和 `version` 必须分别等于目录名。目录、manifest 或 artifact 不得是符号链接；artifact 路径必须是版本目录内的单段相对文件名，不能是绝对路径或包含 `..`。Markdown 必填，PDF 可选。

示例 `manifest.json`：

```json
{
  "schema_version": "theme_research_report_manifest_v1",
  "theme_id": "ai_power_value_capture_v1",
  "version": "2026-08-01.1",
  "title": "AI供电产业链分析报告",
  "summary": "覆盖供电、液冷与电网侧价值量。",
  "generated_at": "2026-08-01T10:00:00+08:00",
  "generator": {
    "name": "theme-research-report-pipeline",
    "version": "1.0.0"
  },
  "artifacts": {
    "markdown": {
      "path": "report.md",
      "sha256": "<report.md 的 64 位小写 SHA-256>"
    },
    "pdf": {
      "path": "report.pdf",
      "sha256": "<report.pdf 的 64 位小写 SHA-256>"
    }
  },
  "metadata": {
    "pipeline_run_id": "run-20260801-001"
  }
}
```

所有顶层字段均为合同字段，不能添加未知顶层字段。`generated_at` 必须是带时区的 ISO-8601 时间。JSON 必须为 UTF-8、无重复键、无 `NaN`/`Infinity`。SHA-256 必须与最终文件字节完全一致。

## 写入与目录权限

生成系统拥有报告根目录的写权限，Web 运行账户只需要对根目录、主题目录、版本目录的遍历/读取权限，以及对最终 Markdown、PDF、manifest 的只读权限。Web 账户不得修改、删除或覆盖 artifact。

推荐发布顺序：

1. 在报告根同一文件系统内、由生成账户独占的隐藏 staging 目录生成 Markdown/PDF。
2. 计算最终字节的 SHA-256，生成 manifest；manifest 最后写入。
3. 对该版本 staging 目录执行 `chgrp stock-research-readers`，目录设为 `0750`、文件设为 `0440`；确认 Web 运行账户可遍历并读取，但不能写入。
4. `fsync` 文件和目录后，将完整版本目录原子重命名到 `<theme_id>/<version>`；移动后再次校验属组、权限、checksum 和非符号链接约束。
5. 定稿后不得修改该版本内任何字节。需要修订时使用新版本目录。

扫描器忽略隐藏目录和 `.tmp` 目录，但不要依靠忽略规则代替原子定稿。首次建立根目录时，使用 setgid 让新建的主题、staging 和版本目录继承 readers 组；支持 POSIX ACL 的系统再设置默认 ACL，确保生成器新建或原子移动的后续文件持续具有组读取权限：

```bash
install -d -o report-generator -g stock-research-readers -m 2750 /srv/stock-research/theme-research-reports
setfacl -m g:stock-research-readers:rx,d:g:stock-research-readers:rx /srv/stock-research/theme-research-reports
```

若部署环境不支持默认 ACL，生成器必须在每个版本原子移动前显式执行上面的逐版本 `chgrp`/`chmod`，不能只在上线时递归修复一次。生成账户需在定稿前拥有 staging 写权限；Web 账户通过 `stock-research-readers` 组读取。不要给 Web 账户目录写权限。

修复已有报告树权限属于维护操作。先停止或暂停生成器，确认隐藏 staging 目录为空且没有正在写入的版本，再执行；否则递归修改可能与写入、checksum 或原子定稿竞争：

```bash
test -z "$(find /srv/stock-research/theme-research-reports -mindepth 1 -maxdepth 2 -type d -name '.*' -print -quit)"
chown -R report-generator:stock-research-readers /srv/stock-research/theme-research-reports
find /srv/stock-research/theme-research-reports -type d -exec chmod 2750 {} \;
find /srv/stock-research/theme-research-reports -type f -exec chmod 0440 {} \;
find /srv/stock-research/theme-research-reports -type d -exec setfacl -m g:stock-research-readers:rx,d:g:stock-research-readers:rx {} \;
find /srv/stock-research/theme-research-reports -type f -exec setfacl -m g:stock-research-readers:r {} \;
```

完成后以生成账户创建一个 staging canary，并以 Web 账户验证可读不可写；删除 canary 后再恢复生成任务。若系统没有 `setfacl`，省略 ACL 命令并确认生成器的逐版本权限步骤已启用。

## Schema 与首次扫描

先备份数据库并确认 Theme Research 基础 schema 已存在，再使用 migration service 应用独立报告 schema：

```bash
python -m stock_research.theme_research_report_schema --apply
```

成功输出示例：

```json
{"schema_version":"3","service":"stock_research","status":"ok"}
```

随后用 runtime service 对固定根目录执行一次扫描：

```bash
python -m stock_research.theme_research_report_index --root /absolute/report/root
```

成功输出包含 `discovered`、`indexed`、`unchanged`、`invalid`、`errors`、`started_at` 和 `completed_at`：

```json
{"completed_at":"2026-08-01T02:01:01+00:00","discovered":1,"errors":[],"indexed":1,"invalid":0,"started_at":"2026-08-01T02:01:00+00:00","unchanged":0}
```

退出码：`0` 表示没有无效版本；`2` 表示发现版本级错误；`3` 表示根目录/配置等全局错误。重复扫描已登记且字节一致的版本应显示在 `unchanged`，不会重复创建审核事件。

## Scheduler 与诊断

应用启动后立即扫描一次，并按 `THEME_RESEARCH_REPORT_SCAN_INTERVAL_SECONDS` 周期扫描。只有 admin 可读取：

```text
GET /api/admin/theme-research/report-index/status
```

典型响应：

```json
{
  "status": "ok",
  "running": false,
  "last_started_at": "2026-08-01T02:01:00+00:00",
  "last_completed_at": "2026-08-01T02:01:01+00:00",
  "last_result": {
    "discovered": 1,
    "indexed": 0,
    "unchanged": 1,
    "invalid": 0,
    "errors": [],
    "started_at": "2026-08-01T02:01:00+00:00",
    "completed_at": "2026-08-01T02:01:01+00:00"
  }
}
```

`never_run` 只应短暂出现；`running` 表示扫描中；`error` 表示可重试扫描失败；`fatal` 表示文件描述符、内存、磁盘配额或空间等资源耗尽，scheduler 会停止继续循环，必须先消除资源问题并重启服务。

## Canary 审核与发布

1. 选择一个内部 canary 主题，生成全新版本并执行 one-shot scan。
2. 确认 CLI `invalid=0`、`indexed=1`，诊断 endpoint 为 `ok`。
3. 用普通账号确认该 pending 版本在主题摘要、历史列表、文档和 PDF endpoint 均不可发现。
4. 用 admin 打开“报告审核”，核对标题、摘要、生成时间、安全渲染后的正文和 PDF。
5. 批准后用普通账号确认“在线阅读”、PDF 下载和历史版本均正常；检查响应不包含服务器相对路径或 checksum。
6. 再扩展到其余主题。拒绝时填写可操作原因，生成系统用新版本修复，不覆盖被拒版本。

前台审核请求受登录、admin 角色和 CSRF 保护。不要直接修改数据库状态绕过审核事件。

## 回滚、归档与恢复

- 应用代码回滚：保留报告根目录和报告表，不删除文件、不回退审核数据。旧 release 若不认识新 schema，应先验证兼容性；报告 root 必须继续挂载到相同绝对路径。
- 发布新版本：批准时系统原子地将原 current 版本改为 `archived`，并将新版本改为 `published`。归档版本继续作为已批准历史可读。
- 内容回滚：不要修改已发布/归档版本，也不要把数据库状态手工改回去。将需恢复的旧内容复制为一个新的不可变版本、生成新的 checksum/manifest、扫描并由 admin 批准；这样保留完整审计链。
- 灾难恢复：数据库报告表、审核事件表与整个报告根目录必须作为同一恢复点备份。先恢复文件根，再恢复数据库，校验所有已发布/归档记录的 artifact checksum，最后启动 Web/scheduler。
- 误删文件：先从报告根备份恢复相同字节和权限；checksum 校验通过后再恢复服务。不能用相似内容替代相同版本。

## Checksum 与版本冲突

同一 `(theme_id, version)` 一旦登记即代表不可变内容：

- 若重复扫描字节完全一致，结果为 `unchanged`。
- 若 manifest、Markdown 或 PDF 字节改变，扫描会报告 checksum/version 冲突。立即停止该生成任务，保留错误日志，不要覆盖数据库 checksum。
- 正确处理方式是恢复原始字节，或使用新的 `version` 目录重新生成和审核。
- 不要删除数据库行后重用旧版本号；这会破坏审核事件、历史链接和审计证据。
- `MANIFEST_DISCOVERY_CHANGED`、`ARTIFACT_FILE_CHANGED` 表示扫描期间文件发生变化，应检查生成器是否在 final 目录继续写入。

## 备份、监控与告警

备份必须覆盖：

- PostgreSQL 的 `research.theme_research_report_version` 和 `research.theme_research_report_review_event`，以及其依赖的 Theme Research/identity 数据；
- `THEME_RESEARCH_REPORT_ROOT` 全量文件、权限和目录结构；
- 部署配置中 report root 的绝对路径和 runtime/migration service 映射。

至少监控并告警：

- 诊断状态连续两次不是 `ok`，或启动后长时间为 `never_run`；
- `invalid > 0`、任意 `errors[].code`、CLI 非零退出码；
- `last_completed_at` 超过两个扫描周期未推进；
- `fatal`、`THEME_REPORT_SCAN_RESOURCE_EXHAUSTED`、文件描述符/内存/磁盘空间/配额告警；
- pending 队列积压时间和数量异常；
- 普通用户报告 endpoint 的 401/403/404/5xx 突增，或 PDF checksum/read 失败；
- report root 挂载丢失、只读挂载异常或 release 后路径变化。

定期做恢复演练：在隔离环境恢复数据库与 report root，执行 schema inspection、one-shot scan（应以 `unchanged` 为主），再验证 admin 审核和普通用户读取。演练不得连接生产写服务。
