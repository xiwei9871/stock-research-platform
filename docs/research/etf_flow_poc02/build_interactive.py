"""ETF-FLOW-POC-03 — single-file interactive HTML (offline-capable).

Reads existing POC-02.1 daily lane flows + daily coverage and emits
etf_flow_interactive.html with plotly.js inlined (no backend, no CDN).

Top chart: cumulative net creation lines (PIT-rolling or latest-fixed).
Bottom chart: daily net-subscription bars (red=inflow, green=outflow),
selector 全部ETF / 机构主导 / 个人主导. Both charts share the x range;
a zoom/pan on either syncs the other. No data is recomputed, smoothed
or simulated — values come verbatim from the POC-02.1 pipeline output.
"""
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
DATA = HERE / "data"
LANES = ["personal", "institution", "mixed", "pre_disclosure", "unknown"]


def load():
    out, dates, coverage = {}, None, {}
    for mode in ("pit", "fixed"):
        d = pd.read_csv(DATA / f"daily_flow_class_{mode}.csv",
                        parse_dates=["date"], index_col="date")
        if dates is None:
            dates = [x.strftime("%Y-%m-%d") for x in d.index]
        for lane in LANES:
            if lane not in d.columns:
                d[lane] = 0.0
        out[mode] = {lane: [round(float(v), 2) for v in d[lane]]
                     for lane in LANES}
    cov = pd.read_csv(DATA / "daily_coverage.csv",
                      parse_dates=["date"], index_col="date")
    for lane, col in (("reported", "funds_reported"),
                      ("priced", "funds_priced"),
                      ("missing", "missing_valuation"),
                      ("excluded", "excluded_suspect_rows")):
        coverage[lane] = [int(v) for v in cov[col].fillna(0)]
    return dates, out, coverage


def build():
    dates, flows, coverage = load()
    from plotly.offline import get_plotlyjs
    plotly_js = get_plotlyjs()
    payload = json.dumps(
        {"dates": dates, "flows": flows, "coverage": coverage},
        separators=(",", ":"))
    html = TEMPLATE.replace("/*__PLOTLY__*/", plotly_js) \
                   .replace("/*__DATA__*/", payload)
    out = HERE / "etf_flow_interactive.html"
    out.write_text(html, encoding="utf-8")
    print("saved", out, f"{out.stat().st_size/1e6:.1f}MB")


TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>ETF 资金流监测 · 双图联动（POC-03）</title>
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
 #chartCum{width:100%;height:44vh}
 #chartDay{width:100%;height:30vh}
 .chk{display:flex;align-items:center;gap:4px;font-size:12px;color:#444}
 h4{margin:8px 0 2px;font-size:13px;color:#333}
</style></head><body>
<h3 style="margin:4px 0">ETF 资金流监测 · 双图联动
<small style="font-weight:normal;color:#666">（POC-03 ·
2020-01-02 ~ 2026-10-27 · 真实日频数据，净申购≠成交额）</small></h3>
<div class="bar">
 <label>分类口径 <select id="cls">
  <option value="pit" selected>PIT-rolling 滚动</option>
  <option value="fixed">latest-fixed 固定</option></select></label>
 <span>区间：</span>
 <button onclick="setRange('all')">全部</button>
 <button onclick="setRange('2024')">2024</button>
 <button onclick="setRange('2025')">2025</button>
 <button onclick="setRange('2026')">2026</button>
 <input type="date" id="dfrom">
 <span style="font-size:12px">至</span>
 <input type="date" id="dto">
 <button onclick="applyDates()">应用</button>
 <span class="chk"><input type="checkbox" id="recum">区间重新累计</span>
 <label>柱状图分类 <select id="barlane">
  <option value="all" selected>全部ETF</option>
  <option value="institution">机构主导</option>
  <option value="personal">个人主导</option></select></label>
 <span style="flex:1"></span>
 <button onclick="exportPNG()">导出PNG</button>
 <button onclick="exportCSV()">导出所选区间CSV</button>
</div>
<h4>上图：累计净申购（亿元）</h4>
<div id="chartCum"></div>
<h4>下图：每日净申购（亿元）　<span style="color:#c0392b">■ 申购</span>
 <span style="color:#1e8449">■ 赎回</span></h4>
<div id="chartDay"></div>
<div class="note">
 <b>口径说明</b>：数据源=上交所/深交所每日 ETF 份额 × 天天基金单位净值；
 资金流=当日份额变化×当日单位净值（一级市场申赎估算，
 <b>非二级市场成交额</b>）。分类=基金历期持有人披露，机构占比&gt;50%入
 机构车道；PIT 滚动按"披露截止日+90天"假设生效（4只宽基经实际公告日
 抽样吻合），latest-fixed 恒用最新一期。混合/未披露/未知单独成列，
 图例点击可开启，默认不并入个人；"全部ETF"柱状为五类合计。
 IPO 首日、缺失段、已鉴别拆分合并(10)、数据毛刺(105)、待核验(85)行
 已剔除并单列；510310 2024-09-19/20 跨日份额合并为已知待核验点
 （机构车道约低估1906亿）。<b>机构主导 ETF 的净赎回为数据事实，
 不等于任何特定机构主体的实际减持。</b>
</div>
<script>/*__PLOTLY__*/</script>
<script>
const D=/*__DATA__*/;
const LANES=[["personal","个人持有为主 ETF","#1a1a2e"],
 ["institution","机构持有为主 ETF","#7ea6d8"],
 ["mixed","混合(两侧均≤50%)","#c9a227"],
 ["pre_disclosure","尚无生效披露","#7fc8a9"],
 ["unknown","分类未知","#999999"]];
const DATES=D.dates, COV=D.coverage;
let state={cls:"pit",recum:false,barlane:"all",
 range:[DATES[0],DATES[DATES.length-1]]};
function cumsum(a){let s=0;return a.map(v=>s+=v);}
const CUM={};["pit","fixed"].forEach(m=>{CUM[m]={};
 LANES.forEach(([k])=>{CUM[m][k]=cumsum(D.flows[m][k]);});});
function sliceIdx(){
 let i0=DATES.findIndex(d=>d>=state.range[0]);if(i0<0)i0=0;
 let i1=DATES.findIndex(d=>d>state.range[1]);if(i1<0)i1=DATES.length;
 return [i0,i1];}
function cumTraces(){
 const [i0,i1]=sliceIdx();const xs=DATES.slice(i0,i1);
 return LANES.map(([key,lab,col],i)=>{
  const full=CUM[state.cls][key];
  const off=state.recum?(i0>0?full[i0-1]:0):0;
  const base=full.slice(i0,i1).map(v=>v-off);
  return {x:xs,y:base,type:"scatter",mode:"lines",name:lab,
   line:{color:col,width:2.2},
   visible:i<2?true:"legendonly",
   customdata:xs,
   xhoverformat:"%Y-%m-%d",
   hovertemplate:"%{customdata} "+lab+": %{y:.1f} 亿<extra></extra>"};});}
function dayTrace(){
 const src=D.flows[state.cls];
 const vals=DATES.map((_,i)=>{
  if(state.barlane==="all")
   return LANES.reduce((s,[k])=>s+(src[k]?src[k][i]:0),0);
  return src[state.barlane]?src[state.barlane][i]:0;});
 const qual=DATES.map((d,i)=>{
  const m=COV.missing[i]+COV.excluded[i];
  return "覆盖 "+COV.priced[i]+"/"+COV.reported[i]+
   (m?("；剔除/缺失 "+m+" 行"):"；无异常");});
 const name={all:"全部ETF",institution:"机构主导",personal:"个人主导"}
  [state.barlane];
 return {x:DATES,y:vals,type:"bar",name:"每日净申购·"+name,
  marker:{color:vals.map(v=>v>=0?"#c0392b":"#1e8449")},
  customdata:DATES.map((d,i)=>[d,qual[i]]),
  xhoverformat:"%Y-%m-%d",
  hovertemplate:"%{customdata[0]}<br>"+name+": %{y:.1f} 亿<br>"+
   "%{customdata[1]}<extra></extra>"};}
function layoutCum(){
 return {hovermode:"x unified",dragmode:"pan",
  margin:{l:60,r:20,t:10,b:30},
  hoverlabel:{bgcolor:"#fff",bordercolor:"#999",
   font:{size:12,color:"#111"}},
  yaxis:{title:"亿元",zeroline:true},
  xaxis:{type:"date",range:state.range,hoverformat:"%Y-%m-%d",
   tickmode:"auto",nticks:12,
   tickformatstops:[
    {dtickrange:[null,86400000*45],value:"%Y-%m-%d"},
    {dtickrange:[86400000*45,86400000*600],value:"%Y-%m"},
    {dtickrange:[86400000*600,null],value:"%Y"}]},
  legend:{orientation:"h",y:-0.22},showlegend:true};}
function layoutDay(){
 const l=layoutCum();
 l.yaxis={title:"亿元",zeroline:true,zerolinecolor:"#888"};
 l.showlegend=false;l.margin.t=10;
 l.hovermode="closest";
 return l;}
function draw(){
 const cfg={responsive:true,scrollZoom:true,displaylogo:false,
  modeBarButtonsToRemove:["select2d","lasso2d"],
  toImageButtonOptions:{format:"png",filename:"etf_flow",scale:2}};
 Plotly.react("chartCum",cumTraces(),layoutCum(),cfg);
 Plotly.react("chartDay",[dayTrace()],layoutDay(),cfg);
}
function setRange(y){
 const end=DATES[DATES.length-1];
 state.range=(y==="all")?[DATES[0],end]:[y+"-01-01",end];
 draw();
}
function applyDates(){
 const a=document.getElementById("dfrom").value,
       b=document.getElementById("dto").value;
 if(!a||!b)return;
 // 使用范围内实际存在的交易日，不虚构非交易日
 let lo=DATES.find(d=>d>=a)||DATES[0];
 let hi=[...DATES].reverse().find(d=>d<=b)||DATES[DATES.length-1];
 if(lo>hi){const t=lo;lo=hi;hi=t;}
 state.range=[lo,hi];draw();}
document.getElementById("cls").onchange=e=>{state.cls=e.target.value;draw();};
document.getElementById("barlane").onchange=e=>{state.barlane=e.target.value;
 draw();};
document.getElementById("recum").onchange=e=>{state.recum=e.target.checked;
 draw();};
let syncing=false;
function sync(gd){
 return ev=>{
  if(syncing)return;
  let r=null;
  if(ev["xaxis.range[0]"])r=[ev["xaxis.range[0]"].slice(0,10),
   ev["xaxis.range[1]"].slice(0,10)];
  else if(ev["xaxis.range"])r=[ev["xaxis.range"][0].slice(0,10),
   ev["xaxis.range"][1].slice(0,10)];
  else if(ev["xaxis.autorange"])r=[DATES[0],DATES[DATES.length-1]];
  if(!r)return;
  state.range=r;syncing=true;draw();syncing=false;};}
function bindEvents(){
 ["chartCum","chartDay"].forEach(id=>{
  const gd=document.getElementById(id);
  if(gd&&gd.on)gd.on("plotly_relayout",sync(gd));});}
function exportPNG(){
 Plotly.toImage("chartCum",{format:"png",width:1600,height:700,scale:2})
 .then(u=>{const a=document.createElement("a");a.href=u;
  a.download="etf_flow_cum.png";a.click();
  return Plotly.toImage("chartDay",{format:"png",width:1600,height:400,
   scale:2});})
 .then(u=>{const a=document.createElement("a");a.href=u;
  a.download="etf_flow_daily.png";a.click();});}
function exportCSV(){
 const src=D.flows[state.cls];
 const [i0,i1]=sliceIdx();
 let csv="date,"+LANES.map(l=>l[0]+"_daily").join(",")+","+
  LANES.map(l=>l[0]+"_cum").join(",")+"\\n";
 for(let i=i0;i<i1;i++){
  csv+=DATES[i]+","+LANES.map(([k])=>src[k][i]).join(",")+","+
   LANES.map(([k])=>CUM[state.cls][k][i].toFixed(2)).join(",")+"\\n";}
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
