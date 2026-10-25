# P1d.1 STORAGE_MIGRATION_PLAN — asset_status_daily flag 修复方案（未执行）

**状态：方案 + 隔离验证完成，生产表零改动。**
禁止项遵守：未重写 `core.asset_status_daily`（17.29M 行）任何一行；验证全部在
`p1d1_shadow` 独立 schema 完成。

## 根因

`core_data.py:519-540`：`is_limit_up = pct_chg >= {limit_threshold_sql}` 静态阈值，
`limit_up_price = preclose*(1+thr)`——无板块制度/生效日期/上市交易日序号/
无涨跌幅窗口/首日申报笼子的感知。tick 取整缺失导致边界样本系统性偏差。

## 隔离验证（已执行，`p1d1_shadow.asset_status_flags_v2`）

样本：创业板 2019-01-01~2020-12-31 全部状态行（369,681 行）。

| 验证项 | 结果 |
|---|---|
| 行数 / 主键唯一性 | 两次 run 各 369,681 行，distinct(asset_id,trade_date)=369,681，零漂移 |
| 幂等 | v2run1 vs v2run2 **0 行差异**（同输入同输出，可重放） |
| vs 存量 flag | up_diff=7,463、dn_diff=2,497（仅创业板两年窗口，与
`LIMIT_FLAG_RECONCILIATION` 全库口径一致） |
| 附带产出 | 每行携带 `rule_id / rule_source / legal_up / legal_dn`——
修正值可追溯到规则与法定价 |

验证脚本逻辑与 `scripts/p1d1_audit.py::recompute` 同源，可随时重跑放大样本。

## 迁移方案（下阶段，需独立授权）

### 方案 A（推荐）：新增版本化列而非覆盖

1. `ALTER TABLE core.asset_status_daily ADD COLUMN is_limit_up_v2 boolean,
   is_limit_down_v2 boolean, limit_rule_id text, limit_legal_up numeric,
   limit_legal_dn numeric, limit_flag_version text`——老 flag 原样保留，
   不存在静默覆盖；
2. 分批回写（按 trade_date 分区 chunk，每批 commit，单批 ~50 万行）：
   来源 = P1d.1 规则引擎（`resolve_limit_rule` + `legal_limit_price` +
   真实交易日序号 + 620 过渡）；
3. 消费方灰度切换：`vectorized_topn`/`retention` loader 先读 v2 列
   （`COALESCE(v2, v1)` 回退老值），`market_emotion_state_v1`、
   `asset_status_service`、dashboard 依次切换；
4. 观察 1 个 EOD 周期 + 1 次 shadow 回测复核后，老列标记 deprecated，
   保留≥1 个季度再议删除。

### 方案 B：影子表 + 视图切换

新建 `core.asset_status_daily_v2`（全量修正行），`market_daily_bar`-侧
兼容视图切换引用。优点：原表完全不动；缺点：17.29M 行双份存储、
视图切换是部署级变更。作为方案 A 的回退。

### 必须同步修复的 sibling 缺陷（同一授权点一并处理）

- `vectorized_topn_backtest.py:96` SQL 引用了 `market_daily_bar` 不存在的
  `is_limit_up/down/is_suspended` 列 → 改为 join `core.asset_status_daily`；
- `retention_backtest.py`/`backtest.py` bar frame 不含 flag 列 →
  `can_open_long` 的 limit 门静默失效，装载层需显式补列；
- `dragon_case_library._is_limit_up` 静态 4.8/9.5 阈值 → 路由规则引擎；
- `false AS is_limit_*` 常量消费方（intraday/mid_trend/serenity/dashboard.backtests）
  → 评估是否应接真实 flag；
- `core_data.py` 生成逻辑 → 用规则引擎重写，否则新数据继续产生误标。

### 回滚

方案 A 回滚 = 消费方 `COALESCE` 顺序翻转 + 保留老列；方案 B 回滚 =
视图指回旧表。均不涉及数据删除。

### 验收 Gate（迁移执行时）

- 分批前后 `count(*)`、PK 覆盖、is_st/is_suspended/trade_status 零变化；
- 重跑幂等（已验证）；
- EXPLAIN：chunk UPDATE 走 PK 范围扫描，避免全表 seq scan 锁表；
- 抽样回放：每制度段 ≥100 行人工/规则复核；
- 下游 1 次全量 shadow 回测对比。

## 风险

- `is_st` PIT 正确性是 flag 修正的前提——若状态行本身错（如 1990-12-19
  ST 异常行），修正 flag 会延续状态错误；已列入数据修复清单而非本轮处理；
- 北交所 ST 规则 `verified=False` → 迁移后这些行 flag 保持 NULL+rule_unknown，
  消费方需把 NULL 当"不可判定"而非 False。
