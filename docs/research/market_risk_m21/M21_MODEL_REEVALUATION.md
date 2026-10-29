# 模型复评（修正后）
- E 脆弱性：valid AP≈B基线，无增量——保持未验证。
- F=E+ETF：劣化确认（valid .344）——ETF全组输入负贡献第三次复现。
- G 压力（条件参考）：train .711 / valid .233 / replay .958(touched) → NOT_SUPPORTED。
- H 修复（CONF=40标签）：valid AP .082（先验.096）→ NOT_SUPPORTED；M2"H达标"结论撤销：其2026"正确"来自恒守弱输出的先验偏置，非区分能力。
- 全部预测族在独立valid段均无可靠区分力；仅描述性状态层保留。
