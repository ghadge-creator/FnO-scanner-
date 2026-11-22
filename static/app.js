if("serviceWorker"in navigator){navigator.serviceWorker.getRegistrations().then(r=>r.forEach(x=>x.unregister()));}
let pg=0,f1="ALL",ft="ALL",fs="ALL",sn=false,al=false,st=null,sx=0,sy=0,seen=new Set(),cd=[],cm=null,vc=65,po=0,yScale=1.0,dragMode="",dx0=0,dy0=0,pd0=0,ind={e20:true,e50:true,vol:true};
const wp=document.getElementById("wp"),cv=document.getElementById("cvs"),cx=cv.getContext("2d");
document.addEventListener("touchstart",e=>{if(!document.getElementById("md").classList.contains("on")){sx=e.changedTouches.item(0).screenX;sy=e.changedTouches.item(0).screenY;}},{passive:true});
document.addEventListener("touchend",e=>{if(document.getElementById("md").classList.contains("on"))return;const dx=e.changedTouches.item(0).screenX-sx,dy=e.changedTouches.item(0).screenY-sy;if(Math.abs(dx)>55&&Math.abs(dx)>Math.abs(dy)*1.4){if(dx<0&&pg===0)go(1);if(dx>0&&pg===1)go(0);}},{passive:true});
cv.addEventListener("touchstart",e=>{
  if(e.touches.length===1){dx0=e.touches.item(0).clientX;dy0=e.touches.item(0).clientY;dragMode=(dx0>cv.clientWidth-68)?"yscale":"pan";}
  else if(e.touches.length===2){dragMode="pinch";pd0=Math.hypot(e.touches.item(0).clientX-e.touches.item(1).clientX,e.touches.item(0).clientY-e.touches.item(1).clientY);}
},{passive:true});
cv.addEventListener("touchmove",e=>{
  if(!cd.length)return;
  if(e.touches.length===1&&dragMode==="yscale"){const y=e.touches.item(0).clientY,dy=y-dy0;yScale=Math.max(0.45,Math.min(2.8,yScale*(1+dy*0.006)));dy0=y;drw();}
  else if(e.touches.length===1&&dragMode==="pan"){const x=e.touches.item(0).clientX,sh=Math.round((x-dx0)/Math.max(2.5,(cv.clientWidth-68)/vc));if(sh!==0){po=Math.max(0,Math.min(Math.max(0,cd.length-vc),po+sh));dx0=x;drw();}}
  else if(e.touches.length===2){const d=Math.hypot(e.touches.item(0).clientX-e.touches.item(1).clientX,e.touches.item(0).clientY-e.touches.item(1).clientY);if(Math.abs(d-pd0)>12){zm(d>pd0?-6:6);pd0=d;}}
},{passive:true});
function go(i){pg=i;wp.style.transform=`translateX(-${i*100}vw)`;document.getElementById("t0").classList.toggle("on",i===0);document.getElementById("t1").classList.toggle("on",i===1);}
function act(el){el.parentElement.querySelectorAll(".pill").forEach(p=>p.classList.remove("on"));el.classList.add("on");}
function sf1(v,el){f1=v;act(el);rnd();}function stf(v,el){ft=v;act(el);rnd();}function ssd(v,el){fs=v;act(el);rnd();}
function ti(k,el){ind[k]=!ind[k];el.classList.toggle("on",ind[k]);drw();}
function zm(d){if(!cd.length)return;vc=Math.max(15,Math.min(cd.length,vc+d));po=Math.min(po,Math.max(0,cd.length-vc));drw();}
function beep(){try{const c=new(window.AudioContext||window.webkitAudioContext)(),o=c.createOscillator(),g=c.createGain();o.frequency.value=950;g.gain.value=0.25;o.connect(g);g.connect(c.destination);o.start();setTimeout(()=>{o.stop();c.close();},280);}catch(e){}}
function togS(){sn=!sn;if(sn)beep();const b=document.getElementById("sb");b.textContent=sn?"🔊 Sound: ON":"🔇 Sound: OFF";b.classList.toggle("on",sn);}
function togA(){al=!al;if(al&&"Notification"in window)Notification.requestPermission();const b=document.getElementById("ab");b.textContent=al?"🔔 Alerts: ON":"🔕 Alerts: OFF";b.classList.toggle("on",al);}
async function scan(){await fetch("/api/scan",{method:"POST"});load();}
async function ref(){await fetch("/api/refresh",{method:"POST"});load();}
function cls(){document.getElementById("md").classList.remove("on");}
function ema(a,p){if(!a.length)return[];const k=2/(p+1),o=[];let v=a.at(0).c;a.forEach((c,i)=>{v=i===0?c.c:(c.c*k+v*(1-k));o.push(v);});return o;}
async function opn(sym,tf,zt,zl,zh,ltp,ex,ib){
  document.getElementById("m1").textContent=`${sym} (${tf}) • ₹${ltp}`;document.getElementById("m2").textContent=`${zt} Zone: ₹${zl} – ₹${zh} • Drag Right Scale ↕`;
  const b=document.getElementById("ib");if(ib){b.style.display="block";b.textContent=ib;b.style.color=ib.includes("BUYING")?"#34d399":"#f87171";}else b.style.display="none";
  document.getElementById("md").classList.add("on");cd=[];cm={zt,zl:+zl,zh:+zh,ltp:+ltp};po=0;vc=65;yScale=1.0;
  const h=window.innerHeight-90-(ib?28:0);cv.width=window.innerWidth;cv.height=h;
  cx.fillStyle="#0b0f17";cx.fillRect(0,0,cv.width,h);cx.fillStyle="#9ca3af";cx.font="14px sans-serif";cx.fillText("Loading chart...",40,120);
  try{const r=await fetch(`/api/chart/${encodeURIComponent(sym)}?tf=${encodeURIComponent(tf)}`),d=await r.json();cd=d.candles||[];vc=Math.min(65,cd.length||65);drw();}catch(e){cx.fillText("Chart error",40,120);}
}
function drw(){
  const w=cv.width,h=cv.height;cx.fillStyle="#0b0f17";cx.fillRect(0,0,w,h);
  if(!cd.length||!cm){cx.fillStyle="#9ca3af";cx.fillText("No candles right now",60,120);return;}
  const e2=ema(cd,20),e5=ema(cd,50),ed=cd.length-po,bg=Math.max(0,ed-vc),sl=cd.slice(bg,ed),s2=e2.slice(bg,ed),s5=e5.slice(bg,ed);
  const pL=8,pR=66,pT=18,pB=24,cw=w-pL-pR,ch=h-pT-pB;
  let rMin=Math.min(cm.zl,cm.ltp,...sl.map(c=>c.l)),rMax=Math.max(cm.zh,cm.ltp,...sl.map(c=>c.h));
  const mid=(rMax+rMin)/2,half=((rMax-rMin)/2||1)*1.08*yScale,mn=mid-half,mx=mid+half;
  const y=p=>pT+((mx-p)/(mx-mn))*ch;
  cx.fillStyle="#0f172a";cx.fillRect(pL+cw,0,pR,h);
  cx.strokeStyle="#1f2937";cx.lineWidth=1;cx.beginPath();cx.moveTo(pL+cw,0);cx.lineTo(pL+cw,h);cx.stroke();
  cx.font="11px sans-serif";
  for(let g=0;g<=6;g++){const gy=pT+(ch*g)/6,gp=mx-((mx-mn)*g)/6;cx.strokeStyle="#1a2232";cx.beginPath();cx.moveTo(pL,gy);cx.lineTo(pL+cw,gy);cx.stroke();cx.fillStyle="#9ca3af";cx.fillText(gp.toFixed(1),pL+cw+6,gy+4);}
  const yt=y(cm.zh),yb=y(cm.zl),isD=cm.zt==="DEMAND";
  cx.fillStyle=isD?"rgba(16,185,129,.22)":"rgba(239,68,68,.22)";cx.fillRect(pL,yt,cw,Math.max(6,yb-yt));
  cx.strokeStyle=isD?"#10b981":"#ef4444";cx.lineWidth=1.5;cx.strokeRect(pL,yt,cw,Math.max(6,yb-yt));
  cx.fillStyle=isD?"#34d399":"#f87171";cx.font="bold 11px sans-serif";cx.fillText(`${cm.zt} ZONE`,pL+6,Math.max(pT+12,yt-4));
  const sp=cw/sl.length,bw=Math.max(2.5,sp*0.64),mv=Math.max(1,...sl.map(c=>c.v||0));
  sl.forEach((c,i)=>{const x=pL+i*sp+sp/2,up=c.c>=c.o;if(ind.vol&&(c.v||0)>0){const vh=((c.v||0)/mv)*(ch*0.26);cx.fillStyle=up?"rgba(16,185,129,0.65)":"rgba(239,68,68,0.65)";cx.fillRect(x-bw/2,pT+ch-vh,bw,vh);}cx.strokeStyle=up?"#10b981":"#ef4444";cx.fillStyle=up?"#10b981":"#ef4444";cx.beginPath();cx.moveTo(x,y(c.h));cx.lineTo(x,y(c.l));cx.stroke();const tb=y(Math.max(c.o,c.c)),bb=y(Math.min(c.o,c.c));cx.fillRect(x-bw/2,tb,bw,Math.max(1.5,bb-tb));});
  if(ind.e20){cx.strokeStyle="#f59e0b";cx.lineWidth=1.5;cx.beginPath();s2.forEach((v,i)=>{const x=pL+i*sp+sp/2;i===0?cx.moveTo(x,y(v)):cx.lineTo(x,y(v));});cx.stroke();}
  if(ind.e50){cx.strokeStyle="#a855f7";cx.lineWidth=1.5;cx.beginPath();s5.forEach((v,i)=>{const x=pL+i*sp+sp/2;i===0?cx.moveTo(x,y(v)):cx.lineTo(x,y(v));});cx.stroke();}
  const yl=y(cm.ltp);cx.save();cx.setLineDash();cx.strokeStyle="#38bdf8";cx.lineWidth=2;cx.beginPath();cx.moveTo(pL,yl);cx.lineTo(pL+cw,yl);cx.stroke();cx.restore();
  cx.fillStyle="#0284c7";cx.fillRect(pL+cw+2,yl-9,pR-4,18);cx.fillStyle="#fff";cx.font="bold 11px sans-serif";cx.fillText(cm.ltp.toFixed(1),pL+cw+6,yl+4);
  cx.fillStyle="#9ca3af";cx.font="10px sans-serif";if(sl.at(0))cx.fillText(sl.at(0).t,pL+4,h-6);if(sl.at(-1))cx.fillText(sl.at(-1).t,pL+cw-95,h-6);
}
function rnd(){
  if(!st)return;
  const a=document.getElementById("ag");a.textContent=st.angel_connected?"Connected":"Fallback";a.className=st.angel_connected?"ok":"warn";
  const m=document.getElementById("mk");m.textContent=st.market_open?"OPEN":"CLOSED";m.style.color=st.market_open?"#10b981":"#f87171";
  document.getElementById("ls").textContent=st.last_scan||"--:--:--";
  const t1=st.touches||[],ins=st.institutional||[];
  let nw=false;t1.forEach(t=>{const k=`${t.symbol}:${t.zone_type}`;if(!seen.has(k)){seen.add(k);nw=true;if(al&&"Notification"in window&&Notification.permission==="granted")new Notification(`🚨 1D ${t.zone_type}: ${t.symbol} @ ₹${t.ltp}`);}});if(nw&&sn)beep();
  document.getElementById("tc").textContent=t1.length;document.getElementById("ic").textContent=ins.length;document.getElementById("b0").textContent=t1.length;document.getElementById("b1").textContent=ins.length;
  const rb=document.getElementById("rb");rb.style.display=st.is_refreshing?"block":"none";if(st.is_refreshing)rb.textContent=`Refreshing... ${st.refresh_progress}`;
  document.getElementById("mt").textContent=`${st.total_zones_1d} 1D zones (${st.demand_zones_1d} demand / ${st.supply_zones_1d} supply) • tap card for chart`;
  const l1=document.getElementById("l1"),fl1=t1.filter(t=>f1==="ALL"||t.zone_type===f1);
  l1.innerHTML=!fl1.length?`<div class="empty">${st.market_open?"Scanning live prices...":'Market closed. Tap "Test Live Scan Now".'}</div>`:fl1.map(t=>`<div class="card" onclick="opn('${t.symbol}','1D','${t.zone_type}',${t.zone_low},${t.zone_high},${t.ltp},'Strength ${t.strength}%','')"><div class="ctop"><span class="sym">${t.symbol} 📊</span><span class="${t.zone_type==="DEMAND"?"td":"ts"}">1D ${t.zone_type}</span></div><div class="cmid"><span>LTP: <b>₹${t.ltp}</b></span><span>Zone: <b>₹${t.zone_low} – ₹${t.zone_high}</b></span></div><div class="meta" style="margin:0">Origin: ${t.origin_ts} • Strength: ${t.strength}%</div></div>`).join("");
  const l2=document.getElementById("l2"),fl2=ins.filter(x=>(ft==="ALL"||x.timeframe===ft)&&(fs==="ALL"||x.inst_side===fs));
  cx.fillStyle=isD?"rgba(16,185,129,.22)":"rgba(239,68,68,.22)";cx.fillRect(pL,yt,cw,Math.max(6,yb-yt));
  cx.strokeStyle=isD?"#10b981":"#ef4444";cx.lineWidth=1.5;cx.strokeRect(pL,yt,cw,Math.max(6,yb-yt));
  cx.fillStyle=isD?"#34d399":"#f87171";cx.font="bold 11px sans-serif";cx.fillText(`${cm.zt} ZONE`,pL+6,Math.max(pT+12,yt-4));
  const sp=cw/sl.length,bw=Math.max(2.5,sp*0.64),mv=Math.max(1,...sl.map(c=>c.v||0));
  sl.forEach((c,i)=>{const x=pL+i*sp+sp/2,up=c.c>=c.o;if(ind.vol&&(c.v||0)>0){const vh=((c.v||0)/mv)*(ch*0.26);cx.fillStyle=up?"rgba(16,185,129,0.65)":"rgba(239,68,68,0.65)";cx.fillRect(x-bw/2,pT+ch-vh,bw,vh);}cx.strokeStyle=up?"#10b981":"#ef4444";cx.fillStyle=up?"#10b981":"#ef4444";cx.beginPath();cx.moveTo(x,y(c.h));cx.lineTo(x,y(c.l));cx.stroke();const tb=y(Math.max(c.o,c.c)),bb=y(Math.min(c.o,c.c));cx.fillRect(x-bw/2,tb,bw,Math.max(1.5,bb-tb));});
  if(ind.e20){cx.strokeStyle="#f59e0b";cx.lineWidth=1.5;cx.beginPath();s2.forEach((v,i)=>{const x=pL+i*sp+sp/2;i===0?cx.moveTo(x,y(v)):cx.lineTo(x,y(v));});cx.stroke();}
  if(ind.e50){cx.strokeStyle="#a855f7";cx.lineWidth=1.5;cx.beginPath();s5.forEach((v,i)=>{const x=pL+i*sp+sp/2;i===0?cx.moveTo(x,y(v)):cx.lineTo(x,y(v));});cx.stroke();}
  const yl=y(cm.ltp);cx.save();cx.setLineDash();cx.strokeStyle="#38bdf8";cx.lineWidth=2;cx.beginPath();cx.moveTo(pL,yl);cx.lineTo(pL+cw,yl);cx.stroke();cx.restore();
  cx.fillStyle="#0284c7";cx.fillRect(pL+cw+2,yl-9,pR-4,18);cx.fillStyle="#fff";cx.font="bold 11px sans-serif";cx.fillText(cm.ltp.toFixed(1),pL+cw+6,yl+4);
  cx.fillStyle="#9ca3af";cx.font="10px sans-serif";if(sl.at(0))cx.fillText(sl.at(0).t,pL+4,h-6);if(sl.at(-1))cx.fillText(sl.at(-1).t,pL+cw-95,h-6);
}
function rnd(){
  if(!st)return;
  const a=document.getElementById("ag");a.textContent=st.angel_connected?"Connected":"Fallback";a.className=st.angel_connected?"ok":"warn";
  const m=document.getElementById("mk");m.textContent=st.market_open?"OPEN":"CLOSED";m.style.color=st.market_open?"#10b981":"#f87171";
  document.getElementById("ls").textContent=st.last_scan||"--:--:--";
  const t1=st.touches||[],ins=st.institutional||[];
  let nw=false;t1.forEach(t=>{const k=`${t.symbol}:${t.zone_type}`;if(!seen.has(k)){seen.add(k);nw=true;if(al&&"Notification"in window&&Notification.permission==="granted")new Notification(`🚨 1D ${t.zone_type}: ${t.symbol} @ ₹${t.ltp}`);}});if(nw&&sn)beep();
  document.getElementById("tc").textContent=t1.length;document.getElementById("ic").textContent=ins.length;document.getElementById("b0").textContent=t1.length;document.getElementById("b1").textContent=ins.length;
  const rb=document.getElementById("rb");rb.style.display=st.is_refreshing?"block":"none";if(st.is_refreshing)rb.textContent=`Refreshing... ${st.refresh_progress}`;
  document.getElementById("mt").textContent=`${st.total_zones_1d} 1D zones (${st.demand_zones_1d} demand / ${st.supply_zones_1d} supply) • tap card for chart`;
  const l1=document.getElementById("l1"),fl1=t1.filter(t=>f1==="ALL"||t.zone_type===f1);
  l1.innerHTML=!fl1.length?`<div class="empty">${st.market_open?"Scanning live prices...":'Market closed. Tap "Test Live Scan Now".'}</div>`:fl1.map(t=>`<div class="card" onclick="opn('${t.symbol}','1D','${t.zone_type}',${t.zone_low},${t.zone_high},${t.ltp},'Strength ${t.strength}%','')"><div class="ctop"><span class="sym">${t.symbol} 📊</span><span class="${t.zone_type==="DEMAND"?"td":"ts"}">1D ${t.zone_type}</span></div><div class="cmid"><span>LTP: <b>₹${t.ltp}</b></span><span>Zone: <b>₹${t.zone_low} – ₹${t.zone_high}</b></span></div><div class="meta" style="margin:0">Origin: ${t.origin_ts} • Strength: ${t.strength}%</div></div>`).join("");
  const l2=document.getElementById("l2"),fl2=ins.filter(x=>(ft==="ALL"||x.timeframe===ft)&&(fs==="ALL"||x.inst_side===fs));
Use code with caution.
l2.innerHTML=!fl2.length?<div class="empty">No institutional orders for filter right now.</div>:fl2.map(x=>{const ib=x.inst_side==="INST_BUYING",bn=${ib?"🔥 INST. BUYING":"🔥 INST. SELLING"} • Vol ${x.vol_ratio}x • Score ${x.inst_score}%;return <div class="card" style="border-left:4px solid ${ib?"#10b981":"#ef4444"}" onclick="opn('${x.symbol}','${x.timeframe}','${x.zone_type}',${x.zone_low},${x.zone_high},${x.ltp},'Vol ${x.vol_ratio}x','${bn}')"><div class="ctop"><span class="sym">[${x.timeframe}] ${x.symbol} 📊</span><span class="${ib?"td":"ts"}">${ib?"🔥 INST. BUY":"🔥 INST. SELL"}</span></div><div class="cmid"><span>LTP: <b>₹${x.ltp}</b></span><span>Zone: <b>₹${x.zone_low} – ₹${x.zone_high}</b></span></div><div class="meta" style="margin:0">Vol: ${x.vol_ratio}x • Score: ${x.inst_score}%</div></div>;}).join("");
}
async function load(){try{const r=await fetch("/api/state");if(r.ok){st=await r.json();rnd();}}catch(e){}}
load();setInterval(load,8000);
