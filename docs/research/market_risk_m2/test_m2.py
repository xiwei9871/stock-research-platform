import pandas as pd, numpy as np, sys
sys.path.insert(0,"."); sys.path.insert(0,"../market_risk_m1")
from build_m2 import episodes_table, mcclellan, px_full
import build_m1; build_m1.D="../market_risk_m1/data"
from build_m1 import cycles_from_dd

def test_systemic_merge():
    px = px_full()
    ep = episodes_table(px)
    # 2026 Jul events across objs must share one sys_id
    e26 = ep[(ep.first_dd10 if "first_dd10" in ep else ep.start) >= "2026-07-01"]
    e26 = ep[ep.start >= "2026-07-01"]
    assert e26.sys_id.nunique() == 1, "2026 cycle must merge to one systemic id"

def test_mcclellan_pit():
    up = list(range(1500, 3000, 50))
    emo = pd.DataFrame({"up_count": up, "down_count": [1500] * 30},
                       index=pd.date_range("2020-01-01", periods=30))
    m = mcclellan(emo)
    assert m.mcc_osc.iloc[-1] > 0, "rising net advance must give positive osc"
    assert abs(m.mcc_sum.iloc[-1] - m.mcc_osc.cumsum().iloc[-1]) < 1e-9

def test_episode_tiers():
    px = px_full()
    ep = episodes_table(px)
    assert set(ep.tier.unique()) <= {"full","price_only"}
    assert (ep.tier=="price_only").sum() > 0

if __name__=="__main__":
    for k,f in list(globals().items()):
        if k.startswith("test_"): f(); print(k,"PASS")
    print("ALL M2 CHECKS PASSED")
