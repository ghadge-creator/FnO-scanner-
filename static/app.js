let curPage=0,f1D="ALL",fTF="ALL",fSide="ALL",snd=false,alr=false,st=null,sx=0,sy=0,seenAlerts=new Set();
const box=document.getElementById("swipeContainer");
document.addEventListener("touchstart",e=>{if(!document.getElementById("chartModal").classList.contains("open")){sx=e.changedTouches.screenX;sy=e.changedTouches.screenY;}},{passive:true});
document.addEventListener("touchend",e=>{if(document.getElementById("chartModal").classList.contains("open"))return;const dx=e.changedTouches.screenX-sx,dy=e.changedTouches.screenY-sy;if(Math.abs(dx)>55&&Math.abs(dx)>Math.abs(dy)*1.4){if(dx<0&&curPage===0)goToPage(1);if(dx>0&&curPage===1)goToPage(0);}},{passive:true});
function goToPage(i){curPage=i;box.style.transform=`translateX(-${i*100}vw)`;document.getElementById("tab0").classList.toggle("active",i===0);document.getElementById("tab1").classList.toggle("active",i===1);}
function setFilter1D(v,el){f1D=v;el.parentElement.querySelectorAll(".pill").forEach(p=>p.classList.remove("active"));el.classList.add("active");renderAll();}
function setTfFilter(v,el){fTF=v;el.parentElement.querySelectorAll(".tf-pill").forEach(p=>p.classList.remove("active"));el.classList.add("active");renderAll();}
function setInstSideFilter(v,el){fSide=v;el.parentElement.querySelectorAll(".pill").forEach(p=>p.classList.remove("active"));el.classList.add("active");renderAll();}
function playBeep(){try{const c=new(window.AudioContext||window.webkitAudioContext)(),o=c.createOscillator(),g=c.createGain();o.type="sine";o.frequency.value=880;g.gain.value=0.25;o.connect(g);g.connect(c.destination);o.start();setTimeout(()=>{o.frequency.value=1175;},150);setTimeout(()=>{o.stop();c.close();},350);}catch(e){}}
function toggleSound(){snd=!snd;if(snd)playBeep();const b=document.getElementById("soundBtn");b.textContent=snd?"🔊 Sound: ON":"🔇 Sound: OFF";b.classList.toggle("on",snd);}
function toggleAlerts(){alr=!alr;if(alr&&"Notification"in window)Notification.requestPermission();const b=document.getElementById("alertBtn");b.textContent=alr?"🔔 Alerts: ON":"🔕 Alerts: OFF";b.classList.toggle("on",alr);}
function notifyNewTouches(list){
  let isNew=false;
  list.forEach(t=>{const k=`${t.symbol}:${t.zone_type}:${t.zone_low}`;if(!seenAlerts.has(k)){seenAlerts.add(k);isNew=true;if(alr&&"Notification"in window&&Notification.permission==="granted"){new Notification(`🚨 1D ${t.zone_type}: ${t.symbol} @ ₹${t.ltp}`,{body:`Zone ₹${t.zone_low} – ₹${t.zone_high}`});}}});
  if(isNew&&snd)playBeep();
}
async function triggerScan(){await fetch("/api/scan",{method:"POST"});fetchState();}
async function triggerRefresh(){await fetch("/api/refresh",{method:"POST"});fetchState();}
function closeChart(){document.getElementById("chartModal").classList.remove("open");document.getElementById("tvChart").innerHTML="";}
function openChart(sym,tf,zt,zl,zh,ltp,ex){
  const m=document.getElementById("chartModal"),el=document.getElementById("tvChart");
  document.getElementById("mTitle").textContent=`${sym} (${tf}) • ₹${ltp}`;
  document.getElementById("mSub").textContent=`${zt} Zone: ₹${zl} – ₹${zh} ${ex?"• "+ex:""}`;
  m.classList.add("open");
  el.innerHTML=`<div id="tv_embed_box" style="width:100%;height:100%;"></div>`;
  const tvIv={"5m":"5","15m":"15","1H":"60","1D":"D","1W":"W"}[tf]||"D";
  const tvSym="NSE:"+sym.replace("-EQ","").replace("&","_");
  const initTV=()=>{new TradingView.widget({autosize:true,symbol:tvSym,interval:tvIv,timezone:"Asia/Kolkata",theme:"dark",style:"1",locale:"en",toolbar_bg:"#111827",enable_publishing:false,hide_top_toolbar:false,hide_legend:false,save_image:false,container_id:"tv_embed_box"});};
  if(window.TradingView){initTV();}else{const s=document.createElement("script");s.src="https://tradingview.com";s.onload=initTV;document.head.appendChild(s);}
}
function renderAll(){
  if(!st)return;
  const a=document.getElementById("angelStatus");a.textContent=st.angel_connected?"Connected":"Fallback";a.className=st.angel_connected?"ok":"warn";
  const mk=document.getElementById("marketStatus");mk.textContent=st.market_open?"OPEN":"CLOSED";mk.style.color=st.market_open?"#10b981":"#f87171";
  document.getElementById("lastScan").textContent=st.last_scan||"--:--:--";
  const t1=st.touches||[],inst=st.institutional||[];
  notifyNewTouches(t1);
  document.getElementById("touchCount").textContent=t1.length;document.getElementById("instCount").textContent=inst.length;
  document.getElementById("badge1d").textContent=t1.length;document.getElementById("badgeInst").textContent=inst.length;
  const bn=document.getElementById("refreshBanner");bn.style.display=st.is_refreshing?"block":"none";if(st.is_refreshing)bn.textContent=`Refreshing Zones... ${st.refresh_progress}`;
  document.getElementById("metaInfo").textContent=`${st.total_zones_1d} 1D zones (${st.demand_zones_1d} demand / ${st.supply_zones_1d} supply) • ${st.total_zones_mtf||0} All-TF zones • tap card for chart`;
  const l1=document.getElementById("list1D"),fl1=t1.filter(t=>f1D==="ALL"||t.zone_type===f1D);
  l1.innerHTML=!fl1.length?`<div class="empty">${st.market_open?"Scanning live F&O prices...":'Market is closed. Tap "Test Live Scan Now" to check latest closing data.'}</div>`:fl1.map(t=>`<div class="card" onclick="openChart('${t.symbol}','1D','${t.zone_type}',${t.zone_low},${t.zone_high},${t.ltp},'Strength ${t.strength}%')"><div class="card-top"><span class="sym">${t.symbol} 📊</span><span class="${t.zone_type==="DEMAND"?"tag-demand":"tag-supply"}">1D ${t.zone_type}</span></div><div class="card-mid"><span>LTP: <b>₹${t.ltp}</b></span><span>Zone: <b>₹${t.zone_low} – ₹${t.zone_high}</b></span></div><div class="meta-line" style="margin:0;">Origin: ${t.origin_ts} • Strength: ${t.strength}% • Tap for TradingView chart</div></div>`).join("");
  const li=document.getElementById("listInst"),fli=inst.filter(x=>(fTF==="ALL"||x.timeframe===fTF)&&(fSide==="ALL"||x.inst_side===fSide));
  li.innerHTML=!fli.length?`<div class="empty">No strong institutional footprint for selected filter right now.<br><br>Swipe right ➔ to return to 1D Zones.</div>`:fli.map(x=>{const ib=x.inst_side==="INST_BUYING",rs=(x.reasons||[]).map(r=>`<span class="inst-chip">${r}</span>`).join("");return `<div class="card" style="border-left:4px solid ${ib?"#10b981":"#ef4444"};" onclick="openChart('${x.symbol}','${x.timeframe}','${x.zone_type}',${x.zone_low},${x.zone_high},${x.ltp},'Vol ${x.vol_ratio}x')"><div class="card-top"><div><span class="tag-tf">${x.timeframe}</span><span class="sym">${x.symbol} 📊</span></div><span class="${ib?"tag-demand":"tag-supply"}">${ib?"🔥 INST. BUYING":"🔥 INST. SELLING"}</span></div><div class="card-mid"><span>LTP: <b>₹${x.ltp}</b></span><span>Zone: <b>₹${x.zone_low} – ₹${x.zone_high}</b></span></div><div class="meta-line" style="margin:0;">Vol: <b>${x.vol_ratio}x</b> • Order Book: <b>${ib?x.buy_sell_ratio+"x Buy":x.sell_buy_ratio+"x Sell"}</b> • Tap for TradingView chart</div><div class="inst-badges">${rs}</div></div>`;}).join("");
}
async function fetchState(){try{const r=await fetch("/api/state");if(r.ok){st=await r.json();renderAll();}}catch(e){}}
fetchState();setInterval(fetchState,8000);
