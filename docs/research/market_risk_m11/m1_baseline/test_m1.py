import pandas as pd, numpy as np, sys
sys.path.insert(0,".")
from build_m1 import cycles_from_dd, fwd_labels, features, load_all

def test_cycle_merge():
    dd = pd.Series([0,-.11,-.12,-.08,-.04,0,-.11,-.13,-.06],
                   index=pd.date_range("2020-01-01",periods=9))
    c = cycles_from_dd(dd)
    assert len(c)==2, "两段独立周期"
    assert c[0]["end_i"]==4
    dd2 = pd.Series([0,-.11,-.08,-.15,-.04,0],index=pd.date_range("2020-01-01",periods=6))
    c2 = cycles_from_dd(dd2)
    assert len(c2)==1, "dd10+dd15同周期合并"

def test_fwd_censoring():
    p = pd.Series(np.linspace(100,90,100))
    fw = fwd_labels(p)
    assert np.isnan(fw[60][2][-60:]).all(), "末60日标签必须NaN"

def test_features_pit():
    F = pd.read_parquet("data/MACRO_RISK_PIT_FEATURES.parquet")
    F.index = pd.to_datetime(F.index)
    T = pd.Timestamp("2024-06-01")
    emo,br,px = load_all()
    F2 = features(emo[emo.index<T],br[br.index<T],px[px.index<T])
    cols=["emotion","pct_ma60","g1_depth","lowvol20","sse_dd120"]
    a=F.loc[:T-pd.Timedelta(days=1),cols]
    b=F2.loc[:T-pd.Timedelta(days=1),cols]
    both=a.join(b,rsuffix="_r",how="inner")
    for c in cols:
        aa,bb=both[c],both[c+"_r"]
        m=aa.notna()&bb.notna()
        assert np.allclose(aa[m],bb[m],atol=1e-6), f"{c} truncation mismatch"

if __name__=="__main__":
    for k,f in list(globals().items()):
        if k.startswith("test_"): f(); print(k,"PASS")
    print("ALL M1 CHECKS PASSED")
