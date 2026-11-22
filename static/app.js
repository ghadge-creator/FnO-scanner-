if("serviceWorker"in navigator){navigator.serviceWorker.getRegistrations().then(r=>r.forEach(x=>x.unregister()));}
let curPage=0,f1D="ALL",fTF="ALL",fSide="ALL",snd=false,alr=false,st=null,sx=0,sy=0,seenAlerts=new Set(),cData=[],cMeta=null,visCount=40,panOffset=0,dragX=0,pinchDist=0,inds={ema20:true,ema50:true,vol:true};
const box=document.getElementById("swipeContainer"),cvs=document.getElementById("zoneCanvas"),ctx=cvs.getContext("2d");
document.addEventListener("touchstart",e=>{if(!document.getElementById("chartModal").classList.contains("open")){sx=e.changedTouches.screenX;sy=e.changedTouches.screenY;}},{passive:true});
document.addEventListener("touchend",e=>{if(document.getElementById("chartModal").classList.contains("open"))return;const dx=e.changedTouches.screenX-sx,dy=e.changedTouches.screenY-sy;if(Math.abs(dx)>55&&Math.abs(dx)>Math.abs(dy)*1.4){if(dx<0&&curPage===0)goToPage(1);if(dx>0&&curPage===1)goToPage(0);}},{passive:true});
cvs.addEventListener("touchstart",e=>{if(e.touches.length===1)dragX=e.touches.clientX;else if(e.touches.length===2)pinchDist=Math.hypot(e.touches.clientX-e.touches.clientX,e.touches.clientY-e.touches.clientY);},{passive:true});
cvs.addEventListener("touchmove",e=>{if(!cData.length)return;if(e.touches.length===1){const dx=e.touches.clientX-dragX,sp=Math.max(4,(cvs.clientWidth-65)/visCount),sh=Math.round(dx/sp);if(sh!==0){panOffset=Math.max(0,Math.min(Math.max(0,cData.length-visCount),panOffset+sh));dragX=e.touches.clientX;drawZoneChart();}}else if(e.touches.length===2){const d=Math.hypot(e.touches.clientX-e.touches.clientX,e.touches.clientY-e.touches.clientY);if(Math.abs(d-pinchDist)>12){zoomChart(d>pinchDist?-4:4);pinchDist=d;}}},{passive:true});
function toggleInd(k,el){inds[k]=!inds[k];el.classList.toggle("on",inds[k]);drawZoneChart();}
function zoomChart(d){if(!cData.length)return;visCount=Math.max(12,Math.min(cData.length,visCount+d));panOffset=Math.min(panOffset,Math.max(0,cData.length-visCount));drawZoneChart();}
function goToPage(i){curPage=i;box.style.transform=`translateX(-${i*100}vw)`;document.getElementById("tab0").classList.toggle("active",i===0);document.getElementById("tab1").classList.toggle("active",i===1);}
function setFilter1D(v,el){f1D=v;el.parentElement.querySelectorAll(".pill").forEach(p=>p.classList.remove("active"));el.classList.add("active");renderAll();}
function setTfFilter(v,el){fTF=v;el.parentElement.querySelectorAll(".tf-pill").forEach(p=>p.classList.remove("active"));el.classList.add("active");renderAll();}
function setInstSideFilter(v,el){fSide=v;el.parentElement.querySelectorAll(".pill").forEach(p=>p.classList.remove("active"));el.classList.add("active");renderAll();}
function playBeep(){try{const c=new(window.AudioContext||window.webkitAudioContext)(),o=c.createOscillator(),g=c.createGain();o.type="sine";o.frequency.value=880;g.gain.value=0.25;o.connect(g);g.connect(c.destination);o.start();setTimeout(()=>o.frequency.value=1175,150);setTimeout(()=>{o.stop();c.close();},350);}catch(e){}}
function toggleSound(){snd=!snd;if(snd)playBeep();const b=document.getElementById("soundBtn");b.textContent=snd?"🔊 Sound: ON":"🔇 Sound: OFF";b.classList.toggle("on",snd);}
function toggleAlerts(){alr=!alr;if(alr&&"Notification"in window)Notification.requestPermission();const b=document.getElementById("alertBtn");b.textContent=alr?"🔔 Alerts: ON":"🔕 Alerts: OFF";b.classList.toggle("on",alr);}
function notifyNewTouches(list){let nw=false;list.forEach(t=>{const k=`${t.symbol}:${t.zone_type}:${t.zone_low}`;if(!seenAlerts.has(k)){seenAlerts.add(k);nw=true;if(alr&&"Notification"in window&&Notification.permission==="granted")new Notification(`🚨 1D ${t.zone_type}: ${t.symbol} @ ₹${t.ltp}`,{body:`Zone ₹${t.zone_low} – ₹${t.zone_high}`});}});if(nw&&snd)playBeep();}
async function triggerScan(){await fetch("/api/scan",{method:"POST"});fetchState();}
async function triggerRefresh(){await fetch("/api/refresh",{method:"POST"});fetchState();}
function closeChart(){document.getElementById("chartModal").classList.remove("open");}
function chartH(){return window.innerHeight-90-(document.getElementById("mInstBar").style.display==="block"?30:0);}
function calcEMA(arr,p){const k=2/(p+1),out=[];let pr=arr?arr.c:0;arr.forEach((c,i)=>{pr=i===0?c.c:(c.c*k+pr*(1-k));out.push(pr);});return out;}
async function openChart(sym,tf,zt,zl,zh,ltp,ex,ib){
  document.getElementById("mTitle").textContent=`${sym} (${tf}) • ₹${ltp}`;document.getElementById("mSub").textContent=`${zt} Zone: ₹${zl} – ₹${zh} ${ex?"• "+ex:""}`;
  const bar=document.getElementById("mInstBar");if(ib){bar.style.display="block";bar.textContent=ib;bar.style.color=ib.includes("BUYING")?"#34d399":"#f87171";}else bar.style.display="none";
  document.getElementById("chartModal").classList.add("open");cData=[];cMeta={zt,zl:+zl,zh:+zh,ltp:+ltp};panOffset=0;visCount=42;
  const dpr=window.devicePixelRatio||1,ch=chartH();cvs.width=window.innerWidth*dpr;cvs.height=ch*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.fillStyle="#0b0f17";ctx.fillRect(0,0,window.innerWidth,ch);ctx.fillStyle="#9ca3af";ctx.font="14px sans-serif";ctx.fillText("Loading candles & zone...",window.innerWidth/2-80,ch/2);
  try{const r=await fetch(`/api/chart/${encodeURIComponent(sym)}?tf=${encodeURIComponent(tf)}`),d=await r.json();cData=d.candles||[];visCount=Math.min(42,cData.length||42);drawZoneChart();}catch(e){ctx.fillStyle="#f87171";ctx.fillText("Could not load candles",window.innerWidth/2-70,ch/2);}
}
function drawZoneChart(){
  const w=window.innerWidth,h=chartH();ctx.fillStyle="#0b0f17";ctx.fillRect(0,0,w,h);
  if(!cData.length||!cMeta){ctx.fillStyle="#9ca3af";ctx.fillText("No candles available right now.",w/2-95,h/2);return;}
  const e20A=calcEMA(cData,20),e50A=calcEMA(cData,50),end=cData.length-panOffset,stI=Math.max(0,end-visCount),sl=cData.slice(stI,end),e20=e20A.slice(stI,end),e50=e50A.slice(stI,end);
  const pL=10,pR=62,pT=22,pB=26,cw=w-pL-pR,ch=h-pT-pB;
  let minP=Math.min(cMeta.zl,cMeta.ltp,...sl.map(c=>c.l)),maxP=Math.max(cMeta.zh,cMeta.ltp,...sl.map(c=>c.h));const pad=(maxP-minP)*0.08||1;minP-=pad;maxP+=pad;
  const yOf=p=>pT+((maxP-p)/(maxP-minP))*ch;
  ctx.strokeStyle="#1f2937";ctx.lineWidth=1;for(let g=0;g<=4;g++){const gy=pT+(ch*g)/4;ctx.beginPath();ctx.moveTo(pL,gy);ctx.lineTo(pL+cw,gy);ctx.stroke();}
  const yT=yOf(cMeta.zh),yB=yOf(cMeta.zl),zH=Math.max(6,yB-yT),isD=cMeta.zt==="DEMAND";
  ctx.fillStyle=isD?"rgba(16,185,129,0.24)":"rgba(239,68,68,0.24)";ctx.fillRect(pL,yT,cw,zH);ctx.strokeStyle=isD?"#10b981":"#ef4444";ctx.lineWidth=1.5;ctx.strokeRect(pL,yT,cw,zH);
  ctx.fillStyle=isD?"#34d399":"#f87171";ctx.font="bold 11px sans-serif";ctx.fillText(`${cMeta.zt} ZONE (₹${cMeta.zl} - ₹${cMeta.zh})`,pL+6,Math.max(pT+12,yT-5));
  const step=cw/sl.length,bw=Math.max(3,step*0.64),maxV=Math.max(1,...sl.map(c=>c.v||0));
  sl.forEach((c,i)=>{const x=pL+i*step+step/2,up=c.c>=c.o;if(inds.vol&&(c.v||0)>0){const vh=((c.v||0)/maxV)*(ch*0.22);ctx.fillStyle=up?"rgba(16,185,129,0.22)":"rgba(239,68,68,0.22)";ctx.fillRect(x-bw/2,pT+ch-vh,bw,vh);}ctx.strokeStyle=up?"#10b981":"#ef4444";ctx.fillStyle=up?"#10b981":"#ef4444";ctx.beginPath();ctx.moveTo(x,yOf(c.h));ctx.lineTo(x,yOf(c.l));ctx.stroke();const tB=yOf(Math.max(c.o,c.c)),bB=yOf(Math.min(c.o,c.c));ctx.fillRect(x-bw/2,tB,bw,Math.max(1.5,bB-tB));});
  if(inds.ema20){ctx.strokeStyle="#f59e0b";ctx.lineWidth=1.5;ctx.beginPath();e20.forEach((v,i)=>{const x=pL+i*step+step/2;i===0?ctx.moveTo(x,yOf(v)):ctx.lineTo(x,yOf(v));});ctx.stroke();}
  if(inds.ema50){ctx.strokeStyle="#a855f7";ctx.lineWidth=1.5;ctx.beginPath();e50.forEach((v,i)=>{const x=pL+i*step+step/2;i===0?ctx.moveTo(x,yOf(v)):ctx.lineTo(x,yOf(v));});ctx.stroke();}
  const yL=yOf(cMeta.ltp);ctx.setLineDash();ctx.strokeStyle="#60a5fa";ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(pL,yL);ctx.lineTo(pL+cw,yL);ctx.stroke();ctx.setLineDash([]);
  ctx.font="11px sans-serif";[maxP,cMeta.zh,cMeta.zl,minP].forEach(p=>{ctx.fillStyle="#9ca3af";ctx.fillText(p.toFixed(1),pL+cw+5,yOf(p)+4);});
  ctx.fillStyle="#2563eb";ctx.fillRect(pL+cw+2,yL-9,pR-4,18);ctx.fillStyle="#fff";ctx.font="bold 11px sans-serif";ctx.fillText(cMeta.ltp.toFixed(1),pL+cw+5,yL+4);
  ctx.fillStyle="#9ca3af";ctx.font="10px sans-serif";if(sl)ctx.fillText(sl.t,pL+4,h-8);if(sl[sl.length-1])ctx.fillText(sl[sl.length-1].t,pL+cw-95,h-8);
}
function renderAll(){
  if(!st)return;
  const a=document.getElementById("angelStatus");a.textContent=st.angel_connected?"Connected":"Fallback";a.className=st.angel_connected?"ok":"warn";
  const mk=document.getElementById("marketStatus");mk.textContent=st.market_open?"OPEN":"CLOSED";mk.style.color=st.market_open?"#10b981":"#f87171";
  document.getElementById("lastScan").textContent=st.last_scan||"--:--:--";
  const t1=st.touches||[],inst=st.institutional||[];notifyNewTouches(t1);
  document.getElementById("touchCount").textContent=t1.length;document.getElementById("instCount").textContent=inst.length;document.getElementById("badge1d").textContent=t1.length;document.getElementById("badgeInst").textContent=inst.length;
  const bn=document.getElementById("refreshBanner");bn.style.display=st.is_refreshing?"block":"none";if(st.is_refreshing)bn.textContent=`Refreshing Zones... ${st.refresh_progress}`;
  document.getElementById("metaInfo").textContent=`${st.total_zones_1d} 1D zones (${st.demand_zones_1d} demand / ${st.supply_zones_1d} supply) • ${st.total_zones_mtf||0} All-TF zones • tap card for chart`;
  const l1=document.getElementById("list1D"),fl1=t1.filter(t=>f1D==="ALL"||t.zone_type===f1D);
l1.innerHTML=!fl1.length?<div class="empty">${st.market_open?"Scanning live F&O prices...":'Market is closed. Tap "Test Live Scan Now" to check latest closing data.'}</div>:fl1.map(t=>{const fp=t.institutional||{};const ib=fp.is_institutional?(fp.inst_side==="INST_BUYING"?🔥 INST. BUYING • Vol ${fp.vol_ratio}x • Score ${fp.inst_score}%:🔥 INST. SELLING • Vol ${fp.vol_ratio}x • Score ${fp.inst_score}%):"";return <div class="card" onclick="openChart('${t.symbol}','1D','${t.zone_type}',${t.zone_low},${t.zone_high},${t.ltp},'Strength ${t.strength}%','${ib}')"><div class="card-top"><span class="sym">${t.symbol} 📊</span><span class="${t.zone_type==="DEMAND"?"tag-demand":"tag-supply"}">1D ${t.zone_type}</span></div><div class="card-mid"><span>LTP: <b>₹${t.ltp}</b></span><span>Zone: <b>₹${t.zone_low} – ₹${t.zone_high}</b></span></div><div class="meta-line" style="margin:0;">Origin: ${t.origin_ts} • Strength: ${t.strength}% • Tap for Chart</div></div>;}).join("");
const li=document.getElementById("listInst"),fli=inst.filter(x=>(fTF==="ALL"||x.timeframe===fTF)&&(fSide==="ALL"||x.inst_side===fSide));
li.innerHTML=!fli.length?<div class="empty">No strong institutional footprint for selected filter right now.<br><br>Swipe right ➔ to return to 1D Zones.</div>:fli.map(x=>{const ib=x.inst_side==="INST_BUYING",rs=(x.reasons||[]).map(r=><span class="inst-chip">${r}</span>).join(""),ob=ib?${x.buy_sell_ratio}x Buy:${x.sell_buy_ratio}x Sell,banner=${ib?"🔥 INST. BUYING":"🔥 INST. SELLING"} • Vol ${x.vol_ratio}x • Order Book ${ob} • Score ${x.inst_score}%;return <div class="card" style="border-left:4px solid ${ib?"#10b981":"#ef4444"};" onclick="openChart('${x.symbol}','${x.timeframe}','${x.zone_type}',${x.zone_low},${x.zone_high},${x.ltp},'Vol ${x.vol_ratio}x','${banner}')"><div class="card-top"><div><span class="tag-tf">${x.timeframe}</span><span class="sym">${x.symbol} 📊</span></div><span class="${ib?"tag-demand":"tag-supply"}">${ib?"🔥 INST. BUYING":"🔥 INST. SELLING"}</span></div><div class="card-mid"><span>LTP: <b>₹${x.ltp}</b></span><span>Zone: <b>₹${x.zone_low} – ₹${x.zone_high}</b></span></div><div class="meta-line" style="margin:0;">Vol: <b>${x.vol_ratio}x</b> • Order Book: <b>${ob}</b> • Tap for Chart</div><div class="inst-badges">${rs}</div></div>;}).join("");
}
async function fetchState(){try{const r=await fetch("/api/state");if(r.ok){st=await r.json();renderAll();}}catch(e){}}
fetchState();setInterval(fetchState,8000);
