import pandas as pd, numpy as np, sys
sys.path.insert(0,"."); sys.path.insert(0,"../market_risk_m1"); sys.path.insert(0,"../market_risk_m2")
from m21_audit import union_find_merge

def test_union_find_transitive():
    ep = pd.DataFrame([
        {"obj":"sse","cycle_id":"a","start":pd.Timestamp("2020-01-01"),"end":pd.Timestamp("2020-03-01"),"trough":pd.Timestamp("2020-02-01"),"max_dd":-.12,"status":"COMPLETED","tier":"full"},
        {"obj":"cyb","cycle_id":"b","start":pd.Timestamp("2020-02-15"),"end":pd.Timestamp("2020-04-01"),"trough":pd.Timestamp("2020-03-01"),"max_dd":-.20,"status":"COMPLETED","tier":"full"},
        {"obj":"szse","cycle_id":"c","start":pd.Timestamp("2020-03-20"),"end":pd.Timestamp("2020-05-01"),"trough":pd.Timestamp("2020-04-01"),"max_dd":-.15,"status":"COMPLETED","tier":"full"},
        {"obj":"alla","cycle_id":"d","start":pd.Timestamp("2021-01-01"),"end":pd.Timestamp("2021-02-01"),"trough":pd.Timestamp("2021-01-15"),"max_dd":-.11,"status":"COMPLETED","tier":"full"}])
    e = union_find_merge(ep)
    # a-b overlap, b-c overlap, a-c NOT overlap -> transitive merge => a,b,c same; d separate
    assert e.sys_id_v2.iloc[0]==e.sys_id_v2.iloc[1]==e.sys_id_v2.iloc[2]!=e.sys_id_v2.iloc[3]
    assert e.sys_id_v2.nunique()==2

def test_disjoint_not_merged():
    ep = pd.DataFrame([
        {"obj":"sse","cycle_id":"a","start":pd.Timestamp("2020-01-01"),"end":pd.Timestamp("2020-02-01"),"trough":pd.Timestamp("2020-01-15"),"max_dd":-.12,"status":"COMPLETED","tier":"full"},
        {"obj":"cyb","cycle_id":"b","start":pd.Timestamp("2020-06-01"),"end":pd.Timestamp("2020-07-01"),"trough":pd.Timestamp("2020-06-15"),"max_dd":-.20,"status":"COMPLETED","tier":"full"}])
    e = union_find_merge(ep)
    assert e.sys_id_v2.nunique()==2

def test_2026_single_systemic():
    e = pd.read_csv("SYSTEMIC_EPISODES_CORRECTED.csv", parse_dates=["start","end","trough"])
    e26 = e[e.start>="2026-07-01"]
    assert e26.sys_id_v2.nunique()==1 and e26.obj.nunique()==4

if __name__=="__main__":
    for k,f in list(globals().items()):
        if k.startswith("test_"): f(); print(k,"PASS")
    print("ALL M2.1 CHECKS PASSED")
