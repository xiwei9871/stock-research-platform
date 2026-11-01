# 任务A：187 宿主机磁盘归因（2026-10-28，只读）

## 可见范围声明（诚实边界）
- 唯一授权通道：187 postgres 容器内 `COPY FROM PROGRAM`（容器 PID/mount 命名空间，仅 11 进程可见）。
- 187 无 SSH（`jqz@187` publickey 拒绝）；185→187 ssh 拒绝；`monitor-agent` 只是 Uptime Kuma push 客户端，无执行能力。
- 以下"实测"= 容器内直接测量；"宿主盲区"= 物理在盘上但容器不可枚举，只能给出归因线索+管理员命令清单。

## 磁盘全景（实测）

| 层 | 实测 | 说明 |
|---|---|---|
| 宿主盘 | nvme0n1 ~954GB，单分区 ~952.8GB | lsblk（上轮） |
| 文件系统 | `/dev/mapper/root-98d1f8b1f435`（LVM LV，ext4） | 本次挂载证据 |
| 总量/已用/可用 | **959,271MB / 889,973MB / 20,498MB（98%）** | df，pgdata 挂载点与容器 / 同盘 |
| 保留块 | **≈48,800MB（~5%，ext4 默认）** | 937-869-21 差额，属"不可用但未占用" |
| inode | 79.0万/6244万（2%） | 健康 |

## pgdata 内部（703,950MB，100% 归因）

| 目录 | MB | 可回收? |
|---|---|---|
| base | 702,922 | 业务库本体，膨胀部分见 STORAGE-R1（索引 ~57GB、整体 ~161GB） |
| pg_wal | 1,025 | 健康水位，不动 |
| pg_xact 等其余 | ~20 | — |
| pgsql_tmp | <1 | 无泄漏 |
| log 目录 | 0 | 未启用文件日志（走 stdout→容器日志） |
| 已删除仍占用 fd | 1 个 WAL 16MB | 微量，checkpoint/重启即释放 |

## 宿主盲区 ~186GB（=889,973-703,950，待管理员核验）

容器证据：宿主用 **containerd**（overlay lowerdir 指向 `/var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots/*`）。pgdata 与容器 rootfs 同在 root LV。postgres 容器自身可写层仅 **447MB**。

候选构成（按经验排序，均为**估计**，需清单核验）：
1. `io.containerd.content.v1.content` + snapshotter——**全部容器镜像层**（187 上容器数未知，可能含 Kuma/agent/其他业务容器镜像，常见 20–80GB，含旧镜像层累积）；
2. 其他容器 volume/本地数据（187 上除 postgres 外其他业务的 volumes，属**他人有效数据**，不可擅动）；
3. 容器日志（containerd/k8s 风格 `/var/log/pods|containers` 或 journald）——常见可回收大头；
4. journald/系统日志、apt/包缓存、旧内核、core dump、临时目录；
5. 其他业务宿主目录。

## 管理员只读检查清单（需宿主权限，全部只读）
```bash
df -hT / ; df -i / ; lsblk -f ; lvs ; pvs ; vgs
du -xsm /var/lib/containerd/* 2>/dev/null | sort -rn | head
du -xsm /var/log /var/lib/systemd /var/cache /tmp /root /home /opt /srv /data* 2>/dev/null | sort -rn
du -xsm /* 2>/dev/null | sort -rn | head -20          # 顶层归因
journalctl --disk-usage
lsof +L1                                               # 已删除仍占用
find / -xdev -type f -size +1G -ls 2>/dev/null         # 大文件点名
tune2fs -l /dev/mapper/root-98d1f8b1f435 | grep -iE 'reserved|block count|free'
ctr -n moby images ls 2>/dev/null; crictl images 2>/dev/null   # 镜像清单
crictl ps -a 2>/dev/null                                # 全部容器（含已退出）
```

## 回收判定
- **确定可回收（低风险）**：旧镜像层、已退出容器、journald/容器日志截断、apt/包缓存、core dump —— 预估 30–120GB，待清单确认；
- **有效数据，不可动**：其他业务容器 volumes、运行中镜像；
- **保留块 47.7GB**：属策略性储备，不建议为腾空间调低（root 应急余量）；
- pgdata 内无宿主级垃圾——回收必须走 STORAGE-R1 的库内路径（REINDEX/repack），与本目录无关。

## 结论
"180GB"= ~186GB 宿主侧 containerd/系统/其他业务内容 + ~47.7GB ext4 保留块（后者不计入 used）。**其中有多少可回收，取决于管理员清单输出**；postgres 容器视角已穷尽。
