(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
  const fmt = (n) => (n === null || n === undefined || isNaN(n)) ? '--' :
    Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* ignore */ } },
  };

  let live = [], test = [], shown = [];
  let mode = 'live', filter = 'ALL', status = {};
  let soundOn = store.get('sound', false), notifOn = store.get('notif', false);
  let seen = new Set(), firstLoad = true;
  let audioCtx = null, chart = null, ro = null, deferredInstall = null, toastTimer = null;

  // ---------- helpers ----------
  function toast(msg, ms = 2800) {
    const t = $('toast');
    t.textContent = msg;
    t.classList.remove('hidden');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.add('hidden'), ms);
  }

  function ensureAudio() {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === 'suspended') audioCtx.resume();
  }

  function chime() {
    if (!soundOn) return;
    try {
      ensureAudio();
      const t0 = audioCtx.currentTime;
      [[880, 0], [1175, 0.18], [1568, 0.36]].forEach(([f, d]) => {
        const o = audioCtx.createOscillator();
        const g = audioCtx.createGain();
        o.type = 'sine';
        o.frequency.value = f;
        g.gain.setValueAtTime(0.0001, t0 + d);
        g.gain.exponentialRampToValueAtTime(0.35, t0 + d + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, t0 + d + 0.32);
        o.connect(g); g.connect(audioCtx.destination);
        o.start(t0 + d); o.stop(t0 + d + 0.36);
      });
    } catch (e) { /* audio unavailable */ }
  }

  async function pushNotify(t) {
    if (!notifOn || !('Notification' in window) || Notification.permission !== 'granted') return;
    const title = `${t.side === 'DEMAND' ? '🟢' : '🔴'} ${t.symbol} touched 1D ${t.side}`;
    const body = `LTP ${fmt(t.ltp)} • Zone ${fmt(t.proximal)} – ${fmt(t.distal)} • ${t.pattern} ${t.freshness}`;
    try {
      const reg = await navigator.serviceWorker.ready;
      await reg.showNotification(title, { body, icon: '/icon-192.png', tag: t.id, vibrate: [200, 100, 200] });
    } catch (e) {
      try { new Notification(title, { body }); } catch (_) { /* ignore */ }
    }
  }

  // ---------- rendering ----------
  function renderStatus() {
    const a = $('st-angel');
    a.textContent = status.angel || '--';
    a.className = 'font-semibold ' + (status.angel === 'Connected' ? 'text-emerald-400' : 'text-amber-400');
    const m = $('st-market');
    m.innerHTML = status.market === 'LIVE'
      ? '<span class="pulse-dot inline-block w-2 h-2 rounded-full bg-emerald-400 mr-1"></span>LIVE'
      : 'CLOSED';
    m.className = 'font-semibold ' + (status.market === 'LIVE' ? 'text-emerald-400' : 'text-slate-400');
    $('st-scan').textContent = status.last_scan || '--:--:--';
    $('st-active').textContent = String(live.length);

    const rb = $('refresh-bar');
    if (status.refreshing) { rb.classList.remove('hidden'); $('refresh-progress').textContent = status.progress || ''; }
    else rb.classList.add('hidden');

    const parts = [];
    if (status.zones_total !== undefined)
      parts.push(`${status.zones_total} zones (${status.demand} demand / ${status.supply} supply)`);
    if (status.zones_updated) parts.push(`updated ${status.zones_updated}`);
    if (status.source && status.source !== '-') parts.push(`feed: ${status.source}`);
    if (!status.ready) parts.push('starting up…');
    if (status.angel !== 'Connected' && status.angel_error) parts.push(status.angel_error);
    $('zone-summary').textContent = parts.join(' • ');
  }

  function cardHtml(t, i) {
    const dem = t.side === 'DEMAND';
    const border = dem ? 'border-l-emerald-500' : 'border-l-rose-500';
    const badge = dem ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40'
                      : 'bg-rose-500/15 text-rose-300 border-rose-500/40';
    const fresh = t.freshness === 'Fresh' ? 'bg-sky-500/15 text-sky-300' : 'bg-amber-500/15 text-amber-300';
    const zoneState = mode === 'test' ? '' : (t.in_zone
      ? '<span class="rounded-md bg-yellow-400/20 text-yellow-300 px-2 py-0.5 text-[10px] font-bold">IN ZONE NOW</span>'
      : '<span class="rounded-md bg-slate-700/60 text-slate-300 px-2 py-0.5 text-[10px] font-semibold">TOUCHED</span>');
    return `
    <button data-i="${i}" class="card w-full text-left rounded-2xl bg-slate-900 border border-slate-800 border-l-4 ${border} p-3 active:bg-slate-800 ${t._new ? 'flash' : ''}">
      <div class="flex items-start justify-between">
        <div>
          <div class="text-lg font-bold leading-tight">${esc(t.symbol)}</div>
          <div class="mt-1 flex flex-wrap gap-1.5">
            <span class="rounded-md border px-2 py-0.5 text-[10px] font-bold ${badge}">1D ${dem ? 'Demand' : 'Supply'}</span>
            <span class="rounded-md bg-slate-800 px-2 py-0.5 text-[10px] font-bold text-slate-200">${esc(t.pattern)}</span>
            <span class="rounded-md px-2 py-0.5 text-[10px] font-bold ${fresh}">${esc(t.freshness)}</span>
            ${zoneState}
          </div>
        </div>
        <div class="text-right">
          <div class="text-[10px] text-slate-500">LTP</div>
          <div class="text-lg font-bold font-mono">${fmt(t.ltp)}</div>
        </div>
      </div>
      <div class="mt-2 grid grid-cols-3 gap-2 text-[11px]">
        <div><div class="text-slate-500">Day High</div><div class="font-mono text-slate-200">${fmt(t.high)}</div></div>
        <div><div class="text-slate-500">Day Low</div><div class="font-mono text-slate-200">${fmt(t.low)}</div></div>
        <div><div class="text-slate-500">${mode === 'test' ? 'Candle' : 'Trigger'}</div><div class="font-mono text-slate-200">${esc(t.time)}</div></div>
      </div>
      <div class="mt-2 rounded-lg bg-slate-950/70 px-2 py-1.5 text-[11px] flex justify-between">
        <span class="text-slate-500">Zone (Proximal – Distal)</span>
        <span class="font-mono font-semibold ${dem ? 'text-emerald-300' : 'text-rose-300'}">${fmt(t.proximal)} – ${fmt(t.distal)}</span>
      </div>
    </button>`;
  }

  function render() {
    const src = mode === 'test' ? test : live;
    shown = src.filter((t) => filter === 'ALL' || t.side === filter);
    $('cards').innerHTML = shown.map(cardHtml).join('');
    const empty = $('empty');
    if (shown.length === 0) {
      empty.classList.remove('hidden');
      if (mode === 'test') empty.textContent = 'No stock is touching a 1D zone on the latest closing data.';
      else if (status.market === 'LIVE') empty.textContent = 'Scanning live… no stock has touched a 1-Day zone yet today.';
      else empty.textContent = 'Market is closed. Tap “Test Live Scan Now” to run the scanner on the latest closing data.';
    } else empty.classList.add('hidden');
    document.querySelectorAll('.tab').forEach((b) => {
      const on = b.dataset.filter === filter;
      b.className = 'tab flex-1 rounded-lg py-2 font-semibold ' +
        (on ? 'bg-slate-100 text-slate-900' : 'bg-slate-900 text-slate-300 border border-slate-800');
    });
    $('btn-sound').textContent = soundOn ? '🔔 Sound: ON' : '🔇 Sound: OFF';
    $('btn-notif').textContent = notifOn ? '🔔 Alerts: ON' : '🔕 Alerts: OFF';
    $('test-banner').classList.toggle('hidden', mode !== 'test');
  }

  // ---------- polling ----------
  async function poll() {
    try {
      const r = await fetch('/api/state', { cache: 'no-store' });
      if (!r.ok) throw new Error('bad');
      const d = await r.json();
      status = d.status || {};
      const fresh = [];
      live = (d.touches || []).map((t) => {
        if (!seen.has(t.id)) {
          seen.add(t.id);
          if (!firstLoad) { t._new = true; fresh.push(t); }
        }
        return t;
      });
      firstLoad = false;
      if (fresh.length) {
        chime();
        fresh.forEach(pushNotify);
        toast(`${fresh.length} new 1D zone touch${fresh.length > 1 ? 'es' : ''}: ${fresh.map((t) => t.symbol).slice(0, 3).join(', ')}`);
        if (navigator.vibrate) navigator.vibrate([150, 80, 150]);
      }
      renderStatus();
      if (mode === 'live') render();
    } catch (e) {
      $('st-angel').textContent = 'Offline';
      $('st-angel').className = 'font-semibold text-rose-400';
    }
  }

  // ---------- chart ----------
  async function openChart(t) {
    const dem = t.side === 'DEMAND';
    const color = dem ? '#22c55e' : '#ef4444';
    $('chart-modal').classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    $('chart-title').textContent = `${t.symbol} • 1D`;
    $('chart-sub').textContent = `${dem ? 'Demand' : 'Supply'} ${t.pattern} • ${t.freshness} • LTP ${fmt(t.ltp)}`;
    $('chart-legend').innerHTML =
      `<span style="color:${color}" class="font-semibold">━ Proximal ${fmt(t.proximal)}</span>` +
      `<span class="mx-2 text-slate-600">|</span>` +
      `<span style="color:${color}" class="font-semibold">┅ Distal ${fmt(t.distal)}</span>`;
    const el = $('chart');
    el.innerHTML = '';
    try {
      const r = await fetch(`/api/chart/${encodeURIComponent(t.symbol)}?live=${mode === 'live' ? 1 : 0}`, { cache: 'no-store' });
      const d = await r.json();
      const candles = d.candles || [];
      if (!candles.length) { el.innerHTML = '<p class="p-6 text-center text-slate-500">No candle data yet.</p>'; return; }
      chart = LightweightCharts.createChart(el, {
        width: el.clientWidth, height: el.clientHeight,
        layout: { background: { color: '#0b1220' }, textColor: '#cbd5e1' },
        grid: { vertLines: { color: '#162033' }, horzLines: { color: '#162033' } },
        rightPriceScale: { borderColor: '#334155' },
        timeScale: { borderColor: '#334155', rightOffset: 4 },
        crosshair: { mode: 0 },
      });
      const series = chart.addCandlestickSeries({
        upColor: '#22c55e', downColor: '#ef4444',
        borderUpColor: '#22c55e', borderDownColor: '#ef4444',
        wickUpColor: '#22c55e', wickDownColor: '#ef4444',
      });
      series.setData(candles);
      series.createPriceLine({ price: t.proximal, color, lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: 'Proximal' });
      series.createPriceLine({ price: t.distal, color, lineWidth: 2, lineStyle: 2, axisLabelVisible: true, title: 'Distal' });
      const n = candles.length;
      if (n > 120) chart.timeScale().setVisibleLogicalRange({ from: n - 120, to: n + 3 });
      else chart.timeScale().fitContent();
      ro = new ResizeObserver(() => chart && chart.applyOptions({ width: el.clientWidth, height: el.clientHeight }));
      ro.observe(el);
    } catch (e) {
      el.innerHTML = '<p class="p-6 text-center text-rose-400">Could not load chart.</p>';
    }
  }

  function closeChart() {
    if (ro) { ro.disconnect(); ro = null; }
    if (chart) { chart.remove(); chart = null; }
    $('chart').innerHTML = '';
    $('chart-modal').classList.add('hidden');
    document.body.style.overflow = '';
  }

  // ---------- events ----------
  $('cards').addEventListener('click', (e) => {
    const b = e.target.closest('[data-i]');
    if (b) openChart(shown[Number(b.dataset.i)]);
  });
  $('chart-close').addEventListener('click', closeChart);
  document.querySelectorAll('.tab').forEach((b) =>
    b.addEventListener('click', () => { filter = b.dataset.filter; render(); }));

  $('btn-test').addEventListener('click', async () => {
    const btn = $('btn-test');
    btn.disabled = true; btn.textContent = 'Scanning…';
    try {
      const r = await fetch('/api/test-scan', { method: 'POST' });
      const d = await r.json();
      if (!d.ok) { toast(d.message, 4000); }
      else {
        test = d.touches; mode = 'test';
        $('test-msg').textContent = d.message;
        render();
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    } catch (e) { toast('Test scan failed. Check connection.'); }
    btn.disabled = false; btn.textContent = '▶ Test Live Scan Now';
  });

  $('btn-exit-test').addEventListener('click', () => { mode = 'live'; render(); });

  $('btn-refresh').addEventListener('click', async () => {
    try {
      const r = await fetch('/api/refresh-zones', { method: 'POST' });
      const d = await r.json();
      toast(d.started ? 'Refreshing 1D zones… this takes a few minutes.' : 'A refresh is already running.', 3500);
      poll();
    } catch (e) { toast('Could not start refresh.'); }
  });

  $('btn-sound').addEventListener('click', () => {
    soundOn = !soundOn; store.set('sound', soundOn);
    if (soundOn) { try { ensureAudio(); } catch (e) { /* ignore */ } chime(); }
    render();
  });

  $('btn-notif').addEventListener('click', async () => {
    if (notifOn) { notifOn = false; store.set('notif', false); render(); return; }
    if (!('Notification' in window)) { toast('Notifications are not supported on this browser.'); return; }
    const perm = await Notification.requestPermission();
    notifOn = perm === 'granted';
    store.set('notif', notifOn);
    if (!notifOn) toast('Notification permission was not granted.');
    render();
  });

  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredInstall = e;
    $('btn-install').classList.remove('hidden');
  });
  $('btn-install').addEventListener('click', async () => {
    if (!deferredInstall) return;
    deferredInstall.prompt();
    await deferredInstall.userChoice;
    deferredInstall = null;
    $('btn-install').classList.add('hidden');
  });
  window.addEventListener('appinstalled', () => $('btn-install').classList.add('hidden'));
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
  }

  render();
  poll();
  setInterval(poll, 5000);
})();
