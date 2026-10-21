# CAP-02 T3 P0 验收报告

日期：2026-10-21 ｜ commit 基准：`e2119bd5` 之后 R2.1+T3 收口

## 一、原文核验清单（直读 PDF 原表）

| 记录 | 文件/页 | 核验项 | 结果 |
|---|---|---|---|
| seg_002837_dc_thermal | 002837 年报 p15-16 | 机房温控 3,448,477,492.62 元 / 56.83% / 毛利 28.36% / +41.28%，单位=元，分产品表 | **accepted** |
| seg_002837_ess_thermal | 同上 | 机柜温控 1,977,423,139.19 元 / 32.59% / 毛利 27.24%（-4.24pct） | **accepted** |
| seg_002837_total | p15 | 总营收 6,067,759,091.55 元 +32.23%；归母净利 52,191.48 万 | **accepted** |
| seg_688686_mv | 688686 年报 p46 | 机器视觉 960,146,650.95 元 / 毛利 65.54%；主营合计 12.68 亿 +39.43% | **accepted** |
| seg_301018_datasvc | 301018 年报 p10/p15 | 数据服务行业 2,343,264,576.37 元 / 55.67% / +51.42%；新增订单 +72%（**板块口径含风冷/相变**） | **accepted** |
| seg_002371_unextracted | cninfo PDF 本地缺失 | 分产品表未入库 → 记 unextracted（非"未披露"） | pending→缺 DATA 线补 PDF |
| ord_002837_nocontracts | 002837 年报 p16 | "重大销售合同履行情况：□适用 √不适用" | **accepted**（明示无重大合同披露） |
| cust_002837_intel_nvidia | 年报 p9-10 | Intel 至强6冷板集成商 + NVIDIA MGX 生态（UQD/MQD）+ 主流厂商规模采购 | **accepted** |
| cust_301018_topcust | 年报 p10 | H公司/字节/腾讯/阿里/主要COLO商 合作粘性强化 | **accepted** |
| rival_301018_liquid | 年报 p10-11 | CDU 全序列+智造基地投产+CDU 厂商第一（赛迪） | **accepted**（事实级）；**"同等有效替代"强判断=待核验** |
| cust_688686_yuejiang / ord_688686_yuejiang | 券商点评 | 越疆合作接触 | **lead_only** |
| rival_603757 / rival_002050 | 券商摘要/内部摘要 | 一手披露缺失 | **lead_only** |

**计数**：accepted 9 条 / pending 1 条（002371 缺口）/ lead_only 4 条。

## 二、三节点矩阵 before/after（T3 收口）

| 节点·公司 | R2.1 矩阵 | T3 P0 后 |
|---|---|---|
| 液冷·002837 | rev: disclosed_broader_scope | 同 + **订单 none_disclosed**（年报明示无重大合同）+ **验证 validated**（Intel/NVIDIA） |
| 液冷·301018 | 无画像 unknown | **rev: disclosed_broader_scope（数据服务 23.43亿）+ valdel: validated + ord: contracted_at_industry_board**（板块口径不归液冷单线） |
| 液冷·002050 | unknown | **missing**（ru_* 零覆盖如实暴露） |
| 半导体·002371 | rev unextracted | 同 + orders none_seen（千台交付是里程碑≠订单） |
| 人形·688686 | rev missing | 同 + valdel/orders **pending_review**（越疆 lead_only 入队不计数） |

节点判定不变：液冷 unverified / 半导体 unverified / 人形 needs_evidence。`nc_process_scarce` 现由 **accepted 一手申菱披露**反驳（contradicted），`nc_nonexclusive_suppliers` 升 **confirmed**（M1+申菱两独立来源）——verified 事实保留且更强，瓶颈仍未证实。

## 三、收口要点落实

- `segment_cell`：pending 只进 `candidate_facts`，可信 state 仅由 accepted 计算；PIT 同一套规则（ingested 晚于 as_of → 排除）
- `RivalSupplyRecord`：`source_type`/`reliability_level`/`available_at` 真实透传——大元=broker_report S3、三花=industry_data S2，不再冒充 company_filing
- 竞对证据双行绑定：`{rid}`→refute 稀缺 claim、`{rid}_roster`→support 格局 claim；"完整替代有效性"强判断保留待核验
- `t3_sha256` 并入 `dossier_fingerprint`：记录内容/审核/日期/产品线变更必改指纹
- 无 dossier 的申菱：T3 事实独立呈现于矩阵/t3_facts，无六维结论

## 四、缺口移交 DATA 线

1. 002371 年报分产品表（电子工艺装备/电子元器件）——PDF 未入库
2. 三花智控液冷一手披露（ru_* 零覆盖）
3. 大元泵业 CDU 泵适配一手披露
4. 英维克液冷单线收入拆分（机房温控含液冷未拆）
5. 申菱液冷单线收入/订单（数据服务板块口径含风冷/相变）

## 五、复现命令

```bash
cd /Users/xiwei/stock_research/.worktrees/cap-01
.venv/bin/pytest tests/test_chain_bottleneck.py -q   # 27 passed
for c in liquid_cooling_node semi_equipment_node humanoid_vision_node; do
  PYTHONPATH=src .venv/bin/python -m stock_research.cli chain-bottleneck-dossier \
    --case docs/cap02/cases/$c.json \
    --dossier-dir outputs/research/company_intelligence \
    --output-dir outputs/research/chain_bottleneck \
    --code-sha "$(git rev-parse --short HEAD)"
done
```
