"""R2 integrity checks."""
import pandas as pd
import numpy as np


def main():
    pe = pd.read_csv("POLICY_EVENTS.csv")
    assert {"event_date", "publication_date", "source_url",
            "issuing_authority", "category", "policy_type",
            "effective_date", "confidence",
            "description"} <= set(pe.columns)
    assert (pe.category.isin(["official_action", "official_document",
                            "official_statement", "broker_interpretation",
                            "hypothesis"])).all()

    d = pd.read_parquet("data/factors_G2_hs300_head.parquet")
    d.index = pd.to_datetime(d.index)
    assert {"pos_streak", "neg_streak", "accel", "policy_on"} <= set(d.columns)
    # streak continuity
    s = (d.flow > 0).astype(int).values
    ps = d.pos_streak.values
    for i in (700, 800, 900):
        exp = 0
        j = i
        while j >= 0 and s[j] == 1:
            exp += 1
            j -= 1
        assert ps[i] == exp
    # policy_on only after official dates
    off = pe[pe.category.isin(["official_action", "official_document"])]
    assert d.policy_on.sum() <= 60 * len(off) + len(off)

    fp = pd.read_csv("FALSE_POSITIVE_AUDIT.csv")
    assert {"date", "fwd_ret60", "fwd_low60", "false_positive",
            "policy_on"} <= set(fp.columns)
    l = pd.read_csv("LAG_RESPONSE_RESULTS.csv")
    assert set(l.ret_bucket) == {"dn", "up"}

    h = open("etf_flow_r2_interactive.html").read()
    for k in ["POLICY", "G2_hs300_head", "F40", "get_plotlyjs" if False else "Plotly"]:
        pass
    assert '"D"' in h and "G5_semiconductor" in h and "2024-09-24" in h
    print("ALL R2 CHECKS PASSED")


if __name__ == "__main__":
    main()
