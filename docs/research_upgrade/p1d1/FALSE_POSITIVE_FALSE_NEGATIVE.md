# P1d.1 FALSE_POSITIVE_FALSE_NEGATIVE — 存量涨跌停误标双向重算

数据源：`LIMIT_FLAG_RECONCILIATION.csv`（`scripts/p1d1_audit.py` 生成，162,119 行非平凡判定）。
判定口径：原始价 close 对比法定限价（`legal_limit_price(preclose, rule_pct)`，
0.01 元 tick 取整），真实上市交易日序号 + PIT 状态 + 620 号过渡。
**FP = 存量 flag=True 但历史并非涨/跌停；FN = 存量 flag=False 但历史实为涨/跌停。**

## 总量

| 分类 | 行数 |
|---|---|
| CONFIRMED_MISLABEL | **63,821**（FP 20,082 / FN 43,739） |
| CORRECT（抽样段内判定一致） | 98,274 |
| RULE_UNKNOWN（fail-closed） | 24 |

对比 P1d 预估（28,205 创业板候选 + 1,305 IPO 候选 = 29,510）：
**最终实锤 63,821 行，约为预估的 2.16 倍**。差异原因：P1d 只估了"创业板 10% 制度下
达到 10% 但静态阈值漏标"的单方向 + IPO 窗口，未计入主板 ST 双向、pre-1996 无涨跌幅
年代、首日 44% 笼子误标、以及改革后制度下静态 4.8%/9.5% 阈值产生的过度阻断。

## 分段明细（行 = side 级判定，buy 侧对 is_limit_up、sell 侧对 is_limit_down）

| 分段 | CORRECT | CONFIRMED_MISLABEL | RULE_UNKNOWN | 方向拆分 |
|---|---|---|---|---|
| chinext_all | 9,469 | **46,160** | 0 | FN 42,094 / FP 4,066 |
| main_st_flags | 73,274 | 5,550 | 8 | FN 1,645 / FP 3,905 |
| main_ipo_recent | 13,180 | 2,889 | 8 | FP 2,889（首日/首五窗口误标） |
| star_all | 2,351 | 995 | 0 | FP 995（IPO 窗口误标为主） |
| pre_19961216 | 0 | 8,227 | 8 | FP 8,227（无涨跌幅年代的存量 flag 全为误标） |
| beijing_all | — | 0 | 0 | 扫描无分歧行 |
| relisting | — | 0 | 0 | 无样本 |

## 年度分布（CONFIRMED_MISLABEL）

- **2015 单年 13,529 行**（牛市涨停潮，创业板 10% FN 集中释放）
- 2014–2020 合计 ~38,700 行（改革前创业板制度期）
- **2024–2026 仍有 4,240 行**：main_10pct 边缘阈值、IPO 窗口、ST 双向误标持续产生
  → 现代回测窗口同样受污染（见 BACKTEST_SHADOW_REPORT）

## RULE_UNKNOWN 24 行

全部落于 1990-12-19（沪市开市首日）且 `is_st=True`：600601/600602/600651/600653。
ST 制度 1998-04-22 才建立，状态行本身可疑；按任务要求不猜测，fail-closed 计入
RULE_UNKNOWN，列入下一阶段数据修复清单。

## 生成逻辑根因（core_data.py:519-540）

存量 flag 由 `pct_chg >= 静态阈值` 生成，阈值不区分板块制度、日期、上市序号、
无涨跌幅窗口与首日申报笼子；`limit_up_price = preclose*(1+thr)` 同样无视 tick
取整与制度切换。修复方案见 `STORAGE_MIGRATION_PLAN.md`。
