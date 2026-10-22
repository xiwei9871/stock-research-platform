# CAP-02 DATA-D2 液冷子环节研究报告

日期：2026-10-22 ｜ 复用 T1/T2/T3 冻结框架，零新判定引擎

## 一、来源完整性

`t3_source_manifest.json` 4/4 VERIFIED：主路径 SHA256 全匹配 + 独立副本已落 `data/manual/t3_primary_sources_20261022/`（原回填目录曾 10-19 清空，manifest 记录 backup_status=VERIFIED/backup_sha256_match）。

## 二、三子节点 dossier（`outputs/research/chain_bottleneck/`）

| 子节点 | verdict | 格局论点 | 认证壁垒 | 供给约束 |
|---|---|---|---|---|
| CDU整机及系统集成 | bottleneck_unverified | partially_supported(2) | partially_supported(1) | unknown |
| 冷板/Manifold/快接头 | bottleneck_unverified | partially_supported(2) | partially_supported(1) | unknown |
| 屏蔽泵及循环组件 | bottleneck_unverified | partially_supported(1) | partially_supported(1) | unknown |

父节点公司画像未自动升级：各子节点独立绑定 node-scope 证据；三花未出现在任何子节点成员（无产品级证据）；申菱板块客户关系（dc_liquid_cooling 归因）未进入 cdu_system 子节点。

## 三、子节点证据矩阵

### CDU 整机及系统集成

| 公司 | 技术 | 认证 | 交付 | 收入 | 竞争优势 |
|---|---|---|---|---|---|
| 002837 英维克 | Coolinside全链CDU序列(accepted) | **Intel测试验证**(validated) | 未披露台数/合同 | 未单独披露 | unverified |
| 301018 申菱 | CDU全序列+智造基地(accepted) | 无产品级认证证据 | 无液冷CDU级交付证据 | 未单独披露 | unverified |

### 冷板/Manifold/快接头

| 公司 | 技术 | 认证 | 交付 | 收入 | 竞争优势 |
|---|---|---|---|---|---|
| 002837 | 冷板/UQD04/分水器/MQD(accepted) | **Intel测试+NVIDIA MGX生态** | 规模采购应用表述(无量) | 未单独披露 | unverified |
| 301018 | 冷板/快接头/Manifold序列(accepted) | 无 | 无 | 未单独披露 | unverified |

### 屏蔽泵及液体循环组件

| 公司 | 技术 | 认证 | 交付 | 收入 | 竞争优势 |
|---|---|---|---|---|---|
| 603757 大元 | In-Rack 1-15kW/In-Row 22-37kW/48v/800V 永磁屏蔽泵(accepted) | **UL 等产品认证**(product_certified) | **~5万台组件级交付 + 曙光8000项目交付** | 未披露金额 | unverified（先发卡位自述，无定价/份额证据） |
| 外资(格兰富/赛莱默) | CME/CM CDU专用泵、CR系列40年迭代(pending) | — | 美区+20%叙述 | — | 在位者优势(二手叙述) |

## 四、大元泵业六事实链（深度样本）

| 维度 | 事实 | 等级 | 边界 |
|---|---|---|---|
| 技术规格 | In-Rack 1-15kW、In-Row 22/37kW 永磁同步/异步屏蔽泵、48v低压、800V联合开发、浸没式氟化液泵组 | accepted(2026H1 p17) | — |
| 认证 | 单机测试及认证（含 UL） | product_certified | **产品认证≠客户认证** |
| 交付 | In-Rack ~3万台(2025)+~2万台(2026H1)；曙光8000泵组供应完成 | verified_delivered | **组件级交付≠整套CDU；交付≠可识别合同** |
| 收入 | 未披露（仅台数，无金额） | missing | 不推算 |
| 毛利 | 未披露 | missing | — |
| 竞争优势 | "率先千瓦级大批量稳定交付""先发卡位" | unverified | 自述；无份额/定价/利润证据 |

语义边界已固化：17家对接覆盖=contact（不默认逐家送样）；substitution_verified=False（泵供给≠系统替代）。

## 五、可信覆盖率与缺口

- 覆盖率（accepted 事实/六维格子）：大元 4/6（缺收入、毛利）；英维克 3/6（技术、认证、部分交付表述；缺收入、毛利、可量化交付）；申菱 1/6（仅技术序列）
- 三子节点 accepted 节点级证据：CDU 3 / 冷板 3 / 泵 2（+1 pending 外资叙述）
- **未解决关键问题**：①液冷各子环节收入/毛利全线未披露；②大元液冷金额与单价；③泵环节除大元外国内第二家验证供应商缺位（外资不在 A 股口径）；④申菱产品级客户认证；⑤英维克 CDU/冷板交付量级

## 六、复现

```bash
for c in liquid_cooling_cdu_system liquid_cooling_coldplate_manifold liquid_cooling_pump_components; do
  PYTHONPATH=src .venv/bin/python -m stock_research.cli chain-bottleneck-dossier \
    --case docs/cap02/cases/${c}_node.json \
    --dossier-dir outputs/research/company_intelligence \
    --output-dir outputs/research/chain_bottleneck \
    --code-sha "$(git rev-parse --short HEAD)"
done
```

边界：research_only、零生产写入、未部署。verified_delivered 仅表述交付事实，全文未称其为已核实订单合同。
