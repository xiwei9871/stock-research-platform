# Founder OS 模型恢复监督器运行手册

## 目标

当豆包主模型和 OpenAI fallback 同时不可用时，监督器等待任一模型恢复，并在当天北京时间窗口内补跑全部模型失败任务。它不增加第三模型，不跨日补跑，也不自动重试业务、权限、文件或工具错误。

## 模型策略

- 主模型：`volcengine-plan/doubao-seed-2.0-code`
- 唯一 fallback：`openai/gpt-5.4`
- 配置工具不会修改任何任务的 `model` 或 `fallbacks`

## 文件和状态

- 运行入口：`/Users/xiwei/.openclaw/bin/founder-os-model-recovery`
- 仓库脚本：`scripts/run_founder_os_model_recovery_cron.sh`
- 每日状态：`/Users/xiwei/.openclaw/state/founder-os-model-recovery/YYYY-MM-DD.json`
- cron 备份：`/Users/xiwei/.openclaw/state/founder-os-model-recovery/cron-backup-*.json`
- 运行日志：`/Users/xiwei/.openclaw/logs/founder-os-model-recovery.log`

状态项以 `(job_id, original_failed_run_id)` 去重。成功补跑的任务不会再次执行；北京时间跨日后创建新状态，不导入昨日待办。

## 配置预览

先执行：

```bash
rtk scripts/install_founder_os_model_recovery.sh --dry-run
```

预览必须满足：

- 只管理启用的 `agentTurn` cron；
- 排除 command 任务、`orchestration-dashboard-sync` 和监督器自身；
- 只关闭受管任务的逐条 failure alert；
- 新增一个每 20 分钟运行的 command supervisor；
- 将 `founder-os-cron-health-guard` 转为 deterministic audit command；
- 不出现 `--model` 或 `--fallbacks` 修改命令。

## 监督器 dry-run

```bash
rtk env PYTHONPATH=src .venv/bin/python \
  -m stock_research.founder_os_model_recovery_cli run \
  --dry-run
```

dry-run 会读取实时 cron 和 run history、识别当天失败并预览脱敏通知，但不会：

- 触发 `openclaw cron run`；
- 写入每日状态；
- 真正发送飞书消息。

## 应用配置

```bash
rtk scripts/install_founder_os_model_recovery.sh --apply
```

命令先输出完整 cron 备份路径，再应用配置。若已经存在同名监督器，应用会拒绝继续。

应用后检查：

```bash
rtk openclaw cron list --all --json
rtk openclaw cron get 7bb1fe09-5543-4f79-8dfc-cd0fe308638d
```

预期：

- 恰好一个 `founder-os-model-recovery-supervisor`，payload 为 command，每 20 分钟运行；
- `founder-os-cron-health-guard` 的 payload 为 command；
- 原 agentTurn 任务仍保持豆包主模型和 OpenAI fallback；
- 原 agentTurn 任务不再单独发送 failure alert；
- 成功任务原有 delivery 保持不变。

## 补跑流程

每轮监督器：

1. 读取北京时间当天的模型失败任务；
2. 等待 20 分钟 probe cooldown；
3. 先补跑最早失败的一项；
4. 若仍是模型不可用，停止本轮，避免批量失败；
5. 若 probe 成功，顺序补跑其余当天任务；
6. 业务或权限错误不重试，只进入聚合摘要；
7. 23:50 仍未恢复时只发一条未解决摘要；
8. 跨日后不再补跑昨天任务。

## 通知格式

故障期最多发送一条：

```text
Founder OS 模型暂不可用
受影响任务: 5 个
处理: 已进入当天自动等待与补跑队列
下次检查: 09:20
群内不再逐条发送原始模型错误
```

恢复后最多发送一条：

```text
Founder OS 模型恢复补跑完成
补跑成功: morning-brief, opportunity-triage
非模型失败: 无
```

通知不得包含 provider request ID、堆栈、原始错误正文或 heartbeat。

## 健康审计

```bash
rtk /Users/xiwei/.openclaw/bin/founder-os-model-recovery audit
```

以下情况返回非零：

- 状态 JSON 损坏；
- 监督器超过 45 分钟未更新 heartbeat；
- `replay_unknown` 状态超过 40 分钟。

等待模型恢复的 pending 状态本身是正常状态，不导致审计失败。

## 回滚

先找到最近备份：

```bash
rtk ls -1t /Users/xiwei/.openclaw/state/founder-os-model-recovery/cron-backup-*.json
```

示例：

```bash
rtk scripts/install_founder_os_model_recovery.sh --rollback \
  /Users/xiwei/.openclaw/state/founder-os-model-recovery/cron-backup-20260725T220000+0800.json
```

回滚会删除监督器 cron，并恢复备份中的任务 schedule、payload、model、fallback、delivery、failure alert、timeout 和 health guard。每日状态与日志作为审计证据保留，不删除任务产物。

## 故障处理

- 无法读取 cron：不触发补跑，下一轮重试。
- 状态写入失败：不触发补跑，防止重复执行。
- 补跑命令返回非零：继续读取 run history，并按最终 run 状态分类。
- 飞书发送失败：重新打开对应通知标志，下一轮只重试通知，不重复补跑成功任务。
- 锁已占用：第二实例正常退出，并在本地日志写入一行 locked 记录。
