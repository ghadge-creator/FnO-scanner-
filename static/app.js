let currentPage = 0, filter1D = "ALL", filterTF = "ALL", filterInstSide = "ALL";
let soundOn = false, alertsOn = false, latestState = null, tvChartObj = null;
let touchStartX = 0, touchStartY = 0;
const container = document.getElementById("swipeContainer");

document.addEventListener("touchstart", (e) => {
  if (document.getElementById("chartModal").classList.contains("open")) return;
  touchStartX = e.changedTouches.screenX;
  touchStartY = e.changedTouches.screenY;
}, { passive: true });

document.addEventListener("touchend", (e) => {
  if (document.getElementById("chartModal").classList.contains("open")) return;
  const dx = e.changedTouches.screenX - touchStartX;
  const dy = e.changedTouches.screenY - touchStartY;
  if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.4) {
    if (dx < 0 && currentPage === 0) goToPage(1);
    if (dx > 0 && currentPage === 1) goToPage(0);
  }
}, { passive: true });

function goToPage(idx) {
  currentPage = idx;
  container.style.transform = `translateX(-${idx * 100}vw)`;
  document.getElementById("tab0").classList.toggle("active", idx === 0);
  document.getElementById("tab1").classList.toggle("active", idx === 1);
}

function setFilter1D(val, el) {
  filter1D = val;
  el.parentElement.querySelectorAll(".pill").forEach((p) => p.classList.remove("active"));
  el.classList.add("active");
  renderAll();
}

function setTfFilter(val, el) {
  filterTF = val;
  el.parentElement.querySelectorAll(".tf-pill").forEach((p) => p.classList.remove("active"));
  el.classList.add("active");
  renderAll();
}

function setInstSideFilter(val, el) {
  filterInstSide = val;
  el.parentElement.querySelectorAll(".pill").forEach((p) => p.classList.remove("active"));
  el.classList.add("active");
  renderAll();
}

function toggleSound() {
  soundOn = !soundOn;
  const btn = document.getElementById("soundBtn");
  btn.textContent = soundOn ? "🔊 Sound: ON" : "🔇 Sound: OFF";
  btn.classList.toggle("on", soundOn);
}

function toggleAlerts() {
  alertsOn = !alertsOn;
  if (alertsOn && "Notification" in window) Notification.requestPermission();
  const btn = document.getElementById("alertBtn");
  btn.textContent = alertsOn ? "🔔 Alerts: ON" : "🔕 Alerts: OFF";
  btn.classList.toggle("on", alertsOn);
}

async function triggerScan() { await fetch("/api/scan", { method: "POST" }); fetchState(); }
async function triggerRefresh() { await fetch("/api/refresh", { method: "POST" }); fetchState(); }

function closeChart() {
  document.getElementById("chartModal").classList.remove("open");
  if (tvChartObj) { tvChartObj.remove(); tvChartObj = null; }
}

async function openChart(sym, tf, zType, zLow, zHigh, ltp, extraText) {
  const modal = document.getElementById("chartModal");
  document.getElementById("mTitle").textContent = `${sym} (${tf}) • ₹${ltp}`;
  document.getElementById("mSub").textContent = `${zType} Zone: ₹${zLow} – ₹${zHigh} ${extraText ? "• " + extraText : ""}`;
  modal.classList.add("open");

  const chartEl = document.getElementById("tvChart");
  chartEl.innerHTML = "";
  if (tvChartObj) { tvChartObj.remove(); tvChartObj = null; }

  try {
    const res = await fetch(`/api/chart/${encodeURIComponent(sym)}?tf=${encodeURIComponent(tf)}`);
    const data = await res.json();
    const raw = data.candles || [];
    if (!raw.length) {
      chartEl.innerHTML = `<div style="padding:40px;text-align:center;color:#9ca3af;">No candle data available right now.</div>`;
      return;
    }

    tvChartObj = LightweightCharts.createChart(chartEl, {
      width: chartEl.clientWidth,
      height: chartEl.clientHeight,
      layout: { background: { color: "#0b0f17" }, textColor: "#d1d5db" },
      grid: { vertLines: { color: "#1f2937" }, horzLines: { color: "#1f2937" } },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#374151" },
      timeScale: { borderColor: "#374151", timeVisible: tf !== "1D" && tf !== "1W" },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true },
      handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
    });

    const candleSeries = tvChartObj.addCandlestickSeries({
      upColor: "#10b981", downColor: "#ef4444",
      borderUpColor: "#10b981", borderDownColor: "#ef4444",
      wickUpColor: "#10b981", wickDownColor: "#ef4444",
    });

    const seenT = new Set();
    const bars = [];
    raw.forEach((c) => {
      const ts = Math.floor(new Date(c.t.replace(" ", "T")).getTime() / 1000);
      if (!isNaN(ts) && !seenT.has(ts)) {
        seenT.add(ts);
        bars.push({ time: ts, open: c.o, high: c.h, low: c.l, close: c.c });
      }
    });
    bars.sort((a, b) => a.time - b.time);
    candleSeries.setData(bars);

    const zColor = zType === "DEMAND" ? "#10b981" : "#ef4444";
    candleSeries.createPriceLine({ price: zHigh, color: zColor, lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: `${zType} TOP` });
    candleSeries.createPriceLine({ price: zLow, color: zColor, lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: `${zType} BOT` });
    candleSeries.createPriceLine({ price: ltp, color: "#60a5fa", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "LTP" });

    tvChartObj.timeScale().fitContent();
  } catch (e) {
    chartEl.innerHTML = `<div style="padding:40px;text-align:center;color:#f87171;">Error loading interactive chart.</div>`;
  }
}

