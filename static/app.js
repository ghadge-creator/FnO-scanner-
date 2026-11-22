let currentPage = 0;
let filter1D = "ALL";
let filterTF = "ALL";
let filterInstSide = "ALL";
let soundOn = false;
let alertsOn = false;
let latestState = null;

// WhatsApp-style Touch Swipe Navigation
let touchStartX = 0;
let touchStartY = 0;
const container = document.getElementById("swipeContainer");

document.addEventListener("touchstart", (e) => {
  touchStartX = e.changedTouches[0].screenX;
  touchStartY = e.changedTouches[0].screenY;
}, { passive: true });

document.addEventListener("touchend", (e) => {
  const dx = e.changedTouches[0].screenX - touchStartX;
  const dy = e.changedTouches[0].screenY - touchStartY;
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
  if (alertsOn && "Notification" in window) {
    Notification.requestPermission();
  }
  const btn = document.getElementById("alertBtn");
  btn.textContent = alertsOn ? "🔔 Alerts: ON" : "🔕 Alerts: OFF";
  btn.classList.toggle("on", alertsOn);
}

async function triggerScan() {
  await fetch("/api/scan", { method: "POST" });
  fetchState();
}

async function triggerRefresh() {
  await fetch("/api/refresh", { method: "POST" });
  fetchState();
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
  const touches = s.touches || [];
  const instList = s.institutional || [];

  document.getElementById("touchCount").textContent = touches.length;
  document.getElementById("instCount").textContent = instList.length;
  document.getElementById("badge1d").textContent = touches.length;
  document.getElementById("badgeInst").textContent = instList.length;

  const banner = document.getElementById("refreshBanner");
  if (s.is_refreshing) {
    banner.style.display = "block";
    banner.textContent = `Refreshing Multi-TF Zones... ${s.refresh_progress}`;
  } else {
    banner.style.display = "none";
  }

  document.getElementById("metaInfo").textContent =
    `${s.total_zones_1d} 1D zones (${s.demand_zones_1d} demand / ${s.supply_zones_1d} supply) • ${s.total_zones_mtf || 0} All-TF zones • updated ${s.last_zone_update}`;

  // Render Page 1 (1D Demand & Supply)
  const list1D = document.getElementById("list1D");
  const filtered1D = touches.filter((t) => filter1D === "ALL" || t.zone_type === filter1D);
  if (!filtered1D.length) {
    list1D.innerHTML = `<div class="empty">${
      s.market_open
        ? "Scanning live F&O prices... No 1D zone touch right now."
        : 'Market is closed. Tap "Test Live Scan Now" to check latest closing data.'
    }</div>`;
  } else {
    list1D.innerHTML = filtered1D
      .map(
        (t) => `
      <div class="card">
        <div class="card-top">
          <span class="sym">${t.symbol}</span>
          <span class="${t.zone_type === "DEMAND" ? "tag-demand" : "tag-supply"}">1D ${t.zone_type}</span>
        </div>
        <div class="card-mid">
          <span>LTP: <b>₹${t.ltp}</b></span>
          <span>Zone: <b>₹${t.zone_low} – ₹${t.zone_high}</b></span>
        </div>
        <div class="meta-line" style="margin:0;">Origin: ${t.origin_ts} • Strength: ${t.strength}% • ${t.touched_at}</div>
      </div>`
      )
      .join("");
  }

  // Render Page 2 (All-Timeframe Institutional Orders)
  const listInst = document.getElementById("listInst");
  const filteredInst = instList.filter((item) => {
    const tfOk = filterTF === "ALL" || item.timeframe === filterTF;
    const sideOk = filterInstSide === "ALL" || item.inst_side === filterInstSide;
    return tfOk && sideOk;
  });

  if (!filteredInst.length) {
    listInst.innerHTML = `<div class="empty">No strong institutional buying/selling footprint detected for selected filter right now.<br><br>Swipe right ➔ to return to 1D Zones.</div>`;
  } else {
    listInst.innerHTML = filteredInst
      .map((item) => {
        const isBuy = item.inst_side === "INST_BUYING";
        const reasonsHtml = (item.reasons || [])
          .map((r) => `<span class="inst-chip">${r}</span>`)
          .join("");
        return `
      <div class="card" style="border-left: 4px solid ${isBuy ? "#10b981" : "#ef4444"};">
        <div class="card-top">
          <div><span class="tag-tf">${item.timeframe}</span><span class="sym">${item.symbol}</span></div>
          <span class="${isBuy ? "tag-demand" : "tag-supply"}">${isBuy ? "🔥 INST. BUYING" : "🔥 INST. SELLING"}</span>
        </div>
        <div class="card-mid">
          <span>LTP: <b>₹${item.ltp}</b></span>
          <span>Zone: <b>₹${item.zone_low} – ₹${item.zone_high}</b></span>
        </div>
        <div class="meta-line" style="margin:0;">
          Vol Spike: <b>${item.vol_ratio}x</b> • Buyers/Sellers: <b>${isBuy ? item.buy_sell_ratio + "x Buy" : item.sell_buy_ratio + "x Sell"}</b> • Score: <b>${item.inst_score}%</b>
        </div>
        <div class="inst-badges">${reasonsHtml}</div>
      </div>`;
      })
      .join("");
  }
}

async function fetchState() {
  try {
    const res = await fetch("/api/state");
    if (!res.ok) return;
    latestState = await res.json();
    renderAll();
  } catch (e) {}
}

fetchState();
setInterval(fetchState, 8000);
