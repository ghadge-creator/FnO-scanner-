let curPage=0,f1D="ALL",fTF="ALL",fSide="ALL",snd=false,alr=false,st=null,chart=null,sx=0,sy=0;
const box=document.getElementById("swipeContainer");
document.addEventListener("touchstart",e=>{if(!document.getElementById("chartModal").classList.contains("open")){sx=e.changedTouches.screenX;sy=e.changedTouches.screenY;}},{passive:true});
document.addEventListener("touchend",e=>{if(document.getElementById("chartModal").classList.contains("open"))return;const dx=e.changedTouches.screenX-sx,dy=e.changedTouches.screenY-sy;if(Math.abs(dx)>55&&Math.abs(dx)>Math.abs(dy)*1.4){if(dx<0&&curPage===0)goToPage(1);if(dx>0&&curPage===1)goToPage(0);}},{passive:true});
function goToPage(i){curPage=i;box.style.transform=`translateX(-${i*100}vw)`;document.getElementById("tab0").classList.toggle("active",i===0);document.getElementById("tab1").classList.toggle("active",i===1);}
function setFilter1D(v,el){f1D=v;el.parentElement.querySelectorAll(".pill").forEach(p=>p.classList.remove("active"));el.classList.add("active");renderAll();}
function setTfFilter(v,el){fTF=v;el.parentElement.querySelectorAll(".tf-pill").forEach(p=>p.classList.remove("active"));el.classList.add("active");renderAll();}
function setInstSideFilter(v,el){fSide=v;el.parentElement.querySelectorAll(".pill").forEach(p=>p.classList.remove("active"));el.classList.add("active");renderAll();}
function toggleSound(){snd=!snd;const b=document.getElementById("soundBtn");b.textContent=snd?"🔊 Sound: ON":"🔇 Sound: OFF";b.classList.toggle("on",snd);}
function toggleAlerts(){alr=!alr;if(alr&&"Notification"in window)Notification.requestPermission();const b=document.getElementById("alertBtn");b.textContent=alr?"🔔 Alerts: ON":"🔕 Alerts: OFF";b.classList.toggle("on",alr);}
async function triggerScan(){await fetch("/api/scan",{method:"POST"});fetchState();}
async function triggerRefresh(){await fetch("/api/refresh",{method:"POST"});fetchState();}
function closeChart(){document.getElementById("chartModal").classList.remove("open");if(chart){chart.remove();chart=null;}}
function toUnix(s){const m=String(s).match(/(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/);return m?Math.floor(Date.UTC(+m[1],+m[2]-1,+m[3],+(m[4]||0),+(m[5]||0))/1000):NaN;}
async function openChart(sym,tf,zt,zl,zh,ltp,ex){
  const m=document.getElementById("chartModal"),el=document.getElementById("tvChart");
  document.getElementById("mTitle").textContent=`${sym} (${tf}) • ₹${ltp}`;
  document.getElementById("mSub").textContent=`${zt} Zone: ₹${zl} – ₹${zh} ${ex?"• "+ex:""}`;
  m.classList.add("open");el.innerHTML=`<div style="padding:40px;text-align:center;color:#9ca3af;">Loading full-screen chart...</div>`;
  if(chart){chart.remove();chart=null;}
  try{
    const r=await fetch(`/api/chart/${encodeURIComponent(sym)}?tf=${encodeURIComponent(tf)}`),d=await r.json(),raw=d.candles||[];
    if(!raw.length){el.innerHTML=`<div style="padding:40px;text-align:center;color:#9ca3af;">No candle data available.</div>`;return;}
    el.innerHTML="";
    chart=LightweightCharts.createChart(el,{width:el.offsetWidth||window.innerWidth,height:el.offsetHeight||(window.innerHeight-58),layout:{background:{type:"solid",color:"#0b0f17"},textColor:"#d1d5db"},grid:{vertLines:{color:"#1f2937"},horzLines:{color:"#1f2937"}},rightPriceScale:{borderColor:"#374151"},timeScale:{borderColor:"#374151",timeVisible:tf!=="1D"&&tf!=="1W"},handleScroll:{mouseWheel:true,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:true},handleScale:{axisPressedMouseMove:true,mouseWheel:true,pinch:true}});
    const cs=chart.addCandlestickSeries({upColor:"#10b981",downColor:"#ef4444",borderUpColor:"#10b981",borderDownColor:"#ef4444",wickUpColor:"#10b981",wickDownColor:"#ef4444"});
    const seen=new Set(),bars=[];
    raw.forEach(c=>{const t=toUnix(c.t);if(!isNaN(t)&&!seen.has(t)){seen.add(t);bars.push({time:t,open:+c.o,high:+c.h,low:+c.l,close:+c.c});}});
    bars.sort((a,b)=>a.time-b.time);cs.setData(bars);
    const col=zt==="DEMAND"?"#10b981":"#ef4444";
    cs.createPriceLine({price:+zh,color:col,lineWidth:2,lineStyle:0,axisLabelVisible:true,title:`${zt} TOP`});
    cs.createPriceLine({price:+zl,color:col,lineWidth:2,lineStyle:0,axisLabelVisible:true,title:`${zt} BOT`});
    cs.createPriceLine({price:+ltp,color:"#60a5fa",lineWidth:1,lineStyle:2,axisLabelVisible:true,title:"LTP"});
    chart.timeScale().fitContent();
  }catch(e){el.innerHTML=`<div style="padding:40px;text-align:center;color:#f87171;">Error: ${e&&e.message?e.message:e}</div>`;}
}
function renderAll(){
  if(!st)return;
  const a=document.getElementById("angelStatus");a.textContent=st.angel_connected?"Connected":"Fallback";a.className=st.angel_connected?"ok":"warn";
  const mk=document.getElementById("marketStatus");mk.textContent=st.market_open?"OPEN":"CLOSED";mk.style.color=st.market_open?"#10b981":"#f87171";
  document.getElementById("lastScan").textContent=st.last_scan||"--:--:--";
  const t1=st.touches||[],inst=st.institutional||[];
  document.getElementById("touchCount").textContent=t1.length;document.getElementById("instCount").textContent=inst.length;
  document.getElementById("badge1d").textContent=t1.length;document.getElementById("badgeInst").textContent=inst.length;
  const bn=document.getElementById("refreshBanner");bn.style.display=st.is_refreshing?"block":"none";if(st.is_refreshing)bn.textContent=`Refreshing Zones... ${st.refresh_progress}`;
  document.getElementById("metaInfo").textContent=`${st.total_zones_1d} 1D zones (${st.demand_zones_1d} demand / ${st.supply_zones_1d} supply) • ${st.total_zones_mtf||0} All-TF zones • tap card for chart`;
  const l1=document.getElementById("list1D"),fl1=t1.filter(t=>f1D==="ALL"||t.zone_type===f1D);
  l1.innerHTML=!fl1.length?`<div class="empty">${st.market_open?"Scanning live F&O prices...":'Market is closed. Tap "Test Live Scan Now" to check latest closing data.'}</div>`:fl1.map(t=>`<div class="card" onclick="openChart('${t.symbol}','1D','${t.zone_type}',${t.zone_low},${t.zone_high},${t.ltp},'Strength ${t.strength}%')"><div class="card-top"><span class="sym">${t.symbol} 📊</span><span class="${t.zone_type==="DEMAND"?"tag-demand":"tag-supply"}">1D ${t.zone_type}</span></div><div class="card-mid"><span>LTP: <b>₹${t.ltp}</b></span><span>Zone: <b>₹${t.zone_low} – ₹${t.zone_high}</b></span></div><div class="meta-line" style="margin:0;">Origin: ${t.origin_ts} • Strength: ${t.strength}% • Tap for full chart</div></div>`).join("");
  const li=document.getElementById("listInst"),fli=inst.filter(x=>(fTF==="ALL"||x.timeframe===fTF)&&(fSide==="ALL"||x.inst_side===fSide));
  li.innerHTML=!fli.length?`<div class="empty">No strong institutional footprint for selected filter right now.<br><br>Swipe right ➔ to return to 1D Zones.</div>`:fli.map(x=>{const ib=x.inst_side==="INST_BUYING",rs=(x.reasons||[]).map(r=>`<span class="inst-chip">${r}</span>`).join("");return `<div class="card" style="border-left:4px solid ${ib?"#10b981":"#ef4444"};" onclick="openChart('${x.symbol}','${x.timeframe}','${x.zone_type}',${x.zone_low},${x.zone_high},${x.ltp},'Vol ${x.vol_ratio}x')"><div class="card-top"><div><span class="tag-tf">${x.timeframe}</span><span class="sym">${x.symbol} 📊</span></div><span class="${ib?"tag-demand":"tag-supply"}">${ib?"🔥 INST. BUYING":"🔥 INST. SELLING"}</span></div><div class="card-mid"><span>LTP: <b>₹${x.ltp}</b></span><span>Zone: <b>₹${x.zone_low} – ₹${x.zone_high}</b></span></div><div class="meta-line" style="margin:0;">Vol: <b>${x.vol_ratio}x</b> • Order Book: <b>${ib?x.buy_sell_ratio+"x Buy":x.sell_buy_ratio+"x Sell"}</b> • Tap for full chart</div><div class="inst-badges">${rs}</div></div>`;}).join("");
}
async function fetchState(){try{const r=await fetch("/api/state");if(r.ok){st=await r.json();renderAll();}}catch(e){}}
fetchState();setInterval(fetchState,8000);