function renderAll() {
  if (!latestState) return;
  const s = latestState;
  const angelEl = document.getElementById("angelStatus");
  angelEl.textContent = s.angel_connected ? "Connected" : "Fallback";
  angelEl.className = s.angel_connected ? "ok" : "warn";

  const mktEl = document.getElementById("marketStatus");
  mktEl.textContent = s.market_open ? "OPEN" : "CLOSED";
  mktEl.style.color = s.market_open ? "#10b981" : "#f87171";

  document.getElementById("lastScan").textContent = s.last_scan || "--:--:--";
  const touches = s.touches || [], instList = s.institutional || [];
  document.getElementById("touchCount").textContent = touches.length;
  document.getElementById("instCount").textContent = instList.length;
  document.getElementById("badge1d").textContent = touches.length;
  document.getElementById("badgeInst").textContent = instList.length;

  const banner = document.getElementById("refreshBanner");
  banner.style.display = s.is_refreshing ? "block" : "none";
  if (s.is_refreshing) banner.textContent = `Refreshing Zones... ${s.refresh_progress}`;

  document.getElementById("metaInfo").textContent =
    `${s.total_zones_1d} 1D zones (${s.demand_zones_1d} demand / ${s.supply_zones_1d} supply) • ${s.total_zones_mtf || 0} All-TF zones • tap card for chart`;

  const list1D = document.getElementById("list1D");
  const filtered1D = touches.filter((t) => filter1D === "ALL" || t.zone_type === filter1D);
  list1D.innerHTML = !filtered1D.length
    ? `<div class="empty">${s.market_open ? "Scanning live F&O prices..." : 'Market is closed. Tap "Test Live Scan Now" to check latest closing data.'}</div>`
    : filtered1D.map((t) => `
      <div class="card" onclick="openChart('${t.symbol}','1D','${t.zone_type}',${t.zone_low},${t.zone_high},${t.ltp},'Strength ${t.strength}%')">
        <div class="card-top">
          <span class="sym">${t.symbol} 📊</span>
          <span class="${t.zone_type === "DEMAND" ? "tag-demand" : "tag-supply"}">1D ${t.zone_type}</span>
        </div>
        <div class="card-mid">
          <span>LTP: <b>₹${t.ltp}</b></span>
          <span>Zone: <b>₹${t.zone_low} – ₹${t.zone_high}</b></span>
        </div>
        <div class="meta-line" style="margin:0;">Origin: ${t.origin_ts} • Strength: ${t.strength}% • Tap for Chart</div>
      </div>`).join("");

  const listInst = document.getElementById("listInst");
  const filteredInst = instList.filter((item) => (filterTF === "ALL" || item.timeframe === filterTF) && (filterInstSide === "ALL" || item.inst_side === filterInstSide));
  listInst.innerHTML = !filteredInst.length
    ? `<div class="empty">No strong institutional footprint for selected filter right now.<br><br>Swipe right ➔ to return to 1D Zones.</div>`
    : filteredInst.map((item) => {
        const isBuy = item.inst_side === "INST_BUYING";
        const reasonsHtml = (item.reasons || []).map((r) => `<span class="inst-chip">${r}</span>`).join("");
        return `
      <div class="card" style="border-left:4px solid ${isBuy ? "#10b981" : "#ef4444"};" onclick="openChart('${item.symbol}','${item.timeframe}','${item.zone_type}',${item.zone_low},${item.zone_high},${item.ltp},'Vol ${item.vol_ratio}x')">
        <div class="card-top">
          <div><span class="tag-tf">${item.timeframe}</span><span class="sym">${item.symbol} 📊</span></div>
          <span class="${isBuy ? "tag-demand" : "tag-supply"}">${isBuy ? "🔥 INST. BUYING" : "🔥 INST. SELLING"}</span>
        </div>
        <div class="card-mid">
          <span>LTP: <b>₹${item.ltp}</b></span>
          <span>Zone: <b>₹${item.zone_low} – ₹${item.zone_high}</b></span>
        </div>
        <div class="meta-line" style="margin:0;">Vol: <b>${item.vol_ratio}x</b> • Order Book: <b>${isBuy ? item.buy_sell_ratio + "x Buy" : item.sell_buy_ratio + "x Sell"}</b> • Tap for Chart</div>
        <div class="inst-badges">${reasonsHtml}</div>
      </div>`;
      }).join("");
}

async function fetchState() {
  try {
    const res = await fetch("/api/state");
    if (res.ok) { latestState = await res.json(); renderAll(); }
  } catch (e) {}
}
fetchState();
setInterval(fetchState, 8000);
