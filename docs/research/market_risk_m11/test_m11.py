import pandas as pd, numpy as np, sys
sys.path.insert(0,"."); sys.path.insert(0,"../market_risk_m1")
from analyze_m11 import sm_variants, episodes, corrected_audit
import build_m1

def test_sm_hysteresis():
    pct = pd.Series([.5,.85,.7,.5,.85,.5,.5])
    sm = sm_variants(pct)
    # enter>=.8, exit<.55: [.5N,.85W,.7W,.5N,.85W,.5N]
    assert sm["hysteresis"].tolist()==["NORMAL","WATCH","WATCH","NORMAL","WATCH","NORMAL","NORMAL"], "滞回保持"
def test_sm_memory():
    pct = pd.Series([.5,.95]+[.5]*9+[.5])
    sm = sm_variants(pct)
    assert sm["memory10"][5]=="WATCH" and sm["memory10"][11]=="NORMAL"
def test_episodes_count():
    sn = pd.DataFrame({"date":pd.date_range("2026-01-01",periods=6),
        "obj":["sse"]*6,"model":["A"]*6,
        "state":["NORMAL","WATCH","WATCH","NORMAL","ELEVATED","NORMAL"]})
    e = episodes(sn,"sse","A")
    assert len(e)==2 and e[0]["days"]==2 and e[1]["peak"]=="ELEVATED"
def test_not_evaluated():
    sn = pd.DataFrame({"date":pd.to_datetime(["2026-07-01"]),"obj":["sse"],"model":["A"],"state":["WATCH"]})
    cy = pd.DataFrame({"obj":["sse"],"cycle_id":["C00"],"first_dd10":[pd.Timestamp("2020-03-01")],"trough":[pd.Timestamp("2020-03-05")]})
    ca = corrected_audit(sn,cy)
    assert ca.eval_status.iloc[0]=="NOT_EVALUATED"

if __name__=="__main__":
    for k,f in list(globals().items()):
        if k.startswith("test_"): f(); print(k,"PASS")
    print("ALL M1.1 CHECKS PASSED")
