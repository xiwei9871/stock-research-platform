# B0 存储容量审计（只读，2026-10-27）

**本轮零写入/零清理/零迁移。** 证据全部为只读命令输出（见文末）。

## 1. 187 生产服务器

| 项 | 值 | 证据等级 |
|---|---|---|
| 宿主磁盘/分区/文件系统 | — | **`UNVERIFIED`**（22 端口开放但无 SSH 凭据） |
| Docker volume 真实位置 | `data_directory=/var/lib/postgresql/data`（容器内路径；宿主映射未知） | **`UNVERIFIED`** |
| 独立备份盘/卷快照/配额 | — | **`UNVERIFIED`** |
| 数据库大小 | **678 GB**（pg_database_size 实测） | 实测 |
| pg_default 表空间 | 686 GB | 实测 |
| pg_wal | 656 MB | 实测 |
| 表空间外置 | 无（全部在 pg_default） | 实测 |

### 主要表占用（实测 top-5）

| 表 | 总量 | heap | index |
|---|---|---|---|
| factor.factor_daily | 228 GB | 70 GB | **158 GB** |
| market.stock_minute_bar_default | 135 GB | 68 GB | 67 GB |
| public.label_snapshot | 45 GB | 17 GB | 28 GB |
| factor.stock_technical_features_daily | 29 GB | 19 GB | 9.9 GB |
| raw_baostock.daily_bar_payload | 25 GB | 17 GB | 8.2 GB |
| core.asset_status_daily | 3.0 GB | — | PK only |
| raw_akshare.finance_payload | 2.55 GB | — | — |

## 2. 185 中转服务器（实测）

| 挂载 | 设备 | 类型 | 总量 | 可用 | 判定 |
|---|---|---|---|---|---|
| `/` | nvme LVM `ubuntu--vg-ubuntu--lv` | ext4 本地 | 1.1T | **249G (77% 用)** | 系统+82 个 docker volume 所在——**勿用作备份落盘** |
| `/mnt/data1` | `/dev/sda1` | ext4 **本地 SATA 盘** | 1.8T | **1.1T (34% 用)** | ✅ 备份落盘可用 |
| `/mnt/Public` | `//192.168.3.253/Public` | cifs 3.1.1 | 59T | 20.3T | 备份文件仓可用 |
| `~/NAS` | `//192.168.3.253/public/msDataBackup` | cifs | 59T | 20.3T | jqz **不可写**（0755 root-owned share） |

- `L1` 备份已落地 `/mnt/data1/stock_research_backup/L1/`（207MB，本地盘确认）；
- `/mnt/Public` 挂载选项 `file_mode=0777,forceuid` → stat 级可写验证为 **WRITABLE**（未创建测试文件）；
- docker volumes 全在 nvme 根卷——与本项目无关存量 82 个。

## 3. 253 NAS（经 185 挂载核实）

- 总 59T / 用 39T / **余 ~20.3T**（两挂载同一池）；
- 链路：185 enp6s0 ↔ LAN，mount vers=3.1.1 healthy；
- **可用共享：`/mnt/Public`（可写）**；`msDataBackup` 对 jqz 不可写；
- 配额：未见显式配额痕迹（`UNVERIFIED` 细项）；
- **cifs 仅可存备份文件**——不能作 PG data_directory（fsync/mmap 语义不满足，全库恢复不得指向 NAS）。

## 4. 容量方案测算（686GB 基线）

| 方案 | 单次体量 | 依据 | 2–4 代保留 | 可行落点 |
|---|---|---|---|---|
| L1 单表 | **206MB 实测**（3.0GB→7%） | 实测 | <1GB | 任意 |
| L1 finver+raw | ~0.2–0.6GB 估 | raw 2.55GB×压缩率类比 | <2GB | 任意 |
| L2 全库 `-Fc` | **估 70–170GB**（10–25% 压缩率；`factor_daily` heap 70GB 但 index 158GB 不入 data dump，逻辑备份体积以 heap+TOAST 计） | 估计 | 140–680GB | `/mnt/data1`(1.1T) ✅ / NAS(20.3T) ✅ |
| L3 物理基备 `-Ft -z` | 估 200–400GB（全目录含索引） | 估计 | 400–1600GB | NAS(20.3T) ✅；`/mnt/data1` 仅 1–2 代 |
| WAL 归档 | 估 1–5GB/日（T4 期 ~3GB+/日额外） | 估计 | 14 天 <70GB | NAS ✅ |
| **全库独立恢复演练** | 需 **≥686GB 数据目录 + dump 文件 70–170GB ≈ ≥800GB** | 推算 | — | **仅 `/mnt/data1`(1.1T) 可行**（须先挪/预占空间；本机 Mac 仅 17GiB 剩余 ❌；NAS 不可作数据目录 ❌） |

**实测/估计/未知已分列；所有"估"标注未实测。**

## 5. 结论 — 三设备能否支撑 L2 全库备份+独立恢复？

**能，但有明确瓶颈与顺序：**

1. ✅ **L2 全库逻辑备份可行**：产物落 NAS `/mnt/Public`（20.3T）或 `/mnt/data1`（1.1T，2–4 代够）；网络 0.23ms RTT 同 LAN；按实测 3GB→29s 外推全库约 **1.5–3 小时**（估）；
2. ✅ **独立恢复演练可行**：在 185 上以 docker `postgres:16.x` + `/mnt/data1` 数据目录恢复（≥800GB 需一次性腾空位；`/` 根卷只有 249G 不可用）；
3. ⚠️ **瓶颈清单**：
   - 187 宿主机零可见性 → 卷快照/备份盘永远 UNVERIFIED，L3 基备只能走 `pg_basebackup` 网络拉取（需 pg_hba replication 放行——**未验证**）；
   - `pg_restore/pg_dump` 客户端版本需与服务器 16.x 对齐（185 上现有的是 14.x ❌，本机 18.3 可用但有 transaction_timeout 警告）——**需在 185 装 PG16 客户端或从本机推送产物**；
   - NAS `msDataBackup` 共享对备份账号不可写，统一走 `/mnt/Public`；
   - `archive_mode` 变更=生产配置改动，独立审批；
   - 185 根盘 249G 不足以容纳任何 dump 中转——中转必须显式指向 `/mnt/data1`。

## 附：关键只读命令证据

```
# 187 via SQL (read-only)
SELECT pg_size_pretty(pg_database_size('stock_research'));      -- 678 GB
SELECT pg_size_pretty(sum(size)::bigint) FROM pg_ls_waldir();  -- 656 MB
pg_tablespace listing: pg_default 686GB, pg_global 965kB

# 185
df -hT            -> / 77% used 249G avail; /mnt/data1 34% 1.1T avail
findmnt -T ...    -> /mnt/data1 = /dev/sda1 ext4 (local SATA)
findmnt -t cifs   -> Public + msDataBackup on //192.168.3.253, vers=3.1.1
[ -w /mnt/Public ] -> WRITABLE ; [ -w ~/NAS ] -> NOT_WRITABLE
docker volume ls  -> 82 vols on root LVM (none stock_research PG)

# Mac
df -h -> Data volume 92% used, 17GiB avail -> 本机不可作全库恢复目标
```
