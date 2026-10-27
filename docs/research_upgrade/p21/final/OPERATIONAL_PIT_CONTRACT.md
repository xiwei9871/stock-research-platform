# P2.1-Final-C Operational PIT 语义契约

## 修正点

`updated_at` 是**最近一次写入/刷新时间**，随每次 UPSERT 重抓刷新，不等于首次入库时间（first_seen_at 不存在）。

## 契约

| 维度 | 判定依据 | 字段 |
|---|---|---|
| 公开可用性 | 已核实公告日 `announcement_date < as_of`（D+1） | `publicly_available_at_asof` |
| 平台当时实际持有 | **无可信 first_seen 证据时恒 UNKNOWN** | `operationally_available_at_asof = None` |

- 禁止由 `updated_at > as_of` 推出"当时不可用"（可能只是重抓刷新，首次入库仍更早）；
- 禁止由 `updated_at <= as_of` 推出"当时可用"（同理反向不成立）；
- `updated_at` 仅保留在 `evidence_trace.last_updated_at` 作审计痕迹；
- 若未来新增 append-only 写入 + first_seen 列，才可把 operational availability 从 UNKNOWN 提升为布尔判定。

## initial_public 语义分级

| 情形 | pit_status | 含义 |
|---|---|---|
| 多版本链存在，选最早版本 | `restated_selected` | 最早**幸存**版本（仍非全局初版证明，reasons 注明） |
| 单版本 + 法定窗口内公告 | `verified_public` | 幸存版本疑似初版，`initial_version_provable=true`（仍是推断非证明） |
| `initial_public` 请求但不可验证（多版本外情形/疑似再披露） | `historical_version_missing` | **幸存版本仍可能已公开**（publicly_available_at_asof 如实），但不得被消费者当作"已验证初版" |

- 长公告滞后（>240d）只标 `suspected re-announcement`，**不反推真实初披日期**；
- `initial_version_provable` 存于 `evidence_trace`，消费者应读取该位而非凭 pit_status 猜测。

## 同日与哨兵

- `announcement_date = as_of` → not_yet_published（D+1）；
- `1900-01-01` 哨兵 → publication_date_missing（fail-closed）；
- 非法 as_of/report_period → ValueError。
