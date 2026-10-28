"""ETF-FLOW-POC-03 — single-file interactive HTML (offline-capable).

Reads existing POC-02.1 daily lane flows and emits
etf_flow_interactive.html with plotly.js inlined (no backend, no CDN).

Modes: cumulative line / daily bar; classification: pit / fixed;
lanes: personal + institution on by default, mixed/pre_disclosure/
unknown toggleable via legend (never merged into personal).
"""
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
DATA = HERE / "data"
LANES = ["personal", "institution", "mixed", "pre_disclosure", "unknown"]


def load():
    out = {}
    dates = None
    for mode in ("pit", "fixed"):
        d = pd.read_csv(DATA / f"daily_flow_class_{mode}.csv",
                        parse_dates=["date"], index_col="date")
        if dates is None:
            dates = [x.strftime("%Y-%m-%d") for x in d.index]
        out[mode] = {
            lane: [round(float(v), 2) for v in d[lane].fillna(0)]
            for lane in LANES if lane in d.columns}
    return dates, out


def build():
    dates, flows = load()
    try:
        from plotly.offline import get_plotlyjs
        plotly_js = get_plotlyjs()
    except Exception:
        plotly_js = ""
    payload = json.dumps({"dates": dates, "flows": flows},
                         separators=(",", ":"))
    html = TEMPLATE.replace("/*__PLOTLY__*/", plotly_js) \
                   .replace("/*__DATA__*/", payload)
    out = HERE / "etf_flow_interactive.html"
    out.write_text(html, encoding="utf-8")
    print("saved", out, f"{out.stat().st_size/1e6:.1f}MB")


TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>ETF 累计净申购 · 交互图表（POC-03）</title>
<style>
 body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  margin:16px;color:#222}
 .bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:6px}
 .bar label{font-size:13px;color:#444}
 .bar select,.bar button,.bar input{font-size:13px;padding:3px 8px;
  border:1px solid #bbb;border-radius:4px;background:#fff;cursor:pointer}
 .bar button:hover{background:#eef3fa}
 .note{font-size:12px;color:#555;line-height:1.7;margin-top:4px;
  border-top:1px solid #ddd;padding-top:8px}
 .note b{color:#a04030}
 #chart{width:100%;height:72vh}
 .chk{display:flex;align-items:center;gap:4px;font-size:12px;color:#444}
</style></head><body>
<h3 style="margin:4px 0">ETF 累计净申购 · 个人 / 机构持有为主
<small style="font-weight:normal;color:#666">（POC-03 ·
2020-01-02 ~ 2026-10-27 · 真实日频数据）</small></h3>
<div class="bar">
 <label>分类口径 <select id="cls">
  <option value="pit" selected>PIT-rolling 滚动</option>
  <option value="fixed">latest-fixed 固定</option></select></label>
 <label>纵轴 <select id="ymode">
  <option value="cum" selected>累计净申购(亿元)</option>
  <option value="day">单日净申购(亿元)</option></select></label>
 <span>区间：</span>
 <button onclick="setRange('all')">全部</button>
 <button onclick="setRange('2024')">2024</button>
 <button onclick="setRange('2025')">2025</button>
 <button onclick="setRange('2026')">2026</button>
 <span class="chk"><input type="checkbox" id="recum">区间重新累计</span>
 <span style="flex:1"></span>
 <button onclick="exportPNG()">导出PNG</button>
 <button onclick="exportCSV()">导出所选区间CSV</button>
</div>
<div id="chart"></div>
<div class="note">
 <b>口径说明</b>：数据源=上交所/深交所每日 ETF 份额 × 天天基金单位净值；
 资金流=当日份额变化×当日单位净值（一级市场申赎估算，
 <b>非二级市场成交额</b>）。分类=基金历期持有人披露，机构占比&gt;50%入
 机构车道；PIT 滚动按"披露截止日+90天"假设生效（4只宽基经实际公告日
 抽样吻合），latest-fixed 恒用最新一期。混合/未披露/未知单独成列，
 图例点击可开启，默认不并入个人。IPO 首日、缺失段、已鉴别拆分合并
 (10)、数据毛刺(105)、待核验(85)行已剔除并单列；
 510310 2024-09-19/20 跨日份额合并为已知待核验点（机构车道约低估
 1906亿）。<b>机构主导 ETF 的净赎回为数据事实，不等于任何特定机构
 主体的实际减持。</b>
</div>
<script>/*__PLOTLY__*/</script>
<script>
const D=/*__DATA__*/;
const LANES=[["personal","个人持有为主 ETF","#1a1a2e"],
 ["institution","机构持有为主 ETF","#7ea6d8"],
 ["mixed","混合(两侧均≤50%)","#c9a227"],
 ["pre_disclosure","尚无生效披露","#7fc8a9"],
 ["unknown","分类未知","#999999"]];
const DATES=D.dates;
let state={cls:"pit",ymode:"cum",range:[DATES[0],DATES[DATES.length-1]],
 recum:false};
function cumsum(a){let s=0;return a.map(v=>s+=v);}
function traces(){
 const src=D.flows[state.cls];
 const i0=DATES.indexOf(state.range[0])<0?0:DATES.indexOf(state.range[0]);
 return LANES.map(([key,lab,col],i)=>{
  const daily=src[key]||DATES.map(()=>0);
  let y,typ;
  if(state.ymode==="cum"){
   y=cumsum(state.recum?daily.slice(i0):daily);typ="scatter";
   if(state.recum)y=y.concat(); // same length handled by x slice
  }else{y=daily;typ="bar";}
  return {x:DATES,y:y,type:typ,name:lab,mode:"lines",
   marker:{color:col},line:{color:col,width:typ==="bar"?0:2.2},
   visible:i<2?true:"legendonly",
   hovertemplate:"%{x}<br>"+lab+": %{y:.1f}亿<extra></extra>"};});
}
function layout(){
 return {barmode:"relative",hovermode:"x unified",
  dragmode:"pan",
  margin:{l:60,r:20,t:30,b:40},
  yaxis:{title:state.ymode==="cum"?"累计净申购（亿元，估算）"
          :"单日净申购（亿元，估算）",zeroline:true},
  xaxis:{type:"date",range:state.range},
  legend:{orientation:"h",y:-0.18},
  showlegend:true};}
function draw(){
 Plotly.react("chart",traces(),layout(),
  {responsive:true,scrollZoom:true,displaylogo:false,
   modeBarButtonsToRemove:["select2d","lasso2d"],
   toImageButtonOptions:{format:"png",filename:"etf_flow",scale:2}});
}
function setRange(y){
 const end=DATES[DATES.length-1];
 state.range=(y==="all")?[DATES[0],end]:[y+"-01-01",end];
 draw();
}
document.getElementById("cls").onchange=e=>{state.cls=e.target.value;draw();};
document.getElementById("ymode").onchange=e=>{state.ymode=e.target.value;draw();};
document.getElementById("recum").onchange=e=>{state.recum=e.target.checked;draw();};
function bindEvents(){
 const gd=document.getElementById("chart");
 if(!gd.on)return;
 gd.on("plotly_relayout",ev=>{
  if(ev["xaxis.range[0]"])state.range=[ev["xaxis.range[0]"].slice(0,10),
   ev["xaxis.range[1]"].slice(0,10)];
  else if(ev["xaxis.range"])state.range=[ev["xaxis.range"][0].slice(0,10),
   ev["xaxis.range"][1].slice(0,10)];
  else if(ev["xaxis.autorange"])state.range=[DATES[0],DATES[DATES.length-1]];});}
function exportPNG(){
 Plotly.toImage("chart",{format:"png",width:1600,height:900,scale:2})
 .then(u=>{const a=document.createElement("a");a.href=u;
  a.download="etf_flow.png";a.click();});}
function exportCSV(){
 const src=D.flows[state.cls];
 const i0=DATES.findIndex(d=>d>=state.range[0]);
 const i1=DATES.findIndex(d=>d>state.range[1]);
 const j1=i1<0?DATES.length:i1;
 const cum={};LANES.forEach(([k])=>{cum[k]=cumsum(src[k]||DATES.map(()=>0));});
 let csv="date,"+LANES.map(l=>l[0]+"_daily").join(",")+","+
  LANES.map(l=>l[0]+"_cum").join(",")+"\\n";
 for(let i=i0;i<j1;i++){
  csv+=DATES[i]+","+LANES.map(([k])=>((src[k]||[])[i]||0)).join(",")+","+
   LANES.map(([k])=>cum[k][i].toFixed(2)).join(",")+"\\n";}
 const a=document.createElement("a");
 a.href=URL.createObjectURL(new Blob([csv],{type:"text/csv"}));
 a.download="etf_flow_"+state.range[0]+"_"+state.range[1]+"_"+state.cls+
  ".csv";a.click();}
draw();
bindEvents();
</script></body></html>
"""

if __name__ == "__main__":
    sys.exit(build())
