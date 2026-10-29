"""R3 single-file offline interactive HTML — capital withdrawal cycles."""
import json
import pandas as pd
from plotly.offline import get_plotlyjs

GROUPS = ["G2_hs300_head", "G1_all_equity", "G9_sse50_head", "G3_other_broad",
          "G4k_star", "G5_semiconductor", "G6_ai_compute", "G7_robot",
          "G8_softinfo"]
dd = pd.read_csv("FUND_FLOW_CYCLE_DAILY.csv", parse_dates=["date"])
cyc = pd.read_csv("FUND_FLOW_CYCLES.csv")
D = {}
for g in GROUPS:
    d = pd.read_parquet(f"../etf_flow_r21/data/factors_{g}.parquet")
    d.index = pd.to_datetime(d.index)
    dd_g = dd[dd.group == g].set_index("date")
    B = d.flow.cumsum()
    D[g] = {"d": [str(x)[:10] for x in d.index],
            "flow": d.flow.round(2).tolist(),
            "idx": (d.idx_level / d.idx_level.dropna().iloc[0]).round(4).tolist(),
            "src": str(d.idx_source.iloc[0]),
            "B": B.round(1).tolist(),
            "F20": (d.F20 * 100).round(3).tolist(),
            "fstate": dd_g.fstate.reindex(d.index).fillna("NEUTRAL").tolist(),
            "depth": (dd_g.depth.reindex(d.index) * 100).round(2).tolist(),
            "breadth": d.breadth_out.round(3).tolist()}
    D[g]["cycles"] = [{"s": r.start, "e": (r.end_live if
                       isinstance(r.end_live, str) and r.end_live else
                       str(d.index[-1])[:10]), "id": r.cycle_id,
                       "status": r.status, "dep": round(r.depth_max * 100, 1)}
                      for r in cyc[cyc.group == g].itertuples()]
pe = pd.read_csv("../etf_flow_r2/POLICY_EVENTS.csv")
PAYLOAD = json.dumps({"D": D, "PE": pe.event_date.tolist(), "GROUPS": GROUPS},
                     ensure_ascii=False)

HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>ETF-R3 资金配置周期</title>
<script>__PLOTLY__</script>
<style>body{font-family:-apple-system,sans-serif;margin:12px;background:#fafafa}
.bar{margin:6px 0;font-size:13px}button{margin-right:4px;padding:2px 8px}
.sel{border:1px solid #999;border-radius:4px;background:#fff}
.on{background:#cde}input{padding:2px 4px;width:90px}
footer{font-size:11px;color:#666;max-width:1150px}</style></head><body>
<div class="bar"><b>分组</b><span id="grp"></span>
&nbsp;&nbsp;<b>视图</b><button id="m1" class="sel on">累计余额</button>
<button id="m2" class="sel">撤离深度%</button><button id="m3" class="sel">F20%</button>
&nbsp;&nbsp;年份<button class="sel" onclick="Y='';draw()">全部</button>
<button class="sel" onclick="Y='2024';draw()">2024</button>
<button class="sel" onclick="Y='2025';draw()">2025</button>
<button class="sel" onclick="Y='2026';draw()">2026</button>
<input id="d0" placeholder="YYYY-MM-DD">—<input id="d1"><button onclick="draw()">应用</button>
&nbsp;&nbsp;政策<button id="pl" class="sel on">显示</button>
&nbsp;&nbsp;<button onclick="csv()">导出CSV</button></div>
<div id="c" style="height:80vh"></div>
<footer>资金周期：余额回撤法（CYCLE_DEFINITION.md）。色带=事前可观察资金状态：
WITHDRAWING红/减速橙/稳定黄/回补绿。周期起止标注为事后统计字段(post_)，
当日仅能观察到 fstate 与深度——两者已区分。机构归因不可得。research_only。</footer>
<script>
const P=__PAYLOAD__;let G="G2_hs300_head",M="B",Y="",POL=true;
const gdiv=document.getElementById("grp");
P.GROUPS.forEach(g=>{let b=document.createElement("button");b.textContent=g;
 b.className="sel"+(g==G?" on":"");b.onclick=()=>{G=g;upd();draw()};gdiv.appendChild(b)});
[["m1","B"],["m2","depth"],["m3","F20"]].forEach(([id,m])=>{
 document.getElementById(id).onclick=e=>{M=m;
  ["m1","m2","m3"].forEach(x=>document.getElementById(x).classList.remove("on"));
  e.target.classList.add("on");draw()}});
document.getElementById("pl").onclick=e=>{POL=!POL;e.target.textContent=POL?"显示":"隐藏";draw()};
function upd(){[...gdiv.children].forEach(b=>b.classList.toggle("on",b.textContent==G))}
const SC={"WITHDRAWING":"rgba(255,120,120,.45)","WITHDRAWAL_DECELERATING":
 "rgba(255,190,90,.4)","FLOW_STABILIZING":"rgba(255,240,120,.4)",
 "REACCUMULATING":"rgba(120,220,120,.4)"};
function range(){let d=P.D[G].d;return Y?[Y+"-01-01",Y+"-12-31"]:
 [document.getElementById("d0").value||d[0],
  document.getElementById("d1").value||d[d.length-1]]}
function draw(){let d=P.D[G],[r0,r1]=range();
 let y=M=="B"?d.B:(M=="depth"?d.depth:d.F20);
 let t0={type:"scatter",x:d.d,y:y,mode:"lines",
  name:M=="B"?"累计净申购(亿)":(M=="depth"?"撤离深度%":"F20%"),
  line:{color:"#c33",width:1},fill:M=="F20"?"tozeroy":"none"};
 let t1={type:"scatter",x:d.d,y:d.idx,mode:"lines",name:"指数(归一)",
  line:{color:"#000",width:1},yaxis:"y2"};
 let sh=[],s0=0,st=d.fstate[0];
 for(let i=1;i<=d.fstate.length;i++){if(i==d.fstate.length||d.fstate[i]!=st){
  if(SC[st])sh.push({type:"rect",x0:d.d[s0],x1:d.d[i-1],y0:0,y1:1,yref:"paper",
   fillcolor:SC[st],line:{width:0},layer:"below"});
  s0=i;st=d.fstate[i]}}
 if(POL)P.PE.forEach(x=>sh.push({type:"line",x0:x,x1:x,y0:0,y1:1,yref:"paper",
  line:{color:"#36c",width:1,dash:"dot"}}));
 let ann=d.cycles.map(c=>({x:c.s,y:1.02,yref:"paper",text:c.id+" "+c.dep+"%"+
  (c.status=="OPEN"?" OPEN":""),showarrow:false,font:{size:9}}));
 Plotly.react("c",[t0,t1],{xaxis:{range:[r0,r1],hoverformat:"%Y-%m-%d"},
  yaxis:{title:M=="B"?"亿元":"%",zeroline:true},
  yaxis2:{overlaying:"y",side:"right",title:"指数"},
  shapes:sh,annotations:ann,hovermode:"x unified",
  legend:{orientation:"h",y:1.08},margin:{t:40,b:40,l:60,r:60},
  title:G+" | "+d.src},{responsive:true})}
function csv(){let d=P.D[G],rows=["date,flow,B,F20,depth,fstate,idx"];
 d.d.forEach((x,i)=>rows.push([x,d.flow[i],d.B[i],d.F20[i],d.depth[i],
  d.fstate[i],d.idx[i]].join(",")));
 let a=document.createElement("a");a.href=URL.createObjectURL(new Blob(
  [rows.join("\\n")],{type:"text/csv"}));a.download=G+"_cycles.csv";a.click()}
draw();
</script></body></html>"""

html = (HTML.replace("__PLOTLY__", get_plotlyjs())
            .replace("__PAYLOAD__", PAYLOAD))
open("etf_capital_cycle_r3.html", "w").write(html)
print("html bytes:", len(html))
