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
    idx = pd.read_csv(DATA / "index_daily.csv", index_col="date")
    idx = idx.reindex(dates)
    if int(idx.isna().sum().sum()):
        raise SystemExit("index_daily.csv has dates outside ETF calendar")
    index = {c: [round(float(v), 2) for v in idx[c]] for c in idx.columns}
    aum = {}
    for mode in ("pit", "fixed"):
        a = pd.read_csv(DATA / f"lane_aum_{mode}.csv", index_col="date")
        a = a.reindex(dates).fillna(0.0)
        aum[mode] = {lane: [round(float(a[lane].iloc[i]), 2)
                           if lane in a.columns else 0.0
                           for i in range(len(dates))]
                     for lane in LANES}
    return dates, out, coverage, index, aum


def build():
    dates, flows, coverage, index, aum = load()
    from plotly.offline import get_plotlyjs
    plotly_js = get_plotlyjs()
    payload = json.dumps(
        {"dates": dates, "flows": flows, "coverage": coverage,
         "index": index, "aum": aum},
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
 #chart{width:100%;height:74vh}
 .chk{display:flex;align-items:center;gap:4px;font-size:12px;color:#444}
 h4{margin:8px 0 2px;font-size:13px;color:#333}
 #chart .hoverlayer{display:none!important}
 #tip{display:none;position:fixed;z-index:99;pointer-events:none;
  background:#fff;border:1px solid #999;border-radius:4px;
  padding:6px 10px;font-size:12px;line-height:1.7;color:#111;
  box-shadow:0 2px 8px rgba(0,0,0,.15);max-width:320px}
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
 <label>展示口径 <select id="unit">
  <option value="amt" selected>金额(亿元)</option>
  <option value="pct">占当日规模%</option></select></label>
 <label>柱状图分类 <select id="barlane">
  <option value="all" selected>全部ETF</option>
  <option value="institution">机构主导</option>
  <option value="personal">个人主导</option></select></label>
 <span style="flex:1"></span>
 <button onclick="exportPNG()">导出PNG</button>
 <button onclick="exportCSV()">导出所选区间CSV</button>
</div>
<div id="chart"></div>
<div id="tip"></div>
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
 不等于任何特定机构主体的实际减持。</b><br>
 <b>指数曲线</b>：上证(000001)/深成(399001)来自新浪日线，
 中证全指(000985，全A口径)来自中证指数官网；金额口径下在右轴点位，
 占比口径下换算为区间起点涨跌幅%与强度同轴对照。<br>
 <b>占当日规模%</b>：每日=当日净申购/当日车道规模(份额×净值)，
 累计=逐日占比累加（强度口径，消除规模膨胀），指数同口径转 % 后可比。
</div>
<script>/*__PLOTLY__*/</script>
<script>
const D=/*__DATA__*/;
const LANES=[["personal","个人主导ETF","#1a1a2e"],
 ["institution","机构主导ETF","#7ea6d8"],
 ["mixed","混合型","#c9a227"],
 ["pre_disclosure","未披露生效","#7fc8a9"],
 ["unknown","未知","#999999"]];
const IDX=[["sse","上证指数","#e6550d","solid"],
 ["szse","深证成指","#756bb1","dot"],
 ["all_a","中证全指(全A)","#8c8c8c","dash"]];
const DATES=D.dates, COV=D.coverage, IX=D.index, AUM=D.aum;
let state={cls:"pit",recum:false,barlane:"all",unit:"amt",
 range:[DATES[0],DATES[DATES.length-1]]};
function cumsum(a){let s=0;return a.map(v=>s+=v);}
const CUM={};["pit","fixed"].forEach(m=>{CUM[m]={};
 LANES.forEach(([k])=>{CUM[m][k]=cumsum(D.flows[m][k]);});});
// 累计净申购强度 = Σ(当日净申购/当日车道规模)，消除规模膨胀
const PCTCUM={};["pit","fixed"].forEach(m=>{PCTCUM[m]={};
 LANES.forEach(([k])=>{let s=0;
  PCTCUM[m][k]=D.flows[m][k].map((f,i)=>{
   const a=AUM[m][k][i];s+=(a>0?f/a*100:0);return s;});});});
const IDXPCT={};IDX.forEach(([k])=>{const v0=IX[k][0];
 IDXPCT[k]=IX[k].map(v=>(v/v0-1)*100);});
function dailyPct(src,i){
 const laneSum=k=>src[k]?src[k][i]:0;
 const aumSum=k=>AUM[state.cls][k]?AUM[state.cls][k][i]:0;
 if(state.barlane==="all"){
  const f=LANES.reduce((s,[k])=>s+laneSum(k),0),
        a=LANES.reduce((s,[k])=>s+aumSum(k),0);
  return a>0?f/a*100:0;}
 const a=aumSum(state.barlane);
 return a>0?laneSum(state.barlane)/a*100:0;}
function sliceIdx(){
 let i0=DATES.findIndex(d=>d>=state.range[0]);if(i0<0)i0=0;
 let i1=DATES.findIndex(d=>d>state.range[1]);if(i1<0)i1=DATES.length;
 return [i0,i1];}
function traces(){
 const [i0]=sliceIdx();
 const src=D.flows[state.cls];
 const isP=state.unit==="pct";
 const t=LANES.map(([key,lab,col],i)=>{
  const full=isP?PCTCUM[state.cls][key]:CUM[state.cls][key];
  const off=state.recum?(i0>0?full[i0-1]:0):0;
  const vals=full.map(v=>v-off);
  return {x:DATES,y:vals,type:"scatter",mode:"lines",name:lab,
   line:{color:col,width:2.2},
   visible:i<2?true:"legendonly",
   legendgroup:"flows",legendgrouptitle:i===0?{text:"ETF车道"}:undefined,
   customdata:DATES,xaxis:"x",yaxis:"y",
   hovertemplate:"%{customdata} "+lab+": %{y:.2f}"+
    (isP?"%":" 亿")+"<extra></extra>"};});
 const dvals=DATES.map((_,i)=>{
  if(isP)return dailyPct(src,i);
  if(state.barlane==="all")
   return LANES.reduce((s,[k])=>s+(src[k]?src[k][i]:0),0);
  return src[state.barlane]?src[state.barlane][i]:0;});
 const yvals=DATES.map((_,i)=>{
  if(state.barlane==="all")
   return LANES.reduce((s,[k])=>s+(src[k]?src[k][i]:0),0);
  return src[state.barlane]?src[state.barlane][i]:0;});
 const qual=DATES.map((d,i)=>{
  const m=COV.missing[i]+COV.excluded[i];
  return "覆盖 "+COV.priced[i]+"/"+COV.reported[i]+
   (m?("；剔除/缺失 "+m+" 行"):"；无异常");});
 const bname={all:"全部ETF",institution:"机构主导",personal:"个人主导"}
  [state.barlane];
 t.push({x:DATES,y:dvals,type:"bar",name:"每日净申购·"+bname,
  marker:{color:dvals.map(v=>v>=0?"#c0392b":"#1e8449")},
  customdata:DATES.map((d,i)=>[d,qual[i],yvals[i]]),
  xaxis:"x",yaxis:"y2",showlegend:false,
  legendgroup:"daily",
  hovertemplate:"%{customdata[0]} 每日净申购·"+bname+
   (isP?": %{y:.2f}% (%{customdata[2]:.1f} 亿)":": %{y:.1f} 亿")+
   "<br>%{customdata[1]}<extra></extra>"});
 [["申购","#c0392b"],["赎回","#1e8449"]].forEach(([lab,col],i)=>{
  t.push({x:[DATES[0]],y:[null],type:"scatter",mode:"markers",
   name:lab,marker:{symbol:"square",size:10,color:col},
   xaxis:"x",yaxis:"y2",legendgroup:"daily",
   legendgrouptitle:i===0?{text:"每日柱"}:undefined,
   hoverinfo:"skip",showlegend:true});});
 IDX.forEach(([key,lab,col,dash],i)=>{
  t.push({x:DATES,y:isP?IDXPCT[key]:IX[key],type:"scatter",
   mode:"lines",name:lab,line:{color:col,width:1.4,dash:dash},
   xaxis:"x",yaxis:isP?"y":"y3",
   legendgroup:"index",
   legendgrouptitle:i===0?{text:isP?"指数(同轴%)":"指数(右轴)"}:undefined,
   hovertemplate:"%{x|%Y-%m-%d} "+lab+": %{y:.2f}"+
    (isP?"%":"")+"<extra></extra>"});});
 return t;}
const TICKSTOPS=[
 {dtickrange:[null,86400000*45],value:"%Y-%m-%d"},
 {dtickrange:[86400000*45,86400000*600],value:"%Y-%m"},
 {dtickrange:[86400000*600,null],value:"%Y"}];
function layout(){
 const isP=state.unit==="pct";
 return {hovermode:"x unified",dragmode:"pan",
  margin:{l:70,r:70,t:56,b:30},
  hoverlabel:{bgcolor:"#fff",bordercolor:"#999",
   font:{size:12,color:"#111"}},
  yaxis:{title:isP?"累计净申购强度 %":"累计净申购（亿元）",
   domain:[0.20,1],zeroline:true,fixedrange:true},
  yaxis2:{title:isP?"当日净申购/规模 %":"每日净申购（亿元）",
   domain:[0,0.14],zeroline:true,zerolinecolor:"#888",
   fixedrange:true},
  yaxis3:{title:"指数点位",overlaying:"y",side:"right",
   showgrid:false,fixedrange:true,visible:!isP},
  xaxis:{type:"date",anchor:"y2",side:"bottom",range:state.range,
   hoverformat:"%Y-%m-%d",tickmode:"auto",nticks:12,
   tickformatstops:TICKSTOPS},
  bargap:0.15,
  legend:{orientation:"h",x:0,y:1.0,yref:"container",
   xanchor:"left",yanchor:"top",font:{size:11},
   groupclick:"toggleitem"},
  showlegend:true};}
function draw(){
 const cfg={responsive:true,scrollZoom:true,displaylogo:false,
  modeBarButtonsToRemove:["select2d","lasso2d"],
  toImageButtonOptions:{format:"png",filename:"etf_flow",scale:2}};
 Plotly.react("chart",traces(),layout(),cfg);
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
document.getElementById("unit").onchange=e=>{state.unit=e.target.value;
 draw();};
document.getElementById("recum").onchange=e=>{state.recum=e.target.checked;
 draw();};
function normDate(v){
 return (typeof v==="string"?v:v.toISOString()).slice(0,10);}
let syncing=false;
function tipHTML(d){
 const i=DATES.indexOf(d);if(i<0)return null;
 const src=D.flows[state.cls];
 const [i0]=sliceIdx();
 const gd=document.getElementById("chart");
 let html="<b>"+d+"</b>";
 LANES.forEach(([key,lab,col],j)=>{
  const vis=j<2||gd.data[j].visible===true;
  if(!vis)return;
  const cv=CUM[state.cls][key][i]-
   (state.recum&&i0>0?CUM[state.cls][key][i0-1]:0);
  const pv=PCTCUM[state.cls][key][i]-
   (state.recum&&i0>0?PCTCUM[state.cls][key][i0-1]:0);
  html+="<br><span style='color:"+col+"'>■</span> "+lab+
   (state.unit==="pct"?
    " 累计强度: <b>"+pv.toFixed(2)+"%</b> ("+cv.toFixed(1)+" 亿)":
    " 累计: <b>"+cv.toFixed(1)+"</b> 亿");});
 const dv=(state.barlane==="all")?
  LANES.reduce((s,[k])=>s+(src[k]?src[k][i]:0),0):
  (src[state.barlane]?src[state.barlane][i]:0);
 const dp=dailyPct(src,i);
 const bname={all:"全部ETF",institution:"机构主导",
  personal:"个人主导"}[state.barlane];
 const m=COV.missing[i]+COV.excluded[i];
 html+="<br><span style='color:"+(dv>=0?"#c0392b":"#1e8449")+
  "'>■</span> 每日净申购·"+bname+
  (state.unit==="pct"?
   ": <b>"+dp.toFixed(2)+"%</b> ("+dv.toFixed(1)+" 亿)":
   ": <b>"+dv.toFixed(1)+"</b> 亿");
 html+="<br><span style='color:#888'>覆盖 "+COV.priced[i]+"/"+
  COV.reported[i]+(m?("；剔除/缺失 "+m+" 行"):"；无异常")+"</span>";
 html+="<br><span style='color:#555'>上证 "+IX.sse[i].toFixed(1)+
  "("+(IDXPCT.sse[i]>=0?"+":"")+IDXPCT.sse[i].toFixed(1)+"%) · 深成 "+
  IX.szse[i].toFixed(1)+"("+(IDXPCT.szse[i]>=0?"+":"")+
  IDXPCT.szse[i].toFixed(1)+"%) · 全A "+IX.all_a[i].toFixed(1)+
  "("+(IDXPCT.all_a[i]>=0?"+":"")+IDXPCT.all_a[i].toFixed(1)+"%)</span>";
 return html;}
function bindEvents(){
 const gd=document.getElementById("chart"),
       tip=document.getElementById("tip");
 gd.on("plotly_hover",ev=>{
  if(!ev.points||!ev.points.length)return;
  const d=normDate(ev.points[0].x);
  const html=tipHTML(d);if(!html)return;
  Plotly.relayout(gd,{shapes:[{type:"line",xref:"x",x0:d,x1:d,
   yref:"paper",y0:0,y1:1,
   line:{color:"#666",width:1,dash:"dot"}}]});
  tip.innerHTML=html;tip.style.display="block";
  const r=tip.getBoundingClientRect();
  tip.style.left=Math.min(ev.event.clientX+15,innerWidth-r.width-8)+"px";
  tip.style.top=Math.min(ev.event.clientY-20,innerHeight-r.height-8)+"px";});
 gd.on("plotly_unhover",()=>{tip.style.display="none";
  Plotly.relayout(gd,{shapes:[]});});
 gd.on("plotly_relayout",ev=>{
  if(syncing)return;
  let r=null;
  for(const pre of["xaxis"]){
   if(ev[pre+".range[0]"])
    r=[normDate(ev[pre+".range[0]"]),normDate(ev[pre+".range[1]"])];
   else if(ev[pre+".range"])
    r=[normDate(ev[pre+".range"][0]),normDate(ev[pre+".range"][1])];
   else if(ev[pre+".autorange"])r=[DATES[0],DATES[DATES.length-1]];
   if(r)break;}
  if(!r)return;
  state.range=r;
  if(state.recum){syncing=true;draw();syncing=false;}});}
function exportPNG(){
 Plotly.toImage("chart",{format:"png",width:1600,height:900,scale:2})
 .then(u=>{const a=document.createElement("a");a.href=u;
  a.download="etf_flow_"+state.range[0]+"_"+state.range[1]+".png";
  a.click();});}
function exportCSV(){
 const src=D.flows[state.cls];
 const [i0,i1]=sliceIdx();
 let csv="date,"+LANES.map(l=>l[0]+"_daily").join(",")+","+
  LANES.map(l=>l[0]+"_cum").join(",")+",sse,szse,all_a\\n";
 for(let i=i0;i<i1;i++){
  csv+=DATES[i]+","+LANES.map(([k])=>src[k][i]).join(",")+","+
   LANES.map(([k])=>CUM[state.cls][k][i].toFixed(2)).join(",")+","+
   IX.sse[i]+","+IX.szse[i]+","+IX.all_a[i]+"\\n";}
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
