"""R2.1 single-file offline interactive HTML."""
import json
import pandas as pd
from plotly.offline import get_plotlyjs

GROUPS = ["G2_hs300_head", "G1_all_equity", "G9_sse50_head", "G3_other_broad",
          "G4k_star", "G5_semiconductor", "G6_ai_compute", "G7_robot",
          "G8_softinfo"]
WINS = [5, 20, 40, 60]
D, ST = {}, {}
for g in GROUPS:
    d = pd.read_parquet(f"data/factors_{g}.parquet")
    d.index = pd.to_datetime(d.index)
    D[g] = {"d": [str(x)[:10] for x in d.index],
            "flow": d.flow.round(2).tolist(),
            "idx": (d.idx_level / d.idx_level.dropna().iloc[0]).round(4).tolist(),
            "src": str(d.idx_source.iloc[0]),
            "WP": d.WP.round(1).tolist(), "AS": d.AS.round(1).tolist(),
            "state": d.state.tolist(),
            **{f"F{w}": (d[f"F{w}"] * 100).round(4).tolist() for w in WINS}}
tr = pd.read_csv("WARNING_TRANSITIONS.csv")
tr["trigger"] = (tr["from"] + "→" + tr["to"] + " WP=" + tr.WP.astype(str) +
                 " F20=" + (tr.F20 * 100).round(1).astype(str) + "%")
ST["trans"] = tr[["date", "trigger"]].to_dict("records")
pe = pd.read_csv("../etf_flow_r2/POLICY_EVENTS.csv")
PAYLOAD = json.dumps({"D": D, "ST": ST, "PE": pe.event_date.tolist(),
                      "GROUPS": GROUPS, "WINS": WINS}, ensure_ascii=False)

HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>ETF-R2.1 资金风险预警</title>
<script>__PLOTLY__</script>
<style>body{font-family:-apple-system,sans-serif;margin:12px;background:#fafafa}
.bar{margin:6px 0;font-size:13px}button{margin-right:4px;padding:2px 8px}
.sel{border:1px solid #999;border-radius:4px;background:#fff}
.on{background:#cde}input{padding:2px 4px;width:90px}
footer{font-size:11px;color:#666;max-width:1150px}</style></head><body>
<div class="bar"><b>分组</b><span id="grp"></span>&nbsp;&nbsp;<b>窗口</b><span id="win"></span>
&nbsp;&nbsp;<b>口径</b><button id="mode" class="sel on">F强度%</button>
<button id="sc" class="sel on">WP/AS</button>
&nbsp;&nbsp;年份<button class="sel yr" onclick="setY('')">全部</button>
<button class="sel yr" onclick="setY('2024')">2024</button>
<button class="sel yr" onclick="setY('2025')">2025</button>
<button class="sel yr" onclick="setY('2026')">2026</button>
&nbsp;&nbsp;<input id="d0" placeholder="YYYY-MM-DD">—<input id="d1">
<button onclick="draw()">应用</button>
&nbsp;&nbsp;政策<button id="pl" class="sel on">显示</button>
&nbsp;&nbsp;<button onclick="csv()">导出CSV</button></div>
<div id="c" style="height:80vh"></div>
<footer>WP/AS=历史扩展百分位合成的撤离压力/承接强度(0-100,PIT,min252d)。状态色带：
WATCH黄/ELEVATED橙/HIGH_PRESSURE红/RECOVERING蓝——是资金状态标签,非已校准风险等级。
规则见 PRE_REGISTERED_RULES.json。机构归因不可得;科技组多为市值加权代理指数。research_only。</footer>
<script>
const P=__PAYLOAD__;let G="G2_hs300_head",W=20,MODE="F",SHOWPOL=true;
const gdiv=document.getElementById("grp"),wdiv=document.getElementById("win");
P.GROUPS.forEach(g=>{let b=document.createElement("button");b.textContent=g;
 b.className="sel"+(g==G?" on":"");b.onclick=()=>{G=g;upd();draw()};gdiv.appendChild(b)});
P.WINS.forEach(w=>{let b=document.createElement("button");b.textContent="F"+w;
 b.className="sel"+(w==W?" on":"");b.onclick=()=>{W=w;upd();draw()};wdiv.appendChild(b)});
document.getElementById("mode").onclick=e=>{MODE=MODE=="F"?"A":"F";
 e.target.textContent=MODE=="F"?"F强度%":"金额(亿)";draw()};
document.getElementById("sc").onclick=e=>{MODE=MODE=="S"?"F":"S";
 e.target.textContent=MODE=="S"?"WP/AS✓":"WP/AS";draw()};
document.getElementById("pl").onclick=e=>{SHOWPOL=!SHOWPOL;
 e.target.textContent=SHOWPOL?"显示":"隐藏";draw()};
function upd(){[...gdiv.children].forEach(b=>b.classList.toggle("on",b.textContent==G));
 [...wdiv.children].forEach(b=>b.classList.toggle("on",b.textContent=="F"+W))}
let YR="";function setY(y){YR=y;draw()}
const SC={"WATCH":"rgba(255,220,80,.45)","ELEVATED":"rgba(255,160,60,.5)",
 "HIGH_PRESSURE":"rgba(255,80,80,.45)","RECOVERING":"rgba(120,200,255,.45)"};
function range(){let d=P.D[G].d;return YR?[YR+"-01-01",YR+"-12-31"]:
 [document.getElementById("d0").value||d[0],
  document.getElementById("d1").value||d[d.length-1]]}
function bands(d){let sh=[],s0=0,st=d.state[0];
 for(let i=1;i<=d.state.length;i++){if(i==d.state.length||d.state[i]!=st){
  if(SC[st])sh.push({type:"rect",x0:d.d[s0],x1:d.d[i-1],y0:0,y1:1,yref:"paper",
   fillcolor:SC[st],line:{width:0},layer:"below"});
  s0=i;st=d.state[i]}}return sh}
function draw(){let d=P.D[G],[r0,r1]=range();
 let t1={type:"scatter",x:d.d,y:d.idx,mode:"lines",name:"指数(归一)",
  line:{color:"#000",width:1},yaxis:"y3"};
 let trs=[t1];
 if(MODE=="A")trs.push({type:"bar",x:d.d,y:d.flow,name:"日净申购(亿)",
  marker:{color:d.flow.map(v=>v>=0?"#c33":"#2a7")},yaxis:"y"});
 else if(MODE=="S"){trs.push({type:"scatter",x:d.d,y:d.WP,name:"WP撤离压力",
   line:{color:"#c33",width:1.2},yaxis:"y2"},
  {type:"scatter",x:d.d,y:d.AS,name:"AS承接强度",line:{color:"#2a7",width:1.2},
   yaxis:"y2"})}
 else trs.push({type:"scatter",x:d.d,y:d["F"+W],name:"F"+W+" %",
  line:{color:"#a00",width:1},fill:"tozeroy",yaxis:"y",
  fillcolor:"rgba(200,0,0,.12)"});
 let tr=P.ST.trans.filter(t=>t.date>=r0&&t.date<=r1);
 trs.push({type:"scatter",x:tr.map(t=>t.date),
  y:tr.map(t=>d.idx[d.d.indexOf(t.date)]||null),mode:"markers",
  marker:{size:9,color:"#a0a",symbol:"diamond"},yaxis:"y3",
  text:tr.map(t=>t.trigger),name:"状态转移",hovertemplate:"%{x} %{text}"});
 let sh=bands(d);
 if(SHOWPOL)P.PE.forEach(x=>sh.push({type:"line",x0:x,x1:x,y0:0,y1:1,
  yref:"paper",line:{color:"#36c",width:1,dash:"dot"}}));
 Plotly.react("c",trs,{xaxis:{range:[r0,r1],hoverformat:"%Y-%m-%d"},
  yaxis:{title:"F%/亿元",zeroline:true,domain:[0,.32]},
  yaxis2:{title:"WP/AS",range:[0,100],domain:[0,.32],side:"right"},
  yaxis3:{title:"指数",domain:[.36,1]},
  shapes:sh,hovermode:"x unified",legend:{orientation:"h",y:1.06},
  margin:{t:40,b:40,l:60,r:60},title:G+" | "+d.src},{responsive:true})}
function csv(){let d=P.D[G],rows=["date,flow,F"+W+",WP,AS,state,idx"];
 d.d.forEach((x,i)=>rows.push([x,d.flow[i],d["F"+W][i],d.WP[i],d.AS[i],
  d.state[i],d.idx[i]].join(",")));
 let a=document.createElement("a");a.href=URL.createObjectURL(new Blob(
  [rows.join("\\n")],{type:"text/csv"}));a.download=G+"_warning.csv";a.click()}
draw();
</script></body></html>"""

html = (HTML.replace("__PLOTLY__", get_plotlyjs())
            .replace("__PAYLOAD__", PAYLOAD))
open("etf_risk_warning_poc.html", "w").write(html)
print("html bytes:", len(html))
