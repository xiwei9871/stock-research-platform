"""R2 single-file offline interactive HTML."""
import json
import pandas as pd
import numpy as np
from plotly.offline import get_plotlyjs

GROUPS = ["G2_hs300_head", "G1_all_equity", "G9_sse50_head",
          "G5_semiconductor", "G6_ai_compute", "G7_robot",
          "G8_softinfo", "G4k_star"]
WINS = [5, 20, 40, 60]
D = {}
for g in GROUPS:
    d = pd.read_parquet(f"data/factors_{g}.parquet")
    D[g] = {"d": [str(x)[:10] for x in d.index],
            "flow": d.flow.round(2).tolist(),
            "idx": (d.idx_level / d.idx_level.dropna().iloc[0]).round(4).tolist(),
            "src": str(d.idx_source.iloc[0]),
            **{f"F{w}": (d[f"F{w}"] * 100).round(4).tolist() for w in WINS}}
pe = pd.read_csv("POLICY_EVENTS.csv")
PE = [{"d": r.event_date, "t": r.description[:60], "c": r.category}
      for r in pe.itertuples()]
PAYLOAD = json.dumps({"D": D, "PE": pe.event_date.tolist(),
                      "GROUPS": GROUPS, "WINS": WINS}, ensure_ascii=False)

HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>ETF-FLOW-R2 归一化资金流与政策状态</title>
<script>__PLOTLY__</script>
<style>body{font-family:-apple-system,sans-serif;margin:12px;background:#fafafa}
.bar{margin:6px 0;font-size:13px}button{margin-right:4px;padding:2px 8px}
.sel{border:1px solid #999;border-radius:4px;background:#fff}
.on{background:#cde}input{padding:2px 4px;width:90px}
footer{font-size:11px;color:#666;max-width:1100px}</style></head><body>
<div class="bar"><b>分组</b><span id="grp"></span>&nbsp;&nbsp;<b>窗口</b><span id="win"></span>
&nbsp;&nbsp;<b>口径</b><button id="mode" class="sel on">F强度%</button>
&nbsp;&nbsp;日期 <input id="d0" placeholder="2024-01-01">—<input id="d1" placeholder="2026-10-27">
<button onclick="applyR()">应用</button><button onclick="resetR()">全部</button></div>
<div id="c" style="height:80vh"></div>
<footer>比例口径：F_W(t)=窗口净申购合计/窗口期初ETF净资产×100%。绝对金额为辅助。
政策竖线=官方事件(POLICY_EVENTS.csv)。机构/个人归因不可得；科技组指数为市值加权代理。
数据：交易所份额×基金净值（一级市场申赎估计）。research_only。</footer>
<script>
const P=__PAYLOAD__;let G="G2_hs300_head",W=20,MODE="F";
const gdiv=document.getElementById("grp"),wdiv=document.getElementById("win");
P.GROUPS.forEach(g=>{let b=document.createElement("button");b.textContent=g;
 b.className="sel"+(g==G?" on":"");b.onclick=()=>{G=g;draw();upd()};gdiv.appendChild(b)});
P.WINS.forEach(w=>{let b=document.createElement("button");b.textContent="F"+w;
 b.className="sel"+(w==W?" on":"");b.onclick=()=>{W=w;draw();upd()};wdiv.appendChild(b)});
document.getElementById("mode").onclick=e=>{MODE=MODE=="F"?"A":"F";e.target.textContent=MODE=="F"?"F强度%":"金额(亿)";draw()};
function upd(){[...gdiv.children].forEach(b=>b.classList.toggle("on",b.textContent==G));
 [...wdiv.children].forEach(b=>b.classList.toggle("on",b.textContent=="F"+W))}
function range(){let D0=P.D[G].d;return [document.getElementById("d0").value||D0[0],
 document.getElementById("d1").value||D0[D0.length-1]]}
function applyR(){draw()}function resetR(){document.getElementById("d0").value="";document.getElementById("d1").value="";draw()}
function draw(){let d=P.D[G];
 let y=MODE=="F"?d["F"+W]:d.flow;
 let t1={type:"scatter",x:d.d,y:d.idx,mode:"lines",name:"指数(归一)",line:{color:"#000",width:1},yaxis:"y2"};
 let t0=MODE=="F"?{type:"scatter",x:d.d,y:y,mode:"lines",name:"F"+W+" 强度%",
  line:{color:"#a00",width:1},fill:"tozeroy",fillcolor:"rgba(200,0,0,.12)"}
  :{type:"bar",x:d.d,y:y,name:"日净申购(亿)",marker:{color:y.map(v=>v>=0?"#c33":"#2a7")}};
 let sh=P.PE.map(x=>({type:"line",x0:x,x1:x,y0:0,y1:1,yref:"paper",
  line:{color:"#36c",width:1,dash:"dot"}}));
 let [r0,r1]=range();
 Plotly.react("c",[t0,t1],{xaxis:{range:[r0,r1],rangeslider:{visible:false},
  hoverformat:"%Y-%m-%d"},yaxis:{title:MODE=="F"?"F"+W+" %":"亿元",zeroline:true},
  yaxis2:{overlaying:"y",side:"right",title:"指数"},shapes:sh,hovermode:"x unified",
  legend:{orientation:"h",y:1.08},margin:{t:40,b:40,l:60,r:60},
  title:G+" | "+d.src},{responsive:true})}
draw();
</script></body></html>"""

html = (HTML.replace("__PLOTLY__", get_plotlyjs())
            .replace("__PAYLOAD__", PAYLOAD))
open("etf_flow_r2_interactive.html", "w").write(html)
print("html bytes:", len(html))
